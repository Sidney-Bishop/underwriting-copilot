"""Unit tests for ``src/underwriting_copilot/cleanup.py``.

Each test uses small inline string fixtures rather than the actual corpus
files — the corpus is what `scripts/probes/05_cleanup_audit.py` exercises
end-to-end. Unit tests need isolated, debuggable behaviour examples.

Tests are grouped by function and cover:

  - **Happy path** — the documented behaviour.
  - **Edge cases** — empty input, threshold boundaries.
  - **Non-behaviour** — things the function should *not* do. Important to
    lock down because the Munich Re TOC discovery on Day 1 showed us that
    some "obvious" cleanups (e.g. whitespace normalisation across table
    variants) are deliberately not done. A test that pins this prevents
    future-me from "fixing" something that was a considered choice.
"""

from __future__ import annotations

from underwriting_copilot.cleanup import (
    apply_doc_specific,
    clean,
    dedupe_repeating_tables,
    strip_image_placeholders,
)


# ============================================================================
# strip_image_placeholders
# ============================================================================


class TestStripImagePlaceholders:
    def test_removes_single_placeholder(self) -> None:
        text = "before\n<!-- image -->\nafter"
        cleaned, n = strip_image_placeholders(text)
        assert "<!-- image -->" not in cleaned
        assert n == 1

    def test_removes_multiple_placeholders(self) -> None:
        text = "<!-- image -->\nA\n<!-- image -->\nB\n<!-- image -->\n"
        cleaned, n = strip_image_placeholders(text)
        assert "<!-- image -->" not in cleaned
        assert n == 3

    def test_preserves_surrounding_content(self) -> None:
        text = (
            "Header\n"
            "<!-- image -->\n"
            "Body paragraph one.\n"
            "Body paragraph two."
        )
        cleaned, _ = strip_image_placeholders(text)
        assert "Header" in cleaned
        assert "Body paragraph one." in cleaned
        assert "Body paragraph two." in cleaned

    def test_zero_placeholders_returns_zero_count(self) -> None:
        text = "Just regular text\nwith no placeholders."
        cleaned, n = strip_image_placeholders(text)
        assert n == 0
        assert cleaned == text

    def test_empty_input(self) -> None:
        cleaned, n = strip_image_placeholders("")
        assert cleaned == ""
        assert n == 0

    def test_does_not_match_other_html_comments(self) -> None:
        # Only the exact ``<!-- image -->`` placeholder should match.
        # Other comments are legitimate markup we shouldn't touch.
        text = "<!-- image -->\n<!-- table -->\n<!-- footnote -->\n"
        cleaned, n = strip_image_placeholders(text)
        assert n == 1
        assert "<!-- table -->" in cleaned
        assert "<!-- footnote -->" in cleaned


# ============================================================================
# dedupe_repeating_tables
# ============================================================================


