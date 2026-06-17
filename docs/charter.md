# Charter

Why **Cedant** (`underwriting-copilot`) exists, what success looks like, and —
just as important — what is explicitly *out* of scope. Short, and it should
change rarely. Its job is to settle "should we even be doing this?" by
pointing at agreed scope.

## Mission

Local-first RAG copilot for reinsurance underwriting — hybrid retrieval, cited
answers, and a real evaluation harness. Built as a public portfolio artefact
to demonstrate Lead-level generative-AI judgement in a regulated-industry
context.

## In scope

- Ingestion of public regulatory and policy documents (PRA supervisory
  statements, EIOPA guidelines, Lloyd's market bulletins, public reinsurer
  ESG disclosures).
- Structured metadata extraction at ingest with schema validation.
- Semantic chunking that preserves section / subsection hierarchy.
- Hybrid retrieval (dense embeddings + BM25) with cross-encoder reranking.
- Answer generation grounded in retrieved context, with explicit citations
  and an enforced refusal path when evidence is insufficient.
- An evaluation harness with a hand-curated benchmark set measuring
  retrieval metrics (Recall@K, MRR), generation metrics (faithfulness,
  citation accuracy), and refusal correctness.
- Design documents for governance (RBAC, audit trail) and security (prompt
  injection defences), with minimal stub implementations where the design
  alone is not credible.
- A polished README that leads with the local-first positioning and a
  reproducible install / run path.

## Out of scope

- **Full RBAC implementation.** RBAC is *designed* in `governance.md` with a
  minimal SQLite stub; production-grade enforcement is not built.
- **The "Underwriting Decision Pack" stretch goal.** Mentioned in
  `backlog.md` with a structural sketch, not implemented.
- **Confidence scoring beyond a simple formula.** One paragraph in
  `evaluation.md` explains the four inputs and the chosen weights; no
  learned calibration.
- **Any UI beyond a CLI.** A minimal Gradio surface may be added if Day 5
  has slack; not required.
- **Use of any real reinsurer's internal documents.** The corpus is
  exclusively public.

## What success looks like

- The repository is a credible public artefact for a Lead generative-AI
  interview: a non-technical interviewer can read the README in four
  minutes and understand what was built and why; a technical interviewer
  can browse the docs and find that every Lead-level question the spec
  raises (hallucination, retrieval quality, RBAC, audit, prompt injection,
  evaluation) has a visible position.
- The system runs end-to-end on a single workstation with no external API
  calls, ingesting the chosen corpus and either answering with citations
  or refusing when evidence is thin.
- The evaluation harness produces a numbers table in `evaluation.md` with
  at least Recall@K, MRR, citation accuracy, and refusal precision /
  recall over a hand-curated benchmark of 40+ questions.
- Documentation is complete enough that a reader can reconstruct *what*
  was built, *why* the major choices were made, and *what was deliberately
  left undone* — without asking a follow-up.

## Budget

Five working days of development plus a documentation-and-polish pass on
day five. Anything that does not fit this budget is either dropped from
scope or moved to `backlog.md` with a one-line note on why.