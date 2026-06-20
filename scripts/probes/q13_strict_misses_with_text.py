#!/usr/bin/env python3
"""
scripts/probes/q13_strict_misses_with_text.py

Phase 1b for Q13 retrieval remediation spike.

Builds on Phase 1a (q13_baseline_misses.py) by adding chunk text
lookup from the local Qdrant index. For each of the 11 strict
misses on the production-default cell (Gemma 4 31B IT x v2),
prints:

    - The query (from benchmark.toml)
    - The gold chunk_id(s) and full text -- what the model needed
      but did NOT receive
    - The 5 retrieved chunk_ids and full text -- what the model
      received instead

This is the evidence base for classifying each miss by failure
mode (paraphrase, abbreviation, cross-doc, gold-narrow, other) in
a way a reviewer can verify by reading the printed text.

Connects to Qdrant via the same QdrantClient(path=...) pattern as
src/underwriting_copilot/retrieve.py. Read-only. No LLM calls.

Usage:
    uv run python scripts/probes/q13_strict_misses_with_text.py
    uv run python scripts/probes/q13_strict_misses_with_text.py > scratch/q13_phase1b.txt
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

# These two imports must come from the project environment.
# `uv run python ...` activates the venv where they're installed.
try:
    from qdrant_client import QdrantClient, models
except ImportError as e:
    print(
        f"ERROR: qdrant_client not available -- run via `uv run python ...`",
        file=sys.stderr,
    )
    print(f"  ({e})", file=sys.stderr)
    sys.exit(2)

try:
    from underwriting_copilot.retrieve import COLLECTION_NAME
except ImportError as e:
    print(
        f"ERROR: could not import COLLECTION_NAME from "
        f"underwriting_copilot.retrieve",
        file=sys.stderr,
    )
    print(f"  ({e})", file=sys.stderr)
    print(
        f"  → run via `uv run python ...` from the repo root.",
        file=sys.stderr,
    )
    sys.exit(2)


# --------------------------------------------------------------------------
# Paths and target cell
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PATH = REPO_ROOT / "eval" / "benchmark.toml"
CANONICAL_RUN_DIR = (
    REPO_ROOT / "eval" / "results" / "2026-06-18T15-32-07Z"
)
RAW_JSONL = CANONICAL_RUN_DIR / "raw.jsonl"
QDRANT_PATH = REPO_ROOT / "scratch" / "qdrant"

TARGET_MODEL = "gemma-4-31B-it-MLX-6bit"
TARGET_PROMPT = "v2"

# Truncate displayed chunk text to keep stdout manageable.
# Gold chunks shown fully (or close to it) so we can verify the
# answer is or isn't in there; retrieved chunks shown abridged
# since we mostly need to see why they were retrieved.
GOLD_MAX_CHARS = 2500
RETRIEVED_MAX_CHARS = 800


# --------------------------------------------------------------------------
# Loaders (mirror Phase 1a)
# --------------------------------------------------------------------------


def load_benchmark() -> dict[str, dict[str, Any]]:
    if not BENCHMARK_PATH.exists():
        print(
            f"ERROR: benchmark not found at {BENCHMARK_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)
    with BENCHMARK_PATH.open("rb") as f:
        data = tomllib.load(f)
    qlist = data.get("question") or data.get("questions") or []
    return {q["id"]: q for q in qlist if q.get("id")}


def load_strict_misses(
    benchmark: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the strict-miss records for the target cell.

    Strict miss: expected_refusal == False AND no overlap between
    gold_chunk_ids and retrieved_chunk_ids.
    """
    if not RAW_JSONL.exists():
        print(
            f"ERROR: canonical run not found at {RAW_JSONL}",
            file=sys.stderr,
        )
        sys.exit(1)

    misses: list[dict[str, Any]] = []
    with RAW_JSONL.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("model") != TARGET_MODEL:
                continue
            if rec.get("prompt_version") != TARGET_PROMPT:
                continue
            if rec.get("expected_refusal") is not False:
                continue
            gold = set(rec.get("gold_chunk_ids") or [])
            retr = set(rec.get("retrieved_chunk_ids") or [])
            if gold and not (gold & retr):
                qid = rec["question_id"]
                bench_q = benchmark.get(qid, {})
                misses.append({
                    "question_id": qid,
                    "category": rec.get("category", "unknown"),
                    "query": bench_q.get(
                        "query", "(query not in benchmark)"
                    ),
                    "gold_chunk_ids": sorted(gold),
                    "retrieved_chunk_ids": list(
                        rec.get("retrieved_chunk_ids") or []
                    ),
                })
    return misses


