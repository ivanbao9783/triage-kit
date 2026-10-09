# P004 — Multi-step task per-step check expansion

Status: **proposed** · Type: feature · Priority: low

## Background & motivation

Multi-step tasks (`steps/` with per-step `instruction.md`) are a
Harbor-native format. `task_reader.detect_steps` already detects and
validates them, but `Checker.check_task` runs a **single whole-task
pass** — the per-step expansion once claimed in the v2 design doc was
never built (fixed in the v3 as-built rewrite). Consequence: for
multi-step tasks where the root `instruction.md`/`tests/` are empty,
several criteria lose their subject — the same blind spot the upstream
originals have.

## Goals

- `triage check <multi_step_task_dir>` expands to per-step checks
  (each step judged against the rubric) plus an aggregated top-level
  verdict; products land per-step under
  `steps/<step-n>/triage-kit/check-result.json` with a summary at the
  task root.

## Non-goals

- No analyzer-side (trial) changes — multi-step applies to the check
  workflow only.
- No new criteria or schema changes.

## Current state & gap

- `task_reader`: `detect_steps` + validation implemented (empty
  `steps/` is rejected).
- `checker`: single-pass only; no per-step loop, no aggregation.

## Design

**To be finalized when started** (Gate 1). Open questions: per-step
prompt rendering (file tree scoped to the step dir?); cache identity
for step products (rubric sha + model per step); aggregation format
(steps' verdicts into one summary — reuse analyze-job aggregation
pattern as candidate).

## Compatibility impact

Additive: new product locations only for multi-step tasks;
single-step tasks unchanged. Tests: new fixtures with steps/, plus
aggregation tests.

## Verification plan

- TDD: multi-step fixture driven by FakeBackend (per-step calls
  scripted), single-step regression untouched.
- Live verification: check a real multi-step task (locate one from
  the dataset or construct from DeepSWE samples).

## Status & links

- Proposed 2026-10-09 during the DESIGN.md v3 as-built audit
  (phantom-feature finding, honestly re-filed here).
