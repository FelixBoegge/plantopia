## Context

See `proposal.md` — Why. What shapes the approach is how small and how load-bearing the
existing piece is.

`tools/care_profiles.py` is 94 lines: a dict of 18 `CareProfile` objects, an alias table
mapping scientific and alternate names onto its keys, and `lookup_plant_care_profile(species)`
returning `CareProfile | None`. It reaches the graph through `Deps.care_profile`, a
`Callable[[str], CareProfile | None]`, and has exactly two consumers:

- `agent/nodes/enrich.py:_care_baseline` renders it into one sentence on the diagnosis prompt
  and records `lookup_plant_care_profile` in `tools_used`.
- `agent/chat_agent.py:lookup_plant_care_profile` returns it as text to the chat model, and on
  a miss returns a sentence telling the model to search instead.

`CareProfile` itself is five fields: `species`, `light`, `water`, `temperature_c` as an
`(int, int)` tuple, `humidity`. Nothing else in the codebase reads it.

`tools/web_search.py:web_search_plant_info` returns `list[Passage]` and returns `[]` on any
failure including a missing key. Confirmed working against Tavily on 2026-08-31: four passages
for a real query, and — importantly — *Ocimum basilicum* content in answer to an *Ocimum
africanum* question.

`core/guards.py` has `wrap_untrusted` and `scan_for_injection`, already used by `diagnose` on
retrieved passages.

## Goals / Non-Goals

**Goals:**

- A baseline for the long tail of species Pl@ntNet can name and the curated list cannot.
- Paid for once per species, not once per run.
- Honest about which profiles are guesses, where a person can see it.
- No new external service.

**Non-Goals:**

- **Growing the curated set.** Hand-writing more profiles is a content job with no engineering
  in it, and the whole point here is that no hand-written set reaches 50,000 species.
- **Correcting or re-researching a stored profile.** No refresh, no expiry, no feedback loop.
  A profile that turns out wrong is a `known-limitations` row, not a subsystem.
- **A screen for care profiles.** The chat reply is where this material is read today, and
  that is the surface the honesty requirement attaches to. A dedicated view belongs with
  `add-plant-timeline`, which is where the plant's other per-species material will live.
- **Per-owner overrides.** "My monstera likes less water" is the learned owner profile's job
  and it already exists.

## Decisions

### Three tiers, in one function, behind the existing port

`lookup_plant_care_profile` keeps its name and its position and gains two tiers behind it:
curated, then stored, then researched. Callers are unchanged in structure.

The port's *return type* has to change, because the honesty requirement needs provenance to
travel with the content, and today the content is a bare `CareProfile`. Adding a field to
`CareProfile` rather than wrapping it keeps the two consumers reading one object:

```
CareProfile:
    species, light, water, temperature_c, humidity   # unchanged
    origin: "curated" | "researched"                 # new, defaults to curated
    sources: list[str]                               # new, empty for curated
```

A default of `curated` means the 18 hand-written entries need no edit and no migration of
meaning. It also means a profile that somehow loses its origin claims to be curated, which is
the wrong way round — so the researched path sets it explicitly and a test asserts a stored
profile reads back as researched rather than trusting the default.

`Deps.care_profile` stays `Callable[[str], CareProfile | None]` by signature. **This is the
one place worth being careful**: `tests/unit/agent/test_port_arity.py` checks arity, not
return types, and this change alters a return type without altering arity — precisely the
hole that test does not cover. The compensating check is that both real wirings are exercised
by a test that reads a *researched* profile end to end, not only a curated one.

### Stored globally, keyed by a normalised name

One new table, `species_care_profiles`, with a unique normalised species key. Not scoped to an
owner: what *Monstera deliciosa* wants is the same fact for everybody, and the per-user thing
already exists as `ProfileFact`.

This is a deliberate asymmetry with the rest of the schema, where nearly every table carries a
`user_id` and the tenancy tests enforce it. The argument for breaking the pattern here is that
this table holds no personal data at all — a species name and public care guidance — and
scoping it per owner would mean researching *Ocimum africanum* again for every new account
that photographs one, which is the cost this change exists to avoid paying twice.

The consequence to state plainly: **one owner's run causes a row another owner's run reads.**
Nothing about a person crosses that boundary, but the write is triggered by one and consumed
by others, and a poisoned profile would be poisoned for everybody. That is what the refusal
rule and the untrusted fencing are for, and it is why they are requirements rather than
niceties.

The normalised key reuses whatever the existing alias table already does — lowercased and
stripped — so that `"Monstera Deliciosa"`, `"monstera deliciosa"` and `" monstera deliciosa "`
are one row rather than three.

### The refusal is the hard part, and it gets its own gate

Search returns near misses confidently. The extraction prompt therefore asks two things: the
profile, and whether the material actually describes *this* species. A model that is unsure
returns no profile.

Two properties make this tractable rather than a coin flip:

- **The species name is in the material or it is not.** A structured extraction that must
  echo back the species it found, compared against the species asked for, catches the
  *Ocimum basilicum* case without asking the model to be wise about it.
