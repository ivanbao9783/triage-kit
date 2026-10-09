# P011 — Native Chinese reports (replace translation hop)

Status: **proposed** · Type: optimization · Priority: medium

## Background & motivation

`--lang zh` currently produces `analysis.zh.md` via a second-hop
**translation** of the English `analysis.md`: the inline prompt (in
`core/analyzer.py`, `"Translate the following Markdown report into
Simplified Chinese."`) asks the model to translate the finished
English report. Live E2E (2026-10-09, 113-trial job) confirmed the
user-experienced defect: the output reads as translationese —
grammatically valid but unnatural Chinese (European-style sentence
structure, unnatural terminology), poor readability for native
reviewers.

## Goals

- `analysis.zh.md` reads as natively written Chinese technical prose,
  not a translation of English.
- English contract products stay untouched (`analysis.json`,
  `analysis.md` remain the stable schema-bearing artifacts).

## Non-goals

- No change to frozen assets — the zh prompt is inline code, and the
  analyze prompt/rubric assets stay byte-frozen.
- No new product files (still one `analysis.zh.md` per level).
- No locale framework / multi-language generalization (zh only, as
  today).

## Current state & gap

- Second-hop call in `core/analyzer.py` (~line 68 prompt, ~129
  writer): pure translation of the English markdown.
- The model never re-reasons in Chinese; it re-renders English
  sentences, which is the root of the translationese.

## Design

**To be finalized at Gate 1.** Candidate directions:

- (a) Rewrite-not-translate: change the second-hop prompt to "用中文
  撰写诊断报告" with the analysis content (JSON verdicts + English
  report as source material, explicitly instructing native-style
  composition rather than sentence-level translation).
- (b) Parallel generation: run the zh hop on the same trial context
  (task section + trajectory pointers) as a fresh composition task —
  higher fidelity but a second full agent pass (cost).
- Open question: is (a) sufficient in practice, or does quality
  demand (b)?

## Compatibility impact

- `analysis.zh.md` content style changes (intended); file name,
  location, and trigger (`--lang zh`) unchanged. No schema impact.

## Verification plan

- Unit: prompt content assert updated (translation → composition
  wording); product naming/placement unchanged.
- Live: regenerate zh products for a handful of trials from
  `details`; readability review by the user (native reviewer is the
  oracle here).

## Status & links

- Proposed 2026-10-09. Evidence: `details/triage-kit/analysis.zh.md`
  translationese observed in live E2E.
