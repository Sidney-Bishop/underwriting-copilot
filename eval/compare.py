#!/usr/bin/env python3
"""Compare two or more canonical sweep runs.

Each run lives in ``eval/results/<timestamp>/`` and must contain:

  - ``manifest.toml`` describing the run (cells, retriever config,
    use_hyde, etc.). See ``eval/results/2026-06-18T15-32-07Z/manifest.toml``
    for the schema.
  - ``raw.jsonl`` with one record per (question, cell) combination.

Cells are matched across runs by ``id`` from each manifest's ``[[cells]]``
entries. Identical IDs across runs are treated as the same configuration.
For renamed or rebuilt cells, use ``--pair OLD_ID:NEW_ID`` to map a cell
in run-1 to a cell in run-N.

Output sections:

  1. Run summary -- what each run is.
  2. Per matched cell pair:
     - Aggregate metric deltas (mean retrieval_recall, citation_recall,
       hallucinated_citations, refusal_correctness, mean latency).
     - Per-question retrieval_recall changes (only questions where
       the value changed).
  3. Optional ``--focus-questions q001,q004,...`` highlights specific
     question IDs in the per-question section (e.g. Q14's mechanism-clear
     set).

Usage:
    uv run python eval/compare.py \\
        eval/results/2026-06-18T15-32-07Z \\
        eval/results/2026-06-20T??Z

    uv run python eval/compare.py \\
        eval/results/2026-06-18T15-32-07Z \\
        eval/results/2026-06-20T??Z \\
        --pair gemma_v2:gemma_v2_hyde \\
        --focus-questions q001,q004,q051,q055,q056

No tomli backport; Python 3.11+ stdlib ``tomllib`` is required.
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from statistics import mean
from typing import Any


# ---- Loading ----------------------------------------------------------


def load_run(run_dir: Path) -> dict[str, Any]:
    """Load manifest + raw records from a sweep directory."""
    manifest_path = run_dir / "manifest.toml"
    raw_path = run_dir / "raw.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"missing manifest.toml in {run_dir} -- author one or pass "
            f"a run directory that has it"
        )
    if not raw_path.exists():
        raise FileNotFoundError(f"missing raw.jsonl in {run_dir}")
    with manifest_path.open("rb") as f:
        manifest = tomllib.load(f)
    raw = []
    with raw_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw.append(json.loads(line))
    return {"dir": run_dir, "manifest": manifest, "raw": raw}


def cells_in_run(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return a dict mapping cell_id -> cell config from the manifest."""
    cells = run["manifest"].get("cells") or []
    return {c["id"]: c for c in cells}


