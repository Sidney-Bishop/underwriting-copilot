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


## D011 — BM25 sparse channel: word-level tokenisation + Porter stemming + minimal stopwords + corpus-wide vocabulary

**Date:** 2026-06-18  
**Status:** Active

### Decision

The sparse channel referenced in D009 is implemented as classical BM25 with these specifics:

1. **Tokenisation:** word-level via regex `\b\w+\b` on lower-cased text.
2. **Stopwords:** small hand-curated list (~30 high-frequency function words), removed before stemming.
3. **Stemming:** Porter algorithm via the `snowballstemmer` package.
4. **Vocabulary scope:** corpus-wide. Built once at index time from all 461 chunks, persisted as `corpus/bm25_vocab.json`.
5. **BM25 parameters:** `k1=1.5`, `b=0.75` (canonical defaults). Tune at Day 3 eval if needed.
6. **Implementation:** write the BM25 scorer ourselves (~50 lines), no `rank-bm25` dependency.

### Sparse-vector construction

Standard Qdrant pattern, nailed down here so retrieval code can be unambiguous:

- **At index time** (per chunk `c` with tokens `T_c`):
  ```
  sparse[c] = {
      vocab_id[t]: idf(t) * (tf(t, c) * (k1 + 1))
                   / (tf(t, c) + k1 * (1 - b + b * |c| / avgdl))
      for t in T_c
  }
  ```
- **At query time** (query tokens `T_q`):
  ```
  sparse[q] = {vocab_id[t]: 1.0 for t in T_q if t in vocab}
  ```
- Qdrant computes the inner product between query and indexed sparse vectors — by construction, that inner product equals the BM25 score.

### Why word-level tokenisation, not BGE-M3's XLM-RoBERTa subword tokenizer?

Tempting because it would reuse the same vocabulary as the dense channel (~250k subwords, zero OOV, no extra dependency). Rejected because BM25's underlying intuition is "how often does this **term** appear", and subwords break that.

In SentencePiece, `regulator`, `regulators`, and `regulating` tokenise into different subword sequences. BM25 would treat them as distinct terms and miss the lexical match they should obviously satisfy. The whole reason to *have* BM25 alongside dense is to capture exact-term matching that subword embeddings smooth over — using subwords for both channels collapses their distinctness.

### Why Porter stemming, not full lemmatisation (spaCy / NLTK)?

Regulatory text has many morphological variants where the underlying term is the same: guideline/guidelines, supervisory/supervise, test/testing/tested, climate/climatic. Without stemming, BM25 misses these matches entirely.

Porter stemming is the standard, ships as a tiny pure-Python package (`snowballstemmer`, no data files), and gives ~80% of lemmatisation's benefit at ~1% of the cost. Full NLP pipelines (spaCy POS tagging + lemmatisation, NER, dependency parsing) add hundreds of MB of model weights and milliseconds per chunk for capabilities we don't need.

### Why a minimal stopword list (~30 words), not NLTK's 179-word default?

Aggressive stopword removal strips meaningful tokens from technical regulatory phrases like "in accordance with", "to the extent that", "subject to". These multi-word constructions carry actual regulatory meaning that lives partly in the connective words.

The minimal list targets unambiguous noise (the, a, an, and, or, but, of, in, on, at, to, for, is, are, was, were, be, been, this, that, these, those, it, as, by, with, from, into, etc.). Bias when in doubt: keep the word. BM25's IDF handles common terms anyway — true noise gets near-zero IDF and contributes nothing.

### Why corpus-wide vocabulary, not per-document?

IDF requires global statistics: `idf(t) = log((N - df(t) + 0.5) / (df(t) + 0.5) + 1)` where `N` is the corpus size and `df(t)` is the document frequency of term `t`. Per-document vocabularies don't have a meaningful IDF — every term is "rare in this document" or "common in this document", which doesn't help retrieval.

### Why roll our own BM25, not `rank-bm25`?

`rank-bm25` exposes a query → top-k scoring API. We need something different: per-(term, chunk) BM25 *contributions* as sparse-vector values to upsert into Qdrant. Reimplementing the BM25 formula and its statistics-gathering pass is ~50 lines, fully unit-testable, and removes a third-party dependency from the retrieval-critical path. The wrap-around-the-library option would require post-processing internal `rank-bm25` state, which is more fragile than computing the same thing directly.

### Trade-offs and notes

- **Stopword bias toward inclusion** means the vocabulary will be larger than strictly necessary. Disk and memory are not a concern at our corpus scale; retrieval quality is.
- **Vocabulary refresh:** must rebuild when the corpus changes (e.g. synthetic documents added per D003). The build step is fast (~seconds), so this is operational discipline, not architecture.
- **BM25 parameters frozen at defaults** until eval. Resist the temptation to tune them by feel — without a ground-truth query set, parameter changes are noise.
- **Tokenisation is asymmetric** by design: index-time builds full BM25 contributions; query-time uses presence indicators only (value 1.0 per query term). This is the canonical Qdrant BM25 pattern and matches what Qdrant's internal BM25 fastembed model does.

### When to revisit

- Day 3 eval — if the sparse channel underperforms expectations on the benchmark, candidates to adjust are (in order of effort): BM25 parameters, stopword list, then tokeniser (only as a last resort).
- If synthetic documents per D003 substantially change the corpus shape (e.g. lots of new abbreviations or product names), the stopword list may need expansion.


## D012 — Index module design: full-text payload, scratch-located Qdrant, one-shot rebuild

**Date:** 2026-06-18  
**Status:** Active

### Decision

Three sub-decisions for `src/underwriting_copilot/index.py`:

1. **Payload schema includes the chunk text.** Each Qdrant point's payload carries the 16 fields needed for retrieval-time filtering, citation rendering, and inspection — *including* the chunk's full text. Retrieval is then self-contained: one Qdrant query returns everything needed to render a cited answer, no second-pass lookup.

2. **Persistent Qdrant data lives at `scratch/qdrant/`.** Derived data, gitignored, regeneratable from chunks + embeddings + metadata. Matches the existing convention for `scratch/chunks/` and `scratch/embeddings/`.

3. **One-shot wipe-and-rebuild on every run.** If `scratch/qdrant/` exists when `index.py` runs, it is removed and the collection is built fresh. Simple, deterministic, idempotent.

### Payload field list