- **The default is refusal.** Every failure mode — no results, a failed call, an unparseable
  response, a name that does not match — lands on `None`, which is the outcome the callers
  have always handled.

The risk this leaves is a model that echoes the asked-for name back regardless of what it
read. That is a real failure mode of asking a model to check its own work, and the honest
answer is that this design does not fully solve it — it makes the common case (search drifted
to a relative) detectable, and accepts that a determined hallucination gets through. The
mitigation is that a wrong profile is labelled researched wherever it is read, so the person
seeing it knows how much to trust it. Recorded as a limitation rather than claimed as solved.

### Researched inside the run, not behind a queue

`enrich` already makes several outbound calls, and a background job would mean the diagnosis
that triggered the research does not benefit from it — the first owner of an unusual plant
pays the latency and gets nothing, and every subsequent one gets the profile. That is the
wrong way round.

Cost is one search plus one small structured call, on a species miss only. The ceiling is the
number of distinct species ever photographed, not the number of runs.

The failure mode to guard is latency, not spend: an unresponsive search must not hold a
diagnosis open. The existing tool already returns `[]` on any failure including timeout, so
this inherits that behaviour rather than adding its own.

### The write goes through the caller's session

**Amended during implementation.** This section originally proposed a *separate* session for
the cache write, reasoning that a care profile is reference data whose lifetime is independent
of the run that discovered it, and that a chat turn has no write boundary of its own so a
profile researched there would never be committed.

Both halves turned out to be wrong, and the correction is worth recording rather than leaving
as a silent difference between this document and the code:

- **Both callers already commit.** agent/nodes/persist.py wraps the end of a diagnosis and
  services/chat_service.py wraps each turn, so a write left pending on their session lands
  at their boundary. The chat hole the separate session existed to close was never open.
- **A separate session commits outside the caller's transaction**, which in tests means real
  rows written past a fixture rollback into whichever database the settings happen to name.
  That is test pollution bought with a guarantee nothing needed — and it is how the mistake
  was found: two wiring tests failed against a database that had never seen the table.

What it costs: a diagnosis that fails after enrich discards the profile it researched, and
the next run for that species researches it again. One search, rarely, against a second
connection and a commit nobody asked for.

### The chat tool says what it is; the diagnosis prompt says it differently

The chat tool's returned text is read by the model and relayed to a person, so it carries the
label and the sources in words.

The diagnosis prompt gets the same fact for a different reason: a model told a baseline is
researched rather than curated should weight it slightly less against a contradicting
observation. One clause on the existing sentence, not a new section.

`care_baseline_text` remains prompt-only and reaches no client, which is unchanged and worth
saying out loud: outside chat, a person still never sees the baseline at all. That is
`add-plant-timeline`'s to fix and is recorded rather than quietly widened here.

## Risks / Trade-offs

- **A generated profile is a guess presented in the same shape as a curated one** → labelled
  everywhere it is read, refused where the material does not match, and never allowed to
  shadow a curated entry. Residual risk accepted and recorded.
- **A shared table means one owner's run writes what another reads** → no personal data
  crosses, and the alternative is paying for the same research per account. The refusal rule
  and the fencing are the defences, and they are requirements.
- **The port's return type changes and the arity test cannot see it** → the compensating test
  drives a researched profile through both real wirings. Worth stating because the last port
  change broke both wirings silently and only a browser run found it.
- **More prompt tokens on the diagnosis** → one clause, on runs that have a profile at all.
- **The evaluation may move** → the golden cases are common species the curated list covers,
  so in principle nothing changes. That is a prediction, and `M39` and `M42` already record
  that the baseline is stale; verifying no golden case newly triggers research is cheap and is
  a task rather than an assumption.
- **A model that echoes the species name back regardless** defeats the match check. Accepted;
  see above.

## Migration Plan

Additive throughout. One migration creates one table; nothing existing changes shape.

Order, which is also the order the risk retires:

1. `CareProfile` gains `origin` and `sources`, defaulting to curated. Nothing behaves
   differently; the two consumers keep working unchanged.
2. The table and its migration, with the lookup reading it as a second tier. Still nothing
   researches anything — a tier that is always empty.
3. The research path and its refusal gate, verified against a real search response recorded
   first, as `add-plantnet-identification` and `add-granular-weather` both did.
4. The labels on both surfaces.

**Rollback** is removing the research tier: the stored table becomes inert, the curated tier
is untouched, and every caller returns to today's behaviour.

## Open Questions

- **Whether a researched profile should be re-researched when the species name is later
  corrected.** Somebody who overrides the identification changes which species the plant is,
  and the profile already fetched was for the old one. The run's own flow makes this rare —
  identification settles before `enrich` — but a re-check on a plant whose species was
  corrected afterwards is a real path. Worth confirming during implementation rather than
  designing around now.
- **Whether `sources` should be URLs or the passage identifiers the search returns.** The
  latter is what `Passage.doc_id` already carries and costs nothing; the former is what a
  person would actually want to click. Deferred to the task that writes them.
