# PROJECT_BRIEF.md

**Orientation document for a fresh Claude instance.** Read this first if
you have no prior context on Cedant / underwriting-copilot. After reading,
you should know what the project is, what it does, how it's organised,
what its current state is, and where to look for what.

**Written:** 2026-06-21 (initial draft) / **revised:** 2026-06-21 (v0.2)
**Authored by:** Claude Opus 4.7, mid-session, with Jason
**Status:** Living document. Append updates; do not edit history. If a
section becomes stale, write a new section below correcting it rather
than overwriting.

> *Project documentation thesis (from `docs/philosophy.md`):* **every
> piece of information lives in exactly one place whose job it obviously
> is.** This brief points at those places. It is the map, not the
> territory.

---

## 1. Project at a Glance

| | |
|---|---|
| **Codename** | Cedant |
| **Repo name** | `underwriting-copilot` |
| **GitHub** | `github.com/Sidney-Bishop/underwriting-copilot` (public, MIT) |
| **Published report** | `https://cedant.netlify.app` |
| **Author** | Jason (solo developer, Dublin) |
| **What it is** | A local-first RAG (Retrieval-Augmented Generation) copilot for reinsurance underwriting research |
| **Purpose** | A 5-day public-repo artefact built to preempt Lead-level technical questions in a generative-AI interview context. The documentation is *as much* the deliverable as the code. |
| **Started** | 2026-06-17 |
| **v1.0 published** | 2026-06-19 |
| **Current branch** | `v2.0-dev/q13-hyde-spike` (v2 development; main is at v1.0.1 patch level) |
| **Hardware** | M5 Max MacBook Pro, 128GB RAM, Python 3.14, uv for env mgmt |
| **Inference** | All local via oMLX serving on `127.0.0.1:8000`; OpenAI-compatible API surface |
| **Production model** | `gemma-4-31B-it-MLX-6bit` (D015) |
| **Test count** | 343 passing (as of 2026-06-21) |
| **Decisions logged** | D001-D015, with D016 pending |

---

## 2. Detailed Project Overview

### What Cedant does

Cedant answers natural-language questions about a fixed corpus of six
regulatory and corporate-sustainability PDFs (PRA SS1/21 operational
resilience, PRA SS3/19 [superseded], PRA SS5/25 climate, EIOPA System
of Governance, Munich Re Sustainability 2023, Swiss Re Sustainability
2024) with cited answers, structurally validated. The corpus is 461
chunks after Docling parse + chunking; the indexed corpus sits in a
540KB Qdrant directory at `scratch/qdrant/`.

### The three contracts (per `docs/governance.md`)

The system makes three contractual commitments to its users, all
testable and tested:

1. **Citation contract.** Every factual claim in an answer must be
   followed by an inline citation in `[chunk_id]` format. Citations
   are validated against the retrieved context: any citation whose
   identifier is not in the retrieved chunks is flagged as a
   *hallucinated citation* (the `hallucinated_citations` field on
   `AnswerResult`). Hallucinated citations are surfaced in the UI as
   red `[?]` badges; reviewers cannot mistake them for real citations.
   This is the load-bearing safety property of the system.

2. **Refusal contract.** When retrieval surfaces no relevant chunks,
   or the LLM determines retrieved chunks don't contain the answer,
   the system returns *exactly* the phrase `"I cannot answer this
   from the provided sources."` — strict-string matched,
   case-sensitive, partial refusals (refusal phrase + smuggled answer)
   rejected as failures.

3. **Determinism contract.** Same query, same corpus, same model, same
   prompt produces the same answer at temperature=0. The eval harness
   relies on this for reproducibility; `report.md` regenerated from
   `raw.jsonl` always produces identical aggregates.

A fresh Claude reading this should treat all three as load-bearing.
Tests verify each; the contracts are enforced in code, not relied on
as prompt instructions the LLM is asked to honour.

### Human oversight model (per `docs/governance.md`)

Cedant is **a research assistant, not a decision-maker.** The intended
workflow is structurally encoded:

1. Underwriter poses a question relevant to their case.
2. System returns a cited answer or a refusal.
3. Underwriter reads the answer **and follows the citations to the
   original source documents** to verify context, scope,
   applicability.
4. Underwriter makes the underwriting decision *on the strength of the
   sources they have now read directly*, not on the strength of
   Cedant's summary.

The chain of accountability runs underwriter → source documents.
Cedant is a research tool in that chain, not an authority. Citations
exist so the operator can verify; the refusal contract exists so the
operator is told when the system cannot answer rather than guessing.

### What Cedant is *not*

- **Not a production system.** Documentation explicitly says no
  underwriter should rely on it without verification.
- **Not a cross-document synthesis tool.** The `cross_document`
  benchmark subset scores ~0.23 mean citation recall on the production
  default — the system's clearest weakness. `docs/governance.md`
  commits to this limitation explicitly: cross-document synthesis is
  *not* a supported primary use case at v1.
- **Not multi-user.** No auth, no concurrency, no audit log. Single
  user, single process. Streamlit UI for one analyst at a time.

### Why this project exists (the constraint that shapes everything)

Cedant is a public-repo interview deliverable for a Lead-level role
at a reinsurer. The budget was 5 working days. Per
`docs/charter.md`:

> *"What success looks like: the repository is a credible public
> artefact for a Lead generative-AI interview: a non-technical
> interviewer can read the README in four minutes and understand what
> was built and why; a technical interviewer can browse the docs and
> find that every Lead-level question the spec raises (hallucination,
> retrieval quality, RBAC, audit, prompt injection, evaluation) has a
> visible position."*

