# Implementation tasks

Ordered so the thing that cannot be undone is proven before it is reachable from a screen. No
schema change: every cascade this depends on already exists.

## 1. Proving what a deletion has to reach

- [ ] 1.1 Write the schema-derived completeness check: create a full account, delete its `users` row, then walk `Base.metadata.tables` and assert each is empty except the reference ones; verify it fails when a table is removed from the classification.
- [ ] 1.2 Confirm the database cascade is as complete as it appears; verify a test asserts the six tables with no `user_id` — observations, diagnoses, roadmap_steps, feedback, profile_cursors, run_events — are empty afterwards.
- [ ] 1.3 Confirm reference data survives; verify a test asserts `corpus_chunks` and `species_care_profiles` are untouched by a deletion.
- [ ] 1.4 Confirm another owner is untouched; verify a test creates two full accounts, deletes one, and asserts every row of the other remains.

## 2. Deleting an account

- [ ] 2.1 Add the deletion service: revoke refresh tokens, delete checkpoints by thread prefix, then delete the user; verify a test asserts all three happened.
- [ ] 2.2 Order checkpoints before the user row and say why; verify a test asserts the order, and record the reasoning where the order is set.
- [ ] 2.3 Delete the checkpoint rows through the existing `agent/checkpoints.delete_for_user`; verify a test asserts a checkpoint written under the owner's prefix is gone and one under another prefix is not.
- [ ] 2.4 Confirm the deletion of application rows is one transaction; verify a test asserts a failure part-way leaves the account intact.
- [ ] 2.5 Confirm signing in afterwards is refused indistinguishably from an unknown address; verify a test compares both responses.

## 3. The endpoint, and its confirmation

- [ ] 3.1 Add the deletion endpoint taking a password and a typed confirmation, acting only on the requesting account; verify a test asserts it takes no identifier.
- [ ] 3.2 Verify the password server-side against the current user; verify a test covers the right password, the wrong one, and a missing one.
- [ ] 3.3 Check the typed confirmation server-side; verify a test asserts a request with the correct password and no confirmation deletes nothing.
- [ ] 3.4 Confirm the client-type agreement test covers any new request shape; verify both sides match.
- [ ] 3.5 Confirm a refresh after deletion is refused; verify a test asserts it.
- [ ] 3.6 Record what an access token issued before deletion can still do; verify a test asserts a read returns nothing and a write fails rather than creating a record.

## 4. Taking the data out

- [ ] 4.1 Add the export, assembling every record from the repositories that already read them; verify a test asserts plants, observations, diagnoses, roadmap steps, messages, learned facts and usage all appear.
- [ ] 4.2 Include the photographs; verify a test asserts the bytes in the archive match what was uploaded.
- [ ] 4.3 Carry names alongside identifiers so it reads without this application; verify a test asserts a diagnosis names its plant rather than only referencing it.
- [ ] 4.4 Include nothing belonging to another owner; verify a test with two populated accounts asserts it.
- [ ] 4.5 Produce a valid empty export for an account with nothing; verify a test asserts it is readable rather than an error.
- [ ] 4.6 Add a size guard as configuration; verify a test asserts an account over the limit is refused rather than served, and `.env.example` names the setting.
- [ ] 4.7 Add the export endpoint with a filename a browser will use; verify a test asserts the disposition header and that it requires a session.

## 5. The controls somebody uses

- [ ] 5.1 Add a client helper that receives a binary body and reads its filename; verify a test asserts the existing JSON helper is unchanged.
- [ ] 5.2 Add the export control to the account screen; verify a component test asserts it downloads through the authenticated path rather than a bare link.
- [ ] 5.3 Add the delete-account control with password entry and typed confirmation, following the existing two-step pattern; verify a component test covers cancelling, a wrong password, and completing.
- [ ] 5.4 Say plainly what deletion destroys before it happens; verify a test asserts the warning names photographs, diagnoses and conversations.
- [ ] 5.5 Confirm the account screen still passes axe with both controls present; verify the accessibility test covers the route.

## 6. The adjacent leaks this change makes untenable

- [ ] 6.1 Make `services/chat_service` build its thread id through `agent/threads.chat_thread` rather than by hand; verify a test asserts the two produce the same string, and that the duplicate is gone.
- [ ] 6.2 Delete a plant's chat checkpoints when the plant is deleted; verify a test asserts they are gone and that another plant's are not.
- [ ] 6.3 Confirm `recheck_thread` and `chat_thread` have production callers or record why not; verify by stating what was found.

## 7. Proving it works, and closing

- [ ] 7.1 Add a browser flow exporting an account; verify a file arrives and its name is what the header asked for.
- [ ] 7.2 Add a browser flow deleting an account; verify the wrong password refuses, the right one completes, and signing in afterwards fails.
- [ ] 7.3 Delete a real account in the development database and check the tables by hand; verify what remains and record anything unexpected.
- [ ] 7.4 Update the README: what an export contains, what deletion removes, and what it deliberately does not; verify every command runs as written on a clean clone.
- [ ] 7.5 Record what this leaves undone — the access-token window, the export's omission of cited corpus text, no retention policy; verify identifiers and dates against the file's conventions.
- [ ] 7.6 Run `openspec validate add-privacy-controls --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
