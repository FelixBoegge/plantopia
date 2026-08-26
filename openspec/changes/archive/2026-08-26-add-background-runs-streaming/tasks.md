## 1. The run record

- [x] 1.1 Add `Run` and `RunEvent` models — owner, plant, kind, thread id, status, timestamps, error, resulting diagnosis; and per-run sequence, kind, payload, time; verify the schema test asserts the new table names, that every timestamp carries a timezone, and that a run's sequence is unique within its run rather than globally.
- [x] 1.2 Generate and apply the migration; verify `alembic upgrade head` on an empty database and `alembic check` reporting no drift.
- [x] 1.3 Add a status constraint permitting only the six statuses; verify a test that writing an invented status is refused by the database, not only by Python.
- [x] 1.4 Add `RunRepository`, owner-scoped like every other; verify a test that another owner's run is unreachable through every method, added to the repository tenancy table.
- [x] 1.5 Add settings for pool size, queue depth, the working ceiling, the answering ceiling and the keep-alive interval, with `.env.example` documentation; verify a test that each has a default and that the two ceilings are separately configurable.

## 2. Execution and the bus, without a graph behind them

- [x] 2.1 Add the `RunExecutor` port and a bounded thread-pool adapter; verify tests that work submitted is executed, that the pool does not exceed its size, and that a task raising does not kill the worker for the next one.
- [x] 2.2 Refuse submission when the queue is at its ceiling; verify a test that the refusal is distinguishable from an allowance and from the daily cap, since it is the only one that clears on its own.
- [x] 2.3 Add the event bus — publish to a run's subscribers, subscribe, unsubscribe; verify tests that two subscribers to one run both receive, that a subscriber to another run receives nothing, and that a subscriber that goes away does not block a publish.
- [x] 2.4 Make every status transition a conditional update on the current status; verify a test that two concurrent transitions from one status produce one winner and one caller that sees no rows changed.

## 3. Starting a run

- [x] 3.1 `POST /runs` creating a run for an owner's plant and queueing it; verify tests that the response is immediate, carries an identifier and a status, and carries no diagnosis.
- [x] 3.2 Refuse a run naming another owner's plant with 404 and create nothing; verify a test asserting both halves.
- [x] 3.3 Apply the quota guard and the daily cap before the run is created; verify tests that a refused run makes no model call, leaves no run record, and does not count towards the allowance that refused it.
- [x] 3.4 `GET /runs/{id}` and `GET /runs`; verify tests for the fields a run carries, for most-recent-first ordering, and for another owner's run answering 404 rather than 403.
- [x] 3.5 Run the diagnosis graph on the executor, advancing `queued` → `running` → `completed` and recording the diagnosis produced; verify a test driving a whole run with scripted models and asserting the terminal status and the diagnosis identifier.
- [x] 3.6 Record a failed run as `failed` with a description that exposes no internal detail; verify tests that a raising node produces `failed` and that neither an exception message nor a module name reaches the client.

## 4. Events

- [x] 4.1 Add the node-name mapping and assert it is total; verify a test enumerating every node in both graphs and failing on one without a description, plus a test that an unmapped node yields a neutral event rather than its own name.
- [x] 4.2 Persist each node update as a `run_events` row before publishing it; verify tests for sequence numbers increasing within a run, for two concurrent runs not interleaving, and that a row exists for every event a subscriber saw.
- [x] 4.3 `GET /runs/{id}/events` as SSE, replaying from the beginning then following live; verify a test that a client opening mid-run receives the earlier events before the later ones.
- [x] 4.4 Honour `Last-Event-ID`, delivering only events after it; verify tests for reconnecting mid-run and for reconnecting after the run finished, where the stream closes rather than waiting.
- [x] 4.5 Send keep-alive traffic on an idle stream; verify tests that it is sent within the configured interval and that it does not reach the client as an event.
- [x] 4.6 Deliver a terminal event for `completed`, `failed` and `cancelled`, then close; verify a test per status that the stream ends with a statement rather than a dropped connection.
- [x] 4.7 Refuse another owner's stream with 404 and deliver no events; verify a test asserting both.
- [x] 4.8 Keep blocking work off the event loop — replay reads in a threadpool, live delivery from the bus only; verify a test that the loop remains responsive to a second request while a long run streams.

