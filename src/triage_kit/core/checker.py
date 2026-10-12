"""Task quality inspection: judge task directories against a rubric.

Mirrors the Analyzer pattern (same backend contract, same rubric
compilation). Single mode judges one task directory; batch mode (P014)
checks every task directory one level under a root through a bounded
thread pool, folding failures instead of raising them. Products land in
<dir>/triage-kit/ — the subdirectory keeps the task tree clean of triage
output.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from triage_kit.core import cache
from triage_kit.core.analyzer import ZH_COMPOSE_RULES, log_item_scope
from triage_kit.core.assets import get_asset
from triage_kit.core.rubric import Rubric, build_criteria_guidance
from triage_kit.core.schema import build_check_response_schema
from triage_kit.core.task_reader import (
    list_task_dirs,
    render_file_tree,
    validate_task_dir,
)

logger = logging.getLogger(__name__)

# File-tree guardrails (upstream parity + truncation): deep/large task trees must
# not flood the prompt. Truncation is annotated so the model knows to explore
# the rest with its read_file/glob/grep tools.
_MAX_TREE_DEPTH = 6
_MAX_TREE_ENTRIES = 200

# Products subdirectory, shared convention with the Analyzer.
_PRODUCTS_DIR = "triage-kit"


def _render_check_md(result: dict, task_name: str) -> str:
    """Mechanical human-readable rendering of a check result (P014 D3)."""
    lines = [f"# Task Check: {task_name}", ""]
    for name, check in result["checks"].items():
        lines.append(f"## {name}: {check['outcome']}")
        lines.append("")
        lines.append(check["explanation"])
        lines.append("")
    return "\n".join(lines)


def _zh_check_compose(task_name: str) -> str:
    """zh compose instruction for check-result.md (P014 D3, P009 rules).

    The task name is embedded here because the check JSON payload —
    unlike the analyze payload — carries no task name.
    """
    return ZH_COMPOSE_RULES + (
        "报告结构（与英文版 check-result.md 同构）：\n"
        f"一级标题「# 任务质检：{task_name}」→ "
        "每个判据一节「## {判据名}: {outcome}」，节内为该判据的中文论述。\n"
        "\n诊断材料（JSON）：\n\n"
    )


class Checker:
    """Rubric-driven quality inspection over task directories."""

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
        self._template = get_asset("check/check.txt").read_text(encoding="utf-8")
        self._response_schema = build_check_response_schema(rubric)

    def _identity(self) -> dict:
        return {"rubric_sha256": self.rubric.source_sha256, "model": self.model}

    def check_task(self, task_dir: Path) -> dict:
        result, _cached = self._check_task_tracked(task_dir)
        return result

    def _check_task_tracked(self, task_dir: Path) -> tuple[dict, bool]:
        """Full single-task flow; the bool says whether the cache hit.

        Split out so batch mode can count cache hits without re-reading
        the cached products a second time.
        """
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
            logger.info("cache hit: reusing cached check result")
            return cached, True

        # P011 parity with the Analyzer: explicit start/finish markers
        # so the persisted run.log carries a readable run trace.
        logger.info("check start")
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
        if self.lang == "zh":
            # P014 D3 (P009 route B semantics): --lang zh composes
            # check-result.md natively in Chinese; the JSON stays English.
            composed, _meta = self.backend.query(
                _zh_check_compose(task_dir.name)
                + json.dumps(result, ensure_ascii=False, indent=2),
                model=self.model,
            )
            if not composed.strip():
                raise ValueError(
                    f"zh composition returned empty output "
                    f"(task={task_dir.name})"
                )
            (products_dir / "check-result.md").write_text(
                composed, encoding="utf-8"
            )
        else:
            (products_dir / "check-result.md").write_text(
                _render_check_md(result, task_dir.name), encoding="utf-8"
            )
        cache.write_json(products_dir / "check-result.meta.json", self._identity())
        logger.info("check finished")
        return result, False

    def _check_one(
        self, task_dir: Path
    ) -> tuple[str, dict | None, bool, Exception | None]:
        """Pool worker: check one task under the log-prefix contextvar.

        Never raises — failures travel back as the last tuple element and
        are folded into failed_tasks after the join (P014 D4).
        """
        with log_item_scope(task_dir.name):
            try:
                result, cached = self._check_task_tracked(task_dir)
                return task_dir.name, result, cached, None
            except Exception as exc:
                return task_dir.name, None, False, exc

    def check_batch(self, root: Path) -> dict:
        """P014 D1/D2/D4: check every task directory one level under root.

        Runs through a bounded pool; results fold in directory order, so
        the summary is j-invariant over the same task set. The summary is
        purely mechanical counting (zero LLM) and lands in
        <root>/triage-kit/check-summary.json.
        """
        root = Path(root)
        task_dirs = list_task_dirs(root)
        if not task_dirs:
            raise ValueError(
                f"no task directories found under {root} (expected "
                f"direct subdirectories containing task.toml)"
            )

        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            futures = [pool.submit(self._check_one, d) for d in task_dirs]
            all_results: list[dict] = []
            cached_count = 0
            failed_tasks: list[str] = []
            # Consume in listing order — result() blocks on that specific
            # task — so failed_tasks and per_criterion counts are
            # j-invariant (P003 pattern, P014 D4).
            for task_dir, future in zip(task_dirs, futures):
                _name, result, cached, exc = future.result()
                if exc is not None:
                    failed_tasks.append(task_dir.name)
                    logger.error(
                        "[%s] check failed: %s: %s",
                        task_dir.name, type(exc).__name__, exc,
                    )
                    logger.debug(
                        "[%s] failure traceback", task_dir.name, exc_info=exc
                    )
                else:
                    all_results.append(result)
                    if cached:
                        cached_count += 1

        # per_criterion counts every verdict (cached included): a
        # resumed CI rerun must not lose its statistics — cached
        # products are schema-revalidated on read-back.
        per_criterion = {
            c.name: {"pass": 0, "fail": 0, "not_applicable": 0}
            for c in self.rubric.criteria
        }
        for result in all_results:
            for name, check in result["checks"].items():
                per_criterion[name][check["outcome"]] += 1

        summary = {
            "total": len(task_dirs),
            "checked": len(all_results) - cached_count,
            "cached": cached_count,
            "failed": len(failed_tasks),
            "per_criterion": per_criterion,
            "failed_tasks": failed_tasks,
        }
        products_dir = root / _PRODUCTS_DIR
        products_dir.mkdir(exist_ok=True)
        cache.write_json(products_dir / "check-summary.json", summary)
        return summary
