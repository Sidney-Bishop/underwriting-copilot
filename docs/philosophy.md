# Project Documentation: What to Keep and Why

A guide for the early stages of a technical project — whether you're a human
setting up a repo or a coding agent asked to "add some documentation." It
explains *which* documents should exist, *what each one is for*, and — most
importantly — *how to decide where a given sentence belongs*. That last skill
is the one that actually keeps documentation useful over time.

This is opinionated. It is written for projects that are built incrementally,
often across many sessions, sometimes with collaborators (human or AI) who
weren't there for the earlier reasoning. If your project is a throwaway
script, ignore most of this and keep a good README. If your project is
something you'll return to in three months and ask "wait, why did we do it
that way?" — read on.


## The one idea everything else follows from

Most bad documentation isn't bad because it's poorly written. It's bad
because **two fundamentally different kinds of information have been mixed
into one document**, so neither is served well. Before deciding what files to
create, internalise this distinction:

> **State** describes what is true *now*. Updating it *overwrites* the past.
>
> **History** describes how things *came to be*. It is *append-only*; nothing
> is ever overwritten.

A file's most important property is which of these it is. A status report that
tries to also be a history becomes a cluttered mess that's neither current nor
complete. A changelog that gets edited to "fix" old entries stops being a
trustworthy record. Decide a file's kind first; everything else follows.

There is a second, finer split *within* history that catches people out:

> **Decision history** records *destinations* — the settled choices and the
> reasoning behind them.
>
> **Session history** records the *road* — what you tried, what broke, the
> dead ends, the bugs, the things you believed before you knew better.

These are different, and — this is the trap — **having good decision history
can disguise the total absence of session history.** A clean decision log
makes a project feel well-documented while the actual texture of building it
(the half-day lost to an environment bug, the wrong conclusion you nearly
shipped, the gremlin that confused you twice) vanishes entirely. Decision logs
record where you arrived. The value, very often, is in the road.

Keep all three axes — state, decision history, session history — and keep them
in files whose *kind* is unambiguous.


## The recommended file set

Not every project needs all of these on day one. The starred (★) files are
the minimum viable set; add the rest as the project earns them. Names are
suggestions — consistency matters more than the exact words.

| File | Kind | Answers the question | Update style |
|------|------|----------------------|--------------|
| ★ `README.md` | State | "What is this and how do I run it?" | Overwrite |
| ★ `decisions.md` | Decision history | "What did we choose, and why?" | Append + supersede |
| `architecture.md` | State | "How is it built? What are the moving parts?" | Overwrite |
| `status.md` | State | "Where are we right now?" | Overwrite |
| `open_questions.md` | State | "What don't we know yet?" | Overwrite (questions resolve and leave) |
| `charter.md` | State (rarely changes) | "What is this project *for*? What's in/out of scope?" | Overwrite (but seldom) |
| `journal.md` | Session history | "What happened, session by session?" | Append-only, dated |
| `backlog.md` | State-ish | "What might we do next?" | Fluid; cross off when done |

The split looks like a lot of files. It isn't bureaucracy — each file has one
job, which means each edit has a small blast radius, and anyone (human or
agent) can find the right place to read or write without parsing a monolith.


## What each file is for

### README.md — the front door (State)

The only document many people will ever read. Its job is orientation, not
completeness:

- What the project is, in one or two sentences.
- How to install and run it. Exact commands. Assume the reader has none of the
  context you have.
- Where to look for more (link to the other docs).
- Just enough "how it works" to be dangerous — not the full architecture.

**What does NOT belong here:** the decision history, the full architecture
deep-dive, the running status, your todo list. The README is overwritten
freely as the project changes; it always reflects the current state. If you
find yourself writing "previously this used X but now uses Y" in a README,
that sentence belongs in `decisions.md` or `journal.md`, not here.

### decisions.md — the choices and their reasons (Decision history)

The single highest-leverage document for a project you'll return to. It records
**significant, hard-to-reverse choices** and — crucially — *why* you made them,
including what you ruled out.

The discipline that makes it valuable is **supersede, don't edit**:

> When a decision changes, you do NOT delete or rewrite the old one. You leave
> it intact, mark it superseded, and write a new one that references it.

Why this matters: the *path* of decisions is itself information. "We chose A,
then later replaced it with B because we discovered C" tells a future reader
far more than a `decisions.md` that simply shows B as if it were always
obvious. Overwriting destroys the reasoning that's most valuable precisely
when someone is questioning a choice.

A good decision entry has a stable ID and looks roughly like:

