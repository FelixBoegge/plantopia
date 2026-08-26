# Implementation tasks

Ordered so the parts that need nothing external come first, and the one external service is
verified against the real thing before any test is written from it — which is what the last
change established as the way to avoid `U2`.

## 1. Reading what a photograph declares

- [ ] 1.1 Add `core/metadata.py` reading the capture date and any position from image bytes; verify a test reads both from a photograph in `test_pics/` with known metadata.
- [ ] 1.2 Return nothing rather than raising for bytes with no metadata, unreadable metadata, or a malformed block; verify a table-driven test covers each and asserts nothing raises.
- [ ] 1.3 Ignore a capture date in the future or before digital photography; verify a test covers both bounds and that a plausible date survives.
- [ ] 1.4 Coarsen a position to one decimal degree inside the reading function, and never return the precise value; verify a test asserts the precise fix is not among what the function returns.
- [ ] 1.5 Take the earliest capture date when several photographs disagree; verify a test covers disagreement and one photograph having no date at all.

## 2. Reading before normalising

- [ ] 2.1 Read metadata in `store_upload` before `upright_bytes`, returning it with the `ImageRef`; verify the type checker and every existing caller are updated.
- [ ] 2.2 Add the ordering test: a photograph with known metadata through the real `store_upload`, asserting what was read survived; verify it fails when the two calls are swapped.
- [ ] 2.3 Read nothing from an upload that validation refused; verify a test asserts a refused upload reads no metadata.
- [ ] 2.4 Confirm the stored bytes are unchanged by any of this; verify the existing photo-storage tests pass untouched.

## 3. The place name, verified against the real service

- [ ] 3.1 Write `tools/geocoding.py` on the pattern of `tools/weather.py`: no credential, a configurable base URL and user agent, and nothing on failure; verify a test asserts an empty result for a timeout, a 4xx, a 5xx and an unparseable body.
- [ ] 3.2 Make one manual call to the live service with a real coarse position, and save the raw response under `tests/fixtures/`; verify the file exists and names a place.
- [ ] 3.3 Reconcile the request against the service's terms — user agent, rate, and the response fields the parser reads; verify by the call in 3.2 succeeding, and record any correction made.
- [ ] 3.4 Build the parsing tests from the recorded response rather than a written one; verify they fail if the fixture is replaced with an empty result.
- [ ] 3.5 Cache results on the coarsened position; verify a test asserts two lookups of one position make one request.
- [ ] 3.6 Add the settings for the base URL and user agent, with defaults that work on a fresh clone; verify the settings test covers both and `.env.example` names them.

## 4. What an observation records

- [ ] 4.1 Add nullable captured-at and coarse position columns to `Observation` with a migration; verify the migration test passes and that it mentions no checkpoint table.
- [ ] 4.2 Date the observation by the capture date where there is one; verify a test covers a photograph with a date, one without, and that the stored row reads back correctly.
- [ ] 4.3 Anchor the weather window on the observation's date rather than today; verify a test asserts the window moves with a capture date three days old.
- [ ] 4.4 Report an observation made before this change as knowing neither; verify a test asserts a row written without them reads as null rather than as a guess.

## 5. Through the run

- [ ] 5.1 Carry the detected date and place on the run's initial state; verify a test asserts both reach the graph and that absent means absent.
- [ ] 5.2 Skip the location question when a place was detected for an outdoor plant; verify a test asserts the question is absent, and present when nothing was detected.
- [ ] 5.3 Return what was detected from the upload path so a client can show it; verify the client-type agreement test covers the new fields.
- [ ] 5.4 Use what the person left rather than what was detected; verify a test asserts a corrected value wins over the detected one.

## 6. The wizard

- [ ] 6.1 Show a detected date and place after photographs are chosen, before the run starts; verify a component test asserts nothing is shown when nothing was detected.
- [ ] 6.2 Make both editable and clearable; verify a component test asserts a cleared value is sent as absent rather than as the detected one.
- [ ] 6.3 Credit the naming source wherever a detected place name is shown; verify a test asserts the credit appears with a name and not without one.
- [ ] 6.4 Keep the whole thing reachable and operable from the keyboard; verify the accessibility suite covers it and the axe pass is clean.
- [ ] 6.5 Add a browser flow uploading a photograph with metadata, correcting what was detected, and starting the run; verify it passes against the real stack.

## 7. Proving it works, and closing

- [ ] 7.1 Run a diagnosis end to end with a photograph carrying a real capture date and position; verify the detected values appear, the observation is dated by the photograph, and no precise position is anywhere in the database.
- [ ] 7.2 Run the same diagnosis with a photograph carrying nothing; verify it behaves exactly as before this change and asks for a location as it used to.
- [ ] 7.3 Confirm the evaluation harness is unmoved; verify the harness-wiring and independence tests pass and that no golden case reaches this code.
- [ ] 7.4 Update the README: what is read, what is discarded, the new settings, and the attribution obligation; verify every command runs as written on a clean clone.
- [ ] 7.5 Record what this change leaves undone — anything detected that is still unused, and the privacy surface it opens; verify identifiers and dates against the file's conventions.
- [ ] 7.6 Run `openspec validate add-image-metadata-capture --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
