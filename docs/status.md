# Cedant — Project Status

**Project:** `underwriting-copilot` — RAG-based reinsurance underwriting Q&A
**Phase:** End of Day 3 of 5
**Last updated:** 2026-06-18 late afternoon

## What works end-to-end

The full retrieve → generate → cite → validate pipeline is operational on
real regulatory and corporate documents:

- **Corpus**: 461 chunks across 6 PDFs (PRA SS1/21, SS3/19, SS5/25, EIOPA
  System of Governance, Munich Re Sustainability 2023, Swiss Re
  Sustainability 2024). Indexed via Docling chunking, BGE-M3 dense
  embeddings (CLS+L2 pooled), BM25 sparse with Porter-stemmed vocabulary,
  all persisted in Qdrant local mode.
- **Retrieval**: hybrid BGE-M3 dense + BM25 sparse fused via RRF (k=60),
  exclude-superseded filter on by default. Single-query latency 30-50ms
  warm.
- **Answer generation**: `AnswerGenerator` against oMLX's
  OpenAI-compatible chat-completions endpoint. Two models in active use:
  `gemma-4-31B-it-MLX-6bit` (default) and `Qwen3.6-35B-A3B-4bit`
  (with `enable_thinking=False` via `chat_template_kwargs`).
- **Citation validation**: `validate_citations` partitions LLM citations
  into valid (in retrieved context) and hallucinated, the load-bearing
  eval signal.
- **Refusal contract**: exact-phrase refusal detector with 100% precision
  observed across both models and both prompts (14/14 across all 4 cells
  of the D014 sweep).
- **Eval harness**: 40-question benchmark, 2×2 sweep runner, per-cell
  scoring (citation_recall, citation_precision, citation_f1,
  retrieval_recall, refusal_correct, latency). 80 unit tests pinning the
  harness's correctness.

## Key findings from Day 3 sweep

The D014 sweep (2 models × 2 prompts × 40 questions = 160 cells, 0
errors, 23.7 minutes wall-clock) settled the load-bearing Day 3 question:

- **Interpretation B is supported.** The Day 2 family-axis finding
  (Qwen weaker at rigid format than Gemma even with thinking off)
  retracts on N=26 follow-up. Prompt v2 closes 89% of the Day 2 gap.
- **Within-document workload: equivalent quality between models.**
  Gemma v2 and Qwen v2 both at 0.929 mean recall on 21 within-document
  retrievable questions; both at 1.000 on 15 single-chunk retrievable.
- **Cross-document synthesis (N=2): Gemma 0.417, Qwen 0.000.**
  Suggestive but not robust at this sample size.
- **Refusal: 100% across the board.** Both models, both prompts, all 14
  refusal types (out-of-corpus, adjacent-but-unanswered, false-premise).
- **Latency: Qwen 6.1× faster on answerable workload** (3.4s vs 20.7s
  mean), 6.2× faster on refusal (1.3s vs 7.9s).
- **Retrieval miss rate: 11.5%** (3/26 answerable questions). Upstream
  of the answer model; the same 3 questions fail across all 4 cells.

## Open questions

| ID | Status | Topic |
|---|---|---|
| Q7  | OPEN | Revisit FlagEmbedding for full BGE-M3 multi-functionality (multi-vector / sparse channels). Possibly strengthened by Q12. |
| Q8  | CLOSED 2026-06-18 (resolved) | SS1/21 supersession metadata corrected; SS3/19→SS5/25 verified. |
| Q9  | CLOSED 2026-06-18 (deferred) | Gemma 4 12B blocked at oMLX/mlx_vlm layer. 7-14B sweet spot remains empirically untestable on current stack. |
| Q10 | EXPLORATORY 2026-06-18 | DSPy/GEPA layer. Was Phase 2 of D014; downgraded to exploratory after prompt v2 closed the gap. Phase 2 work optional for Day 5. |
| Q11 | OPEN | Production model choice: Gemma 31B IT vs Qwen 35B A3B. Trade-off is latency (6.1× favoring Qwen) vs cross-doc synthesis (Gemma edge, N=2 only). |
| Q12 | OPEN | Retrieval miss pattern (11.5% of answerable). Day 4 investigation. |

## Test count

All unit tests green: 80 in eval/, plus the existing retrieval + answer
test suite from Days 1-2. Run with `uv run pytest`.

## Recent commits (since v4 answer.py)

```
4f1d050  feat: answer.py v4 — Gemma default, env-var override; Day 3 preliminary journal
4079dc9  docs: D014 + Q10 + Day 3 preliminary follow-up
fef824f  docs: Q9 CLOSED (DEFERRED) — Gemma 4 12B blocked by oMLX/mlx_vlm size-specific loader bug
ad02fdc  feat: eval benchmark + prompt versions for D014
a3b4601  feat: eval scorer + runner — D014 harness operational
<pending>  docs: Day 3 full close — family-axis retraction, Q11/Q12 opened
```

## Day 3 sweep artefact location

`eval/results/2026-06-18T12-16-35Z/`
- `raw.jsonl` — 160 per-cell records, gitignored
- `run_meta.json` — sweep metadata, gitignored

A `tee` of stderr is at `eval/results/sweep_console.log`, also
gitignored. Re-running the sweep is reproducible via
`uv run python -m eval.runner` with the same defaults; the raw.jsonl
will be the authoritative input for `report.py` (next session).

## Day 4 priorities (in order)

1. **Q12 investigation** — top_k experiment first (cheapest), then
   deeper diagnostics if needed. Affects all subsequent results.
2. **Q11 decision** — production model choice. Once made, lodge as D015.
3. **`eval/report.py`** — deterministic aggregator from `raw.jsonl`
   producing the per-cell summary tables for the Day 5 artefact.
4. **`docs/governance.md`, `docs/security.md`, `docs/evaluation.md`** —
   original Day 4 plan, possibly trimmed depending on Day 4 throughput.
5. **Optional Q10 Phase 2 (GEPA)** — only if Day 4 has slack.

## Day 5 priorities

- Synthetic documents per D003 (Risk Appetite, Delegated Authority,
  Internal Policy).
- Final README polish and Day 5 narrative finalization.
- Final journal entry consolidating the whole 5-day arc.

## Pending external artefact

`~/Downloads/tst_llm_journal_snippet.md` — v3 supersedes the v2
that's currently staged. Records the retracted family-axis finding
honestly. Still uncommitted to either project; lands in
`tst_llm/docs/journal.md` next time that project is touched.
