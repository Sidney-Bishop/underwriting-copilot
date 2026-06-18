"""Aggregate ``raw.jsonl`` from a sweep run into a Markdown report.

Reads ``eval/results/<timestamp>/{raw.jsonl, run_meta.json}`` (or any
run directory passed via ``--run-dir``) and writes ``report.md`` into
the same directory. Deterministic: same raw.jsonl always produces the
same report. Replaces the journal's eyeballed numbers with
reproducible aggregates generated from the per-cell records.

Sections produced, in order:

1. **Run metadata** — what was swept, when, how long.
2. **Headline 4-cell summary** — citation_recall, precision, refusal,
   hallucinations, latency per ``(model, prompt)`` cell.
3. **Subset analysis** — citation_recall by question subset
   (single-chunk retrievable, within-document, cross-document, etc).
   This is where the within-document parity finding becomes visible
   in numeric form.
4. **Refusal correctness by category** — out_of_corpus, adjacent,
   false_premise broken out separately.
5. **Retrieval miss diagnostic** — question IDs where
   ``retrieval_recall = 0`` across all cells (the Q12 finding).
6. **Hallucination breakdown** — count per cell, total per model.
7. **Latency** — mean and median per cell, split answerable vs
   refusal.
8. **Per-question detail** — two tables, one per question type.
9. **Errored cells** — any cells with ``cell_status="error"``.

CLI defaults to the latest run directory under ``eval/results/``.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_RESULTS_ROOT = Path("eval/results")


# ---- Data classes ------------------------------------------------------


@dataclass(frozen=True)
class CellSummary:
    """Per-(model, prompt) aggregate. Citation/retrieval metrics are over
    answerable cells only; refusal metrics are over refusal cells only."""

    model: str
    prompt_version: str
    n_answerable: int
    n_refusal: int
    citation_recall_mean: float | None
    citation_precision_mean: float | None
    citation_f1_mean: float | None
    retrieval_recall_mean: float | None
    refusal_correct_count: int
    refusal_total: int
    total_hallucinations: int
    latency_answerable_mean: float | None
    latency_answerable_median: float | None
    latency_refusal_mean: float | None
    latency_refusal_median: float | None
    error_count: int


@dataclass(frozen=True)
class SubsetSummary:
    """Mean citation_recall on a question subset, broken out per cell."""

    name: str
    description: str
    n_questions: int
    by_cell: dict[tuple[str, str], float]  # (model, prompt) -> mean recall


@dataclass(frozen=True)
class RefusalCategorySummary:
    """Refusal correctness for one refusal category (e.g. out_of_corpus)."""

    category: str
    n_questions: int
    by_cell: dict[tuple[str, str], tuple[int, int]]  # (model, prompt) -> (correct, total)


@dataclass(frozen=True)
class Report:
    """Aggregated view of one sweep run."""

    meta: dict[str, Any]
    cells: list[CellSummary]
    subsets: list[SubsetSummary]
    refusal_categories: list[RefusalCategorySummary]
    retrieval_misses: list[str]  # question_ids where retrieval_recall=0 across all answerable cells
    error_cells: list[dict[str, Any]]
    questions_by_category: dict[str, list[str]] = field(default_factory=dict)


# ---- Loading -----------------------------------------------------------


def load_records(jsonl_path: Path) -> list[dict[str, Any]]:
    """Load per-cell records from a JSONL file. Order preserved."""
    records: list[dict[str, Any]] = []
    with open(jsonl_path) as fp:
        for line in fp:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_meta(meta_path: Path) -> dict[str, Any]:
    """Load sweep metadata from ``run_meta.json``."""
    with open(meta_path) as fp:
        return json.load(fp)


def find_latest_run_dir(results_root: Path) -> Path:
    """Return the most recently modified subdirectory of ``results_root``.

    Raises ``SystemExit`` if no run directories exist.
    """
    if not results_root.exists():
        raise SystemExit(f"No results directory at {results_root}")
    subdirs = [p for p in results_root.iterdir() if p.is_dir()]
    if not subdirs:
        raise SystemExit(f"No run directories in {results_root}")
    return max(subdirs, key=lambda p: p.stat().st_mtime)


# ---- Aggregation helpers -----------------------------------------------


def _safe_mean(xs: list[float]) -> float | None:
    """Return mean of a list, or None for empty input.

    Filters out None values (refusal questions have None citation
    metrics, errored cells have no metrics at all).
    """
    filtered = [x for x in xs if x is not None]
    return statistics.mean(filtered) if filtered else None


def _safe_median(xs: list[float]) -> float | None:
    filtered = [x for x in xs if x is not None]
    return statistics.median(filtered) if filtered else None


def summarize_cell(
    records: list[dict[str, Any]], model: str, prompt_version: str
) -> CellSummary:
    """Build a CellSummary for one ``(model, prompt)`` combination."""
    cell = [r for r in records if r["model"] == model and r["prompt_version"] == prompt_version]
    ok = [r for r in cell if r.get("cell_status") == "ok"]
    errored = [r for r in cell if r.get("cell_status") == "error"]
    answerable = [r for r in ok if not r["expected_refusal"]]
    refusal = [r for r in ok if r["expected_refusal"]]

    return CellSummary(
        model=model,
        prompt_version=prompt_version,
        n_answerable=len(answerable),
        n_refusal=len(refusal),
        citation_recall_mean=_safe_mean([r["citation_recall"] for r in answerable]),
        citation_precision_mean=_safe_mean([r["citation_precision"] for r in answerable]),
        citation_f1_mean=_safe_mean([r["citation_f1"] for r in answerable]),
        retrieval_recall_mean=_safe_mean([r["retrieval_recall"] for r in answerable]),
        refusal_correct_count=sum(1 for r in refusal if r["refusal_correct"]),
        refusal_total=len(refusal),
        total_hallucinations=sum(r.get("hallucinated_citations_count", 0) for r in ok),
        latency_answerable_mean=_safe_mean([r["latency_seconds"] for r in answerable]),
        latency_answerable_median=_safe_median([r["latency_seconds"] for r in answerable]),
        latency_refusal_mean=_safe_mean([r["latency_seconds"] for r in refusal]),
        latency_refusal_median=_safe_median([r["latency_seconds"] for r in refusal]),
        error_count=len(errored),
    )


def find_retrieval_misses(records: list[dict[str, Any]]) -> list[str]:
    """Return question IDs where retrieval_recall = 0 across all
    answerable cells.

    Refusal questions (expected_refusal=True, gold empty, retrieval_recall=None)
    are excluded. Cells with cell_status=error are excluded.
    """
    by_qid: dict[str, list[float | None]] = defaultdict(list)
    for r in records:
        if r.get("cell_status") != "ok":
            continue
        if r["expected_refusal"]:
            continue
        by_qid[r["question_id"]].append(r["retrieval_recall"])

    misses = []
    for qid, recalls in by_qid.items():
        # All recalls must be 0.0 (not None — None means refusal, which
        # we already excluded). If all 0.0, no model/prompt found gold.
        if recalls and all(r == 0.0 for r in recalls):
            misses.append(qid)
    return sorted(misses)


def _list_cells(records: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return sorted unique (model, prompt) pairs from the records."""
    return sorted({(r["model"], r["prompt_version"]) for r in records})


