# Evaluation report

Generated 2026-08-19T10:51:29.255352+00:00 by `uv run python -m eval.run_eval`.

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
| Total tokens | 388,397 in / 61,048 out (449,445 total) |
| Total cost | $1.5444 |

## Headline metrics

| Metric | Score |
|---|---|
| Top-1 diagnostic accuracy | 89.3% |
| Top-3 diagnostic accuracy | 96.4% |
| Context precision (ranked passages only) | 54.5% |
| Context recall | 98.2% |
| Faithfulness | 74.4% |
| Answer relevancy | 58.2% |

28 cases scored, of which **0 failed** and are counted in the denominator rather than dropped. 1 top-1 miss landed on a disorder the case listed as a confusable neighbour.

No case needed a second attempt.

## By category

| Category | Cases | Top-1 | Top-3 |
|---|---|---|---|
| environmental | 4 | 100.0% | 100.0% |
| fungal | 4 | 100.0% | 100.0% |
| light | 3 | 66.7% | 100.0% |
| nutrient | 6 | 83.3% | 100.0% |
| other | 2 | 50.0% | 50.0% |
| pest | 5 | 100.0% | 100.0% |
| watering | 4 | 100.0% | 100.0% |

## Stability

8 cases run 5 times each, on byte-identical input: `aphids-clustered-new-growth-hibiscus`, `botrytis-grey-mould-spent-flowers`, `calcium-deficiency-crinkled-new-leaf`, `cold-draught-one-sided-blackening-fiddle-leaf`, `etiolation-leggy-stretched-wandering-jew`, `fungal-leaf-spot-target-spots-schefflera`, `fungus-gnats-flies-over-damp-soil`, `heat-stress-wilting-heatwave-olive`.

| Measure | Value |
|---|---|
| Top-1 agreement | 100.0% |
| Candidate-set churn | 21.7% |
| Clarifying-question drift | 58.3% |

Churn is mean pairwise Jaccard distance between candidate sets: 0% identical, 100% disjoint. Question drift is the same measure over the clarifying questions asked, reported separately because those are model-generated — without it, question variance would read as diagnostic instability.

Top-1 agreement and candidate-set churn normalise disorder-id formatting (`insufficient_light` vs `insufficient-light`) before comparing; figures from runs recorded before this normalisation was added to `stability()` were computed without it and may overstate disagreement slightly.

## What this does not measure

**The vision layer.** Golden cases supply symptoms as text and are injected past `identify_plant` and `assess_symptoms`, so nothing here says anything about species identification or symptom extraction from a photograph. Every metric above scores retrieval and reasoning only.

**Chat.** The chat agent is not exercised, and its token usage is not tracked at all (`M17`).

**Real-world photograph quality.** Every case assumes a usable photo; the quality gate is scripted to pass.

---

## This baseline is stale, and knowingly so

Two changes have landed since this run that alter what every golden case is shown. Neither has
been measured, because a run costs about $1.55 and the standing instruction is to keep that
spend low; both are recorded here so the next run is read as a *new baseline* rather than
compared against these figures.

**The clarifying questions were rewritten** (`M39`). The harness uses a real reasoning model
for the tier that selects those questions, so rewriting the prompt to ask about a plant's
recent treatment — and raising the count from at most two to three or four — changes each
case's `situation` string. `answer_relevancy` and the question-drift figure read that string
directly.

**The weather is now a dated series rather than five numbers** (`add-granular-weather`,
2026-08-31). Four outdoor cases carry `location_text: "Berlin"` and fetch real weather:
`heat-stress-wilting-heatwave-olive`, `powdery-mildew-dusty-coating-courgette`,
`rust-orange-pustules-rose`, and `magnesium-deficiency-marbled-tomato-leaves`. Where they used
to see `low 11.4C high 36.1C 31.1mm 0 frost 2 heat`, they now see named events with dates —
"Above 32.0 °C from 2026-08-14 to 2026-08-15, up to 36.1 °C" — plus the seven days before the
photograph and seven ahead, roughly 300 tokens where the old sentence was about 20.

Which way each metric should be expected to move, and why:

- **Top-1 and top-3 accuracy on those four cases could go either way, and down is a real
  possibility.** The dated series is strictly more information, but it is also more *specific*,
  and specificity can contradict a case's premise out loud. `heat-stress-wilting-heatwave-olive`
  asserts a heatwave; the aggregate `2 heat days` was vague enough to be read as supporting it,
  while "one heat spell, two days, a fortnight before the photograph" argues against heat stress
  being the current cause. If that case drops, the diagnosis has become *more* honest and the
  score has become worse, and the score is the thing that is wrong.
- **Faithfulness should rise slightly** on those cases: claims about the weather can now be
  grounded in dated context rather than inferred from an aggregate.
- **Context precision and recall should not move.** They score retrieved corpus passages, and
  the weather block is not retrieval.
- **The 24 indoor cases should not move at all.** They fetch no weather, and nothing else about
  their prompt changed in this change. If they *do* move, that is the signal that something
  unintended reached them, and it is worth more attention than any movement in the four.
- **Cost per run rises a little.** Four cases × ~280 extra prompt tokens is under a cent.

The weather these four cases see is also **not reproducible**: with no capture date in the
fixtures the window anchors on the day the harness runs, so two runs a week apart score against
different weather. That was already true of the aggregates and is merely more visible now, but
it means the four outdoor cases carry noise the other 24 do not. Pinning a capture date into
those fixtures would fix it and is worth doing before the next run is treated as a baseline.
