"""Per-question scoring for the D014 eval harness.

Pure functions, no I/O. The runner calls these against the ``AnswerResult``
objects produced by ``answer.py`` to produce per-question score records
that get written to ``eval/results/<timestamp>/``.

Three measurement axes per D014:

1. **Refusal correctness** — binary per question, aggregated per-cell into
   precision/recall over the should-refuse set.
2. **Citation quality** — recall, precision, and F1 against gold chunk_ids.
   ``None`` for refusal questions (gold is empty by construction; the
   refusal_correct field carries the meaningful signal in those cases).
   Also tracked: ``extra_citations_count`` (valid citations not in gold),
   ``hallucinated_citations_count`` (already produced by ``answer.py``).
3. **Retrieval quality** — ``retrieval_recall`` measures the upper bound on
   ``citation_recall``: if the gold chunk wasn't retrieved, the answer
   model couldn't possibly have cited it. Cheap (no extra LLM calls) and
   localises failures between "retrieval missed" vs "answer model ignored".

Per-question records are emitted as plain dicts via
:func:`question_score_to_json` so the runner can write them straight to
disk without conditional serialization logic.
"""

from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path
from typing import Any

from underwriting_copilot.answer import AnswerResult


# ---- Benchmark loading -------------------------------------------------


@dataclasses.dataclass(frozen=True)
class BenchmarkQuestion:
    """Single question from ``eval/benchmark.toml``.

    The ``notes`` field is optional and informational only — it documents
    why a question exists (especially for adjacent-refusal and
    false-premise refusals where intent isn't obvious from the query).
    Not used in scoring.
    """

    id: str
    query: str
    expected_refusal: bool
    gold_chunk_ids: list[str]
    category: str
    notes: str = ""