def compute_subsets(
    records: list[dict[str, Any]], retrieval_misses: list[str]
) -> list[SubsetSummary]:
    """Compute citation_recall by subset across question categories.

    Subsets defined here illuminate the within-document vs cross-document
    finding from Day 3 — together they show that the headline 3.2pp
    Gemma-Qwen v2 gap is concentrated in 2 cross-document questions and
    that within-document workloads are tied.
    """
    miss_set = set(retrieval_misses)
    cells = _list_cells(records)
    answerable = [
        r for r in records
        if r.get("cell_status") == "ok" and not r["expected_refusal"]
    ]

    # Each entry: (name, description, predicate over record)
    subset_specs = [
        ("all_answerable",
         "All answerable questions",
         lambda r: True),
        ("excluding_retrieval_misses",
         "Excluding questions where retrieval failed across all cells",
         lambda r: r["question_id"] not in miss_set),
        ("single_chunk",
         "Single-chunk questions (one gold chunk per question)",
         lambda r: r["category"].startswith("single_chunk_")),
        ("single_chunk_retrievable",
         "Single-chunk questions with retrieval working",
         lambda r: r["category"].startswith("single_chunk_") and r["question_id"] not in miss_set),
        ("multi_chunk",
         "Multi-chunk questions (multiple gold chunks, same document)",
         lambda r: r["category"].startswith("multi_chunk_")),
        ("within_document",
         "Within-document questions (single + multi, no cross-document)",
         lambda r: r["category"].startswith("single_chunk_")
                   or r["category"].startswith("multi_chunk_")),
        ("within_document_retrievable",
         "Within-document with retrieval working",
         lambda r: (r["category"].startswith("single_chunk_")
                    or r["category"].startswith("multi_chunk_"))
                   and r["question_id"] not in miss_set),
        ("cross_document",
         "Cross-document synthesis questions (gold chunks span two issuers)",
         lambda r: r["category"] == "cross_document"),
    ]

    subsets: list[SubsetSummary] = []
    for name, description, predicate in subset_specs:
        filtered = [r for r in answerable if predicate(r)]
        n_questions = len({r["question_id"] for r in filtered})
        by_cell: dict[tuple[str, str], float] = {}
        for cell in cells:
            cell_records = [
                r for r in filtered
                if r["model"] == cell[0] and r["prompt_version"] == cell[1]
            ]
            mean = _safe_mean([r["citation_recall"] for r in cell_records])
            if mean is not None:
                by_cell[cell] = mean
        subsets.append(SubsetSummary(
            name=name,
            description=description,
            n_questions=n_questions,
            by_cell=by_cell,
        ))
    return subsets


