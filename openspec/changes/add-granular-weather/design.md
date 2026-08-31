## Context

See `proposal.md` — Why. What shapes the approach is that most of the work is already being
done and thrown away.

`tools/weather.py:_fetch_archive` asks Open-Meteo for `temperature_2m_min`,
`temperature_2m_max` and `precipitation_sum` across the window, receives three parallel arrays
of about twenty-one values each, and reduces them to a `WeatherSummary` of five numbers. The
arrays are discarded inside the function. Adding the series costs nothing at the network —
the same request already returns it.

`get_local_weather` takes a *place name*, forward-geocodes it through Open-Meteo's geocoding
endpoint, and then fetches. Since `add-image-metadata-capture` a coarse position is frequently
already known and recorded on the observation, and `M40` records that it is written and never
read: the name is resolved back into coordinates that were the source of the name.

`enrich` decides whether to fetch at all — outdoor plants with a known place — and
`diagnose` renders one sentence into the prompt. Both are one small function.

The chat agent has six tools and a table naming each one for a person
(`services/chat_events.TOOL_NAMES`); a seventh is a small addition to both.

## Goals / Non-Goals

**Goals:**

- A diagnosis that can tell last night's frost from one a fortnight ago.
- A treatment plan that knows what the week ahead looks like.
- A diagnosis whose weather can be read back afterwards, like its species provenance.
- No new external service, no key, no cost.

**Non-Goals:**

- Drawing any of it. `add-plant-timeline` has the surface and the history.
- Hourly resolution. Daily is what a plant responds to; hourly is a much larger response for
  a question nothing here asks.
- Weather for indoor plants. Unchanged: not fetched.

## Decisions

### The prompt gets a reading of the series, not the series

Thirty-seven rows of unremarkable weather bury the one frost date that explains the plant,
and cost tokens on every outdoor run to do it. So the block is:

1. **What was notable** — frost dates, days above the heat threshold, dry spells and wet
   spells, each with its date. Nothing is listed that was not unusual.
2. **The last seven days**, day by day, so the model can place the notable events against
   what came immediately before the photograph.
3. **The seven days ahead**, day by day, because the plan is about them.

Where nothing was notable, that is said in a sentence rather than demonstrated with a table.

Both the thresholds — what counts as a frost, a heat day, a dry spell — already exist for the
current aggregates and are reused rather than re-invented.

### Two anchors, because there are two questions

The history ends the day before the photograph was taken. The forecast starts today. These
are not the same anchor and using one for both would be wrong in one direction or the other:
a plant photographed a week ago did not stand in this week's weather, and advice about what
to do next is about the days that are actually next.

That means a run on an old photograph gets a gap between the two — the days between the
photograph and now, which are neither what the plant was standing in nor what it is about to
face. Those days are fetched as part of the archive window where they fall inside it, and
otherwise simply absent. Naming the gap in the prompt would cost more than it explains.

### The position wins where it was accepted, the name where it was changed

`M40`'s open question, now that it matters. The rule is what the owner left:

- The location answer is unchanged from the prefill that came from a photograph's position →
  use the position. It is where the name came from, and rounder.
- The answer differs → resolve the name. A correction that lost to the coordinates behind it
  would be a control that does nothing.
- No position at all → resolve the name, exactly as now.

Comparing the answer against the prefill is how "unchanged" is decided, which means the run
has to carry the prefill it offered. It already does: the question is in the event the run
published when it paused, which is also where the required-answer check reads from.

### The series is stored as JSON on the observation

One column, the days as objects. Not a table of weather rows: nothing queries across
observations by weather, the series is always read whole and always belongs to exactly one
observation, and a table would be a join to reconstruct a list that was always a list.

Stored because a diagnosis's evidence should be recoverable, which is the argument
`species_method` already made. That it is also what `add-plant-timeline` will draw is a
convenience rather than the reason — data stored for a feature that does not exist is what
`M40` records as a mistake, and this is not that.

### The chat tool reads the record first

`get_plant_weather(days_back)` answers from the stored series where the window falls inside
it, and fetches otherwise. Reading the record first is not only cheaper: it is what makes the
answer *consistent with the diagnosis*, which was made against those days. An agent that
re-fetched could tell somebody about weather the diagnosis never saw.

It joins `TOOL_NAMES` as "the weather where this plant is", because "get_plant_weather" is a
function name and the person reading it did not write it.

## Risks / Trade-offs

- **Prompt size on every outdoor run** → the block is a reading rather than a dump, and it is
  bounded: notable events are rare by construction, and the two seven-day windows are fixed.
  A few hundred tokens where the current sentence is about twenty.
- **The evaluation numbers will move** → four outdoor golden cases turn on weather and will
  see three weeks of days rather than five numbers. This is the change where that is the
  point rather than a side effect; `M39` already records that the baseline is not comparable,
  and this compounds it.
- **One more thing that can fail mid-run** → the forecast is a second request, and its
  failure is survivable independently: history without forecast is a worse plan, not a failed
  diagnosis.
- **A stored series is a stored thing that could grow** → twenty-one days of three numbers is
  a few hundred bytes per observation. Bounded by the window, which is configuration.
- **Two anchors are harder to explain than one** → they are, and the alternative is a wrong
  answer in one direction. The prompt block labels both.

## Migration Plan

Additive. One migration adds a nullable JSON column to `observations`; existing rows keep
null, which means no weather was recorded, which is true of every observation before this.

Order, which is also the order the risk retires:

1. The series out of the archive parse, and the summary derived from it rather than fetched.
   No new request, no schema.
2. The forecast, verified against the live service before its tests are written from it.
3. The position-or-name rule.
4. The stored column and the prompt block.
5. The chat tool.

**Rollback** is the prompt block reverting to its sentence: the series is additive on the
schema and additive in the state, and nothing else reads it.

## Open Questions

- **Whether the forecast should reach the roadmap prompt as well as the diagnosis one.**
  Treatment steps carry a `day_offset`, so "feed it in a fortnight" could in principle avoid
  a forecast frost. That is a change to how a plan is built rather than to what weather is
  available, and it wants the plan's own attention.
