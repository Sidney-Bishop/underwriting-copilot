"""BM25 sparse channel implementation per D011.

Tokenisation pipeline:
    text → regex word split (``\\b\\w+\\b``) → lowercase
         → drop stopwords (~30 high-frequency function words)
         → Porter stem via ``snowballstemmer``

The :class:`BM25Index` holds the corpus-wide vocabulary, document
frequencies, precomputed IDF, and average document length. Built once at
index time, persisted as ``corpus/bm25_vocab.json``, and consulted at
both indexing and query time to produce Qdrant-compatible sparse vectors.

Sparse-vector construction matches the convention pinned in D011:

- **Index time** (per chunk ``c`` with tokens ``T_c``): each entry is the
  BM25 contribution of one term — ``idf(t) * (tf(t,c) * (k1+1)) /
  (tf(t,c) + k1 * (1 - b + b * |c|/avgdl))``.
- **Query time** (per query token set ``T_q``): each entry is a
  presence indicator (value ``1.0``).

The inner product between an index-time vector and a query-time vector
equals the BM25 score by construction — which is exactly what Qdrant's
native sparse vector index computes.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import snowballstemmer

# ---- Module-level singletons --------------------------------------------

# Snowball stemmer construction isn't free; build once.
_STEMMER = snowballstemmer.stemmer("english")

# Regex matches word boundaries — strips punctuation, keeps alphanumerics.
# Tokens like "SS1/21" split into ["SS1", "21"] which is the right behaviour
# for regulatory document references: both parts retained for BM25 matching.
_WORD_RE = re.compile(r"\b\w+\b")

#: Minimal hand-curated stopword list per D011. Bias toward keeping words —
#: BM25's IDF handles common terms anyway. "not", "if", "shall", "must" are
#: deliberately omitted because they carry regulatory meaning.
STOPWORDS: frozenset[str] = frozenset({
    # Articles
    "the", "a", "an",
    # Conjunctions
    "and", "or", "but",
    # Common prepositions
    "of", "in", "on", "at", "to", "for", "as", "by", "with", "from", "into",
    # "Be" forms
    "is", "are", "was", "were", "be", "been", "being", "am",
    # Demonstratives + pronouns we don't need
    "this", "that", "these", "those", "it", "its",
    # "Have" forms
    "has", "have", "had",
    # "Do" forms
    "do", "does", "did",
    # First-person pronoun (after lower-casing "I")
    "i",
})


# ---- Tokenisation -------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Apply the D011 tokenisation pipeline.

    Steps: lowercase → regex word-split → drop stopwords → Porter stem.

    Token order is preserved (matches the surface order of terms in the
    input). Tokens that collapse to empty after stemming are dropped.
    """
    if not text:
        return []
    out: list[str] = []
    for match in _WORD_RE.finditer(text.lower()):
        word = match.group(0)
        if word in STOPWORDS:
            continue
        stem = _STEMMER.stemWord(word)
        if stem:
            out.append(stem)
    return out


# ---- The index ----------------------------------------------------------


