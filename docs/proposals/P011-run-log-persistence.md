# P011 — Run log persistence under triage-kit/

Status: **accepted** · Type: feature · Priority: medium

## Background & motivation

Live debugging of the 113-trial E2E (2026-10-09) relied on ad-hoc
console redirection; the run log was a side artifact of how the
command was invoked, not a product. Debugging badcase analysis after
the fact (what did the judge read? which turn failed? why 400?)
requires the log to survive alongside the products.

## Goals

- Each analyze/check run persists its execution log inside the
  products directory (`<dir>/triage-kit/`), self-contained with the
  verdicts it explains.
- Logs are cleaned up by the existing `triage clean` flow (they live
  under `triage-kit/`) — no new lifecycle commands.

## Non-goals

- No remote/log-shipping, no rotation service, no structured
  (JSON-lines) log format change — plain text, same content as the
  console emits today.
- No log retention policy beyond `triage clean`.

## Current state & gap

- Logging goes to the console only (root handler installed by the
  CLI). `-v` toggles DEBUG; nothing is written to disk.
- Judge-visibility note (corrected 2026-10-10): the earlier claim
  that "the sandbox already deny-lists `triage-kit/`, so logs cannot
  leak into a later judge run" described the retired general
  backend. On the claude path the CLI tools do not pass through any
  deny-list (the P013 gap): a persisted `run.log` is exactly as
  visible to a later judge as the `analysis.json` already sitting in
  the same directory. Persisting the log adds no new exposure
  surface; closing the gap itself is P013's scope.

## Design

User-confirmed decisions (2026-10-10, Gate 1):

1. **Location & naming (D1)**: one file per invocation, at
   `<path>/triage-kit/run.log` where `<path>` is the CLI argument
   (trial dir / job dir / task dir alike — the products dir is
   `path/triage-kit/` on all three commands, so a single assembly
   point covers them).
2. **Overwrite, not append (D2)**: `mode="w"` per run. The log must
   explain the products it sits next to; append would let stale
   entries contradict fresh verdicts and grow unboundedly across
   `--force` reruns.
3. **File level is always DEBUG (D3)**: the console keeps its
   current behavior (INFO default, DEBUG with `-v`). The whole point
   of persistence is after-the-fact debugging (what did the judge
   read, which turn failed) — that detail lives at DEBUG. Observed
   volume from the 113-trial E2E: ~17k lines (~2 MB) at full DEBUG,
   acceptable.

Implementation shape: each CLI command attaches a
`logging.FileHandler(path/triage-kit/run.log, mode="w")` with level
DEBUG after argument validation, before execution; the handler is
removed at command end. Concurrency (P003): 16 workers interleaving
into one file handler is safe (logging locks per record) and the
`[trial_name]` prefixes carry attribution. `triage clean` needs no
change (whole-directory removal already covers the log).

## Compatibility impact

- New file inside `triage-kit/` products (schema-bearing files
  unchanged; the products-dir contract allows additional files).
- `triage clean` needs no change (already removes the whole
  directory).

## Verification plan

- Unit: log file appears under `triage-kit/`, contains prefixed
  records, clean removes it.
- Live: rerun a small job; confirm the log explains a deliberately
  broken trial (e.g. a 400) after the fact.

## Status & links

- Proposed 2026-10-09. Gate 1 accepted 2026-10-10 (D1 unified
  `run.log`, D2 overwrite, D3 file-always-DEBUG). Related: P003
  (`[trial_name]` prefixes make persisted logs attributable); P013
  (judge-visibility gap applies to the log the same as to existing
  products).
