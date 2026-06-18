# Status

A short, **current** snapshot. Overwrite freely; never mourn the old version.
If this starts accumulating dated entries, it's turning into a journal — move
that content to `journal.md` and let this snap back to a snapshot.

**Done:**
- Project scaffolded with project-bootstrap.
- Charter, decisions D001–D010, open questions Q2–Q5 + Q7, journal entries
  for 2026-06-17 and 2026-06-18.
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
- `mlx-embeddings` dependency added (pulls in the broader MLX ecosystem
  via upstream's loose scoping; accepted).
- Probe 07: BGE-M3 sanity via mlx-embeddings. Switched from `BAAI/bge-m3`
  to `mlx-community/bge-m3-mlx-fp16` after the upstream repo's safetensors
  weren't fetched by mlx-embeddings' downloader. Verified: load 27.8s,
  warm 0.067s/chunk (~31s projected full corpus), dim 1024 matches spec,
  cross-document geometry sensible. CLS-pooled + L2-normalised pinned via
  D010 after CLS-vs-text_embeds cosine sim measured 0.687 (well below the
  pooling-low-stakes threshold of 0.80).

**In progress:**
- Day 2 embedding pipeline. D009 + D010 lodged. Probe 07 done. Next probe
  is Qdrant local-mode sanity (collection with dense + sparse vector
  fields, payload metadata, insert + filter-and-query check).

**Blocked:**
- None.

**Next (Day 2):**
- Probe 08: Qdrant local-mode collection schema (1024-dim dense + sparse
  fields), insert + filter-and-query sanity on a handful of chunks.
- BM25 channel: tokenisation, vocabulary build over the corpus, sparse
  vector generation per chunk.
- Production embed module (`src/underwriting_copilot/embed.py`): batch
  BGE-M3 dense over all 461 chunks (~31s projected), CLS+L2 pooling
  per D010.
- Production index module (`src/underwriting_copilot/index.py`): create
  Qdrant collection, upsert chunks with both vector channels and payload.
- Retrieval module (`src/underwriting_copilot/retrieve.py`): hybrid
  query, RRF fusion, payload filtering by `document_id`, `issuer_type`,
  etc.
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
