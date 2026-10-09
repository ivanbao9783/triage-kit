"""Tests for triage_kit.core.checker — task quality inspection, FakeBackend-driven."""

import json

import pytest

from tests.conftest import CHECK_RUBRIC, make_task, write_sidecar

# Products live in the triage-kit/ subdirectory next to the task data.
TK = "triage-kit"
RESULT = "check-result.json"
SIDECAR = "check-result.meta.json"


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

    def test_file_tree_excludes_products_dir_on_force_rerun(
        self, task, rubric, good_response
    ):
        """D-audit: --force 重跑时，prompt 的文件树不得包含 triage-kit/
        产物目录——judge 不能看到自己上一次的判定结果（自引用偏差）。"""
        from triage_kit.core.checker import Checker

        # 模拟上一轮产物存在
        tk = task / TK
        tk.mkdir()
        (tk / RESULT).write_text("{}", encoding="utf-8")

        backend = make_backend(good_response)
        Checker(backend=backend, rubric=rubric, model="test-model",
                force=True).check_task(task)

        prompt = backend.agent_prompts[0]
        assert "triage-kit" not in prompt
        assert "check-result" not in prompt
        # task 本体文件仍在树中
        assert "instruction.md" in prompt

    def test_writes_check_result_json(self, task, rubric, good_response):
        from triage_kit.core.checker import Checker

        backend = make_backend(good_response)
        result = Checker(backend=backend, rubric=rubric, model="test-model").check_task(task)

        out = task / TK / RESULT
        assert out.is_file()
        saved = json.loads(out.read_text(encoding="utf-8"))
        first = rubric.criteria[0].name
        assert saved["checks"][first]["outcome"] == "pass"
        assert result == saved
        # task 根目录不残留产物
        assert not (task / "triage-check-result.json").exists()

    def _write_check_sidecar(self, task, *, model):
        tk = task / TK
        tk.mkdir(exist_ok=True)
        write_sidecar(tk, SIDECAR, model=model,
                      rubric_path=CHECK_RUBRIC)

    def test_existing_check_result_is_reused_without_backend_call(
        self, task, rubric, good_response
    ):
        from triage_kit.core.checker import Checker

        cached = {"checks": {
            c.name: {"outcome": "pass", "explanation": "cached"}
            for c in rubric.criteria
        }}
        tk = task / TK
        tk.mkdir()
        (tk / RESULT).write_text(
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

        tk = task / TK
        tk.mkdir()
        (tk / RESULT).write_text(
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

    def test_identity_mismatch_errors_and_force_overrides(
        self, task, rubric, good_response
    ):
        """M1: 身份链路对齐 Analyzer——换 model/rubric 报错提示 --force，
        force 重跑覆盖，不误覆盖。"""
        from triage_kit.core.checker import Checker
        from triage_kit.core.rubric import load_rubric

        Checker(backend=make_backend(good_response), rubric=rubric,
                model="glm-4.7").check_task(task)

        # 换 model → 报错提示 force
        with pytest.raises(ValueError, match="force"):
            Checker(backend=make_backend(good_response), rubric=rubric,
                    model="glm-5.3").check_task(task)
        # 产物未被覆盖（sidecar model 仍是旧值）
        meta = json.loads((task / TK / SIDECAR).read_text())
        assert meta["model"] == "glm-4.7"

        # force=True → 重跑覆盖
        backend3 = make_backend(good_response)
        Checker(backend=backend3, rubric=rubric, model="glm-5.3",
                force=True).check_task(task)
        assert len(backend3.agent_prompts) == 1
        meta = json.loads((task / TK / SIDECAR).read_text())
        assert meta["model"] == "glm-5.3"

        # 换 rubric（sha 变）→ 同样报错
        other_file = task.parent / "other-rubric.toml"
        other_file.write_text(
            CHECK_RUBRIC.read_text() + '\n[[criteria]]\nname = "extra"\n'
            'description = "d"\nguidance = "g"\n',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="rubric"):
            Checker(backend=make_backend(good_response),
                    rubric=load_rubric(other_file),
                    model="glm-5.3").check_task(task)

    def test_cache_without_sidecar_is_treated_as_miss(
        self, task, rubric, good_response
    ):
        """M1: 旧版产物（无 sidecar）：视为无缓存重跑。"""
        from triage_kit.core.checker import Checker

        tk = task / TK
        tk.mkdir()
        (tk / RESULT).write_text(
            json.dumps({"checks": {}}), encoding="utf-8"
        )
        backend = make_backend(good_response)
        result = Checker(backend=backend, rubric=rubric,
                         model="test-model").check_task(task)

        assert len(backend.agent_prompts) == 1   # reran
        first = rubric.criteria[0].name
        assert result["checks"][first]["outcome"] == "pass"
