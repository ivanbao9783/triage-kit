# P010 — Job aggregation summary quality

Status: **proposed** · Type: feature · Priority: medium

## Background & motivation

The job-level aggregation (per `analyze-job.txt`, injected with the
per-trial `trial_name / summary / checks` results) produces summaries
that deviate from what the user expects on real jobs (2026-10-09
113-trial live E2E). Observed pain points: the six-section structure
produced by the template does not match the user's mental model of an
actionable job-level badcase report, and section 6 ("Key differences
between agents/models") is dead weight on single-agent jobs (see
P007).

## Goals

- Job-level `analysis.md` / `analysis.zh.md` summaries that match the
  user's expectations for actionable triage reporting on real jobs.
- The exact expectation set is captured at Gate 1 (see open
  questions) before any asset or code change.

## Non-goals

- No change to per-trial analysis (analyze.txt / rubric stay frozen).
- No schema change to `analysis.json` (product stability contract).
- Not addressing the model-identity gap (that is P007, separate).

## Current state & gap

- Aggregation prompt = frozen asset `assets/analyze/analyze-job.txt`
  (sha256-guarded by `tests/test_assets.py`). **Constraint conflict**:
  any prompt improvement touches a byte-frozen file.
- Injection payload is only `trial_name / summary / checks` per trial
  (`core/analyzer.py` ~line 237).

## Design

**To be finalized at Gate 1.** Decisions required:

1. **Capture expectations**: the user writes down (or reviews samples
   and annotates) what a good job-level report contains — sections,
   prioritization, length. The current six-section template is the
   baseline to critique.
2. **Frozen-asset strategy**, candidate paths:
   - (a) Consciously diverge: modify `analyze-job.txt`, update the
     sha256 guard, document the divergence from upstream (loses
     upstream diff-ability for this one file).
   - (b) New non-frozen variant (e.g. `analyze-job-v2.txt`) selected
     by default or via option; the frozen original stays for
     provenance.
   - (c) Enrich the injection payload only (e.g. include check
     verdict details), prompt unchanged — may be enough if the
     deviation is data-starvation rather than template-shape.
- Open question: which failure dominates — template shape (a/b) or
  thin payload (c)?

## Compatibility impact

- Touches either a frozen asset (needs an explicit divergence
  decision + sha256 guard update) or adds a new asset file; product
  filenames unchanged.

## Verification plan

- Live: rerun aggregation on the `details` job (46 badcases, cached
  trial results make this cheap); user reviews the summary against
  the annotated expectations.
- Unit: asset-guard tests updated to match the chosen strategy.

## Status & links

- Proposed 2026-10-09. Related: P007 (model identity in the
  aggregation payload).
