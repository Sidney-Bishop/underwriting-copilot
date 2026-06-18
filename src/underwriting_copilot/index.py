"""Index module — builds the persistent Qdrant collection over the corpus.

Per **D012**:
  - 17-field payload (chunk fields + document metadata + chunk text).
  - Persistent Qdrant lives at ``scratch/qdrant/``.
  - One-shot wipe-and-rebuild on every run; idempotent re-runs.

Per **D009**:
  - Named vectors: ``dense`` (1024-dim cosine) + ``sparse`` (BM25-based).
  - RRF fusion happens at query time in ``retrieve.py``.

Per **D011**:
  - BM25 vocabulary persisted as ``corpus/bm25_vocab.json``.

The module is one-shot driver code. Reading chunks + embeddings + metadata,
building the BM25 index, and upserting into Qdrant is the entire scope —
no query-time concerns live here.
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from underwriting_copilot.bm25 import BM25Index
from underwriting_copilot.metadata import DocumentMetadata, load_corpus_metadata

# ---- Module constants ---------------------------------------------------

COLLECTION_NAME = "underwriting_copilot"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
DENSE_DIM = 1024


# ---- Loading helpers ----------------------------------------------------


def _load_chunks(chunks_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all chunks from ``{chunks_dir}/*.jsonl``, keyed by chunk_id."""
    chunks: dict[str, dict[str, Any]] = {}
    for jsonl in sorted(chunks_dir.glob("*.jsonl")):
        with jsonl.open() as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                chunk = json.loads(stripped)
                chunks[chunk["chunk_id"]] = chunk
    return chunks


def _load_embeddings(embeddings_dir: Path) -> dict[str, list[float]]:
    """Load all dense embeddings from ``{embeddings_dir}/*.jsonl``,
    keyed by chunk_id."""
    embeddings: dict[str, list[float]] = {}
    for jsonl in sorted(embeddings_dir.glob("*.jsonl")):
        with jsonl.open() as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                record = json.loads(stripped)
                embeddings[record["chunk_id"]] = record["vector"]
    return embeddings


def _metadata_by_document_id(
    corpus_metadata,
) -> dict[str, DocumentMetadata]:
    """Normalise corpus metadata to a dict keyed by ``document_id`` —
    NOT the filename that ``corpus_metadata.toml`` uses as its section
    header.

    ``load_corpus_metadata`` returns a dict keyed by filename (e.g.
    ``"pra_ss5-25_climate_dec2025.pdf"``) per the TOML's own convention:
    the on-disk filename is the file's incidental identifier and may
    differ from the logical document_id (e.g. ``"pra_ss5-25_climate"``).
    Chunks reference the inner ``document_id``, so this helper re-keys
    uniformly off the model's own ``document_id`` attribute, regardless
    of the input container type.
    """
    if isinstance(corpus_metadata, dict):
        items = corpus_metadata.values()
    else:
        items = corpus_metadata
    return {doc.document_id: doc for doc in items}


# ---- Payload projection ------------------------------------------------


def chunk_to_payload(
    chunk: dict[str, Any], doc_metadata: DocumentMetadata
) -> dict[str, Any]:
    """Project a chunk + its document's metadata into the 17-field
    Qdrant payload per D012.

    All metadata fields come from the Pydantic model — including
    ``issuer_type``, fixing the prefix-lookup shortcut Probe 08 used.
    """
    return {
        # ---- Chunk fields (from chunker JSONL) ----
        "chunk_id": chunk["chunk_id"],
        "document_id": chunk["document_id"],
        "section_path": chunk["section_path"],
        "merged_section_paths": chunk.get("merged_section_paths", []),
        "chunk_strategy": chunk["chunk_strategy"],
        "token_count": chunk["token_count"],
        "text": chunk["text"],
        # ---- Document metadata (from corpus_metadata.toml) ----
        "title": doc_metadata.title,
        "issuer": doc_metadata.issuer,
        "issuer_type": doc_metadata.issuer_type,
        "jurisdiction": doc_metadata.jurisdiction,
        "document_type": doc_metadata.document_type,
        "effective_date": str(doc_metadata.effective_date),
        "version": doc_metadata.version,
        "superseded_by": doc_metadata.superseded_by,
        "source_url": doc_metadata.source_url,
        "topics": list(doc_metadata.topics),
    }


