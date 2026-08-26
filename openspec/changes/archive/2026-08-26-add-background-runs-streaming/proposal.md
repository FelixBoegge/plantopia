## Why

**Diagnosis is currently unreachable.** It is the thing this project does, and since
Streamlit was retired nothing but the evaluation harness can start one — there is no
endpoint. That was deliberate: a synchronous endpoint would block for ninety seconds and
would have been written to be deleted. This is the change that was waiting.

Ninety seconds is also why a run cannot be a request. A client that holds a connection that
long has no way to say what is happening, a reload loses a run the owner has already paid
for, and the graph pauses partway through to ask clarifying questions — which a
request/response endpoint can only express as a failure and a second call.

The spend guard built with the auth change is complete, tested, and calls nothing, because
there was no run to guard. This is where it gets wired in.

## What Changes

- **A run becomes a resource.** `runs` records who started it, for which plant, its kind,
  its thread, its status and what it produced. Status is the contract the client reads:
  `queued` → `running` → `awaiting_answers` → `running` → `completed`, or `failed` /
  `cancelled`. The client reads a status; it never infers one from silence.
- **Runs execute in the background**, on a bounded pool behind a `RunExecutor` port. Not
  Celery, not Redis: a second service and a second deploy target for a handful of
  concurrent IO-bound calls. Everything durable is already in Postgres.
- **Every node update becomes a persisted event**, then goes to an in-process bus.
  `GET /runs/{id}/events` replays from `Last-Event-ID` and then follows live, so a reload
  or flaky connection resumes a run rather than losing it.
- **The interrupt becomes a status, not an error.** The graph pauses, the run flips to
  `awaiting_answers`, an event carries the questions, and `POST /runs/{id}/answers`
  resumes it. The client's connection stays open across the pause.
- **Node names never reach a client raw.** One module maps `identify_plant` to
  "Identifying the species", so the graph's internal structure is not part of the public
  interface and renaming a node is not a breaking change.
- **A run can be cancelled**, and one that overruns a wall-clock ceiling is failed by a
  sweeper rather than left `running` forever.
- **Chat streams over the same shape.** `POST /plants/{id}/messages` gains a streaming
  sibling carrying tool calls as they happen, so a lookup is visible rather than being a
  silence. **BREAKING** for nothing yet: the synchronous endpoint stays, because the
  evaluation harness and the API tests use it and no client has been written against
  either.
- **The quota guard and usage recording are wired in.** Every run checks the daily cap and
  the owner's allowance before any model call, and records what it spent on the way out —
  including when it fails after spending.

Explicitly **not** in scope:

- **A worker process.** The port exists so that swapping one in is configuration. Building
  it now would be a deployment story for a load nobody has measured.
- **Rendering any of this.** The React frontend is the next change; here the interface is
  the OpenAPI page and the tests.
- **Recheck as a separate flow.** It is the same graph on a different entry point and
  rides along as a run `kind`, not as a second mechanism.

## Capabilities

### New Capabilities

- `runs`: what a run is, how it is started, what statuses it moves through, how it is
  answered, cancelled, and reaped, and what a client may rely on not changing.
- `run-streaming`: the event stream — ordering, replay after a dropped connection, what an
  event may say, and the guarantee that a client never has to infer progress from silence.

### Modified Capabilities

- `http-api`: the chat requirement currently states that streaming a reply "is deliberately
  not part of this requirement". That stops being true.
- `usage-limits`: the requirement that a run is refused before any model call currently
  describes behaviour nothing performs. This change makes it describe something real, and
  adds what happens to a run refused before it starts.

## Impact

**Code.** New: `data/models.Run` and `RunEvent` with a migration; `services/runs.py`;
`api/routers/runs.py`; a `RunExecutor` port with a thread-pool adapter; an event bus; the
node-name mapping; a sweeper. Modified: `agent/wiring.py` (a graph built per run rather
than per process), `api/dependencies.py`, `services/chat_service.py` for the streaming
path.

**Interface.** Five new endpoints under `/api/v1/runs`, plus a streaming chat endpoint.
Existing endpoints are untouched.

**Operational.** The bus and the pool live in the API process, so the deployment runs one
process until the executor port is given a real worker — the same constraint `M28` already
records for rate limiting, and it should be recorded once for both rather than twice.

**Dependencies.** `sse-starlette` for the event stream. Nothing else.

**Risk.** The spike run before this proposal confirmed that the graph's own generator
*ends* at the interrupt: a handler that streams `graph.stream(...)` straight to the
response closes the connection mid-diagnosis. The bus indirection is what makes "the stream
never closes" true, and the design records that as one decision rather than two independent
ones.
