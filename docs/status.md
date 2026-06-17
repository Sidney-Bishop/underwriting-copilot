# Status

A short, **current** snapshot. Overwrite freely; never mourn the old version.
If this starts accumulating dated entries, it's turning into a journal — move
that content to `journal.md` and let this snap back to a snapshot.

**Done:**
- Project scaffolded with project-bootstrap.
- Charter, decisions D001–D007, open questions Q2–Q6, journal entry for
  2026-06-17.
- 6 real public PDFs collected into `corpus/real/` (PRA × 3, EIOPA × 1,
  Munich Re × 1, Swiss Re × 1).
- Hand-curated metadata in `corpus/corpus_metadata.toml`, Pydantic-validated
  via `src/underwriting_copilot/metadata.py`.
- Docling installed and probed against the full corpus (~134s end-to-end with
  OCR disabled per D004).
- Section-size and noise audits complete; chunker design now data-driven
  (D007).

**In progress:**
- Cleanup pre-pass: rules scoped from the noise audit, not yet implemented.

**Blocked:**
- None.

**Next:**
- Implement cleanup pre-pass (universal `<!-- image -->` strip;
  repeating-table detection for Munich Re's TOC; doc-specific watermarks
  and the EIOPA `glyph[.notdef]` fix).
- Implement chunker per D007, resolving Q6 along the way.
- Author 4–6 synthetic documents covering Risk Appetite, Delegated
  Authority, Internal Policy categories per D003.