# ---- Qdrant collection setup -------------------------------------------


def build_qdrant_collection(
    client: QdrantClient,
    collection_name: str = COLLECTION_NAME,
    dense_dim: int = DENSE_DIM,
) -> None:
    """Create the underwriting_copilot collection with named dense +
    sparse vectors per D009."""
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=dense_dim,
                distance=models.Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(),
        },
    )


# ---- Point construction ------------------------------------------------


def _iter_points(
    chunks_by_id: dict[str, dict[str, Any]],
    embeddings_by_id: dict[str, list[float]],
    metadata_by_doc_id: dict[str, DocumentMetadata],
    bm25_index: BM25Index,
) -> Iterator[models.PointStruct]:
    """Yield Qdrant ``PointStruct`` objects ready for upsert.

    Joins each chunk with its dense embedding (from JSONL) and document
    metadata (from corpus_metadata.toml). Sparse vectors are computed
    on-the-fly via the BM25 index.

    Point IDs are sequential ints assigned by alphabetical iteration
    over chunk_ids. This gives a stable point-id ordering across
    re-runs of ``index_corpus``.

    Raises:
        KeyError: if a chunk has no embedding (orphan) or its
            document_id is missing from the metadata.
    """
    for point_id, chunk_id in enumerate(sorted(chunks_by_id.keys())):
        chunk = chunks_by_id[chunk_id]
        document_id = chunk["document_id"]

        if chunk_id not in embeddings_by_id:
            raise KeyError(
                f"Chunk {chunk_id!r} has no embedding. Re-run embed.py."
            )
        if document_id not in metadata_by_doc_id:
            raise KeyError(
                f"Chunk {chunk_id!r} references document_id "
                f"{document_id!r} which is not in corpus_metadata.toml."
            )

        dense_vec = embeddings_by_id[chunk_id]
        sparse_indices, sparse_values = bm25_index.chunk_sparse_vector(
            chunk["text"]
        )
        sparse_vec = models.SparseVector(
            indices=sparse_indices,
            values=sparse_values,
        )
        payload = chunk_to_payload(chunk, metadata_by_doc_id[document_id])

        yield models.PointStruct(
            id=point_id,
            vector={
                DENSE_VECTOR_NAME: dense_vec,
                SPARSE_VECTOR_NAME: sparse_vec,
            },
            payload=payload,
        )


# ---- File-system helpers ----------------------------------------------


def _wipe_directory(path: Path) -> None:
    """Remove ``path`` (and its contents) if it exists.

    Enforces the wipe-and-rebuild contract from D012 — every run of
    ``index_corpus`` starts from a clean slate.
    """
    if path.exists():
        shutil.rmtree(path)


# ---- Top-level driver --------------------------------------------------


