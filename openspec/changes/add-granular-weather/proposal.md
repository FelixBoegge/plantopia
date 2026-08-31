## Why

The weather this project fetches is thrown away before anything reads it. `tools/weather.py`
asks Open-Meteo for three weeks of daily minima, maxima and precipitation — sixty-odd
numbers — and reduces them to five: a low, a high, a total, and two counts. The diagnosis
prompt then receives one sentence.

That sentence loses the thing weather is diagnostically for. "Two frost days over twenty-one
days" does not say whether they were last night or a fortnight ago, and the difference is the
difference between frost damage and something else entirely. "Fourteen millimetres of rain"
does not distinguish a fortnight of drizzle from one thunderstorm on a plant that has been dry
since. A plant responds to *when*, and the aggregate is exactly the part that cannot say.

It also stops at the present. Every diagnosis ends in a treatment plan — water less, move it
somewhere brighter, feed it next week — and none of that advice knows whether a frost is
forecast for Thursday. The forecast is free, from a service already in use, and is the
difference between a plan that survives contact with the week ahead and one that does not.

And a diagnosis's weather is currently unrecoverable. Somebody asking in three weeks why a
diagnosis blamed heat stress cannot see what heat it saw, because the numbers were reduced
and then discarded. That is the same gap `species_method` closed for identification.

## What Changes

- **The daily series is kept rather than collapsed.** One fetch, the same one, parsed into a
  day-by-day record instead of five aggregates.
- **The forecast is fetched too** — seven days ahead, from Open-Meteo's forecast endpoint. No
  key, no cost, the same client.
- **The diagnosis prompt gets a condensed block**: the notable events, the last seven days
  day by day, and the seven days ahead. A few hundred tokens, chosen so that the frost date
  that explains everything is not buried in thirty-seven unremarkable rows.
- **The series is stored with the observation**, so a diagnosis's weather can be read back
  afterwards. The evidence a diagnosis reasoned from should be recoverable for the same
  reason its species provenance is.
- **The chat agent can ask about it**: a tool answering "was it cold last week?" from the
  stored series, and from Open-Meteo for a window the series does not cover.
- **The coarse position from a photograph is used where there is one**, rather than
  round-tripping a place name through a geocoder to arrive back at coordinates. This is what
  `M40` records as stored-and-unread.

Not in scope, deliberately:

- **Drawing any of it.** A chart belongs with `add-plant-timeline`, which is where there is a
  surface to draw on and a history to draw. This change makes the data exist and be read by
  the agent; a person still sees weather only through what the diagnosis says about it.
- **Hourly resolution.** Daily is what a plant responds to and what the archive gives without
  a much larger response. An hourly window is a change of its own if anything ever needs it.
- **Any new external service.** Open-Meteo's forecast endpoint is the same host, the same
  client, and the same absence of a key as its archive.

## Capabilities

### New Capabilities

- `weather`: What weather a diagnosis is read against — which window, at what resolution,
  where it comes from, what is recorded, and what happens when it is unavailable.

### Modified Capabilities

- `image-metadata`: The coarse position stops being written-and-unread. What a photograph's
  position is *for* becomes part of what that capability promises.

## Impact

- `tools/weather.py` — the archive parse keeps its days, a forecast fetch is added, and the
  lookup accepts a position as well as a place name.
- `agent/schemas.py` — `WeatherSummary` gains the series; a `WeatherDay` joins it.
- `agent/nodes/enrich.py`, `agent/nodes/diagnose.py` — what is fetched and what reaches the
  prompt.
- `agent/chat_agent.py` — one more tool, and one more entry in the table that names a lookup
  for a person.
- `data/models.py` and a migration — the series stored against the observation.
- **Prompt size.** The diagnosis prompt grows by a few hundred tokens on outdoor plants with
  a known location. That is a real cost on every such run, and the block is shaped to earn
  it: events first, recent days next, forecast last, nothing unremarkable.
- **The evaluation numbers should be expected to move**, and this time for a reason worth
  measuring: four outdoor golden cases turn on weather, and they will see three weeks of days
  rather than five numbers. `M39` already records that the last baseline is not comparable.
