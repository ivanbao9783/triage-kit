# E2E Runbook — mini dataset (P015)

Fixed 3-task / 3-trial fixtures for live end-to-end verification.
Anyone, anytime, same inputs → comparable results. One full pass
≈ 12–14 LLM calls (minutes, not tens of minutes).

Dataset (see [P015](../../docs/proposals/P015-e2e-mini-dataset.md) for
selection rationale):

| # | Task (`data/tasks/`) | Trial (`data/trial_results/`) | Reward | Role |
|---|----------------------|---------------------|--------|------|
| A | `abs-module-cache-flags` | `abs-module-cache-flags__CuCWVBi` | 1 | pass attribution |
| B | `adaptix-name-mapping-aliases` | `adaptix-name-mapping-aliases__ptkak5r` | 0 | normal badcase |
| C | `boa-hierarchical-evaluation-cancellation` | `boa-hierarchical-evaluation-canc__rWMKbsB` | 0 + exception | exception path |

Trials are slimmed copies (raw `mini-swe-agent.*` duplicates dropped;
canonical `agent/trajectory.json` and all evidence kept verbatim).
Trial `config.json` records the original Linux task path — it never
resolves locally, so analyze defaults to the degraded task section
(the documented main path); step 6 covers the `--task-dir` override.

## Prerequisites

```bash
export ANTHROPIC_API_KEY=sk-...                              # endpoint key
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic  # or Anthropic official (omit)
```

Default model below: `deepseek-flash` (substitute as needed). Run
from the repo root.

Products are intentionally kept after a pass — they are the review
material for rubric/prompt quality and the input for the future
diagnosis viewer (P006). Only when you need a fresh live pass (no
cache hits) run `triage clean tests/e2e/data --yes` first, and note
it wipes the previous pass's products.

## Command matrix

### 1. Batch check — D1–D4, summary, concurrency

```bash
triage check tests/e2e/data/tasks -m deepseek-flash -j 2
```

Expected:
- exit 0; `data/tasks/triage-kit/check-summary.json` with
  `total=3, checked=3, cached=0, failed=0`, non-trivial
  `per_criterion` counts (real verdicts, not all-pass), empty
  `failed_tasks`
- per-task `triage-kit/check-result.{json,md,meta.json}` in each of
  the 3 task dirs; md skeleton `# Task Check: {task_name}`
- `data/tasks/triage-kit/run.log` exists, `[task_name]`-prefixed lines

### 2. Single-task check — dual form, md

```bash
triage check tests/e2e/data/tasks/abs-module-cache-flags -m deepseek-flash --force
```

Expected: exit 0; `check-result.md` regenerated (mechanical en
rendering, zero compose hop); `run.log` at the task level.

### 3. Cache-hit rerun — zero LLM

```bash
triage check tests/e2e/data/tasks -m deepseek-flash -j 2
```

Expected: exit 0; summary shows `cached=3, checked=0, failed=0`;
`run.log` contains 3 `cache hit` lines; wall time ≈ instant.

### 4. Job analyze — aggregation, concurrency

```bash
triage analyze tests/e2e/data/trial_results -m deepseek-flash -j 2
```

Expected:
- exit 0; 3 trial-level `triage-kit/analysis.{json,md,meta.json}`
- job-level `data/trial_results/triage-kit/analysis.json` (`summary` +
  3 trials) and `analysis.md` (`# Job Analysis`)
- job `run.log` with `[trial_name]` prefixes, 3 × `analysis finished`
- trial A (reward=1) judged; B and C attributed as badcases

### 5. Failing-only + Chinese reports — filter, compose

Cache identity is rubric + model (P009 decision (i)): **lang is not
part of it**. A plain rerun after step 4 therefore cache-hits every
failing trial and skips the zh compose entirely (only the uncached
job-level zh summary regenerates). To live-verify trial-level zh
composition, force the failing subset:

```bash
triage analyze tests/e2e/data/trial_results --failing --force -m deepseek-flash -j 2 --lang zh
```

Expected: exit 0; trials B + C re-analyzed; their `analysis.md` is
natively composed Chinese (not translationese; identifiers stay
English); JSON stays English; `analysis.zh.md` never appears;
job-level `analysis.md` regenerates as `# 作业级分析` (failing
subset: 0 / 2 passed). Trial A is excluded by `--failing` and keeps
its step-4 products.

### 6. Single trial + task-dir override — local-task path

Same cache semantics: add `--force` for live verification.

```bash
triage analyze tests/e2e/data/trial_results/abs-module-cache-flags__CuCWVBi -m deepseek-flash --task-dir tests/e2e/data/tasks/abs-module-cache-flags --force
```

Expected: exit 0; trial-level products only (no job aggregation);
the analysis references real task requirement details (evidence the
override fed the actual task files, not the degraded section);
`run.log` at the trial level.

## After the pass — products stay

All `triage-kit/` products remain under `tests/e2e/data/` after the
matrix completes. Use them to:

- **Review rubric & prompt quality** (deferred to the next E2E pass):
  suspicious verdicts in `check-result.json` → the criterion text in
  `check-rubric.toml`; attribution-vs-reward consistency in
  `analysis.json` → the prompt templates and `analyze-rubric.toml`.
- **Feed the diagnosis viewer** (P006): the product tree is exactly
  the viewer's input shape.

`triage clean` remains available as a standalone command for manual
cleanup when a fresh pass is needed (see Prerequisites).

## Recording results

For each feature's Gate 2, run the relevant subset (or full matrix)
and record: date, model, commands run, pass/fail per expected
outcome, anomalies. Keep it in the feature's proposal status line or
commit message.
