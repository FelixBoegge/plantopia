# Evaluation report

Generated 2026-08-14T07:37:10.459833+00:00 by `uv run python -m eval.run_eval`.

## Run provenance

| Setting | Value |
|---|---|
| Reasoning model | `openai/gpt-4o` |
| Vision tier | `scripted` |
| Embedding model | `openai/text-embedding-3-small` |
| Temperature | 0.2 |
| Corpus documents | 43 |
| Golden-set size | 28 |
| Total tokens | 192,500 in / 53,937 out (246,437 total) |
| Total cost | $1.0168 |

## Headline metrics

| Metric | Score |
|---|---|
| Top-1 diagnostic accuracy | 75.0% |
| Top-3 diagnostic accuracy | 82.1% |
| Context precision | 63.3% (16 of 28 scored) |
| Context recall | 73.8% (14 of 28 scored) |
| Faithfulness | 47.5% (13 of 28 scored) |
| Answer relevancy | 52.5% (18 of 28 scored) |

28 cases scored, of which **0 failed** and are counted in the denominator rather than dropped. 2 top-1 misses landed on a disorder the case listed as a confusable neighbour.

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

8 cases run 5 times each, on byte-identical input: `aphids-clustered-new-growth-hibiscus`, `botrytis-grey-mould-spent-flowers`, `calcium-deficiency-crinkled-new-leaf`, `cold-draught-one-sided-blackening-fiddle-leaf`, `etiolation-leggy-stretched-wandering-jew`, `fungal-leaf-spot-target-spots-schefflera`, `fungus-gnats-flies-over-damp-soil`, `heat-stress-wilting-heatwave-olive`.

| Measure | Value |
|---|---|
| Top-1 agreement | 92.5% |
| Candidate-set churn | 21.3% |
| Clarifying-question drift | 57.1% |

Churn is mean pairwise Jaccard distance between candidate sets: 0% identical, 100% disjoint. Question drift is the same measure over the clarifying questions asked, reported separately because those are model-generated — without it, question variance would read as diagnostic instability.

## What this does not measure

**The vision layer.** Golden cases supply symptoms as text and are injected past `identify_plant` and `assess_symptoms`, so nothing here says anything about species identification or symptom extraction from a photograph. Every metric above scores retrieval and reasoning only.

**Chat.** The chat agent is not exercised, and its token usage is not tracked at all (`M17`).

**Real-world photograph quality.** Every case assumes a usable photo; the quality gate is scripted to pass.
