"""app.py — Cedant: Streamlit interface for the underwriting copilot.

Local-first analyst-facing UI for the RAG pipeline. Talks to the same
``Retriever`` and ``AnswerGenerator`` that ``eval/runner.py`` uses, so
behaviour observed here is the behaviour the eval measures.

Run from repo root:

    uv run streamlit run app.py --server.port 8502 --server.headless true --server.address 127.0.0.1

Requires oMLX running on http://127.0.0.1:8000 with at least one of
the candidate models loaded.

Diagnostic logging: every Ask click prints a `[cedant]` line to stderr
so the streamlit terminal shows exactly which code path the script took.
"""

from __future__ import annotations

import html
import re
import sys
import time
from pathlib import Path

import httpx
import markdown as md
import streamlit as st

from underwriting_copilot.answer import (
    CITATION_REGEX,
    DEFAULT_API_BASE,
    AnswerGenerator,
    AnswerResult,
)
from underwriting_copilot.retrieve import Retriever


def log(msg: str) -> None:
    """Print a [cedant] diagnostic line to stderr.

    Visible in the terminal running ``streamlit run``. Use for state
    transitions only — not per-render noise.
    """
    print(f"[cedant {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ============================================================================
# Configuration
# ============================================================================

REPO_ROOT = Path(__file__).resolve().parent
QDRANT_PATH = REPO_ROOT / "scratch" / "qdrant"
VOCAB_PATH = REPO_ROOT / "corpus" / "bm25_vocab.json"
ASSETS_DIR = REPO_ROOT / "assets"
SYCAMORE_LOGO = ASSETS_DIR / "sycamore.png"

MODEL_OPTIONS = [
    ("gemma-4-31B-it-MLX-6bit", "Gemma 4 31B IT  ·  production default  ·  ~30–60s/query"),
    ("Qwen3.6-35B-A3B-4bit",    "Qwen3.6 35B A3B  ·  latency-budget  ·  ~5–10s/query"),
]

SAMPLE_QUERIES = [
    {
        "label": "PRA climate scenario analysis",
        "query": "What does the PRA expect insurers to do for climate scenario analysis?",
        "kind": "Single-document, regulatory",
    },
    {
        "label": "Munich vs Swiss thermal coal",
        "query": "How do Munich Re and Swiss Re differ in their disclosed approach to fossil fuel exclusion criteria?",
        "kind": "Cross-document synthesis",
    },
    {
        "label": "Munich Re green bonds",
        "query": "What does Munich Re say about its issued green bonds?",
        "kind": "Single-document, corporate",
    },
    {
        "label": "Bermuda hurricane bonds (out-of-corpus)",
        "query": "What is the maximum solvency capital ratio required for a hurricane bond issuer in Bermuda?",
        "kind": "Should refuse — out of corpus",
    },
]

# ============================================================================
# Page setup
# ============================================================================

st.set_page_config(
    page_title="Cedant — Reinsurance Underwriting Copilot",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# Custom CSS
# ============================================================================

st.markdown(
    """
<style>
@import url('https://rsms.me/inter/inter.css');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
.stApp { background-color: #fafafa; }
html { scroll-behavior: smooth; }

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

section.main > div.block-container {
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 1280px;
}

.cedant-header {
    display: flex;
    align-items: baseline;
    gap: 1rem;
    margin: 0 0 0.25rem 0;
}
.cedant-title {
    font-size: 2.25rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1;
    letter-spacing: -0.02em;
}
.cedant-mark {
    color: #1e40af;
    font-size: 1.5rem;
    line-height: 1;
}
.cedant-sub {
    font-size: 0.92rem;
    color: #64748b;
    margin-bottom: 2rem;
    line-height: 1.4;
}

section[data-testid="stSidebar"] {
    background-color: #f1f5f9;
    border-right: 1px solid #e2e8f0;
}
section[data-testid="stSidebar"] .stMarkdown h3 {
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #475569;
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
}

.question-card {
    background: #0f172a;
    color: #f1f5f9;
    padding: 1.2rem 1.5rem;
    border-radius: 8px;
    font-size: 1.18rem;
    line-height: 1.5;
    margin: 1.5rem 0 1rem 0;
    font-weight: 500;
}
.question-card .question-label {
    display: block;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94a3b8;
    margin-bottom: 0.4rem;
}

.answer-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1.75rem 2rem;
    font-size: 1.18rem;
    line-height: 1.75;
    color: #0f172a;
    margin-bottom: 1.25rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.answer-card p { margin: 0 0 1rem 0; }
.answer-card p:last-child { margin-bottom: 0; }

.cite {
    display: inline-block;
    background: #eff6ff;
    color: #1e40af;
    border: 1px solid #bfdbfe;
    border-radius: 4px;
    padding: 0 6px;
    margin: 0 2px;
    font-size: 0.78em;
    font-weight: 600;
    text-decoration: none !important;
    font-family: 'JetBrains Mono', 'SF Mono', monospace;
    vertical-align: super;
    line-height: 1.3;
    transition: all 0.12s ease;
}
.cite:hover {
    background: #dbeafe;
    border-color: #93c5fd;
    color: #1e3a8a;
}
.cite-halluc {
    background: #fef2f2;
    color: #b91c1c;
    border-color: #fecaca;
}
.cite-halluc:hover {
    background: #fee2e2;
}

.refusal-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #64748b;
    padding: 1.25rem 1.5rem;
    color: #334155;
    border-radius: 6px;
    margin: 1rem 0 1.25rem 0;
}
.refusal-card .refusal-label {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
    margin-bottom: 0.5rem;
}
.refusal-card .refusal-text {
    font-size: 1.15rem;
    line-height: 1.55;
}

.halluc-banner {
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-left: 4px solid #dc2626;
    padding: 1rem 1.3rem;
    border-radius: 6px;
    color: #991b1b;
    font-size: 1rem;
    margin: 0.5rem 0 1.25rem 0;
}
.halluc-banner b { color: #7f1d1d; }
.halluc-banner code {
    background: #fee2e2;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.85em;
    color: #991b1b;
}

.metric-row {
    display: flex;
    gap: 0;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 0;
    margin: 0 0 1.5rem 0;
    overflow: hidden;
}
.metric-cell {
    flex: 1;
    padding: 0.85rem 1.2rem;
    border-right: 1px solid #e2e8f0;
}
.metric-cell:last-child { border-right: none; }
.metric-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748b;
    margin-bottom: 0.2rem;
}
.metric-value {
    font-size: 1.1rem;
    font-weight: 600;
    color: #0f172a;
    font-variant-numeric: tabular-nums;
}
.metric-value.warn { color: #dc2626; }
.metric-value.ok { color: #15803d; }
.metric-value.muted { color: #64748b; font-weight: 500; font-size: 0.95rem; }

.section-heading {
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #475569;
    margin: 1.5rem 0 0.75rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #e2e8f0;
}
.section-heading .count {
    color: #94a3b8;
    font-weight: 500;
    margin-left: 0.4rem;
    text-transform: none;
    letter-spacing: 0;
}

.source-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.7rem;
    scroll-margin-top: 1rem;
    transition: border-color 0.2s ease;
}
.source-card.cited { border-left: 3px solid #1e40af; }
.source-card.uncited { opacity: 0.75; }
.source-card:target {
    border-color: #1e40af;
    box-shadow: 0 0 0 3px #dbeafe;
}
.source-head {
    display: flex;
    gap: 0.6rem;
    align-items: baseline;
    flex-wrap: wrap;
    margin-bottom: 0.35rem;
}
.source-num {
    background: #1e40af;
    color: white;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.75rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    min-width: 1.8rem;
    text-align: center;
}
.source-num.uncited {
    background: #cbd5e1;
    color: #475569;
}
.source-issuer {
    font-weight: 600;
    color: #0f172a;
    font-size: 1rem;
}
.source-title {
    color: #475569;
    font-size: 0.95rem;
}
.source-breadcrumb {
    color: #64748b;
    font-size: 0.85rem;
    margin-bottom: 0.5rem;
    font-family: 'JetBrains Mono', 'SF Mono', monospace;
    word-break: break-word;
}
.source-cid {
    color: #94a3b8;
    font-size: 0.72rem;
    margin-bottom: 0.6rem;
    font-family: 'JetBrains Mono', monospace;
    word-break: break-all;
    user-select: all;
}
.source-text {
    color: #1e293b;
    font-size: 1rem;
    line-height: 1.65;
    border-top: 1px solid #f1f5f9;
    padding-top: 0.8rem;
    white-space: pre-wrap;
    max-height: 360px;
    overflow-y: auto;
}

.empty-hero {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1.75rem 2rem;
    margin: 1rem 0 1.5rem 0;
}
.empty-hero h3 {
    font-size: 1rem;
    color: #0f172a;
    margin: 0 0 0.5rem 0;
}
.empty-hero p {
    color: #475569;
    font-size: 0.92rem;
    line-height: 1.55;
    margin: 0 0 1rem 0;
}

div[data-testid="stButton"] > button {
    font-size: 0.88rem;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
    background: #ffffff;
    color: #0f172a;
    text-align: left;
    padding: 0.8rem 1rem;
    transition: all 0.15s;
    white-space: normal;
    height: auto;
    line-height: 1.4;
}
div[data-testid="stButton"] > button:hover {
    border-color: #1e40af;
    box-shadow: 0 1px 4px rgba(30, 64, 175, 0.08);
    color: #1e40af;
}
div[data-testid="stButton"] > button[kind="primary"] {
    background: #0f172a;
    color: white;
    border-color: #0f172a;
    text-align: center;
    font-weight: 600;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #1e40af;
    border-color: #1e40af;
    color: white;
}

.error-card {
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-left: 4px solid #dc2626;
    padding: 1rem 1.25rem;
    border-radius: 6px;
    color: #7f1d1d;
    margin: 1rem 0;
}
.error-card b { color: #991b1b; }
.error-card code {
    background: #fee2e2;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.88em;
}

div[data-testid="stSpinner"] {
    color: #0f172a;
    padding: 1rem 0;
    font-size: 0.95rem;
}
div[data-testid="stSpinner"] > div {
    border-color: #1e40af transparent transparent transparent !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================================
# Cached resources
# ============================================================================


@st.cache_resource(show_spinner=False)
def load_retriever() -> Retriever:
    """Open the Qdrant index once per Streamlit session."""
    log("loading retriever (cache miss — first call)")
    r = Retriever(
        qdrant_path=QDRANT_PATH,
        vocab_path=VOCAB_PATH,
        verbose=False,
    )
    log("retriever loaded")
    return r


def make_generator(model: str, enable_thinking: bool) -> AnswerGenerator:
    """Build an AnswerGenerator with the chosen model."""
    return AnswerGenerator(
        retriever=load_retriever(),
        model=model,
        enable_thinking=enable_thinking,
    )


# ============================================================================
# Rendering helpers (pure — also exercised by tests/test_app_helpers.py)
# ============================================================================


def build_ordinal_map(answer_text: str) -> dict[str, int]:
    """Map chunk_id -> ordinal [1, 2, 3, ...] in order of first appearance."""
    seen: list[str] = []
    for match in CITATION_REGEX.finditer(answer_text):
        cid = match.group(1)
        if cid not in seen:
            seen.append(cid)
    return {cid: i + 1 for i, cid in enumerate(seen)}


def render_answer_with_badges(result: AnswerResult) -> str:
    """Return HTML for the answer text with citations rewritten as badges.

    Gemma emits markdown (``**bold**`` for section headers, ``* item``
    for bullet lists). We escape literal HTML first, then convert
    markdown to HTML, then substitute citation badges over the rendered
    HTML.

    Order is load-bearing:
    1. ``html.escape`` neutralises any raw HTML in Gemma's output so it
       cannot render as markup.
    2. ``md.markdown`` converts markdown emphasis and lists. HTML
       entities from step 1 (``&lt;``, ``&gt;``) pass through unchanged.
    3. ``CITATION_REGEX.sub`` finds ``[chunk_id]`` tokens in the
       resulting HTML and replaces them with ``<a class="cite">``
       badges. The markdown library leaves bare ``[chunk_id]`` tokens
       as literal text (no matching link reference is defined for
       them), so the pattern survives intact.

    ``sane_lists`` extension keeps list parsing strict — inline
    asterisks that are not at the start of a line do not accidentally
    start lists.
    """
    halluc_set = set(result.hallucinated_citations)
    ordinal_map = build_ordinal_map(result.answer)

    escaped = html.escape(result.answer)
    # Gemma sometimes emits bullet lists inline as " * **Header:**" within
    # a flowing paragraph rather than line-separated. Markdown only treats
    # "*" as a bullet marker when it appears at the start of a line, so
    # those mid-paragraph markers would otherwise render as literal
    # asterisks. Promote each whitespace-asterisk-whitespace sequence
    # immediately followed by bold (**) into a line-separated bullet so
    # the markdown pass sees a proper list.
    #
    # Whitespace is matched with \s+ so the pattern tolerates anything
    # Python recognises as whitespace — regular space (U+0020), NBSP
    # (U+00A0), narrow NBSP (U+202F), tab, newline. Gemma has been
    # observed emitting NBSP between bold markers, which a literal
    # space-asterisk-space regex silently misses.
    #
    # The bullet character set includes Unicode asterisk variants in
    # case the model emits a fullwidth (U+FF0A), asterisk-operator
    # (U+2217), or low-asterisk (U+204E) instead of ASCII U+002A. The
    # lookahead remains ASCII ** because that is what the bold-render
    # path consistently produces in observed output.
    bullet_pattern = r"\s+[*\uff0a\u2217\u204e]\s+(?=\*\*)"
    bullet_matches = len(re.findall(bullet_pattern, escaped))
    if bullet_matches:
        log(f"normalised {bullet_matches} inline-bullet marker(s) in answer")
    normalized = re.sub(bullet_pattern, "\n\n* ", escaped)
    html_body = md.markdown(normalized, extensions=["sane_lists"])

    def replace_citation(match: re.Match) -> str:
        cid = match.group(1)
        if cid in halluc_set:
            return (
                f'<a class="cite cite-halluc" '
                f'title="Hallucinated citation: {html.escape(cid)} — not in retrieved context">[?]</a>'
            )
        n = ordinal_map.get(cid, 0)
        return (
            f'<a class="cite" href="#src-{html.escape(cid)}" '
            f'title="{html.escape(cid)}">[{n}]</a>'
        )

    rewritten = CITATION_REGEX.sub(replace_citation, html_body)
    return f'<div class="answer-card">{rewritten}</div>'


def render_source_card(hit, ordinal: int | None, cited: bool) -> str:
    """Return HTML for a single source chunk."""
    p = hit.payload
    cid = p["chunk_id"]
    issuer = html.escape(p.get("issuer", "(unknown issuer)"))
    title = html.escape(p.get("title", "(unknown title)"))
    section_path = p.get("section_path", [])
    breadcrumb = " › ".join(html.escape(s) for s in section_path) if section_path else "(no section)"
    text = html.escape(p["text"])
    cid_safe = html.escape(cid)

    if ordinal is None:
        num_html = '<span class="source-num uncited">·</span>'
        card_class = "source-card uncited"
    else:
        num_html = f'<span class="source-num">{ordinal}</span>'
        card_class = "source-card cited"

    return f"""
<div id="src-{cid_safe}" class="{card_class}">
    <div class="source-head">
        {num_html}
        <span class="source-issuer">{issuer}</span>
        <span class="source-title">— {title}</span>
    </div>
    <div class="source-breadcrumb">{breadcrumb}</div>
    <div class="source-cid">{cid_safe}</div>
    <div class="source-text">{text}</div>
</div>
"""


def render_metrics_row(result: AnswerResult, top_k: int) -> str:
    """Return HTML for the metric-row beneath the answer."""
    halluc_n = len(result.hallucinated_citations)
    halluc_class = "warn" if halluc_n > 0 else "muted"
    cited_n = len(result.citations)
    retrieved_n = len(result.used_chunks)
    citation_summary = f"{cited_n} / {retrieved_n}"
    model_short = result.model.split("-")[0].title()
    return f"""
<div class="metric-row">
    <div class="metric-cell">
        <div class="metric-label">Model</div>
        <div class="metric-value muted">{model_short}</div>
    </div>
    <div class="metric-cell">
        <div class="metric-label">Latency</div>
        <div class="metric-value">{result.elapsed_seconds:.1f}s</div>
    </div>
    <div class="metric-cell">
        <div class="metric-label">Cited / retrieved</div>
        <div class="metric-value">{citation_summary}</div>
    </div>
    <div class="metric-cell">
        <div class="metric-label">Hallucinated</div>
        <div class="metric-value {halluc_class}">{halluc_n}</div>
    </div>
</div>
"""


# ============================================================================
# Pending-query transfer — BEFORE any widget is rendered
# ============================================================================
#
# This block must run before `st.text_area(key="query_input", ...)` is
# created on this rerun. Streamlit forbids modifying a widget's
# session_state key after the widget has been instantiated.
#
# Why this is here at all: when a sample-query button is clicked, we
# need to populate the text area with that sample's text. We can't
# pass `value=` to text_area because (a) `value=` is overridden by
# session_state when a key is present, and (b) without a key, the
# text area resets to `value` on every rerun — which dropped the
# sample query the moment the user clicked Ask, leaving the script
# with an empty query and silently skipping the LLM call (the bug
# diagnosed by the fan-spin signal: Gemma never ran).
#
# Pattern: sample/history click sets `pending_query` and reruns; on
# the new rerun, we transfer `pending_query` into `query_input`
# (the keyed widget state) and pop it. The widget reads from
# `query_input`, which now persists across all subsequent reruns
# until the user changes it.

if "pending_query" in st.session_state:
    st.session_state.query_input = st.session_state.pop("pending_query")
    log(f"transferred pending_query into query_input")

# Initialise query_input if not yet present, so the widget has a key.
if "query_input" not in st.session_state:
    st.session_state.query_input = ""


# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    st.markdown('<div style="font-size:1.4rem;font-weight:700;color:#0f172a;margin-bottom:0;">◆ Cedant</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.78rem;color:#64748b;margin-bottom:1.5rem;">Underwriting copilot · v1</div>', unsafe_allow_html=True)

    st.markdown("### Model")
    model_choice = st.radio(
        "model",
        options=[m[0] for m in MODEL_OPTIONS],
        format_func=lambda m: next(o[1] for o in MODEL_OPTIONS if o[0] == m),
        index=0,
        label_visibility="collapsed",
        key="model_choice",
    )

    enable_thinking = False
    if "Qwen" in model_choice:
        enable_thinking = st.checkbox(
            "Enable thinking trace",
            value=False,
            key="enable_thinking",
            help="Qwen3-family models emit a <think> trace by default. Off for citation tasks; consumes the token budget that should hold the answer.",
        )

    st.markdown("### Retrieval")
    top_k = st.slider(
        "Top-K chunks",
        min_value=1,
        max_value=10,
        value=5,
        key="top_k",
        help="Number of chunks fed to the LLM. Eval default: 5.",
    )
    exclude_superseded = st.checkbox(
        "Exclude superseded documents",
        value=True,
        key="exclude_superseded",
        help="On by default — PRA SS3/19 is filtered out in favor of SS5/25.",
    )

    st.markdown("### Filters")
    issuer_filter = st.text_input(
        "Issuer type",
        value="",
        placeholder="(any)",
        key="issuer_filter",
        help="e.g. 'regulator', 'insurer'. Leave blank for no filter.",
    )
    jurisdiction_filter = st.text_input(
        "Jurisdiction",
        value="",
        placeholder="(any)",
        key="jurisdiction_filter",
        help="e.g. 'UK', 'EU'. Leave blank for no filter.",
    )

    with st.expander("About this artefact"):
        st.markdown(
            "**Cedant** is a local-first RAG copilot for reinsurance underwriting "
            "research, built as a 5-day interview artefact. The corpus is 461 "
            "chunks across 6 public PDFs. Retrieval is hybrid BGE-M3 dense + "
            "BM25 sparse fused via RRF; answer generation is local oMLX Gemma 4 "
            "31B IT or Qwen3.6 35B A3B.\n\n"
            "See **README.md** at repo root and **docs/evaluation.md** for the "
            "eval methodology."
        )

    if st.session_state.get("history"):
        st.markdown("### Recent queries")
        for q in reversed(st.session_state.history[-5:]):
            short = q if len(q) <= 64 else q[:61] + "…"
            if st.button(short, key=f"hist_{hash(q)}", help=q):
                st.session_state.pending_query = q
                st.rerun()

    # Synthetic test corpus issuer mark. Sycamore Reinsurance is a fictional
    # reinsurer whose generated documents form part of the indexed corpus per
    # D003. The mark is displayed here to make that origin visible without
    # conflating it with Cedant's own brand at the top of the sidebar.
    if SYCAMORE_LOGO.exists():
        st.markdown("### Test corpus")
        st.image(str(SYCAMORE_LOGO), width=140)
        st.markdown(
            '<div style="font-size:0.78rem;color:#64748b;margin-top:-0.4rem;'
            'line-height:1.4;">'
            '<b style="color:#475569;">Sycamore Reinsurance</b><br>'
            'Synthetic issuer generated for D003 corpus documents — '
            'not a real entity.'
            '</div>',
            unsafe_allow_html=True,
        )


# ============================================================================
# Header
# ============================================================================

st.markdown(
    '<div class="cedant-header">'
    '<span class="cedant-mark">◆</span>'
    '<span class="cedant-title">Cedant</span>'
    '</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="cedant-sub">'
    'Local-first cited-answer copilot over PRA · EIOPA · Munich Re · Swiss Re. '
    'Hybrid retrieval, structural citation validation, exact-phrase refusal contract.'
    '</div>',
    unsafe_allow_html=True,
)


# ============================================================================
# Query input — `key="query_input"` makes the value persist across reruns,
# so clicking Ask after a sample populates does NOT reset the field.
# ============================================================================

col_input, col_button = st.columns([5, 1])
with col_input:
    query = st.text_area(
        "Question",
        key="query_input",
        height=80,
        placeholder="What does the PRA expect for climate scenario analysis?",
        label_visibility="collapsed",
    )
with col_button:
    st.markdown('<div style="height:0.25rem"></div>', unsafe_allow_html=True)
    ask = st.button("Ask  →", type="primary", use_container_width=True)


# ============================================================================
# Empty state — sample queries
# ============================================================================

if "current_result" not in st.session_state and not ask:
    st.markdown(
        '<div class="empty-hero">'
        '<h3>Try a sample question</h3>'
        '<p>Each sample exercises a different system property — single-document retrieval, '
        'cross-document synthesis, and the refusal contract on an out-of-corpus query.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for i, sample in enumerate(SAMPLE_QUERIES):
        with cols[i % 2]:
            label = f"**{sample['kind']}**\n\n{sample['query']}"
            if st.button(label, key=f"sample_{i}", use_container_width=True):
                log(f"sample clicked: {sample['label']}")
                st.session_state.pending_query = sample["query"]
                st.rerun()


# ============================================================================
# Query submission
# ============================================================================

if ask:
    q = (query or "").strip()
    log(f"Ask clicked. query_len={len(q)} model={model_choice} top_k={top_k}")

    if not q:
        log("query empty — skipping LLM call")
        st.markdown(
            '<div class="error-card">'
            '<b>Empty query.</b> Type a question or click a sample card before pressing Ask.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        issuer_arg = issuer_filter.strip() or None
        jurisdiction_arg = jurisdiction_filter.strip() or None
        spinner_msg = f"Retrieving chunks and calling {model_choice}…"

        try:
            with st.spinner(spinner_msg):
                log("building generator")
                generator = make_generator(model_choice, enable_thinking)
                log("calling generator.answer()")
                t0 = time.perf_counter()
                result = generator.answer(
                    query=q,
                    top_k=top_k,
                    exclude_superseded=exclude_superseded,
                    issuer_type=issuer_arg,
                    jurisdiction=jurisdiction_arg,
                )
                log(f"answer received: {result.elapsed_seconds:.1f}s, "
                    f"refused={result.refused}, "
                    f"citations={len(result.citations)}, "
                    f"halluc={len(result.hallucinated_citations)}")

            st.session_state.current_result = result
            st.session_state.current_top_k = top_k
            history = st.session_state.get("history", [])
            if q not in history:
                history.append(q)
            st.session_state.history = history

        except httpx.ConnectError as e:
            log(f"ConnectError: {e}")
            st.markdown(
                f'<div class="error-card">'
                f'<b>Cannot reach oMLX.</b> Tried <code>{DEFAULT_API_BASE}</code>. '
                f'Is oMLX running and listening on port 8000?'
                f'</div>',
                unsafe_allow_html=True,
            )
        except httpx.HTTPStatusError as e:
            log(f"HTTPStatusError: HTTP {e.response.status_code}")
            st.markdown(
                f'<div class="error-card">'
                f'<b>oMLX returned HTTP {e.response.status_code}.</b> '
                f'The model <code>{html.escape(model_choice)}</code> may not be loaded. '
                f'Check <code>omlx list</code> and load it with <code>omlx load {html.escape(model_choice)}</code>.'
                f'</div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            log(f"Unhandled {type(e).__name__}: {e}")
            st.markdown(
                f'<div class="error-card">'
                f'<b>{type(e).__name__}:</b> {html.escape(str(e))}'
                f'</div>',
                unsafe_allow_html=True,
            )


# ============================================================================
# Result rendering
# ============================================================================

if "current_result" in st.session_state:
    result: AnswerResult = st.session_state.current_result
    top_k_used = st.session_state.get("current_top_k", 5)

    # "New question" button — clears the current result and the text-area
    # contents, returning the user to the empty-state sample grid.
    # Without this affordance the result was a dead-end (no way back to the
    # samples short of typing a new query and clicking Ask, which the user
    # might not realise is possible).
    _, col_new = st.columns([5, 1])
    with col_new:
        if st.button("← New question", key="new_question", use_container_width=True):
            log("new question clicked — clearing result + query_input")
            for k in ("current_result", "current_top_k", "query_input"):
                st.session_state.pop(k, None)
            st.rerun()

    st.markdown(
        f'<div class="question-card">'
        f'<span class="question-label">Question</span>'
        f'{html.escape(result.query)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    if result.refused:
        if result.used_chunks:
            sub = (
                "The retriever returned chunks, but the model determined they don't "
                "contain enough information to answer the question. Review the "
                "retrieved sources below to verify the refusal."
            )
        else:
            sub = (
                "The retriever returned no chunks under the current filters. "
                "Try relaxing the filters or rephrasing the question."
            )
        st.markdown(
            f'<div class="refusal-card">'
            f'<div class="refusal-label">Refusal</div>'
            f'<div class="refusal-text">Cedant could not answer this from the indexed corpus.</div>'
            f'<div class="refusal-text" style="color:#64748b;font-size:0.88rem;margin-top:0.5rem;">{sub}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(render_answer_with_badges(result), unsafe_allow_html=True)

        if result.hallucinated_citations:
            halluc_html = ", ".join(
                f"<code>{html.escape(c)}</code>" for c in result.hallucinated_citations
            )
            plural = len(result.hallucinated_citations) > 1
            st.markdown(
                f'<div class="halluc-banner">'
                f'<b>Hallucinated citation{"s" if plural else ""}:</b> '
                f'the model emitted {halluc_html}, which {"do" if plural else "does"} '
                f'not correspond to any retrieved chunk. The eval harness records this as a quality signal.'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown(render_metrics_row(result, top_k_used), unsafe_allow_html=True)

    if result.used_chunks:
        ordinal_map = build_ordinal_map(result.answer)
        retrieved_ids = {h.payload["chunk_id"] for h in result.used_chunks}
        cited_in_order = [cid for cid in ordinal_map if cid in retrieved_ids]
        cited_set = set(cited_in_order)
        by_id = {h.payload["chunk_id"]: h for h in result.used_chunks}

        n_cited = len(cited_in_order)
        n_uncited = len(result.used_chunks) - n_cited
        if n_cited and n_uncited:
            heading_suffix = f"{n_cited} cited · {n_uncited} retrieved but uncited"
        elif n_cited:
            heading_suffix = f"{n_cited} cited"
        else:
            heading_suffix = f"{n_uncited} retrieved · none cited"

        st.markdown(
            f'<div class="section-heading">Sources<span class="count">{heading_suffix}</span></div>',
            unsafe_allow_html=True,
        )

        for cid in cited_in_order:
            hit = by_id[cid]
            st.markdown(
                render_source_card(hit, ordinal=ordinal_map[cid], cited=True),
                unsafe_allow_html=True,
            )

        for hit in result.used_chunks:
            if hit.payload["chunk_id"] not in cited_set:
                st.markdown(
                    render_source_card(hit, ordinal=None, cited=False),
                    unsafe_allow_html=True,
                )
