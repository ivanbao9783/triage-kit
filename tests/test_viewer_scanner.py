"""Tests for triage_kit.viewer.scanner — plain-JSON product discovery.

The scanner is the viewer's entire data layer: it must read the
`triage-kit/` sub-directory layout with zero upstream model
dependencies, tolerate missing native side files, and never crash on a
raw evaluation directory (diagnosis degrades to empty).
"""

import json

import pytest

from tests.conftest import make_task, make_trial
from triage_kit.viewer import scanner


def write_products(directory, *, md="# diag\n", analysis=True):
    """Drop a triage-kit/ product dir next to evaluation data."""
    tk = directory / "triage-kit"
    tk.mkdir(parents=True, exist_ok=True)
    if analysis:
        (tk / "analysis.json").write_text("{}", encoding="utf-8")
    if md is not None:
        (tk / "analysis.md").write_text(md, encoding="utf-8")
    return tk


def make_full_trial(path, *, reward=0.0, with_diagnosis=True):
    """A trial carrying every native side file the viewer reads."""
    path.mkdir(parents=True)
    (path / "trial.log").write_text("", encoding="utf-8")
    result = {
        "trial_name": path.name,
        "task_name": "demo-task",
        "agent_info": {
            "name": "mini-swe-agent",
            "model_info": {"provider": "anthropic", "name": "claude-x"},
        },
        "agent_result": {
            "n_input_tokens": 100,
            "n_cache_tokens": 50,
            "n_output_tokens": 20,
            "cost_usd": 0.0123,
        },
        "verifier_result": {
            "rewards": {
                "reward": reward,
                "f2p_passed": 3,
                "f2p_total": 4,
                "p2p_passed": 10,
                "p2p_total": 10,
                "partial": 0.75,
            }
        },
        "exception_info": None,
        "environment_setup": {"started_at": "2026-10-12T10:00:00Z",
                              "finished_at": "2026-10-12T10:00:05Z"},
        "agent_setup": {"started_at": "2026-10-12T10:00:05Z",
                        "finished_at": "2026-10-12T10:00:06Z"},
        "agent_execution": {"started_at": "2026-10-12T10:00:06Z",
                            "finished_at": "2026-10-12T10:01:00Z"},
        "verifier": {"started_at": "2026-10-12T10:01:00Z",
                     "finished_at": "2026-10-12T10:01:30Z"},
        "started_at": "2026-10-12T10:00:00Z",
        "finished_at": "2026-10-12T10:01:30Z",
    }
    (path / "result.json").write_text(json.dumps(result), encoding="utf-8")

    (path / "verifier").mkdir()
    (path / "verifier" / "ctrf.json").write_text(json.dumps({
        "results": {
            "tool": {"name": "pytest"},
            "summary": {"tests": 14, "passed": 13, "failed": 1},
            "tests": [{"name": "t::ok", "status": "passed"},
                      {"name": "t::bad", "status": "failed"}],
        }
    }), encoding="utf-8")

    (path / "artifacts").mkdir()
    (path / "artifacts" / "manifest.json").write_text(json.dumps([
        {"source": "/s", "destination": "/d", "type": "file", "status": "ok"}
    ]), encoding="utf-8")

    if with_diagnosis:
        write_products(path)
    return path


class TestDetectMode:
    def test_trial_dir(self, tmp_path):
        t = tmp_path / "t1__aaa"
        make_trial(t, reward=1.0)
        assert scanner.detect_mode(t) == "trial"

    def test_job_dir(self, tmp_path):
        make_trial(tmp_path / "t1__aaa", reward=1.0)
        assert scanner.detect_mode(tmp_path) == "job"

    def test_tasks_root_rejected_as_check_unsupported(self, tmp_path):
        """tasks 目录属于 check 模式，本版本不支持 → 专用错误。"""
        make_task(tmp_path / "task-a")
        with pytest.raises(scanner.CheckModeUnsupported):
            scanner.detect_mode(tmp_path)

    def test_single_task_dir_rejected_as_check_unsupported(self, tmp_path):
        task = tmp_path / "task-a"
        make_task(task)
        with pytest.raises(scanner.CheckModeUnsupported):
            scanner.detect_mode(task)

    def test_empty_dir_errors(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ValueError):
            scanner.detect_mode(empty)


