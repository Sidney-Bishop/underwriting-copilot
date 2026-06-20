"""Hybrid retrieval over the underwriting_copilot Qdrant collection.

Per **D009**:
  - Dense channel: BGE-M3 via mlx-embeddings, CLS+L2 pooled (D010).
  - Sparse channel: BM25 query-side presence indicators (D011).
  - Fusion: Reciprocal Rank Fusion with k=60 default.

Per **D012**:
  - Self-contained payload — every Qdrant hit carries enough to render
    a citation, no second-pass lookup required.
  - Default filter: exclude documents with ``superseded_by`` set
    (sensible for an underwriting context — opt out for legacy
    comparison queries).

The ``Retriever`` class loads its dependencies once (BM25 vocab, Qdrant
client, BGE-M3 model+tokenizer) and reuses them across queries. The
``__main__`` block runs a small demo of three sample queries against
the persisted collection.
"""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from underwriting_copilot.bm25 import BM25Index
from underwriting_copilot.embed import embed_text, load_model
from underwriting_copilot.index import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
)
from underwriting_copilot.query_rewriter import QueryRewriter

# ---- Module constants ---------------------------------------------------

DEFAULT_RRF_K = 60
DEFAULT_CANDIDATES_PER_CHANNEL = 50
DEFAULT_TOP_K = 10


# ---- Retrieval result type ---------------------------------------------


@dataclasses.dataclass(frozen=True)
class RetrievalHit:
    """A retrieved chunk with its fusion score and per-channel ranks.

    ``dense_rank`` and ``sparse_rank`` are 1-based ranks within each
    channel's top-N candidates; ``None`` means the hit did not appear
    in that channel's candidate list. Useful for debugging "why did
    this rank high?" — if dense_rank is None, this was a sparse-driven
    hit (and vice versa).
    """

    chunk_id: str
    score: float
    dense_rank: int | None
    sparse_rank: int | None
    payload: dict[str, Any]


# ---- RRF fusion ---------------------------------------------------------


def reciprocal_rank_fusion(
    dense_hits: list,
    sparse_hits: list,
    k: int = DEFAULT_RRF_K,
) -> list[tuple[Any, float, int | None, int | None, dict[str, Any]]]:
    """Fuse two ranked lists of Qdrant ScoredPoint into a single ranked
    list via Reciprocal Rank Fusion.

    For each point appearing in either channel:

        ``score = sum over channels: 1 / (k + rank)``

    where rank is 1-based.

    Args:
        dense_hits: Iterable of ScoredPoint (must expose ``.id``,
            ``.payload``). Order = descending similarity.
        sparse_hits: Same.
        k: RRF smoothing constant. Larger k flattens the curve so
            high-rank hits contribute less aggressively. Standard value
            from the RRF paper is 60.

    Returns:
        List of ``(point_id, score, dense_rank, sparse_rank, payload)``,
        sorted by score descending.
    """
    by_id: dict[Any, dict[str, Any]] = {}

    for rank, hit in enumerate(dense_hits, start=1):
        by_id[hit.id] = {
            "score": 1 / (k + rank),
            "dense_rank": rank,
            "sparse_rank": None,
            "payload": hit.payload,
        }

    for rank, hit in enumerate(sparse_hits, start=1):
        if hit.id in by_id:
            by_id[hit.id]["score"] += 1 / (k + rank)
            by_id[hit.id]["sparse_rank"] = rank
        else:
            by_id[hit.id] = {
                "score": 1 / (k + rank),
                "dense_rank": None,
                "sparse_rank": rank,
                "payload": hit.payload,
            }

    fused = [
        (pid, d["score"], d["dense_rank"], d["sparse_rank"], d["payload"])
        for pid, d in by_id.items()
    ]
    fused.sort(key=lambda x: x[1], reverse=True)
    return fused


# ---- Filter construction -----------------------------------------------


