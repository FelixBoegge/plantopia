## Context

See `proposal.md` — Why. What shapes the approach here is where the existing pieces already
sit.

`identify_plant` is one node between `quality_check` and `assess_symptoms`. It calls the
vision model once, writes a `SpeciesGuess` to state, and returns early when `state.species` is
already set — which is how a re-check of an identified plant skips it. `select_questions`
chooses the clarifying questions and writes them to state; `gather_context`, a separate node,
does nothing but `interrupt()`. They are separate deliberately: LangGraph replays a node's
body from the top on resume, so any model call in the same node as the interrupt would fire
again on every resume. Anything added before the interrupt has to respect that boundary.

Two existing tools set the pattern for an outside service. `tools/weather.py` needs no key and
returns `None` on every failure. `tools/web_search.py` takes `api_key: str | None` and returns
an empty list when it is absent — the key arrives from `Settings` through `Deps`, and the tool
itself decides nothing about configuration. `U1` records that the web-search path has never
run against the real service for want of a key, which is the outcome to avoid repeating here.

`tests/api/test_question_shape_agrees.py` now pins the interrupt's question payload against
`agent.schemas.Question`, because that payload travels in a stream event and has no OpenAPI
schema behind it. Anything else added to that payload has the same problem and needs the same
treatment.

## Goals / Non-Goals

**Goals:**

- A second identification that is genuinely independent — different evidence, different
  failure modes — and that can be compared against the first.
- Identification provenance recorded on the diagnosis, so a wrong answer can later be
  attributed to the identification or to the reasoning.
- No added model spend, and no added pause.
- Degradation that is real rather than nominal: the no-key path is the path this project
  actually runs on until a key exists, so it must be the one that is exercised first.

**Non-Goals:**

- Concurrency between the two identifications. See the first decision below.
- Any change to how a species is *used* once chosen. Downstream nodes read
  `state.species` exactly as they do today.
- A per-account or per-day quota for the identification service. It is free and rate-limited
  by the provider; exceeding it degrades like any other failure.

## Decisions

### The vision call is extended, not duplicated, and the two identifications run in sequence

§14.1 says both identifications run in parallel. They will not, and the reason is the organ
tagging: the service takes each photograph's organ as an input, so the organs must be known
*before* it is called, and the cheapest place to determine them is the vision request that is
already examining the same photographs. That makes the order vision → service, which is
sequential by construction.

The alternative that preserves parallelism is a separate gate-tier call to tag organs, so the
service can be asked at the same time as the vision model. That is one more model call on
every diagnosis, for a latency saving of one to two seconds on a run that takes ninety. Cost
is a standing constraint on this project and latency is not, so the trade goes the other way.

`SpeciesGuess` gains the organs alongside the guess — one schema, one call. Concretely the
vision model is asked for its species guess *and* the organ of each photograph in the same
structured response.

### The candidates are a separate block in the interrupt payload, not extra questions

A clarifying question is a key, a sentence, a kind and some options. A candidate is a species,
a method, a confidence and possibly a scientific name. Squeezing one into the other would mean
either a `Question` that carries data no question has, or a chooser rendered from stringly
options with the provenance lost — and the provenance is the entire reason the choice is worth
showing.

So `interrupt()` carries `{"questions": [...], "identification": {...}}`, and the resume
payload carries the chosen species alongside the answers. `Question` is untouched, which
keeps `test_question_shape_agrees.py` meaningful; the new block gets an agreement test of its
own on the same reasoning, because it travels the same way and is invisible to OpenAPI for the
same reason.

### Where the choice is applied

`gather_context` already writes `answers` from the resume payload. It will also write
`species` when the payload names one — a plain state write in a node that does nothing else,
so the resume-replay hazard does not arise. When the payload names none, state is left as
`identify_plant` set it, and the recorded provenance says unconfirmed.

Rejected: applying the choice in `select_questions`. It runs before the interrupt and would
have to guess.

### Provenance is an enum on the diagnosis, defaulting to unknown

`Diagnosis` gains two columns: the method that produced the species, and whether a person
confirmed it. Nullable, with existing rows reading as unknown — a backfill would have to
invent a provenance for diagnoses made when only one method existed, and "unknown" is the
true answer for those.

`SpeciesGuess` carries the same provenance in state so the node that persists it does not have
to reconstruct where the species came from.

### The adapter is gated on the key and returns nothing on every failure

`tools/plantnet.py`, taking `api_key: str | None` like `web_search_plant_info`, returning an
empty candidate list for a missing key, a timeout, a 429, a transport error or an unparseable
body. The node treats an empty list and a failed call identically; only the run's recorded
error distinguishes them, and only for somebody reading the log afterwards.

### The request shape is verified against the reference before it is written into a test

`U2` is the precedent and it is worth restating: a model slug taken from a documentation fetch
was written into the code, flagged as unverified, and turned out not to exist. The same
failure is available here — a wrong field name in the multipart body, or an organ vocabulary
that does not match theirs, produces an adapter whose tests pass against a fixture recorded
from an assumption.

So the first task against the real service is a single manual call with a real key, whose
response is saved as the fixture every later test uses. The fixture is recorded, not written.

### Attribution lives with the component that renders a candidate

Not on the wizard page, not in the footer. A term of use satisfied by remembering to add
something to each new screen is one that will be unsatisfied on the third screen. Putting it
inside the component that renders a service-derived candidate makes omitting it require
deleting it.

## Risks / Trade-offs

- **A third party on the diagnosis critical path** → every failure mode degrades to today's
  behaviour, and the no-key path is implemented and tested before the with-key path, so the
  degradation is the default rather than an afterthought. A short timeout, well inside the
  patience of a ninety-second run.
- **The organ vocabulary is theirs, not ours** → the vision model is asked for a value from
  their vocabulary, and an unrecognised value is sent as no organ rather than as a guess. A
  test pins our enum against the values the adapter will send.
- **Two identifications that disagree could read as the system being unsure of itself** →
  that is what it is, and saying so is the point; the interface says which method thought
  what rather than presenting a bare list. Where they agree, one candidate is shown and the
  agreement is stated.
- **The choice is skippable, so most people will skip it** → intended. The default is the
  highest-confidence candidate, which is what happens today; what changes is that the record
  says nobody confirmed it.
- **Identification accuracy is still unmeasured** → this change makes it measurable and does
  not measure it. Recorded as a limitation with the shape of the missing thing named: an
  image-based golden set.
- **The evaluation harness must not move** → it injects past `identify_plant` entirely, so
  nothing here is on its path. Verified by running it, not by reasoning about it.

## Migration Plan

Additive. One migration adds two nullable columns to `diagnoses`; existing rows read as
unknown provenance. Nothing existing changes shape.

Order, which is also the order the risk retires:

1. The adapter and its configuration, with the no-key path first.
2. One real call with a real key; record the fixture from the response.
3. Organs on the vision call, and the second identification in `identify_plant`.
4. The candidates through the interrupt and back, and the recorded provenance.
5. The wizard's species field, the chooser, and the attribution.

**Rollback** is removing the key: with no credential the adapter returns nothing, the choice
is never offered, and the pipeline is what it is today. That is a property worth having
independently of rollback, and it is the same path a deployment without a key takes.

## Open Questions

- **Whether a plant's species should be re-openable after a diagnosis.** Somebody who realises
  the identification was wrong currently has no way to correct it except a new diagnosis. That
  is plant editing rather than identification, it does not change anything here, and it wants
  the timeline change's surfaces to be worth doing.
