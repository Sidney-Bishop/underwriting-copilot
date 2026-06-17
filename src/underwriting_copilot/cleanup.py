"""Cleanup pre-pass for Docling markdown output.

Three rules, applied in order:

  1. UNIVERSAL: strip ``<!-- image -->`` placeholder lines that Docling emits
     for embedded images we are not retrieving (398 instances corpus-wide
     per probe 04).

  2. STRUCTURAL: detect markdown table blocks that appear verbatim 3+ times
     within a single document, strip all but the first occurrence. Catches
     table-of-contents widgets that some PDF layouts reprint at every
     section break — Munich Re's sustainability report being the
     load-bearing case at 36 repetitions of its main TOC.

     Note: the Munich Re report contains multiple distinct TOC variants
     (one with sub-sections expanded, one without, etc.) that share many
     rows. Each variant is correctly deduped to its first occurrence, so
     several TOC tables survive cleanup. The chunker's floor rule (D008)
     absorbs them into adjacent sections, so retrieval impact is minimal.

  3. DOCUMENT-SPECIFIC: rules keyed by ``document_id``, applied per-document.

     - ``eiopa_guidelines_system_of_governance``: replace
       ``glyph[.notdef]`` with a hyphen. The EIOPA PDF's subset font has no
       Unicode mapping for the hyphen/en-dash, so Docling falls back to the
       PostScript glyph name. 76 instances; EIOPA-only.

     - ``pra_ss1-21_operational_resilience``: strip the inline ``Superseded``
       watermark (which the PDF rendering embeds inside body text rather
       than as a separate overlay) and the repeating ``Please see: ...
       ss1/22-march-2022.pdf...`` reference line. The watermark didn't reach
       Probe 04's repeat threshold because it appears inline rather than as
       standalone lines, but it does poison body-text tokenisation.

This module is pure: input string + document_id, output cleaned string +
stats. No I/O, no global state. Easier to test, easier to compose into the
chunker.
"""

from __future__ import annotations

import re
from collections.abc import Callable


# -- Rule 1: universal image-placeholder strip -----------------------------

_IMAGE_PLACEHOLDER_RE = re.compile(r"^<!-- image -->\s*\n?", re.MULTILINE)


def strip_image_placeholders(text: str) -> tuple[str, int]:
    """Remove ``<!-- image -->`` lines.

    Returns (cleaned_text, n_removed).
    """
    n = len(_IMAGE_PLACEHOLDER_RE.findall(text))
    return _IMAGE_PLACEHOLDER_RE.sub("", text), n


# -- Rule 2: structural repeating-table dedup ------------------------------

# A markdown table is a run of consecutive lines starting with ``|``.
_TABLE_BLOCK_RE = re.compile(r"(?:^\|.*$\n?)+", re.MULTILINE)

# Tables shorter than this many rows are not worth deduplicating — they're
# probably legitimate small inline tables, not navigation widgets.
_MIN_TABLE_ROWS_FOR_DEDUP = 3

# A repeating table must appear at least this many times within a single
# document to be flagged as duplicate-noise. Matches Probe 04's threshold.
_MIN_REPEATS_FOR_DEDUP = 3


def dedupe_repeating_tables(text: str) -> tuple[str, int]:
    """Strip markdown tables that appear verbatim 3+ times within the input,
    keeping only the first occurrence of each.

    Returns (cleaned_text, n_removed_blocks).
    """
    blocks = list(_TABLE_BLOCK_RE.finditer(text))
    if not blocks:
        return text, 0

    # Normalize: ignore trailing whitespace differences across instances.
    normalized = [(m.span(), m.group(0).rstrip()) for m in blocks]

    counts: dict[str, int] = {}
    for _, content in normalized:
        if content.count("\n") + 1 < _MIN_TABLE_ROWS_FOR_DEDUP:
            continue
        counts[content] = counts.get(content, 0) + 1

    duplicates: set[str] = {
        content for content, n in counts.items() if n >= _MIN_REPEATS_FOR_DEDUP
    }

    if not duplicates:
        return text, 0

    seen: set[str] = set()
    n_removed = 0
    out_parts: list[str] = []
    cursor = 0
    for (start, end), content in normalized:
        out_parts.append(text[cursor:start])
        cursor = end
        if content in duplicates:
            if content in seen:
                n_removed += 1
                continue
            seen.add(content)
        out_parts.append(text[start:end])
    out_parts.append(text[cursor:])
    return "".join(out_parts), n_removed


