# Open Questions

What we don't yet know but want to. A **state** document: resolved questions
are removed or marked closed — no growing graveyard (that's the journal's
job). Questions resolve *into* decisions; the two files are two ends of one
pipeline.

- **Q2** — Orchestration framework: LangGraph vs. plain Python
  orchestration vs. DSPy.
  - Status: open
  - Notes: LangGraph is familiar from `rag-eu-ai` and natural for
    graph-shaped retrieval pipelines, but adds dependency weight. Plain
    Python keeps the blast radius small and makes the code more readable
    for an interviewer browsing the repo. DSPy is interesting specifically
    for the confidence-scoring component (prompt optimisation), but
    introduces a learning cost against the 5-day budget.
  - Resolves into: a D-entry naming the framework choice and why.

- **Q3** — Confidence-score formula: how to combine retrieval score,
  reranker score, citation coverage, and LLM self-assessment into a
  single confidence number.
  - Status: open
  - Notes: The spec lists the four inputs but doesn't weight them. A
    defensible v1 is a simple weighted sum with weights chosen on the
    benchmark set; a more honest v1 reports all four numbers separately
    and explains why collapsing them to one is misleading at this stage.
    Worth treating as a probe rather than guessing.
  - Resolves into: a D-entry recording the formula (or the explicit choice
    not to collapse to one number) and the reasoning.

- **Q4** — Target deployment context: what stack does the interviewing
  reinsurer use today (Azure OpenAI / on-prem / hybrid)?
  - Status: open
  - Notes: The same project is framed differently depending on the answer.
    Cloud-first → local is "evaluation / dev environment mirroring a
    deployable architecture." Cautious about cloud → local is a deliberate
    data-sovereignty design choice. The README's lead paragraph depends on
    this.
  - Resolves into: a framing choice in the README (not a D-entry) once the
    answer is known.

- **Q5** — Topic vocabulary discipline: free-form list vs. controlled
  vocabulary.
  - Status: open
  - Notes: The first metadata pass (D006) surfaced near-synonyms in the
    topic list — `scenario_analysis` (PRA climate docs) vs.
    `scenario_testing` (PRA operational resilience); `esg` vs.
    `sustainability`. For retrieval this is fine — hybrid retrieval
    handles synonyms. For *filtering* — e.g. "show me only ESG docs" —
    synonyms split the result set. The question is whether to introduce a
    controlled vocabulary now (six docs, easy) or defer until the corpus
    is larger and the synonym problem is observable in eval results.
  - Resolves into: a D-entry naming either the controlled vocabulary OR
    the explicit deferral, with reasoning.


## Q7 — Revisit BGE-M3's full multi-functionality (FlagEmbedding/PyTorch) if Path B retrieval quality is insufficient?

D009 commits to Path B: MLX dense + BM25 sparse, fused via RRF in Qdrant. The rejected paths — FlagEmbedding's full triple-vector (dense + learned sparse + ColBERT) or an ONNX equivalent — remain valid options if Day 3 eval reveals retrieval ceiling effects that Path B cannot overcome.

Resolution criteria:

- If retrieval is acceptable on the Day 3 benchmark (target: ≥80% citation accuracy on the hand-curated query set), close Q7 with *Path B sufficient*.
- If quality is bounded by the sparse channel specifically (rather than the dense channel or generation layer), consider sidecar-ing FlagEmbedding for its learned sparse weights while keeping MLX for dense.
- If quality is bounded by single-vector dense limits, ColBERT-style late interaction becomes interesting; would more likely arrive via a cross-encoder reranker pass than via full BGE-M3 multi-vector.

To be revisited after the Day 3 eval pass.

## Q14 — Does HyDE recover the mechanism-clear strict misses on the production-default cell?

