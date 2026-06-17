# Status

A short, **current** snapshot. Overwrite freely; never mourn the old version.
If this starts accumulating dated entries, it's turning into a journal — move
that content to `journal.md` and let this snap back to a snapshot.

**Done:**
- Project scaffolded with project-bootstrap.
- Charter, decisions D001–D008, open questions Q2–Q5, journal entry for
  2026-06-17.
- 6 real public PDFs collected into `corpus/real/` (PRA × 3, EIOPA × 1,
  Munich Re × 1, Swiss Re × 1).
- Hand-curated metadata in `corpus/corpus_metadata.toml`, Pydantic-validated
  via `src/underwriting_copilot/metadata.py`.
- Docling installed and probed against the full corpus (~134s end-to-end
  with OCR disabled per D004).
- Cleanup pre-pass (`src/underwriting_copilot/cleanup.py`): image
  placeholders stripped, repeating-table dedup, EIOPA glyph fix, PRA SS1/21
  watermark and ss1/22-link stripping.
- Chunker v1 (`src/underwriting_copilot/chunking.py`) per D008: hierarchy-
  aware default, paragraph-fallback for sections > 1500 tokens, iterative
  floor-merge for chunks < 100 tokens.
- Full ingest pipeline verified end-to-end: 461 chunks across 6 documents,
  all health checks pass. Chunks materialised in `scratch/chunks/*.jsonl`.

**In progress:**
- Nothing currently in progress; clean stopping point.

**Blocked:**
- None.

**Next (Day 2):**
- Embeddings: BGE-M3 via `mlx-embeddings` likely (dense + sparse + ColBERT
  from one model; decision pending).
- Vector store: Qdrant in local mode, payload metadata for filtering.
- Hybrid retrieval (dense + BM25, fused via Reciprocal Rank Fusion).
- Cross-encoder reranker (`bge-reranker-v2-m3` on MPS).
- First end-to-end query → cited answer demo, with refusal behaviour
  when evidence is thin.

**Later (Days 3–5):**
- Eval harness with hand-curated benchmark (40+ questions across the
  five spec categories), RAGAS metrics, citation accuracy, refusal
  precision / recall.
- Synthetic-document authoring for Risk Appetite, Delegated Authority,
  Internal Policy categories per D003.
- README, governance.md, security.md, evaluation.md, decisions.md
  publication pass. Polish.
