"""Unit tests for ``src/underwriting_copilot/retrieve.py``.

Tests focus on the two pure functions: ``reciprocal_rank_fusion`` and
``_build_filter``. The Retriever class itself is exercised by the demo
``python -m underwriting_copilot.retrieve`` against the real corpus —
mocking Qdrant + BGE-M3 in a unit test would test the mock, not the
integration.

The load-bearing RRF test pins the formula against hand-computed values
at full precision, so any future refactor of the score arithmetic has to
keep this green.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qdrant_client import models

from underwriting_copilot.retrieve import (
    DEFAULT_RRF_K,
    _build_filter,
    reciprocal_rank_fusion,
)


# ============================================================================
# Test helpers
# ============================================================================


def _hit(point_id, payload=None):
    """Minimal stand-in for ``qdrant_client.models.ScoredPoint`` —
    only ``.id`` and ``.payload`` are used by RRF."""
    return SimpleNamespace(
        id=point_id,
        payload=payload or {"chunk_id": f"c{point_id}"},
    )


# ============================================================================
# reciprocal_rank_fusion  — the load-bearing fusion logic
# ============================================================================


class TestReciprocalRankFusion:
    def test_empty_lists_return_empty(self) -> None:
        assert reciprocal_rank_fusion([], []) == []

    def test_dense_only_uses_dense_ranks(self) -> None:
        dense = [_hit(10), _hit(20)]
        fused = reciprocal_rank_fusion(dense, [], k=60)
        # 2 results, both from dense.
        assert len(fused) == 2
        # Rank 1: score = 1/(60+1) = 1/61
        assert fused[0][0] == 10
        assert fused[0][1] == pytest.approx(1 / 61)
        # Rank 2: score = 1/(60+2) = 1/62
        assert fused[1][0] == 20
        assert fused[1][1] == pytest.approx(1 / 62)

    def test_sparse_only_uses_sparse_ranks(self) -> None:
        sparse = [_hit(7), _hit(3)]
        fused = reciprocal_rank_fusion([], sparse, k=60)
        assert len(fused) == 2
        assert fused[0][0] == 7
        # Sparse rank recorded, dense rank None.
        assert fused[0][2] is None
        assert fused[0][3] == 1

    def test_overlap_sums_scores(self) -> None:
        # Point 5 appears in both lists at rank 1.
        dense = [_hit(5), _hit(9)]
        sparse = [_hit(5), _hit(11)]
        fused = reciprocal_rank_fusion(dense, sparse, k=60)
        # Point 5 wins: score = 1/61 + 1/61 = 2/61.
        assert fused[0][0] == 5
        assert fused[0][1] == pytest.approx(2 / 61)
        # Other points: each appears in one list at rank 2.
        scores = {pid: score for pid, score, _, _, _ in fused}
        assert scores[9] == pytest.approx(1 / 62)
        assert scores[11] == pytest.approx(1 / 62)

    def test_records_per_channel_ranks(self) -> None:
        dense = [_hit(1), _hit(2)]
        sparse = [_hit(2), _hit(3)]
        fused = reciprocal_rank_fusion(dense, sparse, k=60)
        ranks = {
            pid: (dense_rank, sparse_rank)
            for pid, _, dense_rank, sparse_rank, _ in fused
        }
        # Dense-only.
        assert ranks[1] == (1, None)
        # Both channels.
        assert ranks[2] == (2, 1)
        # Sparse-only.
        assert ranks[3] == (None, 2)

    def test_sorted_by_score_descending(self) -> None:
        dense = [_hit(10), _hit(20), _hit(30)]
        sparse = [_hit(20)]  # boosts 20
        fused = reciprocal_rank_fusion(dense, sparse, k=60)
        scores = [score for _, score, _, _, _ in fused]
        assert scores == sorted(scores, reverse=True)
        # Point 20 wins because it's in both channels.
        assert fused[0][0] == 20

    def test_payload_propagates(self) -> None:
        dense = [_hit(1, payload={"chunk_id": "abc", "title": "Doc A"})]
        fused = reciprocal_rank_fusion(dense, [], k=60)
        assert fused[0][4] == {"chunk_id": "abc", "title": "Doc A"}

    def test_k_zero_gives_full_weight_to_rank_1(self) -> None:
        # With k=0, rank 1 = score 1/(0+1) = 1.0.
        dense = [_hit(1)]
        fused = reciprocal_rank_fusion(dense, [], k=0)
        assert fused[0][1] == pytest.approx(1.0)

    def test_against_hand_computed(self) -> None:
        # The pinned formula check.
        #   Point 1: dense rank 1, sparse rank 3 → 1/61 + 1/63.
        #   Point 2: dense rank 2 only → 1/62.
        #   Point 3: sparse rank 1 only → 1/61.
        #   Point 4: sparse rank 2 only → 1/62.
        dense = [_hit(1), _hit(2)]
        sparse = [_hit(3), _hit(4), _hit(1)]
        fused = reciprocal_rank_fusion(dense, sparse, k=60)
        scores = {pid: score for pid, score, _, _, _ in fused}
        assert scores[1] == pytest.approx(1 / 61 + 1 / 63)
        assert scores[2] == pytest.approx(1 / 62)
        assert scores[3] == pytest.approx(1 / 61)
        assert scores[4] == pytest.approx(1 / 62)
        # Point 1 has highest score.
        assert fused[0][0] == 1


# ============================================================================
# _build_filter
# ============================================================================


class TestBuildFilter:
    def test_no_filters_returns_none(self) -> None:
        result = _build_filter(
            exclude_superseded=False,
            issuer_type=None,
            jurisdiction=None,
        )
        assert result is None

    def test_exclude_superseded_only(self) -> None:
        result = _build_filter(
            exclude_superseded=True,
            issuer_type=None,
            jurisdiction=None,
        )
        assert isinstance(result, models.Filter)
        assert len(result.must) == 1
        assert isinstance(result.must[0], models.IsNullCondition)

    def test_issuer_type_filter(self) -> None:
        result = _build_filter(
            exclude_superseded=False,
            issuer_type="regulator",
            jurisdiction=None,
        )
        assert isinstance(result, models.Filter)
        assert len(result.must) == 1
        cond = result.must[0]
        assert isinstance(cond, models.FieldCondition)
        assert cond.key == "issuer_type"

    def test_jurisdiction_filter(self) -> None:
        result = _build_filter(
            exclude_superseded=False,
            issuer_type=None,
            jurisdiction="UK",
        )
        assert isinstance(result, models.Filter)
        assert len(result.must) == 1
        cond = result.must[0]
        assert isinstance(cond, models.FieldCondition)
        assert cond.key == "jurisdiction"

    def test_combined_filters(self) -> None:
        result = _build_filter(
            exclude_superseded=True,
            issuer_type="regulator",
            jurisdiction="UK",
        )
        assert isinstance(result, models.Filter)
        assert len(result.must) == 3

    def test_default_rrf_k_constant(self) -> None:
        # Sanity: the documented default matches the RRF paper.
        assert DEFAULT_RRF_K == 60
