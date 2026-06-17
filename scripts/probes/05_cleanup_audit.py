"""Probe: apply the cleanup pre-pass (cleanup.clean) to each markdown
produced by Probe 01, write cleaned output to scratch/docling_cleaned/,
and verify the previously-flagged noise patterns are now gone.

This probe is the verification half of the cleanup module. It exists so
that future contributors (and future-me) can:
  - re-run cleanup over the full corpus without writing new glue code
  - confirm at a glance that each rule fired the expected number of times
  - catch regressions: if a future cleanup change causes a previously-clean
    document to suddenly report stripped tables, that's a signal worth
    eyeballing.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROBES = PROJECT_ROOT / "scratch" / "docling_probes"
CLEANED = PROJECT_ROOT / "scratch" / "docling_cleaned"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from underwriting_copilot.cleanup import clean  # noqa: E402
from underwriting_copilot.metadata import load_corpus_metadata  # noqa: E402


def main() -> None:
    if not PROBES.exists():
        raise SystemExit(f"No probe outputs at {PROBES} — run probe 01 first.")

    CLEANED.mkdir(parents=True, exist_ok=True)

    # Build filename-stem → document_id map from the metadata so doc-specific
    # rules dispatch correctly. The markdown files in PROBES are named after
    # the PDF basenames (e.g. pra_ss5-25_climate_dec2025.md), but the
    # document_id from metadata is the canonical slug
    # (e.g. pra_ss5-25_climate) — these are not always identical.
    metadata = load_corpus_metadata(PROJECT_ROOT / "corpus" / "corpus_metadata.toml")
    stem_to_doc_id = {Path(fname).stem: m.document_id for fname, m in metadata.items()}

    md_files = sorted(PROBES.glob("*.md"))

    print(f"{'document':50s}  {'imgs':>5s}  {'tbls':>5s}  {'doc?':>5s}  {'glyphs':>10s}")
    print("-" * 95)

    totals = {"images_stripped": 0, "tables_deduped": 0, "doc_specific_fired": 0}

    for md_file in md_files:
        document_id = stem_to_doc_id.get(md_file.stem, md_file.stem)
        original = md_file.read_text()
        cleaned, stats = clean(original, document_id)

        glyphs_before = original.count("glyph[.notdef]")
        glyphs_after = cleaned.count("glyph[.notdef]")
        glyphs_str = f"{glyphs_before}→{glyphs_after}"

        out = CLEANED / md_file.name
        out.write_text(cleaned)

        totals["images_stripped"] += stats["images_stripped"]
        totals["tables_deduped"] += stats["tables_deduped"]
        if stats["doc_specific_applied"]:
            totals["doc_specific_fired"] += 1

        print(
            f"{document_id:50s}  "
            f"{stats['images_stripped']:>5d}  "
            f"{stats['tables_deduped']:>5d}  "
            f"{('yes' if stats['doc_specific_applied'] else 'no'):>5s}  "
            f"{glyphs_str:>10s}"
        )

    print("-" * 95)
    print(
        f"{'TOTALS':50s}  "
        f"{totals['images_stripped']:>5d}  "
        f"{totals['tables_deduped']:>5d}  "
        f"{totals['doc_specific_fired']:>5d}  "
        f"{'':>10s}"
    )

    # Post-cleanup verification: confirm the patterns Probe 04 flagged are gone.
    print("\n=== POST-CLEANUP VERIFICATION ===")

    checks = [
        (
            "eiopa_guidelines_system_of_governance.md",
            "glyph[.notdef]",
            "EIOPA glyph artifacts",
            76,
        ),
        (
            "munich_re_sustainability_2023.md",
            "<!-- image -->",
            "Munich Re image placeholders",
            246,
        ),
        (
            "swiss_re_sustainability_2024.md",
            "<!-- image -->",
            "Swiss Re image placeholders",
            143,
        ),
        (
            "pra_ss1-21_operational_resilience.md",
            "<!-- image -->",
            "PRA SS1/21 image placeholders",
            9,
        ),
    ]

    all_pass = True
    for filename, pattern, label, expected_before in checks:
        cleaned_text = (CLEANED / filename).read_text()
        n = cleaned_text.count(pattern)
        status = "✓" if n == 0 else "✗"
        if n != 0:
            all_pass = False
        print(f"  {status}  {label:45s} {expected_before}→{n}")

    # Munich Re TOC: the source PDF reprints SEVERAL distinct TOC variants
    # (e.g. one with sub-sections 3.1/3.2/3.3 expanded, another without).
    # Dedup keeps the first instance of each variant, so the surviving count
    # equals the number of distinct variants rather than 1. We accept this:
    # the chunker's <100-token floor rule (D008) absorbs surviving TOC
    # tables into adjacent sections, so retrieval impact is near-zero.
    munich_cleaned = (CLEANED / "munich_re_sustainability_2023.md").read_text()
    repeating_toc_marker = "| Sustainability in insurance"
    n_marker = munich_cleaned.count(repeating_toc_marker)
    # ≤8 reflects "several variants" without being a free pass for regressions.
    status = "✓" if n_marker <= 8 else "✗"
    if n_marker > 8:
        all_pass = False
    print(
        f"  {status}  {'Munich Re TOC line surviving':45s} "
        f"36→{n_marker}  (≤8 expected: several distinct TOC variants,"
        f" each kept once)"
    )

    print()
    print("All checks pass." if all_pass else "FAILURES — see above.")


if __name__ == "__main__":
    main()
