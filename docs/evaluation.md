# Cedant — Evaluation Methodology

**Project:** `underwriting-copilot` — RAG-based reinsurance underwriting Q&A
**Last updated:** 2026-06-18 (Day 4 of 5)
**Status doc:** overwrites freely; supersedes any earlier version

This document records the methodology of the D014 evaluation: how the
benchmark was constructed, what each metric measures, what the 2x2
sweep design was intended to test, what we can and cannot claim from
the results, and how to reproduce the work. It complements
`governance.md` (scope and contracts) and `security.md` (threat model)
and is the methodology paired with the machine-generated data in
`eval/results/2026-06-18T12-16-35Z/report.md`.

## Purpose of the evaluation

The D014 eval was designed to **falsify** an early-Day-2 finding that
the citation discipline gap between `gemma-4-31B-it-MLX-6bit` and
`Qwen3.6-35B-A3B-4bit` reflected a model-family property. The
preliminary N=3 measurement showed Qwen producing systematically
malformed `[chunk_id_N]` placeholder citations while Gemma produced
clean verbatim chunk_ids. The framing at the time was
"family-axis decisive on rigid-format tasks." The risk was that this
interpretation conflated three confounded variables — model property,
prompt-fit artifact, and sampling noise — all of which were consistent
with the surface measurement.

D014 was deliberately designed to be capable of falsifying that
framing. A 2x2 sweep (both models × two prompts) on a 26-question
answerable benchmark plus 14-question refusal benchmark would
distinguish the candidates: if prompt v2 closed the gap on Qwen with
no change to Gemma, the framing was a prompt-fit artifact, not a
model property. The pre-stated falsification criterion was 10
percentage points on citation_recall — if v2 moved Qwen toward Gemma
by less than 10pp, the family-axis interpretation survived; otherwise
it had to be retracted.

The eval is therefore not just "how well does the system work?"; it's
"is the earlier interpretation supportable on more data?" The
distinction matters for what we can and cannot claim from the results.

## Benchmark construction

The benchmark is **40 hand-crafted questions** stored in
`eval/benchmark.toml`, partitioned as follows:

**26 answerable questions** (gold chunk_id references mandatory):

- 7 PRA SS5/25 climate questions (4 single-chunk, 3 multi-chunk).
- 5 EIOPA System of Governance questions (4 single-chunk, 1 multi-chunk).
- 5 Munich Re Sustainability 2023 questions (4 single-chunk, 1
  multi-chunk).
- 5 Swiss Re Sustainability 2024 questions (4 single-chunk, 1
  multi-chunk).
- 2 PRA SS1/21 operational resilience questions (both single-chunk).
- 2 cross-document synthesis questions where the gold spans two issuers
  (Munich vs Swiss thermal coal policy; EIOPA vs PRA regulatory common
  themes).

**14 should-refuse questions** with gold_chunk_ids = [] by construction:

- 6 out-of-corpus refusals — topics outside the corpus entirely
  (Bermuda hurricane bond ratios, NAIC capital rules, China insurance
  policy, Lloyd's crypto, etc.).
- 4 adjacent-but-unanswered refusals — topics the corpus discusses
  qualitatively but where the question demands a specific number or
  detail the corpus doesn't contain. This is the hardest category: the
  model has to refuse rather than invent a number that "sounds right
  for the topic."
- 4 false-premise refusals — questions that assume something the
  corpus actively contradicts (e.g., asking about a tornado-specific
  PRA Supervisory Statement when no such SS exists; asking about a
  Munich Re withdrawal from a market when no such withdrawal happened).

All 37 gold_chunk_id references were reconciled against the 461-chunk
corpus before the eval ran; the runner does this validation at startup
via `validate_benchmark_against_corpus`, failing fast if any reference
is stale.

**Why hand-crafted, not auto-generated.** Auto-generated benchmarks
typically produce questions that are answerable by surface-level
extraction or that don't test specific failure modes. Each question
here was written to test a particular property of the pipeline:
single-chunk to test simple retrieval + cite; multi-chunk to test
synthesis; cross-document to test multi-source reasoning; the three
refusal categories to test the refusal contract under
increasingly subtle attacks. The benchmark is small (40) but
deliberately structured.

## Metrics

Six per-question metrics produced by `eval/scorer.py`, plus three
diagnostic counts:

**citation_recall** = |cited ∩ gold| / |gold|. Set-based — duplicate
citations don't inflate the score. `None` for refusal questions (gold
is empty by construction). Answers "did the model find the chunks we
expected?" Insensitive to extra citations.

**citation_precision** = |cited ∩ gold| / |cited|. `None` for refusal
questions. Answers "of the chunks the model cited, what fraction was
actually relevant?" Penalises citation sprawl.

