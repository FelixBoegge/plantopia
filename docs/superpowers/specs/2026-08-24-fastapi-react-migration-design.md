# Capstone Design — FastAPI, React and Postgres

**Status:** awaiting review. Implementation plan not yet written, nothing implemented.

**Companion documents:** [`project_brief_capstone.md`](../../../project_brief_capstone.md) is the
assignment this is built against; [`project_brief_Sprint4.md`](../../../project_brief_Sprint4.md)
records the target the existing agent was built to satisfy.
[`docs/known-limitations.md`](../../known-limitations.md) supplies the constraints this migration
inherits and the three it closes as a side effect.

---

## 1. Scope

Plantopia becomes a multi-user web application. The agent does not change.

That second sentence is the load-bearing one. This is a **platform migration**, and every
behaviour difference it produces is a defect rather than a feature. The diagnosis graph, its
fourteen nodes, its prompts, its tools, the corpus and the evaluation harness all cross over
unmodified. What changes is everything around them: who can use the app, where its data lives,
how it is served, and what it looks like.

**In scope:**

| Area | Change |
|---|---|
| Backend | FastAPI over the existing `services/` layer, `backend/` at the repository root |
| Frontend | React + Vite + TypeScript + Tailwind/shadcn SPA, `frontend/` at the root, redesigned UI |
| Database | One Postgres: domain tables, the corpus in pgvector, both LangGraph checkpointers |
| Auth | Own email/password with argon2id, JWT access tokens, rotating refresh tokens, open self-registration with email verification and password reset |
| Runs | Diagnoses execute in the background with per-step progress streamed over SSE across the clarifying-question interrupt |
| Spend control | Per-user quotas, a global daily spend cap, per-IP rate limits on the cheap-to-hammer endpoints |
| Privacy | Cascading account deletion, full data export, explicit consent at signup |
| Delivery | Docker Compose for local, twelve-factor config, GitHub Actions CI |
| Removed | Streamlit, SQLite, Chroma, the `ui/` package and its test tier |

**Explicitly out of scope**, and why:

| Item | Disposition |
|---|---|
| Any change to diagnosis behaviour | The whole migration is verified against the premise that behaviour is constant. Changing it concurrently would destroy the only reference point available. |
| **The healthy-plant false-positive rate** | Observed in testing 2026-08-24: diagnoses skew toward finding a disorder on plants that are fine. The `is_healthy` guard exists at three layers — schema validator, diagnose prompt, `plan`/`recheck` handling — but **all 28 golden cases are disorder cases**, so the false-positive rate is structurally unmeasured. Deferred by explicit decision. The cheap check when it resumes: healthy-plant cases in the golden set, scored as an `is_healthy` metric of its own. |
| Vision-layer measurement (`M19`) | The other structurally unmeasured thing. Deferred with the agent-depth work. |
| Upload downscaling (`U3`) | Changes what the vision model sees, and nothing measures vision. Kept apart from the blob-store work deliberately — see §4.5. |
| Subscription billing | The `tier` column and `usage_events` are the seam. No payment provider, no plans, no checkout. |
| Photo retention policy | Needs a scheduler that nothing else needs. |
| S3 object storage | A second `BlobStore` adapter, later. The port ships now; the adapter does not. |
| Multi-replica deployment | The `RunExecutor` and event-bus ports allow it. One container is the target. |
| Chroma's image-search path | `supports_image_search` / `search_by_image` port across as no-ops, as they already are — no reachable multimodal embedder (`U2`). |

**Budget:** four weeks at 30–40h/week, so 120–160 hours. The estimate below totals ~155.
That is at the ceiling with no slack, and §11 names what gets cut first.

---

## 2. Sequencing

Risk-first strangler. `services/` is the seam that makes it work: `ui/` never touches `agent/`
or `data/` directly, so FastAPI becomes a *second* client of the same service layer and
Streamlit keeps running unchanged while the new stack grows beside it. Streamlit is deleted
last, when React has replaced it, and until then it is a free control: if a diagnosis behaves
oddly, run it through the old UI and find out whether the platform or the redesign did it.

