# P003 — Parallel trial analysis (`-j/--jobs`)

Status: **building** (Gate 1 passed 2026-10-09) · Type: optimization · Priority: high

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

Direction agreed in discussion; the subsections below are the Gate 1
finalization.

### Execution frame

- `Analyzer.__init__` gains `jobs: int = 1`; `analyze_job` routes every
  trial through `ThreadPoolExecutor(max_workers=jobs)` — including
  `-j 1`. A single FIFO worker preserves submission order, so one code
  path serves both modes and the entire existing suite doubles as the
  `-j 1` equivalence test (no `j == 1` special-case branch to maintain).
- The worker wrapper never raises: it returns
  `(trial_name, analysis | None, exception | None)` per trial.
- Post-join, results fold in `list_trials` listing order, so
  `trial_results` / `failed_trials` in the job product keep today's
  order regardless of completion order — the aggregation prompt and all
  products are then j-invariant (same trial set ⇒ byte-identical job
  product for any `j`).
- Empty-selection short-circuit, job-level aggregation, and the
  `--lang zh` translation hop run unchanged after the join; per-trial
  translations stay inside the worker (per-trial isolation already
  holds: each worker owns its directory and cache identity).
- CLI: `-j/--jobs` on `triage analyze` only (`check` is single-task);
  values < 1 are rejected at the CLI boundary. Single-trial direct
  `analyze_trial` is untouched (no pool, no prefix).

### Log prefix (attributability)

The bulk of `--verbose` output is emitted from inside the harnesses
(per-turn tool logs in general, start/done lines in both), where no
trial context exists. Prefixing at the call site would require an
`AgentBackend` contract change. Instead:

- A module-level `contextvars.ContextVar` holds the current trial name.
  Each worker sets it at entry; contextvars are inherently per-thread,
  so workers cannot see each other's value and no propagation is
  needed.
- A `logging` record factory (installed via
  `logging.setLogRecordFactory` at CLI startup, idempotent) rewrites
  `record.msg` to `[trial_name] <msg>` for records from `triage_kit.*`
  loggers when the contextvar is set. Record factories run at record
  creation, so the prefix is visible to any handler (including
  `logging.lastResort` and pytest's caplog) — this supersedes the
  handler-side Filter sketched before implementation.
- Scope: the prefix is active in job mode for all `j` (uniform code
  path) — log format at `-j 1` therefore changes slightly, products are
  unaffected. Direct single-trial analysis stays unprefixed (no
  ambiguity to resolve).

### Exception collection

- Today a trial exception is swallowed silently (append to
  `failed_trials`, no log). Under concurrency that is unacceptable —
  a failed or hung trial must be attributable from the console.
- The worker wrapper catches `Exception` (not `BaseException`); after
  the join, each failure logs one line at ERROR
  (`[trial] analysis failed: <ExcType>: <msg>`) with the full traceback
  at DEBUG (`--verbose`).
- Product surface unchanged: `failed_trials` remains a plain list of
  names (schema stability); command exit semantics unchanged.

### Test fakes (`make_backend_seq` adaptation)

- At `-j 1` the unified pool is a single FIFO worker ⇒ call order ==
  listing order ⇒ deterministic. `make_backend_seq` and every existing
  test pass **unmodified** — the ordering contract is exactly the
  `-j 1` equivalence guarantee; no rewrite needed.
- New `-j > 1` tests need order-independent fakes, added to
  `tests/conftest.py` (fake-centralization convention):
  - `make_backend_keyed(mapping)` — `query_agent` dispatches on
    `Path(cwd).name`; `query` dispatches on prompt shape (leading
    "Translate…" vs aggregation).
  - `BarrierBackend(n)` — `query_agent` blocks on
    `threading.Barrier(n)`; only genuinely overlapped execution lets
    all parties through (sequential execution breaks the barrier and
    the test fails).

### Thread-safety audit (prerequisite)

- general: `openai.OpenAI` wraps an `httpx.Client`, which is
  thread-safe for concurrent requests.
- claude: each call runs `asyncio.run` on its own thread-local loop
  (no shared event loop) and the SDK spawns a fresh query per call; no
  shared mutable state. Flagged for live confirmation during E2E (not
  unit-testable).
- `Analyzer` fields are read-only after `__init__`; workers write only
  into their own `<trial>/triage-kit/` directory; `cache` helpers are
  stateless.

## Compatibility impact

- CLI: new `-j/--jobs` option (additive, default preserves behavior).
- Products/cache: unchanged — per-trial writes are already isolated
  by directory, and job-product ordering is pinned to listing order.
- Logs: job-mode lines gain a `[trial_name]` prefix at all `j`
  (console-only; products untouched).
- Tests: existing sequential tests must pass unmodified at `-j 1`;
  new tests cover overlap proof, failure isolation, and ordering
  stability under concurrency.

## Verification plan

- TDD (new tests, all fake-driven):
  - Overlap proof: `BarrierBackend(2)`, two trials, `jobs=2` — both
    analyses complete and products exist; a sequential (buggy)
    implementation breaks the barrier and fails the test.
  - Failure isolation under concurrency: keyed fake, one trial returns
    a schema-invalid response, sibling trial analyzed,
    `failed_trials == [bad]`, aggregation still runs.
  - Order stability: three trials with inverted artificial completion
    order at `jobs=4`; the product's `trials` list equals listing
    order.
  - CLI: `-j 0` rejected with a clear error; `-j 2` plumbed through.
- `-j 1` equivalence: the existing 161-test suite passes unmodified —
  the suite itself is the equivalence oracle.
- Live verification: re-run the 113-trial-scale job (or `details`
  doubled) at `-j 8`, compare products with the sequential run; check
  interleaved `--verbose` logs for per-trial attributability and
  confirm the claude SDK path under concurrency.

## Status & links

- Gate 1 passed 2026-10-09; implementation landed same day (TDD
  red→green, 9 new tests, full suite 170 green, existing tests
  unmodified — the `-j 1` equivalence oracle).
- Live E2E passed 2026-10-09 (deepseek-flash, 2-trial job, `-j 2
  --force --lang zh -v`): exit 0, all 11 products written, trial
  products landed 2s apart (true overlap), interleaved logs fully
  attributed via `[trial_name]` prefixes, verdicts identical to the
  sequential baseline, `failed_trials` empty.
- Implementation note: the log prefix uses
  `logging.setLogRecordFactory` instead of the originally documented
  handler-side Filter — record factories apply at record creation and
  are visible to any handler (including pytest caplog and
  logging.lastResort); semantics are unchanged.
- Motivation data from the 2026-10 real-endpoint E2E.
