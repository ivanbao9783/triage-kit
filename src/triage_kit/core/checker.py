"""Task quality inspection: judge a Harbor task directory against a rubric.

Mirrors the Analyzer pattern (same backend contract, same rubric compilation)
but operates on task directories. Products land in
<task_dir>/triage-kit/check-result.json — the subdirectory keeps the task
tree clean of triage output.
"""

from pathlib import Path

from triage_kit.core import cache
from triage_kit.core.assets import get_asset
from triage_kit.core.rubric import Rubric, build_criteria_guidance
from triage_kit.core.schema import build_check_response_schema
from triage_kit.core.task_reader import render_file_tree, validate_task_dir

# File-tree guardrails (pier parity + truncation): deep/large task trees must
# not flood the prompt. Truncation is annotated so the model knows to explore
# the rest with its read_file/glob/grep tools.
_MAX_TREE_DEPTH = 6
_MAX_TREE_ENTRIES = 200

# Products subdirectory, shared convention with the Analyzer.
_PRODUCTS_DIR = "triage-kit"


class Checker:
    """Rubric-driven quality inspection over a single task directory."""

    def __init__(self, *, backend, rubric: Rubric, model: str,
                 force: bool = False):
        self.backend = backend
        self.rubric = rubric
        self.model = model
        self.force = force
        self._template = get_asset("check/check.txt").read_text(encoding="utf-8")
        self._response_schema = build_check_response_schema(rubric)

    def _identity(self) -> dict:
        return {"rubric_sha256": self.rubric.source_sha256, "model": self.model}

    def check_task(self, task_dir: Path) -> dict:
        task_dir = Path(task_dir)
        products_dir = task_dir / _PRODUCTS_DIR

        cached = cache.resolve_cache(
            cached_path=products_dir / "check-result.json",
            sidecar_path=products_dir / "check-result.meta.json",
            force=self.force,
            identity=self._identity(),
            schema=self._response_schema,
        )
        if cached is not None:
            return cached

        errors = validate_task_dir(task_dir)
        if errors:
            raise ValueError(f"invalid task dir {task_dir}: {'; '.join(errors)}")

        prompt = self._template.format(
            file_tree=render_file_tree(
                task_dir,
                max_depth=_MAX_TREE_DEPTH,
                max_entries=_MAX_TREE_ENTRIES,
                exclude={_PRODUCTS_DIR},
            ),
            criteria_guidance=build_criteria_guidance(self.rubric),
        )
        raw, _meta = self.backend.query_agent(
            prompt,
            cwd=task_dir,
            model=self.model,
            output_schema=self._response_schema,
        )
        result = self._response_schema.model_validate(raw).model_dump(mode="json")

        products_dir.mkdir(exist_ok=True)
        cache.write_json(products_dir / "check-result.json", result)
        cache.write_json(products_dir / "check-result.meta.json", self._identity())
        return result
