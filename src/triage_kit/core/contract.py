"""The backend contract — the ONLY interface between core and LLM harnesses.

`query_agent`: judge loop with read-only tools over a working directory,
optionally constrained to a structured output schema.
`query`: plain single-shot text call (job-level aggregation).

Harnesses live in `backends/` and implement this Protocol; core never
imports a backend directly.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class AgentMeta(BaseModel):
    """Execution metadata. Fields are nullable but the structure is fixed."""

    n_turns: int
    n_input_tokens: int | None = None
    n_output_tokens: int | None = None
    cost_usd: float | None = None
    model: str


@runtime_checkable
class AgentBackend(Protocol):
    def query_agent(
        self,
        prompt: str,
        *,
        cwd: Path,
        model: str,
        add_dirs: list[Path] | None = None,
        output_schema: type[BaseModel] | None = None,
        max_turns: int = 15,
    ) -> tuple[dict, AgentMeta]: ...

    def query(self, prompt: str, *, model: str) -> tuple[str, AgentMeta]: ...
