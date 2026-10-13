# triage-kit

Decoupled, model-agnostic **badcase triage & task quality check toolkit** for Harbor-ecosystem agent evaluation.

- **`triage analyze`** — post-evaluation triage of trial results: filter badcases (`--failing`), attribute each one against a rubric (reward hacking / task specification)
- **`triage check`** — pre-evaluation quality gate for task directories (11-criteria default rubric): single task or batch over a tasks root (`-j` concurrency, root-level summary)
- **`triage view`** — local **read-only** web view of the analyze diagnosis products: a trials overview (job aggregate + Reward filter) and a single-trial page split into five tabs (overview / score / trace / tool analysis / diagnosis)
- **`triage clean`** — restore evaluated directories by removing all `triage-kit/` product directories (dry-run by default)

triage-kit is an **independently runnable** toolkit powered by the Claude Agent SDK — reaching both Anthropic's own models and Anthropic-compatible endpoints (e.g. DeepSeek via `ANTHROPIC_BASE_URL`). Its prompt/rubric assets originate from the [Harbor framework](https://github.com/harbor-framework/harbor) (Apache-2.0, vendored byte-for-byte). Design document: [docs/DESIGN.md](docs/DESIGN.md).

## Quick start

```bash
# 1. install (from the repo root)
pip install -r requirements.txt   # or: pip install -e .

# 2. provide credentials
export ANTHROPIC_API_KEY=sk-ant-...        # Anthropic official
# — or, e.g. DeepSeek's Anthropic-compatible endpoint:
# export ANTHROPIC_API_KEY=sk-...
# export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic

# 3. run over a Harbor job directory (failing trials only)
triage analyze outputs/xxx/details --failing --model deepseek-flash

# 4. inspect the products
cat outputs/xxx/details/triage-kit/analysis.md   # overview (aggregated verdicts)

# 4b. or open them in the read-only web viewer (needs the [viewer] extra)
pip install -e '.[viewer]'
triage view outputs/xxx/details --port 8137       # overview page; click through to any trial

# 5. restore the evaluated directory when done
triage clean outputs/xxx/details         # dry-run: just list
triage clean outputs/xxx/details --yes   # actually delete
```

Use `--lang zh` to get `analysis.md` natively composed in Simplified Chinese (default `en` keeps the mechanical English rendering; `analysis.json` stays English either way).

For task quality inspection before running an evaluation:

```bash
# one task (task.toml required) — products in <task>/triage-kit/
triage check path/to/tasks/fix-the-bug --model deepseek-flash
cat path/to/tasks/fix-the-bug/triage-kit/check-result.md

# batch: check every task directory one level under the root
triage check path/to/tasks --model deepseek-flash -j 4
cat path/to/tasks/triage-kit/check-summary.json   # deterministic totals
```

## Installation

```bash
pip install -r requirements.txt   # one-click: runtime + dev + viewer
pip install -e .                  # runtime only
pip install -e '.[viewer]'        # + the optional viewer (fastapi/uvicorn/jinja2/markdown-it-py)
```

Requires Python 3.11+. The claude-agent-sdk dependency bundles the Claude Code CLI, so no separate Node/npm install is needed. The editable install keeps the `assets/` tree next to the package (see [docs/DESIGN.md](docs/DESIGN.md) for the packaging boundary). The viewer is an optional extra — `triage analyze`/`check`/`clean` work without it, and `triage view` prints the exact install command when the extra is missing.

## CLI reference

### `triage analyze <trial_dir | job_dir>`

| Option | Description |
|---|---|
| `--failing` | Job mode: analyze failing trials only |
| `--task-dir <path>` | Task directory override (the recorded task path may not exist on this machine) |
| `--rubric <file>` | Custom rubric file (default: `assets/analyze/analyze-rubric.toml`) |
| `--backend claude` | Backend selection (default: `claude`; more backends planned) |
| `-m, --model <name>` | Model name (default: `haiku`; pass e.g. `deepseek-flash` when using `ANTHROPIC_BASE_URL`) |
| `-f, --force` | Re-analyze even if cached `triage-kit/analysis.json` exists (overwrites) |
| `--lang en\|zh` | Report language for `analysis.md` (default: `en`; `zh` = natively composed Chinese, `analysis.json` stays English) |
| `-j, --jobs <n>` | Concurrent trial analyses in job mode (default: `1` = sequential; single-trial analysis is never pooled) |
| `-v, --verbose` | Debug logging |