```
### D007 — Use an external drafter for speculative decoding

**Date:** 2026-05-22
**Status:** Active
**Supersedes:** D004 (which assumed no speculation was available)

**Context:** what situation prompted the decision.
**Decision:** what we chose, stated plainly.
**Rationale:** why — including the alternatives considered and rejected.
**Trade-offs / risks:** what we're giving up or exposing ourselves to.
**When to revisit:** the condition under which this should be reconsidered.
```

The stable ID (D001, D002, …) lets every other document — and every
conversation — reference a decision unambiguously and forever. When D007
supersedes D004, you edit D004's *status line only* ("Superseded by D007") and
leave its body untouched as the historical record.

**The test for whether something is a decision:** would a reasonable person,
months from now, ask "why is it done this way?" — and would the answer be a
deliberate choice rather than an accident? If yes, it's a decision. If it's
just "what happened," it's session history (`journal.md`).

### architecture.md — the moving parts (State)

How the system is actually built *right now*: the components, how they fit
together, the key data flows, where things live on disk, external services and
how they're configured, the non-obvious technical constraints. This is the
document a new contributor reads to form a mental model.

It is a *state* document — it describes the present and is overwritten as the
architecture changes. The *reasons* the architecture is shaped this way live
in `decisions.md`; the *story* of how it got there lives in `journal.md`.
`architecture.md` just says what is.

### status.md — where we are (State)

A short, current snapshot: what's done, what's in progress, what's blocked,
what's next. Deliberately ephemeral — you overwrite it constantly and never
mourn the old version. Its whole value is being *current*. If `status.md`
starts accumulating dated entries and history, it's quietly turning into a
journal; move that content out.

### open_questions.md — the known unknowns (State)

A live list of things you don't yet know but want to. Each question ideally
has an ID (Q1, Q2, …) so it can be referenced. Questions have a natural
lifecycle: they're **opened**, sometimes **partially answered**, and
eventually **resolved** — at which point they often graduate into a decision
(`decisions.md`) or simply get answered inline and closed.

This is a state document: resolved questions can be removed or marked closed;
you don't keep a growing graveyard of every question ever asked (that's what
the journal is for). The open-questions list should always be readable as
"here's what's genuinely still open."

A useful relationship to keep in mind:

> **Open questions** are "what we don't know." **Decisions** are "what we've
> settled." Questions *resolve into* decisions. The two files are the two ends
> of the same pipeline.

### charter.md — what this is even for (State, rarely changes)

The mission and scope. Why the project exists, what success looks like, and —
just as important — what is explicitly *out* of scope. Short, and it should
change rarely; if it changes often, the project lacks direction. Its main job
is to settle "should we even be doing this?" arguments by pointing at the
agreed scope. Many small projects fold this into the top of the README, which
is fine until scope disputes start happening — then split it out.

### journal.md — the road, not just the destination (Session history)

The append-only, dated narrative of building the thing. **One entry per
working session.** This is the document most projects lack and most regret
lacking. It holds exactly what the state documents and even the decision log
cannot:

- What you actually did this session.
- What broke, and how you diagnosed it.
- The dead ends — things you tried that didn't work, and *why you abandoned
  them*.
- The wrong conclusions you reached and later corrected (these are gold —
  they stop you re-deriving the same mistake).
- The small gremlins (the environment-specific bug, the tooling quirk, the
  thing that confused you twice).
- Mistakes made by you or by tools/agents, recorded honestly.

**Why it's worth the discipline:** git records *diffs, not reasoning*; it's
keyed on *files, not episodes*; and a single session often touches several
documents, so reconstructing "what happened that afternoon" from git means
cross-referencing file histories by timestamp. The journal just *tells* you,
in order, in one place.

**The failure mode to avoid:** the empty journal with good intentions. A
journal you create and never write in is worse than none, because it implies a
record that doesn't exist. The fix: **seed it with the current session the
moment you create it.** Don't create an empty file — create it with a real
first entry describing the work that's fresh in your mind right now,
*including* whatever went sideways. Seeding the first entry with a mistake or a
dead end is ideal: it sets the precedent that the journal records the whole
truth, not just the wins.

Entry shape, roughly:

```
## 2026-05-22 — installed stable release, confirmed the speedup, nearly got it wrong

- Upgraded the serving layer; config survived, speedup carried over.
- Then a measurement saga: an extended sweep *looked* like the feature did
  nothing. Chased it. Turned out the metric included setup cost that
  dominated at scale — the feature was fine, the measurement was wrong.
- Also: a config toggle we assumed was being flipped between runs had never
  moved. Several "off" measurements were actually "on". Lesson logged.
- Tooling gremlin: multi-file downloads arrive zipped; confused us for a
  minute.
```

