## Why

The project has five gates and no machine runs any of them. Passing depends on a person
remembering five commands in two toolchains, and `M33` records what that costs: the React work
landed with three defects the Python suite could not have seen and the component suite did not
— a startup that revoked its own session, every clarifying question rendered as an unlabelled
text box, and a plant created by a run that never appeared on the grid.

`uv run pytest` is green whatever the state of `web/`. Nothing in the Python gate compiles
TypeScript, runs Vitest, or opens a browser. The three cross-language agreement tests close
part of that hole and cannot close the rest, because they check shapes rather than behaviour.

Everything needed is already true: the suites make **no** model calls and need **no** API keys
— an absolute constraint the project already holds itself to — so the only thing standing
between the gates and a machine running them is that nobody has written it down.

## What Changes

- **Every push and pull request runs all five gates**: ruff, the Python suite against a real
  PostgreSQL with pgvector, the frontend typecheck and unit suite, a production frontend
  build, and Playwright.
- **The gates are the same commands a developer runs**, not a parallel set that can drift.
- **No secret is required to run them.** A fork's pull request gets the same verification as a
  branch, and a leaked workflow file reveals nothing.
- **The evaluation harness never runs.** It costs real money and needs live keys; the standing
  instruction is to keep that spend low.
- **`M33` is closed**, and the README stops saying a contributor has to remember two suites.

## Capabilities

### New Capabilities

- `continuous-integration`: what must be verified before a change is trusted, that the
  verification matches what a developer runs, and what it may and may not require.

### Modified Capabilities

None. This adds no behaviour to the running system.

## Impact

**Not in scope, deliberately**

- **Containers.** No Dockerfile, no application service in compose. The design specifies them
  and this defers them: they are how the project is *deployed*, and deployment is a decision
  for after the review rather than before it.
- **Deploying anywhere.** A running instance means a public URL, real keys and real spend, and
  the hosting decision stays open (`openspec/config.yaml`: "hosting decided at deploy time").
- **Anything `M28` forbids.** That row records three things depending on this being one
  process — the rate limiter, the run executor pool and the event bus — and says a deployment
  change must not scale horizontally without replacing them. Nothing here scales anything.

**What this will need from the workflow**

- Both toolchains in one job for the browser tests: `web/playwright.config.ts` starts the API
  and the frontend itself, so Python, Node and Chromium have to be present together.
- `web/src/` present when pytest runs, because three Python tests read TypeScript source.
- A PostgreSQL the test harness can create and drop databases in, with the `vector` extension
  — `tests/postgres.py` creates `plantopia_test` and `tests/e2e/server.py` creates
  `plantopia_e2e`.

**Two things this change should say out loud rather than fix quietly**

- **The capstone brief requires a showcase link in the README** and there is none. Uploading
  the project to `showcase.turingcollege.com` is something only its owner can do, so this
  records the requirement and leaves the doing.
- **The README's own limitations section still says "Single user, no authentication"**, which
  three changes have since contradicted. A deployment-facing document that is wrong about
  whether the thing has accounts is worth correcting while here.
