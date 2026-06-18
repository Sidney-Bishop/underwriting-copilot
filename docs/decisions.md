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
**Status:** Superseded by D008

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

---

### D008 — Chunker strategy refined: per-section fat-leaf detection

**Date:** 2026-06-17
**Status:** Active
**Supersedes:** D007
**Closes:** Q6

**Context:** D007 committed to a two-mode chunker with mode selected
per-document. Q6 asked the specific mode-detection heuristic. Three
candidates were considered: (a) heading-density threshold computed
per-document, (b) post-extraction per-section check (if a leaf section
exceeds a token cap, re-split that section in paragraph mode),
(c) per-document explicit declaration in `corpus_metadata.toml`.

While drafting these candidates it became clear that D007's per-document
framing was unnecessary. The two strategies (hierarchy-aware default;
paragraph-fallback for thin sections) can be applied **per-section** rather
than per-document, with simpler implementation and equivalent or better
behaviour:

- For PRA SS1/21, every body section individually exceeds the cap (the
  largest is 5709 tokens), so paragraph-fallback fires document-wide — the
  same outcome D007's per-document framing would have produced.
- For Munich Re and Swiss Re, only the genuinely fat sections trigger
  paragraph-fallback while the rest of the document keeps clean
  hierarchy-aware chunking — strictly better than the all-or-nothing
  per-document framing would have allowed.

**Decision:**

- The chunker always extracts sections by heading first.
- For each extracted leaf section, apply per-section strategy:
  - If section size **> soft cap (default 1500 tokens)**: re-split using
    paragraph-fallback (split on numbered-paragraph patterns like
    `^\d+\.\d+\s`; if no such pattern is found, fall back to splitting on
    paragraph blank-lines).
  - If section size **< soft floor (default 100 tokens)**: merge upward
    into the parent section.
  - Otherwise: emit the section as a single chunk.
- Every chunk inherits the document-level metadata (D006) and gains a
  `section_path` field recording its position in the heading hierarchy for
  citation.

**Rationale:**

- Per-section is data-driven — each section's actual size decides the
  strategy, no a-priori classification needed.
- It collapses the implementation to one chunking pipeline with branching
  per section, rather than two modes plus a selection layer.
- Thresholds (1500/100) come from Probe 03's data. The corpus has a clean
  separation: Swiss Re max is 1948, PRA SS5/25 max is 1551, no other doc
  exceeds 1128. A 1500-token cap captures only the genuinely-fat sections
  while leaving normal sections untouched, matching the observed ~2% cap-
  fire rate. The 100-token floor matches the observed 46% floor-fire rate,
  i.e. the actual chunking problem.

Alternatives rejected:
- **(a) Per-document heading-density:** vague (no notion of "page" in
  markdown), fails on heterogeneous documents (e.g. well-structured early
  chapters and thin later ones in the same file).
- **(c) Metadata declaration:** moves a code judgment into hand-maintained
  metadata; easy to forget when adding documents, invisible to readers of
  the chunker code.

**Trade-offs / risks:** Thresholds are heuristic. A document with one
legitimate 1600-token discussion (e.g. a long preamble) would get
unnecessarily paragraph-split. Acceptable: paragraph-split chunks are still
citeable at finer granularity, and the eval will catch any retrieval quality
drop. Thresholds are constructor args, so tuning is cheap.

**When to revisit:** If eval shows systematic over- or under-firing of
paragraph-fallback, or if a new document type appears with section sizes
outside the current corpus distribution.

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


## D009 — BGE-M3 dense via mlx-embeddings + BM25 sparse via Qdrant native sparse vectors

**Date:** 2026-06-18  
**Status:** Active

### Decision

Hybrid retrieval over two channels indexed in Qdrant:

1. **Dense channel** — BGE-M3 (`BAAI/bge-m3`) via `mlx-embeddings`. 1024-dim vectors. Apple Silicon native, consistent with the local-first MLX stack established by D004 and the broader project orientation.
2. **Sparse channel** — BM25 sparse vectors computed via `rank-bm25` over the corpus vocabulary, indexed in Qdrant's native sparse vector field.

Fusion: Reciprocal Rank Fusion (RRF) at query time via Qdrant's hybrid query API.

### Why not BGE-M3's full multi-functionality (dense + learned sparse + ColBERT)?

