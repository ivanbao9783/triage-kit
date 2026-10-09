"""E2E: `triage analyze` against a mock OpenAI-compatible endpoint.

Spins up a real local HTTP server implementing POST /v1/chat/completions
with scripted responses (read_file tool call, then submit_analysis), then
runs the CLI as a subprocess pointing --base-url at it. Exercises the full
production chain: typer CLI -> build_backend -> openai.OpenAI ->
GeneralHarness tool loop -> Analyzer orchestration -> analysis.json/md.
"""

import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))            # for tests.conftest
sys.path.insert(0, str(REPO / "src"))    # for triage_kit

from tests.conftest import make_trial  # noqa: E402

SUBMIT = {
    "trial_name": "demo__e2e",
    "summary": "Agent failed early: never edited the target file.",
    "checks": {
        "reward_hacking": {
            "outcome": "pass", "explanation": "no cheating observed",
        },
        "task_specification": {
            "outcome": "pass", "explanation": "instructions sufficient",
        },
    },
}


def completion(tool_calls=None, content=None, p=100, c=50):
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = [
            {
                "id": f"call-{i}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
            for i, (name, args) in enumerate(tool_calls)
        ]
    return {
        "id": "chatcmpl-mock", "object": "chat.completion", "created": 0,
        "model": "mock-model",
        "choices": [{"index": 0, "message": message,
                     "finish_reason": "tool_calls" if tool_calls else "stop"}],
        "usage": {"prompt_tokens": p, "completion_tokens": c,
                  "total_tokens": p + c},
    }


class MockEndpoint(BaseHTTPRequestHandler):
    """Scripted chat/completions; records what the harness actually sends."""

    calls: list[dict] = []

    def do_POST(self):
        try:
            self._handle()
        except Exception:
            import traceback
            traceback.print_exc()
            self.send_response(500)
            self.end_headers()

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        MockEndpoint.calls.append(body)
        print(f"[mock] POST {self.path} model={body.get('model')} "
              f"tools={[t['function']['name'] for t in body.get('tools', [])]}"
              f" tool_choice={body.get('tool_choice')}")

        turn = len(MockEndpoint.calls)
        if turn == 1:
            resp = completion(tool_calls=[
                ("read_file", {"path": "result.json"}),
            ])
        elif turn == 2:
            # verify the tool result flowed back before submitting
            msgs = body["messages"]
            tool_results = [m for m in msgs if m.get("role") == "tool"]
            assert tool_results and '"reward"' in tool_results[-1]["content"], \
                "read_file result did not flow back to the model"
            resp = completion(tool_calls=[("submit_analysis", SUBMIT)])
        else:
            resp = completion(content="unexpected extra turn")

        payload = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence default stderr logging
        pass


def main() -> None:
    workdir = Path(tempfile.mkdtemp(prefix="triage-e2e-"))
    trial = workdir / "demo__e2e"
    make_trial(trial, reward=0.0)
    print(f"trial dir: {trial}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), MockEndpoint)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"mock endpoint: http://127.0.0.1:{port}/v1\n")

    import os
    env = {**os.environ, "OPENAI_API_KEY": "mock-key-not-used"}
    proc = subprocess.run(
        [sys.executable, "-m", "triage_kit.cli", "analyze", str(trial),
         "--backend", "general", "--model", "glm-4.7",
         "--base-url", f"http://127.0.0.1:{port}/v1"],
        capture_output=True, text=True, cwd=str(REPO), env=env,
    )
    print(f"--- CLI exit={proc.returncode} ---")
    if proc.stdout:
        print(proc.stdout[-2000:])
    if proc.stderr:
        print(proc.stderr[-2000:])
    server.shutdown()

    assert proc.returncode == 0, "CLI failed"

    # product assertions (products live in the triage-kit/ subdirectory)
    products = trial / "triage-kit"
    analysis = json.loads(
        (products / "analysis.json").read_text(encoding="utf-8")
    )
    md = (products / "analysis.md").read_text(encoding="utf-8")
    assert analysis["summary"] == SUBMIT["summary"]
    assert analysis["checks"]["reward_hacking"]["outcome"] == "pass"
    assert "demo__e2e" in md and "reward_hacking" in md
    print("\nanalysis.json checks:", list(analysis["checks"]))
    print("analysis.md first line:", md.splitlines()[0])

    # wire-format assertions from the mock's call log
    first = MockEndpoint.calls[0]
    assert first["model"] == "glm-4.7"
    tool_names = {t["function"]["name"] for t in first["tools"]}
    assert tool_names == {"read_file", "glob", "grep", "submit_analysis"}
    assert first["tool_choice"] == "auto"
    assert len(MockEndpoint.calls) == 2, "expected exactly 2 API turns"

    print("\nE2E PASSED: CLI -> OpenAI client -> HTTP -> tool loop -> "
          "schema validation -> products. (2 turns, no retry)")


if __name__ == "__main__":
    main()