The constraint shapes everything:

- **Documentation is heavy** because the artefact is meant to
  demonstrate engineering judgement under budget, and documentation
  is the non-code half of the evidence (per charter). There are
  ~5,100 lines across 11 files in `docs/`.
- **Pre-registered falsification criteria** are a recurring pattern —
  written *before* evidence, recorded in `docs/decisions.md` or
  `docs/open_questions.md`. The discipline is the deliverable as
  much as any result.
- **Retractions are appended, not edited.** Two claims have been
  formally retracted on the record in `docs/journal.md` (the Day-2
  family-axis claim and the N=40 within-document parity claim). A
  third is Q14's falsification (2026-06-20). Append-only history is
  the project's primary accountability mechanism.

### Charter intent vs v1 reality

`docs/charter.md` is the project's scope-settling document. A reader
should note a few drifts between charter and what actually shipped:

- Charter lists "hybrid retrieval (dense + BM25) **with cross-encoder
  reranking**" — but reranking was deferred to v2 (Q7).
- Charter lists "any UI beyond a CLI" as *out of scope*, with "a
  minimal Gradio surface may be added if Day 5 has slack" — Streamlit
  replaced Gradio and shipped properly.
- Charter is intentionally aspirational; what shipped is the v1
  reality the eval measures. Both are honest; the drift is in the
  charter's direction (slightly more shipped than promised).

---

## 3. Architecture Overview

### The pipeline (6 stages, per `docs/architecture.md` plus journal updates)

```
USER QUESTION
    │
    ▼
[Hybrid Retrieval]    Dense (BGE-M3) + Sparse (BM25) via RRF (k=60) in Qdrant.
                      Top-k = 5 by default. Optional HyDE pre-pass (v2 branch).
                      Filters: exclude_superseded=True (default), optional
                      issuer_type / jurisdiction.
    │
    ▼
[Prompt Assembly]     System prompt (frozen v2 per D015) + retrieved SOURCES
                      block + user QUESTION.
    │
    ▼
[LLM Call]            Local oMLX at 127.0.0.1:8000, OpenAI-compatible chat
                      completions. Temperature hard-pinned to 0.0 in
                      _build_payload. Default model gemma-4-31B-it-MLX-6bit
                      (D015), overridable via UNDERWRITING_COPILOT_MODEL env
                      var.
    │
    ▼
[Citation Validator]  Regex-extract [chunk_id]; partition into valid /
                      hallucinated against the retrieved set. Strict regex
                      `\[([A-Za-z0-9_\-]+)\]` — won't false-match natural
                      bracketed prose like "[Article 12]".
    │
    ▼
[Refusal Detector]    Exact-phrase strict match. Partial refusals rejected.
    │
    ▼
AnswerResult          Structured object: answer text, citations[],
                      hallucinated[], used_chunks[], refused, elapsed.
```

Each stage is independently testable and lives in its own module. The
two contracts (citation, refusal) are enforced *after* the LLM call —
they are not relied on as prompt instructions. If the LLM ignores the
prompt, the contract detectors still fire correctly.

### Ingestion & chunking (Day-1 work, per `docs/architecture.md`)

The ingestion pipeline takes PDFs → Docling (with OCR disabled per
D004) → cleanup → chunking → indexed corpus. Cleanup applies three
rules in order:

1. **Universal**: strip `<!-- image -->` placeholders (398 instances
   corpus-wide).
2. **Structural**: dedupe markdown table blocks appearing ≥3× within
   one document (Munich Re TOC handling).
3. **Document-specific**: EIOPA `glyph[.notdef]` → hyphen
   (font-encoding pathology); PRA SS1/21 inline `Superseded` watermark
   + supersession link stripping.

Chunking is **two-pass** per D008:

1. **Emission pass.** Parse markdown into `Segment`s at heading
   boundaries. For each segment: if `token_count > soft_cap (1500)`,
   split via paragraph-fallback (numbered-paragraph anchors →
   blank-line paragraphs → greedy word split → coalesce); otherwise
   emit single chunk.
2. **Floor-merge pass.** Iteratively merge sub-floor chunks (< 100
   tokens) into neighbours. Prefer backward merge; skip if either
   target would push receiver over cap.

Output: 461 chunks across 6 documents, all between 100 and 1500
tokens.

**Critical detail to know:** "token counts are word splits, not real
tokenizer tokens." The soft_cap=1500 and soft_floor=100 thresholds
are in this unit. Swapping in a real tokenizer would silently change
what the thresholds mean — D008 should be revisited if that's done.

### Retrieval architecture

- **Dense channel (D009 + D010):** BGE-M3 1024-dim embeddings via
  `mlx-embeddings` (Apple Silicon native). CLS-pooled and
  L2-normalised — *not* `text_embeds` mean-pooled. D010 was prompted
  by a Day-2 retrieval failure on a query that should have hit; the
  fix was a one-line change but the diagnostic that found it is
  recorded.
- **Sparse channel (D011):** BM25 over ~4,810-term Porter-stemmed
  vocabulary at `corpus/bm25_vocab.json`. Word-level tokenisation;
  minimal stopwords (domain-specific near-stopwords like "shall" /
  "may" / "should" preserved). `k1=1.5`, `b=0.75`.
- **Fusion:** Reciprocal Rank Fusion (RRF) with k=60 (Cormack et al.
  default). Up to 50 candidates per channel before fusion.
