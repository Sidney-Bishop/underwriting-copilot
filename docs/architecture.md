# Architecture

How **underwriting-copilot** (codename Cedant) is built *right now* — the
moving parts, how they fit, key data flows, where things live, external
services, non-obvious constraints.

A **state** document: overwrite it as the architecture changes. The *reasons*
the architecture is shaped this way live in `decisions.md`; the *story* of
how it got there lives in `journal.md`. This file just says what *is*.

## Components

**Ingestion** (planned, `src/underwriting_copilot/ingest.py`): Docling-based
PDF → markdown extraction with OCR disabled by default (D004). Reads from
`corpus/real/` and `corpus/synthetic/`, writes structured markdown for
downstream chunking. Verified working on the full corpus via
`scripts/probes/01_docling_corpus_sweep.py`.

**Cleanup pre-pass** (planned): Strips known noise from Docling output before
chunking. Three classes of rule are scoped from `scripts/probes/04_noise_audit.py`:
universal (the `<!-- image -->` placeholder, 398 instances corpus-wide);
structural (markdown tables that repeat verbatim ≥3× within one document —
Munich Re's table-of-contents being the load-bearing case at 36×);
document-specific (e.g. EIOPA's `glyph[.notdef]` font artefacts mapped to
hyphens at ingest time).

**Metadata** (`src/underwriting_copilot/metadata.py`): Hand-curated
`corpus/corpus_metadata.toml`, validated by a Pydantic schema at load time
(D006). Document-level fields are inherited by every chunk: `document_id`,
`title`, `document_type`, `issuer`, `issuer_type`, `jurisdiction`,
`effective_date`, `version`, `superseded_by`, `topics`, `provenance`,
`source_url`.

**Chunking** (planned, per D007): Two-mode chunker. Hierarchy-aware by
default — one chunk per leaf `##`/`###` section, merge upward aggressively
when sections fall below a token floor, split rarely when sections exceed a
cap. Paragraph-fallback for thin-structure documents (e.g. PRA SS1/21) —
split on numbered-paragraph patterns within the nearest enclosing heading.
Mode-detection heuristic is Q6.

**Embeddings, vector store, retrieval, reranking, answer generation, eval
harness:** not yet built. Sketched in `charter.md` under in-scope.

## Data flow

```
corpus/{real,synthetic}/*.pdf
        │
        ▼
   Docling (do_ocr=False)
        │
        ▼
   markdown + structural metadata
        │
        ▼
   Cleanup pre-pass
        │     ┌──────────────────────┐
        │ ◄───┤ corpus_metadata.toml │
        ▼     └──────────────────────┘
   Chunker (mode = hierarchy | paragraph-fallback)
        │
        ▼
   Chunks + per-chunk metadata
        │
        ▼
   [vector store + BM25 — TBD]
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
- **Reading order is not always preserved by Docling.** Watermarks (e.g. the
  "Superseded" overlay on PRA SS1/21) or unusual page layouts can scramble
  paragraph order. Mitigation lives in the chunker — D007's paragraph-fallback
  mode reconstructs order from numbered-paragraph anchors rather than trusting
  the document order Docling emits.
- **Hand-curated metadata is the source of truth.** No metadata is inferred
  at ingest time except from Docling-detected structure. Adding a new
  document requires updating `corpus_metadata.toml` first;
  `scripts/probes/02_validate_metadata.py` checks that PDFs and metadata stay
  in sync (no orphans either direction).
- **OCR is disabled by default.** Adding a scanned PDF to the corpus will
  yield empty text unless OCR is re-enabled for it; see D004 and the
  mitigation noted there.
- **Reinsurer reports dominate ingestion time.** Munich Re and Swiss Re
  together account for ~80% of the ~134s full-corpus Docling pass, despite
  being 33% of the corpus. Batch any chunker / cleanup tuning rather than
  reingesting after every change.