class TestDedupeRepeatingTables:
    def test_strips_three_identical_tables_keeping_first(self) -> None:
        table = "| A | B |\n|---|---|\n| 1 | 2 |"
        text = f"{table}\n\nfirst\n\n{table}\n\nsecond\n\n{table}\n"
        cleaned, n = dedupe_repeating_tables(text)
        # 3 instances, 2 stripped, first kept.
        assert n == 2
        assert cleaned.count("| A | B |") == 1

    def test_keeps_two_identical_tables_below_threshold(self) -> None:
        # Threshold is 3+ occurrences. Two should both be kept.
        table = "| A | B |\n|---|---|\n| 1 | 2 |"
        text = f"{table}\n\nbetween\n\n{table}\n"
        cleaned, n = dedupe_repeating_tables(text)
        assert n == 0
        assert cleaned.count("| A | B |") == 2

    def test_keeps_singleton_table(self) -> None:
        text = "| A | B |\n|---|---|\n| 1 | 2 |"
        cleaned, n = dedupe_repeating_tables(text)
        assert n == 0
        assert cleaned == text

    def test_ignores_two_row_tables_even_if_repeated(self) -> None:
        # Tables under MIN_ROWS (3) are not considered noise candidates —
        # they're likely inline data tables, not navigation widgets.
        short = "| A | B |\n| 1 | 2 |"
        text = f"{short}\n\n{short}\n\n{short}\n\n{short}\n"
        cleaned, n = dedupe_repeating_tables(text)
        assert n == 0

    def test_preserves_non_table_content(self) -> None:
        table = "| A | B |\n|---|---|\n| 1 | 2 |"
        text = (
            "## Heading\n\n"
            "paragraph one\n\n"
            f"{table}\n\n"
            f"{table}\n\n"
            f"{table}\n\n"
            "final paragraph"
        )
        cleaned, _ = dedupe_repeating_tables(text)
        assert "## Heading" in cleaned
        assert "paragraph one" in cleaned
        assert "final paragraph" in cleaned

    def test_distinct_repeating_tables_handled_independently(self) -> None:
        # Two separate repeating tables: each keeps its first, others stripped.
        t1 = "| A | B |\n|---|---|\n| 1 | 2 |"
        t2 = "| X | Y |\n|---|---|\n| 9 | 8 |"
        text = "\n\n".join([t1, t2, t1, t2, t1, t2])
        cleaned, n = dedupe_repeating_tables(text)
        # 2 stripped of each variant.
        assert n == 4
        assert cleaned.count("| A | B |") == 1
        assert cleaned.count("| X | Y |") == 1

    def test_does_not_normalise_whitespace_variants(self) -> None:
        # Documented limitation discovered Day 1 with Munich Re TOC:
        # tables that differ only in column padding are treated as distinct.
        #
        # This is deliberate — the alternative (whitespace normalisation)
        # was tried and tested in the journal, and revealed that the actual
        # Munich Re TOC variants differ in CONTENT (some have sub-section
        # rows expanded, others don't), not just whitespace. Normalising
        # would risk merging content-distinct tables.
        #
        # The chunker's floor rule (D008) absorbs surviving small TOC
        # variants into adjacent sections, so retrieval impact is minimal.
        t_narrow = "| A | B |\n|---|---|\n| 1 | 2 |"
        t_wide = "| A   | B   |\n|-----|-----|\n| 1   | 2   |"
        text = "\n\n".join(
            [t_narrow, t_wide, t_narrow, t_wide, t_narrow, t_wide]
        )
        cleaned, n = dedupe_repeating_tables(text)
        # Each variant deduped independently: 2 from each = 4 removed.
        assert n == 4

    def test_empty_input(self) -> None:
        cleaned, n = dedupe_repeating_tables("")
        assert cleaned == ""
        assert n == 0


# ============================================================================
# apply_doc_specific
# ============================================================================