def compute_refusal_categories(
    records: list[dict[str, Any]]
) -> list[RefusalCategorySummary]:
    """Break refusal correctness down by category.

    Each refusal question's ``category`` should be one of
    ``refusal_out_of_corpus``, ``refusal_adjacent``,
    ``refusal_false_premise`` per the benchmark spec. Other refusal
    categories surface here too if added later.
    """
    cells = _list_cells(records)
    refusal_records = [
        r for r in records
        if r.get("cell_status") == "ok" and r["expected_refusal"]
    ]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in refusal_records:
        by_category[r["category"]].append(r)

    summaries: list[RefusalCategorySummary] = []
    for category in sorted(by_category):
        records_for_cat = by_category[category]
        n_questions = len({r["question_id"] for r in records_for_cat})
        by_cell: dict[tuple[str, str], tuple[int, int]] = {}
        for cell in cells:
            cell_records = [
                r for r in records_for_cat
                if r["model"] == cell[0] and r["prompt_version"] == cell[1]
            ]
            correct = sum(1 for r in cell_records if r["refusal_correct"])
            total = len(cell_records)
            by_cell[cell] = (correct, total)
        summaries.append(RefusalCategorySummary(
            category=category,
            n_questions=n_questions,
            by_cell=by_cell,
        ))
    return summaries