```
chunk_id              # unique per chunk; matches the chunk JSONL id
document_id           # links to corpus_metadata.toml entry
title                 # human-readable document name (from metadata)
issuer                # full organisation name (from metadata)
issuer_type           # "regulator" | "reinsurer" (from metadata)
jurisdiction          # ISO code or jurisdiction tag (from metadata)
document_type         # supervisory_statement | guideline | sustainability_report
effective_date        # ISO date (from metadata)
version               # optional version string (from metadata)
superseded_by         # optional document_id of successor (from metadata)
source_url            # citation URL (from metadata)
topics                # list of topic tags (from metadata)
section_path          # list[str] from the chunker
merged_section_paths  # list[list[str]] if this chunk absorbed others (D008)
chunk_strategy        # hierarchy | paragraph_fallback | merged (from D008)
token_count           # int (from the chunker)
text                  # the chunk's full text content
```

`issuer_type` is now read from the Pydantic metadata model — fixes the prefix-lookup shortcut Probe 08 used and removes a duplication of knowledge.

### Why text-in-payload, not lean-payload-plus-lookup?

The lean alternative would strip `text` from the payload and have `retrieve.py` perform a second-pass lookup against `scratch/embeddings/*.jsonl` or `scratch/chunks/*.jsonl` to fetch text for the top-k hits.

Trade-offs:

- **Storage:** including text adds ~1 MB to the Qdrant collection. Negligible at corpus scale; we are not RAM-constrained.
- **Retrieval simplicity:** self-contained retrieval is one query, no joins, no path coupling. Simpler code, fewer failure modes.
- **Coupling:** lean payload would require `retrieve.py` to know about the path layout of `scratch/`, hard-coding what is currently a probe-and-pipeline implementation detail.

For a 5-day artefact, the simplicity win is decisive. A real production system at 100× scale would revisit.

### Why `scratch/qdrant/` and not `corpus/qdrant/`?

The Qdrant index is fully derived: given the chunks (from the chunker), the dense embeddings (from `embed.py`), the BM25 vocab (from `bm25.py`), and the corpus metadata, the index is a deterministic function. Same logic as `scratch/embeddings/`.

D011 separately specifies `corpus/bm25_vocab.json` as the BM25 vocab location. The inconsistency is real but deliberate: the BM25 vocab is small, text-format, and useful to commit as part of the corpus's interpretation. The Qdrant store is large, binary, and a pure runtime artefact. Splitting them is honest.

### Why one-shot rebuild instead of incremental?

For Day 2:

- **Speed:** full rebuild over 461 chunks should be a few seconds (Probe 08 showed 0.42s for 10-point upsert with embedding). At full scale this is ~10-20s. Cheaper to rebuild than to maintain incremental-correctness invariants.
- **Determinism:** every run produces an identical collection state. No "what's in there now?" mental load when iterating on schema or BM25 parameters.
- **Idempotence:** re-running `python -m underwriting_copilot.index` is always safe. No `--force` flag needed.

Day 4+ if the corpus grows (synthetic documents per D003) and rebuild becomes slow, incremental upsert becomes attractive. Until then, the simplicity of "delete and rebuild" wins.

### Trade-offs and notes

- **Payload size:** all 17 fields per point × 461 points. Worst case (Munich Re full chunks at 1500 tokens, plus metadata) ≈ 8 KB per point ≈ 4 MB collection-wide. Still negligible.
- **No collection-time payload indexes** in this version. Qdrant supports per-field payload indexes for fast filtering on `keyword` / `integer` / `datetime` fields; we'll add these only if retrieval latency reveals filtering bottlenecks. Premature optimisation otherwise.
- **`scratch/qdrant/` survives across runs by design.** Existence is checked at start of `index.py`; if present, removed before rebuild. The directory itself is gitignored.

### When to revisit

- If retrieval latency on filtered queries (`issuer_type=regulator`, `superseded_by IS NULL`) exceeds a useful threshold (say >50ms p95), add Qdrant payload indexes on the filtered fields.
- If the corpus grows past ~10× current size (4-5k chunks), revisit the wipe-and-rebuild approach in favour of incremental upserts.
- If retrieve.py's second-pass lookup pattern (text from somewhere else) becomes useful for a reranker or a streaming demo, revisit lean payload.


## Q8 — Does the exclude_superseded default leave coverage gaps when the successor isn't in the corpus? Is SS1/22's relationship to SS1/21 actually supersession?

**Date:** 2026-06-18  
**Status:** Closed 2026-06-18 — SS1/21 metadata corrected (SS1/22 is unrelated 'Trading activity wind-down'); SS3/19 → SS5/25 verified correct (replaces in entirety, 3 Dec 2025).

### Background

D012 made `exclude_superseded=True` the default for `retrieve.py`, on the policy that surfacing legacy guidance to underwriters is risky in production. The first end-to-end demo (2026-06-18, three queries, top-5 each) confirmed the filter works as designed: zero hits from PRA SS3/19 (superseded by SS5/25 per the metadata) and zero hits from PRA SS1/21 (superseded by SS1/22 per the metadata).

Two concerns surface:

1. **Coverage gap in the demo corpus.** SS1/22 is not in our corpus. So by marking SS1/21 as superseded, we have hidden the only operational-resilience-dedicated document from default-mode retrieval — leaving only the brief mentions of operational resilience inside SS5/25 (climate context). Query 2 of the demo (operational resilience + third-party risk) bears this out: no SS1/21 results, and the top hits were climate-document mentions of operational resilience rather than the dedicated guidance.

2. **Is "superseded_by" the right semantic for SS1/21 → SS1/22?** The metadata field implies one-document-replaces-another. PRA supervisory statements are not always replaced by their successors — sometimes a new SS *amends* or *updates* an earlier one without fully replacing it. If SS1/22 is an amendment rather than a replacement, the metadata is overstating the relationship.

### Resolution criteria

- **Step 1:** Verify what SS1/22 actually does to SS1/21 (Bank of England supervisory statement page lookup).
- **Step 2A (if SS1/22 fully supersedes):** Either add SS1/22 to the corpus during Day 4/5 expansion (per D003), or accept the gap and document it explicitly in `evaluation.md` so Day 3 eval scores on operational-resilience queries are interpreted with the gap in mind.
- **Step 2B (if SS1/22 only amends):** Change the metadata field semantics — drop `superseded_by` for SS1/21, or introduce a separate `amended_by` field that doesn't drive the `exclude_superseded` filter.

