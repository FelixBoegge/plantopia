# Implementation tasks

Ordered so that the part needing no new request comes first, and the one new endpoint is
verified against the live service before any test is written from it — the discipline that
caught `habit` and the 200-with-an-error-body.

## 1. Keeping the days

- [x] 1.1 Add a `WeatherDay` schema carrying a date, a minimum, a maximum and precipitation; verify a test asserts a day cannot be built without its date.
- [x] 1.2 Carry the days on `WeatherSummary` and derive its existing five figures from them; verify the current weather tests pass with their assertions unchanged.
- [x] 1.3 Skip a day the service returned nothing for, rather than recording it as zero; verify a test asserts a null day is absent and does not drag an average down.
- [x] 1.4 Confirm no additional request is made; verify a test asserts the archive is called exactly once for a window.

## 2. The days ahead

- [x] 2.1 Make one manual call to Open-Meteo's forecast endpoint and save the raw response under `tests/fixtures/`; verify the file exists and covers at least seven days.
- [x] 2.2 Reconcile the request against the response — parameter names, the daily fields, how far ahead it reaches; verify by the call in 2.1 succeeding, and record any correction made.
- [x] 2.3 Add the forecast fetch, anchored on today rather than on the photograph; verify a test asserts the two windows have different anchors when the photograph is three days old.
- [x] 2.4 Build the forecast parsing tests from the recorded response; verify they fail if the fixture is replaced with an empty one.
- [x] 2.5 Survive a forecast that fails while the history succeeds; verify a test asserts the diagnosis proceeds with the history alone.

## 3. Where to look it up

- [ ] 3.1 Let the weather lookup take a position as well as a place name; verify a test asserts no geocoding request is made when a position is given.
- [ ] 3.2 Use the position when the location answer is unchanged from the prefill it produced; verify a test covers accepted, corrected, and no-position-at-all.
- [ ] 3.3 Read the prefill the run offered rather than trusting the client; verify a test asserts a client claiming an unchanged answer cannot force a stale position.
- [ ] 3.4 Confirm `M40` is closed: verify a test asserts the stored position is read by something.

## 4. What the diagnosis is shown

- [ ] 4.1 Render the notable events with their dates — frosts, heat days, dry and wet spells — reusing the existing thresholds; verify a test asserts a frost's date reaches the block.
- [ ] 4.2 Render the last seven days and the seven ahead, day by day; verify a test asserts both windows are labelled and distinguishable.
- [ ] 4.3 Say so in a sentence when nothing was notable, rather than listing every day; verify a test asserts an unremarkable window produces no table.
- [ ] 4.4 Keep the block bounded; verify a test asserts its length for a three-week window is within a stated budget.

## 5. A photograph old enough to mislead

- [ ] 5.1 Add the staleness threshold to `Settings`, defaulting to seven days; verify the settings test covers it and `.env.example` names it.
- [ ] 5.2 Tell the owner at the pause when the photograph is older than the threshold; verify a component test covers older, newer, and exactly at the boundary.
- [ ] 5.3 Judge the age by the date the owner left rather than the one the camera recorded; verify a test asserts a corrected date changes the verdict.
- [ ] 5.4 Tell the diagnosis prompt how old the photograph is when it exceeds the threshold, and instruct it to say so; verify a test asserts the age reaches the prompt and that a recent photograph adds nothing.
- [ ] 5.5 Complete the diagnosis regardless; verify a test asserts a three-week-old photograph still produces a differential.
- [ ] 5.6 Add a browser flow uploading a stale photograph; verify the warning appears at the pause and the run can still be carried on.

## 6. What is written down

- [ ] 6.1 Add a nullable weather column to `Observation` with a migration; verify the migration test passes and mentions no checkpoint table.
- [ ] 6.2 Record the series against the observation; verify a test asserts a stored series round-trips day for day.
- [ ] 6.3 Report an observation from before this as having no weather rather than an empty window; verify a test asserts the distinction.
- [ ] 6.4 Expose it on the diagnosis endpoint; verify the client-type agreement test covers the new field.

## 7. Asking about it in conversation

- [ ] 7.1 Add a chat tool answering from the stored series; verify a test asserts no fetch happens for a window the record covers.
- [ ] 7.2 Fetch for a window the record does not cover; verify a test asserts the fetch happens and the answer is returned.
- [ ] 7.3 Name the tool for a person in `TOOL_NAMES`; verify the source-names agreement test passes on both sides.
- [ ] 7.4 Add a browser flow asking about the weather; verify the lookup is announced before the reply arrives.

## 8. Proving it works, and closing

- [ ] 8.1 Run a diagnosis end to end for an outdoor plant with a real place; verify the prompt block carried real dated events and a forecast, and that the series was stored.
- [ ] 8.2 Run one for an indoor plant; verify no weather was fetched and nothing about the diagnosis changed.
- [ ] 8.3 Confirm what this does to the evaluation and record it; verify the harness-wiring and independence tests pass, and state plainly which metrics should be expected to move and why.
- [ ] 8.4 Update the README: what weather a diagnosis sees, the two anchors, and what is recorded; verify every command runs as written on a clean clone.
- [ ] 8.5 Record what this change leaves undone; verify identifiers and dates against the file's conventions.
- [ ] 8.6 Run `openspec validate add-granular-weather --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
