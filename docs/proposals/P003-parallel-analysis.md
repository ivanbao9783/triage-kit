# P003 — Parallel trial analysis (`-j/--jobs`)

Status: **proposed** · Type: optimization · Priority: high

## Background & motivation

`Analyzer.analyze_job` processes trials in a strictly sequential
synchronous for-loop (no asyncio, threads, or pools anywhere in the
package). Real-endpoint E2E measured ~1 min/trial (deepseek-flash,
~10 tool-loop rounds). A 113-trial job therefore costs ~2h of wall
clock while the CPU sits nearly idle — LLM judging is I/O-wait, the
ideal workload for concurrency.

## Goals

- `triage analyze <job_dir> -j N` (default 1 = current behavior):
  run per-trial analysis through a bounded thread pool, preserving
  all current semantics (products, cache, failure isolation).

## Non-goals

- No asyncio rewrite — a thread pool matches the sync codebase.
- No cross-job or cross-machine parallelism.
- No rate-limit scheduler — API 429 handling stays manual (user
  lowers `-j`).

## Current state & gap

- Loop body is already dependency-free: each trial owns its
  directory, cache identity, and LLM session; `failed_trials`
  aggregation and the job-level product write happen after the loop.
- Missing: the pool itself, per-trial log prefixing (interleaved
  logs must stay attributable), and a guard so job-level aggregation
  and translation still run exactly once, after all trials.

## Design

Direction agreed in discussion; details finalized at Gate 1:
`ThreadPoolExecutor(max_workers=j)` around `analyze_trial`,
results collected then aggregated (no shared-state locking needed if
aggregation is post-join). Log lines gain a trial-name prefix.
Empty-selection short-circuit and `--lang zh` translation hop run
unchanged after the join.

## Compatibility impact

- CLI: new `-j/--jobs` option (additive, default preserves behavior).
- Products/cache: unchanged — per-trial writes are already isolated
  by directory.
- Tests: existing sequential tests must pass unmodified at `-j 1`;
  new tests cover ordering-independence and failure isolation under
  concurrency.

## Verification plan

- TDD: concurrent run with a fake backend (barrier-synchronized to
  prove overlap), single-trial failure does not poison siblings,
  `-j 1` bit-for-bit equivalent to today.
- Live verification: re-run the 113-trial-scale job (or `details`
  doubled) at `-j 8`, compare products with the sequential run.

## Status & links

- Proposed; motivation data from the 2026-10 real-endpoint E2E.
