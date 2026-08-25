## 1. Dependencies and database bring-up

- [x] 1.1 Resolve the dependency set — `sqlalchemy`, `alembic`, `psycopg[binary]`, `pgvector`, a UUIDv7 generator, `langgraph-checkpoint-postgres` — against the pinned LangGraph version; verify `uv sync` succeeds and `uv run python -c "from langgraph.checkpoint.postgres import PostgresSaver"` imports. If it cannot resolve, stop and take the fallback in design.md — Risks (checkpointers move in the background-runs change instead).
- [x] 1.2 Add `docker-compose.yml` with a `db` service on `pgvector/pgvector:pg17`, a named volume and a healthcheck; verify `docker compose up -d db` reaches healthy and `CREATE EXTENSION IF NOT EXISTS vector` succeeds.
- [x] 1.3 Add `database_url` to `Settings` with `.env.example` documentation; verify `tests/unit/core/test_config.py` covers the default and an override, constructed with `_env_file=None`.

## 2. Models and migrations

- [x] 2.1 Add a UUIDv7 helper in `core/`; verify a test that generates 100 identifiers in sequence and asserts they sort ascending and are all distinct.
- [x] 2.2 Write typed `Mapped[]` models for `users` and the eight existing tables, with UUIDv7 primary keys and `timestamptz` columns; verify a test asserting `Base.metadata.tables` holds exactly the expected nine names.
- [x] 2.3 Add `user_id` to `plants`, `user_profile` and `messages`, change `UNIQUE(fact)` to `UNIQUE(user_id, fact)`, and carry the existing `ON DELETE CASCADE` chains across; verify tests that two owners may hold the same learned fact and that deleting a plant removes its observations, diagnoses and roadmap steps.
- [x] 2.4 Scaffold Alembic and autogenerate the initial migration from the models; verify `alembic upgrade head` builds every table on an empty database and `alembic check` reports no drift afterwards.
- [x] 2.5 Add a SQLAlchemy engine, session factory and transaction context manager; verify a test proves commit on success and rollback on exception. Adjusted during implementation: this lands as a new `data/engine.py` rather than a rewrite of `data/db.py` in place. Twenty modules import `data.db`, and replacing it before the repositories move (group 4) would leave the suite red across the whole of groups 2 and 3. `data/db.py` is deleted in 4.6, when its last caller is gone.

## 3. Test infrastructure

- [x] 3.1 Add pytest fixtures that create the schema once per session against the compose database and wrap each test in a transaction rolled back at teardown; verify two tests writing the same natural key both pass in either execution order.
- [x] 3.2 Add a `pgvector` extension fixture and a corpus-loading fixture for retriever tests; verify a smoke test that stores and queries one vector.
- [ ] 3.3 Document `docker compose up -d db` as a prerequisite in the README's Development section and retire the "no network calls" claim, keeping the no-LLM-calls claim explicit; verify by reading the section back against what the suite now does.

## 4. Repositories with enforced tenancy

- [x] 4.1 Rewrite `PlantRepository` with `user_id` as the required first parameter on every method; verify its existing tests port plus a new test that a second owner reading the first owner's plant gets nothing back.
- [x] 4.2 Rewrite `ObservationRepository` and `DiagnosisRepository` the same way; verify ported tests plus cross-owner cases on `list_for_plant` and `latest_for_plant`.
- [x] 4.3 Rewrite `RoadmapRepository` and `FeedbackRepository`; verify ported tests, the `M10` rowcount `ValueError` on an unknown step id is preserved, and marking another owner's step raises rather than silently succeeding.
- [x] 4.4 Rewrite the profile and message repositories including `profile_cursors`; verify ported tests plus a test that the same fact for two owners is two rows. Found during implementation: two integer-id assumptions travel with this. `services/profile_service.py` reads `cursor_for(plant_id) or 0` — a sentinel that cannot exist for a UUID — and both the cursor comparison and `MessageRepository.list_for_plant`'s `ORDER BY id` rely on identifiers being chronological. Order by `created_at, id` and compare the cursor on an explicit `None` instead of leaning on UUIDv7's ordering, which ties arbitrarily within a millisecond.
- [ ] 4.5 Add a table-driven tenancy test that walks every public repository method taking a record identifier and asserts a foreign owner is refused; verify it fails when a `user_id` filter is deliberately removed from one method.
- [x] 4.6 Seed a single owner at startup and thread its id from `ui/bootstrap.py` through `services/` into the repositories; verify `uv run pytest -m ui --no-cov` passes and Streamlit still completes a diagnosis end to end.

