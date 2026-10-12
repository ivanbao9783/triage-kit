# P006 — Diagnosis results viewer

Status: **accepted** (2026-10-12) · Type: feature · Priority: medium

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

- `triage view <dir>`: a local read-only web UI for **analyze**
  diagnosis results — an overview page (job aggregate `analysis.md` +
  a trials list with a Reward filter) and a single-trial page (native
  evaluation blocks + that trial's `analysis.md`). Since
  `analysis.md` already follows `--lang` (P009 route B), zh/en render
  as stored — there is no parallel `.zh.md`.
- Scanner layer: plain-JSON discovery of `triage-kit/` product
  directories, zero upstream model dependencies.
- Works on raw evaluation results too: the diagnosis sections degrade
  to empty when no `triage-kit/` products are present.

**Deferred (same feature, a later landing):** the parallel **check** /
tasks entry (task list + single-task page from `check-result.*`). The
endpoint is designed but not shipped here.

## Non-goals

- No wholesale reimplementation: the upstream viewer spans full
  evaluation lifecycle (jobs, models, pricing, critique heatmaps);
  triage-kit's viewer scopes to **diagnosis results** (analyze/check
  products) only.
- No remote/hosted deployment — local read-only viewing.
- No write path: the viewer never regenerates products (the upstream
  viewer has embedded summarize triggers; we keep judging in the CLI).
- This landing excludes: the check/tasks mode, heatmap / criteria
  matrix, structured checks tables, and the trajectory timeline.

## Current state & gap

- Products exist with a stable schema and sidecar identity; no
  visualization at all.
- Reference: the upstream viewer (FastAPI server + scanners +
  bun-built frontend) — architecture is proven, the read layout
  differs.

## Design

**Gate 1 decisions (2026-10-12, user-confirmed D1–D8):**

- **D1 — Form: FastAPI + Jinja2 server-side rendering, zero build.**
  No bun/npm/vite; HTML is assembled on the server and the browser
  receives only HTML/CSS. Avoids inheriting the upstream viewer's
  24k-line TS toolchain, and matches the toolkit's "runs standalone"
  character. Dependencies: `fastapi` / `uvicorn` / `jinja2` /
  `markdown-it-py`.
- **D2 — Dependency placement: optional extra `[viewer]`.** CLI-only
  users (analyze/check/clean) are unaffected; `triage view` fails
  with a `pip install 'triage-kit[viewer]'` hint when the extra is
  missing. `httpx` joins the `dev` extra for TestClient.
- **D3 — Command: `triage view <dir> [--host --port]`, read-only,
  dual form (mirrors analyze).** `<dir>` is a trials-root or a single
  trial. No write path — no summarize/generate button; judging stays
  in the CLI.
- **D4 — Mode routing: trials → analyze; tasks → check; mutually
  exclusive.** This landing implements analyze/trials only. A tasks
  directory is rejected with an explicit "check mode not yet
  supported" error rather than silently mixed.
- **D5 — Rendering: markdown-first.** The overview renders the job
  aggregate `analysis.md`; a single-trial page renders that trial's
  `analysis.md`. No structured checks tables yet — left to a UI
  optimization pass. Markdown tables must be enabled
  (`MarkdownIt("commonmark").enable(["table","strikethrough"])`).
- **D6 — Degradation: native-first, diagnosis optional.** The input
  may be raw evaluation results (no `triage-kit/`); the overview and
  the diagnosis section then show a "no diagnosis products" notice
  while every native block still renders. Products present → the
  diagnosis renders automatically.
- **D7 — Scanner: reuse primitives + new module.** New additive
  `triage_kit/viewer/`. Mode detection reuses
  `trial_reader.is_trial_dir/is_job_dir/list_trials`; tasks detection
  reuses `task_reader.is_task_dir/list_task_dirs`. Product reads are
  plain JSON — zero upstream model dependencies.
- **D8 — Overview trials list: Reward filter.** Server-side query
  param (`/?reward=1|0`), zero JS, with count badges.

**Language.** CLI help/errors keep the existing English style of
`cli.py`; template-visible labels follow the accepted prototype
(Chinese). No language logic in the viewer — `analysis.md` already
follows `--lang`, so it renders as stored.

## Compatibility impact

- Additive new module (`triage_kit/viewer/` + CLI command); reads
  products, never writes — no impact on cache or products.
- New dependency surface: an optional `[viewer]` extra
  (fastapi/uvicorn/jinja2/markdown-it-py) — the claude backend and
  the core CLI are unaffected.

## Verification plan

- TDD for scanner logic (product discovery, missing-file tolerance).
- Live verification: serve the `details` sample job (2 trials, real
  products) + one checked task; assert rendered content against the
  JSON products.

## Status & links

- Proposed 2026-10-09. Gate 1 accepted 2026-10-12 (user-confirmed
  D1–D8; validated by a zero-build prototype against real products).
  Reference: the upstream evaluation framework's viewer module
  (FastAPI server, task_scanner, bun-built frontend).
