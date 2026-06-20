# Eval Report — D014 Sweep

**Generated from:** `raw.jsonl` at `2026-06-18T15-32-07Z`

## Run metadata

- Models swept: `gemma-4-31B-it-MLX-6bit`, `Qwen3.6-35B-A3B-4bit`
- Prompts swept: `v1`, `v2`
- Benchmark: `eval/benchmark.toml`
- Question count after filter: 70
- Total cells: 280
- Errored cells: 0
- Wall-clock: 2739.0s (45.7 min)
- Run completed cleanly: True
- top_k: 5

## Headline: per-cell summary

Metrics over 44 answerable + 26 refusal questions per cell.

| Cell | citation_recall | citation_precision | citation_f1 | refusal | hallucinations | latency_ans | latency_ref |
|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B-4bit × v1 | 0.386 | 0.296 | 0.319 | 26/26 | 23 | 3.3s | 0.8s |
| Qwen3.6-35B-A3B-4bit × v2 | 0.545 | 0.483 | 0.489 | 26/26 | 7 | 3.4s | 0.9s |
| gemma-4-31B × v1 | 0.598 | 0.524 | 0.537 | 26/26 | 0 | 21.7s | 8.4s |
| gemma-4-31B × v2 | 0.598 | 0.520 | 0.533 | 26/26 | 0 | 22.9s | 8.6s |

## Subset analysis — citation_recall by question subset

Where the headline numbers come from. Differences between subsets localize whether a model gap is concentrated in a specific question type or spread evenly.

| Subset | n | Qwen3.6-35B-A3B-4bit × v1 | Qwen3.6-35B-A3B-4bit × v2 | gemma-4-31B × v1 | gemma-4-31B × v2 |
|---|---|--- | --- | --- | ---|
| all_answerable | 44 | 0.386 | 0.545 | 0.598 | 0.598 |
| excluding_retrieval_misses | 33 | 0.515 | 0.727 | 0.798 | 0.798 |
| single_chunk | 22 | 0.591 | 0.727 | 0.773 | 0.773 |
| single_chunk_retrievable | 17 | 0.765 | 0.941 | 1.000 | 1.000 |
| multi_chunk | 12 | 0.208 | 0.542 | 0.583 | 0.583 |
| within_document | 34 | 0.456 | 0.662 | 0.706 | 0.706 |
| within_document_retrievable | 27 | 0.574 | 0.833 | 0.889 | 0.889 |
| cross_document | 10 | 0.150 | 0.150 | 0.233 | 0.233 |

**Subset definitions:**
- `all_answerable` (44 q): All answerable questions
- `excluding_retrieval_misses` (33 q): Excluding questions where retrieval failed across all cells
- `single_chunk` (22 q): Single-chunk questions (one gold chunk per question)
- `single_chunk_retrievable` (17 q): Single-chunk questions with retrieval working
- `multi_chunk` (12 q): Multi-chunk questions (multiple gold chunks, same document)
- `within_document` (34 q): Within-document questions (single + multi, no cross-document)
- `within_document_retrievable` (27 q): Within-document with retrieval working
- `cross_document` (10 q): Cross-document synthesis questions (gold chunks span two issuers)

## Refusal correctness by category

Each cell: `correct / total`. Higher is better; the production-relevant failure mode is should-refuse questions answered as if confidently known.

| Category | n | Qwen3.6-35B-A3B-4bit × v1 | Qwen3.6-35B-A3B-4bit × v2 | gemma-4-31B × v1 | gemma-4-31B × v2 |
|---|---|--- | --- | --- | ---|
| refusal_adjacent | 10 | 10/10 | 10/10 | 10/10 | 10/10 |
| refusal_false_premise | 6 | 6/6 | 6/6 | 6/6 | 6/6 |
| refusal_out_of_corpus | 10 | 10/10 | 10/10 | 10/10 | 10/10 |

## Retrieval miss diagnostic

**11 of 44 answerable questions (25.0%)** had `retrieval_recall = 0` across **all** cells — the gold chunks were not retrieved by any model/prompt combination. This localizes the failures as upstream of the answer model; see Q12 in `decisions.md`.

Affected questions:
- `q001`
- `q004`
- `q013`
- `q042`
- `q044`
- `q046`
- `q047`
- `q051`
- `q053`
- `q055`
- `q056`

## Hallucination breakdown

Citations the model emitted that did **not** correspond to any retrieved chunk. Confabulation signal — qualitatively different from 'wrong but real chunk cited'.

| Cell | Hallucinations (all answerable cells) |
|---|---|
| Qwen3.6-35B-A3B-4bit × v1 | 23 |
| Qwen3.6-35B-A3B-4bit × v2 | 7 |
| gemma-4-31B × v1 | 0 |
| gemma-4-31B × v2 | 0 |

## Latency

Mean and median wall-clock per cell, split by question type.

| Cell | mean_ans | median_ans | mean_ref | median_ref |
|---|---|---|---|---|
| Qwen3.6-35B-A3B-4bit × v1 | 3.3s | 3.0s | 0.8s | 0.6s |
| Qwen3.6-35B-A3B-4bit × v2 | 3.4s | 3.2s | 0.9s | 0.7s |
| gemma-4-31B × v1 | 21.7s | 19.9s | 8.4s | 8.0s |
| gemma-4-31B × v2 | 22.9s | 21.1s | 8.6s | 8.3s |

