# AGENTS.md

Instructions for AI coding agents (Claude, Codex, OpenCode, Cursor, …) working
in **underwriting-copilot**. Kept deliberately lean: bloated instruction files get
ignored wholesale rather than filtered. This file *points at* the docs instead
of restating them.

## What this is

Local-first RAG copilot for reinsurance underwriting — hybrid retrieval, cited answers, and a real evaluation harness.

## Build / test / run

```bash
uv sync          # install dependencies
uv run pytest    # run the test suite
```

## Where to find things

Read the **documentation map** in `README.md` first — it says which file holds
what. In particular:

- `docs/decisions.md` — why the code is the way it is (the "why" behind choices).
- `docs/architecture.md` — the current structure and moving parts.
- `docs/journal.md` — the running narrative; **append-only**, never edit old entries.

## Conventions

- Source lives in `src/`; exploratory work (if any) in `notebooks/`.
- Record significant choices in `docs/decisions.md` using supersede-don't-edit.
- When you finish a working session, append a dated entry to `docs/journal.md`.
- Don't duplicate architecture or status into this file — link to the docs.

## Guardrails

- Treat `docs/decisions.md` and `docs/journal.md` as append-mostly: edits that
  delete large chunks are a red flag — show the diff before applying.
- Don't run destructive commands (data deletion, force-push) without asking.