BGE-M3 produces three vector types from one forward pass, but only via:

- **`FlagEmbedding`** (PyTorch/MPS) — canonical implementation. Breaks the MLX-everywhere stack, heavier dependency surface, slower on Apple Silicon than MLX would be in our environment.
- **ONNX runtime** — works, but new ecosystem dependency and more debugging surface for the project budget.

The MLX packages (`mlx-embeddings`, `mlx-embedding-models`) load BGE-M3 as a standard XLM-RoBERTa encoder. The sparse linear+ReLU head and ColBERT projection head are model-specific and not implemented in either package. Going via MLX means dense-only.

BM25 substitution sacrifices BGE-M3's learned sparse term weights. At a 6-document, 461-chunk corpus, the gap between learned-sparse and BM25 is small in expectation. RRF fusion with dense gives industry-standard hybrid retrieval performance.

ColBERT-style late interaction is deferred (see Q7). If eval reveals retrieval ceiling effects on Day 3, FlagEmbedding becomes a candidate for revisitation.

### Why Qdrant native sparse, not client-side fusion?

Qdrant supports sparse vectors as a first-class type since v1.7. Keeping both channels in Qdrant means one storage system, one query path, and one set of operational concerns. Client-side fusion would require maintaining a separate sparse store and lose Qdrant's hybrid-query optimisation.

### Operational notes

- Dense vector dim: 1024 (BGE-M3 standard).
- Sparse representation: `(indices[], values[])` pairs in Qdrant's native sparse vector format.
- BM25 parameters: defaults (`k1=1.5`, `b=0.75`) until eval suggests tuning.
- BM25 vocabulary computed at index time over the full corpus; query-time uses the same vocabulary.
- Last-checked: `mlx-embeddings` v0.1.0 on PyPI (Blaizzy/mlx-embeddings), supports XLM-RoBERTa architecture which BGE-M3 derives from.


## D010 — BGE-M3 dense embeddings use CLS-pooled + L2-normalised, not `text_embeds` mean-pooled

**Date:** 2026-06-18  
**Status:** Active

### Decision

For dense embeddings produced by BGE-M3 via `mlx-embeddings`, use:

```python
cls_raw = outputs.last_hidden_state[:, 0, :]            # CLS token
vec = cls_raw / mx.linalg.norm(cls_raw, axis=-1,
                               keepdims=True)            # L2 normalise
```

**Not** `outputs.text_embeds` (which `mlx-embeddings` produces as mean-pooled + normalised by default for XLM-RoBERTa-family models, including BGE-M3).

### Rationale

The BGE-M3 paper specifies CLS-token pooling with L2 normalisation as the canonical dense embedding strategy. The `mlx-embeddings` package defaults to mean pooling for XLM-RoBERTa, and the `mlx-community/bge-m3-mlx-fp16` model card example follows that default. Both would silently produce a sub-optimal embedding for BGE-M3 specifically.

Probe 07 measured cosine similarity between the two pooling strategies across five chunks spanning all six corpus documents:

| Chunk source | cos(cls, text_embeds) |
|---|---|
| EIOPA Guidelines | 0.6265 |
| Munich Re Sustainability 2023 | 0.7391 |
| PRA SS1/21 Operational Resilience | 0.6170 |
| PRA SS3/19 Climate | 0.6991 |
| PRA SS5/25 Climate | 0.7533 |
| **mean** | **0.6870** |

The probe's pre-declared interpretation thresholds: > 0.95 → pooling choice is low-stakes; < 0.80 → the choice substantively shapes the representation. **0.687 is well below the lower threshold** — the two strategies produce meaningfully different vectors. Following the BGE-M3 paper is the safe call.

### Trade-offs and notes

- The penalty for using `text_embeds` would be silent: retrieval would still *work*, but at lower quality than the model was tuned for. The kind of error that wouldn't surface until eval on Day 3 and might still pass eval while capping the retrieval ceiling lower than necessary.
- Re-embedding the full corpus (~31s on the M5 Max per Probe 07) is cheap enough that this decision is revisitable if Day 3 eval surprises us.
- The CLS+L2 logic lives in a small named helper in the forthcoming `src/underwriting_copilot/embed.py`. Unit tests pin its shape (vector dim, unit norm) so a future refactor can't silently revert to mean pooling.
