## Context

See `proposal.md` — Why. Requirements are in `specs/http-api`.

What the previous change left in place, and which this one is shaped by:

- **`services/` is already the boundary.** `ui/` never touches `agent/` or `data/`
  directly. An HTTP layer is a second caller, not a new architecture.
- **Services carry their owner.** `PlantService(user_id=…)`, `DiagnosisService.user_id`.
  A request has to produce an owner and build services around it.
- **Repositories refuse another owner already**, returning `None` on reads and raising
  `RecordNotFoundError` on writes. The HTTP layer maps those, and must not weaken them.
- **The data layer is synchronous.** Repositories are injected into LangGraph nodes.
- **Streamlit stays.** It is the control client for the whole migration.

## Goals / Non-Goals

**Goals:**

- Every existing owner-facing capability reachable over HTTP, with no behaviour change.
- Owner resolution isolated to one function, so the next change edits one thing.
- Failures that a client can branch on and that leak nothing.

**Non-Goals:**

- Performance. One process, a handful of users, no caching layer.
- A stable public contract. This interface has one consumer, being written next; the
  version prefix exists so that changing it later is possible, not because it is frozen.
- Anything the frontend needs that the services do not already provide. If a screen turns
  out to need something new, that is a service-layer change with its own reasoning.

## Decisions

### Sync handlers, not async

`def` rather than `async def` throughout. FastAPI runs sync endpoints in a threadpool.

*Alternative rejected: async handlers.* The data layer is synchronous by an explicit
decision recorded in the previous change — repositories are injected into graph nodes, so
making them async cascades through nodes, tools, services and their tests. Async handlers
over a sync data layer would mean either blocking the event loop or wrapping every call in
`run_in_threadpool` by hand, which is what FastAPI already does for a sync handler.

### One request, one session, one set of services

A dependency opens a session per request, builds the services around the resolved owner,
and closes it when the response is done. Services are not cached across requests.

*Alternative rejected: process-wide cached services, as `ui/bootstrap.py` does.* That
works for Streamlit because there is one owner and one session. Here a cached service
would pin an owner into a process serving many, which is the failure this whole migration
exists to prevent — and it would share one SQLAlchemy session across concurrent requests,
which is not safe.

### Owner resolution is one function with one implementation

```python
def current_owner(session: Session = Depends(...)) -> UUID:
    return default_owner_id(session)
```

Every handler depends on it. The next change replaces the body with a token check and
edits nothing else.

*Alternative rejected: a header naming the owner.* It would make the tenancy tests more
convincing — two owners in one test run — but it is an authentication bypass with a
comment promising it will be removed. The tenancy tests reach the second owner through the
service layer instead, which tests the same property without shipping the hole.

**Consequence, recorded because it is a real gap:** with one resolvable owner, no HTTP
request in this change can be made *as* a second owner. Endpoint tenancy is therefore
tested by constructing the router's dependencies with a second owner directly, rather than
by issuing a request. The full end-to-end version arrives with authentication, and the
tasks say so.

### Errors: RFC 9457, mapped in one place

Three handlers, registered on the app: `RecordNotFoundError` → 404, `ValueError` from a
service → 400, everything else → 500 with the detail logged and not returned.

*Alternative rejected: try/except in each handler.* Twenty handlers, twenty chances for
one to return a bare string or leak an exception message. A handler that lets
`RecordNotFoundError` escape is doing the right thing.

**404 is asserted, not assumed.** The spec forbids 403, so the tenancy test asserts the
status code rather than just the absence of data — a handler that caught the repository's
refusal and re-raised it as "forbidden" would otherwise pass a data-only check while
telling a stranger the record exists.

### Response schemas are written, not inferred

Pydantic response models per endpoint, distinct from the repository record dataclasses.

*Alternative rejected: returning the dataclasses.* They are storage shapes. Returning them
directly makes every column a public field, so removing one becomes a breaking change to
clients, and a column added for internal reasons is published by accident.

### Readiness runs a query; liveness does not

`/health` returns immediately. `/ready` executes `SELECT 1`.

The distinction is the point: an orchestrator restarting a container that is merely waiting
for its database turns a slow start into a crash loop.

### Chat stays a single request

`POST /plants/{id}/messages` runs the agent and returns the reply — ten to thirty seconds.

Streaming belongs with the change that introduces background runs and SSE, and it will
change this endpoint's *response mode* rather than replace the handler. That is why chat is
here and diagnosis is not: diagnosis needs a run resource, a background executor and an
event stream before it means anything, while chat is a request that already has an answer.

## Risks / Trade-offs

- **A handler reaches past the services into a repository**, and tenancy or a transaction
  boundary is enforced in two places → routers may depend only on services. The one
  exception is photograph serving, which needs the blob store directly; it takes the owner
  the same way and is called out in the tasks so it is not read as precedent.
- **Endpoint tenancy is tested below HTTP**, because only one owner can be resolved → an
  honest partial: the mapping from a repository refusal to a 404 is tested at the handler,
  and the end-to-end version lands with authentication. Recorded rather than glossed.
- **Response schemas drift from what the frontend needs** → the frontend is being written
  next, by the same person, against these endpoints. Discovering a missing field is a
  normal iteration, not a failure of this change.
- **Two processes in development** where there was one → the README gains a second command.
  Streamlit continues to work with the API stopped, which keeps the control client honest.
- **`/ready` becomes a way to make the database do work** → it is one `SELECT 1`, and
  nothing here is exposed publicly yet. Worth revisiting when there is an ingress.

## Migration Plan

Additive. Nothing existing changes, so there is nothing to migrate and nothing to roll
back beyond reverting the branch. Streamlit is unaffected at every commit — which is the
check to run when in doubt: if the wizard stops working, this change broke something it
had no business touching.

Order: application factory and error handlers, then dependencies, then routers in
increasing order of what they touch — plants, care actions, profile, photographs, chat —
then the tenancy test across all of them.

## Open Questions

- **Pagination.** No endpoint paginates. One owner has tens of plants and hundreds of
  messages, so it costs nothing today; the shape of the answer will be clearer once the
  frontend exists and it is known which list actually grows.
- **Whether `/photos/{key}` should redirect to object storage** once an S3 adapter exists,
  rather than proxying bytes through the application. Nothing decides that now, and the
  `BlobStore` port is what keeps the option open.
