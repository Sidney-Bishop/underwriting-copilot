"""Probe: characterise the leaf-section size distribution across the corpus.

Reads the markdown outputs from scratch/docling_probes/ (produced by probe 01),
splits each on '##' / '###' boundaries, and reports the token-count distribution
of leaf sections. The goal is to make chunking decisions from data, not vibes:
  - How often would an 800-token soft cap fire?
  - How often would a 100-token soft floor fire?
  - Is the long tail one outlier doc or systemic?

Tokens are approximated as words for portability — accurate enough for sizing
chunking parameters. We're not training anything here.
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROBES = PROJECT_ROOT / "scratch" / "docling_probes"

# A "leaf section" is the body between one ##/### heading and the next heading
# of equal-or-shallower depth. For sizing purposes we don't need to be strict
# about which level — we just want the unit-of-text that follows a heading.
HEADING_RE = re.compile(r"^(#{2,4})\s+(.+)$", re.MULTILINE)

# Soft thresholds we're stress-testing.
SOFT_CAP_TOKENS = 800
SOFT_FLOOR_TOKENS = 100

# Approximate "tokens ~= words" — a reasonable proxy for sizing decisions.
def approx_tokens(text: str) -> int:
    return len(text.split())


def split_into_sections(md: str) -> list[tuple[str, str]]:
    """Yield (heading, body) pairs. Body is text up to the next heading."""
    matches = list(HEADING_RE.finditer(md))
    sections: list[tuple[str, str]] = []

    if not matches:
        return [("(no heading)", md)]

    # Preamble (text before any heading) — count as anonymous section if non-empty
    preamble = md[: matches[0].start()].strip()
    if preamble:
        sections.append(("(preamble)", preamble))

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        body = md[body_start:body_end].strip()
        sections.append((heading, body))

    return sections


def histogram(counts: list[int], buckets: list[int]) -> dict[str, int]:
    """Bucketize counts into labelled bins. buckets defines the upper edges."""
    hist = {f"≤{b}": 0 for b in buckets}
    hist[f">{buckets[-1]}"] = 0
    for c in counts:
        placed = False
        for b in buckets:
            if c <= b:
                hist[f"≤{b}"] += 1
                placed = True
                break
        if not placed:
            hist[f">{buckets[-1]}"] += 1
    return hist


def main() -> None:
    if not PROBES.exists():
        raise SystemExit(f"No probe outputs at {PROBES} — run probe 01 first.")

    md_files = sorted(PROBES.glob("*.md"))
    if not md_files:
        raise SystemExit(f"No .md files in {PROBES} — run probe 01 first.")

    all_sizes: list[int] = []
    per_doc: dict[str, list[int]] = {}

    print(f"{'document':50s}  {'sects':>5s}  {'min':>4s}  {'p50':>5s}  "
          f"{'p90':>5s}  {'max':>6s}  {'>cap':>5s}  {'<flr':>5s}")
    print("-" * 100)

    for md_file in md_files:
        md = md_file.read_text()
        sections = split_into_sections(md)
        sizes = [approx_tokens(body) for _, body in sections if body]
        per_doc[md_file.stem] = sizes
        all_sizes.extend(sizes)

        over_cap = sum(1 for s in sizes if s > SOFT_CAP_TOKENS)
        under_floor = sum(1 for s in sizes if s < SOFT_FLOOR_TOKENS)
        p50 = statistics.median(sizes) if sizes else 0
        p90 = (
            statistics.quantiles(sizes, n=10)[-1]
            if len(sizes) >= 10
            else max(sizes) if sizes else 0
        )
        print(
            f"{md_file.stem:50s}  {len(sizes):>5d}  {min(sizes) if sizes else 0:>4d}  "
            f"{int(p50):>5d}  {int(p90):>5d}  {max(sizes) if sizes else 0:>6d}  "
            f"{over_cap:>5d}  {under_floor:>5d}"
        )

    print()
    print(f"CORPUS TOTALS: {len(all_sizes)} leaf sections")
    print(f"  min / median / p90 / max tokens: "
          f"{min(all_sizes)} / {int(statistics.median(all_sizes))} / "
          f"{int(statistics.quantiles(all_sizes, n=10)[-1])} / {max(all_sizes)}")
    print(f"  mean: {statistics.mean(all_sizes):.1f}, "
          f"stdev: {statistics.stdev(all_sizes):.1f}")

    over_cap = sum(1 for s in all_sizes if s > SOFT_CAP_TOKENS)
    under_floor = sum(1 for s in all_sizes if s < SOFT_FLOOR_TOKENS)
    print(f"  over {SOFT_CAP_TOKENS} tokens (cap fires): "
          f"{over_cap} ({over_cap/len(all_sizes)*100:.0f}%)")
    print(f"  under {SOFT_FLOOR_TOKENS} tokens (floor fires): "
          f"{under_floor} ({under_floor/len(all_sizes)*100:.0f}%)")

    print("\nDistribution:")
    buckets = [50, 100, 200, 400, 800, 1600]
    hist = histogram(all_sizes, buckets)
    max_count = max(hist.values())
    for label, count in hist.items():
        bar = "█" * int(count / max_count * 40) if max_count else ""
        print(f"  {label:>6s}  {count:>4d}  {bar}")


if __name__ == "__main__":
    main()
