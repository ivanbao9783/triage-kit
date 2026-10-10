# P014 — check batch mode & human-readable products

Status: **proposed** · Type: feature · Priority: medium

## Background & motivation

The 2026-10-10 post-refactor audit compared the analyze and check
command surfaces. Two gaps surfaced, both on the check side:

1. **No batch mode**: `triage check` accepts exactly one task
   directory. Analyze has a single-trial form *and* a job form with
   `-j` concurrency (P003); check has only the single-task form.
   Pre-launch quality gates over a real dataset (e.g. 100+ tasks
   under `deep-swe/tasks/`) would run strictly sequentially.
2. **No human-readable product**: check writes
   `check-result.json` only. Analyze renders `analysis.md`
   (mechanical for `--lang en`, natively composed for `--lang zh`,
   P009 route B); check has neither. Note pier's native check also
   produces JSON only (console Rich table, optional `-o` file) —
   triage-kit already exceeds it with auto-persisted products +
   run.log (P011), so this is a product-completeness gap, not a
   regression.

## Goals

- `triage check <tasks_root>` batch mode: scan subdirectories for
  valid task dirs, check them with `-j` concurrency (P003 pool
  pattern), per-task products in place.
- `check-result.md` human-readable rendering on every check path:
  mechanical table rendering for `--lang en`; natively composed
  Chinese for `--lang zh` (reusing the P009 compose mechanism).
- `--lang` option on check, semantics identical to analyze
  (`en` default; `zh` composes natively; JSON stays English).

## Non-goals

- No change to the frozen prompt/rubric assets
  (`check.txt`, rubric TOMLs stay byte-frozen).
- No schema change to `check-result.json` (product stability).
- No job-level aggregation across tasks (check results are
  per-task; a cross-task roll-up, if wanted, is future work and
  gets its own entry).

## Current state & gap

- `Checker.check_task` operates on one task dir; CLI `check`
  command takes one path argument (single form only).
- `check-result.json` + sidecar + `run.log` land per task — the
  products layout already supports per-task placement, so batch
  mode is an orchestration gap only.
- No `--lang`, no md rendering anywhere on the check path.

## Design

**To be finalized at Gate 1.** Candidate shape:

- **Batch detection**: if the CLI argument is not itself a valid
  task dir, scan it for child task dirs (a `tasks/` root or any
  directory of task dirs); if none found, fail with the current
  error. Single-task and batch share one command (analyze's
  trial/job dual-form precedent).
- **Concurrency**: reuse the P003 pattern —
  `ThreadPoolExecutor(max_workers=j)` around a `_check_one`
  worker that never raises (returns `(name, result, exc)`),
  results folded in listing order; `[task_name]` log prefixes via
  the existing contextvar + LogRecord factory.
- **Run log**: batch mode lands one `run.log` at the root
  argument dir (analyze job-mode precedent); single-task mode
  keeps the current per-task log.
- **md rendering**: `_render_check_md` (mechanical, en) mirroring
  `_render_analysis_md`; zh via a `_ZH_CHECK_COMPOSE` instruction
  (payload = check-result JSON, same rules block as P009).
- **Cache**: per-task cache identity unchanged; cache hits skip
  the compose hop (P009 decision (i) precedent — `--force`
  regenerates).

Open questions for Gate 1: recursive vs one-level task scan (or
`--recursive` flag); whether batch mode also writes a root-level
summary listing pass/fail counts (light, no LLM) or strictly
per-task products.

## Compatibility impact

- Additive: `check` gains a batch form and two options (`-j`,
  `--lang`); single-task behavior and products unchanged.
- New product file `check-result.md` next to `check-result.json`
  (in-place, `triage clean` covers it).

## Verification plan

- TDD for batch orchestration (pool, ordering, failure folding,
  log prefixes) and md rendering (en mechanical / zh compose /
  cache-hit skip).
- Live verification on `deep-swe/tasks/` (batch, small `-j`) and
  one single task, folded into the next unified E2E run.

## Status & links

- Proposed 2026-10-10 (post-refactor audit: batch gap + readable
  product gap; pier-native check has neither). Related: P003
  (pool pattern), P009 (compose mechanism, `--lang` semantics),
  P011 (run.log conventions).