| Week | Work | Hours |
|---|---|---|
| 1 | SSE-across-interrupt spike (throwaway). Data layer: SQLAlchemy 2.0, Alembic, Postgres, UUIDv7, tenancy, blob store, both checkpointers. pgvector retriever behind the parity gate (§9.3). | ~40 |
| 2 | FastAPI: routers, `current_user`, auth with verification and reset, quotas and the spend cap, run lifecycle, background executor, SSE, chat. | ~45 |
| 3 | React: scaffold, auth flows, plant grid, plant detail, the diagnose wizard with the live reasoning panel. | ~40 |
| 4 | Chat, learned-profile and account surfaces. Privacy features. Streamlit deleted. Containers, CI, deployment, README and showcase entry. | ~30 |

The week-1 spike comes first and is thrown away. Proving that LangGraph's `interrupt()` can be
resumed from a different request while a stream stays open is the highest-unknown piece of the
design, and discovering otherwise in week 3 would be expensive.

---

## 3. Repository layout

```
frontend/            React + Vite + TS + Tailwind/shadcn
backend/
  api/               FastAPI: routers, dependencies, schemas, auth      NEW
  services/          the boundary both clients call            gains user scoping
  agent/             graphs, nodes, prompts                          unchanged
  knowledge/         corpus, ingest, retrieval                  Chroma to pgvector
  data/              models, repositories, migrations          SQLite to Postgres
  core/              config, llm, guards, images, cost, tracing  gains blob store
  eval/              golden set, harness, metrics               unchanged
  ui/                Streamlit                              deleted in week 4
  tests/
docker-compose.yml   db + api + frontend
```

Moving Python under `backend/` stales the module paths in `docs/code-tour.md`. Accepted: the
tour is a record of the codebase as it was built, and it says so.

`langgraph.json` and `agent/studio.py` move with the package and keep working — Studio remains
the way to inspect a paused graph.

---

## 4. Data layer

### 4.1 Sync, not async

SQLAlchemy 2.0 with psycopg3, synchronous. The reflex with FastAPI is `async def` everywhere and
it would be wrong here: `agent/nodes/persist.py` writes through four repositories injected into
the graph via `Deps`, so async repositories mean async nodes, async tools, async services, and a
rewrite of the suite covering them. The codebase has three `async def`s in 8,000 lines. FastAPI
runs sync endpoints on a threadpool, per-request queries are sub-millisecond, and the one long
operation — a diagnosis — goes to a background worker regardless.

### 4.2 Tenancy is enforced in the repositories

Every repository method takes `user_id` as a required first parameter and every query filters on
it. Services pass it down from the authenticated request; routers never hand a raw path id to a
repository. The alternative — trusting each service method to scope correctly across eight
tables — makes one forgotten `WHERE` a cross-tenant leak. A required parameter turns that class
of bug into a `TypeError` before the app starts.

`user_id` lives on `plants`, `user_profile` and `messages`. The other tables reach a user through
their parent, and `ON DELETE CASCADE` already chains from `plants`, which is what makes account
deletion nearly free. `user_profile`'s `UNIQUE(fact)` becomes `UNIQUE(user_id, fact)` — otherwise
no two users can ever learn the same thing.

### 4.3 Schema

New tables: `users`, `refresh_tokens`, `email_tokens`, `usage_events`, `runs`, `run_events`,
`blobs`, `corpus_chunks`. Existing tables port across with UUIDv7 primary keys, real `timestamptz`
columns in place of hand-parsed TEXT, and the tenancy columns above. `M3`'s inert
`PARSE_DECLTYPES` line disappears with the sqlite3 driver.

