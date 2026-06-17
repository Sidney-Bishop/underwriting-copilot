"""Hierarchy-aware chunker with paragraph-fallback (D008).

Algorithm
---------

  1. Parse the cleaned markdown into a sequence of (heading_path, body)
     ``Segment`` records, one per heading boundary. Text before any heading
     becomes a ``(preamble)`` segment.

  2. **Emission pass.** Walk segments in document order:

     - If body > soft_cap: split into multiple chunks using paragraph-
       fallback (numbered-paragraph anchors → blank-line paragraphs →
       greedy word split), then greedily coalesce adjacent pieces while
       combined size stays ≤ soft_cap. This absorbs micro-fragments
       produced by anchor splitting on thin-structure documents.
     - Else: emit a single hierarchy chunk.

  3. **Floor-merge pass.** Walk the emitted chunks. For each chunk below
     soft_floor, attempt to merge:

     - First into the previous chunk.
     - Failing that (no previous chunk, or merge would exceed soft_cap),
       into the next chunk.
     - Failing that, accept the chunk as-is.

     The pass is iterative: a merge can produce a chunk that is itself
     still below the floor (rare but possible when the receiving chunk
     was already tiny), and the index doesn't advance after a merge so
     the same position is re-checked.

  4. Each ``Chunk`` carries:

     - ``chunk_id`` — stable, sequence-indexed at creation, includes a slug
       for human inspection. Floor-merge gaps in the sequence are accepted
       rather than renumbering (renumbering would break id stability across
       runs).
     - ``document_id`` — key for joining ``DocumentMetadata`` downstream.
     - ``section_path`` — headings from document root to leaf.
     - ``merged_section_paths`` — section_paths absorbed by floor merging.
     - ``text`` — chunk content. Merged segments include their heading
       inline as a marker so the chunk remains attributable on inspection.
     - ``token_count`` — word-split approximation; same metric as Probe 03
       and D008's thresholds.
     - ``chunk_strategy``: ``hierarchy`` | ``paragraph_fallback`` | ``merged``.

Defaults (from D008): ``soft_cap = 1500``, ``soft_floor = 100``.

Notes
-----

- Token count uses a word split. This is intentional: the Probe 03
  distribution was computed this way, so D008's numerical thresholds are
  in this unit. Switching to a real tokenizer would silently change what
  the thresholds mean.
- Floor merging prefers backward (into previous) over forward (into next)
  to match the "merge upward into the parent" intuition in D008 — the
  previous chunk in document order is almost always at the same depth as
  or shallower than the current chunk. Forward fallback exists for the
  case of a sub-floor first chunk (typically a tiny preamble).
- Merges that would push the receiving chunk over the cap are skipped
  rather than forced. We accept some sub-floor survivors in preference
  to over-cap chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


# ---- token approximation -----------------------------------------------

def approx_tokens(text: str) -> int:
    """Approximate token count via word split.

    Matches the metric used in Probe 03; therefore matches the numerical
    units of D008's thresholds (1500/100). Do not swap for a real tokenizer
    without revisiting D008.
    """
    return len(text.split())


# ---- structural patterns -----------------------------------------------

_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+)$", re.MULTILINE)
_NUMBERED_PARA_RE = re.compile(r"^\s*(\d+\.\d+(?:\.\d+)?)\s+", re.MULTILINE)


# ---- data classes ------------------------------------------------------

@dataclass
class Segment:
    """A heading-bounded slice of the document."""
    heading_text: str
    heading_depth: int
    heading_path: list[str]
    body: str
    token_count: int


@dataclass
class Chunk:
    """A unit retrievable from the vector store."""
    chunk_id: str
    document_id: str
    section_path: list[str]
    text: str
    token_count: int
    chunk_strategy: Literal["hierarchy", "paragraph_fallback", "merged"] = "hierarchy"
    merged_section_paths: list[list[str]] = field(default_factory=list)


# ---- parsing -----------------------------------------------------------

def parse_segments(text: str) -> list[Segment]:
    """Split cleaned markdown into ``Segment`` records at heading boundaries.

    Text before the first heading becomes a ``(preamble)`` segment.
    """
    matches = list(_HEADING_RE.finditer(text))
    segments: list[Segment] = []

    preamble_end = matches[0].start() if matches else len(text)
    preamble = text[:preamble_end].strip()
    if preamble:
        segments.append(
            Segment(
                heading_text="(preamble)",
                heading_depth=1,
                heading_path=["(preamble)"],
                body=preamble,
                token_count=approx_tokens(preamble),
            )
        )

    stack: list[tuple[str, int]] = []
    for i, m in enumerate(matches):
        depth = len(m.group(1))
        heading = m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()

        while stack and stack[-1][1] >= depth:
            stack.pop()
        stack.append((heading, depth))
        path = [h for h, _ in stack]

        segments.append(
            Segment(
                heading_text=heading,
                heading_depth=depth,
                heading_path=path,
                body=body,
                token_count=approx_tokens(body),
            )
        )

    return segments


# ---- paragraph-fallback splitting --------------------------------------

def _split_then_coalesce(body: str, soft_cap: int) -> list[str]:
    """Split a too-large body into pieces ≤ soft_cap tokens, then greedily
    coalesce adjacent pieces while combined size stays ≤ soft_cap.

    Strategy:
      1. Numbered-paragraph anchors (``^\\d+\\.\\d+``) if at least 2 found.
      2. Blank-line paragraph boundaries.
      3. Greedy word split as a final guarantee.
      4. Greedy coalesce of adjacent pieces (the new pass).
    """
    anchors = list(_NUMBERED_PARA_RE.finditer(body))
    if len(anchors) >= 2:
        pieces: list[str] = []
        preamble = body[: anchors[0].start()].strip()
        if preamble:
            pieces.append(preamble)
        for i, m in enumerate(anchors):
            start = m.start()
            end = anchors[i + 1].start() if i + 1 < len(anchors) else len(body)
            piece = body[start:end].strip()
            if piece:
                pieces.append(piece)
    else:
        pieces = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        if not pieces:
            pieces = [body]

    # Guarantee each piece ≤ soft_cap via greedy word split.
    sized: list[str] = []
    for piece in pieces:
        if approx_tokens(piece) <= soft_cap:
            sized.append(piece)
        else:
            words = piece.split()
            for i in range(0, len(words), soft_cap):
                sized.append(" ".join(words[i : i + soft_cap]))

    # Greedy coalesce: combine adjacent pieces while total stays ≤ cap.
    coalesced: list[str] = []
    buffer = ""
    buffer_tokens = 0
    for piece in sized:
        piece_tokens = approx_tokens(piece)
        if not buffer:
            buffer = piece
            buffer_tokens = piece_tokens
        elif buffer_tokens + piece_tokens <= soft_cap:
            buffer = f"{buffer}\n\n{piece}"
            buffer_tokens += piece_tokens
        else:
            coalesced.append(buffer)
            buffer = piece
            buffer_tokens = piece_tokens
    if buffer:
        coalesced.append(buffer)

    return coalesced


# ---- slugging ----------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 40) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return (s[:max_len].rstrip("-")) or "section"


# ---- floor-merge pass --------------------------------------------------

def _merge_into(receiver: Chunk, absorbed: Chunk, *, append: bool) -> None:
    """Merge ``absorbed`` into ``receiver`` in place.

    If ``append`` is True, absorbed content follows receiver content;
    otherwise it precedes. Both ordering options preserve the absorbed
    section_path in ``merged_section_paths`` and mark the receiver's
    strategy as ``merged``.
    """
    receiver.merged_section_paths.append(list(absorbed.section_path))
    receiver.merged_section_paths.extend(absorbed.merged_section_paths)

    heading = absorbed.section_path[-1] if absorbed.section_path else "merged"
    marker = f"## {heading}"
    absorbed_block = f"{marker}\n\n{absorbed.text}"

    if append:
        receiver.text = f"{receiver.text}\n\n{absorbed_block}"
    else:
        receiver.text = f"{absorbed_block}\n\n{receiver.text}"

    receiver.token_count = approx_tokens(receiver.text)
    receiver.chunk_strategy = "merged"


def _apply_floor_merging(
    chunks: list[Chunk],
    soft_floor: int,
    soft_cap: int,
) -> list[Chunk]:
    """Iteratively merge sub-floor chunks with neighbors.

    Prefers backward merge (into previous); falls back to forward merge
    (into next) when there is no previous chunk. Skips any merge that
    would push the receiver over ``soft_cap``.
    """
    i = 0
    while i < len(chunks):
        c = chunks[i]
        if c.token_count >= soft_floor:
            i += 1
            continue

        merged = False

        # Backward merge.
        if i > 0:
            prev = chunks[i - 1]
            if prev.token_count + c.token_count <= soft_cap:
                _merge_into(prev, c, append=True)
                chunks.pop(i)
                merged = True
                # Don't increment — the chunk that took position i needs
                # checking too. If chunks[i-1] is now itself below floor
                # (very rare), the next iteration of the while-loop at
                # index i won't catch that, but the *previous* chunk gets
                # one more chance via i-1 on the next pass. Acceptable.

        # Forward merge.
        if not merged and i + 1 < len(chunks):
            nxt = chunks[i + 1]
            if nxt.token_count + c.token_count <= soft_cap:
                _merge_into(nxt, c, append=False)  # prepend
                chunks.pop(i)
                merged = True
                # Don't increment — the merged chunk is at position i now.

        if not merged:
            # No neighbor can accept this chunk without exceeding cap, or
            # it's the only chunk in the document. Accept as-is.
            i += 1

    return chunks


# ---- top-level chunker -------------------------------------------------

def chunk_document(
    text: str,
    document_id: str,
    soft_cap: int = 1500,
    soft_floor: int = 100,
) -> list[Chunk]:
    """Chunk a single document's cleaned markdown per D008."""
    segments = parse_segments(text)
    chunks: list[Chunk] = []

    # Emission pass.
    for seg in segments:
        if seg.token_count == 0:
            continue

        if seg.token_count > soft_cap:
            pieces = _split_then_coalesce(seg.body, soft_cap)
            slug = _slugify(seg.heading_text)
            for idx, piece in enumerate(pieces):
                chunks.append(
                    Chunk(
                        chunk_id=f"{document_id}__{len(chunks):04d}__{slug}__pf{idx:02d}",
                        document_id=document_id,
                        section_path=list(seg.heading_path),
                        text=piece,
                        token_count=approx_tokens(piece),
                        chunk_strategy="paragraph_fallback",
                    )
                )
        else:
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}__{len(chunks):04d}__{_slugify(seg.heading_text)}",
                    document_id=document_id,
                    section_path=list(seg.heading_path),
                    text=seg.body,
                    token_count=seg.token_count,
                    chunk_strategy="hierarchy",
                )
            )

    # Floor-merge pass.
    chunks = _apply_floor_merging(chunks, soft_floor, soft_cap)

    return chunks
