"""Tests for triage_kit.cli — command entry, arg parsing, wiring.

The backend factory (build_backend) is monkeypatched with a FakeBackend, so
CLI wiring — path dispatch, option plumbing, product placement — is tested
without typer's app depending on openai/claude SDKs being installed.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import make_task, make_trial

runner = CliRunner()


def _patch_openai_with_fake(monkeypatch):
    """Swap sys.modules['openai'] for a capture stub; returns captured kwargs."""
    import sys

    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", type(sys)("openai"))
    sys.modules["openai"].OpenAI = FakeOpenAI
    return captured


def make_fake_backend():
    from triage_kit.core.contract import AgentMeta

    class FakeBackend:
        def __init__(self):
            self.agent_prompts: list[str] = []
            self.plain_prompts: list[str] = []
            self.calls: list[dict] = []

        def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                        output_schema=None, max_turns=15):
            self.agent_prompts.append(prompt)
            self.calls.append({"kind": "agent", "cwd": str(cwd),
                               "model": model,
                               "add_dirs": [str(d) for d in (add_dirs or [])]})
            response = self._response_for(output_schema)
            # The analyzer asserts trial_name matches the trial directory,
            # so the fake must echo the real directory name.
            if "trial_name" in response:
                response["trial_name"] = Path(cwd).name
            return response, AgentMeta(
                n_turns=1, model=model
            )

        def query(self, prompt, *, model):
            self.plain_prompts.append(prompt)
            return "JOB SUMMARY", AgentMeta(n_turns=0, model=model)

        def _response_for(self, output_schema):
            # fill every field the dynamic schema requires
            schema = output_schema.model_json_schema()
            props = schema.get("properties", {})
            defs = schema.get("$defs", {})

            def resolve(ref: str) -> dict:
                return defs[ref.split("/")[-1]]

            checks_spec = props.get("checks", {})
            if "$ref" in checks_spec:
                checks_spec = resolve(checks_spec["$ref"])
            if "allOf" in checks_spec:
                checks_spec = resolve(checks_spec["allOf"][0]["$ref"])
            check_names = checks_spec.get("properties", {})

            response = {
                "checks": {
                    name: {"outcome": "pass", "explanation": "ok"}
                    for name in check_names
                }
            }
            if "trial_name" in props:  # analyze model
                response["trial_name"] = "x"
            if "summary" in props:
                response["summary"] = "s"
            return response

    return FakeBackend()


@pytest.fixture
def fake_backend(monkeypatch):
    backend = make_fake_backend()
    import triage_kit.cli as cli

    monkeypatch.setattr(cli, "build_backend", lambda *a, **kw: backend)
    return backend


@pytest.fixture
def trial(tmp_path):
    t = tmp_path / "demo__abc123"
    make_trial(t, reward=0.0)
    return t


class TestAnalyzeCommand:
    def test_identity_mismatch_errors_and_force_overrides(
        self, fake_backend, trial
    ):
        """缓存身份不符 → 报错退出；--force → 重跑覆盖。"""
        import hashlib

        from triage_kit.cli import app

        # 首跑：glm-4.7
        result = runner.invoke(
            app, ["analyze", str(trial), "--model", "glm-4.7"]
        )
        assert result.exit_code == 0, result.output

        # 换 model 重跑 → 非零退出 + 提示 force
        result = runner.invoke(
            app, ["analyze", str(trial), "--model", "glm-5.3"]
        )
        assert result.exit_code != 0
        assert "force" in result.output

        # --force → 成功，sidecar model 更新
        result = runner.invoke(
            app, ["analyze", str(trial), "--model", "glm-5.3", "--force"]
        )
        assert result.exit_code == 0, result.output
        meta = json.loads(
            (trial / "triage-kit" / "analysis.meta.json").read_text())
        assert meta["model"] == "glm-5.3"

    def test_trial_dir_writes_analysis(self, fake_backend, trial):
        from triage_kit.cli import app

        result = runner.invoke(app, ["analyze", str(trial), "--model", "m1"])

        assert result.exit_code == 0, result.output
        assert (trial / "triage-kit" / "analysis.json").is_file()
        assert (trial / "triage-kit" / "analysis.md").is_file()
        assert len(fake_backend.agent_prompts) == 1
        assert fake_backend.calls[0]["cwd"] == str(trial)

    def test_job_dir_aggregates(self, fake_backend, tmp_path):
        from triage_kit.cli import app

        make_trial(tmp_path / "t1__aaa", reward=1.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)

        result = runner.invoke(app, ["analyze", str(tmp_path), "--model", "m1"])

        assert result.exit_code == 0, result.output
        # both trials + one aggregation
        assert len(fake_backend.agent_prompts) == 2
        assert len(fake_backend.plain_prompts) == 1
        assert (tmp_path / "triage-kit" / "analysis.json").is_file()

    def test_failing_flag_limits_trials(self, fake_backend, tmp_path):
        from triage_kit.cli import app

        make_trial(tmp_path / "t1__aaa", reward=1.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)

        result = runner.invoke(
            app, ["analyze", str(tmp_path), "--failing", "--model", "m1"]
        )

        assert result.exit_code == 0, result.output
        assert len(fake_backend.agent_prompts) == 1

    def test_task_dir_option_plumbed_through(self, fake_backend, trial,
                                             tmp_path):
        from triage_kit.cli import app

        task = tmp_path / "task"
        make_task(task)

        result = runner.invoke(
            app, ["analyze", str(trial), "--task-dir", str(task),
                  "--model", "m1"]
        )

        assert result.exit_code == 0, result.output
        call = fake_backend.calls[0]
        # task dir lands in add_dirs (agent-readable alongside the trial)
        assert str(task) in call["add_dirs"]

    def test_custom_rubric_path(self, fake_backend, trial, tmp_path):
        from triage_kit.cli import app

        custom = tmp_path / "my-rubric.toml"
        custom.write_text(
            '[[criteria]]\nname = "only_one"\ndescription = "d"\n'
            'guidance = "g"\n',
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["analyze", str(trial), "--rubric", str(custom),
                  "--model", "m1"]
        )

        assert result.exit_code == 0, result.output
        # the custom criterion name reaches the prompt
        assert "only_one" in fake_backend.agent_prompts[0]
        saved = json.loads(
            (trial / "triage-kit" / "analysis.json").read_text(encoding="utf-8"))
        assert "only_one" in saved["checks"]

    def test_task_dir_option_nonexistent_errors(self, fake_backend, trial,
                                                  tmp_path):
        """M6: --task-dir 指向不存在的目录必须显式报错，
        而非让 prompt 声称一个假路径。"""
        from triage_kit.cli import app

        result = runner.invoke(
            app, ["analyze", str(trial), "--task-dir", str(tmp_path / "nope"),
                  "--model", "m1"]
        )
        assert result.exit_code != 0
        assert "task-dir" in result.output

    def test_invalid_path_errors(self, fake_backend, tmp_path):
        from triage_kit.cli import app

        empty = tmp_path / "nothing"
        empty.mkdir()
        result = runner.invoke(app, ["analyze", str(empty)])

        assert result.exit_code != 0

    def test_missing_path_errors(self, fake_backend, tmp_path):
        from triage_kit.cli import app

        result = runner.invoke(app, ["analyze", str(tmp_path / "nope")])

        assert result.exit_code != 0


class TestJobsOption:
    """P003: `-j/--jobs` — analyze 并发度（job 模式）。"""

    def test_jobs_zero_rejected(self, fake_backend, trial):
        from triage_kit.cli import app

        result = runner.invoke(
            app, ["analyze", str(trial), "--model", "m1", "--jobs", "0"]
        )
        assert result.exit_code != 0
        assert "--jobs" in result.output

    def test_negative_jobs_rejected(self, fake_backend, trial):
        from triage_kit.cli import app

        result = runner.invoke(
            app, ["analyze", str(trial), "--model", "m1", "-j", "-1"]
        )
        assert result.exit_code != 0
        assert "--jobs" in result.output

    def test_jobs_two_on_job_dir(self, fake_backend, tmp_path):
        from triage_kit.cli import app

        make_trial(tmp_path / "t1__aaa", reward=0.0)
        make_trial(tmp_path / "t2__bbb", reward=0.0)

        result = runner.invoke(
            app, ["analyze", str(tmp_path), "--model", "m1", "-j", "2"]
        )

        assert result.exit_code == 0, result.output
        assert len(fake_backend.agent_prompts) == 2
        assert (tmp_path / "triage-kit" / "analysis.json").is_file()

    def test_jobs_ignored_for_single_trial_dir(self, fake_backend, trial):
        """单 trial 直调不进池：-j 只影响 job 模式。"""
        from triage_kit.cli import app

        result = runner.invoke(
            app, ["analyze", str(trial), "--model", "m1", "-j", "4"]
        )

        assert result.exit_code == 0, result.output
        assert len(fake_backend.agent_prompts) == 1


class TestModelValidation:
    """Model authority lives at the CLI layer:
    - general: -m is mandatory (no sane default across OpenAI-compatible
      endpoints, and a literal 'default' in AgentMeta would be a lie);
    - claude: pier-compatible defaults (analyze: haiku, check: sonnet)."""

    def test_general_without_model_errors(self, monkeypatch, trial):
        import triage_kit.cli as cli

        from triage_kit.cli import app

        monkeypatch.setattr(cli, "build_backend", lambda *a, **kw: None)
        result = runner.invoke(app, ["analyze", str(trial),
                                     "--backend", "general"])
        assert result.exit_code != 0
        assert "--model" in result.output

    def test_general_check_without_model_errors(self, monkeypatch, tmp_path):
        import triage_kit.cli as cli

        from triage_kit.cli import app

        monkeypatch.setattr(cli, "build_backend", lambda *a, **kw: None)
        result = runner.invoke(app, ["check", str(tmp_path),
                                     "--backend", "general"])
        assert result.exit_code != 0
        assert "--model" in result.output

    def test_claude_analyze_defaults_to_haiku(self, fake_backend, trial):
        from triage_kit.cli import app

        result = runner.invoke(app, ["analyze", str(trial),
                                     "--backend", "claude"])
        assert result.exit_code == 0, result.output
        assert fake_backend.calls[0]["model"] == "haiku"

    def test_claude_check_defaults_to_sonnet(self, fake_backend, tmp_path):
        from triage_kit.cli import app

        task = tmp_path / "task"
        make_task(task)
        result = runner.invoke(app, ["check", str(task),
                                     "--backend", "claude"])
        assert result.exit_code == 0, result.output
        assert fake_backend.calls[0]["model"] == "sonnet"

    def test_general_with_model_passes(self, fake_backend, trial):
        from triage_kit.cli import app

        result = runner.invoke(app, ["analyze", str(trial),
                                     "--backend", "general",
                                     "--model", "glm-4.7"])
        assert result.exit_code == 0, result.output
        assert fake_backend.calls[0]["model"] == "glm-4.7"


class TestCheckCommand:
    def test_task_dir_writes_check_result(self, fake_backend, tmp_path):
        from triage_kit.cli import app

        task = tmp_path / "task"
        make_task(task)

        result = runner.invoke(app, ["check", str(task), "--model", "m1"])

        assert result.exit_code == 0, result.output
        out = task / "triage-kit" / "check-result.json"
        assert out.is_file()
        saved = json.loads(out.read_text(encoding="utf-8"))
        assert "behavior_in_task_description" in saved["checks"]
        assert fake_backend.calls[0]["cwd"] == str(task)

    def test_rubric_option_accepts_path(self, fake_backend, tmp_path):
        from triage_kit.cli import app

        task = tmp_path / "task"
        make_task(task)
        custom = tmp_path / "r.toml"
        custom.write_text(
            '[[criteria]]\nname = "one_check"\ndescription = "d"\n'
            'guidance = "g"\n',
            encoding="utf-8",
        )

        result = runner.invoke(
            app, ["check", str(task), "--rubric", str(custom),
                  "--model", "m1"]
        )

        assert result.exit_code == 0, result.output
        saved = json.loads(
            (task / "triage-kit" / "check-result.json").read_text(encoding="utf-8")
        )
        assert list(saved["checks"]) == ["one_check"]

    def test_missing_path_errors(self, fake_backend, tmp_path):
        from triage_kit.cli import app

        result = runner.invoke(
            app, ["check", str(tmp_path / "nope"), "--model", "m1"]
        )
        assert result.exit_code != 0

    def test_invalid_task_dir_errors(self, fake_backend, tmp_path):
        """M2: 无 task.toml 的目录不是合法任务 → 非零退出。"""
        from triage_kit.cli import app

        empty = tmp_path / "not-a-task"
        empty.mkdir()
        result = runner.invoke(app, ["check", str(empty), "--model", "m1"])
        assert result.exit_code != 0


class TestCleanCommand:
    """triage clean: 复原原生输入——递归删除 triage-kit/ 产物目录。"""

    @staticmethod
    def _make_job_with_products(tmp_path):
        """job 级 + trial 级产物俱全的 job 结构。"""
        job = tmp_path / "job"
        make_trial(job / "t1__aaa", reward=0.0)
        for d in (job, job / "t1__aaa"):
            tk = d / "triage-kit"
            tk.mkdir(parents=True)
            (tk / "analysis.json").write_text("{}", encoding="utf-8")
        return job

    def test_dry_run_lists_but_keeps_everything(self, tmp_path):
        """默认 dry-run：列出待删清单但不删。"""
        from triage_kit.cli import app

        job = self._make_job_with_products(tmp_path)
        result = runner.invoke(app, ["clean", str(job)])

        assert result.exit_code == 0, result.output
        assert "would remove" in result.output
        assert str(job / "triage-kit") in result.output
        assert str(job / "t1__aaa" / "triage-kit") in result.output
        # nothing deleted
        assert (job / "triage-kit" / "analysis.json").is_file()
        assert (job / "t1__aaa" / "triage-kit" / "analysis.json").is_file()

    def test_yes_removes_products_preserves_originals(self, tmp_path):
        """--yes 真删：两个位置的产物目录都消失，原生数据零损伤。"""
        from triage_kit.cli import app

        job = self._make_job_with_products(tmp_path)
        result = runner.invoke(app, ["clean", str(job), "--yes"])

        assert result.exit_code == 0, result.output
        assert not (job / "triage-kit").exists()
        assert not (job / "t1__aaa" / "triage-kit").exists()
        # 原生评测数据原封不动
        assert (job / "t1__aaa" / "result.json").is_file()
        assert (job / "t1__aaa" / "trial.log").is_file()
        assert "removed" in result.output

    def test_no_products_reports_and_exits_cleanly(self, tmp_path):
        from triage_kit.cli import app

        plain = tmp_path / "plain"
        make_trial(plain / "t1__aaa", reward=0.0)
        result = runner.invoke(app, ["clean", str(plain)])

        assert result.exit_code == 0, result.output
        assert "No triage-kit" in result.output

    def test_missing_path_errors(self, tmp_path):
        from triage_kit.cli import app

        result = runner.invoke(
            app, ["clean", str(tmp_path / "no-such-dir")]
        )
        assert result.exit_code != 0
        assert "path not found" in result.stderr

    def test_path_is_file_errors(self, tmp_path):
        """路径是文件：明确报"not a directory"，不是 traceback。"""
        from triage_kit.cli import app

        f = tmp_path / "afile.txt"
        f.write_text("x", encoding="utf-8")
        result = runner.invoke(app, ["clean", str(f)])

        assert result.exit_code != 0
        assert "not a directory" in result.stderr

    def test_scan_permission_error_fails_with_clear_message(
        self, tmp_path, monkeypatch
    ):
        """rglob 扫描权限不足：报"cannot scan"，不崩溃成 traceback。"""
        from triage_kit.cli import app

        def boom(self, pattern):
            raise PermissionError("Access is denied")

        monkeypatch.setattr(Path, "rglob", boom)
        result = runner.invoke(app, ["clean", str(tmp_path)])

        assert result.exit_code != 0
        assert "cannot scan" in result.stderr
        # handled (SystemExit), not an uncaught crash
        assert not isinstance(result.exception, PermissionError)

    def test_remove_failure_names_target_and_continues(
        self, tmp_path, monkeypatch
    ):
        """rmtree 单个目标失败：点名失败目录，其余照删，非零退出。"""
        import shutil as shutil_mod

        from triage_kit.cli import app

        job = self._make_job_with_products(tmp_path)
        locked = job / "t1__aaa" / "triage-kit"
        real_rmtree = shutil_mod.rmtree

        def rmtree_or_raise(target, *a, **kw):
            if Path(target) == locked:
                raise PermissionError(f"Access is denied: {target}")
            return real_rmtree(target, *a, **kw)

        monkeypatch.setattr(shutil_mod, "rmtree", rmtree_or_raise)
        result = runner.invoke(app, ["clean", str(job), "--yes"])

        assert result.exit_code != 0
        assert "failed to remove" in result.stderr
        assert str(locked) in result.stderr
        # 其余目标不受牵连
        assert not (job / "triage-kit").exists()
        assert locked.exists()


class TestBackendSelection:
    def test_invalid_backend_name_errors(self, monkeypatch, trial):
        import triage_kit.cli as cli

        def boom(*a, **kw):
            raise ValueError(f"unknown backend {a[0]!r}")

        monkeypatch.setattr(cli, "build_backend", boom)

        from triage_kit.cli import app

        result = runner.invoke(
            app, ["analyze", str(trial), "--backend", "bogus"]
        )
        assert result.exit_code != 0

    def test_backend_factory_general_shape(self, monkeypatch):
        """The real factory maps names to harnesses with model plumbing."""
        import triage_kit.cli as cli

        captured = _patch_openai_with_fake(monkeypatch)

        harness = cli.build_backend("general", "glm-4.7", None)
        assert harness.default_model == "glm-4.7"
        assert "base_url" not in captured  # default endpoint

    def test_backend_factory_base_url(self, monkeypatch):
        import triage_kit.cli as cli

        captured = _patch_openai_with_fake(monkeypatch)

        cli.build_backend("general", "m", "https://api.example.com/v1")
        assert captured["base_url"] == "https://api.example.com/v1"

    def test_base_url_with_claude_backend_errors(self, monkeypatch, trial):
        """#7: --base-url 对 claude 后端无意义，必须显式拒绝而非静默忽略。"""
        from triage_kit.cli import app

        result = runner.invoke(
            app,
            ["analyze", str(trial), "--backend", "claude",
             "--base-url", "https://api.example.com/v1"],
        )
        assert result.exit_code != 0
        assert "ANTHROPIC_BASE_URL" in result.output

    def test_backend_factory_unknown_name_raises(self):
        import triage_kit.cli as cli

        with pytest.raises(ValueError):
            cli.build_backend("trae", "m", None)

    def test_base_url_host_added_to_no_proxy(self, monkeypatch):
        """A system proxy (Windows registry proxies) must not intercept an
        explicitly targeted endpoint: httpx honors NO_PROXY but skips the
        WinINET bypass list, so the CLI adds the host itself."""
        import os

        import triage_kit.cli as cli

        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.setattr(cli, "_open_general_backend",
                            lambda model, base_url: None)

        cli.build_backend(
            "general", "m", "https://internal.example.com/v1"
        )
        assert "internal.example.com" in os.environ["NO_PROXY"]

    def test_no_proxy_not_touched_without_base_url(self, monkeypatch):
        import os

        import triage_kit.cli as cli

        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.setattr(cli, "_open_general_backend",
                            lambda model, base_url: None)
        cli.build_backend("general", "m", None)
        assert "NO_PROXY" not in os.environ
