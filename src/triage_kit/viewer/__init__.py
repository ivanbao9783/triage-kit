"""Local read-only viewer for triage-kit diagnosis products (P006).

The viewer is deliberately split in two:

- ``scanner`` — the data layer: plain-JSON discovery over the
  ``triage-kit/`` sub-directory layout, zero web or markdown
  dependencies (so it unit-tests without a server).
- ``server`` — the presentation layer: a zero-build FastAPI + Jinja2
  SSR app that renders scanner output as HTML.

Both are optional extras: ``pip install 'triage-kit[viewer]'``.
"""