def load_benchmark(path: Path) -> list[BenchmarkQuestion]:
    """Load benchmark.toml and return BenchmarkQuestion objects.

    Order is preserved from the TOML file (TOML arrays are ordered).
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return [
        BenchmarkQuestion(
            id=q["id"],
            query=q["query"],
            expected_refusal=q["expected_refusal"],
            gold_chunk_ids=list(q["gold_chunk_ids"]),
            category=q["category"],
            notes=q.get("notes", ""),
        )
        for q in data["question"]
    ]


def validate_benchmark_against_corpus(
    questions: list[BenchmarkQuestion],
    corpus_chunk_ids: set[str],
) -> list[str]:
    """Return list of error messages; empty list means valid.

    The runner calls this at startup to fail fast if ``benchmark.toml``
    references chunk_ids that no longer exist in the corpus (e.g. after
    re-chunking). Catching this at startup beats a confusing 0% citation
    accuracy result later.
    """
    errors: list[str] = []
    for q in questions:
        for cid in q.gold_chunk_ids:
            if cid not in corpus_chunk_ids:
                errors.append(f"{q.id}: gold_chunk_id {cid!r} not in corpus")
    return errors


# ---- Pure scoring functions --------------------------------------------


def score_citation_recall(
    cited: list[str], gold: list[str]
) -> float | None:
    """Return ``|cited ∩ gold| / |gold|``, or ``None`` if gold is empty.

    Refusal questions have empty gold lists by construction, so recall is
    undefined for them — the refusal_correct field carries the meaningful
    signal. Set-based to be robust to citation duplicates (the same chunk
    cited multiple times counts once).
    """
    if not gold:
        return None
    return len(set(cited) & set(gold)) / len(set(gold))


def score_citation_precision(
    cited: list[str], gold: list[str]
) -> float | None:
    """Return ``|cited ∩ gold| / |cited|``, or ``None`` if gold is empty.

    If gold is non-empty but cited is empty, precision is 0 (vacuously,
    nothing right was cited). This contrasts with recall, which would
    also be 0 in that case — both penalise a model that fails to cite
    anything.
    """
    if not gold:
        return None
    if not cited:
        return 0.0
    return len(set(cited) & set(gold)) / len(set(cited))


def score_citation_f1(
    recall: float | None, precision: float | None
) -> float | None:
    """Harmonic mean of precision and recall.

    Returns ``None`` if either input is ``None`` (i.e. refusal question
    with empty gold). Returns ``0.0`` when both are zero (avoids
    ZeroDivisionError on the harmonic-mean formula).
    """
    if recall is None or precision is None:
        return None
    if recall + precision == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def score_retrieval_recall(
    retrieved: list[str], gold: list[str]
) -> float | None:
    """Return ``|retrieved ∩ gold| / |gold|``, or ``None`` if gold is empty.

    Upper bound on citation_recall: the answer model can only cite chunks
    that the retrieval surfaced. A citation_recall noticeably below
    retrieval_recall means the answer model ignored chunks that were
    available; a citation_recall ≈ retrieval_recall means the answer
    model used what it was given.
    """
    if not gold:
        return None
    return len(set(retrieved) & set(gold)) / len(set(gold))


def score_refusal_correctness(expected: bool, actual: bool) -> bool:
    """True iff the model's refusal decision matched the gold label.

    No middle ground here — partial refusals (model both refuses and
    answers) are already classified as ``refused=False`` by
    ``answer.py``'s :func:`detect_refusal`.
    """
    return expected == actual


# ---- Per-question score record -----------------------------------------


@dataclasses.dataclass(frozen=True)
class QuestionScore:
    """One per ``(question × model × prompt_version)`` triple.

    Citation metrics (recall, precision, F1, retrieval_recall) are
    ``None`` for refusal questions where gold is empty. The runner's
    aggregation code must handle the None case.

    Raw outputs (``answer_text``, ``cited_chunks``, ``hallucinated_citations``,
    ``retrieved_chunk_ids``) are kept for debugging and for any future
    rescoring against a richer metric (e.g., LLM-judged claim alignment
    per Q10.3).
    """

    # Identifiers
    question_id: str
    model: str
    prompt_version: str
    category: str

    # Refusal axis
    expected_refusal: bool
    actual_refused: bool
    refusal_correct: bool

    # Citation axis (None when gold is empty)
    citation_recall: float | None
    citation_precision: float | None
    citation_f1: float | None

    # Citation diagnostics
    total_citations_count: int        # raw count including duplicates
    unique_citations_count: int       # after dedup
    extra_citations_count: int        # valid citations not in gold
    hallucinated_citations_count: int

    # Retrieval axis (None when gold is empty)
    retrieval_recall: float | None

    # Performance
    latency_seconds: float

    # Raw outputs (for debugging / future re-scoring)
    answer_text: str
    cited_chunks: list[str]
    hallucinated_citations: list[str]
    gold_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]


def score_question(
    question: BenchmarkQuestion,
    result: AnswerResult,
    prompt_version: str,
) -> QuestionScore:
    """Score one ``(question, result)`` pair.

    Citations are deduplicated before scoring (set arithmetic), so a
    model that cites the same chunk five times gets credit for one
    citation. Duplicate-citation counting is preserved in
    ``total_citations_count`` for context.
    """
    retrieved_ids = [h.chunk_id for h in result.used_chunks]
    unique_cited = list(dict.fromkeys(result.citations))

    recall = score_citation_recall(unique_cited, question.gold_chunk_ids)
    precision = score_citation_precision(unique_cited, question.gold_chunk_ids)
    f1 = score_citation_f1(recall, precision)
    retr_recall = score_retrieval_recall(retrieved_ids, question.gold_chunk_ids)
    extra = len(set(unique_cited) - set(question.gold_chunk_ids))

    return QuestionScore(
        question_id=question.id,
        model=result.model,
        prompt_version=prompt_version,
        category=question.category,
        expected_refusal=question.expected_refusal,
        actual_refused=result.refused,
        refusal_correct=score_refusal_correctness(
            question.expected_refusal, result.refused
        ),
        citation_recall=recall,
        citation_precision=precision,
        citation_f1=f1,
        total_citations_count=len(result.citations),
        unique_citations_count=len(unique_cited),
        extra_citations_count=extra,
        hallucinated_citations_count=len(result.hallucinated_citations),
        retrieval_recall=retr_recall,
        latency_seconds=result.elapsed_seconds,
        answer_text=result.answer,
        cited_chunks=unique_cited,
        hallucinated_citations=list(result.hallucinated_citations),
        gold_chunk_ids=list(question.gold_chunk_ids),
        retrieved_chunk_ids=retrieved_ids,
    )


def question_score_to_json(score: QuestionScore) -> dict[str, Any]:
    """JSON-serializable dict for ``runner.py``'s output files.

    ``dataclasses.asdict`` recursively converts. Python's ``None`` becomes
    JSON ``null`` when written via ``json.dump``, which is what we want
    for refusal questions' citation metrics.
    """
    return dataclasses.asdict(score)
