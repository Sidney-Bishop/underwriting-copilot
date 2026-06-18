"""Unit + integration tests for ``src/underwriting_copilot/index.py``.

Most tests are pure-function unit tests for the projection and I/O
helpers. One integration test exercises ``build_qdrant_collection``
against an in-memory Qdrant — cheap enough to keep in the unit suite.

The full-pipeline integration test is
``python -m underwriting_copilot.index`` against the real corpus.

``DocumentMetadata`` is faked with ``SimpleNamespace`` so these tests
don't break if the Pydantic schema in metadata.py evolves — they only
care that ``chunk_to_payload`` reaches the documented attributes.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from qdrant_client import QdrantClient, models

from underwriting_copilot.bm25 import BM25Index
from underwriting_copilot.index import (
    COLLECTION_NAME,
    DENSE_DIM,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    _iter_points,
    _load_chunks,
    _load_embeddings,
    _metadata_by_document_id,
    _wipe_directory,
    build_qdrant_collection,
    chunk_to_payload,
)


# ============================================================================
# Test fixtures
# ============================================================================


def _make_doc_metadata(
    document_id: str = "test_doc",
    issuer_type: str = "regulator",
    superseded_by: str | None = None,
) -> SimpleNamespace:
    """Stand-in for DocumentMetadata using SimpleNamespace.

    Avoids importing the real Pydantic class so the tests stay tied to
    the documented attribute surface, not the validator's internals.
    """
    return SimpleNamespace(
        document_id=document_id,
        title="Test Doc Title",
        issuer="Test Issuer",
        issuer_type=issuer_type,
        jurisdiction="GB",
        document_type="supervisory_statement",
        effective_date="2024-01-01",
        version="1.0",
        superseded_by=superseded_by,
        source_url="https://example.com/test_doc.pdf",
        topics=["climate", "operational_resilience"],
    )


def _make_chunk(
    chunk_id: str = "test_doc__0001__intro",
    document_id: str = "test_doc",
    text: str = "sample chunk text",
) -> dict:
    """Minimal chunk dict matching the chunker's JSONL schema."""
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "section_path": ["root", "intro"],
        "merged_section_paths": [],
        "chunk_strategy": "hierarchy",
        "token_count": 100,
        "text": text,
    }


# ============================================================================
# chunk_to_payload — projection logic
# ============================================================================


class TestChunkToPayload:
    def test_all_seventeen_fields_present(self) -> None:
        payload = chunk_to_payload(_make_chunk(), _make_doc_metadata())
        expected = {
            # Chunk fields
            "chunk_id", "document_id", "section_path",
            "merged_section_paths", "chunk_strategy", "token_count",
            "text",
            # Metadata fields
            "title", "issuer", "issuer_type", "jurisdiction",
            "document_type", "effective_date", "version",
            "superseded_by", "source_url", "topics",
        }
        assert set(payload.keys()) == expected
        assert len(payload) == 17

    def test_chunk_fields_propagate(self) -> None:
        chunk = _make_chunk(chunk_id="c1", text="real text", document_id="d1")
        payload = chunk_to_payload(chunk, _make_doc_metadata(document_id="d1"))
        assert payload["chunk_id"] == "c1"
        assert payload["text"] == "real text"
        assert payload["document_id"] == "d1"
        assert payload["section_path"] == ["root", "intro"]
        assert payload["token_count"] == 100

    def test_metadata_fields_propagate(self) -> None:
        meta = _make_doc_metadata(issuer_type="reinsurer")
        payload = chunk_to_payload(_make_chunk(), meta)
        assert payload["issuer_type"] == "reinsurer"
        assert payload["title"] == "Test Doc Title"
        assert payload["topics"] == ["climate", "operational_resilience"]
        assert payload["jurisdiction"] == "GB"

    def test_handles_none_superseded_by(self) -> None:
        meta = _make_doc_metadata(superseded_by=None)
        payload = chunk_to_payload(_make_chunk(), meta)
        assert payload["superseded_by"] is None

    def test_propagates_superseded_by_value(self) -> None:
        # Real example: PRA SS3/19 is superseded by SS5/25.
        meta = _make_doc_metadata(superseded_by="pra_ss5-25_climate")
        payload = chunk_to_payload(_make_chunk(), meta)
        assert payload["superseded_by"] == "pra_ss5-25_climate"

    def test_missing_merged_section_paths_defaults_to_empty(self) -> None:
        chunk = _make_chunk()
        del chunk["merged_section_paths"]
        payload = chunk_to_payload(chunk, _make_doc_metadata())
        assert payload["merged_section_paths"] == []

    def test_effective_date_stringified(self) -> None:
        # Whether the Pydantic model gives us a date object or string,
        # payload must hold a string (Qdrant payload is JSON).
        payload = chunk_to_payload(_make_chunk(), _make_doc_metadata())
        assert isinstance(payload["effective_date"], str)


