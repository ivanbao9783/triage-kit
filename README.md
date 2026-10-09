# triage-kit

Decoupled, model-agnostic **badcase triage & task quality check toolkit** for Harbor-ecosystem agent evaluation.

triage-kit is extracted from [pier](https://github.com/datacurve-ai/pier)-ecosystem evaluation tooling. Its prompt/rubric assets originate from the [Harbor framework](https://github.com/harbor-framework/harbor) (Apache-2.0, vendored); the goal of this repo is to restore them to their Harbor-native form as an **independently runnable** toolkit:

- **analyze** — post-evaluation triage of trial results (badcase filtering + reward-hacking / task-specification attribution)
- **check** — pre-evaluation quality gate for tasks (11-criteria rubric, family-customizable)

**Status: implemented (M1–M7).** Core chain is complete and E2E-verified (117 tests): contract → rubric-driven schema → general/claude harnesses → CLI. The trae SKILL.md asset pack (M8) is in progress. Design document: [docs/DESIGN.md](docs/DESIGN.md).

## Installation

```bash
pip install -e ".[general]"   # OpenAI-compatible backends (GLM / DeepSeek / Qwen / ...)
pip install -e ".[claude]"    # Claude Agent SDK backend
pip install -e ".[dev]"       # run the test suite
```

## Usage

### general backend (any OpenAI-compatible endpoint)

```bash
export OPENAI_API_KEY=...                       # or your provider's key
export OPENAI_BASE_URL=https://api.deepseek.com/v1   # optional, non-default endpoint

# badcase attribution over a trial (or a whole job dir)
triage analyze outputs/job/details --failing \
    --backend general --model glm-4.7

# task quality gate (11-criteria default rubric)
triage check deep-swe/tasks/ts-pattern-match-each \
    --backend general --model glm-4.7
```

Notes: `-m/--model` is **required** for `--backend general` (no sane default across endpoints). `--base-url` overrides the endpoint; the target host is auto-exempted from system proxies.

### claude backend (reference implementation, pier-compatible defaults)

```bash
export ANTHROPIC_API_KEY=sk-ant-...

triage analyze outputs/job/details      # defaults to -m haiku (pier parity)
triage check path/to/task               # defaults to -m sonnet (pier parity)
```

### trae harness

Not a CLI option: the hosting agent itself is the tool loop. A SKILL.md asset pack (M8) directs it to run the same workflows with the same assets and product formats.

## Why

1. The original tooling hard-binds to `claude_agent_sdk` + `ANTHROPIC_API_KEY`. triage-kit defines an agent-granularity backend contract (`query_agent -> (result, meta)`) with pluggable harnesses:
   - **general harness** — self-built read-only tool loop over any OpenAI-compatible LLM (GLM / DeepSeek / Qwen / ...)
   - **trae harness** — executed by a hosting agent harness via a SKILL.md asset pack
   - **claude SDK** — retained as a reference implementation
2. Task/trial files are read as plain JSON (Harbor-native layout), so results produced by standard Harbor jobs work out of the box.

## Repository layout

```
assets/                  pure-text assets, fully decoupled from code
├── analyze/             triage workflow
│   ├── analyze.txt        judge prompt template ({task_section} {criteria_guidance})
│   ├── analyze-rubric.toml  default criteria: reward_hacking / task_specification
│   └── analyze-job.txt    job-level aggregation template ({trial_results})
└── check/               task quality workflow
    ├── check.txt          judge prompt template ({file_tree} {criteria_guidance})
    └── rubrics/
        ├── check-default.toml  11 criteria (bidirectional completeness / anti-cheating / reproducibility / hygiene)
        ├── KNOWN-ISSUES.md    documented rubric defects backlog (real-badcase driven fixes)
        └── check-deep-swe.toml  (planned) family rubric for DeepSWE-style datasets
docs/
└── DESIGN.md            full design document (decisions, architecture, roadmap)
```

Core design philosophy (inherited from the original): **judgment criteria live in data (rubrics), and output schemas are generated dynamically from them** — extending evaluation dimensions requires zero code changes.

## License

Apache-2.0. Prompt/rubric assets are derived from the [Harbor framework](https://github.com/harbor-framework/harbor) (vendored via pier); see [NOTICE](NOTICE).
