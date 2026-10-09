"""Tests for triage_kit.core.analyzer — driven by a FakeBackend, no LLM."""

import json

import pytest

from tests.conftest import (
    ANALYZE_RUBRIC,
    make_backend_keyed,
    make_barrier_backend,
    make_trial,
    write_sidecar,
)


def make_backend(response: dict):
    from triage_kit.core.contract import AgentMeta

    class FakeBackend:
        def __init__(self):
            self.agent_prompts: list[str] = []
            self.plain_prompts: list[str] = []

        def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                        output_schema=None, max_turns=15):
            self.agent_prompts.append(prompt)
            return response, AgentMeta(n_turns=2, model=model)

        def query(self, prompt, *, model):
            self.plain_prompts.append(prompt)
            return "JOB SUMMARY", AgentMeta(n_turns=0, model=model)

    return FakeBackend()


def make_backend_seq(responses: list):
    """FakeBackend that returns the given responses in order (one per call)."""
    from triage_kit.core.contract import AgentMeta

    class FakeBackend:
        def __init__(self):
            self.responses = list(responses)
            self.agent_prompts: list[str] = []
            self.plain_prompts: list[str] = []

        def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                        output_schema=None, max_turns=15):
            self.agent_prompts.append(prompt)
            return self.responses.pop(0), AgentMeta(n_turns=2, model=model)

        def query(self, prompt, *, model):
            self.plain_prompts.append(prompt)
            # query and query_agent consume the SAME list in true call
            # order (interleaved) — script responses in the exact order
            # the workflow calls the backend
            return self.responses.pop(0), AgentMeta(n_turns=0, model=model)

    return FakeBackend()


GOOD_RESPONSE = {
    "trial_name": "demo__abc123",
    "summary": "Agent solved it.",
    "checks": {
        "reward_hacking": {"outcome": "pass", "explanation": "legit"},
        "task_specification": {"outcome": "pass", "explanation": "clear"},
    },
}


@pytest.fixture
def trial(tmp_path):
    t = tmp_path / "demo__abc123"
    make_trial(t, reward=1.0)
    return t


@pytest.fixture
def rubric():
    from triage_kit.core.rubric import load_rubric

    return load_rubric(ANALYZE_RUBRIC)


@pytest.fixture
def rubric_file():
    return ANALYZE_RUBRIC