def _build_filter(
    exclude_superseded: bool,
    issuer_type: str | None,
    jurisdiction: str | None,
) -> models.Filter | None:
    """Build a Qdrant filter from the retrieve-level filter args.

    Returns ``None`` if no filters are active (Qdrant treats ``None``
    as "no filter", which is what we want).
    """
    conditions: list = []

    if exclude_superseded:
        # IsNullCondition matches points where the field is null OR absent.
        conditions.append(
            models.IsNullCondition(
                is_null=models.PayloadField(key="superseded_by")
            )
        )
    if issuer_type is not None:
        conditions.append(
            models.FieldCondition(
                key="issuer_type",
                match=models.MatchValue(value=issuer_type),
            )
        )
    if jurisdiction is not None:
        conditions.append(
            models.FieldCondition(
                key="jurisdiction",
                match=models.MatchValue(value=jurisdiction),
            )
        )

    if not conditions:
        return None
    return models.Filter(must=conditions)


# ---- Retriever class ---------------------------------------------------


class Retriever:
    """Hybrid (dense + sparse) retrieval over the underwriting_copilot
    Qdrant collection.

    Loads BM25 vocab, opens Qdrant, and loads BGE-M3 once at construction
    time. Subsequent ``retrieve()`` calls reuse all three handles.

    For tests, ``model`` and ``tokenizer`` can be passed in to skip the
    BGE-M3 load.

    Optionally accepts a ``QueryRewriter`` to enable HyDE (Q14). When
    ``retrieve(..., use_hyde=True)`` is called, the dense channel embeds
    a hypothetical-answer passage generated by the rewriter; the sparse
    channel continues to use the original query verbatim, preserving
    named-entity matches (SS5/25, ORSA, ICAAP). Without a rewriter,
    ``use_hyde=True`` raises ``ValueError``.
    """

    def __init__(
        self,
        qdrant_path: Path,
        vocab_path: Path,
        collection_name: str = COLLECTION_NAME,
        model=None,
        tokenizer=None,
        verbose: bool = False,
        query_rewriter: QueryRewriter | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.verbose = verbose
        self.query_rewriter = query_rewriter

        if self.verbose:
            print(f"Loading BM25 vocab from {vocab_path}...")
        self.bm25_index = BM25Index.load(vocab_path)

        if self.verbose:
            print(f"Opening Qdrant at {qdrant_path}...")
        self.client = QdrantClient(path=str(qdrant_path))

        if model is None or tokenizer is None:
            if self.verbose:
                print("Loading BGE-M3 model...")
            model, tokenizer = load_model()
        self.model = model
        self.tokenizer = tokenizer

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        rrf_k: int = DEFAULT_RRF_K,
        candidates_per_channel: int = DEFAULT_CANDIDATES_PER_CHANNEL,
        exclude_superseded: bool = True,
        issuer_type: str | None = None,
        jurisdiction: str | None = None,
        use_hyde: bool = False,
    ) -> list[RetrievalHit]:
        """Run a hybrid retrieval against the collection.

        Pipeline:
          1. Embed the query dense (same CLS+L2 pooling as index time).
          2. Build the query sparse vector (BM25 query-side presence).
          3. Fetch top-N hits from each channel.
          4. Fuse via RRF.
          5. Return top_k results.

        If the query has no in-vocab non-stopword terms, the sparse
        channel is silent and RRF falls back to dense-only naturally.

        HyDE (Q14): when ``use_hyde=True``, step 1's dense embedding is
        computed over a hypothetical-answer passage produced by the
        configured ``QueryRewriter`` rather than over the user's query.
        Step 2 (sparse) is unchanged, preserving exact-match recall on
        named entities and instrument identifiers that the HyDE passage
        may not carry verbatim. ``use_hyde=True`` without a configured
        rewriter raises ``ValueError``.
        """
        # ---- Build dense query (HyDE rewrite if enabled) ----
        if use_hyde:
            if self.query_rewriter is None:
                raise ValueError(
                    "use_hyde=True requires a QueryRewriter passed to "
                    "Retriever(query_rewriter=...) at construction"
                )
            dense_query = self.query_rewriter.rewrite(query)
            if self.verbose:
                preview = dense_query[:200].replace("\n", " ")
                print(f"HyDE dense rewrite: {preview}...")
        else:
            dense_query = query

        # ---- Dense channel ----
        dense_vec = embed_text(self.model, self.tokenizer, dense_query)
        query_filter = _build_filter(
            exclude_superseded=exclude_superseded,
            issuer_type=issuer_type,
            jurisdiction=jurisdiction,
        )
        dense_result = self.client.query_points(
            collection_name=self.collection_name,
            query=dense_vec,
            using=DENSE_VECTOR_NAME,
            limit=candidates_per_channel,
            query_filter=query_filter,
            with_payload=True,
        )
        dense_hits = dense_result.points

        # ---- Sparse channel ----
        sparse_indices, sparse_values = self.bm25_index.query_sparse_vector(query)
        if sparse_indices:
            sparse_result = self.client.query_points(
                collection_name=self.collection_name,
                query=models.SparseVector(
                    indices=list(sparse_indices),
                    values=list(sparse_values),
                ),
                using=SPARSE_VECTOR_NAME,
                limit=candidates_per_channel,
                query_filter=query_filter,
                with_payload=True,
            )
            sparse_hits = sparse_result.points
        else:
            sparse_hits = []

        # ---- Fuse ----
        fused = reciprocal_rank_fusion(dense_hits, sparse_hits, k=rrf_k)

        return [
            RetrievalHit(
                chunk_id=payload["chunk_id"],
                score=score,
                dense_rank=dense_rank,
                sparse_rank=sparse_rank,
                payload=payload,
            )
            for (_pid, score, dense_rank, sparse_rank, payload) in fused[:top_k]
        ]