## 5. Blob storage

- [x] 5.1 Define the `BlobStore` port and implement `PostgresBlobStore` over a `blobs` table; verify tests for put/get round-trip, an unknown key returning nothing, a foreign owner's key returning nothing, and `delete_for_user` leaving other owners untouched.
- [x] 5.2 Replace `ImageRef.data_b64` with `ImageRef.key` and resolve bytes from the store at the vision call only; verify the vision node tests pass against a fake store and that no other node reads image bytes.
- [x] 5.3 Route `core/images.py:store_upload` through the port, keeping magic-byte validation and orientation correction; verify the existing image tests port and a new test asserts delivered bytes equal uploaded bytes after orientation only — no downscaling.
- [x] 5.4 Add a test that serialises a completed diagnosis's run state and asserts it contains no image payload and stays under a fixed size ceiling; verify it fails if `ImageRef` is given bytes again.

## 6. Corpus vectors and parity fixtures

- [x] 6.1 Write a one-shot export script reading embeddings, documents and metadata out of the existing Chroma collection; verify it emits 301 sections across 43 documents at 1536 dimensions.
- [x] 6.2 Add the `corpus_chunks` table and an ingestion command that loads the exported vectors; verify row count, dimension and that every corpus document id is present.
- [x] 6.3 Capture the parity fixtures — the golden set's retrieval queries with their embedding vectors, the fetch-by-identifier requests, and the results `ChromaRetriever` returns for each; verify the fixture file is committed and covers all 28 cases. Embedding the recorded queries once costs well under a cent; nothing else in this gate calls an API.
- [x] 6.4 Record, alongside each fixture, whether the best score clears the 0.35 escalation threshold; verify the captured decisions match what the current pipeline does for those queries.

## 7. The pgvector retriever and its gate

- [ ] 7.1 Implement `PgVectorRetriever.search` with exact cosine ordering, a result limit and section filtering, and no index; verify the search half of the parity fixtures returns identical document ids, section names and ordering.
- [ ] 7.2 Implement `sections_for`, `known_doc_ids`, `supports_image_search` and `search_by_image`; verify the fetch-by-identifier fixtures match exactly, including a document that similarity search ranks outside the top twenty, and that image search reports itself unavailable.
- [ ] 7.3 Add the score-parity assertion at `1e-6` and the escalation-decision assertion against the captured decisions; verify the test fails if the score conversion is altered by a constant factor.
- [ ] 7.4 Construct the new retriever in `agent/wiring.py`, `ui/bootstrap.py` and `eval/run_eval.py`, and delete `ChromaRetriever` from the runtime path; verify the full suite is green and no runtime module imports `chromadb`.
- [ ] 7.5 Move `chromadb` from the runtime dependencies to the dev group; verify `uv run python -c "import chromadb"` still works from the dev environment and no module under `agent/`, `services/` or `knowledge/` imports it outside the export script. Moved here from group 1 during implementation: `langchain-chroma` is a runtime dependency that imports it, so the move is only valid once 7.4 has taken `ChromaRetriever` off the runtime path.

## 8. Checkpointers

- [ ] 8.1 Move both graphs to `PostgresSaver` and add a thread-id helper that prefixes every handle with the owner; verify a test that a diagnosis paused at the interrupt resumes with identification and symptoms intact after the saver is rebuilt.
- [ ] 8.2 Verify ownership on every resume path, including the re-check entry point; verify a test that a foreign owner presenting a valid handle is refused and no state is disclosed.
- [ ] 8.3 Preserve the `U7` thread rotation on the rejected and retake branches under the new handle scheme; verify the existing rotation tests port and still prove an abandoned attempt does not merge into the next.
- [ ] 8.4 Add checkpoint removal for one owner to the deletion path; verify a test that after removal none of that owner's runs resume and other owners' threads still do.
- [ ] 8.5 Remove `langgraph-checkpoint-sqlite` and the two checkpoint file paths from configuration; verify `uv sync` and the full suite.

## 9. Documentation

- [ ] 9.1 Update the README — prerequisites, the compose command, the project structure table, the retired network claim and the corpus ingestion step; verify every command in it runs as written on a clean clone.
- [ ] 9.2 Update `docs/known-limitations.md` — strike `M15` and `M3` as resolved with today's date, amend `M17` to record that the migration path now exists, and add a row for the suite's new Postgres dependency; verify the referenced identifiers and dates against the file's existing conventions.
- [ ] 9.3 Run `openspec validate add-postgres-data-layer --strict` and the full suite including the `ui` tier; verify both are clean before the change is considered done.
