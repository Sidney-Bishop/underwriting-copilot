"""Probe 08 — Qdrant local-mode sanity: collection schema, hybrid query, filters.

Goals:
  1. Verify ``QdrantClient(":memory:")`` runs Qdrant embedded (no server)
     and accepts our intended schema:
       - Named dense vector ``dense``: 1024-dim, cosine distance.
       - Named sparse vector ``sparse``: default params.
       - Payload carrying the chunk-level and document-level metadata
         we'll need for filtering and citation.
  2. Verify upsert with both vector channels populates the collection
     correctly (point count, payload round-trip).
  3. Verify four query patterns work end-to-end:
       (a) Dense-only — use one chunk's own embedding as the query; it
           should retrieve itself in the top-1 position. Sanity check.
       (b) Sparse-only — verify the sparse channel returns *anything*.
           Sparse vectors are placeholders in this probe (random valid
           structure); real BM25 is a separate concern lodged in D009.
       (c) Hybrid RRF — verify Qdrant's FusionQuery API behaves and
           returns a result list that is plausibly different from
           either dense-only or sparse-only alone.
       (d) Filtered — filter by ``issuer_type=regulator`` should
           exclude reinsurer chunks entirely.

D-entries touched:
  - D005 (probes-first), D009 (Qdrant native sparse + RRF), D010
    (CLS-pooled + L2-normalised dense embeddings — helper extracted
    here for eventual lift to ``src/underwriting_copilot/embed.py``).
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import mlx.core as mx
from mlx_embeddings.utils import load
from qdrant_client import QdrantClient, models

REPO_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_DIR = REPO_ROOT / "scratch" / "chunks"
OUTPUT_PATH = REPO_ROOT / "scratch" / "probe_08_results.json"

MODEL_NAME = "mlx-community/bge-m3-mlx-fp16"
DENSE_DIM = 1024
COLLECTION = "probe_08_chunks"
N_SAMPLE_CHUNKS = 10  # Enough for filter/hybrid to be meaningful, small enough to stay fast.
SPARSE_VOCAB_SIZE = 5000  # Placeholder sparse vocab — real BM25 vocab is forthcoming.
SPARSE_NNZ = 100  # Non-zeros per fake sparse vector.

# Issuer-type lookup keyed by document_id prefix. The chunks themselves don't
# carry this field directly; we derive it from the corpus metadata convention
# (regulator IDs start with `eiopa_` or `pra_`; reinsurer IDs end with the
# year, e.g. `_2023` or `_2024`).
ISSUER_TYPE_BY_PREFIX = {
    "eiopa_": "regulator",
    "pra_": "regulator",
    "munich_re_": "reinsurer",
    "swiss_re_": "reinsurer",
}


def issuer_type_for(document_id: str) -> str:
    """Map a chunk's document_id to its issuer_type using the corpus
    naming convention. Returns ``"unknown"`` if no prefix matches."""
    for prefix, kind in ISSUER_TYPE_BY_PREFIX.items():
        if document_id.startswith(prefix):
            return kind
    return "unknown"


def cls_l2_pool(outputs) -> mx.array:
    """BGE-M3 dense embedding per D010: CLS token, L2-normalised.

    This is the pooling helper that ``src/underwriting_copilot/embed.py``
    will eventually export. Defining it inline here keeps the probe
    self-contained while pinning the canonical implementation.
    """
    cls_raw = outputs.last_hidden_state[:, 0, :]
    return cls_raw / mx.linalg.norm(cls_raw, axis=-1, keepdims=True)


def embed_text(model, tokenizer, text: str) -> list[float]:
    """Embed one text using CLS+L2 pooling. Returns a Python list of
    floats ready for upsert into Qdrant."""
    input_ids = tokenizer.encode(text, return_tensors="mlx")
    outputs = model(input_ids)
    vec = cls_l2_pool(outputs)
    mx.eval(vec)
    # Qdrant expects a 1-D Python list per point.
    return vec[0].tolist()


def fake_sparse(rng: random.Random) -> models.SparseVector:
    """Generate a placeholder sparse vector with valid Qdrant structure.

    Real BM25-derived sparse vectors will come from the forthcoming
    BM25 vocab + tokenisation work (separate scope from this probe).
    Indices are drawn without replacement; values are positive floats.
    """
    indices = rng.sample(range(SPARSE_VOCAB_SIZE), SPARSE_NNZ)
    values = [round(rng.uniform(0.1, 1.0), 4) for _ in range(SPARSE_NNZ)]
    return models.SparseVector(indices=indices, values=values)


def load_sample_chunks(n: int) -> list[dict]:
    """Pull chunks spread across all six documents, up to ``n`` total.

    Round-robins through the per-document JSONL files so the sample
    spans the corpus rather than concentrating in one document."""
    by_doc: list[list[dict]] = []
    for jsonl in sorted(CHUNKS_DIR.glob("*.jsonl")):
        with jsonl.open() as f:
            by_doc.append([json.loads(line) for line in f if line.strip()])

    chunks: list[dict] = []
    idx = 0
    while len(chunks) < n and any(len(d) > idx for d in by_doc):
        for d in by_doc:
            if len(d) > idx:
                chunks.append(d[idx])
                if len(chunks) >= n:
                    break
        idx += 1
    return chunks[:n]


def chunk_to_payload(chunk: dict) -> dict:
    """Project chunk JSON into the payload schema we'll use in production.

    We intentionally drop the chunk text itself from the payload — the
    text is reproduced at retrieval-time from the source via chunk_id,
    keeping the index lean. (This is a probe-level convention; the
    production index module may revisit.)"""
    return {
        "chunk_id": chunk["chunk_id"],
        "document_id": chunk["document_id"],
        "section_path": chunk["section_path"],
        "merged_section_paths": chunk.get("merged_section_paths", []),
        "token_count": chunk["token_count"],
        "chunk_strategy": chunk["chunk_strategy"],
        "issuer_type": issuer_type_for(chunk["document_id"]),
    }


def print_results(label: str, hits: list, max_lines: int = 5) -> None:
    """Print a query's top hits in a compact, scannable form."""
    print(f"\n--- {label} ---")
    if not hits:
        print("  (no results)")
        return
    for h in hits[:max_lines]:
        pl = h.payload or {}
        cid = pl.get("chunk_id", "<no chunk_id>")[:55]
        doc = pl.get("document_id", "<no document_id>")[:32]
        kind = pl.get("issuer_type", "?")
        print(f"  score={h.score:.4f}  [{kind:9s}]  {doc:32s}  {cid}")


