# Journal

The append-only, dated narrative of building this. **One entry per working
session.** Records the *road*, not just the destination: what you did, what
broke, the dead ends, the wrong turns you corrected, the small gremlins.

**Append-only.** Never edit an old entry to "fix" it — if it was wrong, write
a new entry correcting it. The wrongness is part of the record.

---

## 2026-06-17 — project scaffolded

- Created `underwriting-copilot` from the project-bootstrap scaffolder.
- Layout, docs skeleton, and environment are in place; this is the seed entry
  so the journal is never an empty file pretending a record exists.
- First real work starts from here — log what you try, including what fails.
- Spent the first working session on documentation policy and scope
  rather than code — deliberately. The interview brief is a 5-day
  budget to produce a public-repo artefact that pre-empts Lead-level
  questions; that makes the README and supporting docs the actual
  deliverable, with code as their substrate.
- Filled out `charter.md` with mission, in-scope / out-of-scope (full
  RBAC, Decision Pack stretch, learned confidence calibration, and any
  UI beyond a CLI are explicitly out), success criteria framed as
  interview-credibility signals, and a `## Budget` section recording
  the 5-day constraint.
- Lodged Q1 (corpus: real public vs. synthetic), Q2 (orchestration
  framework: LangGraph vs. plain Python vs. DSPy), and Q3 (confidence-
  score formula) in `open_questions.md` as the first three known
  unknowns — each will resolve into a D-entry.
- Added Q4 (target deployment context — what stack does the
  interviewing reinsurer use today). Nearly mis-shelved this as a
  technical question; it's actually a *framing* question that resolves
  into the README's lead paragraph rather than a D-entry. Recorded the
  distinction explicitly in the Q4 notes so the pattern isn't repeated.
- Landed on "Cedant" (codename) + `underwriting-copilot` (repo) as the
  name pair — see D002 for the reasoning and rejected alternatives.
- Closed Q1 by lodging D003 (hybrid corpus: real public for ESG +
  Regulatory categories, synthetic for Risk Appetite + Delegated
  Authority + Internal Policy). Decided after realising pure-public
  would leave two of the five spec query categories with no source
  documents available.
- Collected 6 real public PDFs into `corpus/real/` via `wget`. Two URLs
  404'd on the first pass: EIOPA's `GuidelinesSII/...` path had been
  retired in favour of `system/files/2022-10/final_en_sog_clean.pdf`,
  and Munich Re's CDN path with the `_jcr_content/renditions/original./`
  suffix had rotated entirely. Resolved by searching for current canonical
  URLs. The Munich Re report ultimately came from the UNEP FI mirror —
  worth recording because corporate sustainability URLs rotate more often
  than regulator URLs, and if the source URL is the cited provenance, we
  should think about what happens when those rotate post-publication.
- Installed Docling. First run pulled ~40MB of RapidOCR Chinese-language
  model weights (cls + det + rec + keys) into the venv — for an
  all-English text-PDF corpus. Logged but not fixed in the moment; see
  D004 for the eventual fix.
- Established `scripts/probes/` (committed, numbered) + `scratch/`
  (gitignored) as the convention for exploratory code and its outputs
  (D005). Came out of pushback on a sloppy `/tmp` suggestion — D005 is
  the right answer: probes are part of the project's history of
  validation, not throwaway.
- **Probe 01** (Docling sweep, OCR initially enabled): EIOPA processed
  cleanly with hierarchical headings detected, BUT 76 `glyph[.notdef]`
  artefacts appeared in the output. Diagnosis: font-encoding pathology
  — the EIOPA PDF's subset font has no Unicode mapping for the
  hyphen / en-dash, so the parser falls back to the PostScript glyph
  name. Not a Docling bug. One-line replace at ingest will fix it.
  EIOPA-only across the corpus.
- **Probe 01 gremlin:** the per-page `RapidOCR returned empty result!`
  warnings looked like errors but were actually correct behaviour —
  there is no image-text to OCR in a text PDF. The default OCR pipeline
  was doing wasted work AND emitting misleading warnings. Lodged D004
  (`do_ocr=False`). EIOPA dropped from 5.4s to 2.4s.
- Probe 01 sweep over all six docs with `do_ocr=False`: ~134s total.
  Reinsurer reports (Munich Re 76.6s, Swiss Re 45.5s) cost 80% of the
  total despite being 33% of the corpus. PRA docs ran in 1–4s each;
  EIOPA 2.4s. Worth knowing: a full corpus reingest after any pipeline
  change is ~2 minutes, not seconds — so batch any chunker tuning.
- Hand-curated `corpus/corpus_metadata.toml` and built
  `src/underwriting_copilot/metadata.py` with a Pydantic schema (D006).
  The curation pass surfaced a field I hadn't planned: `superseded_by`.
  Two of six docs are superseded by newer versions (PRA SS3/19 → SS5/25;
  PRA SS1/21 → SS1/22). Without this field, "what does the PRA currently
  say about X?" would mix superseded guidance into results — a quietly
  bad failure mode. One line of schema, clearly the right call once the
  data demanded it.
- **Probe 02** validated metadata: 6 entries, no orphans either direction,
  snake_case discipline holds, 19 unique topics. Topic vocabulary already
  shows synonym pairs (`scenario_analysis` vs. `scenario_testing`, `esg`
  vs. `sustainability`) — lodged as Q5.
- **Probe 03** (section sizes) was the single most informative probe of
  the day. Mental model going in: "cap matters most, floor is
  fine-tuning." Reality: cap (>800 tokens) fires 2%, floor (<100 tokens)
  fires 46%. The chunking problem is overwhelmingly about *coalescing
  small sections*, not splitting large ones. Original "split-and-cap"
  mental model: wrong. Replaced with "merge upward aggressively, split
  rarely." (D007.)
