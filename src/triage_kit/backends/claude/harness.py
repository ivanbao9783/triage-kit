"""Claude harness: AgentBackend over claude_agent_sdk.

Ported from pier's analyze/backend.py (the reference implementation), with
two adaptations:

1. Contract fit — returns ``(result, meta)`` (core/contract.py) instead of
   a bare str/dict, and is synchronous (the SDK's async stream is bridged
   via asyncio.run).
2. Injectable SDK — tests pass a fake ``sdk`` namespace (query + message
   classes); the real path lazily imports claude_agent_sdk.

The SDK namespace must expose: ``query`` (async generator), and the
``AssistantMessage``/``ResultMessage``/``ToolUseBlock``/``TextBlock``
classes used for isinstance dispatch.

CLI demo (parameter-compatible with pier's analyze/check)::

    export ANTHROPIC_API_KEY=sk-ant-...
    triage analyze <trial_or_job_dir> --backend claude   # -m defaults to haiku
    triage check <task_dir> --backend claude             # -m defaults to sonnet
"""

import asyncio
import logging
import os

from triage_kit.core.contract import AgentMeta

logger = logging.getLogger(__name__)

DEFAULT_TOOLS = ["Read", "Glob", "Grep"]


def normalize_model_name(model: str) -> str:
    """Strip the "anthropic/" prefix; the SDK takes long names directly."""
    if model.startswith("anthropic/"):
        return model[len("anthropic/"):]
    return model


def _schema_dict(output_schema) -> dict:
    """Accept a pydantic model class or a plain JSON-schema dict."""
    if hasattr(output_schema, "model_json_schema"):
        return output_schema.model_json_schema()
    return dict(output_schema)


class ClaudeHarness:
    """AgentBackend over the Claude Agent SDK (reference harness)."""

    def __init__(self, *, default_model: str | None = None, sdk=None):
        self.default_model = default_model
        self._sdk = sdk

    def _load_sdk(self):
        if self._sdk is None:
            import claude_agent_sdk  # lazy: optional dependency

            self._sdk = claude_agent_sdk
        return self._sdk

    def _guard_real_path(self) -> None:
        """Env guard only applies to the real SDK path (tests inject one)."""
        if self._sdk is None and not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable is required. "
                "Set it with: export ANTHROPIC_API_KEY=sk-ant-..."
            )

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
        self._guard_real_path()
        # meta records what actually ran (post-normalization)
        model = normalize_model_name(model)
        sdk = self._load_sdk()

        options = sdk.ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            allowed_tools=DEFAULT_TOOLS,
            cwd=str(cwd),
            model=normalize_model_name(model),
            add_dirs=[str(d) for d in (add_dirs or [])],
        )
        if output_schema is not None:
            options.max_thinking_tokens = 10000
            options.output_format = {
                "type": "json_schema",
                "schema": _schema_dict(output_schema),
            }

        logger.info(
            "query_agent start: model=%s cwd=%s schema=%s",
            model, cwd, output_schema is not None,
        )

        structured_output = None
        text_parts: list[str] = []
        final: object | None = None

        async def run() -> None:
            nonlocal structured_output, final
            async for message in sdk.query(prompt=prompt, options=options):
                if isinstance(message, sdk.AssistantMessage):
                    for block in message.content:
                        if isinstance(block, sdk.ToolUseBlock) and \
                                block.name == "StructuredOutput":
                            structured_output = block.input
                        if output_schema is None and \
                                isinstance(block, sdk.TextBlock):
                            text_parts.append(block.text)
                elif isinstance(message, sdk.ResultMessage):
                    final = message
                    # ResultMessage wins when present
                    if message.structured_output is not None:
                        structured_output = message.structured_output

        asyncio.run(run())

        if final is None:
            raise ValueError("SDK stream ended without a ResultMessage")

        final_n_turns = getattr(final, "num_turns", 0)
        logger.info(
            "done: turns=%d cost=%s",
            final_n_turns, getattr(final, "total_cost_usd", None),
        )

        meta = AgentMeta(
            n_turns=final_n_turns,
            n_input_tokens=getattr(getattr(final, "usage", None),
                                   "input_tokens", None),
            n_output_tokens=getattr(getattr(final, "usage", None),
                                    "output_tokens", None),
            cost_usd=getattr(final, "total_cost_usd", None),
            model=model,
        )

        if output_schema is not None:
            if structured_output is None:
                logger.error("SDK did not return structured output")
                raise ValueError("SDK did not return structured output")
            return structured_output, meta

        return "\n".join(text_parts), meta

    def query(self, prompt: str, *, model: str | None = None):
        model = model or self.default_model
        self._guard_real_path()
        # meta records what actually ran (post-normalization)
        model = normalize_model_name(model)
        sdk = self._load_sdk()

        options = sdk.ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            allowed_tools=[],
            cwd=".",
            model=normalize_model_name(model),
        )
        logger.info("query (no tools): model=%s prompt=%d chars",
                    model, len(prompt))

        text_parts: list[str] = []
        final: object | None = None

        async def run() -> None:
            nonlocal final
            async for message in sdk.query(prompt=prompt, options=options):
                if isinstance(message, sdk.AssistantMessage):
                    for block in message.content:
                        if isinstance(block, sdk.TextBlock):
                            text_parts.append(block.text)
                elif isinstance(message, sdk.ResultMessage):
                    final = message

        asyncio.run(run())

        if final is None:
            raise ValueError("SDK stream ended without a ResultMessage")

        logger.info("done: turns=%d", getattr(final, "num_turns", 0))
        meta = AgentMeta(
            n_turns=getattr(final, "num_turns", 0),
            n_input_tokens=getattr(getattr(final, "usage", None),
                                   "input_tokens", None),
            n_output_tokens=getattr(getattr(final, "usage", None),
                                    "output_tokens", None),
            cost_usd=getattr(final, "total_cost_usd", None),
            model=model,
        )
        return "\n".join(text_parts), meta
