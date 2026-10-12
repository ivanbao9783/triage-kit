"""ATIF trajectory parsing for the viewer's trace and tool tabs.

Reads the agent-side ``trajectory.json`` (Agent Trajectory Interchange
Format) and turns it into a compact, render-ready structure: per-step
message / reasoning / tool calls / observation, a flat call list for
tool analytics, and a per-tool aggregation. Pure data — it imports only
the tolerant JSON readers from ``scanner``, so it is unit-testable on
its own and stays independent of the web and markdown layers.

Long text (message / observation / reasoning, commands, outputs) is
clipped to keep the server-rendered HTML bounded; a clipped step is
flagged so the page can point back at the full ``trajectory.json``.
"""

import json
from pathlib import Path

from triage_kit.viewer.scanner import parse_dt, read_json

_TXT_CLIP = 4000
_CMD_CLIP = 120
_OUT_CLIP = 200


def _atif_text(content) -> str:
    """Text extraction compatible with str | ContentPart[] (multimodal)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(part.get("text") or "")
                elif part.get("type") == "image":
                    src = part.get("source") or {}
                    parts.append(f"[image: {src.get('path', '?')}]")
                else:
                    parts.append(str(part))
            else:
                parts.append(str(part))
        return "\n".join(x for x in parts if x)
    return str(content)


def _clip(value, n: int) -> str:
    s = "" if value is None else str(value)
    return s if len(s) <= n else s[:n] + "…"


def _dur(a, b):
    ta, tb = parse_dt(a), parse_dt(b)
    return round((tb - ta).total_seconds(), 1) if ta and tb else None


def _tool_sample(tool: dict):
    """A representative command for a tool call (command/cmd/code first)."""
    args = tool.get("args") or {}
    for key in ("command", "cmd"):
        if isinstance(args.get(key), str) and args[key]:
            return args[key]
    if isinstance(args.get("code"), str) and args["code"]:
        return args["code"]
    return None


def _describe_tool(tool: dict) -> tuple[str, str]:
    """Render kind + text for one tool call: a shell-style block when a
    command/code argument exists, else the function name plus its args."""
    sample = _tool_sample(tool)
    if sample is not None:
        return "cmd", _clip(sample, _CMD_CLIP)
    args = tool.get("args") or {}
    text = tool.get("fn") or "unknown"
    if args:
        text += " " + json.dumps(args, ensure_ascii=False)
    return "fn", _clip(text, _CMD_CLIP)


def _aggregate_tool_stats(steps: list) -> list:
    """Per-tool call count and step-level timing estimates.

    ATIF records no per-tool wall clock, so a tool's duration is the gap
    between adjacent step timestamps; parallel calls inside one step
    share that gap (it cannot be split).
    """
    agg: dict = {}
    timed: set = set()
    for step in steps:
        dur = step.get("dur")
        valid = dur if (dur is not None and dur >= 0) else None
        tools = step.get("tools") or []
        for tool in tools:
            fn = tool.get("fn") or "unknown"
            entry = agg.setdefault(fn, {"fn": fn, "count": 0, "step_durs": [],
                                        "parallel": 0, "sample": None})
            entry["count"] += 1
            if valid is not None and id(step) not in timed:
                timed.add(id(step))
                entry["step_durs"].append(valid)
            if len(tools) > 1:
                entry["parallel"] += 1
            if entry["sample"] is None and tool.get("kind") == "cmd":
                entry["sample"] = tool.get("text")
    out = []
    for entry in agg.values():
        durs = sorted(entry["step_durs"])
        if durs:
            mid = len(durs) // 2
            median = durs[mid] if len(durs) % 2 else (durs[mid - 1] + durs[mid]) / 2
        else:
            median = None
        out.append({
            "fn": entry["fn"],
            "count": entry["count"],
            "total_dur": round(sum(durs), 1) if durs else None,
            "avg_dur": round(sum(durs) / len(durs), 1) if durs else None,
            "median_dur": round(median, 1) if median is not None else None,
            "max_dur": round(max(durs), 1) if durs else None,
            "parallel": entry["parallel"],
            "sample": entry["sample"],
        })
    out.sort(key=lambda x: (-x["count"], x["fn"]))
    return out


def slim_trajectory(traj: dict) -> dict:
    """Compact, render-ready view of an ATIF trajectory (never raises)."""
    steps = []
    flat_calls = []
    prev_ts = None
    for raw in traj.get("steps") or []:
        tools = []
        for call in raw.get("tool_calls") or []:
            kind, text = _describe_tool({
                "fn": call.get("function_name", ""),
                "args": call.get("arguments") or {},
            })
            tools.append({
                "id": call.get("tool_call_id", ""),
                "fn": call.get("function_name", ""),
                "kind": kind,
                "text": text,
                "out": "",
            })
        observation = raw.get("observation") or {}
        results = observation.get("results") or []
        obs = "\n".join(
            x for x in (_atif_text(r.get("content")) for r in results) if x
        )
        # source_call_id ties each result back to its call (parallel-safe)
        by_id = {t["id"]: t for t in tools if t["id"]}
        for r in results:
            cid = r.get("source_call_id")
            if cid and cid in by_id:
                by_id[cid]["out"] = _atif_text(r.get("content"))
        metrics = raw.get("metrics") or {}
        ts = raw.get("timestamp")
        dur = _dur(prev_ts, ts)
        prev_ts = ts
        msg = _atif_text(raw.get("message"))
        reasoning = raw.get("reasoning_content") or ""
        truncated = (len(msg) > _TXT_CLIP or len(reasoning) > _TXT_CLIP
                     or len(obs) > _TXT_CLIP)
        steps.append({
            "i": raw.get("step_id"),
            "ts": ts,
            "dur": dur,
            "src": raw.get("source") or "",
            "msg": _clip(msg, _TXT_CLIP),
            "reasoning": _clip(reasoning, _TXT_CLIP),
            "tools": tools,
            "obs": _clip(obs, _TXT_CLIP),
            "truncated": truncated,
            "ptok": metrics.get("prompt_tokens"),
            "ctok": metrics.get("completion_tokens"),
        })
        for tool in tools:
            flat_calls.append({
                "step": raw.get("step_id"),
                "dur": dur,
                "fn": tool["fn"] or "unknown",
                "cmd": tool["text"],
                "out": _clip(tool.get("out"), _OUT_CLIP),
            })

    stats = _aggregate_tool_stats(steps)
    # step-level timing: one entry per step, parallel tools share it
    step_durs = []
    seen = set()
    for call in flat_calls:
        if call["dur"] is not None and call["step"] not in seen:
            seen.add(call["step"])
            step_durs.append(call["dur"])
    return {
        "n_steps": len(steps),
        "steps": steps,
        "flat_calls": flat_calls,
        "tool_stats": stats,
        "tool_totals": {
            "n_calls": len(flat_calls),
            "n_kinds": len(stats),
            "top_fn": stats[0]["fn"] if stats else None,
            "top_count": stats[0]["count"] if stats else None,
            "step_total_dur": round(sum(step_durs), 1) if step_durs else None,
            "step_avg_dur": (round(sum(step_durs) / len(step_durs), 1)
                             if step_durs else None),
            "step_max_dur": round(max(step_durs), 1) if step_durs else None,
        },
    }


def load_trajectory(trial_dir: Path):
    """Slim trajectory for a trial, or None when absent/unreadable.

    Prefers the Harbor-normalized ``agent/trajectory.json``, falling back
    to the first ``agent/*.trajectory.json`` (raw agent output).
    """
    trial_dir = Path(trial_dir)
    traj = read_json(trial_dir / "agent" / "trajectory.json")
    if traj is None:
        agent_dir = trial_dir / "agent"
        candidates = (sorted(agent_dir.glob("*.trajectory.json"))
                      if agent_dir.is_dir() else [])
        traj = read_json(candidates[0]) if candidates else None
    return slim_trajectory(traj) if traj else None