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
