"""Tests for triage_kit.viewer.trajectory — ATIF parsing + tool analytics.

The trajectory layer is the data core behind the viewer's trace and tool
tabs: it must turn a raw ATIF trajectory.json into a compact render-ready
structure, tie each observation back to its originating call, aggregate
per-tool timings, and never raise on absent / malformed input.
"""

import json

from triage_kit.viewer import trajectory


def traj(steps):
    return {"schema_version": "1", "steps": steps}


def call(cid, fn, args):
    return {"tool_call_id": cid, "function_name": fn, "arguments": args}


def three_steps():
    """Three sequential steps: two bash calls, then one edit."""
    return traj([
        {"step_id": 1, "source": "assistant",
         "timestamp": "2026-10-12T10:00:00Z", "message": "first",
         "tool_calls": [call("c1", "bash", {"command": "ls"})],
         "observation": {"results": [
             {"source_call_id": "c1", "content": "a.txt"}]}},
        {"step_id": 2, "source": "assistant",
         "timestamp": "2026-10-12T10:00:05Z", "message": "second",
         "tool_calls": [call("c2", "bash", {"command": "cat a.txt"})]},
        {"step_id": 3, "source": "user",
         "timestamp": "2026-10-12T10:00:12Z", "message": "third",
         "tool_calls": [call("c3", "edit",
                             {"path": "a.py", "content": "x"})]},
    ])


class TestAtifText:
    def test_str_passthrough(self):
        assert trajectory._atif_text("hello") == "hello"

    def test_none_is_empty(self):
        assert trajectory._atif_text(None) == ""

    def test_content_parts_joined(self):
        parts = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        assert trajectory._atif_text(parts) == "a\nb"

    def test_image_part_placeholder(self):
        parts = [{"type": "image", "source": {"path": "/x.png"}}]
        assert trajectory._atif_text(parts) == "[image: /x.png]"


class TestSlimTrajectory:
    def test_steps_and_fields(self):
        s = trajectory.slim_trajectory(three_steps())

        assert s["n_steps"] == 3
        assert [st["i"] for st in s["steps"]] == [1, 2, 3]
        assert s["steps"][0]["msg"] == "first"
        assert s["steps"][2]["src"] == "user"

    def test_observation_tied_to_call_by_source_call_id(self):
        s = trajectory.slim_trajectory(three_steps())

        assert s["steps"][0]["tools"][0]["out"] == "a.txt"

    def test_command_arg_renders_as_cmd_kind(self):
        s = trajectory.slim_trajectory(three_steps())

        assert s["steps"][0]["tools"][0]["kind"] == "cmd"
        assert s["steps"][0]["tools"][0]["text"] == "ls"

    def test_arg_only_call_renders_as_fn_kind(self):
        s = trajectory.slim_trajectory(three_steps())

        edit = s["steps"][2]["tools"][0]
        assert edit["kind"] == "fn"
        assert edit["text"].startswith("edit ")
        assert '"path": "a.py"' in edit["text"]

    def test_step_duration_from_adjacent_timestamps(self):
        s = trajectory.slim_trajectory(three_steps())

        assert s["steps"][0]["dur"] is None  # first step has no predecessor
        assert s["steps"][1]["dur"] == 5.0
        assert s["steps"][2]["dur"] == 7.0

    def test_parallel_calls_flagged(self):
        s = trajectory.slim_trajectory(traj([
            {"step_id": 1, "source": "assistant",
             "timestamp": "2026-10-12T10:00:00Z",
             "tool_calls": [call("c1", "bash", {"command": "a"}),
                            call("c2", "bash", {"command": "b"})]},
        ]))

        assert s["tool_stats"][0]["count"] == 2
        assert s["tool_stats"][0]["parallel"] == 2  # both calls ran in one step
        assert s["tool_stats"][0]["sample"] == "a"  # first parallel command


class TestToolStats:
    def test_aggregation_counts_and_timings(self):
        s = trajectory.slim_trajectory(three_steps())

        bash, edit = s["tool_stats"]
        assert bash["fn"] == "bash" and bash["count"] == 2
        assert bash["total_dur"] == 5.0  # only step 2 carried a duration
        assert bash["avg_dur"] == 5.0
        assert bash["median_dur"] == 5.0
        assert bash["max_dur"] == 5.0
        assert bash["sample"] == "ls"  # first observed command
        assert edit["fn"] == "edit" and edit["count"] == 1
        assert edit["total_dur"] == 7.0

    def test_totals(self):
        s = trajectory.slim_trajectory(three_steps())
        tt = s["tool_totals"]

        assert tt["n_calls"] == 3
        assert tt["n_kinds"] == 2
        assert tt["top_fn"] == "bash" and tt["top_count"] == 2
        assert tt["step_total_dur"] == 12.0  # 5.0 + 7.0
        assert tt["step_avg_dur"] == 6.0
        assert tt["step_max_dur"] == 7.0

    def test_empty_trajectory_degrades(self):
        s = trajectory.slim_trajectory({})

        assert s["n_steps"] == 0
        assert s["tool_stats"] == []
        assert s["tool_totals"]["n_calls"] == 0
        assert s["tool_totals"]["top_fn"] is None
        assert s["tool_totals"]["step_total_dur"] is None


class TestClipping:
    def test_long_message_is_clipped_and_flagged(self):
        s = trajectory.slim_trajectory(traj([
            {"step_id": 1, "source": "assistant",
             "timestamp": "2026-10-12T10:00:00Z", "message": "x" * 5000},
        ]))

        step = s["steps"][0]
        assert step["truncated"] is True
        assert len(step["msg"]) < 5000
        assert step["msg"].endswith("…")

    def test_short_message_not_flagged(self):
        s = trajectory.slim_trajectory(traj([
            {"step_id": 1, "source": "assistant",
             "timestamp": "2026-10-12T10:00:00Z", "message": "short"},
        ]))

        assert s["steps"][0]["truncated"] is False


class TestLoadTrajectory:
    def _write(self, path, steps):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(traj(steps)), encoding="utf-8")

    def test_prefers_normalized_path(self, tmp_path):
        agent = tmp_path / "agent"
        self._write(agent / "trajectory.json", three_steps()["steps"])
        self._write(agent / "raw.trajectory.json",
                    three_steps()["steps"][:1])

        got = trajectory.load_trajectory(tmp_path)

        assert got["n_steps"] == 3  # normalized wins over the glob

    def test_falls_back_to_glob(self, tmp_path):
        self._write(tmp_path / "agent" / "raw.trajectory.json",
                    three_steps()["steps"][:1])

        got = trajectory.load_trajectory(tmp_path)

        assert got is not None
        assert got["n_steps"] == 1

    def test_none_when_absent(self, tmp_path):
        assert trajectory.load_trajectory(tmp_path) is None

    def test_none_when_empty_object(self, tmp_path):
        agent = tmp_path / "agent"
        agent.mkdir(parents=True)
        (agent / "trajectory.json").write_text("{}", encoding="utf-8")

        assert trajectory.load_trajectory(tmp_path) is None