def index_corpus(
    chunks_dir: Path,
    embeddings_dir: Path,
    metadata_path: Path,
    qdrant_path: Path,
    vocab_path: Path,
    verbose: bool = True,
) -> dict[str, int]:
    """Build the BM25 vocab + Qdrant collection from scratch.

    Order of operations:

      1. Load chunks, dense embeddings, and corpus metadata.
      2. Hard orphan check: every chunk must have an embedding, every
         embedding must have a chunk.
      3. Build BM25 index from chunk texts; save to ``vocab_path``.
      4. Wipe ``qdrant_path`` and create a persistent ``QdrantClient``.
      5. Create the collection with named dense + sparse vectors.
      6. Upsert all points.
      7. Verify post-upsert count matches chunk count.

    Returns a dict mapping ``document_id → chunk_count`` plus a
    ``_total`` entry for the overall count.
    """
    if verbose:
        print("=== index_corpus ===")
        print(f"  chunks_dir:     {chunks_dir}")
        print(f"  embeddings_dir: {embeddings_dir}")
        print(f"  metadata_path:  {metadata_path}")
        print(f"  qdrant_path:    {qdrant_path}")
        print(f"  vocab_path:     {vocab_path}\n")

    # ---- 1. Load ---------------------------------------------------
    t0 = time.perf_counter()
    chunks_by_id = _load_chunks(chunks_dir)
    embeddings_by_id = _load_embeddings(embeddings_dir)
    corpus_metadata = load_corpus_metadata(metadata_path)
    metadata_by_doc_id = _metadata_by_document_id(corpus_metadata)
    load_s = time.perf_counter() - t0
    if verbose:
        print(
            f"Loaded {len(chunks_by_id)} chunks, "
            f"{len(embeddings_by_id)} embeddings, "
            f"{len(metadata_by_doc_id)} documents in {load_s:.2f}s"
        )

    # ---- 2. Orphan checks (fail fast) ------------------------------
    missing_emb = set(chunks_by_id) - set(embeddings_by_id)
    if missing_emb:
        raise RuntimeError(
            f"{len(missing_emb)} chunks have no embedding (first: "
            f"{next(iter(missing_emb))!r}). Re-run embed.py."
        )
    missing_chunks = set(embeddings_by_id) - set(chunks_by_id)
    if missing_chunks:
        raise RuntimeError(
            f"{len(missing_chunks)} embeddings have no chunk (first: "
            f"{next(iter(missing_chunks))!r}). Re-run the chunker."
        )

    # ---- 3. Build + save BM25 -------------------------------------
    t0 = time.perf_counter()
    texts = [chunks_by_id[cid]["text"] for cid in sorted(chunks_by_id)]
    bm25_index = BM25Index.build(texts)
    vocab_path.parent.mkdir(parents=True, exist_ok=True)
    bm25_index.save(vocab_path)
    bm25_s = time.perf_counter() - t0
    if verbose:
        print(
            f"Built BM25 index: {len(bm25_index.vocab)} vocab terms, "
            f"avgdl={bm25_index.avgdl:.1f}, in {bm25_s:.2f}s"
        )
        print(f"  saved to {vocab_path}")

    # ---- 4. Wipe + create Qdrant ----------------------------------
    _wipe_directory(qdrant_path)
    qdrant_path.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(qdrant_path))
    build_qdrant_collection(client)
    if verbose:
        print(
            f"Created Qdrant collection {COLLECTION_NAME!r} at "
            f"{qdrant_path}"
        )

    # ---- 5. Upsert ------------------------------------------------
    t0 = time.perf_counter()
    points = list(
        _iter_points(
            chunks_by_id, embeddings_by_id, metadata_by_doc_id, bm25_index
        )
    )
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    upsert_s = time.perf_counter() - t0
    count = client.count(COLLECTION_NAME, exact=True).count
    if verbose:
        print(f"Upserted {count} points in {upsert_s:.2f}s")

    # ---- 6. Sanity check -----------------------------------------
    if count != len(chunks_by_id):
        raise RuntimeError(
            f"Post-upsert collection count {count} != chunk count "
            f"{len(chunks_by_id)}"
        )

    # ---- 7. Per-document summary ---------------------------------
    summary: dict[str, int] = {}
    for chunk in chunks_by_id.values():
        doc_id = chunk["document_id"]
        summary[doc_id] = summary.get(doc_id, 0) + 1

    if verbose:
        print(f"\nIndexed {count} chunks across {len(summary)} documents:")
        for doc_id, n in sorted(summary.items()):
            print(f"  - {doc_id:40s}  {n:>4} chunks")

    return {**summary, "_total": count}


if __name__ == "__main__":
    # Run with `uv run python -m underwriting_copilot.index` from repo root.
    repo_root = Path(__file__).resolve().parents[2]
    index_corpus(
        chunks_dir=repo_root / "scratch" / "chunks",
        embeddings_dir=repo_root / "scratch" / "embeddings",
        metadata_path=repo_root / "corpus" / "corpus_metadata.toml",
        qdrant_path=repo_root / "scratch" / "qdrant",
        vocab_path=repo_root / "corpus" / "bm25_vocab.json",
        verbose=True,
    )
