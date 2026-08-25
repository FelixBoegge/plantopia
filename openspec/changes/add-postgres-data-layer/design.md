## Context

See `proposal.md` — Why. The requirements this design has to satisfy are in
`specs/data-persistence`, `specs/photo-storage`, `specs/disorder-retrieval` and
`specs/run-checkpointing`.

The constraints that shape the approach, all of them properties of the code as it stands:

- **Repositories are injected into the graph.** `agent/nodes/persist.py` writes through four
  repositories reached via `Deps`. Whatever the data layer becomes, the graph is a caller.
- **`Retriever` is already a Protocol** with five methods, and `ChromaRetriever` is one
  implementation. The seam for swapping storage exists.
- **The escalation gate reads a retrieval score.** `PLANTOPIA_RETRIEVAL_SCORE_THRESHOLD` (0.35)
  decides whether web search fires. Scores are not merely displayed; they change control flow.
- **Three `async def`s exist in ~8,000 lines of application code.** This is a synchronous codebase.
- **Streamlit must keep working** until React replaces it, because it is the control client for
  telling platform bugs from redesign bugs during the migration.

## Goals / Non-Goals

**Goals:**

- One datastore for domain records, corpus vectors and run checkpoints.
- Ownership enforced where it cannot be forgotten, rather than by convention at call sites.
- A retrieval implementation whose equivalence to the current one is *proven*, not assumed.
- A schema that can change again without hand-written DDL.

**Non-Goals:**

- Performance work. The corpus is ~300 sections and the workload is single-digit concurrent
  users; nothing here needs an index or a tuned pool.
- Making the data layer reusable beyond this application.
- Any behavioural change to diagnosis. The parity gate exists to hold this line.

## Decisions

### Synchronous SQLAlchemy 2.0 on psycopg3

Typed `Mapped[]` models, a synchronous `Session`, psycopg3 as the driver.

*Alternative rejected: async SQLAlchemy with asyncpg.* FastAPI's idiom is async, and choosing
sync deliberately is the kind of thing that looks like an oversight later, so the reason is worth
recording. Repositories are called from inside LangGraph nodes. Making them async makes the nodes
async, which makes the tools and services async, which rewrites the suite covering them — for
work that spends its time waiting on OpenRouter over HTTP, where threads are already the right
tool. FastAPI runs sync endpoints in a threadpool. The cost of the async version is measured in
weeks; the benefit is zero at this concurrency.

### Alembic, with the first migration generated from the models

`data/schema.sql` becomes the models; `alembic revision --autogenerate` produces the initial
migration; `alembic upgrade head` runs on application start.

*Alternative rejected: keep executing `schema.sql` at startup.* It works precisely once — the
first time a database is created. It has no answer for a column added later, which is exactly the
gap `M17` has been sitting behind.

### UUIDv7 primary keys, generated in the application

Identifiers are generated before insert rather than by the database, because a blob key and a
plant id are both needed in application code before the row exists.

Python 3.12's `uuid` module has no v7 generator, and the target image is PostgreSQL 17, whose
`gen_random_uuid()` is v4. So a small library supplies it. v7 rather than v4 because it is
time-ordered: random v4 keys scatter index inserts across the whole B-tree, and while that does
not matter at this size, it costs nothing to avoid.

*Alternative rejected: bigint internally with a public UUID column.* Two identifiers per row, a
lookup on every request, and a standing opportunity to leak the internal one in a response.

### Tenancy as a required parameter, not row-level security

Every repository method takes `user_id` first. A method that does not take it cannot be written
without failing at the call site.

*Alternative considered and deferred: PostgreSQL row-level security.* RLS is genuinely stronger —
it holds even when application code is wrong. It also requires `SET LOCAL` on every checked-out
connection, which entangles tenancy with pool behaviour, and it protects nothing extra against
the failure this design actually fears: a repository method that queries the right rows for the
wrong reason. Recorded as an open question rather than dismissed.

### Blob storage as a port with one adapter

```
put(user_id, data, content_type) -> key
get(user_id, key) -> bytes | None
delete_for_user(user_id) -> int
```

`PostgresBlobStore` writes to a `blobs` table with a `bytea` column, keyed by UUIDv7, owned by a
user, carrying content type and byte size. The key is opaque by contract
(`specs/photo-storage`), which is what allows an S3 adapter later without touching callers.

*Alternative rejected: PostgreSQL large objects.* They need their own API, their own vacuum
behaviour, and they do not participate in the same transaction discipline as ordinary columns.
`bytea` at photograph sizes is simpler and adequate.

### `ImageRef` carries a key, never bytes

`ImageRef.data_b64` is replaced by `ImageRef.key`. Bytes are resolved from the store at the one
boundary that needs them — the vision call — and never enter graph state.

*Alternative rejected: making `data_b64` optional.* An optional field that used to be populated
will be populated again by the first code path that forgets, and `M15`'s 205 MB of checkpoint
blobs is what that looks like.

### The retriever: exact cosine, no index, vectors exported not recomputed

