"""LLM cited-answer generation on top of ``retrieve.py``.

Per **D013**:
  - Citation format: ``[chunk_id]`` inline with claims.
  - Refusal phrase: exact ``"I cannot answer this from the provided sources."``
  - Citation validation: hallucinated citations recorded as a quality
    signal for the Day 3 eval harness.
  - Model + endpoint injected at construction; no hardcoded model.

Talks to the OpenAI-compatible chat-completions surface that oMLX exposes
locally (per ``serving_local_models.md``). oMLX runs on Apple Silicon and
also speaks an Anthropic-compatible API on the same host:port — using the
OpenAI surface here because it accepts per-request sampling parameters
end-to-end, which the Anthropic surface does not for this server.

Single-shot: one prompt in, one answer out. No streaming, multi-turn, or
tool use.
"""

from __future__ import annotations

import dataclasses
import re
import time
from pathlib import Path
from typing import Any

import httpx

from underwriting_copilot.retrieve import Retriever, RetrievalHit

# ---- Module constants ---------------------------------------------------

#: Default model name to pass in the chat-completions request. Override via
#: ``AnswerGenerator(model=...)``. Per Q9, Day 3 eval will sweep across
#: multiple models, so this default is a starting point, not a verdict.
DEFAULT_MODEL = "Qwen3.6-35B-A3B-4bit"

#: oMLX's default bind address (``http://127.0.0.1:8000``) plus the ``/v1``
#: prefix that the OpenAI-compatible API uses. The ``/chat/completions``
#: suffix is appended inside ``_call_llm``. Override via ``api_base=...``.
DEFAULT_API_BASE = "http://127.0.0.1:8000/v1"

#: oMLX's literal auth token per ``~/.omlx/settings.json``. Not a secret;
#: it exists to satisfy the SDK contract, not to provide security against
#: an attacker who already has local network access.
DEFAULT_API_KEY = "claude"

DEFAULT_TOP_K = 5
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_TOKENS = 1024

#: The single fixed refusal phrase per D013. The detector and the
#: system prompt both reference this constant — they are one contract.
REFUSAL_PHRASE = "I cannot answer this from the provided sources"

#: Regex for ``[chunk_id]`` citations. Permissive on character class
#: (any alphanumeric + underscore + hyphen sequence) and strict on
#: structure (no whitespace inside the brackets, so natural-language
#: bracketed phrases like "[Article 12]" won't match). The validator
#: partitions matches into valid + hallucinated.
CITATION_REGEX = re.compile(r"\[([A-Za-z0-9_\-]+)\]")


# ---- System prompt -----------------------------------------------------

#: The system prompt that instructs the LLM about citation rules and the
#: refusal contract. Tied to ``REFUSAL_PHRASE`` and ``CITATION_REGEX``
#: above — changes here require coordinated changes there.
SYSTEM_PROMPT = """You are an underwriting copilot for a reinsurance company. \
You answer questions about regulatory and corporate documents using ONLY the \
sources provided in the user message. You never use information from your \
training data.

Citation rules:
- Every factual claim in your answer MUST be followed by a citation in the \
exact format [chunk_id], using the chunk_id from the SOURCES section.
- Use only chunk_ids that appear in the SOURCES section. Never invent a \
chunk_id.
- A single sentence may carry multiple citations: [chunk_id_1][chunk_id_2].

Refusal rule:
- If the SOURCES do not contain enough information to answer the QUESTION, \
respond with EXACTLY this phrase and nothing else:

I cannot answer this from the provided sources.

Keep answers concise. Quote source text only when exact wording matters."""


