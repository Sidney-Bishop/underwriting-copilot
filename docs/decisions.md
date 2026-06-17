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

---

### D003 — Hybrid corpus: real public regulatory + synthetic for internal categories

**Date:** 2026-06-17
**Status:** Active
**Closes:** Q1

**Context:** The spec describes five question categories (Risk Appetite,
Delegated Authority, ESG, Regulatory, Internal Policy). Mapping these to
publicly available source documents revealed that only ESG and Regulatory have
substantial public corpora (reinsurer sustainability reports, PRA/EIOPA
guidelines, Lloyd's market bulletins). Risk Appetite statements, delegated
authority matrices, and internal underwriting guidance are not public — they
are internal to each reinsurer.

**Decision:** The corpus is **hybrid**: real public documents for ESG and
Regulatory categories; hand-authored synthetic documents for Risk Appetite,
Delegated Authority, and Internal Policy categories. Every document carries a
`provenance: real | synthetic` field at the metadata level (D006), inherited
by every chunk, and surfaced in citations.

**Rationale:** Pure real-public would have left two of the five spec categories
untestable, undermining the eval framework's coverage. Pure synthetic would
have lost the credibility that comes with answering questions grounded in
actual PRA / EIOPA / reinsurer documents. The hybrid path covers all five
categories AND turns provenance into a visible governance signal in the README
and citations — which is itself a Lead-level signal.

Alternatives considered and rejected:
- **Pure real-public:** missed two spec categories; no public source for risk
  appetite or delegated authority matrices.
- **Pure synthetic:** smaller credibility footprint, easier for an interviewer
  to dismiss as a toy.
- **Real-only with categories rewritten to fit:** would have meant changing
  the spec to match the corpus, defeating the purpose.

**Trade-offs / risks:** Synthetic documents need to be authored carefully —
bland LLM output would not stress-test the system as well as documents
containing deliberate contradictions and edge cases. Mixed provenance must be
honestly disclosed in the README and in citations.

**When to revisit:** If real internal reinsurer documents become available
(e.g. via the interviewing employer), shift to those and reduce the synthetic
share.

---

### D004 — Docling with OCR disabled for text PDFs

**Date:** 2026-06-17
**Status:** Active

**Context:** Docling's default `DocumentConverter` runs OCR on every page of
every PDF, regardless of whether the PDF actually contains scanned images. For
text PDFs (the entire current corpus, verified via `file`), this means: ~40MB
of OCR model weights downloaded on first run, ~60% additional ingestion time
per document, and per-page "empty result" warnings in stderr. The OCR did no
useful work.

**Decision:** Run Docling with `PdfPipelineOptions(do_ocr=False)` as the
project default. Re-enable OCR on a per-document basis only when ingestion
encounters a scanned PDF.

**Rationale:** All six current corpus PDFs are text — confirmed by `file`.
With `do_ocr=False`, EIOPA's ingestion dropped from 5.4s to 2.4s (~55%
reduction). The Chinese RapidOCR model auto-download is also tidied away. For
the synthetic documents we will author, OCR is irrelevant. The cost of
re-enabling OCR per-document later is one config line.

**Trade-offs / risks:** Any future scanned PDF added to the corpus will fail
silently (zero text extracted) until OCR is re-enabled for it. Mitigation: the
ingestion pipeline should sanity-check that each document yielded a
non-trivial amount of text, and fall back to OCR if not.

**When to revisit:** If a scanned PDF is added to the corpus, or if Docling
changes its default OCR behaviour.

---

### D005 — Probes in `scripts/probes/`, scratch outputs in `scratch/`

**Date:** 2026-06-17
**Status:** Active

**Context:** Exploratory scripts ("probes") are useful for validating
assumptions about an unfamiliar corpus or library before committing to
production code. They are not throwaway — the right probes become part of the
project's history of "how we validated each step." But they don't belong in
`src/` (they are not the product), and they should not live in `/tmp`
(invisible to git, lost on reboot, no record for future readers).

**Decision:** Probes live in `scripts/probes/`, numbered (e.g.
`01_docling_corpus_sweep.py`, `02_validate_metadata.py`) so their order is
preserved. The directory is committed to git. Their outputs go to `scratch/`,
which is gitignored.

**Rationale:** The numbered prefix means probes order naturally in directory
listings. Committed scripts mean an interviewer browsing the repo can see
exactly what was run to validate each design choice. Gitignored outputs mean
we don't pollute the repo with large or transient artefacts (Docling markdown,
histograms, etc.) — they are regenerable from the probes.

**Trade-offs / risks:** Probes accumulate over time. Eventually some will be
obsoleted by changes to the corpus or pipeline. They should be deleted (with
a journal note) when no longer informative, not left to rot.

