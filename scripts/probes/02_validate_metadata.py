"""Probe: load and validate corpus_metadata.toml.

Checks:
  - Every entry validates against DocumentMetadata.
  - Every PDF in corpus/real/ and corpus/synthetic/ has a metadata entry.
  - Every metadata entry has a corresponding PDF on disk.
  - Topic vocabulary is consistent (lowercase, snake_case).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from underwriting_copilot.metadata import load_corpus_metadata  # noqa: E402

METADATA = PROJECT_ROOT / "corpus" / "corpus_metadata.toml"
CORPUS_DIRS = [PROJECT_ROOT / "corpus" / "real", PROJECT_ROOT / "corpus" / "synthetic"]


def main() -> None:
    metadata = load_corpus_metadata(METADATA)
    print(f"Loaded {len(metadata)} entries from {METADATA.name}\n")

    pdfs_on_disk: set[str] = set()
    for d in CORPUS_DIRS:
        if d.exists():
            pdfs_on_disk.update(p.name for p in d.glob("*.pdf"))

    missing_metadata = pdfs_on_disk - set(metadata.keys())
    missing_pdfs = set(metadata.keys()) - pdfs_on_disk

    if missing_metadata:
        print(f"PDFs without metadata: {sorted(missing_metadata)}")
    if missing_pdfs:
        print(f"Metadata without PDFs: {sorted(missing_pdfs)}")
    if not missing_metadata and not missing_pdfs:
        print("All PDFs have metadata; all metadata maps to PDFs.\n")

    print(f"{'document_id':40s}  {'issuer':12s}  {'type':22s}  {'topics':>6s}  superseded_by")
    print("-" * 110)
    for fname, m in sorted(metadata.items()):
        sup = m.superseded_by or "-"
        print(
            f"{m.document_id:40s}  {m.issuer:12s}  {m.document_type:22s}  "
            f"{len(m.topics):>6d}  {sup}"
        )

    all_topics = sorted({t for m in metadata.values() for t in m.topics})
    print(f"\nTopic vocabulary ({len(all_topics)} unique):")
    print("  " + ", ".join(all_topics))

    bad_topics = [t for t in all_topics if t != t.lower() or " " in t]
    if bad_topics:
        print(f"\nWARNING: topics that should be normalized: {bad_topics}")

    provenance_counts: dict[str, int] = {}
    for m in metadata.values():
        provenance_counts[m.provenance] = provenance_counts.get(m.provenance, 0) + 1
    print(f"\nProvenance: {provenance_counts}")


if __name__ == "__main__":
    main()
