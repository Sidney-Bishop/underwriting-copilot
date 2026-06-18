"""Unit tests for ``src/underwriting_copilot/bm25.py`` per D011.

Tests are grouped by concern:

  - ``tokenize``: lower-case, regex word-split, stopword removal, Porter stem.
  - ``BM25Index.build``: vocab construction, df counts, IDF computation,
    average document length, reproducibility.
  - Sparse vector construction:
      * ``chunk_sparse_vector`` — BM25 contributions, OOV handling.
      * ``query_sparse_vector`` — presence indicators, dedupe, OOV handling.
  - The invariant that ``<query_vector, chunk_vector> == BM25 score``,
    pinned via a hand-computed expected value.
  - Serialisation round-trip via dict, file, and version-mismatch refusal.

All tests use inline string fixtures — no corpus files. Real-corpus
behaviour will be exercised by Probe 09 (forthcoming).
"""

from __future__ import annotations

import math

import pytest

from underwriting_copilot.bm25 import BM25Index, STOPWORDS, tokenize


# ============================================================================
# tokenize
# ============================================================================


class TestTokenize:
    def test_empty_string(self) -> None:
        assert tokenize("") == []

    def test_whitespace_only(self) -> None:
        assert tokenize("   \n\n   ") == []

    def test_lowercases(self) -> None:
        # Case-folding verified via identical stem output.
        assert tokenize("REGULATION") == tokenize("regulation")

    def test_drops_stopwords(self) -> None:
        # "the" is a stopword; "regulation" survives.
        toks = tokenize("the regulation")
        assert "the" not in toks
        assert len(toks) == 1

    def test_porter_stems_morphological_variants(self) -> None:
        # All three should collapse to the same stem.
        toks = tokenize("regulating regulations regulator")
        assert len(set(toks)) == 1
        assert all(t == toks[0] for t in toks)

    def test_punctuation_stripped(self) -> None:
        # \b\w+\b strips punctuation, keeps tokens.
        toks = tokenize("regulation; supervision, governance.")
        assert toks == ["regul", "supervis", "govern"]

    def test_numbers_preserved(self) -> None:
        # Regulatory document references should split but preserve parts.
        toks = tokenize("SS1/21")
        assert "ss1" in toks
        assert "21" in toks

    def test_preserves_token_order(self) -> None:
        toks = tokenize("alpha beta gamma delta")
        assert toks == ["alpha", "beta", "gamma", "delta"]

    def test_repeated_tokens_repeated_in_output(self) -> None:
        # Tokenisation preserves term frequency — Counter happens later.
        toks = tokenize("climate climate climate")
        assert len(toks) == 3
        assert len(set(toks)) == 1

    def test_regulatory_negation_words_preserved(self) -> None:
        # "not", "shall", "must" carry regulatory meaning and must survive
        # the stopword pass.
        toks = tokenize("shall not exceed")
        assert "not" in toks or "shall" in toks  # at least one survives stemming
        for word in ("shall", "not", "must"):
            assert word not in STOPWORDS


# ============================================================================
# BM25Index.build
# ============================================================================