### When to revisit

- **Before Day 3 eval design.** If we plan benchmark queries that expect SS1/21 to surface (operational resilience, third-party risk, impact tolerances), the metadata needs to be honest first — otherwise we'll be measuring filter behaviour rather than retrieval quality.
- **During Day 4/5 corpus expansion** if we add real-or-synthetic operational resilience material that closes the gap.

### What this is not

This is not a bug in `retrieve.py` or in the filter logic. The filter does exactly what D012 said it should. The question is whether the metadata feeding the filter is *factually accurate* — and whether the policy (silently hide superseded docs by default) plays well with a corpus that is not yet complete.


## D013 — answer.py design contracts: citation format, refusal phrase, model+endpoint configurability

**Date:** 2026-06-18  
**Status:** Active

### Decision

Four contract-shape decisions for `src/underwriting_copilot/answer.py`:

1. **Citation format: `[chunk_id]` inline with claims.** The exact bracket-and-id form is the contract between the prompt template (which tells the LLM to use this format) and the citation validator (which parses it back out). Changing the format requires changing both sides.

2. **Refusal phrase: exact match of "I cannot answer this from the provided sources."** When retrieved chunks don't contain sufficient information to answer, the LLM must respond with this exact sentence. The detector matches on this exact string (after stripping trailing whitespace/punctuation) for the `refused=True` signal. The prompt template instructs the LLM in these exact words.

3. **Citation validation guardrail.** Every `[chunk_id]` cited in the answer must exist in the set of chunks fed to the LLM. Any citation pointing to a chunk_id that wasn't in the context is recorded as a `hallucinated_citation` — a quality signal the Day 3 eval harness will score against.

4. **Model + endpoint injected at construction.** `AnswerGenerator(retriever, model="...", api_base="...")` — no hardcoded model name. Day 3's eval harness will sweep across multiple models per D003 and Q9, so model-id-as-constructor-arg is the architecturally honest choice from day one. Defaults: model `Qwen3.6-35B-A3B-4bit` (in the served roster, known-good for instruction-following); endpoint `http://127.0.0.1:8080/v1` (mlx-lm.server default). Both overridable.

### Why these specific choices

- **Citation format `[chunk_id]`**: simple, regex-parseable, and unlikely to appear naturally in regulatory text. Alternative forms (`{chunk_id}`, `<cite>...</cite>`) add complexity without benefit at this stage.
- **Refusal phrase exact-match**: fuzzy refusal detection (e.g. semantic similarity against "I don't know") is more robust but introduces ambiguity. Exact-match makes eval-harness scoring deterministic. The cost is that the LLM must follow the format precisely; the prompt is unambiguous about this.
- **Hallucinated-citation detection**: the main guardrail against LLM confabulation. Even a perfectly-formatted citation is worthless if it doesn't reference a real chunk. One set-membership test per citation; cheap.
- **Configurability**: hardcoding the model in `answer.py` would force code edits to swap models during eval, which conflicts with the project's own Day 3 architecture. Model name and URL belong in runtime config, not in code.

### Non-goals (deferred, not in answer.py)

