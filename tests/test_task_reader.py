"""Tests for triage_kit.core.task_reader — against real deep-swe tasks."""

from pathlib import Path

import pytest

from tests.conftest import make_task

REPO_ROOT = Path(__file__).parent.parent
REAL_TASK = REPO_ROOT.parent / "deep-swe" / "tasks" / "ts-pattern-match-each"
TASKS_ROOT = REPO_ROOT.parent / "deep-swe" / "tasks"

needs_task = pytest.mark.skipif(
    not REAL_TASK.exists(), reason="real deep-swe task dir not present"
)


class TestValidateTaskDir:
    @needs_task
    def test_real_task_is_valid(self):
        from triage_kit.core.task_reader import validate_task_dir

        assert validate_task_dir(REAL_TASK) == []

    def test_empty_dir_reports_errors(self, tmp_path):
        from triage_kit.core.task_reader import validate_task_dir

        errors = validate_task_dir(tmp_path)
        assert any("task.toml" in e for e in errors)

    def test_multi_step_task_without_root_instruction_is_valid(self, tmp_path):
        """Root instruction/tests may be empty for multi-step tasks."""
        from triage_kit.core.task_reader import validate_task_dir

        make_task(tmp_path, with_steps=True)
        assert validate_task_dir(tmp_path) == []


class TestDetectSteps:
    @needs_task
    def test_single_step_task_has_no_steps(self):
        from triage_kit.core.task_reader import detect_steps

        assert detect_steps(REAL_TASK) == []

    def test_multi_step_task_expands(self, tmp_path):
        from triage_kit.core.task_reader import detect_steps

        make_task(tmp_path, with_steps=True)
        steps = detect_steps(tmp_path)
        assert [s.name for s in steps] == ["step-1"]


class TestRenderFileTree:
    @needs_task
    def test_tree_lists_all_top_level_entries(self):
        from triage_kit.core.task_reader import render_file_tree

        tree = render_file_tree(REAL_TASK)
        for entry in ("task.toml", "instruction.md", "environment", "tests", "solution"):
            assert entry in tree

    @needs_task
    def test_tree_is_indented(self):
        from triage_kit.core.task_reader import render_file_tree

        tree = render_file_tree(REAL_TASK)
        lines = tree.splitlines()
        # children are listed after their parent directory, indented
        assert "environment" in lines
        idx = lines.index("environment")
        assert lines[idx + 1] == "  Dockerfile"

    def test_tree_empty_dir(self, tmp_path):
        from triage_kit.core.task_reader import render_file_tree

        assert render_file_tree(tmp_path) == ""


class TestRenderFileTreeLimits:
    def test_depth_limit_cuts_with_annotation(self, tmp_path):
        """限深：超出 max_depth 的条目不列出，截断处有显式标注。"""
        from triage_kit.core.task_reader import render_file_tree

        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "leaf.txt").write_text("x", encoding="utf-8")

        tree = render_file_tree(tmp_path, max_depth=2)
        lines = tree.splitlines()
        assert "a" in lines            # depth 1
        assert "  b" in lines          # depth 2：列出但不展开
        assert "c" not in tree         # depth 3 被截
        assert "deeper entries omitted" in tree

    def test_entry_cap_summarizes_remainder(self, tmp_path):
        """省略标注：超出 max_entries 的部分汇总为一条 ... N more entries。"""
        from triage_kit.core.task_reader import render_file_tree

        for i in range(10):
            (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")

        tree = render_file_tree(tmp_path, max_entries=3)
        shown = [ln for ln in tree.splitlines() if not ln.startswith("...")]
        assert len(shown) == 3
        assert "... (7 more entries omitted)" in tree

    def test_within_limits_tree_unchanged(self, tmp_path):
        """限额内：输出与无限制版本完全一致（截断对正常任务零影响）。"""
        from triage_kit.core.task_reader import render_file_tree

        make_task(tmp_path)

        assert render_file_tree(tmp_path, max_depth=6, max_entries=200) == \
            render_file_tree(tmp_path)
