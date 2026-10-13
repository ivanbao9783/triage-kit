# P019 — Dependency lockfile (uv.lock) for reproducible installs

Status: **proposed** (2026-10-13) · Type: process · Priority: **low**

## Background & motivation

`pyproject.toml` is the single dependency source and declares only
lower bounds (`pydantic>=2.0`, `pyyaml>=6.0`, `typer>=0.12`, plus the
`[viewer]` extra's four), with `claude-agent-sdk==0.2.165` the one
exact pin. Transitive dependencies and every floating lower bound are
resolved fresh on each install, so two machines can build different
environments from the same commit — the reproducibility the project's
own conventions ask for is not enforced.

User decision (2026-10-13): **defer**. No CI exists yet, so a
lockfile's `--check` gate would be manual and its day-to-day value
limited; adopt **`uv.lock`** when CI is introduced.

## Goals

- A committed lockfile pinning the full transitive set (with hashes),
  covering the `dev` and `viewer` extras in one file.
- CI (once added) runs `uv sync --locked` (or `uv lock --check`).

## Non-goals

- No change to products, cache identity, CLI, or runtime behavior.
- No build-backend switch (stays hatchling); uv is used for env
  resolution/sync only.
- No retroactive pinning of the other direct deps in `pyproject.toml`.

## Current state & gap

- No lockfile of any kind; `requirements.txt` is only the
  `pip install -r` convenience entry (`-e .[dev,viewer]`).
- No CI (`.github/` absent), so nothing consumes a locked env today.

## Design

- **Chosen: `uv.lock`.** Native support for optional-dependency groups
  (`dev` / `viewer`) in one file and for the editable root package
  (`-e .`); cross-platform wheel markers; `uv lock --check` as a
  one-command CI gate; `uv export --format requirements-txt` still
  yields a pip-consumable locked file for non-uv users.
- **Rejected: pip-tools `requirements.lock`.** pip-native, but it does
  not support extras natively (one `.in` per extra) and
  `--require-hashes` conflicts with the editable root install — exactly
  the two shapes this repo has.

## Compatibility impact

None at runtime. Adds one dev tool (uv) and one committed artifact
(`uv.lock`); `requirements.txt` stays as the pip fallback.

## Verification plan

- `uv lock` produces a lock covering both extras; `uv sync --locked
  --extra dev --extra viewer` reproduces the passing suite (249 tests)
  from a clean env.
- `uv export --format requirements-txt` installs cleanly with pip.

## Status & links

- Proposed 2026-10-13 (deferred until CI lands).
- Related: P000 (process/doc threshold — a lockfile introduces a new
  artifact + dev tool); the 2026-10-13 dependency review that pinned
  `claude-agent-sdk==0.2.165`.