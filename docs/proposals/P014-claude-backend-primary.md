# P014 — Claude Agent SDK backend as the primary (and only) harness

Status: **landed** · Type: refactor · Priority: high

## Background & motivation

The general harness (hand-rolled OpenAI-compatible tool loop) accumulated
defects that are structural, not incidental: P008 (forced tool_choice
400s on reasoning endpoints — 16/46 badcases lost in the 113-trial live
E2E), P009 (tool exceptions killing trials), unbounded context growth,
low tool throughput. All of this is agent-harness engineering — plumbing
the project never wanted to own. The project's core value is the
diagnostic rubric and prompt assets.

Two spikes (2026-10-10, DeepSeek's Anthropic-compatible endpoint
`https://api.deepseek.com/anthropic`) proved the alternative:

- Layer 1 (plain HTTP): model names (`deepseek-flash`,
  `deepseek-v4-pro`, even `claude-sonnet-4-5` mapped), tool use, and
  thinking blocks all work.
- Layer 2 (real `ClaudeHarness`, unchanged repo code): both contract
  call shapes work — `query()` and `query_agent()` with tools +
  dynamic output_schema, producing a correct structured analysis.
- E2E-lite: `triage analyze <trial> --backend claude -m deepseek-flash
  --force` on a trial the general backend had killed (400 at the
  forcing turn) ran 16 turns autonomously and produced a complete,
  high-quality product set (json/md/meta + verdicts + cache identity).

Claude Code CLI (bundled with the SDK, no separate Node install)
manages the tool loop, context, and structured output — the entire
class of general-harness defects disappears. Domestic model providers
(DeepSeek, and others) expose Anthropic-compatible endpoints for
Claude Code compatibility, so coverage is wider than "Anthropic only".

## Goals

- `claude` becomes the default and only backend; the general harness,
  its tools, scripts, and tests are removed.
- CLI keeps `--backend` (currently accepts only `claude`) — future
  backends (codex SDK, DeepSeek harness SDK) are planned entries.
- Dependencies simplified: `claude-agent-sdk` becomes a hard
  dependency; `openai` extra removed; a thin `requirements.txt`
  (`-e .[dev]`) provides one-click install.
- The 21 badcases lost in the 113-trial E2E (16 × P008 + 5 × P009)
  are re-analyzed with the claude backend (verdict recovery is part
  of verification).

## Non-goals

- No codex/deepseek-harness backend implementation here (separate
  future entries; `--backend` keeps the extension seam).
- No judge sandbox work in this entry (the CLI Read/Glob/Grep do not
  pass through our deny-list — filed as P015).
- No `--base-url` re-introduction; endpoint override stays via
  `ANTHROPIC_BASE_URL` (verified working against DeepSeek).
- No changes to rubric/prompt assets, product schemas, or caching
  identity (rubric sha256 + model).

## Current state & gap

- `backends/general/` (harness.py 275 lines, tools.py sandbox layer)
  plus `scripts/demo_general_harness.py`, `scripts/e2e_mock_endpoint.py`,
  4 test files (~610 lines), conftest FakeClient section, CLI
  `--base-url`/general branches, pyproject `general` extra.
- `backends/claude/harness.py` already satisfies the full contract
  (E2E-lite verified end-to-end against DeepSeek).

## Design

User-confirmed decisions (2026-10-10):

1. `--backend` stays; valid values now `{"claude"}` only; default
   `claude`. Unknown names error as today.
2. `--base-url` option removed (both commands); `_open_general_backend`
   and `_exempt_from_system_proxy` deleted; `build_backend()` reduces
   to the claude branch.
3. `_resolve_model`: general branch removed; claude defaults
   (haiku/analyze, sonnet/check) unchanged.
4. Delete: `src/triage_kit/backends/general/`, both general scripts,
   `tests/test_general_harness.py`, `tests/test_tools.py`,
   `tests/test_harness_logging.py`, `tests/test_e2e_cli.py`;
   conftest loses the FakeClient/SUBMIT_RESULT/tool_call/response
   section (zero remaining consumers); test_cli drops ~8
   general-specific cases and gains rejection coverage for the
   removed `--base-url`.
5. pyproject: `[project.dependencies]` = pydantic, pyyaml, typer,
   claude-agent-sdk; extras reduce to `dev`; new thin
   `requirements.txt` (`-e .[dev]`) — pyproject stays the single
   dependency source of truth.
6. ROADMAP: P008/P009 → dropped (defect carrier retired); P015 filed
   (sandbox gap); docs (README/DESIGN) rewritten to the single-backend
   shape with DeepSeek-via-`ANTHROPIC_BASE_URL` as the worked example.

## Compatibility impact

- CLI surface: `--backend general` and `--base-url` stop working
  (error); `--backend claude` + `-m` + `ANTHROPIC_BASE_URL` is the
  new canonical form. README quick-start updated accordingly.
- Products/schemas/cache identity unchanged.
- Known regression (accepted, filed as P015): judge can read
  `triage-kit/` products via CLI tools on the claude path — the
  general-only deny-list disappears with it.

## Verification plan

- Full unit regression green (expected ~125 cases after removals).
- Live E2E: re-run the 21 lost-badcase trials from `details` with the
  claude backend (`-m deepseek-flash`, `ANTHROPIC_BASE_URL` pointed at
  DeepSeek); assert verdicts recovered and products well-formed.
- README/DESIGN review against actual `--help` output.

## Verification results (2026-10-10)

- Full unit regression: **127 passed** after the removals (4 test
  files / ~610 lines deleted, conftest FakeClient section dropped).
- Recovery E2E (`triage analyze details --failing -m deepseek-flash
  --lang zh -j 8`, `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`):
  - 47/47 trials produced products, `failed_trials: []` — 26 cache
    hits + 21 re-analyzed (all badcases lost to P008/P009 recovered
    with complete verdicts; e.g. `bandit-incremental-cache-control__S7DF6Qj`,
    previously killed at the forcing turn, finished autonomously).
  - Verdict distribution: `reward_hacking` 47 pass;
    `task_specification` 33 pass / 14 fail.
  - 46 trial-level `analysis.zh.md` + job-level 3 products
    (json/md/zh.md); 0 "analysis failed" log lines.
  - Wrapper exit 1 identified as a TRAE sandbox artifact (the bundled
    Claude CLI subprocess writing `~/.claude` session files was
    blocked), not a triage-kit failure — products landed fresh and
    complete.
- README/DESIGN reviewed against actual `--help` (no `--base-url`,
  `--backend claude` default, requirements.txt quick start).

## Status & links

- Accepted 2026-10-10 (user decisions on backend option retention,
  requirements.txt form, P008/P009 drop, test removal).
- Landed 2026-10-10 (verification plan fully green, see above).
  Related: P015 (sandbox gap), P008/P009 (dropped).
