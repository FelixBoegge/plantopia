## Why

Plantopia is single-user by construction, and not by choice: the domain data is a SQLite file
with no notion of an owner, `user_profile` carries a global `UNIQUE(fact)` so no two people
could ever learn the same thing, and a checkpoint thread id is `recheck-{plant_id}-{n}` — a
guessable, resumable handle to somebody else's paid diagnosis the moment a second person exists.
Nothing else on the roadmap can start until that is fixed. Authentication has nowhere to put a
user; background runs have nowhere durable to record their state; and a deployment that keeps
its database, its vector store and two checkpoint files on a container filesystem loses all four
on the first redeploy.

Two measured problems come with it. Graph state carries whole photographs as base64, and
LangGraph re-serialises state at every superstep — two completed diagnoses of 3 MB photographs
produced **205 MB of checkpoint blobs** against a 69 KB main database on 2026-08-10 (`M15`). And
the absence of any migration path is the stated reason chat token accounting was never added
(`M17`); it will keep being the reason until a migration tool exists.

This change moves everything into one Postgres and makes ownership a property the database
enforces rather than a convention callers are trusted to follow.

## What Changes

- **SQLAlchemy 2.0 typed models replace `data/schema.sql` and hand-written SQL**, synchronous on
  psycopg3. Repositories are injected into LangGraph nodes via `Deps`, so an async data layer
  would cascade through nodes, tools, services and every test covering them for no gain on work
  that is IO-bound on someone else's HTTP API.
- **Alembic from the first migration**, generated from those models. The project's first
  migration path.
- **BREAKING: every repository method takes `user_id` as its required first parameter** and every
  query filters on it. A row belonging to another owner is absent, not forbidden — callers get
  the same answer they would get for a row that never existed.
- **BREAKING: primary keys become UUIDv7.** `/plants/3` tells a stranger how many plants exist
  and invites them to try `/plants/4`; time-ordered UUIDs end that without giving up insert
  locality.
- **`user_id` is added to `plants`, `user_profile` and `messages`**; the other five tables reach
  an owner through their parent, where `ON DELETE CASCADE` already chains. `UNIQUE(fact)` becomes
  `UNIQUE(user_id, fact)`.
- **A `users` table is created here**, because the foreign keys need somewhere to point.
  Registration, password hashing, sessions and everything else about identity belong to the next
  change; this one seeds a single owner so the Streamlit UI keeps working while React is built.
- **Timestamps become real `timestamptz`** instead of ISO strings parsed by hand. `M3`'s inert
  `PARSE_DECLTYPES` line leaves with the sqlite3 driver.
- **A `BlobStore` port with a Postgres `bytea` adapter.** Graph state carries keys, not bytes,
  which closes `M15`. S3 becomes a second adapter later rather than a rewrite.
- **Both LangGraph checkpointers move to Postgres**, and thread ids gain an owner prefix
  (`{user_id}:diagnose:…`, `{user_id}:chat:{plant_id}`). Every resume path verifies ownership
  before touching state.
- **A hand-written `PgVectorRetriever` replaces `ChromaRetriever`**, implementing the existing
  `Retriever` Protocol unchanged. Exact cosine search over ~300 corpus sections with **no HNSW
  index**: approximate search can reorder results on its own, and this change needs any
  difference to be attributable to the new SQL. Embeddings are exported from Chroma rather than
  recomputed — same vectors, same model, no API calls.
- **A retrieval parity gate** ships with it: committed query-vector fixtures replayed through
  both retrievers, asserting identical document ids, sections and ordering for `search` *and* for
  the `sections_for` fetch-by-id path. It costs nothing and runs in CI.
- **Tests gain a Postgres dependency.** `docker compose up -d db` becomes a prerequisite, and the
  suite's "no network calls" claim is retired rather than faked.

**Explicitly out of scope:**

- *Authentication, registration, sessions* — the next change. This one creates the table and one
  seeded owner, nothing more.
- *Upload downscaling (`U3`)* — it changes what the vision model sees, and evaluation is
  structurally blind to vision (`M19`), so nothing here could detect the damage if it did any.
  Full-size bytes continue to reach the model.
- *An HNSW index* — 43 documents, ~300 sections. Revisit an order of magnitude later.
- *An S3 blob adapter* — the port ships; the adapter does not.
- *Migrating existing local data* — development data is development data. The database starts
  empty and the corpus is re-ingested.
- *Any change to diagnosis behaviour* — this change is verified against the premise that
  behaviour is constant, and the parity gate is how that premise is checked.

## Capabilities

### New Capabilities

- `data-persistence`: how domain records are stored, identified and isolated per owner — the
  tenancy rule, identifier scheme, timestamp handling, and the migration path that lets the
  schema change without losing data.
- `photo-storage`: how uploaded photographs are stored, addressed and retrieved, and what the
  agent's state carries in their place.
- `disorder-retrieval`: how the disorder corpus is searched — similarity search over sections,
  and fetch-by-document-id with no ranking involved, which is what hypothesis-driven retrieval
  depends on.
- `run-checkpointing`: how a paused diagnosis and a chat thread persist between requests, and
  who is permitted to resume one.

### Modified Capabilities

None. This is the first change under OpenSpec, so `openspec/specs/` is empty and each capability
above is being described for the first time. Three of the four already exist as behaviour in the
code; writing them down is part of this change's work, and the parity gate exists precisely to
prove that what is written down matches what shipped.

## Impact

**Code.** `data/` is rewritten (models, repositories, migrations). `knowledge/retriever.py` gains
`PgVectorRetriever` and loses `ChromaRetriever` from the runtime path. `core/images.py` writes
through the `BlobStore` port. `agent/state.py` and the nodes that consume `ImageRef` carry keys
instead of base64. `agent/wiring.py`, `ui/bootstrap.py` and `eval/run_eval.py` construct the new
retriever and repositories. `services/` gains `user_id` on its call signatures.

**Dependencies.** Added: `sqlalchemy`, `alembic`, `psycopg`, `pgvector`, a UUIDv7 generator, and
`langgraph-checkpoint-postgres`. Removed from the runtime: `langgraph-checkpoint-sqlite`.
`chromadb` moves to the dev group rather than leaving — the vector export and the parity fixtures
need it, and deleting the old retriever before the gate has run would destroy the only evidence
that retrieval survived.

**Tests.** Repository and retriever tests are rewritten against Postgres; every other tier is
untouched. Coverage stays gated at 85%.

**Operations.** `docker compose up -d db` (`pgvector/pgvector:pg17`) becomes required for
development and for the test suite. Corpus ingestion becomes an explicit one-shot command rather
than a side effect of first run.

**Risk.** The retrieval rewrite is the one part of this change that could move diagnostic
accuracy — 89.3% top-1 and 96.4% top-3 over 28 golden cases, measured 2026-08-19. The parity gate
is the mitigation, and it is stricter than re-measuring accuracy because it fails on the specific
thing that can break rather than on a number that moves for six reasons.