All products are written in place, into a `triage-kit/` subdirectory next to the analyzed data — the evaluated directories stay clean, and `triage clean` restores them:

```
<trial_dir>/triage-kit/          (also written at <job_dir>/ level)
├── analysis.json                machine-readable attribution (always English)
├── analysis.md                  human-readable rendering (language follows --lang)
├── analysis.meta.json           cache-identity sidecar (rubric sha + model)
└── run.log                      execution log of the run (always DEBUG, overwritten per run)
```

### `triage check <task_dir | tasks_root>`

Single task (the argument contains `task.toml`) or batch (every task directory one level under the argument; a one-level scan, no `--recursive`).

| Option | Description |
|---|---|
| `-r, --rubric <file\|family>` | Rubric file path or family name (default: `check-default`) |
| `--backend claude` | Backend selection (default: `claude`; more backends planned) |
| `-m, --model <name>` | Model name (default: `sonnet`; pass e.g. `deepseek-flash` when using `ANTHROPIC_BASE_URL`) |
| `-f, --force` | Re-check even if cached `triage-kit/check-result.json` exists (overwrites) |
| `--lang en\|zh` | Report language for `check-result.md` (default: `en`; `zh` = natively composed Chinese, `check-result.json` stays English) |
| `-j, --jobs <n>` | Concurrent task checks in batch mode (default: `1` = sequential; single-task check is never pooled) |
| `-v, --verbose` | Debug logging |

Products (all in place, in `triage-kit/` subdirectories):

```
<task_dir>/triage-kit/
├── check-result.json             machine-readable verdict (always English)
├── check-result.md               human-readable rendering (language follows --lang)
├── check-result.meta.json        cache-identity sidecar (rubric sha + model)
└── run.log                       execution log (single-task mode)

<tasks_root>/triage-kit/          (batch mode)
├── check-summary.json            deterministic totals: total/checked/cached/failed,
│                                 per_criterion pass/fail/not_applicable, failed_tasks
└── run.log                       execution log ([task_name]-prefixed under -j)
```

Batch mode folds failures instead of aborting: a failed task is reported with an ERROR log line and lands in `failed_tasks`; sibling tasks continue and their products persist normally. The summary is pure mechanical counting — zero LLM calls.

### `triage view <trial_dir | job_dir>`

Local **read-only** web viewer for the analyze diagnosis products. Zero build: a FastAPI + Jinja2 server renders HTML server-side (no npm/bun/vite) and there is no write path — judging always stays in the CLI.

| Option | Description |
|---|---|
| `--host <addr>` | Bind host (default: `127.0.0.1`) |
| `-p, --port <n>` | Bind port (default: `8000`) |

Two shapes mirror `triage analyze`: a **trials root** serves an overview page (`/`) — summary KPI cards + the job-level aggregate `analysis.md` + a trials table with an independent server-side **Reward filter** row (ALL / Resolved / Unresolved, `?reward=1|0`, anchored at `#trials` so filtering never jumps to the top) — and each row links to a single-trial page (`/trial/<name>`); a **single trial** renders that trial page directly at `/`. The left nav always lists every trial, independent of the table filter.