class TestScanTrials:
    def test_lexicographic_with_fields(self, tmp_path):
        make_trial(tmp_path / "b__2", reward=0.0)
        make_trial(tmp_path / "a__1", reward=1.0)
        write_products(tmp_path / "a__1")

        trials = scanner.scan_trials(tmp_path)

        assert [t["name"] for t in trials] == ["a__1", "b__2"]
        assert trials[0]["reward"] == 1
        assert trials[0]["resolved"] is True
        assert trials[0]["has_diagnosis"] is True
        assert trials[1]["reward"] == 0
        assert trials[1]["resolved"] is False
        assert trials[1]["has_diagnosis"] is False

    def test_skips_subdirs_without_result_json(self, tmp_path):
        make_trial(tmp_path / "a__1", reward=1.0)
        (tmp_path / "junk").mkdir()

        trials = scanner.scan_trials(tmp_path)

        assert [t["name"] for t in trials] == ["a__1"]

    def test_reward_falls_back_to_verifier_reward_json(self, tmp_path):
        t = tmp_path / "a__1"
        t.mkdir()
        (t / "trial.log").write_text("", encoding="utf-8")
        (t / "result.json").write_text(
            json.dumps({"trial_name": "a__1"}), encoding="utf-8"
        )
        (t / "verifier").mkdir()
        (t / "verifier" / "reward.json").write_text(
            json.dumps({"reward": 0.5}), encoding="utf-8"
        )

        trials = scanner.scan_trials(tmp_path)

        assert trials[0]["reward"] == 0.5

    def test_missing_result_pure_result_json_reward_none(self, tmp_path):
        t = tmp_path / "a__1"
        t.mkdir()
        (t / "trial.log").write_text("", encoding="utf-8")
        (t / "result.json").write_text(
            json.dumps({"trial_name": "a__1"}), encoding="utf-8"
        )

        trials = scanner.scan_trials(tmp_path)

        assert trials[0]["reward"] is None


class TestScanTrialFields:
    def test_rich_fields_from_full_trial(self, tmp_path):
        make_full_trial(tmp_path / "a__1", reward=1.0)

        (row,) = scanner.scan_trials(tmp_path)

        assert row["resolved"] is True
        assert row["tokens_in"] == 100
        assert row["tokens_out"] == 20
        assert row["duration_sec"] == 90.0
        assert row["failed_tests"] == 1
        assert row["has_exception"] is False

    def test_minimal_trial_degrades_to_none_fields(self, tmp_path):
        make_trial(tmp_path / "a__1", reward=0.0)

        (row,) = scanner.scan_trials(tmp_path)

        assert row["tokens_in"] is None
        assert row["tokens_out"] is None
        assert row["duration_sec"] is None
        assert row["failed_tests"] is None
        assert row["has_exception"] is False
        assert row["resolved"] is False

    def test_exception_flag(self, tmp_path):
        make_trial(tmp_path / "a__1", reward=0.0, exception=True)

        (row,) = scanner.scan_trials(tmp_path)

        assert row["has_exception"] is True


class TestRewardSelection:
    def _trials(self):
        return [{"name": "a", "reward": 1}, {"name": "b", "reward": 0},
                {"name": "c", "reward": None}]

    def test_counts(self):
        assert scanner.reward_counts(self._trials()) == {
            "all": 3, "1": 1, "0": 1
        }

    def test_select_reward_zero(self):
        got = scanner.select_reward(self._trials(), "0")
        assert [t["name"] for t in got] == ["b"]

    def test_select_reward_one(self):
        got = scanner.select_reward(self._trials(), "1")
        assert [t["name"] for t in got] == ["a"]

    def test_select_reward_none_keeps_all(self):
        assert len(scanner.select_reward(self._trials(), None)) == 3
        assert len(scanner.select_reward(self._trials(), "bogus")) == 3


class TestRewardItems:
    def test_pairs_passed_total_into_ratio(self):
        items = scanner.reward_items({
            "reward": 1, "f2p_passed": 3, "f2p_total": 4, "partial": 0.75,
        })

        assert [i["key"] for i in items] == ["f2p", "partial"]
        f2p = items[0]
        assert (f2p["passed"], f2p["total"], f2p["ratio"]) == (3, 4, 0.75)
        # a plain scalar key keeps its value and carries no ratio
        assert items[1]["value"] == 0.75
        assert items[1]["ratio"] is None

    def test_dataset_agnostic_no_hardcoded_keys(self):
        items = scanner.reward_items(
            {"reward": 0, "tests_passed": 2, "tests_total": 2}
        )

        assert items == [{"key": "tests", "value": None,
                          "passed": 2, "total": 2, "ratio": 1.0}]

    def test_zero_total_yields_no_ratio(self):
        items = scanner.reward_items({"ui_passed": 0, "ui_total": 0})

        assert items[0]["ratio"] is None

    def test_main_reward_excluded(self):
        assert scanner.reward_items({"reward": 1}) == []

    def test_empty_block(self):
        assert scanner.reward_items(None) == []
        assert scanner.reward_items({}) == []


