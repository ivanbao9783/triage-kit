"""Tests for triage_kit.core.checker — task quality inspection, FakeBackend-driven."""

import json

import pytest

from tests.conftest import (
    CHECK_RUBRIC,
    make_backend_keyed,
    make_task,
    write_sidecar,
)

# Products live in the triage-kit/ subdirectory next to the task data.
TK = "triage-kit"
RESULT = "check-result.json"
SIDECAR = "check-result.meta.json"
MD = "check-result.md"


def make_backend(response: dict, *, plain: str = "unused"):
    from triage_kit.core.contract import AgentMeta

    class FakeBackend:
        def __init__(self):
            self.agent_prompts: list[str] = []
            self.plain_prompts: list[str] = []

        def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                        output_schema=None):
            self.agent_prompts.append(prompt)
            self.last_cwd = cwd
            return response, AgentMeta(n_turns=2, model=model)

        def query(self, prompt, *, model):
            self.plain_prompts.append(prompt)
            return plain, AgentMeta(n_turns=0, model=model)

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
        """方案3（对齐上游）：check 侧树限深 + 省略标注，深目录不撑爆 prompt。"""
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


class TestCheckMd:
    """check-result.md —— en 机械渲染 / zh 原生撰写。"""

    def test_en_writes_mechanical_md(self, task, rubric, good_response):
        """en 默认：md 由 JSON 机械渲染，零额外 LLM 调用。"""
        from triage_kit.core.checker import Checker

        backend = make_backend(good_response)
        Checker(backend=backend, rubric=rubric,
                model="test-model").check_task(task)

        md = (task / TK / MD).read_text(encoding="utf-8")
        first = rubric.criteria[0].name
        assert md.startswith(f"# Task Check: {task.name}\n")
        assert f"## {first}: pass" in md
        assert "fine" in md                        # explanation carried
        assert backend.plain_prompts == []         # zero LLM on en
        saved = json.loads((task / TK / RESULT).read_text(encoding="utf-8"))
        assert saved["checks"][first]["outcome"] == "pass"

    def test_zh_composes_native_md(self, task, rubric, good_response):
        """zh：compose 跳原生撰写 check-result.md，payload 是结构化 JSON。"""
        from triage_kit.core.checker import Checker

        backend = make_backend(good_response, plain="ZH CHECK REPORT")
        Checker(backend=backend, rubric=rubric, model="test-model",
                lang="zh").check_task(task)

        assert len(backend.plain_prompts) == 1
        prompt = backend.plain_prompts[0]
        assert "撰写" in prompt                    # shared rules block
        assert "不得重新判定" in prompt
        assert "任务质检" in prompt and task.name in prompt
        first = rubric.criteria[0].name
        assert first in prompt and '"pass"' in prompt   # JSON payload
        md = (task / TK / MD).read_text(encoding="utf-8")
        assert md == "ZH CHECK REPORT"
        saved = json.loads((task / TK / RESULT).read_text(encoding="utf-8"))
        assert saved["checks"][first]["outcome"] == "pass"  # JSON 恒英文契约

    def test_zh_empty_compose_output_raises(self, task, rubric, good_response):
        from triage_kit.core.checker import Checker

        backend = make_backend(good_response, plain="  ")
        with pytest.raises(ValueError, match="empty"):
            Checker(backend=backend, rubric=rubric, model="test-model",
                    lang="zh").check_task(task)

    def test_cache_hit_skips_md_hop(self, task, rubric, good_response):
        """缓存命中不 compose，md 不写。"""
        from triage_kit.core.checker import Checker

        cached = {"checks": {
            c.name: {"outcome": "pass", "explanation": "cached"}
            for c in rubric.criteria
        }}
        tk = task / TK
        tk.mkdir()
        (tk / RESULT).write_text(json.dumps(cached), encoding="utf-8")
        write_sidecar(tk, SIDECAR, model="test-model",
                      rubric_path=CHECK_RUBRIC)

        backend = make_backend(good_response, plain="ZH")
        Checker(backend=backend, rubric=rubric, model="test-model",
                lang="zh").check_task(task)

        assert backend.agent_prompts == []
        assert backend.plain_prompts == []         # no compose on cache hit
        assert not (tk / MD).exists()