class TestBM25IndexBuild:
    def test_empty_corpus_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            BM25Index.build([])

    def test_builds_vocab_from_all_texts(self) -> None:
        idx = BM25Index.build(["alpha beta", "beta gamma"])
        # Three unique stems across both texts.
        assert set(idx.vocab.keys()) == {"alpha", "beta", "gamma"}

    def test_vocab_ids_reproducible_alphabetical(self) -> None:
        # Building twice with the same corpus gives identical vocab ids —
        # critical because the ids are baked into stored sparse vectors.
        texts = ["climate risk", "operational resilience"]
        idx1 = BM25Index.build(texts)
        idx2 = BM25Index.build(texts)
        assert idx1.vocab == idx2.vocab

    def test_vocab_ids_assigned_alphabetically(self) -> None:
        idx = BM25Index.build(["gamma alpha beta"])
        # Alphabetical ordering → alpha=0, beta=1, gamma=2.
        assert idx.vocab["alpha"] < idx.vocab["beta"] < idx.vocab["gamma"]

    def test_document_frequencies(self) -> None:
        idx = BM25Index.build(["alpha beta", "beta gamma", "beta delta"])
        # "beta" in all 3 docs; "alpha" only in 1.
        assert idx.df["beta"] == 3
        assert idx.df["alpha"] == 1
        assert idx.df["gamma"] == 1
        assert idx.df["delta"] == 1

    def test_idf_higher_for_rarer_terms(self) -> None:
        idx = BM25Index.build([
            "common common common",
            "common common rare",
            "common common common",
            "common common common",
        ])
        # "rare" appears in 1/4 docs; "common" in 4/4.
        assert idx.idf["rare"] > idx.idf["common"]

    def test_avgdl_matches_average_token_count(self) -> None:
        # After stopword removal + stemming:
        #   "the regulation"      → ["regul"]            length 1
        #   "the climate risk"    → ["climat", "risk"]   length 2
        idx = BM25Index.build(["the regulation", "the climate risk"])
        assert idx.avgdl == pytest.approx(1.5)

    def test_corpus_size_matches_text_count(self) -> None:
        idx = BM25Index.build(["a", "b", "c", "d", "e"])
        assert idx.corpus_size == 5


# ============================================================================
# Sparse vector construction
# ============================================================================


def _three_doc_index() -> BM25Index:
    """Small reusable fixture: three docs with overlapping + unique terms."""
    return BM25Index.build([
        "climate change climate risk",   # → [climat, chang, climat, risk]
        "operational resilience risk",   # → [oper, resili, risk]
        "supervisory governance",         # → [supervisori, govern]
    ])


class TestChunkSparseVector:
    def test_returns_aligned_indices_values(self) -> None:
        idx = _three_doc_index()
        indices, values = idx.chunk_sparse_vector("climate risk")
        assert isinstance(indices, list)
        assert isinstance(values, list)
        assert len(indices) == len(values)

    def test_one_entry_per_unique_term(self) -> None:
        # "climate climate risk" → 2 unique stems.
        idx = _three_doc_index()
        indices, _ = idx.chunk_sparse_vector("climate climate risk")
        assert len(indices) == 2

    def test_values_are_positive(self) -> None:
        idx = _three_doc_index()
        _, values = idx.chunk_sparse_vector("climate risk")
        assert all(v > 0 for v in values)

    def test_empty_text_returns_empty(self) -> None:
        idx = _three_doc_index()
        indices, values = idx.chunk_sparse_vector("")
        assert indices == []
        assert values == []

    def test_oov_terms_silently_skipped(self) -> None:
        idx = _three_doc_index()
        # "quantum" was never in the build corpus.
        indices, _ = idx.chunk_sparse_vector("climate quantum")
        assert len(indices) == 1  # only "climat"

    def test_higher_tf_gives_higher_contribution(self) -> None:
        # Term saturation under k1 means the relationship is sub-linear,
        # but TF=3 should still give a strictly higher contribution than TF=1.
        idx = _three_doc_index()
        climat_id = idx.vocab["climat"]

        idx_low, vals_low = idx.chunk_sparse_vector("climate risk")
        idx_high, vals_high = idx.chunk_sparse_vector(
            "climate climate climate risk"
        )
        v_low = vals_low[idx_low.index(climat_id)]
        v_high = vals_high[idx_high.index(climat_id)]
        assert v_high > v_low


class TestQuerySparseVector:
    def test_values_are_presence_indicators(self) -> None:
        idx = _three_doc_index()
        _, values = idx.query_sparse_vector("climate risk")
        assert all(v == 1.0 for v in values)

    def test_oov_terms_skipped(self) -> None:
        idx = _three_doc_index()
        indices, _ = idx.query_sparse_vector("climate quantum")
        assert len(indices) == 1  # only "climat" in vocab

    def test_dedupes_repeated_query_terms(self) -> None:
        idx = _three_doc_index()
        indices, _ = idx.query_sparse_vector("climate climate climate")
        assert len(indices) == 1

    def test_empty_query_returns_empty(self) -> None:
        idx = _three_doc_index()
        indices, values = idx.query_sparse_vector("")
        assert indices == []
        assert values == []