class TestAnalyzeTrial:
    def test_prompt_contains_guidance_and_degraded_task_section(
        self, trial, rubric
    ):
        from triage_kit.core.analyzer import Analyzer

        backend = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend, rubric=rubric, model="test-model").analyze_trial(trial)

        prompt = backend.agent_prompts[0]
        assert "reward_hacking" in prompt          # criteria guidance
        assert "task_specification" in prompt
        assert "not available" in prompt           # degraded task section

    def test_writes_analysis_json_and_md(self, trial, rubric):
        from triage_kit.core.analyzer import Analyzer

        backend = make_backend(GOOD_RESPONSE)
        result = Analyzer(backend=backend, rubric=rubric, model="test-model").analyze_trial(trial)

        assert result["trial_name"] == "demo__abc123"
        assert (trial / "triage-kit" / "analysis.json").is_file()
        assert (trial / "triage-kit" / "analysis.md").is_file()
        saved = json.loads(
            (trial / "triage-kit" / "analysis.json").read_text(encoding="utf-8")
        )
        assert saved["checks"]["reward_hacking"]["outcome"] == "pass"

    def test_products_live_in_triage_kit_subdirectory(self, trial, rubric):
        """D1: 产物全部落 <trial>/triage-kit/ 子目录（去前缀），
        trial 根目录不残留任何 triage 产物。"""
        from triage_kit.core.analyzer import Analyzer

        Analyzer(backend=make_backend(GOOD_RESPONSE), rubric=rubric,
                 model="test-model").analyze_trial(trial)

        tk = trial / "triage-kit"
        assert (tk / "analysis.json").is_file()
        assert (tk / "analysis.md").is_file()
        assert (tk / "analysis.meta.json").is_file()
        # 根目录零残留（既无平铺产物，也无旧前缀副本）
        assert not (trial / "analysis.json").exists()
        assert not (trial / "analysis.md").exists()
        assert not (trial / "triage-kit-analysis.md").exists()

    def test_job_products_live_in_triage_kit_subdirectory(self, tmp_path, rubric):
        """D1: job 级产物同样进 triage-kit/ 子目录。"""
        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__aaa", reward=0.0)
        backend = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend, rubric=rubric,
                 model="test-model").analyze_job(tmp_path)

        tk = tmp_path / "triage-kit"
        original = (tk / "analysis.md").read_text(encoding="utf-8")
        assert original.startswith("# Job Analysis")
        assert (tk / "analysis.json").is_file()
        assert not (tmp_path / "analysis.md").exists()

    def test_lang_zh_writes_translated_copy_per_trial_and_job(
        self, tmp_path, rubric
    ):
        """Q3: --lang zh 在英文产物之外追加 analysis.zh.md。

        翻译二跳：analysis.md 保持英文不动，中文版是增量产物。
        job 级翻译用一次 query，trial 级各一次——本测试共
        2 trial + 1 job = 3 次翻译调用。
        """
        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__aaa", reward=0.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)
        # Responses are consumed in true call order — per-trial translation
        # happens inside analyze_trial, interleaved between agent calls:
        # agent(t1) → query(t1 zh) → agent(t2) → query(t2 zh) → job agg → job zh
        backend = make_backend_seq([
            dict(GOOD_RESPONSE, trial_name="t1__aaa"),
            "TRANSLATED",   # t1 zh
            dict(GOOD_RESPONSE, trial_name="t2__bbb"),
            "TRANSLATED",   # t2 zh
            "JOB SUMMARY",  # job aggregation
            "TRANSLATED",   # job zh
        ])
        Analyzer(backend=backend, rubric=rubric, model="test-model",
                 lang="zh").analyze_job(tmp_path)

        # trial 级中文副本
        for name in ("t1__aaa", "t2__bbb"):
            zh = (tmp_path / name / "triage-kit" / "analysis.zh.md").read_text(
                encoding="utf-8"
            )
            assert zh == "TRANSLATED"
        # job 级中文副本
        assert (tmp_path / "triage-kit" / "analysis.zh.md").read_text(
            encoding="utf-8"
        ) == "TRANSLATED"
        # 英文产物与中文版并存
        en = (tmp_path / "t1__aaa" / "triage-kit" / "analysis.md").read_text(
            encoding="utf-8"
        )
        assert "Agent solved it." in en
        # 翻译调用次数：2 trial + 1 job = 3（另有 1 次 job 聚合 query）
        translations = [
            p for p in backend.plain_prompts if p.startswith("Translate")
        ]
        assert len(translations) == 3

    def test_lang_default_is_english_no_extra_calls(self, trial, rubric):
        """Q3: 默认英文——零翻译调用，无中文副本。"""
        from triage_kit.core.analyzer import Analyzer

        backend = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend, rubric=rubric,
                 model="test-model").analyze_trial(trial)

        assert len(backend.plain_prompts) == 0
        assert not (trial / "triage-kit" / "analysis.zh.md").exists()

    def test_task_dir_override_lands_in_prompt(self, trial, tmp_path, rubric):
        from triage_kit.core.analyzer import Analyzer

        task_dir = tmp_path / "task"
        (task_dir / "environment").mkdir(parents=True)
        (task_dir / "task.toml").write_text("", encoding="utf-8")
        (task_dir / "instruction.md").write_text("hello", encoding="utf-8")

        backend = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend, rubric=rubric, model="test-model").analyze_trial(
            trial, task_dir=task_dir
        )

        assert str(task_dir) in backend.agent_prompts[0]

    def test_task_section_lists_key_files_not_full_tree(
        self, trial, tmp_path, rubric
    ):
        """方案3（对齐上游）：task_section 手列关键文件，不再渲染全量树。"""
        from triage_kit.core.analyzer import Analyzer

        task_dir = tmp_path / "task"
        (task_dir / "environment").mkdir(parents=True)
        (task_dir / "tests" / "deep" / "deeper").mkdir(parents=True)
        (task_dir / "tests" / "deep" / "deeper" / "buried.txt").write_text(
            "x", encoding="utf-8")
        (task_dir / "task.toml").write_text("", encoding="utf-8")
        (task_dir / "instruction.md").write_text("hello", encoding="utf-8")

        backend = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend, rubric=rubric, model="test-model").analyze_trial(
            trial, task_dir=task_dir
        )

        prompt = backend.agent_prompts[0]
        assert "instruction.md" in prompt     # 手列关键文件
        assert "task.toml" in prompt
        assert "tests/" in prompt
        assert "solution/" in prompt
        assert "buried.txt" not in prompt     # 深层文件不再全量进 prompt
        assert "File tree" not in prompt      # 不再渲染树

    def test_existing_analysis_is_reused_without_backend_call(self, trial, rubric):
        from triage_kit.core.analyzer import Analyzer

        cached = {"trial_name": "demo__abc123", "summary": "cached",
                  "checks": GOOD_RESPONSE["checks"]}
        tk = trial / "triage-kit"
        tk.mkdir()
        (tk / "analysis.json").write_text(json.dumps(cached), encoding="utf-8")
        write_sidecar(tk, "analysis.meta.json", model="test-model",
                      rubric_path=ANALYZE_RUBRIC)

        backend = make_backend(GOOD_RESPONSE)
        result = Analyzer(backend=backend, rubric=rubric, model="test-model").analyze_trial(trial)

        assert backend.agent_prompts == []       # no LLM call
        assert result["summary"] == "cached"

    def test_invalid_backend_response_raises(self, trial, rubric):
        from triage_kit.core.analyzer import Analyzer

        bad = {"trial_name": "demo__abc123", "summary": "s",
               "checks": {"reward_hacking": {"outcome": "weird", "explanation": "x"}}}
        backend = make_backend(bad)
        with pytest.raises(Exception):
            Analyzer(backend=backend, rubric=rubric, model="test-model").analyze_trial(trial)


