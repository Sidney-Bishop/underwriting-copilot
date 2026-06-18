"""Prompt versions for the D014 eval sweep.

The Day 2 N=3 demo found that Qwen3.6-35B-A3B-4bit (with thinking off)
produced two distinct citation-format failures:

  - Wrapper drift: ``[chunk_id=<real_id>]`` rather than ``[<real_id>]``
    (regex doesn't match; 0 valid citations on query 1).
  - Placeholder collapse: ``[chunk_id_1]``, ``[chunk_id_5]`` — the model
    treats the literal string ``chunk_id`` as the format and substitutes
    its own indices (13 hallucinated placeholders on query 2).

Both failure modes are consistent with the prompt using the literal
characters ``[chunk_id]`` as the metasyntactic variable name for the
format AND as instructive text. The model receives an ambiguous signal:
should it emit ``[<actual_id>]`` or echo the literal token ``[chunk_id]``?

Interpretation A (model property) says Qwen3.6 has weaker format
discipline than Gemma irrespective of prompt; this prompt change won't
close the gap. Interpretation B (prompt artifact) says the echo trap is
the cause; removing it should close most of the gap. The 2x2 sweep
({Gemma, Qwen} x {v1, v2}) tests this directly. See D014.

v2 changes:
  1. Metasyntactic variable name changed from ``chunk_id`` to ``<ID>``.
     The angle-bracket convention is unambiguously a placeholder.
  2. One concrete worked example with a real-looking chunk_id shape.
  3. Explicit prohibition against echoing the literal token.

No other content changes — refusal phrase, no-citation-invention rule,
and conciseness instruction all carry over verbatim from v1.
"""

from underwriting_copilot.answer import SYSTEM_PROMPT as _V1_FROM_ANSWER_PY

# v1: the prompt currently committed in answer.py. Imported by reference so
# the eval harness measures exactly what production uses, not a copy that
# could drift.
SYSTEM_PROMPT_V1 = _V1_FROM_ANSWER_PY

# v2: echo-trap fix. Self-contained string so eval has full diff control.
SYSTEM_PROMPT_V2 = """You are an underwriting copilot for a reinsurance company. \
You answer questions about regulatory and corporate documents using ONLY the \
sources provided in the user message. You never use information from your \
training data.

Citation format:
- Every factual claim in your answer MUST be followed by a citation in square \
brackets containing the source's actual chunk identifier. Write the identifier \
verbatim from the SOURCES section, with NOTHING else inside the brackets — no \
prefix, no equals sign, no quotes, no abbreviation.
- Worked example: if the SOURCES section lists a source as \
[pra_ss5-25_climate__0027__role-of-scenario-analysis], cite a claim from it as \
[pra_ss5-25_climate__0027__role-of-scenario-analysis], not as \
[chunk_id=pra_ss5-25_climate__0027__role-of-scenario-analysis] and not as \
[chunk_id_1] or [source_1]. The brackets contain the verbatim identifier and \
nothing else.
- A single sentence may carry multiple citations back-to-back: \
[<first_identifier>][<second_identifier>].
- Use only identifiers that appear verbatim in the SOURCES section. Never \
invent an identifier.

Refusal rule:
- If the SOURCES do not contain enough information to answer the QUESTION, \
respond with EXACTLY this phrase and nothing else:

I cannot answer this from the provided sources.

Keep answers concise. Quote source text only when exact wording matters."""


PROMPTS: dict[str, str] = {
    "v1": SYSTEM_PROMPT_V1,
    "v2": SYSTEM_PROMPT_V2,
}
"""Registry of prompt versions, keyed by short name.

The eval runner iterates ``PROMPTS.items()`` to sweep all versions
without hardcoding the list anywhere else.
"""
