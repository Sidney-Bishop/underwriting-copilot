"""Unit tests for ``src/underwriting_copilot/embed.py``.

The full-pipeline integration test is ``python -m underwriting_copilot.embed``
against the real corpus — that exercises BGE-M3 end-to-end. These unit
tests pin the pieces that can be tested in isolation:

  - ``cls_l2_pool``: pooling correctness (CLS extraction + L2 normalisation).
    Load-bearing per D010 — the test pins the pooling that gets used in
    production so a future refactor can't silently revert to mean pooling.
  - ``_iter_chunks``: JSONL reading, ordering, blank-line handling.
  - ``write_embeddings_jsonl``: per-document grouping, file structure.
"""

from __future__ import annotations

import json

import mlx.core as mx
import pytest

from underwriting_copilot.embed import (
    EmbeddedChunk,
    _iter_chunks,
    cls_l2_pool,
    write_embeddings_jsonl,
)


# ============================================================================
# cls_l2_pool  (D010 pooling pinned here)
# ============================================================================


class _FakeOutputs:
    """Minimal stand-in for the mlx-embeddings model output object —
    just enough surface area for ``cls_l2_pool``."""

    def __init__(self, hidden_state: mx.array) -> None:
        self.last_hidden_state = hidden_state


class TestClsL2Pool:
    def test_extracts_cls_token_position_zero(self) -> None:
        # Distinct values per sequence position so CLS extraction is
        # observable — the test would fail if cls_l2_pool ever did mean
        # pooling instead.
        # Shape: (batch=1, seq_len=3, dim=4)
        hidden = mx.array(
            [
                [
                    [1.0, 0.0, 0.0, 0.0],  # CLS (position 0)
                    [0.0, 1.0, 0.0, 0.0],  # not CLS
                    [0.0, 0.0, 1.0, 0.0],  # not CLS
                ]
            ]
        )
        pooled = cls_l2_pool(_FakeOutputs(hidden))
        mx.eval(pooled)
        assert pooled.shape == (1, 4)
        # CLS is already unit-norm so output equals input.
        assert pooled[0].tolist() == [1.0, 0.0, 0.0, 0.0]

    def test_l2_normalises_to_unit_length(self) -> None:
        # CLS has non-unit norm; output must have L2 norm = 1.
        hidden = mx.array([[[3.0, 4.0, 0.0]]])  # norm = 5
        pooled = cls_l2_pool(_FakeOutputs(hidden))
        norm = float(mx.linalg.norm(pooled[0]).item())
        assert norm == pytest.approx(1.0, rel=1e-6)
        # Direction preserved (3/5, 4/5, 0).
        assert pooled[0, 0].item() == pytest.approx(0.6, rel=1e-6)
        assert pooled[0, 1].item() == pytest.approx(0.8, rel=1e-6)

    def test_preserves_batch_dimension(self) -> None:
        hidden = mx.array(
            [
                [[1.0, 0.0]],
                [[0.0, 1.0]],
            ]
        )
        pooled = cls_l2_pool(_FakeOutputs(hidden))
        assert pooled.shape == (2, 2)

    def test_independent_normalisation_per_batch_item(self) -> None:
        # Two items with different norms — each should normalise independently.
        hidden = mx.array(
            [
                [[3.0, 4.0]],   # norm 5
                [[5.0, 12.0]],  # norm 13
            ]
        )
        pooled = cls_l2_pool(_FakeOutputs(hidden))
        n0 = float(mx.linalg.norm(pooled[0]).item())
        n1 = float(mx.linalg.norm(pooled[1]).item())
        assert n0 == pytest.approx(1.0, rel=1e-6)
        assert n1 == pytest.approx(1.0, rel=1e-6)


# ============================================================================
# _iter_chunks  (JSONL I/O)
# ============================================================================


