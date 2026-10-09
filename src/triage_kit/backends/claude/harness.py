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
from triage_kit.core.schema import to_json_schema_dict

logger = logging.getLogger(__name__)

DEFAULT_TOOLS = ["Read", "Glob", "Grep"]


def normalize_model_name(model: str) -> str:
    """Strip the "anthropic/" prefix; the SDK takes long names directly."""
    if model.startswith("anthropic/"):
        return model[len("anthropic/"):]
    return model


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

    def _collect(self, sdk, prompt: str, options):
        """Consume one SDK query stream: (final, text_parts, structured).

        Collects both text and StructuredOutput unconditionally — each
        public method picks what its contract variant needs.
        """
        text_parts: list[str] = []
        structured_output = None
        final = None

        async def run() -> None:
            nonlocal structured_output, final
            async for message in sdk.query(prompt=prompt, options=options):
                if isinstance(message, sdk.AssistantMessage):
                    for block in message.content:
                        if isinstance(block, sdk.ToolUseBlock) and \
                                block.name == "StructuredOutput":
                            structured_output = block.input
                        if isinstance(block, sdk.TextBlock):
                            text_parts.append(block.text)
                elif isinstance(message, sdk.ResultMessage):
                    final = message
                    # ResultMessage wins when present
                    if message.structured_output is not None:
                        structured_output = message.structured_output

        asyncio.run(run())
        return final, text_parts, structured_output

    @staticmethod
    def _meta(final, model: str) -> AgentMeta:
        usage = getattr(final, "usage", None)
        return AgentMeta(
            n_turns=getattr(final, "num_turns", 0),
            n_input_tokens=getattr(usage, "input_tokens", None),
            n_output_tokens=getattr(usage, "output_tokens", None),
            cost_usd=getattr(final, "total_cost_usd", None),
            model=model,
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
        self._guard_real_path()
        # meta records what actually ran (post-normalization)
        model = normalize_model_name(model or self.default_model)
        sdk = self._load_sdk()

        options = sdk.ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            allowed_tools=DEFAULT_TOOLS,
            cwd=str(cwd),
            model=model,
            add_dirs=[str(d) for d in (add_dirs or [])],
        )
        if output_schema is not None:
            options.max_thinking_tokens = 10000
            options.output_format = {
                "type": "json_schema",
                "schema": to_json_schema_dict(output_schema),
            }

        logger.info(
            "query_agent start: model=%s cwd=%s schema=%s",
            model, cwd, output_schema is not None,
        )

        final, text_parts, structured_output = self._collect(
            sdk, prompt, options
        )
        if final is None:
            raise ValueError("SDK stream ended without a ResultMessage")

        logger.info(
            "done: turns=%d cost=%s",
            getattr(final, "num_turns", 0),
            getattr(final, "total_cost_usd", None),
        )
        meta = self._meta(final, model)

        if output_schema is not None:
            if structured_output is None:
                logger.error("SDK did not return structured output")
                raise ValueError("SDK did not return structured output")
            return structured_output, meta

        return "\n".join(text_parts), meta

    def query(self, prompt: str, *, model: str | None = None):
        self._guard_real_path()
        # meta records what actually ran (post-normalization)
        model = normalize_model_name(model or self.default_model)
        sdk = self._load_sdk()

        options = sdk.ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            allowed_tools=[],
            cwd=".",
            model=model,
        )
        logger.info("query (no tools): model=%s prompt=%d chars",
                    model, len(prompt))

        final, text_parts, _structured = self._collect(sdk, prompt, options)
        if final is None:
            raise ValueError("SDK stream ended without a ResultMessage")

        logger.info("done: turns=%d", getattr(final, "num_turns", 0))
        return "\n".join(text_parts), self._meta(final, model)
