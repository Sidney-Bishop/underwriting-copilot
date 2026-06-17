"""Unit tests for ``src/underwriting_copilot/chunking.py``.

Tests are grouped by function. The public API surface is small (essentially
``chunk_document``), but the internal helpers (``parse_segments``,
``_split_then_coalesce``, ``_apply_floor_merging``) carry enough logic that
testing them directly catches regressions that would otherwise only show
up as subtle changes in chunk distributions across the corpus.

Pragma: testing private helpers (leading underscore) is acceptable here
because the project values correctness diagnostics over strict API hygiene.
When a future refactor moves logic between these helpers, these tests will
either need updating (legitimate) or will reveal a behaviour change (the
whole point).
"""

from __future__ import annotations

from underwriting_copilot.chunking import (
    Chunk,
    _apply_floor_merging,
    _split_then_coalesce,
    approx_tokens,
    chunk_document,
    parse_segments,
)


# ============================================================================
# approx_tokens
# ============================================================================


class TestApproxTokens:
    def test_simple_word_count(self) -> None:
        assert approx_tokens("one two three") == 3

    def test_multiple_whitespace_collapses(self) -> None:
        # str.split() with no args treats runs of whitespace as one separator.
        assert approx_tokens("one    two\n\nthree") == 3

    def test_empty_string(self) -> None:
        assert approx_tokens("") == 0

    def test_whitespace_only(self) -> None:
        assert approx_tokens("   \n\n  ") == 0


# ============================================================================
# parse_segments
# ============================================================================


class TestParseSegments:
    def test_single_heading_with_body(self) -> None:
        text = "## Section A\n\nThis is the body."
        segs = parse_segments(text)
        assert len(segs) == 1
        assert segs[0].heading_text == "Section A"
        assert segs[0].heading_depth == 2
        assert segs[0].heading_path == ["Section A"]
        assert segs[0].body == "This is the body."

    def test_nested_headings_build_path(self) -> None:
        text = (
            "## Section A\n\n"
            "Intro to A.\n\n"
            "### Subsection A.1\n\n"
            "Body of A.1.\n\n"
            "### Subsection A.2\n\n"
            "Body of A.2."
        )
        segs = parse_segments(text)
        # Three segments — Section A's body, A.1's body, A.2's body.
        assert len(segs) == 3
        assert segs[0].heading_path == ["Section A"]
        assert segs[1].heading_path == ["Section A", "Subsection A.1"]
        assert segs[2].heading_path == ["Section A", "Subsection A.2"]

    def test_sibling_pops_ancestors(self) -> None:
        # When ## B follows ### A.1, the path should be just [B],
        # not [A, A.1, B].
        text = (
            "## A\n\nbody A\n\n"
            "### A.1\n\nbody A.1\n\n"
            "## B\n\nbody B"
        )
        segs = parse_segments(text)
        assert segs[-1].heading_path == ["B"]
        assert segs[-1].heading_text == "B"

    def test_preamble_segment_for_text_before_first_heading(self) -> None:
        text = "This is preamble text content.\n\n## Heading\n\nBody."
        segs = parse_segments(text)
        assert len(segs) == 2
        assert segs[0].heading_text == "(preamble)"
        assert segs[0].heading_depth == 1
        assert "preamble" in segs[0].body.lower()

    def test_no_headings_produces_only_preamble(self) -> None:
        text = "Just a paragraph.\n\nAnother paragraph."
        segs = parse_segments(text)
        assert len(segs) == 1
        assert segs[0].heading_text == "(preamble)"

    def test_empty_input_produces_no_segments(self) -> None:
        assert parse_segments("") == []

    def test_heading_with_empty_body(self) -> None:
        text = "## Empty\n\n## Next\n\nbody."
        segs = parse_segments(text)
        assert segs[0].heading_text == "Empty"
        assert segs[0].body == ""
        assert segs[1].heading_text == "Next"
        assert segs[1].body == "body."

    def test_deeply_nested_path(self) -> None:
        # Three levels of nesting; path should track all three.
        text = (
            "## L2\n\nbody L2\n\n"
            "### L3\n\nbody L3\n\n"
            "#### L4\n\nbody L4"
        )
        segs = parse_segments(text)
        assert segs[-1].heading_path == ["L2", "L3", "L4"]
        assert segs[-1].heading_depth == 4


# ============================================================================
# _split_then_coalesce
# ============================================================================


