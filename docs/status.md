# Cedant — Project Status

**Project:** `underwriting-copilot` — RAG-based reinsurance underwriting Q&A
**Phase:** End of Day 4 of 5 (substantive)
**Last updated:** 2026-06-18 evening

## What works end-to-end

The full retrieve → generate → cite → validate pipeline is operational
on real regulatory and corporate documents, with prompt v2 promoted to
production per D015 follow-up:

- **Corpus**: 461 chunks across 6 PDFs (PRA SS1/21, SS3/19, SS5/25,
  EIOPA System of Governance, Munich Re Sustainability 2023, Swiss Re
  Sustainability 2024). Indexed via Docling chunking, BGE-M3 dense
  embeddings (CLS+L2 pooled), BM25 sparse with Porter-stemmed
  vocabulary, all persisted in Qdrant local mode.
- **Retrieval**: hybrid BGE-M3 dense + BM25 sparse fused via RRF
  (k=60, candidates_per_channel=50), exclude-superseded filter on by
  default. Single-query latency 30-50ms warm. Known limitation per
  Q12: query/chunk language asymmetry on single-vector dense produces
  ~11.5% retrieval miss rate on the benchmark; remediation deferred
  to v2 per Q13.
- **Answer generation**: `AnswerGenerator` against oMLX's
  OpenAI-compatible chat-completions endpoint. Production default
  `gemma-4-31B-it-MLX-6bit` per D015; overridable via
  `UNDERWRITING_COPILOT_MODEL`. Production prompt `SYSTEM_PROMPT` is
  v2 per D015 follow-up; v1 preserved historically in
  `eval/prompts.py` for D014 sweep replay.
- **Citation validation**: `validate_citations` partitions LLM
  citations into valid (in retrieved context) and hallucinated, the
  load-bearing eval signal.
- **Refusal contract**: exact-phrase detector with 100% precision
  observed across both models and both prompts (56/56 refusal cases
  across all 4 cells of the D014 sweep, all three refusal categories).
- **Eval harness**: 40-question benchmark, 2×2 sweep runner, per-cell
  scoring, deterministic aggregator producing `report.md` from
  `raw.jsonl`. Numbers reproducible end-to-end from raw data.
- **Documentation trio**: `governance.md`, `security.md`,
  `evaluation.md` — scope/contracts/decisions, threat model and
  mitigations, evaluation methodology paired with the machine-
  generated `report.md`.

## Key findings from Day 3 sweep

The D014 sweep (2 models × 2 prompts × 40 questions = 160 cells, 0
errors, 23.7 minutes wall-clock) settled the load-bearing Day 3
question. Numbers below reproduce exactly from `report.py` running
over `raw.jsonl`:

- **Interpretation B is supported.** The Day 2 family-axis finding
  (Qwen weaker at rigid format than Gemma even with thinking off)
  retracts on N=26 follow-up. Prompt v2 closes 89% of the Day 2 gap.
- **Within-document workload: equivalent quality between models.**
  Gemma v2 and Qwen v2 both at 0.929 mean recall on 21 within-
  document retrievable questions; both at 1.000 on 15 single-chunk
  retrievable. The 3.2pp full-sample gap is entirely concentrated in
  the 2 cross-document questions.
- **Cross-document synthesis (N=2): Gemma 0.417, Qwen 0.000.**
  Suggestive but not robust at this sample size; explicitly flagged
  as a claim-not-supported in `docs/evaluation.md`.
- **Refusal: 100% across the board.** Both models, both prompts, all
  14 refusal types (out-of-corpus, adjacent-but-unanswered, false-
  premise).
- **Latency: Qwen 6.1× faster on answerable workload** (3.4s vs 20.7s
  mean), 6.2× faster on refusal (1.3s vs 7.9s).
- **Hallucination floor:** Gemma 0 across the full 80-cell answerable
  sweep; Qwen × v2 had 3 (q008 ×2, q019 ×1). Small absolute numbers,
  qualitative difference.
- **Retrieval miss rate: 11.5%** (3/26 answerable questions; q001,
  q004, q013). Upstream of the answer model; the same 3 questions
  fail across all 4 cells. Root cause per Q12: query/chunk language
  asymmetry on CLS-pooled dense embeddings.

## Open questions

| ID | Status | Topic |
|---|---|---|
| Q7  | OPEN | Revisit FlagEmbedding for full BGE-M3 multi-functionality (multi-vector / sparse channels). Strengthened by Q13. |
| Q8  | CLOSED 2026-06-18 (resolved) | SS1/21 supersession metadata corrected; SS3/19→SS5/25 verified. |
| Q9  | CLOSED 2026-06-18 (deferred) | Gemma 4 12B blocked at oMLX/mlx_vlm layer. 7-14B sweet spot remains empirically untestable on current stack. |
| Q10 | EXPLORATORY 2026-06-18 | DSPy/GEPA layer. Was Phase 2 of D014; downgraded to exploratory after prompt v2 closed the gap. Phase 2 work optional for Day 5. |
| Q11 | RESOLVED 2026-06-18 → D015 | Production model choice. Gemma 31B IT as default; Qwen via env override. |
| Q12 | CLOSED 2026-06-18 (diagnosed) | Retrieval miss pattern root-caused to query/chunk language asymmetry on single-vector dense. Remediation deferred to v2 via Q13. |
| Q13 | OPEN | Remediation options for query/chunk asymmetry — three paths (LLM query expansion / HyDE; cross-encoder reranker; BGE-M3 multi-vector via Q7). v2 work-stream. |

