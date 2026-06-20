#!/usr/bin/env python3
"""
scripts/probes/q13_baseline_misses.py

Phase 1 baseline for Q13 (HyDE / retrieval remediation spike).

Reads the canonical N=70 evaluation run committed at
eval/results/2026-06-18T15-32-07Z/raw.jsonl, filters for the
production-default cell (Gemma 4 31B IT x prompt v2), and identifies
retrieval failures on the 44 answerable questions in two flavours:

    STRICT MISS    none of the gold chunk_ids appear in
                   retrieved_chunk_ids (retrieval_recall == 0.0)

    PARTIAL MISS   some but not all gold chunk_ids appear in
                   retrieved_chunk_ids (0.0 < retrieval_recall < 1.0)

The strict misses are the primary diagnostic substrate for Q14:
    "Does LLM-based query rewriting (HyDE) close the Q12 retrieval
    mechanism on the missed questions?"

Partial misses are reported separately because they are a
qualitatively different problem: retrieval found *something*
relevant; the gap is selection within neighbourhood, not failure
to find the neighbourhood.

This script is read-only against the committed eval artefacts.
No Qdrant connection, no LLM calls, no writes outside stdout.

Note: the JSONL records do NOT carry chunk text -- only chunk_ids
and metrics. Inspecting query/chunk language asymmetry requires a
separate Phase 1b script that queries Qdrant for the gold and
retrieved chunks' text.

Usage:
    uv run python scripts/probes/q13_baseline_misses.py
"""

from __future__ import annotations

import json
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PATH = REPO_ROOT / "eval" / "benchmark.toml"
CANONICAL_RUN_DIR = (
    REPO_ROOT / "eval" / "results" / "2026-06-18T15-32-07Z"
)
RAW_JSONL = CANONICAL_RUN_DIR / "raw.jsonl"

# Production-default cell (D015 model, D014 prompt).
TARGET_MODEL = "gemma-4-31B-it-MLX-6bit"
TARGET_PROMPT = "v2"


# --------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------


