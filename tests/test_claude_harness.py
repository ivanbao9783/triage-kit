"""Tests for backends/claude/harness.py — ClaudeHarness over a fake SDK.

The claude_agent_sdk surface (query + message classes) is injected, so the
port's logic — async-to-sync bridging, StructuredOutput dual-path capture,
token accounting, options wiring — is verified without the SDK installed.
"""

from types import SimpleNamespace

import pytest

SUBMIT_RESULT = {"trial_name": "t", "summary": "s"}
SCHEMA = {"type": "object", "properties": {}}


# ---------- fake claude_agent_sdk surface ----------

class FakeToolUseBlock:
    def __init__(self, name, input):
        self.name = name
        self.input = input


class FakeTextBlock:
    def __init__(self, text):
        self.text = text


class FakeAssistantMessage:
    def __init__(self, content):
        self.content = content


class FakeResultMessage:
    def __init__(self, *, structured_output=None, num_turns=0,
                 total_cost_usd=None, input_tokens=None, output_tokens=None):
        self.structured_output = structured_output
        self.num_turns = num_turns
        self.total_cost_usd = total_cost_usd
        self.usage = SimpleNamespace(
            input_tokens=input_tokens, output_tokens=output_tokens
        )


def make_fake_sdk(messages):
    class FakeSDK:
        # captured options for assertions
        last_options = None

        @staticmethod
        def ClaudeAgentOptions(**kwargs):
            opts = SimpleNamespace(**kwargs)
            FakeSDK.last_options = opts
            return opts

        @staticmethod
        async def query(*, prompt, options):
            for m in messages:
                yield m

    # harness uses isinstance() against these
    FakeSDK.AssistantMessage = FakeAssistantMessage
    FakeSDK.ResultMessage = FakeResultMessage
    FakeSDK.ToolUseBlock = FakeToolUseBlock
    FakeSDK.TextBlock = FakeTextBlock
    return FakeSDK


@pytest.fixture
def workdir(tmp_path):
    (tmp_path / "result.json").write_text('{"reward": 1}', encoding="utf-8")
    return tmp_path


class TestNormalizeModelName:
    def test_strips_anthropic_prefix(self):
        from triage_kit.backends.claude.harness import normalize_model_name

        assert normalize_model_name("anthropic/claude-sonnet-4-6") == \
            "claude-sonnet-4-6"
        assert normalize_model_name("sonnet") == "sonnet"


class TestQueryAgent:
    def test_structured_result_and_meta_from_result_message(self, workdir):
        from triage_kit.backends.claude.harness import ClaudeHarness

        sdk = make_fake_sdk([
            FakeAssistantMessage([FakeToolUseBlock("StructuredOutput",
                                                   {"fallback": True})]),
            FakeResultMessage(
                structured_output=SUBMIT_RESULT, num_turns=3,
                total_cost_usd=0.05, input_tokens=100, output_tokens=50,
            ),
        ])
        result, meta = ClaudeHarness(default_model="m", sdk=sdk).query_agent(
            "analyze", cwd=workdir, model="anthropic/m", output_schema=SCHEMA
        )

        # ResultMessage.structured_output wins over the ToolUseBlock fallback
        assert result == SUBMIT_RESULT
        assert meta.n_turns == 3
        assert meta.cost_usd == 0.05
        assert meta.n_input_tokens == 100
        assert meta.n_output_tokens == 50
        assert meta.model == "m"

    def test_tool_use_fallback_when_result_message_lacks_output(self, workdir):
        from triage_kit.backends.claude.harness import ClaudeHarness

        fallback = {"trial_name": "t", "summary": "from tool use"}
        sdk = make_fake_sdk([
            FakeAssistantMessage(
                [FakeToolUseBlock("StructuredOutput", fallback)]
            ),
            FakeResultMessage(structured_output=None, num_turns=2),
        ])
        result, _ = ClaudeHarness(default_model="m", sdk=sdk).query_agent(
            "analyze", cwd=workdir, model="m", output_schema=SCHEMA
        )
        assert result == fallback

    def test_missing_structured_output_raises(self, workdir):
        from triage_kit.backends.claude.harness import ClaudeHarness

        sdk = make_fake_sdk([FakeResultMessage(structured_output=None)])
        with pytest.raises(ValueError):
            ClaudeHarness(default_model="m", sdk=sdk).query_agent(
                "analyze", cwd=workdir, model="m", output_schema=SCHEMA
            )

    def test_text_mode_joins_text_blocks(self, workdir):
        from triage_kit.backends.claude.harness import ClaudeHarness

        sdk = make_fake_sdk([
            FakeAssistantMessage([FakeTextBlock("part one, ")]),
            FakeAssistantMessage([FakeToolUseBlock("Read", {"file_path": "x"})]),
            FakeResultMessage(num_turns=2),
        ])
        text, meta = ClaudeHarness(default_model="m", sdk=sdk).query_agent(
            "analyze", cwd=workdir, model="m"
        )
        assert text == "part one, "
        assert meta.n_turns == 2


class TestOptionsWiring:
    def test_agent_options_default_tools_and_paths(self, workdir, tmp_path):
        from triage_kit.backends.claude.harness import ClaudeHarness

        extra = tmp_path / "task"
        extra.mkdir()
        sdk = make_fake_sdk([FakeResultMessage(structured_output=SUBMIT_RESULT)])
        ClaudeHarness(default_model="m", sdk=sdk).query_agent(
            "analyze", cwd=workdir, model="anthropic/claude-x",
            add_dirs=[extra],
        )

        opts = sdk.last_options
        assert opts.allowed_tools == ["Read", "Glob", "Grep"]
        assert opts.permission_mode == "bypassPermissions"
        assert opts.model == "claude-x"          # normalized
        assert opts.cwd == str(workdir)
        assert opts.add_dirs == [str(extra)]

    def test_schema_sets_output_format(self, workdir):
        from triage_kit.backends.claude.harness import ClaudeHarness

        class OutputModel:
            @staticmethod
            def model_json_schema():
                return {"type": "object", "properties": {}}

        sdk = make_fake_sdk([FakeResultMessage(structured_output=SUBMIT_RESULT)])
        ClaudeHarness(default_model="m", sdk=sdk).query_agent(
            "analyze", cwd=workdir, model="m", output_schema=OutputModel,
        )

        opts = sdk.last_options
        assert opts.output_format == {
            "type": "json_schema",
            "schema": {"type": "object", "properties": {}},
        }
        assert opts.max_thinking_tokens == 10000


class TestQueryPlain:
    def test_query_runs_without_tools(self):
        from triage_kit.backends.claude.harness import ClaudeHarness

        sdk = make_fake_sdk([FakeResultMessage(num_turns=1)])
        text, meta = ClaudeHarness(default_model="m", sdk=sdk).query(
            "aggregate", model="m"
        )

        assert text == ""
        assert meta.n_turns == 1
        opts = sdk.last_options
        assert opts.allowed_tools == []
        assert opts.cwd == "."


class TestRealPathGuard:
    def test_missing_api_key_raises_before_sdk_import(self, workdir,
                                                     monkeypatch):
        from triage_kit.backends.claude.harness import ClaudeHarness

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            ClaudeHarness().query_agent("x", cwd=workdir, model="m")
