"""Unit tests for ``eval/scorer.py``.

The pure scoring functions are exhaustively covered (every edge case in
the gold-empty / cited-empty / overlap cells of the truth table).
``score_question`` is covered with a fake AnswerResult that has the same
shape as the real one. ``load_benchmark`` is covered with both a synthetic
inline benchmark and a smoke test against the committed ``eval/benchmark.toml``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from eval.scorer import (
    BenchmarkQuestion,
    QuestionScore,
    load_benchmark,
    question_score_to_json,
    score_citation_f1,
    score_citation_precision,
    score_citation_recall,
    score_question,
    score_refusal_correctness,
    score_retrieval_recall,
    validate_benchmark_against_corpus,
)


# ============================================================================
# score_citation_recall
# ============================================================================


class TestScoreCitationRecall:
    def test_perfect_recall(self) -> None:
        assert score_citation_recall(["a", "b"], ["a", "b"]) == 1.0

    def test_partial_recall(self) -> None:
        assert score_citation_recall(["a"], ["a", "b"]) == 0.5

    def test_zero_recall_when_no_overlap(self) -> None:
        assert score_citation_recall(["c", "d"], ["a", "b"]) == 0.0

    def test_empty_gold_returns_none(self) -> None:
        # Refusal questions have empty gold by construction.
        assert score_citation_recall(["a", "b"], []) is None

    def test_empty_cited_with_nonempty_gold(self) -> None:
        assert score_citation_recall([], ["a", "b"]) == 0.0

    def test_extra_citations_do_not_penalise_recall(self) -> None:
        # Recall answers "did we find what we expected?" — extras are
        # precision's concern.
        assert score_citation_recall(["a", "b", "x", "y"], ["a", "b"]) == 1.0

    def test_duplicates_in_cited_are_deduplicated(self) -> None:
        # Set-based; duplicate citations don't count twice.
        assert score_citation_recall(["a", "a", "b"], ["a", "b", "c"]) == pytest.approx(2 / 3)


# ============================================================================
# score_citation_precision
# ============================================================================


class TestScoreCitationPrecision:
    def test_perfect_precision(self) -> None:
        assert score_citation_precision(["a", "b"], ["a", "b"]) == 1.0

    def test_lower_precision_with_extras(self) -> None:
        # 2 of 3 cited chunks are in gold.
        assert score_citation_precision(["a", "b", "x"], ["a", "b"]) == pytest.approx(2 / 3)

    def test_zero_precision_when_no_overlap(self) -> None:
        assert score_citation_precision(["x", "y"], ["a", "b"]) == 0.0

    def test_empty_gold_returns_none(self) -> None:
        assert score_citation_precision(["a"], []) is None

    def test_empty_cited_is_zero_not_undefined(self) -> None:
        # Vacuously, "nothing right was cited" — symmetric with recall's
        # behaviour for the same input.
        assert score_citation_precision([], ["a"]) == 0.0


# ============================================================================
# score_citation_f1
# ============================================================================


class TestScoreCitationF1:
    def test_perfect_f1(self) -> None:
        assert score_citation_f1(1.0, 1.0) == 1.0

    def test_harmonic_mean(self) -> None:
        # F1(recall=0.5, precision=1.0) = 2*0.5*1.0/(0.5+1.0) = 2/3
        assert score_citation_f1(0.5, 1.0) == pytest.approx(2 / 3)

    def test_zero_when_either_is_zero(self) -> None:
        # The harmonic-mean formula would divide by zero; we return 0.0.
        assert score_citation_f1(0.0, 0.5) == 0.0
        assert score_citation_f1(0.5, 0.0) == 0.0
        assert score_citation_f1(0.0, 0.0) == 0.0

    def test_none_when_either_is_none(self) -> None:
        # Refusal questions propagate None through to F1.
        assert score_citation_f1(None, 0.5) is None
        assert score_citation_f1(0.5, None) is None
        assert score_citation_f1(None, None) is None


# ============================================================================
# score_retrieval_recall
# ============================================================================


class TestScoreRetrievalRecall:
    def test_perfect_retrieval(self) -> None:
        assert score_retrieval_recall(["a", "b", "c"], ["a", "b"]) == 1.0

    def test_partial_retrieval(self) -> None:
        assert score_retrieval_recall(["a", "c"], ["a", "b"]) == 0.5

    def test_zero_retrieval(self) -> None:
        assert score_retrieval_recall(["x", "y"], ["a"]) == 0.0

    def test_empty_gold_returns_none(self) -> None:
        assert score_retrieval_recall(["a"], []) is None


# ============================================================================
# score_refusal_correctness
# ============================================================================


class TestScoreRefusalCorrectness:
    def test_correctly_refused(self) -> None:
        assert score_refusal_correctness(True, True) is True

    def test_correctly_answered(self) -> None:
        assert score_refusal_correctness(False, False) is True

    def test_should_refuse_but_answered(self) -> None:
        # The dangerous case: model confabulates on out-of-corpus question.
        assert score_refusal_correctness(True, False) is False

    def test_should_answer_but_refused(self) -> None:
        # Less dangerous but still wrong: model refuses on answerable.
        assert score_refusal_correctness(False, True) is False


# ============================================================================
# validate_benchmark_against_corpus
# ============================================================================


class TestValidateBenchmarkAgainstCorpus:
    def test_all_present_returns_empty(self) -> None:
        questions = [
            BenchmarkQuestion(
                id="q1", query="?", expected_refusal=False,
                gold_chunk_ids=["a", "b"], category="x",
            ),
        ]
        assert validate_benchmark_against_corpus(questions, {"a", "b", "c"}) == []

    def test_missing_chunk_reported_with_question_id(self) -> None:
        questions = [
            BenchmarkQuestion(
                id="q42", query="?", expected_refusal=False,
                gold_chunk_ids=["missing_chunk"], category="x",
            ),
        ]
        errors = validate_benchmark_against_corpus(questions, {"a"})
        assert len(errors) == 1
        assert "q42" in errors[0]
        assert "missing_chunk" in errors[0]

    def test_refusal_with_empty_gold_passes_against_empty_corpus(self) -> None:
        # Edge case: empty corpus shouldn't error on refusal questions.
        questions = [
            BenchmarkQuestion(
                id="q1", query="?", expected_refusal=True,
                gold_chunk_ids=[], category="x",
            ),
        ]
        assert validate_benchmark_against_corpus(questions, set()) == []

    def test_reports_all_missing_not_just_first(self) -> None:
        questions = [
            BenchmarkQuestion(
                id="q1", query="?", expected_refusal=False,
                gold_chunk_ids=["missing_a", "missing_b"], category="x",
            ),
            BenchmarkQuestion(
                id="q2", query="?", expected_refusal=False,
                gold_chunk_ids=["missing_c"], category="x",
            ),
        ]
        errors = validate_benchmark_against_corpus(questions, set())
        assert len(errors) == 3


# ============================================================================
# load_benchmark
# ============================================================================


class TestLoadBenchmark:
    def test_loads_minimal_benchmark(self, tmp_path: Path) -> None:
        path = tmp_path / "b.toml"
        path.write_text(
            """
