"""Tests for triage_kit.core.trial_reader — Harbor-native layout, plain JSON reads.

Runs against the real sample job exported from a Linux Harbor run
(``tmp_workspace/details``). Tests auto-skip if the sample is absent.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_JOB = REPO_ROOT.parent / "details"
SAMPLE_TRIAL = SAMPLE_JOB / "ts-pattern-match-each__9giF4pL"

needs_sample = pytest.mark.skipif(
    not SAMPLE_JOB.exists(), reason="real sample job dir not present"
)


def make_trial(path: Path, *, reward: float, exception: bool = False) -> None:
    """Synthesize a minimal Harbor-layout trial directory."""
    path.mkdir(parents=True)
    (path / "trial.log").write_text("", encoding="utf-8")
    result = {
        "trial_name": path.name,
        "config": {"task": {"path": "/nonexistent/task"}},
        "verifier_result": {"rewards": {"reward": reward}},
        "exception_info": "boom" if exception else None,
    }
    (path / "result.json").write_text(json.dumps(result), encoding="utf-8")


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
    def test_finds_both_sample_trials(self):
        from triage_kit.core.trial_reader import list_trials

        trials = list_trials(SAMPLE_JOB)
        names = {t.name for t in trials}
        assert names == {
            "ts-pattern-match-each__9giF4pL",
            "tomlkit-toml-table-converters__BVG4s9W",
        }

    @needs_sample
    def test_failing_only_empty_for_passing_samples(self):
        from triage_kit.core.trial_reader import list_trials

        assert list_trials(SAMPLE_JOB, failing_only=True) == []

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
