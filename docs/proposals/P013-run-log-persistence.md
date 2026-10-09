# P013 — Run log persistence under triage-kit/

Status: **proposed** · Type: feature · Priority: medium

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
- The judge sandbox already deny-lists `triage-kit/` for
  read_file/glob/grep, so persisted logs cannot leak into a later
  judge run (self-referential bias guard already covers this).

## Design

**To be finalized at Gate 1.** Candidate shape:

- A per-run file handler attached at CLI start, writing to
  `<dir>/triage-kit/run.log` (name TBD: `run.log` vs
  `analysis.log` / `check.log` per command).
- Level: mirror the console level (INFO default, DEBUG with `-v`).
- Overwrite per run vs append-with-run-header (append preserves
  history across `--force` reruns; overwrite keeps size bounded).
- Concurrency note (P003): 16 workers interleaving into one file
  handler is safe (logging handlers are locked per-record) and the
  `[trial_name]` prefixes carry the attribution.
- Open questions: log file naming; append vs overwrite; whether the
  job-level product dir or each trial dir gets the log (single
  job-level file recommended).

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

- Proposed 2026-10-09. Related: P003 (`[trial_name]` prefixes make
  persisted logs attributable).
