## Why

`tools/care_profiles.py` holds 18 hand-written profiles. Pl@ntNet can name upwards of 50,000
species, so `add-plantnet-identification` **widened** the gap it looks like it should have
closed: the better the identification gets, the more often a plant is correctly named as
something the care list has never heard of. A run that identifies *Ocimum africanum* precisely
and then has no idea what it wants is worse off than one that guessed "basil".

The baseline is what grounds "is this normal for this plant?" — a fern dropping fronds in dry
air is a different situation from a succulent doing the same thing. Without one, the
differential reasons about a generic plant.

This is not hypothetical. `agent/chat_agent.py` carries a comment recording the observed
failure: with strawberries, where the profile list has nothing, the agent answered from its
own memory and attempted no search until the owner asked for one. The fix at the time was to
tell the model where to look next. This change gives it somewhere to look.

## What Changes

- **A researched profile when the list has none.** On a miss, the agent researches the
  species' baseline through the existing web-search tool and writes a `CareProfile` from what
  it finds.
- **Cached in Postgres, once per species rather than once per owner.** What *Monstera
  deliciosa* wants is the same fact for everybody; the learned owner profile is the thing that
  is personal, and this is not that.
- **Hand-written profiles stay the trusted tier and always win.** Lookup order is
  hand-written, then cache, then research. A generated profile can never shadow a curated one.
- **Refusing is a valid outcome, and a required one.** Web search returns near misses: asked
  about *Ocimum africanum* it returns *Ocimum basilicum* content. A profile confidently
  written for a cousin is worse than no profile, because the caller's whole contract is that a
  miss widens the differential and lowers confidence — and a wrong profile does neither.
- **Every generated profile carries its sources and is labelled derived**, and the label
  travels with the content rather than sitting only in the database. The chat tool's reply is
  where a person actually reads this material, so that is where it has to say what it is.
- **What the search returns is fenced as untrusted data**, through the existing
  `core/guards.wrap_untrusted`, on the same reasoning as retrieved passages.

## Capabilities

### New Capabilities

- `species-care`: what baseline care requirements a run may use, where they may come from,
  which source wins, when a profile must be refused rather than invented, and what a person is
  told about a profile that was generated rather than curated.

### Modified Capabilities

None. `species-identification` decides *which* plant this is and is untouched; this change is
about what is known of a plant once named. The diagnosis and chat surfaces consume the profile
through `Deps.care_profile`, whose contract widens without any existing requirement changing.

## Impact

**Code**

- `tools/care_profiles.py` — the hand-written table stays as the trusted tier; lookup gains
  the tiers behind it.
- New research path: a prompt, a structured `CareProfile` extraction, and the refusal rule.
- `agent/deps.py` — `care_profile` currently returns `CareProfile | None`; it needs to carry
  provenance, so the port's return type changes.
- `agent/nodes/enrich.py:_care_baseline` and `agent/chat_agent.py:lookup_plant_care_profile` —
  the two consumers; both render the profile, and the chat one must say where it came from.
- `agent/wiring.py` and `eval/run_eval.py` — both construct `Deps` by hand, and
  `tests/unit/agent/test_port_arity.py` now exists precisely because the last port change
  broke both silently.
- `data/models.py` plus a migration — one new table.

**Cost and latency.** Researching a profile is a web search plus a structured model call, on
the first diagnosis of an unseen species only; every later run for that species reads the
cache. The evaluation harness is unaffected in practice — its golden cases are common species
the hand-written list already covers — but that is worth verifying rather than assuming.

**External services.** No new one. Tavily is already wired and was confirmed working on
2026-08-31, which retires half of `U1`'s "web-search escalation (no Tavily key)".