- Streaming responses (no UX in scope yet).
- Multi-turn conversations (single-shot Q→A only).
- Reranking (Q7's territory; revisit if eval shows ceiling).
- LLM-as-judge scorers (Day 3 eval may add; not part of `answer.py`).

### Trade-offs

- **Exact-match refusal phrase is brittle.** If the LLM produces "I cannot answer this from the provided sources" with a different terminal punctuation or wraps it in extra words, exact match fails. Mitigation: prompt is unambiguous; detector strips trailing whitespace and `.!?` before comparing.
- **Hardcoded citation format taxes smaller models.** If eval shows format-drift failures (e.g. uses `(chunk_id)` instead of `[chunk_id]`), the prompt needs tightening, not the format relaxed — relaxing makes the parser ambiguous against naturally-occurring brackets in text.

### When to revisit

- If eval shows >10% of otherwise-valid answers scored as "no citations" because of format drift: revisit prompt strictness, not parser tolerance.
- If a different model is selected as default and produces refusals with different phrasing: update prompt and detector together (they are one contract).
- If multi-turn conversations become a requirement (post-Day-5): this entire module is single-shot and a new wrapper would be needed.


## Q9 — Should we pull a 7-14B-class instruction-tuned model before the Day 3 eval harness runs?

**Date:** 2026-06-18  
**Status:** Open

### Background

The Cedant brief observes that for constrained extract-and-synthesise-with-citations tasks, a well-tuned 7-14B model will often outperform a less-tuned larger model. Disciplined instruction-following matters more than raw reasoning capacity for this specific task shape (single-shot, small context, strict format rules, refuse-on-insufficient-context).

The current served oMLX roster (per commit `2991730`, snapshot 2026-06-08) does not include a clean candidate in the 7-14B range. The Gemma 4 family on disk is 26B (A4B) and 31B; no Qwen3-8B; no Gemma 4 12B IT.

For today's Day 2 demo, `answer.py` defaults to `Qwen3.6-35B-A3B-4bit` per D013 — well above the brief's sweet spot but served, instruction-following, and known-good.

### Resolution criteria

Before the Day 3 eval harness sweep is designed:

- **Step 1.** Decide whether to pull a 12B-class instruction-tuned MLX-quantised model (e.g. Gemma 4 12B IT, Qwen3-7B/14B variants). Estimated cost: 15-30 minutes of `huggingface-cli download` plus an oMLX config entry. Reversible.
- **Step 2A (if pulled):** include it in the Day 3 eval sweep alongside Qwen3.6-35B-A3B-4bit so the brief's prediction about the sweet spot is tested empirically. This is the load-bearing data point — if a 12B beats 35B on Cedant's metrics, the brief's claim is validated; if it doesn't, the project's model-sizing intuition is wrong for this corpus.
- **Step 2B (if not pulled):** document in `evaluation.md` that the eval was run only against served models in the ≥26B class. Note that the brief's 7-14B-sweet-spot claim was not tested for this corpus, so any conclusion about model size is unsupported.

### When to revisit

- **Day 3 morning, before designing the eval sweep matrix.** The decision is cheap to make and cheap to reverse, but it shapes the Day 3 eval's headline finding.


---

## D014 — Day 3 eval harness design: plain Python, sweep over {models} × {prompts}

**Date:** 2026-06-18
**Status:** Decided

The Day 3 eval harness is plain Python — no DSPy or other prompt-optimization framework — and measures the AnswerGenerator pipeline across a benchmark of 40+ questions with gold-standard chunks. The harness produces per-question results that are reduced to per-cell summaries across a sweep grid.

**Measurement axes** (all per-question, aggregated per-cell):

- `citation_accuracy` — fraction of cited chunks that are (a) in the retrieved context (already handled by `validate_citations`) AND (b) actually support the claim they're attached to. The (b) check is gold-labeled, not LLM-judged, in v1.
- `hallucinated_citation_count` — chunk_ids cited but absent from retrieved context. Already produced by `validate_citations`.
- `refusal_precision_recall` — for each question, gold-label whether it should be refused; measure refusal correctness against that label.
- `latency_p50_p95` — wall-clock per question, from `AnswerResult.elapsed_seconds`.

**Sweep grid for the Day 3 run.** At minimum 2 × 2:

- models: `gemma-4-31B-it-MLX-6bit`, `Qwen3.6-35B-A3B-4bit` (with `enable_thinking=False`)
- prompts: v1 (current — has the literal `[chunk_id]` placeholder name that Qwen echoed two different ways), v2 (uses `[<ID>]` metasyntax + one concrete worked example to remove the echo trap)

Q9 may add a 12B-class IT model as a third row if one is pulled before the eval runs.

**Why plain Python first, not DSPy.**

1. The eval harness is the project's measurement infrastructure. It must work whether or not DSPy integrates cleanly with oMLX.
2. The metric function we write here is reusable as a DSPy metric later — building it without the framework keeps measurement quality and framework quality as independent variables we can debug separately.
3. The 2×2 sweep directly tests Interpretation A vs B (family-axis finding as model property vs prompt artifact). DSPy adds nothing to that specific question and would obscure it.

**Architectural location** (initial proposal, subject to refinement at implementation time):

- `eval/benchmark.toml` — benchmark questions, gold chunks, expected_refusal flags
- `eval/scorer.py` — per-question scoring; the metric function
- `eval/runner.py` — sweep loop over models × prompts × questions, writes per-cell JSON
- `eval/report.py` — reduces JSON to a comparison table
- `eval/results/<timestamp>/` — gitignored raw outputs

**Falsification criterion for the family-axis finding** (per the Day 3 preliminary journal entry, proposed thresholds): if Qwen3.6 with prompt v2 closes the gap to Gemma to within 10 percentage points on `citation_accuracy` AND `hallucinated_citation_count` drops to within 2× Gemma's, the family-axis claim gets weakened or retracted in the final Day 3 journal entry. Thresholds may be refined when the harness lands and we see the shape of the baseline data.

---

## Q10 — DSPy/GEPA prompt optimization layer

**Date:** 2026-06-18
**Status:** OPEN
**Phase:** Day 4–5, gated on D014 results

After D014's plain-Python eval harness lands and the 2×2 sweep runs, the open question is whether to layer DSPy's GEPA optimizer on top to test whether prompt optimization can close the family-axis gap.

**The hypothesis Q10 tests.** The Day 2 N=3 finding (family axis appears more decisive than size axis on rigid-format tasks) has two competing interpretations:

- **Interpretation A (model property):** Qwen3.6-35B-A3B has weaker rigid-format discipline than Gemma-4-31B-it irrespective of prompt; prompt tuning helps marginally; model selection is the dominant lever.
- **Interpretation B (prompt artifact):** Our v1 prompt has an ambiguity (the literal `[chunk_id]` placeholder name) that Gemma was robust to but Qwen exploited; with a better prompt Qwen might match Gemma.

D014's 2×2 sweep gives a first answer (hand-designed v2 vs v1). GEPA goes further: rather than hand-designing v2, let GEPA's reflection LM propose prompt variants per-model and see whether any closes the gap. This tests Interpretation B at its strongest.

**Phased plan.**

- **Phase 1 (Day 3, D014):** Plain-Python harness + 2×2 sweep. Outcome determines whether Phase 2 is exploratory or load-bearing.
- **Phase 2 (Day 4 or Day 5, this Q10):** Wrap `AnswerGenerator`'s prompt step as a `dspy.Module`. Reuse D014's scorer as the DSPy metric with text feedback added. Run GEPA (`auto="light"`, ~6 candidate prompts) against Qwen3.6 specifically.

**Sub-questions to resolve before Phase 2.**

- **Q10.1 — Reflection LM choice.** Local Gemma-4-31B-it (matches local-first pitch, weaker reflector), local Qwen3.6 with thinking on (reasoning-style models may reflect well, untested), or remote Claude/GPT-4 via API (best reflectors, breaks local-first). Default to local Gemma unless a probe shows it's too weak.
- **Q10.2 — LiteLLM ↔ oMLX integration.** Verify LiteLLM's OpenAI-compatible client passes `extra_body.chat_template_kwargs.enable_thinking` through to oMLX correctly. 30-minute probe before any heavy commitment to DSPy.
- **Q10.3 — Text-feedback metric depth.** Hallucinated_citation_count and refusal correctness signals are straightforward. The "you cited X but the claim about Y isn't in X" signal requires either gold-labeled claim-to-chunk alignment or an LLM judge. Defer the LLM-judge variant unless Phase 1 results suggest it would change the answer.

**Resolution paths.**

- If D014's prompt v2 closes the Qwen-Gemma gap (per the criterion in D014), Q10 becomes curiosity-driven. GEPA may still be worth running for Day 5 narrative ("systematic optimization beat hand-tuning") but isn't load-bearing.
- If D014's prompt v2 does not close the gap, Q10 becomes the next honest experiment: GEPA's reflection loop is precisely the tool for finding prompts hand-iteration misses.
- If GEPA closes the gap, Interpretation B is supported and the family-axis claim retracts. If GEPA fails to close the gap, Interpretation A is hardened — and the cross-project note delivered to `tst_llm` becomes a more confident finding too.


---

## Q9 — CLOSED 2026-06-18 (DEFERRED, not RESOLVED)

**Original question (re-stated for clarity):** should we pull a 7-14B-class instruction-tuned MLX model before designing the Day 3 eval sweep, to test the brief's "sweet spot" hypothesis against the 31B-class winner from Day 2's preliminary finding?

**Resolution: deferred to future work.** The 7-14B sweet spot is empirically untestable on the current serving stack within the 5-day timeline.

**What we tried.** Pulled `mlx-community/gemma-4-12B-it-8bit` and `lmstudio-community/gemma-4-12B-it-MLX-8bit` from HuggingFace via oMLX 0.4.1's downloader. Both downloads completed cleanly (12.4 GB each, no checksum issues). Both failed to load on the `/v1/chat/completions` endpoint with identical errors:

```
Model type gemma4_unified not supported.
Error: No module named 'mlx_vlm.speculative.drafters.gemma4_unified'
VLM loading failed; LLM fallback also failed.
```

The currently-working `gemma-4-31B-it-MLX-6bit` is the *same* `gemma4_unified` architecture and loads cleanly. Both failures are size-specific within oMLX's loader, not architecture-specific.

**Root cause not pinned.** Two equally plausible hypotheses from outside oMLX's source:
- Speculative-drafter wiring exists for the 31B but not the 12B in our installed `mlx_vlm` version.
- Size-specific config-key handling (head_dim, num_kv_heads, intermediate_size scaling) hardcoded per-size and not generalised to the 12B yet.

The symptom is identical under both. We did not investigate further given the project timeline.

**Three unblocking paths considered (none pursued):**

1. **Upgrade oMLX / mlx_vlm.** Days-long timeline plus risk of breaking the rest of the served roster. Out of scope.
2. **File an upstream bug.** Days-to-weeks resolution timeline. Out of scope.
3. **Swap serving backend for the 12B row only.** llama.cpp loads `gemma4_unified` GGUFs without the `mlx_vlm` dependency, and the same IT 12B is widely available as GGUF. Cost: two backends to maintain, latency comparisons confounded by backend differences. Plausible follow-up if the size-axis question becomes load-bearing in future work; not justified for the 5-day interview artefact.

**Day 3 eval re-scope.** The 2×2 matrix from D014 ({Gemma 4 31B IT, Qwen3.6 35B-A3B with thinking off} × {prompt-v1, prompt-v2-fixed}) is the eval, unchanged. No size-axis row. The brief's 7-14B sweet spot hypothesis is recorded as **flagged-but-untested on this stack**, distinct from rejected.

**Cleanup recorded:** broken model directories removed from `~/.lmstudio/models/`. oMLX served roster down to 12 models (was 14 transiently).

**Cross-project note.** `tst_llm_journal_snippet.md` (the staging artifact for the next `tst_llm` session) updated to record that the size axis is confirmed untestable on the current oMLX 0.4.1 + mlx_vlm stack. Real infrastructure intelligence for that project's roster planning.


---

## Q10 — STATUS AMENDED 2026-06-18 (now EXPLORATORY)

**Original status:** OPEN, Phase 2 gated on D014 results.

**Update:** Per D014's resolution criteria, "if prompt v2 closes the Qwen-Gemma gap, Q10 becomes curiosity-driven." It has. The Day 3 sweep showed prompt v2 closes 89% of the v1 gap (Qwen citation_recall 0.481 → 0.750, Gemma unchanged at 0.782), with within-document parity at 0.929/0.929 across 21 questions and single-chunk parity at 1.000/1.000 across 15.

**New status: EXPLORATORY.** Q10's Phase 2 work (wrap AnswerGenerator as a `dspy.Module`, run GEPA against Qwen with the eval scorer as the metric) is no longer load-bearing for the Day 5 artefact's main story — the hand-designed prompt v2 already achieved what GEPA was held in reserve to attempt.

**The narrative case for running GEPA anyway** remains: a "systematic optimization beats hand-tuning" demonstration would be a strong Day 5 talking point if GEPA pushes Qwen above Gemma on the within-document tasks (currently tied at 100% on single-chunk; closing the gap on multi-chunk-within-doc would be the target). Worth approximately half a day of work if Day 4 has slack after Q11 and Q12 are addressed. Not a project blocker.

**Sub-questions Q10.1, Q10.2, Q10.3 remain open** if Phase 2 is pursued.

---

## Q11 — OPEN: production model choice

**Date:** 2026-06-18
**Status:** OPEN

The Day 3 sweep results support an open question rather than a settled answer. With prompt v2 applied:

| Workload | Gemma 4 31B IT × v2 | Qwen3.6 35B-A3B × v2 |
|---|---|---|
| Single-doc retrievable (n=15) | recall 1.000 | recall 1.000 |
| Within-doc retrievable (n=21) | recall 0.929 | recall 0.929 |
| Cross-document synthesis (n=2) | recall 0.417 | recall 0.000 |
| Refusal correctness (n=14) | 14/14 | 14/14 |
| Mean latency, answerable | 20.7s | 3.4s |
| Mean latency, refusal | 7.9s | 1.3s |
| Hallucination count, full sweep | 0 | 3 |

The data shows: **on the bulk of the eval workload these two models produce equivalent quality, with Qwen 6.1× faster.** The Gemma advantage on cross-document synthesis (q025 thermal-coal Munich-vs-Swiss; q026 EIOPA-vs-PRA regulatory common themes) is real on the two questions tested but N=2 doesn't establish a robust pattern.

**The trade-off is a product decision, not a technical one.** Considerations:
- Anticipated query mix at production: what fraction of real underwriting queries will require cross-document synthesis?
- Latency budget: is 6× faster meaningful for the intended use case (research/analysis workflows vs real-time interaction)?
- Cross-document capability robustness: is the 0.417 vs 0.000 on N=2 enough evidence to weight against latency?
- Cost / infrastructure: both run on the same MacBook M5 Max stack, so no infrastructure cost differential.

**Resolution path:** Jason decides based on product context. Once decided, lodge as D015 with the rationale recorded. The benchmark's cross-document subset is too small to drive the call by itself; the call should be made on anticipated usage patterns plus the equivalence on within-document workloads.

**Pending decision data:** if cross-document synthesis is anticipated to be common enough to matter, an extended benchmark with say 6-8 cross-document questions could give a more robust read on whether the Gemma advantage holds. That's deferable to post-interview if Q11 is settled on latency grounds for the artefact.

---

## Q12 — OPEN: retrieval miss pattern

**Date:** 2026-06-18
**Status:** OPEN
**Phase:** Day 4

The Day 3 sweep showed 3 of 26 answerable questions (11.5%) had `retrieval_recall = 0` across all 4 cells — the gold chunk was not in the BGE-M3 + BM25 RRF top-5 for any model × prompt combination. This is model-independent: it's an upstream retrieval-quality finding.

**The three retrieval-miss questions:**

- **q001** "Which entities does PRA Supervisory Statement 5/25 apply to?" — gold `pra_ss5-25_climate__0005__scope`. Retrieval surfaced `__0002__contents`, `__0003__1-introduction`, `__0018__corporate-governance-structures`, `__0014__evolution-of-climate-related-risk-measur`, `__0010__proportionate-application-of-expectation`. The dedicated scope chunk was outside top-5.

- **q004** "What three characteristics make climate-related risks distinctive and require a strategic management approach?" — gold `pra_ss5-25_climate__0007__characteristics-of-climate-related-risks`. Same shape: query is conceptually narrow but the gold chunk wasn't surfaced.

- **q013** "What is Munich Re's underwriting policy on new thermal coal mines and power plants?" — gold `munich_re_sustainability_2023__0053__thermal-coal`. This is the diagnostically interesting one: the chunk is literally titled `thermal-coal` and the query contains the verbatim string "thermal coal." BM25 sparse should have surfaced this near the top. The fact that it didn't suggests RRF is downweighting strong BM25 matches when the dense channel disagrees.

**Investigation paths for Day 4 (no commitments made; ordered by cheapness):**

1. **Increase top_k from 5 to 8 or 10**, re-run the sweep on the affected questions only (via `--question-ids q001,q004,q013`). If gold chunks appear at rank 6-8, problem is cheap to solve at the retrieval call site — top_k=5 was tuned by gut feel during Day 2 not from data.

2. **Inspect the dense and sparse channel scores separately** for the three queries. The `Retriever` doesn't currently expose per-channel scores in its public output but adding a debug mode is small. If BM25 ranks the gold chunk high and dense ranks it low, RRF fusion is the suspect. If both channels rank it low, it's a deeper chunking or representation issue.

3. **Revisit Q7** (FlagEmbedding for full BGE-M3 multi-functionality). Q12's investigation may strengthen the case for Q7 — using BGE-M3's lexical + sparse + multi-vector channels rather than the current dense-only pooling could reduce miss rate. Or could complicate things further without payoff. Empirical question.

4. **Re-examine the chunking**. The retrieval-miss chunks are all section-headed (`__0005__scope`, `__0007__characteristics`, `__0053__thermal-coal`). If the chunker is including or excluding section headers in ways that affect embedding similarity, that's a chunking issue not a retrieval issue.

**Falsification criterion (proposed):** if increasing top_k from 5 to 8 surfaces all three gold chunks, Q12's resolution is "raise top_k=8 as the production default; no deeper retrieval changes needed." If raising top_k doesn't fix it, deeper investigation (paths 2-4) becomes necessary.

**Cross-link to Q11:** Q12's resolution may not change the production model choice — both models are equally affected by retrieval misses — but it does change the headline citation_recall numbers reported in the Day 5 artefact. If retrieval improvements lift baseline recall by ~10pp, that's a more compelling overall result than the current numbers.


---

## Q12 — CLOSED 2026-06-18 (DIAGNOSED, REMEDIATION DEFERRED)

**Original question:** retrieval miss pattern at 11.5% of answerable questions (3/26 in the D014 sweep). Investigation needed for Day 4.

**Resolution: root cause diagnosed; remediation deferred to v2 / Q13.**

### Investigation summary

Three probes run in sequence, each cheaper than the next would have been:

**Probe 1 — top_k experiment.** Re-ran the three failing questions (q001, q004, q013) at `top_k=8`. All three still missed. Confirmed: not a top_k truncation issue.

**Probe 2 — RRF tuning grid.** Swept 6 configurations of `(candidates_per_channel, rrf_k)` across `(50, 60)`, `(200, 60)`, `(50, 20)`, `(200, 20)`, `(461, 20)`, `(461, 10)`. Best-case configuration moved q013 from rank #20 to rank #11; q001 and q004 barely moved. None of the three landed in top-5 under any configuration. Falsified both candidate-set-width and RRF-flatness hypotheses cleanly.

**Probe 3 — dense channel localization on q013.** Direct dense-only query against the 461-chunk corpus placed `munich_re_sustainability_2023__0053__thermal-coal` at **rank 107** for the benchmark query "What is Munich Re's underwriting policy on new thermal coal mines and power plants?" The gold chunk was beaten by 106 chunks the dense embedding considered more semantically similar to the query, including Swiss Re's parallel thermal-coal chunk at rank 1.

### Root cause

**Self-retrieval test confirmed the embedding is sound.** Querying with the chunk's own first 200 characters retrieved it at rank 1 with score 0.8110 — a substantial gap to rank 2 (0.6964). The chunk's vector is valid; the corpus index is valid.

**Alternative query phrasings localized the asymmetry.** Of four alternative phrasings of the q013 query:

| Phrasing | Gold rank |
|---|---|
| "thermal coal mines coal-fired power plants insurance" | #1 |
| "Munich Re no longer insures thermal coal mines" | #3 |
| "Munich Re thermal coal" | not in top-5 |
| "stand-alone risks thermal coal Munich Re" | not in top-5 |

The pattern: queries phrased like the **chunk's actual claim verbs** ("no longer insures", "stand-alone risks") embed close to the chunk. Queries phrased like **meta-policy questions** ("what is X's policy on Y") embed close to OTHER chunks that themselves discuss policies meta-statically — investment policy chunks, decarbonisation approach chunks, etc.

**This is a well-understood limitation of single-vector dense retrieval.** CLS-pooled BGE-M3 (per D010) encodes "what is this passage about" at a topical level. The gold chunk is about a specific 2018 operational decision; the benchmark query is about a policy class. Different semantic clusters in the embedding space. RRF fusion cannot rescue chunks the dense channel ranks at #107 because the candidate set realistically caps below 500.

### Why no v1 remediation

Three remediation options exist; each is real engineering work outside the 5-day budget:

1. **LLM query expansion / HyDE** — use the LLM to expand or rephrase the query before retrieval. ~1-2 hours plus added per-query LLM latency.
2. **Cross-encoder reranker** — fetch a wide candidate set, then rerank the top-50 with a cross-encoder model. ~3-4 hours plus added reranking latency.
3. **BGE-M3 multi-vector channel** — Q7 revisit. Move from mlx-embeddings (single-vector) to FlagEmbedding for full multi-functionality including ColBERT-style multi-vector. ~4-8 hours; breaks the "MLX everywhere" decision (D009).

Q11 still resolves cleanly without these — the 11.5% retrieval miss affects both models equally and doesn't change the production choice. The Day 5 artefact ships with the diagnostic finding documented and the remediation paths scoped, which is a stronger narrative than a half-implemented optimization.

### Meta-finding worth recording

I formed two cheap hypotheses (candidate-set width too narrow; RRF k too charitable to mediocre-on-both chunks) and the data falsified both cleanly. The right discipline was "form hypothesis, design test that can falsify it, accept the falsification." The wrong discipline would have been "form hypothesis, implement the fix without testing it, ship and hope." Probes 1 and 2 each took under a minute to design and run; either could have surfaced before any code change.

---

## Q13 — OPEN: remediation for query/chunk asymmetry in retrieval

**Date:** 2026-06-18
**Status:** OPEN
**Phase:** post-interview / v2

Per Q12's closure, the 11.5% retrieval miss rate observed in the D014 sweep is caused by query/chunk asymmetry on single-vector dense embeddings, not by fusion tuning or candidate-set width. Three remediation paths to evaluate for v2:

### Option A — LLM query expansion or HyDE

Pre-process every query through an LLM that either:
- **Expands** the query with semantically equivalent phrasings (e.g., "Munich Re thermal coal policy" → "Munich Re no longer insures thermal coal; underwriting restrictions on coal-fired power plants; single-location stand-alone risks").
- **Hypothesises** what an answer chunk would look like and embeds *that* (HyDE — Hypothetical Document Embeddings).

**Cost:** ~1-2 hours of integration. One additional LLM call per query (~3-10s on Qwen).
**Risk:** LLM rewrites can be wrong; expanding "Bermuda hurricane bonds" with hypothetical content could surface false-positive chunks and harm refusal precision.
**Strength:** keeps the existing index and infrastructure; pure pre-processing layer.

### Option B — Cross-encoder reranker

Fetch a wide candidate set (top-50 from RRF, say), then rerank with a cross-encoder model (e.g., `mxbai-rerank-large-v1` or BGE's own reranker) that scores each (query, chunk) pair jointly rather than independently.

**Cost:** ~3-4 hours including model selection, integration, and re-running eval.
**Risk:** added latency per query (~1-3s for a top-50 rerank). May not help if the gold chunk isn't in the candidate set to begin with (q013's case at width=461 suggests this risk is real).
**Strength:** addresses the asymmetry directly — cross-encoders are designed to handle query/passage style differences.

### Option C — BGE-M3 multi-vector channel (Q7 revisit)

Move from mlx-embeddings (single-vector dense via CLS pooling) to FlagEmbedding (full multi-functionality). Add a third channel to RRF: ColBERT-style multi-vector token-level matching, which would handle "thermal coal" verbatim regardless of overall query/chunk style mismatch.

**Cost:** ~4-8 hours. Breaks D009 ("MLX-everywhere"). Re-index 461 chunks.
**Risk:** significant refactor; the MLX-everywhere decision had real benefits (Apple Silicon utilization, single inference stack).
**Strength:** strongest architectural fix; the multi-vector channel is built for exactly this failure mode.

### Resolution path

Not for the 5-day artefact. Empirical comparison across A/B/C is a v2 work-stream. Decision when v2 is scoped will depend on:
- Whether per-query latency budget can absorb option A's LLM call or option B's reranker pass.
- Whether the D009 commitment to MLX-everywhere is load-bearing for the v2 use case.
- Whether the 11.5% miss rate is actually production-blocking, or whether users can rephrase their queries when retrieval surfaces obviously-wrong chunks (operator workaround).

### Cross-link to Q7

Q7 (FlagEmbedding for BGE-M3 multi-functionality) was lodged on Day 2 as a possible Day 3 follow-up if retrieval hit a ceiling. Q12's investigation has now produced the empirical evidence Q7 was waiting for: there is a real retrieval ceiling, and the multi-vector channel is one of the three plausible remediations. **Q7's case is now stronger by Q13.** If v2 scoping picks Option C, Q7 closes via implementation.


---

## D015 — Production model default: gemma-4-31B-it-MLX-6bit

**Date:** 2026-06-18
**Status:** Decided
**Resolves:** Q11

The production default model for `AnswerGenerator` is
`gemma-4-31B-it-MLX-6bit`. Override at the shell via
`UNDERWRITING_COPILOT_MODEL` for latency-sensitive use cases that
warrant Qwen3.6-35B-A3B-4bit's 6.1× speed advantage.

### Rationale

The Day 3 D014 sweep (160 cells, 0 errors) showed the two candidate
models are equivalent on the bulk of the workload:

- **Single-chunk retrievable (n=15):** both at 1.000 citation_recall.
- **Within-document retrievable (n=21):** both at 0.929.
- **Refusal correctness (n=14):** both at 14/14 across all 4 sweep cells.

Where they differ, the data favors Gemma weakly:

- **Cross-document synthesis (n=2):** Gemma 0.417 vs Qwen 0.000. Direction
  is consistent but the sample is too small to call this robust.
- **Hallucinations across the full 80 answerable cells:** Gemma 0,
  Qwen 3. Both are small numbers; zero is qualitatively different from
  low-but-nonzero for a copilot operating on regulatory content.

Qwen's 6.1× latency advantage (3.4s vs 20.7s mean on answerable; 1.3s vs
7.9s on refusal) is real. For an analyst-tool use case where queries
arrive in research-and-refine workflows rather than real-time chat, this
latency difference changes "essentially instant" to "slightly noticeable"
rather than changing the workflow shape. The advantage is not weightless
— it matters at the margin and may matter more in deployments we don't
have visibility into — but it does not currently outweigh the small
quality edges Gemma carries on the harder workloads.

