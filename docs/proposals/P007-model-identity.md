# P007 — Model identity in job aggregation

Status: **proposed** · Type: feature · Priority: low

## Background & motivation

The job-level aggregation prompt (analyze-job.txt, point 6) asks the
LLM for "key differences between agents/models", but the trial data
injected into the prompt carries only `trial_name / summary / checks`.
The evaluated agent and model are recorded in each trial's
`result.json` (`config.agent.name`, `config.agent.model_name`) but
never reach the aggregation. In the 2026-10-09 E2E the LLM correctly
reported "model identity was not provided, so no model-level
comparison is possible" — the section is dead weight for multi-agent
comparison jobs, which is its intended use case.

## Goals

- Make per-trial agent/model identity available to the job
  aggregation so summary point 6 can actually compare agents/models
  when a job mixes them.

## Non-goals

- No changes to the frozen `assets/` prompt/rubric files.
- No new per-trial product fields unless the chosen design requires
  them (schema stability is a soft convention for the future viewer).
- No cross-job comparison.

## Current state & gap

- `result.json` has the identity (`config.agent.name`,
  `config.agent.model_name`, top-level `agent_info`).
- The per-trial judge CAN read `result.json` (read_file tool) but has
  no schema field to report identity into.
- The aggregation prompt is built from per-trial `analysis.json`
  dicts only ([analyzer.py, `analyze_job`]).

## Design

Two candidate directions (to be decided at Gate 1):

1. **Bypass injection**: `analyze_job` reads
   `config.agent.{name,model_name}` from each trial's `result.json`
   via `trial_reader` and injects a compact identity table ahead of
   `{trial_results}` in the aggregation prompt. No schema change, no
   product change; prompt is assembled in code (template untouched).
2. **Schema extension**: add a `model` field to the per-trial response
   schema and ask the judge to echo it. More moving parts (schema,
   cached-product compatibility) for little gain over (1).

Direction (1) looks favored: identity is ground truth from the
platform, not something the judge should opine on.

## Compatibility impact

- Products: likely unchanged under (1); under (2) a new field would
  appear in `analysis.json` (viewer convention impact).
- Frozen assets: untouched under both.
- Tests: new aggregation-prompt assertions; no existing behavior
  change.

## Verification plan

- Unit: multi-agent fake job (two trials with different
  `config.agent.model_name`) asserts the identity reaches the
  aggregation prompt text.
- Live: multi-agent job E2E; summary point 6 references actual model
  identities.

## Status & links

- Proposed 2026-10-09 after the P003 E2E surfaced the gap.
