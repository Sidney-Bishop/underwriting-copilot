# Status

A short, **current** snapshot. Overwrite freely; never mourn the old version.
If this starts accumulating dated entries, it's turning into a journal — move
that content to `journal.md` and let this snap back to a snapshot.

**Done:**
- Project scaffolded with project-bootstrap.
- Charter, decisions D001–D009, open questions Q2–Q5 + Q7, journal entry
  for 2026-06-17.
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
- Unit tests: 60 tests across `test_cleanup.py` and `test_chunking.py`,
  inline string fixtures, all green.
- Full ingest pipeline verified end-to-end: 461 chunks across 6 documents,
  all health checks pass. Chunks materialised in `scratch/chunks/*.jsonl`.

**In progress:**
- Day 2 embedding pipeline. D009 lodged (BGE-M3 dense via `mlx-embeddings`
  + BM25 sparse via Qdrant native sparse vectors, RRF fusion). Next probe
  is BGE-M3 sanity check on a small chunk sample.

**Blocked:**
- None.

**Next (Day 2):**
- Probe 07: `mlx-embeddings` load + BGE-M3 sanity on a 5-chunk sample.
  Verify dense-only vector shape, dim (expected 1024), and per-chunk
  throughput on the M5 Max.
- Probe 08: Qdrant local-mode collection schema (dense + sparse fields),
  insert + filter-and-query sanity.
- Production embed module (`src/underwriting_copilot/embed.py`): batch
  embed all 461 chunks, persist alongside chunk metadata.
- BM25 channel: tokenisation, vocabulary build, sparse vector generation
  per chunk.
- Production index module (`src/underwriting_copilot/index.py`): create
  Qdrant collection, upsert chunks with both vector channels and payload.
- Retrieval module (`src/underwriting_copilot/retrieve.py`): hybrid query,
  RRF fusion, payload filtering by `document_id`, `issuer_type`, etc.
- First end-to-end demo: query → retrieve → cited answer with refusal
  behaviour when evidence is thin.

**Later (Days 3–5):**
- Cross-encoder reranker (`bge-reranker-v2-m3` on MPS).
- Eval harness with hand-curated benchmark (40+ questions across the
  five spec categories), RAGAS metrics, citation accuracy, refusal
  precision / recall.
- Synthetic-document authoring for Risk Appetite, Delegated Authority,
  Internal Policy categories per D003.
- README, governance.md, security.md, evaluation.md, decisions.md
  publication pass. Polish.