# --------------------------------------------------------------------------
# Qdrant lookup
# --------------------------------------------------------------------------


def fetch_chunk_text(
    client: QdrantClient,
    chunk_id: str,
) -> tuple[str | None, dict[str, Any] | None]:
    """Look up a chunk by its chunk_id field via Qdrant scroll + filter.

    Returns (text, payload) where text is None if the chunk wasn't
    found and payload is the full Qdrant payload (useful if the
    text field name is non-standard).
    """
    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="chunk_id",
                    match=models.MatchValue(value=chunk_id),
                )
            ]
        ),
        limit=1,
        with_payload=True,
    )
    if not points:
        return None, None
    payload = points[0].payload or {}
    # Try common text-field names from the retrieve.py docstring.
    for key in ("text", "chunk_text", "content", "body"):
        if key in payload and payload[key]:
            return str(payload[key]), payload
    return None, payload


# --------------------------------------------------------------------------
# Output formatting
# --------------------------------------------------------------------------


def format_chunk_text(
    text: str,
    indent: str = "    ",
    max_chars: int = 800,
) -> str:
    text = text.strip()
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True
    # Indent each line
    lines = [indent + line for line in text.split("\n")]
    out = "\n".join(lines)
    if truncated:
        out += f"\n{indent}... [truncated, {max_chars} of full text shown]"
    return out


def print_miss(
    i: int,
    total: int,
    miss: dict[str, Any],
    client: QdrantClient,
) -> None:
    print()
    print("=" * 72)
    print(
        f"STRICT MISS {i} of {total} | {miss['question_id']} | "
        f"{miss['category']}"
    )
    print("=" * 72)
    print(f"Q: {miss['query']}")
    print()

    print(f"GOLD CHUNKS (expected; NOT retrieved):")
    for gid in miss["gold_chunk_ids"]:
        text, payload = fetch_chunk_text(client, gid)
        print(f"  --- {gid} ---")
        if text is None:
            if payload is None:
                print(f"      [chunk not found in Qdrant]")
            else:
                print(
                    f"      [payload present but no recognised text "
                    f"field; keys: {sorted(payload.keys())}]"
                )
        else:
            print(format_chunk_text(text, max_chars=GOLD_MAX_CHARS))
    print()

    print(f"RETRIEVED CHUNKS (received instead):")
    for rank, cid in enumerate(miss["retrieved_chunk_ids"], 1):
        text, payload = fetch_chunk_text(client, cid)
        print(f"  [{rank}] {cid}")
        if text is None:
            if payload is None:
                print(f"      [chunk not found in Qdrant]")
            else:
                print(
                    f"      [payload present but no recognised text "
                    f"field; keys: {sorted(payload.keys())}]"
                )
        else:
            print(format_chunk_text(text, max_chars=RETRIEVED_MAX_CHARS))


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> int:
    benchmark = load_benchmark()
    misses = load_strict_misses(benchmark)

    print("=" * 72)
    print("Q13 PHASE 1B -- STRICT MISSES WITH CHUNK TEXT")
    print("=" * 72)
    print(f"Cell:             {TARGET_MODEL} x {TARGET_PROMPT}")
    print(f"Benchmark:        {BENCHMARK_PATH.relative_to(REPO_ROOT)}")
    print(f"Canonical run:    {RAW_JSONL.relative_to(REPO_ROOT)}")
    print(f"Qdrant index:     {QDRANT_PATH.relative_to(REPO_ROOT)}")
    print(f"Collection:       {COLLECTION_NAME}")
    print(f"Strict misses:    {len(misses)}")

    if not misses:
        print("\nNo strict misses found -- nothing to print.")
        return 0

    if not QDRANT_PATH.exists():
        print(
            f"\nERROR: Qdrant index path not found at {QDRANT_PATH}",
            file=sys.stderr,
        )
        return 1

    print(f"\nOpening Qdrant client at {QDRANT_PATH}...")
    client = QdrantClient(path=str(QDRANT_PATH))

    try:
        for i, miss in enumerate(misses, 1):
            print_miss(i, len(misses), miss, client)
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
