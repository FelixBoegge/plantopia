## Context

See `proposal.md` — Why. What shapes the approach is that most of the machinery already
exists and none of it is wired to anything.

**The database already cascades completely.** Every foreign key in `data/models.py` declares
`ondelete="CASCADE"` — all nineteen of them. `DELETE FROM users WHERE id = X` today reaches
every one of the owned tables, including the six that carry no `user_id` and are reachable
only through a parent (`observations`, `diagnoses`, `roadmap_steps`, `feedback`,
`profile_cursors`, `run_events`), and including `blobs`, which carries `user_id` directly.
Nothing fails on a constraint and nothing is orphaned. The one `SET NULL`
(`runs.diagnosis_id`) is irrelevant, because the run row itself goes by `runs.user_id`.

**Two `delete_for_user` functions already exist, and neither has a production caller:**

- `agent/checkpoints.py:delete_for_user(url, user_id)` — deletes from `checkpoint_writes`,
  `checkpoint_blobs` and `checkpoints` by `thread_id LIKE '{user}:%'`, with `!` `%` `_`
  escaped. Exercised only by its own tests.
- `core/blobs.py:PostgresBlobStore.delete_for_user(user_id)` — exercised only by its own tests,
  and redundant against the database cascade.

`identity/sessions.py:revoke_all_for_user(session, user_id)` exists too, also unused by any
deletion path. This is the same shape as `M40`: capability built, never connected.

**Thread ids carry the owner**, which is what makes the checkpoint sweep possible.
`agent/threads.py` defines `diagnosis_thread`, `recheck_thread`, `chat_thread` and
`prefix_for`, and every production thread id begins `{user_id}:`. One caveat found while
scouting: `services/chat_service.py:_thread_id` builds `f"{user_id}:chat:{plant_id}"` by hand
instead of calling `chat_thread`, so the invariant deletion depends on is enforced in two
places rather than one.

**There is no archive support anywhere** — no `zipfile`, no `tarfile`, nothing in
`pyproject.toml`. The only binary response in the API is `api/routers/photos.py`, a buffered
`Response`; no endpoint sets `Content-Disposition`.

**The frontend cannot receive a binary body.** `web/src/api/client.ts:request` always
`JSON.parse`s. And the access token lives in memory (`web/src/api/session.ts`), not a cookie,
so a plain `<a href>` download would arrive unauthenticated.

**There is no password-change flow**, so no "verify the current password" helper.
`identity/passwords.verify(password, hash)` exists, and `identity/accounts.authenticate` shows
the pattern including its timing-equalisation.

## Goals / Non-Goals

**Goals:**

- Take everything out, in a form readable without this application.
- Delete an account and leave nothing — including what the schema does not describe.
- Prove completeness in a way that a table added next year cannot slip past.
- Leave reference data alone.

**Non-Goals:**

- **Retention or scheduled deletion.** Nothing expires on a timer.
- **Anonymising instead of deleting.**
- **Administrative deletion of another account.**
- **A password-change flow.** Re-entry here is a confirmation, not account management.
- **Streaming the export.** See below.

## Decisions

### Deletion is one `DELETE`, plus the two things the database cannot see

The database already does the hard part. What the application must add is what is outside its
schema:

1. Revoke the refresh tokens, so the session cannot be extended.
2. Delete the checkpoint rows by thread prefix.
3. `DELETE FROM users WHERE id = X`, and let nineteen cascades do the rest.

In that order, and in one transaction — except the checkpoints, which are on a **different
connection**: the checkpointer owns its own pool. So the honest statement is that this is
*two* atomic operations, and the order matters. Checkpoints first means a failure at step 3
leaves an account whose conversations have lost their history — recoverable, embarrassing.
Checkpoints last means a failure leaves checkpoint rows belonging to a user who no longer
exists — unreachable by anyone, invisible, and never cleaned up.

Losing history for an account that still exists is the better failure, because somebody can
see it and complain. So checkpoints go first.

### Completeness is derived from the schema, not from a list

`tests/unit/data/test_models.py` already classifies every table as `OWNED_DIRECTLY`,
reference data, or owned-through-a-parent, and asserts the classification covers
`Base.metadata` exactly. The deletion test reuses that: create a full account, delete it,
then walk `Base.metadata.tables` and assert every table is empty except the reference ones and
the other owner's rows.

This is the whole reason to trust the change. A hand-written list of tables to check is a list
that goes stale silently; a check derived from the schema fails the moment somebody adds a
table without classifying it, which is exactly when it should.