def main() -> None:
    print(f"=== Probe 08: Qdrant local-mode sanity ===\n")
    print(f"Model:        {MODEL_NAME}")
    print(f"Dense dim:    {DENSE_DIM}")
    print(f"Collection:   {COLLECTION}")
    print(f"Sample size:  {N_SAMPLE_CHUNKS}\n")

    # ---- Load model ------------------------------------------------------
    print("Loading BGE-M3 (cached from Probe 07)...")
    t0 = time.perf_counter()
    model, tokenizer = load(MODEL_NAME)
    load_s = time.perf_counter() - t0
    print(f"  load time: {load_s:.2f}s\n")

    # ---- Load sample chunks ---------------------------------------------
    if not CHUNKS_DIR.exists():
        raise SystemExit(f"FAIL: {CHUNKS_DIR} not found. Run Probe 06.")
    chunks = load_sample_chunks(N_SAMPLE_CHUNKS)
    if len(chunks) < N_SAMPLE_CHUNKS:
        raise SystemExit(
            f"FAIL: only found {len(chunks)} chunks across the corpus."
        )
    print(f"Loaded {len(chunks)} chunks across the corpus:")
    for c in chunks:
        print(f"  - {c['document_id'][:32]:32s}  {c['chunk_id'][:50]}")
    print()

    # ---- Create in-memory Qdrant + collection ---------------------------
    print("Creating in-memory Qdrant collection...")
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            "dense": models.VectorParams(
                size=DENSE_DIM,
                distance=models.Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(),
        },
    )
    info = client.get_collection(COLLECTION)
    print(f"  collection created. status={info.status}")
    print(f"  vectors_config keys: {list(info.config.params.vectors.keys())}")
    print(
        "  sparse_vectors_config keys: "
        f"{list((info.config.params.sparse_vectors or {}).keys())}\n"
    )

    # ---- Embed + upsert -------------------------------------------------
    print("Embedding + upserting points...")
    rng = random.Random(42)  # Deterministic fake sparse vectors.
    t0 = time.perf_counter()
    points = []
    dense_by_id = {}  # cache for the dense-only self-retrieval test
    for idx, chunk in enumerate(chunks):
        dense_vec = embed_text(model, tokenizer, chunk["text"])
        sparse_vec = fake_sparse(rng)
        dense_by_id[idx] = dense_vec
        points.append(
            models.PointStruct(
                id=idx,
                vector={"dense": dense_vec, "sparse": sparse_vec},
                payload=chunk_to_payload(chunk),
            )
        )
    client.upsert(collection_name=COLLECTION, points=points)
    upsert_s = time.perf_counter() - t0
    print(f"  upserted {len(points)} points in {upsert_s:.2f}s")
    count = client.count(COLLECTION, exact=True).count
    print(f"  collection count (verified): {count}")
    assert count == len(chunks), (
        f"FAIL: collection count {count} != upserted {len(chunks)}"
    )
    print()

    # ---- Query (a): dense-only, self-retrieval sanity --------------------
    # Use chunk 0's own embedding as the query. It MUST come back as top-1.
    print("Query (a): dense-only, self-retrieval sanity check")
    print(f"  query = chunk[0] = {chunks[0]['chunk_id']}")
    res_dense = client.query_points(
        collection_name=COLLECTION,
        query=dense_by_id[0],
        using="dense",
        limit=5,
        with_payload=True,
    ).points
    print_results("dense-only top 5", res_dense)
    assert res_dense[0].id == 0, (
        f"FAIL: dense-only self-retrieval put id={res_dense[0].id} at top, "
        f"expected 0 (the query chunk itself)."
    )
    print("  ✓ self-retrieval: chunk[0] is top-1")

    # ---- Query (b): sparse-only ----------------------------------------
    print("\nQuery (b): sparse-only with a placeholder sparse query")
    query_sparse = fake_sparse(rng)
    res_sparse = client.query_points(
        collection_name=COLLECTION,
        query=query_sparse,
        using="sparse",
        limit=5,
        with_payload=True,
    ).points
    print_results("sparse-only top 5", res_sparse)
    print(
        "  (placeholder sparse vectors — geometry is meaningless; we're "
        "only checking the channel returns *anything*.)"
    )

    # ---- Query (c): hybrid RRF -----------------------------------------
    print("\nQuery (c): hybrid (dense + sparse) with RRF fusion")
    res_hybrid = client.query_points(
        collection_name=COLLECTION,
        prefetch=[
            models.Prefetch(
                query=dense_by_id[0],
                using="dense",
                limit=10,
            ),
            models.Prefetch(
                query=query_sparse,
                using="sparse",
                limit=10,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=5,
        with_payload=True,
    ).points
    print_results("hybrid RRF top 5", res_hybrid)
    dense_ids = [p.id for p in res_dense]
    sparse_ids = [p.id for p in res_sparse]
    hybrid_ids = [p.id for p in res_hybrid]
    print(f"\n  dense-only ids:  {dense_ids}")
    print(f"  sparse-only ids: {sparse_ids}")
    print(f"  hybrid RRF ids:  {hybrid_ids}")

    # ---- Query (d): filtered (issuer_type=regulator) -------------------
    print("\nQuery (d): dense + filter (issuer_type='regulator' only)")
    res_filt = client.query_points(
        collection_name=COLLECTION,
        query=dense_by_id[0],
        using="dense",
        limit=5,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="issuer_type",
                    match=models.MatchValue(value="regulator"),
                )
            ]
        ),
        with_payload=True,
    ).points
    print_results("regulator-only top 5", res_filt)
    non_regulator = [
        p for p in res_filt if (p.payload or {}).get("issuer_type") != "regulator"
    ]
    assert not non_regulator, (
        f"FAIL: regulator filter leaked {len(non_regulator)} non-regulator hits"
    )
    print("  ✓ filter held: every hit has issuer_type=regulator")

    # ---- Persist results ------------------------------------------------
    payload = {
        "model": MODEL_NAME,
        "collection": COLLECTION,
        "dense_dim": DENSE_DIM,
        "load_time_s": load_s,
        "upsert_time_s": upsert_s,
        "point_count": count,
        "sample_chunks": [
            {
                "id": idx,
                "chunk_id": c["chunk_id"],
                "document_id": c["document_id"],
                "issuer_type": issuer_type_for(c["document_id"]),
            }
            for idx, c in enumerate(chunks)
        ],
        "queries": {
            "dense_only_top5": dense_ids,
            "sparse_only_top5": sparse_ids,
            "hybrid_rrf_top5": hybrid_ids,
            "filtered_regulator_top5": [p.id for p in res_filt],
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nResults written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
