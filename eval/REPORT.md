# Evaluation report

Generated 2026-08-18T18:34:51.880391+00:00 by `uv run python -m eval.run_eval`.

## Run provenance

| Setting | Value |
|---|---|
| Reasoning model | `openai/gpt-4o` |
| Vision tier | `scripted` |
| Embedding model | `openai/text-embedding-3-small` |
| Temperature | 0.2 |
| Corpus documents | 43 |
| Golden-set size | 28 |
| Profile | `overwaterer` |
| Total tokens | 386,964 in / 60,256 out (447,220 total) |
| Total cost | $1.5345 |

## Headline metrics

| Metric | Score |
|---|---|
| Top-1 diagnostic accuracy | 89.3% |
| Top-3 diagnostic accuracy | 96.4% |
| Context precision (ranked passages only) | _not measured_ (0 of 28 scored) |
| Context recall | 94.6% |
| Faithfulness | 69.8% |
| Answer relevancy | 59.2% |

28 cases scored, of which **0 failed** and are counted in the denominator rather than dropped. 1 top-1 miss landed on a disorder the case listed as a confusable neighbour.

No case needed a second attempt.

## By category

| Category | Cases | Top-1 | Top-3 |
|---|---|---|---|
| environmental | 4 | 100.0% | 100.0% |
| fungal | 4 | 100.0% | 100.0% |
| light | 3 | 66.7% | 100.0% |
| nutrient | 6 | 66.7% | 83.3% |
| other | 2 | 100.0% | 100.0% |
| pest | 5 | 100.0% | 100.0% |
| watering | 4 | 100.0% | 100.0% |

## Stability

8 cases run 5 times each, on byte-identical input: `aphids-clustered-new-growth-hibiscus`, `botrytis-grey-mould-spent-flowers`, `calcium-deficiency-crinkled-new-leaf`, `cold-draught-one-sided-blackening-fiddle-leaf`, `etiolation-leggy-stretched-wandering-jew`, `fungal-leaf-spot-target-spots-schefflera`, `fungus-gnats-flies-over-damp-soil`, `heat-stress-wilting-heatwave-olive`.

| Measure | Value |
|---|---|
| Top-1 agreement | 100.0% |
| Candidate-set churn | 23.2% |
| Clarifying-question drift | 59.2% |

Churn is mean pairwise Jaccard distance between candidate sets: 0% identical, 100% disjoint. Question drift is the same measure over the clarifying questions asked, reported separately because those are model-generated — without it, question variance would read as diagnostic instability.

Top-1 agreement and candidate-set churn normalise disorder-id formatting (`insufficient_light` vs `insufficient-light`) before comparing; figures from runs recorded before this normalisation was added to `stability()` were computed without it and may overstate disagreement slightly.

## What this does not measure

**The vision layer.** Golden cases supply symptoms as text and are injected past `identify_plant` and `assess_symptoms`, so nothing here says anything about species identification or symptom extraction from a photograph. Every metric above scores retrieval and reasoning only.

**Chat.** The chat agent is not exercised, and its token usage is not tracked at all (`M17`).

**Real-world photograph quality.** Every case assumes a usable photo; the quality gate is scripted to pass.
