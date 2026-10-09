"""General harness: an OpenAI-compatible client driven through the tool loop.

Implements the AgentBackend contract (core/contract.py). The agent gets
three sandboxed file tools (read_file/glob/grep, see tools.py) plus a
final tool ``submit_analysis`` whose argument schema is compiled from the
caller's output_schema — structured output via a forced tool call, so it
works with any OpenAI-compatible endpoint regardless of native
response_format support.

CLI demo::

    export OPENAI_API_KEY=...
    triage analyze <trial_or_job_dir> --backend general --model glm-4.7
    triage check <task_dir> --backend general --model glm-4.7
    # --model is required (no sane cross-endpoint default);
    # --base-url overrides the endpoint (auto-exempted from system proxies)
"""

import json
import logging
from pathlib import Path

from triage_kit.backends.general.tools import GeneralTools
from triage_kit.core.contract import AgentMeta
from triage_kit.core.schema import to_json_schema_dict

logger = logging.getLogger(__name__)

FINAL_TOOL = "submit_analysis"

_LOOSE_SCHEMA = {
    "type": "object",
    "properties": {"result": {"type": "string"}},
    "required": ["result"],
}

_TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a file. Relative paths resolve against the "
                "working directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {
                        "type": "integer",
                        "description": "Line offset to start from (0-based)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max lines to return (default 2000)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": (
                "Search file contents with a regex. Returns "
                "path:line:content matches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {
                        "type": "string",
                        "description": "File or directory (default '.')",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Restrict search to matching filenames",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]


class GeneralHarness:
    """AgentBackend over any OpenAI-compatible chat-completions client."""

    def __init__(self, client, *, default_model: str | None = None):
        self.client = client
        self.default_model = default_model

    def query_agent(
        self,
        prompt: str,
        *,
        cwd,
        model: str | None = None,
        add_dirs=None,
        output_schema=None,
        max_turns: int = 15,
    ):
        model = model or self.default_model
        tools_impl = GeneralTools(cwd=Path(cwd), add_dirs=add_dirs)
        logger.info(
            "query_agent start: model=%s cwd=%s max_turns=%d schema=%s",
            model, cwd, max_turns, output_schema is not None,
        )

        if output_schema is not None:
            final_schema = to_json_schema_dict(output_schema)
        else:
            final_schema = _LOOSE_SCHEMA
        tool_specs = _TOOL_SPECS + [
            {
                "type": "function",
                "function": {
                    "name": FINAL_TOOL,
                    "description": (
                        "Submit the final result. Call this exactly once, "
                        "after gathering all evidence."
                    ),
                    "parameters": final_schema,
                },
            }
        ]

        messages = [{"role": "user", "content": prompt}]
        n_turns = 0
        n_input = 0
        n_output = 0
        submitted = None

        for turn in range(max_turns):
            forcing = turn == max_turns - 1
            if forcing and submitted is None:
                logger.info(
                    "turn %d/%d: forcing submit_analysis (turn budget exhausted)",
                    turn + 1, max_turns,
                )
            logger.debug("turn %d/%d start", turn + 1, max_turns)
            tool_choice = (
                {"type": "function", "function": {"name": FINAL_TOOL}}
                if forcing
                else "auto"
            )
            resp = self.client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tool_specs,
                tool_choice=tool_choice,
            )
            n_turns += 1
            usage = getattr(resp, "usage", None)
            if usage is not None:
                n_input += getattr(usage, "prompt_tokens", 0) or 0
                n_output += getattr(usage, "completion_tokens", 0) or 0

            message = resp.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                raise ValueError(
                    f"model ended turn {turn + 1} without calling {FINAL_TOOL}"
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": getattr(message, "content", None) or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                logger.info(
                    "tool %s args=%s", name,
                    json.dumps(args, ensure_ascii=False)[:200],
                )
                if name == FINAL_TOOL:
                    submitted = args
                    tool_result = "Result received."
                elif hasattr(tools_impl, name):
                    tool_result = getattr(tools_impl, name)(**args)
                else:
                    tool_result = f"Error: unknown tool {name}"
                logger.debug(
                    "%s -> %d chars", name, len(str(tool_result)),
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(tool_result),
                    }
                )

            if submitted is not None:
                logger.info(
                    "%s received: turns=%d input_tokens=%d output_tokens=%d",
                    FINAL_TOOL, n_turns, n_input, n_output,
                )
                return submitted, AgentMeta(
                    n_turns=n_turns,
                    n_input_tokens=n_input or None,
                    n_output_tokens=n_output or None,
                    model=model,
                )

        logger.error(
            "model did not call %s within %d turns", FINAL_TOOL, max_turns,
        )
        raise ValueError(
            f"model did not call {FINAL_TOOL} within {max_turns} turns"
        )

    def query(self, prompt: str, *, model: str | None = None):
        model = model or self.default_model
        logger.info(
            "query (no tools): model=%s prompt=%d chars",
            model, len(prompt),
        )
        resp = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = getattr(resp, "usage", None)
        # Some endpoints omit content on tool-only/plain turns; the
        # aggregation layer expects a str (its empty-summary check is the
        # intended error path for blank responses).
        text = resp.choices[0].message.content or ""
        return (
            text,
            AgentMeta(
                n_turns=1,
                n_input_tokens=(getattr(usage, "prompt_tokens", 0) or None)
                if usage
                else None,
                n_output_tokens=(getattr(usage, "completion_tokens", 0) or None)
                if usage
                else None,
                model=model,
            ),
        )
