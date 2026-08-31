## Why

A plant has a history and nowhere to read it. Each diagnosis is a verdict on one moment, and
the question an owner actually has after the second or third is the one no screen answers:
*is this getting better?*

The material for that answer already exists and has been accumulating for three changes.
Observations carry the date the photograph was taken and roughly where (`add-image-metadata-
capture`). Outdoor observations carry a day-by-day weather series (`add-granular-weather`).
Diagnoses carry their leading candidate, how the species was identified, and whether a person
confirmed it. Roadmap steps carry what was done and when it was completed or skipped. Chat
messages carry the tool calls behind every reply.

All of it is stored, most of it is already returned by the plant endpoint, and none of it is
drawn. `U12` records the weather half of this: the series is stored, exposed and typed on the
client, and no screen shows it.

That is the causal chain a history page exists to show — **what you saw, what it was judged to
be, what you did, and what the weather was doing** — and today it is four disconnected lists.

## What Changes

- **One chronological timeline per plant**, ordered by when things happened rather than by
  which table they came from: observations with their photograph, diagnoses with their leading
  candidate, roadmap steps as completed or skipped.
- **Dated by when the photograph was taken**, not when it was uploaded. The two differ for
  anybody who does not upload immediately, and a history ordered by upload puts events in the
  wrong order — which is the same defect `add-image-metadata-capture` fixed for the weather
  window.
- **Weather drawn underneath, for outdoor plants**, from the series already stored against the
  observation. A person reads a chart better than a model reads a table, which is the half of
  `M40`'s data that the diagnosis prompt deliberately does not get.
- **`ObservationOut` gains what the observation already holds** — the capture date and the
  weather series. Both are on the row today and neither is exposed; the weather is currently
  reachable only through the diagnosis that was made from it, which is the wrong way round for
  a timeline whose spine is observations.
- **A chat escalation appears as an event.** When the agent flags a described symptom as
  warranting a fresh look, that is a real event in the plant's history. It is already durable
  — stored in the assistant message's tool calls, with its reason — so this is a read rather
  than a new record.
- **A sparse history reads correctly.** Most existing observations have no weather and some
  have no capture date, because they predate the columns. The timeline shows what it has and
  says nothing about what it does not, rather than inventing a zero or a date.

## Capabilities

### New Capabilities

- `plant-timeline`: what a plant's history shows, in what order, dated by what, what is drawn
  for weather, and how a history missing most of its data reads.

### Modified Capabilities

- `http-api`: the plant-detail requirement already says the response carries "the history a
  plant page needs". What an observation carries changes — the capture date and the weather
  series — so the requirement's scenario changes with it.

## Impact

**Code**

- `api/schemas.py` — `ObservationOut` gains `captured_at` and `weather`; `api/converters.py`
  passes them through. The `ObservationRecord` already carries the weather; the capture date
  is on the row but not on the record.
- `web/src/api/types.ts` — the matching client fields, checked by the existing agreement test.
- A new timeline surface under `web/src/screens/`, and whatever it needs to draw a weather
  series.

**Deliberately not in scope**

- **Chat keeps its own tab.** Everything a conversation contains is not a plant's history; only
  the escalation is an event.
- **No editing history.** Nothing here deletes, annotates or corrects a past event. Deletion is
  `add-privacy-controls`.
- **No comparison between plants.** One plant, one timeline.

**The design tension worth stating.** `U11` records that the frontend has never been designed —
no type scale, no spacing rhythm, no considered colour. This change adds the largest new
surface in the project on top of that, which means making visual decisions now that a later
design pass will inherit. The mitigation is to make as few as possible: build from the existing
component vocabulary, keep the browser tests locating by role and label so a restyle survives
them, and prefer a plain reading of the data over a bespoke visual language. Recorded here
rather than discovered later.
