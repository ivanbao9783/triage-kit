# P017 — Codex SDK backend

Status: **proposed** (2026-10-12) · Type: feature · Priority: **medium**

## Background & motivation

`--backend` is the project's single extension seam: all LLM harness
engineering lives behind `AgentBackend` (`core/contract.py`), and the
core never imports a backend directly. Today only `claude` is wired
(P012); the OpenAI Codex Python SDK (`openai-codex`) is a second
first-class harness whose entire tool loop / workspace access runs
inside the SDK.

The Codex SDK exposes `Codex()` (context manager) → `thread_start()` →
`thread.run(prompt)` → `TurnResult` (final response, collected items,
token usage); authentication reuses an existing Codex login or supports
ChatGPT browser / device-code / API-key login. Running the same rubric
and prompt assets through a second harness is what enables cross-harness
verdict comparison and reduces single-vendor dependence.

## Goals

- `backends/codex/harness.py` implementing `AgentBackend`
  (`query_agent` + `query`), mirroring `ClaudeHarness`.
- `--backend codex` selectable on both `analyze` and `check`; per-command
  default model added to `_DEFAULT_MODEL["codex"]`.
- Map the SDK's `TurnResult` / usage into `AgentMeta` (turns, tokens,
  cost — nullable fields where the SDK does not surface a value).
- Package the SDK as an optional extra; `claude-agent-sdk` stays the only
  hard dependency so the base install does not bloat.

## Non-goals

- No change to products, schemas, or cache identity (rubric sha256 +
  model).
- No new rubric / prompt assets.
- No removal of the `claude` backend — it stays the default.
- No judge-sandbox work here (P013 covers the claude path; Codex
  workspace access is a separate concern).
- No interactive login flow wired into the CLI — auth is out of band
  (the SDK reuses an existing Codex login or an API key set before the
  run).

## Current state & gap

- `cli.build_backend` maps only `claude`; `_DEFAULT_MODEL` has a single
  `claude` entry; `backends/` contains only `claude/` (the `trae` dir is
  a skill form, not a CLI backend).
- Contract: `AgentBackend.query_agent(prompt, *, cwd, model, add_dirs,
  output_schema, max_turns)` and `query(prompt, *, model)` —
  `output_schema` is a mandatory capability for `analyze`/`check`.
- **Structured output — resolved by spike (native):** `Thread.run(...)`
  takes `output_schema: JsonObject | None`; the schema-constrained result
  comes back as JSON text in `TurnResult.final_response` (parse with
  `json.loads`). No prompt-driven fallback is needed.

## Design

- Mirror `ClaudeHarness`: lazy SDK import, injectable `sdk` for tests, an
  env guard on the real path only, and a `_meta` mapping into
  `AgentMeta`.
- Parameter mapping: `cwd` → thread working directory; read-only judge
  loop → `sandbox=Sandbox.read_only` (native); `model` → `model`; `effort`
  → `ReasoningEffort`; `output_schema` → native
  `output_schema=` then `json.loads(final_response)`.
- Turn budget: the real signature exposes **no** turn/step cap (only
  `effort`), so `max_turns` is advisory here — the harness must bound the
  loop itself (or accept an unbounded turn and rely on the SDK's own
  limits). Decide during Gate 1.
- `query` (no tools, single-shot, job aggregation) → `thread.run` with a
  read-only/no-tool turn.
- Auth: reuse existing Codex auth; document the login precondition.
- Add a `codex` extra in `pyproject.toml`; extend `build_backend`,
  `_DEFAULT_MODEL`, and the unknown-backend error to list valid values.

## Compatibility impact

- Additive CLI surface: a new `--backend codex` value; the claude path is
  unchanged. New optional dependency / extra.
- Products and cache identity unchanged. **Note:** cache identity keys on
  `rubric sha256 + model`, not on the harness — two harnesses sharing a
  model string would collide unless the identity is extended (decision
  deferred; surface in the design review).

## Verification plan

- Unit: harness contract tests with an injected fake SDK (mirror
  `tests/test_claude_harness.py`); `build_backend` / `_resolve_model`
  routing; unknown-backend rejection.
- Live E2E-lite: `triage analyze <trial> --backend codex -m <model>
  --force` on a P015 mini trial; assert well-formed products and real
  verdicts (Gate 2 requires this live pass).

## Spike results (2026-10-12)

Venv install + real introspection of `openai-codex` **0.162.1** (PyPI
metadata + `inspect.signature` on the installed package):

- **Structured output: native.** `Thread.run(input, *, ..., output_schema:
  JsonObject | None = None, ...) -> TurnResult`; the example `12_turn_params_kitchen_sink`
  passes a raw JSON-schema dict and `json.loads`es `final_response`.
- **Sandbox: native presets** `Sandbox.read_only` / `workspace_write` /
  `full_access` → the read-only judge loop maps directly.
- **`TurnResult` fields:** `id, status, error, started_at, completed_at,
  duration_ms, final_response, items, usage`. `usage` is
  `ThreadTokenUsage(last, model_context_window, total)` → input/output
  token counts are available; **no `num_turns`** (derive `n_turns` from
  `items`) and **no cost** (null).
- **Windows / size:** win_amd64 wheel present
  (`openai_codex-0.162.1`, 0.1 MB + pinned `openai-codex-cli-bin==0.162.1`,
  **144.7 MB**); requires Python >=3.10; pulls `pydantic>=2.12`,
  `packaging>=26.2`. Bundled CLI, no system Node.
- Consequence: drop the prompt-driven fallback; `n_turns`/`cost` in
  `AgentMeta` are best-effort.

## Status & links

- Proposed 2026-10-12 (medium priority; registered while the backend seam
  is single-implementation).
- Spike 2026-10-12: structured output is native (`output_schema`) and the
  read-only sandbox is native; no turn cap, no cost — see Spike results.
- Related: P012 (backend seam), P013 (judge sandbox), P018 (DeepSeek
  harness SDK peer). Upstream: https://github.com/openai/codex/blob/main/sdk/python/README.md