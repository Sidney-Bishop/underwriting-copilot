# Cedant — Governance

**Project:** `underwriting-copilot` — RAG-based reinsurance underwriting Q&A
**Last updated:** 2026-06-18 (Day 4 of 5)
**Status doc:** overwrites freely; supersedes any earlier version

This document records the governance posture for v1 of the artefact: who
decided what, how those decisions are auditable, what contracts the
system commits to with its users, and what's deferred for production
hardening. It's written for an engineering reviewer who wants to assess
whether the system has been built with appropriate operational
discipline rather than just appropriate code quality.

## Purpose and scope

Cedant is a research-grade RAG system that answers natural-language
questions about a fixed corpus of regulatory and corporate documents
(PRA SS1/21, SS3/19, SS5/25; EIOPA System of Governance; Munich Re
Sustainability 2023; Swiss Re Sustainability 2024). It returns natural-
language answers with inline citations to specific document chunks. It
refuses, with a fixed phrase, when the corpus does not contain enough
information to answer.

**In scope (v1):**

- Cited natural-language Q&A over the 6-document, 461-chunk corpus.
- Local-only execution: all models served via oMLX on Apple Silicon;
  no calls to third-party APIs at any point in the pipeline.
- Deterministic output for the same query (temperature=0).
- Two model defaults swept via `eval.runner` and resolved per D014/D015.

**Out of scope (v1):**

- Automated underwriting decisions. The system never acts on its
  answers; it presents cited content for a human underwriter to read,
  follow citations into source documents, and act on themselves.
- Authentication, authorization, or multi-tenant isolation. v1 assumes
  one local operator on one machine.
- Live document ingestion. The corpus is built once and indexed; new
  documents would require a corpus rebuild (see "Data lineage" below).
- Customer PII or any client data. The corpus contains only publicly
  published regulatory and sustainability documents.
- Cross-corpus synthesis at production confidence. The eval (n=2 on
  cross-document questions) suggests the system is suggestive at best
  on this workload; v1 deployments should not be relied on for
  cross-document synthesis as a primary use case.

## System inventory

The deployed system has four versioned components, all pinned via
explicit commits in this repository:

- **Corpus index** at `scratch/qdrant/` and `corpus/bm25_vocab.json` —
  built once on Day 1 from the 6 source PDFs. Re-buildable via the
  ingestion pipeline; not part of the git tree (gitignored under
  `scratch/`) but the build steps are.
- **Retriever** (`src/underwriting_copilot/retrieve.py`) — hybrid
  BGE-M3 dense (via `mlx-embeddings`, CLS-pooled per D010) + BM25
  sparse (Porter-stemmed vocabulary, ~4810 terms), fused via reciprocal
  rank fusion (k=60, candidates_per_channel=50 per current defaults).
- **AnswerGenerator** (`src/underwriting_copilot/answer.py`) — LLM
  call orchestrator. Model resolved at construction time with explicit
  > env-var > default precedence. Default is `gemma-4-31B-it-MLX-6bit`
  per D015; overridable via `UNDERWRITING_COPILOT_MODEL`.
- **System prompt** — v2 per D014/D015, frozen in `answer.py`'s
  `SYSTEM_PROMPT` constant. Historical v1 preserved in `eval/prompts.py`
  for D014 replay.

All four are version-controlled and changes flow through commits with
heredoc messages documenting rationale.

## Decision discipline

The repository enforces a strict documentation pattern across three
files:

- **`docs/decisions.md`** is append-only. New decisions get
  `D<NN>` IDs and never delete or rewrite earlier entries. Open
  questions get `Q<NN>` IDs and their statuses are amended in-place via
  new appended status notes, never by editing the original entry.
- **`docs/journal.md`** is append-only narrative. Each working session
  appends an entry covering what happened, what was tried, what was
  found, and what remains open. The session-by-session view of the
  project's reasoning trail.
- **State docs** (`status.md`, this file, `architecture.md` if added)
  overwrite freely. They reflect the current state, not the history.

Append-only discipline is verified before each commit via
`git diff <file> | grep "^-[^-]"`; the output should be empty (no lines
removed from prior content). This catches accidental edits to historical
records.

As of Day 4, the project has 39 commits, 15 decisions (D001-D015), and
13 numbered open questions (Q1-Q13, with Q8-Q12 resolved or closed).

## Output contracts

The system makes three contractual commitments to its users, all
testable and tested:

- **Citation contract.** Every factual claim in an answer must be
  followed by an inline citation in `[chunk_id]` format. Citations are
  validated against the retrieved context: any citation whose
  identifier is not in the retrieved chunks is flagged as a hallucinated
  citation (the `hallucinated_citations` field on `AnswerResult`).
  Hallucinated citations are the main eval-time signal of LLM
  confabulation. Day 3 D014 sweep showed Gemma 4 31B IT × v2 produced 0
  hallucinations across the full 80 answerable cells; Qwen3.6 35B-A3B
  × v2 produced 3.
