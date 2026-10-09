# P010 — Single-item flows: verification + documentation

Status: **proposed** · Type: docs · Priority: low

## Background & motivation

Live usage during the 113-trial E2E (2026-10-09) surfaced the question
of whether single-granularity workflows are supported. Code review
confirms both already are:

- `triage analyze <trial_dir>` — single trial (CLI detects the dir
  shape; runs without the thread pool, no job aggregation)
- `triage check <task_dir>` — single task (task.toml required)

Neither flow is called out in the README; the examples only show job
and multi-item forms. No code change is expected.

## Goals

- Live-verify both single-item flows against real endpoints
  (one trial from `details`, one task from `deep-swe/tasks/`).
- Document both flows in the README usage section.

## Non-goals

- No CLI/code changes (if verification exposes a real defect, it gets
  its own entry instead of scope-creeping this one).
- No new tests beyond what already covers these paths.

## Current state & gap

- Code paths exist and are unit-tested (single-trial analyze,
  single-task check).
- README shows `triage analyze path/to/trial` only in passing inside
  the claude backend block; no explicit single-item usage section.

## Design

Documentation-only: add a short "single-item flows" subsection to the
README usage area showing both concrete command forms and what
products they produce (trial-level products without job aggregation;
task-level check products).

## Compatibility impact

None — docs only.

## Verification plan

- Run `triage analyze details/<one failing trial> --backend general
  --model deepseek-flash --base-url https://api.deepseek.com` and one
  `triage check deep-swe/tasks/<task>` against the live endpoint;
  confirm products land correctly.
- README review against actual `--help` output.

## Status & links

- Proposed 2026-10-09.
