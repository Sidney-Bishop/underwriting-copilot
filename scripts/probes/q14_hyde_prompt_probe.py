#!/usr/bin/env python3
"""
scripts/probes/q14_hyde_prompt_probe.py

Phase 2a for Q14: compare 3 HyDE prompt variants against baseline
on the 6 mechanism-clear strict misses identified in Phase 1b
(q001, q004, q013, q051, q055, q056).

For each (question, condition) cell, runs the full hybrid Retriever
and checks whether the gold chunk appears in the top-5 fused results.
The four conditions are:

    BASELINE         retrieve(original_query)
    HYDE_GENERIC     retrieve(LLM_rewrite(generic_prompt, query))
    HYDE_DOMAIN      retrieve(LLM_rewrite(domain_prompt, query))
    HYDE_CONSTRAINED retrieve(LLM_rewrite(constrained_prompt, query))

This is a prompt-iteration probe. It does NOT decide whether HyDE is
the right v2.0 path -- that decision lives in Q14's falsification
criterion, which a later script will evaluate against the full
production-default cell.

The probe uses the same production-default LLM (Gemma 4 31B IT) for
all three HyDE variants, same model that produces answers. Same model
keeps the spike honest -- if HyDE helps with a smaller model that
wouldn't reflect the production cell we'd evaluate against.

Output: stdout (redirect to scratch/q14_prompt_probe.txt). At the end,
a summary table shows which prompt variant recovered the most golds.

Usage:
    uv run python scripts/probes/q14_hyde_prompt_probe.py
    uv run python scripts/probes/q14_hyde_prompt_probe.py > scratch/q14_prompt_probe.txt
"""

from __future__ import annotations

import json
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

# Environment imports -------------------------------------------------------

try:
    import httpx
except ImportError as e:
    print(
        f"ERROR: httpx not available -- run via `uv run python ...`\n  ({e})",
        file=sys.stderr,
    )
    sys.exit(2)

try:
    from underwriting_copilot.retrieve import Retriever
except ImportError as e:
    print(
        f"ERROR: could not import Retriever from "
        f"underwriting_copilot.retrieve\n  ({e})",
        file=sys.stderr,
    )
    print(
        f"  → run via `uv run python ...` from the repo root.",
        file=sys.stderr,
    )
    sys.exit(2)

# Try to pull the LLM endpoint constants from answer.py; fall back to
# the documented defaults if the constant names differ.
try:
    from underwriting_copilot.answer import (  # type: ignore
        DEFAULT_API_BASE,
        DEFAULT_API_KEY,
    )
except ImportError:
    DEFAULT_API_BASE = "http://127.0.0.1:8000/v1"
    DEFAULT_API_KEY = "claude"  # placeholder; oMLX accepts on localhost


# Constants -----------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PATH = REPO_ROOT / "eval" / "benchmark.toml"
QDRANT_PATH = REPO_ROOT / "scratch" / "qdrant"
VOCAB_PATH = REPO_ROOT / "corpus" / "bm25_vocab.json"

MODEL = "gemma-4-31B-it-MLX-6bit"  # D015 production default
TOP_K = 5  # match the production default in retrieve.py

# The 6 mechanism-clear strict misses identified in Phase 1b.
TARGET_QIDS = ("q001", "q004", "q013", "q051", "q055", "q056")


# HyDE prompts --------------------------------------------------------------

PROMPT_GENERIC = """Please write a passage to answer the question.

Question: {query}

Passage:"""

PROMPT_DOMAIN = """Write a passage from a regulatory supervisory statement or corporate sustainability report that would answer the following question. Use the formal, declarative register typical of such documents. Keep the passage to two or three sentences.

Question: {query}

Passage:"""

PROMPT_CONSTRAINED = """Imagine you have access to the regulatory supervisory statement or corporate sustainability report that contains the answer to this question. Write the exact paragraph from that document that contains the answer. Be specific, use technical terminology, and name any organisations or instruments referenced. One paragraph only; do not preface with commentary.

Question: {query}

Paragraph:"""