**citation_f1** = harmonic mean of recall and precision. `None` for
refusal questions. Single-score summary; useful when comparing cells
but reduces interpretability vs the separate channels.

**retrieval_recall** = |retrieved ∩ gold| / |gold|. `None` for refusal
questions. Upper bound on citation_recall: the answer model can only
cite chunks the retriever surfaced. **Crucial axis** — without it,
retrieval failures look like model failures.

**refusal_correct** = boolean, did the model's refusal decision match
the gold label. The detector is exact-phrase (case-sensitive, partial
refusals rejected). Aggregated as correct/total per cell.

**hallucinated_citations_count** = number of citations the model
emitted that pointed to chunks not in the retrieved context. Distinct
from extra_citations_count, which counts valid citations to retrieved
chunks not in gold. The hallucination count is the confabulation
signal.

**Diagnostic counts:** total_citations_count (raw count including
dupes), unique_citations_count (deduplicated), extra_citations_count
(valid citations beyond gold). Latency in seconds.

**Why None for refusal questions on citation/retrieval metrics.**
Gold is empty for refusal questions by construction. Recall is
undefined when the denominator is zero. We could define it as 1.0
(vacuously, the model found everything it was supposed to find), but
that would conflate "correctly refused" with "answered with citations"
in any aggregation. Keeping it as None forces aggregation code to
handle the refusal case explicitly, which is the right discipline for
this metric.

## Sweep design

The 2x2 design is:

- **Models:** gemma-4-31B-it-MLX-6bit, Qwen3.6-35B-A3B-4bit (with
  `enable_thinking=False`).
- **Prompts:** v1 (original; uses literal `[chunk_id]` as both
  placeholder name and emit-format), v2 (uses `<ID>` metasyntax plus
  one concrete worked example; explicit prohibitions against observed
  drift patterns).

Total: 4 cells × 40 questions = 160 cells per sweep. Wall-clock 23.7
minutes on the MacBook M5 Max with both models warm-loaded in oMLX.

The eval harness runs each cell sequentially (one cell creates a
fresh `AnswerGenerator` per `(model, prompt)` combo, then iterates
the questions). Each `(question, model, prompt)` cell wraps the
inference call in a retry-once-then-skip wrapper so transient oMLX
hiccups don't kill the sweep. Cell status (ok / error) is recorded
per record; the D014 sweep had 0 errored cells.

**Falsification criterion (pre-stated, per D014):** if prompt v2 moves
Qwen's mean citation_recall toward Gemma's by ≥10 percentage points,
the Day 2 family-axis interpretation is retracted. The observed
movement was **+26.9 percentage points** on Qwen, with Gemma
unchanged. The interpretation was retracted accordingly.

## Subset analysis

The full-sample mean is one number; subset analysis localizes where
that number comes from. Eight subsets reported by `eval/report.py`:

- **all_answerable** (n=26) — the headline number.
- **excluding_retrieval_misses** (n=23) — what the headline would be
  if retrieval worked perfectly. Localizes the upper bound of
  answer-model-only quality.
- **single_chunk** (n=18) / **single_chunk_retrievable** (n=15) —
  the simplest questions; retrieval-failed ones removed.
- **multi_chunk** (n=6) — multiple gold chunks within one document.
- **within_document** (n=24) / **within_document_retrievable** (n=21)
  — single + multi, retrieval-failed ones removed in the second
  variant.
- **cross_document** (n=2) — gold spans two issuers.

The breakdown reveals the within-document vs cross-document split
that the headline number obscures. On the D014 data, Gemma v2 and
Qwen v2 are identical on within_document_retrievable (both 0.929)
and on single_chunk_retrievable (both 1.000). The full-sample 3.2pp
gap collapses to 0pp on these subsets and concentrates entirely in
the 2 cross-document questions (Gemma 0.417, Qwen 0.000).

Subset analysis is also where the **N=2 caveat for cross-document
becomes structurally visible** — the subset table shows n=2 next to
the numbers, which makes the sample-size limitation impossible to
overlook in any reading of the report.

## What we can claim and what we cannot

**Claims supported by the data:**

- Prompt v2 closes the v1 Gemma-vs-Qwen citation_recall gap from
  30.1pp to 3.2pp on the full 26-question answerable set, with no
  change to Gemma. The Day 2 family-axis interpretation is retracted.
- On within-document workloads (single-chunk and multi-chunk within
  one document, n=21 retrievable), Gemma and Qwen produce equivalent
  quality with prompt v2.
- Both models, both prompts, refuse correctly on all 14 refusal-
  category questions across all 56 cells. The refusal contract works
  as designed on this benchmark.
