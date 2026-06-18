"""Unit tests for ``eval/runner.py``.

Focus on the testable parts: retry wrapper behavior, cell record
constructors, CLI argument parsing, question filtering, and the
``run_sweep`` loop with a fake AnswerGenerator (no oMLX dependency).

The ``main()`` function and ``_all_corpus_chunk_ids`` are not unit-
tested — they're thin integration glue around external state (Qdrant
index, filesystem, oMLX server). They get exercised by the actual
sweep run.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from eval.runner import (
    DEFAULT_MODELS,
    DEFAULT_PROMPTS,
    SweepProgress,
    _build_argparser,
    _filter_questions,
    _format_success_summary,
    _parse_csv_list,
    _validate_prompts,
    make_error_record,
    make_success_record,
    run_sweep,
    try_answer_with_retry,
)
from eval.scorer import BenchmarkQuestion, score_question


# ============================================================================
# Test helpers
# ============================================================================


def _fake_hit(chunk_id: str):
    return SimpleNamespace(chunk_id=chunk_id)


def _fake_answer_result(
    *,
    citations=None,
    used_chunk_ids=None,
    refused=False,
    model="test-model",
    elapsed=1.0,
):
    return SimpleNamespace(
        query="(unused)",
        answer="answer text",
        citations=citations or [],
        hallucinated_citations=[],
        used_chunks=[_fake_hit(c) for c in (used_chunk_ids or [])],
        refused=refused,
        elapsed_seconds=elapsed,
        model=model,
    )


def _http_status_error(status_code: int = 500) -> httpx.HTTPStatusError:
    """Construct a real-looking HTTPStatusError for the retry tests."""
    req = httpx.Request("POST", "http://test/v1/chat/completions")
    resp = httpx.Response(status_code, request=req)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=req, response=resp
    )


class _FakeRetriever:
    def __init__(self, hits) -> None:
        self._hits = hits

    def retrieve(self, query, top_k=5, **kwargs):
        return self._hits[:top_k]


class _CountingFakeGenerator:
    """Stand-in for AnswerGenerator that counts ``answer()`` calls and
    can be programmed to fail."""

    def __init__(
        self,
        *,
        retriever=None,
        model="test-model",
        system_prompt=None,
        canned_result=None,
        fail_times: int = 0,
        fail_with: Exception | None = None,
    ) -> None:
        self.retriever = retriever
        self.model = model
        self.system_prompt = system_prompt
        self.canned_result = canned_result
        self.fail_times = fail_times
        self.fail_with = fail_with or _http_status_error(500)
        self.call_count = 0

    def answer(self, query, top_k=5):
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise self.fail_with
        if self.canned_result is None:
            return _fake_answer_result(model=self.model, citations=["a"])
        return self.canned_result


# ============================================================================
# try_answer_with_retry
# ============================================================================


class TestTryAnswerWithRetry:
    def test_success_first_try(self) -> None:
        gen = _CountingFakeGenerator(fail_times=0)
        result, error = try_answer_with_retry(
            gen, "?", sleep_fn=lambda _: None
        )
        assert result is not None
        assert error is None
        assert gen.call_count == 1

    def test_retry_succeeds_on_second_attempt(self) -> None:
        gen = _CountingFakeGenerator(fail_times=1)  # fails once, succeeds
        result, error = try_answer_with_retry(
            gen, "?", sleep_fn=lambda _: None
        )
        assert result is not None
        assert error is None
        assert gen.call_count == 2

    def test_persistent_failure_records_error(self) -> None:
        gen = _CountingFakeGenerator(fail_times=99)  # always fails
        result, error = try_answer_with_retry(
            gen, "?", max_retries=1, sleep_fn=lambda _: None
        )
        assert result is None
        assert error is not None
        assert "HTTP 500" in error
        # max_retries=1 means 2 attempts total
        assert gen.call_count == 2

    def test_network_error_retried(self) -> None:
        gen = _CountingFakeGenerator(
            fail_times=1,
            fail_with=httpx.ConnectError("connection refused"),
        )
        result, error = try_answer_with_retry(
            gen, "?", sleep_fn=lambda _: None
        )
        assert result is not None
        assert gen.call_count == 2

    def test_unknown_exception_not_retried(self) -> None:
        # Programming errors (KeyError, etc) should surface fast — they
        # aren't transient.
        gen = _CountingFakeGenerator(
            fail_times=99,
            fail_with=KeyError("unexpected"),
        )
        result, error = try_answer_with_retry(
            gen, "?", sleep_fn=lambda _: None
        )
        assert result is None
        assert error is not None
        assert "Unexpected error" in error
        assert "KeyError" in error
        # No retry — single attempt
        assert gen.call_count == 1

    def test_max_retries_zero_means_one_attempt(self) -> None:
        gen = _CountingFakeGenerator(fail_times=99)
        result, error = try_answer_with_retry(
            gen, "?", max_retries=0, sleep_fn=lambda _: None
        )
        assert result is None
        assert gen.call_count == 1

    def test_sleep_between_retries(self) -> None:
        # Verifies the delay actually fires between attempts.
        slept: list[float] = []
        gen = _CountingFakeGenerator(fail_times=1)
        try_answer_with_retry(
            gen, "?", retry_delay=2.5, sleep_fn=slept.append
        )
        assert slept == [2.5]


# ============================================================================
# make_success_record / make_error_record
# ============================================================================


class TestMakeRecords:
    def test_success_record_marks_cell_ok(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        result = _fake_answer_result(citations=["a"], used_chunk_ids=["a"])
        score = score_question(q, result, prompt_version="v1")
        record = make_success_record(score)
        assert record["cell_status"] == "ok"
        assert record["error_message"] is None
        # And carries through all the scorer fields
        assert record["question_id"] == "q1"
        assert record["citation_recall"] == 1.0

    def test_error_record_keeps_identifiers(self) -> None:
        q = BenchmarkQuestion(
            id="q5", query="?", expected_refusal=True,
            gold_chunk_ids=[], category="refusal_test",
        )
        record = make_error_record(
            q, model="m1", prompt_version="v2",
            error_message="HTTP 500 on attempt 2/2",
        )
        assert record["cell_status"] == "error"
        assert record["error_message"] == "HTTP 500 on attempt 2/2"
        assert record["question_id"] == "q5"
        assert record["category"] == "refusal_test"
        assert record["model"] == "m1"
        assert record["prompt_version"] == "v2"
        # Reports must check cell_status before reading metrics; the
        # error record should not include metric fields that could be
        # mistakenly treated as 0.0.
        assert "citation_recall" not in record
        assert "citation_precision" not in record

    def test_records_are_json_serializable(self) -> None:
        import json

        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        result = _fake_answer_result(citations=["a"], used_chunk_ids=["a"])
        score = score_question(q, result, prompt_version="v1")
        ok_record = make_success_record(score)
        err_record = make_error_record(q, "m", "v1", "err")
        # Both must round-trip through JSON since runner.py writes JSONL.
        json.dumps(ok_record)
        json.dumps(err_record)


# ============================================================================
# CLI argument parsing
# ============================================================================


class TestParseCSVList:
    def test_simple_comma_split(self) -> None:
        assert _parse_csv_list("a,b,c") == ["a", "b", "c"]

    def test_strips_whitespace(self) -> None:
        assert _parse_csv_list(" a , b ,c") == ["a", "b", "c"]

    def test_skips_empties(self) -> None:
        assert _parse_csv_list("a,,b,") == ["a", "b"]

    def test_single_item(self) -> None:
        assert _parse_csv_list("solo") == ["solo"]


class TestBuildArgparser:
    def test_defaults_match_d014_sweep(self) -> None:
        # The CLI without args runs the canonical D014 sweep. If these
        # defaults drift, the next session's sweep won't reproduce what's
        # documented.
        args = _build_argparser().parse_args([])
        assert args.models == DEFAULT_MODELS
        assert args.prompts == DEFAULT_PROMPTS
        assert args.top_k == 5
        assert args.limit is None
        assert args.question_ids is None

    def test_models_override(self) -> None:
        args = _build_argparser().parse_args(["--models", "m1,m2,m3"])
        assert args.models == ["m1", "m2", "m3"]

    def test_prompts_override(self) -> None:
        args = _build_argparser().parse_args(["--prompts", "v1"])
        assert args.prompts == ["v1"]

    def test_question_ids_override(self) -> None:
        args = _build_argparser().parse_args(
            ["--question-ids", "q001,q002,q005"]
        )
        assert args.question_ids == ["q001", "q002", "q005"]

    def test_limit_override(self) -> None:
        args = _build_argparser().parse_args(["--limit", "5"])
        assert args.limit == 5

    def test_output_dir_is_path(self) -> None:
        args = _build_argparser().parse_args(["--output-dir", "/tmp/eval"])
        assert isinstance(args.output_dir, Path)


class TestValidatePrompts:
    def test_known_prompts_pass(self) -> None:
        # Doesn't raise.
        _validate_prompts(["v1", "v2"])

    def test_unknown_prompts_raise(self) -> None:
        with pytest.raises(SystemExit) as exc:
            _validate_prompts(["v1", "v99"])
        assert "v99" in str(exc.value)


# ============================================================================
# _filter_questions
# ============================================================================


def _qs(*ids):
    return [
        BenchmarkQuestion(
            id=i, query=f"q for {i}", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        for i in ids
    ]


class TestFilterQuestions:
    def test_no_filter_returns_all(self) -> None:
        qs = _qs("q1", "q2", "q3")
        assert _filter_questions(qs, None, None) == qs

    def test_question_ids_filter(self) -> None:
        qs = _qs("q1", "q2", "q3")
        result = _filter_questions(qs, ["q1", "q3"], None)
        assert [q.id for q in result] == ["q1", "q3"]

    def test_question_ids_preserve_benchmark_order(self) -> None:
        # Even though --question-ids was given as q3,q1, the filter
        # should preserve the order from the benchmark, not the CLI.
        # That keeps results predictable across runs with different
        # --question-ids orderings.
        qs = _qs("q1", "q2", "q3")
        result = _filter_questions(qs, ["q3", "q1"], None)
        assert [q.id for q in result] == ["q1", "q3"]

    def test_unknown_question_id_raises(self) -> None:
        qs = _qs("q1", "q2")
        with pytest.raises(SystemExit) as exc:
            _filter_questions(qs, ["q1", "q999"], None)
        assert "q999" in str(exc.value)

    def test_limit_caps_count(self) -> None:
        qs = _qs("q1", "q2", "q3", "q4", "q5")
        result = _filter_questions(qs, None, 3)
        assert [q.id for q in result] == ["q1", "q2", "q3"]

    def test_limit_applied_after_question_ids(self) -> None:
        qs = _qs("q1", "q2", "q3", "q4")
        result = _filter_questions(qs, ["q2", "q3", "q4"], 2)
        assert [q.id for q in result] == ["q2", "q3"]


# ============================================================================
# _format_success_summary
# ============================================================================


class TestFormatSuccessSummary:
    def test_answerable_summary_includes_recall(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        result = _fake_answer_result(
            citations=["a"], used_chunk_ids=["a"], elapsed=12.34,
        )
        score = score_question(q, result, prompt_version="v1")
        summary = _format_success_summary(score)
        assert "12.3s" in summary
        assert "recall=1.00" in summary

    def test_refusal_summary_omits_recall(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=True,
            gold_chunk_ids=[], category="refusal",
        )
        result = _fake_answer_result(refused=True, elapsed=0.5)
        score = score_question(q, result, prompt_version="v1")
        summary = _format_success_summary(score)
        # Refusal questions have None for recall — summary shouldn't try
        # to print that.
        assert "recall" not in summary
        assert "refused=True" in summary
        assert "correct=True" in summary

    def test_summary_flags_hallucinations(self) -> None:
        q = BenchmarkQuestion(
            id="q1", query="?", expected_refusal=False,
            gold_chunk_ids=["a"], category="cat",
        )
        result = _fake_answer_result(citations=["a"], used_chunk_ids=["a"])
        result.hallucinated_citations = ["fake_x", "fake_y"]
        score = score_question(q, result, prompt_version="v1")
        summary = _format_success_summary(score)
        assert "halluc=2" in summary


# ============================================================================
# run_sweep
# ============================================================================


class TestRunSweep:
    def test_iterates_full_sweep_grid(self) -> None:
        questions = _qs("q1", "q2")
        models = ["m1", "m2"]
        prompts = ["v1", "v2"]

        def factory(retriever, model, system_prompt):
            return _CountingFakeGenerator(
                retriever=retriever, model=model, system_prompt=system_prompt,
                canned_result=_fake_answer_result(
                    citations=["a"], used_chunk_ids=["a"], model=model,
                ),
            )

        records = list(
            run_sweep(
                retriever=_FakeRetriever([_fake_hit("a")]),
                questions=questions,
                models=models,
                prompt_names=prompts,
                prompt_registry={"v1": "p1", "v2": "p2"},
                generator_factory=factory,
            )
        )
        # 2 models × 2 prompts × 2 questions = 8 cells
        assert len(records) == 8
        # Every cell is "ok"
        assert all(rec["cell_status"] == "ok" for rec, _ in records)
        # The grid covers every combination exactly once
        triples = {
            (r["model"], r["prompt_version"], r["question_id"])
            for r, _ in records
        }
        assert len(triples) == 8

    def test_progress_indices_run_sequentially(self) -> None:
        questions = _qs("q1", "q2", "q3")

        def factory(retriever, model, system_prompt):
            return _CountingFakeGenerator(
                retriever=retriever, model=model, system_prompt=system_prompt,
                canned_result=_fake_answer_result(
                    citations=["a"], used_chunk_ids=["a"],
                ),
            )

        records = list(
            run_sweep(
                retriever=_FakeRetriever([_fake_hit("a")]),
                questions=questions, models=["m"], prompt_names=["v1"],
                prompt_registry={"v1": "p1"},
                generator_factory=factory,
            )
        )
        progresses = [p for _, p in records]
        assert [p.cell_index for p in progresses] == [1, 2, 3]
        assert all(p.total_cells == 3 for p in progresses)

    def test_failed_cell_recorded_and_sweep_continues(self) -> None:
        # First question fails persistently; second succeeds. Verify the
        # sweep doesn't short-circuit.
        questions = _qs("q1", "q2")
        call_state = {"q_index": 0}

        def factory(retriever, model, system_prompt):
            gen = MagicMock()

            def fake_answer(query, top_k=5):
                # Fail on q1 (first call across the two questions),
                # succeed on q2. fail_times=99 isn't right here because
                # the same generator handles both questions.
                if "q for q1" in query:
                    raise _http_status_error(500)
                return _fake_answer_result(
                    citations=["a"], used_chunk_ids=["a"],
                )

            gen.answer.side_effect = fake_answer
            return gen

        # Patch time.sleep so retries don't actually wait
        import eval.runner as runner_mod

        original = runner_mod.try_answer_with_retry

        def patched_retry(gen, query, **kwargs):
            return original(gen, query, sleep_fn=lambda _: None, **kwargs)

        runner_mod.try_answer_with_retry = patched_retry
        try:
            records = list(
                run_sweep(
                    retriever=_FakeRetriever([_fake_hit("a")]),
                    questions=questions, models=["m"], prompt_names=["v1"],
                    prompt_registry={"v1": "p1"},
                    generator_factory=factory,
                )
            )
        finally:
            runner_mod.try_answer_with_retry = original

        assert len(records) == 2
        record_by_qid = {r["question_id"]: r for r, _ in records}
        assert record_by_qid["q1"]["cell_status"] == "error"
        assert "HTTP 500" in record_by_qid["q1"]["error_message"]
        assert record_by_qid["q2"]["cell_status"] == "ok"

    def test_generator_created_once_per_model_prompt_combo(self) -> None:
        # Each (model, prompt) combo creates one AnswerGenerator that's
        # reused across all questions in that cell. Saves repeated
        # construction; reflects how production would do it.
        questions = _qs("q1", "q2", "q3")
        factory_calls: list[tuple[str, str]] = []

        def factory(retriever, model, system_prompt):
            factory_calls.append((model, system_prompt))
            return _CountingFakeGenerator(
                retriever=retriever, model=model, system_prompt=system_prompt,
                canned_result=_fake_answer_result(
                    citations=["a"], used_chunk_ids=["a"],
                ),
            )

        list(
            run_sweep(
                retriever=_FakeRetriever([_fake_hit("a")]),
                questions=questions,
                models=["m1", "m2"], prompt_names=["v1", "v2"],
                prompt_registry={"v1": "p1", "v2": "p2"},
                generator_factory=factory,
            )
        )
        # 2 models × 2 prompts = 4 generator constructions, regardless
        # of question count.
        assert len(factory_calls) == 4
        assert set(factory_calls) == {
            ("m1", "p1"), ("m1", "p2"), ("m2", "p1"), ("m2", "p2"),
        }

    def test_progress_carries_correct_status(self) -> None:
        questions = _qs("q1")

        def factory(retriever, model, system_prompt):
            return _CountingFakeGenerator(
                retriever=retriever, model=model, system_prompt=system_prompt,
                canned_result=_fake_answer_result(
                    citations=["a"], used_chunk_ids=["a"],
                ),
            )

        records = list(
            run_sweep(
                retriever=_FakeRetriever([_fake_hit("a")]),
                questions=questions, models=["m"], prompt_names=["v1"],
                prompt_registry={"v1": "p1"},
                generator_factory=factory,
            )
        )
        _, progress = records[0]
        assert isinstance(progress, SweepProgress)
        assert progress.question_id == "q1"
        assert progress.model == "m"
        assert progress.prompt_version == "v1"
        assert progress.cell_status == "ok"
