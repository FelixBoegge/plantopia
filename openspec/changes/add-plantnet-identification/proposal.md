## Why

Every diagnosis rests on the species, and the species currently comes from one source: a
general-purpose vision model asked "what is this?". That guess is unverified, unfalsifiable
and silently confident — nothing in the system can tell a right answer from a wrong one, and
a wrong species widens every downstream judgement without ever announcing itself. The one
number that would say how good it is does not exist: golden cases inject symptoms past
`identify_plant`, so no figure in `eval/REPORT.md` describes identification at all.

Pl@ntNet is a second, independent method — a specialist classifier over 50,000+ species with
a published score, on a free tier that permits commercial use. Two methods that agree are
worth more than one that is confident. Two that disagree are worth more still: that is the
moment to ask the owner, who is standing in front of the plant and can settle it in a second.

This also closes the last piece of §14.1's original idea, which dissolved on contact with
`U2`: a reference-image knowledge base needed multimodal embeddings, no reachable model
provides them, and a local embedder meant ~2 GB of torch in the container. An external
classifier gets the same answer without either.

## What Changes

- **A Pl@ntNet adapter** in `tools/`, alongside the existing weather and web-search tools:
  photographs and their organs in, ranked species candidates with scores out. Gated on
  `PLANTOPIA_PLANTNET_API_KEY` exactly as web search is gated on Tavily's, and degrading the
  same way when it is absent.
- **The vision identification also reports each photograph's organ** — leaf, flower, fruit,
  bark or habit — because Pl@ntNet accepts those as input and is markedly more accurate with
  them. This extends the existing call's schema rather than adding a second call.
- **The owner chooses the species at the pause that already exists.** The clarifying
  interrupt gains an identification block carrying up to three candidates: the name they
  typed, if they typed one; Pl@ntNet's best match with its score; the vision model's
  suggestion. Where the two methods agree the block says so and offers one.
- **An optional species field under the upload widget**, so somebody who already knows can
  say so. Left blank, the pipeline behaves exactly as it does today.
- **Attribution.** *"Powered by Pl@ntNet"* is shown wherever a Pl@ntNet result appears. This
  is a condition of the free tier, not a courtesy.
- **The diagnosis records which method produced its species and whether the owner confirmed
  it**, so a later look at a wrong diagnosis can tell a bad identification from bad reasoning
  on a good one.

Not in scope, deliberately:

- **Measuring identification accuracy.** It needs an image-based golden set, which is its own
  change and its own dataset; the existing text-injected golden set cannot say anything about
  it. This change makes the number *measurable* by giving identification a recorded provenance
  and a second opinion to compare against; it does not produce the number.
- **Re-identifying an existing plant.** A re-check of an unidentified plant already routes
  through `identify_plant` and therefore gains this for free. Changing the species of a plant
  already identified is a plant-editing feature, not an identification one.

## Capabilities

### New Capabilities

- `species-identification`: How a plant's species is determined — the two independent methods,
  the organ tagging that feeds one of them, what happens when they disagree, what happens when
  either is unavailable, and what is recorded about which method won.

### Modified Capabilities

- `diagnosis-wizard`: The pause gains a species choice alongside its questions, and the upload
  step gains an optional species field. Both change what the wizard asks and what an answer
  may contain.
- `web-client`: A third-party attribution has to appear wherever its data does, and the
  identification choice is a control with its own accessibility obligations — it is the first
  place in the application where a person picks between machine judgements.

## Impact

- **New dependency on an external service.** The first one on the diagnosis critical path
  that is not OpenRouter. It must never be able to block a diagnosis: no key, a timeout, a
  429 past the 500/day free tier, or a malformed response all degrade to the behaviour that
  exists today.
- `agent/`: `SpeciesGuess` gains provenance, a new `ImageOrgan` enum, `identify_plant` calls
  both methods, `select_questions`/`gather_context` carry the choice through the interrupt.
- `tools/plantnet.py`, `core/config.py`, `data/models.py` (the diagnosis's recorded
  provenance and a migration), `api/` (the answer payload), `web/` (the upload field, the
  chooser, the attribution).
- **The evaluation harness must not move.** Golden cases are injected past identification, so
  its numbers should be identical. If they move, something here reached somewhere it should
  not have.
- **Cost is unchanged.** Pl@ntNet's free tier is free, and the organ tagging rides on a call
  that already happens rather than adding one.
