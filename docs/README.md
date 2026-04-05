# Docs

Active documentation now lives in a small set of stable directories:

- `docs/architecture/`
  - Runtime, CMS, watchdog, and account-data architecture notes.
- `docs/guides/`
  - Operator and developer guides such as broker, market-data, and export workflows.
- `docs/strategy/`
  - Current strategy documentation that still reflects the active implementation.
- `docs/archive/`
  - Historical design drafts, old refactor notes, archived planning records, and retired reports.

Rules for keeping this tree clean:

- Put current-facing documentation in `architecture`, `guides`, or `strategy`.
- Move superseded drafts, experiments, and execution logs into `archive`.
- Do not create new top-level markdown files under `docs/` unless they are this index or a future top-level convention file.
