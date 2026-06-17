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

<!-- Entry shape:

## YYYY-MM-DD — short summary of the session

- What you actually did.
- What broke and how you diagnosed it.
- Dead ends — what you tried that didn't work, and why you abandoned it.
- Wrong conclusions you reached and later corrected (these are gold).
- Gremlins — the environment bug, the tooling quirk, the thing that confused
  you twice.
-->
