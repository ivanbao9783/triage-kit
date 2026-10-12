"""Tests for triage_kit.viewer.server — the zero-build SSR routes.

Uses fastapi.testclient (httpx) so routing, filtering, markdown
rendering and the graceful-degradation paths are asserted end to end
without starting a real server.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_trial
from tests.test_viewer_scanner import make_full_trial, write_products
from triage_kit.viewer import server


def client(root):
    return TestClient(server.create_app(root))


def trials_table(html):
    """The overview table slice, excluding the always-full left nav."""
    return html.split('id="trials"', 1)[1]


def write_trajectory(trial_dir):
    """Drop an ATIF trajectory.json into a trial's agent/ directory."""
    agent = trial_dir / "agent"
    agent.mkdir(exist_ok=True)
    (agent / "trajectory.json").write_text(json.dumps({
        "steps": [
            {"step_id": 1, "source": "assistant",
             "timestamp": "2026-10-12T10:00:06Z", "message": "let me look",
             "tool_calls": [{"tool_call_id": "c1", "function_name": "bash",
                             "arguments": {"command": "ls -la"}}],
             "observation": {"results": [
                 {"source_call_id": "c1", "content": "file.txt"}]}},
            {"step_id": 2, "source": "assistant",
             "timestamp": "2026-10-12T10:00:10Z", "message": "done",
             "tool_calls": [{"tool_call_id": "c2", "function_name": "edit",
                             "arguments": {"path": "a.py"}}]},
        ]
    }), encoding="utf-8")


@pytest.fixture
def job(tmp_path):
    make_full_trial(tmp_path / "a__1", reward=1.0)
    make_full_trial(tmp_path / "b__2", reward=0.0)
    write_products(
        tmp_path,
        md="# Job Summary\n\n| k | v |\n|---|---|\n| x | 1 |\n",
    )
    return tmp_path


@pytest.fixture
def job_with_traj(tmp_path):
    trial = make_full_trial(tmp_path / "a__1", reward=1.0)
    write_trajectory(trial)
    return tmp_path


class TestOverviewRoute:
    def test_lists_trials_and_renders_job_md(self, job):
        r = client(job).get("/")

        assert r.status_code == 200
        assert "a__1" in r.text and "b__2" in r.text
        assert "Job Summary" in r.text
        # the markdown pipe table must become a real HTML table
        assert "<table>" in r.text

    def test_reward_filter_zero_keeps_only_failures(self, job):
        r = client(job).get("/?reward=0")

        assert r.status_code == 200
        assert "/trial/b__2" in trials_table(r.text)
        assert "/trial/a__1" not in trials_table(r.text)

    def test_reward_filter_one_keeps_only_passes(self, job):
        r = client(job).get("/?reward=1")

        assert r.status_code == 200
        assert "/trial/a__1" in trials_table(r.text)
        assert "/trial/b__2" not in trials_table(r.text)

    def test_filter_row_lists_counts(self, job):
        r = client(job).get("/")

        assert "?reward=1" in r.text and "?reward=0" in r.text
        assert "ALL 2" in r.text
        assert "Resolved 1" in r.text
        assert "Unresolved 1" in r.text
        # links keep the view anchored at the trials list (no jump to top)
        assert 'href="/?reward=1#trials"' in r.text

    def test_degraded_without_products(self, tmp_path):
        make_trial(tmp_path / "a__1", reward=1.0)

        r = client(tmp_path).get("/")

        assert r.status_code == 200
        assert "a__1" in r.text
        assert "triage-kit/analysis.md" in r.text  # degradation hint

    def test_missing_root_404(self, tmp_path):
        r = client(tmp_path / "nope").get("/")

        assert r.status_code == 404


class TestTrialRoute:
    def test_overview_is_the_default_tab(self, job):
        r = client(job).get("/trial/a__1")

        assert r.status_code == 200
        assert "mini-swe-agent" in r.text
        assert "anthropic/claude-x" in r.text
        assert "Environment setup" in r.text  # timing phase
        assert "Artifacts" in r.text

    def test_diagnosis_tab_renders_analysis_md(self, job):
        r = client(job).get("/trial/a__1?tab=diagnosis")

        assert r.status_code == 200
        assert "diag" in r.text  # the trial's analysis.md, rendered

    def test_unknown_trial_404(self, job):
        assert client(job).get("/trial/nope").status_code == 404

    def test_degraded_diagnosis_hint(self, tmp_path):
        make_trial(tmp_path / "a__1", reward=1.0)

        r = client(tmp_path).get("/trial/a__1?tab=diagnosis")

        assert r.status_code == 200
        assert "无诊断产物" in r.text

    def test_rejects_path_traversal(self, job):
        r = client(job).get("/trial/..%2F..%2Fetc")

        assert r.status_code == 404


