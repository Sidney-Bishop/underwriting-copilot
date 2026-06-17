"""Probe: find repeating-line patterns across the corpus markdown.

Lines that repeat ≥3 times within a single document are almost always
noise — headers, footers, watermarks, page-decoration. We want a
data-driven list to inform a cleanup pre-pass before chunking.

For each doc, report:
  - Lines that appear ≥3 times (with the count)
  - Lines that appear ≥3 times AND are short (≤120 chars) — the strong
    noise signal; long repeating lines are usually legitimate content
    (e.g. boilerplate disclosure paragraphs)
  - Cross-doc: any short line that repeats across ≥2 documents (these
    are universal noise candidates worth a global rule)
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROBES = PROJECT_ROOT / "scratch" / "docling_probes"

# A line is "short" enough to be plausible noise rather than content if
# it's under this many chars. 120 is generous; headers/footers are
# typically much shorter.
SHORT_LINE_THRESHOLD = 120

# A line must repeat at least this many times within one doc to count
# as suspicious. 3 catches once-per-section watermarks without flagging
# every "is" or blank-style line.
REPEAT_THRESHOLD = 3


def normalize(line: str) -> str:
    """Light normalization so 'Page 1' and 'Page 2' don't collapse, but
    leading/trailing whitespace doesn't make twins look different."""
    return line.strip()


def main() -> None:
    md_files = sorted(PROBES.glob("*.md"))
    if not md_files:
        raise SystemExit(f"No .md files in {PROBES} — run probe 01 first.")

    # For cross-doc analysis: which docs contain each suspicious line.
    cross_doc: dict[str, set[str]] = {}

    for md_file in md_files:
        lines = [
            normalize(l) for l in md_file.read_text().splitlines()
            if normalize(l)  # skip blanks
        ]
        counts = Counter(lines)
        suspicious = [
            (line, n) for line, n in counts.items()
            if n >= REPEAT_THRESHOLD and len(line) <= SHORT_LINE_THRESHOLD
        ]
        suspicious.sort(key=lambda x: -x[1])

        print(f"\n=== {md_file.stem} ===")
        print(f"  {len(lines)} non-blank lines, "
              f"{len(suspicious)} suspicious patterns")
        if not suspicious:
            print("  (no repeating short lines)")
        for line, n in suspicious[:20]:
            display = line if len(line) <= 100 else line[:97] + "..."
            print(f"  {n:>4d}×  {display!r}")
            cross_doc.setdefault(line, set()).add(md_file.stem)

    # Cross-doc noise — lines flagged in 2+ docs are universal cleanup candidates.
    print("\n=== CROSS-DOC NOISE (lines flagged in ≥2 documents) ===")
    universal = [
        (line, docs) for line, docs in cross_doc.items() if len(docs) >= 2
    ]
    universal.sort(key=lambda x: -len(x[1]))
    if not universal:
        print("  (none — all noise is doc-specific)")
    for line, docs in universal:
        display = line if len(line) <= 100 else line[:97] + "..."
        print(f"  {len(docs)} docs: {display!r}")


if __name__ == "__main__":
    main()
