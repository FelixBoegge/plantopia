## Context

See `proposal.md` — Why. What shapes the approach is that almost all the data is already
fetched and thrown away.

`web/src/screens/plants/PlantDetail.tsx` is 144 lines, a single scrolling column with no tabs:
a header, "What Plantopia thinks" (the latest diagnosis's reasoning), `<Roadmap>`, `<Chat>`,
`<PlantSettings>`. It destructures `{ plant, diagnoses, roadmap_steps }` from `usePlant` —
**`observations` is fetched on every load and never rendered.**

What the layers actually carry, which is not the same at each level:

| | model row | repository record | API shape | client type |
|---|---|---|---|---|
| `captured_at` | yes | **no** | **no** | **no** |
| `latitude`/`longitude` | yes | **no** | **no** | **no** |
| `weather` | yes | yes | **no** | **no** |

So the weather is on `ObservationRecord` and `api/converters.py:observation()` drops it on the
floor; the capture date and position stop one layer earlier, at the record. Three layers to
widen, not one.

Ordering differs per repository and none of it is timeline order: observations come oldest
first, diagnoses newest first, roadmap steps by their diagnosis's date descending then ordinal
ascending.

Messages are **not** in `PlantDetailOut`. They come from `GET /plants/{id}/messages` through
`useTranscript(plantId)`, which `<Chat>` already calls. `_extract_tool_calls` stores every tool
call of a turn as `{name, args, result}` with the result truncated at 500 characters and the
args whole — so a `suggest_new_diagnosis` call keeps its `reason` intact.

Photographs are not plain URLs. `<img src>` cannot send an `Authorization` header, so
`usePhoto` fetches `/api/v1/photos/{key}` with the bearer token and wraps the blob in
`URL.createObjectURL`, revoking on unmount. `<Photo photoKey>` is the only path to an image.

There is **no charting library** — 12 runtime dependencies, none of them for drawing — and no
hand-authored SVG anywhere in `web/src`. `web/src/accessibility.test.tsx` runs axe over every
route as a failure, so whatever is drawn is checked.

## Goals / Non-Goals

**Goals:**

- One sequence answering "is this getting better?" from data already stored.
- Ordered and dated by when things happened to the plant.
- Weather visible where it explains a diagnosis.
- A history that predates all of it still reads.

**Non-Goals:**

- **A new endpoint.** Everything needed is already served by two calls the page makes anyway.
- **Feedback events.** `data/repositories/feedback.py` has no read method at all, deliberately
  — speculative reads were removed from it once already. Adding one to draw a dot is how that
  file got trimmed in the first place.
- **Editing, annotating or deleting history.** Deletion belongs to `add-privacy-controls`.
- **Cross-plant comparison.**
- **The forecast.** A stored series carries seven days ahead of the *run*, which is history by
  the time anybody reads the timeline. Drawing it would be drawing a prediction that has
  already been overtaken.

## Decisions

### Built on the client from what the page already fetches

The timeline is a merge of four sources: observations, diagnoses, roadmap steps and the
escalations inside chat messages. Three arrive in `usePlant`; the fourth in `useTranscript`,
which `<Chat>` on the same page already calls, so TanStack Query serves both from one request.

A server-side aggregate would mean a new endpoint whose only consumer is one screen, a new
response shape to keep in agreement with the client, and a fifth thing for
`test_client_types.py` to check. The merge is a sort over data already in memory.

The cost is that the page now depends on the transcript loading before the timeline is
complete. The timeline renders without it and gains escalation events when it arrives, which is
the same progressive behaviour `<Chat>` already has.

### A section on the plant page, not a route of its own

It goes between "What Plantopia thinks" and `<Roadmap>`: after the current verdict, before the
plan that follows from it, which is the order the page already reads in.

A `/plants/:id/history` route would mean a second page load for the thing most people want
immediately after the verdict, and would split a short page in two for no reason other than
tidiness.

### Dated by capture, ordered by the same

Each event carries one instant. For an observation that is its capture date where it has one
and its upload otherwise — the same fallback the wizard's date field already uses, and the same
reasoning: the two differ for anybody who does not upload immediately.

Diagnoses and roadmap steps have no equivalent ambiguity; a diagnosis happened when it was
made. A step is placed by its completion where it has one and by its due date otherwise, so a
plan that has not been carried out reads as pending future work rather than as history.

### The weather chart is hand-drawn SVG

Roughly 21 days of minimum, maximum and precipitation. That is two line paths and a row of
bars — under a hundred lines of arithmetic and a `viewBox`.

Adding a charting library for it would add a large dependency to a project with twelve, for one
chart, and would bring its own colour and accessibility decisions into a codebase that has
made those decisions deliberately elsewhere.

**It cannot be colour alone.** `openspec/specs/web-client/spec.md` already requires that colour
is never the only carrier of meaning and that every path is reachable from the keyboard, and
axe runs over this route. So the series is also rendered as a table — visually hidden, actually
present — and the chart carries a text summary naming the range and the notable days. The table
is the accessible representation; the chart is the fast one.

### Widening three layers rather than reaching around them

`ObservationRecord` gains `captured_at`, `latitude` and `longitude`; `observation()` stops
dropping `weather`; `ObservationOut` and the client `Observation` gain the capture date and the
series.

The alternative — reading the weather off the diagnosis, which already exposes it — would work
for exactly the observations that produced a diagnosis and fail for a re-check whose run was
cancelled. The observation is where the weather was recorded and where a timeline's spine is.

Position is added to the record and the API for completeness with the capture date, and is
**not drawn**. A coarse pair of coordinates is not something to show somebody who has already
told you where the plant is; it is there because leaving one of three sibling fields behind is
how the next person discovers it missing.

### An unknown is absent, never a default

Most existing observations predate all three columns: of the seven in the development
database, five have a capture date and one has weather. So the common case in any real history
is a partial one.

An event renders from what it holds. No zero temperature, no epoch date, no "unknown" chip
where a field simply was not captured — the timeline says less rather than saying something
untrue, which is the same rule `species_method: null` follows on a diagnosis.

## Risks / Trade-offs

- **This is the largest new surface on a frontend that has never been designed** (`U11`) →
  built from the existing component vocabulary, tests locating by role and label so a restyle
  survives them, and no bespoke visual language beyond the one chart that genuinely needs one.
- **A hand-drawn chart is code nobody else maintains** → it is small, it has one caller, and
  the accessible table beside it means a rendering bug degrades to a readable table rather than
  to nothing.
- **Two queries instead of one** → both are already made by this page; the timeline adds no
  request.
- **Escalations are read out of stored tool calls** rather than a column, so a change to how
  tool calls are recorded would silently drop them → a test asserts an escalation is found in a
  stored message, and the tool name is already shared with `services/chat_events.TOOL_NAMES`,
  which has its own agreement test.
- **A long history is a long page** → observations are bounded by how often somebody
  photographs a plant, and nothing here paginates. If it ever matters, the newest are the ones
  that matter and the rest can collapse.

## Migration Plan

Additive. No schema change at all — every column this reads already exists.

Order, which is also the order the risk retires:

1. The three layers widen, and the existing agreement tests confirm both sides match. Nothing
   renders differently.
2. The event merge and its ordering, as a pure function over the four sources, tested without
   a browser.
3. The section, from the existing components.
4. The chart and its accessible table.

**Rollback** is removing the section: the widened fields are additive everywhere and nothing
else depends on them.

## Open Questions

- **Whether a roadmap step that was skipped should read differently from one never done.**
  Both are "not completed", and the record distinguishes them, but whether that difference is
  worth a visual distinction is a question about what an owner does with it — worth deciding
  against a real history rather than in advance.
- **Whether the timeline should collapse beyond some number of events.** Deferred until there
  is a plant with enough history to make the page unpleasant; guessing the threshold now would
  be guessing.