## Decisions

15 lodged: D001-D015. Latest:

- **D013**: answer.py contracts (citation `[chunk_id]`, refusal
  phrase exact, hallucination signal, model/endpoint injected).
- **D014**: eval harness shape (plain-Python, 40-question benchmark,
  2×2 sweep with pre-stated falsification criterion). Closed; numbers
  in `eval/results/2026-06-18T12-16-35Z/report.md`.
- **D015**: production model default Gemma 4 31B IT, resolves Q11.
  Override via env var.

## Test count

158 unit tests green across the project:

- 36 retrieval/index tests (Days 1-2)
- 46 answer.py tests
- 44 eval/scorer tests
- 36 eval/runner tests (4 missing from earlier — recount; the actual
  number when last verified was 36)
- 32 eval/report tests

Run with `uv run pytest`. Full suite: ~2-3 seconds.

## Recent commits

```
4f1d050  feat: answer.py v4 — Gemma default, env-var override
4079dc9  docs: D014 + Q10 + Day 3 preliminary follow-up
fef824f  docs: Q9 CLOSED (DEFERRED) — Gemma 4 12B blocked
ad02fdc  feat: eval benchmark + prompt versions for D014
a3b4601  feat: eval scorer + runner — D014 harness operational
7e60ef4  docs: Day 3 close — family-axis retraction; Q11+Q12 opened
b08c8b8  docs: Q12 closed (diagnosed-not-resolved); Q13 lodged
ad12047  docs: D015 — production model default Gemma 4 31B IT, resolves Q11
c243a40  feat: promote prompt v2 to production per D015 follow-up
6300352  feat: eval/report.py — deterministic aggregator over raw.jsonl
3548323  docs: governance.md — state doc
9e02e4c  docs: security.md — state doc
62ed289  docs: evaluation.md — eval methodology
```

42 commits total in the 5-day window.

## Sweep artefact location

`eval/results/2026-06-18T12-16-35Z/`
- `raw.jsonl` — 160 per-cell records (gitignored)
- `run_meta.json` — sweep metadata (gitignored)
- `report.md` — 150-line aggregated markdown report, generated by
  `eval/report.py` from raw.jsonl (gitignored; regenerable
  deterministically)

Stderr `tee` at `eval/results/sweep_console.log` (gitignored).

Reproduction:

```bash
# Full sweep, ~24 min
uv run python -m eval.runner

# Regenerate report from existing run
uv run python -m eval.report --run-dir eval/results/2026-06-18T12-16-35Z
```

A separate ad-hoc probe run lives at
`eval/results/2026-06-18T14-31-01Z/` — the Q12 top_k=8 spot-check.
Not the canonical D014 data.

## Day 4 outcomes (complete)

- Q12 investigated through three probes (top_k experiment, RRF tuning
  grid, dense-channel localization) and closed-diagnosed. Q13 lodged
  for v2 remediation.
- Q11 resolved → D015 lodged (Gemma default; Qwen via env override).
  No code change required.
- Prompt v2 promoted to production: `answer.py`'s `SYSTEM_PROMPT`
  body replaced with v2 text; `eval/prompts.py` SYSTEM_PROMPT_V1
  inlined as a string literal so D014 replay still measures the
  original v1.
- `eval/report.py` shipped + 32 unit tests + numerical validation
  against the journal's eyeballed numbers (all reproduce exactly).
- `docs/governance.md`, `docs/security.md`, `docs/evaluation.md`
  shipped as state docs.

## Day 5 priorities

1. **Synthetic documents per D003** — three documents for the corpus
   (Risk Appetite Statement, Delegated Authority Matrix, Internal
   Policy on Coal Underwriting) to demonstrate the system extends to
   internal/proprietary documents beyond public regulatory ones. Most
   substantial Day 5 work.
2. **README polish** — top-level README that orients a fresh reviewer.
   Currently minimal; needs to explain the project, how to run the
   demo, and where to read for evaluation/governance/security context.
3. **Final 5-day consolidation journal entry** — summary of the whole
   arc covering the family-axis retraction, the Q12 diagnostic close,
   and the production posture.

Optional Day 5 if slack remains:

- **Q10 Phase 2 (GEPA on Qwen)** — exploratory work-stream from D014.
- **Extended benchmark** — additional questions to harden the
  cross-document N=2 claim and reduce the benchmark-size limitation
  flagged in evaluation.md.
- **Demo session capture** for the README — sample queries with
  cited outputs.

## Pending external artefact

`~/Downloads/tst_llm_journal_snippet.md` — v3 supersedes v2.bak.
Records the retracted family-axis finding honestly and updates the
cross-project read-across to be methodological (echo-trap pattern as
prompt-design hazard) rather than model-property. Still uncommitted
to either project; lands in `tst_llm/docs/journal.md` next time that
project is touched.