class TestIterChunks:
    def test_reads_multiple_jsonl_files_alphabetically(self, tmp_path) -> None:
        (tmp_path / "b.jsonl").write_text(
            json.dumps({"chunk_id": "b1"}) + "\n"
        )
        (tmp_path / "a.jsonl").write_text(
            json.dumps({"chunk_id": "a1"}) + "\n"
        )
        ids = [c["chunk_id"] for c in _iter_chunks(tmp_path)]
        assert ids == ["a1", "b1"]

    def test_preserves_within_file_order(self, tmp_path) -> None:
        (tmp_path / "doc.jsonl").write_text(
            "\n".join(
                json.dumps({"chunk_id": f"c{i}"}) for i in range(5)
            )
            + "\n"
        )
        ids = [c["chunk_id"] for c in _iter_chunks(tmp_path)]
        assert ids == [f"c{i}" for i in range(5)]

    def test_skips_blank_lines(self, tmp_path) -> None:
        (tmp_path / "doc.jsonl").write_text(
            json.dumps({"chunk_id": "c1"})
            + "\n\n\n"
            + json.dumps({"chunk_id": "c2"})
            + "\n"
        )
        ids = [c["chunk_id"] for c in _iter_chunks(tmp_path)]
        assert ids == ["c1", "c2"]

    def test_empty_dir_yields_nothing(self, tmp_path) -> None:
        assert list(_iter_chunks(tmp_path)) == []

    def test_ignores_non_jsonl_files(self, tmp_path) -> None:
        (tmp_path / "data.jsonl").write_text(
            json.dumps({"chunk_id": "c1"}) + "\n"
        )
        (tmp_path / "README.md").write_text("# not jsonl")
        ids = [c["chunk_id"] for c in _iter_chunks(tmp_path)]
        assert ids == ["c1"]


# ============================================================================
# write_embeddings_jsonl
# ============================================================================


def _e(chunk_id: str, document_id: str) -> EmbeddedChunk:
    """Test helper: minimal EmbeddedChunk with predictable fields."""
    return EmbeddedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        section_path=["root"],
        text="text",
        vector=[0.1, 0.2, 0.3],
    )


class TestWriteEmbeddingsJsonl:
    def test_groups_by_document_id(self, tmp_path) -> None:
        embedded = [
            _e("a1", "doc_a"),
            _e("b1", "doc_b"),
            _e("a2", "doc_a"),
        ]
        counts = write_embeddings_jsonl(embedded, tmp_path)
        assert counts == {"doc_a": 2, "doc_b": 1}
        assert (tmp_path / "doc_a.jsonl").exists()
        assert (tmp_path / "doc_b.jsonl").exists()

    def test_jsonl_is_parseable(self, tmp_path) -> None:
        embedded = [_e("a1", "doc_a"), _e("a2", "doc_a")]
        write_embeddings_jsonl(embedded, tmp_path)
        lines = (tmp_path / "doc_a.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
        parsed = [json.loads(line) for line in lines]
        assert parsed[0]["chunk_id"] == "a1"
        assert parsed[1]["chunk_id"] == "a2"

    def test_jsonl_preserves_vector_field(self, tmp_path) -> None:
        embedded = [_e("a1", "doc_a")]
        write_embeddings_jsonl(embedded, tmp_path)
        loaded = json.loads(
            (tmp_path / "doc_a.jsonl").read_text().strip()
        )
        assert loaded["vector"] == [0.1, 0.2, 0.3]
        assert loaded["section_path"] == ["root"]
        assert loaded["text"] == "text"

    def test_empty_input_creates_no_files(self, tmp_path) -> None:
        counts = write_embeddings_jsonl([], tmp_path)
        assert counts == {}
        assert list(tmp_path.iterdir()) == []

    def test_creates_output_dir_if_missing(self, tmp_path) -> None:
        target = tmp_path / "nested" / "embeddings"
        write_embeddings_jsonl([_e("a1", "doc_a")], target)
        assert target.is_dir()
        assert (target / "doc_a.jsonl").exists()
