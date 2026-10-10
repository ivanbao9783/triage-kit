# P008 — Forcing-path compatibility with reasoning endpoints

Status: **dropped** · Type: bugfix · Priority: high

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

**Finalized at Gate 1 (2026-10-10): hybrid — keep forced tool_choice,
add a single 400-fallback with prompt nudge.**

Rationale: in the 113-trial E2E, 16 of 47 analyzed trials (34%)
reached the forcing turn — forced tool_choice does real work on
struggling trials. Pure prompt-based forcing (option a) would regress
submission discipline on permissive endpoints; pure retention (no
fallback) keeps losing verdicts on thinking endpoints. The hybrid
keeps the hard guarantee where the endpoint honors it and degrades
gracefully where it does not.

Mechanics (harness.py, final-turn block only):

1. On the final turn, send the forced `tool_choice` request as today
   (permissive endpoints: behavior unchanged).
2. If that request raises an exception with
   `status_code == 400` (via `getattr`, no SDK import), log a
   WARNING and retry the same turn **once** with:
   - an appended user-role nudge message:
     "You have exhausted the tool-call turn budget. Do not call any
     further tools. Call the submit_analysis tool NOW with your best
     assessment based on the evidence gathered so far. If evidence is
     incomplete, state that explicitly in the summary."
   - `tool_choice="auto"`.
3. Non-400 exceptions propagate unchanged; a second 400 propagates
   (bounded — exactly one retry, no loop).
4. No budget extension: if the retried turn still fails to submit
   (text-only response, or a non-final tool call), the existing
   error paths apply (`ended turn without calling` /
   `did not call within N turns`).

Detection note: matching on `status_code == 400` alone (not message
text) — endpoint error phrasing is not stable across providers; a
non-tool_choice 400 wastes one retry and then surfaces, which is
acceptable.

## Compatibility impact

- Harness-internal only: no product/schema change, no asset change,
  no CLI change. Existing tests that assert forcing behavior may need
  updating alongside the chosen design.

## Verification plan

- Unit: fake client raises 400 on non-auto tool_choice — assert the
  trial still submits via the fallback path (nudge message present
  in the retried request).
- Unit: forcing still forces on a permissive fake client (forced
  request observed, no nudge).
- Unit: 400 on both attempts — the exception propagates (bounded
  retry).
- Unit: fallback turn responds text-only — `ended turn without
  calling` ValueError (no budget extension).
- Live: rerun the 16 affected trials from the `details` job (cache
  miss via `--force`); assert verdicts are produced.

## Status & links

- Proposed 2026-10-09. Evidence: `e2e-113.log` (46-trial run, 21
  failures, 16 × tool_choice 400).
- **Dropped 2026-10-10**: the defect carrier (general harness) is
  retired by P014 — the claude backend (Claude Agent SDK) has no
  forced-tool_choice mechanism and was verified live against the same
  DeepSeek thinking endpoint (E2E-lite, 16 autonomous turns, full
  product set). The affected 16 badcases are re-analyzed under P014's
  verification plan.