UUIDv7 rather than bigint: `/plants/3` tells a stranger how many plants exist and invites them to
try `/plants/4`. Time-ordered UUIDs keep insert locality, so index behaviour stays close to a
bigint's, and the cost — a pass over every repository and fixture — is being paid anyway.

Alembic from the first migration, generated from typed `Mapped[]` models. This is the project's
first migration path, whose absence `M17` records as the reason chat token tracking was never
added.

**No data migration.** Fresh database; the corpus is re-ingested. Local dev data is dev data.

### 4.4 Retrieval on pgvector

A hand-written `PgVectorRetriever` implementing the existing `Retriever` Protocol — `search`,
`sections_for`, `known_doc_ids`, `supports_image_search`, `search_by_image`. Roughly 120 lines of
SQL over `corpus_chunks (doc_id, section, content, embedding vector(1536), metadata)`.

Not `langchain-postgres`: the 89.3% top-1 rides on `sections_for`, which fetches by document id
with no ranking involved — the entire point of `hypothesise`. A wrapper would put a schema I do
not control between me and the one query that matters.

**No HNSW index.** 43 documents hold 301 sections; an exact cosine scan over ~300 rows is
sub-millisecond
and *deterministic*, where HNSW is approximate by design and can reorder results on its own. Any
difference between old and new retrieval is then my SQL rather than the index — which is exactly
what the parity gate in §9.3 needs to isolate. Revisit if the corpus grows by an order of
magnitude.

**Vectors are exported from Chroma, not recomputed.** Chroma stores the embeddings; they move
across as the same 1536-dimension floats from the same model. Zero API cost, and it makes parity
exact rather than statistical.

### 4.5 Blobs

A `BlobStore` port — `put(user_id, data, content_type) -> key`, `get(key) -> bytes`,
`delete_for_user(user_id)`. One adapter now: Postgres `blobs`, keyed by UUID, owned by a user.
S3 is a later adapter, not a later rewrite.

Graph state carries **keys, not bytes**. That closes `M15` — today `ImageRef.data_b64` puts whole
images in state and LangGraph re-serialises state at every superstep, producing ~100 MB of
checkpoint blobs per diagnosis — and it is forced by multi-user anyway.

Downscaling (`U3`) is deliberately **not** bundled with this. It changes what the vision model
sees, and since evaluation is blind to vision (`M19`), nothing would detect the damage if it did
any. Full-size bytes continue to reach the model.

### 4.6 Checkpointers

Both graphs move to `langgraph-checkpoint-postgres`. Thread ids gain a user prefix:
`{user_id}:diagnose:{...}` and `{user_id}:chat:{plant_id}`. Today a thread id is
`recheck-{plant_id}-{n}` — on a multi-user system that is a resumable handle to another user's
paid run. Every resume path verifies ownership before touching state, and the prefix is what
makes checkpoint rows deletable per user in §8.

---

## 5. API and auth

### 5.1 Surface

REST + JSON under `/api/v1`; photographs as `multipart/form-data` on upload. Six groups:

| Group | Endpoints |
|---|---|
| `auth` | register, verify-email, login, refresh, logout, password-reset request/confirm, me, delete me, export me |
| `plants` | list, create, get, patch, delete |
| `runs` | start diagnosis, start recheck, stream events, submit answers, get run, cancel |
| `chat` | list messages, send message (streamed) |
| `care` | patch roadmap step, post feedback |
| `profile` | list learned facts, forget one |

Plus `photos/{key}`, `me/usage`, `admin/evaluation`, and health/readiness probes.

### 5.2 Tokens

Access JWT at 15 minutes, held **in memory** by the SPA and never in `localStorage`. Refresh
token at 30 days in an `httpOnly; Secure; SameSite=Strict` cookie, stored server-side as a hash
with a family id, rotated on every use, with **reuse detection**: presenting an already-rotated
token kills the family, because that pattern means it was stolen.

Passwords are argon2id. Verification and reset tokens are single-use, hashed at rest, expiring at
24h and 1h. Login and reset responses are generic so neither enumerates registered addresses.

