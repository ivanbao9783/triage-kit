# P009 — Tool exception isolation in the general harness

Status: **dropped** · Type: bugfix · Priority: medium

## Background & motivation

Live E2E on a real 113-trial job (2026-10-09, `details`, deepseek-flash,
`-j 16`): **5 of 21** failed trials died with
`NotImplementedError: Non-relative patterns are unsupported`, raised by
`Path.glob` (Python 3.13 pathlib) when the model passed an absolute
pattern to the `glob` tool. The exception propagates through the
harness tool-dispatch point (no try/except) and kills the whole trial:
a recoverable tool-argument mistake becomes a lost verdict.

`read_file` and `grep` already follow the defensive convention — bad
input returns an `"Error: ..."` string so the model can correct itself
and retry. `glob` lacks the guard, and the dispatch site has no
catch-all.

## Goals

- A tool-level exception never aborts the trial: the model receives
  the error as a tool result and can retry with corrected arguments.
- The fix follows the existing `"Error: ..."` tool-result convention.

## Non-goals

- No new tools, no tool signature changes.
- No retry budgets or automatic argument repair (the model retries on
  its own).
- No change to the sandbox security model (PermissionError deny-list
  behavior stays as-is).

## Current state & gap

- `backends/general/tools.py` `glob()` (~line 99): `r.glob(pattern)`
  uncaught; absolute patterns raise `NotImplementedError`.
- `backends/general/harness.py` (~line 215): `tool_result =
  getattr(tools_impl, name)(**args)` — no exception boundary; any
  tool exception escapes `query_agent`.

## Design

**To be finalized at Gate 1.** Two layers (belt and suspenders):

- (a) Harness dispatch boundary: wrap the dispatch in
  `except Exception` and return `f"Error: {type(e).__name__}: {e}"`
  as the tool result — guarantees isolation for every current and
  future tool.
- (b) `glob()` hardening: normalize or explicitly reject absolute
  patterns with a helpful message (e.g. suggest the relative form),
  matching the existing read_file/grep error style.
- Open question: should (b) convert absolute patterns to
  root-relative instead of erroring (more helpful, slightly more
  magic)?

## Compatibility impact

- Harness/tools internal: no product/schema/asset/CLI change. Tool
  results gain error strings the model already knows how to consume
  (convention exists in read_file/grep).

## Verification plan

- Unit: glob with an absolute pattern returns an `"Error: ..."`
  string, trial survives, loop continues.
- Unit: a tool raising an arbitrary exception is contained at the
  dispatch boundary.
- Live: rerun the 5 affected trials from the `details` job; assert
  verdicts are produced.

## Status & links

- Proposed 2026-10-09. Evidence: `e2e-113.log` (5 × glob
  NotImplementedError tracebacks through `tools.py:104`).
- **Dropped 2026-10-10**: the defect carrier (general harness tools)
  is retired by P014 — the claude backend uses the Claude Code CLI's
  own Glob implementation, which handles absolute patterns. The 5
  affected badcases are re-analyzed under P014's verification plan.
