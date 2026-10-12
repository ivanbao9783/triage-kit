# P018 — DeepSeek Harness SDK backend

Status: **proposed** (2026-10-12) · Type: feature · Priority: **medium**

## Background & motivation

`--backend` is the project's single extension seam (P012): all harness
engineering sits behind `AgentBackend` (`core/contract.py`). DeepSeek is
the primary model family this project is exercised against (the P012
recovery E2E ran `deepseek-flash`), so a first-party DeepSeek harness is
a natural second backend.

The DeepSeek Harness Python SDK (`deepseek-harness-sdk`) drives DeepSeek's
own agent harness (`dsh --profile sdk`) over newline-delimited JSON-RPC on
stdio; the SDK ships the exact same-version, platform-specific runtime
wheel, so no system Node.js is required for normal runs. Usage is
`DeepSeekHarness(dsh_home=..., cwd=..., provider=..., model=...,
reasoning_effort=..., max_tokens=...)` → `harness.run(prompt,
session_id=...)` → `RunResult(final_response, finish_reason, events,
notifications)`. Credentials/endpoints come from `DEEPSEEK_API_KEY` /
`DEEPSEEK_BASE_URL` (overridable via `api_key` / `base_url`).

## Goals

- `backends/deepseek/harness.py` implementing `AgentBackend`
  (`query_agent` + `query`), mirroring `ClaudeHarness`.
- `--backend deepseek` selectable on both `analyze` and `check`; per-command
  default model added to `_DEFAULT_MODEL["deepseek"]`.
- Isolated `dsh_home` per invocation (never auto-discover `~/.dsh`);
  `cwd` → agent workspace; provider/model(/effort/token cap) threaded from
  the CLI `model`.
- Map `RunResult` into `AgentMeta` (nullable fields where the SDK does not
  surface a value).

## Non-goals

- No external plugin / profile authoring beyond the shipped `sdk`
  profile.
- No Office operations (a separate local API, unrelated to judging).
- No change to products, schemas, or cache identity (rubric sha256 +
  model); no new rubric / prompt assets; `claude` stays the default.
- No judge-sandbox work here (P013 covers the claude path).

## Current state & gap

- `cli.build_backend` maps only `claude`; `_DEFAULT_MODEL` has a single
  `claude` entry; `backends/` contains only `claude/`.
- **Gap / open question (structured output):** the README does not document
  a JSON-schema output mode — the harness owns the loop and returns
  `final_response` text. The mandatory `output_schema` capability must be
  satisfied natively or approximated (prompt-driven JSON + parse), same
  decision as P017.
- **Gap / open question (meta):** `RunResult` per the README exposes
  `final_response` / `finish_reason` / `events` / `notifications` — not
  tokens or cost. `AgentMeta` fields are nullable, but the metric gap
  should be confirmed against the API reference.
- **Gap / platform:** the runtime wheel is platform-specific and ships a
  bundled binary; confirm Windows support and the install footprint
  before landing.

## Design

- Mirror `ClaudeHarness`: lazy SDK import, injectable harness for tests,
  an env guard on the real path only.
- `dsh_home`: create an isolated home per run (fresh home isolates
  profile-owned stores); a fresh `session_id` per trial for independent
  work.
- `query` (no tools, single-shot, job-level aggregation) → `run()` with a
  tools-minimal profile / prompt-only path (verify which profile fits).
- CLI/env: honor `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`; add a
  `deepseek` extra in `pyproject.toml`; extend `build_backend`,
  `_DEFAULT_MODEL`, and the unknown-backend error to list valid values.

## Compatibility impact

- Additive CLI surface: a new `--backend deepseek` value; the claude path
  is unchanged. New optional dependency carrying a platform-specific
  runtime wheel (heavier than the other extras).
- Products and cache identity unchanged; the harness-not-in-identity note
  from P017 applies identically.

## Verification plan

- Unit: harness contract tests with an injected fake harness (mirror
  `tests/test_claude_harness.py`); `build_backend` / `_resolve_model`
  routing; unknown-backend rejection.
- Live E2E-lite: `triage analyze <trial> --backend deepseek -m
  deepseek-v4-flash --force` on a P015 mini trial; assert the runtime
  starts (profile handshake within `initialize_timeout_seconds`) and
  products / verdicts are well-formed (Gate 2 requires this live pass).

## Status & links

- Proposed 2026-10-12 (medium priority; registered while the backend seam
  is single-implementation).
- Related: P012 (backend seam), P013 (judge sandbox), P017 (Codex SDK
  peer). Upstream: https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md