# ============================================================================
# _load_chunks / _load_embeddings
# ============================================================================


class TestLoadChunks:
    def test_keys_by_chunk_id(self, tmp_path) -> None:
        (tmp_path / "doc.jsonl").write_text(
            json.dumps({"chunk_id": "c1", "text": "a"}) + "\n"
            + json.dumps({"chunk_id": "c2", "text": "b"}) + "\n"
        )
        chunks = _load_chunks(tmp_path)
        assert set(chunks.keys()) == {"c1", "c2"}

    def test_reads_multiple_files(self, tmp_path) -> None:
        (tmp_path / "a.jsonl").write_text(json.dumps({"chunk_id": "c1"}) + "\n")
        (tmp_path / "b.jsonl").write_text(json.dumps({"chunk_id": "c2"}) + "\n")
        chunks = _load_chunks(tmp_path)
        assert len(chunks) == 2

    def test_skips_blank_lines(self, tmp_path) -> None:
        (tmp_path / "doc.jsonl").write_text(
            json.dumps({"chunk_id": "c1"}) + "\n\n\n"
            + json.dumps({"chunk_id": "c2"}) + "\n"
        )
        chunks = _load_chunks(tmp_path)
        assert len(chunks) == 2

    def test_empty_dir_returns_empty_dict(self, tmp_path) -> None:
        assert _load_chunks(tmp_path) == {}


class TestLoadEmbeddings:
    def test_keys_by_chunk_id_with_vector(self, tmp_path) -> None:
        (tmp_path / "doc.jsonl").write_text(
            json.dumps({"chunk_id": "c1", "vector": [0.1, 0.2]}) + "\n"
        )
        emb = _load_embeddings(tmp_path)
        assert emb == {"c1": [0.1, 0.2]}

    def test_empty_dir_returns_empty_dict(self, tmp_path) -> None:
        assert _load_embeddings(tmp_path) == {}


# ============================================================================
# _metadata_by_document_id  — handles list-or-dict from load_corpus_metadata
# ============================================================================


class TestMetadataByDocumentId:
    def test_list_converted_to_dict(self) -> None:
        docs = [
            _make_doc_metadata(document_id="d1"),
            _make_doc_metadata(document_id="d2"),
        ]
        result = _metadata_by_document_id(docs)
        assert set(result.keys()) == {"d1", "d2"}

    def test_dict_rekeyed_by_document_id(self) -> None:
        # corpus_metadata.toml is keyed by FILENAME, not document_id;
        # the adapter must re-key by the inner document_id field so
        # downstream lookups against chunks' document_id work.
        docs = {
            "some_filename.pdf": _make_doc_metadata(document_id="real_doc_id"),
        }
        result = _metadata_by_document_id(docs)
        assert set(result.keys()) == {"real_doc_id"}


# ============================================================================
# _wipe_directory
# ============================================================================


class TestWipeDirectory:
    def test_removes_existing_dir(self, tmp_path) -> None:
        target = tmp_path / "to_wipe"
        target.mkdir()
        (target / "f.txt").write_text("x")
        _wipe_directory(target)
        assert not target.exists()

    def test_noop_when_dir_missing(self, tmp_path) -> None:
        target = tmp_path / "never_existed"
        _wipe_directory(target)  # must not raise

    def test_recursive_wipe(self, tmp_path) -> None:
        target = tmp_path / "to_wipe"
        nested = target / "deep" / "sub"
        nested.mkdir(parents=True)
        (nested / "f.txt").write_text("x")
        _wipe_directory(target)
        assert not target.exists()


# ============================================================================
# build_qdrant_collection  — integration with in-memory Qdrant
# ============================================================================


