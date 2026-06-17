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

---

### D002 — Project named "Cedant" (codename), `underwriting-copilot` (repo)

**Date:** 2026-06-17
**Status:** Active

**Context:** Public-facing portfolio project needs a name that is both
searchable for an interviewer browsing GitHub and distinctive enough to
remember in conversation. Two competing pressures: technical legibility
(an interviewer skimming should immediately understand the domain) and
domain credibility (a name that signals familiarity with the vocabulary
of reinsurance is itself a low-effort competence signal).

**Decision:** Use **"Cedant"** as the project codename in documentation,
conversation, and the README masthead. Use **`underwriting-copilot`** as
the GitHub repository name and the Python package name (already locked in
`pyproject.toml`).

**Rationale:** A *cedant* in reinsurance is the insurer ceding risk to
the reinsurer — a real term of art, short, memorable, and one whose
appearance in a project README signals domain literacy without
explanation. `underwriting-copilot` as the repo name is immediately
legible to a non-technical reader and searchable in a way "cedant" alone
would not be. The two-name split gives both the SEO benefit of a
descriptive repo URL and the distinctive shorthand for conversation.

Alternatives considered and rejected:
- `cedant` alone — too obscure as a repo name; an interviewer skimming
  GitHub might not realise what it is.
- `underwriting-copilot` alone — loses the domain-literacy signal and
  reads as a generic AI side project.
- Acronyms (`RURC`, `RUBRIC`) — read as corporate marketing rather than
  considered design.

**Trade-offs / risks:** Slight cognitive cost of carrying two names.
Possible name collision on PyPI or with another GitHub project — should
be checked before any package publication, though local-only use is
unaffected.

**When to revisit:** If the project is renamed for any external reason
(employer requirement, publication, brand collision), or if the two-name
split causes confusion in interview contexts.

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