class TestAnalyzeJob:
    def test_aggregates_trials_into_job_summary(self, tmp_path, rubric):
        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__aaa", reward=1.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)

        backend = make_backend(GOOD_RESPONSE)
        result = Analyzer(backend=backend, rubric=rubric, model="test-model").analyze_job(tmp_path)

        # two judge calls + one aggregation call
        assert len(backend.agent_prompts) == 2
        assert len(backend.plain_prompts) == 1
        assert result["summary"] == "JOB SUMMARY"
        assert (tmp_path / "triage-kit" / "analysis.json").is_file()
        assert (tmp_path / "triage-kit" / "analysis.md").is_file()

    def test_failing_only_limits_trials(self, tmp_path, rubric):
        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__aaa", reward=1.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)

        backend = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend, rubric=rubric, model="test-model").analyze_job(
            tmp_path, failing_only=True
        )

        assert len(backend.agent_prompts) == 1

    def test_corrupted_cache_is_rejected_and_lands_in_failed_trials(
        self, tmp_path, rubric
    ):
        """(d) 缓存读回必须过同一 response schema：
        损坏的 analysis.json 不能带病直通 job 产物，
        而是被拦截并计入 failed_trials。"""
        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__good", reward=0.0)
        make_trial(tmp_path / "t2__corrupt", reward=0.0)
        # 模拟半写中断/手改：outcome 非法
        tk = tmp_path / "t2__corrupt" / "triage-kit"
        tk.mkdir()
        (tk / "analysis.json").write_text(
            json.dumps({
                "trial_name": "t2__corrupt", "summary": "s",
                "checks": {"reward_hacking":
                           {"outcome": "bogus", "explanation": "x"}},
            }),
            encoding="utf-8",
        )
        # 身份匹配的 sidecar：确保走的是"校验拒绝"而非"无 sidecar 重跑"
        write_sidecar(tk, "analysis.meta.json",
                      model="test-model", rubric_path=ANALYZE_RUBRIC)

        backend = make_backend(dict(GOOD_RESPONSE, trial_name="t1__good"))
        result = Analyzer(
            backend=backend, rubric=rubric, model="test-model"
        ).analyze_job(tmp_path)

        assert result["failed_trials"] == ["t2__corrupt"]
        assert len(result["trials"]) == 1  # only t1__good survived
        # 损坏缓存被拦截后不重跑 LLM（保留现场，供人工排查）
        assert len(backend.agent_prompts) == 1

    def test_empty_summary_is_treated_as_failure(self, tmp_path, rubric):
        """(d) query() 返回空 summary 视为该次聚合失败，不写产物。"""
        from triage_kit.core.analyzer import Analyzer
        from triage_kit.core.contract import AgentMeta

        make_trial(tmp_path / "t1__aaa", reward=1.0)

        class EmptySummaryBackend:
            def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                            output_schema=None, max_turns=15):
                return dict(GOOD_RESPONSE, trial_name="t1__aaa"), AgentMeta(
                    n_turns=1, model=model)

            def query(self, prompt, *, model):
                return "", AgentMeta(n_turns=1, model=model)

        with pytest.raises(ValueError, match="empty"):
            Analyzer(backend=EmptySummaryBackend(), rubric=rubric,
                     model="test-model").analyze_job(tmp_path)
        assert not (tmp_path / "triage-kit" / "analysis.json").exists()

    def test_empty_trial_set_short_circuits(self, tmp_path, rubric):
        """#6: 零 trial 时短路返回——不调 LLM、不写任何产物。"""
        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__aaa", reward=1.0)  # all passing

        backend = make_backend(GOOD_RESPONSE)
        result = Analyzer(backend=backend, rubric=rubric,
                          model="test-model").analyze_job(
            tmp_path, failing_only=True
        )

        assert backend.plain_prompts == []        # no aggregation call
        assert backend.agent_prompts == []        # no trial analysis either
        assert result == {"summary": "", "trials": [], "failed_trials": []}
        assert not (tmp_path / "triage-kit").exists()

    def test_fresh_analysis_writes_identity_sidecar(self, trial, rubric):
        """新鲜产物必须落 sidecar：rubric sha + model（缓存身份）。"""
        from triage_kit.core.analyzer import Analyzer

        backend = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend, rubric=rubric, model="glm-4.7").analyze_trial(trial)

        sidecar = trial / "triage-kit" / "analysis.meta.json"
        assert sidecar.is_file()
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        assert set(meta) == {"rubric_sha256", "model"}
        assert meta["model"] == "glm-4.7"
        assert len(meta["rubric_sha256"]) == 64  # sha256 hex

    def test_cache_reused_only_when_identity_matches(
        self, trial, rubric, rubric_file
    ):
        from triage_kit.core.analyzer import Analyzer
        from triage_kit.core.rubric import load_rubric

        backend = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend, rubric=rubric, model="glm-4.7").analyze_trial(trial)

        # 相同身份 → 复用（零调用）
        backend2 = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend2, rubric=rubric, model="glm-4.7").analyze_trial(trial)
        assert backend2.agent_prompts == []

        # 换 model → 报错，提示 --force，不覆盖
        with pytest.raises(ValueError, match="force"):
            Analyzer(backend=make_backend(GOOD_RESPONSE), rubric=rubric,
                     model="glm-5.3").analyze_trial(trial)
        # 产物未被覆盖（sidecar model 仍是旧值）
        meta = json.loads(
            (trial / "triage-kit" / "analysis.meta.json").read_text())
        assert meta["model"] == "glm-4.7"

        # force=True → 警告并重跑覆盖
        backend3 = make_backend(GOOD_RESPONSE)
        Analyzer(backend=backend3, rubric=rubric, model="glm-5.3",
                 force=True).analyze_trial(trial)
        assert len(backend3.agent_prompts) == 1
        meta = json.loads(
            (trial / "triage-kit" / "analysis.meta.json").read_text())
        assert meta["model"] == "glm-5.3"

        # 换 rubric（sha 变）→ 同样报错
        other_file = trial.parent / "other-rubric.toml"
        other_file.write_text(
            rubric_file.read_text() + '\n[[criteria]]\nname = "extra"\n'
            'description = "d"\nguidance = "g"\n',
            encoding="utf-8",
        )
        other = load_rubric(other_file)
        with pytest.raises(ValueError, match="rubric"):
            Analyzer(backend=make_backend(GOOD_RESPONSE), rubric=other,
                     model="glm-5.3").analyze_trial(trial)

    def test_cache_without_sidecar_is_treated_as_miss(self, trial, rubric):
        """旧版产物（无 sidecar）：提示后视为无缓存重跑。"""
        from triage_kit.core.analyzer import Analyzer

        tk = trial / "triage-kit"
        tk.mkdir()
        (tk / "analysis.json").write_text(
            json.dumps(GOOD_RESPONSE), encoding="utf-8",
        )
        backend = make_backend(GOOD_RESPONSE)
        result = Analyzer(backend=backend, rubric=rubric,
                          model="test-model").analyze_trial(trial)
        assert len(backend.agent_prompts) == 1  # reran
        assert result["summary"] == GOOD_RESPONSE["summary"]

    def test_mismatched_trial_name_lands_in_failed_trials(self, tmp_path, rubric):
        """#8: 模型交回的 trial_name 与目录名不符 → job 下计入 failed_trials。"""
        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__aaa", reward=0.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)

        bad = dict(GOOD_RESPONSE, trial_name="wrong__name")
        good = dict(GOOD_RESPONSE, trial_name="t2__bbb")
        backend = make_backend_seq([bad, good, "JOB SUMMARY"])

        result = Analyzer(backend=backend, rubric=rubric,
                          model="test-model").analyze_job(tmp_path)

        assert result["failed_trials"] == ["t1__aaa"]
        assert [t["trial_name"] for t in result["trials"]] == ["t2__bbb"]

    def test_mismatched_trial_name_raises_for_single_trial(self, trial, rubric):
        """#8: 单 trial 直调 → 名字不符直接抛错（调用方就是针对这个 trial 的）。"""
        from triage_kit.core.analyzer import Analyzer

        bad = dict(GOOD_RESPONSE, trial_name="wrong__name")
        backend = make_backend(bad)

        with pytest.raises(ValueError, match="trial_name"):
            Analyzer(backend=backend, rubric=rubric,
                     model="test-model").analyze_trial(trial)

    def test_single_trial_failure_does_not_abort_job(self, tmp_path, rubric):
        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__aaa", reward=0.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)

        bad = {"trial_name": "t1__aaa", "summary": "s",
               "checks": {"reward_hacking": {"outcome": "bogus", "explanation": "x"}}}
        good = {"trial_name": "t2__bbb", "summary": "ok",
                "checks": GOOD_RESPONSE["checks"]}
        backend = make_backend_seq([bad, good, "JOB SUMMARY"])
        result = Analyzer(backend=backend, rubric=rubric, model="test-model").analyze_job(tmp_path)

        # t1 failed validation, t2 still analyzed, aggregation still happened
        assert len(backend.agent_prompts) == 2
        assert len(backend.plain_prompts) == 1
        assert result["failed_trials"] == ["t1__aaa"]
        assert result["trials"][0]["trial_name"] == "t2__bbb"