- **Refusal contract.** When retrieval surfaces no relevant chunks
  (pre-LLM refusal) or the LLM determines the retrieved chunks don't
  contain the answer, the system returns the exact phrase
  "I cannot answer this from the provided sources." The detector is
  case-sensitive and rejects partial refusals (where the model both
  refuses and answers). Day 3 D014 sweep showed both models, both
  prompts, all 14 refusal-category questions: 56/56 correct.
- **Determinism contract.** Same query, same corpus, same model, same
  prompt produces the same answer at temperature=0. The eval harness
  relies on this for reproducibility; the report.md generated from
  raw.jsonl always produces identical aggregates.

## Known limitations

Documented honestly because hidden limitations are worse than visible
ones in operational contexts.

- **Retrieval miss rate 11.5%** on the D014 benchmark (3 of 26
  answerable questions). Root cause identified per Q12: query/chunk
  language asymmetry on single-vector CLS-pooled dense embeddings.
  Affects both models equally; remediation paths (LLM query expansion,
  cross-encoder reranker, BGE-M3 multi-vector via Q7) deferred to v2
  per Q13.
- **Cross-document synthesis weakness** on N=2 questions. Gemma scored
  0.417 vs Qwen 0.000 — suggestive of an architectural difference but
  underpowered evidence. Production deployments relying on cross-
  document synthesis as a primary use case should not be made on this
  data.
- **Corpus-bound knowledge only.** The system has no fallback to LLM
  training data — by design — and will refuse out-of-corpus questions
  even when the underlying models likely know the answer. This is a
  feature for regulatory contexts where the operator needs to know
  whether an answer is grounded in the indexed sources; it is a
  limitation for general-purpose research.
- **No real-time updates.** Corpus rebuilds are manual. Documents
  superseded after the corpus build (e.g. PRA SS3/19 superseded by
  SS5/25 — see D012) are handled via the `superseded_by` metadata field
  and the `exclude_superseded=True` retrieval filter, but only for
  supersessions known at build time.
- **Single-operator local deployment only.** No authentication,
  authorization, or audit logging beyond git's commit trail. Multi-user
  production would require all three.

## Human oversight model

Cedant is a research assistant, not a decision-maker. The intended
workflow:

1. Underwriter poses a question relevant to their case.
2. System returns a cited answer or a refusal.
3. Underwriter reads the answer **and follows the citations to the
   original source documents** to verify context, scope, and
   applicability.
4. Underwriter makes the underwriting decision, on the strength of the
   sources they have now read directly, not on the strength of Cedant's
   summary.

This is encoded structurally: every claim is cited, citations are
verifiable against retrievable chunk text, and the refusal contract
exists specifically so the system tells the operator when it can't
answer rather than guessing. The chain of accountability runs from the
underwriter through the source documents; Cedant is a research tool in
that chain, not an authority.

## Evaluation and monitoring

The D014 eval is a snapshot. See `docs/evaluation.md` for methodology
and `eval/results/2026-06-18T12-16-35Z/report.md` for the headline data.
For a production deployment, the eval would become:

- **Rolling re-evals** whenever any of the four versioned components
  changes (model, prompt, retriever config, corpus). Currently the
  harness supports this — `uv run python -m eval.runner` takes 23.7
  minutes against the 2x2 sweep.
- **Live monitoring** of citation_recall and hallucination rates on
  real user queries. Out of scope for v1.
- **Periodic gold-set extensions.** The 40-question benchmark is small;
  drift detection and edge-case coverage would benefit from a benchmark
  closer to 200-500 questions.

## What ships, what's deferred

v1 of the artefact (this repository) ships with:

- The complete retrieve → answer → cite pipeline on 6 real documents.
- The D014 eval harness reproducible via `eval.runner` + `eval.report`.
- 15 decisions and a complete journal trail covering the 5-day arc.
- A documented retraction of the Day 2 family-axis finding on the basis
  of Day 3 follow-up data.
- All 158+ unit tests green.

Deferred to v2 (Q13 + Q10 follow-on + post-interview hardening):

- Retrieval remediation for the 11.5% miss rate (query expansion /
  reranker / multi-vector).
- Authentication, authorization, audit logging for multi-user
  deployment.
- Extended benchmark covering ≥200 questions across additional
  document classes.
- Optional GEPA / DSPy systematic prompt optimization on Qwen.
- Live corpus update pipeline (ingest new SS/Sustainability documents
  without full rebuild).

Anything labeled "v2" or "deferred" in this document corresponds to an
open question in `decisions.md` with the same labels; v2 work would
start by triaging that list.
