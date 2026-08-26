## Why

**Nobody can use any of this.** Streamlit was retired when the seeded owner it resolved
through became real accounts, and the two changes since have added an authenticated API,
background runs and a live event stream that no human being can reach. The interface today
is an OpenAPI page and a `curl` command with a bearer token in it.

It is also the wrong interface for the thing this project is best at. A diagnosis takes
ninety seconds, pauses to ask questions, and reports each step as it happens — and
Streamlit showed a spinner for all of it. The reasoning panel is the most interesting
artefact here and it has never been visible to anyone.

Three smaller things are only reachable from a frontend and are therefore here: a person
cannot see what the system has learned about them, cannot tell how much of their monthly
allowance is left, and cannot find the plant a diagnosis just created.

## What Changes

- **A React application** at `web/`: Vite, TypeScript, Tailwind and shadcn/ui, light and
  dark. Routes for `/login`, `/register`, `/verify-email`, `/reset-password`, the plant
  grid at `/`, `/plants/:id`, the wizard at `/plants/:id/diagnose` and `/diagnose`, and
  `/account`.
- **The diagnosis wizard**, which is the centrepiece: upload, a live reasoning panel that
  shows the agent working step by step, the clarifying questions rendered mid-stream on the
  same connection, and then the differential as ranked cards carrying confidence, evidence
  for and against, and the five-minute confirming test.
- **Server state is TanStack Query.** Every screen is a cache of something the server owns.
  The only genuinely client-side state is the access token and the wizard's in-progress
  form.
- **`useRunStream` reads the event stream with `fetch` and a `ReadableStream`**, not
  `EventSource`. `EventSource` cannot send an `Authorization` header, and the usual
  workaround puts the access token in the query string, where it lands in every access log
  and every browser history.
- **Roles exist.** `/admin/evaluation` renders the harness's newest result, and that page
  means nothing to a stranger and something to whoever runs the project. The identity spec
  currently says there is one kind of person; this change makes that false deliberately
  rather than by accident. **BREAKING** for nothing deployed: a column with a default.
- **Four API gaps close**, each found by asking what a screen needs:
  - `GET /me` — who is signed in, their role and tier, and how much of the allowance is
    left. Without it a client cannot render an account page, gate the admin route, or warn
    somebody before a run is refused.
  - **A completed run names the plant it created.** A run started without a plant makes one
    in its `persist` node, and the run row never recorded which — so a client is handed a
    `diagnosis_id` and no way to navigate to the thing it just paid for.
  - `GET /diagnoses/{id}` — the wizard's result screen, reachable directly so a link to a
    diagnosis works.
  - `GET /evaluation/latest` — what the admin page reads, replacing the Streamlit page that
    read the file off disk.
- **Accessibility is part of the work, not after it.** Severity carries a text label as
  well as a colour, because today's coloured badges alone fail for a colourblind reader.
  Focus moves deliberately through the wizard, the streaming panel is `aria-live`, and
  every path is reachable from the keyboard.

Explicitly **not** in scope:

- **Data export and account deletion.** They are `add-privacy-controls`, and the account
  page leaves room for them rather than pretending.
- **The features in §14** — identification, image metadata, granular weather, care profiles,
  the timeline. Each is its own change and each will add to screens this one establishes.
- **Server-side rendering, a mobile app, offline support.** None is asked for and each is a
  second architecture.

## Capabilities

### New Capabilities

- `web-client`: what a person can do in a browser — the routes, what each screen shows, how
  a session is held and refreshed, what happens when a request is refused, and the
  accessibility guarantees that are part of the contract rather than a nicety.
- `diagnosis-wizard`: the flow that starts a run, shows it working, asks its questions
  mid-stream, and presents the result — including what happens when the connection drops
  part-way through work somebody has already paid for.

### Modified Capabilities

- `identity`: a person now has a role, and one route is refused to most people. The current
  requirement says the opposite in as many words.
- `http-api`: `GET /me`, `GET /diagnoses/{id}` and `GET /evaluation/latest` are added, and
  the last is the first endpoint whose answer depends on who is asking beyond ownership.
- `runs`: a completed run names the plant it created, not only the diagnosis.

## Impact

**New.** A `web/` directory with its own toolchain, dependency set and test runner —
the first non-Python code in this repository, and the first thing here with a `node_modules`.

**Modified.** `data/models.User` gains `role` with a migration; `identity` grows an
authorisation check distinct from authentication; `api/routers/` gains three endpoints;
`runs/worker.py` records the plant a run created.

**Testing.** Vitest and React Testing Library against a mocked API for components and
hooks; Playwright for a handful of flows against the real stack — registering, a diagnosis
through the interrupt and out the other side, and a chat reply. The backend's rule holds
unchanged: no test makes an LLM call, so Playwright runs against scripted models.

**Risk.** The wizard is the piece most likely to be wrong and the hardest to test, because
what makes it good — a connection held open across a pause, reconnecting without losing
work — is exactly what a mocked fetch makes look easy. That is why Playwright is here and
not deferred.
