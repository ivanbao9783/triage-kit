# triage-kit

Decoupled, model-agnostic **badcase triage & task quality check toolkit** for Harbor-ecosystem agent evaluation.

- **`triage analyze`** — post-evaluation triage of trial results: filter badcases (`--failing`), attribute each one against a rubric (reward hacking / task specification)
- **`triage check`** — pre-evaluation quality gate for task directories (11-criteria default rubric)

triage-kit is extracted from the [pier](https://github.com/datacurve-ai/pier)-ecosystem evaluation tooling. Its prompt/rubric assets originate from the [Harbor framework](https://github.com/harbor-framework/harbor) (Apache-2.0, vendored byte-for-byte); this repo restores them as an **independently runnable** toolkit that works with any OpenAI-compatible endpoint or the Claude Agent SDK. Design document: [docs/DESIGN.md](docs/DESIGN.md).

## Quick start

```bash
# 1. install (editable, from the repo root)
pip install -e ".[general]"        # OpenAI-compatible backends (GLM / DeepSeek / Qwen / ...)

# 2. provide credentials for your endpoint
export OPENAI_API_KEY=...

# 3. run over a Harbor job directory (failing trials only)
triage analyze outputs/job/details --failing --backend general --model glm-4.7

# 4. inspect the products — written next to the trials
cat outputs/job/details/<trial>/analysis.md     # human-readable attribution
cat outputs/job/details/<trial>/analysis.json  # machine-readable (same schema)
```

For task quality inspection before running an evaluation:

```bash
triage check path/to/task --backend general --model glm-4.7
cat path/to/task/check-result.json
```

## Installation

```bash
pip install -e ".[general]"   # OpenAI-compatible backends
pip install -e ".[claude]"    # Claude Agent SDK backend
pip install -e ".[dev]"       # run the test suite (pytest)
```

Requires Python 3.11+. The editable install keeps the `assets/` tree next to the package (see [docs/DESIGN.md](docs/DESIGN.md) for the packaging boundary).

## CLI reference

### `triage analyze <trial_dir | job_dir>`

| Option | Description |
|---|---|
| `--failing` | Job mode: analyze failing trials only |
| `--task-dir <path>` | Task directory override (the recorded task path may not exist on this machine) |
| `--rubric <file>` | Custom rubric file (default: `assets/analyze/analyze-rubric.toml`) |
| `--backend general\|claude` | Backend selection (default: `general`) |
| `-m, --model <name>` | Model name — **required for `general`** |
| `--base-url <url>` | OpenAI-compatible endpoint override — `general` only |
| `-f, --force` | Re-analyze even if cached `analysis.json` exists (overwrites) |
| `-v, --verbose` | Debug logging |

Products are written into each trial directory (`analysis.json` + `analysis.md`) and the job directory (aggregated `analysis.json` + `analysis.md`).

### `triage check <task_dir>`

| Option | Description |
|---|---|
| `-r, --rubric <file\|family>` | Rubric file path or family name (default: `check-default`) |
| `--backend general\|claude` | Backend selection (default: `general`) |
| `-m, --model <name>` | Model name — **required for `general`** |
| `--base-url <url>` | OpenAI-compatible endpoint override — `general` only |
| `-f, --force` | Re-check even if cached `check-result.json` exists (overwrites) |
| `-v, --verbose` | Debug logging |

Product: `check-result.json` in the task directory.

### Backends

**general** — self-built read-only tool loop (`read_file` / `glob` / `grep` + final-tool submission) over any OpenAI-compatible endpoint. `-m/--model` is required (no sane default across endpoints). `--base-url` overrides the endpoint; the target host is auto-exempted from system proxies.

**claude** — Claude Agent SDK, retained as the pier-compatible reference implementation:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
triage analyze path/to/trial     # defaults to -m haiku (pier parity)
triage check path/to/task        # defaults to -m sonnet (pier parity)
```

`--base-url` is rejected for this backend (set `ANTHROPIC_BASE_URL` instead).

**trae** — the hosting agent itself is the tool loop; a SKILL.md asset pack is on the roadmap (see [Roadmap](#roadmap)).

### Caching

Both commands reuse cached products by default. A cache hit requires an identity match: the rubric sha256 and model recorded in the sidecar (`analysis.meta.json` / `check-result.meta.json`) must equal the current run's. On mismatch the command errors and points at `--force`; on `--force` it reruns and overwrites. Cached files are re-validated against the live response schema — a corrupted cache never flows into products silently.

## What the judge sees

Task/trial files are read as plain JSON in the Harbor-native layout (trial directories with `result.json`, task directories with `task.toml`), so results produced by standard Harbor jobs work out of the box.

Judgment criteria live in data (TOML rubrics); output schemas are generated dynamically from them — extending evaluation dimensions requires zero code changes:

```
assets/                  pure-text assets, decoupled from code
├── analyze/             triage workflow
│   ├── analyze.txt          judge prompt template ({task_section} {criteria_guidance})
│   ├── analyze-job.txt      job-level aggregation template ({trial_results})
│   └── analyze-rubric.toml  default criteria: reward_hacking / task_specification
└── check/               task quality workflow
    ├── check.txt            judge prompt template ({file_tree} {criteria_guidance})
    └── rubrics/
        ├── check-default.toml   11 criteria (completeness / anti-cheating / reproducibility / hygiene)
        └── KNOWN-ISSUES.md      documented rubric defects backlog (real-badcase driven)
```

The five prompt/rubric files are frozen byte-for-byte against their pier originals (guarded by sha256 snapshot tests) for pier-viewer product compatibility.

## Roadmap

- trae harness SKILL.md asset pack (M8)
- family rubrics (e.g. `deep-swe`) shipped under `assets/check/rubrics/`
- real-endpoint E2E (mock-endpoint E2E is already in the test suite)

## Development

```bash
pip install -e ".[dev]"
pytest                    # 144 tests, no network access needed
```

## License

Apache-2.0. Prompt/rubric assets are derived from the [Harbor framework](https://github.com/harbor-framework/harbor) (vendored via pier); see [NOTICE](NOTICE).
