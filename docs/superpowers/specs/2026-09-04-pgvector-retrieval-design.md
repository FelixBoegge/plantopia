# Retrieval moves to pgvector, and Chroma goes

*2026-09-04*

`M25` has stood since 2026-08-25: the corpus lives in two places and only one of them is
used. `corpus_chunks` and `PgVectorRetriever` are migrated and tested, and nothing consumes
them. This change makes pgvector the only retrieval path and removes Chroma, its two
dependencies and the vector store on disk.

Deliberately **not** a change to the embedding model. That question is settled by keeping
`openai/text-embedding-3-small`, and the reasoning is in *One variable* below.

## What M25 was waiting for, re-checked

It recorded two blockers that compound. Only one of them still exists.

**The parity gate is already gone.** `M25` worried that the gate justifying the switch
rested on replaying recorded query vectors, which `M24` shows cannot be an exact baseline.
That machinery no longer exists: `ddcea71` deleted `knowledge/export_chroma.py` (95 lines),
`eval/capture_retrieval_fixtures.py` (190), `eval/retrieval_fixtures.py` (55) and
`eval/fixtures/retrieval_parity.json`. Nothing in the repository now depends on recorded
vectors, so nothing has to be argued away.

Two references outlived it and are corrected here. `pyproject.toml:74-75` still omits both
deleted files from coverage. And `knowledge/ingest_corpus.py`'s docstring still says
"Makes no model calls. The vectors come from ``knowledge.export_chroma``" — while the code
directly beneath it calls `embeddings.embed_documents(texts)`. The command has been able to
embed the corpus by itself the whole time; only its documentation said otherwise, which is
why the remaining work looked larger than it is.

**The embedding model was the real blocker, and the answer is to keep the current one.**
Settled with the owner on 2026-09-04.

## One variable

Keeping `text-embedding-3-small` is what makes this change cheap, and more importantly
what makes it *legible*.

Removing Chroma is an infrastructure change that should move no diagnostic numbers.
Changing the embedding model is an accuracy change that can only be justified by
measurement. Bundled, they are indistinguishable: if top-1 moved off 89.3%, nothing would
say which half did it, and the honest response would be to unpick them and measure twice
anyway. So the store moves first, on identical vectors, and the model question stays open
as its own change with its own baseline.

The consequences of that choice, all of them good:

- **No migration.** `EMBEDDING_DIMENSIONS` is 1536 (`data/models.py:45`) and the column is
  `Vector(dim=1536)` (`67f6ce1daf6d`). A different width would need an Alembic revision;
  the same width needs nothing.
- **No new evaluation baseline, and no $1.55.** The 2026-08-19 run cost $1.5444 and is the
  standing baseline at 89.3% top-1 and 96.4% top-3. A run is only warranted when something
  is expected to move numbers, and the standing instruction is to keep that spend low.
- **Re-embedding the corpus costs about $0.0005.** 43 documents, 92,487 characters, roughly
  23,000 tokens at $0.02/1M. `ingest_corpus` is idempotent, keyed on `(doc_id, section)`.

Rejected: `text-embedding-3-large` truncated to 1536, and at its full 3072. Both are
plausible improvements and neither belongs here. The first still changes every vector and
so needs a fresh baseline despite needing no migration; the second needs both. They are
the *next* change, and the register keeps the question open.

## The switch removes more than it adds

`PgVectorRetriever` already implements the same five members as `ChromaRetriever` —
`search`, `sections_for`, `known_doc_ids`, `supports_image_search`, `search_by_image` — and
shares `knowledge.merging`. So this is construction, not a rewrite. The interesting part is
what construction looks like afterwards.

Today `agent/wiring.py` reaches the retriever through two functions and a cache:
`_shared_retriever(settings)` delegates to an `@lru_cache(maxsize=2)` `_retriever_for(...)`
keyed on six scalars, because "embedding the corpus and opening the collection is the
expensive part of wiring" and building it per call "would re-embed on every chat message —
slow, billable, and in tests a network call the suite forbids".

None of that is true of pgvector. The vectors are already in Postgres; there is no corpus
to load at startup, no collection to open, and nothing to embed until somebody actually
searches. So both functions go, along with the cache and its six-scalar key, and
`build_deps` constructs `PgVectorRetriever(session, build_embeddings())` inline on the
session it already has.

