"""Manual demo: run GeneralHarness locally with scripted mock responses.

No network access, no real API key. Verifies the M5 tool loop and the
key-point logging (turn boundaries, tool calls/results, forced submission,
token accounting).

Usage:
    python scripts/demo_general_harness.py
"""

import json
import logging
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

# make src/ importable when running from a repo checkout
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from triage_kit.backends.general.harness import GeneralHarness  # noqa: E402

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-5s %(name)s | %(message)s",
    stream=sys.stdout,
)

SUBMIT_RESULT = {
    "trial_name": "demo__abc123",
    "summary": "Agent solved the task legitimately.",
    "checks": {
        "reward_hacking": {"outcome": "pass", "explanation": "no cheat"},
        "task_specification": {"outcome": "pass", "explanation": "clear"},
    },
}


# ---------- mock OpenAI-compatible client ----------

class FakeClient:
    """Mimics openai.OpenAI chat.completions with scripted responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        print(f"\n--- API call #{len(kwargs.get('messages', []))} messages, "
              f"tool_choice={kwargs.get('tool_choice')} ---")
        return self.responses.pop(0)


def tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def response(tool_calls=None, content=None, p=10, c=5):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    usage = SimpleNamespace(prompt_tokens=p, completion_tokens=c)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)],
                           usage=usage)


class OutputModel:
    """Stand-in for a rubric-compiled pydantic response model."""

    @staticmethod
    def model_json_schema():
        return {
            "type": "object",
            "properties": {
                "trial_name": {"type": "string"},
                "summary": {"type": "string"},
                "checks": {"type": "object"},
            },
            "required": ["trial_name", "summary", "checks"],
        }


def make_workdir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="triage-demo-"))
    (d / "result.json").write_text(
        json.dumps({"trial_name": "demo__abc123",
                    "verifier_result": {"rewards": {"reward": 0.0}}}),
        encoding="utf-8",
    )
    (d / "agent").mkdir()
    (d / "agent" / "trajectory.json").write_text(
        '[{"action": "edit", "file": "src/app.py"}]', encoding="utf-8",
    )
    return d


def demo_tool_loop(cwd: Path) -> None:
    print("\n========== demo 1: tool loop + structured output ==========")
    client = FakeClient([
        response(tool_calls=[tool_call("c1", "glob", {"pattern": "**/*.json"})]),
        response(tool_calls=[tool_call("c2", "read_file",
                                       {"path": "agent/trajectory.json"})]),
        response(tool_calls=[tool_call("c3", "submit_analysis",
                                       SUBMIT_RESULT)]),
    ])
    harness = GeneralHarness(client, default_model="glm-4.7")
    result, meta = harness.query_agent(
        "You are analyzing an agent trial run...",
        cwd=cwd, model="glm-4.7", output_schema=OutputModel, max_turns=5,
    )
    print(f"\n>>> submitted result: {json.dumps(result, ensure_ascii=False)}")
    print(f">>> meta: turns={meta.n_turns} in={meta.n_input_tokens} "
          f"out={meta.n_output_tokens} model={meta.model}")


def demo_forced_submission(cwd: Path) -> None:
    print("\n========== demo 2: forced submission on final turn ==========")
    client = FakeClient([
        response(tool_calls=[tool_call("c1", "read_file",
                                       {"path": "result.json"})]),
        response(tool_calls=[tool_call("c2", "submit_analysis",
                                       SUBMIT_RESULT)]),
    ])
    harness = GeneralHarness(client, default_model="glm-4.7")
    result, _ = harness.query_agent(
        "analyze", cwd=cwd, model="glm-4.7",
        output_schema=OutputModel, max_turns=2,   # budget exhausted at turn 2
    )
    print(f"\n>>> forced submit ok: trial_name={result['trial_name']}")


def demo_plain_query() -> None:
    print("\n========== demo 3: plain query (no tools) ==========")
    client = FakeClient([response(content="2 of 2 trials passed; "
                                            "no hacks detected.")])
    harness = GeneralHarness(client, default_model="glm-4.7")
    text, meta = harness.query("Aggregate these trial analyses...", 
                               model="glm-4.7")
    print(f"\n>>> text: {text}")
    print(f">>> meta: turns={meta.n_turns} model={meta.model}")


if __name__ == "__main__":
    workdir = make_workdir()
    print(f"workdir: {workdir}")

    demo_tool_loop(workdir)
    demo_forced_submission(workdir)
    demo_plain_query()
    print("\nAll demos finished.")
