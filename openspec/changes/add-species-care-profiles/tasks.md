# Implementation tasks

Ordered so that the part that changes no behaviour comes first, and the live service is
recorded before any test is written from it — the discipline that caught Pl@ntNet's
whole-request 400 and Nominatim's 200-with-an-error-body.

## 1. Provenance on the shape everything already reads

- [x] 1.1 Add `origin` and `sources` to `CareProfile`, defaulting to curated and empty; verify the existing care-profile tests pass with their assertions unchanged.
- [x] 1.2 Confirm the 18 hand-written profiles read as curated without being edited; verify a test asserts one of them reports `curated`.
- [x] 1.3 Confirm nothing else in the codebase constructs a `CareProfile` that would now claim to be curated wrongly; verify by searching for constructions and stating what was found.

## 2. Somewhere to keep one

- [x] 2.1 Add a `species_care_profiles` table with a unique normalised species key and a migration; verify the migration test passes and mentions no checkpoint table.
- [x] 2.2 Confirm the table carries no `user_id` deliberately and that the tenancy table does not cover it; verify by stating why in the model's docstring and checking the endpoint tenancy test still passes unchanged.
- [x] 2.3 Round-trip a profile through the repository; verify a test asserts `sources` and `origin` survive, and that a stored profile reads back as `researched` rather than relying on the default.
- [x] 2.4 Normalise the key the way the alias table already does; verify a test asserts three spellings of one species resolve to one row.

## 3. The lookup gains its tiers

- [x] 3.1 Read the stored table as a second tier behind the curated one; verify a test asserts a curated profile wins over a stored one naming the same species.
- [x] 3.2 Keep the tier inert until group 4 — no research yet; verify the full suite passes with the research path absent.
- [x] 3.3 Confirm a miss still returns `None`; verify the existing enrich and chat miss-path tests pass unchanged.

## 4. Researching one, and refusing to

- [x] 4.1 Make one manual search for a species outside the curated set and save the raw response under `tests/fixtures/`; verify the file exists and record which species and what came back.
- [x] 4.2 Make a second search for a species whose close relative dominates the results — *Ocimum africanum* is the known case — and save that too; verify the recording actually contains the near-miss, because the refusal tests are built from it.
- [x] 4.3 Add the extraction: a structured `CareProfile` plus the species the material describes; verify a test built from 4.1 produces a usable profile.
- [x] 4.4 Refuse where the described species does not match the one asked for; verify a test built from 4.2 asserts no profile is produced, and that it fails if the comparison is removed.
- [x] 4.5 Refuse on no results, a failed call, and an unparseable response; verify a test covers each and asserts the caller sees the same `None` a miss has always produced.
- [x] 4.6 Do not store a refusal as an answer; verify a test asserts a second request after a refusal is still a miss rather than an empty profile.
- [x] 4.7 Fence the retrieved material as untrusted before the model reads it; verify a test asserts material carrying an instruction produces a care profile and not the instruction's effect.
- [x] 4.8 Confirm a run completes when research fails; verify a test asserts the diagnosis still produces a differential.

## 5. Saying what it is

- [x] 5.1 Say in the chat tool's reply whether the profile was curated or researched, with its sources; verify a test asserts both wordings and that a curated profile is not described as researched.
- [x] 5.2 Tell the diagnosis prompt the same fact in one clause; verify a test asserts the clause is present for a researched profile and absent for a curated one.
- [x] 5.3 Confirm the miss wording still names the next step; verify the existing test covering the strawberry case passes unchanged.

## 6. The wirings, which have broken silently before

- [x] 6.1 Drive a researched profile through `agent.wiring.build_deps` end to end; verify a test asserts the profile it returns reports `researched` — the arity test cannot see a changed return type.
- [x] 6.2 Do the same for the evaluation harness's hand-built `Deps`; verify the harness-wiring and port-arity tests pass and that this one fails if either wiring is left on the old shape.
- [x] 6.3 Confirm no golden case newly triggers research; verify by listing the golden set's species against the curated set and stating the result.

## 7. Proving it works, and closing

- [x] 7.1 Run a live diagnosis for a species outside the curated set; verify a profile was researched, stored, labelled, and reached the prompt.
- [x] 7.2 Run a second diagnosis for the same species; verify no search happened and the stored profile was used.
- [x] 7.3 Ask the chat agent about that plant's care; verify the reply says the guidance was researched.
- [x] 7.4 Update the README: the three tiers, why a profile can be refused, and what "researched" means where somebody reads it; verify every command runs as written on a clean clone.
- [x] 7.5 Record what this leaves undone — the echo-back failure mode, no refresh, no surface outside chat, the shared table's write-triggered-by-one-read-by-others property; verify identifiers and dates against the file's conventions, and retire `U1`'s web-search half.
- [x] 7.6 Run `openspec validate add-species-care-profiles --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