## Per-question detail — answerable

Each cell shows `citation_recall` (None for refusal questions, which appear in the next table). Categories abbreviated for table width.

| ID | category | Qwen3.6-35B-A3B-4bit × v1 | Qwen3.6-35B-A3B-4bit × v2 | gemma-4-31B × v1 | gemma-4-31B × v2 |
|---|---|--- | --- | --- | ---|
| `q001` | `single_chunk_pra_climate` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q002` | `single_chunk_pra_climate` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q003` | `single_chunk_pra_climate` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q004` | `single_chunk_pra_climate` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q005` | `multi_chunk_pra_climate` | 0.00 | 1.00 | 1.00 | 1.00 |
| `q006` | `multi_chunk_pra_climate` | 0.00 | 0.50 | 0.50 | 0.50 |
| `q007` | `multi_chunk_pra_climate` | 0.00 | 0.50 | 0.50 | 0.50 |
| `q008` | `multi_chunk_eiopa` | 0.00 | 1.00 | 1.00 | 1.00 |
| `q009` | `single_chunk_eiopa` | 0.00 | 1.00 | 1.00 | 1.00 |
| `q010` | `single_chunk_eiopa` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q011` | `single_chunk_eiopa` | 0.00 | 1.00 | 1.00 | 1.00 |
| `q012` | `single_chunk_eiopa` | 0.00 | 1.00 | 1.00 | 1.00 |
| `q013` | `single_chunk_munich_re` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q014` | `single_chunk_munich_re` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q015` | `single_chunk_munich_re` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q016` | `single_chunk_munich_re` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q017` | `multi_chunk_munich_re` | 0.50 | 0.50 | 0.50 | 0.50 |
| `q018` | `single_chunk_swiss_re` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q019` | `single_chunk_swiss_re` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q020` | `single_chunk_swiss_re` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q021` | `single_chunk_swiss_re` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q022` | `multi_chunk_swiss_re` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q023` | `single_chunk_pra_opres` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q024` | `single_chunk_pra_opres` | 0.00 | 1.00 | 1.00 | 1.00 |
| `q025` | `cross_document` | 0.00 | 0.00 | 0.50 | 0.50 |
| `q026` | `cross_document` | 0.00 | 0.00 | 0.33 | 0.33 |
| `q041` | `cross_document` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q042` | `cross_document` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q043` | `cross_document` | 0.50 | 0.50 | 0.50 | 0.50 |
| `q044` | `cross_document` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q045` | `cross_document` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q046` | `cross_document` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q047` | `cross_document` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q048` | `cross_document` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q049` | `multi_chunk_pra_climate` | 0.50 | 0.50 | 0.50 | 0.50 |
| `q050` | `multi_chunk_pra_climate` | 0.00 | 1.00 | 1.00 | 1.00 |
| `q051` | `multi_chunk_munich_re` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q052` | `multi_chunk_munich_re` | 0.50 | 0.50 | 0.50 | 0.50 |
| `q053` | `multi_chunk_swiss_re` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q054` | `multi_chunk_pra_climate` | 0.00 | 0.00 | 0.50 | 0.50 |
| `q055` | `single_chunk_pra_climate` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q056` | `single_chunk_pra_climate` | 0.00 | 0.00 | 0.00 | 0.00 |
| `q057` | `single_chunk_munich_re` | 1.00 | 1.00 | 1.00 | 1.00 |
| `q058` | `single_chunk_swiss_re` | 1.00 | 0.00 | 1.00 | 1.00 |

## Per-question detail — refusal

Each cell shows `✓` (refused correctly) or `✗` (failed to refuse).

| ID | category | Qwen3.6-35B-A3B-4bit × v1 | Qwen3.6-35B-A3B-4bit × v2 | gemma-4-31B × v1 | gemma-4-31B × v2 |
|---|---|--- | --- | --- | ---|
| `q027` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q028` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q029` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q030` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q031` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q032` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q033` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q034` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q035` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q036` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q037` | `refusal_false_premise` | ✓ | ✓ | ✓ | ✓ |
| `q038` | `refusal_false_premise` | ✓ | ✓ | ✓ | ✓ |
| `q039` | `refusal_false_premise` | ✓ | ✓ | ✓ | ✓ |
| `q040` | `refusal_false_premise` | ✓ | ✓ | ✓ | ✓ |
| `q059` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q060` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q061` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q062` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q063` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q064` | `refusal_adjacent` | ✓ | ✓ | ✓ | ✓ |
| `q065` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q066` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q067` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q068` | `refusal_out_of_corpus` | ✓ | ✓ | ✓ | ✓ |
| `q069` | `refusal_false_premise` | ✓ | ✓ | ✓ | ✓ |
| `q070` | `refusal_false_premise` | ✓ | ✓ | ✓ | ✓ |

## Errored cells

_No cells errored. All cells completed cleanly._
