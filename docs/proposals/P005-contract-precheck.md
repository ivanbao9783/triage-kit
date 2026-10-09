# P005 — Deterministic contract pre-check layer

Status: **proposed** · Type: feature · Priority: medium

## Background & motivation

The check workflow relies on the LLM judge for two fundamentally
different kinds of verification. A large share of what matters most
for DeepSWE-style tasks is **purely mechanical contract consistency**
— answerable by string/structure comparison, with a single correct
answer: config.json report path vs. test.sh output path, f2p/p2p
node-ids vs. test.patch contents, test.sh anti-cheat claims vs.
solution.patch touched paths. LLM judges verify these unreliably
(missed reads, hallucination), slowly, and at per-call cost, while a
script gives exact, reproducible, zero-cost verdicts in milliseconds.

## Goals

- A deterministic pre-check module (e.g. `core/contract_checks.py`)
  that runs before the LLM pass for supported families, verifying
  contract self-consistency programmatically.
- Verified/falsified facts injected into the judge prompt as trusted
  context ("the following contracts were verified programmatically —
  accept, don't re-judge"), so the LLM only handles judgment calls.
- Deterministic checks usable standalone as a fast CI gate,
  independent of the LLM check.

## Non-goals

- No replacement of the LLM check — the two layers complement
  (deterministic gate + LLM trend judgment, per the project's
  evaluation philosophy).
- No new CLI command in the first cut: hook into the existing
  `triage check` pipeline (checker has a reserved pre-layer slot).

## Current state & gap

- `checker.py` pipeline has an architectural slot for a pre-layer
  (design intent recorded in DESIGN.md §9.3) but nothing implemented.
- No contract-check scripts exist; every check today costs an LLM
  call including the mechanical ones.

## Design

**To be finalized when started** (Gate 1). Open questions: which
families get which checks (deep-swe first: report-path, node-id,
anti-cheat-claim consistency); output schema of the deterministic
layer and how it merges into check-result.json (separate section vs.
criteria entries); whether standalone CI mode needs an exit-code
contract.

## Compatibility impact

- check-result.json gains a deterministic-checks section (additive
  schema growth — products schema is stable but may grow).
- checker pipeline gains a pre-LLM stage; cache identity may need to
  include the pre-check script version.

## Verification plan

- TDD: contract checks are pure functions over fixture task dirs —
  ideal unit-test targets (expected pass/fail per check, no LLM).
- Live verification: run over the DeepSWE sample tasks; compare
  judge verdicts with and without injected facts.

## Status & links

- Proposed 2026-10-09; design direction recorded earlier in
  DESIGN.md §9.3 (second-batch work).
