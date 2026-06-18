"""Dense embedding pipeline for the underwriting-copilot corpus.

Per D009 the dense channel uses BGE-M3 via ``mlx-embeddings`` on
``mlx-community/bge-m3-mlx-fp16`` (the pre-converted MLX/safetensors
variant — see journal 2026-06-18 for why the upstream ``BAAI/bge-m3``
repo wasn't usable directly).

Per D010 pooling is **CLS-token then L2-normalisation**, *not* the
mean-pooled ``text_embeds`` output that ``mlx-embeddings`` produces by
default for XLM-RoBERTa-family models. The CLS-vs-text_embeds cosine
similarity across five sample chunks averaged 0.687 in Probe 07 — well
below the 0.80 low-stakes threshold — so the choice is substantive.

``cls_l2_pool`` is exported so ``retrieve.py`` uses the same pooling for
query embedding. Asymmetric pooling between index time and query time
would silently degrade retrieval.

Outputs are persisted as JSONL (one file per source document) to keep
embedding decoupled from indexing: re-indexing Qdrant from already-
embedded chunks costs zero re-embed time, useful when iterating on the
Qdrant collection schema in ``index.py``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, NamedTuple

import mlx.core as mx
from mlx_embeddings.utils import load

# ---- Module constants ---------------------------------------------------

#: The MLX-converted BGE-M3 model. The upstream ``BAAI/bge-m3`` repo's
#: safetensors aren't fetched by mlx-embeddings' downloader — the
#: pre-converted mlx-community variant is the working path.
MODEL_NAME = "mlx-community/bge-m3-mlx-fp16"

#: BGE-M3 dense vector dim. Asserted at embedding time as a sanity check
#: against the wrong model loading silently.
DENSE_DIM = 1024


# ---- Pooling helper -----------------------------------------------------


def cls_l2_pool(outputs) -> mx.array:
    """Apply BGE-M3's recommended pooling: CLS-token, then L2-normalise.

    Pinned by D010. The empirical CLS-vs-text_embeds cosine similarity
    across five sample chunks averaged 0.687 (Probe 07), well below the
    0.80 low-stakes threshold. Following the BGE-M3 paper's specification
    rather than mlx-embeddings' XLM-RoBERTa default mean pooling.

    Args:
        outputs: Raw model output from mlx-embeddings, exposing a
            ``last_hidden_state`` tensor of shape (batch, seq_len, dim).

    Returns:
        An mlx array of shape (batch, dim) with unit L2 norm per row.
    """
    cls_raw = outputs.last_hidden_state[:, 0, :]
    return cls_raw / mx.linalg.norm(cls_raw, axis=-1, keepdims=True)


# ---- Single-text embedding ---------------------------------------------


def embed_text(model, tokenizer, text: str) -> list[float]:
    """Embed one text into a Python list of floats ready for Qdrant.

    The list is L2-normalised, so cosine similarity reduces to inner
    product — which is what Qdrant computes when the collection uses
    cosine distance (set in ``index.py``).
    """
    input_ids = tokenizer.encode(text, return_tensors="mlx")
    outputs = model(input_ids)
    vec = cls_l2_pool(outputs)
    mx.eval(vec)
    return vec[0].tolist()


# ---- Convenience: load model with the right name -----------------------


def load_model():
    """Load the BGE-M3 MLX model + tokenizer per D009/D010.

    Returns ``(model, tokenizer)``. First call downloads ~1.15 GB of
    safetensors from HuggingFace and converts to MLX format (~28s on
    a clean cache). Subsequent calls mmap from the local cache (~1s).
    """
    return load(MODEL_NAME)


# ---- Batch embedding over a chunk corpus -------------------------------


class EmbeddedChunk(NamedTuple):
    """A chunk with its computed dense vector plus enough identifying
    metadata to upsert into Qdrant without re-reading the chunk JSONL.
    """

    chunk_id: str
    document_id: str
    section_path: list[str]
    text: str
    vector: list[float]


def _iter_chunks(chunks_dir: Path) -> Iterator[dict[str, Any]]:
    """Yield chunk dicts from ``{chunks_dir}/*.jsonl`` in document order
    (alphabetical filename) and within-document chunk order."""
    for jsonl in sorted(chunks_dir.glob("*.jsonl")):
        with jsonl.open() as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    yield json.loads(stripped)


def embed_chunks(
    chunks: Iterable[dict[str, Any]],
    model=None,
    tokenizer=None,
    verbose: bool = False,
) -> Iterator[EmbeddedChunk]:
    """Lazily embed each chunk dict. Yields :class:`EmbeddedChunk`.

    If ``model`` and ``tokenizer`` aren't supplied, they are loaded via
    :func:`load_model` — typically the caller supplies them so the cost
    of model load is paid once across multiple calls.

    A hard dimension assertion fails fast if BGE-M3 produces anything
    other than the expected 1024-dim vector — guards against the wrong
    model silently being loaded.
    """
    if model is None or tokenizer is None:
        model, tokenizer = load_model()

    for chunk in chunks:
        vec = embed_text(model, tokenizer, chunk["text"])
        if len(vec) != DENSE_DIM:
            raise RuntimeError(
                f"Expected dense vector dim {DENSE_DIM}, got {len(vec)} "
                f"for chunk {chunk.get('chunk_id', '<unknown>')}. "
                f"This usually means the wrong embedding model loaded."
            )
        if verbose:
            print(f"  embedded {chunk['chunk_id']}")
        yield EmbeddedChunk(
            chunk_id=chunk["chunk_id"],
            document_id=chunk["document_id"],
            section_path=chunk["section_path"],
            text=chunk["text"],
            vector=vec,
        )


# ---- Persistence -------------------------------------------------------


def write_embeddings_jsonl(
    embedded: Iterable[EmbeddedChunk],
    output_dir: Path,
) -> dict[str, int]:
    """Persist embedded chunks to per-document JSONL files.

    Groups chunks by ``document_id`` and writes one ``{document_id}.jsonl``
    per source document. Each line is a JSON object with chunk_id,
    document_id, section_path, text, and vector fields.

    Returns ``{document_id: chunk_count}`` so the caller can print a
    summary. Files are opened on first chunk of each document; all are
    closed in a ``finally`` to avoid leaks on partial failure.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    open_files: dict[str, Any] = {}
    counts: dict[str, int] = {}

    try:
        for e in embedded:
            doc_id = e.document_id
            if doc_id not in open_files:
                path = output_dir / f"{doc_id}.jsonl"
                open_files[doc_id] = path.open("w")
                counts[doc_id] = 0
            open_files[doc_id].write(json.dumps(e._asdict()) + "\n")
            counts[doc_id] += 1
    finally:
        for f in open_files.values():
            f.close()

    return counts


# ---- Convenience driver -------------------------------------------------


def embed_corpus(
    chunks_dir: Path,
    output_dir: Path,
    verbose: bool = True,
) -> dict[str, int]:
    """Embed all chunks under ``chunks_dir`` and write per-document JSONL
    files to ``output_dir``. Returns ``{document_id: chunk_count}``.

    Logs model load time, per-chunk wall time, and total throughput when
    ``verbose=True``.
    """
    if verbose:
        print(f"=== embed_corpus ===")
        print(f"  chunks_dir: {chunks_dir}")
        print(f"  output_dir: {output_dir}")
        print(f"  model:      {MODEL_NAME}\n")

    t0 = time.perf_counter()
    if verbose:
        print(f"Loading model...")
    model, tokenizer = load_model()
    load_s = time.perf_counter() - t0
    if verbose:
        print(f"  load time: {load_s:.2f}s\n")

    chunks_list = list(_iter_chunks(chunks_dir))
    if verbose:
        print(f"Embedding {len(chunks_list)} chunks...")

    t0 = time.perf_counter()
    embedded_iter = embed_chunks(
        chunks_list, model=model, tokenizer=tokenizer, verbose=False
    )
    counts = write_embeddings_jsonl(embedded_iter, output_dir)
    embed_s = time.perf_counter() - t0
    total = sum(counts.values())

    if verbose:
        print(f"\nEmbedded {total} chunks across {len(counts)} documents:")
        for doc_id, n in sorted(counts.items()):
            print(f"  - {doc_id:40s}  {n:>4} chunks")
        per_chunk = embed_s / max(total, 1)
        print(f"\nTotal embed time: {embed_s:.2f}s ({per_chunk:.3f}s/chunk)")
        print(f"Output: {output_dir}")

    return counts


if __name__ == "__main__":
    # Run with `uv run python -m underwriting_copilot.embed` from repo root.
    repo_root = Path(__file__).resolve().parents[2]
    embed_corpus(
        chunks_dir=repo_root / "scratch" / "chunks",
        output_dir=repo_root / "scratch" / "embeddings",
        verbose=True,
    )
