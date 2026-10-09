"""Tests for backends/general/harness.py — tool loop + final-tool output.

The OpenAI-compatible client is replaced by a scripted FakeClient, so the
whole agent loop (tool dispatch, sandbox wiring, forced submission, token
accounting) is exercised without network access.
"""

import json
from types import SimpleNamespace

import pytest

SUBMIT_RESULT = {"trial_name": "t", "summary": "s", "answer": 42}


class FakeClient:
    """Mimics openai.OpenAI's chat.completions surface, scripted per call."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def tool_call(call_id: str, name: str, arguments: dict):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def response(tool_calls=None, content=None, p=10, c=5):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    usage = SimpleNamespace(prompt_tokens=p, completion_tokens=c)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)], usage=usage
    )


class OutputModel:
    """Minimal pydantic-like stand-in exposing model_json_schema()."""

    @staticmethod
    def model_json_schema():
        return {
            "type": "object",
            "properties": {
                "trial_name": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["trial_name", "summary"],
        }


@pytest.fixture
def workdir(tmp_path):
    (tmp_path / "result.json").write_text('{"reward": 1}', encoding="utf-8")
    return tmp_path


class TestQueryAgent:
    def test_tool_loop_returns_submitted_dict(self, workdir):
        from triage_kit.backends.general.harness import GeneralHarness

        client = FakeClient([
            response(tool_calls=[tool_call("c1", "read_file",
                                           {"path": "result.json"})]),
            response(tool_calls=[tool_call("c2", "submit_analysis",
                                           SUBMIT_RESULT)]),
        ])
        harness = GeneralHarness(client, default_model="m1")
        result, meta = harness.query_agent(
            "analyze", cwd=workdir, model="m1", output_schema=OutputModel
        )

        assert result == SUBMIT_RESULT
        assert meta.n_turns == 2
        assert meta.model == "m1"
        assert meta.n_input_tokens == 20   # 2 turns x 10
        assert meta.n_output_tokens == 10  # 2 turns x 5

        # first call: user prompt + all four tool specs, auto choice
        first = client.calls[0]
        assert first["messages"][0]["content"] == "analyze"
        tool_names = {t["function"]["name"] for t in first["tools"]}
        assert tool_names == {"read_file", "glob", "grep", "submit_analysis"}
        assert first["tool_choice"] == "auto"

        # second call: assistant tool_call + tool result with file content
        second = client.calls[1]
        assert second["messages"][1]["tool_calls"][0]["function"]["name"] \
            == "read_file"
        assert '"reward": 1' in second["messages"][2]["content"]
        assert second["messages"][2]["tool_call_id"] == "c1"

    def test_forces_submit_on_final_turn(self, workdir):
        from triage_kit.backends.general.harness import GeneralHarness

        client = FakeClient([
            response(tool_calls=[tool_call("c1", "read_file",
                                           {"path": "result.json"})]),
            response(tool_calls=[tool_call("c2", "submit_analysis",
                                           SUBMIT_RESULT)]),
        ])
        harness = GeneralHarness(client, default_model="m1")
        result, _ = harness.query_agent(
            "analyze", cwd=workdir, model="m1",
            output_schema=OutputModel, max_turns=2,
        )

        assert result == SUBMIT_RESULT
        last = client.calls[-1]
        assert last["tool_choice"] == {
            "type": "function", "function": {"name": "submit_analysis"}
        }

    def test_without_schema_uses_loose_final_tool(self, workdir):
        from triage_kit.backends.general.harness import GeneralHarness

        client = FakeClient([
            response(tool_calls=[tool_call("c1", "submit_analysis",
                                           {"result": "plain text"})]),
        ])
        harness = GeneralHarness(client, default_model="m1")
        result, meta = harness.query_agent("hi", cwd=workdir, model="m1")

        assert result == {"result": "plain text"}
        assert meta.n_turns == 1
        specs = client.calls[0]["tools"]
        submit = next(t for t in specs if t["function"]["name"] == "submit_analysis")
        assert "result" in submit["function"]["parameters"]["properties"]

    def test_model_defaults_to_harness_default(self, workdir):
        from triage_kit.backends.general.harness import GeneralHarness

        client = FakeClient([
            response(tool_calls=[tool_call("c1", "submit_analysis",
                                           {"result": "x"})]),
        ])
        GeneralHarness(client, default_model="fallback").query_agent(
            "hi", cwd=workdir
        )
        assert client.calls[0]["model"] == "fallback"


class TestQuery:
    def test_plain_query_returns_text(self):
        from triage_kit.backends.general.harness import GeneralHarness

        client = FakeClient([response(content="JOB SUMMARY")])
        harness = GeneralHarness(client, default_model="m1")
        text, meta = harness.query("aggregate", model="m1")

        assert text == "JOB SUMMARY"
        assert meta.n_turns == 1
        call = client.calls[0]
        assert "tools" not in call
        assert call["messages"] == [
            {"role": "user", "content": "aggregate"}
        ]


class TestDemoScenarios:
    """Formalized from scripts/demo_general_harness.py — end-to-end
    regression scenarios. Demo 2 (forced submission) and demo 3 (plain
    query) are covered by test_forces_submit_on_final_turn and
    test_plain_query_returns_text above; the multi-tool sequence below is
    the scenario the other tests don't exercise."""

    def test_glob_read_submit_scenario(self, workdir):
        from triage_kit.backends.general.harness import GeneralHarness

        (workdir / "agent").mkdir()
        (workdir / "agent" / "trajectory.json").write_text(
            '[{"action": "edit", "file": "src/app.py"}]', encoding="utf-8"
        )
        client = FakeClient([
            response(tool_calls=[tool_call("c1", "glob",
                                            {"pattern": "**/*.json"})]),
            response(tool_calls=[tool_call("c2", "read_file",
                                           {"path": "agent/trajectory.json"})]),
            response(tool_calls=[tool_call("c3", "submit_analysis",
                                           SUBMIT_RESULT)]),
        ])
        result, meta = GeneralHarness(client, default_model="glm-4.7").query_agent(
            "You are analyzing an agent trial run...",
            cwd=workdir, model="glm-4.7",
            output_schema=OutputModel, max_turns=5,
        )

        assert result == SUBMIT_RESULT
        assert meta.n_turns == 3
        assert meta.n_input_tokens == 30
        assert meta.n_output_tokens == 15

        # turn 1: glob result flows back into the conversation
        glob_result = client.calls[1]["messages"][2]["content"]
        assert "agent/trajectory.json" in glob_result
        assert "result.json" in glob_result

        # turn 2: read_file returns the actual trajectory content
        # (messages: user, asst(glob), tool, asst(read), tool)
        read_result = client.calls[2]["messages"][4]["content"]
        assert "edit" in read_result
        assert client.calls[2]["messages"][4]["tool_call_id"] == "c2"
        assert client.calls[2]["messages"][3]["tool_calls"][0]["function"][
            "name"
        ] == "read_file"