def collect_error_cells(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return raw error records for the report's error section."""
    return [r for r in records if r.get("cell_status") == "error"]


def collect_questions_by_category(
    records: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """Map each category to its sorted list of question IDs.

    Question IDs may appear under more than one cell; this returns
    unique IDs.
    """
    by_cat: dict[str, set[str]] = defaultdict(set)
    for r in records:
        by_cat[r["category"]].add(r["question_id"])
    return {cat: sorted(qids) for cat, qids in by_cat.items()}


def build_report(records: list[dict[str, Any]], meta: dict[str, Any]) -> Report:
    """Compose a complete Report from raw records + metadata."""
    cells = _list_cells(records)
    retrieval_misses = find_retrieval_misses(records)
    return Report(
        meta=meta,
        cells=[summarize_cell(records, m, p) for m, p in cells],
        subsets=compute_subsets(records, retrieval_misses),
        refusal_categories=compute_refusal_categories(records),
        retrieval_misses=retrieval_misses,
        error_cells=collect_error_cells(records),
        questions_by_category=collect_questions_by_category(records),
    )


# ---- Rendering ---------------------------------------------------------


def _fmt(x: float | None, precision: int = 3) -> str:
    """Render a metric value with consistent precision, or '—' for None."""
    return "—" if x is None else f"{x:.{precision}f}"


def _fmt_latency(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f}s"


def _cell_label(model: str, prompt_version: str) -> str:
    """Short label for the cell in tables (avoid huge column headers)."""
    # Trim "MLX-6bit" / "MLX-4bit" suffixes and family-only prefix
    # patterns to keep tables readable.
    short = model
    for suffix in ("-it-MLX-6bit", "-MLX-4bit", "-MLX-6bit"):
        if short.endswith(suffix):
            short = short[: -len(suffix)]
            break
    return f"{short} × {prompt_version}"


def render_markdown(report: Report) -> str:
    """Render a full Markdown report from the aggregated data."""
    lines: list[str] = []

    # ---- 1. Run metadata
    lines.append(f"# Eval Report — D014 Sweep")
    lines.append("")
    lines.append(f"**Generated from:** `raw.jsonl` at "
                 f"`{report.meta.get('timestamp_utc', '(unknown timestamp)')}`")
    lines.append("")
    lines.append("## Run metadata")
    lines.append("")
    lines.append(f"- Models swept: {', '.join(f'`{m}`' for m in report.meta.get('models', []))}")
    lines.append(f"- Prompts swept: {', '.join(f'`{p}`' for p in report.meta.get('prompts', []))}")
    lines.append(f"- Benchmark: `{report.meta.get('benchmark_path', '(unknown)')}`")
    lines.append(f"- Question count after filter: {report.meta.get('question_count', '?')}")
    lines.append(f"- Total cells: {report.meta.get('total_cells', '?')}")
    lines.append(f"- Errored cells: {report.meta.get('error_cells', '?')}")
    lines.append(f"- Wall-clock: {report.meta.get('elapsed_seconds', 0):.1f}s "
                 f"({report.meta.get('elapsed_seconds', 0)/60:.1f} min)")
    lines.append(f"- Run completed cleanly: {report.meta.get('completed', '?')}")
    lines.append(f"- top_k: {report.meta.get('top_k', '?')}")
    lines.append("")

    # ---- 2. Headline 4-cell summary
    lines.append("## Headline: per-cell summary")
    lines.append("")
    if report.cells:
        n_ans = report.cells[0].n_answerable
        n_ref = report.cells[0].n_refusal
        lines.append(f"Metrics over {n_ans} answerable + {n_ref} refusal "
                     f"questions per cell.")
        lines.append("")
    lines.append("| Cell | citation_recall | citation_precision | "
                 "citation_f1 | refusal | hallucinations | latency_ans | latency_ref |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in report.cells:
        refusal_str = f"{c.refusal_correct_count}/{c.refusal_total}"
        lines.append(
            f"| {_cell_label(c.model, c.prompt_version)} "
            f"| {_fmt(c.citation_recall_mean)} "
            f"| {_fmt(c.citation_precision_mean)} "
            f"| {_fmt(c.citation_f1_mean)} "
            f"| {refusal_str} "
            f"| {c.total_hallucinations} "
            f"| {_fmt_latency(c.latency_answerable_mean)} "
            f"| {_fmt_latency(c.latency_refusal_mean)} |"
        )
    lines.append("")

    # ---- 3. Subset analysis
    lines.append("## Subset analysis — citation_recall by question subset")
    lines.append("")
    lines.append("Where the headline numbers come from. Differences between "
                 "subsets localize whether a model gap is concentrated in a "
                 "specific question type or spread evenly.")
    lines.append("")
    cells = _cells_in_report(report)
    header_cells = " | ".join(_cell_label(m, p) for m, p in cells)
    sep_cells = " | ".join(["---"] * len(cells))
    lines.append(f"| Subset | n | {header_cells} |")
    lines.append(f"|---|---|{sep_cells}|")
    for s in report.subsets:
        cell_values = " | ".join(
            _fmt(s.by_cell.get((m, p))) for m, p in cells
        )
        lines.append(f"| {s.name} | {s.n_questions} | {cell_values} |")
    lines.append("")
    lines.append("**Subset definitions:**")
    for s in report.subsets:
        lines.append(f"- `{s.name}` ({s.n_questions} q): {s.description}")
    lines.append("")

    # ---- 4. Refusal correctness by category
    lines.append("## Refusal correctness by category")
    lines.append("")
    if report.refusal_categories:
        lines.append("Each cell: `correct / total`. Higher is better; "
                     "the production-relevant failure mode is should-refuse "
                     "questions answered as if confidently known.")
        lines.append("")
        header_cells = " | ".join(_cell_label(m, p) for m, p in cells)
        sep_cells = " | ".join(["---"] * len(cells))
        lines.append(f"| Category | n | {header_cells} |")
        lines.append(f"|---|---|{sep_cells}|")
        for cat_summary in report.refusal_categories:
            cell_values = " | ".join(
                f"{cat_summary.by_cell.get((m, p), (0, 0))[0]}/"
                f"{cat_summary.by_cell.get((m, p), (0, 0))[1]}"
                for m, p in cells
            )
            lines.append(f"| {cat_summary.category} | {cat_summary.n_questions} "
                         f"| {cell_values} |")
        lines.append("")
    else:
        lines.append("_No refusal questions in this run._")
        lines.append("")

    # ---- 5. Retrieval miss diagnostic
    lines.append("## Retrieval miss diagnostic")
    lines.append("")
    if report.retrieval_misses:
        n_answerable = report.cells[0].n_answerable if report.cells else 0
        pct = 100.0 * len(report.retrieval_misses) / n_answerable if n_answerable else 0
        lines.append(f"**{len(report.retrieval_misses)} of {n_answerable} "
                     f"answerable questions ({pct:.1f}%)** had "
                     f"`retrieval_recall = 0` across **all** cells — the gold "
                     f"chunks were not retrieved by any model/prompt "
                     f"combination. This localizes the failures as upstream "
                     f"of the answer model; see Q12 in `decisions.md`.")
        lines.append("")
        lines.append("Affected questions:")
        for qid in report.retrieval_misses:
            lines.append(f"- `{qid}`")
        lines.append("")
    else:
        lines.append("_All answerable questions had their gold chunks "
                     "retrieved in at least one cell._")
        lines.append("")

    # ---- 6. Hallucinations
    lines.append("## Hallucination breakdown")
    lines.append("")
    lines.append("Citations the model emitted that did **not** correspond "
                 "to any retrieved chunk. Confabulation signal — "
                 "qualitatively different from 'wrong but real chunk cited'.")
    lines.append("")
    lines.append("| Cell | Hallucinations (all answerable cells) |")
    lines.append("|---|---|")
    for c in report.cells:
        lines.append(f"| {_cell_label(c.model, c.prompt_version)} "
                     f"| {c.total_hallucinations} |")
    lines.append("")

    # ---- 7. Latency
    lines.append("## Latency")
    lines.append("")
    lines.append("Mean and median wall-clock per cell, split by question type.")
    lines.append("")
    lines.append("| Cell | mean_ans | median_ans | mean_ref | median_ref |")
    lines.append("|---|---|---|---|---|")
    for c in report.cells:
        lines.append(
            f"| {_cell_label(c.model, c.prompt_version)} "
            f"| {_fmt_latency(c.latency_answerable_mean)} "
            f"| {_fmt_latency(c.latency_answerable_median)} "
            f"| {_fmt_latency(c.latency_refusal_mean)} "
            f"| {_fmt_latency(c.latency_refusal_median)} |"
        )
    lines.append("")

    # ---- 8. Per-question detail (answerable)
    lines.append("## Per-question detail — answerable")
    lines.append("")
    lines.append("Each cell shows `citation_recall` (None for refusal questions, "
                 "which appear in the next table). Categories abbreviated for "
                 "table width.")
    lines.append("")
    header_cells = " | ".join(_cell_label(m, p) for m, p in cells)
    sep_cells = " | ".join(["---"] * len(cells))
    lines.append(f"| ID | category | {header_cells} |")
    lines.append(f"|---|---|{sep_cells}|")
    # Build a per-question lookup
    answerable_by_qid = _per_question_recall(report)
    answerable_qids = sorted(_answerable_qids(report))
    for qid in answerable_qids:
        cat = answerable_by_qid[qid].get("category", "?")
        cell_values = " | ".join(
            _fmt(answerable_by_qid[qid].get((m, p)), precision=2)
            for m, p in cells
        )
        lines.append(f"| `{qid}` | `{cat}` | {cell_values} |")
    lines.append("")

    # ---- Per-question detail (refusal)
    lines.append("## Per-question detail — refusal")
    lines.append("")
    lines.append("Each cell shows `✓` (refused correctly) or `✗` (failed to refuse).")
    lines.append("")
    lines.append(f"| ID | category | {header_cells} |")
    lines.append(f"|---|---|{sep_cells}|")
    refusal_by_qid = _per_question_refusal(report)
    refusal_qids = sorted(_refusal_qids(report))
    for qid in refusal_qids:
        cat = refusal_by_qid[qid].get("category", "?")
        cell_values = " | ".join(
            "✓" if refusal_by_qid[qid].get((m, p)) is True
            else ("✗" if refusal_by_qid[qid].get((m, p)) is False else "—")
            for m, p in cells
        )
        lines.append(f"| `{qid}` | `{cat}` | {cell_values} |")
    lines.append("")

    # ---- 9. Errored cells
    lines.append("## Errored cells")
    lines.append("")
    if report.error_cells:
        lines.append(f"{len(report.error_cells)} cells errored:")
        lines.append("")
        for e in report.error_cells:
            lines.append(f"- `{e['question_id']}` × `{e['model']}` × "
                         f"`{e['prompt_version']}`: {e.get('error_message', '(no message)')}")
        lines.append("")
    else:
        lines.append("_No cells errored. All cells completed cleanly._")
        lines.append("")

    return "\n".join(lines)


# ---- Per-question helpers (kept out of build_report to avoid bloating it) ----


def _cells_in_report(report: Report) -> list[tuple[str, str]]:
    return [(c.model, c.prompt_version) for c in report.cells]


def _answerable_qids(report: Report) -> set[str]:
    """Question IDs that appear in any non-refusal category."""
    qids = set()
    for cat, q_list in report.questions_by_category.items():
        if not cat.startswith("refusal_"):
            qids.update(q_list)
    return qids


def _refusal_qids(report: Report) -> set[str]:
    qids = set()
    for cat, q_list in report.questions_by_category.items():
        if cat.startswith("refusal_"):
            qids.update(q_list)
    return qids


def _per_question_recall(report: Report) -> dict[str, dict]:
    """Build lookup: question_id → {(model, prompt) → recall, "category" → cat}.

    Requires re-reading the records, but report doesn't carry them.
    Reconstructed from category map for category, recall reconstructed
    by reading raw.jsonl. Caller is expected to populate this from
    elsewhere; here we return an empty-shaped dict and the renderer
    handles missing values.
    """
    # The renderer fills this in via a side-channel — see main().
    return getattr(report, "_per_question_answerable", {})


def _per_question_refusal(report: Report) -> dict[str, dict]:
    return getattr(report, "_per_question_refusal", {})


def attach_per_question_detail(report: Report, records: list[dict[str, Any]]) -> Report:
    """Mutate a Report to attach per-question detail dicts.

    Pragmatic side-channel — keeping these in the Report dataclass would
    bloat it for what's a render-only concern. The renderer reads the
    underscore-prefixed attributes if present.

    Errored cells get an entry created with ``category`` set and no
    per-(model, prompt) keys — the renderer fills those slots with the
    None placeholder. Without this, questions that only appear as
    errored cells in the run cause a KeyError in the renderer.
    """
    answerable: dict[str, dict] = {}
    refusal: dict[str, dict] = {}
    for r in records:
        qid = r["question_id"]
        # Errored cells still need a stub entry so the per-question
        # tables can show the row with empty cells. The expected_refusal
        # field is preserved on error records by make_error_record in
        # runner.py, so we can route correctly.
        target = refusal if r.get("expected_refusal") else answerable
        if qid not in target:
            target[qid] = {"category": r.get("category", "?")}
        if r.get("cell_status") != "ok":
            continue  # don't write a per-cell value for errored cells
        key = (r["model"], r["prompt_version"])
        if r["expected_refusal"]:
            target[qid][key] = bool(r["refusal_correct"])
        else:
            target[qid][key] = r["citation_recall"]
    # Frozen dataclass — use object.__setattr__ to bypass.
    object.__setattr__(report, "_per_question_answerable", answerable)
    object.__setattr__(report, "_per_question_refusal", refusal)
    return report


# ---- CLI ---------------------------------------------------------------


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eval.report",
        description="Aggregate a sweep's raw.jsonl into a Markdown report.",
    )
    p.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help=f"Sweep results directory containing raw.jsonl and run_meta.json. "
             f"Default: latest run in {DEFAULT_RESULTS_ROOT}/.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the Markdown report. Default: <run-dir>/report.md.",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the report to stdout after writing.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    run_dir = args.run_dir if args.run_dir else find_latest_run_dir(DEFAULT_RESULTS_ROOT)
    raw_path = run_dir / "raw.jsonl"
    meta_path = run_dir / "run_meta.json"

    if not raw_path.exists():
        raise SystemExit(f"Missing: {raw_path}")
    if not meta_path.exists():
        raise SystemExit(f"Missing: {meta_path}")

    print(f"Reading {raw_path}...")
    records = load_records(raw_path)
    print(f"  {len(records)} records")
    meta = load_meta(meta_path)

    print("Building report...")
    report = build_report(records, meta)
    attach_per_question_detail(report, records)

    md = render_markdown(report)

    output_path = args.output if args.output else run_dir / "report.md"
    output_path.write_text(md)
    print(f"Wrote {output_path} ({len(md.splitlines())} lines)")

    if args.stdout:
        print()
        print(md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
