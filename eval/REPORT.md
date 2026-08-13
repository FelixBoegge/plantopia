# Evaluation report

Generated 2026-08-13T15:03:10.449588+00:00 by `uv run python -m eval.run_eval`.

## Run provenance

| Setting | Value |
|---|---|
| Reasoning model | `openai/gpt-4o` |
| Vision tier | `scripted` |
| Embedding model | `openai/text-embedding-3-small` |
| Temperature | 0.2 |
| Corpus documents | 43 |
| Golden-set size | 28 |

## Headline metrics

| Metric | Score |
|---|---|
| Top-1 diagnostic accuracy | 75.0% |
| Top-3 diagnostic accuracy | 82.1% |
| Context precision | 65.1% |
| Context recall | 72.7% |
| Faithfulness | 56.8% |
| Answer relevancy | 42.0% |

28 cases scored, of which **0 failed** and are counted in the denominator rather than dropped. 1 top-1 misses landed on a disorder the case listed as a confusable neighbour.

## By category

| Category | Cases | Top-1 | Top-3 |
|---|---|---|---|
| environmental | 4 | 75.0% | 100.0% |
| fungal | 4 | 100.0% | 100.0% |
| light | 3 | 66.7% | 100.0% |
| nutrient | 6 | 33.3% | 33.3% |
| other | 2 | 50.0% | 50.0% |
| pest | 5 | 100.0% | 100.0% |
| watering | 4 | 100.0% | 100.0% |

## Stability

8 cases run 5 times each, on byte-identical input.

| Measure | Value |
|---|---|
| Top-1 agreement | 97.5% |
| Candidate-set churn | 19.2% |
| Clarifying-question drift | 62.1% |

Churn is mean pairwise Jaccard distance between candidate sets: 0% identical, 100% disjoint. Question drift is the same measure over the clarifying questions asked, reported separately because those are model-generated — without it, question variance would read as diagnostic instability.

## What this does not measure

**The vision layer.** Golden cases supply symptoms as text and are injected past `identify_plant` and `assess_symptoms`, so nothing here says anything about species identification or symptom extraction from a photograph. Every metric above scores retrieval and reasoning only.

**Chat.** The chat agent is not exercised, and its token usage is not tracked at all (`M17`).

**Real-world photograph quality.** Every case assumes a usable photo; the quality gate is scripted to pass.