[[question]]
id = "q1"
query = "What is X?"
expected_refusal = false
gold_chunk_ids = ["chunk_a"]
category = "test_single"
"""
        )
        qs = load_benchmark(path)
        assert len(qs) == 1
        assert qs[0].id == "q1"
        assert qs[0].query == "What is X?"
        assert qs[0].expected_refusal is False
        assert qs[0].gold_chunk_ids == ["chunk_a"]
        assert qs[0].category == "test_single"
        assert qs[0].notes == ""

    def test_loads_notes_when_present(self, tmp_path: Path) -> None:
        path = tmp_path / "b.toml"
        path.write_text(
            """
[[question]]
id = "q1"
query = "What?"
expected_refusal = true
gold_chunk_ids = []
category = "refusal_test"
notes = "Tests a subtle case."
"""
        )
        qs = load_benchmark(path)
        assert qs[0].notes == "Tests a subtle case."

    def test_preserves_question_order(self, tmp_path: Path) -> None:
        path = tmp_path / "b.toml"
        path.write_text(
            """
[[question]]
id = "qB"
query = "B?"
expected_refusal = false
gold_chunk_ids = ["b"]
category = "x"

[[question]]
id = "qA"
query = "A?"
expected_refusal = false
gold_chunk_ids = ["a"]
category = "x"
"""
        )
        qs = load_benchmark(path)
        # TOML preserves array order; loader must too.
        assert [q.id for q in qs] == ["qB", "qA"]

    def test_committed_benchmark_smoke(self) -> None:
        """Sanity check the actual committed eval/benchmark.toml.

        Loads the real file and verifies the design contract from D014:
        40 questions, 26 answerable, 14 should-refuse.
        """
        benchmark_path = Path(__file__).parent.parent / "eval" / "benchmark.toml"
        questions = load_benchmark(benchmark_path)
        assert len(questions) == 70
        answerable = [q for q in questions if not q.expected_refusal]
        refusals = [q for q in questions if q.expected_refusal]
        assert len(answerable) == 44
        assert len(refusals) == 26
        # All refusals have empty gold; all answerables have non-empty gold.
        assert all(q.gold_chunk_ids == [] for q in refusals)
        assert all(q.gold_chunk_ids for q in answerable)
        # IDs are unique.
        ids = [q.id for q in questions]
        assert len(set(ids)) == len(ids)


# ============================================================================
# score_question (integration with AnswerResult shape)
# ============================================================================


def _fake_hit(chunk_id: str):
    """Minimal stand-in for RetrievalHit — only ``chunk_id`` is read."""
    return SimpleNamespace(chunk_id=chunk_id)


def _fake_answer_result(
    *,
    citations: list[str],
    hallucinated: list[str] = None,
    used_chunk_ids: list[str] = None,
    refused: bool = False,
    answer_text: str = "answer text",
    model: str = "test-model",
    elapsed: float = 1.23,
):
    """Build a fake AnswerResult — duck-typed, matches answer.py's shape."""
    return SimpleNamespace(
        query="(unused)",
        answer=answer_text,
        citations=citations,
        hallucinated_citations=hallucinated or [],
        used_chunks=[_fake_hit(c) for c in (used_chunk_ids or [])],
        refused=refused,
        elapsed_seconds=elapsed,
        model=model,
    )