### The export is JSON in a ZIP, built in memory

A ZIP because photographs are bytes and JSON is not, and one file is what somebody can keep.
JSON because it is readable without this application, which is the requirement.

Built in memory rather than streamed. Streaming a ZIP means either buffering it anyway or
generating it in pieces while holding a database session open across the whole response, and
the sizes here do not justify that: the data is one person's plants and their photographs,
bounded by an upload limit that is already configuration. A size guard refuses rather than
exhausting memory, and the number it guards is a setting.

**Identifiers are kept and are not enough on their own.** An export whose rows reference each
other only by UUID is technically complete and practically unreadable. Each record carries the
name of what it points at as well — a diagnosis names its plant — so the archive can be read
by a person rather than reconstructed by one.

### The token that outlives the account

`api/dependencies.current_owner` believes an access token on its signature alone and reads no
row. Its docstring is explicit that this is the deal a stateless token makes, and that the
fifteen-minute lifetime is the only lever.

So deletion **cannot** make an outstanding access token stop working, and the spec says what is
true instead: refresh tokens are revoked so the session cannot be extended, and the access
token dies on its own within fifteen minutes. In between, the holder — who is the person who
just asked to be deleted — can call endpoints. Reads return nothing, because nothing of theirs
remains. Writes fail on the foreign key to a `users` row that is gone, which is an ugly error
rather than an orphaned record.

Adding a database read to `current_owner` would fix the window and would change the
architecture of every request in the application to buy fifteen minutes against a threat that
is the account's own owner. That is not a trade this change should make quietly; it is
recorded instead.

### Password re-entry, and what its failure may say

`identity.passwords.verify` against the loaded user. Unlike `authenticate`, this path may say
plainly that the password was wrong: the caller is already authenticated as this account, so
confirming the password is wrong reveals nothing that the session does not already establish.

The typed confirmation is checked server-side as well as in the browser. A confirmation only
the client enforces is a confirmation that a script does not have to type.

### The frontend needs a way to receive bytes

`request` always parses JSON, so the export needs a sibling that returns a blob and reads the
filename from `Content-Disposition`. It goes beside `request` rather than replacing it,
because every other call in the application does want JSON.

The download is triggered from an object URL, the same mechanism `usePhoto` already uses for
authenticated images — a bare link cannot carry the bearer token.

## Risks / Trade-offs

- **Deletion is irreversible and now reachable from a screen** → password re-entry, a typed
  confirmation, and both checked on the server.
- **Two atomic operations rather than one**, because checkpoints live on another connection →
  ordered so the survivable failure is the one that can happen, and stated plainly.
- **An export holds everything about a person in one file** → it is generated per request,
  never stored, and requires a live session.
- **A large account could produce a large archive** → a size guard that refuses, with the limit
  as configuration.
- **The prefix invariant is enforced in two places** (`agent/threads.py` and the hand-built
  string in `chat_service`) → the duplicate is removed as part of this, since deletion's
  correctness now depends on it.
- **`plant_service.delete_plant` does not remove the checkpoints of that plant's chat thread**
  — a pre-existing leak in a path whose spec says "the plant and everything hanging off it are
  removed". Adjacent to this change rather than part of it, and fixed here because leaving it
  while adding a requirement about deletion meaning deletion would be inconsistent.

## Migration Plan

No schema change. Every cascade this depends on already exists and is already in the
migrations.

Order, which is also the order the risk retires:

1. The deletion service, and the schema-derived test that proves it.
2. The endpoint, its confirmation, and session revocation.
3. The export, built from the repositories that already read everything.
4. The two screens' controls.
5. The adjacent fixes: the duplicated thread-id construction, and plant deletion's
   checkpoints.

**Rollback** is removing the two endpoints. Nothing else changes shape, and the two
`delete_for_user` functions return to being unused rather than becoming wrong.

## Open Questions

- **Whether an export should include the corpus passages a diagnosis cited.** They are
  reference data and identical for everybody, so including them makes every export larger to
  say the same thing — but a diagnosis that cites `[overwatering §2]` and does not carry the
  text is a diagnosis somebody cannot fully re-read afterwards. Deferred until somebody asks
  to read one.
- **Whether deletion should be confirmable by typing the email address** rather than a fixed
  word. The address is specific to the account and harder to type by reflex; a fixed word is
  easier to get right in a hurry, which cuts both ways.