- **Indexing (D012):** Both channels in a single Qdrant collection at
  `scratch/qdrant/`. Self-describing payload (chunk text + metadata).
  540KB total — a fresh clone reproduces v1.0 numbers from git
  alone, no external service.

### Key architectural decisions (D-series)

The full set lives in `docs/decisions.md` (1,159 lines, 15 active
decisions D001-D015 with D016 pending). **Read decisions.md directly
for any "why was X chosen?" question.** Grep for the relevant
D-number rather than reading sequentially.

Decision titles by D-number, as inferred from the journal and
decisions.md TOC. **Note:** The grep that produced this brief only
matched D009 onward (D001-D008 use a different header level in
decisions.md). A future Claude should grep `^### D` or read the file
sequentially for full set.

- **D001-D008** (inferred from journal references): project name
  ("Cedant" + "underwriting-copilot"), corpus selection (D003:
  hybrid public + synthetic), Docling with OCR disabled (D004),
  `scripts/probes/` + `scratch/` convention (D005), Pydantic metadata
  schema (D006), chunking (D008). Read decisions.md for canonical
  versions.
- **D009** — Hybrid retrieval: BGE-M3 dense + BM25 sparse via Qdrant
  native sparse vectors.
- **D010** — BGE-M3 dense uses CLS-pooled + L2-normalised, *not*
  `text_embeds` mean-pooled.
- **D011** — BM25 design: word-level + Porter stemming + minimal
  stopwords + corpus-wide vocabulary.
- **D012** — Index module: full-text payload, scratch-located Qdrant,
  one-shot rebuild.
- **D013** — `answer.py` contracts: citation format, refusal phrase,
  model + endpoint configurability.
- **D014** — Day-3 eval harness: plain Python, sweep over {models} ×
  {prompts}.
- **D015** — Production model default: `gemma-4-31B-it-MLX-6bit`.
  Selected over Qwen3.6-35B-A3B-4bit on zero hallucinated citations
  across the N=70 sweep (Qwen had 7 at v2; 23 at v1). Latency cost
  accepted (~22s vs ~3s for Qwen).
- **D016 (open)** — Not yet written. The pragmatic-split decision on
  `httpx` (used in both `answer.py` and the new `query_rewriter.py`)
  vs the OpenAI SDK migration deferred to v2.0 release.

### The prompt v1 → v2 story (worth knowing)

