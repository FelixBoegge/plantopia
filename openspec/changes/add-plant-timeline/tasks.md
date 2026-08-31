# Implementation tasks

Ordered so that the layers widen first — changing nothing anybody can see — and the drawing
comes last. No schema change: every column this reads already exists.

## 1. Three layers catch up with the row

- [ ] 1.1 Add `captured_at`, `latitude` and `longitude` to `ObservationRecord`; verify a test asserts all three round-trip, and that an observation carrying none of them reads back as `None` rather than defaulted.
- [ ] 1.2 Stop `api/converters.py:observation()` dropping `record.weather`; verify a test asserts a stored series reaches `ObservationOut`, and that it fails if the field is dropped again.
- [ ] 1.3 Add the capture date, the position and the weather to `ObservationOut`; verify the client-type agreement test passes on both sides and covers the new fields.
- [ ] 1.4 Confirm the position is exposed and deliberately not drawn; verify by stating why in the schema comment.
- [ ] 1.5 Confirm nothing existing changed shape; verify the plant-detail endpoint tests pass with their assertions unchanged.

## 2. What happened, in order

- [ ] 2.1 Build the event merge as a pure function over observations, diagnoses, roadmap steps and messages; verify a test asserts one sequence in one order from the four differently-ordered sources.
- [ ] 2.2 Date an observation by its capture date where it has one and its upload otherwise; verify a test covers both and asserts nothing claims a capture date it does not have.
- [ ] 2.3 Place a roadmap step by its completion where it has one and its due date otherwise; verify a test covers completed, skipped and pending.
- [ ] 2.4 Read escalations out of stored tool calls, with their reason; verify a test asserts one is found in a stored message and that an ordinary exchange contributes nothing.
- [ ] 2.5 Handle a transcript that has not loaded yet; verify a test asserts the timeline renders without it and gains escalations when it arrives.
- [ ] 2.6 Render an event from whatever it holds; verify a test asserts an observation with no capture date, no position and no weather still appears.

## 3. The section on the plant page

- [ ] 3.1 Add the timeline between "What Plantopia thinks" and `<Roadmap>`; verify a component test asserts it appears in that order and carries a heading.
- [ ] 3.2 Show each event's kind and date, and a photograph where the event has one, through the existing `<Photo>`; verify a test asserts the thumbnail goes through the authenticated path rather than a bare `src`.
- [ ] 3.3 Reach the full diagnosis from a diagnosis event; verify a test asserts the link's destination.
- [ ] 3.4 Say so plainly when a plant has no history yet; verify a test asserts the empty state rather than an empty frame.
- [ ] 3.5 Confirm `observations` is no longer fetched and discarded; verify by checking `PlantDetail` reads it.

## 4. Drawing the weather

- [ ] 4.1 Draw the recorded daily series as SVG — minima, maxima and precipitation; verify a test asserts a series of known values produces the expected number of points and a `viewBox`.
- [ ] 4.2 Render the same series as a table beside it, present but visually hidden; verify a test reads the values out of the table rather than the chart.
- [ ] 4.3 Add a text summary naming the range and the notable days; verify a test asserts it for a window with a frost and for one without.
- [ ] 4.4 Show nothing for an observation with no series; verify a test asserts no chart, no table and no empty axes.
- [ ] 4.5 Confirm the chart is not colour-alone and survives axe; verify the accessibility test passes over the plant route with a timeline present.
- [ ] 4.6 Confirm the forecast is deliberately not drawn; verify by stating why where the series is read.

## 5. Proving it works, and closing

- [ ] 5.1 Add a browser flow opening a plant with a history; verify the events appear in order and a diagnosis is reachable from one.
- [ ] 5.2 Add a browser flow for a plant with an outdoor observation; verify the weather appears and its values are readable without colour.
- [ ] 5.3 Look at a real plant in the development database, which has partial history; verify what renders and record anything that reads badly.
- [ ] 5.4 Update the README: what the timeline shows, what dates it, and what it does not show; verify every command runs as written on a clean clone.
- [ ] 5.5 Record what this leaves undone — no pagination, no feedback events, the forecast, `U11`'s design debt now carrying a larger surface, and whether `U12` is closed; verify identifiers and dates against the file's conventions.
- [ ] 5.6 Run `openspec validate add-plant-timeline --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