`localStorage` is the common shape and it hands the session to any XSS on the page. In-memory
plus an httpOnly refresh cookie costs one silent-refresh interceptor in the frontend.

### 5.3 Tenancy at the edge

One `current_user` dependency resolves the token. A resource belonging to another user returns
**404, never 403** — 403 confirms the row exists.

### 5.4 Quotas and the spend cap

`usage_events` records tokens and cost per **run**. Before a run starts, a `QuotaGuard` checks the
user's monthly run count against their tier and the day's global spend against a ceiling. Either
refuses with 429 carrying a structured reason the UI renders properly — "20 of 20 diagnoses used,
resets on the 1st" — rather than a bare error. `users.tier` has one value today, `free`; it is the
seam subscriptions plug into without a migration.

Recording usage per run rather than per diagnosis closes `M18`: a run that spends real money and
produces no differential currently records nothing at all, and quotas cannot be honest if failed
runs are invisible.

Per-IP rate limits on register, login and password reset; per-user limits on run starts.

### 5.5 Errors

RFC 9457 problem details throughout — one shape, machine-readable `type`, safe to render. The
existing prompt-injection reporting from `core/guards.py` rides the same channel.

---

## 6. Runs, background execution and the interrupt

### 6.1 A run is a resource

`runs`: id, user, plant, kind (`diagnosis` | `recheck`), thread_id, status, timestamps, error,
resulting diagnosis. Status is the contract:
`queued` → `running` → `awaiting_answers` → `running` → `completed`, or `failed` / `cancelled`.
The frontend reads a status; it never infers one.

### 6.2 Execution

A bounded `ThreadPoolExecutor` inside the API process, behind a `RunExecutor` port. Not Celery,
not arq, not Redis: those are a second service and a second deploy target for a workload that is
a handful of concurrent, IO-bound HTTP calls. Everything durable is in Postgres — checkpoint, run
row, events — so a crash loses the in-flight step and the run resumes from its checkpoint.
Swapping the port for a real worker later is configuration.

### 6.3 Events are persisted, then published

`stream(stream_mode="updates")` emits a per-node update; each becomes a `run_events` row with a
sequence number *and* goes to an in-process bus. `GET /runs/{id}/events` replays persisted events
after `Last-Event-ID`, then subscribes live. Reload-during-diagnosis, flaky wifi and reconnect are
then correct by construction, which matters because the user has already paid and waited for that
run. A heartbeat comment every 15 seconds keeps proxies from closing an idle stream.

Node names never reach the client raw. One module maps `identify_plant` to "Identifying the
species", so internal structure is not part of the public API.

### 6.4 The interrupt is a status

The graph hits `interrupt()`, the run flips to `awaiting_answers`, an event carries the questions.
`POST /runs/{id}/answers` checks ownership and status, then resumes with `Command(resume=...)` on
the worker. The stream never closes: the client renders the form mid-stream and the same
connection continues. A second submission against a resumed run is 409, not a duplicate run.

### 6.5 Cancellation and timeouts

`DELETE /runs/{id}` sets a flag the worker checks between nodes, so an abandoned tab stops burning
the reasoning tier. A sweeper fails runs that exceed a wall-clock ceiling.

Chat uses the same bus and the same SSE shape, with tool calls surfaced as events rather than
appearing after a silence.

---

## 7. Frontend

**Routing:** `/login`, `/register`, `/verify-email`, `/reset-password`; `/` plant grid;
`/plants/:id` detail with history, roadmap and chat; `/plants/:id/diagnose` wizard; `/account`
for learned facts, export, deletion and the consent record; `/admin/evaluation` behind a role
check — that page reads a harness file and means nothing to a logged-in stranger.

**Server state is TanStack Query.** Every screen is a cache of something the server owns. The only
genuinely client-side state is the access token and the wizard's in-progress form. No Redux.

