# Implementation tasks

Ordered so the parts that need nothing external come first, and the one external service is
verified against the real thing before any test is written from it — which is what the last
change established as the way to avoid `U2`.

## 1. Reading what a photograph declares

- [x] 1.1 Add `core/metadata.py` reading the capture date and any position from image bytes; verify a test reads both from a photograph in `test_pics/` with known metadata.
- [x] 1.2 Return nothing rather than raising for bytes with no metadata, unreadable metadata, or a malformed block; verify a table-driven test covers each and asserts nothing raises.
- [x] 1.3 Ignore a capture date in the future or before digital photography; verify a test covers both bounds and that a plausible date survives.
- [x] 1.4 Coarsen a position to one decimal degree inside the reading function, and never return the precise value; verify a test asserts the precise fix is not among what the function returns.
- [x] 1.5 Take the earliest capture date when several photographs disagree; verify a test covers disagreement and one photograph having no date at all.

## 2. Reading before normalising

- [x] 2.1 Read metadata in `store_upload` before `upright_bytes`, returning it with the `ImageRef`; verify the type checker and every existing caller are updated.
- [x] 2.2 Add the ordering test: a photograph with known metadata through the real `store_upload`, asserting what was read survived; verify it fails when the two calls are swapped.
- [x] 2.3 Read nothing from an upload that validation refused; verify a test asserts a refused upload reads no metadata.
- [x] 2.4 Confirm the stored bytes are unchanged by any of this; verify the existing photo-storage tests pass untouched.

## 3. The place name, verified against the real service

- [x] 3.1 Write `tools/geocoding.py` on the pattern of `tools/weather.py`: no credential, a configurable base URL and user agent, and nothing on failure; verify a test asserts an empty result for a timeout, a 4xx, a 5xx and an unparseable body.
- [x] 3.2 Make one manual call to the live service with a real coarse position, and save the raw response under `tests/fixtures/`; verify the file exists and names a place.
- [x] 3.3 Reconcile the request against the service's terms — user agent, rate, and the response fields the parser reads; verify by the call in 3.2 succeeding, and record any correction made.
- [x] 3.4 Build the parsing tests from the recorded response rather than a written one; verify they fail if the fixture is replaced with an empty result.
- [x] 3.5 Cache results on the coarsened position; verify a test asserts two lookups of one position make one request.
- [x] 3.6 Add the settings for the base URL and user agent, with defaults that work on a fresh clone; verify the settings test covers both and `.env.example` names them.

## 4. What an observation records

- [x] 4.1 Add nullable captured-at and coarse position columns to `Observation` with a migration; verify the migration test passes and that it mentions no checkpoint table.
- [x] 4.2 Date the observation by the capture date where there is one; verify a test covers a photograph with a date, one without, and that the stored row reads back correctly.
- [x] 4.3 Anchor the weather window on the observation's date rather than today; verify a test asserts the window moves with a capture date three days old.
- [x] 4.4 Report an observation made before this change as knowing neither; verify a test asserts a row written without them reads as null rather than as a guess.

## 5. Through the run

- [x] 5.1 Carry the detected date and place on the run's initial state; verify a test asserts both reach the graph and that absent means absent.
- [x] 5.2 Give `Question` a prefilled answer and a required flag; verify the question-shape agreement test covers both and fails when either side is renamed.
- [x] 5.3 Ask the location question on every run, prefilled with any detected place, required only when the plant is outdoors; verify tests cover detected/not-detected against indoors/outdoors.
- [x] 5.4 Refuse an answer submission that leaves a required question empty; verify a test asserts the run stays paused and says which question is missing.
- [x] 5.5 Use what the person left rather than what was detected; verify a test asserts a corrected place wins over the detected one.

## 6. The wizard

- [ ] 6.1 Remove the location field from the upload step; verify a component test asserts a run starts without anybody being asked where the plant is.
- [ ] 6.2 Render a prefilled question with its answer already in the field; verify a component test asserts submitting untouched sends the prefilled value.
- [ ] 6.3 Mark a required question and refuse submission while it is empty; verify a component test covers outdoors-with-nothing-detected and indoors-with-nothing-detected.
- [ ] 6.4 Credit the naming source wherever a detected place name is shown; verify a test asserts the credit appears with a name and not without one.
- [ ] 6.5 Keep the whole thing reachable and operable from the keyboard, and announce a refused submission; verify the accessibility suite covers it and the axe pass is clean.
- [ ] 6.6 Add a browser flow uploading a photograph with metadata, correcting the prefilled place, and starting the run; verify it passes against the real stack.
- [ ] 6.7 Add a browser flow for an outdoor plant whose photograph knew nothing; verify the run cannot be resumed until a place is given.

## 7. Proving it works, and closing

- [ ] 7.1 Run a diagnosis end to end with a photograph carrying a real capture date and position; verify the detected values appear, the observation is dated by the photograph, and no precise position is anywhere in the database.
- [ ] 7.2 Run the same diagnosis with a photograph carrying nothing; verify the location question is asked empty at the pause and the run cannot continue without it outdoors.
- [ ] 7.3 Confirm the evaluation harness is unmoved; verify the harness-wiring and independence tests pass and that no golden case reaches this code.
- [ ] 7.4 Update the README: what is read, what is discarded, the new settings, and the attribution obligation; verify every command runs as written on a clean clone.
- [ ] 7.5 Record what this change leaves undone — anything detected that is still unused, and the privacy surface it opens; verify identifiers and dates against the file's conventions.
- [ ] 7.6 Run `openspec validate add-image-metadata-capture --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
