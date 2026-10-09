"""triage CLI: `triage analyze` (badcase attribution) + `triage check`
(task quality inspection).

Backend selection is limited to 'general' (any OpenAI-compatible endpoint)
and 'claude' (Claude Agent SDK). The trae harness is a skill form, not a
CLI option.
"""

import logging
from pathlib import Path

import typer

from triage_kit.core import trial_reader
from triage_kit.core.analyzer import Analyzer
from triage_kit.core.assets import get_asset
from triage_kit.core.checker import Checker
from triage_kit.core.rubric import load_rubric

app = typer.Typer(
    add_completion=False,
    help="Badcase triage & task quality check for Harbor-ecosystem evaluation.",
)
logger = logging.getLogger(__name__)


def _open_general_backend(model: str | None, base_url: str | None):
    from openai import OpenAI

    from triage_kit.backends.general.harness import GeneralHarness

    client = OpenAI(base_url=base_url) if base_url else OpenAI()
    return GeneralHarness(client, default_model=model)


def _exempt_from_system_proxy(base_url: str) -> None:
    """Ensure an explicitly targeted endpoint bypasses system proxies.

    httpx reads Windows registry proxies but ignores the WinINET bypass
    list, so a localhost/intranet endpoint would be routed through the
    system proxy (and fail). NO_PROXY is the cross-platform exemption
    channel httpx does honor.
    """
    import os
    from urllib.parse import urlparse

    host = urlparse(base_url).hostname
    if not host:
        return
    current = os.environ.get("NO_PROXY", "")
    if host not in current.split(","):
        os.environ["NO_PROXY"] = f"{current},{host}".lstrip(",")


def build_backend(name: str, model: str | None, base_url: str | None = None):
    """Map a backend name to a harness satisfying the AgentBackend contract."""
    if name == "general":
        if base_url:
            _exempt_from_system_proxy(base_url)
        return _open_general_backend(model, base_url)
    if name == "claude":
        if base_url:
            raise ValueError(
                "--base-url only applies to --backend general; the claude "
                "backend manages its own endpoint (set ANTHROPIC_BASE_URL "
                "to override it)"
            )
        from triage_kit.backends.claude.harness import ClaudeHarness

        return ClaudeHarness(default_model=model)
    raise ValueError(
        f"unknown backend {name!r} (expected 'general' or 'claude')"
    )


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


# pier-compatible claude defaults; general has no sane cross-endpoint default
# so -m is mandatory there (a literal "default" in AgentMeta would be a lie).
_DEFAULT_MODEL = {"claude": {"analyze": "haiku", "check": "sonnet"}}


def _resolve_model(backend: str, command: str, model: str | None) -> str:
    if model is not None:
        return model
    if backend == "general":
        _fail("--model/-m is required for --backend general")
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
        "general", "--backend", help="general | claude."
    ),
    model: str = typer.Option(
        None, "--model", "-m", help="Model name for the chosen backend."
    ),
    base_url: str = typer.Option(
        None, "--base-url", help="OpenAI-compatible endpoint override."
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Re-analyze even if cached analysis.json exists (overwrites).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Attribute badcases: judge trials against a rubric."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    path = Path(path)
    if not path.exists():
        _fail(f"path not found: {path}")
    if not path.is_dir():
        _fail(f"not a directory: {path}")

    try:
        effective_model = _resolve_model(backend, "analyze", model)
        rubric_path = (
            Path(rubric) if rubric is not None
            else get_asset("analyze/analyze-rubric.toml")
        )
        harness = build_backend(backend, effective_model, base_url)
        analyzer = Analyzer(
            backend=harness,
            rubric=load_rubric(rubric_path),
            model=effective_model,
            force=force,
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
    backend: str = typer.Option("general", "--backend"),
    model: str = typer.Option(None, "--model", "-m"),
    base_url: str = typer.Option(None, "--base-url"),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Re-check even if cached check-result.json exists (overwrites).",
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
        harness = build_backend(backend, effective_model, base_url)
        checker = Checker(
            backend=harness,
            rubric=load_rubric(rubric_path),
            model=effective_model,
            force=force,
        )
        checker.check_task(path)
    except ValueError as e:
        _fail(str(e))


if __name__ == "__main__":
    app()