class TestSummarize:
    def _trials(self):
        return [
            {"reward": 1.0, "tokens_in": 100, "tokens_out": 20,
             "duration_sec": 90.0, "has_exception": False},
            {"reward": 0.0, "tokens_in": 50, "tokens_out": 10,
             "duration_sec": 30.0, "has_exception": True},
            {"reward": None, "tokens_in": None, "tokens_out": None,
             "duration_sec": None, "has_exception": False},
        ]

    def test_counts_rate_and_totals(self):
        s = scanner.summarize(self._trials())

        assert s["trials"] == 3
        assert s["resolved"] == 1
        assert s["rewarded"] == 2
        assert s["resolved_rate"] == 0.5
        assert s["tokens_in"] == 150
        assert s["tokens_out"] == 30
        assert s["avg_duration_sec"] == 60.0
        assert s["exceptions"] == 1

    def test_empty_trials_degrade_to_none(self):
        s = scanner.summarize([])

        assert s["trials"] == 0
        assert s["resolved_rate"] is None
        assert s["tokens_in"] is None
        assert s["avg_duration_sec"] is None


class TestLoadOverview:
    def test_job_md_and_counts(self, tmp_path):
        make_trial(tmp_path / "a__1", reward=1.0)
        make_trial(tmp_path / "b__2", reward=0.0)
        write_products(tmp_path, md="# Job Summary\n")

        ov = scanner.load_overview(tmp_path)

        assert ov["job_md"] == "# Job Summary\n"
        assert ov["counts"] == {"all": 2, "1": 1, "0": 1}
        assert [t["name"] for t in ov["trials"]] == ["a__1", "b__2"]
        assert ov["summary"]["trials"] == 2
        assert ov["summary"]["resolved_rate"] == 0.5

    def test_job_md_none_when_no_products(self, tmp_path):
        make_trial(tmp_path / "a__1", reward=1.0)

        ov = scanner.load_overview(tmp_path)

        assert ov["job_md"] is None
        assert ov["counts"]["all"] == 1
        assert ov["summary"]["resolved"] == 1


class TestLoadTrial:
    def test_native_blocks_extracted(self, tmp_path):
        t = make_full_trial(tmp_path / "a__1")

        d = scanner.load_trial(t)

        assert d["name"] == "a__1"
        assert d["task_name"] == "demo-task"
        assert d["agent_name"] == "mini-swe-agent"
        assert d["model"] == "anthropic/claude-x"
        assert d["reward"] == 0.0
        assert d["resolved"] is False
        assert [i["key"] for i in d["reward_items"]] == ["f2p", "p2p", "partial"]
        f2p = d["reward_items"][0]
        assert (f2p["passed"], f2p["total"], f2p["ratio"]) == (3, 4, 0.75)
        assert d["reward_items"][2]["value"] == 0.75
        assert d["tokens"] == {"input": 100, "cache": 50, "output": 20,
                               "cost": 0.0123}
        labels = [p["label"] for p in d["timing"]]
        assert labels == ["Environment setup", "Agent setup",
                          "Agent execution", "Verifier"]
        assert d["timing"][0]["sec"] == 5.0
        assert d["total_sec"] == 90.0
        assert d["ctrf"]["summary"]["failed"] == 1
        assert d["manifest"][0]["type"] == "file"
        assert d["analysis_md"] == "# diag\n"

    def test_degrades_on_missing_side_files(self, tmp_path):
        t = tmp_path / "a__1"
        make_trial(t, reward=1.0)  # no ctrf / manifest / agent blocks

        d = scanner.load_trial(t)

        assert d["ctrf"] == {}
        assert d["manifest"] == []
        assert d["analysis_md"] is None
        assert d["reward"] == 1.0
        assert d["resolved"] is True
        assert d["reward_items"] == []
        assert d["exception"] == {}

    def test_exception_info_passed_through(self, tmp_path):
        t = tmp_path / "a__1"
        make_trial(t, reward=0.0, exception=True)

        d = scanner.load_trial(t)

        assert d["exception"] == "boom"

    def test_analysis_md_only_json_still_none(self, tmp_path):
        t = tmp_path / "a__1"
        make_trial(t, reward=1.0)
        write_products(t, md=None)  # analysis.json only, no md

        d = scanner.load_trial(t)

        assert d["analysis_md"] is None


class TestTimeHelpers:
    def test_parse_dt_handles_z_and_garbage(self):
        assert scanner.parse_dt("2026-10-12T10:00:00Z") is not None
        assert scanner.parse_dt("not-a-date") is None
        assert scanner.parse_dt(None) is None

    def test_duration_sec_rounds_to_tenths(self):
        phase = {"started_at": "2026-10-12T10:00:00Z",
                 "finished_at": "2026-10-12T10:00:05.500Z"}
        assert scanner.duration_sec(phase) == 5.5

    def test_duration_sec_none_when_incomplete(self):
        assert scanner.duration_sec({"started_at": "2026-10-12T10:00:00Z"}) is None
        assert scanner.duration_sec(None) is None