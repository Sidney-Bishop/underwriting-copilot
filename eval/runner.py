"""Sweep ``AnswerGenerator`` across ``{models} × {prompts} × benchmark`` per D014.

Defaults map to the D014 canonical sweep: Gemma 4 31B IT and Qwen3.6 35B
A3B (thinking off) crossed with prompt v1 and v2. Override via CLI flags.

Output layout::

    eval/results/<UTC-timestamp>/
      raw.jsonl        # one JSON object per cell, written incrementally
      run_meta.json    # what was swept, when, how long, error counts, args

JSONL is written incrementally as cells complete, so a Ctrl+C or
network-level kill preserves partial data. The metadata file is written
only at the end (with a sentinel ``completed: false`` if the run was
interrupted, set by a context-manager-style finalizer).

Error handling: each cell is wrapped in retry-once-then-record-error.
The cell record's ``cell_status`` field is ``"ok"`` on success and
``"error"`` on persistent failure. Successful cells carry the full
scorer output; failed cells carry ``error_message``. Both share the
identifier fields (question_id, model, prompt_version, category) so the
report can pivot uniformly.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from eval.prompts import PROMPTS
from eval.scorer import (
    BenchmarkQuestion,
    load_benchmark,
    question_score_to_json,
    score_question,
    validate_benchmark_against_corpus,
)
from underwriting_copilot.answer import AnswerGenerator
from underwriting_copilot.retrieve import Retriever
from underwriting_copilot.query_rewriter import QueryRewriter


# ---- Defaults ----------------------------------------------------------

DEFAULT_MODELS: list[str] = [
    "gemma-4-31B-it-MLX-6bit",
    "Qwen3.6-35B-A3B-4bit",
]
DEFAULT_PROMPTS: list[str] = ["v1", "v2"]
DEFAULT_BENCHMARK_PATH = Path("eval/benchmark.toml")
DEFAULT_OUTPUT_DIR = Path("eval/results")
DEFAULT_TOP_K = 5

#: Wait between retry attempts. Short — oMLX hiccups are usually
#: instantaneous, so we don't need long backoff.
RETRY_DELAY_SECONDS = 2.0

#: Number of retries after the initial attempt fails. The total
#: attempts per cell is ``MAX_RETRIES + 1``.
MAX_RETRIES = 1


# ---- Retry wrapper -----------------------------------------------------


def try_answer_with_retry(
    generator: AnswerGenerator,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    max_retries: int = MAX_RETRIES,
    retry_delay: float = RETRY_DELAY_SECONDS,
    sleep_fn=time.sleep,
    use_hyde: bool = False,
):
    """Call ``generator.answer(query)`` with bounded retry.

    Returns ``(AnswerResult, None)`` on success or
    ``(None, error_message)`` on persistent failure.

    Retries on ``httpx.HTTPStatusError`` (e.g. oMLX 500) and
    ``httpx.RequestError`` (e.g. connection refused). Other exceptions
    are not retried — they indicate programming errors rather than
    transient infrastructure issues.

    ``sleep_fn`` parameter exists for tests; production calls use
    ``time.sleep``.
    """
    last_error: str | None = None
    for attempt in range(max_retries + 1):
        try:
            return generator.answer(query, top_k=top_k, use_hyde=use_hyde), None
        except httpx.HTTPStatusError as e:
            last_error = (
                f"HTTP {e.response.status_code} on attempt "
                f"{attempt + 1}/{max_retries + 1}"
            )
        except httpx.RequestError as e:
            last_error = (
                f"Network error on attempt {attempt + 1}/{max_retries + 1}: {e}"
            )
        except Exception as e:  # noqa: BLE001 — surface anything else verbatim
            return None, f"Unexpected error: {type(e).__name__}: {e}"

        if attempt < max_retries:
            sleep_fn(retry_delay)

    return None, last_error


# ---- Cell record builders ----------------------------------------------


def make_success_record(score) -> dict[str, Any]:
    """Wrap a :class:`QuestionScore` for JSONL output."""
    d = question_score_to_json(score)
    d["cell_status"] = "ok"
    d["error_message"] = None
    return d


def make_error_record(
    question: BenchmarkQuestion,
    model: str,
    prompt_version: str,
    error_message: str,
) -> dict[str, Any]:
    """Record for a failed cell — same identifier fields as success
    records but no metric fields. Report code must check ``cell_status``
    before reading metric fields."""
    return {
        "question_id": question.id,
        "category": question.category,
        "model": model,
        "prompt_version": prompt_version,
        "cell_status": "error",
        "error_message": error_message,
        "expected_refusal": question.expected_refusal,
    }


# ---- Sweep loop --------------------------------------------------------


@dataclass
class SweepProgress:
    """Per-cell progress for stderr reporting. Not serialised."""

    cell_index: int
    total_cells: int
    question_id: str
    model: str
    prompt_version: str
    cell_status: str  # "ok" or "error"
    summary: str  # short human description of result


def run_sweep(
    retriever: Retriever,
    questions: list[BenchmarkQuestion],
    models: list[str],
    prompt_names: list[str],
    top_k: int = DEFAULT_TOP_K,
    max_tokens: int | None = None,
    prompt_registry: dict[str, str] | None = None,
    generator_factory=None,  # for tests
    use_hyde: bool = False,
) -> Iterator[tuple[dict[str, Any], SweepProgress]]:
    """Yield ``(cell_record, progress)`` pairs as cells complete.

    The caller is responsible for writing records to disk and emitting
    progress to the terminal — this generator stays pure and testable.
    ``generator_factory`` exists for tests to substitute a fake
    AnswerGenerator; production calls let it default.

    ``max_tokens`` overrides AnswerGenerator's DEFAULT_MAX_TOKENS when
    provided. Leave as None for the canonical D014 behaviour; set to
    a higher floor (>=1500-2048) for hybrid-reasoning models like
    GLM-4.5 / GLM-4.7 where reasoning + close-marker + answer share
    the budget.
    """
    if prompt_registry is None:
        prompt_registry = PROMPTS
    if generator_factory is None:
        generator_factory = AnswerGenerator

    total = len(models) * len(prompt_names) * len(questions)
    cell_index = 0

    for model in models:
        for prompt_name in prompt_names:
            prompt_text = prompt_registry[prompt_name]
            generator_kwargs: dict = {
                "retriever": retriever,
                "model": model,
                "system_prompt": prompt_text,
            }
            if max_tokens is not None:
                generator_kwargs["max_tokens"] = max_tokens
            generator = generator_factory(**generator_kwargs)
            for question in questions:
                cell_index += 1
                result, error = try_answer_with_retry(
                    generator, question.query, top_k=top_k, use_hyde=use_hyde
                )
                if error is not None:
                    record = make_error_record(
                        question, model, prompt_name, error
                    )
                    progress = SweepProgress(
                        cell_index=cell_index,
                        total_cells=total,
                        question_id=question.id,
                        model=model,
                        prompt_version=prompt_name,
                        cell_status="error",
                        summary=error,
                    )
                else:
                    score = score_question(
                        question, result, prompt_version=prompt_name
                    )
                    record = make_success_record(score)
                    progress = SweepProgress(
                        cell_index=cell_index,
                        total_cells=total,
                        question_id=question.id,
                        model=model,
                        prompt_version=prompt_name,
                        cell_status="ok",
                        summary=_format_success_summary(score),
                    )
                yield record, progress


def _format_success_summary(score) -> str:
    """One-line description of a successful cell for stderr progress."""
    parts = [f"{score.latency_seconds:.1f}s"]
    if score.expected_refusal:
        parts.append(
            f"refused={score.actual_refused} "
            f"correct={score.refusal_correct}"
        )
    else:
        if score.citation_recall is not None:
            parts.append(f"recall={score.citation_recall:.2f}")
        if score.citation_precision is not None:
            parts.append(f"prec={score.citation_precision:.2f}")
        if score.hallucinated_citations_count:
            parts.append(f"halluc={score.hallucinated_citations_count}")
    return ", ".join(parts)


# ---- CLI ---------------------------------------------------------------


def _parse_csv_list(s: str) -> list[str]:
    """Split a comma-separated string into a list, stripping whitespace
    and skipping empties."""
    return [item.strip() for item in s.split(",") if item.strip()]


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eval.runner",
        description="Run the D014 eval sweep across models × prompts × benchmark.",
    )
    p.add_argument(
        "--models",
        type=_parse_csv_list,
        default=DEFAULT_MODELS,
        help=f"Comma-separated model IDs. Default: {','.join(DEFAULT_MODELS)}",
    )
    p.add_argument(
        "--prompts",
        type=_parse_csv_list,
        default=DEFAULT_PROMPTS,
        help=f"Comma-separated prompt versions from eval.prompts.PROMPTS. "
        f"Default: {','.join(DEFAULT_PROMPTS)}",
    )
    p.add_argument(
        "--benchmark",
        type=Path,
        default=DEFAULT_BENCHMARK_PATH,
        help=f"Benchmark TOML path. Default: {DEFAULT_BENCHMARK_PATH}",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write results subdirectory. Default: {DEFAULT_OUTPUT_DIR}",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Chunks per retrieval. Default: {DEFAULT_TOP_K}",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap on number of questions used (for smoke testing). "
        "Applied after --question-ids filter.",
    )
    p.add_argument(
        "--question-ids",
        type=_parse_csv_list,
        default=None,
        help="Comma-separated question IDs to include. Default: all questions.",
    )
    p.add_argument(
        "--use-hyde",
        action="store_true",
        help="Enable HyDE query rewriting on the dense channel (Q14). "
             "Original query continues to feed the sparse channel.",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Override AnswerGenerator's max_tokens budget. Default: "
             "None means use AnswerGenerator's DEFAULT_MAX_TOKENS "
             "(1024). Hybrid-reasoning models (GLM-4.5, GLM-4.7) "
             "typically need >=1500-2048 to avoid truncation of "
             "reasoning + answer; non-reasoning models like Gemma "
             "can leave this unset.",
    )
    return p


def _filter_questions(
    questions: list[BenchmarkQuestion],
    question_ids: list[str] | None,
    limit: int | None,
) -> list[BenchmarkQuestion]:
    if question_ids:
        wanted = set(question_ids)
        questions = [q for q in questions if q.id in wanted]
        missing = wanted - {q.id for q in questions}
        if missing:
            raise SystemExit(
                f"--question-ids referenced unknown IDs: {sorted(missing)}"
            )
    if limit is not None:
        questions = questions[:limit]
    return questions


def _validate_prompts(prompt_names: list[str]) -> None:
    unknown = [p for p in prompt_names if p not in PROMPTS]
    if unknown:
        raise SystemExit(
            f"--prompts referenced unknown versions: {unknown}. "
            f"Available: {sorted(PROMPTS.keys())}"
        )


def _emit_progress(progress: SweepProgress) -> None:
    """One line per cell to stderr; flushed so it doesn't buffer during
    long runs."""
    status_tag = "OK" if progress.cell_status == "ok" else "ERR"
    line = (
        f"[{progress.cell_index:03d}/{progress.total_cells:03d}] "
        f"{progress.question_id} {progress.model} {progress.prompt_version} "
        f"-> {status_tag} ({progress.summary})"
    )
    print(line, file=sys.stderr, flush=True)


def _utc_timestamp() -> str:
    """Filename-safe UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    _validate_prompts(args.prompts)

    print(f"Loading benchmark from {args.benchmark}...", file=sys.stderr)
    questions = load_benchmark(args.benchmark)
    questions = _filter_questions(questions, args.question_ids, args.limit)
    print(f"  {len(questions)} questions after filter.", file=sys.stderr)

    # Find repo root so retriever paths resolve regardless of cwd.
    repo_root = Path(__file__).resolve().parents[1]
    qdrant_path = repo_root / "scratch" / "qdrant"

    # Pre-flight: every gold_chunk_id must exist in the corpus, else the
    # eval is measuring against a stale benchmark. Done BEFORE the
    # Retriever opens so a second QdrantClient doesn't race with the
    # long-lived one for the (potentially locked) on-disk path.
    print("Validating benchmark against corpus...", file=sys.stderr)
    all_chunk_ids = _all_corpus_chunk_ids(qdrant_path)
    errors = validate_benchmark_against_corpus(questions, all_chunk_ids)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 2
    print(f"  All {sum(len(q.gold_chunk_ids) for q in questions)} gold "
          f"chunk references reconciled.", file=sys.stderr)

    query_rewriter = None
    if args.use_hyde:
        print("HyDE enabled — constructing QueryRewriter.", file=sys.stderr)
        query_rewriter = QueryRewriter()

    print("Initialising retriever...", file=sys.stderr)
    retriever = Retriever(
        qdrant_path=qdrant_path,
        vocab_path=repo_root / "corpus" / "bm25_vocab.json",
        verbose=False,
        query_rewriter=query_rewriter,
    )

    # Output directory
    timestamp = _utc_timestamp()
    run_dir = args.output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_path = run_dir / "raw.jsonl"
    meta_path = run_dir / "run_meta.json"
    print(f"Writing results to {run_dir}", file=sys.stderr)

    # Run the sweep
    total = len(questions) * len(args.models) * len(args.prompts)
    print(
        f"\nSweep: {len(args.models)} models × {len(args.prompts)} prompts "
        f"× {len(questions)} questions = {total} cells\n",
        file=sys.stderr,
    )

    start_time = time.time()
    error_count = 0
    completed = False
    try:
        with open(raw_path, "w") as fp:
            for record, progress in run_sweep(
                retriever=retriever,
                questions=questions,
                models=args.models,
                prompt_names=args.prompts,
                top_k=args.top_k,
                max_tokens=args.max_tokens,
                use_hyde=args.use_hyde,
            ):
                fp.write(json.dumps(record) + "\n")
                fp.flush()  # incremental persistence
                _emit_progress(progress)
                if record["cell_status"] == "error":
                    error_count += 1
        completed = True
    finally:
        elapsed = time.time() - start_time
        meta = {
            "completed": completed,
            "timestamp_utc": timestamp,
            "elapsed_seconds": round(elapsed, 2),
            "models": args.models,
            "prompts": args.prompts,
            "benchmark_path": str(args.benchmark),
            "question_count": len(questions),
            "total_cells": total,
            "error_cells": error_count,
            "top_k": args.top_k,
            "limit": args.limit,
            "question_ids": args.question_ids,
            "use_hyde": args.use_hyde,
            "max_tokens": args.max_tokens,
        }
        with open(meta_path, "w") as fp:
            json.dump(meta, fp, indent=2)

    print(
        f"\nDone. {total - error_count}/{total} cells ok, {error_count} errored "
        f"in {elapsed:.1f}s. Results in {run_dir}",
        file=sys.stderr,
    )
    return 0 if error_count == 0 else 1


def _all_corpus_chunk_ids(qdrant_path: Path) -> set[str]:
    """Pull every chunk_id from the Qdrant collection for validation.

    Self-contained: opens its own QdrantClient, scrolls, closes. Run
    before the Retriever is created so the two clients don't contend
    for the (potentially locked) on-disk path. Done at startup so a
    benchmark drift (chunk renamed / removed) surfaces before we spend
    an hour on the sweep.
    """
    from qdrant_client import QdrantClient

    client = QdrantClient(path=str(qdrant_path))
    try:
        collections = client.get_collections().collections
        if not collections:
            raise RuntimeError(f"No Qdrant collections found in {qdrant_path}")
        name = collections[0].name
        all_ids: set[str] = set()
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=name,
                limit=200,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                cid = p.payload.get("chunk_id")
                if cid:
                    all_ids.add(cid)
            if offset is None:
                break
        return all_ids
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
