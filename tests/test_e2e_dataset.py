"""Guard tests for the E2E mini dataset (P015).

The dataset is the fixed input contract of the E2E runbook
(tests/e2e/RUNBOOK.md): renames are breaking (the analyzer's
trial_name contract) and accidental deletion silently hollows out
every future Gate 2. These tests are cheap directory-shape checks,
not content validation.
"""

from pathlib import Path

DATA = Path(__file__).resolve().parent / "e2e" / "data"

TASKS = [
    "abs-module-cache-flags",
    "adaptix-name-mapping-aliases",
    "boa-hierarchical-evaluation-cancellation",
]

TRIALS = [
    "abs-module-cache-flags__CuCWVBi",
    "adaptix-name-mapping-aliases__ptkak5r",
    "boa-hierarchical-evaluation-canc__rWMKbsB",
]


def _fixture_names(directory: Path) -> list[str]:
    """Fixture directory names, ignoring triage-kit/ runtime products
    (a completed E2E pass intentionally keeps its products in place —
    they are review material and future viewer input)."""
    return sorted(
        d.name for d in directory.iterdir() if d.name != "triage-kit"
    )


class TestE2eMiniDataset:
    def test_exact_task_set(self):
        assert _fixture_names(DATA / "tasks") == sorted(TASKS)

    def test_exact_trial_set(self):
        assert _fixture_names(DATA / "trial_results") == sorted(TRIALS)

    def test_tasks_are_valid_task_dirs(self):
        from triage_kit.core.task_reader import validate_task_dir

        for name in TASKS:
            assert validate_task_dir(DATA / "tasks" / name) == [], name

    def test_trials_carry_evidence(self):
        """Slimmed copies keep the canonical evidence: result.json
        (reward / exception attribution input) and agent/trajectory.json
        (judge's evidence source)."""
        for name in TRIALS:
            trial = DATA / "trial_results" / name
            assert (trial / "result.json").is_file(), name
            assert (trial / "agent" / "trajectory.json").is_file(), name

    def test_trials_are_slimmed(self):
        """The mini-swe-agent.* raw duplicates are the slimming cut —
        their reappearance means someone copied verbatim (~30 MB)."""
        for name in TRIALS:
            mini = list(
                (DATA / "trial_results" / name).rglob("mini-swe-agent*")
            )
            assert mini == [], f"{name}: {mini}"

    def test_reward_coverage_pass_fail_exception(self):
        """The 3-trial selection covers the three attribution paths:
        A pass, B plain fail, C fail + exception_info."""
        import json

        def read(name, key):
            result = json.loads(
                (DATA / "trial_results" / name / "result.json").read_text(
                    encoding="utf-8"
                )
            )
            return result[key]

        assert read(TRIALS[0], "verifier_result")["rewards"]["reward"] == 1
        assert read(TRIALS[1], "verifier_result")["rewards"]["reward"] == 0
        result_c = read(TRIALS[2], "verifier_result")
        assert result_c["rewards"]["reward"] == 0
        assert read(TRIALS[2], "exception_info"), "C must carry exception"