- Probe 03 also caught a real anomaly: PRA SS1/21 produced only 6
  sections, with p90 = max = 5709 tokens. Looked broken. Diagnostic
  dive (`head -50`, heading counts): Docling extracted correctly — the
  document genuinely has only 6 `##` headings and zero `###` for ~120
  pages. Body uses numbered paragraphs (1.1, 1.2, ...) with no
  sub-headings. Reading order was *also* scrambled by the "Superseded"
  watermark fragmenting page layout (paragraphs appeared as 1.1, 1.2,
  1.7, 1.3, 1.8). This finding drove D007 (two-mode chunker with
  paragraph-fallback). The remaining sub-question — the specific
  mode-detection heuristic — is captured in Q6.
- **Probe 04** (noise audit): mostly good news. Corpus is cleaner than
  feared. `<!-- image -->` is universal at 398 instances corpus-wide
  (cheap regex). Munich Re's TOC repeats *as a literal markdown table*
  36 times — this would be chunking poison if not stripped (queries
  about section 3.1 would match the TOC 36 times instead of the one
  content chunk). Swiss Re less affected. EIOPA, PRA SS3/19, PRA SS5/25
  are clean. The Munich Re repeating-table issue is structural, not
  header noise — needs detection-of-repeating-tables logic in the
  cleanup pre-pass, not just a regex.
- **Wrong conclusion corrected:** going into Probe 04, I expected the
  PRA "Superseded" watermark to appear as repeating page-footer noise
  across many pages. It didn't — it appears once in body text, not as a
  per-page artefact. So the SS1/21 problem is reading-order scramble,
  not duplicate content. Mental model corrected: not all watermarks
  become repeating noise. The fact that this was wrong doesn't change
  the eventual chunker design (D007 still stands), but the assumption
  was load-bearing for what kind of cleanup rule was needed.
- **Wrong habit corrected:** caught mid-session by the user — we'd done
  five probes, made eight findings, taken five decisions, and committed
  exactly one of them. The state was living in chat history, which is
  exactly the failure mode `philosophy.md` warns about. Stopped to
  document everything (D003–D007, Q5, Q6, this journal pass,
  architecture and status updates). Lesson: probe → decide → document
  is the loop; skipping the document step is what destroys projects in
  the medium term, not the short term, and that delay is exactly what
  makes it tempting to skip.
- Nearly gitignored `publications/` on the assumption it was unused
  project-bootstrap scaffold — caught before commit, Quarto is in. The
  scaffold has 9 numbered sections (exec summary through conclusions,
  plus a metrics explainer) — the eval write-up will live there as a
  separate paper rather than a README chapter, which usefully separates
  the polished publication artefact from the narrative documentation.
  Lesson: don't gitignore scaffold components without confirming intent.
  "Unused now" isn't "unwanted."
- **Day 1 evening session.** Pushed past my own recommendation to stop —
  user wanted to keep going into the chunker. Justified in retrospect:
  closing Q6 and shipping cleanup + chunker tonight means tomorrow's
  Day 2 can move straight to embeddings / retrieval without a
  documentation-and-design pass first.
- Lodged **D008** closing Q6. While drafting candidate heuristics, it
  became clear D007's "two-mode chunker selected per-document" framing
  was unnecessarily granular. D008 refines to per-section strategy:
  hierarchy default, paragraph-fallback for sections > soft cap, floor
  merge for sections < soft floor. Same end-state behaviour, simpler
  implementation. Marked D007 as superseded per philosophy rather than
  editing it.
- Built `cleanup.py` with three rules: universal `<!-- image -->` strip,
  structural repeating-table dedup (Munich Re TOC handling),
  document-specific dispatch (EIOPA glyph fix; PRA SS1/21 inline
  watermark + ss1/22 link stripping). All three rules tested via
  `scripts/probes/05_cleanup_audit.py`.