# ---- Result type --------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class AnswerResult:
    """Result of a single answer-generation call.

    Fields:
        query: The user's natural-language question.
        answer: Raw text the LLM produced (or the refusal phrase when no
            chunks could be retrieved).
        citations: chunk_ids cited in the answer that point to chunks
            actually in the retrieved context.
        hallucinated_citations: chunk_ids cited in the answer that do
            *not* correspond to any retrieved chunk. The main eval-time
            signal of LLM confabulation.
        used_chunks: All RetrievalHit objects fed to the LLM as context.
        refused: True if the LLM produced the exact refusal phrase, or
            if no chunks were retrieved at all (pre-LLM refusal).
        elapsed_seconds: Wall-clock time for retrieve + LLM call.
        model: Model identifier passed to the chat-completions endpoint.
    """

    query: str
    answer: str
    citations: list[str]
    hallucinated_citations: list[str]
    used_chunks: list[RetrievalHit]
    refused: bool
    elapsed_seconds: float
    model: str


# ---- Pure helpers -------------------------------------------------------


def parse_citations(answer_text: str) -> list[str]:
    """Extract all ``[chunk_id]`` citations from the LLM's answer.

    Returns chunk_ids in order of appearance, preserving duplicates so
    downstream callers can spot a single chunk being cited multiple
    times if they care.
    """
    return CITATION_REGEX.findall(answer_text)


def validate_citations(
    citations: list[str], known_chunk_ids: set[str]
) -> tuple[list[str], list[str]]:
    """Partition citations into ``(valid, hallucinated)``.

    ``valid`` contains citations that reference chunks actually fed to
    the LLM; ``hallucinated`` contains everything else. Order within
    each list matches the order of appearance in the input.
    """
    valid: list[str] = []
    hallucinated: list[str] = []
    for cite in citations:
        if cite in known_chunk_ids:
            valid.append(cite)
        else:
            hallucinated.append(cite)
    return valid, hallucinated


def detect_refusal(answer_text: str) -> bool:
    """Return True iff the LLM answer is a clean refusal.

    A clean refusal is the exact phrase from ``REFUSAL_PHRASE`` —
    case-sensitive — with optional trailing whitespace and terminal
    ``.!?`` stripped before comparison. Partial refusals (where the
    LLM also gave an answer) return False.
    """
    stripped = answer_text.strip().rstrip(".!?").strip()
    expected = REFUSAL_PHRASE.rstrip(".!?").strip()
    return stripped == expected


def _build_user_prompt(query: str, hits: list[RetrievalHit]) -> str:
    """Build the user-role message containing SOURCES + QUESTION.

    Each source block names the chunk_id (in the format the LLM is
    instructed to cite), the issuer + title + section as orientation,
    then the chunk text itself.
    """
    parts: list[str] = ["SOURCES:", ""]
    for hit in hits:
        p = hit.payload
        section = " > ".join(p.get("section_path", [])) or "(no section)"
        parts.append(f"[{p['chunk_id']}]")
        parts.append(f"{p['issuer']} — {p['title']} — {section}")
        parts.append(p["text"])
        parts.append("")
    parts.append(f"QUESTION: {query}")
    parts.append("")
    parts.append(
        "Answer with citations per the rules above. If the sources do "
        "not contain enough information to answer, respond with the "
        "refusal phrase exactly."
    )
    return "\n".join(parts)


# ---- Generator class ---------------------------------------------------


