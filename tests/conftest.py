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


# ---------- Concurrency-test fakes (P003) ----------

def make_backend_keyed(mapping: dict, *, delays: dict | None = None):
    """Order-independent fake for concurrent runs.

    query_agent dispatches on the trial directory name (cwd), query on
    prompt shape (leading 'Translate' = zh hop, otherwise job
    aggregation) — no dependence on call order. Optional per-trial
    delays let tests invert the completion order.
    """
    import time

    from triage_kit.core.contract import AgentMeta

    delays = delays or {}

    class FakeBackend:
        def __init__(self):
            self.agent_prompts: list[str] = []
            self.plain_prompts: list[str] = []

        def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                        output_schema=None, max_turns=15):
            name = Path(cwd).name
            time.sleep(delays.get(name, 0))
            self.agent_prompts.append(prompt)
            return mapping[name], AgentMeta(n_turns=2, model=model)

        def query(self, prompt, *, model):
            self.plain_prompts.append(prompt)
            text = ("TRANSLATED" if prompt.startswith("Translate")
                    else "JOB SUMMARY")
            return text, AgentMeta(n_turns=0, model=model)

    return FakeBackend()


def make_barrier_backend(parties: int, response: dict):
    """Fake whose query_agent blocks on a threading.Barrier(parties).

    Only genuinely overlapped execution lets all parties through — a
    sequential (or under-provisioned) implementation breaks the barrier
    (BrokenBarrierError) and the trials land in failed_trials, failing
    the test.
    """
    import threading

    from triage_kit.core.contract import AgentMeta

    class FakeBackend:
        def __init__(self):
            self.barrier = threading.Barrier(parties)

        def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                        output_schema=None, max_turns=15):
            self.barrier.wait(timeout=5)
            return dict(response, trial_name=Path(cwd).name), AgentMeta(
                n_turns=2, model=model)

        def query(self, prompt, *, model):
            return "JOB SUMMARY", AgentMeta(n_turns=0, model=model)

    return FakeBackend()


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
