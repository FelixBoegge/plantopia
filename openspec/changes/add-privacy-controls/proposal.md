## Why

Registration records what somebody consented to, and nothing in the application lets them act
on it. An owner can create everything and remove nothing: no way to take their data out, and
no way to close the account and have it actually gone.

The tenancy work proved a strong property — one owner's records are indistinguishable from
records that do not exist, enforced by a table-driven test over every endpoint. That is about
*reading*. Its counterpart has never been built: nothing proves the system can **forget**.

Those are different guarantees and the second is harder. A read path that misses a table
fails visibly the first time somebody looks. A delete path that misses a table fails silently
and forever, and the person who asked to be forgotten has no way to find out they were not.

Consent that can be recorded and never withdrawn is a record of permission, not a control.

## What Changes

- **An owner can take their data out.** One request returns everything held about them —
  plants, observations, diagnoses, treatment plans, chat transcripts, learned profile facts,
  usage — as structured data, together with the original photographs.
- **An owner can delete their account, and it is actually deleted.** Everything belonging to
  them goes: every table that reaches them, the stored photographs, and the conversation
  checkpoints that are not part of the application's own schema.
- **Deleting is gated by more than a click.** The password is re-entered and the intent typed
  out, because this is the one action in the system with no undo.
- **Reference data survives, deliberately.** The disorder corpus and the researched species
  care profiles belong to nobody and describe nothing personal. Deleting an account must not
  delete what a species needs, and the distinction is enforced rather than remembered.
- **The proof is driven off the schema itself.** The existing model tests already classify
  every table as directly owned, owned through a parent, or reference data, and assert that
  classification is exhaustive. Deletion is verified the same way: after deleting an account,
  every table in the schema is empty except the reference ones. A table added later cannot be
  forgotten, because it must be classified before its own tests pass.

## Capabilities

### New Capabilities

- `privacy`: what an owner can do with the data held about them — take it out, and have it
  removed — and what "removed" is required to mean.

### Modified Capabilities

- `http-api`: two endpoints on the account surface, and the confirmation deletion requires.

## Impact

**What makes this harder than it looks**

- **Checkpoint tables are not in the application's schema.** LangGraph's Postgres checkpointer
  creates and owns its own tables, so they are invisible to the model-driven sweep that covers
  everything else. They are reachable only through the thread identifiers the application
  constructs, which is why those identifiers carry the owner.
- **Photographs are bytes, not rows.** Whatever holds them has to be told as well.
- **Deletion is irreversible and runs across many tables.** It is one transaction or it is a
  half-deleted account.

**Deliberately not in scope**

- **Retention policies or scheduled deletion.** Nothing expires on a timer here. An account is
  deleted when its owner asks.
- **Anonymising rather than deleting.** Keeping "anonymised" rows attached to a deleted account
  is exactly the outcome somebody asking to be forgotten did not agree to.
- **Changing what is collected, or the consent text.** Consent capture already exists and is
  already specified; this is the other half of the same promise, not a revision of it.
- **Administrative deletion of somebody else's account.** There is a role in the system and
  this is not a use for it.