class TestCheckBatch:
    """批量模式 —— 一层扫描、确定性汇总、失败折叠。"""

    def test_jobs_below_one_rejected(self, rubric):
        from triage_kit.core.checker import Checker

        with pytest.raises(ValueError, match="jobs"):
            Checker(backend=make_backend({}), rubric=rubric, model="m",
                    jobs=0)

    def test_batch_writes_summary_and_per_task_products(
        self, tmp_path, rubric, good_response
    ):
        from triage_kit.core.checker import Checker

        for name in ("t1", "t2", "t3"):
            make_task(tmp_path / name)
        backend = make_backend_keyed(
            {n: good_response for n in ("t1", "t2", "t3")}
        )

        summary = Checker(backend=backend, rubric=rubric, model="m",
                          jobs=2).check_batch(tmp_path)

        assert summary["total"] == 3
        assert summary["checked"] == 3
        assert summary["cached"] == 0
        assert summary["failed"] == 0
        assert summary["failed_tasks"] == []
        first = rubric.criteria[0].name
        assert summary["per_criterion"][first]["pass"] == 3
        saved = json.loads(
            (tmp_path / TK / "check-summary.json").read_text(encoding="utf-8")
        )
        assert saved == summary
        for name in ("t1", "t2", "t3"):
            assert (tmp_path / name / TK / RESULT).is_file()
            assert (tmp_path / name / TK / MD).is_file()

    def test_batch_counts_cache_hits(self, tmp_path, rubric, good_response):
        """缓存命中的 task 计 cached：不调 LLM、不写 md。"""
        from triage_kit.core.checker import Checker

        make_task(tmp_path / "t1")
        make_task(tmp_path / "t2")
        tk = tmp_path / "t1" / TK
        tk.mkdir()
        (tk / RESULT).write_text(
            json.dumps(good_response), encoding="utf-8"
        )
        write_sidecar(tk, SIDECAR, model="m", rubric_path=CHECK_RUBRIC)

        backend = make_backend_keyed({"t2": good_response})
        summary = Checker(backend=backend, rubric=rubric, model="m",
                          jobs=2).check_batch(tmp_path)

        assert summary["cached"] == 1
        assert summary["checked"] == 1
        assert len(backend.agent_prompts) == 1     # only t2 hit the LLM
        assert not (tmp_path / "t1" / TK / MD).exists()
        assert (tmp_path / "t2" / TK / MD).exists()
        # cached verdicts count toward per_criterion too: the summary
        # must reflect the task set's verdicts on every (re)run —
        # a resumed CI rerun cannot lose its statistics
        first = rubric.criteria[0].name
        assert summary["per_criterion"][first]["pass"] == 2

    def test_single_failure_folded_not_raised(
        self, tmp_path, rubric, good_response, caplog
    ):
        """坏 task 落 failed_tasks 并有 ERROR 行点名，兄弟照常。"""
        import logging as logging_mod

        from triage_kit.core.checker import Checker

        make_task(tmp_path / "t1__bad")
        make_task(tmp_path / "t2__good")
        bad = {"checks": {"typos":
                          {"outcome": "bogus", "explanation": "x"}}}
        backend = make_backend_keyed(
            {"t1__bad": bad, "t2__good": good_response}
        )

        with caplog.at_level(logging_mod.ERROR):
            summary = Checker(backend=backend, rubric=rubric, model="m",
                              jobs=2).check_batch(tmp_path)

        assert summary["failed_tasks"] == ["t1__bad"]
        assert summary["failed"] == 1
        assert summary["checked"] == 1
        assert (tmp_path / "t2__good" / TK / RESULT).is_file()
        assert any(
            r.levelname == "ERROR" and "t1__bad" in r.getMessage()
            for r in caplog.records
        )

    def test_failed_tasks_follow_listing_not_completion(
        self, tmp_path, rubric
    ):
        """顺序钉定：完成顺序倒置时 failed_tasks 仍按目录序。"""
        from triage_kit.core.checker import Checker

        make_task(tmp_path / "t1__slow")
        make_task(tmp_path / "t2__fast")
        bad = {"checks": {"typos":
                          {"outcome": "bogus", "explanation": "x"}}}
        backend = make_backend_keyed(
            {"t1__slow": bad, "t2__fast": bad},
            delays={"t1__slow": 0.3, "t2__fast": 0.0},
        )

        summary = Checker(backend=backend, rubric=rubric, model="m",
                          jobs=2).check_batch(tmp_path)

        assert summary["failed_tasks"] == ["t1__slow", "t2__fast"]

    def test_batch_log_prefixes(self, tmp_path, rubric, good_response,
                                caplog):
        """归因前缀复用：并发下 triage_kit 日志带 [task_name] 前缀。"""
        import logging as logging_mod

        from triage_kit.core.analyzer import install_item_log_prefix
        from triage_kit.core.checker import Checker

        for name in ("t1", "t2"):
            make_task(tmp_path / name)
        backend = make_backend_keyed(
            {n: good_response for n in ("t1", "t2")}
        )

        install_item_log_prefix()
        with caplog.at_level(logging_mod.INFO):
            Checker(backend=backend, rubric=rubric, model="m",
                    jobs=2).check_batch(tmp_path)

        finished = [
            r.getMessage() for r in caplog.records
            if "check finished" in r.getMessage()
        ]
        assert len(finished) == 2
        assert {m.split("]")[0] + "]" for m in finished} == {
            "[t1]", "[t2]",
        }

    def test_barrier_proves_real_overlap(self, tmp_path, rubric,
                                         good_response):
        """重叠证明：2 task / jobs=2，barrier 只在真并发时放行。"""
        import threading

        from triage_kit.core.checker import Checker
        from triage_kit.core.contract import AgentMeta

        for name in ("t1", "t2"):
            make_task(tmp_path / name)

        class BarrierBackend:
            def __init__(self):
                self.barrier = threading.Barrier(2)

            def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                            output_schema=None):
                self.barrier.wait(timeout=5)
                return good_response, AgentMeta(n_turns=2, model=model)

            def query(self, prompt, *, model):
                return "ZH", AgentMeta(n_turns=0, model=model)

        summary = Checker(backend=BarrierBackend(), rubric=rubric,
                          model="m", jobs=2).check_batch(tmp_path)

        assert summary["failed"] == 0
        assert summary["checked"] == 2

    def test_nested_task_dirs_not_discovered(self, tmp_path):
        """一层扫描 —— 孙目录任务不进批量，非任务目录被忽略。"""
        from triage_kit.core.task_reader import list_task_dirs

        make_task(tmp_path / "t1")
        make_task(tmp_path / "group" / "t2")
        (tmp_path / "notatask").mkdir()

        assert [p.name for p in list_task_dirs(tmp_path)] == ["t1"]

    def test_empty_batch_raises(self, tmp_path, rubric):
        from triage_kit.core.checker import Checker

        with pytest.raises(ValueError, match="task"):
            Checker(backend=make_backend({}), rubric=rubric,
                    model="m").check_batch(tmp_path)