`corpus_chunks(id, doc_id, section, content, metadata jsonb, embedding vector(1536))`. Search is
`ORDER BY embedding <=> :query LIMIT :k` — cosine distance, sequential scan over ~300 rows,
sub-millisecond. `sections_for` is a plain `WHERE doc_id = ANY(...) AND section = ANY(...)` with
no ordering by distance at all, because ranking is exactly what that path must not do.

**No HNSW index.** Approximate search may reorder results by construction. This change has to be
able to attribute any retrieval difference to the new SQL, and an approximate index makes that
impossible.

**Vectors are exported from the existing Chroma collection**, not recomputed. Re-embedding would
produce vectors that differ in the last bits and make exact parity unprovable — quite apart from
spending money to get less certainty.

*Alternative rejected: `langchain-postgres`'s PGVector.* It brings its own schema and its own
opinions about how documents are stored, between this code and the one query — fetch-by-id — that
the 89.3% top-1 accuracy depends on.

### Score parity is asserted separately from ranking parity

The current retriever converts Chroma's cosine distance into a score, and that number feeds the
web-search escalation threshold. pgvector computes the same distance in different arithmetic, so
the last bits will differ.

Ranking, document ids and section names are asserted **exactly**. Scores are asserted within
`1e-6`, and the escalation decision is asserted directly: for every recorded query, whether the
best score falls above or below 0.35 must be the same on both sides. A change that silently
turned web escalation on or off would otherwise pass a ranking-only comparison.

### One checkpointer instance, thread ids namespaced by owner

`PostgresSaver` from `langgraph-checkpoint-postgres`, one instance serving both graphs. Thread
ids become `{user_id}:diagnose:{...}` and `{user_id}:chat:{plant_id}`. Resume paths parse the
prefix and compare it to the requesting owner before touching state.

*Alternative rejected: separate schemas or databases per graph.* The lifetimes differ, which was
the original reason for two SQLite files, but two tables in one database already give that.

### A single seeded owner keeps Streamlit alive

The `users` table is created here with one seeded row. `ui/bootstrap.py` passes that id into
services. Authentication replaces the seed in the next change.

*Alternative rejected: making Streamlit unusable until auth lands.* It is the control client for
the whole migration; losing it in week one costs more than the seed does.

## Risks / Trade-offs

- **The retrieval rewrite moves diagnostic accuracy** (89.3% top-1, 96.4% top-3, 28 cases,
  2026-08-19) → The parity gate in `specs/disorder-retrieval` is the mitigation: recorded query
  vectors replayed through both implementations, asserting identical ids, sections and ordering,
  scores within tolerance, and identical escalation decisions. It costs nothing and runs in CI.
  If parity cannot be reached, the change stops rather than proceeding on a re-measured number.
- **Score scale drift silently changes web escalation** → asserted directly, as above, rather
  than inferred from ranking.
- **Chroma is deleted before the gate has run**, destroying the reference → `chromadb` moves to
  the dev dependency group and stays until the fixtures are committed and green. Ordering is
  explicit in the tasks.
- **The suite gains an infrastructure dependency** → `docker compose up -d db` becomes a
  prerequisite, and CI gains a service container. The suite's "no network calls" claim is retired
  in the README rather than quietly falsified; **no-LLM-calls is unaffected and stays absolute**.
- **Coverage dips while `data/` is in flight** → the gate stays at 85% and the work is sequenced
  so repositories land with their tests, not before them.
- **`langgraph-checkpoint-postgres` may lag the pinned LangGraph version** → verified as the
  first task, before anything depends on it. If it cannot be satisfied, the fallback is to keep
  checkpointers on SQLite for this change and move them in the change that introduces background
  runs, where the interrupt is already being reworked.

## Migration Plan

No data migration: the database starts empty, and development data is discarded (`proposal.md` —
What Changes). Deployment of this change is `alembic upgrade head` followed by the one-shot
corpus ingestion command.

Order of work, which is also the order the risks retire:

1. Verify the checkpointer and pgvector dependency set resolves against the pinned LangGraph.
2. Models, initial migration, an empty database that starts.
3. Repositories with `user_id`, their tests, and the seeded owner — Streamlit still runs.
4. Blob store, `ImageRef` carrying keys, and the state-size assertion.
5. Export the Chroma vectors, capture the parity fixtures, commit them.
6. `PgVectorRetriever`, then the parity gate, then — only once it is green — remove
   `ChromaRetriever` from the runtime path.
7. Checkpointers, with owner-prefixed thread ids.

**Rollback** is `git revert` of the branch. Nothing in production depends on this yet; the
application is not deployed, and the only data at risk is local development data that is
deliberately not being migrated.

## Open Questions

- **Row-level security as a second layer.** Worth adding once there is a compliance reason or a
  second application touching the same database. It changes no requirement here — tenancy is
  already specified as behaviour — so it can be added later without reopening this change.
- **Content-hash deduplication of blobs.** The same photograph uploaded twice is stored twice.
  Cheap to add later, no observable behaviour change either way.
