## Why

A plant's conversation replays in full on every turn, and nothing prunes it. The README has
recorded this since the chat agent shipped: *"Chat context grows without bound. Every turn
replays the whole conversation to the model, and checkpoints are never pruned."*

Measuring it says where the weight actually is, and it is not where a reader would guess:

| What a turn adds | Tokens, roughly |
|---|---|
| A web-search result | **~1,315** |
| A weather block | ~250 |
| A knowledge-base lookup | ~295 |
| Everything a person and the agent actually *said* | ~200 |

**Tool output is the bulk, by six to one.** And web search is the common path rather than the
rare one — the system prompt directs the agent there for general care, watering, siting,
propagation, varieties, seasons and edibles, which is most of what somebody asks.

The cost compounds: turn *N* pays for turns 1..*N*. Forty turns is roughly 1.2 million prompt
tokens billed across the conversation and about 60,000 on the last turn alone — half the
context window, with latency to match, for a conversation about one plant.

Nobody would notice, either. `M17` records that chat token usage is not tracked at all.

## What Changes

- **Stale tool results stop being replayed.** Past a threshold, older tool output is dropped
  from what the model sees and replaced with a marker; the most recent results stay whole.
- **The conversation itself is condensed** past a much higher threshold, so a very long one is
  bounded rather than merely lighter.
- **What a person said is never silently discarded** — condensing replaces old turns with a
  summary of them, and recent turns are always kept verbatim.
- **The stored transcript is untouched.** Only what is sent to the model changes. A person can
  still scroll back and read every word, and the escalations the timeline reads still resolve.

## Capabilities

### New Capabilities

- `chat-context`: how much of a conversation reaches the model, what may be dropped from it,
  and what must survive.

### Modified Capabilities

None. The behaviour a person sees is unchanged — the transcript, the announcements and the
record on each reply all stay as they are.

## Impact

**Two mechanisms, in order of cost**

The measurements argue for doing the cheap thing first: dropping stale tool output costs
nothing and removes six-sevenths of the weight. Summarising costs a model call each time it
fires, and can lose nuance, so it is the backstop rather than the first line.

Both exist in the agent framework already (`ContextEditingMiddleware` with `ClearToolUsesEdit`,
and `SummarizationMiddleware`), so this is configuration and its justification rather than new
machinery.

**Deliberately not in scope**

- **Tracking chat token usage** (`M17`). It is how somebody would *see* this working, and it is
  a separate change — this one is verified by counting what reaches the model in a test, which
  needs no new storage.
- **Pruning checkpoint rows.** The rows are small; what was expensive was replaying them.
  Deleting history is `add-privacy-controls`' business, and it already does it per account.
- **Touching the diagnosis graph.** It has no accumulating conversation — each run is its own
  thread with a bounded set of nodes.