**`EventSource` cannot send an `Authorization` header.** The usual workaround puts the token in the
query string, where it lands in every access log. Instead `useRunStream` uses `fetch` with a
`ReadableStream` reader — header auth intact, `Last-Event-ID` on reconnect, about sixty lines.

**The redesign.** Tailwind + shadcn/ui, light and dark. The wizard is the centrepiece: upload,
clarifying questions, **a live reasoning panel** showing the agent working step by step, then the
differential. That panel is the best thing this project has to show and Streamlit's spinner has
been hiding it. The differential becomes ranked cards with confidence, evidence for and against,
and the five-minute confirming test; the roadmap a dated checklist; chat keeps per-reply source
chips.

**Accessibility:** severity carries a text label as well as colour — today's coloured badges fail
for a colourblind user. Focus management through the wizard, `aria-live` on the streaming panel,
full keyboard paths.

---

## 8. Privacy

Three features, each with a test that proves it rather than a claim that asserts it.

**Consent at signup.** Plain language: what is stored, that photographs and text are sent to models
routed through OpenRouter, and that the system infers durable facts about the person. Recorded as
`consent_version` and a timestamp on the user row, so what someone agreed to is provable.

**Export.** `GET /me/export` returns a ZIP of JSON plus original photographs, generated in-request
behind a size guard. Test: a round-trip that finds every plant, diagnosis, message and learned fact.

**Deletion.** `DELETE /me` behind password re-entry and a typed confirmation. Cascades through
plants, diagnoses, messages, learned facts, blobs **and checkpoint rows** — the last of which only
works because thread ids carry the user prefix from §4.6. Test: zero rows across every table
afterwards, including checkpoints.

The learned-profile page keeps its per-fact forget button and gains provenance for each fact.

---

## 9. Testing

### 9.1 What ports

Tests over `agent/`, `core/`, `tools/` and `services/` cross largely untouched — those layers do
not change shape. Repository tests move to Postgres, retriever tests to pgvector, and the `ui`
tier is deleted with Streamlit.

### 9.2 What is new

**Tenancy tests, table-driven over the router list**: for every route taking a resource id, user B
gets 404 for user A's row. Written once, and it fails the day someone adds an endpoint that
forgets to scope. This is the most valuable new test in the suite.

Endpoint tests per router; auth tests covering rotation, reuse detection, expiry and the generic
responses; quota tests covering refusal and reset; Vitest and React Testing Library with MSW on
the frontend; Playwright on exactly two journeys — register/verify/login, and
upload/questions/differential.

Postgres comes from `docker compose up -d db` (`pgvector/pgvector:pg17`), schema per session, each
test in a transaction that rolls back. This retires the suite's "no network calls" claim, which is
the honest trade: a local socket to a container is not what that claim was protecting against, and
mocked repositories testing themselves would be worse. **LLM calls stay banned absolutely.**
Coverage gate stays at 85%; the `ui/*` omissions leave with Streamlit and `api/*` is covered.

### 9.3 The retrieval parity gate — cost: zero

The pgvector rewrite is the one change that could quietly move the diagnostic accuracy. It ships
behind a snapshot test rather than an evaluation run:

1. Capture every golden case's retrieval queries **and their embedding vectors** from the current
   Chroma path, once, and commit them as fixtures.
2. Feed identical vectors through both retrievers.
3. Assert identical document ids, sections and ordering — for `search` *and* for the
   `sections_for` fetch-by-id path that `hypothesise` depends on.

No API calls, so it runs in CI. It is stricter than comparing an accuracy figure, and it fails on
the specific thing that can break rather than on a number that moves for six reasons.

The 2026-08-19 report — top-1 89.3%, top-3 96.4%, 28 cases, `overwaterer` profile — remains the
committed baseline; re-running it to reproduce a number already on disk would be waste. One
end-state harness run is optional, for a fresh figure in the README and showcase entry, at roughly
$1.50 and only on request.

---

