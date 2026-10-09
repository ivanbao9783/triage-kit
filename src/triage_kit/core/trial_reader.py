"""Plain-JSON reads over Harbor-native trial/job layouts.

No pydantic TrialResult dependency: result.json is consumed as a dict, so
results produced by vanilla Harbor jobs (and copied across machines) work
without schema drift issues.
"""

import json
from pathlib import Path


def is_trial_dir(path: Path) -> bool:
    return (Path(path) / "trial.log").exists()


def is_job_dir(path: Path) -> bool:
    return (Path(path) / "job.log").exists()


def _read_result(trial_dir: Path) -> dict:
    return json.loads((Path(trial_dir) / "result.json").read_text(encoding="utf-8"))


def _verifier_reward(result: dict):
    """Main reward from verifier_result.rewards.reward (None if absent)."""
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    return rewards.get("reward")


def read_reward(trial_dir: Path) -> float | None:
    """Return the trial's main reward, or None if absent."""
    reward = _verifier_reward(_read_result(trial_dir))
    return float(reward) if reward is not None else None


def _is_passing(trial_dir: Path) -> bool:
    result = _read_result(trial_dir)
    return (
        _verifier_reward(result) == 1
        and result.get("exception_info") is None
    )


def list_trials(job_dir: Path, *, failing_only: bool = False) -> list[Path]:
    """List trial directories under a job dir, optionally badcases only."""
    job_dir = Path(job_dir)
    trials = sorted(p for p in job_dir.iterdir() if is_trial_dir(p))
    if failing_only:
        return [t for t in trials if not _is_passing(t)]
    return trials


def extract_task_dir(trial_dir: Path, *, override: Path | None = None) -> Path | None:
    """Locate the source task directory for a trial.

    Returns None when the recorded task path does not exist on this machine
    (the canonical case for results copied off the eval box) — callers
    degrade to trajectory-only analysis.
    """
    if override is not None:
        override = Path(override)
        return override if override.exists() else None

    result = _read_result(trial_dir)
    task_path = (result.get("config") or {}).get("task", {}).get("path")
    if not task_path:
        return None
    candidate = Path(task_path)
    return candidate if candidate.exists() else None