- Gemma's hallucination floor is 0 across the full 80-cell answerable
  sweep; Qwen × v2 is 3. Qualitative difference but small absolute
  numbers.
- Qwen is 6.1× faster on answerable queries (3.4s vs 20.7s mean) and
  6.2× faster on refusal (1.3s vs 7.9s).

**Claims NOT supported by the data:**

- That Gemma is "better at cross-document synthesis" than Qwen. The
  cross-document subset is N=2. The direction favors Gemma but the
  sample is too small to support a confident claim.
- That the 11.5% retrieval miss rate is representative of production
  workloads. The benchmark questions were chosen to test specific
  failure modes; the retrieval miss rate on operator-written queries
  in production could be substantially higher or lower.
- That citation_recall is a complete measure of answer quality. It
  measures whether the model found the gold chunks we identified; it
  does not measure whether the model's natural-language answer
  accurately summarised those chunks. An LLM-as-judge layer would be
  needed for that and is deferred (Q10.3 sub-question).
- That zero errored cells in 160 means the system is highly
  available. Both models were warm-loaded in oMLX before the sweep
  began; cold-start, model-switch, and long-tail latency behavior
  are not characterised here.

## Methodological limitations

- **Benchmark size.** 40 questions across 6 source documents is small
  by IR standards. Drift detection and edge-case coverage would
  benefit from ≥200 questions. Pinned as an explicit limitation in
  `governance.md`.
- **N=2 on cross-document.** Two questions is too few to support a
  confident model comparison on this dimension. Acknowledged in every
  surface where the cross-document numbers appear, including the
  per-cell subset table in the machine-generated report.
- **Gold-chunk model.** Each answerable question has a designated
  gold chunk set. The model may legitimately cite a chunk that
  answers the question but isn't in our gold list — these would
  count against citation_precision. The metric is a proxy for
  "correctness", not correctness itself. On the cross-document
  questions specifically, the benchmark notes record that the model
  may legitimately cite supporting chunks beyond the anchors; this
  is partially mitigated by reporting both recall and precision.
- **No baseline comparison.** The eval reports absolute numbers per
  cell. It does not compare to a baseline (no retrieval; retrieval
  without RAG; a hosted LLM like Claude or GPT-4). Useful for
  internal comparison; less useful for situating the result in the
  broader IR / RAG literature.
- **No LLM-as-judge semantic correctness.** citation_recall and
  related metrics measure structural correctness (did the model cite
  the chunks we expected to cite). They don't measure whether the
  model's prose accurately reflects the chunks it cited. A v2 eval
  could layer this on; deferred as Q10.3.
- **One-shot, no temperature sweep.** Temperature is hardcoded to 0
  for determinism. Production behavior at temperatures >0 (which
  some deployments use for "more natural" output) is not
  characterised.
- **Two models tested, not a wider survey.** The 2x2 design tested
  two specific candidates because they were the ones available on
  the oMLX stack at the right size. Gemma 4 12B was deferred per Q9
  (infrastructure-blocked). A wider model survey would strengthen
  generalisation.

## Reproduction

The full sweep is reproducible end-to-end:

```bash
# Run the sweep (~24 minutes, requires oMLX running with both models)
uv run python -m eval.runner

# Generate the markdown report from the latest run
uv run python -m eval.report

# Or generate from a specific run
uv run python -m eval.report --run-dir eval/results/2026-06-18T12-16-35Z
```

The harness writes per-cell records incrementally to `raw.jsonl`,
flushing after each cell, so a partial run preserves its data even
if interrupted. The `run_meta.json` `completed` field distinguishes
clean finishes from interrupted runs.

A smaller sweep for quick verification:

```bash
uv run python -m eval.runner --limit 2 --models gemma-4-31B-it-MLX-6bit --prompts v2
```

Filters by question IDs are supported for targeted re-runs after
changes:

```bash
uv run python -m eval.runner --question-ids q001,q004,q013 --top-k 8
```

(That last command was the Q12 top_k probe from Day 4 morning.)

## What this eval is for, restated

This is the empirical basis for D015 (the production model choice)
and for Q11's resolution. It is the data behind the family-axis
retraction. It is the evidence that informed the Q12 closure as
"diagnosed-but-unresolved" rather than "fixable with config." Every
load-bearing claim in `docs/journal.md` about Day 3 findings traces
back to a specific cell or subset in this evaluation; the journal's
eyeballed numbers all reproduce exactly in `report.md` regenerated
from `raw.jsonl`.

The methodology described here is not an academic publication's
methodology — it's the methodology of a one-engineer five-day
artefact built for an interview review. The principle behind both,
though, is the same: name what was measured, name what was
controlled, name what was not, and let the reader assess whether the
claims survive their assumptions.