class TestOverviewKpiAndNav:
    def test_kpi_band_and_callout(self, job):
        r = client(job).get("/")

        assert r.status_code == 200
        assert "Resolved 率" in r.text
        assert "平均耗时" in r.text

    def test_nav_tree_stays_full_when_filtered(self, job):
        r = client(job).get("/?reward=0")

        # the left rail keeps every trial regardless of the table filter
        assert 'href="/trial/a__1"' in r.text
        assert 'href="/trial/b__2"' in r.text

    def test_nav_tree_lists_all_on_unfiltered(self, job):
        r = client(job).get("/")

        assert 'href="/trial/a__1"' in r.text
        assert 'href="/trial/b__2"' in r.text


class TestTrialRewardBreakdown:
    def test_generic_reward_items_rendered(self, job):
        r = client(job).get("/trial/a__1?tab=score")

        assert r.status_code == 200
        assert "Reward 分项" in r.text
        assert "3/4" in r.text  # f2p_passed / f2p_total, dataset-agnostic

    def test_score_tab_renders_ctrf_and_exception(self, job):
        r = client(job).get("/trial/a__1?tab=score")

        assert r.status_code == 200
        assert "CTRF" in r.text
        assert "Exception" in r.text

    def test_all_tests_listed_with_status_badges(self, job):
        r = client(job).get("/trial/a__1?tab=score")

        assert "测试用例" in r.text
        # passing cases are listed too, not just failures
        assert "t::ok" in r.text and "t::bad" in r.text
        assert ">pass<" in r.text and ">fail<" in r.text

    def test_trial_page_nav_lists_siblings(self, job):
        r = client(job).get("/trial/a__1")

        assert 'href="/trial/a__1"' in r.text
        assert 'href="/trial/b__2"' in r.text


class TestTrialTabs:
    def test_tab_bar_links_every_tab(self, job):
        r = client(job).get("/trial/a__1")

        for key in server.TABS:
            assert f"?tab={key}" in r.text
        # the active tab is marked
        assert 'class="tab on"' in r.text

    def test_unknown_tab_falls_back_to_overview(self, job):
        r = client(job).get("/trial/a__1?tab=bogus")

        assert r.status_code == 200
        assert "Artifacts" in r.text  # overview content

    def test_trace_tab_degrades_without_trajectory(self, job):
        r = client(job).get("/trial/a__1?tab=trace")

        assert r.status_code == 200
        assert "无轨迹数据" in r.text

    def test_tools_tab_degrades_without_trajectory(self, job):
        r = client(job).get("/trial/a__1?tab=tools")

        assert r.status_code == 200
        assert "无轨迹数据" in r.text

    def test_trace_tab_renders_steps_and_tools(self, job_with_traj):
        r = client(job_with_traj).get("/trial/a__1?tab=trace")

        assert r.status_code == 200
        assert "逐步明细" in r.text
        assert "ls -la" in r.text  # command rendered as a cmd block
        assert "file.txt" in r.text  # observation tied to its call
        assert "每步 token 用量" in r.text

    def test_tools_tab_renders_aggregation_and_details(self, job_with_traj):
        r = client(job_with_traj).get("/trial/a__1?tab=tools")

        assert r.status_code == 200
        assert "工具聚合" in r.text
        assert "调用明细" in r.text
        assert "bash" in r.text and "edit" in r.text
        assert "调用次数" in r.text  # KPI band

    def test_trace_bars_deep_link_to_steps(self, job_with_traj):
        r = client(job_with_traj).get("/trial/a__1?tab=trace")

        assert 'id="step-1"' in r.text and 'id="step-2"' in r.text
        # each token bar links back to (and opens) its own step
        assert "step=1#step-1" in r.text
        assert "step=2#step-2" in r.text

    def test_trace_step_param_opens_that_step(self, job_with_traj):
        r = client(job_with_traj).get("/trial/a__1?tab=trace&step=2")

        # whitespace between attributes is insignificant
        assert re.search(r'id="step-2"\s+open', r.text)


class TestSingleTrialInput:
    def test_root_renders_the_trial_page(self, tmp_path):
        make_full_trial(tmp_path / "a__1")

        r = client(tmp_path / "a__1").get("/")

        assert r.status_code == 200
        assert "mini-swe-agent" in r.text

    def test_root_serves_diagnosis_tab(self, tmp_path):
        make_full_trial(tmp_path / "a__1")

        r = client(tmp_path / "a__1").get("/?tab=diagnosis")

        assert r.status_code == 200
        assert "diag" in r.text
        # single-trial tab links stay rooted at '/'
        assert 'href="/?tab=score"' in r.text