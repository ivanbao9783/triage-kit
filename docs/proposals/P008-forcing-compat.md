# P008 — Forcing-path compatibility with reasoning endpoints

Status: **proposed** · Type: bugfix · Priority: high

## Background & motivation

Live E2E on a real 113-trial job (2026-10-09, `details`, deepseek-flash,
`-j 16`): of 46 failing trials analyzed, 21 errored. **16 of the 21**
failed with `BadRequestError 400 — "Thinking mode does not support this
tool_choice"`. Root cause: when the turn budget is exhausted, the
general harness forces submission by setting
`tool_choice={"type": "function", "function": {"name": submit_analysis}}`
on the final turn. DeepSeek reasoning endpoints reject any non-`auto`
tool_choice, so the request itself 400s and the trial dies — the
verdict is never produced. Log evidence: every 400 failure follows a
`turn 15/15: forcing submit_analysis (turn budget exhausted)` line
(3/3 sampled, prefix-attributed).

## Goals

- Budget-exhausted trials still produce a verdict on endpoints that
  reject explicit tool_choice (DeepSeek thinking mode and similar).
- The forcing fallback degrades gracefully: one retry path, no
  infinite loops, no silent verdicts.

## Non-goals

- No endpoint capability detection framework (no per-provider config
  matrix).
- No change to `max_turns` semantics or the final-tool contract.
- No change to the claude backend (the Agent SDK has its own
  submission mechanism).
- Not fixing "the model used all 15 turns" itself — that is model
  behavior, out of scope.

## Current state & gap

`backends/general/harness.py` (~line 151-169): on the last turn the
loop sets the forced `tool_choice` and calls the endpoint. Works on
standard OpenAI-compatible endpoints; hard-fails on DeepSeek thinking
mode. The 400 exception propagates out of `query_agent`, the analyzer
collects the trial into `failed_trials`, and no product is written.

## Design

**To be finalized at Gate 1.** Candidate directions:

- (a) Prompt-based forcing: on the final turn, append a user-role
  nudge ("call submit_analysis now with your best assessment") and
  keep `tool_choice="auto"` — endpoint-agnostic.
- (b) Reactive fallback: try forced `tool_choice` first; on a 400
  that mentions tool_choice/thinking, retry once without it plus the
  prompt nudge.
- Open question: does (a) alone weaken submission discipline on
  endpoints where tool_choice forcing works today?

## Compatibility impact

- Harness-internal only: no product/schema change, no asset change,
  no CLI change. Existing tests that assert forcing behavior may need
  updating alongside the chosen design.

## Verification plan

- Unit: fake client raises 400 on non-auto tool_choice — assert the
  trial still submits and produces a result.
- Unit: forcing still forces on a permissive fake client.
- Live: rerun the 16 affected trials from the `details` job (cache
  miss via `--force`); assert verdicts are produced.

## Status & links

- Proposed 2026-10-09. Evidence: `e2e-113.log` (46-trial run, 21
  failures, 16 × tool_choice 400).
