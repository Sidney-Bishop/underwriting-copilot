# underwriting-copilot — status

**Last updated:** 2026-06-18 (end of Day 2)
**Repo:** `/Users/jroche/Workspace/Python/underwriting-copilot`
**Stage:** Full retrieval pipeline working end-to-end.

---

## Where we are

Day 2 complete. The pipeline runs cleanly from a real PDF query to ranked, citable chunks:

```
PDF  →  Docling extract  →  cleanup.py  →  chunking.py
     →  scratch/chunks/ (461 chunks across 6 docs)
     →  embed.py  →  scratch/embeddings/ (461 BGE-M3 1024-dim vectors)
     →  index.py  →  scratch/qdrant/ + corpus/bm25_vocab.json
     →  retrieve.py  →  hybrid dense+sparse + RRF fusion
```

First end-to-end demo (three sample queries, top-5 each) returned plausibly relevant chunks in **22-43ms per query** after model warm-up. Filters working as designed: `exclude_superseded=True` correctly hides PRA SS3/19 and SS1/21.

---

## Code state

### Modules (Day 2 additions)

| Module | Lines | Tests | Notes |
|---|---|---|---|
| `bm25.py` | 210 | 33 | Invariant test pins formula at 1e-9 |
| `embed.py` | 210 | 14 | CLS+L2 pooling pinned per D010 |
| `index.py` | 349 | 25 | Wipe-and-rebuild; orphan check verified |
| `retrieve.py` | 280 | 15 | RRF formula pinned vs hand-computed |
| **Day 2 subtotal** | **~1,050** | **87** | |
| Day 1 carry-forward | (cleanup + chunking + metadata) | 61 | |
| **Repo total** | | **148** | All green |

### Persistent artifacts

| Path | Status | Tracked? |
|---|---|---|
| `corpus/corpus_metadata.toml` | hand-curated | ✓ |
| `corpus/bm25_vocab.json` | 212K, 4810 terms | ✓ |
| `scratch/chunks/*.jsonl` | 461 chunks | gitignored |
| `scratch/embeddings/*.jsonl` | 461 vectors, ~12MB | gitignored |
| `scratch/qdrant/` | 7.0M Qdrant store | gitignored |

### Probes

- 01–06: Day 1 (PDF extraction, cleanup, chunking, metadata)
- 07: BGE-M3 sanity via mlx-embeddings (Day 2 morning)
- 08: Qdrant local-mode sanity (Day 2 morning) — includes the "probe almost lied to us" finding around sparse-vector sparsity

---

## Decisions log

12 decisions active (D001–D012). None superseded.

**Open questions:**

- **Q7** — Should we revisit FlagEmbedding/PyTorch for BGE-M3 full multi-functionality (sparse + ColBERT from one model call)?
  *Revisit if Day 3 eval shows a retrieval ceiling.*

- **Q8** — Does `exclude_superseded=True` leave coverage gaps when the successor document isn't in the corpus? Is SS1/22's relationship to SS1/21 actually supersession (replacement) or amendment (additive)?
  *Revisit before Day 3 eval design — metadata accuracy needs to precede benchmark queries on operational resilience.*

---

## Day 3 plan

In order:

1. **Resolve Q8** — verify SS1/22 semantics; either add SS1/22 to corpus or correct the metadata field.
2. **`answer.py`** — LLM cited-answer generation on top of `retrieve.py`. oMLX integration, prompt construction, refusal logic when retrieved chunks don't answer the question, citation enforcement (no claims without a chunk_id reference).
3. **`eval/` harness** — 40+ benchmark questions with gold-standard chunks. Citation accuracy, refusal precision/recall. RAGAS optional — decide after seeing the harness shape.

Day 3 is heavy. Realistically may spill into Day 4 if `answer.py` proves substantial. Day 5 reserves capacity for the synthetic documents per D003 and final polish (README, governance.md, security.md, evaluation.md).

---

## Known caveats and quirks

- **Embed projection drift:** Probe 07 projected 0.067s/chunk based on first-chunks; real corpus run was 0.120s/chunk (1.8× slower) because first chunks are intro-heavy and short. Not a bug; documented in journal.
- **Q8 coverage gap** as above — operational-resilience queries currently surface only climate-context mentions, not the dedicated SS1/21 guidance.
- **No Qdrant payload indexes** yet (D012 deferred; add only if filter latency reveals bottlenecks).
- **One-shot rebuild** is the current `index.py` contract. Day 4+ revisit if the corpus grows past ~10× current size.
- **`uv add` of `mlx-embeddings` pulls 28 transitive packages** including mlx-lm, mlx-vlm, mlx-audio, fastapi, sounddevice — upstream broad scoping, accepted.

---

## Where to find what

- Source: `src/underwriting_copilot/`
- Tests: `tests/`
- Probes: `scripts/probes/`
- Decisions and open questions: `docs/decisions.md`
- State docs (overwrite freely): `docs/charter.md`, `docs/status.md` (this file), `docs/architecture.md`
- Journal (append-only): `docs/journal.md`
- Real PDFs: `corpus/real/`
- Hand-curated metadata: `corpus/corpus_metadata.toml`
- Committed derived state: `corpus/bm25_vocab.json`
- Gitignored derived artifacts: `scratch/`

---

## How to reproduce from scratch

```bash
# 1. PDFs already in corpus/real/, metadata in corpus/corpus_metadata.toml
# 2. Run the pipeline
uv run python -m underwriting_copilot.cleanup
uv run python -m underwriting_copilot.chunking
uv run python -m underwriting_copilot.embed
uv run python -m underwriting_copilot.index
# 3. Run the demo
uv run python -m underwriting_copilot.retrieve
```

Full corpus rebuild: ~60s wall (model load + 461 × 0.12s embed + 1s upsert).
