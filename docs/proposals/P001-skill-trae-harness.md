# P001 — trae harness SKILL.md asset pack

Status: **proposed** · Type: feature · Priority: medium
(was milestone M8 from the original build-out plan)

## Background & motivation

The CLI currently accepts `--backend claude` only (general was retired
by P014; codex / DeepSeek harness backends are planned). The trae
harness (running the judge inside the trae agent environment) exists
as a **skill form**, not a CLI backend — this was a deliberate scope
decision recorded during M1–M7 (see `docs/DESIGN.md`). M8 — authoring
the SKILL.md asset pack that makes the triage judge invocable as a
skill — was deferred at MVP close and is the last unfinished original
milestone.

## Goals

- A `SKILL.md` (plus any referenced assets) that lets a trae agent
  execute the analyze workflow with the same prompts, rubric
  loading, schema validation, and product layout as the CLI path.

## Non-goals

- No new `--backend trae` CLI option (existing decision, unchanged).
- No re-implementation of the tool loop — the skill reuses the core
  orchestration (`Analyzer` + `AgentBackend` contract).

## Current state & gap

- Core orchestration is backend-agnostic (proven by the fake-backend
  test suite and two real harnesses).
- No skill asset exists; trae users have no documented path.

## Design

**To be finalized when started** (Gate 1). Open questions to answer
in the design pass: which parts of the judge prompt/rubric loading
live in the skill vs. stay in package code; how the skill surfaces
products; whether caching applies on the skill path.

## Compatibility impact

Additive (new asset only). No product, cache, or CLI surface changes.

## Verification plan

- TDD where package code changes.
- Live verification: run the skill end-to-end on the `details` sample
  job and compare products against the CLI-path outputs.

## Status & links

- Proposed; awaits scheduling.
