# Cedant — `underwriting-copilot`

Local-first RAG copilot for reinsurance underwriting research. Hybrid retrieval over a regulatory + corporate-sustainability corpus, cited answers, and a falsification-designed evaluation harness.

Built as a five-day artefact for a Lead Generative AI interview at a reinsurance firm.

---

## What works in v1

- **Corpus:** 461 chunks across 6 PDFs — PRA SS1/21 (operational resilience), PRA SS3/19 + SS5/25 (climate), EIOPA System of Governance, Munich Re Sustainability 2023, Swiss Re Sustainability 2024.
- **Retrieval:** hybrid BGE-M3 dense + BM25 sparse, fused via Reciprocal Rank Fusion (k=60), exclude-superseded filter on by default. Query latency 30–50 ms warm.
- **Answer generation:** local oMLX serving Gemma 4 31B IT (production default) or Qwen3.6 35B A3B via OpenAI-compatible chat completions. Override via `UNDERWRITING_COPILOT_MODEL`.
- **Citation discipline:** every claim cites the chunk(s) it came from; citations validated structurally against the retrieved context (hallucinated citations partitioned out and counted).
- **Refusal contract:** exact-phrase refusal detector; 104/104 correct refusals across the 4-cell sweep on a 26-question refusal benchmark covering out-of-corpus, adjacent-but-unanswered, and false-premise categories.
- **Eval harness:** 70-question benchmark, 2 × 2 sweep runner (models × prompts), deterministic markdown report generator from raw JSONL.

## What v1 does *not* do

Honestly noted, not buried:

- **No production-grade authentication.** Bearer-token only; v1 is local-only single-operator.
- **No LLM-as-judge for semantic correctness.** The eval measures whether the model cited the chunks we expected (structural correctness), not whether its prose accurately reflects them.
- **Retrieval ceiling at ~25% miss rate** on the 70-question benchmark. Diagnosed (Q12: query/chunk language asymmetry on CLS-pooled dense embeddings); remediation deferred to v2 (Q13).
- **No internal-document indexing.** Three synthetic Lloyd's-syndicate documents in `corpus/synthetic/` demonstrate the *kind* of internal content the system extends to, but they are not indexed in v1.

`docs/governance.md` and `docs/evaluation.md` are explicit about scope, contracts, and limitations.

## Prerequisites

- macOS on Apple Silicon (developed on M5 Max). The MLX dependency assumes Apple Silicon.
- Python 3.14 via [`uv`](https://docs.astral.sh/uv/).
- oMLX running locally on port 8000 with `gemma-4-31B-it-MLX-6bit` and (optionally) `Qwen3.6-35B-A3B-4bit` available. See `docs/serving.md` if present, or oMLX docs.
- ~30 GB disk for the Qdrant index and model weights.

## Quickstart

```bash
# Environment setup
uv sync

# Run the test suite (158+ tests)
uv run pytest

# Smoke-test the eval harness on a single question
uv run python -m eval.runner --question-ids q002 --models gemma-4-31B-it-MLX-6bit --prompts v2

# Full sweep (~45 minutes, 280 cells)
uv run python -m eval.runner

# Generate the markdown report from the latest run
uv run python -m eval.report
```

The smoke test exercises the full retrieve → generate → cite → validate pipeline on one question and prints the result; if it passes, every component is wired correctly.

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
   user query  ──►  hybrid retrieve (RRF k=60)  ──►  top-K chunks
                                                       │
                                                       ▼
                          oMLX (Gemma/Qwen) generates cited answer
                                                       │
                                                       ▼
                          validate_citations partitions valid vs hallucinated
                                                       │
                                                       ▼
                          cited answer + structural correctness signals
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

## Evaluation

The eval harness is in `eval/`. It runs a 70-question benchmark across both production-candidate models and both prompt versions (4 cells × 70 questions = 280 cells per sweep).

**To read the data:**

- `eval/results/2026-06-18T15-32-07Z/report.md` — machine-generated aggregated report from the canonical 280-cell sweep. Headline numbers, subset analysis, refusal correctness by category, retrieval miss diagnostic, hallucination breakdown, per-question detail.
- `docs/evaluation.md` — methodology paired with the report. What was measured, how, what we can claim, what we cannot, methodological limitations.

**To re-run from scratch:**

```bash
uv run python -m eval.runner               # ~45 min wall-clock
uv run python -m eval.report               # regenerate report.md
```

The harness writes per-cell records incrementally to `raw.jsonl`; an interrupted sweep preserves its partial data.

## Documentation map

Single-purpose docs. Find by the *kind* of information you have, not by topic.

| Document | Kind | Read it for… | Update style |
|---|---|---|---|
| `docs/status.md` | State | Where the project is today | Overwrite |
| `docs/governance.md` | State | Scope, contracts, decisions, output discipline | Overwrite |
| `docs/security.md` | State | Threat model and v1 mitigations | Overwrite |
| `docs/evaluation.md` | State | Eval methodology paired with report.md | Overwrite |
| `docs/decisions.md` | Decision history | Choices made and why (D-IDs); open Q-IDs | Append + supersede |
| `docs/journal.md` | Session history | What happened, what broke, what was retracted | Append-only, dated |
| `corpus/synthetic/README.md` | Guide | Demo internal documents (Sycamore Re) | Overwrite |

**Routing rule** — where does a sentence go? *true now* → a State doc · *a choice someone will later question* → `decisions.md` · *something that happened* → `journal.md`.

The journal is where the honest story lives. Two specific entries to read if assessing this artefact:

1. **Day 3 close (commit `7e60ef4`)** — the family-axis interpretation retraction. Day 2 had identified a model-family property; D014's designed-to-falsify 2×2 sweep showed it was a prompt-fit artifact. Retracted publicly with pre-stated falsification criterion. Documents the discipline of *designing the test to falsify, not confirm*.

2. **Day 5 morning (commit `5d0a23a`)** — the within-document parity claim update. Day 3's "Gemma and Qwen are tied at 0.929 on within-document workloads" turned out to be a small-sample artifact. The extended 70-question sweep showed Gemma consistently ~5pp ahead across single-chunk, multi-chunk, and within-document subsets. Documents the discipline of *raising the bar for parity claims based on power, not point estimates*.

## Layout

```
underwriting-copilot/
├── src/underwriting_copilot/   # pipeline modules (8 files)
├── eval/                       # benchmark.toml, scorer, runner, report
├── tests/                      # pytest — 158+ tests
├── docs/                       # state, decision, narrative
├── corpus/
│   ├── *.pdf                   # 6 source PDFs (gitignored — see ingestion docs)
│   └── synthetic/              # demo internal documents (not indexed in v1)
└── scratch/                    # Qdrant index (gitignored)
```

## Notes

- Production model default is Gemma 4 31B IT (D015). Qwen3.6 35B A3B remains available via `UNDERWRITING_COPILOT_MODEL` for latency-budgeted workloads.
- All inference is local: no outbound network calls in steady state. The eval and pipeline are deterministic at `temperature=0`.
- The 5-day arc produced 45 commits, two empirically-driven retractions of prior framings, and the artefact you're reading now. The journal is the unredacted version.

## License

MIT · Jason Roche
