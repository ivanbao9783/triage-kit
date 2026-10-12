# P017 — Codex SDK backend

Status: **accepted** (2026-10-12) · Type: feature · Priority: **medium**

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
- `--backend codex` selectable on both `analyze` and `check`;
  `_DEFAULT_MODEL["codex"] = {"analyze": "gpt-5.4", "check": "gpt-5.4"}`
  (overridable with `-m`).
- Map `TurnResult` / usage into `AgentMeta`.
- Package the SDK as an optional `codex` extra; `claude-agent-sdk` stays
  the only hard dependency so the base install does not bloat.
- Prerequisite contract cleanup: drop the dead `max_turns` parameter
  (see Decisions D1).

## Non-goals

- No change to products or cache identity (kept as `rubric sha256 +
  model`; see Decisions D3).
- No new rubric / prompt assets.
- No removal of the `claude` backend — it stays the default.
- No judge-sandbox work here (P013 covers the claude path).
- No interactive login flow wired into the CLI — auth is out of band.
- No turn-cap re-implementation: since neither claude (unwired) nor codex
  (no SDK support) uses `max_turns`, the parameter is deleted rather than
  enforced (see Decisions D1).

## Current state & gap

- `cli.build_backend` maps only `claude`; `_DEFAULT_MODEL` has a single
  `claude` entry; `backends/` contains only `claude/` (the `trae` dir is
  a skill form, not a CLI backend).
- Contract: `AgentBackend.query_agent(prompt, *, cwd, model, add_dirs,
  output_schema)` and `query(prompt, *, model)` — `output_schema` is a
  mandatory capability for `analyze`/`check`.
- **Structured output — resolved by spike (native):** `Thread.run(...)`
  takes `output_schema: JsonObject | None`; the schema-constrained result
  comes back as JSON text in `TurnResult.final_response` (parse with
  `json.loads`). No prompt-driven fallback is needed.
- **`max_turns` — dead parameter:** declared in the contract, accepted but
  never wired by `ClaudeHarness` (the SDK *does* support it), never passed
  by `analyzer`/`checker`, and absent from pier's own `query_agent`
  signature (pier only carries it as a Claude-Code CLI flag for the
  *evaluated* agent). Codex has no such parameter either → delete.

## Design

- Mirror `ClaudeHarness`: lazy SDK import, injectable `sdk` for tests, an
  env guard on the real path only, and a `_meta` mapping into
  `AgentMeta`.
- Parameter mapping: `cwd` → thread working directory; read-only judge
  loop → `sandbox=Sandbox.read_only`; `model` → `model`; `output_schema`
  → native `output_schema=` then `json.loads(final_response)`.
- Sandbox / approval: Codex defaults turn starts to
  `ApprovalMode.auto_review`; the harness sets `Sandbox.read_only` so the
  judge cannot write the trial directory (mirrors the claude
  `allowed_tools=[Read, Glob, Grep]` intent). Confirm `add_dirs`
  (task_dir) maps to a readable extra root at implementation.
- `AgentMeta`: `n_turns` derived from `TurnResult.items`; input/output
  token counts from `usage.total`; `cost_usd` is `None` (the SDK exposes
  no cost).
- `query` (no tools, single-shot, job aggregation) → `thread.run` with a
  read-only / no-tool turn.
- Auth: reuse existing Codex auth locally; Gate 2 E2E must use a
  non-interactive API-key path.
- Contract cleanup: remove `max_turns` from `core/contract.py`,
  `ClaudeHarness.query_agent`, the test fakes, and the DESIGN.md `n_turns`
  note.
- Packaging: add a `codex` extra in `pyproject.toml`; bump
  `pydantic>=2.12`; extend `build_backend`, `_DEFAULT_MODEL`, and the
  unknown-backend error to list valid values.

## Decisions (Gate 1, 2026-10-12)

| # | Decision | Rationale |
|---|---|---|
| D1 | Delete `max_turns` | Dead: never passed by callers, never honored by claude, not inherited from pier, unsupported by Codex. |
| D2 | Default model `gpt-5.4` for both `analyze` and `check` | Matches the official SDK example; `-m` overrides. |
| D3 | Cache identity unchanged (`rubric sha256 + model`) | Real model strings differ per harness, so collisions are contrived; documented as a limitation instead of paying a cache-key migration. |
| D4 | Structured output via native `output_schema` | Spike-confirmed; no prompt-driven fallback. |

## Compatibility impact

- Additive CLI surface (`--backend codex`); the claude path is unchanged.
  New optional extra plus a `pydantic>=2.12` floor bump.
- Products unchanged. **Known limitation (D3):** the cache identity does
  not include the harness, so two harnesses sharing one model string
  would collide; accepted as-is.

## Verification plan

- Unit: harness contract tests with an injected fake SDK (mirror
  `tests/test_claude_harness.py`); `build_backend` / `_resolve_model`
  routing; unknown-backend rejection; the `max_turns` removal keeps the
  test fakes consistent.
- Live E2E-lite: `triage analyze <trial> --backend codex -m gpt-5.4
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

- **Gate 1 passed 2026-10-12** → `accepted`; implementation pending.
  Decisions D1–D4 recorded above.
- Spike 2026-10-12: structured output is native (`output_schema`) and the
  read-only sandbox is native; no turn cap, no cost — see Spike results.
- Related: P012 (backend seam), P013 (judge sandbox), P018 (DeepSeek
  harness SDK peer). Upstream: https://github.com/openai/codex/blob/main/sdk/python/README.md