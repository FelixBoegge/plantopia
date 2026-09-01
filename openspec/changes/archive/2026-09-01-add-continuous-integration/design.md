## Context

See `proposal.md` — Why. The shape of this is decided almost entirely by facts already in the
repository.

**There is no CI of any kind.** No `.github/` directory. The only awareness of it anywhere is
`web/playwright.config.ts:35`, which already picks a `github` reporter when `CI` is set — so
somebody anticipated this and it never arrived.

**The suites need a database and nothing else.** `tests/postgres.py` connects to the `postgres`
maintenance database, drops and creates `plantopia_test`, runs `CREATE EXTENSION IF NOT EXISTS
vector`, and builds the schema with `Base.metadata.create_all` — not Alembic. So the role needs
`CREATEDB` and enough rights to create an extension, which the `pgvector/pgvector:pg17` image's
superuser has. `tests/e2e/server.py` does the same for `plantopia_e2e`, except that it *does*
run Alembic, which makes the browser suite the only place the migrations are exercised.

**No test needs a key or the network.** `tests/conftest.py` sets a fake key and a test secret
autouse; models come from `tests/fakes/`, embeddings are hashing, HTTP is mocked with `respx`,
and `tests/e2e/server.py` patches every outbound service and blanks the Pl@ntNet and Tavily
keys explicitly. The README states the constraint as absolute. This is what makes a
secret-free workflow possible rather than aspirational.

**Playwright starts its own servers**, both of them: `uv run python -m tests.e2e.server` on
8100 and Vite on 5273. So the browser job needs Python, Node, Chromium and Postgres present at
once — it cannot be split.

**Three Python tests read TypeScript source** (`test_client_types.py`,
`test_source_names_agree.py`, `test_question_shape_agrees.py`), so `web/src/` must exist when
pytest runs. A checkout gives that for free; it is worth knowing before somebody "optimises"
the Python job by not checking out the frontend.

**The frontend has no lint or typecheck script.** `npm run build` is `tsc -b && vite build`,
so the typecheck and the production build are the same command — which is convenient and worth
stating, because "we typecheck in CI" would otherwise look unimplemented.

**The Node version is unpinned**: no `engines`, no `.nvmrc`, no `volta`. Vite 8, Vitest 4 and
TypeScript 7 imply a modern Node and nothing declares it.

## Goals / Non-Goals

**Goals:**

- Every gate runs on every push, without anybody remembering to.
- The same commands as local, so the two cannot disagree.
- No secret, so a fork's pull request is verified identically.

**Non-Goals:**

- **Containers and deployment.** Deferred by decision: the review comes first, and the hosting
  question stays open.
- **Publishing anything** — no image, no artefact, no release.
- **Running the evaluation harness.** It bills.
- **Coverage reporting as a service.** The gate is already `--cov-fail-under=85` inside
  `pytest`; sending the number somewhere is a different feature.
- **Caching every possible thing.** Correctness first; a slow honest pipeline beats a fast one
  that reuses a stale environment.

## Decisions

### Three jobs, split by what they need rather than by what they are

- **lint** — ruff only. Seconds, no database, no Node. Fails fastest on the most common
  mistake.
- **python** — the Python suite against a Postgres service container. Needs the database and
  the frontend source, not Node.
- **browser** — Playwright. Needs everything: Python, Node, Chromium, Postgres.

The frontend typecheck, unit suite and production build ride in the **browser** job rather
than getting a fourth. They need Node, which that job already has, and `npm ci` is the
expensive part — paying for it twice to make a diagram tidier is not a trade worth making. It
also means the browser tests never run against a frontend that failed its own unit tests.

### The gates run the documented commands, unchanged

`uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, `npm run build`,
`npm test`, `npx playwright test`. No extra flags, no reimplemented thresholds.

The coverage floor is in `pyproject.toml`'s `addopts`, so `uv run pytest` enforces it without
CI restating it. If somebody moves the floor, the machine moves with it — which is the point:
a second copy in a workflow file is a second thing to forget.

The one deliberate addition is `ruff format --check`, because `ruff format` rewrites files and
a machine that silently reformatted and then passed would be reporting on code nobody wrote.

### The database is a service container, published on 5433

`tests/postgres.py` reads `Settings().database_url`, whose default is
`postgresql+psycopg://plantopia:plantopia@localhost:5433/plantopia` — chosen to match
`docker-compose.yml`, with 5433 rather than 5432 because of Windows port contention.

CI could set `PLANTOPIA_DATABASE_URL` instead, and deliberately does not: publishing the
service on 5433 with the same credentials means the environment a workflow provides is the
environment the README describes. One fewer way for local and CI to be different.

Credentials in a workflow file would normally be a smell. These are the ones already committed
in `docker-compose.yml` and `.env.example` for a throwaway container that exists for the
length of one run.

### Pinning what the repository already pins, and only that

Python comes from `.python-version` (3.12), which `uv` reads. Node has nothing to read, so the
workflow states a version — and that choice is recorded here as the one thing CI knows that
the repository does not, which is a small piece of drift accepted deliberately rather than a
detail nobody decided.

### Failure has to be legible

Playwright already writes traces on failure and screenshots on failure, into
`web/test-results/`. Uploading those on failure is the difference between "the browser test
failed" and knowing why, on a machine nobody can attach a debugger to. On success they are not
uploaded, because nobody reads a trace of a passing test.

## Risks / Trade-offs

- **CI takes about five minutes** — the Python suite alone is ~3½. Split into three jobs so
  lint fails in seconds, and nothing is serialised that need not be.
- **The browser job is the fragile one**: two toolchains, a browser, a database, and two
  servers it starts itself. It is also the one that found the last three real bugs in this
  project, so it earns its flakiness budget.
- **A pinned Node version drifts from local** where nothing is pinned at all. Stated in the
  workflow rather than assumed, and worth an `.nvmrc` if it ever bites.
- **Credentials in a workflow file** — the same throwaway ones already in the compose file, for
  a container that lives for one run.
- **This does not deploy anything**, which was the roadmap's intent for this slot. Recorded in
  the proposal as a deliberate deferral rather than left as a gap somebody discovers.

## Migration Plan

Purely additive: one directory of workflow files, and two corrections to the README. Nothing
in the application changes, and no test changes behaviour.

**Rollback** is deleting the workflow. The suites are unaffected — they ran before it and will
run after it.

## Open Questions

- **Whether the browser job should retry once.** `retries: 0` today, deliberately, and a retry
  hides flakiness rather than fixing it. Worth revisiting only if a specific test proves
  genuinely non-deterministic, and then by fixing that test.
- **Whether to pin the Node version in the repository** rather than only in CI. An `.nvmrc`
  would remove the drift this change accepts, and is a decision about local development
  rather than about verification.
