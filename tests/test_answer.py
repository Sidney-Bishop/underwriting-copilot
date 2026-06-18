"""Unit tests for ``src/underwriting_copilot/answer.py``.

The pure helpers (parsing, validation, refusal detection, prompt
building) are exercised in isolation. The ``AnswerGenerator`` integration
is tested with a subclass that overrides ``_call_llm`` to return canned
responses — the actual HTTP path is exercised by the demo run against
the live mlx-lm.server.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from underwriting_copilot.answer import (
    CITATION_REGEX,
    REFUSAL_PHRASE,
    AnswerGenerator,
    AnswerResult,
    _build_user_prompt,
    detect_refusal,
    parse_citations,
    validate_citations,
)


# ============================================================================
# Test helpers
# ============================================================================


def _hit(chunk_id: str, text: str = "sample chunk text", **extras):
    """Minimal stand-in for RetrievalHit — only ``chunk_id`` and
    ``payload`` are read by answer.py."""
    payload = {
        "chunk_id": chunk_id,
        "document_id": "doc_test",
        "title": "Test Doc",
        "issuer": "Test Issuer",
        "issuer_type": "regulator",
        "section_path": ["root", "intro"],
        "text": text,
        **extras,
    }
    return SimpleNamespace(
        chunk_id=chunk_id,
        payload=payload,
        score=0.5,
        dense_rank=1,
        sparse_rank=1,
    )


class _FakeRetriever:
    """Stand-in for Retriever — returns a canned hit list per query."""

    def __init__(self, hits) -> None:
        self._hits = hits

    def retrieve(self, query, top_k=5, **kwargs):
        return self._hits[:top_k]


class _FakeAnswerGenerator(AnswerGenerator):
    """AnswerGenerator with ``_call_llm`` overridden to return a fixed
    response — keeps the unit tests off the network."""

    def __init__(self, retriever, canned_response: str) -> None:
        super().__init__(retriever=retriever)
        self._canned_response = canned_response

    def _call_llm(self, user_prompt: str) -> str:
        # Capture the prompt for assertion in tests that care.
        self.last_user_prompt = user_prompt
        return self._canned_response


# ============================================================================
# parse_citations
# ============================================================================


class TestParseCitations:
    def test_extracts_single_citation(self) -> None:
        text = "The PRA requires X [chunk_id_1]."
        assert parse_citations(text) == ["chunk_id_1"]

    def test_extracts_multiple_citations(self) -> None:
        text = "A [c1] and B [c2]."
        assert parse_citations(text) == ["c1", "c2"]

    def test_preserves_order_of_appearance(self) -> None:
        text = "[c3] then [c1] then [c2]."
        assert parse_citations(text) == ["c3", "c1", "c2"]

    def test_preserves_duplicates(self) -> None:
        # Same chunk cited twice — both occurrences captured so callers
        # can spot the pattern if they want.
        text = "First mention [c1], later mention [c1]."
        assert parse_citations(text) == ["c1", "c1"]

    def test_handles_realistic_chunk_id(self) -> None:
        text = "Source: [eiopa_guidelines_system_of_governance__0001__introduction]."
        assert parse_citations(text) == [
            "eiopa_guidelines_system_of_governance__0001__introduction"
        ]

    def test_no_citations_returns_empty_list(self) -> None:
        assert parse_citations("Plain text with no citations.") == []

    def test_ignores_brackets_with_internal_whitespace(self) -> None:
        # The regex character class has no whitespace, so natural-language
        # bracketed phrases don't accidentally match.
        text = "See paragraph [4.124 of the SS] for details."
        assert parse_citations(text) == []

    def test_back_to_back_citations(self) -> None:
        text = "Multiple sources [c1][c2][c3]."
        assert parse_citations(text) == ["c1", "c2", "c3"]


# ============================================================================
# validate_citations
# ============================================================================


class TestValidateCitations:
    def test_all_valid_when_all_in_context(self) -> None:
        valid, hallucinated = validate_citations(
            ["c1", "c2"], {"c1", "c2", "c3"}
        )
        assert valid == ["c1", "c2"]
        assert hallucinated == []

    def test_all_hallucinated_when_none_in_context(self) -> None:
        valid, hallucinated = validate_citations(
            ["fake1", "fake2"], {"c1", "c2"}
        )
        assert valid == []
        assert hallucinated == ["fake1", "fake2"]

    def test_mixed_partitioning(self) -> None:
        valid, hallucinated = validate_citations(
            ["c1", "fake", "c2"], {"c1", "c2"}
        )
        assert valid == ["c1", "c2"]
        assert hallucinated == ["fake"]

    def test_preserves_order_within_partitions(self) -> None:
        valid, hallucinated = validate_citations(
            ["c2", "fake_a", "c1", "fake_b"], {"c1", "c2"}
        )
        assert valid == ["c2", "c1"]
        assert hallucinated == ["fake_a", "fake_b"]

    def test_empty_citations(self) -> None:
        assert validate_citations([], {"c1"}) == ([], [])


# ============================================================================
# detect_refusal
# ============================================================================


class TestDetectRefusal:
    def test_exact_phrase_without_punctuation(self) -> None:
        assert detect_refusal(REFUSAL_PHRASE) is True

    def test_with_trailing_period(self) -> None:
        assert detect_refusal(f"{REFUSAL_PHRASE}.") is True

    def test_with_trailing_exclamation(self) -> None:
        assert detect_refusal(f"{REFUSAL_PHRASE}!") is True

    def test_with_extra_whitespace(self) -> None:
        assert detect_refusal(f"  {REFUSAL_PHRASE}.  ") is True

    def test_with_trailing_newline(self) -> None:
        assert detect_refusal(f"{REFUSAL_PHRASE}.\n") is True

    def test_partial_refusal_returns_false(self) -> None:
        # If the LLM both refuses AND tries to answer, that's not a
        # clean refusal — the eval harness should see it as a defective
        # answer attempt, not a refusal.
        text = f"{REFUSAL_PHRASE}, but the SOURCES suggest..."
        assert detect_refusal(text) is False

    def test_substantive_answer_returns_false(self) -> None:
        assert detect_refusal("The PRA requires firms to do X [c1].") is False

    def test_empty_string_returns_false(self) -> None:
        assert detect_refusal("") is False

    def test_case_sensitive(self) -> None:
        # Per D013 the contract is exact match (case-sensitive). If a
        # model drifts the casing, that's a prompt-following failure
        # worth surfacing in eval — not silently treated as a refusal.
        assert detect_refusal("i cannot answer this from the provided sources") is False


# ============================================================================
# _build_user_prompt
# ============================================================================


class TestBuildUserPrompt:
    def test_includes_query_verbatim(self) -> None:
        hits = [_hit("c1")]
        prompt = _build_user_prompt("What does PRA expect?", hits)
        assert "QUESTION: What does PRA expect?" in prompt

    def test_includes_each_chunk_id_in_bracket_form(self) -> None:
        hits = [_hit("c1"), _hit("c2")]
        prompt = _build_user_prompt("Q", hits)
        # The LLM must see chunk_ids in the same format it should cite.
        assert "[c1]" in prompt
        assert "[c2]" in prompt

    def test_includes_chunk_text(self) -> None:
        hits = [_hit("c1", text="The PRA requires X.")]
        prompt = _build_user_prompt("Q", hits)
        assert "The PRA requires X." in prompt

    def test_includes_issuer_and_title(self) -> None:
        hits = [_hit("c1")]
        prompt = _build_user_prompt("Q", hits)
        assert "Test Issuer" in prompt
        assert "Test Doc" in prompt

    def test_includes_section_path(self) -> None:
        hits = [_hit("c1")]  # default section_path = ["root", "intro"]
        prompt = _build_user_prompt("Q", hits)
        assert "root > intro" in prompt


# ============================================================================
# AnswerGenerator (mocked LLM, mocked retriever)
# ============================================================================


class TestAnswerGenerator:
    def test_pre_llm_refusal_when_no_hits(self) -> None:
        # No hits returned → LLM is never called, refusal returned directly.
        gen = _FakeAnswerGenerator(
            retriever=_FakeRetriever(hits=[]),
            canned_response="(this should never be returned)",
        )
        result = gen.answer("Q")
        assert result.refused is True
        assert result.citations == []
        assert result.hallucinated_citations == []
        assert result.used_chunks == []
        assert REFUSAL_PHRASE in result.answer

    def test_records_valid_citations(self) -> None:
        gen = _FakeAnswerGenerator(
            retriever=_FakeRetriever(hits=[_hit("c1"), _hit("c2")]),
            canned_response="The answer is X [c1] and Y [c2].",
        )
        result = gen.answer("Q")
        assert result.refused is False
        assert result.citations == ["c1", "c2"]
        assert result.hallucinated_citations == []
        assert len(result.used_chunks) == 2

    def test_records_hallucinated_citations(self) -> None:
        # The LLM cites a chunk that wasn't in the context. Caught by the
        # validator — this is the load-bearing eval signal.
        gen = _FakeAnswerGenerator(
            retriever=_FakeRetriever(hits=[_hit("c1")]),
            canned_response="X is true [c1] and also Y [c99].",
        )
        result = gen.answer("Q")
        assert result.citations == ["c1"]
        assert result.hallucinated_citations == ["c99"]

    def test_refusal_detected(self) -> None:
        gen = _FakeAnswerGenerator(
            retriever=_FakeRetriever(hits=[_hit("c1")]),
            canned_response=f"{REFUSAL_PHRASE}.",
        )
        result = gen.answer("Q")
        assert result.refused is True
        assert result.citations == []
        assert result.hallucinated_citations == []

    def test_model_name_recorded_in_result(self) -> None:
        gen = _FakeAnswerGenerator(
            retriever=_FakeRetriever(hits=[_hit("c1")]),
            canned_response="An answer [c1].",
        )
        result = gen.answer("Q")
        # Default model per D013.
        assert result.model == "Qwen3.6-35B-A3B-4bit"

    def test_used_chunks_passed_through(self) -> None:
        hits = [_hit("c1"), _hit("c2"), _hit("c3")]
        gen = _FakeAnswerGenerator(
            retriever=_FakeRetriever(hits=hits),
            canned_response="An answer [c1].",
        )
        result = gen.answer("Q", top_k=3)
        assert [h.chunk_id for h in result.used_chunks] == ["c1", "c2", "c3"]

    def test_top_k_limits_retrieved_chunks(self) -> None:
        hits = [_hit(f"c{i}") for i in range(10)]
        gen = _FakeAnswerGenerator(
            retriever=_FakeRetriever(hits=hits),
            canned_response="An answer [c0].",
        )
        result = gen.answer("Q", top_k=3)
        assert len(result.used_chunks) == 3

    def test_user_prompt_contains_retrieved_chunks(self) -> None:
        # Verify the prompt sent to the LLM actually includes the chunks
        # — not silently dropping context.
        gen = _FakeAnswerGenerator(
            retriever=_FakeRetriever(hits=[_hit("c1", text="UNIQUE_MARKER_TEXT")]),
            canned_response="X [c1].",
        )
        gen.answer("Q")
        assert "UNIQUE_MARKER_TEXT" in gen.last_user_prompt
        assert "[c1]" in gen.last_user_prompt