def load_benchmark() -> dict[str, dict[str, Any]]:
    """Load benchmark.toml -> {question_id: question_record}."""
    if not BENCHMARK_PATH.exists():
        print(
            f"ERROR: benchmark not found at {BENCHMARK_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)
    with BENCHMARK_PATH.open("rb") as f:
        data = tomllib.load(f)
    # The benchmark uses [[question]] (singular) per inspection of
    # eval/benchmark.toml header.
    qlist = data.get("question") or data.get("questions") or []
    questions: dict[str, dict[str, Any]] = {}
    for q in qlist:
        qid = q.get("id")
        if qid:
            questions[qid] = q
    if not questions:
        print(
            "ERROR: benchmark.toml parsed but no questions found "
            "under [[question]] or [[questions]].",
            file=sys.stderr,
        )
        print(
            f"Top-level keys: {list(data.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)
    return questions


def load_cell_records() -> list[dict[str, Any]]:
    """Load raw.jsonl records for the production-default cell."""
    if not RAW_JSONL.exists():
        print(
            f"ERROR: canonical run not found at {RAW_JSONL}",
            file=sys.stderr,
        )
        sys.exit(1)
    records: list[dict[str, Any]] = []
    with RAW_JSONL.open() as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"WARN: skipping malformed line {line_num}: {e}",
                    file=sys.stderr,
                )
                continue
            if (
                rec.get("model") == TARGET_MODEL
                and rec.get("prompt_version") == TARGET_PROMPT
            ):
                records.append(rec)
    return records


# --------------------------------------------------------------------------
# Miss classification
# --------------------------------------------------------------------------


def classify_misses(
    benchmark: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (strict_misses, partial_misses).

    Strict miss:   none of the gold chunk_ids were retrieved.
    Partial miss:  some but not all of the gold chunk_ids were
                   retrieved.
    """
    strict: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for rec in records:
        # The record uses expected_refusal == False for answerable.
        if rec.get("expected_refusal") is not False:
            continue
        gold_ids = set(rec.get("gold_chunk_ids") or [])
        retrieved_ids = set(rec.get("retrieved_chunk_ids") or [])
        if not gold_ids:
            continue
        intersection = gold_ids & retrieved_ids
        qid = rec.get("question_id")
        bench_q = benchmark.get(qid, {})
        miss_record = {
            "question_id": qid,
            "query": bench_q.get("query", "(no query in benchmark)"),
            "category": rec.get("category", "unknown"),
            "gold_chunk_ids": sorted(gold_ids),
            "retrieved_chunk_ids": list(rec.get("retrieved_chunk_ids", [])),
            "intersection": sorted(intersection),
            "retrieval_recall": rec.get("retrieval_recall"),
            "gold_count": len(gold_ids),
            "found_count": len(intersection),
        }
        if not intersection:
            strict.append(miss_record)
        elif intersection != gold_ids:
            partial.append(miss_record)
    return strict, partial


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def print_header(
    benchmark: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
    strict: list[dict[str, Any]],
    partial: list[dict[str, Any]],
) -> None:
    answerable = [
        r for r in records if r.get("expected_refusal") is False
    ]
    n_ans = len(answerable)
    print("=" * 72)
    print("Q13 BASELINE -- RETRIEVAL FAILURES ON PRODUCTION-DEFAULT CELL")
    print("=" * 72)
    print(f"Benchmark:           {BENCHMARK_PATH.relative_to(REPO_ROOT)}")
    print(f"Canonical run:       {RAW_JSONL.relative_to(REPO_ROOT)}")
    print(f"Cell:                {TARGET_MODEL} x {TARGET_PROMPT}")
    print()
    print(f"Benchmark questions: {len(benchmark)} total")
    print(f"Cell records:        {len(records)}")
    print(f"Answerable in cell:  {n_ans}")
    print()
    print(f"Strict misses        {len(strict):3d} of {n_ans} "
          f"({100*len(strict)/n_ans:5.1f}%)  "
          f"no gold chunk retrieved")
    print(f"Partial misses       {len(partial):3d} of {n_ans} "
          f"({100*len(partial)/n_ans:5.1f}%)  "
          f"some but not all gold chunks retrieved")
    n_full = n_ans - len(strict) - len(partial)
    print(f"Full retrievals      {n_full:3d} of {n_ans} "
          f"({100*n_full/n_ans:5.1f}%)  "
          f"all gold chunks retrieved")
    print()

    by_cat = Counter(m["category"] for m in strict)
    if by_cat:
        print("Strict misses by category:")
        for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
            print(f"  {cat:30s} {n}")
        print()
    by_cat_p = Counter(m["category"] for m in partial)
    if by_cat_p:
        print("Partial misses by category:")
        for cat, n in sorted(by_cat_p.items(), key=lambda x: -x[1]):
            print(f"  {cat:30s} {n}")
        print()


def print_misses(
    misses: list[dict[str, Any]],
    label: str,
) -> None:
    if not misses:
        return
    print("=" * 72)
    print(f"{label}: {len(misses)} records")
    print("=" * 72)
    for i, miss in enumerate(misses, 1):
        print("-" * 72)
        print(
            f"{label[0]}{i:02d} | {miss['question_id']} | "
            f"category: {miss['category']} | "
            f"recall={miss['retrieval_recall']}"
        )
        print("-" * 72)
        print(f"Q: {miss['query']}")
        print()
        print(
            f"Gold ({miss['gold_count']} chunk"
            f"{'s' if miss['gold_count'] != 1 else ''}, "
            f"{miss['found_count']} found):"
        )
        for gid in miss["gold_chunk_ids"]:
            marker = "FOUND" if gid in miss["intersection"] else "MISS "
            print(f"  [{marker}] {gid}")
        print()
        print(f"Retrieved chunks ({len(miss['retrieved_chunk_ids'])}):")
        for rank, cid in enumerate(miss["retrieved_chunk_ids"], 1):
            print(f"  [{rank}] {cid}")
        print()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> int:
    benchmark = load_benchmark()
    records = load_cell_records()

    if not records:
        print(
            f"ERROR: no records matched {TARGET_MODEL} x "
            f"{TARGET_PROMPT} in {RAW_JSONL}.",
            file=sys.stderr,
        )
        return 1

    strict, partial = classify_misses(benchmark, records)
    print_header(benchmark, records, strict, partial)
    print_misses(strict, "STRICT")
    print_misses(partial, "PARTIAL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
