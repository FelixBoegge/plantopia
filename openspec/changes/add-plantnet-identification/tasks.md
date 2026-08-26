# Implementation tasks

Ordered so the risk retires early: the no-key path first, because it is the path this project
runs on until a key exists and the one every failure degrades to; the real request shape
second, because `U2` is what happens when an unverified shape is written into a test.

## 1. The adapter, and the path with no key

- [ ] 1.1 Add `plantnet_api_key: str | None` to `Settings` and document it in `.env.example`; verify a settings test asserts it defaults to `None` and that `.env.example` names it.
- [ ] 1.2 Add an `ImageOrgan` enum to `agent/schemas.py` covering the service's vocabulary plus an explicit "unknown"; verify a test asserts every member except "unknown" is a value the adapter will send.
- [ ] 1.3 Add a `SpeciesCandidate` schema carrying species, optional scientific name, confidence and the method that produced it; verify a test asserts a candidate cannot be constructed without a method.
- [ ] 1.4 Write `tools/plantnet.py` with the signature the design describes, returning an empty list for a missing key without making a request; verify a test asserts no HTTP call is attempted when the key is `None`.
- [ ] 1.5 Return an empty list on timeout, transport error, 4xx, 5xx and an unparseable body; verify a table-driven test covers each with `respx` and asserts nothing raises.
- [ ] 1.6 Treat the quota response distinctly in the log and identically in the return; verify a test asserts an exhausted allowance logs at warning and still returns an empty list.

## 2. The real request, verified once against the real service

- [ ] 2.1 Make one manual call with a real key and at least two photographs from `test_pics/`, and save the raw response under `tests/fixtures/`; verify the file exists and contains a ranked result with scores.
- [ ] 2.2 Reconcile the adapter's request against the service's reference — field names, the organ vocabulary, the multipart shape, the ranking order; verify by the call in 2.1 succeeding, and record any correction made.
- [ ] 2.3 Build the adapter's parsing tests from the recorded fixture rather than from a hand-written body; verify the tests fail if the fixture is replaced with an empty result set.
- [ ] 2.4 Record in `docs/known-limitations.md` what remains unverified about the integration and what would settle it; verify identifiers and dates against the file's conventions.

## 3. Organs and the second identification

- [ ] 3.1 Extend the vision identification's structured output to report each photograph's organ alongside the species guess; verify a node test asserts one model call is made, not two.
- [ ] 3.2 Map an organ the vision model returns that is outside the vocabulary to "unknown"; verify a test asserts an unrecognised value is sent as no organ rather than as a guess.
- [ ] 3.3 Call the adapter from `identify_plant` with the photographs and their organs, after the vision call; verify a test asserts the organs sent match the ones the vision model reported.
- [ ] 3.4 Carry both results as candidates on the state, deduplicating where the two methods name the same species; verify a test covers agreement, disagreement, and one method returning nothing.
- [ ] 3.5 Record an adapter failure against the run's errors without failing the node; verify a test asserts the diagnosis proceeds and the error is recorded.
- [ ] 3.6 Keep `identify_plant`'s existing early return for an already-identified plant; verify the re-check tests still pass unchanged.

## 4. The species somebody typed

- [ ] 4.1 Accept an optional species when a run is started, through the API and into the initial state; verify an endpoint test asserts a run starts with and without it.
- [ ] 4.2 Carry a typed species as a candidate rather than as the species; verify a test asserts the identifications still run when one was typed.
- [ ] 4.3 Leave behaviour unchanged when the field is absent; verify an existing wizard test passes without modification.

## 5. The choice, through the interrupt and back

- [ ] 5.1 Add the identification block to the interrupt payload alongside the questions; verify a test asserts the payload carries both and that `Question` is unchanged.
- [ ] 5.2 Omit the block when there is nothing to choose between; verify a test asserts a single candidate produces no block.
- [ ] 5.3 Accept a chosen species in the resume payload and apply it in `gather_context`; verify a test asserts the resumed run proceeds on the chosen species.
- [ ] 5.4 Proceed on the highest-confidence candidate when no choice is made; verify a test asserts the diagnosis completes and the choice is recorded as unconfirmed.
- [ ] 5.5 Add a cross-language agreement test for the identification payload, on the model of `test_question_shape_agrees.py`; verify it fails when a field is renamed on either side.

## 6. What the diagnosis records

- [ ] 6.1 Add the provenance and confirmation columns to `Diagnosis` with a migration; verify the migration test passes and that it mentions no checkpoint table.
- [ ] 6.2 Persist which method produced the species and whether a person confirmed it; verify a test asserts each of the four combinations round-trips.
- [ ] 6.3 Report an older diagnosis's provenance as unknown rather than inventing one; verify a test asserts a row written before this change reads as unknown.
- [ ] 6.4 Expose both on the diagnosis endpoint; verify the client-type agreement test covers the new fields.

## 7. The wizard

- [ ] 7.1 Add the optional species field to the upload step; verify a component test asserts a run starts with the field empty.
- [ ] 7.2 Render the candidates at the pause with their method and confidence, confidence in words; verify a component test asserts no bare probability is rendered.
- [ ] 7.3 Make choosing optional and submitting without a choice possible; verify a component test asserts the submit control is enabled with nothing chosen.
- [ ] 7.4 Make the chooser keyboard-operable, with the selection conveyed by more than colour; verify the accessibility suite covers it and the axe pass is clean.
- [ ] 7.5 Put the attribution inside the component that renders a service-derived candidate; verify a test asserts it appears whenever such a candidate is rendered and not when none is.
- [ ] 7.6 Add a browser flow for a diagnosis where the identifications disagree and the owner chooses; verify it passes against the real stack with scripted models.

## 8. Proving it works, and closing

- [ ] 8.1 Run a diagnosis end to end with a real key and photographs of a real plant; verify the chooser offers both identifications and the chosen one reaches the differential.
- [ ] 8.2 Run the same diagnosis with the key removed; verify it completes, offers no chooser, and shows no attribution.
- [ ] 8.3 Confirm the evaluation harness is unmoved: run it and compare against the last recorded result; verify the harness-independence test passes and no number changed.
- [ ] 8.4 Update the README: the new setting, what happens without it, and the attribution obligation; verify every command runs as written on a clean clone.
- [ ] 8.5 Record what this change leaves undone — identification accuracy is now measurable and still unmeasured, and what an image-based golden set would need; verify identifiers and dates against the file's conventions.
- [ ] 8.6 Run `openspec validate add-plantnet-identification --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