**Status**: Open  
**Opened**: 2026-06-20  
**Branch**: `v2.0-dev/q13-hyde-spike`  
**Depends on**: Q12 (diagnosis, resolved), Q13 (workstream)  
**Related**: Q15 (gold-labelling review — should resolve before Q14's final evaluation)

### Statement

Among the 11 strict retrieval misses identified on the production-default
cell (Gemma 4 31B IT × prompt v2) of the N=70 benchmark, 6 have failure
mechanisms that LLM query rewriting (HyDE) should plausibly address:

- **q001** — topic dominance (query topic dominates over scope intent)
- **q004** — surface match exists but missed (unexpected; needs investigation)
- **q013** — cross-issuer interference (Swiss Re returned over Munich Re)
- **q051** — topic dominance (broader "ambition" pulled away from specific decarb)
- **q055** — surface match exists but missed (unexpected; needs investigation)
- **q056** — surface match exists but missed (unexpected; needs investigation)

The other 5 strict misses are excluded from Q14's evaluation:

- **q042** — cross-document needing query decomposition, not query rewriting
- **q044, q046, q047, q053** — gold-labelling tightness, not retrieval failures
  (see Q15)

See the 2026-06-20 journal entry for the per-question mechanism
classification and the evidence base (gold and retrieved chunk text)
on which it rests.

### Falsification criterion (stated before evaluation runs)

HyDE must recover at least **4 of the 6** mechanism-clear strict
misses on the production-default cell, *without* introducing new
strict misses in the 23 currently-full-retrieval questions.

If HyDE recovers fewer than 4: HyDE is not the v2.0 lead path for
Q13 retrieval remediation, and instruct-tuned embeddings becomes the
lead candidate.

If HyDE introduces new strict misses among the 23 full retrievals:
HyDE cannot ship unmodified. The trade-off requires explicit
justification rather than aggregate-metrics hand-waving.

### Method (planned)

1. Implement `query_rewriter.py` in `src/underwriting_copilot/`. Wraps
   an LLM call with a fixed prompt that produces a hypothetical
   answer passage. Use the production-default model (D015).
2. Add `use_hyde: bool` flag to `Retriever.retrieve()`. Default
   `False` so the existing path is unchanged.
3. Re-run the production-default cell of the canonical sweep with
   `use_hyde=True`. Compare per-question miss rate against the
   2026-06-18T15-32-07Z baseline.
4. Per-question comparison: which of the 6 mechanism-clear misses
   recover, which don't, which currently-full questions regress.

### Out of scope for Q14

- q044, q046, q047, q053 gold-labelling review — see Q15
- q042 query decomposition — future work, likely Q16+
- Other cells (Qwen × v1/v2, Gemma × v1) — re-evaluate only if HyDE
  proves out on the production-default cell first
- Latency budget for HyDE adding a pre-retrieval LLM call — will be
  measured but is not the falsification axis at this stage

---

## Q15 — Gold-labelling review on 4 strict-miss questions

**Status**: Open  
**Opened**: 2026-06-20  
**Branch**: `v2.0-dev/q13-hyde-spike` (raised here; resolution may move to a separate branch)  
**Related**: Q14 (must resolve before Q14's final evaluation to avoid confounding)

### Statement

Phase 1b inspection (see 2026-06-20 journal entry) revealed that 4 of
the 11 strict-miss questions on the production-default cell appear to
have gold tags that are tighter than the question text warrants. In
each case, the retrieved chunks arguably answer the question; the
gold tags are narrow choices that do not reflect the only valid
answers.

If confirmed, this means the published `mean_recall = 0.598` for the
production-default cell **understates** the system's true retrieval
quality. Section 6 of the v1.0 report does not currently acknowledge
this.

### The 4 questions

**q044** — "What climate-related insurance products or solutions do
Munich Re and Swiss Re highlight in their sustainability disclosures?"

Gold pairs Munich Re's `climate-insurance-solutions` with Swiss Re's
`impact-on-the-insurability-of-property-r`. The Swiss Re gold chunk is
about *insurability* (whether properties can be insured), not about
insurance products or solutions. The pairing appears semantically
inconsistent.

**q046** — "How does Swiss Re's underwriting approach align with the
PRA's expectations on scenario governance and controls in SS5/25?"

Gold pairs PRA's `scenario-governance-controls-and-review` with Swiss
Re's `approach-in-underwriting`. The Swiss Re gold chunk is about
thermal coal policy specifically, not about scenario governance or
controls. The two gold chunks do not align with each other or with
the question.

**q047** — "What renewable energy investment or coverage approaches do
Munich Re and Swiss Re disclose in their sustainability reports?"

Gold pairs Munich Re's `renewable-energy-and-green-bonds` with Swiss
Re's `number-of-re-insured-renewable-energy-po` (a metrics page).
Retrieval found Swiss Re's `advancing-the-net-zero-transition`, which
also discusses renewables. The Swiss Re gold is a narrow choice;
broader chunks may be valid answers.

**q053** — "How does Swiss Re combine its underwriting approach with
its broader monitoring of climate risks?"

Gold pairs `approach-in-underwriting` (thermal coal policy only) with
`monitoring-climate-risks` (GHG emissions monitoring only). Other
Swiss Re underwriting and monitoring chunks (e.g. `underwriting`,
`physical-and-transition-risks`) are also relevant and were retrieved.

### Resolution path

1. **Review each gold tag**. Read the original question, the current
   gold chunks, and 2-3 plausible alternative chunks. Decide whether
   the gold should be widened, narrowed, or replaced.
2. **If gold tags change**: re-run the canonical sweep on the
   production-default cell (and ideally all 4 cells for honesty).
   Update Section 6 of the report and the published numbers.
3. **If gold tags stand**: document why each is the only valid answer
   despite the Phase 1b evidence suggesting otherwise.
4. **Either way**: record the result in the journal and as a new
   decision in `docs/decisions.md` (likely D016).

### Implication for v1.0

The v1.0 report's `mean_recall = 0.598` was honestly published from
the canonical run with the gold tags as they stood. Q15 may move the
number upward. If it does, that is a strengthening of the v1.0
claim, not a retraction — but the change should be tracked
transparently rather than silently re-run.

### Implication for Q14

Q14's HyDE evaluation should not target these 4 questions. If gold
tags change, q044/q046/q047/q053 should be re-classified before the
HyDE evaluation runs, to avoid HyDE getting credit (or blame) for
gold-labelling movement.
