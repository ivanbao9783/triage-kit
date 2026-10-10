# P009 — Native Chinese reports (`--lang` selects `analysis.md` language)

Status: **landed** · Type: optimization · Priority: medium
Scope revision (2026-10-10, user decision): `analysis.zh.md` is retired;
`--lang` now selects the language of `analysis.md` itself.

## Goals

- `--lang zh` produces a natively composed Chinese `analysis.md`
  (single human-readable report per level); `--lang en` (default)
  keeps the mechanical English rendering — the language follows the
  flag instead of a side-by-side copy.
- `analysis.json` stays the stable English contract artifact at all
  times (judge reasoning unchanged, downstream consumers unaffected).

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

Root cause: the model is instructed to *translate*, so it performs
sentence-level re-rendering of English prose instead of composing in
Chinese.

## Non-goals

- No change to frozen assets — the zh prompt is inline code, and the
  analyze prompt/rubric assets stay byte-frozen.
- No locale framework / multi-language generalization (zh only, as
  today).
- No job-aggregation quality work (the summary content itself is
  P010's scope; P009 only changes how the zh report is composed).

## Current state & gap

- Second-hop call in `core/analyzer.py`: `_TRANSLATE_INSTRUCTION` +
  the English markdown → `_translate_markdown()` writes
  `analysis.zh.md`. Used by both the trial path (after
  `_render_analysis_md`) and the job path (after rendering
  `# Job Analysis\n\n{summary}`).
- The model never composes in Chinese; it re-renders English
  sentences, which is the root of the translationese.

## Design

User-confirmed decisions (2026-10-10, Gate 1):

1. **Approach (a) — compose, don't translate.** The second hop keeps
   its current shape (a single plain `backend.query` call, no tools,
   same cost as today) but the prompt and input change:
   - Prompt is written in Chinese and instructs native Chinese
     technical composition ("用中文撰写诊断报告"), explicitly
     forbidding sentence-level translation of English source.
   - Input is the **structured analysis payload** (the same dict
     behind the English markdown), not the English markdown:
     - trial level: the trial `analysis.json` content (trial_name,
       summary, checks with outcome + explanation)
     - job level: the job summary text (the sole content of the
       English job markdown)
   - Verdict consistency is a hard constraint: outcomes/verdicts in
     the zh report must match the JSON exactly; the model must not
     re-adjudicate.
   - Identifiers (file names, trial names, criterion names such as
     `reward_hacking`) stay in English.
2. **Structure: keep the existing skeleton.** The zh report follows
   the same section layout as the English `analysis.md` (title →
   summary → one section per criterion with outcome), so the two
   reports stay side-by-side comparable.
3. **Job level: same treatment.** Both call sites switch to the new
   compose prompt; one instruction constant, two input shapes
   (trial JSON payload / job summary).

Code shape: `_TRANSLATE_INSTRUCTION` → the Chinese rules block +
level-specific skeletons (`_ZH_COMPOSE_RULES`, `_ZH_TRIAL_COMPOSE`,
`_ZH_JOB_COMPOSE`); `_translate_markdown(products_dir, markdown)` →
`_compose_zh_report(products_dir, instruction, md_name, payload)`
where payload is the structured source; both `analyze_trial` and the
job path pass their dict/summary instead of the rendered markdown,
and the composed report is written as `analysis.md` (route B).
Empty-output guard unchanged.

### Payload contract (finalized 2026-10-10)

**Trial level** — the input is the trial `analysis.json` content
verbatim (the `model_dump(mode="json")` result already validated
against the response schema; no additions or removals):

```json
{
  "trial_name": "<trial directory name>",
  "summary": "<English summary paragraph>",
  "checks": {
    "<criterion>": {"outcome": "pass|fail|not_applicable",
                    "explanation": "<English reasoning>"}
  }
}
```

`checks` keys are rubric-determined (count not fixed).
Serialization: `json.dumps(analysis, ensure_ascii=False, indent=2)`.
The English `analysis.md` no longer enters the second hop (it is a
mechanical rendering of the JSON — a strict subset informationally).

**Job level** — the input is the job `summary` string alone (exactly
what the English job markdown renders: `# Job Analysis` + summary; no
trial detail expansion).

**Prompt structure** — a shared Chinese rules block plus a
level-specific skeleton instruction:

- Shared rules: (1) compose in native Chinese technical prose, no
  sentence-level translation; (2) outcomes must match the input
  exactly — no re-adjudication; (3) identifiers (file/trial/criterion
  names, metrics like p2p/f2p) stay in English; (4) Markdown body
  only, no preamble, no code fences.
- Trial skeleton: `# 分析：{trial_name}` → Chinese summary paragraph →
  one `## {criterion}: {outcome}` section per criterion (isomorphic
  to the English `analysis.md`).
- Job skeleton: `# 作业级分析` → Chinese summary body (user-confirmed
  title, 2026-10-10).

Rejected alternative: (b) parallel generation (a second full agent
pass over the trial context composing directly in Chinese) — doubles
per-trial cost and, worse, two independent reasoning passes can
diverge on verdicts, breaking the zh/JSON consistency guarantee.

## Compatibility impact

- **Product naming (scope revision)**: `analysis.zh.md` is retired.
  `--lang zh` writes the Chinese composition directly as
  `analysis.md`; `--lang en` keeps the mechanical English rendering.
  Same for both levels (trial and job).
- `analysis.json` (contract artifact) is always English — judge
  prompt, rubric assets, and cached verdicts are language-invariant.
- Cache semantics unchanged (identity = rubric sha + model; the zh
  compose hop was never part of cache identity). On a cache hit with
  `--lang zh`, no compose happens — rerun with `--force` to get a
  Chinese `analysis.md` (user decision (i), 2026-10-10).
- `triage clean` is unaffected (it removes whole `triage-kit/`
  directories; file names inside are irrelevant).

## Verification plan

- TDD: update/extend unit tests — compose prompt content (native
  composition wording, verdict-consistency constraint, identifier
  rules), input shape (payload not markdown), `--lang zh` writes
  Chinese content into `analysis.md` (no `.zh.md`), `--lang en`
  unchanged, empty-output guard still raises.
- Live: regenerate products for a handful of trials from `details`
  (`--force --lang zh`); readability review by the user (native
  reviewer is the oracle here).

## Status & links

- Proposed 2026-10-09. Gate 1 accepted 2026-10-10 (user confirmed
  approach (a), skeleton retention, job-level inclusion). Scope
  revised 2026-10-10 after the 3-trial live E2E review: route B
  (md language follows `--lang`, JSON stays English) + cache-hit
  decision (i) (no compose on hit, `--force` to regenerate).
  Evidence: `details/triage-kit/analysis.zh.md` translationese
  observed in live E2E. Related: P010 (job summary quality —
  orthogonal).
- Landed 2026-10-10: unified E2E (deepseek-flash) verified the
  route-B shape on both levels — trial-level `analysis.md` natively
  composed in Chinese (user-approved readability, 3-trial review +
  the unified run), job-level `analysis.md` as `# 作业级分析`
  composed from the job summary; cache hits (47/47) correctly skip
  the compose hop per decision (i); stale `analysis.zh.md` files are
  retired leftovers removable via `triage clean`.
