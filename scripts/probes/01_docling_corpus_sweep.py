"""Probe: run Docling over every PDF in corpus/real/ and report on structural
quality, glyph artifacts, and time-per-doc. Output written to scratch/.

OCR is disabled — all six corpus PDFs are text PDFs (verified via `file`),
so the default OCR pipeline only adds latency and emits empty-result warnings."""

from pathlib import Path
import time
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS = PROJECT_ROOT / "corpus" / "real"
OUT = PROJECT_ROOT / "scratch" / "docling_probes"
OUT.mkdir(parents=True, exist_ok=True)

pipeline_options = PdfPipelineOptions(do_ocr=False)
converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
)

print(f"{'document':50s}  {'time':>6s}  {'chars':>10s}  {'lines':>7s}  {'glyphs':>7s}")
print("-" * 90)

for pdf in sorted(CORPUS.glob("*.pdf")):
    t0 = time.time()
    result = converter.convert(pdf)
    md = result.document.export_to_markdown()
    (OUT / f"{pdf.stem}.md").write_text(md)
    glyph_count = md.count("glyph[.notdef]")
    print(f"{pdf.name:50s}  {time.time()-t0:5.1f}s  {len(md):>10,}  "
          f"{md.count(chr(10)):>7,}  {glyph_count:>7,}", flush=True)
