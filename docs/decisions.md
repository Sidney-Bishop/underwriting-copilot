# Decisions

Significant, hard-to-reverse choices and **why** they were made — including
what was ruled out. **Discipline: supersede, don't edit.** When a decision
changes, leave the old one intact, mark it `Superseded by Dxxx`, and write a
new entry. The *path* of decisions is itself information.

The test for whether something belongs here: would a reasonable person, months
from now, ask "why is it done this way?" — and is the answer a deliberate
choice rather than an accident? If yes, it's a decision. If it's just "what
happened," it belongs in `journal.md`.

---

### D001 — Scaffolded with project-bootstrap

**Date:** 2026-06-17
**Status:** Active

**Context:** New project `underwriting-copilot` started from the project-bootstrap
scaffolder rather than assembled by hand.

**Decision:** Adopt the standard layout — single-purpose docs, src/ package,
uv for environment, and (where enabled) git, DVC, Graphify, and agent files.

**Rationale:** Recurring plumbing is error-prone to reassemble each time;
starting from a considered baseline keeps every project consistent and means
the documentation discipline is in place from commit one.

**Trade-offs / risks:** The scaffold may include structure this project never
grows into; prune what you don't use rather than letting it rot.

**When to revisit:** If the standard itself changes materially, note whether
this project should be re-aligned.

<!-- Copy this shape for new decisions:

### D002 — <short title>

**Date:** YYYY-MM-DD
**Status:** Active | Superseded by Dxxx
**Supersedes:** Dxxx (optional)

**Context:** what situation prompted the decision.
**Decision:** what you chose, stated plainly.
**Rationale:** why — including alternatives considered and rejected.
**Trade-offs / risks:** what you're giving up or exposing yourself to.
**When to revisit:** the condition under which this should be reconsidered.
-->