class TestApplyDocSpecific:
    EIOPA = "eiopa_guidelines_system_of_governance"
    PRA_SS1_21 = "pra_ss1-21_operational_resilience"

    def test_eiopa_replaces_glyph_with_hyphen(self) -> None:
        text = "Risk-management is required."
        text_with_glyph = text.replace("-", "glyph[.notdef]")
        out = apply_doc_specific(text_with_glyph, self.EIOPA)
        assert "glyph[.notdef]" not in out
        assert out == text

    def test_eiopa_handles_multiple_glyphs(self) -> None:
        text = (
            "## Guidelineglyph[.notdef]5 glyph[.notdef] Key functions\n\n"
            "Riskglyph[.notdef]management is required."
        )
        out = apply_doc_specific(text, self.EIOPA)
        assert "glyph[.notdef]" not in out
        assert "## Guideline-5 - Key functions" in out
        assert "Risk-management is required." in out

    def test_eiopa_preserves_non_glyph_content(self) -> None:
        text = "## Guideline 5 - Key functions\n\nSome content here."
        out = apply_doc_specific(text, self.EIOPA)
        assert out == text

    def test_pra_ss1_21_strips_inline_superseded_prefix(self) -> None:
        # The PDF rendering embeds "Superseded" inline at the start of
        # the title line. We strip just the watermark, preserving the
        # legitimate title content.
        text = "Superseded Supervisory Statement | SS1/21\nBody continues."
        out = apply_doc_specific(text, self.PRA_SS1_21)
        assert "Superseded Supervisory" not in out
        assert "Supervisory Statement | SS1/21" in out

    def test_pra_ss1_21_strips_inline_superseded_suffix(self) -> None:
        # Watermark appended at end of a body sentence.
        text = "The policy is effective immediately. Superseded\nNext line."
        out = apply_doc_specific(text, self.PRA_SS1_21)
        assert "immediately. Superseded" not in out
        assert "The policy is effective immediately." in out
        assert "Next line." in out

    def test_pra_ss1_21_strips_ss122_link(self) -> None:
        text = (
            "Some preamble.\n"
            "Please see: https://www.bankofengland.co.uk/-/media/boe/files/"
            "prudential-regulation/supervisory-statement/2022/ss1/22-march-2022.pdf"
            " which comes in to effect on 31 March 2022\n"
            "Continued content."
        )
        out = apply_doc_specific(text, self.PRA_SS1_21)
        assert "ss1/22-march-2022.pdf" not in out
        assert "Some preamble." in out
        assert "Continued content." in out

    def test_pra_ss1_21_preserves_lowercase_superseded_in_prose(self) -> None:
        # Critical non-behaviour: the word "superseded" can legitimately
        # appear in body sentences (e.g. "this SS has been superseded by..."
        # is a real phrase). Only the watermark pattern (capital-S
        # Superseded touching content at line edges) is stripped.
        text = (
            "## Introduction\n\n"
            "1.1 This supervisory statement has been superseded by SS1/22.\n"
            "1.2 The policy remains relevant for historical analysis."
        )
        out = apply_doc_specific(text, self.PRA_SS1_21)
        assert "has been superseded by SS1/22" in out
        assert "1.2 The policy remains" in out

    def test_unknown_document_id_returns_input_unchanged(self) -> None:
        text = "Some content with glyph[.notdef] and Superseded watermark."
        out = apply_doc_specific(text, "not_a_known_document")
        assert out == text


# ============================================================================
# clean (top-level pipeline)
# ============================================================================


class TestClean:
    EIOPA = "eiopa_guidelines_system_of_governance"

    def test_applies_all_rules_for_eiopa(self) -> None:
        text = (
            "<!-- image -->\n"
            "## Section glyph[.notdef] One\n\n"
            "Body text.\n"
        )
        cleaned, stats = clean(text, self.EIOPA)
        assert "<!-- image -->" not in cleaned
        assert "glyph[.notdef]" not in cleaned
        assert "## Section - One" in cleaned
        assert stats["images_stripped"] == 1
        assert stats["doc_specific_applied"] is True

    def test_returns_zero_stats_for_clean_input(self) -> None:
        text = "## Heading\n\nClean content with no noise."
        cleaned, stats = clean(text, "unknown_doc")
        assert cleaned == text
        assert stats["images_stripped"] == 0
        assert stats["tables_deduped"] == 0
        assert stats["doc_specific_applied"] is False

    def test_image_strip_runs_before_table_dedup(self) -> None:
        # Order matters: image-strip first means an image line between
        # otherwise-identical tables doesn't prevent dedup.
        table = "| A | B |\n|---|---|\n| 1 | 2 |"
        text = (
            f"{table}\n\n"
            "<!-- image -->\n\n"
            f"{table}\n\n"
            "<!-- image -->\n\n"
            f"{table}\n"
        )
        _, stats = clean(text, "unknown_doc")
        assert stats["images_stripped"] == 2
        assert stats["tables_deduped"] == 2

    def test_stats_dict_has_expected_keys(self) -> None:
        _, stats = clean("anything", "unknown_doc")
        assert set(stats.keys()) == {
            "images_stripped",
            "tables_deduped",
            "doc_specific_applied",
        }

    def test_doc_specific_not_marked_applied_when_no_change(self) -> None:
        # The EIOPA fixer runs but finds nothing to replace — the stats
        # should reflect that no change actually happened.
        text = "## Clean heading\n\nNo glyph artifacts here."
        _, stats = clean(text, self.EIOPA)
        assert stats["doc_specific_applied"] is False
