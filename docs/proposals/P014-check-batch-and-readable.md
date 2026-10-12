# P014 — check batch mode & human-readable products

Status: **landed** (2026-10-12) · Type: feature · Priority: medium
(Gate 2 passed 2026-10-12: full P015 mini-dataset matrix, live
deepseek-flash. Batch check (-j 2, real verdicts incl. 1 fail + 2
not_applicable), cache rerun, single-task --force, per-task md
skeletons, summary + root run.log all verified. One fix landed from
the run: per_criterion now counts cached verdicts too — a resumed
CI rerun must not lose its statistics. Regression 162 green.)

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

**Gate 1 decisions (2026-10-12, user-confirmed D1–D4):**

- **D1 — Batch detection: single command, dual form; one-level
  scan, no `--recursive`.** If the CLI argument is itself a valid
  task dir (has `task.toml`), run the single-task form (current
  behavior unchanged). Otherwise scan its immediate
  subdirectories for task dirs (child contains `task.toml`); ≥1
  found → batch mode; 0 found → current "not a task dir" error.
  Mirrors analyze's trial/job dual form; nested task trees are
  YAGNI until they actually appear.
- **D2 — Root-level summary: yes, deterministic, zero LLM.**
  Batch mode writes `<root>/triage-kit/check-summary.json`:
  `total / checked / cached / failed`, `per_criterion`
  pass/fail/not_applicable counts, and `failed_tasks` names.
  Mechanical counting only — serves the CI-gate preference
  (deterministic, low-latency metrics); LLM aggregation across
  tasks, if ever wanted, is a separate future entry. Run log
  lands once at `<root>/triage-kit/run.log` (analyze job-mode
  precedent); single-task mode keeps the per-task log.
- **D3 — md skeleton mirrors `analysis.md`.** `# 任务质检：
  {task_name}` → one `## {criterion}: {outcome}` section per
  check with its explanation. `--lang` semantics identical to
  analyze: `en` (default) mechanically renders from JSON (zero
  LLM); `zh` runs a compose hop (`_ZH_COMPOSE_RULES` shared
  rules block + a `_ZH_CHECK_COMPOSE` skeleton instruction,
  payload = check-result JSON); JSON stays English; cache hits
  skip the compose hop (P009 decision (i) precedent).
- **D4 — Failure folding mirrors P003.** `_check_one` worker
  never raises (returns `(name, result, exc)`); results folded
  in directory-listing order regardless of completion order;
  `[task_name]` log prefixes via the existing contextvar +
  LogRecord factory; failed tasks get ERROR logs with task name
  + exception, land in `failed_tasks`, and never abort the
  batch — surviving tasks' products persist normally.

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