## 10. Config, containers, CI

`pydantic-settings`, twelve-factor, extended with `DATABASE_URL`, `JWT_SECRET`, the mail provider
block, `CORS_ORIGINS`, quota limits and the global daily spend cap. `.env.example` documents each
the way it already documents the model tiers.

Compose brings up `db`, `api` and `frontend`. Multi-stage Dockerfiles, `alembic upgrade head` on
API start, corpus ingestion as a one-shot command. Nothing platform-specific: the hosting decision
is deferred until deployment.

GitHub Actions: ruff check and format, pytest against a Postgres service container with the
coverage gate, frontend typecheck plus Vitest plus a production build, Playwright on pull requests.
The evaluation harness never runs in CI — it costs money and needs real keys.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| **The budget has no slack** (~155h estimated against 120–160 available) | Cut list in order: second Playwright journey; redesign ambition on My Plants and the account page, reverting to a parity port; admin evaluation route dropped from the app; export without photographs. The wizard, auth, quotas and the privacy features are not on the list. |
| **A redesign removes the reference point** for telling platform bugs from design changes | The API contract stays behaviour-identical and is covered by tests; Streamlit survives until React reaches parity and can be run against the same services. |
| **pgvector retrieval silently degrades accuracy** | §9.3's parity gate, plus exported vectors and exact search so nothing is approximate. |
| **SSE across a LangGraph interrupt does not work as designed** | Week-1 throwaway spike, before anything depends on it. |
| **Open registration exposes the API key** | Per-user quotas, a global daily spend cap, per-IP limits on the cheap endpoints, email verification. |
| **The rubric grades LLM engineering, and this sprint adds none** | The existing agent work is retained and demonstrated: agentic RAG, LangGraph, observability, the evaluation harness. The migration adds multi-user, privacy and spend-control engineering on top. Worth stating plainly in the README rather than hoping a reviewer infers it. |

---

## 12. Decisions log

| Decision | Rationale |
|---|---|
| Sync SQLAlchemy, not async | Repositories are injected into graph nodes; async would cascade through nodes, tools, services and their tests for no gain on IO-bound work |
| Repositories require `user_id` | Turns a cross-tenant leak into a `TypeError` |
| UUIDv7 primary keys | Ends id enumeration on a public API; the rewrite pays the cost anyway |
| Hand-written pgvector retriever | The 89.3% rides on fetch-by-id; no wrapper schema between me and that query |
| No HNSW index | ~300 chunks; exact search is deterministic, which the parity gate needs |
| Threadpool executor, not Celery | One container, IO-bound work, durable state already in Postgres |
| Events persisted then published | Makes reconnect and reload correct by construction on a run the user paid for |
| Access token in memory, refresh in httpOnly cookie | `localStorage` hands the session to any XSS |
| 404 rather than 403 on another user's row | 403 confirms existence |
| Postgres `bytea` behind a `BlobStore` port | S3 later as an adapter swap, not a rewrite |
| Keys in graph state, but no downscaling | Closes `M15`; avoids changing what the vision model sees while vision is unmeasured |
| Retrieval parity by snapshot, not by eval run | Zero cost, stricter, and fails on the specific thing that can break |
| Streamlit deleted last | It is a free control client for behaviour differences until React replaces it |

---

## 13. Open follow-ups (not blocking this migration)

- **The healthy-plant false-positive rate** (§1). Healthy cases in the golden set, scored as an
  `is_healthy` metric. Deferred by decision, not by oversight.
- **Vision-layer measurement** (`M19`) — the other structurally unmeasured thing.
- **Chat context growth and chat token tracking** (`M16`, `M17`). Alembic removes the reason
  `M17` was carried.
- **Upload downscaling** (`U3`) — after vision is measurable.
- **Empty differentials** (`U9`) — a run that returns no candidates at all.
- **S3 blob adapter**, subscription tiers, multi-replica deployment. Seams exist; features do not.