Notice that almost none of that is a "decision." It's all road. That's the
point.

### backlog.md — what might come next (fluid)

A loose, low-ceremony list of things you *could* do next, roughly ordered by
value. Not a roadmap, not a commitment. Cross items off (strikethrough) with a
one-line note on what came of them rather than deleting — that little bit of
retained "we did this, here's where it landed" is mild session history and
costs nothing. Drop items that no longer interest you, noting why so you don't
re-add them by reflex later.


## How to decide where a sentence goes

This is the actual daily skill. When you write a sentence of documentation,
ask in order:

1. **Is this describing what's true right now?** → a State doc (which one
   depends on whether it's orientation, architecture, status, scope, or an
   open question).
2. **Is this a deliberate choice someone will later question?** →
   `decisions.md`.
3. **Is this something that happened — a step, a bug, a dead end, a
   correction?** → `journal.md`.

The most common mistakes, and their fixes:

- *Writing history into a state doc.* "This used to use X but now uses Y" in
  the README or architecture doc. → The "now uses Y" part stays (state); the
  "used to use X, changed because…" goes to `decisions.md` (if it was a
  choice) or `journal.md` (if it was just an evolution).
- *Writing state into the journal.* Re-describing the whole current
  architecture in a session entry. → The journal says "refactored the storage
  layer, see architecture.md"; the architecture doc holds the current picture.
- *Editing the journal or changelog to "fix" an old entry.* → Never. History
  is append-only. If an old entry was wrong, write a new entry correcting it.
  The wrongness is itself part of the record.
- *Letting status.md accumulate dates.* → That's a journal trying to be born.
  Move the dated content to `journal.md` and let status.md snap back to a
  current snapshot.


## On the changelog-vs-journal question

Some projects keep a `changelog.md` (terse: "what changed, version by version")
*and* a `journal.md` (narrative: "what happened and how it felt to build").
Others fuse them into a single dated narrative log. Both are valid. The fork:

- **Fuse them** if your changelog entries are already narrative and a single
  person/small team maintains them. One file, less overhead, and the narrative
  doesn't get neglected. The risk of splitting is that the terse half becomes
  the only half anyone updates, and the texture is lost.
- **Split them** if you have a genuine need for terse machine-or-newcomer-
  readable release notes *separate* from the messy human story — e.g. a
  published library where users read the changelog but contributors read the
  journal.

When in doubt, fuse. It's easier to split a fused log later than to revive a
neglected journal.


## Mechanical discipline (the part that prevents disasters)

Documentation files — especially the long-lived ones like `decisions.md` and
`journal.md` — become some of the most valuable artifacts in the project.
Treat edits to them with the same care as edits to code:

- **Before committing an edit to a long doc, check the diff shape.** A doc edit
  that's meant to *add* content should show insertions far exceeding deletions.
  A large unexpected deletion count means you're about to overwrite or roll
  back something — stop and look. (A simple `git diff --stat` is enough.) This
  single check catches the most damaging documentation accident: silently
  reverting a file to an older version because you edited a stale copy.
- **Verify you're editing the current version, not a stale copy.** If you
  downloaded, exported, or otherwise round-tripped the file, confirm its size
  or line count matches what's committed before you start editing on top of it.
- **For append-only files, only ever append.** If a tool or agent proposes a
  change to `journal.md` that touches lines other than the new entry at the
  end, that's a red flag — review it.
- **When an agent edits a shared doc, have it show the diff before applying,
  and re-check after.** Agents (and humans) occasionally swallow a heading or
  a section while editing nearby. Reviewing the proposed diff catches it before
  it's committed; checking `git diff` after confirms disk matches intent.

These habits feel like overkill until the first time one of them saves you from
quietly deleting a month of decisions. They pay for themselves on that single
occasion.


## A minimal starting point

If all of this feels like too much for day one, start here and grow:

1. `README.md` — how to run it.
2. `decisions.md` — with a single entry D001 recording your first real choice,
   in the supersede-don't-edit format.
3. `journal.md` — created *with* a first dated entry describing today, dead
   ends included. Not empty.

Those three cover state (README), decision history (decisions), and session
history (journal) — the three axes. Add `architecture.md`, `status.md`,
`open_questions.md`, `charter.md`, and `backlog.md` as the project grows large
enough that cramming them into the README stops working.

The goal is never "lots of documentation." It's that **every piece of
information lives in exactly one place whose job it obviously is** — so that
both the person writing it and the person (or agent) reading it six months
later always know where to look.
