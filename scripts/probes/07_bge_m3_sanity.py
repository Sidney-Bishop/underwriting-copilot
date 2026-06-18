"""Probe 07 — BGE-M3 sanity check via mlx-embeddings.

Goals:
  1. Confirm ``BAAI/bge-m3`` loads via mlx-embeddings on this machine.
     First run will download ~2-3 GB of weights from HuggingFace and
     convert to MLX format — expect 1-3 minutes wall time the first time.
  2. Verify the dense vector dim matches the BGE-M3 spec (1024).
  3. Measure throughput: cold load, first embed (graph build), subsequent
     embeds (warm). Project to the full 461-chunk corpus.
  4. Surface the pooling choice empirically. The BGE-M3 paper specifies
     CLS-token pooling with L2 normalisation, but mlx-embeddings defaults
     to mean pooling for XLM-RoBERTa-family models. The probe computes
     both and reports how similar they are. A high similarity means the
     choice is low-stakes; a low one means we have a real decision.
  5. Sanity-check the geometry: embed five chunks from
     ``scratch/chunks/*.jsonl`` (one per document where possible) and
     print a pairwise cosine similarity matrix. Cross-document similarity
     should be visibly lower than within-document similarity, with the
     two reinsurer reports (Munich Re, Swiss Re) more similar to each
     other than to the regulators.

D-entries touched: D005 (probes-first), D009 (BGE-M3 dense via mlx-embeddings).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import mlx.core as mx
from mlx_embeddings.utils import load

REPO_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_DIR = REPO_ROOT / "scratch" / "chunks"
OUTPUT_PATH = REPO_ROOT / "scratch" / "probe_07_results.json"

MODEL_NAME = "mlx-community/bge-m3-mlx-fp16"
EXPECTED_DIM = 1024
N_SAMPLE_CHUNKS = 5
CORPUS_CHUNK_COUNT = 461  # from Probe 06; used for full-run projection.


def normalize(x: mx.array) -> mx.array:
    """L2-normalise along the last axis."""
    return x / mx.linalg.norm(x, axis=-1, keepdims=True)


def embed_one(model, tokenizer, text: str) -> dict:
    """Embed one text. Return CLS-pooled (normalised), mean-pooled (from
    ``outputs.text_embeds``), the vector dim, and the wall time taken."""
    t0 = time.perf_counter()
    input_ids = tokenizer.encode(text, return_tensors="mlx")
    outputs = model(input_ids)
    cls_raw = outputs.last_hidden_state[:, 0, :]  # (1, dim)
    cls_norm = normalize(cls_raw)
    text_embeds = outputs.text_embeds  # already mean-pooled + normalised per docs
    mx.eval(cls_norm, text_embeds)  # force compute before timing stops
    elapsed = time.perf_counter() - t0
    return {
        "cls_norm": cls_norm,
        "text_embeds": text_embeds,
        "dim": int(cls_raw.shape[-1]),
        "time_s": elapsed,
    }


def cosine(a: mx.array, b: mx.array) -> float:
    """Cosine similarity between two pre-normalised vectors."""
    return float((a * b).sum().item())


def load_sample_chunks(n: int) -> list[dict]:
    """Pull the first chunk from each document until we have ``n`` of them,
    so the cross-document similarity matrix is meaningful."""
    chunks: list[dict] = []
    for jsonl in sorted(CHUNKS_DIR.glob("*.jsonl")):
        with jsonl.open() as f:
            line = f.readline()
            if line.strip():
                chunks.append(json.loads(line))
        if len(chunks) >= n:
            break
    return chunks[:n]


def main() -> None:
    print(f"=== Probe 07: BGE-M3 sanity via mlx-embeddings ===\n")
    print(f"Model: {MODEL_NAME}")
    print(f"Expected dim: {EXPECTED_DIM}")
    print(f"Sample chunks: {N_SAMPLE_CHUNKS}\n")

    # ---- Cold load -------------------------------------------------------
    print("Loading model... (first run downloads ~2-3GB and converts to MLX)")
    t0 = time.perf_counter()
    model, tokenizer = load(MODEL_NAME)
    load_s = time.perf_counter() - t0
    print(f"  load time:      {load_s:.2f}s")
    print(f"  model type:     {type(model).__name__}")
    print(f"  tokenizer type: {type(tokenizer).__name__}\n")

    # ---- First embed (graph build) ---------------------------------------
    print("First embed (graph build)...")
    first = embed_one(model, tokenizer, "warmup text for graph build.")
    print(f"  time: {first['time_s']:.3f}s")
    print(f"  dim:  {first['dim']}")
    if first["dim"] != EXPECTED_DIM:
        raise SystemExit(
            f"FAIL: dim {first['dim']} != expected {EXPECTED_DIM}. "
            f"BGE-M3 did not load as expected."
        )
    print(f"  ✓ dim matches BGE-M3 spec ({EXPECTED_DIM})\n")

    # ---- Sample chunks ---------------------------------------------------
    if not CHUNKS_DIR.exists():
        raise SystemExit(
            f"FAIL: {CHUNKS_DIR} does not exist. Re-run Probe 06 first."
        )
    chunks = load_sample_chunks(n=N_SAMPLE_CHUNKS)
    if len(chunks) < N_SAMPLE_CHUNKS:
        raise SystemExit(
            f"FAIL: only found {len(chunks)} chunks in {CHUNKS_DIR}. "
            f"Need at least {N_SAMPLE_CHUNKS}."
        )
    print(f"Loaded {len(chunks)} sample chunks from {CHUNKS_DIR}:")
    for c in chunks:
        print(f"  - {c['chunk_id'][:60]:60s}  ({c['token_count']:>4} tokens)")
    print()

    # ---- Embed all sample chunks (warm path) -----------------------------
    print("Embedding sample chunks (warm path)...")
    results = []
    for c in chunks:
        r = embed_one(model, tokenizer, c["text"])
        r["chunk_id"] = c["chunk_id"]
        r["document_id"] = c["document_id"]
        results.append(r)
        print(f"  - {c['document_id'][:30]:30s}  {r['time_s']:.3f}s")
    warm_times = [r["time_s"] for r in results]
    warm_mean = sum(warm_times) / len(warm_times)
    print()
    print(f"  warm mean: {warm_mean:.3f}s/chunk")
    print(f"  warm min:  {min(warm_times):.3f}s")
    print(f"  warm max:  {max(warm_times):.3f}s")
    projected = warm_mean * CORPUS_CHUNK_COUNT
    print(f"  → projected full corpus ({CORPUS_CHUNK_COUNT} chunks): "
          f"{projected:.1f}s (~{projected/60:.1f} min)\n")

    # ---- Cosine similarity matrix (CLS-pooled) ---------------------------
    print("Pairwise cosine similarity (CLS-pooled, L2-normalised):")
    labels = [r["document_id"][:22] for r in results]
    print(f"  {'':24s}" + "  ".join(f"{lbl:>22s}" for lbl in labels))
    matrix = []
    for i, r_i in enumerate(results):
        row = []
        for j, r_j in enumerate(results):
            sim = cosine(r_i["cls_norm"][0], r_j["cls_norm"][0])
            row.append(sim)
        matrix.append(row)
        print(f"  {labels[i]:24s}" + "  ".join(f"{v:>22.4f}" for v in row))
    print()

    # ---- Pooling comparison: CLS vs text_embeds --------------------------
    print("Pooling comparison (CLS-pooled vs text_embeds mean-pooled):")
    pool_sims = []
    for r in results:
        cls_v = r["cls_norm"][0]
        txt_v = r["text_embeds"][0]
        # text_embeds is documented as already normalised, but defensive:
        txt_n = float(mx.linalg.norm(txt_v).item())
        if abs(txt_n - 1.0) > 0.01:
            txt_v = txt_v / txt_n
        sim = cosine(cls_v, txt_v)
        pool_sims.append(sim)
        print(f"  - {r['document_id'][:30]:30s}  cls·text_embeds = {sim:.4f}")
    pool_mean = sum(pool_sims) / len(pool_sims)
    print(f"\n  mean: {pool_mean:.4f}")
    print(
        f"  interpretation: > 0.95 → pooling choice is low-stakes;\n"
        f"                  < 0.80 → real decision, prefer CLS per BGE-M3 spec.\n"
    )

    # ---- Persist results -------------------------------------------------
    payload = {
        "model": MODEL_NAME,
        "load_time_s": load_s,
        "expected_dim": EXPECTED_DIM,
        "actual_dim": first["dim"],
        "first_embed_s": first["time_s"],
        "warm_embed_times_s": warm_times,
        "warm_mean_s": warm_mean,
        "projected_full_corpus_s": projected,
        "sample_chunks": [
            {"chunk_id": r["chunk_id"], "document_id": r["document_id"]}
            for r in results
        ],
        "cosine_matrix_cls_pooled": matrix,
        "cls_vs_text_embeds_sim_mean": pool_mean,
        "cls_vs_text_embeds_sim_per_chunk": pool_sims,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Results written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