## 5. The interrupt

- [x] 5.1 Flip a run to `awaiting_answers` on the interrupt and publish an event carrying the questions; verify a test that the status and the event both appear and that the run does not advance further.
- [x] 5.2 Release the pool slot at the interrupt rather than blocking a worker; verify a test that a second run can start while the first waits for answers, with a pool of one.
- [x] 5.3 `POST /runs/{id}/answers` resuming the run from its checkpoint; verify tests that the run returns to `running`, completes, and produces a diagnosis reflecting the answers rather than starting again.
- [x] 5.4 Keep the stream open across the pause; verify a test that one connection receives events from before and after the resume, with sequence numbers continuing rather than restarting.
- [x] 5.5 Refuse a second submission of answers with 409, and refuse answers to a run not awaiting them; verify a test per status that neither starts a second run nor disturbs the first.
- [x] 5.6 Refuse answers to another owner's run with 404 and leave it unaffected; verify a test asserting both.

## 6. Abandoning a run

- [x] 6.1 `DELETE /runs/{id}` setting a cancellation flag the worker checks between nodes; verify tests that a cancelled run stops advancing and that the step already in flight is allowed to finish.
- [x] 6.2 Refuse cancelling a run that has already reached a terminal status, with 409 and no status change; verify a test per terminal status.
- [x] 6.3 Add the sweeper failing runs past the working ceiling and, separately, past the answering ceiling; verify tests that each ceiling applies to its own status, that the answering one is measured from when the questions were asked, and that a run within its ceiling is left alone.
- [x] 6.4 Make the sweeper idempotent; verify a test that a run it has already failed is not failed twice and that usage already recorded is not recorded again.
- [x] 6.5 Distinguish a swept run's recorded reason from a run that failed while working; verify a test comparing the two.

## 7. Chat over the same shape

- [x] 7.1 Add the streaming chat endpoint delivering the reply progressively; verify tests that the reply arrives in more than one piece and that the transcript afterwards is indistinguishable from the single-request form's.
- [x] 7.2 Surface the agent's lookups as events before the reply continues; verify a test that consulting a source produces an event naming it in the product's language.
- [x] 7.3 Record the message and the completed reply even when the connection drops mid-reply; verify a test that disconnects part-way and then reads the transcript.
- [x] 7.4 Refuse a streaming request naming another owner's plant with 404, recording nothing; verify a test asserting both.
- [x] 7.5 Leave the single-request endpoint working unchanged; verify that its existing tests pass untouched and that the evaluation harness still calls it.

## 8. Spend, and closing the gaps

- [x] 8.1 Record tokens and cost when a run reaches any terminal status, including cancelled and swept; verify tests for completed, failed, cancelled and swept, and that a provider reporting no cost leaves unknown rather than zero.
- [x] 8.2 Delete `tests/unit/services/test_limits_are_not_wired_yet.py` and the note in `services/limits.py`; verify the suite is green with both gone and that the guard is genuinely called by a run.
- [x] 8.3 Confirm the evaluation harness still calls the graph directly rather than going through runs; verify a test asserting it, so the accuracy baseline cannot drift through this change.
- [x] 8.4 Strike `M29` as resolved with today's date, and record the in-process bus alongside `M28` as one constraint on the deployment rather than two; verify identifiers and dates against the file's conventions.
- [x] 8.5 Update the README: starting a diagnosis, watching it, answering it, and the one-process constraint; verify every command runs as written against a live server, including the interrupt and the resume.
- [x] 8.6 Run `openspec validate add-background-runs-streaming --strict`, the full suite, and ruff; verify all three are clean.
