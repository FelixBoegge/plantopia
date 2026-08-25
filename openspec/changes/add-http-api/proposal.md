## Why

Everything Plantopia knows is reachable only by running Streamlit. There is no way for a
browser, a script, or the React frontend this migration is heading towards to read a plant
or mark a roadmap step — the service layer is a Python API and nothing else.

That is the whole obstacle. `services/` was already built as the boundary the UI calls, so
the work is not to invent an interface but to expose the one that exists: a second client
of the same services, alongside Streamlit rather than instead of it. Until this lands, the
frontend cannot begin, and neither can anything that wants to automate against Plantopia.

The previous change made this possible rather than merely desirable. Every repository
method now takes an owner, so an HTTP handler has something real to scope a request to —
before it, an endpoint would have had no way to answer "whose plant is this?".

## What Changes

- **A FastAPI application under `/api/v1`**, mounted alongside the Streamlit app rather
  than replacing it. Both call the same services; neither knows about the other.
- **Read and write endpoints for everything a plant owner already has**: their plants,
  one plant's full detail, its chat transcript and sending a message, marking a roadmap
  step, submitting feedback on a diagnosis, listing and forgetting learned facts, and
  fetching a photograph by key.
- **A `current_owner` dependency** that resolves to the seeded owner. It is the single
  seam authentication replaces, and it exists as a dependency now precisely so that the
  next change edits one function rather than every handler.
- **Tenancy at the edge, restated in HTTP terms.** A resource belonging to somebody else
  returns **404, never 403** — the repositories already refuse it; this change makes sure
  the status code does not undo that by confirming the resource exists.
- **RFC 9457 problem details as the single error shape.** One structure, a
  machine-readable `type`, and no stack traces or database messages reaching a client.
- **Health and readiness probes**, distinguished: alive is not the same as able to serve,
  and a deployment that cannot tell them apart restarts a container that is merely waiting
  for its database.
- **CORS configured from settings**, because the frontend will not share an origin.
- **A table-driven endpoint tenancy test**, mirroring the repository one that already
  exists: every route taking a resource identifier, asked once as its owner and once as
  somebody else.

**Explicitly out of scope:**

- *Authentication, registration, tokens, quotas, the spend cap and email* — the next
  change. This one has a seeded owner and one seam to replace.
- *Diagnosis and re-check endpoints.* They belong with the change that makes runs
  background and streams their progress, because the alternative is a handler that blocks
  for ninety seconds and then gets deleted. Streamlit keeps the wizard until then, which
  it can, because it is still a first-class client.
- *Multipart upload handling.* Dropped from this change's scope during planning: the only
  thing that uploads a photograph is starting a diagnosis, and that is out of scope, so an
  upload endpoint here would have no caller. Photographs are *served*, not received.
- *Any change to what the services do.* This change adds a caller. A behavioural
  difference visible through Streamlit would be a defect.
- *A frontend.* Nothing in this change renders anything.

## Capabilities

### New Capabilities

- `http-api`: how Plantopia is reached over HTTP — the resource surface, how a request is
  attributed to an owner, what a failure looks like, and what a client may rely on
  remaining stable.

### Modified Capabilities

None. `data-persistence`, `photo-storage` and `run-checkpointing` describe how records are
stored and isolated, and this change adds a caller rather than changing any of it. The
tenancy rule they state is the rule this change is obliged to preserve at a new boundary,
which is a reason to test it here, not a reason to restate it.

## Impact

**Code.** A new `api/` package: application factory, routers, dependencies, request and
response schemas, and the error handlers. `core/config.py` gains CORS origins and the API
root path. `services/` is untouched — if a handler cannot do its job through the existing
service methods, that is a finding worth surfacing rather than a reason to reach past
them.

**Dependencies.** `fastapi` and `uvicorn`. `python-multipart` is deliberately *not* added,
since nothing here receives an upload.

**Tests.** A new endpoint tier using FastAPI's `TestClient` against the real database, on
the same fixtures the repository tests use. No LLM calls: the one endpoint that would make
one — sending a chat message — is tested with the scripted model the rest of the suite
already uses.

**Operations.** A second process to run in development (`uvicorn api.main:app --reload`)
and a second service in Compose later. Streamlit is unaffected and keeps working.

**Risk.** Low, and deliberately so. Nothing existing changes behaviour; the new surface is
additive and the seeded owner means no security decision is being made yet. The one real
risk is a handler that scopes incorrectly, which is what the table-driven tenancy test
exists to catch — and it is written to fail if a scope is removed, the same way the
repository one was verified.