- **Wrong conclusion corrected (cleanup):** when the Munich Re TOC
  dedup left 5 surviving copies of `| Sustainability in insurance`
  instead of the expected ≤2, I hypothesised the variants differed in
  column-width whitespace and added a whitespace-normalisation pass to
  the dedup key function. Re-ran the probe: identical output. Re-read
  the noise audit data: the variants don't differ in *formatting*, they
  differ in *content* — variant 1 has sub-section rows (3.1, 3.2, 3.3)
  that variant 2 lacks. The whitespace fix solved a problem that didn't
  exist. Reverted to the simpler dedup, relaxed the probe's check
  threshold to ≤8 (reflecting "several distinct TOC variants, one kept
  per variant"), and updated the cleanup docstring to honestly describe
  the limitation. The chunker's floor rule absorbs the surviving small
  TOC chunks into adjacent sections, so retrieval impact is negligible.
  Lesson: when a "fix" produces zero change in measurable output, the
  hypothesis is wrong, not the implementation.
- Built `chunking.py` per D008. Two-pass design: emission pass walks
  segments and either splits (> cap) or emits as hierarchy chunks;
  floor-merge pass iteratively merges sub-floor chunks with neighbours.
- **Three problems caught and fixed in the chunker** (initial v1 had
  8.2% sub-floor rate, well above the ≤5% threshold):
  1. *Preamble starvation* — a first-segment under-floor chunk has no
     previous chunk to merge into. Fix: bidirectional fallback in the
     floor-merge pass (try previous, then next, accept only if both
     would exceed cap).
  2. *Paragraph-fallback micro-fragments* — numbered-paragraph splitting
     on PRA SS1/21 produced tiny pieces (4 tokens, 24 tokens) when
     anchors were followed by little body. Fix: greedy coalesce pass at
     the end of `_split_then_coalesce`, combining adjacent pieces while
     staying under cap.
  3. *Single-pass merging insufficiency* — a sub-floor chunk that
     absorbed another sub-floor chunk could still be under floor; the
     single-pass logic emitted it anyway. Fix: iterative loop, don't
     advance the index after a merge so the same position is rechecked.
  After fixes: 461 chunks corpus-wide, 0 sub-floor, 0 over-cap, all
  health checks pass.
- **Gremlin (zsh history expansion):** the strings `<!-- image -->` and
  `glyph[.notdef]` in the commit message contain `!`, which zsh
  interprets as history expansion (`!-` → "look up event ending in -").
  `git commit -m "..."` blew up with `zsh: event not found: -` and
  silently aborted the chained `git add` ahead of it. Fix: single-quote
  the commit body (zsh doesn't expand `!` inside single quotes), or
  break `git add` and `git commit` onto separate lines so the add isn't
  taken down by a commit failure. Adding to muscle memory.
- **End of Day 1:** full ingest pipeline working PDF → Docling →
  cleanup → chunker → 461 chunks in `scratch/chunks/*.jsonl`. Day 2
  starts from "feed chunks into a vector store" — purely additive work,
  no design backtracking needed.

<!-- Entry shape:

## YYYY-MM-DD — short summary of the session

- What you actually did.
- What broke and how you diagnosed it.
- Dead ends — what you tried that didn't work, and why you abandoned it.
- Wrong conclusions you reached and later corrected (these are gold).
- Gremlins — the environment bug, the tooling quirk, the thing that confused
  you twice.
-->


## 2026-06-18 — Day 2 morning: D009, D010, first BGE-M3 sanity

- Opened with `git log`, `status.md`, and the graphify rebuild log to re-orient. Eight commits from Day 1 all present. Worth noting from the graphify log: the post-commit hook fired a **semantic** rebuild last night ("Rebuilt: 201 nodes, 272 edges, 17 communities", up from 114/182/13 on Day 1) despite the original briefing implying semantic rebuilds were "manual deliberate acts." Not a problem — the graph is fresher than expected — but my reading of the briefing was incomplete. Filing this as a known unknown about the hook.

- **Wrong assumption corrected (D2 first):** last night's `status.md` claimed BGE-M3 would give us "dense + sparse + ColBERT from one MLX call." Pre-flight web-search showed this is wrong — the MLX packages (`mlx-embeddings`, `mlx-embedding-models`) load BGE-M3 as a plain XLM-RoBERTa encoder, exposing **dense vectors only**. The sparse linear+ReLU head and ColBERT projection head are model-specific and only implemented in `FlagEmbedding` (PyTorch/MPS) or via ONNX runtime.

- Lodged **D009**: hybrid retrieval via MLX BGE-M3 dense + classical BM25 sparse, both indexed in Qdrant, fused via RRF. Rejected: FlagEmbedding (breaks the MLX-everywhere stack; heavier deps; slower on Apple Silicon than MLX), ONNX (new ecosystem, more debugging surface for the project budget). Lodged **Q7** as the road-not-taken: if Day 3 eval shows retrieval ceiling effects, FlagEmbedding becomes a candidate for revisitation.

- `uv add mlx-embeddings` pulled in 28 transitive packages, including the whole MLX ecosystem we don't actually need (mlx-lm, mlx-vlm, mlx-audio), a full async HTTP stack (aiohttp, fastapi, starlette, uvicorn), audio I/O (miniaudio, sounddevice), and `datasets`+`pyarrow`. Upstream `mlx-embeddings` has very loose dependency scoping. Accepted rather than fought. fsspec was downgraded `2026.6.0 → 2026.4.0` by uv's solver to satisfy a new transitive constraint — recorded in case any fsspec warnings appear later.

- **Wrong assumption corrected (model repo):** Probe 07 initially pointed at `BAAI/bge-m3`. The download fetched 14 files at 39.3 MB total and then failed with `No safetensors found in /Users/jroche/.cache/huggingface/hub/...`. The upstream HF repo *does* contain a 2.27 GB `model.safetensors` (verified in the repo tree), but mlx-embeddings' downloader didn't pick it up — either a file-pattern filter mismatch or the snapshot the cache resolved to was an older revision without safetensors. Didn't dig further: the canonical fix is `mlx-community/bge-m3-mlx-fp16`, which is the pre-converted MLX/safetensors variant with documented mlx-embeddings usage on its model card. Lesson: a plausible HF repo path is not a guarantee your loader will fetch what you need. Verify the artifact exists in the right format under the path the loader actually downloads.

- Probe 07 re-ran successfully against the pre-converted variant. Headline results:
  - Load + 1.15 GB download: 27.8 seconds.
  - First embed (graph build): 1.54s.
  - Warm throughput: 0.067s/chunk. **Projected full corpus = ~31 seconds.** Re-embedding the entire corpus is essentially free — this unlocks experimentation on chunking strategies and pooling choices later in the project without a real cost penalty.
  - Dense vector dim: 1024, matches the BGE-M3 spec.
  - Geometry passes the smell test: PRA-to-PRA similarities highest (climate↔climate = 0.81, operational-resilience↔climate = 0.78), EIOPA↔Munich Re lowest (0.55) as expected for the most cross-domain pair (governance regulation vs. reinsurer sustainability report). The dense channel is encoding meaningful semantic structure, not noise around 0.5.

- **Empirical finding (pooling — drives D010):** the probe also compared CLS-pooled + L2-normalised against `outputs.text_embeds` (which mlx-embeddings produces as mean-pooled + normalised by default for XLM-RoBERTa-family models). Cosine similarity across the five sample chunks averaged **0.687** — well below the 0.80 threshold the probe pre-declared as the "real-decision" boundary. The two strategies produce meaningfully different vectors. The BGE-M3 paper specifies CLS+L2; following the paper.
  - **Why this matters in process terms:** mean-pooled would have shipped silently as the default if the probe hadn't included the comparison from the start. Both the mlx-embeddings library default *and* the mlx-community/bge-m3-mlx-fp16 model card example use mean pooling. Two independent upstream signals saying "use mean," one paper saying "use CLS." The probe surfaced the disagreement before it could harden into a silently sub-optimal implementation. **Building the disagreement check into the first probe — not after the first failed eval — is the lesson.**

- Lodged **D010** to pin CLS+L2 pooling as the dense embedding strategy.


- `uv add qdrant-client` — 7 transitive packages, all expected (gRPC stack + `portalocker` for local-mode persistence). Pleasant contrast with the `mlx-embeddings` 28-package sprawl earlier; tightly-scoped upstream packaging makes a real difference to dependency hygiene.

- Built **Probe 08** around four queries against an in-memory Qdrant collection: dense-only self-retrieval (sanity), sparse-only (channel populated?), hybrid RRF (fusion mechanics), and dense+filter (`issuer_type=regulator` excludes reinsurer chunks). Extracted `cls_l2_pool()` as a named helper inside the probe — the canonical D010-pinned pooling, ready to lift to `src/underwriting_copilot/embed.py` when production code arrives.

- First-run results were mostly green: schema clean (named `dense` 1024-dim cosine + named `sparse`), dense self-retrieval returned chunk 0 at score 1.0000 with chunk 6 (same EIOPA doc, different section) at 0.8232, and the regulator filter held without leaks. **But sparse-only returned zero results.**

- **The probe almost lied to us.** A no-error completion where one of the four queries returned an empty list could easily have been read as "fine, move on, the real BM25 vectors will be denser anyway." That would have meant writing `retrieve.py` against an untested fusion path — the kind of silent gap that surfaces during eval, not during the probe that was supposed to catch it.

- Diagnosed: placeholder sparse vectors were configured at 8 non-zeros from a 5000-element vocab. Birthday-problem maths: probability of any index overlap between two such vectors is ~`1 - (4992/5000)^8 ≈ 1.3%` per pair. Across 10 indexed points and one query, expected overlaps ≈ 0. Confirmed with a one-liner:

  ```
  rng = random.Random(42)
  samples = [set(rng.sample(range(5000), 8)) for _ in range(11)]
  overlaps = sum(1 for s in samples[:-1] if s & samples[-1])  # → 0
  ```

  Not a Qdrant bug, not a schema problem — a probe-parameter mistake. The hybrid query *technically* worked (Qdrant didn't crash, RRF handled the empty-sparse case gracefully by falling through to dense ranks only) but the fusion-of-two-non-empty-lists code path was never exercised.

- **Lesson** worth pinning: *an unexpected zero result is a finding, not a non-finding*. A probe that produces "no results" without a structural explanation is failing silently in a way that's particularly hard to catch — it looks like success.

- Recovery: bumped `SPARSE_NNZ` from 8 to 100 (~87% per-pair overlap probability), re-ran. Sparse-only returned 5 ranked hits, hybrid RRF produced `[9, 0, 6, 4, 5]` — visibly different from dense-only `[0, 6, 3, 2, 4]` and from sparse-only `[9, 4, 5, 7, 6]`. id 9 (sparse-top, not-in-dense-top-5) and id 0 (dense-top, not-in-sparse-top-5) both surface in the hybrid top 2. RRF scoring arithmetic confirmed empirically: classic `1/(k+rank)` with `k=60` default — top hits at 0.6250, 0.6111, etc.

- Performance: 0.79s warm model load (vs. 27.8s first-time in Probe 07), 0.42s for 10-chunk embed-and-upsert combined. Per-chunk cost ~42ms. Full-corpus projection: ~20s for embed-and-index together. Cheap enough to re-index iteratively while we tune.

- One operational shortcut introduced in the probe that production code will need to fix: I derived `issuer_type` from a `document_id` prefix lookup table inside the probe rather than reading it from `corpus_metadata.toml` via the Pydantic model. That works because of the corpus naming convention, but it duplicates knowledge the metadata schema already encodes. `embed.py` / `index.py` should read `issuer_type` from the metadata model directly. Logging this as a known shortcut to fix, not a bug.


---

# Day 2 — 2026-06-18

## Where we started

End of Day 1: six real PDFs cleaned and chunked into 461 chunks under `scratch/chunks/`, all 60-then-61 unit tests green, D001–D008 closed, corpus_metadata.toml hand-curated. The Day 1 status.md promised that Day 2 would use BGE-M3 to get "dense + sparse + ColBERT from one MLX call". That promise turned out to be wrong, and the day opened with that finding.

## Morning re-orient: the BGE-M3 assumption was wrong

A pre-flight web search before adding `mlx-embeddings` to the dependencies showed that the two viable MLX wrappers (`mlx-embeddings` and `mlx-embedding-models`) load BGE-M3 as a plain XLM-RoBERTa encoder, exposing only the dense head. The sparse linear+ReLU head and the ColBERT projection are only available through FlagEmbedding's PyTorch/MPS path or through ONNX. Neither was in keeping with the project's MLX-everywhere lean.

This collapsed into **D009**: hybrid retrieval via MLX BGE-M3 dense + classical BM25 sparse, both stored in Qdrant, fused at query time via Reciprocal Rank Fusion. The FlagEmbedding road-not-taken was lodged as **Q7** with explicit resolution criteria — if Day 3 eval shows a retrieval ceiling, revisit.

Honest moment: the previous evening's status.md had been written confidently about a setup the morning's reading immediately disproved. The fix was cheap because the discipline of "decisions before code" caught it — no code had been written against the wrong assumption.

## Probe 07: BGE-M3 sanity, with a model-repo gotcha

The first probe loaded BGE-M3 via `mlx-embeddings.utils.load("BAAI/bge-m3")` and embedded five chunks. The probe failed silently in a particular way: the downloader fetched 14 files totalling 39.3 MB — config and tokenizer only, no safetensors. The model existed at `BAAI/bge-m3` (the upstream repo has a 2.27 GB safetensors file) but `mlx-embeddings`' downloader didn't pull it. The fix was to point at the pre-converted MLX variant `mlx-community/bge-m3-mlx-fp16`, which has both an mlx-embeddings-friendly file layout and documented usage on the model card.

With the right model loaded, Probe 07 confirmed:

- Dim 1024 ✓
- Cold load 27.8s, warm load 0.79s
- Warm embed 0.067s/chunk (would prove optimistic later, see embed.py)
- Geometry sensible: PRA-to-PRA chunk similarities highest (climate↔climate 0.81, operational↔climate 0.78); EIOPA↔Munich Re lowest (0.55)

The other finding from Probe 07 was a **substantive correction to default pooling**. `mlx-embeddings` returns an `outputs` object with both `last_hidden_state` (which can be CLS-pooled) and `text_embeds` (which is mean-pooled by default for XLM-RoBERTa-family models). The cosine similarity between CLS-pooled and mean-pooled across the five sample chunks averaged 0.687 — well below the low-stakes 0.80 threshold. Going with mean-pooled would have been a silent ~30% pooling-mismatch with what the BGE-M3 paper recommends.

This became **D010**: CLS-token + L2-normalisation, exported as `cls_l2_pool()` from `embed.py` so that `retrieve.py` uses the same pooling at query time (asymmetric pooling between index and query would silently degrade retrieval).

## Probe 08: Qdrant local-mode sanity — and "the probe almost lied to us"

Probe 08 verified Qdrant's local in-memory mode with named dense (1024-dim cosine) and named sparse vectors, exercised four query shapes:

- (a) Dense self-retrieval — chunk 0 returns itself at 1.0000 ✓
- (b) Sparse-only — **first run returned zero results**
- (c) Hybrid RRF
- (d) Payload filter on `issuer_type=regulator`

The zero-result run for (b) is the day's most important finding, and it has a name now: **the probe almost lied to us**. The probe was using placeholder sparse vectors with `SPARSE_NNZ=8` (8 non-zero indices out of a 5000-element vocab). The birthday-problem math says any two such vectors have a ~1.3% probability of sharing even one index. Result: sparse queries returned nothing, the fusion code path that combines two non-empty lists was never exercised, and a casual eye would have read the test as "passed" because the dense channel did its job.

The recovery was: bump `SPARSE_NNZ` from 8 to 100 (~87% pair-overlap probability), re-run, and confirm that hybrid RRF genuinely fuses two non-empty ranked lists. RRF scoring with k=60 verified empirically.

Lesson pinned for the project memory: **an unexpected zero result is a finding, not a non-finding.** When a test returns nothing, the first question is whether the test was capable of returning anything. Sparsity in synthetic vectors must be sized so that the code path under test will fire in the expected percentage of cases.

## D011: BM25 design before code

With sparse confirmed real and dense confirmed sensible, I wrote **D011** — the BM25 channel design — before any of bm25.py.

The decisions inside D011:

- Tokenisation via `\b\w+\b` regex, lowercased, ~33 stopwords (bias toward keeping, e.g. negation words like "not" and "no" preserved because regulatory text leans heavily on them).
- Porter stemming via `snowballstemmer` (pure Python, zero transitive deps).
- BM25 parameters: k1=1.5, b=0.75 (the textbook defaults).
- Vocab ids assigned **alphabetically** — load-bearing for reproducibility, since the ids get baked into stored sparse vectors and any re-build that produced different ids would silently invalidate the index.
- Vocab persisted as `corpus/bm25_vocab.json` (per-corpus committed state).
- Asymmetric sparse construction: BM25 contributions at index time, presence indicators at query time.

## bm25.py: 33 tests, including the invariant

The module is ~210 lines. The load-bearing test pins the asymmetric construction against a hand-computed BM25 expected value at 1e-9 relative precision:

```python
def test_inner_product_equals_hand_computed_bm25():
    # <query_sparse, chunk_sparse> reproduces canonical BM25
    # for a 3-document, hand-traceable corpus.
    ...
```

If the asymmetric construction ever drifts from the textbook formula, that test fires. All 33 tests passed first run (commit `06b78b9`).

## embed.py: corpus run reveals the projection drift

`embed.py` ~210 lines + 14 tests, all green first run (commit `91967d0`). Module surface: `cls_l2_pool()` exported, `embed_text()` single-text path, `embed_chunks()` lazy iterator yielding `EmbeddedChunk` named tuples, `write_embeddings_jsonl()` for per-document persistence, `embed_corpus()` driver, `__main__` block.

The full corpus run produced 461 dense vectors in 55.29s (`scratch/embeddings/*.jsonl`, 12 MB total). That is 0.120s/chunk — about **1.8× slower** than Probe 07's projection of 0.067s/chunk.

The cause was straightforward and worth recording. Probe 07 sampled the first chunk of each document. First chunks tend to be introductions: short, thin on technical vocabulary, and quick to embed. The full corpus includes chunks up to 1500 tokens with dense regulatory text — those take longer to attend over. The mean speed across the real distribution is slower than the mean speed across "first chunks only".

Mini-lesson: **projections from cherry-picked early samples bias optimistic.** Worth keeping in mind when sketching latency for retrieve and answer paths.

## D012: index module design — three sub-decisions

Three coupled choices before writing index.py:

1. **17-field payload including the chunk text.** The lean alternative (text omitted, retrieve.py does a second-pass lookup) would save ~1 MB of payload across the collection — negligible. The simplicity win for retrieve.py (one query, no joins) is decisive at this scale.
2. **`scratch/qdrant/` location.** Derived data, gitignored, regeneratable. The bm25_vocab.json honoured D011's choice of `corpus/` since vocab is small, text-format, and useful to commit; the Qdrant store is large and binary. Splitting them is honest.
3. **One-shot wipe-and-rebuild.** Idempotent re-runs, no `--force` flag, no "what's currently in there" cognitive load. Day 4+ revisit if rebuild becomes slow.

`issuer_type` also moved to being read from the Pydantic metadata model — fixing the prefix-lookup shortcut Probe 08 had used.

## index.py: orphan check catches a real metadata coordination bug

`index.py` was 349 lines + 25 tests (commit `bb125ae`). All tests passed first run, including the integration test that exercises `build_qdrant_collection` against an in-memory Qdrant.

Then I ran it against the real corpus and **it failed at step 2 (orphan check)**:

```
KeyError: "Chunk 'eiopa_guidelines_system_of_governance__0001__introduction'
references document_id 'eiopa_guidelines_system_of_governance' which is not
in corpus_metadata.toml."
```

The orphan check did exactly what it was designed to do. Three things needed unpacking:

- **What was the actual mismatch?** A diagnostic script (saved to `/tmp/diag.py` via heredoc after the terminal mangled an inline f-string with `{k!r}` — paste-history corruption, not a code bug) printed the two side-by-side. Chunks said `eiopa_guidelines_system_of_governance`; metadata keys said `eiopa_guidelines_system_of_governance.pdf`. Same pattern for Munich Re, PRA SS1/21, Swiss Re. For PRA SS3/19 and SS5/25 the date-suffix mismatched too: chunks said `pra_ss3-19_climate`, metadata said `pra_ss3-19_climate_nov2024.pdf`.

- **Which side was canonical?** Reading the TOML's header comment surfaced the answer: TOML section keys are *filenames* (the on-disk identifier — files may live in `corpus/real/` or `corpus/synthetic/`), and `document_id` is a separate inner field for the logical identifier. The TOML was well-designed; my `index.py` adapter was wrong.

- **What was the bug?** `_metadata_by_document_id()` had two branches: `isinstance(corpus_metadata, dict)` passed through unchanged; otherwise it built a dict from the list. The dict branch's "pass through" assumed the dict was already keyed by `document_id` — but `load_corpus_metadata()` returns a dict keyed by filename. Re-keying off the model's own `document_id` attribute regardless of input container was the fix.

The patch was three lines of code plus a test rename (`test_dict_passthrough` → `test_dict_rekeyed_by_document_id`) with a docstring explaining what the test now pins. Patched in place via heredoc (not delivered as a new file — small enough), tests stayed at 25 green.

Second corpus build attempt succeeded: 461 points upserted in 1.04s after 0.06s load and 0.77s BM25 build. 4810 vocab terms, avgdl=238.2 tokens/chunk. Persistence verified by reopening the collection from a fresh Python process — status green, count 461, payload sample matched D012's 17 fields exactly.

Meta-lesson: **the orphan check was decisive value.** The failure happened before any data hit Qdrant. The wipe-and-rebuild contract (D012) meant the corrected re-run was a single command, no partial state to clean up. Cheap rebuilds at this scale pay for themselves in iteration cost.

The committed `corpus/bm25_vocab.json` (212K, 14443 line-insertions because of JSON pretty-print) was the artefact most visible from this commit chain.

## retrieve.py: hybrid retrieval lands cleanly

`retrieve.py` ~280 lines + 15 tests (commit `88c4a94`). Module surface: `RetrievalHit` frozen dataclass; `reciprocal_rank_fusion()` pure function (load-bearing RRF formula pinned against hand-computed values); `_build_filter()` for the Qdrant filter construction; `Retriever` class holding BM25 vocab + Qdrant client + BGE-M3 across queries; `_demo()` running three sample queries.

All 15 tests passed first run. The RRF formula test pins `1/(k+rank)` semantics at full precision for combinations of dense-only, sparse-only, and overlap cases — anything that touches the score arithmetic in the future has to keep that green.

## The demo: Day 2 lands

Three queries, top-5 each, 22-43ms per query after model warm-up:

| Query | Top hit | Both channels? |
|---|---|---|
| PRA climate scenario analysis | PRA SS5/25 §4.124 ORSA | yes (dense 2, sparse 1) |
| Operational resilience + third-party | PRA SS5/25 Op-resilience §4.43 | yes (dense 1, sparse 1) |
| EIOPA fit and proper | EIOPA Guideline 13 | yes (dense 3, sparse 1) |

All hits substantively relevant. Score range 0.0296–0.0328 — the theoretical ceiling for "both channels rank 1" is `2/61 = 0.0328`, hit exactly by query 2's top result. The math checks out.

`exclude_superseded` filter working: zero hits from PRA SS3/19 across all three queries.

## Q8: the demo surfaces a metadata question worth lodging

Query 2 (operational resilience) had no PRA SS1/21 hits — even though SS1/21 is *the* operational resilience supervisory statement. The reason is correct filter behaviour with possibly-incorrect input data: `corpus_metadata.toml` marks SS1/21 with `superseded_by = "SS1/22"`. But SS1/22 isn't in our corpus, so the result is that the dedicated guidance is hidden by default and operational-resilience queries surface only climate-context mentions.

Lodged as **Q8** with explicit sub-questions: (a) is SS1/22 a *replacement* (true supersession) or an *amendment* (additive update) of SS1/21? and (b) if it's a replacement, do we add SS1/22 to the corpus or accept the gap and document it explicitly for eval interpretation? Resolution required before Day 3 eval design — otherwise we'd be benchmarking filter behaviour rather than retrieval quality.

## Meta-lessons from Day 2

1. **An unexpected zero result is a finding, not a non-finding.** Probe 08's sparse-channel near-silence was a clue, not a pass.
2. **Decisions before code keeps wrong assumptions cheap to correct.** The mlx-embeddings/BGE-M3 finding cost zero code rework.
3. **Cherry-picked early samples bias projections optimistic.** Embed time projection was off by 1.8× because the sample was first-chunks-only.
4. **Wipe-and-rebuild contracts make orphan-check failures cheap.** Index.py's first build failed at exactly the right point. Recovery was one patched function and one command.
5. **Working terminals are mostly an illusion of consistency.** Paste-history corruption (the `{k!r}` → `rm -rf graphify-out ...` substitution that destroyed an inline diagnostic) shows up rarely but reliably. The fix — write the script to a file via heredoc — is cheaper than fighting the paste.

## Where we stand

Day 2 functional state at commit `9e64ae2` (status.md update). The retrieval pipeline runs cleanly from PDF to ranked cited chunks. 148 tests green across the repo, 87 of them added today. Q7 and Q8 open. D009–D012 active.

## Day 3 plan

1. Resolve Q8 (verify SS1/22 metadata semantics; either add SS1/22 to corpus or correct the field).
2. `answer.py` — LLM cited-answer generation on top of `retrieve.py`. oMLX integration, prompt construction for citation-enforced answers, refusal logic when retrieved chunks don't answer the question.
3. `eval/` harness — 40+ benchmark questions with gold-standard chunks. Citation accuracy, refusal precision/recall. RAGAS optional.

Day 3 may spill into Day 4. The harness needs `answer.py` to score against, and `answer.py` involves real prompt engineering — neither is mechanical.

## Commits today

```
a50bb04 chore: add mlx-embeddings dependency
6a9939d docs: D009 embedding stack + Q7
e75655c feat: probe 07 — BGE-M3 sanity
d67c43f docs: D010 (BGE-M3 CLS+L2 pooling), journal, status
f39f865 chore: add qdrant-client dependency
1d346ec feat: probe 08 — Qdrant local-mode sanity
07085f8 docs: journal + status — Probe 08 narrative
3d74f98 docs: D011 BM25 sparse channel design
1c5fb81 chore: add snowballstemmer dependency
06b78b9 feat: BM25 sparse channel per D011 + 33 unit tests
91967d0 feat: embed.py — dense embedding pipeline per D009/D010
0bfc30c docs: D012 index module design
bb125ae feat: index.py — Qdrant + BM25 corpus index per D012
9de5c55 chore: commit BM25 vocab from first corpus index build
88c4a94 feat: retrieve.py — hybrid retrieval with RRF fusion per D009
2f576b1 docs: Q8 — does exclude_superseded leave coverage gaps?
9e64ae2 docs: status.md — end of Day 2 state
```

Seventeen commits today. Tomorrow's first commit will be journal append for Day 2.


---

# Day 3 (preliminary) — 2026-06-18 morning into early afternoon

This is a preliminary Day 3 entry covering the LLM answer-generation work and the model-choice probe. The full Day 3 entry (eval harness + decisive model selection + Q9 resolution) will come at end-of-day after the harness runs.

## Where we started

End of Day 2 at commit `e8fee72` (journal append). Retrieval pipeline working, 148 tests green, 22 commits across the day, Q7 and Q8 open. Q8 closed first thing this morning via two web searches and a one-line metadata correction.

## Q8 closure

Two supersession claims in `corpus_metadata.toml` needed scrutiny: SS1/21 → SS1/22, and SS3/19 → SS5/25. Web search showed:

- **SS1/21 → SS1/22 was wrong.** SS1/22 exists but is titled "Trading activity wind-down" (May 2022) — unrelated to operational resilience. SS1/21 is the current operative document; transitional period ended 31 March 2025. Fix: dropped the `superseded_by = "SS1/22"` line from SS1/21's metadata entry. Re-indexed; verified the previously-failing operational-resilience query now returns three SS1/21 sections in the top-5.
- **SS3/19 → SS5/25 was correct.** Multiple authoritative sources (PwC, Milliman, Clifford Chance, MHA, Forvis Mazars, and SS5/25's own text) confirm SS5/25 published 3 December 2025 replaces SS3/19 in its entirety. No fix needed.

Lesson: one of two claimed supersessions was wrong. The orphan check that caught the metadata adapter bug on Day 2 was for *structure*; this Q8 finding was about *factual content*. Different failure mode, same family — metadata accuracy matters beyond schema validity.

## D013 + Q9 — answer.py design contracts

Before writing code, lodged:

- **D013**: four contract-shape decisions for `answer.py` — citation format `[chunk_id]`, refusal phrase exact match, citation validation as eval signal, model + endpoint injected at construction.
- **Q9**: should we pull a 7-14B-class instruction-tuned model before the Day 3 eval harness? The brief flags 7-14B as the sweet spot for disciplined-faithfulness tasks; the served oMLX roster has no candidate in that range (smallest is 26B-A4B).

D013 recorded the wrong endpoint default — `8080` (mlx-lm.server) instead of `8000` (oMLX). That was my error; corrected in code before any live demo ran. D013 is append-only history, so the wrong port stays in the record with this journal entry as the correction note.

## answer.py and the live-demo loop

Built `answer.py` (~270 LOC) plus 35 unit tests. The module surface:

- `parse_citations(text)` extracts `[chunk_id]` tokens via regex.
- `validate_citations(citations, known_ids)` partitions into `(valid, hallucinated)`. The hallucinated list is the load-bearing eval signal of LLM confabulation.
- `detect_refusal(text)` exact-matches against `REFUSAL_PHRASE` with whitespace/punctuation tolerance.
- `AnswerGenerator` class holds Retriever + model + endpoint, talks to oMLX's OpenAI-compatible API.

The live demo immediately revealed three real findings, each requiring a code or config change before the next iteration.

### Finding 1 — wrong endpoint assumption

I'd assumed mlx-lm.server on port 8080. The actual served stack is oMLX on port 8000 with literal Bearer token `claude`, documented in `serving_local_models.md` at `/Users/jroche/Workspace/Python/tst_llm/`. Found via `conversation_search`. Two constants changed. Should have searched before guessing.

### Finding 2 — thinking-trace consumed the token budget

First Qwen3.6-35B-A3B-4bit run produced 15.8s on query 1 with the entire 1024-token budget consumed by `Here's a thinking process: 1. Analyze user question...` reasoning trace. The final answer was truncated mid-citation.

The fix is not "raise max_tokens" (treats symptom) or "tell the model not to think" (Qwen ignores prompt-level `/no_think` per a Chat_summarization probe done 2026-06-07). The fix is `chat_template_kwargs: {"enable_thinking": False}` in the request body, which oMLX honours as a server-side hard switch.

Added `enable_thinking` constructor parameter (default False), `_build_payload` extracted as method for unit-testing, four payload tests added.

### Finding 3 — Qwen3.6 format drift even with thinking off

With thinking disabled, Qwen3.6-35B-A3B-4bit was fast (6.8s) but produced format drift:

- Query 1: emitted `[chunk_id=pra_ss5-25_climate__...]` — added a `chunk_id=` prefix the regex doesn't parse. 0 valid citations.
- Query 2: emitted `[chunk_id_1]`, `[chunk_id_5]` — collapsed real chunk_ids to abstract placeholder names. 0 valid citations, 13 hallucinated placeholders.

The query 3 refusal was perfect on both runs.

Swapped to `gemma-4-31B-it-MLX-6bit` (instruction-tuned variant, different family). Same prompt, same chunks, same temperature 0. Results:

- Query 1: **18 valid citations, 0 hallucinated.** Substantively comprehensive answer covering proportionality, ORSA integration, scenario design, governance, use cases. 57.1s (cold load) → 31.3s (warm).
- Query 2: **12 valid citations, 0 hallucinated.** Clean Fit / Proper / Policies structure. 31.3s.
- Query 3: **Refusal in 7.7s, exact phrase.**

Same prompt, different model, dramatically different format discipline.

## The finding worth recording — with appropriate epistemic weight

**Preliminary on N=3 queries: instruction-tuned `it`-suffix Gemma-4-31B outperformed thinking-style Qwen3.6-35B-A3B-4bit on rigid citation-format discipline even with thinking disabled. Family axis (`it` vs `A3B`-thinking-style) appears more relevant than size axis (31B vs 35B) on this task.**

The data supports this claim *as preliminary*, not as a settled finding. Three confounds limit how strongly it can be stated:

1. **Same prompt template.** Both models saw the same system prompt and user-message structure. A differently-worded prompt might surface Qwen3.6's strength on the same task — what we measured includes prompt-specific bias.
2. **High keyword overlap in two of three queries.** PRA climate scenario analysis and EIOPA fit-and-proper both have heavy domain-vocabulary overlap with the retrieved chunks (the "easy" cases for retrieval and citation). Harder cases — partial-information questions, cross-chunk synthesis, ambiguous topics — were not tested.
3. **N=3 is small.** Format drift on Qwen was binary (perfect vs imperfect) on every query, not borderline; but three queries from a single domain do not generalise to the model's behaviour across the full eval space.

Day 3 eval will replicate across (a) larger N (40+ benchmark queries planned per the original Day 3 design), (b) harder cases including partial-information and cross-chunk-synthesis questions, and (c) at least one more model from each family to reduce per-model-quirk confound.

## Code state at the end of this preliminary entry

`answer.py` v4 lands at the end of this work block:

- Default model `gemma-4-31B-it-MLX-6bit` (was `Qwen3.6-35B-A3B-4bit` in D013; superseded by data).
- Environment variable `UNDERWRITING_COPILOT_MODEL` overrides the default at construction time, but loses to an explicit `model=` arg. 12-factor precedence. Lazy resolution inside `__init__`, not at import time.
- `chat_template_kwargs.enable_thinking` always sent in payload (harmless on non-Qwen models).
- 39 unit tests covering pure functions, payload construction, model resolution precedence, and AnswerGenerator integration.

## Q9 status

Still open. Today's data weakly supports the brief's underlying intuition ("disciplined-faithfulness tasks favour well-tuned instruction models over larger thinking-style models") along the **family axis** rather than the **size axis** the brief specifically called out. The size-axis claim (7-14B sweet spot) remains untested — the served roster's smallest candidate is 26B-A4B.

Decision on whether to pull a 12B-class IT model before the Day 3 eval still deferred to before-eval-design. Today's finding gives more reason to do it — testing a 12B-IT model alongside Gemma-4-31B-IT would isolate the size axis cleanly with family held constant.

## Cross-project read-across

Cedant runs on the same MLX serving stack as `tst_llm` and uses some of the same models. Today's Cedant finding has a useful read-across for `tst_llm` Q21 (the agentic-axis Qwen3.6-vs-Qwen3-Coder question): the model that wins on flexible agentic tasks might not win on rigid-format tasks, and Cedant's data is the first data point in this project family supporting that hypothesis. Delivered a paragraph to land in `tst_llm`'s journal next time that project is touched.

## Where we stand

Mid-Day-3. answer.py shipped, model-resolution architecture is correct for the eval harness, preliminary model finding recorded with appropriate caveats. Next concrete moves: build the eval harness, design the sweep matrix, run replication, decide Q9, write the full Day 3 journal entry.

## Commits since end-of-Day-2

```
823c474 fix: Q8 metadata — SS1/21 is not superseded by SS1/22
a2afe76 docs: Q8 closed — SS1/21 metadata fixed, SS3/19→SS5/25 verified
976e3b8 docs: D013 + Q9 — answer.py contracts and Day 3 model-prep question
8c6d95f feat: answer.py — LLM cited-answer generation per D013
<next commit> feat: answer.py v4 — Gemma default, env-var override, payload thinking toggle
```