That last point is a correctness improvement rather than a tidy-up. `PgVectorRetriever`
holds a `Session`, and a process-wide cache is exactly where a session must not live —
`api/dependencies.py` already argues this: a cached service pins one owner into a process
serving many, and a single SQLAlchemy session is not safe to share across concurrent
requests. Because `build_deps` is already handed a per-request session and already builds
every repository on it, the retriever simply joins them. A process-cached retriever holding
a session would have been a bug; there is no version of this change where the cache
survives.

Two smaller effects worth stating plainly:

- **Process start stops making a billable network call.** `build_vectorstore` embeds all
  301 sections on every start to upsert them into Chroma. After this, startup touches no
  embedding endpoint at all.
- **`known_doc_ids` caching narrows from per-process to per-request.** It is memoised on
  the instance, and the instance now lives for one request, so a diagnosis pays one extra
  `SELECT DISTINCT doc_id` over 301 rows. At that size it scans in under a millisecond, and
  trading it for a session-holding singleton would be a bad bargain.

## The cross-modal path is dropped, not preserved

Settled with the owner on 2026-09-04: no multimodal embedding model will be available, so
the idea is abandoned rather than parked. That makes this simpler than the first draft of
this design, which proposed amending `core/config.py`'s promise that the path would "light
up with no code change". There is no promise to amend once the path is gone.

The cross-modal path (spec §10.4, `U2`) has never run in production. It was off by default
because no multimodal embedding model is reachable — `gemini-embedding-001` is data-policy
blocked on restricted keys, and the OpenAI embedding models reject image input outright.
Keeping it would mean carrying a Protocol member, a settings flag, a threshold, a branch in
`enrich`, an HTTP client and 91 lines of tests for a capability nothing can supply.

Removed: `core/embeddings.py` (`ImageEmbedder`) and its tests; `multimodal_embeddings` and
`image_match_threshold` from `core/config.py` and their tests; `supports_image_search` and
`search_by_image` from the `Retriever` Protocol, from `ChromaRetriever` and from
`PgVectorRetriever`; the visual-matches branch in `agent/nodes/enrich.py` together with the
`search_by_photograph` entry it contributes to `tools_used`; `embed_image` from
`tests/fakes/embeddings.py`; and the explanatory comments in `core/llm.py` and
`eval/run_eval.py`.

`U2` is closed as *not pursued* rather than struck as fixed — the distinction matters,
because a future reader should find that the capability was considered and declined for a
supply reason, not that it was delivered.

This is the one part of this change that removes a documented feature, so it is stated
plainly rather than folded into the deletion list: §10.4 of the design describes a
capability the application will no longer have any code for. Nothing observable changes,
because the flag has always been off.

## The data wipe, and what it does and does not change

The owner intends to wipe the application's data on 2026-09-04, before this change lands.
That has one real consequence for the order of work and two opportunities, and it does not
affect the decision above.

**`corpus_chunks` is in the same database as the user data.** There is one
`database_url`; the corpus table is not held apart from plants and diagnoses. So
`docker compose down -v`, which drops the `pgdata` volume, takes the corpus with it. The
ingestion step therefore belongs *after* the wipe, or it is simply done twice. Chroma is
unaffected either way — it lives on the filesystem at `data/chroma/`, not in Postgres — and
if that directory is deleted too, `build_vectorstore` rebuilds it from the markdown corpus
on the next start for about $0.0005. The comparison in step 4 survives either choice.

**It does not reopen the embedding model.** A wipe removes the cost of *preserving* data
across a width change, which was the weakest of the three reasons for staying on
`text-embedding-3-small`. The two that carry the decision are untouched: a different model
still needs an Alembic revision whether or not rows exist, still needs the $1.55 baseline,
and still makes an accuracy change indistinguishable from an infrastructure one. Bundling
them now would save exactly one re-ingestion — $0.0005 — in exchange for not being able to
attribute a change in top-1 accuracy. The decision stands, and the wipe strengthens rather
than weakens it.

**Two things become verifiable that otherwise are not.** Both are free and neither is
required by this change, so they are noted rather than promised:

- `M49` — deleting an account failed outright on a deployment where nobody had run a
  diagnosis, because LangGraph creates its checkpoint tables in `PostgresSaver.setup()` on
  the first one. An empty database is precisely that state, and it cannot be reproduced
  again without destroying data. It is the one moment to confirm that fix.
