"""Unit tests for ``underwriting_copilot.query_rewriter``.

All HTTP is mocked via ``httpx.MockTransport``. No oMLX dependency,
no network calls. Each test exercises one concern:

- model resolution precedence (_resolve_model)
- constructor parameter wiring
- rewrite() success path: returns trimmed passage text
- rewrite() request shape: model, prompt, temperature, max_tokens
- rewrite() error paths: empty input, empty output, malformed
  response, HTTP error
"""
from __future__ import annotations

import httpx
import pytest

from underwriting_copilot.query_rewriter import (
    CONSTRAINED_PROMPT,
    DEFAULT_API_BASE,
    DEFAULT_API_KEY,
    DEFAULT_MODEL,
    MODEL_ENV_VAR,
    QueryRewriter,
    _resolve_model,
)


# ---- _resolve_model -----------------------------------------------------


def test_resolve_model_explicit_wins_over_env(monkeypatch):
    monkeypatch.setenv(MODEL_ENV_VAR, "env-model")
    assert _resolve_model("explicit-model") == "explicit-model"


def test_resolve_model_env_used_when_no_explicit(monkeypatch):
    monkeypatch.setenv(MODEL_ENV_VAR, "env-model")
    assert _resolve_model(None) == "env-model"


def test_resolve_model_default_when_no_explicit_no_env(monkeypatch):
    monkeypatch.delenv(MODEL_ENV_VAR, raising=False)
    assert _resolve_model(None) == DEFAULT_MODEL


def test_resolve_model_empty_string_explicit_falls_through(monkeypatch):
    # Empty-string explicit should not block env/default fallback.
    monkeypatch.setenv(MODEL_ENV_VAR, "env-model")
    assert _resolve_model("") == "env-model"


# ---- Helpers for mocking the LLM response --------------------------------


def _make_mock_transport(
    response_content: str = "mocked passage",
    *,
    status: int = 200,
    payload_override: dict | None = None,
    capture: list | None = None,
) -> httpx.MockTransport:
    """Build a MockTransport that returns ``response_content`` as the
    ``choices[0].message.content`` of a chat-completions response.

    If ``capture`` is provided, the request's parsed JSON body is
    appended to it for inspection by the test.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            import json
            capture.append(json.loads(request.content.decode("utf-8")))
        if payload_override is not None:
            return httpx.Response(status, json=payload_override)
        return httpx.Response(
            status,
            json={
                "choices": [
                    {"message": {"content": response_content}}
                ]
            },
        )

    return httpx.MockTransport(handler)


# ---- Constructor --------------------------------------------------------


def test_constructor_uses_defaults(monkeypatch):
    monkeypatch.delenv(MODEL_ENV_VAR, raising=False)
    r = QueryRewriter()
    assert r.model == DEFAULT_MODEL
    assert r.api_base == DEFAULT_API_BASE
    assert r.api_key == DEFAULT_API_KEY
    assert r.prompt_template == CONSTRAINED_PROMPT


def test_constructor_respects_explicit_model():
    r = QueryRewriter(model="my-model")
    assert r.model == "my-model"


def test_constructor_respects_custom_prompt():
    custom = "answer this: {query}"
    r = QueryRewriter(prompt_template=custom)
    assert r.prompt_template == custom


# ---- rewrite() success path ---------------------------------------------


def test_rewrite_returns_passage_text():
    transport = _make_mock_transport("a hypothetical passage")
    r = QueryRewriter(transport=transport)
    assert r.rewrite("what is X") == "a hypothetical passage"


def test_rewrite_strips_whitespace_from_response():
    transport = _make_mock_transport("  passage with surrounding whitespace  \n")
    r = QueryRewriter(transport=transport)
    assert r.rewrite("anything") == "passage with surrounding whitespace"


def test_rewrite_sends_correct_request_shape():
    captured: list[dict] = []
    transport = _make_mock_transport(capture=captured)
    r = QueryRewriter(
        model="test-model",
        max_tokens=42,
        transport=transport,
    )
    r.rewrite("what is the scope of PRA SS5/25?")

    assert len(captured) == 1
    body = captured[0]
    assert body["model"] == "test-model"
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 42
    assert len(body["messages"]) == 1
    msg = body["messages"][0]
    assert msg["role"] == "user"
    # The prompt template was applied and the query is embedded in it.
    assert "what is the scope of PRA SS5/25?" in msg["content"]
    # The CONSTRAINED prompt opens with a specific imagine-the-document
    # framing; the request must carry it.
    assert "regulatory supervisory statement" in msg["content"]


def test_rewrite_uses_custom_prompt_template():
    captured: list[dict] = []
    transport = _make_mock_transport(capture=captured)
    r = QueryRewriter(
        prompt_template="Q: {query}\nA:",
        transport=transport,
    )
    r.rewrite("test question")

    body = captured[0]
    assert body["messages"][0]["content"] == "Q: test question\nA:"


# ---- rewrite() error paths ----------------------------------------------


def test_rewrite_rejects_empty_query():
    r = QueryRewriter(transport=_make_mock_transport())
    with pytest.raises(ValueError, match="non-empty"):
        r.rewrite("")


def test_rewrite_rejects_whitespace_only_query():
    r = QueryRewriter(transport=_make_mock_transport())
    with pytest.raises(ValueError, match="non-empty"):
        r.rewrite("   \n\t  ")


def test_rewrite_raises_on_empty_response_content():
    transport = _make_mock_transport("")
    r = QueryRewriter(transport=transport)
    with pytest.raises(ValueError, match="empty"):
        r.rewrite("anything")


def test_rewrite_raises_on_whitespace_only_response_content():
    transport = _make_mock_transport("   \n  ")
    r = QueryRewriter(transport=transport)
    with pytest.raises(ValueError, match="empty"):
        r.rewrite("anything")


def test_rewrite_raises_on_malformed_response_missing_choices():
    transport = _make_mock_transport(payload_override={"error": "nope"})
    r = QueryRewriter(transport=transport)
    with pytest.raises(ValueError, match="Malformed"):
        r.rewrite("anything")


def test_rewrite_raises_on_malformed_response_empty_choices():
    transport = _make_mock_transport(payload_override={"choices": []})
    r = QueryRewriter(transport=transport)
    with pytest.raises(ValueError, match="Malformed"):
        r.rewrite("anything")


def test_rewrite_raises_on_http_error_status():
    transport = _make_mock_transport(
        payload_override={"error": "server fell over"},
        status=500,
    )
    r = QueryRewriter(transport=transport)
    with pytest.raises(httpx.HTTPStatusError):
        r.rewrite("anything")
