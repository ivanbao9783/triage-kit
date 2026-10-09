"""Attribution orchestration: render prompts, judge trials, persist products.

The Analyzer owns the analyze (badcase attribution) workflow. All LLM access
goes through the AgentBackend contract, so the orchestration is fully
testable with a fake backend and works with any real harness.

Job mode runs trials through a bounded thread pool (P003: `-j/--jobs`,
default 1). Results fold in directory order after the join, so products
are identical for any j over the same trial set; per-trial failures are
collected (never raised out of a worker) and reported via failed_trials.
"""

import contextvars
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from triage_kit.core import cache, trial_reader
from triage_kit.core.assets import get_asset
from triage_kit.core.rubric import Rubric, build_criteria_guidance
from triage_kit.core.schema import build_analyze_response_schema

logger = logging.getLogger(__name__)

# Current trial for log attribution in job mode (P003). ContextVars are
# per-thread: each pool worker sees only its own value, so concurrent
# trials cannot leak into each other's log context.
_current_trial: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "triage_current_trial", default=None
)
_prefix_installed = False


def install_trial_log_prefix() -> None:
    """Prefix triage_kit log records with the current trial name.

    Concurrent workers interleave their log output; a per-trial prefix
    keeps every line attributable. Implemented as a LogRecord factory
    (runs at record creation) so records emitted by ANY triage_kit
    logger get prefixed, no matter which handler ships them. Idempotent.
    """
    global _prefix_installed
    if _prefix_installed:
        return
    base = logging.getLogRecordFactory()

    def prefixed_factory(*args, **kwargs):
        record = base(*args, **kwargs)
        trial = _current_trial.get()
        if trial is not None and record.name.startswith("triage_kit"):
            record.msg = f"[{trial}] {record.msg}"
        return record

    logging.setLogRecordFactory(prefixed_factory)
    _prefix_installed = True

# All products live in this subdirectory next to the trial/job data,
# so triage output never scatters into the evaluated directories.
_PRODUCTS_DIR = "triage-kit"

_DEGRADED_TASK_SECTION = (
    "The task directory is not available locally. "
    "Use the trajectory and test output to infer what the task required."
)

_TRANSLATE_INSTRUCTION = (
    "Translate the following Markdown report into Simplified Chinese. "
    "Preserve the Markdown structure (headings, lists, code blocks) and "
    "keep technical identifiers (file names, trial names, criterion "
    "names such as reward_hacking) untranslated. Output ONLY the "
    "translated Markdown, no preamble.\n\n"
)


def _render_task_section(task_dir: Path | None) -> str:
    """Hand-list key files instead of rendering a full tree (pier parity).

    A full recursive tree would flood the prompt on deep task dirs; the
    agent has read_file/glob/grep tools to explore on demand.
    """
    if task_dir is None:
        return _DEGRADED_TASK_SECTION
    return (
        f"The task directory is at: {task_dir}\n"
        "Read task files using absolute paths from the task directory.\n\n"
        "Task files (read first to understand requirements):\n"
        "- instruction.md — what the agent was asked to do\n"
        "- task.toml — task configuration\n"
        "- tests/ — test files the agent's work was verified against\n"
        "- solution/ — reference solution (if present)"
    )


def _render_analysis_md(analysis: dict) -> str:
    """Mechanical human-readable rendering of an analysis dict."""
    lines = [f"# Analysis: {analysis['trial_name']}", "", analysis["summary"], ""]
    for name, check in analysis["checks"].items():
        lines.append(f"## {name}: {check['outcome']}")
        lines.append("")
        lines.append(check["explanation"])
        lines.append("")
    return "\n".join(lines)


