# Cedant — `underwriting-copilot`

Local-first RAG copilot for reinsurance underwriting research. Hybrid retrieval over a regulatory + corporate-sustainability corpus, cited answers, and a falsification-designed evaluation harness.

A working proof-of-concept with structurally enforced citation and refusal contracts.

---

## What's in this repository

- **A working RAG pipeline** over six public regulatory and corporate-sustainability PDFs, with structurally enforced citation discipline.
- **A local Streamlit analyst interface** (`app.py`) that demonstrates the system end-to-end.
- **An evaluation harness** (`eval/`) with a 70-question hand-crafted benchmark, a 2×2 sweep runner, and a deterministic report generator.
- **A full Quarto technical report** at `publications/underwriting_copilot/` covering design, methodology, evaluation, limitations, and future work. **This is the primary entry point for a new reader.**
- **A documentation set** (`docs/`) including append-only decision and journal logs.

## Reading the report

The Quarto report is the polished, multi-audience write-up of the project. To preview it locally:

```bash
cd publications/underwriting_copilot
uv run quarto preview
```

Quarto serves the report at a local URL and auto-reloads on file changes. The report has a sidebar nav for the ten sections plus a glossary and a plain-language concepts appendix; business readers can read the Executive Summary + Conclusions and skip the technical sections.

To render static HTML without serving:

```bash
cd publications/underwriting_copilot
uv run quarto render
```

Output lands in `publications/underwriting_copilot/_output/`.

---

## What works in v1

- **Corpus:** 461 chunks across 6 PDFs — PRA SS1/21 (operational resilience), PRA SS3/19 + SS5/25 (climate), EIOPA System of Governance, Munich Re Sustainability 2023, Swiss Re Sustainability 2024.
- **Retrieval:** hybrid BGE-M3 dense + BM25 sparse, fused via Reciprocal Rank Fusion (k=60), exclude-superseded filter on by default. Query latency 30–50 ms warm.
- **Answer generation:** local oMLX serving Gemma 4 31B IT (production default) or Qwen3.6 35B A3B via OpenAI-compatible chat completions. Override via `UNDERWRITING_COPILOT_MODEL`.
- **Citation discipline:** every claim cites the chunk(s) it came from; citations validated structurally against the retrieved context. Hallucinated citations partitioned out and counted (production-default model: **zero hallucinated citations** across the full answerable benchmark).
- **Refusal contract:** exact-phrase refusal detector; **104/104 correct refusals** across the 4-cell sweep on a 26-question refusal benchmark covering out-of-corpus, adjacent-but-unanswered, and false-premise categories.
- **Eval harness:** 70-question benchmark, 2 × 2 sweep runner (models × prompts), deterministic markdown report generator from raw JSONL.
- **Analyst UI:** local Streamlit app rendering cited answers with green citation badges, red badges for hallucinated citations, and source cards beneath each answer.
- **Technical report:** full Quarto report at `publications/underwriting_copilot/`.

## What v1 does *not* do

Honestly noted, not buried:

- **No production-grade authentication.** Bearer-token only; v1 is local-only single-operator.
- **No LLM-as-judge for semantic correctness.** The eval measures whether the model cited the chunks we expected (structural correctness), not whether its prose accurately reflects them.
- **Retrieval ceiling at ~25% miss rate** on the 70-question benchmark. Diagnosed (Q12: query/chunk language asymmetry on CLS-pooled dense embeddings); remediation deferred to v2 (Q13).
- **Cross-document synthesis** scores below 0.25 mean citation recall across all evaluation cells. Not a supported primary use case in v1.
- **No internal-document indexing.** Three synthetic Sycamore Reinsurance documents in `corpus/synthetic/` demonstrate the *kind* of internal content the system extends to, but they are not indexed in v1.

`docs/governance.md` and `docs/evaluation.md` are explicit about scope, contracts, and limitations. The Quarto report's *Limitations and Future Work* section is the most accessible summary.

---

## Prerequisites

