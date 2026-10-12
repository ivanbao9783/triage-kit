# P016 — Criteria matrix / heatmap (cross-trial × dimension)

Status: **proposed** (2026-10-12) · Type: feature · Priority: **low**

## Background & motivation

The viewer (P006) shows per-trial diagnosis and a trials list, but no
cross-trial aggregate of the per-criterion verdicts. Every trial's
`analysis.json` already records `checks.<criterion>.outcome`
(`pass` / `fail` / `not_applicable`) for each rubric criterion
(`assets/analyze/analyze-rubric.toml`), and the job-level
`analysis.json` aggregates them under `trials[].checks` — the data is
already present, only the visualization is missing (the upstream
Harbor viewer ships a criteria heatmap/matrix).

User decision (2026-10-12): log only, do not build now — the column
count is tiny (two criteria) and the matrix is low-density.

## Goals

- A trials × criteria grid on the overview: rows = trials, columns =
  rubric criteria, cells color-coded by outcome, linking into each
  trial's diagnosis tab.
- A per-criterion aggregate (pass / fail / n/a counts and fail rate) —
  the analyze-side analogue of the check batch `per_criterion`.

## Non-goals

- No new product fields and no product-format change (`analysis.json`
  is read as-is).
- No criteria co-occurrence / pairing matrix.
- No check/tasks mode (still P006's deferred entry).

## Current state & gap

- `viewer/scanner.py` reads reward and verdict presence but not the
  per-criterion `checks` map; there is no aggregate view.

## Design

- Extend `scanner.load_overview` to read each trial's `checks` and
  build `criteria` (ordered union of criterion names), `matrix`
  (trial × criterion outcome) and per-criterion counts.
- Render server-side in `index.html` (zero JS): a table with colored
  cells; criterion columns derived from data (dataset-agnostic), never
  hardcoded.

## Compatibility impact

- Read-only; no product / cache / CLI change. Reuses the existing
  optional `[viewer]` extra.

## Verification plan

- TDD: scanner aggregation (multi-criterion, `not_applicable` handling,
  trial without `checks`); server render assertions. Live check against
  the P015 mini set (expect an all-pass 3 × 2 grid) and the 113-trial
  job.

## Status & links

- Proposed 2026-10-12 (low priority; logged while closing out P006).
- Related: P006 (viewer), P010 (job aggregation quality).