@dataclass(frozen=True)
class BM25Index:
    """Frozen BM25 index built once over the corpus.

    The vocab assigns stable integer ids to terms (alphabetically sorted at
    build time, so a fresh build over the same corpus yields identical
    ids — important because the ids are baked into the sparse vectors
    stored in Qdrant).
    """

    vocab: dict[str, int]      # stemmed term → vocab id
    df: dict[str, int]         # stemmed term → document frequency
    idf: dict[str, float]      # stemmed term → precomputed IDF
    corpus_size: int           # N (number of texts indexed)
    avgdl: float               # average document length in tokens
    k1: float = 1.5
    b: float = 0.75

    # ---- Build ----------------------------------------------------------

    @classmethod
    def build(
        cls,
        texts: list[str],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> "BM25Index":
        """Construct an index from a corpus of texts.

        One tokenisation pass per text; document frequencies, IDF, and
        average document length computed in a single traversal.
        """
        n = len(texts)
        if n == 0:
            raise ValueError("Cannot build BM25 index from empty corpus.")

        tokenised: list[list[str]] = [tokenize(t) for t in texts]
        total_tokens = sum(len(toks) for toks in tokenised)
        avgdl = total_tokens / n

        df: Counter[str] = Counter()
        for toks in tokenised:
            df.update(set(toks))  # document frequency, not term frequency

        # Sort terms alphabetically for reproducible vocab ids.
        terms = sorted(df.keys())
        vocab = {term: i for i, term in enumerate(terms)}

        idf = {
            term: math.log((n - df[term] + 0.5) / (df[term] + 0.5) + 1)
            for term in terms
        }

        return cls(
            vocab=vocab,
            df=dict(df),
            idf=idf,
            corpus_size=n,
            avgdl=avgdl,
            k1=k1,
            b=b,
        )

    # ---- Sparse vectors -------------------------------------------------

    def chunk_sparse_vector(
        self, text: str
    ) -> tuple[list[int], list[float]]:
        """Compute the BM25-contribution sparse vector for an indexed
        chunk. Returns ``(indices, values)`` ready to pass into a Qdrant
        :class:`SparseVector`.

        Terms not in the vocab are silently skipped (this should only
        happen for texts not seen at build time — for queries, prefer
        :meth:`query_sparse_vector`).
        """
        tokens = tokenize(text)
        if not tokens:
            return [], []
        tf = Counter(tokens)
        doc_len = len(tokens)

        # Length-normalisation factor (same for every term in this doc).
        len_norm = 1.0 - self.b + self.b * doc_len / self.avgdl

        indices: list[int] = []
        values: list[float] = []
        for term, freq in tf.items():
            vocab_id = self.vocab.get(term)
            if vocab_id is None:
                continue
            numerator = freq * (self.k1 + 1)
            denominator = freq + self.k1 * len_norm
            contribution = self.idf[term] * numerator / denominator
            indices.append(vocab_id)
            values.append(contribution)
        return indices, values

    def query_sparse_vector(
        self, text: str
    ) -> tuple[list[int], list[float]]:
        """Compute the presence-indicator sparse vector for a query.

        Each query term in vocab contributes a single ``1.0``. The inner
        product of this vector with a chunk's index-time vector yields
        the chunk's BM25 score against the query.

        Repeated query terms are deduplicated — query-side weight is
        ``1.0`` regardless of repetition.
        """
        tokens = tokenize(text)
        if not tokens:
            return [], []
        unique_ids = {self.vocab[t] for t in tokens if t in self.vocab}
        indices = sorted(unique_ids)
        values = [1.0] * len(indices)
        return indices, values

    # ---- Serialisation --------------------------------------------------

    def to_dict(self) -> dict:
        """JSON-serialisable dict representation.

        Vocab is stored as an ordered list — ids are positions in the
        list, so on reload the vocab dict is reconstructed deterministically
        without relying on JSON dict ordering.
        """
        terms = list(self.vocab.keys())  # ordered by id
        return {
            "version": 1,
            "vocab": terms,
            "df": [self.df[t] for t in terms],
            "idf": [self.idf[t] for t in terms],
            "corpus_size": self.corpus_size,
            "avgdl": self.avgdl,
            "k1": self.k1,
            "b": self.b,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BM25Index":
        """Reconstruct an index from its JSON dict representation."""
        version = data.get("version", 1)
        if version != 1:
            raise ValueError(
                f"Unsupported BM25Index serialisation version: {version}"
            )
        terms: list[str] = data["vocab"]
        vocab = {term: i for i, term in enumerate(terms)}
        df = {term: data["df"][i] for i, term in enumerate(terms)}
        idf = {term: data["idf"][i] for i, term in enumerate(terms)}
        return cls(
            vocab=vocab,
            df=df,
            idf=idf,
            corpus_size=data["corpus_size"],
            avgdl=data["avgdl"],
            k1=data.get("k1", 1.5),
            b=data.get("b", 0.75),
        )

    def save(self, path: Path) -> None:
        """Persist the index to a JSON file."""
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        """Read an index from a JSON file written by :meth:`save`."""
        return cls.from_dict(json.loads(path.read_text()))
