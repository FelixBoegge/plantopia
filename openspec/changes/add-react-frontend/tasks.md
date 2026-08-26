## 1. The four API gaps

- [x] 1.1 Add `users.role` with a default and a migration; verify the schema test names it, `alembic upgrade head` runs on an empty database, and the migration test reports no drift.
- [x] 1.2 Add the authorisation dependency refusing a route to accounts without the administrative role; verify tests that it refuses with 404 rather than 403, that an ordinary account cannot tell the route exists, and that changing a tier does not change a role.
- [x] 1.3 `GET /me` carrying address, tier, role, consent record and allowance usage; verify tests for each field, for a request without a session being refused, and that no password hash or token appears in the response.
- [x] 1.4 Include remaining allowance and reset date in `GET /me`; verify a test that the numbers match what the quota guard would apply, so a warning and a refusal cannot disagree.
- [x] 1.5 `GET /diagnoses/{id}` returning one diagnosis with its differential, evidence, severity and plan; verify tests for the shape and for another owner's diagnosis answering 404, added to the endpoint tenancy table.
- [x] 1.6 Record the plant a run created on the run row; verify a test that a run started without a plant names one when it completes, and that the plant is reachable by its owner.
- [x] 1.7 `GET /evaluation/latest` reading the newest harness result; verify tests for a permitted account reading it, an ordinary account getting 404, and no harness having run answering plainly rather than failing.
- [x] 1.8 Update the README's settings and endpoint list, and `.env.example` if roles need one; verify every documented command still runs as written.

## 2. The application shell

- [x] 2.1 Scaffold `web/` with Vite, TypeScript, Tailwind and shadcn/ui; verify `npm run build` and `npm run test` both succeed on a clean checkout.
- [x] 2.2 Add Vitest, React Testing Library and MSW with one passing example test; verify the example fails when its assertion is inverted, so the runner is known to be running.
- [x] 2.3 Add the API client and hand-written types for the shapes this consumes; verify a test that a problem-details response is parsed into its type and detail rather than a bare string.
- [x] 2.4 Add the fetch wrapper holding the access token in a module closure; verify tests that the token is sent as a header, never appears in a URL, and is not written to `localStorage` or `sessionStorage`.
- [x] 2.5 Renew once on an expired-token refusal and retry the original request; verify tests for a successful renewal being invisible to the caller, an unauthenticated refusal sending the person to sign in without renewing, and a failed renewal not retrying.
- [x] 2.6 Serialise concurrent renewals; verify a test that several requests failing at once produce exactly one refresh — several would rotate several times, and every rotation but one is a reused token that ends the session.
- [x] 2.7 Add routing and an authenticated layout; verify tests that an unauthenticated visit to an owner-scoped route lands on sign-in, and that the route asked for is returned to afterwards.
- [x] 2.8 Add TanStack Query with its provider and query-key conventions; verify a test that a mutation invalidates what it changed.
- [x] 2.9 Add light and dark themes honouring the system preference; verify a test that the choice persists across a reload and that neither theme is hard-coded in a component.

## 3. Getting in

- [x] 3.1 The registration screen, including consent, with the notice's plain-language text; verify tests that consent cannot be skipped, that the response is the same whether or not the address is taken, and that the person is told to check their email rather than being signed in.
- [x] 3.2 The verification screen consuming a link's token; verify tests for verifying, for a link already used, and for a link that means nothing — all three saying something a person can act on.
- [x] 3.3 The sign-in screen; verify tests for signing in, for a refusal that does not say which half was wrong, and for arriving at the plants afterwards.
- [x] 3.4 The password reset request and confirm screens; verify tests for both, and that the request screen answers identically for an address with no account.
- [x] 3.5 Sign-out, clearing the token and the cached server state; verify a test that no cached data survives into the next session on the same browser.
- [x] 3.6 Establish a session from the refresh cookie on load; verify a test that a reload keeps somebody signed in without a token having been stored.

## 4. Plants

- [x] 4.1 The plant grid; verify tests for rendering a person's plants, for the empty state inviting a first diagnosis, and for a failure to load saying so rather than showing nothing.
- [x] 4.2 The plant detail screen with its history; verify tests for observations and diagnoses in order, and for a plant with no diagnosis yet.
- [x] 4.3 The roadmap as a dated checklist; verify tests that marking a step updates it, that reopening clears its completion, and that the change is visible without a manual reload.
- [x] 4.4 Renaming and removing a plant, with confirmation before removal; verify tests for both and that removal is not reachable in a single click.
- [x] 4.5 The chat screen with per-reply source chips; verify tests that a reply's sources are shown on the reply, and that an answer given without a lookup is distinguishable from one with.
- [x] 4.6 Use the streaming chat endpoint, showing lookups as they happen; verify tests that a lookup appears before the reply and that the transcript afterwards matches what the API returns.
- [x] 4.7 Serve photographs through the authenticated endpoint; verify a test that an image request carries the session and that no photograph URL contains a credential.

