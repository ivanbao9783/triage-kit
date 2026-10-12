# P015 — E2E mini dataset (fixed 3-task / 3-trial fixtures)

Status: **building** · Type: feature · Priority: medium
(Gate 1 passed 2026-10-12; D1–D3 user-confirmed. Dataset built +
runbook + 6 guard tests landed same day — full regression 162 green;
first live matrix run folds into the next unified E2E, closing
Gate 2 and flipping P014 with it.)

## Background & motivation

Every feature's Gate 2 (live verification) currently re-picks samples
ad hoc from the 113-task / 115-trial DeepSWE corpus. That is slow
(~47-trial runs take tens of minutes), not reproducible-comparable
across features, and makes single-point re-verification clumsy. A
**fixed mini fixtures set** turns E2E into a deterministic, cheap,
repeatable ritual: one run covers single-item forms, batch/job forms,
`-j` concurrency, summaries, `--lang`, cache hits, and `clean` —
roughly a dozen LLM calls, minutes of wall time.

Two-layer cadence: the mini set serves **every feature's Gate 2**;
full-corpus runs (e.g. the 113-trial badcase recovery) remain for
major-version closures. The mini set does not replace them.

## Goals

- A fixed, versioned 3-task + 3-trial dataset, checked into the repo,
  drawn from real DeepSWE evaluation artifacts (real trajectory shapes,
  real verifier reports — not the synthetic `make_task`/`make_trial`
  factories used by unit tests).
- A fixed E2E command matrix (runbook) that anyone can execute to
  reproduce the same verification, with expected outcomes per step.

## Non-goals

- No new CLI/code paths — this is test data + documentation only.
- No CI automation for E2E (hits real paid endpoints; stays manual).
- No full-corpus replacement (full runs still happen at major gates).

## Current state & gap

- Unit tests (156) run on synthetic fixtures via FakeBackend — zero
  network. They verify orchestration, not real-data shapes × real
  endpoints.
- Live E2E so far: ad-hoc sample picks per feature (3-trial P009
  verification, 47-trial claude-backend recovery, 2-case + 1-job
  unified run). No fixed inputs → results not comparable over time.

## Design

Measured against the local corpus (2026-10-12): 115 trials — 68
passing, 47 failing, 4 with `exception_info`.

**D1 — Sample selection: 3 task/trial pairs covering the pass, fail,
and exception attribution paths.**

| # | Task | Trial | Reward | Role |
|---|------|-------|--------|------|
| A | `abs-module-cache-flags` | `…__CuCWVBi` | 1 | pass attribution |
| B | `adaptix-name-mapping-aliases` | `…__ptkak5r` | 0 | normal badcase attribution |
| C | `boa-hierarchical-evaluation-cancellation` | `…__rWMKbsB` | 0 + exception | exception-path attribution |

All three tasks exist locally; A/B trials are ordinary, C carries
`exception_info` (degraded/exception evidence). With `--failing`, B+C
form the badcase subset (2 of 3) — `per_criterion` counters in
`check-summary.json` get non-trivial values from real verdicts.

**D2 — Storage: in-repo at `tests/e2e/data/`, slimmed.**

```
tests/e2e/
├── RUNBOOK.md            fixed command matrix + expected outcomes
└── data/
    ├── tasks/            3 task dirs (verbatim from deep-swe/tasks)
    └── job/              3 trial dirs (slimmed copies from details/)
```

Slimming rule: drop `mini-swe-agent.trajectory.json` /
`mini-swe-agent.txt` (raw agent-format duplicates of the canonical
`agent/trajectory.json`; 5.2/2.7/18.3 MB per trial) — everything else
copied verbatim, directory names unchanged (trial_name contract).
Measured total: **≈ 4.3 MB** (tasks 0.5 MB + trials 3.8 MB) vs ≈ 30 MB
verbatim. In-repo beats a non-repo location: E2E's whole point is
anyone/anytime reproducibility, and 4.3 MB is negligible. (Provenance
note: data is from our own DeepSWE × mini-swe-agent evaluation runs;
checking it into the public repo publishes the task content — DeepSWE
is a public benchmark built on open-source repos, so this is fine.)

**D3 — Run form: a fixed runbook, not a pytest suite.**

`tests/e2e/RUNBOOK.md` holds the exact command matrix below; each
feature's Gate 2 executes it (or the relevant subset) and records
outcomes. Fixed inputs + fixed commands = comparable results over
time. Default model: whatever the current primary endpoint provides
(e.g. `deepseek-flash` via `ANTHROPIC_BASE_URL`).

| # | Command | Verifies |
|---|---------|----------|
| 1 | `triage check data/tasks -j 2 -m <m>` | batch D1–D4: summary, per-task products, run.log at root |
| 2 | `triage check data/tasks/<A> -m <m>` | single-task form, check-result.md |
| 3 | rerun #1 | 3 cache hits, 0 LLM calls |
| 4 | `triage analyze data/job -m <m> -j 2` | job mode, aggregation, trial+job products |
| 5 | `triage analyze data/job --failing -m <m> -j 2 --lang zh` | badcase filter (B+C), zh reports |
| 6 | `triage analyze data/job/<A> -m <m> --task-dir data/tasks/<A>` | single trial + task-dir override (local-task path) |
| 7 | `triage clean data/…` (+ `--yes`) | dry-run listing, full restore |

Note: trial `config.json` records the original Linux task path, which
never resolves locally — so #4/#5 default to the degraded task section
(the documented main path), and #6 covers the `--task-dir` override.
Both analyze paths get real coverage. ≈ 12–14 LLM calls total.

## Compatibility impact

- Additive only: new files under `tests/e2e/`; no code, asset, or
  product changes. pytest must keep ignoring the directory (no test
  files there — the runbook is markdown, data is not collected).

## Verification plan

- Self-verifying: build the set, run the full matrix once, confirm
  every expected outcome in the runbook checklist.
- Guard: a unit test asserting the mini set exists with the exact
  3+3 directory names (cheap, prevents accidental deletion/renames —
  trial_name contract makes renames breaking).

## Status & links

- Proposed 2026-10-12. Related: P000 (Gate 2 definition), P014
  (batch + summary coverage in the matrix), P009 (`--lang` steps).
