# P015 — Judge sandbox gap on the claude backend path

Status: **proposed** · Type: feature · Priority: medium

## Background & motivation

The retired general backend carried a defense-in-depth sandbox
(`backends/general/tools.py`): the judge's `read_file`/`glob`/`grep`
silently excluded `triage-kit/` product directories, preventing
self-referential bias (a judge reading a previous verdict about the
same trial). The claude backend uses the Claude Code CLI's own
Read/Glob/Grep tools, which do not pass through our deny-list —
`<trial>/triage-kit/` is visible to the judge. This gap previously
existed as a known limitation (claude was a secondary backend); with
P014 making claude the only backend, it becomes the primary path's
gap.

## Goals

- The judge cannot read `triage-kit/` products through any tool on
  the claude path (parity with the retired sandbox's guarantee).

## Non-goals

- No read_file line/size limits port (the CLI's own tools have their
  own sane limits; our 2000-line/2000-char caps were general-specific).
- No write-path restrictions (judge tools are read-only already).

## Current state & gap

- `ClaudeAgentOptions` is constructed in
  `backends/claude/harness.py` with `permission_mode=
  "bypassPermissions"` and `allowed_tools=["Read", "Glob", "Grep"]`;
  no deny rules.
- The Claude Code CLI supports a permissions system with deny rules
  (e.g. `Read(./triage-kit/**)` deny); whether the SDK options
  surface it (and whether relative deny patterns anchor per-cwd)
  needs verification.

## Design

**To be finalized at Gate 1.** Candidate directions:

- (a) `ClaudeAgentOptions` permission deny rules for
  `Read`/`Glob`/`Grep` on `triage-kit/**` (if the SDK surfaces the
  CLI permissions config).
- (b) CLI-level config file (`~/.claude/settings.json` or
  project-scope `.claude/settings.json`) shipping deny rules — less
  code but couples triage-kit behavior to global user config.
- Open question: does a denied Read return a tool-error the judge can
  see (acceptable — same as the old PermissionError convention) or
  abort the run (unacceptable)?

## Compatibility impact

- Harness-internal; no product/schema/asset/CLI change.

## Verification plan

- Unit (fake SDK): options carry the deny configuration.
- Live: place a stale `triage-kit/analysis.json` in a trial dir,
  ask the judge (via prompt) to read it; assert it cannot.

## Status & links

- Proposed 2026-10-10. Supersedes the sandbox note retired with P014.
