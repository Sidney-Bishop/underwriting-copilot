#!/usr/bin/env python3
"""
scripts/probes/q15_chunk_text_review.py

Q15 gold-labelling review. For each of the 8 candidate questions
identified in docs/journal.md 2026-06-20 (Phase 1b + Phase 2c
diagnostics), dumps:

  - The question text and category
  - The benchmark's gold chunks (full text)
  - The Phase 2c HyDE-retrieved chunks (full text), with rank and
    whether each is a gold chunk or an alternative
  - A blank DECISION block for the reviewer to fill in

So a reviewer can decide, per candidate, whether the gold tag should:
  STAND       — gold is uniquely the right answer
  WIDEN       — retrieved alternatives also valid; add to gold
  REPLACE     — retrieved better than original gold
  AMBIGUOUS   — question itself needs rewriting

The decision criteria are stated in docs/open_questions.md Q15 and
in docs/journal.md 2026-06-20 PM (Q15 review entry).

Output: scratch/q15_chunk_text_review.txt (gitignored).

Usage:
    uv run python scripts/probes/q15_chunk_text_review.py
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

from qdrant_client import QdrantClient

from underwriting_copilot.retrieve import COLLECTION_NAME


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PATH = REPO_ROOT / "eval" / "benchmark.toml"
QDRANT_PATH = REPO_ROOT / "scratch" / "qdrant"
PHASE2C_RAW = (
    REPO_ROOT / "eval" / "results" / "2026-06-20T12-50-24Z" / "raw.jsonl"
)

# The 8 candidates for Q15 review, with their provenance.
# Order: Phase 1b originals first (familiar), then Phase 2c additions.
# Within each group, ordered by question ID.
CANDIDATES = [
    ("q013", "Phase 1b classification: cross-issuer interference (Munich Re); "
              "Phase 2c outcome: not recovered (recall=0.00), HyDE solved "
              "cross-issuer; gold chunk lost to __0100__defined-exclusion-criteria"),
    ("q044", "Phase 1b classification: gold-labelling tightness; "
              "Phase 2c outcome: partial recovery (recall=0.50)"),
    ("q046", "Phase 1b classification: gold-labelling tightness; "
              "Phase 2c outcome: not recovered (recall=0.00)"),
    ("q047", "Phase 1b classification: gold-labelling tightness; "
              "Phase 2c outcome: not recovered (recall=0.00)"),
    ("q053", "Phase 1b classification: gold-labelling tightness; "
              "Phase 2c outcome: not recovered (recall=0.00)"),
    ("q041", "Phase 2c partial regression (1.00 → 0.50); Swiss Re gold "
              "retrieved at rank 3; Munich Re gold missing — same pattern "
              "as q013"),
    ("q051", "Phase 2c not recovered (recall=0.00); all 5 retrieved are "
              "Munich Re (HyDE solved cross-issuer); gold chunks "
              "__0075__decarbonisation and __0151__ambition-2025 absent"),
    ("q056", "Phase 2c not recovered (recall=0.00); all 5 retrieved are "
              "PRA SS5/25 adjacent chunks; gold __0043__credit-risk absent"),
]

CHUNK_TEXT_TRUNCATION = 1200  # chars per chunk; longer than Phase 1b's 400
                              # because decisions need more context here


def load_benchmark_questions() -> dict[str, dict]:
    with BENCHMARK_PATH.open("rb") as f:
        data = tomllib.load(f)
    qlist = data.get("question") or data.get("questions") or []
    return {q["id"]: q for q in qlist if q.get("id")}


def load_phase2c_records() -> dict[str, dict]:
    """Return {question_id: raw_record} for the Phase 2c run."""
    out = {}
    with PHASE2C_RAW.open() as f:
        for line in f:
            r = json.loads(line)
            out[r["question_id"]] = r
    return out


def fetch_chunks_by_id(
    client: QdrantClient,
    chunk_ids: list[str],
) -> dict[str, dict]:
    """Pull each chunk_id from Qdrant via scroll-with-filter.

    Returns {chunk_id: payload}. Missing chunks omitted silently.
    """
    if not chunk_ids:
        return {}
    from qdrant_client import models
    # Scroll with a chunk_id-in-set filter. Sufficient for small sets.
    out: dict[str, dict] = {}
    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="chunk_id",
                    match=models.MatchAny(any=list(chunk_ids)),
                )
            ]
        ),
        limit=len(chunk_ids) + 5,  # small buffer for safety
        with_payload=True,
        with_vectors=False,
    )
    for p in points:
        cid = p.payload.get("chunk_id")
        if cid:
            out[cid] = p.payload
    return out


def truncate(text: str, max_chars: int = CHUNK_TEXT_TRUNCATION) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n        ... [truncated, full chunk is {len(text)} chars]"


def main() -> int:
    if not PHASE2C_RAW.exists():
        print(f"ERROR: Phase 2c raw.jsonl not found at {PHASE2C_RAW}", file=sys.stderr)
        return 1

    benchmark = load_benchmark_questions()
    phase2c = load_phase2c_records()
    client = QdrantClient(path=str(QDRANT_PATH))

    print("=" * 78)
    print("Q15 CHUNK-TEXT REVIEW")
    print("=" * 78)
    print(f"Benchmark: {BENCHMARK_PATH}")
    print(f"Phase 2c run: {PHASE2C_RAW}")
    print(f"Candidates: {len(CANDIDATES)}")
    print()
    print("Decision criteria (state before reading chunks):")
    print("  STAND     — gold uniquely answers the question")
    print("  WIDEN     — retrieved alternatives also valid; expand gold")
    print("  REPLACE   — retrieved better than original gold")
    print("  AMBIGUOUS — question needs rewriting before gold can be set")
    print()
    print("Honesty test: if a rationale starts forming for why a chunk")
    print("'should count', re-read the QUESTION before validating the rationale.")
    print()

    for qid, provenance in CANDIDATES:
        if qid not in benchmark:
            print(f"WARNING: {qid} not in benchmark — skipping", file=sys.stderr)
            continue
        if qid not in phase2c:
            print(f"WARNING: {qid} not in Phase 2c raw.jsonl — skipping", file=sys.stderr)
            continue

        q = benchmark[qid]
        r = phase2c[qid]
        gold_ids: list[str] = list(q.get("gold_chunk_ids") or [])
        retrieved_ids: list[str] = list(r.get("retrieved_chunk_ids") or [])

        # Pull text for everything we need to display.
        all_ids = list(dict.fromkeys(gold_ids + retrieved_ids))  # de-dup, order-preserving
        chunks = fetch_chunks_by_id(client, all_ids)

        print()
        print("=" * 78)
        print(f"CANDIDATE: {qid}")
        print("=" * 78)
        print(f"Category:  {q.get('category', '?')}")
        print(f"Provenance: {provenance}")
        print()
        print(f"Question:")
        print(f"  {q.get('query', '?')}")
        print()
        print(f"Phase 2c retrieval_recall: {r.get('retrieval_recall')}")
        print(f"Phase 2c citation_recall:  {r.get('citation_recall')}")
        print()

        print("GOLD CHUNKS (from benchmark.toml):")
        print("-" * 78)
        for i, gid in enumerate(gold_ids, 1):
            payload = chunks.get(gid)
            print(f"G{i}. {gid}")
            if payload is None:
                print("    [chunk not found in Qdrant — possible benchmark drift]")
                continue
            section = " > ".join(payload.get("section_path", [])) or "(no section)"
            print(f"    section: {section}")
            print(f"    text:")
            for line in truncate(payload.get("text", "")).splitlines():
                print(f"      {line}")
            print()

        print("PHASE 2C TOP-5 RETRIEVED:")
        print("-" * 78)
        for rank, rid in enumerate(retrieved_ids, 1):
            payload = chunks.get(rid)
            is_gold = rid in gold_ids
            mark = "  ← GOLD" if is_gold else ""
            print(f"R{rank}. {rid}{mark}")
            if payload is None:
                print(f"    [chunk not found in Qdrant]")
                continue
            section = " > ".join(payload.get("section_path", [])) or "(no section)"
            print(f"    section: {section}")
            print(f"    text:")
            for line in truncate(payload.get("text", "")).splitlines():
                print(f"      {line}")
            print()

        print("DECISION:")
        print("  [   ] STAND / WIDEN / REPLACE / AMBIGUOUS")
        print("  Reasoning:")
        print("    ")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
