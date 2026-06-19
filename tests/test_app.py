"""tests/test_app.py — Streamlit AppTest harness for app.py.

Uses streamlit.testing.v1.AppTest to drive the script through a
headless simulator. The tests substitute a fake AnswerGenerator and
Retriever via monkeypatching so the LLM endpoint and Qdrant index
are not exercised.

The pivotal test is ``test_sample_click_then_ask_invokes_generator`` —
it would have caught the v1.0 bug where ``st.text_area`` without a
``key`` reset to empty on the rerun triggered by clicking Ask,
silently swallowing the sample-populated query and skipping the LLM
call. Fixed by giving the widget ``key="query_input"`` and
transferring ``pending_query`` into that keyed state before the
widget renders.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


# ---- Fakes -------------------------------------------------------------


@dataclasses.dataclass
class _FakeHit:
    """Mimics ``RetrievalHit`` for rendering tests."""

    payload: dict[str, Any]

    @property
    def chunk_id(self) -> str:
        return self.payload["chunk_id"]


def _make_fake_hit(chunk_id: str, text: str = "Sample chunk text.") -> _FakeHit:
    return _FakeHit(
        payload={
            "chunk_id": chunk_id,
            "issuer": "PRA",
            "title": "Test Document",
            "section_path": ["Chapter 1", "Section A"],
            "text": text,
        }
    )


class _FakeAnswerResult:
    """Mimics ``AnswerResult`` for rendering tests."""

    def __init__(
        self,
        query: str,
        answer: str = "Test answer [chunk_001].",
        citations: list[str] | None = None,
        hallucinated_citations: list[str] | None = None,
        used_chunks: list[_FakeHit] | None = None,
        refused: bool = False,
        elapsed_seconds: float = 1.23,
        model: str = "gemma-4-31B-it-MLX-6bit",
    ):
        self.query = query
        self.answer = answer
        self.citations = citations or []
        self.hallucinated_citations = hallucinated_citations or []
        self.used_chunks = used_chunks or []
        self.refused = refused
        self.elapsed_seconds = elapsed_seconds
        self.model = model


class _FakeGenerator:
    """Stand-in for ``AnswerGenerator`` that records calls and returns
    a canned ``AnswerResult`` instead of hitting oMLX."""

    last_call: dict[str, Any] | None = None
    canned_result: _FakeAnswerResult | None = None

    def __init__(self, *args, **kwargs):
        # Swallow retriever, model, etc. — we don't use them.
        pass

    def answer(self, query: str, top_k: int = 5, **kwargs):
        _FakeGenerator.last_call = {
            "query": query,
            "top_k": top_k,
            **kwargs,
        }
        if _FakeGenerator.canned_result is None:
            return _FakeAnswerResult(query=query)
        return _FakeGenerator.canned_result


class _FakeRetriever:
    """Stand-in for ``Retriever`` — never opened, never queried."""

    def __init__(self, *args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def _patch_pipeline(monkeypatch):
    """Replace AnswerGenerator + Retriever with fakes for every test."""
    import underwriting_copilot.answer as answer_mod
    import underwriting_copilot.retrieve as retrieve_mod

    monkeypatch.setattr(answer_mod, "AnswerGenerator", _FakeGenerator)
    monkeypatch.setattr(retrieve_mod, "Retriever", _FakeRetriever)

    # Reset the recording slot so tests don't see leftovers.
    _FakeGenerator.last_call = None
    _FakeGenerator.canned_result = None
    yield


# ---- Lifecycle tests ---------------------------------------------------


def test_app_loads_to_empty_state():
    """Fresh app launch renders header, sample grid, no result."""
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=10)

    assert not at.exception, f"Unhandled exception: {at.exception}"
    # Sample-state hero is present in the rendered markdown
    rendered = "\n".join(m.value for m in at.markdown)
    assert "Try a sample question" in rendered
    # Question widget exists with empty value
    assert at.session_state["query_input"] == ""


def test_sample_click_populates_query_input():
    """Clicking a sample button transfers its text into query_input
    BEFORE the text area renders (the load-bearing invariant)."""
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=10)

    # Find the first sample button — the empty-state grid creates
    # buttons with keys sample_0 .. sample_3.
    sample_button = next(b for b in at.button if b.key == "sample_0")
    sample_button.click()
    at.run(timeout=10)

    # After click → rerun → pending_query transferred → query_input
    # holds the sample's text.
    assert at.session_state["query_input"].startswith("What does the PRA")
    assert "pending_query" not in at.session_state


def test_ask_with_empty_query_shows_error_not_silent_skip():
    """Clicking Ask without any query text shows a visible error
    rather than silently doing nothing."""
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=10)

    ask = next(b for b in at.button if b.label.startswith("Ask"))
    ask.click()
    at.run(timeout=10)

    # The generator must NOT have been called.
    assert _FakeGenerator.last_call is None
    # The page must show an "empty query" error.
    rendered = "\n".join(m.value for m in at.markdown)
    assert "Empty query" in rendered


def test_sample_click_then_ask_invokes_generator():
    """**THE REGRESSION TEST.**

    Sample button click populates the text area, then Ask click
    must trigger the generator with that exact query. The v1.0 bug
    was that the text_area without a key reset to empty on the
    rerun triggered by Ask, leaving query_input empty and the
    generator never called (silent skip — no spinner, no fan,
    no error, just an empty page).

    The fix (text_area key="query_input" + pending_query transfer
    before widget render) is exercised by this test. If the bug
    regresses, this test fails because last_call stays None.
    """
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=10)

    # Click sample 0 (PRA climate)
    next(b for b in at.button if b.key == "sample_0").click()
    at.run(timeout=10)

    sample_text = at.session_state["query_input"]
    assert sample_text  # not empty post-transfer

    # Click Ask — this used to fail silently due to the reset bug
    next(b for b in at.button if b.label.startswith("Ask")).click()
    at.run(timeout=15)

    # The generator MUST have been invoked, and with the sample's
    # text — proves query_input survived the rerun.
    assert _FakeGenerator.last_call is not None, (
        "Generator was not called — query_input did not persist "
        "across the Ask rerun. The text_area key fix is missing."
    )
    assert _FakeGenerator.last_call["query"] == sample_text


def test_top_k_value_threads_through_to_generator():
    """Top-K slider value reaches the generator call unchanged."""
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=10)

    at.session_state["query_input"] = "test query"
    at.session_state["top_k"] = 8

    next(b for b in at.button if b.label.startswith("Ask")).click()
    at.run(timeout=15)

    assert _FakeGenerator.last_call is not None
    assert _FakeGenerator.last_call["top_k"] == 8


def test_filter_text_inputs_become_none_when_blank():
    """Empty filter strings must reach the generator as None, not ''."""
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=10)

    at.session_state["query_input"] = "test query"
    at.session_state["issuer_filter"] = ""
    at.session_state["jurisdiction_filter"] = ""

    next(b for b in at.button if b.label.startswith("Ask")).click()
    at.run(timeout=15)

    assert _FakeGenerator.last_call is not None
    assert _FakeGenerator.last_call["issuer_type"] is None
    assert _FakeGenerator.last_call["jurisdiction"] is None


def test_refusal_result_renders_refusal_card_not_answer_card():
    """When the generator returns a refused result, the page must show
    the refusal card and NOT call render_answer_with_badges."""
    _FakeGenerator.canned_result = _FakeAnswerResult(
        query="Bermuda hurricane bond ratios?",
        answer="I cannot answer this from the provided sources.",
        refused=True,
        used_chunks=[],
    )

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=10)

    at.session_state["query_input"] = "Bermuda hurricane bond ratios?"
    next(b for b in at.button if b.label.startswith("Ask")).click()
    at.run(timeout=15)

    rendered = "\n".join(m.value for m in at.markdown)
    assert "Refusal" in rendered
    assert "could not answer" in rendered


def test_hallucinated_citation_triggers_warning_banner():
    """If the result carries hallucinated_citations, the warning
    banner must render."""
    _FakeGenerator.canned_result = _FakeAnswerResult(
        query="Test query",
        answer="Test answer [valid_chunk] [made_up_chunk].",
        citations=["valid_chunk"],
        hallucinated_citations=["made_up_chunk"],
        used_chunks=[_make_fake_hit("valid_chunk")],
        refused=False,
    )

    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=10)

    at.session_state["query_input"] = "Test query"
    next(b for b in at.button if b.label.startswith("Ask")).click()
    at.run(timeout=15)

    rendered = "\n".join(m.value for m in at.markdown)
    assert "Hallucinated citation" in rendered
    assert "made_up_chunk" in rendered


# ---- Pure-helper tests (no AppTest needed) -----------------------------


def test_build_ordinal_map_orders_by_first_appearance():
    from app import build_ordinal_map

    answer = "First [b] then [a] then [b] then [c]."
    assert build_ordinal_map(answer) == {"b": 1, "a": 2, "c": 3}


def test_build_ordinal_map_empty_for_no_citations():
    from app import build_ordinal_map

    assert build_ordinal_map("No citations here at all.") == {}


def test_render_answer_with_badges_escapes_html_in_answer():
    from app import render_answer_with_badges

    result = _FakeAnswerResult(
        query="Q",
        answer="Beware <script>alert(1)</script> and [chunk_a].",
        citations=["chunk_a"],
        used_chunks=[_make_fake_hit("chunk_a")],
    )
    html_out = render_answer_with_badges(result)
    # Tag escaped
    assert "&lt;script&gt;" in html_out
    assert "<script>" not in html_out
    # Citation badge rendered
    assert 'href="#src-chunk_a"' in html_out
    assert ">[1]</a>" in html_out


def test_render_answer_with_badges_marks_hallucinations():
    from app import render_answer_with_badges

    result = _FakeAnswerResult(
        query="Q",
        answer="Real [a] fake [b].",
        citations=["a"],
        hallucinated_citations=["b"],
        used_chunks=[_make_fake_hit("a")],
    )
    html_out = render_answer_with_badges(result)
    assert "cite-halluc" in html_out
    assert "[?]" in html_out


# ---- "New question" button -------------------------------------------


def test_new_question_button_clears_result_and_returns_to_empty_state():
    """Clicking 'New question' must clear current_result + query_input
    and return the user to the sample-grid empty state. Without this,
    the result page is a dead-end."""
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=10)

    # Drive an Ask cycle so current_result is populated.
    at.session_state["query_input"] = "test query"
    next(b for b in at.button if b.label.startswith("Ask")).click()
    at.run(timeout=15)
    assert "current_result" in at.session_state, "precondition: result must be present"

    # Click "New question".
    new_q = next(b for b in at.button if "New question" in b.label)
    new_q.click()
    at.run(timeout=10)

    # State cleared.
    assert "current_result" not in at.session_state
    assert at.session_state["query_input"] == ""

    # Sample grid visible again.
    rendered = "\n".join(m.value for m in at.markdown)
    assert "Try a sample question" in rendered