PROMPT_VARIANTS: dict[str, str] = {
    "HYDE_GENERIC": PROMPT_GENERIC,
    "HYDE_DOMAIN": PROMPT_DOMAIN,
    "HYDE_CONSTRAINED": PROMPT_CONSTRAINED,
}


# Loaders -------------------------------------------------------------------


def load_benchmark() -> dict[str, dict[str, Any]]:
    with BENCHMARK_PATH.open("rb") as f:
        data = tomllib.load(f)
    qlist = data.get("question") or data.get("questions") or []
    return {q["id"]: q for q in qlist if q.get("id")}


# LLM call ------------------------------------------------------------------


def llm_rewrite(prompt_template: str, query: str) -> tuple[str, float]:
    """Generate a HyDE rewrite via the production-default LLM.

    Returns (rewritten_text, elapsed_seconds).
    """
    prompt = prompt_template.format(query=query)
    t0 = time.perf_counter()
    response = httpx.post(
        f"{DEFAULT_API_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {DEFAULT_API_KEY}"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,  # deterministic
            "max_tokens": 250,
        },
        timeout=120.0,
    )
    elapsed = time.perf_counter() - t0
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"]["content"].strip()
    return text, elapsed


# Retrieval -----------------------------------------------------------------


def find_gold_rank(
    hits: list[Any],
    gold_chunk_ids: set[str],
) -> tuple[bool, dict[str, int]]:
    """Check whether any gold chunk appears in top-k hits.

    Returns (any_gold_in_topk, {gold_chunk_id: rank}).
    Rank is 1-based; missing gold chunks aren't in the dict.
    """
    found_at: dict[str, int] = {}
    for rank, hit in enumerate(hits, 1):
        cid = getattr(hit, "chunk_id", None)
        if cid is None and isinstance(hit, dict):
            cid = hit.get("chunk_id")
        if cid in gold_chunk_ids:
            found_at[cid] = rank
    return (bool(found_at), found_at)


# Output --------------------------------------------------------------------


def print_question_block(
    qid: str,
    query: str,
    gold_ids: list[str],
    baseline_hits: list[Any],
    variant_results: dict[str, dict[str, Any]],
) -> None:
    print()
    print("=" * 72)
    print(f"QUESTION {qid}")
    print("=" * 72)
    print(f"Q: {query}")
    print()
    print("Gold chunk(s):")
    for g in gold_ids:
        print(f"  - {g}")
    print()

    gold_set = set(gold_ids)

    # Baseline
    print("--- BASELINE (original query) ---")
    found, ranks = find_gold_rank(baseline_hits, gold_set)
    print(f"  Top-{TOP_K} retrieved:")
    for rank, hit in enumerate(baseline_hits, 1):
        cid = getattr(hit, "chunk_id", "?")
        mark = "  ← GOLD" if cid in gold_set else ""
        print(f"    [{rank}] {cid}{mark}")
    print(
        f"  → Gold in top-{TOP_K}: {'YES' if found else 'NO'}"
        + (f" (ranks: {ranks})" if found else "")
    )
    print()

    for label, result in variant_results.items():
        print(f"--- {label} ---")
        if "error" in result:
            print(f"  ERROR: {result['error']}")
            continue
        passage = result["passage"]
        elapsed = result["llm_seconds"]
        hits = result["hits"]
        found, ranks = find_gold_rank(hits, gold_set)
        # Truncate passage for display
        display_passage = passage.replace("\n", " ").strip()
        if len(display_passage) > 500:
            display_passage = display_passage[:500] + " ..."
        print(f"  HyDE passage ({elapsed:.1f}s, {len(passage)} chars):")
        print(f"    {display_passage}")
        print(f"  Top-{TOP_K} retrieved:")
        for rank, hit in enumerate(hits, 1):
            cid = getattr(hit, "chunk_id", "?")
            mark = "  ← GOLD" if cid in gold_set else ""
            print(f"    [{rank}] {cid}{mark}")
        print(
            f"  → Gold in top-{TOP_K}: {'YES' if found else 'NO'}"
            + (f" (ranks: {ranks})" if found else "")
        )
        print()


