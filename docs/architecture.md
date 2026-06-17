# Architecture

How **underwriting-copilot** (codename Cedant) is built *right now* — the
moving parts, how they fit, key data flows, where things live, external
services, non-obvious constraints.

A **state** document: overwrite it as the architecture changes. The *reasons*
the architecture is shaped this way live in `decisions.md`; the *story* of
how it got there lives in `journal.md`. This file just says what *is*.

## Components

**Ingestion** (planned, `src/underwriting_copilot/ingest.py`): top-level
orchestration that takes a PDF, runs Docling with OCR disabled by default
(D004), applies cleanup, runs the chunker, and emits chunks. Not yet
implemented as a single module — currently orchestrated by the probes in
`scripts/probes/` for the end-to-end Day 1 verification. To be consolidated
on Day 2 when the chunks need to be fed to embeddings.

**Cleanup pre-pass** (`src/underwriting_copilot/cleanup.py`): three rules
applied in order to Docling markdown output:

1. Universal: strip `<!-- image -->` placeholders (398 instances corpus-wide).
2. Structural: dedupe markdown table blocks that appear verbatim ≥3× within
   a single document, keeping first occurrence (Munich Re TOC handling).
   Multiple distinct TOC variants in the source PDF are correctly each kept
   once; the chunker's floor rule absorbs the small survivors.
3. Document-specific: EIOPA `glyph[.notdef]` → hyphen (font-encoding
   pathology); PRA SS1/21 inline `Superseded` watermark + `Please see:
   ss1/22-march-2022.pdf` link stripping.

Pure: input string + document_id → cleaned string + stats. No I/O.

**Metadata** (`src/underwriting_copilot/metadata.py`): hand-curated
`corpus/corpus_metadata.toml`, validated by a Pydantic schema at load time
(D006). Document-level fields are inherited by every chunk via `document_id`:
`title`, `document_type`, `issuer`, `issuer_type`, `jurisdiction`,
`effective_date`, `version`, `superseded_by`, `topics`, `provenance`,
`source_url`.

**Chunker** (`src/underwriting_copilot/chunking.py`) per D008: two-pass.

1. *Emission pass.* Parse markdown into `Segment`s at heading boundaries
   (`##`/`###`/etc.) including a `(preamble)` segment for any text before
   the first heading. For each segment: if `token_count > soft_cap` (1500),
   split using paragraph-fallback (numbered-paragraph anchors → blank-line
   paragraphs → greedy word split → coalesce adjacent pieces under cap);
   otherwise emit as a single `hierarchy` chunk.

2. *Floor-merge pass.* Iteratively merge sub-floor chunks (< 100 tokens)
   with neighbours. Prefer backward (into previous), fall back to forward
   (into next); skip if either would push receiver over cap. Don't advance
   the loop index after a merge — same position is rechecked, handling the
   case where a merged chunk is itself still under floor.

Output: 461 chunks across the 6-doc corpus (run via probe 06). All chunks
between 100 and 1500 tokens.

**Embeddings, vector store, retrieval, reranking, answer generation, eval
harness:** not yet built. Day 2 work onward.

## Data flow

```
corpus/{real,synthetic}/*.pdf
        │
        ▼
   Docling (do_ocr=False)
        │
        ▼
   raw markdown + structural metadata
        │
        ▼
   cleanup.clean(text, document_id)
        │     ┌──────────────────────┐
        │ ◄───┤ corpus_metadata.toml │
        ▼     └──────────────────────┘
   chunking.chunk_document(text, document_id, soft_cap=1500, soft_floor=100)
        │
        ▼
   Chunk[] (in document order) with section_path + provenance metadata
        │
        ▼
   [embeddings + vector store + BM25 — TBD]
```

## External services & configuration

**No external services.** Per `charter.md`, the system is local-first; no
external APIs are called at any pipeline stage. Configuration lives in:

- `pyproject.toml` — dependencies and project config.
- `corpus/corpus_metadata.toml` — corpus identity and topical metadata.
- `.env` (TBD) — runtime config when introduced.

## Constraints worth knowing

- **All ingestion is offline.** No network calls during ingestion (Docling
  pulls model weights once on first run; OCR is disabled per D004 so the
  RapidOCR model weights aren't exercised either).
- **Reading order is not always preserved by Docling.** Watermarks (e.g.
  the "Superseded" overlay on PRA SS1/21) or unusual page layouts can
  scramble paragraph order. The chunker's paragraph-fallback mode partially
  mitigates this by re-anchoring on numbered-paragraph markers in
  thin-structure documents.
- **Hand-curated metadata is the source of truth.** No metadata is inferred
  at ingest time except from Docling-detected structure. Adding a new
  document requires updating `corpus_metadata.toml` first;
  `scripts/probes/02_validate_metadata.py` checks that PDFs and metadata
  stay in sync (no orphans either direction).
- **OCR is disabled by default.** Adding a scanned PDF to the corpus will
  yield empty text unless OCR is re-enabled for it; see D004 and the
  mitigation noted there.
- **Reinsurer reports dominate ingestion time.** Munich Re and Swiss Re
  together account for ~80% of the ~134s full-corpus Docling pass, despite
  being 33% of the corpus. Batch any chunker / cleanup tuning rather than
  reingesting after every change.
- **Token counts are word splits, not real tokenizer tokens.** The Probe 03
  size distribution that drove D008's thresholds (1500/100) was computed
  this way, so the thresholds are in this unit. Swapping in a real
  tokenizer would silently change what the thresholds mean — revisit D008
  if doing that.
- **Chunk IDs are stable but non-contiguous after merging.** The emission
  pass numbers chunks sequentially; the floor-merge pass removes some,
  leaving gaps in the index sequence. Gaps are accepted in preference to
  renumbering (which would break ID stability across runs).