class TestSplitThenCoalesce:
    def test_splits_on_numbered_paragraph_anchors(self) -> None:
        # Anchors must be at line start to match (^\d+\.\d+\s+ in MULTILINE).
        body = (
            "1.1 First numbered point.\n"
            "1.2 Second numbered point.\n"
            "1.3 Third numbered point."
        )
        # Tiny cap to prevent coalescing back into one piece.
        pieces = _split_then_coalesce(body, soft_cap=4)
        joined = "\n\n".join(pieces)
        assert "1.1 First" in joined
        assert "1.2 Second" in joined
        assert "1.3 Third" in joined
        # Each anchor should have produced its own piece at this cap.
        assert len(pieces) == 3

    def test_falls_back_to_paragraph_split_without_anchors(self) -> None:
        body = (
            "First paragraph here.\n\n"
            "Second paragraph here.\n\n"
            "Third paragraph here."
        )
        pieces = _split_then_coalesce(body, soft_cap=4)
        # Each paragraph is ~3 words → each becomes its own piece under cap=4.
        assert len(pieces) == 3

    def test_coalesces_tiny_pieces_under_cap(self) -> None:
        # Anchor split produces tiny pieces; coalesce should combine them.
        body = "1.1 short.\n1.2 brief.\n1.3 small."
        pieces = _split_then_coalesce(body, soft_cap=20)
        # Each piece is ~2 words; cap=20 means all combine into one.
        assert len(pieces) == 1

    def test_respects_cap_boundary_with_greedy_word_split(self) -> None:
        # No anchors, single long line, no paragraph breaks — falls through
        # to the greedy word split which caps each piece.
        body = " ".join(f"word{i}" for i in range(100))
        pieces = _split_then_coalesce(body, soft_cap=30)
        for piece in pieces:
            assert approx_tokens(piece) <= 30
        # Should produce multiple pieces given 100 words at cap 30.
        assert len(pieces) >= 3

    def test_single_short_piece_returned_as_is(self) -> None:
        body = "Short body content here."
        pieces = _split_then_coalesce(body, soft_cap=1500)
        assert len(pieces) == 1
        assert pieces[0] == "Short body content here."


# ============================================================================
# _apply_floor_merging
# ============================================================================


def _make_chunk(
    text: str,
    section_path: list[str] | None = None,
    chunk_id: str = "test",
) -> Chunk:
    """Test helper: build a Chunk with sensible defaults."""
    return Chunk(
        chunk_id=chunk_id,
        document_id="test_doc",
        section_path=section_path or ["root"],
        text=text,
        token_count=approx_tokens(text),
    )


class TestApplyFloorMerging:
    def test_backward_merge_when_previous_has_room(self) -> None:
        chunks = [
            _make_chunk("word " * 200, ["A"], "c0"),  # ~200 tokens
            _make_chunk("word " * 50, ["B"], "c1"),   # ~50 tokens, under floor
        ]
        result = _apply_floor_merging(chunks, soft_floor=100, soft_cap=1500)
        assert len(result) == 1
        assert result[0].chunk_strategy == "merged"
        assert ["B"] in result[0].merged_section_paths

    def test_forward_merge_when_no_previous(self) -> None:
        # First chunk under floor — should merge into the next.
        chunks = [
            _make_chunk("word " * 50, ["preamble"], "c0"),  # under floor
            _make_chunk("word " * 200, ["A"], "c1"),
        ]
        result = _apply_floor_merging(chunks, soft_floor=100, soft_cap=1500)
        assert len(result) == 1
        assert result[0].chunk_strategy == "merged"
        # The preamble's path was absorbed into the receiving chunk.
        assert ["preamble"] in result[0].merged_section_paths

    def test_no_merge_when_both_neighbours_would_exceed_cap(self) -> None:
        # Both neighbours are too large to absorb the small one without
        # exceeding cap.
        chunks = [
            _make_chunk("word " * 1490, ["A"], "c0"),
            _make_chunk("word " * 50, ["B"], "c1"),
            _make_chunk("word " * 1490, ["C"], "c2"),
        ]
        result = _apply_floor_merging(chunks, soft_floor=100, soft_cap=1500)
        # Under-floor middle chunk stays — neither merge fits under cap.
        assert len(result) == 3
        assert result[1].token_count == 50

    def test_iterative_recheck_absorbs_chained_small_chunks(self) -> None:
        # The pivotal test for the iterative-merge design (D008): a chunk
        # that absorbs a small neighbour but is *itself* still under floor
        # must be eligible for further merging in the same pass.
        chunks = [
            _make_chunk("word " * 30, ["A"], "c0"),
            _make_chunk("word " * 30, ["B"], "c1"),
            _make_chunk("word " * 50, ["C"], "c2"),
            _make_chunk("word " * 200, ["D"], "c3"),
        ]
        result = _apply_floor_merging(chunks, soft_floor=100, soft_cap=1500)
        # All small chunks should end up merged forward until none are
        # under floor.
        assert all(c.token_count >= 100 for c in result)

    def test_single_chunk_below_floor_preserved(self) -> None:
        # Only one chunk, no neighbours — preserve as-is rather than drop.
        chunks = [_make_chunk("word " * 30, ["A"], "c0")]
        result = _apply_floor_merging(chunks, soft_floor=100, soft_cap=1500)
        assert len(result) == 1
        assert result[0].token_count == 30

    def test_empty_list(self) -> None:
        result = _apply_floor_merging([], soft_floor=100, soft_cap=1500)
        assert result == []

    def test_chunk_already_above_floor_untouched(self) -> None:
        chunks = [
            _make_chunk("word " * 200, ["A"], "c0"),
            _make_chunk("word " * 200, ["B"], "c1"),
        ]
        result = _apply_floor_merging(chunks, soft_floor=100, soft_cap=1500)
        assert len(result) == 2
        assert all(c.chunk_strategy == "hierarchy" for c in result)