# ============================================================================
# The core invariant: <query, chunk> = BM25 score
# ============================================================================


class TestBM25Invariant:
    def test_inner_product_equals_hand_computed_bm25(self) -> None:
        """Verify the inner product of query and chunk sparse vectors
        equals the BM25 score, cross-checked against a hand calculation.

        Tiny corpus:
            doc 1: "alpha beta"         (stems: [alpha, beta], length 2)
            doc 2: "alpha gamma gamma"  (stems: [alpha, gamma, gamma], length 3)

        N = 2, avgdl = (2 + 3) / 2 = 2.5
        df[alpha] = 2; df[beta] = 1; df[gamma] = 1
        idf[alpha] = ln((2 - 2 + 0.5) / (2 + 0.5) + 1) = ln(1.2) ≈ 0.18232

        For query "alpha" against doc 1 "alpha beta":
            tf[alpha] = 1, doc_len = 2, k1 = 1.5, b = 0.75
            len_norm = 1 - 0.75 + 0.75 * (2/2.5) = 0.25 + 0.6 = 0.85
            contrib(alpha) = idf * (tf * (k1+1)) / (tf + k1 * len_norm)
                           = 0.18232 * (1 * 2.5) / (1 + 1.5 * 0.85)
                           = 0.18232 * 2.5 / 2.275
                           ≈ 0.20035
        Inner product = 1.0 * 0.20035 = 0.20035.
        """
        idx = BM25Index.build(["alpha beta", "alpha gamma gamma"])

        chunk_indices, chunk_values = idx.chunk_sparse_vector("alpha beta")
        query_indices, query_values = idx.query_sparse_vector("alpha")

        # Compute inner product over sparse intersection.
        chunk_lookup = dict(zip(chunk_indices, chunk_values))
        score = sum(
            qv * chunk_lookup[qi]
            for qi, qv in zip(query_indices, query_values)
            if qi in chunk_lookup
        )

        # Verify against the hand-computed expected.
        expected_idf_alpha = math.log((2 - 2 + 0.5) / (2 + 0.5) + 1)
        expected_len_norm = 1 - 0.75 + 0.75 * (2 / 2.5)
        expected_contrib = (
            expected_idf_alpha * (1 * (1.5 + 1))
            / (1 + 1.5 * expected_len_norm)
        )
        assert score == pytest.approx(expected_contrib, rel=1e-9)


# ============================================================================
# Serialisation
# ============================================================================


class TestSerialisation:
    def test_to_dict_from_dict_round_trip(self) -> None:
        idx = _three_doc_index()
        idx2 = BM25Index.from_dict(idx.to_dict())
        assert idx == idx2

    def test_save_and_load(self, tmp_path) -> None:
        idx = _three_doc_index()
        path = tmp_path / "bm25_vocab.json"
        idx.save(path)
        idx2 = BM25Index.load(path)
        assert idx == idx2

    def test_version_mismatch_raises(self) -> None:
        idx = _three_doc_index()
        d = idx.to_dict()
        d["version"] = 99
        with pytest.raises(ValueError, match="version"):
            BM25Index.from_dict(d)

    def test_dict_format_uses_aligned_lists(self) -> None:
        # The serialisation deliberately stores vocab as an ordered list
        # so reload doesn't depend on dict ordering — pin that here.
        idx = _three_doc_index()
        d = idx.to_dict()
        assert isinstance(d["vocab"], list)
        assert isinstance(d["df"], list)
        assert isinstance(d["idf"], list)
        assert len(d["vocab"]) == len(d["df"]) == len(d["idf"])
