## Context

See `proposal.md` — Why. What shapes the approach:

- **The graph's generator ends at the interrupt.** A spike run before this proposal streamed
  a full diagnosis: pass one emits six updates (`guard_input` … `select_questions`) and
  then `__interrupt__`, and the generator stops. Resuming with `Command(resume=...)`
  produces a *second* generator that emits seven more and finishes. The resume works from a
  different thread than the one that started the run.
- **The data layer is synchronous**, and stays so. FastAPI's handlers are sync and run in a
  threadpool. SSE, however, is naturally an async generator.
- **`services/limits.check` and `UsageRepository.record` exist, are tested, and are called
  by nothing.** `M29` records that. This change is what makes it false.
- **Checkpointing is Postgres-backed** and already keyed by thread id, with owner-prefixed
  thread ids from the auth change.
- **There is no frontend.** Nothing renders any of this until the next change but one.

## Goals / Non-Goals

**Goals:**

- A run that survives a reload, a dropped connection, and the pause for clarifying answers.
- One event shape, used by both runs and chat, so the frontend learns it once.
- An executor boundary that a real worker can be dropped behind without touching a handler.
- Diagnosis reachable again, having been unreachable since Streamlit was retired.

**Non-Goals (design-level, beyond the proposal's):**

- **Horizontal scale.** The bus is in-process. Two API processes would each see only their
  own runs' events, so a client connected to process B watching a run on process A sees
  nothing. This design is for one process, and says so out loud rather than discovering it
  in a deployment.
- **Exactly-once event delivery.** Events are persisted then published; a client may see one
  twice across a reconnect and is expected to deduplicate on sequence number.
- **Making the graph itself async.** The nodes are synchronous and stay so.

## Decisions

### The SSE handler subscribes to a bus; it never iterates the graph

**This is the load-bearing decision, and the spike is why.** The obvious implementation —
`async for update in graph.stream(...)` piped to the response — closes the connection at the
interrupt, because that is where the generator ends. The client would then reconnect to a
run it has already paid half of.

So the worker owns both generators and publishes each update; the handler owns the
connection and subscribes. The pause is invisible to the connection: it is simply a gap
between two publishes. `run-streaming`'s "the stream survives the pause" and `runs`'s
"the interrupt is a status" are the same decision seen from two sides, not two decisions
that happen to agree.

*Rejected:* streaming the generator directly, and reconnecting after the interrupt. It is
less code and it makes every client handle a run as two halves — including the retry logic,
the progress indicator and the error states.

### Events are written before they are published

A `run_events` row with a per-run sequence number, then the in-process bus. Not the other
way round: publish-then-persist means a client that receives an event the database does not
have, and a reconnect that replays a shorter history than the one already rendered.

The sequence number is per run and assigned under the run's row, not a global counter — two
concurrent runs must not interleave sequence numbers, and a global sequence would make the
replay query a scan.

*Rejected:* PostgreSQL `LISTEN`/`NOTIFY` as the bus. It would survive multiple processes,
which is a real advantage, but it needs a dedicated connection per subscriber and its
payload is capped at 8000 bytes, so events would have to be re-fetched by id anyway. The
port makes it a later substitution, and `M28` already records that this deployment is one
process.

### A bounded thread pool behind a `RunExecutor` port

The workload is a handful of concurrent, IO-bound HTTP calls. Everything durable is in
Postgres — run row, events, checkpoint — so a crash loses the in-flight step and the run
resumes from its checkpoint.

*Rejected:* Celery, arq, or any Redis-backed queue. A second service, a second deploy
target and a second failure mode, for a workload that fits in a pool. The port is the hedge:
swapping it is configuration, and the sweeper below is what makes a crashed process
recoverable in the meantime.

### The pool's size and the queue's depth are both bounded, and a full queue is a refusal

An unbounded queue turns a burst into a pile of runs that each take minutes and each hold a
checkpoint. The queue has a ceiling, and a run that cannot be queued is refused at the door
with its own problem type — distinguishable from the allowance and from the daily cap,
because it is the only one of the three that will clear on its own in a minute.

### The interrupt resumes as a second submission to the pool, not a blocked worker

A worker that waits inside the graph for an answer holds a pool slot for however long a
person takes to read their email. Pass one ends at the interrupt and the slot is released;
answering submits pass two. This is why `awaiting_answers` is a real status rather than a
label on a blocked thread, and it is what the spike's cross-thread resume confirms is safe.

### Cancellation is cooperative, checked between nodes

`DELETE /runs/{id}` sets a flag; the worker checks it before starting each node. A step
already in flight finishes — killing a thread mid-HTTP-call leaks the connection and can
leave a half-written checkpoint.

The consequence is honest and specified: cancelling during a slow reasoning call still pays
for that call. Recorded, because "cancel" implying "stop paying" is the reasonable
assumption and it is wrong here.

### Two ceilings, because waiting for a person is not the same as being stuck

A run `running` for longer than the working ceiling is a process that died. A run
`awaiting_answers` for longer than the answering ceiling is somebody who closed the tab.
One number for both would either reap live conversations or leave dead runs for hours. The
sweeper runs on a schedule inside the process, and is idempotent: a run it has already
failed is not failed twice, and usage already recorded is not recorded again.

### Node names are mapped, and the map is total

Thirteen nodes across a full diagnosis, plus the interrupt. A mapping module turns each into
a stable event kind and a sentence. A node with no entry produces a neutral event rather
than falling back to its own name — a fallback that leaks the internal name is a fallback
that leaks it exactly when somebody added a node and forgot the map, which is the only time
it matters.

A test asserts the map covers every node in both graphs, so adding a node without a
description fails rather than shipping.

### Chat streams over the same shape, and the synchronous endpoint stays

One event vocabulary for the frontend to learn. The existing `POST` remains because the
evaluation harness and every non-interactive caller want a reply, not fragments — and
because deleting a working endpoint to prove a point about consistency is how a migration
acquires an outage.

Chat streams token deltas as well as tool-call events, which runs do not: a chat reply is
prose being written, where a run is a sequence of steps.

### Runs are created before they are queued, and their status starts as `queued`

The row exists before the work is submitted, so a client that receives an identifier can
always fetch something. `queued` is a real state — a full pool means it is where a run
genuinely sits — and not a fiction to fill the gap before `running`.

## Risks / Trade-offs

- **The bus is in-process** → Two API processes and a client sees an empty stream for a run
  that is progressing. Mitigated by the port and by recording it as a known limitation
  alongside `M28`, which constrains the deployment the same way for the same reason. The
  deployment change must not scale this horizontally without substituting the bus.
- **A restart loses in-flight runs** → The sweeper fails them within the ceiling rather than
  leaving them `running` forever, and the checkpoint means a resubmitted run does not
  restart from the first photograph. What is lost is the current step.
- **Cancelling does not stop the current model call** → Specified and recorded rather than
  hidden. The alternative, killing the thread, trades a small overspend for a leaked
  connection and a corrupt checkpoint.
- **Two writers to one run row** — the worker advancing status, and a request cancelling or
  answering → Every transition is a conditional update on the current status, so the loser
  of a race sees zero rows changed and answers 409. Not a read-then-write, which is the
  version of this that passes tests and fails in production.
- **SSE through an async handler over a sync data layer** → The handler must not do
  blocking database work on the event loop. Replay reads happen in a threadpool; live
  delivery reads from the bus only. A test asserts the event loop is not blocked during a
  long run.
- **Diagnostic accuracy** → **This change must not move it.** The graph, its nodes, its
  prompts and its models are untouched; only what observes them changes. The measurement is
  that the evaluation harness runs unchanged and is not rewired to go through runs — it
  keeps calling the graph directly, so a change in its numbers would mean this change
  touched something it should not have. Any deliberate move to accuracy belongs to a
  different change, with a baseline.

## Migration Plan

Additive throughout. No existing endpoint changes behaviour, and the schema gains two
tables.

Order, which is also the order the risk retires:

1. The `runs` and `run_events` tables and their migration.
2. The executor port, its thread-pool adapter, and the bus — tested without a graph behind
   them, because a scheduling bug and a graph bug are hard to tell apart once combined.
3. Starting a run, its statuses, and the quota guard at the door.
4. Events: persist, publish, replay, keep-alive.
5. The interrupt: pause, questions, answer, resume — the part the spike de-risked.
6. Cancellation and the sweeper.
7. Chat over the same shape.
8. Usage recording at every terminal status, closing `M29`.

**Rollback** is reverting the branch. Nothing is deployed and there are no runs to strand.

## Open Questions

- **Whether the sweeper belongs inside the API process.** It is a scheduled task in a
  process that also serves requests, which is fine for one process and wrong for several —
  each would sweep. It does not change the specs, the endpoints, or the tasks, and the
  deployment change is where a second process first becomes possible. Decided there.
- **Whether a completed run's events should be pruned.** They are small and bounded by the
  node count, so nothing forces the question now. `M16` already records unbounded checkpoint
  growth for chat threads; if a retention policy is written, both belong in it.
