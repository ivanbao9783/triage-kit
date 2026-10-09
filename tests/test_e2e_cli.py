"""Formalized E2E regression: `triage analyze` against a mock endpoint.

Covers the full production chain in one process boundary: CLI arg
parsing -> build_backend (with system-proxy exemption) -> openai.OpenAI
-> real HTTP to a scripted local server -> GeneralHarness tool loop
(read_file dispatch, result flow-back, forced-final schema) -> Analyzer
orchestration -> analysis.json/md products.

Skips automatically when the optional `openai` extra is not installed.
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.conftest import REPO_ROOT, make_trial

try:
    import openai  # noqa: F401

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

needs_openai = pytest.mark.skipif(
    not HAS_OPENAI, reason="openai extra not installed"
)

SUBMIT = {
    "trial_name": "demo__e2e",
    "summary": "Agent failed early: never edited the target file.",
    "checks": {
        "reward_hacking": {"outcome": "pass", "explanation": "no cheating"},
        "task_specification": {"outcome": "pass", "explanation": "clear"},
    },
}


def _completion(tool_calls=None, content=None, p=100, c=50):
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
    """Scripted chat/completions; records the exact request bodies."""

    calls: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        MockEndpoint.calls.append(body)

        turn = len(MockEndpoint.calls)
        if turn == 1:
            resp = _completion(tool_calls=[("read_file", {"path": "result.json"})])
        elif turn == 2:
            # tool results must have flowed back before submission
            tool_results = [m for m in body["messages"] if m.get("role") == "tool"]
            assert tool_results, "no tool result flowed back to the model"
            assert '"reward"' in tool_results[-1]["content"]
            resp = _completion(tool_calls=[("submit_analysis", SUBMIT)])
        else:
            resp = _completion(content="unexpected extra turn")

        payload = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence default stderr logging
        pass


@pytest.fixture
def mock_server():
    MockEndpoint.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockEndpoint)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


@needs_openai
class TestAnalyzeE2E:
    def test_full_chain_over_mock_endpoint(self, mock_server, tmp_path):
        trial = tmp_path / "demo__e2e"
        make_trial(trial, reward=0.0)

        port = mock_server.server_address[1]
        env = {
            **os.environ,
            "OPENAI_API_KEY": "mock-key",
            # make src/ importable even without an editable install
            "PYTHONPATH": str(REPO_ROOT / "src"),
        }
        proc = subprocess.run(
            [sys.executable, "-m", "triage_kit.cli", "analyze", str(trial),
             "--backend", "general", "--model", "glm-4.7",
             "--base-url", f"http://127.0.0.1:{port}/v1"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr

        # --- products ---
        analysis = json.loads(
            (trial / "triage-kit" / "analysis.json").read_text(encoding="utf-8")
        )
        md = (trial / "triage-kit" / "analysis.md").read_text(encoding="utf-8")
        assert analysis["summary"] == SUBMIT["summary"]
        assert analysis["checks"]["reward_hacking"]["outcome"] == "pass"
        assert "# Analysis: demo__e2e" in md

        # --- wire format (what the harness actually sent) ---
        assert len(MockEndpoint.calls) == 2  # exactly two turns
        first = MockEndpoint.calls[0]
        assert first["model"] == "glm-4.7"
        tool_names = {t["function"]["name"] for t in first["tools"]}
        assert tool_names == {"read_file", "glob", "grep", "submit_analysis"}
        assert first["tool_choice"] == "auto"
