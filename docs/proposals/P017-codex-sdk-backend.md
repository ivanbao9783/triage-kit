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
- **Gap / open question:** the Codex SDK README does not document
  JSON-schema-constrained output. The structured-output requirement must
  be satisfied natively or approximated (prompt-driven JSON + parse), and
  the fallback's schema-validation path decided.

## Design

- Mirror `ClaudeHarness`: lazy SDK import, injectable `sdk` for tests, an
  env guard on the real path only, and a `_meta` mapping into
  `AgentMeta`.
- Parameter mapping: `cwd` → thread working directory; read-only tools
  (`Read`/`Glob`/`Grep` equivalent) → Codex workspace access; `max_turns`
  → turn cap (confirm the SDK exposes one); `output_schema` → native
  structured output if available, else the prompt-driven fallback above.
- `query` (no tools, single-shot, job-level aggregation) → `thread.run`
  with tools disabled.
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

## Status & links

- Proposed 2026-10-12 (medium priority; registered while the backend seam
  is single-implementation).
- Related: P012 (backend seam), P013 (judge sandbox), P018 (DeepSeek
  harness SDK peer). Upstream: https://github.com/openai/codex/blob/main/sdk/python/README.md