Each trial page is split into five server-rendered tabs (state carried in `?tab=`): **overview** (outcome/tokens/cost KPIs, phase timing, artifacts), **score** (dynamic reward breakdown + verifier CTRF case list + exception), **trace** (per-step trajectory, with token bars deep-linking to a step), **tools** (aggregated tool-call stats + per-call detail), and **diagnosis** (that trial's `analysis.md`). The diagnosis tab **degrades to a hint** when a directory has no `triage-kit/` products, so raw evaluation results can be passed straight in — the native tabs render either way.

Requires the `[viewer]` extra (`pip install -e '.[viewer]'`). The entry point is analyze (trials); a tasks directory is rejected with an explicit "check mode not yet supported" error (the check/tasks view is not implemented yet).

### `triage clean <path>`

| Option | Description |
|---|---|
| `-y, --yes` | Actually delete (default is a dry-run listing) |

Restores evaluated directories to their pre-triage state: recursively finds and removes every `triage-kit/` product directory under the given trial/job/task path. Dry-run by default — pass `--yes` to delete. Original evaluation data (`result.json`, `trajectory.json`, `task.toml`, ...) is never touched. A locked/forbidden target is reported by name and skipped (remaining targets are still removed; exit code 1 signals the partial failure).

### Single-item flows

The commands also accept single-item targets — useful for a quick look at one badcase or one task:

```bash
# one trial: analyze just this badcase (no job-level aggregation,
# no thread pool; products land in <trial_dir>/triage-kit/)
triage analyze outputs/xxx/details/some-trial__abc123 --model deepseek-flash

# one task: check a single task directory (task.toml required)
triage check path/to/tasks/fix-the-bug --model deepseek-flash

# one trial: view just this trial's page
triage view outputs/xxx/details/some-trial__abc123
```

Single-trial analysis produces trial-level products only; the job-level aggregation summary is not generated.

### Backends

**claude** — the Claude Agent SDK backend (the tool loop, context management, and structured-output extraction all run inside the SDK's bundled Claude Code CLI). Endpoint override is via `ANTHROPIC_BASE_URL` — Anthropic-compatible endpoints work directly:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
triage analyze path/to/trial     # defaults to -m haiku
triage check path/to/task        # defaults to -m sonnet

# e.g. DeepSeek's Anthropic-compatible endpoint
export ANTHROPIC_API_KEY=sk-...
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
triage analyze path/to/job --failing -m deepseek-flash -j 8
```

A DeepSeek Harness SDK backend (P018) is planned; it will join `--backend` (see [Roadmap](#roadmap)).

**trae** — the hosting agent itself is the tool loop; a SKILL.md asset pack is on the roadmap.

### Caching

Both commands reuse cached products by default. A cache hit requires an identity match: the rubric sha256 and model recorded in the sidecar (`triage-kit/analysis.meta.json` / `triage-kit/check-result.meta.json`) must equal the current run's. On mismatch the command errors and points at `--force`; on `--force` it reruns and overwrites. Cached files are re-validated against the live response schema — a corrupted cache never flows into products silently.

## What the judge sees

Task/trial files are read as plain JSON in the Harbor-native layout (trial directories with `result.json`, task directories with `task.toml`), so results produced by standard Harbor jobs work out of the box.

The judge never sees its own prior verdicts on the check path: the `triage-kit/` products directory is excluded from the check file tree, so a `--force` re-check is an independent re-judgment. (On the analyze path the claude backend delegates tool execution to the SDK's CLI, which currently has no such deny-list — a known limitation.)

Judgment criteria live in data (TOML rubrics); output schemas are generated dynamically from them — extending evaluation dimensions requires zero code changes:

```
assets/                  pure-text assets, decoupled from code
├── analyze/             triage workflow
│   ├── analyze.txt          judge prompt template
│   ├── analyze-job.txt      job-level aggregation template
│   └── analyze-rubric.toml  default criteria
└── check/               task quality workflow
    ├── check.txt            judge prompt template
    └── rubrics/
        ├── check-default.toml   11 criteria
        └── KNOWN-ISSUES.md      documented rubric defects backlog
```

The five prompt/rubric files are frozen byte-for-byte against their upstream originals (guarded by sha256 snapshot tests) for asset provenance and diff-ability.

## Roadmap

Planned work is tracked in [ROADMAP.md](ROADMAP.md) — the single
source of truth. Larger items get a one-page design doc under
`docs/proposals/` before implementation.

## Development

```bash
pip install -r requirements.txt
pytest                    # 248 tests, no network access needed
```

The viewer tests use `fastapi.testclient` (part of the `dev` extra) and need the `viewer` extra installed.

## License

Apache-2.0. Prompt/rubric assets are derived from the [Harbor framework](https://github.com/harbor-framework/harbor); see [NOTICE](NOTICE).
