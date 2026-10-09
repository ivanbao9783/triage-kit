# P006 — Diagnosis results viewer

Status: **proposed** · Type: feature · Priority: medium

## Background & motivation

triage-kit produces `triage-kit/analysis.json|analysis.md` (per-trial
and per-job) and `triage-kit/check-result.json` (per-task), but
consumption today is raw file reading. The upstream evaluation
framework ships a viewer (FastAPI server + web frontend): scanners
walk job/trial/task directories, aggregate into summaries and
heatmaps (trials x criteria), and serve a bun-built frontend. It is
the natural reference implementation — but it reads the upstream flat
product layout (`<trial>/analysis.json`) and upstream model classes
(TrialResult etc.), so it cannot be reused as-is.

User decision (2026-10-09): triage-kit will build its own viewer
tailored to the new `triage-kit/` sub-directory layout; product
schemas are kept stable precisely so this viewer can read them
(DESIGN.md §7).

## Goals

- `triage view <job_dir|task_dir>` (or equivalent): local web UI for
  diagnosis results — per-trial/job attribution (analysis), per-task
  quality check verdicts (check), with the zh products rendered
  alongside English ones.
- Scanner layer adapted from the upstream viewer's approach:
  plain-JSON discovery of `triage-kit/` product directories, zero
  upstream model dependencies.

## Non-goals

- No wholesale reimplementation: the upstream viewer spans full
  evaluation lifecycle (jobs, models, pricing, critique heatmaps);
  triage-kit's viewer scopes to **diagnosis results** (analyze/check
  products) only.
- No remote/hosted deployment — local read-only viewing.
- No write path: the viewer never regenerates products (the upstream
  viewer has embedded summarize triggers; we keep judging in the CLI).

## Current state & gap

- Products exist with a stable schema and sidecar identity; no
  visualization at all.
- Reference: the upstream viewer (FastAPI server + scanners +
  bun-built frontend) — architecture is proven, the read layout
  differs.

## Design

**To be finalized when started** (Gate 1). Open questions: FastAPI +
bundled frontend (bun build, like the upstream viewer) vs a
zero-build static page reading a JSON bundle; heatmap scope (trials x
criteria, as in the upstream viewer); whether `analysis.zh.md`
toggling is UI-level; scanner reuse of `trial_reader`/`task_reader`
primitives vs new module.

## Compatibility impact

- Additive new module (`triage_kit/viewer/` + CLI command); reads
  products, never writes — no impact on cache or products.
- New dependency surface (fastapi/uvicorn or pure-static) — needs the
  dependency decision at Gate 1; the claude/general backends are
  unaffected.

## Verification plan

- TDD for scanner logic (product discovery, missing-file tolerance).
- Live verification: serve the `details` sample job (2 trials, real
  products) + one checked task; assert rendered content against the
  JSON products.

## Status & links

- Proposed 2026-10-09. Reference: the upstream evaluation
  framework's viewer module (FastAPI server, task_scanner, bun-built
  frontend).
