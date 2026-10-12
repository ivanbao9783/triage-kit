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
- **Structured output — resolved by spike (NOT native):** neither the
  README nor the installed source exposes any schema/output constraint;
  `DeepSeekHarness.run` has no `output_schema` parameter. The mandatory
  capability must be approximated via **prompt-driven JSON + parse** (the
  shaped approach the retired general harness used). This is the main
  engineering risk for this backend.
- **Meta — resolved by spike (no usage):** `RunResult` fields are
  `session_id, final_response, finish_reason, events, notifications` — no
  tokens, no cost. `AgentMeta` renders those fields null unless they can
  be recovered from `events`/`notifications`.
- **Platform / size — resolved by spike:** Windows x64 wheel published
  (no Windows arm64); see Spike results below.

## Design

- Mirror `ClaudeHarness`: lazy SDK import, injectable harness for tests,
  an env guard on the real path only.
- `dsh_home`: create an isolated home per run (fresh home isolates
  profile-owned stores); a fresh `session_id` per trial for independent
  work.
- Structured output: wrap the judge prompt with an explicit "return only
  JSON matching this schema" instruction and `json.loads` + validate the
  parsed object (no schema-enforced decode from the harness).
- Read-only judge loop: the `sdk` profile inherits base `read`/`write`/
  `edit` tools, so there is **no** native read-only sandbox — constrain
  via prompt policy or a profile patch (Decision at Gate 1; overlaps the
  P013 concern).
- `query` (no tools, single-shot, job-level aggregation) → `run()` on the
  `sdk-minimal` profile (single shell tool) or a prompt-only path (verify
  which profile fits).
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

## Spike results (2026-10-12)

Venv install + real introspection of `deepseek-harness-sdk` **0.1.5rc1**
(PyPI metadata + `inspect.signature` + a keyword scan of the installed
source):

- **Structured output: NOT native.** `DeepSeekHarness.run(input, *,
  session_id=None, on_notification=None) -> RunResult` has no
  `output_schema`; a source scan of the installed package for
  `output_schema` / `json_schema` / `response_format` / `structured`
  returned **zero** hits (repo-wide search: only LSP/tool input schemas).
  → prompt-driven JSON + parse is required.
- **`RunResult` fields:** `session_id, final_response, finish_reason,
  events, notifications` → no token/cost surface (confirm whether
  `events`/`notifications` carry usage).
- **Windows / size:** win_amd64 wheel present
  (`deepseek_harness_runtime_bin-0.1.5rc1-py3-none-win_amd64.whl`,
  **68.7 MB**, plus the tiny `deepseek-harness-sdk` wheel); published
  targets are Linux x64/arm64, macOS x64/arm64, Windows x64 — **no
  Windows arm64**. Requires Python >=3.10; pulls `pydantic>=2.12`.
  Bundled native CLI (`dsh`), no system Node.
- **Maturity risk:** the only published version is a **release candidate
  (0.1.5rc1)** — treat the API as unstable; pin the exact version.

## Status & links

- Proposed 2026-10-12 (medium priority; registered while the backend seam
  is single-implementation).
- Spike 2026-10-12: structured output is **not** native (prompt-driven
  JSON needed); no token/cost in `RunResult`; Windows x64 only; SDK is
  `0.1.5rc1` — see Spike results.
- Related: P012 (backend seam), P013 (judge sandbox), P017 (Codex SDK
  peer). Upstream: https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md