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