**When to revisit:** If `scripts/probes/` grows past ~20 files, audit for
obsolete probes.

---

### D006 — Document metadata: hand-curated TOML, Pydantic-validated

**Date:** 2026-06-17
**Status:** Active

**Context:** Each corpus document needs metadata (issuer, type, jurisdiction,
effective date, version, topics, provenance, etc.) for retrieval filtering,
citation rendering, and governance disclosure. Three storage options were
considered: hand-curated single TOML, LLM-extracted per-document JSON
sidecars, or hybrid.

**Decision:** Single `corpus/corpus_metadata.toml`, hand-curated. Schema
defined as a Pydantic model in `src/underwriting_copilot/metadata.py`, loaded
and validated at ingest time. The schema includes a `superseded_by: str | None`
field, added during the curation pass after observing two real supersession
relationships in the corpus (PRA SS3/19 → SS5/25, PRA SS1/21 → SS1/22).

**Rationale:** At six documents, LLM extraction is theatre — we would spend
more time validating LLM output than typing the values ourselves. A single
TOML is easier to eyeball than scattered JSON sidecars, easier to git-diff,
and easier to keep consistent. Pydantic validation catches schema drift at
load time. Hand-curation also forced explicit thinking about every field's
value (e.g. the synonym pair `scenario_analysis` vs `scenario_testing` was
caught immediately and lodged as Q5).

Alternatives considered and rejected:
- **LLM extraction (Qwen3.6-35B + instructor):** overkill for six documents.
  Defer to a later D-entry if the corpus grows beyond the point of practical
  hand-curation.
- **Per-PDF JSON sidecars:** harder to maintain consistency, easier to forget
  a field on one doc.

**Trade-offs / risks:** Does not scale to hundreds of documents — but the
budget says ~12–20 documents total. When the corpus crosses ~50 docs, revisit.

**When to revisit:** Corpus grows past ~50 documents OR a real
interviewer-provided corpus appears that already has metadata in some other
format.

---

### D007 — Hierarchy-aware chunking with paragraph-fallback for thin-structure documents

**Date:** 2026-06-17
**Status:** Active

**Context:** The section-size probe (`scripts/probes/03_section_sizes.py`)
showed two distinct shapes in the corpus. Five of six documents have clean
heading hierarchies: EIOPA (57 sections), PRA SS5/25 (54), PRA SS3/19 (19),
Munich Re (312), Swiss Re (411). Soft-cap (>800 tokens) fires only 2% of the
time; soft-floor (<100 tokens) fires 46% of the time. The 6th document — PRA
SS1/21 — produced only 6 sections, the largest of which was 5709 tokens.
Inspection revealed it genuinely has thin heading structure: only 6 `##`
headings, no `###`, with body content using numbered paragraphs (1.1, 1.2,
...) and no sub-headings. Reading order is also scrambled by the "Superseded"
watermark splitting page layout.

**Decision:** The chunker has two modes, selected per-document based on
heading density:

1. **Hierarchy-aware mode** (default): one chunk per leaf section, merge
   upward aggressively when sections are below a token floor, split rarely
   when sections exceed a cap.
2. **Paragraph-fallback mode** (for thin-structure docs): split on
   numbered-paragraph patterns (e.g. `^\d+\.\d+\s`) within the nearest
   enclosing heading, treating each paragraph as a chunk and inheriting the
   surrounding heading as the section anchor for citation.

**Rationale:** A single-mode chunker (either pure hierarchy or pure
paragraph) would have failed on one or the other half of the corpus.
Hierarchy-only would have produced a 5709-token un-chunked blob for PRA
SS1/21. Paragraph-only would have lost the rich subsection citations
available from well-structured documents. The two-mode design is data-driven
from the section-size probe.

The "merge upward aggressively, split rarely" emphasis comes directly from
the probe data: 46% floor-fire vs 2% cap-fire means the chunking problem is
mostly about coalescing small sections, not splitting large ones.

**Trade-offs / risks:** Mode-detection rule is not yet specified — see Q6. A
naive heuristic could mis-classify documents on the edge of either shape. Eval
will catch this.

**When to revisit:** If the eval set reveals systematic mis-classification of
mode, or if Docling output quality changes such that thin-structure becomes
universal or rare.

<!-- Copy this shape for new decisions:

### D00X — <short title>

**Date:** YYYY-MM-DD
**Status:** Active | Superseded by Dxxx
**Supersedes:** Dxxx (optional)

**Context:** what situation prompted the decision.
**Decision:** what you chose, stated plainly.
**Rationale:** why — including alternatives considered and rejected.
**Trade-offs / risks:** what you're giving up or exposing yourself to.
**When to revisit:** the condition under which this should be reconsidered.
-->
