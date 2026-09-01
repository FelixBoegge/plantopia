## Context

See `proposal.md` — Why. The measurements are what shaped this, and they contradicted the
obvious guess.

`services/chat_service.send` invokes the agent with a *single* message and a `thread_id`:
`agent.invoke({"messages": [{"role": "user", "content": content}]}, config)`. The accumulated
history lives in LangGraph's checkpoint, and the agent replays it. So there is nothing in the
service to trim — the growth is inside the checkpointed state, which is where any fix belongs.

What one turn adds, measured against this repository's own data rather than estimated:

| Source | Measured | Tokens |
|---|---|---|
| Web search | 4 passages, 5,262 chars (`tests/fixtures/tavily_care_calathea.json`) | **~1,315** |
| Weather block | ~1,000 chars typical, 1,628 worst case | ~250–400 |
| Knowledge lookup | 4 passages × 295 chars average of 301 corpus chunks | ~295 |
| The exchange itself | question, tool call, reply | ~200 |

**Tool output is roughly six times the conversation**, and web search — the largest — is the
common path: the system prompt sends the agent there for general care, watering, siting,
propagation, varieties, seasons and edibles.

`langchain 1.3.14`'s `create_agent` takes a `middleware` list, and two of the shipped
middlewares match this exactly:

- `ContextEditingMiddleware(edits=[ClearToolUsesEdit(...)])` — drops old tool output past a
  token trigger, keeps the last *n* results, replaces the rest with a placeholder. No model
  call.
- `SummarizationMiddleware(model, trigger=..., keep=...)` — replaces older messages with a
  summary. One model call whenever it fires.

## Goals / Non-Goals

**Goals:**

- A bound that does not depend on the number of turns.
- The cheap measure first, because it removes most of the weight for nothing.
- Nothing a person said lost without a summary standing in for it.
- The stored transcript untouched.

**Non-Goals:**

- **Tracking chat token usage** (`M17`). Adjacent and separate; this change is verified by
  counting what reaches the model, which needs no new storage.
- **Pruning checkpoint rows.** The rows are small — what was expensive was replaying them.
- **Touching the diagnosis graph.** Each run is its own thread with a bounded set of nodes and
  no accumulating conversation.
- **A cleverer summary prompt than the one shipped.** Tuning a summariser against conversations
  nobody has had yet would be guessing.

## Decisions

### Two mechanisms, layered, cheap one first

`ClearToolUsesEdit` fires at the lower threshold. It costs nothing, and by the measurements it
removes about six-sevenths of the weight — the part that is bulk rather than meaning. A
web-search result from twenty turns ago is not what the current question is about.

`SummarizationMiddleware` fires at a higher one, and only matters if the *conversation* has
grown large on its own. At roughly 200 tokens a turn that takes hundreds of exchanges, so in
practice it is a backstop rather than a working part.

**Why include the backstop at all, when the measurements say the first mechanism suffices?**
Because without it there is still no bound, and the thing being fixed is unboundedness. Tool
clearing bounds the tool output; only summarisation bounds the text. Two configured middlewares
is not meaningfully more complexity than one, and "it will not matter for hundreds of turns" is
the kind of reasoning that ages badly in a system somebody else maintains.

### The thresholds are configuration, and their defaults are argued

The trigger for clearing tool output is set well below the model's context window rather than
at it. Waiting until the window is nearly full would mean paying for every one of those tokens
on every turn until the moment it fires, which is the cost this exists to avoid — the point is
not to avoid an error, it is to avoid the bill.

Both thresholds are settings, because the right value depends on the model behind the agent
and that is a deployment decision.

### The summariser runs on the cheap tier

Summarising is a mechanical extraction, not a judgement about a plant. `build_gate_model` is
what this project already uses for that class of work — the two binary image checks — and the
reasoning tier's prices for a condensation nobody reads would be paying for nothing.

### Recent tool results are kept, and the count is small

`keep` governs how many recent tool results survive. Small, because the value is concentrated
in the latest: the agent is answering the question in front of it, and the results it fetched
for that question are the ones it needs whole.

### Nothing is written back to the transcript

The middlewares act on the messages passed to the model. `messages` rows are written by
`chat_service` before and after the agent runs and are never rewritten, so the transcript, the
export and the timeline's escalation events are all unaffected by construction rather than by
care.

This is worth a test rather than an assertion: a change that started editing stored history
would be invisible until somebody scrolled back, and `add-privacy-controls` promised an export
of what was actually said.

## Risks / Trade-offs

- **A summary loses nuance.** Mitigated by firing late, keeping recent turns verbatim, and
  running only when tool clearing was not enough. The alternative — forgetting silently — is
  worse.
- **A model call inside a chat turn adds latency** when summarisation fires. It fires rarely
  by construction, and on the cheap tier.
- **Thresholds are guesses until somebody has a long conversation.** They are configuration,
  and the numbers behind the defaults are written down here rather than folklore.
- **`M17` still means nobody sees the saving.** Recorded rather than fixed; the test measures
  what reaches the model, which is the same property from the other side.
- **The middlewares are framework behaviour this project does not own.** A version bump could
  change how they trim. The tests assert on the property — what reaches the model — rather than
  on the middleware's internals, so an upgrade that changed the mechanism but kept the
  behaviour would pass, and one that broke the behaviour would fail.

## Migration Plan

Additive and reversible. Two settings, two middlewares passed to `create_agent`, and no schema
change. Existing conversations are unaffected: the middlewares act on what is read, so a
conversation that predates them is simply condensed the first time it exceeds a threshold.

**Rollback** is removing the middleware list. Nothing stored changes shape.

## Open Questions

- **Whether the placeholder left in place of cleared tool output should name the tool.**
  `[cleared]` says something was there; `[weather lookup cleared]` says what. The second is
  more useful to a model reasoning about what it already knows, and is more tokens for
  something the model can usually infer. Worth deciding against a real long conversation.
- **Whether summarisation should be told what the plant is.** The agent's system prompt carries
  the plant and its latest diagnosis; the summariser's does not, so it condenses without
  knowing what the conversation is about. Probably fine for extraction, and testable only
  against conversations long enough to trigger it.