## 5. The wizard

- [x] 5.1 `useRunStream` reading the event stream with `fetch` and a `ReadableStream`; verify tests that it parses events from a fabricated stream, sends the token as a header, and puts nothing in the URL.
- [x] 5.2 Reconnect on a dropped stream using `Last-Event-ID`; verify tests that it resumes from the last event seen and that a duplicate arriving across the reconnect is rendered once.
- [x] 5.3 The upload step, with what was selected shown back; verify tests that nothing starts until the person confirms, and that a refused upload explains itself and leaves no run behind.
- [x] 5.4 The reasoning panel rendering steps as they arrive; verify tests that steps accumulate rather than replace, that a long gap still reads as working, and that no internal name appears.
- [x] 5.5 The clarifying questions, rendered in place mid-stream; verify tests that they appear without losing the progress shown, and that submitting continues the same run.
- [x] 5.6 Handle a second submission being refused; verify a test that the person sees the run's current state rather than an error.
- [x] 5.7 The differential as ranked cards with confidence, evidence for and against, and the confirming test; verify tests for ordering, for a candidate with no confirming test, and that the leading candidate is not presented as the only answer.
- [x] 5.8 Handle a run that produced no diagnosis; verify a test that the reason is shown and that it is not presented as a failure of the system.
- [x] 5.9 Offer the plant a completed run produced; verify a test that the result screen links to it.
- [x] 5.10 Abandoning a run from the wizard; verify tests that it reports as cancelled and that the interface does not imply work already done is unbilled.
- [x] 5.11 Resume the wizard on a reload and on a run opened fresh; verify tests for a run still working, one already completed, and one that failed while the person was away.

## 6. Account and evaluation

- [x] 6.1 The account screen showing learned facts with when and how confident, and forgetting one; verify tests that forgetting removes it and that the list reflects the server afterwards.
- [x] 6.2 Show the consent record and the allowance; verify tests for the notice version and date, and for the remaining runs and reset date.
- [x] 6.3 Warn before a run that would be refused; verify a test that somebody at their allowance is told before starting rather than after.
- [x] 6.4 The evaluation screen for permitted accounts; verify tests that it renders the newest result, that it says so plainly before any harness has run, and that an ordinary account sees what it would see for any unknown route.

## 7. Accessibility and finish

- [ ] 7.1 A `Severity` component carrying a text label; verify tests that every severity renders its label and that no other component renders a severity directly.
- [ ] 7.2 Focus management through the wizard; verify tests that focus moves to each new step rather than staying where it was.
- [ ] 7.3 `aria-live` on the reasoning panel and the chat reply; verify tests that content arriving without a navigation is announced.
- [ ] 7.4 Keyboard paths through every flow; verify tests that starting, answering and reading a diagnosis are reachable without a pointer.
- [ ] 7.5 Run an automated accessibility check over each route; verify no violations at the level the check reports, and record any accepted exception with its reason.

## 8. Proving it works, and closing

- [ ] 8.1 Add Playwright against the real stack with scripted models; verify the harness starts the API and the frontend and that one trivial flow passes.
- [ ] 8.2 A Playwright flow for registering, verifying and signing in; verify it passes against a clean database.
- [ ] 8.3 A Playwright flow for a diagnosis through the interrupt to a differential; verify it passes and that the reasoning panel showed more than one step.
- [ ] 8.4 A Playwright flow that drops the stream mid-run and reconnects; verify the run completes and no step is shown twice.
- [ ] 8.5 A Playwright flow for a chat reply with a lookup; verify the lookup is announced before the reply arrives.
- [ ] 8.6 Confirm the evaluation harness is untouched and its numbers are not expected to move; verify the harness-independence test still passes and that nothing in this change added a prompt, a model call or a retrieval.
- [ ] 8.7 Update the README: running the frontend, running both test suites, and what the admin role is for; verify every command runs as written on a clean clone.
- [ ] 8.8 Record what this change leaves undone — anything the accessibility pass accepted, and the fact that the frontend's tests are a second command a contributor can forget; verify identifiers and dates against the file's conventions.
- [ ] 8.9 Run `openspec validate add-react-frontend --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