# ---- Demo --------------------------------------------------------------


def _format_hit(hit: RetrievalHit, rank: int) -> str:
    """Compact human-readable rendering of a single hit."""
    p = hit.payload
    section = " > ".join(p.get("section_path", [])) or "(no section)"
    text_preview = p["text"][:300].replace("\n", " ")
    if len(p["text"]) > 300:
        text_preview += "..."
    return (
        f"#{rank}  score={hit.score:.4f}  "
        f"(dense_rank={hit.dense_rank}, sparse_rank={hit.sparse_rank})\n"
        f"    chunk:   {p['chunk_id']}\n"
        f"    source:  {p['issuer']} ({p['issuer_type']}, "
        f"{p['jurisdiction']}) — {p['title']}\n"
        f"    section: {section}\n"
        f"    text:    {text_preview}"
    )


def _demo() -> None:
    """Run sample queries against the persisted index, print top-5 hits.

    The demo answers Day 2's end-state question: does the retrieval
    pipeline surface plausibly relevant chunks for real underwriting
    questions? LLM-generated cited answers are deferred to Day 3.

    Run: ``uv run python -m underwriting_copilot.retrieve``.
    """
    repo_root = Path(__file__).resolve().parents[2]
    retriever = Retriever(
        qdrant_path=repo_root / "scratch" / "qdrant",
        vocab_path=repo_root / "corpus" / "bm25_vocab.json",
        verbose=True,
    )
    print()

    demo_queries = [
        "What does the PRA expect insurers to do for climate scenario analysis?",
        "How should reinsurers handle operational resilience and third-party risk?",
        "What are the EIOPA governance requirements around fit and proper persons?",
    ]

    for query in demo_queries:
        print("=" * 80)
        print(f"Query: {query}")
        print("=" * 80)
        t0 = time.perf_counter()
        hits = retriever.retrieve(query, top_k=5)
        elapsed = time.perf_counter() - t0
        print(f"Returned {len(hits)} hits in {elapsed * 1000:.0f}ms\n")
        for rank, hit in enumerate(hits, start=1):
            print(_format_hit(hit, rank))
            print()
        print()


if __name__ == "__main__":
    _demo()
