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
- `mlx-embeddings` and `qdrant-client` dependencies added.
- Probe 07: BGE-M3 dense channel verified via `mlx-community/bge-m3-mlx-fp16`.
  Load 27.8s first-time / 0.79s warm, 0.067s/chunk warm (~31s projected
  full corpus), dim 1024 matches spec, cross-document geometry sensible.
  CLS+L2 pooling pinned via D010 after CLS-vs-text_embeds cosine sim
  measured 0.687 (below the 0.80 low-stakes threshold).
- Probe 08: Qdrant local-mode (in-memory) retrieval substrate verified.
  Named dense + sparse collection schema, four queries:
  - Dense self-retrieval (chunk 0 returns itself at 1.0000, intra-doc
    next-best at 0.8232).
  - Sparse-only (populated with denser placeholders).
  - Hybrid RRF (genuinely fuses two non-empty ranked lists; ids differ
    from either channel alone).
  - Payload filter (`issuer_type=regulator` excludes reinsurer chunks).
  Performance: 0.42s for 10-chunk embed+upsert combined.

**In progress:**
- Day 2 production code. Probes 07 and 08 cleared the retrieval substrate;
  next is lifting helpers into real modules.

**Blocked:**
- None.

**Next (Day 2):**
- Production embed module (`src/underwriting_copilot/embed.py`): lift
  `cls_l2_pool` helper from Probe 08, batch BGE-M3 dense over all 461
  chunks (~31s projected per Probe 07), persist alongside chunk metadata.
  Unit tests pin pooling shape (vector dim, unit norm) so a future
  refactor can't silently revert to mean pooling.
- BM25 sparse channel: tokenisation, vocabulary build over the corpus,
  sparse-vector generation per chunk. Open sub-questions: tokeniser
  choice (BGE-M3's XLM-RoBERTa tokenizer vs. a simpler word-level
  approach), and whether vocabulary scope is corpus-wide or per-document.
- Production index module (`src/underwriting_copilot/index.py`):
  persistent local Qdrant collection (file-based, not in-memory),
  upsert all 461 chunks with both vector channels and the full
  payload schema. `issuer_type` read from the Pydantic metadata model
  rather than the prefix-lookup shortcut Probe 08 used.
- Retrieval module (`src/underwriting_copilot/retrieve.py`): hybrid
  query, RRF fusion, payload filtering by `document_id`, `issuer_type`,
  `superseded_by IS NULL` (exclude superseded guidance), etc.
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
