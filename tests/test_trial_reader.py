"""Tests for triage_kit.core.trial_reader — Harbor-native layout, plain JSON reads.

Runs against the real sample job exported from a Linux Harbor run
(``tmp_workspace/details``). Tests auto-skip if the sample is absent.
"""

import json
from pathlib import Path

import pytest

from tests.conftest import make_trial

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_JOB = REPO_ROOT.parent / "details"
SAMPLE_TRIAL = SAMPLE_JOB / "ts-pattern-match-each__9giF4pL"

needs_sample = pytest.mark.skipif(
    not SAMPLE_JOB.exists(), reason="real sample job dir not present"
)


class TestDirClassification:
    @needs_sample
    def test_trial_dir_recognized(self):
        from triage_kit.core.trial_reader import is_trial_dir

        assert is_trial_dir(SAMPLE_TRIAL) is True

    @needs_sample
    def test_job_dir_not_a_trial(self):
        from triage_kit.core.trial_reader import is_trial_dir, is_job_dir

        assert is_trial_dir(SAMPLE_JOB) is False
        assert is_job_dir(SAMPLE_JOB) is True

    def test_empty_dir_is_neither(self, tmp_path):
        from triage_kit.core.trial_reader import is_job_dir, is_trial_dir

        assert is_trial_dir(tmp_path) is False
        assert is_job_dir(tmp_path) is False


class TestListTrials:
    @needs_sample
    def test_lists_sample_trials(self):
        """Sample-content-insensitive: shape assertions plus the two
        trials the sample has carried since the 2-trial era."""
        from triage_kit.core.trial_reader import is_trial_dir, list_trials

        trials = list_trials(SAMPLE_JOB)
        names = {t.name for t in trials}
        assert {"ts-pattern-match-each__9giF4pL",
                "tomlkit-toml-table-converters__BVG4s9W"} <= names
        assert all(is_trial_dir(t) for t in trials)

    @needs_sample
    def test_failing_only_returns_non_passing_subset(self):
        """Every failing entry is genuinely non-passing (reward != 1 or
        exception recorded); the sample mixes passing and failing."""
        from triage_kit.core.trial_reader import list_trials

        trials = list_trials(SAMPLE_JOB)
        failing = list_trials(SAMPLE_JOB, failing_only=True)
        assert 0 < len(failing) < len(trials)
        assert {t.name for t in failing} < {t.name for t in trials}
        for t in failing:
            result = json.loads(
                (t / "result.json").read_text(encoding="utf-8")
            )
            reward = (
                (result.get("verifier_result") or {}).get("rewards") or {}
            ).get("reward")
            assert reward != 1 or result.get("exception_info") is not None

    def test_failing_only_keeps_failed_and_exception(self, tmp_path):
        from triage_kit.core.trial_reader import list_trials

        make_trial(tmp_path / "passed", reward=1.0)
        make_trial(tmp_path / "failed", reward=0.0)
        make_trial(tmp_path / "crashed", reward=1.0, exception=True)

        failing = list_trials(tmp_path, failing_only=True)
        assert {t.name for t in failing} == {"failed", "crashed"}


class TestTaskDirExtraction:
    @needs_sample
    def test_cross_machine_linux_path_degrades_to_none(self):
        """The canonical case: result copied off the eval machine."""
        from triage_kit.core.trial_reader import extract_task_dir

        assert extract_task_dir(SAMPLE_TRIAL) is None

    @needs_sample
    def test_override_wins(self, tmp_path):
        from triage_kit.core.trial_reader import extract_task_dir

        assert extract_task_dir(SAMPLE_TRIAL, override=tmp_path) == tmp_path


class TestReward:
    @needs_sample
    def test_reads_reward_from_real_result(self):
        from triage_kit.core.trial_reader import read_reward

        assert read_reward(SAMPLE_TRIAL) == 1.0

    def test_missing_rewards_returns_none(self, tmp_path):
        """M6: rewards/verifier_result 缺失时容错返回 None，不抛错。"""
        from triage_kit.core.trial_reader import read_reward

        t = tmp_path / "t"
        t.mkdir()
        (t / "result.json").write_text(
            json.dumps({"trial_name": "t"}), encoding="utf-8"
        )
        assert read_reward(t) is None
