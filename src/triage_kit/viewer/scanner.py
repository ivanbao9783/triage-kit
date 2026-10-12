"""Plain-JSON discovery of triage-kit products for the viewer.

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

# Native timing phases, in display order: (result.json key, label).
_PHASES = (
    ("environment_setup", "Environment setup"),
    ("agent_setup", "Agent setup"),
    ("agent_execution", "Agent execution"),
    ("verifier", "Verifier"),
)

_PASSED_SUFFIX = "_passed"
_TOTAL_SUFFIX = "_total"


class CheckModeUnsupported(ValueError):
    """The target is a check (tasks) input, which this release does not serve.

    analyze (trials) and check (tasks) are peer, mutually-exclusive
    modes; the tasks view is not implemented yet, so such a target is
    rejected explicitly instead of being silently mixed with analyze.
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


def reward_of(rewards: dict | None):
    """Main reward value (the ``reward`` key), or None."""
    return (rewards or {}).get("reward")


def reward_items(rewards: dict | None) -> list[dict]:
    """Dataset-agnostic breakdown of a verifier reward block.

    Every ``<name>_passed`` / ``<name>_total`` pair collapses into one
    item carrying its ratio (rendered as a progress bar); any other key
    becomes a plain item. The main ``reward`` key is excluded — it is the
    outcome badge, not a breakdown row. No dataset-specific key (f2p,
    p2p, ...) is assumed.
    """
    rewards = rewards or {}
    items: list[dict] = []
    seen: set[str] = set()
    for key, value in rewards.items():
        if key == "reward" or key in seen:
            continue
        base = None
        if key.endswith(_PASSED_SUFFIX):
            candidate = key[: -len(_PASSED_SUFFIX)]
            if f"{candidate}{_TOTAL_SUFFIX}" in rewards:
                base = candidate
        elif key.endswith(_TOTAL_SUFFIX):
            candidate = key[: -len(_TOTAL_SUFFIX)]
            if f"{candidate}{_PASSED_SUFFIX}" in rewards:
                base = candidate
        if base is not None:
            passed = rewards[f"{base}{_PASSED_SUFFIX}"]
            total = rewards[f"{base}{_TOTAL_SUFFIX}"]
            seen.update({f"{base}{_PASSED_SUFFIX}", f"{base}{_TOTAL_SUFFIX}"})
            items.append({
                "key": base, "value": None,
                "passed": passed, "total": total,
                "ratio": (passed / total) if total else None,
            })
        else:
            seen.add(key)
            items.append({
                "key": key, "value": value,
                "passed": None, "total": None, "ratio": None,
            })
    return items


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

def _trial_row(trial_dir: Path) -> dict:
    """One overview-table row, read tolerantly from a trial directory.

    The aggregation fields (tokens / duration / failed tests / exception)
    are None/False when their native file is absent, so the overview
    degrades to a name+reward table on a raw directory. Nothing here
    assumes a dataset-specific reward schema.
    """
    result = read_json(trial_dir / "result.json") or {}
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    reward = reward_of(rewards)
    if reward is None:
        reward = reward_of(read_json(trial_dir / "verifier" / "reward.json"))
    agent_result = result.get("agent_result") or {}
    summary = (
        (read_json(trial_dir / "verifier" / "ctrf.json") or {}).get("results")
        or {}
    ).get("summary") or {}
    return {
        "name": trial_dir.name,
        "reward": reward,
        "resolved": reward is not None and reward >= 1,
        "tokens_in": agent_result.get("n_input_tokens"),
        "tokens_out": agent_result.get("n_output_tokens"),
        "duration_sec": duration_sec({"started_at": result.get("started_at"),
                                      "finished_at": result.get("finished_at")}),
        "failed_tests": summary.get("failed"),
        "has_exception": bool(result.get("exception_info")),
        "has_diagnosis": (trial_dir / PRODUCTS_DIR / ANALYSIS_JSON).is_file(),
    }


def scan_trials(root: Path) -> list[dict]:
    """Scan one level of trial directories, lexicographically.

    Returns overview rows (input to both the table and the nav tree);
    sub-directories without a readable ``result.json`` (e.g. the
    job-level ``triage-kit/`` dir) are skipped rather than erroring.
    """
    root = Path(root)
    rows: list[dict] = []
    for entry in sorted(p for p in root.iterdir() if p.is_dir()):
        if read_json(entry / "result.json") is None:
            continue
        rows.append(_trial_row(entry))
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


def summarize(trials: list[dict]) -> dict:
    """Overview KPI band, dataset-agnostic.

    ``resolved_rate`` counts reward>=1 over trials that carry a reward —
    a trial with no reward data cannot be scored either way, so it is
    excluded from the denominator. Token / duration figures ignore
    missing values rather than treating them as 0.
    """
    with_reward = [t for t in trials if t["reward"] is not None]
    resolved = sum(1 for t in with_reward if t["reward"] >= 1)
    ins = [t["tokens_in"] for t in trials if t["tokens_in"] is not None]
    outs = [t["tokens_out"] for t in trials if t["tokens_out"] is not None]
    durs = [t["duration_sec"] for t in trials if t["duration_sec"] is not None]
    return {
        "trials": len(trials),
        "resolved": resolved,
        "rewarded": len(with_reward),
        "resolved_rate": (resolved / len(with_reward)) if with_reward else None,
        "tokens_in": sum(ins) if ins else None,
        "tokens_out": sum(outs) if outs else None,
        "avg_duration_sec": (sum(durs) / len(durs)) if durs else None,
        "exceptions": sum(1 for t in trials if t["has_exception"]),
    }


def load_overview(root: Path) -> dict:
    """Job-level view: aggregate markdown + the trials table + counts."""
    root = Path(root)
    trials = scan_trials(root)
    return {
        "job_md": read_text(root / PRODUCTS_DIR / ANALYSIS_MD),
        "trials": trials,
        "counts": reward_counts(trials),
        "summary": summarize(trials),
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

    reward = reward_of(rewards)
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
        "reward": reward,
        "resolved": reward is not None and reward >= 1,
        "reward_items": reward_items(rewards),
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