# -- Rule 3: document-specific fixes ---------------------------------------

def _fix_eiopa_glyph(text: str) -> str:
    """EIOPA-only: replace the PostScript glyph fallback with a hyphen.

    See journal 2026-06-17 — the EIOPA PDF's subset font has no Unicode
    mapping for the hyphen character, so Docling emits ``glyph[.notdef]``
    (the PostScript glyph name for an undefined character) in its place.
    """
    return text.replace("glyph[.notdef]", "-")


# PRA SS1/21 watermark patterns. Two cases observed in body text:
#   1. ``Superseded Supervisory Statement | SS1/21`` — watermark prepended
#      to the title line.
#   2. ``...manage effectively. Superseded`` — watermark appended to a
#      sentence in body text.
# Both poison tokenisation by attaching the watermark to legitimate words.

_PRA_SS1_21_SUPERSEDED_PREFIX_RE = re.compile(
    r"(^|\n)Superseded\s+(?=\S)", re.MULTILINE
)
_PRA_SS1_21_SUPERSEDED_SUFFIX_RE = re.compile(
    r"(?<=\S)\s+Superseded(?=\s*\n|\s*$)", re.MULTILINE
)
_PRA_SS1_21_SS122_LINK_RE = re.compile(
    r"^Please see: https://www\.bankofengland\.co\.uk/[^\n]*ss1/22[^\n]*\n?",
    re.MULTILINE,
)


def _fix_pra_ss1_21(text: str) -> str:
    """PRA SS1/21-only: strip the inline 'Superseded' watermark and the
    repeating 'Please see ss1/22...' link."""
    # Suffix first, to avoid the prefix rule eating "Superseded" mid-line and
    # leaving an orphan trailing one.
    text = _PRA_SS1_21_SUPERSEDED_SUFFIX_RE.sub("", text)
    text = _PRA_SS1_21_SUPERSEDED_PREFIX_RE.sub(r"\1", text)
    text = _PRA_SS1_21_SS122_LINK_RE.sub("", text)
    return text


_DOC_SPECIFIC_RULES: dict[str, Callable[[str], str]] = {
    "eiopa_guidelines_system_of_governance": _fix_eiopa_glyph,
    "pra_ss1-21_operational_resilience": _fix_pra_ss1_21,
}


def apply_doc_specific(text: str, document_id: str) -> str:
    """Apply any cleanup rule registered for this ``document_id``. No-op if
    none registered."""
    fixer = _DOC_SPECIFIC_RULES.get(document_id)
    return fixer(text) if fixer else text


# -- Top-level pipeline ----------------------------------------------------

def clean(text: str, document_id: str) -> tuple[str, dict[str, int | bool]]:
    """Apply all cleanup rules in order.

    Returns (cleaned_text, stats), where stats has keys:
      - ``images_stripped`` (int): rule 1 count
      - ``tables_deduped`` (int): rule 2 count
      - ``doc_specific_applied`` (bool): rule 3 fired
    """
    text, images_stripped = strip_image_placeholders(text)
    text, tables_deduped = dedupe_repeating_tables(text)

    before_doc_specific = text
    text = apply_doc_specific(text, document_id)
    doc_specific_applied = text != before_doc_specific

    return text, {
        "images_stripped": images_stripped,
        "tables_deduped": tables_deduped,
        "doc_specific_applied": doc_specific_applied,
    }