def records_for_cell(
    run: dict[str, Any],
    cell: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return raw records that belong to ``cell``.

    Matches on (model, prompt_version). Does NOT match on use_hyde
    yet -- raw.jsonl pre-Q14 doesn't carry it. If a future run has
    two cells sharing (model, prompt_version) but differing on
    use_hyde, raw.jsonl will need a ``cell_id`` field; backlog.
    """
    model = cell["model"]
    prompt_version = cell["prompt_version"]
    out = []
    for r in run["raw"]:
        if r.get("model") == model and r.get("prompt_version") == prompt_version:
            out.append(r)
    return out


# ---- Cell pairing -----------------------------------------------------


def resolve_pairs(
    runs: list[dict[str, Any]],
    user_pairs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Build the list of (cell_id_in_run1, cell_id_in_runN) pairs.

    User-supplied --pair takes precedence. Otherwise match cells by id
    across runs and pair them with themselves.
    """
    if len(runs) < 2:
        return []
    cells_run1 = cells_in_run(runs[0])
    cells_runN = cells_in_run(runs[-1])  # only pair first vs last for now
    pairs: list[tuple[str, str]] = []
    user_left = {old for (old, _) in user_pairs}
    # User pairs first.
    for old, new in user_pairs:
        if old not in cells_run1:
            print(
                f"WARNING: --pair source {old!r} not in run 1; skipping",
                file=sys.stderr,
            )
            continue
        if new not in cells_runN:
            print(
                f"WARNING: --pair target {new!r} not in last run; skipping",
                file=sys.stderr,
            )
            continue
        pairs.append((old, new))
    # Automatic matches for cells not user-paired.
    for cell_id in cells_run1:
        if cell_id in user_left:
            continue
        if cell_id in cells_runN:
            pairs.append((cell_id, cell_id))
    return pairs


# ---- Metrics ----------------------------------------------------------


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate metrics for a list of per-question records."""
    answerable = [r for r in records if not r.get("expected_refusal")]
    refusal = [r for r in records if r.get("expected_refusal")]
    rec_vals = [
        r["retrieval_recall"]
        for r in answerable
        if r.get("retrieval_recall") is not None
    ]
    cit_vals = [
        r["citation_recall"]
        for r in answerable
        if r.get("citation_recall") is not None
    ]
    hall = sum(int(r.get("hallucinated_citations_count") or 0) for r in records)
    refusal_correct = sum(
        1
        for r in refusal
        if r.get("refusal_correct") is True
    )
    lat_vals = [
        r["latency_seconds"]
        for r in records
        if r.get("latency_seconds") is not None
    ]
    return {
        "n_records": len(records),
        "n_answerable": len(answerable),
        "n_refusal": len(refusal),
        "mean_retrieval_recall": mean(rec_vals) if rec_vals else None,
        "mean_citation_recall": mean(cit_vals) if cit_vals else None,
        "hallucinated_citations_total": hall,
        "refusal_correct": refusal_correct,
        "mean_latency_s": mean(lat_vals) if lat_vals else None,
    }


def _fmt(v: Any, *, places: int = 3) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{places}f}"
    return str(v)


def _delta(new: Any, old: Any, *, places: int = 3) -> str:
    if new is None or old is None:
        return "n/a"
    if isinstance(new, float) or isinstance(old, float):
        d = float(new) - float(old)
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.{places}f}"
    d = int(new) - int(old)
    sign = "+" if d >= 0 else ""
    return f"{sign}{d}"


# ---- Output -----------------------------------------------------------


def print_run_summary(runs: list[dict[str, Any]]) -> None:
    print("=" * 72)
    print("RUN SUMMARY")
    print("=" * 72)
    for i, run in enumerate(runs, 1):
        m = run["manifest"]["run"]
        print(f"[{i}] {run['dir'].name}")
        print(f"    timestamp:   {m.get('timestamp')}")
        print(f"    git:         {m.get('git_commit', '?')[:12]} "
              f"({m.get('git_branch', '?')})")
        if m.get("retrofit"):
            print(f"    retrofit:    yes (manifest authored after the fact)")
        cells = cells_in_run(run)
        print(f"    cells:       {len(cells)} -- {', '.join(cells.keys())}")
        desc = (m.get("description") or "").strip()
        if desc:
            for line in desc.splitlines():
                print(f"    | {line}")
        print()


def print_aggregate_comparison(
    cell_pair: tuple[str, str],
    runs: list[dict[str, Any]],
) -> None:
    old_id, new_id = cell_pair
    cells_old = cells_in_run(runs[0])
    cells_new = cells_in_run(runs[-1])
    old_records = records_for_cell(runs[0], cells_old[old_id])
    new_records = records_for_cell(runs[-1], cells_new[new_id])
    old_agg = aggregate(old_records)
    new_agg = aggregate(new_records)

    print("-" * 72)
    if old_id == new_id:
        header = f"Cell: {old_id}"
    else:
        header = f"Cell: {old_id} → {new_id}"
    print(header)
    use_hyde_old = cells_old[old_id].get("use_hyde", False)
    use_hyde_new = cells_new[new_id].get("use_hyde", False)
    if use_hyde_old != use_hyde_new:
        print(f"  use_hyde: {use_hyde_old} → {use_hyde_new}")
    print("-" * 72)
    rows = [
        ("n_records", old_agg["n_records"], new_agg["n_records"]),
        ("n_answerable", old_agg["n_answerable"], new_agg["n_answerable"]),
        (
            "mean_retrieval_recall",
            old_agg["mean_retrieval_recall"],
            new_agg["mean_retrieval_recall"],
        ),
        (
            "mean_citation_recall",
            old_agg["mean_citation_recall"],
            new_agg["mean_citation_recall"],
        ),
        (
            "hallucinated_citations_total",
            old_agg["hallucinated_citations_total"],
            new_agg["hallucinated_citations_total"],
        ),
        (
            "refusal_correct (of n_refusal)",
            f"{old_agg['refusal_correct']}/{old_agg['n_refusal']}",
            f"{new_agg['refusal_correct']}/{new_agg['n_refusal']}",
        ),
        (
            "mean_latency_s",
            old_agg["mean_latency_s"],
            new_agg["mean_latency_s"],
        ),
    ]
    print(f"  {'metric':<32}  {'run 1':>14}  {'run N':>14}  {'delta':>10}")
    print(f"  {'-' * 32}  {'-' * 14:>14}  {'-' * 14:>14}  {'-' * 10:>10}")
    for name, old_v, new_v in rows:
        d = _delta(new_v, old_v) if isinstance(old_v, (int, float, type(None))) and not (
            isinstance(old_v, str)
        ) else ""
        # The refusal_correct row uses string "N/M" — no delta there.
        if isinstance(old_v, str) and "/" in old_v:
            d = ""
        print(
            f"  {name:<32}  "
            f"{_fmt(old_v):>14}  "
            f"{_fmt(new_v):>14}  "
            f"{d:>10}"
        )
    print()


def print_per_question_changes(
    cell_pair: tuple[str, str],
    runs: list[dict[str, Any]],
    focus_questions: set[str],
) -> None:
    old_id, new_id = cell_pair
    cells_old = cells_in_run(runs[0])
    cells_new = cells_in_run(runs[-1])
    old_records = {
        r["question_id"]: r
        for r in records_for_cell(runs[0], cells_old[old_id])
    }
    new_records = {
        r["question_id"]: r
        for r in records_for_cell(runs[-1], cells_new[new_id])
    }
    shared = sorted(set(old_records) & set(new_records))
    changed: list[tuple[str, float | None, float | None]] = []
    for qid in shared:
        ov = old_records[qid].get("retrieval_recall")
        nv = new_records[qid].get("retrieval_recall")
        if ov != nv:
            changed.append((qid, ov, nv))

    print(f"  per-question retrieval_recall changes ({len(changed)} of "
          f"{len(shared)} answerable+matched)")
    if not changed and not focus_questions:
        print(f"    (none)")
        print()
        return

    # If focus_questions is set, also show those even if unchanged.
    extra = []
    if focus_questions:
        already = {qid for (qid, _, _) in changed}
        for qid in sorted(focus_questions):
            if qid not in already and qid in shared:
                extra.append(
                    (qid, old_records[qid].get("retrieval_recall"),
                     new_records[qid].get("retrieval_recall"))
                )

    print(f"    {'qid':<8}  {'run 1':>7}  {'run N':>7}  delta    note")
    print(f"    {'-' * 8}  {'-' * 7}  {'-' * 7}  {'-' * 6}  {'-' * 20}")
    for qid, ov, nv in changed + extra:
        note = ""
        if qid in focus_questions:
            if ov == 0.0 and nv and nv > 0.0:
                note = "RECOVERED (focus)"
            elif ov and ov > 0.0 and (nv is None or nv < ov):
                note = "REGRESSED (focus)"
            else:
                note = "focus"
        elif ov and ov >= 1.0 and (nv is None or nv < ov):
            note = "REGRESSION"
        elif (ov is None or ov == 0.0) and nv and nv > 0.0:
            note = "recovered"
        d = _delta(nv, ov)
        print(f"    {qid:<8}  {_fmt(ov):>7}  {_fmt(nv):>7}  {d:>6}  {note}")
    print()


# ---- CLI --------------------------------------------------------------


def parse_pair(arg: str) -> tuple[str, str]:
    if ":" not in arg:
        raise argparse.ArgumentTypeError(
            f"--pair expects OLD_ID:NEW_ID, got {arg!r}"
        )
    old, new = arg.split(":", 1)
    return old, new


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Compare two or more canonical sweep runs"
    )
    p.add_argument(
        "run_dirs",
        type=Path,
        nargs="+",
        help="paths to eval/results/<timestamp>/ directories",
    )
    p.add_argument(
        "--pair",
        type=parse_pair,
        action="append",
        default=[],
        metavar="OLD_ID:NEW_ID",
        help="pair a cell in run 1 to a renamed cell in the last run",
    )
    p.add_argument(
        "--focus-questions",
        type=str,
        default="",
        help="comma-separated qids to highlight (e.g. Q14 mechanism-clear)",
    )
    args = p.parse_args(argv)

    if len(args.run_dirs) < 2:
        print("ERROR: need at least 2 run directories", file=sys.stderr)
        return 1

    runs = [load_run(d) for d in args.run_dirs]
    focus = {q.strip() for q in args.focus_questions.split(",") if q.strip()}

    print_run_summary(runs)

    pairs = resolve_pairs(runs, args.pair)
    if not pairs:
        print(
            "ERROR: no cell pairs to compare. Use --pair OLD_ID:NEW_ID "
            "if cell ids differ across runs.",
            file=sys.stderr,
        )
        return 1

    for pair in pairs:
        print_aggregate_comparison(pair, runs)
        print_per_question_changes(pair, runs, focus)

    return 0


if __name__ == "__main__":
    sys.exit(main())
