# P000 — Feature Management Process

Status: **landed** · Type: process · PRs: this commit

## Background

triage-kit reached MVP (M1–M7b). Post-MVP work arrives as ad-hoc
optimization points discovered during real usage (e.g. product layout
migration, `clean` command, parallel analysis). They need a tracking
system so no feature is developed "unconstrained" again — the README
Roadmap alone cannot carry design rationale.

## Goals

- A lightweight, in-repo process: index table (`ROADMAP.md`) + one-page
  design docs (`docs/proposals/PNNN-<slug>.md`).
- Two gates: design doc must exist and be final **before** coding
  (Gate 1); regression green + live verification + docs synced
  **before** closing (Gate 2).

## Non-goals

- No issue tracker / external platform dependency.
- No heavyweight design process for small fixes (threshold below).

## Design

**Doc skeleton (7 sections, one page max, ~30 min to write):**

1. Background & motivation — why, with evidence (log lines,
   measurements, pain points)
2. Goals / **non-goals** — non-goals are mandatory
3. Current state & gap
4. Design — chosen option + rejected options with reasons
5. Compatibility impact — products / cache identity / CLI / tests
6. Verification plan — TDD test points + whether live E2E is needed
7. Status & links — status, related commits

**Lifecycle:** `proposed → accepted → building → landed` (or
`dropped` with the reason kept).

**Gate 1 (before coding):** doc committed, non-goals filled,
verification plan listed. Missing any → no code.

**Gate 2 (before closing):** full regression green, live verification
done where applicable, README/DESIGN synced, index row updated.

**Doc threshold — create a P doc only if any holds:**

- touches product layout, cache identity, or CLI compatibility surface
- spans ≥3 files as a functional change
- introduces a new dependency or directory convention

Below the threshold: plain TDD + commit message.

## Compatibility impact

None — documentation only. README Roadmap becomes a summary pointing
here.

## Verification plan

N/A (docs). Ongoing verification is dogfooding: every future feature
uses this process.

## Status & links

- Landed with the initial P001–P003 conversion (this commit).