- The fresh-install path — `alembic upgrade head`, then `ingest_corpus`, then a first
  diagnosis — has never been exercised end to end on an empty database.

One expectation to set: with no plants in the database, the timeline and history surfaces
render nothing, which is `U16` arriving by a different route. Looking at those screens
afterwards needs a plant made by hand first.

## Sequence, and why this order

1. **The wipe happens first**, for the reason above: the corpus table goes with it.
2. **Correct the stale references** — `ingest_corpus.py`'s docstring and
   `pyproject.toml`'s two dead coverage omits. Cheap, and doing it first means the rest of
   the change is read against accurate documentation.
3. **Populate `corpus_chunks`** with `python -m knowledge.ingest_corpus`. 301 rows, 43
   documents, about $0.0005. After `alembic upgrade head`, since the wipe took the schema
   too.
4. **Compare the two retrievers while both still exist.** This is the step that has to
   come before deletion, and the reason the order is not arbitrary.
5. **Wire `PgVectorRetriever`** into `agent/wiring.py` and `eval/run_eval.py:164-174`,
   deleting `_shared_retriever`, `_retriever_for` and the cache.
6. **Delete Chroma**: `ChromaRetriever` and `build_vectorstore` from
   `knowledge/retriever.py`, `settings.chroma_path`, the `langchain-chroma` and `chromadb`
   dependencies, `tests/unit/knowledge/test_retriever.py`, the Chroma fixtures in
   `tests/conftest.py` and `tests/e2e/server.py`, and the `data/chroma/`,
   `tests/e2e/.chroma/` and `data/corpus_vectors.json` entries in `.gitignore`.
   The cross-modal removals land here too, since `ChromaRetriever` is the only
   implementation that ever had a working `search_by_image`.
7. **Record it** in `docs/known-limitations.md`: strike `M25` with the date, and amend
   `U2` and `M24`'s standing note.

## Testing

The comparison in step 4 is the substantive check and it replaces the eval run, so it is
worth being precise about what it can and cannot prove. For each of the 28 golden cases,
both retrievers answer the same queries and their top-6 passages are compared by
`(doc_id, section)` and by rank.

Because the vectors come from the same model, the sets should be identical. They may
legitimately differ in the last position, and `M24` is why: the provider does not reproduce
its own vectors — 38 of 87 query strings embedded differently on a second call, moving
merged scores by up to 1.1e-3 — and Chroma additionally normalises in float32 and compares
by inner product, while pgvector's `<=>` is cosine distance. So the assertion is on the
passage *set* and on ranks 1 through 5, with a divergence at rank 6 reported rather than
failed. A difference above 1.1e-3, or any change in the leading passage, is a real finding
and stops the change.

This runs as an opt-in `integration` test, needs no LLM call, and costs only the query
embeddings. It is deleted along with Chroma in step 6 — it exists to license the deletion,
not to be maintained afterwards, and keeping a test of a store that no longer exists is how
the `ui/components` citations happened.

Everything else is the existing suite. `tests/unit/knowledge/test_pgvector_retriever.py`
already covers the retriever against real PostgreSQL. The coverage gate stays at 85%, and
deleting `test_retriever.py` together with `ChromaRetriever` moves both sides of that
fraction, so the gate is checked rather than assumed. `docker compose up -d db` remains a
prerequisite (`M26`).

One check that is easy to forget: `agent/studio.py` names Chroma in its docstring twice as
part of the wiring it deliberately defers, and `data/models.py:391` explains
`sections_for`'s key by reference to "the Chroma ids it replaces". Both are prose about a
thing that will not exist.

## Out of scope

**The embedding model.** Kept at `text-embedding-3-small` by decision above. `M25` is
struck; the model question is recorded as open in its place.

**A vector index.** 301 rows scan exactly in under a millisecond, and an HNSW index may
reorder results by construction. Nothing to buy at this size.

**The cross-modal image path.** Not ported and not kept — removed outright. See *The
cross-modal path is dropped, not preserved*.

**A fresh evaluation baseline.** Not warranted by a change that keeps every vector
identical. The 2026-08-19 numbers remain the standing baseline, already knowingly stale for
reasons unrelated to retrieval.
