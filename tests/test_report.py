"""Unit tests for ``eval/report.py``.

Focus on the pure aggregation functions. The renderer is exercised
once with a smoke test that confirms it produces a Markdown string
with the expected section headers; the rendered numeric values are
verified via the underlying aggregation functions, not by string-
matching the output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.report import (
    CellSummary,
    Report,
    RefusalCategorySummary,
    SubsetSummary,
    attach_per_question_detail,
    build_report,
    collect_error_cells,
    collect_questions_by_category,
    compute_refusal_categories,
    compute_subsets,
    find_latest_run_dir,
    find_retrieval_misses,
    load_meta,
    load_records,
    render_markdown,
    summarize_cell,
)


# ---- Synthetic record builders -----------------------------------------


def _ok_answerable(
    qid: str,
    model: str,
    prompt: str,
    category: str,
    *,
    citation_recall: float = 1.0,
    citation_precision: float = 1.0,
    citation_f1: float | None = None,
    retrieval_recall: float = 1.0,
    hallucinations: int = 0,
    latency: float = 5.0,
) -> dict:
    if citation_f1 is None:
        if citation_recall + citation_precision == 0:
            citation_f1 = 0.0
        else:
            citation_f1 = 2 * citation_recall * citation_precision / (
                citation_recall + citation_precision
            )
    return {
        "question_id": qid,
        "category": category,
        "model": model,
        "prompt_version": prompt,
        "expected_refusal": False,
        "actual_refused": False,
        "refusal_correct": True,
        "citation_recall": citation_recall,
        "citation_precision": citation_precision,
        "citation_f1": citation_f1,
        "total_citations_count": 1,
        "unique_citations_count": 1,
        "extra_citations_count": 0,
        "hallucinated_citations_count": hallucinations,
        "retrieval_recall": retrieval_recall,
        "latency_seconds": latency,
        "answer_text": "...",
        "cited_chunks": ["c1"],
        "hallucinated_citations": [],
        "gold_chunk_ids": ["c1"],
        "retrieved_chunk_ids": ["c1"],
        "cell_status": "ok",
        "error_message": None,
    }


def _ok_refusal(
    qid: str,
    model: str,
    prompt: str,
    category: str,
    *,
    refused: bool = True,
    latency: float = 1.0,
) -> dict:
    return {
        "question_id": qid,
        "category": category,
        "model": model,
        "prompt_version": prompt,
        "expected_refusal": True,
        "actual_refused": refused,
        "refusal_correct": refused,
        "citation_recall": None,
        "citation_precision": None,
        "citation_f1": None,
        "total_citations_count": 0,
        "unique_citations_count": 0,
        "extra_citations_count": 0,
        "hallucinated_citations_count": 0,
        "retrieval_recall": None,
        "latency_seconds": latency,
        "answer_text": "I cannot answer this from the provided sources.",
        "cited_chunks": [],
        "hallucinated_citations": [],
        "gold_chunk_ids": [],
        "retrieved_chunk_ids": ["x"],
        "cell_status": "ok",
        "error_message": None,
    }


def _err(qid: str, model: str, prompt: str, msg: str = "HTTP 500") -> dict:
    return {
        "question_id": qid,
        "category": "test_cat",
        "model": model,
        "prompt_version": prompt,
        "cell_status": "error",
        "error_message": msg,
        "expected_refusal": False,
    }


# ============================================================================
# summarize_cell
# ============================================================================


class TestSummarizeCell:
    def test_pure_answerable_cell(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x", citation_recall=1.0),
            _ok_answerable("q2", "m", "v1", "single_chunk_x", citation_recall=0.5),
        ]
        s = summarize_cell(recs, "m", "v1")
        assert s.n_answerable == 2
        assert s.n_refusal == 0
        assert s.citation_recall_mean == 0.75
        assert s.refusal_correct_count == 0
        assert s.refusal_total == 0
        assert s.total_hallucinations == 0

    def test_mixed_answerable_and_refusal(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x", citation_recall=0.8),
            _ok_refusal("q2", "m", "v1", "refusal_out_of_corpus", refused=True),
            _ok_refusal("q3", "m", "v1", "refusal_adjacent", refused=False),
        ]
        s = summarize_cell(recs, "m", "v1")
        assert s.n_answerable == 1
        assert s.n_refusal == 2
        assert s.citation_recall_mean == 0.8
        assert s.refusal_correct_count == 1
        assert s.refusal_total == 2

    def test_errors_excluded_from_metrics(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "x", citation_recall=1.0),
            _err("q2", "m", "v1"),
        ]
        s = summarize_cell(recs, "m", "v1")
        assert s.n_answerable == 1
        assert s.citation_recall_mean == 1.0
        assert s.error_count == 1

    def test_other_cells_filtered_out(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "x", citation_recall=1.0),
            _ok_answerable("q1", "m2", "v1", "x", citation_recall=0.0),
            _ok_answerable("q1", "m", "v2", "x", citation_recall=0.0),
        ]
        s = summarize_cell(recs, "m", "v1")
        # Only the (m, v1) cell — its single answerable has recall 1.0
        assert s.n_answerable == 1
        assert s.citation_recall_mean == 1.0

    def test_empty_cell_returns_none_metrics(self) -> None:
        s = summarize_cell([], "m", "v1")
        assert s.n_answerable == 0
        assert s.n_refusal == 0
        assert s.citation_recall_mean is None
        assert s.latency_answerable_mean is None

    def test_hallucinations_summed(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "x", hallucinations=2),
            _ok_answerable("q2", "m", "v1", "x", hallucinations=3),
            _ok_refusal("q3", "m", "v1", "refusal_x"),
        ]
        s = summarize_cell(recs, "m", "v1")
        # Refusal records have 0 hallucinations by construction
        assert s.total_hallucinations == 5

    def test_latency_mean_and_median(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "x", latency=2.0),
            _ok_answerable("q2", "m", "v1", "x", latency=4.0),
            _ok_answerable("q3", "m", "v1", "x", latency=6.0),
        ]
        s = summarize_cell(recs, "m", "v1")
        assert s.latency_answerable_mean == 4.0
        assert s.latency_answerable_median == 4.0


# ============================================================================
# find_retrieval_misses
# ============================================================================


class TestFindRetrievalMisses:
    def test_question_missed_across_all_cells(self) -> None:
        recs = [
            _ok_answerable("q1", "m1", "v1", "x", retrieval_recall=0.0),
            _ok_answerable("q1", "m2", "v1", "x", retrieval_recall=0.0),
            _ok_answerable("q1", "m1", "v2", "x", retrieval_recall=0.0),
            _ok_answerable("q1", "m2", "v2", "x", retrieval_recall=0.0),
        ]
        assert find_retrieval_misses(recs) == ["q1"]

    def test_question_found_in_one_cell_is_not_a_miss(self) -> None:
        recs = [
            _ok_answerable("q1", "m1", "v1", "x", retrieval_recall=0.0),
            _ok_answerable("q1", "m2", "v1", "x", retrieval_recall=1.0),
            _ok_answerable("q1", "m1", "v2", "x", retrieval_recall=0.0),
            _ok_answerable("q1", "m2", "v2", "x", retrieval_recall=0.0),
        ]
        assert find_retrieval_misses(recs) == []

    def test_refusal_questions_excluded(self) -> None:
        # Refusal questions have retrieval_recall=None, which doesn't equal 0.0
        recs = [
            _ok_refusal("q1", "m1", "v1", "refusal_x"),
            _ok_refusal("q1", "m2", "v1", "refusal_x"),
        ]
        assert find_retrieval_misses(recs) == []

    def test_errored_cells_dont_falsely_create_misses(self) -> None:
        # If q1 errored on m2/v1 but found gold on m1/v1, it's not a miss
        recs = [
            _ok_answerable("q1", "m1", "v1", "x", retrieval_recall=1.0),
            _err("q1", "m2", "v1"),
        ]
        assert find_retrieval_misses(recs) == []

    def test_multiple_misses_returned_sorted(self) -> None:
        recs = []
        for qid in ["q005", "q001", "q010"]:
            for m, p in [("m1", "v1"), ("m1", "v2")]:
                recs.append(_ok_answerable(qid, m, p, "x", retrieval_recall=0.0))
        misses = find_retrieval_misses(recs)
        assert misses == sorted(misses)
        assert misses == ["q001", "q005", "q010"]


# ============================================================================
# compute_subsets
# ============================================================================


class TestComputeSubsets:
    def test_within_document_vs_cross_document(self) -> None:
        # 2 single-chunk + 1 multi-chunk + 1 cross-doc, all retrievable
        # gemma_v2 perfect on all; qwen_v2 perfect on within-doc, 0 on cross-doc
        recs = [
            _ok_answerable("q1", "g", "v2", "single_chunk_pra", citation_recall=1.0),
            _ok_answerable("q2", "g", "v2", "single_chunk_eiopa", citation_recall=1.0),
            _ok_answerable("q3", "g", "v2", "multi_chunk_pra", citation_recall=1.0),
            _ok_answerable("q4", "g", "v2", "cross_document", citation_recall=0.5),
            _ok_answerable("q1", "q", "v2", "single_chunk_pra", citation_recall=1.0),
            _ok_answerable("q2", "q", "v2", "single_chunk_eiopa", citation_recall=1.0),
            _ok_answerable("q3", "q", "v2", "multi_chunk_pra", citation_recall=1.0),
            _ok_answerable("q4", "q", "v2", "cross_document", citation_recall=0.0),
        ]
        subsets = compute_subsets(recs, retrieval_misses=[])
        by_name = {s.name: s for s in subsets}

        # Within-doc subset: Gemma and Qwen both perfect on n=3
        wd = by_name["within_document"]
        assert wd.n_questions == 3
        assert wd.by_cell[("g", "v2")] == 1.0
        assert wd.by_cell[("q", "v2")] == 1.0

        # Cross-doc: Gemma 0.5, Qwen 0.0 on n=1
        cd = by_name["cross_document"]
        assert cd.n_questions == 1
        assert cd.by_cell[("g", "v2")] == 0.5
        assert cd.by_cell[("q", "v2")] == 0.0

    def test_excluding_retrieval_misses_drops_zero_recall_question(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x",
                           citation_recall=0.0, retrieval_recall=0.0),
            _ok_answerable("q2", "m", "v1", "single_chunk_x",
                           citation_recall=1.0, retrieval_recall=1.0),
        ]
        # If q1 is in retrieval_misses, the excluding subset should only see q2
        subsets = compute_subsets(recs, retrieval_misses=["q1"])
        by_name = {s.name: s for s in subsets}

        # All answerable: n=2, mean recall (0+1)/2 = 0.5
        assert by_name["all_answerable"].n_questions == 2
        assert by_name["all_answerable"].by_cell[("m", "v1")] == 0.5

        # Excluding retrieval misses: n=1, mean recall 1.0
        assert by_name["excluding_retrieval_misses"].n_questions == 1
        assert by_name["excluding_retrieval_misses"].by_cell[("m", "v1")] == 1.0

    def test_single_chunk_subset_excludes_multi(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x", citation_recall=1.0),
            _ok_answerable("q2", "m", "v1", "multi_chunk_x", citation_recall=0.5),
        ]
        subsets = compute_subsets(recs, retrieval_misses=[])
        by_name = {s.name: s for s in subsets}
        assert by_name["single_chunk"].n_questions == 1
        assert by_name["single_chunk"].by_cell[("m", "v1")] == 1.0
        assert by_name["multi_chunk"].n_questions == 1
        assert by_name["multi_chunk"].by_cell[("m", "v1")] == 0.5

    def test_empty_subset_returns_no_cell_entry(self) -> None:
        # No cross-doc questions in the records
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x", citation_recall=1.0),
        ]
        subsets = compute_subsets(recs, retrieval_misses=[])
        cross = next(s for s in subsets if s.name == "cross_document")
        assert cross.n_questions == 0
        assert ("m", "v1") not in cross.by_cell


# ============================================================================
# compute_refusal_categories
# ============================================================================


class TestComputeRefusalCategories:
    def test_three_categories_aggregated_separately(self) -> None:
        recs = [
            _ok_refusal("q1", "m", "v1", "refusal_out_of_corpus", refused=True),
            _ok_refusal("q2", "m", "v1", "refusal_out_of_corpus", refused=True),
            _ok_refusal("q3", "m", "v1", "refusal_adjacent", refused=False),
            _ok_refusal("q4", "m", "v1", "refusal_false_premise", refused=True),
        ]
        cats = compute_refusal_categories(recs)
        by_cat = {c.category: c for c in cats}

        assert by_cat["refusal_out_of_corpus"].by_cell[("m", "v1")] == (2, 2)
        assert by_cat["refusal_adjacent"].by_cell[("m", "v1")] == (0, 1)
        assert by_cat["refusal_false_premise"].by_cell[("m", "v1")] == (1, 1)

    def test_answerable_records_excluded(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x"),
            _ok_refusal("q2", "m", "v1", "refusal_out_of_corpus"),
        ]
        cats = compute_refusal_categories(recs)
        assert len(cats) == 1
        assert cats[0].category == "refusal_out_of_corpus"

    def test_categories_sorted_alphabetically(self) -> None:
        recs = [
            _ok_refusal("q1", "m", "v1", "refusal_zoo"),
            _ok_refusal("q2", "m", "v1", "refusal_apple"),
            _ok_refusal("q3", "m", "v1", "refusal_mango"),
        ]
        cats = compute_refusal_categories(recs)
        assert [c.category for c in cats] == ["refusal_apple", "refusal_mango", "refusal_zoo"]


# ============================================================================
# collect_error_cells / collect_questions_by_category
# ============================================================================


class TestCollectErrorCells:
    def test_returns_only_errored(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "x"),
            _err("q2", "m", "v1", "HTTP 500"),
            _err("q3", "m", "v1", "Connection refused"),
        ]
        errors = collect_error_cells(recs)
        assert len(errors) == 2
        assert errors[0]["error_message"] == "HTTP 500"


class TestCollectQuestionsByCategory:
    def test_groups_unique_qids_by_category(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x"),
            _ok_answerable("q1", "m", "v2", "single_chunk_x"),  # dup qid
            _ok_answerable("q2", "m", "v1", "single_chunk_x"),
            _ok_answerable("q3", "m", "v1", "multi_chunk_x"),
        ]
        result = collect_questions_by_category(recs)
        assert result["single_chunk_x"] == ["q1", "q2"]
        assert result["multi_chunk_x"] == ["q3"]


# ============================================================================
# build_report
# ============================================================================


class TestBuildReport:
    def test_full_pipeline(self) -> None:
        # Minimal viable sweep: 1 answerable + 1 refusal × 2 cells
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x", citation_recall=1.0),
            _ok_refusal("q2", "m", "v1", "refusal_out_of_corpus"),
            _ok_answerable("q1", "m", "v2", "single_chunk_x", citation_recall=0.5),
            _ok_refusal("q2", "m", "v2", "refusal_out_of_corpus"),
        ]
        meta = {
            "models": ["m"],
            "prompts": ["v1", "v2"],
            "question_count": 2,
            "total_cells": 4,
            "error_cells": 0,
            "elapsed_seconds": 10.0,
            "completed": True,
            "timestamp_utc": "2026-06-18T00-00-00Z",
        }
        report = build_report(recs, meta)
        assert len(report.cells) == 2  # (m, v1) and (m, v2)
        assert report.cells[0].citation_recall_mean in (1.0, 0.5)
        assert report.retrieval_misses == []
        assert len(report.refusal_categories) == 1
        assert report.error_cells == []


# ============================================================================
# Rendering smoke test
# ============================================================================


class TestRenderMarkdown:
    def test_produces_expected_section_headers(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x", citation_recall=1.0),
            _ok_refusal("q2", "m", "v1", "refusal_out_of_corpus"),
        ]
        meta = {
            "models": ["m"], "prompts": ["v1"],
            "question_count": 2, "total_cells": 2, "error_cells": 0,
            "elapsed_seconds": 5.0, "completed": True,
            "timestamp_utc": "2026-06-18T00-00-00Z",
        }
        report = build_report(recs, meta)
        attach_per_question_detail(report, recs)
        md = render_markdown(report)

        # The renderer should produce all the expected sections.
        for header in [
            "# Eval Report",
            "## Run metadata",
            "## Headline: per-cell summary",
            "## Subset analysis",
            "## Refusal correctness",
            "## Retrieval miss diagnostic",
            "## Hallucination breakdown",
            "## Latency",
            "## Per-question detail — answerable",
            "## Per-question detail — refusal",
            "## Errored cells",
        ]:
            assert header in md, f"Missing section: {header}"

    def test_reports_no_errors_section_when_clean(self) -> None:
        recs = [_ok_answerable("q1", "m", "v1", "single_chunk_x")]
        meta = {"models": ["m"], "prompts": ["v1"], "question_count": 1,
                "total_cells": 1, "error_cells": 0, "elapsed_seconds": 1.0,
                "completed": True, "timestamp_utc": "t"}
        report = build_report(recs, meta)
        attach_per_question_detail(report, recs)
        md = render_markdown(report)
        assert "No cells errored" in md

    def test_reports_errors_when_present(self) -> None:
        recs = [
            _ok_answerable("q1", "m", "v1", "single_chunk_x"),
            _err("q2", "m", "v1", "HTTP 500"),
        ]
        meta = {"models": ["m"], "prompts": ["v1"], "question_count": 2,
                "total_cells": 2, "error_cells": 1, "elapsed_seconds": 1.0,
                "completed": True, "timestamp_utc": "t"}
        report = build_report(recs, meta)
        attach_per_question_detail(report, recs)
        md = render_markdown(report)
        assert "1 cells errored" in md
        assert "HTTP 500" in md

    def test_retrieval_miss_section_uses_question_ids(self) -> None:
        recs = [
            _ok_answerable("q001", "m", "v1", "single_chunk_x", retrieval_recall=0.0),
            _ok_answerable("q001", "m", "v2", "single_chunk_x", retrieval_recall=0.0),
        ]
        meta = {"models": ["m"], "prompts": ["v1", "v2"], "question_count": 1,
                "total_cells": 2, "error_cells": 0, "elapsed_seconds": 1.0,
                "completed": True, "timestamp_utc": "t"}
        report = build_report(recs, meta)
        attach_per_question_detail(report, recs)
        md = render_markdown(report)
        assert "`q001`" in md


# ============================================================================
# Loading helpers
# ============================================================================


class TestLoadRecords:
    def test_loads_jsonl_in_order(self, tmp_path: Path) -> None:
        recs = [
            {"question_id": "q1", "x": 1},
            {"question_id": "q2", "x": 2},
        ]
        p = tmp_path / "raw.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in recs))
        loaded = load_records(p)
        assert [r["question_id"] for r in loaded] == ["q1", "q2"]

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "raw.jsonl"
        p.write_text('{"x": 1}\n\n{"x": 2}\n')
        assert len(load_records(p)) == 2


class TestLoadMeta:
    def test_loads_json(self, tmp_path: Path) -> None:
        p = tmp_path / "run_meta.json"
        p.write_text('{"models": ["a"], "completed": true}')
        meta = load_meta(p)
        assert meta["models"] == ["a"]
        assert meta["completed"] is True


class TestFindLatestRunDir:
    def test_picks_most_recently_modified(self, tmp_path: Path) -> None:
        a = tmp_path / "2026-06-18T01"
        b = tmp_path / "2026-06-18T02"
        a.mkdir()
        b.mkdir()
        # Touch b later
        import time
        time.sleep(0.01)
        b.touch()
        latest = find_latest_run_dir(tmp_path)
        assert latest == b

    def test_raises_if_no_subdirs(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            find_latest_run_dir(tmp_path)

    def test_raises_if_root_missing(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            find_latest_run_dir(tmp_path / "does_not_exist")
