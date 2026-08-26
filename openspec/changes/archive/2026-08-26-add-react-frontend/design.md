## Context

See `proposal.md` — Why. What shapes the approach:

- **The API is complete for this.** Plants, chat, care, profile, photographs, auth, runs and
  the event stream all exist and are tested. Four gaps close here, each found by asking what
  a screen needs; nothing else about the backend moves.
- **The event stream is the interesting part.** A run reports thirteen-odd steps, pauses
  mid-way for answers on the same connection, and replays from `Last-Event-ID` after a
  drop. All of that is built and none of it has ever been seen.
- **This is the first non-Python code here.** There is no `web/`, no `node_modules`, no
  second test runner, and no precedent for how any of it is arranged.
- **`M28` constrains the deployment to one process.** The frontend is served as static
  files, which does not change that.
- **`M31` records that keep-alive emission is untested.** A real browser holding a real
  stream is the first thing that will exercise it, which is worth knowing when the wizard
  behaves oddly on a slow run.

## Goals / Non-Goals

**Goals:**

- Everything an ordinary person can do, reachable in a browser without a bearer token.
- The reasoning panel: the agent working, visible, step by step.
- A wizard that survives a reload, a dropped tunnel and a closed laptop.
- Accessibility as a property of the components, not a pass over them afterwards.

**Non-Goals (design-level, beyond the proposal's):**

- **A design system.** shadcn/ui is copied-in components that this project then owns.
  Building an abstraction over them would be building a second one.
- **Type generation from OpenAPI.** Hand-written types for the dozen shapes this consumes.
  A generator is a build step, a dependency and a diff to review for a saving of an
  afternoon — and hand-written types are read by the person writing the screen.
- **Server-side rendering.** A signed-in application behind an API gains nothing from it and
  it would make the token story materially harder.

## Decisions

### `fetch` with a `ReadableStream`, not `EventSource`

`EventSource` cannot set an `Authorization` header. Every workaround puts the access token
in the query string, where it lands in the server's access log, the browser's history, and
the `Referer` of anything the page loads next — for a credential that is deliberately never
written to storage. So `useRunStream` reads the response body itself and parses the event
stream: about sixty lines, and `Last-Event-ID` on reconnect is a request header like any
other.

*Rejected:* a token in the query string; a cookie for the access token (it would need to be
readable by script or sent on every request, and the refresh cookie is httpOnly precisely to
avoid the first).

### One `useRunStream`, used by the wizard and by nothing else yet

The hook owns the connection, the reconnect, the deduplication on sequence, and the
translation from events to a list of steps. The wizard renders what it returns.

Deduplication belongs in the hook because the server's contract permits a duplicate across
a reconnect: subscribing happens before the replay, so the tail of the replay can arrive
twice. A component that assumed otherwise would render a step twice on exactly the reconnect
the mechanism exists to make invisible.

### The token lives in a module, not in React state and not in storage

A React context re-renders the tree on every refresh; storage is readable by any injected
script. It lives in a closure that the fetch wrapper reads, and the wrapper is the only
thing that touches it. Renewal is serialised there: several requests failing at once produce
one refresh, not several — and several refreshes would be several rotations, of which all
but one is a reused token and therefore the end of the session.

That serialisation is the subtlest thing in this change. It gets its own test.

### TanStack Query owns everything else

Server state is a cache with invalidation, which is what it is. The alternative — a store
that mirrors the server — is a second copy that can disagree, and every screen here is a
view of something the server owns.

### Roles: a column, a default, and one check

`users.role`, defaulting to the ordinary value, and one dependency that refuses the
evaluation route. Not a permission system, not groups, not a policy engine — two values and
one protected resource.

*Rejected:* an allowlist of administrative email addresses in settings, which was the
alternative offered. It keeps identity simpler but puts an access rule in a place nobody
looks when asking who can do what, and it cannot answer "what is this account allowed to
do?" from the account itself.

### A completed run records its plant

The `persist` node creates a plant when a run was not given one, and the run row never
recorded which. Fixing it in the worker rather than having the client search for a plant by
timestamp, which is what a client would otherwise have to do.

### Vitest and React Testing Library, with Playwright for four flows

Components and hooks against a mocked API. Playwright for registering and verifying, a
diagnosis through the interrupt, a reconnect mid-run, and a chat reply — the four things a
mock makes look easy and a browser does not.

Playwright runs against the real stack with scripted models. The rule that no test makes an
LLM call is unchanged and applies to the browser tests exactly as it applies to the rest.

### Severity carries a label, decided in one place

A `Severity` component, used everywhere a severity appears. The accessibility requirement is
then a property of a component with a test rather than a rule each screen has to remember.

## Risks / Trade-offs

- **The wizard is the hardest thing here to test and the most valuable to get right** →
  Playwright covers the interrupt and the reconnect specifically. The hook's deduplication
  and reconnect logic are unit-tested against a fabricated stream, because the sequence
  arithmetic is where an off-by-one hides.
- **Renewal storms** — several requests failing together, each triggering a refresh, all but
  one presenting a rotated token and ending the session → serialised in the fetch wrapper,
  with a test that fires several concurrent requests at an expired token and asserts one
  refresh.
- **A second toolchain in a Python repository** → `web/` is self-contained, with its own
  lockfile and scripts, and the README says how to run both. The risk is a contributor who
  runs `uv run pytest`, sees green, and has not run the frontend tests; the deployment
  change is where CI makes that impossible.
- **shadcn/ui is copied in, not depended on** → the components become this project's code
  and its maintenance. That is the trade it exists to make, and it is worth stating rather
  than discovering.
- **Diagnostic accuracy** → **this change must not move it.** It adds no prompt, no model
  call and no retrieval; it reads an API. The measurement is unchanged: the evaluation
  harness still calls the graph directly and its numbers should not move at all. If they do,
  something in this change reached somewhere it had no business being.

## Migration Plan

Additive. The API gains three endpoints and a column; nothing existing changes shape.

Order, which is also the order the risk retires:

1. The four API gaps, with tests — including the role and its migration. Done first so the
   frontend is never written against something that does not exist.
2. The application shell: toolchain, routing, the fetch wrapper and its renewal, the
   session.
3. Auth screens, end to end against the real API.
4. Plants: the grid, the detail screen, the roadmap, chat.
5. The wizard, which is the point.
6. The account screen and the evaluation screen.
7. Accessibility and dark mode passes over what exists, plus the Playwright flows.

**Rollback** is reverting the branch. Nothing is deployed, and the API changes are additive
enough to stand alone if the frontend were abandoned.

## Open Questions

- **Where the built frontend is served from.** By the API as static files, or separately
  with CORS already configured for it. It changes a deployment file and nothing in this
  change, and the deployment change is where there is somewhere to serve it from.
- **Whether the evaluation screen should be able to start a run of the harness.** It reads
  the newest result here. Starting one costs real money and takes minutes, which makes it a
  different kind of thing from a page that renders a file — and nothing needs it yet.