class TestScoreQuestion:
    def test_answerable_perfect_match(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a", "b"], category="cat",
        )
        result = _fake_answer_result(
            citations=["a", "b"],
            used_chunk_ids=["a", "b", "c"],  # extra retrieved, none cited
        )
        score = score_question(q, result, prompt_version="v1")
        assert score.refusal_correct is True
        assert score.citation_recall == 1.0
        assert score.citation_precision == 1.0
        assert score.citation_f1 == 1.0
        assert score.extra_citations_count == 0
        assert score.hallucinated_citations_count == 0
        assert score.retrieval_recall == 1.0
        assert score.unique_citations_count == 2
        assert score.total_citations_count == 2

    def test_answerable_partial_recall(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a", "b"], category="cat",
        )
        result = _fake_answer_result(
            citations=["a"],
            used_chunk_ids=["a", "b"],
        )
        score = score_question(q, result, prompt_version="v1")
        assert score.citation_recall == 0.5
        assert score.citation_precision == 1.0
        # Retrieval found both even though answer only cited one — useful
        # localisation signal.
        assert score.retrieval_recall == 1.0

    def test_extra_citations_lower_precision(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        result = _fake_answer_result(
            citations=["a", "x", "y"],
            used_chunk_ids=["a", "x", "y"],
        )
        score = score_question(q, result, prompt_version="v1")
        assert score.citation_recall == 1.0
        assert score.citation_precision == pytest.approx(1 / 3)
        assert score.extra_citations_count == 2  # x and y

    def test_duplicate_citations_counted_once_for_scoring(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a", "b"], category="cat",
        )
        # Model cites 'a' three times — common with Gemma's behaviour
        # observed on Day 2.
        result = _fake_answer_result(
            citations=["a", "a", "a"],
            used_chunk_ids=["a", "b"],
        )
        score = score_question(q, result, prompt_version="v1")
        assert score.citation_recall == 0.5  # 'a' found, 'b' missed
        assert score.citation_precision == 1.0  # 'a' is in gold
        assert score.total_citations_count == 3
        assert score.unique_citations_count == 1

    def test_correctly_refused(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=True,
            gold_chunk_ids=[], category="refusal",
        )
        result = _fake_answer_result(
            citations=[],
            used_chunk_ids=["a", "b"],
            refused=True,
        )
        score = score_question(q, result, prompt_version="v1")
        assert score.refusal_correct is True
        # All citation metrics None for refusal questions.
        assert score.citation_recall is None
        assert score.citation_precision is None
        assert score.citation_f1 is None
        assert score.retrieval_recall is None

    def test_should_refuse_but_answered(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=True,
            gold_chunk_ids=[], category="refusal",
        )
        result = _fake_answer_result(
            citations=["a"],
            used_chunk_ids=["a"],
            refused=False,
        )
        score = score_question(q, result, prompt_version="v1")
        # The dangerous case: model confabulated when it should have refused.
        assert score.refusal_correct is False

    def test_hallucinated_citations_counted_separately(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        # 'a' was cited (valid); 'fake_x' was cited but not retrieved
        # (hallucinated; already partitioned out by answer.py).
        result = _fake_answer_result(
            citations=["a"],
            hallucinated=["fake_x", "fake_y"],
            used_chunk_ids=["a", "b"],
        )
        score = score_question(q, result, prompt_version="v1")
        assert score.hallucinated_citations_count == 2
        # Hallucinations don't affect citation_precision (which is over
        # *valid* citations only). They show up in their own field — a
        # deliberate design choice so confabulation is visible separately
        # from "cited the wrong real chunk".
        assert score.citation_precision == 1.0

    def test_retrieval_recall_below_citation_recall_is_impossible(self) -> None:
        # Sanity invariant: model can only cite what it received. So
        # citation_recall <= retrieval_recall always (when both are defined).
        # This isn't a test of the scorer per se but documents the
        # invariant — if it ever fails, something is wrong upstream.
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a", "b", "c"], category="cat",
        )
        result = _fake_answer_result(
            citations=["a"],
            used_chunk_ids=["a", "b"],  # 'c' not retrieved
        )
        score = score_question(q, result, prompt_version="v1")
        assert score.citation_recall is not None
        assert score.retrieval_recall is not None
        assert score.citation_recall <= score.retrieval_recall

    def test_prompt_version_recorded(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        result = _fake_answer_result(citations=["a"], used_chunk_ids=["a"])
        score = score_question(q, result, prompt_version="v2")
        assert score.prompt_version == "v2"

    def test_model_carried_through_from_result(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        result = _fake_answer_result(
            citations=["a"], used_chunk_ids=["a"],
            model="gemma-4-31B-it-MLX-6bit",
        )
        score = score_question(q, result, prompt_version="v1")
        assert score.model == "gemma-4-31B-it-MLX-6bit"


# ============================================================================
# question_score_to_json
# ============================================================================


class TestQuestionScoreToJson:
    def test_round_trip_serializable(self) -> None:
        import json

        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        result = _fake_answer_result(citations=["a"], used_chunk_ids=["a"])
        score = score_question(q, result, prompt_version="v1")
        d = question_score_to_json(score)
        # Must round-trip through JSON without crashing — runner.py depends
        # on this for the per-cell JSON output files.
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2["question_id"] == "q1"
        assert d2["citation_recall"] == 1.0

    def test_none_metrics_become_json_null(self) -> None:
        import json

        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=True,
            gold_chunk_ids=[], category="refusal",
        )
        result = _fake_answer_result(citations=[], used_chunk_ids=[], refused=True)
        score = score_question(q, result, prompt_version="v1")
        d = question_score_to_json(score)
        # Refusal questions have None for citation/retrieval metrics; these
        # must serialize as JSON null (Python's json module does this), not
        # crash.
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2["citation_recall"] is None
        assert d2["citation_precision"] is None
        assert d2["citation_f1"] is None
        assert d2["retrieval_recall"] is None
