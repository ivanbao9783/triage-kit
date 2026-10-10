# triage-kit

Decoupled, model-agnostic **badcase triage & task quality check toolkit** for Harbor-ecosystem agent evaluation.

- **`triage analyze`** — post-evaluation triage of trial results: filter badcases (`--failing`), attribute each one against a rubric (reward hacking / task specification)
- **`triage check`** — pre-evaluation quality gate for task directories (11-criteria default rubric)
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

# 5. restore the evaluated directory when done
triage clean outputs/xxx/details         # dry-run: just list
triage clean outputs/xxx/details --yes   # actually delete
```

Use `--lang zh` to get `analysis.md` natively composed in Simplified Chinese (default `en` keeps the mechanical English rendering; `analysis.json` stays English either way).

For task quality inspection before running an evaluation:

```bash
triage check path/to/tasks --model deepseek-flash
cat path/to/tasks/triage-kit/check-result.json
```

## Installation

```bash
pip install -r requirements.txt   # one-click: runtime + dev (pytest)
pip install -e .                  # runtime only
```

Requires Python 3.11+. The claude-agent-sdk dependency bundles the Claude Code CLI, so no separate Node/npm install is needed. The editable install keeps the `assets/` tree next to the package (see [docs/DESIGN.md](docs/DESIGN.md) for the packaging boundary).

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
└── analysis.meta.json           cache-identity sidecar (rubric sha + model)
```

### `triage check <task_dir>`

| Option | Description |
|---|---|
| `-r, --rubric <file\|family>` | Rubric file path or family name (default: `check-default`) |
| `--backend claude` | Backend selection (default: `claude`; more backends planned) |
| `-m, --model <name>` | Model name (default: `sonnet`; pass e.g. `deepseek-flash` when using `ANTHROPIC_BASE_URL`) |
| `-f, --force` | Re-check even if cached `triage-kit/check-result.json` exists (overwrites) |
| `-v, --verbose` | Debug logging |

Product: `triage-kit/check-result.json` (+ `check-result.meta.json` sidecar) in the task directory.

### `triage clean <path>`

| Option | Description |
|---|---|
| `-y, --yes` | Actually delete (default is a dry-run listing) |

Restores evaluated directories to their pre-triage state: recursively finds and removes every `triage-kit/` product directory under the given trial/job/task path. Dry-run by default — pass `--yes` to delete. Original evaluation data (`result.json`, `trajectory.json`, `task.toml`, ...) is never touched. A locked/forbidden target is reported by name and skipped (remaining targets are still removed; exit code 1 signals the partial failure).

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

More backends (codex SDK, DeepSeek harness SDK) are planned; they will join `--backend` (see [Roadmap](#roadmap)).

**trae** — the hosting agent itself is the tool loop; a SKILL.md asset pack is on the roadmap.

### Caching

Both commands reuse cached products by default. A cache hit requires an identity match: the rubric sha256 and model recorded in the sidecar (`triage-kit/analysis.meta.json` / `triage-kit/check-result.meta.json`) must equal the current run's. On mismatch the command errors and points at `--force`; on `--force` it reruns and overwrites. Cached files are re-validated against the live response schema — a corrupted cache never flows into products silently.

## What the judge sees

Task/trial files are read as plain JSON in the Harbor-native layout (trial directories with `result.json`, task directories with `task.toml`), so results produced by standard Harbor jobs work out of the box.

The judge never sees its own prior verdicts on the check path: the `triage-kit/` products directory is excluded from the check file tree, so a `--force` re-check is an independent re-judgment. (On the analyze path the claude backend delegates tool execution to the SDK's CLI, which currently has no such deny-list — a known gap tracked as P013 in the roadmap.)

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
source of truth. Each entry has a one-page design doc under
`docs/proposals/`; code starts only after the doc passes its
pre-development gate.

## Development

```bash
pip install -r requirements.txt
pytest                    # 127 tests, no network access needed
```

## License

Apache-2.0. Prompt/rubric assets are derived from the [Harbor framework](https://github.com/harbor-framework/harbor); see [NOTICE](NOTICE).