class Analyzer:
    """Attribution analysis over trials (single) and jobs (aggregate)."""

    def __init__(self, *, backend, rubric: Rubric, model: str,
                 force: bool = False, lang: str = "en", jobs: int = 1):
        if jobs < 1:
            raise ValueError(f"jobs must be an integer >= 1, got {jobs}")
        self.backend = backend
        self.rubric = rubric
        self.model = model
        self.force = force
        self.lang = lang
        self.jobs = jobs
        self._template = get_asset("analyze/analyze.txt").read_text(encoding="utf-8")
        self._job_template = get_asset("analyze/analyze-job.txt").read_text(
            encoding="utf-8"
        )
        self._response_schema = build_analyze_response_schema(rubric)

    def _identity(self) -> dict:
        return {"rubric_sha256": self.rubric.source_sha256, "model": self.model}

    def _translate_markdown(self, products_dir: Path, markdown: str) -> None:
        """Second-hop translation: write analysis.zh.md next to the
        (untouched, English) analysis.md inside the products directory."""
        translated, _meta = self.backend.query(
            _TRANSLATE_INSTRUCTION + markdown, model=self.model
        )
        if not translated.strip():
            raise ValueError(
                f"translation returned empty output (dir={products_dir.parent.name})"
            )
        (products_dir / "analysis.zh.md").write_text(
            translated, encoding="utf-8"
        )

    def analyze_trial(self, trial_dir: Path, *, task_dir: Path | None = None) -> dict:
        trial_dir = Path(trial_dir)
        products_dir = trial_dir / _PRODUCTS_DIR

        cached = cache.resolve_cache(
            cached_path=products_dir / "analysis.json",
            sidecar_path=products_dir / "analysis.meta.json",
            force=self.force,
            identity=self._identity(),
            schema=self._response_schema,
        )
        if cached is not None:
            return cached

        task_dir = trial_reader.extract_task_dir(trial_dir, override=task_dir)
        prompt = self._template.format(
            task_section=_render_task_section(task_dir),
            criteria_guidance=build_criteria_guidance(self.rubric),
        )
        raw, _meta = self.backend.query_agent(
            prompt,
            cwd=trial_dir,
            model=self.model,
            add_dirs=[task_dir] if task_dir is not None else None,
            output_schema=self._response_schema,
        )
        analysis = self._response_schema.model_validate(raw).model_dump(mode="json")
        if analysis["trial_name"] != trial_dir.name:
            raise ValueError(
                f"trial_name mismatch: backend returned "
                f"{analysis['trial_name']!r} but the trial directory is "
                f"{trial_dir.name!r}; refusing to attribute this analysis "
                f"to a different trial"
            )

        products_dir.mkdir(exist_ok=True)
        cache.write_json(products_dir / "analysis.json", analysis)
        markdown = _render_analysis_md(analysis)
        (products_dir / "analysis.md").write_text(markdown, encoding="utf-8")
        if self.lang == "zh":
            self._translate_markdown(products_dir, markdown)
        cache.write_json(products_dir / "analysis.meta.json", self._identity())
        return analysis

    def _analyze_one(
        self, trial_dir: Path
    ) -> tuple[str, dict | None, Exception | None]:
        """Pool worker: analyze one trial under the log-prefix contextvar.

        Never raises — failures travel back as the third tuple element
        and are reported (and folded into failed_trials) after the join.
        """
        token = _current_trial.set(trial_dir.name)
        try:
            logger.info("analysis start")
            analysis = self.analyze_trial(trial_dir)
            logger.info("analysis finished")
            return trial_dir.name, analysis, None
        except Exception as exc:
            return trial_dir.name, None, exc
        finally:
            _current_trial.reset(token)

    def analyze_job(self, job_dir: Path, *, failing_only: bool = False) -> dict:
        job_dir = Path(job_dir)
        trial_dirs = list(
            trial_reader.list_trials(job_dir, failing_only=failing_only)
        )

        # Bounded pool for every j (P003). At j=1 the single FIFO worker
        # preserves submission order, so call order equals listing order
        # — one code path for both modes, no sequential special case.
        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            futures = [pool.submit(self._analyze_one, d) for d in trial_dirs]
            trial_results: list[dict] = []
            failed_trials: list[str] = []
            # Consume in submission (listing) order — result() blocks on
            # that specific trial — so products are j-invariant: the
            # aggregation prompt and job products are byte-identical for
            # any j over the same trial set.
            for trial_dir, future in zip(trial_dirs, futures):
                _name, analysis, exc = future.result()
                if exc is not None:
                    failed_trials.append(trial_dir.name)
                    logger.error(
                        "[%s] analysis failed: %s: %s",
                        trial_dir.name, type(exc).__name__, exc,
                    )
                    logger.debug(
                        "[%s] failure traceback", trial_dir.name, exc_info=exc
                    )
                else:
                    trial_results.append(analysis)

        if not trial_results and not failed_trials:
            # Empty selection (e.g. --failing with zero badcases): an
            # LLM summary over zero trials carries no information — short
            # circuit instead of paying for (and writing) a hollow product.
            return {"summary": "", "trials": [], "failed_trials": []}

        prompt = self._job_template.format(
            trial_results=json.dumps(trial_results, indent=2)
        )
        summary, _meta = self.backend.query(prompt, model=self.model)
        if not summary.strip():
            raise ValueError(
                "job aggregation returned an empty summary "
                f"(job={job_dir.name}); refusing to write analysis.json"
            )

        result = {
            "summary": summary,
            "trials": trial_results,
            "failed_trials": failed_trials,
        }
        products_dir = job_dir / _PRODUCTS_DIR
        products_dir.mkdir(exist_ok=True)
        cache.write_json(products_dir / "analysis.json", result)
        markdown = f"# Job Analysis\n\n{summary}\n"
        (products_dir / "analysis.md").write_text(markdown, encoding="utf-8")
        if self.lang == "zh":
            self._translate_markdown(products_dir, markdown)
        return result
