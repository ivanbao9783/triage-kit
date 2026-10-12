"""Tests for triage_kit.viewer.server — the zero-build SSR routes.

Uses fastapi.testclient (httpx) so routing, filtering, markdown
rendering and the graceful-degradation paths are asserted end to end
without starting a real server.
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_trial
from tests.test_viewer_scanner import make_full_trial, write_products
from triage_kit.viewer import server


def client(root):
    return TestClient(server.create_app(root))


@pytest.fixture
def job(tmp_path):
    make_full_trial(tmp_path / "a__1", reward=1.0)
    make_full_trial(tmp_path / "b__2", reward=0.0)
    write_products(
        tmp_path,
        md="# Job Summary\n\n| k | v |\n|---|---|\n| x | 1 |\n",
    )
    return tmp_path


class TestOverviewRoute:
    def test_lists_trials_and_renders_job_md(self, job):
        r = client(job).get("/")

        assert r.status_code == 200
        assert "a__1" in r.text and "b__2" in r.text
        assert "Job Summary" in r.text
        # the markdown pipe table must become a real HTML table (P006 D5)
        assert "<table>" in r.text

    def test_reward_filter_zero_keeps_only_failures(self, job):
        r = client(job).get("/?reward=0")

        assert r.status_code == 200
        assert "/trial/b__2" in r.text
        assert "/trial/a__1" not in r.text

    def test_reward_filter_one_keeps_only_passes(self, job):
        r = client(job).get("/?reward=1")

        assert r.status_code == 200
        assert "/trial/a__1" in r.text
        assert "/trial/b__2" not in r.text

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
    def test_renders_native_blocks_and_diagnosis(self, job):
        r = client(job).get("/trial/a__1")

        assert r.status_code == 200
        assert "mini-swe-agent" in r.text
        assert "anthropic/claude-x" in r.text
        assert "Environment setup" in r.text
        assert "diag" in r.text  # the trial's analysis.md, rendered

    def test_unknown_trial_404(self, job):
        assert client(job).get("/trial/nope").status_code == 404

    def test_degraded_diagnosis_hint(self, tmp_path):
        make_trial(tmp_path / "a__1", reward=1.0)

        r = client(tmp_path).get("/trial/a__1")

        assert r.status_code == 200
        assert "无诊断产物" in r.text

    def test_rejects_path_traversal(self, job):
        r = client(job).get("/trial/..%2F..%2Fetc")

        assert r.status_code == 404


class TestSingleTrialInput:
    def test_root_renders_the_trial_page(self, tmp_path):
        make_full_trial(tmp_path / "a__1")

        r = client(tmp_path / "a__1").get("/")

        assert r.status_code == 200
        assert "mini-swe-agent" in r.text
        assert "diag" in r.text