- macOS on Apple Silicon (developed on M5 Max). The MLX dependency assumes Apple Silicon.
- Python 3.14 via [`uv`](https://docs.astral.sh/uv/).
- oMLX running locally on port 8000 with `gemma-4-31B-it-MLX-6bit` and (optionally) `Qwen3.6-35B-A3B-4bit` available. See `docs/serving_local_models.md` for the oMLX setup.
- [Quarto](https://quarto.org/docs/get-started/) installed locally if you want to render the technical report (optional — you can also read the source `.qmd` files directly in `publications/underwriting_copilot/sections/`).
- ~30 GB disk for the Qdrant index and model weights.

## Quickstart

The full new-clone-to-running flow:

```bash
# 1. Environment setup
uv sync

# 2. Build the corpus index (one-shot, ~2 min on a warm cache)
uv run python -m underwriting_copilot.index --rebuild

# 3. Verify the test suite (177+ tests, < 1 min)
uv run pytest

# 4. Smoke-test the pipeline on a single question (exercises retrieve → generate → cite → validate)
uv run python -m eval.runner --question-ids q002 --models gemma-4-31B-it-MLX-6bit --prompts v2

# 5. Launch the Streamlit analyst interface
uv run streamlit run app.py --server.port 8502 --server.headless true --server.address 127.0.0.1
```

If the smoke test passes, every component is wired correctly. The Streamlit UI then provides interactive access to the same pipeline.

### Running the full evaluation sweep

```bash
# Full 2×2 sweep across 70 questions (~45 minutes, 280 cells)
uv run python -m eval.runner

# Regenerate the markdown report from the latest raw.jsonl
uv run python -m eval.report
```

The two canonical evaluation runs are already committed at `eval/results/2026-06-18T*Z/` and can be regenerated to the bit from the same software state.

---

## Architecture in 60 seconds

```
   PDFs (6)                    Docling chunking            Qdrant
       │                           │                          │
       ▼                           ▼                          ▼
   corpus/  ──ingest──►   461 chunks + metadata  ──index──► dense (BGE-M3)
                                                            sparse (BM25)
                                                              │
                          ┌─────────────────────────────────────┘
                          │
                          ▼
   user query  ──►  hybrid retrieve (RRF k=60)  ──►  top-k chunks
                                                       │
                                                       ▼
                          oMLX (Gemma/Qwen) generates cited answer
                                                       │
                                                       ▼
                          validate_citations partitions valid vs hallucinated
                                                       │
                                                       ▼
                          AnswerResult (cited answer + source chunks + refusal flag)
                                                       │
                          ┌────────────────────────────┼────────────────────────────┐
                          ▼                            ▼                            ▼
                    Streamlit UI                  eval harness                  CLI smoke test
                          │                            │                            │
                          └──── all share the same Retriever and AnswerGenerator ────┘
```

Source code in `src/underwriting_copilot/`:

| Module | Role |
|---|---|
| `cleanup.py` | PDF normalisation pre-Docling |
| `chunking.py` | Docling-based chunking with metadata extraction |
| `metadata.py` | Issuer, jurisdiction, supersession metadata |
| `bm25.py` | Porter-stemmed sparse vocabulary |
| `embed.py` | BGE-M3 CLS+L2-pooled dense embeddings |
| `index.py` | Qdrant local-mode persistence |
| `retrieve.py` | Hybrid dense + sparse with RRF, jurisdiction/issuer/supersession filters |
| `answer.py` | oMLX inference, system prompt, citation validation, refusal detection |

`docs/architecture.md` has the deeper version with component boundaries, data flow, and the rationale for the specific design choices (BGE-M3 over alternatives, RRF over weighted-sum fusion, the validate-citations partitioning approach). The Quarto report's *Methodology* section is the equivalent in more accessible language.

## Evaluation

The eval harness is in `eval/`. It runs a 70-question benchmark across both production-candidate models and both prompt versions (4 cells × 70 questions = 280 cells per sweep).

**To read the data:**

- `eval/results/2026-06-18T15-32-07Z/report.md` — machine-generated aggregated report from the canonical 280-cell sweep. Headline numbers, subset analysis, refusal correctness by category, retrieval miss diagnostic, hallucination breakdown, per-question detail.
- `publications/underwriting_copilot/sections/06_results.qmd` — the *Results* section of the Quarto report, which presents the same numbers with interpretation and context.
- `docs/evaluation.md` — methodology paired with the report. What was measured, how, what we can claim, what we cannot, methodological limitations.

**To re-run from scratch:**

```bash
uv run python -m eval.runner               # ~45 min wall-clock
uv run python -m eval.report               # regenerate report.md
```

The harness writes per-cell records incrementally to `raw.jsonl`; an interrupted sweep preserves its partial data.

---

## Documentation map

**For most readers, start with the Quarto report at `publications/underwriting_copilot/`.** It is the polished, multi-audience write-up of the project, written for both technical and business readers. The `docs/` tree below is the source-of-truth set the report is built from — useful for maintainers and deep-divers.

Single-purpose docs. Find by the *kind* of information you have, not by topic.

| Document | Kind | Read it for… | Update style |
|---|---|---|---|
| `docs/charter.md` | State (rare) | What this project is for; scope in/out | Overwrite, seldom |
| `docs/architecture.md` | State | How the system is built right now | Overwrite |
| `docs/status.md` | State | Where the project is today | Overwrite |
| `docs/governance.md` | State | Scope, contracts, decisions, output discipline | Overwrite |
| `docs/security.md` | State | Threat model and v1 mitigations | Overwrite |
| `docs/evaluation.md` | State | Eval methodology paired with `report.md` | Overwrite |
| `docs/open_questions.md` | State | Open Q-IDs (Q-state tracking) | Overwrite; resolve out |
| `docs/decisions.md` | Decision history | Choices made and why (D-IDs) | Append + supersede |
| `docs/journal.md` | Session history | What happened, what broke, what was retracted | Append-only, dated |
| `docs/backlog.md` | Fluid | What might come next | Cross off when done |
| `docs/philosophy.md` | Guide | Why the docs are structured thus | Teaches; rarely edited |
| `corpus/synthetic/README.md` | Guide | Demo internal documents (Sycamore Re) | Overwrite |
| `publications/underwriting_copilot/` | Quarto report | Multi-audience technical write-up | Overwrite; preview with `quarto preview` |

**Routing rule** — where does a sentence go? *true now* → a State doc · *a choice someone will later question* → `decisions.md` · *something that happened* → `journal.md`.

---

## Layout

```
underwriting-copilot/
├── src/underwriting_copilot/   # pipeline modules (8 files)
├── eval/                       # benchmark.toml, scorer, runner, report
│   └── results/                # canonical evaluation runs (committed)
├── tests/                      # pytest — 177+ tests (158+ pipeline, 19 Streamlit AppTest)
├── docs/                       # state, decision, narrative, guide docs
├── publications/
│   └── underwriting_copilot/   # Quarto technical report
│       ├── _quarto.yml         # site config
│       ├── index.qmd           # landing page
│       ├── images/             # report assets
│       └── sections/           # 10 report sections + glossary + appendix
├── corpus/
│   ├── real/                   # 6 source PDFs (PRA × 3, EIOPA × 1, Munich Re × 1, Swiss Re × 1)
│   └── synthetic/              # 3 Sycamore Reinsurance documents (not indexed in v1)
├── assets/                     # corpus mark, badges
├── app.py                      # Streamlit analyst interface
├── launch_claude.sh            # dev-only: launch Claude Code against local oMLX
└── scratch/                    # Qdrant index (gitignored)
```

## Notes

- Production model default is Gemma 4 31B IT (D015). Qwen3.6 35B A3B remains available via `UNDERWRITING_COPILOT_MODEL` for latency-budgeted workloads.
- All inference is local: no outbound network calls in steady state. The eval and pipeline are deterministic at `temperature=0`.
- The journal (`docs/journal.md`) is the unredacted version of what happened during development — including the two retracted-on-the-record findings that the report's *Experiments* and *Limitations* sections describe.

## Developer notes

Development of Cedant was assisted by Claude Code pointed at the same local oMLX endpoint Cedant uses at runtime. The launcher script `launch_claude.sh` encodes the setup — it unsets any cloud API key, verifies oMLX is serving, pins the default model (D015), and starts Claude Code with the right environment variables.

This is a dev-time tool only; Cedant itself does not depend on it. A fresh cloner reproducing the pipeline (eval, Streamlit UI, report) does not need to touch it. A fresh cloner reproducing the dev workflow can run `./launch_claude.sh` after installing Claude Code (`npm install -g @anthropic-ai/claude-code`) and serving the candidate models in oMLX.

## License

MIT · Jason Roche
