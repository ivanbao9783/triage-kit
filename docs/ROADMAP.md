# Roadmap

Single source of truth for planned features and optimization work.
Each entry is tracked by a short design doc under `proposals/`
(one page max) — no code is written for an entry until its doc passes
Gate 1 (see `P000`).

Status values: `proposed` → `accepted` → `building` → `landed`, or
`dropped` (with the rejection reason kept in the doc).

| ID | Name | Type | Priority | Status | Doc |
|----|------|------|----------|--------|-----|
| P000 | Feature management process | process | high | landed | [P000-process.md](proposals/P000-process.md) |
| P001 | trae harness SKILL.md asset pack | feature | medium | proposed | [P001-skill-trae-harness.md](proposals/P001-skill-trae-harness.md) |
| P002 | deep-swe family rubric | feature | medium | proposed | [P002-deep-swe-rubric.md](proposals/P002-deep-swe-rubric.md) |
| P003 | Parallel trial analysis (`-j/--jobs`) | optimization | high | landed | [P003-parallel-analysis.md](proposals/P003-parallel-analysis.md) |
| P004 | Multi-step per-step check expansion | feature | low | proposed | [P004-multi-step-check.md](proposals/P004-multi-step-check.md) |
| P005 | Deterministic contract pre-check layer | feature | medium | proposed | [P005-contract-precheck.md](proposals/P005-contract-precheck.md) |
| P006 | Diagnosis results viewer | feature | medium | landed | [P006-diagnosis-viewer.md](proposals/P006-diagnosis-viewer.md) |
| P007 | Model identity in job aggregation | feature | low | proposed | [P007-model-identity.md](proposals/P007-model-identity.md) |
| P008 | Single-item flows: verification + documentation | docs | low | landed | [P008-single-item-flows-docs.md](proposals/P008-single-item-flows-docs.md) |
| P009 | Native Chinese reports (`--lang` selects `analysis.md` language) | optimization | medium | landed | [P009-native-zh-reports.md](proposals/P009-native-zh-reports.md) |
| P010 | Job aggregation summary quality | feature | medium | proposed | [P010-job-aggregation-quality.md](proposals/P010-job-aggregation-quality.md) |
| P011 | Run log persistence under triage-kit/ | feature | medium | landed | [P011-run-log-persistence.md](proposals/P011-run-log-persistence.md) |
| P012 | Claude Agent SDK backend as the primary (and only) harness | refactor | high | landed | [P012-claude-backend-primary.md](proposals/P012-claude-backend-primary.md) |
| P014 | check batch mode & human-readable products | feature | medium | landed | [P014-check-batch-and-readable.md](proposals/P014-check-batch-and-readable.md) |
| P015 | E2E mini dataset (fixed 3-task / 3-trial fixtures) | feature | medium | landed | [P015-e2e-mini-dataset.md](proposals/P015-e2e-mini-dataset.md) |
| P016 | Criteria matrix / heatmap (cross-trial × dimension) | feature | low | proposed | [P016-criteria-matrix.md](proposals/P016-criteria-matrix.md) |
| P018 | DeepSeek Harness SDK backend | feature | medium | proposed | [P018-deepseek-harness-sdk-backend.md](proposals/P018-deepseek-harness-sdk-backend.md) |
| P019 | Dependency lockfile (`uv.lock`) for reproducible installs | process | low | proposed | [P019-dependency-lockfile.md](proposals/P019-dependency-lockfile.md) |
