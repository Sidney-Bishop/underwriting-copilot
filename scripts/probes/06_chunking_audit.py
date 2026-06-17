"""Probe: apply the full ingest pipeline (cleanup + chunking) to each
document and report on chunk health.

For each document:
  - chunk count, broken down by strategy (hierarchy / paragraph_fallback / merged)
  - size distribution (min / p50 / p90 / max tokens)
  - writes chunks to scratch/chunks/{document_id}.jsonl for inspection

Cross-corpus:
  - total chunk count
  - corpus-wide size distribution and strategy split
  - health checks: oversize chunks, surviving sub-floor chunks, empty paths
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROBES = PROJECT_ROOT / "scratch" / "docling_probes"
CLEANED = PROJECT_ROOT / "scratch" / "docling_cleaned"
CHUNKS_OUT = PROJECT_ROOT / "scratch" / "chunks"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from underwriting_copilot.chunking import Chunk, chunk_document  # noqa: E402
from underwriting_copilot.cleanup import clean  # noqa: E402
from underwriting_copilot.metadata import load_corpus_metadata  # noqa: E402

SOFT_CAP = 1500
SOFT_FLOOR = 100


def _ensure_cleaned(stem_to_doc_id: dict[str, str]) -> None:
    """Run cleanup if scratch/docling_cleaned/ is missing or empty."""
    if CLEANED.exists() and any(CLEANED.glob("*.md")):
        return
    if not PROBES.exists():
        raise SystemExit(f"No probes at {PROBES} — run probe 01 first.")
    CLEANED.mkdir(parents=True, exist_ok=True)
    for md_file in PROBES.glob("*.md"):
        document_id = stem_to_doc_id.get(md_file.stem, md_file.stem)
        cleaned, _ = clean(md_file.read_text(), document_id)
        (CLEANED / md_file.name).write_text(cleaned)


def _quantile(sizes: list[int], q: float) -> int:
    if not sizes:
        return 0
    if len(sizes) < 10:
        return max(sizes) if q >= 0.9 else min(sizes)
    return int(statistics.quantiles(sizes, n=10)[int(q * 10) - 1])


def main() -> None:
    metadata = load_corpus_metadata(PROJECT_ROOT / "corpus" / "corpus_metadata.toml")
    stem_to_doc_id = {Path(fname).stem: m.document_id for fname, m in metadata.items()}

    _ensure_cleaned(stem_to_doc_id)
    CHUNKS_OUT.mkdir(parents=True, exist_ok=True)

    print(
        f"{'document':45s}  {'n':>4s}  {'hier':>5s}  {'pf':>3s}  {'mrg':>3s}  "
        f"{'min':>4s}  {'p50':>5s}  {'p90':>5s}  {'max':>5s}"
    )
    print("-" * 100)

    all_chunks: list[Chunk] = []
    for md_file in sorted(CLEANED.glob("*.md")):
        document_id = stem_to_doc_id.get(md_file.stem, md_file.stem)
        chunks = chunk_document(
            md_file.read_text(),
            document_id,
            soft_cap=SOFT_CAP,
            soft_floor=SOFT_FLOOR,
        )
        all_chunks.extend(chunks)

        # Dump chunks for this doc to JSONL for inspection.
        out = CHUNKS_OUT / f"{document_id}.jsonl"
        with out.open("w") as f:
            for c in chunks:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")

        sizes = [c.token_count for c in chunks]
        strategies = {"hierarchy": 0, "paragraph_fallback": 0, "merged": 0}
        for c in chunks:
            strategies[c.chunk_strategy] += 1

        if sizes:
            print(
                f"{document_id:45s}  "
                f"{len(chunks):>4d}  "
                f"{strategies['hierarchy']:>5d}  "
                f"{strategies['paragraph_fallback']:>3d}  "
                f"{strategies['merged']:>3d}  "
                f"{min(sizes):>4d}  "
                f"{_quantile(sizes, 0.5):>5d}  "
                f"{_quantile(sizes, 0.9):>5d}  "
                f"{max(sizes):>5d}"
            )

    print()
    print(f"TOTAL: {len(all_chunks)} chunks across {len(set(c.document_id for c in all_chunks))} documents")

    all_sizes = [c.token_count for c in all_chunks]
    print(
        f"  min/p50/p90/max tokens: "
        f"{min(all_sizes)}/{_quantile(all_sizes, 0.5)}/"
        f"{_quantile(all_sizes, 0.9)}/{max(all_sizes)}"
    )

    all_strats: dict[str, int] = {}
    for c in all_chunks:
        all_strats[c.chunk_strategy] = all_strats.get(c.chunk_strategy, 0) + 1
    print(f"  by strategy: {all_strats}")

    # Health checks.
    print("\n=== HEALTH CHECKS ===")

    # Cap: paragraph-fallback should keep chunks under cap. Allow 10% slack
    # for the final greedy-split fallback which can produce one slightly
    # under-or-equal chunk at the tail.
    cap_slack = int(SOFT_CAP * 1.1)
    over_cap = [c for c in all_chunks if c.token_count > cap_slack]
    status = "✓" if not over_cap else "✗"
    print(f"  {status}  Chunks above cap*1.1 ({cap_slack}): {len(over_cap)}")
    for c in over_cap[:5]:
        print(f"        {c.chunk_id}: {c.token_count} tokens, strat={c.chunk_strategy}")

    # Floor: should be rare after merging. A few survivors are OK — e.g. the
    # first segment of a short doc has no predecessor to merge into. We expect
    # well under 10% of total chunks.
    under_floor = [c for c in all_chunks if c.token_count < SOFT_FLOOR]
    floor_threshold = max(5, int(len(all_chunks) * 0.05))
    status = "✓" if len(under_floor) <= floor_threshold else "✗"
    print(
        f"  {status}  Chunks below floor ({SOFT_FLOOR}): {len(under_floor)} "
        f"(threshold: {floor_threshold})"
    )
    for c in under_floor[:5]:
        print(f"        {c.chunk_id}: {c.token_count} tokens, strat={c.chunk_strategy}")

    # Section paths: every chunk must have one.
    no_path = [c for c in all_chunks if not c.section_path]
    status = "✓" if not no_path else "✗"
    print(f"  {status}  Chunks with empty section_path: {len(no_path)}")

    # Empty text: should never happen.
    empty = [c for c in all_chunks if not c.text.strip()]
    status = "✓" if not empty else "✗"
    print(f"  {status}  Chunks with empty text: {len(empty)}")

    print()
    all_pass = (
        not over_cap
        and len(under_floor) <= floor_threshold
        and not no_path
        and not empty
    )
    print("All checks pass." if all_pass else "Issues found — see above.")
    print(f"\nChunks written to: {CHUNKS_OUT}")


if __name__ == "__main__":
    main()
