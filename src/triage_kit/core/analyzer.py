"""Attribution orchestration: render prompts, judge trials, persist products.

The Analyzer owns the analyze (badcase attribution) workflow. All LLM access
goes through the AgentBackend contract, so the orchestration is fully
testable with a fake backend and works with any real harness.
"""

import json
import logging
from pathlib import Path

from triage_kit.core import cache, trial_reader
from triage_kit.core.assets import get_asset
from triage_kit.core.rubric import Rubric, build_criteria_guidance
from triage_kit.core.schema import build_analyze_response_schema

logger = logging.getLogger(__name__)

_DEGRADED_TASK_SECTION = (
    "The task directory is not available locally. "
    "Use the trajectory and test output to infer what the task required."
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
                 force: bool = False):
        self.backend = backend
        self.rubric = rubric
        self.model = model
        self.force = force
        self._template = get_asset("analyze/analyze.txt").read_text(encoding="utf-8")
        self._job_template = get_asset("analyze/analyze-job.txt").read_text(
            encoding="utf-8"
        )
        self._response_schema = build_analyze_response_schema(rubric)

    def _identity(self) -> dict:
        return {"rubric_sha256": self.rubric.source_sha256, "model": self.model}

    def analyze_trial(self, trial_dir: Path, *, task_dir: Path | None = None) -> dict:
        trial_dir = Path(trial_dir)

        cached = cache.resolve_cache(
            cached_path=trial_dir / "analysis.json",
            sidecar_path=trial_dir / "analysis.meta.json",
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

        cache.write_json(trial_dir / "analysis.json", analysis)
        (trial_dir / "analysis.md").write_text(
            _render_analysis_md(analysis), encoding="utf-8"
        )
        cache.write_json(trial_dir / "analysis.meta.json", self._identity())
        return analysis

    def analyze_job(self, job_dir: Path, *, failing_only: bool = False) -> dict:
        job_dir = Path(job_dir)

        trial_results: list[dict] = []
        failed_trials: list[str] = []
        for trial_dir in trial_reader.list_trials(job_dir, failing_only=failing_only):
            try:
                trial_results.append(self.analyze_trial(trial_dir))
            except Exception:
                failed_trials.append(trial_dir.name)

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
        cache.write_json(job_dir / "analysis.json", result)
        (job_dir / "analysis.md").write_text(
            f"# Job Analysis\n\n{summary}\n", encoding="utf-8"
        )
        return result
