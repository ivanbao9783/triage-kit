"""Task quality inspection: judge a Harbor task directory against a rubric.

Mirrors the Analyzer pattern (same backend contract, same rubric compilation)
but operates on task directories and writes <task_dir>/check-result.json.
"""

import json
from pathlib import Path

from triage_kit.core.assets import get_asset
from triage_kit.core.rubric import Rubric, build_criteria_guidance
from triage_kit.core.schema import build_check_response_schema
from triage_kit.core.task_reader import render_file_tree, validate_task_dir

# File-tree guardrails (pier parity + truncation): deep/large task trees must
# not flood the prompt. Truncation is annotated so the model knows to explore
# the rest with its read_file/glob/grep tools.
_MAX_TREE_DEPTH = 6
_MAX_TREE_ENTRIES = 200


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

    def check_task(self, task_dir: Path) -> dict:
        task_dir = Path(task_dir)

        cached = task_dir / "check-result.json"
        sidecar = task_dir / "check-result.meta.json"
        if cached.is_file() and not self.force:
            if sidecar.is_file():
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
                if meta.get("rubric_sha256") != self.rubric.source_sha256:
                    raise ValueError(
                        f"cached {cached.name} in {task_dir} was produced with a "
                        f"different rubric (cached sha {meta.get('rubric_sha256')}, "
                        f"requested {self.rubric.source_sha256}); "
                        f"rerun with --force to overwrite"
                    )
                if meta.get("model") != self.model:
                    raise ValueError(
                        f"cached {cached.name} in {task_dir} was produced with "
                        f"model {meta.get('model')!r}, requested {self.model!r}; "
                        f"rerun with --force to overwrite"
                    )
                # Cached products must pass the same response schema as fresh
                # backend responses (same rule as Analyzer's analysis.json).
                return self._response_schema.model_validate(
                    json.loads(cached.read_text(encoding="utf-8"))
                ).model_dump(mode="json")
            # legacy product without sidecar: treat as a cache miss
            # (same rule as Analyzer)

        errors = validate_task_dir(task_dir)
        if errors:
            raise ValueError(f"invalid task dir {task_dir}: {'; '.join(errors)}")

        prompt = self._template.format(
            file_tree=render_file_tree(
                task_dir,
                max_depth=_MAX_TREE_DEPTH,
                max_entries=_MAX_TREE_ENTRIES,
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

        (task_dir / "check-result.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        (task_dir / "check-result.meta.json").write_text(
            json.dumps({"rubric_sha256": self.rubric.source_sha256,
                        "model": self.model}, indent=2),
            encoding="utf-8",
        )
        return result