### Override pattern documented for operators

The `MODEL_ENV_VAR` constant (`UNDERWRITING_COPILOT_MODEL`) was lodged in
answer.py v4 specifically to make this override one shell command:

```bash
UNDERWRITING_COPILOT_MODEL=Qwen3.6-35B-A3B-4bit uv run python -m underwriting_copilot.answer
```

The precedence is `explicit constructor arg > env var > DEFAULT_MODEL`,
resolved lazily inside `__init__`. The eval harness already exercises
this — the D014 sweep used the env var to sweep both models cleanly.

### What's not decided here

This decision is about the **default**, not about which model wins
unconditionally. Specifically:

- **Production deployments with documented latency budgets that Qwen
  satisfies and Gemma doesn't** should flip the env var. The default
  optimizes for users who don't think about model choice; users who
  think about it should configure based on context.
- **If a future eval shows cross-document synthesis is more important
  than current N=2 evidence suggests**, the Gemma case strengthens. If
  v2 work (Q13) closes the retrieval-miss pattern and reshapes the
  effective workload, the comparison should be re-run.
- **The D014 sweep's prompt v2 is part of this decision implicitly.** v1
  is not a production candidate for Qwen (citation_recall 0.481 vs v2's
  0.750). The committed default in `answer.py`'s `SYSTEM_PROMPT` is
  still v1 — see follow-up note below.

