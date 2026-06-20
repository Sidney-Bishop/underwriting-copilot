#!/usr/bin/env python3
"""Recompute gold-dependent metrics from a run's raw.jsonl against
the current ``eval/benchmark.toml``, without re-invoking the LLM.

Use case (2026-06-20): Q15 widened/replaced gold tags on 5 questions.
We want to see what the v1.0 baseline numbers and Q14 Phase 2c numbers
look like under the corrected benchmark — but without spending another
26 minutes per cell re-running the LLM. Citation lists, retrieval
lists, refusal verdicts, latency, hallucination counts are all
gold-INDEPENDENT and stay fixed. Only retrieval_recall, citation_recall,
citation_precision, citation_f1 change.

The recomputation calls into ``eval.scorer`` directly — same code path
the original run used — so the rescored numbers are guaranteed
identical to what a re-run would produce, modulo only the gold tags.

Output: writes ``raw_rescored.jsonl`` alongside the original
``raw.jsonl``. The rescored file is structurally identical to the
original; only the four metric values differ where gold changed.

Usage:
    uv run python eval/rescore.py eval/results/2026-06-18T15-32-07Z
    uv run python eval/rescore.py eval/results/2026-06-20T12-50-24Z

A summary table is printed showing per-question metric changes for
questions whose gold differs between the original benchmark snapshot
embedded in raw.jsonl and the current benchmark.toml. Questions whose
gold is unchanged are left out of the diff to keep output focused.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.scorer import (
    load_benchmark,
    score_citation_f1,
    score_citation_precision,
    score_citation_recall,
    score_retrieval_recall,
)


def rescore_record(
    record: dict,
    new_gold_by_qid: dict[str, list[str]],
) -> tuple[dict, dict | None]:
    """Return (rescored_record, diff_summary | None).

    diff_summary is None when nothing changed (gold unchanged or
    record is a refusal question with empty gold either way).
    """
    qid = record["question_id"]
    if qid not in new_gold_by_qid:
        # Question dropped from benchmark — leave record as is.
        return record, None

    old_gold = list(record.get("gold_chunk_ids") or [])
    new_gold = list(new_gold_by_qid[qid])

    if set(old_gold) == set(new_gold):
        return record, None

    # Compute new metrics using the scorer's own functions.
    cited = list(record.get("cited_chunks") or [])
    retrieved = list(record.get("retrieved_chunk_ids") or [])

    new_recall = score_citation_recall(cited, new_gold)
    new_precision = score_citation_precision(cited, new_gold)
    new_f1 = score_citation_f1(new_recall, new_precision)
    new_retr_recall = score_retrieval_recall(retrieved, new_gold)

    # Preserve all other fields exactly.
    rescored = dict(record)
    rescored["gold_chunk_ids"] = new_gold
    rescored["citation_recall"] = new_recall
    rescored["citation_precision"] = new_precision
    rescored["citation_f1"] = new_f1
    rescored["retrieval_recall"] = new_retr_recall

    diff = {
        "question_id": qid,
        "old_gold": old_gold,
        "new_gold": new_gold,
        "old_retrieval_recall": record.get("retrieval_recall"),
        "new_retrieval_recall": new_retr_recall,
        "old_citation_recall": record.get("citation_recall"),
        "new_citation_recall": new_recall,
        "old_citation_f1": record.get("citation_f1"),
        "new_citation_f1": new_f1,
        "model": record.get("model"),
        "prompt_version": record.get("prompt_version"),
    }
    return rescored, diff


def _fmt_metric(v) -> str:
    if v is None:
        return " null"
    if isinstance(v, float):
        return f"{v:5.3f}"
    return str(v)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Rescore a run's raw.jsonl against the current benchmark."
    )
    p.add_argument(
        "run_dir",
        type=Path,
        help="path to an eval/results/<timestamp>/ directory",
    )
    p.add_argument(
        "--benchmark",
        type=Path,
        default=Path("eval/benchmark.toml"),
        help="benchmark TOML path (default: eval/benchmark.toml)",
    )
    p.add_argument(
        "--output-name",
        default="raw_rescored.jsonl",
        help="output filename within run_dir (default: raw_rescored.jsonl)",
    )
    args = p.parse_args(argv)

    raw_path = args.run_dir / "raw.jsonl"
    if not raw_path.exists():
        print(f"ERROR: raw.jsonl not found at {raw_path}", file=sys.stderr)
        return 1
    if not args.benchmark.exists():
        print(f"ERROR: benchmark not found at {args.benchmark}", file=sys.stderr)
        return 1

    questions = load_benchmark(args.benchmark)
    new_gold_by_qid: dict[str, list[str]] = {
        q.id: list(q.gold_chunk_ids) for q in questions
    }

    out_path = args.run_dir / args.output_name
    diffs: list[dict] = []
    n_records = 0
    n_changed = 0

    with raw_path.open() as src, out_path.open("w") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            rescored, diff = rescore_record(record, new_gold_by_qid)
            dst.write(json.dumps(rescored) + "\n")
            n_records += 1
            if diff is not None:
                n_changed += 1
                diffs.append(diff)

    print(f"Rescored {n_records} records → {out_path}")
    print(f"  {n_changed} records had gold differences")
    print()

    if not diffs:
        print("No metric changes — current benchmark gold matches the run's "
              "embedded gold for every record.")
        return 0

    # Print a per-record diff table.
    print("Per-record metric changes:")
    print(f"  {'qid':<6} {'model':<28} {'prompt':<6}  "
          f"{'retr_recall':<14}  {'cit_recall':<14}  {'cit_f1':<14}")
    print(f"  {'-'*6} {'-'*28} {'-'*6}  "
          f"{'-'*14}  {'-'*14}  {'-'*14}")
    for d in diffs:
        model_short = (d["model"] or "")[:28]
        prompt = d["prompt_version"] or ""
        rr = f"{_fmt_metric(d['old_retrieval_recall'])} → {_fmt_metric(d['new_retrieval_recall'])}"
        cr = f"{_fmt_metric(d['old_citation_recall'])} → {_fmt_metric(d['new_citation_recall'])}"
        cf = f"{_fmt_metric(d['old_citation_f1'])} → {_fmt_metric(d['new_citation_f1'])}"
        print(f"  {d['question_id']:<6} {model_short:<28} {prompt:<6}  "
              f"{rr:<14}  {cr:<14}  {cf:<14}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
