# P002 — deep-swe family rubric

Status: **proposed** · Type: feature · Priority: medium

## Background & motivation

Rubrics are organized per family under `assets/check/rubrics/`
(`check-default.toml` today; `check-deep-swe.toml` reserved by the
`-r <family>` naming convention). The default rubric was authored
against generic tasks; `assets/KNOWN-ISSUES.md` accumulates
rubric-quality badcases from real usage, and the deep-swe family
(dense multi-file patch tasks of the kind in the `details` sample
job) is expected to need family-specific criteria weighting.

## Goals

- Ship `assets/check/rubrics/check-deep-swe.toml`, loadable via
  `triage check <task_dir> -r deep-swe`, with criteria and guidance
  tuned from observed badcases.

## Non-goals

- No schema changes — family rubrics reuse the existing rubric
  format and response schema.
- No new check CLI options beyond the already-working `-r` resolution.

## Current state & gap

- `-r deep-swe` currently errors ("neither a file nor a known
  family") because the family file does not exist — the README
  documents this honestly as not yet implemented.
- `KNOWN-ISSUES.md` exists as the badcase backlog; its deep-swe
  entries are the input evidence.

## Design

**To be finalized when started** (Gate 1). Open questions: which
KNOWN-ISSUES entries are family-specific vs. general; whether new
criteria are needed or only reweighting/guidance edits; acceptance
bar (judge verdicts stable across the `details` trials).

## Compatibility impact

Additive asset. Frozen-asset sha256 guards do not cover new rubric
files; `test_assets.py` needs a row for the new file (non-frozen, but
listed). No product/cache/CLI changes.

## Verification plan

- TDD: rubric loading + `-r deep-swe` resolution tests.
- Live verification: check + analyze over the `details` job; verdicts
  reviewed against expectations before landing.

## Status & links

- Proposed; awaits scheduling.
