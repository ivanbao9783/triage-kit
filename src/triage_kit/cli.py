"""triage CLI: `triage analyze` (badcase attribution) + `triage check`
(task quality inspection).

Backend selection: 'claude' (Claude Agent SDK — also reaches
Anthropic-compatible endpoints such as DeepSeek via ANTHROPIC_BASE_URL).
Future backends (codex SDK, DeepSeek harness SDK) will join --backend.
The trae harness is a skill form, not a CLI option.
"""

import logging
from pathlib import Path

import typer

from triage_kit.core import trial_reader
from triage_kit.core.analyzer import Analyzer, install_trial_log_prefix
from triage_kit.core.assets import get_asset
from triage_kit.core.checker import Checker
from triage_kit.core.rubric import load_rubric

app = typer.Typer(
    add_completion=False,
    help="Badcase triage & task quality check for Harbor-ecosystem evaluation.",
)
logger = logging.getLogger(__name__)


def build_backend(name: str, model: str | None):
    """Map a backend name to a harness satisfying the AgentBackend contract."""
    if name == "claude":
        from triage_kit.backends.claude.harness import ClaudeHarness

        return ClaudeHarness(default_model=model)
    raise ValueError(f"unknown backend {name!r} (expected 'claude')")


def _resolve_check_rubric(value: str | None) -> Path:
    """Accept a rubric file path or a family name (e.g. 'deep-swe')."""
    if value is None:
        return get_asset("check/rubrics/check-default.toml")
    candidate = Path(value)
    if candidate.is_file():
        return candidate
    family = (
        get_asset("check/rubrics/check-default.toml").parent
        / f"check-{value}.toml"
    )
    if family.is_file():
        return family
    raise ValueError(
        f"rubric not found: {value!r} (neither a file nor a known family)"
    )


# Upstream-compatible claude defaults (haiku for analyze, sonnet for
# check); non-Anthropic endpoints pass -m explicitly (e.g.
# deepseek-flash via ANTHROPIC_BASE_URL).
_DEFAULT_MODEL = {"claude": {"analyze": "haiku", "check": "sonnet"}}


def _resolve_model(backend: str, command: str, model: str | None) -> str:
    if model is not None:
        return model
    return _DEFAULT_MODEL[backend][command]


def _fail(message: str) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(1)


@app.command()
def analyze(
    path: Path = typer.Argument(..., help="Trial directory or job directory."),
    failing: bool = typer.Option(
        False, "--failing", help="Job mode: analyze failing trials only."
    ),
    task_dir: Path = typer.Option(
        None, "--task-dir", help="Override the (remote) recorded task path."
    ),
    rubric: Path = typer.Option(
        None, "--rubric", help="Rubric file (default: analyze-rubric.toml)."
    ),
    backend: str = typer.Option(
        "claude", "--backend", help="Agent harness backend (claude)."
    ),
    model: str = typer.Option(
        None, "--model", "-m",
        help="Model name (claude backend default: haiku; pass e.g. "
             "deepseek-flash when using ANTHROPIC_BASE_URL).",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Re-analyze even if cached triage-kit/analysis.json exists "
             "(overwrites).",
    ),
    lang: str = typer.Option(
        "en", "--lang",
        help="Product language: en (default) or zh — adds a translated "
             "analysis.zh.md next to the English products.",
    ),
    jobs: int = typer.Option(
        1, "--jobs", "-j",
        help="Concurrent trial analyses in job mode (default 1 = "
             "sequential; single-trial analysis is never pooled).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Attribute badcases: judge trials against a rubric."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    if lang not in ("en", "zh"):
        _fail(f"--lang must be 'en' or 'zh', got {lang!r}")
    if jobs < 1:
        _fail(f"--jobs must be an integer >= 1, got {jobs}")
    install_trial_log_prefix()

    path = Path(path)
    if not path.exists():
        _fail(f"path not found: {path}")
    if not path.is_dir():
        _fail(f"not a directory: {path}")
    if task_dir is not None and not task_dir.exists():
        _fail(f"--task-dir not found: {task_dir}")

    try:
        effective_model = _resolve_model(backend, "analyze", model)
        rubric_path = (
            Path(rubric) if rubric is not None
            else get_asset("analyze/analyze-rubric.toml")
        )
        harness = build_backend(backend, effective_model)
        analyzer = Analyzer(
            backend=harness,
            rubric=load_rubric(rubric_path),
            model=effective_model,
            force=force,
            lang=lang,
            jobs=jobs,
        )

        if trial_reader.is_trial_dir(path):
            analyzer.analyze_trial(path, task_dir=task_dir)
        elif trial_reader.list_trials(path):
            analyzer.analyze_job(path, failing_only=failing)
        else:
            _fail(f"not a trial or job directory: {path}")
    except ValueError as e:
        _fail(str(e))


@app.command()
def check(
    path: Path = typer.Argument(..., help="Task directory to inspect."),
    rubric: str = typer.Option(
        None, "--rubric", "-r",
        help="Rubric file path or family name (default: check-default).",
    ),
    backend: str = typer.Option(
        "claude", "--backend", help="Agent harness backend (claude)."
    ),
    model: str = typer.Option(
        None, "--model", "-m",
        help="Model name (claude backend default: sonnet; pass e.g. "
             "deepseek-flash when using ANTHROPIC_BASE_URL).",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Re-check even if cached triage-kit/check-result.json exists "
             "(overwrites).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Inspect task quality: judge a task directory against a rubric."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    path = Path(path)
    if not path.exists():
        _fail(f"path not found: {path}")
    if not path.is_dir():
        _fail(f"not a directory: {path}")

    try:
        effective_model = _resolve_model(backend, "check", model)
        rubric_path = _resolve_check_rubric(rubric)
        harness = build_backend(backend, effective_model)
        checker = Checker(
            backend=harness,
            rubric=load_rubric(rubric_path),
            model=effective_model,
            force=force,
        )
        checker.check_task(path)
    except ValueError as e:
        _fail(str(e))


@app.command()
def clean(
    path: Path = typer.Argument(
        ..., help="Trial, job or task directory to restore (searched "
                  "recursively for triage-kit/ product directories)."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Actually delete (default is a dry-run listing).",
    ),
) -> None:
    """Restore evaluated directories: remove triage-kit/ product dirs."""
    import shutil

    if not path.exists():
        _fail(f"path not found: {path}")
    if not path.is_dir():
        _fail(f"not a directory: {path}")

    # Products only ever land in <dir>/triage-kit/, so removal is a
    # directory-name search — the original evaluation data never
    # matches and stays untouched.
    try:
        targets = sorted(p for p in path.rglob("triage-kit") if p.is_dir())
    except OSError as e:
        _fail(f"cannot scan {path}: {e}")
    if not targets:
        typer.echo("No triage-kit product directories found.")
        return

    verb = "removed" if yes else "would remove"
    for t in targets:
        typer.echo(f"{verb} {t}")
    if yes:
        # A locked/forbidden target must not abort the remaining
        # removals — report it, keep going, exit non-zero at the end.
        failures = 0
        for t in targets:
            if not t.exists():
                continue
            try:
                shutil.rmtree(t)
            except OSError as e:
                failures += 1
                typer.echo(f"error: failed to remove {t}: {e}", err=True)
        if failures:
            typer.echo(
                f"error: {failures} of {len(targets)} removal(s) failed",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"{len(targets)} product directory(ies) removed.")
    else:
        typer.echo(
            f"{len(targets)} product directory(ies) found — dry run, "
            f"pass --yes to delete."
        )


if __name__ == "__main__":
    app()
