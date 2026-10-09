"""Shared test factories, fakes, and constants for the triage-kit suite.

Every cross-file helper lives here so test modules keep a single
responsibility (testing one production module) instead of doubling as
a factory library for other tests.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYZE_RUBRIC = REPO_ROOT / "assets" / "analyze" / "analyze-rubric.toml"
CHECK_RUBRIC = REPO_ROOT / "assets" / "check" / "rubrics" / "check-default.toml"


# ---------- Harbor-layout factories ----------

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


def make_task(path: Path, *, with_steps: bool = False) -> None:
    """Synthesize a minimal Harbor-layout task directory."""
    (path / "environment").mkdir(parents=True)
    (path / "environment" / "Dockerfile").write_text("FROM busybox\n", encoding="utf-8")
    (path / "instruction.md").write_text("Do the thing.\n", encoding="utf-8")
    if with_steps:
        (path / "steps" / "step-1" / "instruction.md").parent.mkdir(parents=True)
        (path / "steps" / "step-1" / "instruction.md").write_text(
            "Step one.\n", encoding="utf-8"
        )
        (path / "task.toml").write_text(
            '[[steps]]\nname = "step-1"\n', encoding="utf-8"
        )
    else:
        (path / "task.toml").write_text("[task]\n", encoding="utf-8")


def write_sidecar(directory, name, *, model, rubric_path) -> None:
    """Write an identity sidecar matching the given rubric file + model."""
    sha = hashlib.sha256(Path(rubric_path).read_bytes()).hexdigest()
    (Path(directory) / name).write_text(
        json.dumps({"rubric_sha256": sha, "model": model}), encoding="utf-8"
    )


# ---------- OpenAI-compatible client fakes ----------

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