# ============================================================================
# chunk_document (integration)
# ============================================================================


class TestChunkDocument:
    def test_well_sized_hierarchy_produces_one_chunk_per_section(self) -> None:
        text = (
            "## Section A\n\n" + ("word " * 200) + "\n\n"
            "## Section B\n\n" + ("word " * 200) + "\n\n"
            "## Section C\n\n" + ("word " * 200)
        )
        chunks = chunk_document(text, "test_doc")
        assert len(chunks) == 3
        for c in chunks:
            assert c.chunk_strategy == "hierarchy"
            assert 100 <= c.token_count <= 1500

    def test_oversized_section_triggers_paragraph_fallback(self) -> None:
        # Build a section over the cap, with numbered-paragraph anchors at
        # line starts so the fallback splitter has structure to work with.
        body = "\n".join(
            f"1.{i} numbered paragraph point with content here and more text"
            for i in range(1, 300)
        )
        text = f"## Big Section\n\n{body}"
        chunks = chunk_document(text, "test_doc")
        # At least one chunk should be paragraph_fallback strategy.
        assert any(c.chunk_strategy == "paragraph_fallback" for c in chunks)
        # No chunk should exceed cap (with 10% slack for greedy split tail).
        assert all(c.token_count <= int(1500 * 1.1) for c in chunks)

    def test_sub_floor_section_merges_with_neighbour(self) -> None:
        text = (
            "## Big Section\n\n" + ("word " * 200) + "\n\n"
            "## Tiny Section\n\nshort body content.\n\n"  # under floor
            "## Another Big\n\n" + ("word " * 200)
        )
        chunks = chunk_document(text, "test_doc")
        # The tiny section should not appear as a standalone chunk's
        # primary section_path.
        primary_leaves = [c.section_path[-1] for c in chunks]
        assert "Tiny Section" not in primary_leaves
        # But its path should appear in some chunk's merged_section_paths.
        merged_paths = [p for c in chunks for p in c.merged_section_paths]
        assert ["Tiny Section"] in merged_paths

    def test_every_chunk_has_section_path(self) -> None:
        text = (
            "Preamble text content.\n\n"
            "## A\n\n" + ("word " * 200) + "\n\n"
            "### A.1\n\n" + ("word " * 200)
        )
        chunks = chunk_document(text, "test_doc")
        for c in chunks:
            assert len(c.section_path) >= 1

    def test_every_chunk_has_unique_id(self) -> None:
        text = "\n\n".join(
            f"## Section {i}\n\n" + ("word " * 200) for i in range(5)
        )
        chunks = chunk_document(text, "test_doc")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_carry_document_id_prefix(self) -> None:
        text = "## A\n\n" + ("word " * 200)
        chunks = chunk_document(text, "my_special_doc")
        for c in chunks:
            assert c.chunk_id.startswith("my_special_doc__")

    def test_empty_input_produces_no_chunks(self) -> None:
        assert chunk_document("", "test_doc") == []

    def test_thin_structure_document(self) -> None:
        # Mimics PRA SS1/21 shape: only one heading, body uses numbered
        # paragraphs and is far over cap.
        body = "\n".join(
            f"1.{i} body content for numbered paragraph with extra words"
            for i in range(1, 300)
        )
        text = f"## Introduction\n\n{body}"
        chunks = chunk_document(text, "test_doc")
        # All chunks should be paragraph_fallback (no hierarchy chunks since
        # the single section is over cap).
        assert all(c.chunk_strategy == "paragraph_fallback" for c in chunks)
        # All chunks share the same section_path.
        for c in chunks:
            assert c.section_path == ["Introduction"]

    def test_custom_thresholds_respected(self) -> None:
        # Smaller cap should trigger paragraph_fallback on a section that
        # would otherwise be hierarchy under defaults.
        text = "## A\n\n" + ("word " * 200)
        defaults = chunk_document(text, "test_doc")
        tight = chunk_document(text, "test_doc", soft_cap=100, soft_floor=20)
        assert defaults[0].chunk_strategy == "hierarchy"
        assert any(c.chunk_strategy == "paragraph_fallback" for c in tight)