class AnswerGenerator:
    """Single-shot cited-answer generation via oMLX's OpenAI-compatible
    chat-completions surface.

    Construct with a :class:`Retriever` and optional model / endpoint
    overrides; call ``.answer(query)`` for each question. oMLX must be
    running locally with the requested model loaded — see
    ``serving_local_models.md`` for setup details.
    """

    def __init__(
        self,
        retriever: Retriever,
        model: str = DEFAULT_MODEL,
        api_base: str = DEFAULT_API_BASE,
        api_key: str = DEFAULT_API_KEY,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self.retriever = retriever
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt

    def _call_llm(self, user_prompt: str) -> str:
        """Single OpenAI-compatible chat completion call against oMLX.

        Designed to be overridden in tests with a canned-response stub
        (see ``_FakeAnswerGenerator`` in the test suite).
        """
        url = f"{self.api_base}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]

    def answer(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        exclude_superseded: bool = True,
        issuer_type: str | None = None,
        jurisdiction: str | None = None,
    ) -> AnswerResult:
        """Run the full retrieve → prompt → LLM → validate pipeline.

        Two refusal paths:
          - **Pre-LLM:** if no chunks were retrieved (rare given the
            default filters, but possible with restrictive filter
            combos), the LLM is not called and a refusal is returned
            directly.
          - **LLM-driven:** the LLM emits the refusal phrase, detected
            by :func:`detect_refusal`.
        """
        t0 = time.perf_counter()

        hits = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            exclude_superseded=exclude_superseded,
            issuer_type=issuer_type,
            jurisdiction=jurisdiction,
        )

        if not hits:
            elapsed = time.perf_counter() - t0
            return AnswerResult(
                query=query,
                answer=f"{REFUSAL_PHRASE}.",
                citations=[],
                hallucinated_citations=[],
                used_chunks=[],
                refused=True,
                elapsed_seconds=elapsed,
                model=self.model,
            )

        user_prompt = _build_user_prompt(query, hits)
        answer_text = self._call_llm(user_prompt)
        elapsed = time.perf_counter() - t0

        all_citations = parse_citations(answer_text)
        known_ids = {h.chunk_id for h in hits}
        valid, hallucinated = validate_citations(all_citations, known_ids)
        refused = detect_refusal(answer_text)

        return AnswerResult(
            query=query,
            answer=answer_text,
            citations=valid,
            hallucinated_citations=hallucinated,
            used_chunks=hits,
            refused=refused,
            elapsed_seconds=elapsed,
            model=self.model,
        )


# ---- Demo --------------------------------------------------------------


def _format_result(result: AnswerResult) -> str:
    """Compact rendering of a single answer for the demo output."""
    lines = [
        f"QUESTION: {result.query}",
        "",
        f"ANSWER  ({result.model}, {result.elapsed_seconds:.1f}s):",
        result.answer,
        "",
    ]
    if result.refused:
        lines.append("STATUS: refused (sources do not answer the question)")
    else:
        lines.append(f"CITATIONS ({len(result.citations)} valid):")
        for c in result.citations:
            lines.append(f"  - [{c}]")
        if result.hallucinated_citations:
            lines.append(
                f"HALLUCINATED CITATIONS "
                f"({len(result.hallucinated_citations)}):"
            )
            for c in result.hallucinated_citations:
                lines.append(f"  - [{c}]  ← NOT in retrieved context")
    return "\n".join(lines)


def _demo() -> None:
    """Demo Q→A pipeline against the persisted index.

    Runs three queries with mixed expected outcomes: two answerable from
    the corpus, one that the corpus shouldn't be able to answer (so the
    refusal path is exercised).

    Requires oMLX to be running with the configured model loaded — see
    ``serving_local_models.md``. Run: ``uv run python -m underwriting_copilot.answer``.
    """
    repo_root = Path(__file__).resolve().parents[2]
    retriever = Retriever(
        qdrant_path=repo_root / "scratch" / "qdrant",
        vocab_path=repo_root / "corpus" / "bm25_vocab.json",
        verbose=True,
    )
    generator = AnswerGenerator(retriever=retriever)
    print(f"\nUsing model:  {generator.model}")
    print(f"API endpoint: {generator.api_base}\n")

    demo_queries = [
        # Should answer (PRA climate guidance is in the corpus)
        "What does the PRA expect insurers to do for climate scenario analysis?",
        # Should answer (EIOPA fit and proper guidelines are in the corpus)
        "What are the EIOPA governance requirements for fit and proper persons?",
        # Should refuse (Bermuda hurricane bond capital ratios are not in the corpus)
        "What is the maximum solvency capital ratio required for a hurricane bond issuer in Bermuda?",
    ]

    for query in demo_queries:
        print("=" * 80)
        result = generator.answer(query, top_k=5)
        print(_format_result(result))
        print()


if __name__ == "__main__":
    _demo()