The system prompt evolved from v1 to v2 between Day 2 and Day 3. v1
used the literal token `[chunk_id]` as both placeholder name and
emit format. Qwen drifted to placeholders like `[chunk_id_1]`
instead of substituting actual identifiers. v2 disambiguates by
using the actual chunk-id format inside a worked example. This was
the trigger for the **family-axis citation discipline retraction**
— Day 2 framed the Gemma-vs-Qwen gap as a model-family property;
D014's evidence showed most of it was prompt-fit. v2 closed the gap
on Qwen by ~27pp (the N=40 measurement) without changing Gemma. Both
prompt versions are preserved (v1 in `eval/prompts.py` for D014
replay; v2 in `answer.py`'s `SYSTEM_PROMPT` constant).

### Code structure

```
src/underwriting_copilot/
  ├── answer.py          (19KB)  Answer generation + citation/refusal contracts
  ├── retrieve.py        (12.6KB) Hybrid retrieval, RRF, HyDE plumbing (v2)
  ├── query_rewriter.py  (7.2KB)  v2 HyDE rewriter (new on v2 branch)
  ├── index.py           (12.7KB) One-shot Qdrant build from chunks
  ├── chunking.py        (12.5KB) Document → chunks (two-pass, D008)
  ├── embed.py           (8.9KB)  BGE-M3 via mlx-embeddings
  ├── bm25.py            (9.2KB)  Sparse channel
  ├── cleanup.py         (7.2KB)  Pre-pass text cleaning (three rules)
  └── metadata.py        (2KB)    Pydantic schema (D006)

tests/                            14 test files, 343 passing as of 2026-06-21
eval/                             D014 eval harness
  ├── benchmark.toml              70 hand-crafted questions with gold tags
  ├── runner.py                   Sweep over {models} × {prompts}
  ├── scorer.py                   citation/retrieval recall + precision + F1
  ├── rescore.py                  (NEW 2026-06-20) Recompute metrics post-Q15
  ├── compare.py                  Multi-run comparison tooling
  └── results/<timestamp>/        manifest.toml + raw.jsonl + run_meta.json
                                  + raw_rescored.jsonl (post-Q15)

app.py                  Streamlit analyst UI (33KB)
publications/           Quarto report → cedant.netlify.app
```

---

## 4. Documentation Map

This is the **most important section** for a future Claude. Use this
to decide which document to read for a given task.

### The State / History axis (from `docs/philosophy.md`)

Every doc in this project has a *kind* and that kind dictates how
it's used. Internalise this distinction before editing anything:

- **State** describes what is true *now*. Updating it *overwrites*
  the past.
- **History** describes how things *came to be*. It is *append-only*;
  nothing is ever overwritten.

History splits further:

- **Decision history** records *destinations* — the settled choices.
- **Session history** records the *road* — what was tried, what
  broke, the dead ends, the wrong conclusions corrected.

A trap to avoid: "having good decision history can disguise the
total absence of session history." Both axes matter. Cedant has
both.

### Reading priority by task

| Your task | Read these (in order) |
|---|---|
| **Get oriented to the project** | This document, then `docs/charter.md` |
| **Understand "why X was decided"** | `docs/decisions.md` (1,159 lines — grep for the relevant D-number) |
| **Understand recent state / changes** | `docs/journal.md` (2,121 lines — tail-first; entries are append-only and dated) |
| **Understand "what's left open"** | `docs/open_questions.md` (Q-numbered questions; some resolved into D-entries, others deferred) |
| **Understand documentation discipline** | `docs/philosophy.md` (340 lines — the project's documentation thesis; explains why files are split the way they are) |
| **Understand operational commitments** | `docs/governance.md` |
| **Understand security/data residency** | `docs/security.md` |
| **Understand the eval methodology** | `docs/evaluation.md` + `eval/benchmark.toml` |
| **Find the current backlog** | `docs/backlog.md` (kept short — most items live in `open_questions.md` or `journal.md`) |
| **Get current project status** | `docs/status.md` then journal tail |
| **Find current interview prep** | `interview.md` at repo root (gitignored — local only) |
| **Read the published technical report** | `publications/underwriting_copilot/sections/*.qmd` or rendered HTML at https://cedant.netlify.app |

### Document inventory with full descriptions

#### Core orientation (read first)

- **`docs/charter.md`** (3.4KB / 69 lines — **State, rarely
  changes**) Mission, in-scope / out-of-scope, success criteria
  framed as interview-credibility signals, the 5-day budget. Per
  `docs/philosophy.md`: "Short, and it should change rarely; if it
  changes often, the project lacks direction." **Read this for:
  project intent and scope boundaries.** Note charter is aspirational
  — see Section 2 above for charter-vs-v1 drifts.

- **`docs/philosophy.md`** (16.7KB / 340 lines — **conceptual; rarely
  changes**) The project's documentation thesis. State vs history,
  decision history vs session history, supersede-don't-edit,
  mechanical discipline practices, the empty-journal failure mode,
  and the "where does this sentence go?" decision tree. **Read this
  for: understanding *how* Jason organises documentation, why the
  doc set is split the way it is, and the mechanical discipline that
  prevents documentation disasters.** Probably essential reading for
  a fresh Claude expected to *write* into the project's docs (and
  not just read them).

- **`docs/architecture.md`** (6KB / 126 lines — **State**) System
  architecture overview. **⚠ STALE WARNING:** this file is dated
  Day 1 (2026-06-17) and only covers the ingestion, cleanup,
  chunking, and metadata layers. It explicitly says "embeddings,
  vector store, retrieval, reranking, answer generation, eval
  harness: not yet built." That language is from Day 1 — all of
  those layers were subsequently built. A fresh Claude reading
  architecture.md cold will form an outdated picture. For the
  current pipeline, read this brief's Section 3 above and
  `docs/decisions.md` D009-D015. The architecture file should
  eventually be refreshed to reflect post-v1 reality.

- **`docs/governance.md`** (10.3KB / 215 lines — **State**) What the
  system commits to (the three contracts: citation, refusal,
  determinism), the human oversight model, known limitations,
  deferred items. **⚠ NUMBERS PARTIALLY STALE:** governance.md was
  last updated 2026-06-18 (Day 4) and references the N=40 D014
  sweep. The headline contracts and oversight model are still
  current; the specific metric numbers (e.g. "11.5% retrieval miss
  rate") have been superseded by the N=70 extension which raised
  the rate to 25.0%. The N=70 numbers are in the published Quarto
  report and `docs/journal.md`. **Read this for: contracts,
  limitations, and deferred items at the v1 milestone.**

#### Decision and history (read selectively)

- **`docs/decisions.md`** (73.6KB / 1,159 lines — **Decision history,
  supersede-don't-edit**) All numbered design decisions D001-D015
  (D016 pending). Each decision documents context, alternatives
  considered, choice made, rationale, trade-offs/risks, when to
  revisit. **Read this for: any "why was X chosen?" question.**
  Grep for the relevant D-number rather than reading sequentially.
  *Discipline pattern:* when a decision is replaced, the old
  D-entry is marked superseded and *kept intact*; new D-entry
  references it. This is intentional — the path of decisions is
  itself information.

- **`docs/journal.md`** (150KB / 2,121 lines — **Session history,
  append-only**) The project's living memory. Dated entries — one
  per working session. Records the *road*, not just the destination.
  Includes the family-axis retraction (Day 2 → N=40 retracted), the
  N=40 within-document parity retraction (N=40 → N=70 weakened),
  Q14 falsification (2026-06-20), Q15 outcome (2026-06-20), Section
  6 amendment decline (2026-06-21). **Read this for: current state,
  recent decisions, and the texture of what's been tried and
  learned.** Tail-first; newest entry at the bottom. *Append-only
  discipline:* verify with `git diff <file> | grep "^-[^-]"` before
  committing (should be empty).

- **`docs/open_questions.md`** (13.9KB / 294 lines — **State**)
  Q-numbered open questions. Lifecycle: opened → partially answered
  → resolved (either into a D-decision or closed inline). Includes
  Q11 (model selection, resolved as D015), Q12 (retrieval miss
  diagnostic), Q13 (retrieval remediation options — HyDE is one of
  three), Q14 (HyDE falsification, falsified 2026-06-20), Q15
  (gold-labelling review, applied 2026-06-20). **Read this for: any
  open research question or pending design choice.**

#### Operational and reference

- **`docs/evaluation.md`** (15KB / 319 lines — **State**) Eval
  methodology, metric definitions, benchmark structure, the
  falsification-criterion framing. Crucially, evaluation.md frames
  the D014 sweep explicitly as *designed to falsify* the Day-2
  family-axis claim — the sweep was capable of forcing retraction
  by pre-stated criteria, and did. The "Claims supported / Claims
  NOT supported" structure in evaluation.md is the same pattern
  that recurs in journal.md retraction entries. **⚠ NUMBERS
  PARTIALLY STALE:** evaluation.md is also Day-4 / N=40 era; the
  N=70 numbers are current. **Read this for: methodology framing
  and metric definitions.**

- **`docs/security.md`** (10.8KB / 202 lines — **State**) Data
  residency, security posture, what an underwriter deployment would
  require beyond v1. Not yet directly read by current Claude —
  inferred from journal references and governance carve-outs.
  **Read this for: any security or deployment-extension question.**

- **`docs/status.md`** (9.4KB / 203 lines — **State, overwrite
  freely**) Periodically-updated point-in-time status. Less granular
  than journal; more curated. Per philosophy: "deliberately
  ephemeral — you overwrite it constantly and never mourn the old
  version." Not yet directly read by current Claude. **Read this
  for: a quick "where is the project today" without journal's level
  of detail.**

- **`docs/backlog.md`** (2.6KB / 59 lines — **State-ish, fluid**)
  Short list of pending items. Cross-off-don't-delete pattern (small
  amount of session history retained). Most items have richer
  detail in `open_questions.md` or `journal.md`. **Read this for:
  a fast appetite-check on outstanding work.**

#### Top-level

- **`AGENTS.md`** (2.2KB) — Agents convention file. Not yet read
  directly. Likely conventions or working-style notes for AI
  collaborators.

- **`README.md`** (17KB — **State, overwrite freely**) Public-facing
  project README. Aimed at a reviewer/reader visiting GitHub. The
  primary "front door" per philosophy.md. **Read this for: the
  external-facing pitch and quickstart.**

- **`interview.md`** (26KB, gitignored — local only) Q&A prep
  document Jason maintains for interview rehearsal. Typical
  questions, answers with follow-ups, "what to avoid" notes. **Read
  this for: what stories Jason wants to tell about the project and
  how he wants to tell them.**

#### Published report (Quarto)

`publications/underwriting_copilot/sections/`:

| File | What it covers |
|---|---|
| `01_executive_summary.qmd` | Key results, the problem, what was built, what this is not |
| `02_introduction.qmd` | Problem domain, what citation and refusal mean, why it's hard |
| `03_dataset.qmd` | Corpus, Docling, cleanup, chunking, metadata, indexing |
| `04_methodology.qmd` | The 6-stage pipeline in detail, hybrid retrieval, contracts |
| `05_experiments.qmd` | D014 eval, family-axis retraction, Q12 retrieval-miss investigation, D015 |
| `06_results.qmd` | N=70 sweep results, subset analysis, retrieval miss list, q058 anomaly |
| `07_pipeline.qmd` | End-to-end inference walkthrough, CLI, Streamlit UI, reproduction-from-scratch |
| `08_limitations.qmd` | System / eval / corpus limits, the two retracted claims, future work |
| `09_conclusions.qmd` | Headline conclusions, methodology discipline, what's next |
| `metrics_explainer.qmd` | Glossary of metrics and terms |
| `appendix_concepts.qmd` | Concept primers (RAG, hybrid retrieval, citation contract, etc.) |

**Important constraint:** the published report at v1.0 reflects the
benchmark *as it was on 2026-06-19*. The Q15 corrections (2026-06-20)
are documented in the repo (`docs/journal.md`, `eval/rescore.py`,
`eval/benchmark.toml`'s inline comments, rescored result files) but
were *deliberately not* back-ported into the v1.0 published report —
see Section 7 below.

---

## 5. Current State (2026-06-21)

### Branches

- **`main`** — at v1.0.1 (small patches). v1.0 released 2026-06-19.
- **`v2.0-dev/q13-hyde-spike`** — currently active. Contains HyDE
  spike (Q14), Q15 benchmark correction, Section 6 decline. HEAD at
  `e19ded2` (2026-06-21, "Section 6 amendment decision — declined").

### Major recent decisions and events

| Date | Event |
|---|---|
| 2026-06-17 | Project scaffolded. Charter, corpus selection (D003), Docling, probes convention (D005), metadata schema (D006). |
| 2026-06-18 | D014 eval harness; N=70 canonical sweep at `eval/results/2026-06-18T15-32-07Z/`. Published baseline: gemma_v2 cell at mean_citation_recall = 0.598, mean_retrieval_recall = 0.633. |
| 2026-06-19 | v1.0 report published to https://cedant.netlify.app. Streamlit UI shipped. Day closes at v1.0.1 patch level. |
| 2026-06-20 (AM) | v2 branch opened. Q13 Phase 1 baseline + Phase 1b text inspection. Q14 + Q15 opened. |
| 2026-06-20 (mid) | Phase 2a HyDE prompt probe — CONSTRAINED prompt wins 5/6 on mechanism-clear set. Phase 2b: `QueryRewriter` shipped + `use_hyde` flag threaded through `Retriever`. |
| 2026-06-20 (PM) | Phase 2c — full Q14 sweep. **Q14 falsifies at 3/5 strict recovery.** Aggregate +5.1pp retrieval recall, +5.5pp citation recall, 0 new hallucinations, 27% latency cost. |
| 2026-06-20 (eve) | Q15 chunk-text review on 8 candidates. Verdicts: STAND 2, WIDEN 4, REPLACE 1, AMBIGUOUS 1 (q046 deferred). Five benchmark changes applied. `eval/rescore.py` written. Baseline rescored: 0.598 → 0.621 on production-default. Phase 2c rescored: 0.653 → 0.703 on citation recall. Branch pushed to GitHub. `interview.md` drafted. |
| 2026-06-21 (AM) | Section 6 amendment of v1.0 report — **investigated, declined**. v1.0 stands as a snapshot of what was known on 2026-06-19. Backlog item closed. PROJECT_BRIEF.md authored (this doc). |

### What's in-flight / current focus

- **q046 question rewrite (Q15 follow-up)** — the AMBIGUOUS Q15 case.
  Investigation confirmed Swiss Re's 2024 sustainability report has
  *zero* chunks discussing scenario governance (keyword scan across
  all Swiss Re chunks returned nothing). Path B (replace G1 with a
  Swiss Re scenario-governance chunk) closed. Path A (rewrite
  question to ask about general underwriting alignment) is the only
  viable option. Not yet applied — paused on whether to generalise
  or reframe as one-sided.

### Open backlog (rough priority)

1. **q046 rewrite** — small, ~30 min when picked up.
2. **D016 write-up** — pragmatic-split decision (`httpx` in both
   modules, OpenAI SDK migration deferred to v2.0 release).
3. **`dense_rank` / `sparse_rank` exposure in `raw.jsonl`** —
   runner.py modification, ~30 min. Would have settled the
   sparse-interference question on q051 during Phase 2c.
4. **Partial HyDE shipping decision for v2.0** — deferred to v2.0
   release boundary. Aggregate gain is +5.1pp against v1.0 baseline
   or +7.8pp against Q15-corrected. Latency cost real (~27%).
5. **OpenAI SDK migration** at v2.0 release boundary.
6. **Embedding diagnostic** on original Finding 3 lexical-match cases
   — substantially closed; can be downgraded.

---

## 6. Working Conventions (How Jason Works)

These conventions appear consistently throughout the journal and
shape how a Claude should collaborate. Violating them creates
friction.

### The State / History axis is the bedrock

Repeated from Section 4 because it is *the* organising principle.
Before writing any documentation, ask: is this State (overwrite) or
History (append)? Within History: Decision (decisions.md) or Session
(journal.md)?

The "where does this sentence go?" decision tree from
`docs/philosophy.md`:

1. **Is this describing what's true right now?** → State doc (which
   one depends on whether it's orientation, architecture, status,
   scope, or an open question).
2. **Is this a deliberate choice someone will later question?** →
   `docs/decisions.md`.
3. **Is this something that happened — a step, a bug, a dead end, a
   correction?** → `docs/journal.md`.

Common mistakes the philosophy doc names:
- **Writing history into a state doc** ("this used to use X but now
  uses Y" in the README or architecture doc). Fix: the "now uses Y"
  stays in state; the "used to use X" goes to decisions.md (if
  choice) or journal.md (if just evolution).
- **Editing the journal or decisions to "fix" an old entry.** Never.
  If old entry was wrong, write a new entry correcting it.
- **Letting `status.md` accumulate dated entries.** That's a journal
  trying to be born — move the dated content out.

### Append-only mechanical discipline

For `docs/journal.md` and `docs/decisions.md`:

- **Before committing, verify the diff shape.** A doc edit meant to
  *add* content should show insertions far exceeding deletions. A
  large unexpected deletion count means you're about to overwrite or
  roll back. Use `git diff <file>` or `git diff --stat`.
- **Verify append-only with:** `git diff <file> | grep "^-[^-]"` — if
  output is empty, no lines were removed from prior content.
- **Confirm you're editing the current version, not a stale copy.**
  If the file was downloaded or exported, check size or line count
  against committed before editing on top of it.

This single discipline — verifying diff shape and append-only on long
docs — catches the most damaging documentation accident: silently
reverting a file to an older version by editing a stale copy.

### Strict one-thing-at-a-time

Terminal output is the signal to proceed. Don't queue multiple
actions or run multiple commands hoping one will work. Single
decision → single action → single terminal output → next decision.

### File handling

- **Never** ask Jason to `cat` a whole file. Use `head`, `tail`, `sed
  -n '<range>p'`, or `grep` with context.
- **File reviews use `open -a "TextEdit"`** — not terminal output.
- **File edits delivered as downloadable artefacts or terminal
  commands** — no manual paste tasks expected of Jason.
- **`scripts/probes/` is committed; `scratch/` is gitignored** (D005).
  Probes are part of the project's validation history.

### Pre-registered falsification

When running an experiment, state the falsification criterion *and*
the prediction beforehand, in the journal. The discipline is the
deliverable. Two retractions in the project's history (Day-2
family-axis claim, N=40 within-document parity claim) plus Q14's
falsification (2026-06-20) all turned on pre-registration that
preceded evidence. Changing criteria post-evidence is the failure
mode the project's whole epistemics are built to avoid.

### Honesty checks during reviews

If a rationale for "this should also count" starts forming, re-read
the *question* before validating the rationale. Q15's first reviewed
candidate (q013) had a slug pattern that suggested gold-labelling
tightness, but chunk-text reading revealed the retrieved
alternatives were about *investment* policy, not the underwriting
policy the question asks. Without the honesty check, the verdict
would have drifted toward widening; with it, the verdict was STAND.
This pattern recurs.

### Defer decisions requiring fresh judgement

Don't force end-of-day decisions; record them as deferred with the
criteria for picking them up later. The Section 6 amendment was
deferred at end-of-day on 2026-06-20 and declined on fresh review
2026-06-21 — both decisions are on the record.

### Tone preferences

- Dislikes: sycophancy, hedging, meta-commentary, options lists
  without a recommendation.
- Expects: pushback when Claude overclaims or runs ahead of where
  Jason is in execution. Direct disagreement is welcomed; obsequious
  agreement is not.
- When asked for advice: give it honestly, with reasoning, including
  the counter-case. Then make a recommendation.

### Workflow shape

- **Repeat the project context check after compactions.** If the
  conversation summary has been compacted, the first move is to
  reconfirm repo state: branch, HEAD vs origin, working tree, recent
  decisions. Don't assume the summary is complete.
- **Commit at phase boundaries.** Each commit message tells the story
  of one decision or one shipped piece of work. The git log is part
  of the project's narrative.
- **Tests stay green at every commit boundary.** 343 passing as of
  2026-06-21.

---

## 7. Important Constraints and "Things to Know"

### v1.0 published numbers are *intentionally* uncorrected

The v1.0 Quarto report at https://cedant.netlify.app uses pre-Q15
numbers throughout. `mean_citation_recall = 0.598` on the
production-default cell.

This is **intentional, not stale**. Decision dated 2026-06-21
(`docs/journal.md`):

> The v1.0 report stands as a snapshot of what was known on
> 2026-06-19. The Q15 correction is documented in yesterday's
> entries, in eval/rescore.py, in the rescored result files, and in
> the benchmark.toml inline comments. A reviewer who reads the
> repository has the complete picture; a reviewer who reads only the
> published report has the v1.0 conclusions as published. Both
> audiences are correctly served.

**Do not** "fix" Section 6 of the report without an explicit
decision to revisit this. The corrected numbers (0.621 baseline,
0.703 Phase 2c) are publishable but live in the journal and
benchmark comments, not in the report.

### Q14 is *not* retroactively unfalsified by Q15

Q15 verdicts WIDEN q051 and q056. Under widened gold, Phase 2c shows
partial recovery on both — 0.500 retrieval_recall each. This might
tempt a reader to say "well, Q14 actually passed."

**It did not.** The Q14 criterion was stated against gold tags as
they existed at the time of pre-registration. Changing gold tags to
make Q14 pass would be exactly the post-hoc rescue the project's
discipline is built to avoid. Q14's published outcome is 3/5 strict
recovery, falsified. Q15 is an independent benchmark correction. A
*future* Q14-style experiment against the corrected gold might yield
a different result; that experiment hasn't been run.

This is in the journal in plain text. A new Claude should not be
tempted to "improve" the framing.

### The interview is the context for everything

Cedant exists for an interview. Every design choice, every
retraction, every methodology section is implicitly answering "how
does this engineer think?" rather than "is the system
production-ready?". The philosophy is: don't oversell, don't hide
trade-offs, treat self-correction as a strength.

A future Claude collaborating with Jason should default to the same
posture. Don't try to make the project look better than it is. The
honesty is the asset.

### 7.5 Cross-project context (shared infrastructure)

Cedant shares the local oMLX serving stack at `127.0.0.1:8000` with
at least one other active project (`tst_llm`, Jason's local-LLM
benchmarking project). A few cross-project realities a fresh Claude
should know about:

**Shared hardware, different workload shape.** Cedant's workload is
**single-shot RAG synthesis** (one retrieve + one LLM call per
query). tst_llm exercises **multi-step agentic** workloads (multiple
tool-using rounds, sustained warm sessions). The shared
infrastructure is real, but the risk profile is not 1:1. Two kernel
panics occurred on 2026-06-20 and 2026-06-21 under tst_llm's
sustained-multi-step load on this M5 Max (signature `PMC0 Assert ID:
0x4c, rail:DCS` — SoC power-management). macOS Tahoe 26.5.1 was
installed 2026-06-22 as a candidate fix. Cedant's single-shot
pattern *may* not exercise the same hardware surface but uses the
same SoC and stack — risk is non-zero, not 1:1.

**New GLM models now available on the shared oMLX stack:**

- `GLM-4.7-Flash-6bit` (~20-25 GB resident, ~30B class) — added
  2026-06-21. Passes oMLX reasoning-parser cleanly; passes Q17-shape
  chat-template compatibility for tool-loop driving.
- `GLM-4.5-Air-6bit` (~75-80 GB resident, 106B-total / 12B-active MoE)
  — also added 2026-06-21. Same compatibility passes. Currently in
  "structurally-compatible but resource-marginal" category — stalled
  on 2026-06-21 with memory pressure at 115/128 GB during a
  multi-step agentic probe. Currently *deferred* from tst_llm work
  pending hardware-stability evidence.

**Which (if any) is a Cedant candidate by Cedant's own criteria?**

- **GLM-4.5-Air is the more interesting candidate for Cedant** —
  Air's 12B-active sits cleanly in the 7-14B sweet spot the project's
  stated criteria favour. Flash is ~30B class, less of a fit for
  Cedant's deployment priorities. Air being deferred from tst_llm
  doesn't directly carry over: Cedant's single-shot workload doesn't
  hit the multi-step memory pressure that stalled Air's tst_llm
  probe. A Day-3-style Cedant eval against Air on Cedant's own
  fixtures is the experiment that would clear it for either use
  case.
- **Flash is not necessarily disqualified** but isn't the brief's
  most natural fit on size.
- **Either candidate would need to clear D015's criterion (zero
  hallucinated citations across the answerable sweep, or close to it)
  to be considered as a Gemma replacement** — not just a recall
  number.

**Cross-project evidence on the fabrication-vs-recall trade-off:**
tst_llm's headless harness showed GLM-4.7-Flash scoring 75.0% recall
with 0 fabricated findings, while Qwen3.6-35B-A3B-4bit scored 87.5%
recall with 1 verified-wrong-about-the-code finding the rubric
doesn't flag. This *corroborates* D015's reasoning at the principle
level — recall and fabrication signal point different directions,
and headline recall alone doesn't capture citation-format discipline.
But the tst_llm finding is **N=1 fixture, N=1 run** with explicit
caveats throughout its journal. D015 stands on Cedant's own
multi-query structured comparison (the full N=70 sweep, ~80 cells).
The two findings agree at the principle level; they are not
independent confirmations at the same statistical weight.

**For tst_llm-side specifics** (the `claude -p` env block, the
hybrid-reasoning token-budget floor, the panic-file hygiene step,
the inlined `launch_claude.sh`): read `serving_local_models.md`
(refreshed 2026-06-22) and `docs/journal.md` entries on the tst_llm
side. These are not duplicated into Cedant.

**Session hygiene affecting Cedant work:** the panic-file check at
session start/end is recommended given the recent panics. Run
`ls /Library/Logs/DiagnosticReports/ | grep panic`. Baseline as of
2026-06-22 is 2 files (the two panics). New files beyond that
baseline indicate fresh panics.

---

## 8. Suggested Reading Order for a Fresh Claude

If you're a Claude instance just instantiated against this project,
read in this order:

1. **This document** (`docs/PROJECT_BRIEF.md`) — orientation.
2. **`docs/charter.md`** — what the project is and why.
3. **`docs/philosophy.md`** — *how* documentation is organised and
   *why* that organisation exists. Essential if you'll be writing
   into the project's docs.
4. **Tail of `docs/journal.md`** — last ~500 lines. Recent state and
   in-flight work.
5. **`docs/open_questions.md`** — what's open.
6. **Whatever specific file is relevant to the current task** — see
   the document map in Section 4.

You do *not* need to read every doc before being useful. Read the
orientation, then read targeted material as the task requires. The
"every piece of information lives in exactly one place" principle
means you can find what you need by knowing the *kind* of question
you're asking.

---

## 9. What This Document Does Not Capture

Honest accounting of this document's limits:

- **The texture of working sessions.** The journal captures
  decisions; it doesn't capture the live debugging of the heredoc
  that broke this morning, or the moment yesterday when q013 turned
  out to be a STAND and reset the whole Q15 framing. A future Claude
  reading this won't feel those moments the way Jason and I did.
- **Code-level detail.** This brief gestures at module layout but
  does not summarise each module. For "how does X work?", read the
  module.
- **The full set of D001-D008.** The grep used to inventory
  decisions.md only matched D009 onward. A future Claude needs to
  read decisions.md directly for the early decisions.
- **Direct readings of `security.md`, `status.md`, `backlog.md`,
  `open_questions.md`, `AGENTS.md`, `README.md`.** These were not
  read in full when authoring this brief. Charter, philosophy,
  architecture, governance, and evaluation *were* read in full. The
  remaining 6 docs' content is inferred from journal references and
  cross-references in the docs that were read. Direct reading of
  those files will sharpen this brief's claims about them.
- **Anything that's happened after the date written above.** This is
  a living document. If you're reading it months later, the journal
  tail is your truth source for "current state", not this section.

---

## 10. Maintenance

When making project changes, update this brief if:

- Architecture changes substantially (new pipeline stage, new
  dependency).
- A new top-level decision lands (D-series).
- A new major branch or release ships.
- A working convention changes.
- The document map drifts (new files in `docs/`, files removed or
  renamed).
- New shared-infrastructure context (other projects sharing the
  oMLX stack, new models registered, hardware changes).

For each update: add a new dated section at the bottom describing the
change. Do not edit prior sections. The append-only history pattern
is how this document stays trustworthy — same discipline as
`journal.md` and `decisions.md`.

---

## 11. Revision History

### 2026-06-21 — v0.2

- All 5 foundation docs directly read (charter, philosophy,
  architecture, governance, evaluation).
- Section 2 expanded: added determinism contract (3rd contract),
  4-step human oversight workflow, charter-vs-v1 drift notes.
- Section 3 expanded: chunking + cleanup details from architecture.md,
  the v1→v2 prompt evolution story.
- Section 4 expanded: state/history axis added as lead, stale-doc
  warnings on architecture.md (Day-1) and governance/evaluation
  (N=40-era).
- Section 6 expanded: state/history discipline added as the lead
  pattern, append-only mechanical discipline detailed, "where does
  this sentence go?" decision tree from philosophy.md.
- Section 7.5 added: cross-project context (shared oMLX with tst_llm,
  GLM models, panic-file hygiene, the corroborating-vs-independent
  evidence framing on fabrication-vs-recall).
- Section 9 updated: 5 of 5 foundation docs read directly (was 0 of 5
  in v0.1); remaining 6 still inferred.

### 2026-06-21 — v0.1

- Initial draft authored by Claude Opus 4.7 mid-session with Jason.
- Worked from `docs/journal.md` (full head + tail), `docs/decisions.md`
  TOC (D009+ only), prior conversation context, and directory
  listings.
- Foundation docs (charter, philosophy, architecture, governance,
  evaluation) inferred but not directly read.

---

**End of brief.** ~750 lines, ~5,100 words.