### Coordination follow-up

`answer.py`'s `SYSTEM_PROMPT` currently uses v1 (the original prompt with
the `[chunk_id]` echo trap). The D014 evidence shows v2 is strictly
better — closes 89% of the Qwen v1→v2 gap, no change to Gemma, no other
side effects observed. The production prompt should be v2.

Lodged as a small action item: copy `SYSTEM_PROMPT_V2` from
`eval/prompts.py` over `SYSTEM_PROMPT` in `answer.py`, update the
related tests (the existing 46 answer.py tests don't pin specific prompt
text, so this should be drop-in), commit as a separate small feat
landing prompt v2 as the production default. Not bundled into D015
because it touches code; D015 is a documentation-only decision.


---

## Q13 — STATUS AMENDED 2026-06-18 (urgency elevated)

**Original status:** OPEN, v2 / post-interview work-stream.

**Update:** The Day 5 morning extended benchmark sweep showed the
retrieval miss rate is **25.0% at N=44** (was 11.5% at N=26). The 8
additional missed questions are concentrated in the new cross-document
questions (q042, q044-q048) and the new multi-chunk questions (q051,
q053). The cross-document misses confirm Q12's diagnosis: queries
phrased as cross-issuer comparisons ("How do Munich Re and Swiss Re
differ in their...") embed near OTHER chunks that discuss meta-level
comparisons, not near the chunks holding the actual comparable
content.

The Day 5 `excluding_retrieval_misses` subset showed Gemma at 0.798
vs the full-set 0.598, and Qwen v2 at 0.727 vs 0.545. **20pp of
locked quality across both models sits behind the retrieval ceiling**
— a much sharper picture than the 9pp lift Day 3 showed at the
smaller N.

**Status amendment:** Q13's three remediation paths (LLM query
expansion / HyDE; cross-encoder reranker; BGE-M3 multi-vector via Q7)
remain the same. What changes is **priority**: Q13 is now the highest-
value v2 work-stream by a comfortable margin. The retrieval ceiling
caps headline citation_recall at ~0.80; closing it could move the
artefact from "research-grade" to "production-candidate" on this
corpus.

