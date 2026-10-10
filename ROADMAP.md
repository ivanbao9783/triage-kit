# Roadmap

Single source of truth for planned features and optimization work.
Each entry is tracked by a short design doc under `docs/proposals/`
(one page max) — no code is written for an entry until its doc passes
Gate 1 (see `P000`).

Status values: `proposed` → `accepted` → `building` → `landed`, or
`dropped` (with the rejection reason kept in the doc).

| ID | Name | Type | Priority | Status | Doc |
|----|------|------|----------|--------|-----|
| P000 | Feature management process | process | high | landed | [P000-process.md](docs/proposals/P000-process.md) |
| P001 | trae harness SKILL.md asset pack | feature | medium | proposed | [P001-skill-trae-harness.md](docs/proposals/P001-skill-trae-harness.md) |
| P002 | deep-swe family rubric | feature | medium | proposed | [P002-deep-swe-rubric.md](docs/proposals/P002-deep-swe-rubric.md) |
| P003 | Parallel trial analysis (`-j/--jobs`) | optimization | high | landed | [P003-parallel-analysis.md](docs/proposals/P003-parallel-analysis.md) |
| P004 | Multi-step per-step check expansion | feature | low | proposed | [P004-multi-step-check.md](docs/proposals/P004-multi-step-check.md) |
| P005 | Deterministic contract pre-check layer | feature | medium | proposed | [P005-contract-precheck.md](docs/proposals/P005-contract-precheck.md) |
| P006 | Diagnosis results viewer | feature | medium | proposed | [P006-diagnosis-viewer.md](docs/proposals/P006-diagnosis-viewer.md) |
| P007 | Model identity in job aggregation | feature | low | proposed | [P007-model-identity.md](docs/proposals/P007-model-identity.md) |
| P008 | Single-item flows: verification + documentation | docs | low | landed | [P008-single-item-flows-docs.md](docs/proposals/P008-single-item-flows-docs.md) |
| P009 | Native Chinese reports (`--lang` selects `analysis.md` language) | optimization | medium | landed | [P009-native-zh-reports.md](docs/proposals/P009-native-zh-reports.md) |
| P010 | Job aggregation summary quality | feature | medium | proposed | [P010-job-aggregation-quality.md](docs/proposals/P010-job-aggregation-quality.md) |
| P011 | Run log persistence under triage-kit/ | feature | medium | landed | [P011-run-log-persistence.md](docs/proposals/P011-run-log-persistence.md) |
| P012 | Claude Agent SDK backend as the primary (and only) harness | refactor | high | landed | [P012-claude-backend-primary.md](docs/proposals/P012-claude-backend-primary.md) |
| P013 | Judge sandbox gap on the claude backend path | feature | medium | proposed | [P013-judge-sandbox-claude-path.md](docs/proposals/P013-judge-sandbox-claude-path.md) |
| P014 | check batch mode & human-readable products | feature | medium | proposed | [P014-check-batch-and-readable.md](docs/proposals/P014-check-batch-and-readable.md) |
