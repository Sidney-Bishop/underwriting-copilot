# Synthetic corpus documents

This directory contains three synthetic internal documents drafted per
D003 ("synthetic documents demonstrating the system's extension to
internal/proprietary content beyond the public regulatory and corporate
documents indexed in v1").

The documents describe a **fictional** Lloyd's syndicate, **Sycamore Re
Syndicate 4271**, operated by **Sycamore Underwriting Limited**. The
syndicate, the Managing Agent, the named officers, the document IDs,
the quantitative limits, and the revision histories are all invented.
Any resemblance to real Lloyd's syndicates, Managing Agents, or their
internal documents is incidental.

## Documents

- **`sycamore_risk_appetite_statement.md`** — Board-level Risk Appetite
  Statement for 2026 YoA. Two-line framework (hard limits + soft
  preferences), quantitative limits per risk category, climate/ESG
  appetite section, escalation pathways.
- **`sycamore_delegated_authority_matrix.md`** — Underwriting Authority
  Schedule version 5.2. Four-level hierarchy (Active Underwriter →
  Class Underwriter → Deputy → Coverholder), per-class authority limits
  for Property D&F, Energy, Specialty Treaty, Marine & Cargo, Coverholder
  requirements per Lloyd's standards.
- **`sycamore_thermal_coal_underwriting_policy.md`** — Operational policy
  implementing the RAS's climate commitments. Decision framework for
  thermal coal exposure across Open Market and Binding Authority business.

## What these documents demonstrate

The three documents together demonstrate the **kind** of internal
content a reinsurance underwriting copilot would need to handle in
production deployment, alongside the publicly-published regulatory and
sustainability documents indexed in v1:

- Risk-appetite statements with quantitative ceilings and qualitative
  principles
- Authority schedules with class-specific limits and Coverholder rules
- Operational policies that implement higher-level commitments

The documents cross-reference each other and the public corpus
documents (PRA SS1/21 for operational resilience, PRA SS5/25 for
climate, Lloyd's Sustainable Marketplace Initiative for ESG), modelling
the way real internal documents sit within a wider regulatory and
voluntary-standards landscape.

## Status: not indexed in v1

These documents are **not** part of the Qdrant index used by the
retrieve→answer pipeline in v1. They exist as demonstration content
only. The corpus indexed in v1 remains the original 6 PDFs (PRA SS1/21,
SS3/19, SS5/25; EIOPA SoG; Munich Re Sustainability 2023; Swiss Re
Sustainability 2024); the eval harness measures against that corpus
only.

## v2 work-stream for these documents

A v2 deployment that included these documents in the indexed corpus
would require:

1. **Ingestion** through the Docling chunking pipeline, producing
   chunk_ids of the form
   `sycamore_risk_appetite_2026__NNNN__section-slug`,
   `sycamore_delegated_authority_2026__NNNN__section-slug`, and
   `sycamore_thermal_coal_2026__NNNN__section-slug`.
2. **Re-indexing** of the BGE-M3 dense and BM25 sparse vectors against
   the extended corpus.
3. **Extended benchmark questions** covering the new internal content
   — single-chunk questions, multi-chunk questions within these
   documents, and cross-document questions between the public
   regulatory documents and these synthetic internal ones (e.g.,
   "How does Sycamore Re's thermal coal underwriting policy align with
   PRA SS5/25's climate-related risk-management expectations?"). The
   cross-document subset is currently the smallest answerable subset
   (n=10 in v1); these synthetic documents would naturally expand it.
4. **Access control** — internal documents in production would carry
   access restrictions per role, which the existing retrieval filter
   parameters (`issuer_type`, `jurisdiction`) provide the starting
   point for but would need extending with explicit per-document or
   per-section ACL semantics.

These steps are not part of v1 and are not load-bearing for the 5-day
artefact. They are the kind of work a real deployment would require to
move from "indexes public documents" to "indexes the firm's own
documents alongside public ones".
