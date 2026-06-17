# Open Questions

What we don't yet know but want to. A **state** document: resolved questions
are removed or marked closed — no growing graveyard (that's the journal's
job). Questions resolve *into* decisions; the two files are two ends of one
pipeline.

- **Q1** — Corpus: real public regulatory documents vs. a synthetic toy
  corpus.
  - Status: open
  - Notes: The spec describes internal reinsurer documents (risk appetite,
    delegated authority matrices, ESG policies) — none of which are public.
    Two workable paths: (a) a real public corpus drawn from PRA, EIOPA,
    Lloyd's, and reinsurer ESG disclosures, framed as adjacent to a real
    internal copilot; (b) a fully synthetic corpus we generate and are
    transparent about. Real-public is harder to dismiss but introduces
    PDF-extraction risk on day 1.
  - Resolves into: a D-entry naming the chosen corpus and the day-1
    fallback (per the Day 1 corpus-risk plan).

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
  - Resolves into: a framing choice in the README (not a D-entry) once
    the answer is known.