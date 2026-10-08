# triage-kit

Decoupled, model-agnostic **badcase triage & task quality check toolkit** for Harbor-ecosystem agent evaluation.

triage-kit is extracted from pier-ecosystem evaluation tooling (datacurve-pier, a Harbor fork). Its prompt/rubric assets originate from the [Harbor framework](https://github.com/harbor-framework/harbor) (Apache-2.0, vendored); the goal of this repo is to restore them to their Harbor-native form as an **independently runnable** toolkit:

- **analyze** — post-evaluation triage of trial results (badcase filtering + reward-hacking / task-specification attribution)
- **check** — pre-evaluation quality gate for tasks (11-criteria rubric, family-customizable)

**Status: design phase.** The design document ([docs/DESIGN.md](docs/DESIGN.md)) is the source of truth; the implementation plan lives in its "实施步骤" section. This repository currently ships the extracted assets and design docs only.

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
