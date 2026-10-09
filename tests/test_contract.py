"""Tests for triage_kit.core.contract — the backend contract."""

from pathlib import Path

from triage_kit.core.contract import AgentMeta


class TestAgentMeta:
    def test_required_and_optional_fields(self):
        meta = AgentMeta(n_turns=3, model="glm-4.7")
        assert meta.n_turns == 3
        assert meta.model == "glm-4.7"
        assert meta.n_input_tokens is None
        assert meta.n_output_tokens is None
        assert meta.cost_usd is None

    def test_backend_conformance_is_structural(self):
        """Any class with the right methods satisfies the Protocol."""
        from typing import Protocol, runtime_checkable

        from triage_kit.core.contract import AgentBackend

        class Fake:
            def query_agent(self, prompt, *, cwd, model, add_dirs=None,
                            output_schema=None, max_turns=15):
                return {}, AgentMeta(n_turns=1, model=model)

            def query(self, prompt, *, model):
                return "text", AgentMeta(n_turns=0, model=model)

        assert isinstance(Fake(), AgentBackend)