**Remediation triage suggestion for v2:**

1. **Cross-encoder reranker first** (lowest-cost, highest-likely
   payoff). Fetch a wider candidate set (200+) and rerank with
   bge-reranker-v2-m3 or mxbai-rerank. Estimated 3-4 hours; doesn't
   break MLX-everywhere (D009) because the reranker is small enough
   to run on CPU/MPS with reasonable latency.

2. **LLM query expansion second** if reranker doesn't fully close
   the cross-document gap. Could be implemented with the production
   Gemma 31B model itself (one extra inference call adding ~3-5s
   per query, acceptable for analyst-research workloads).

3. **Full multi-vector via Q7** third. The largest refactor; deferred
   unless 1+2 prove insufficient.

This triage isn't lodged as a decision — it's the recommended order
for v2 scoping. The decision would be lodged as D016+ at v2 kickoff.

---

## D015 — STATUS NOTE 2026-06-18 (rationale strengthened by extended sweep)

D015 (production model default Gemma 4 31B IT) was lodged on Day 4 on
the basis of Day 3 data showing within-document parity plus weakly-
held cross-doc edge plus zero hallucinations. The Day 5 morning
extended sweep at N=44 strengthens the rationale across the board:

| Subset | Day 3 (N=21-26) | Day 5 (N=44, extended) |
|---|---|---|
| Single-chunk retrievable | both 1.000 (parity) | Gemma 1.000, Qwen v2 0.941 (5.9pp Gemma edge) |
| Multi-chunk | both 0.750 (parity, n=6) | Gemma 0.583, Qwen v2 0.542 (4.1pp Gemma edge, n=12) |
| Within-document retrievable | both 0.929 (parity, n=21) | Gemma 0.889, Qwen v2 0.833 (5.6pp Gemma edge, n=27) |
| Cross-document | Gemma 0.417 vs Qwen 0.000 (n=2, weakly held) | Gemma 0.233 vs Qwen 0.150 (n=10, 8.3pp Gemma edge) |
| Hallucinations (full sweep) | Gemma 0, Qwen v2 3 | Gemma 0, Qwen v2 7 |
| Refusal correctness | 56/56 across 4 cells | 104/104 across 4 cells |
| Latency (mean answerable) | Gemma 20.7s, Qwen 3.4s | Gemma 22.9s, Qwen 3.4s |

D015's substantive conclusion stands: Gemma is the production default;
Qwen via env-var override remains the latency-budget escape hatch. The
extended data adds a margin of confidence that wasn't there before —
Gemma is the higher-quality model on *every* answerable subset, not
just cross-document.

No code change required; the D015 decision in `answer.py` (Gemma as
`DEFAULT_MODEL`) is unchanged.

The Day 3 within-document parity claim that motivated the
"equivalent on most workloads" framing in D015 was a small-sample
artifact. The current honest framing is: Gemma carries a consistent
~5pp quality edge across answerable workloads, plus the 0-vs-7
hallucination floor difference; Qwen carries a ~6× latency advantage.
For an analyst-research deployment the quality edges accumulate to a
clearer recommendation than the Day 3 framing supported.