class TestBuildQdrantCollection:
    def test_creates_collection_with_named_dense_and_sparse(self) -> None:
        client = QdrantClient(":memory:")
        build_qdrant_collection(client)
        info = client.get_collection(COLLECTION_NAME)

        # Dense channel.
        vectors_config = info.config.params.vectors
        assert DENSE_VECTOR_NAME in vectors_config
        assert vectors_config[DENSE_VECTOR_NAME].size == DENSE_DIM
        assert (
            vectors_config[DENSE_VECTOR_NAME].distance
            == models.Distance.COSINE
        )

        # Sparse channel.
        sparse_config = info.config.params.sparse_vectors or {}
        assert SPARSE_VECTOR_NAME in sparse_config


# ============================================================================
# _iter_points  — point construction with fakes
# ============================================================================


class TestIterPoints:
    def test_yields_one_point_per_chunk(self) -> None:
        chunks = {
            "c1": _make_chunk(chunk_id="c1", document_id="d1", text="alpha"),
            "c2": _make_chunk(chunk_id="c2", document_id="d1", text="beta"),
        }
        embeddings = {
            "c1": [0.1] * DENSE_DIM,
            "c2": [0.2] * DENSE_DIM,
        }
        metadata = {"d1": _make_doc_metadata(document_id="d1")}
        bm25 = BM25Index.build(["alpha sample text", "beta sample text"])

        points = list(_iter_points(chunks, embeddings, metadata, bm25))
        assert len(points) == 2

    def test_raises_on_missing_embedding(self) -> None:
        chunks = {"c1": _make_chunk(chunk_id="c1")}
        embeddings: dict[str, list[float]] = {}
        metadata = {"test_doc": _make_doc_metadata()}
        bm25 = BM25Index.build(["sample text"])

        with pytest.raises(KeyError, match="no embedding"):
            list(_iter_points(chunks, embeddings, metadata, bm25))

    def test_raises_on_unknown_document_id(self) -> None:
        chunks = {
            "c1": _make_chunk(chunk_id="c1", document_id="unknown_doc"),
        }
        embeddings = {"c1": [0.1] * DENSE_DIM}
        metadata = {"test_doc": _make_doc_metadata()}  # mismatched id
        bm25 = BM25Index.build(["sample text"])

        with pytest.raises(KeyError, match="corpus_metadata"):
            list(_iter_points(chunks, embeddings, metadata, bm25))

    def test_points_have_both_dense_and_sparse_vectors(self) -> None:
        chunks = {"c1": _make_chunk(chunk_id="c1", text="alpha beta")}
        embeddings = {"c1": [0.1] * DENSE_DIM}
        metadata = {"test_doc": _make_doc_metadata()}
        bm25 = BM25Index.build(["alpha beta gamma"])

        points = list(_iter_points(chunks, embeddings, metadata, bm25))
        assert DENSE_VECTOR_NAME in points[0].vector
        assert SPARSE_VECTOR_NAME in points[0].vector
        assert points[0].vector[DENSE_VECTOR_NAME] == [0.1] * DENSE_DIM
        # Sparse vector has indices + values.
        sparse = points[0].vector[SPARSE_VECTOR_NAME]
        assert hasattr(sparse, "indices") and hasattr(sparse, "values")

    def test_point_ids_are_sequential_ints(self) -> None:
        chunks = {f"c{i}": _make_chunk(chunk_id=f"c{i}") for i in range(3)}
        embeddings = {f"c{i}": [0.1] * DENSE_DIM for i in range(3)}
        metadata = {"test_doc": _make_doc_metadata()}
        bm25 = BM25Index.build(["sample"] * 3)

        points = list(_iter_points(chunks, embeddings, metadata, bm25))
        assert [p.id for p in points] == [0, 1, 2]

    def test_point_payload_matches_chunk_to_payload(self) -> None:
        chunk = _make_chunk(chunk_id="c1", text="alpha")
        chunks = {"c1": chunk}
        embeddings = {"c1": [0.1] * DENSE_DIM}
        meta = _make_doc_metadata()
        metadata = {"test_doc": meta}
        bm25 = BM25Index.build(["alpha"])

        points = list(_iter_points(chunks, embeddings, metadata, bm25))
        assert points[0].payload == chunk_to_payload(chunk, meta)
