# Journal

The append-only, dated narrative of building this. **One entry per working
session.** Records the *road*, not just the destination: what you did, what
broke, the dead ends, the wrong turns you corrected, the small gremlins.

**Append-only.** Never edit an old entry to "fix" it — if it was wrong, write
a new entry correcting it. The wrongness is part of the record.

---

## 2026-06-17 — project scaffolded

- Created `underwriting-copilot` from the project-bootstrap scaffolder.
- Layout, docs skeleton, and environment are in place; this is the seed entry
  so the journal is never an empty file pretending a record exists.
- First real work starts from here — log what you try, including what fails.
- Spent the first working session on documentation policy and scope
  rather than code — deliberately. The interview brief is a 5-day
  budget to produce a public-repo artefact that pre-empts Lead-level
  questions; that makes the README and supporting docs the actual
  deliverable, with code as their substrate.
- Filled out `charter.md` with mission, in-scope / out-of-scope (full
  RBAC, Decision Pack stretch, learned confidence calibration, and any
  UI beyond a CLI are explicitly out), success criteria framed as
  interview-credibility signals, and a `## Budget` section recording
  the 5-day constraint.
- Lodged Q1 (corpus: real public vs. synthetic), Q2 (orchestration
  framework: LangGraph vs. plain Python vs. DSPy), and Q3 (confidence-
  score formula) in `open_questions.md` as the first three known
  unknowns — each will resolve into a D-entry.
- Added Q4 (target deployment context — what stack does the
  interviewing reinsurer use today). Nearly mis-shelved this as a
  technical question; it's actually a *framing* question that resolves
  into the README's lead paragraph rather than a D-entry. Recorded the
  distinction explicitly in the Q4 notes so the pattern isn't repeated.
- Landed on "Cedant" (codename) + `underwriting-copilot` (repo) as the
  name pair — see D002 for the reasoning and rejected alternatives.

<!-- Entry shape:

## YYYY-MM-DD — short summary of the session

- What you actually did.
- What broke and how you diagnosed it.
- Dead ends — what you tried that didn't work, and why you abandoned it.
- Wrong conclusions you reached and later corrected (these are gold).
- Gremlins — the environment bug, the tooling quirk, the thing that confused
  you twice.
-->
