# Implementation tasks

Ordered so the cheapest gate is proven first and the one needing four things at once is
proven last. Nothing in the application changes.

## 1. Linting, which needs nothing

- [x] 1.1 Add the workflow triggered on push and on pull request, with a job running `uv run ruff check .`; verify it runs on a push and reports against the change.
- [x] 1.2 Add `uv run ruff format --check .`; verify it fails on a deliberately misformatted file and that CI does not rewrite anything.
- [x] 1.3 Take the Python version from `.python-version` rather than restating it; verify the job reports 3.12 without the workflow naming it.

## 2. The Python suite, which needs a database

- [x] 2.1 Add a PostgreSQL service with pgvector, published on 5433 with the committed development credentials; verify the suite finds it without `PLANTOPIA_DATABASE_URL` being set.
- [x] 2.2 Confirm the service is ready before the suite starts; verify a run does not fail on a connection refused.
- [x] 2.3 Run `uv run pytest` unchanged; verify the coverage floor is enforced by `pyproject.toml` rather than restated in the workflow.
- [x] 2.4 Confirm the frontend source is present for the three cross-language tests; verify by checking those tests pass in the job.
- [x] 2.5 Confirm no secret is required; verify the job passes with no repository secrets configured.

## 3. The frontend, and the browser

- [x] 3.1 Add the job with both toolchains and Chromium; verify `npm ci` installs from the committed lockfile.
- [x] 3.2 Run `npm run build`, which is the typecheck and the production build in one command; verify a type error fails the job and record that this is what "typecheck in CI" means here.
- [x] 3.3 Run `npm test`; verify it runs before the browser tests, so those never run against a frontend whose unit tests failed.
- [x] 3.4 Run `npx playwright test`, letting it start its own two servers; verify the job provides the database both of them need.
- [x] 3.5 Upload traces and screenshots when the browser job fails, and not when it passes; verify by inspecting a failing run's artefacts.
- [x] 3.6 Pin the Node version in the workflow and say why it is stated there rather than read from the repository; verify the job reports that version.

## 4. What must not happen

- [x] 4.1 Confirm the evaluation harness is never invoked; verify by searching the workflow for it and stating what was found.
- [x] 4.2 Confirm nothing publishes, deploys or pushes an image; verify the workflow has no such step.
- [x] 4.3 Confirm a fork's pull request is verified identically; verify by checking no step reads a secret.

## 5. Proving it, and closing

- [x] 5.1 Run the whole workflow locally where possible — the commands, in order, as the workflow will — and record what passed and how long it took.
- [x] 5.2 Push it and watch a real run; verify every job passes and record the total time.
- [x] 5.3 Deliberately break one thing per job — a format error, a failing test, a type error — and verify each job fails for the reason it should.
- [x] 5.4 Update the README: that CI runs the gates, and stop saying a contributor has to remember two suites; verify every command still runs as written on a clean clone.
- [x] 5.5 Correct the README's stale claim of "Single user, no authentication"; verify nothing else in that section contradicts what the system now does.
- [x] 5.6 Record the showcase requirement the capstone brief makes, which only the owner can satisfy; verify the README says plainly where the link belongs.
- [x] 5.7 Close `M33` and record what this leaves undone — no containers, no deployment, the Node version pinned only in CI; verify identifiers and dates against the file's conventions.
- [x] 5.8 Run `openspec validate add-continuous-integration --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
