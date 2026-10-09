"""Tests for triage_kit.core.checker — task quality inspection, FakeBackend-driven."""

import json
from pathlib import Path

import pytest

from tests.test_task_reader import make_task

REPO_ROOT = Path(__file__).parent.parent
CHECK_RUBRIC = REPO_ROOT / "assets" / "check" / "rubrics" / "check-default.toml"


def make_backend(response: dict):
    from triage_kit.core.contract import AgentMeta

    class FakeBackend:
        def __init__(self):
            self.agent_prompts: list[str] = []
            self.plain_prompts: list[str] = []

        def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                        output_schema=None, max_turns=15):
            self.agent_prompts.append(prompt)
            self.last_cwd = cwd
            return response, AgentMeta(n_turns=2, model=model)

        def query(self, prompt, *, model):
            self.plain_prompts.append(prompt)
            return "unused", AgentMeta(n_turns=0, model=model)

    return FakeBackend()


@pytest.fixture
def task(tmp_path):
    t = tmp_path / "demo-task"
    make_task(t)
    return t


@pytest.fixture
def rubric():
    from triage_kit.core.rubric import load_rubric

    return load_rubric(CHECK_RUBRIC)


@pytest.fixture
def good_response(rubric):
    return {
        "checks": {
            c.name: {"outcome": "pass", "explanation": "fine"}
            for c in rubric.criteria
        }
    }


class TestAssetsResolution:
    def test_check_template_is_found(self):
        from triage_kit.core.assets import get_asset

        template = get_asset("check/check.txt")
        assert template.is_file()
        assert "{file_tree}" in template.read_text(encoding="utf-8")


class TestCheckTask:
    def test_prompt_contains_file_tree_and_guidance(self, task, rubric, good_response):
        from triage_kit.core.checker import Checker

        backend = make_backend(good_response)
        Checker(backend=backend, rubric=rubric, model="test-model").check_task(task)

        prompt = backend.agent_prompts[0]
        assert "instruction.md" in prompt        # file tree content
        assert "Dockerfile" in prompt
        assert rubric.criteria[0].name in prompt  # criteria guidance
        assert backend.last_cwd == task

    def test_deep_tree_truncated_with_annotation(self, task, rubric, good_response):
        """方案3（对齐 pier）：check 侧树限深 + 省略标注，深目录不撑爆 prompt。"""
        from triage_kit.core.checker import Checker

        deep = task / "tests" / "l1" / "l2" / "l3" / "l4" / "l5" / "l6" / "l7"
        deep.mkdir(parents=True)
        (deep / "buried.txt").write_text("x", encoding="utf-8")

        backend = make_backend(good_response)
        Checker(backend=backend, rubric=rubric, model="test-model").check_task(task)

        prompt = backend.agent_prompts[0]
        assert "buried.txt" not in prompt         # depth-cut
        assert "deeper entries omitted" in prompt  # annotated truncation

    def test_writes_check_result_json(self, task, rubric, good_response):
        from triage_kit.core.checker import Checker

        backend = make_backend(good_response)
        result = Checker(backend=backend, rubric=rubric, model="test-model").check_task(task)

        out = task / "check-result.json"
        assert out.is_file()
        saved = json.loads(out.read_text(encoding="utf-8"))
        first = rubric.criteria[0].name
        assert saved["checks"][first]["outcome"] == "pass"
        assert result == saved

    def _write_check_sidecar(self, task, *, model):
        import hashlib

        sha = hashlib.sha256(CHECK_RUBRIC.read_bytes()).hexdigest()
        (task / "check-result.meta.json").write_text(
            json.dumps({"rubric_sha256": sha, "model": model}),
            encoding="utf-8",
        )

    def test_existing_check_result_is_reused_without_backend_call(
        self, task, rubric, good_response
    ):
        from triage_kit.core.checker import Checker

        cached = {"checks": {
            c.name: {"outcome": "pass", "explanation": "cached"}
            for c in rubric.criteria
        }}
        (task / "check-result.json").write_text(
            json.dumps(cached), encoding="utf-8"
        )
        self._write_check_sidecar(task, model="test-model")

        backend = make_backend(good_response)
        result = Checker(backend=backend, rubric=rubric,
                         model="test-model").check_task(task)

        assert backend.agent_prompts == []       # no LLM call
        assert result["checks"][rubric.criteria[0].name]["outcome"] == "pass"

    def test_corrupted_check_result_cache_is_rejected(self, task, rubric):
        """坏缓存（outcome 非法）必须抛错，不能带病直通。"""
        from triage_kit.core.checker import Checker

        (task / "check-result.json").write_text(
            json.dumps({"checks": {"typos":
                {"outcome": "bogus", "explanation": "x"}}}),
            encoding="utf-8",
        )
        self._write_check_sidecar(task, model="test-model")

        backend = make_backend(good_response)
        with pytest.raises(Exception):
            Checker(backend=backend, rubric=rubric,
                    model="test-model").check_task(task)

    def test_invalid_response_raises(self, task, rubric):
        from triage_kit.core.checker import Checker

        bad = {
            "checks": {
                c.name: {"outcome": "bogus", "explanation": "x"}
                for c in rubric.criteria
            }
        }
        backend = make_backend(bad)
        with pytest.raises(Exception):
            Checker(backend=backend, rubric=rubric, model="test-model").check_task(task)
