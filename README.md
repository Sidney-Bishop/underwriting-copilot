# underwriting-copilot

Local-first RAG copilot for reinsurance underwriting — hybrid retrieval, cited answers, and a real evaluation harness.

## Quickstart

```bash
uv sync          # set up the environment
uv run pytest    # run tests (if present)
```

## Documentation map

This project keeps information in single-purpose files. Find the right one by
the *kind* of information you have. This map indexes roles; it does **not**
summarise contents (those live in the files and would rot here).

| Document                 | Kind             | Read it for…                       | Update style          |
|--------------------------|------------------|------------------------------------|-----------------------|
| `docs/charter.md`        | State (rare)     | What this is for; scope in/out     | Overwrite, seldom     |
| `docs/architecture.md`   | State            | How it's built right now           | Overwrite             |
| `docs/status.md`         | State            | Where we are today                 | Overwrite             |
| `docs/open_questions.md` | State            | What we don't know yet (Q-IDs)     | Overwrite; resolve out|
| `docs/decisions.md`      | Decision history | What we chose and why (D-IDs)      | Append + supersede    |
| `docs/journal.md`        | Session history  | The road: what happened, what broke| Append-only, dated    |
| `docs/backlog.md`        | Fluid            | What might come next               | Cross off when done   |
| `docs/philosophy.md`     | Guide            | *Why* the docs are structured thus | Teaches; rarely edited|

**Routing rule** — where does a sentence go? `true now` → a State doc ·
`a choice someone will later question` → `decisions.md` ·
`something that happened` → `journal.md`.

## Layout

```
underwriting-copilot/
├── src/            # the importable package
├── tests/          # pytest (if enabled)
├── docs/           # the single-purpose docs above
└── data/           # DVC-tracked inputs/outputs (if enabled)
```

## License

MIT · Jason Roche