class TestContractIntegration:
    """The real harness satisfies the AgentBackend contract: the Analyzer
    (M4, built against a FakeBackend) runs unchanged on top of it."""

    def test_analyzer_runs_on_general_harness(self, workdir):
        from pathlib import Path

        from tests.test_trial_reader import make_trial
        from triage_kit.backends.general.harness import GeneralHarness
        from triage_kit.core.analyzer import Analyzer
        from triage_kit.core.rubric import load_rubric

        trial = workdir / "demo__abc123"
        make_trial(trial, reward=0.0)

        submit = {
            "trial_name": "demo__abc123",
            "summary": "Agent failed early.",
            "checks": {
                "reward_hacking": {"outcome": "pass", "explanation": "no cheat"},
                "task_specification": {"outcome": "pass", "explanation": "clear"},
            },
        }
        client = FakeClient([
            response(tool_calls=[tool_call("c1", "read_file",
                                           {"path": "result.json"})]),
            response(tool_calls=[tool_call("c2", "submit_analysis", submit)]),
        ])
        harness = GeneralHarness(client, default_model="m1")
        analyzer = Analyzer(
            backend=harness,
            rubric=load_rubric(
                Path(__file__).parent.parent / "assets" / "analyze"
                / "analyze-rubric.toml"
            ),
            model="m1",
        )
        result = analyzer.analyze_trial(trial)

        assert result["summary"] == "Agent failed early."
        assert result["checks"]["reward_hacking"]["outcome"] == "pass"
        assert (trial / "analysis.json").is_file()
        # the agent actually read the trial file through the sandbox
        read_args = json.loads(
            client.calls[1]["messages"][1]["tool_calls"][0]["function"]
            ["arguments"]
        )
        assert read_args["path"] == "result.json"