class TestParallelAnalysis:
    """P003: `-j/--jobs` — 有界线程池包裹 analyze_trial，join 后聚合。
    产物顺序钉在目录序上（对 j 不变），单 trial 失败不毒化兄弟。"""

    def test_jobs_below_one_rejected(self, rubric):
        from triage_kit.core.analyzer import Analyzer

        with pytest.raises(ValueError, match="jobs"):
            Analyzer(backend=make_backend(GOOD_RESPONSE), rubric=rubric,
                     model="m", jobs=0)

    def test_barrier_proves_real_overlap(self, tmp_path, rubric):
        """重叠证明：2 trial / jobs=2，barrier 只在真并发时放行。
        串行（或 max_workers<2）实现会 break barrier，
        两个 trial 全部落入 failed_trials，本测试失败。"""
        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__aaa", reward=0.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)
        backend = make_barrier_backend(2, GOOD_RESPONSE)

        result = Analyzer(backend=backend, rubric=rubric, model="m",
                          jobs=2).analyze_job(tmp_path)

        assert result["failed_trials"] == []
        assert [t["trial_name"] for t in result["trials"]] == [
            "t1__aaa", "t2__bbb",
        ]

    def test_single_failure_under_concurrency_does_not_poison_siblings(
        self, tmp_path, rubric, caplog
    ):
        """失败隔离：坏 trial 落 failed_trials 并有 ERROR 行点名，
        兄弟照常分析，聚合照跑。"""
        import logging as logging_mod

        from triage_kit.core.analyzer import Analyzer

        make_trial(tmp_path / "t1__bad", reward=0.0)
        make_trial(tmp_path / "t2__good", reward=0.0)
        bad = {"trial_name": "t1__bad", "summary": "s",
               "checks": {"reward_hacking":
                          {"outcome": "bogus", "explanation": "x"}}}
        good = dict(GOOD_RESPONSE, trial_name="t2__good")
        backend = make_backend_keyed({"t1__bad": bad, "t2__good": good})

        with caplog.at_level(logging_mod.ERROR):
            result = Analyzer(backend=backend, rubric=rubric, model="m",
                              jobs=2).analyze_job(tmp_path)

        assert result["failed_trials"] == ["t1__bad"]
        assert [t["trial_name"] for t in result["trials"]] == ["t2__good"]
        assert len(backend.plain_prompts) == 1  # aggregation still ran
        assert any(
            r.levelname == "ERROR" and "t1__bad" in r.getMessage()
            for r in caplog.records
        )

    def test_job_product_order_follows_listing_not_completion(
        self, tmp_path, rubric
    ):
        """顺序钉定：完成顺序与目录序相反时，产物 trials 仍按目录序
        ——产物对 j 不变（同 trial 集合逐字节等价的前提）。"""
        from triage_kit.core.analyzer import Analyzer

        for name in ("t1__aaa", "t2__bbb", "t3__ccc"):
            make_trial(tmp_path / name, reward=0.0)
        responses = {
            name: dict(GOOD_RESPONSE, trial_name=name)
            for name in ("t1__aaa", "t2__bbb", "t3__ccc")
        }
        # 完成顺序倒置：排最前的最慢，排最后的零延迟
        delays = {"t1__aaa": 0.3, "t2__bbb": 0.15, "t3__ccc": 0.0}
        backend = make_backend_keyed(responses, delays=delays)

        result = Analyzer(backend=backend, rubric=rubric, model="m",
                          jobs=4).analyze_job(tmp_path)

        assert result["failed_trials"] == []
        assert [t["trial_name"] for t in result["trials"]] == [
            "t1__aaa", "t2__bbb", "t3__ccc",
        ]

    def test_worker_logs_carry_trial_prefix(self, tmp_path, rubric, caplog):
        """归因前缀：并发下 triage_kit 日志带 [trial_name] 前缀。"""
        import logging as logging_mod

        from triage_kit.core.analyzer import (
            Analyzer,
            install_trial_log_prefix,
        )

        make_trial(tmp_path / "t1__aaa", reward=0.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)
        responses = {
            name: dict(GOOD_RESPONSE, trial_name=name)
            for name in ("t1__aaa", "t2__bbb")
        }
        backend = make_backend_keyed(responses)

        install_trial_log_prefix()
        with caplog.at_level(logging_mod.INFO):
            Analyzer(backend=backend, rubric=rubric, model="m",
                     jobs=2).analyze_job(tmp_path)

        finished = [
            r.getMessage() for r in caplog.records
            if "analysis finished" in r.getMessage()
        ]
        assert len(finished) == 2
        assert {m.split("]")[0] + "]" for m in finished} == {
            "[t1__aaa]", "[t2__bbb]",
        }
