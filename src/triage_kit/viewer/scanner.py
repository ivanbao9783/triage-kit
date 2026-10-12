"""Plain-JSON discovery of triage-kit products for the viewer (P006).

Reads the ``<dir>/triage-kit/`` sub-directory layout (DESIGN.md §7) with
no upstream model dependency — products are consumed as dicts, so
results copied off the eval box render without schema drift. Every
native side file is optional: a raw evaluation directory yields a fully
populated native view and an empty (``None``) diagnosis section.

Imports nothing from the web stack or a markdown renderer, so this
module is the unit-testable core.
"""

import json
from datetime import datetime
from pathlib import Path

from triage_kit.core import task_reader, trial_reader

PRODUCTS_DIR = "triage-kit"
ANALYSIS_JSON = "analysis.json"
ANALYSIS_MD = "analysis.md"
CHECK_RESULT_JSON = "check-result.json"
CHECK_RESULT_MD = "check-result.md"

# Native timing phases, in display order: (result.json key, label).
_PHASES = (
    ("environment_setup", "Environment setup"),
    ("agent_setup", "Agent setup"),
    ("agent_execution", "Agent execution"),
    ("verifier", "Verifier"),
)

_REWARD_KEYS = ("reward", "f2p_passed", "f2p_total", "p2p_passed",
                "p2p_total", "partial")


class CheckModeUnsupported(ValueError):
    """The target is a check (tasks) input — not in this P006 landing.

    analyze (trials) and check (tasks) are peer, mutually-exclusive
    modes; the tasks path ships in a later landing, so it is rejected
    explicitly instead of being silently mixed with analyze.
    """


# ---------- tolerant readers ----------

def read_json(path: Path):
    """Return parsed JSON, or None when missing/unreadable/malformed."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_text(path: Path) -> str | None:
    """Return file text, or None when missing/unreadable."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def parse_dt(value):
    """Parse an ISO timestamp, tolerating a trailing 'Z'; None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_sec(phase):
    """Seconds between a phase's started_at/finished_at, or None."""
    if not isinstance(phase, dict):
        return None
    start = parse_dt(phase.get("started_at"))
    end = parse_dt(phase.get("finished_at"))
    return round((end - start).total_seconds(), 1) if start and end else None


def norm_rewards(rewards: dict | None) -> dict:
    """Pin the reward block to a stable key set (missing → None)."""
    rewards = rewards or {}
    return {key: rewards.get(key) for key in _REWARD_KEYS}


# ---------- mode routing ----------

def is_single_trial(path: Path) -> bool:
    """True when the path is itself a trial directory (vs a trials root)."""
    return trial_reader.is_trial_dir(Path(path))


def detect_mode(path: Path) -> str:
    """Classify a view target as 'trial' or 'job'; raise otherwise.

    Raises CheckModeUnsupported for a task / tasks root (check mode, a
    later landing), and ValueError for anything else.
    """
    path = Path(path)
    if is_single_trial(path):
        return "trial"
    if task_reader.is_task_dir(path) or task_reader.list_task_dirs(path):
        raise CheckModeUnsupported(
            "check mode (tasks) is not yet supported by 'triage view' — "
            "this release renders analyze (trials) products only"
        )
    if trial_reader.list_trials(path):
        return "job"
    raise ValueError(f"not a trial or job directory: {path}")


# ---------- scanning ----------

def _trial_reward(trial_dir: Path):
    """Main reward from verifier_result.rewards, else verifier/reward.json."""
    result = read_json(trial_dir / "result.json") or {}
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    reward = rewards.get("reward")
    if reward is None:
        reward = (read_json(trial_dir / "verifier" / "reward.json") or {}).get(
            "reward"
        )
    return reward


def scan_trials(root: Path) -> list[dict]:
    """Scan one level of trial directories, lexicographically.

    Returns ``{name, reward, has_diagnosis}`` rows; sub-directories
    without a readable ``result.json`` (e.g. the job-level
    ``triage-kit/`` dir) are skipped rather than erroring.
    """
    root = Path(root)
    rows: list[dict] = []
    for entry in sorted(p for p in root.iterdir() if p.is_dir()):
        if read_json(entry / "result.json") is None:
            continue
        rows.append({
            "name": entry.name,
            "reward": _trial_reward(entry),
            "has_diagnosis": (entry / PRODUCTS_DIR / ANALYSIS_JSON).is_file(),
        })
    return rows


def reward_counts(trials: list[dict]) -> dict:
    """Badge counts for the overview filters."""
    return {
        "all": len(trials),
        "1": sum(1 for t in trials if t["reward"] == 1),
        "0": sum(1 for t in trials if t["reward"] == 0),
    }


def select_reward(trials: list[dict], reward: str | None) -> list[dict]:
    """Filter scanned trials by the raw ``?reward=`` query value.

    Only '1' / '0' are meaningful; anything else (including None) keeps
    the full list.
    """
    if reward in ("1", "0"):
        return [t for t in trials if t["reward"] == int(reward)]
    return trials


def load_overview(root: Path) -> dict:
    """Job-level view: aggregate markdown + the trials table + counts."""
    root = Path(root)
    trials = scan_trials(root)
    return {
        "job_md": read_text(root / PRODUCTS_DIR / ANALYSIS_MD),
        "trials": trials,
        "counts": reward_counts(trials),
    }


def load_trial(trial_dir: Path) -> dict:
    """Single-trial view: native blocks + this trial's diagnosis markdown."""
    trial_dir = Path(trial_dir)
    result = read_json(trial_dir / "result.json") or {}
    agent = result.get("agent_info") or {}
    model_info = agent.get("model_info") or {}
    agent_result = result.get("agent_result") or {}

    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    if not rewards:
        rewards = read_json(trial_dir / "verifier" / "reward.json") or {}

    ctrf = (read_json(trial_dir / "verifier" / "ctrf.json") or {}).get(
        "results"
    ) or {}

    return {
        "name": trial_dir.name,
        "task_name": result.get("task_name"),
        "agent_name": agent.get("name"),
        "model": "/".join(
            p for p in (model_info.get("provider"), model_info.get("name")) if p
        ),
        "rewards": norm_rewards(rewards),
        "exception": result.get("exception_info") or {},
        "tokens": {
            "input": agent_result.get("n_input_tokens"),
            "cache": agent_result.get("n_cache_tokens"),
            "output": agent_result.get("n_output_tokens"),
            "cost": agent_result.get("cost_usd"),
        },
        "timing": [
            {"label": label, "sec": duration_sec(result.get(key))}
            for key, label in _PHASES
        ],
        "total_sec": duration_sec({"started_at": result.get("started_at"),
                                   "finished_at": result.get("finished_at")}),
        "ctrf": ctrf,
        "manifest": read_json(trial_dir / "artifacts" / "manifest.json") or [],
        "analysis_md": read_text(trial_dir / PRODUCTS_DIR / ANALYSIS_MD),
    }