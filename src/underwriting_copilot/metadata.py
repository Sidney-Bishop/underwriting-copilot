"""Document metadata schema and loader.

The corpus_metadata.toml file is the hand-curated source of truth for
document-level metadata: identity, issuer, type, topics, provenance, and
supersession relationships. Runtime metadata (page count, chunk count,
extraction timestamp) is added by the ingestion pipeline and lives
elsewhere — it is not the user's concern here.
"""

from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

DocumentType = Literal[
    "supervisory_statement",
    "regulatory_guideline",
    "sustainability_report",
    "policy_statement",
    "internal_policy",
]

IssuerType = Literal["regulator", "reinsurer", "industry_body"]
Provenance = Literal["real", "synthetic"]


class DocumentMetadata(BaseModel):
    """Hand-curated, document-level metadata.

    Keyed in the TOML file by the document's filename relative to corpus/.
    """

    document_id: str = Field(
        description="Stable slug used as the canonical reference."
    )
    title: str
    document_type: DocumentType
    issuer: str
    issuer_type: IssuerType
    jurisdiction: str | None = None
    effective_date: date | None = None
    version: str | None = None
    superseded_by: str | None = Field(
        default=None,
        description="Version string of a superseding document, if any.",
    )
    topics: list[str] = Field(default_factory=list)
    provenance: Provenance
    source_url: str | None = None

    model_config = {"extra": "forbid"}


def load_corpus_metadata(toml_path: Path) -> dict[str, DocumentMetadata]:
    """Load and validate every entry in corpus_metadata.toml.

    Returns a dict mapping filename -> DocumentMetadata. Raises if any
    entry fails validation.
    """
    with toml_path.open("rb") as f:
        raw = tomllib.load(f)

    return {
        filename: DocumentMetadata(**entry)
        for filename, entry in raw.items()
        if isinstance(entry, dict)
    }