def print_summary(
    per_question: dict[str, dict[str, bool]],
) -> None:
    print()
    print("=" * 72)
    print("SUMMARY: gold-in-top-5 by question x condition")
    print("=" * 72)
    conditions = ["BASELINE"] + list(PROMPT_VARIANTS.keys())
    header = f"  {'QID':<8}" + "".join(
        f"{c:<20}" for c in conditions
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    totals = {c: 0 for c in conditions}
    for qid in TARGET_QIDS:
        row = f"  {qid:<8}"
        for c in conditions:
            v = per_question.get(qid, {}).get(c, False)
            mark = "YES" if v else "no"
            row += f"{mark:<20}"
            if v:
                totals[c] += 1
        print(row)
    print("  " + "-" * (len(header) - 2))
    tot_row = f"  {'TOTAL':<8}"
    for c in conditions:
        tot_row += f"{totals[c]}/{len(TARGET_QIDS):<18}"
    print(tot_row)
    print()
    print("Falsification context (Q14):")
    print("  HyDE must recover at least 4 of 6 mechanism-clear misses")
    print("  AND not regress any baseline hits (BASELINE shows current state).")


# Entry point ---------------------------------------------------------------


def main() -> int:
    if not BENCHMARK_PATH.exists():
        print(f"ERROR: benchmark not found at {BENCHMARK_PATH}", file=sys.stderr)
        return 1
    if not QDRANT_PATH.exists():
        print(
            f"ERROR: Qdrant index not found at {QDRANT_PATH}",
            file=sys.stderr,
        )
        return 1
    if not VOCAB_PATH.exists():
        print(
            f"ERROR: BM25 vocab not found at {VOCAB_PATH}",
            file=sys.stderr,
        )
        return 1

    benchmark = load_benchmark()
    missing = [qid for qid in TARGET_QIDS if qid not in benchmark]
    if missing:
        print(
            f"ERROR: target questions missing from benchmark: {missing}",
            file=sys.stderr,
        )
        return 1

    print("=" * 72)
    print("Q14 HYDE PROMPT PROBE")
    print("=" * 72)
    print(f"LLM:              {MODEL}")
    print(f"API base:         {DEFAULT_API_BASE}")
    print(f"Retriever:        full hybrid (dense + sparse + RRF)")
    print(f"Top-k:            {TOP_K}")
    print(f"Target questions: {', '.join(TARGET_QIDS)}")
    print(f"Variants:         BASELINE + {', '.join(PROMPT_VARIANTS.keys())}")
    print()

    print("Constructing Retriever (loads BM25 + Qdrant + BGE-M3)...")
    t0 = time.perf_counter()
    retriever = Retriever(qdrant_path=QDRANT_PATH, vocab_path=VOCAB_PATH)
    print(f"  → ready in {time.perf_counter() - t0:.1f}s")

    per_question: dict[str, dict[str, bool]] = {}

    for qid in TARGET_QIDS:
        q = benchmark[qid]
        query = q["query"]
        gold_ids = list(q.get("gold_chunk_ids") or [])
        gold_set = set(gold_ids)

        # Baseline: retrieve on the original query.
        baseline_hits = retriever.retrieve(
            query=query,
            top_k=TOP_K,
            exclude_superseded=True,
        )
        baseline_found, _ = find_gold_rank(baseline_hits, gold_set)
        per_question.setdefault(qid, {})["BASELINE"] = baseline_found

        # HyDE variants.
        variant_results: dict[str, dict[str, Any]] = {}
        for label, prompt_template in PROMPT_VARIANTS.items():
            try:
                passage, elapsed = llm_rewrite(prompt_template, query)
            except Exception as e:
                variant_results[label] = {"error": str(e)}
                per_question[qid][label] = False
                continue
            hits = retriever.retrieve(
                query=passage,
                top_k=TOP_K,
                exclude_superseded=True,
            )
            found, _ = find_gold_rank(hits, gold_set)
            variant_results[label] = {
                "passage": passage,
                "llm_seconds": elapsed,
                "hits": hits,
            }
            per_question[qid][label] = found

        print_question_block(
            qid, query, gold_ids, baseline_hits, variant_results
        )

    print_summary(per_question)
    return 0


if __name__ == "__main__":
    sys.exit(main())
