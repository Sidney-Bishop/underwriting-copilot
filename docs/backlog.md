# Backlog

A loose, low-ceremony list of things we *could* do next, roughly by value.
Not a roadmap, not a commitment. Cross items off (~~strikethrough~~) with a
one-line note on what came of them rather than deleting. Drop items that no
longer interest you, noting why so you don't re-add them by reflex.

- [ ] TODO

<!-- Append or integrate the items below into docs/backlog.md. -->
<!-- They reflect the state of the Q13 work-stream after 2026-06-20. -->

### Active

- **Q14 — HyDE evaluation on production-default cell** (branch:
  `v2.0-dev/q13-hyde-spike`). Falsification criterion stated in
  `docs/open_questions.md`. Next concrete step: implement
  `query_rewriter.py` and the `use_hyde` flag in `Retriever.retrieve()`.

- **Q15 — Gold-labelling review on q044, q046, q047, q053.** Independent
  of HyDE but should resolve before Q14's final evaluation to avoid
  confounding HyDE credit/blame with gold-tag movement.

### Deferred (Q13 alternative remediation paths)

- **Instruct-tuned embeddings** (e.g. `gte-Qwen2-7B-instruct`,
  NV-Embed-v2). Cleanest architectural fix for query/chunk language
  asymmetry but requires re-indexing the full corpus and larger model
  memory footprint. Re-evaluate only if Q14 fails its falsification
  criterion.

- **Query expansion via term dictionary.** Lowest-impact, lowest-cost
  path. Does not address paraphrase mismatch. Recorded for
  completeness; unlikely to be picked up unless higher-impact paths
  are exhausted.

### Future (raised this session, not yet Q-numbered)

- **Query decomposition for cross-document synthesis** (informed by
  q042). Split a question naming N sources into N single-source
  sub-queries, retrieve separately, merge. Likely Q16 or later;
  scoped only after Q14 and Q15 close.

- **Embedding pathology investigation on q004, q055, q056.** Three
  strict misses where surface match exists but dense retrieval missed.
  Mechanism is not paraphrase asymmetry as described in Q12. Worth a
  small probe: re-embed the gold and adjacent chunks, inspect the
  dense rank of the gold for each query, look for any chunk-content
  boundary or normalisation anomaly. Could be a separate Q-question
  if the diagnostic surfaces something concrete.

### Housekeeping

- **`scripts/probes/dump_chunks.py` referenced but missing.** The
  `eval/benchmark.toml` header (line 27) refers to a script that does
  not exist in the working tree. Either restore the script (so a
  reviewer can re-validate the 461 chunk_ids against the index from
  scratch) or remove the reference from the benchmark header. Low
  priority but worth doing once Q14 settles.
