## 1. Schema and settings

- [x] 1.1 Add `argon2-cffi` and `pyjwt`; verify `uv sync` and that both import.
- [x] 1.2 Add password, verification and consent columns to `users`, plus `refresh_tokens`, `email_tokens` and `usage_events` models; verify the schema test asserts the new table names and that every timestamp carries a timezone.
- [x] 1.3 Generate and apply the migration; verify `alembic upgrade head` on an empty database and `alembic check` reporting no drift.
- [x] 1.4 Add settings for the JWT secret, token lifetimes, the Resend key, quota allowance and the daily spend cap, with `.env.example` documentation; verify a test that the application refuses to start without a JWT secret — a generated default would log everybody out on every restart, and would work perfectly in development.

## 2. Hashing and tokens

- [x] 2.1 Add password hashing and verification with argon2id at library defaults; verify tests that a hash never equals its password, that two accounts with the same password store different values, and that verification accepts the right password and rejects a wrong one.
- [x] 2.2 Add access-token issue and verification; verify tests for a valid token resolving to its subject, an expired one being refused, a tampered one being refused, and one signed with a different secret being refused.
- [x] 2.3 Add refresh-token issue, hashing and rotation with family tracking; verify tests that a token is stored only as a hash, that rotation issues a new one and retires the old, and that the retired one no longer works.
- [x] 2.4 Add reuse detection; verify a test that presenting an already-rotated token invalidates the family — including the token issued by the legitimate refresh — and a test that a second device's family is untouched.

## 3. Registration and verification

- [x] 3.1 Add the email port with a console adapter and a Resend adapter; verify tests that the console adapter writes where a developer can read it, that no adapter sends in tests, and that a provider failure is logged rather than raised.
- [x] 3.2 `POST /auth/register` creating an unverified account and sending a verification message; verify tests for the account being created unverified, the message being sent, and the password appearing nowhere in the response.
- [x] 3.3 Refuse registration without consent, and record the notice version and time; verify tests both ways.
- [x] 3.4 Refuse passwords below the minimum length; verify a test that no account is created.
- [x] 3.5 Make registering an existing address indistinguishable from registering a new one, notifying that address instead; verify a test comparing both responses field by field, and one asserting no second account exists.
- [x] 3.6 `POST /auth/verify` consuming a single-use token; verify tests for verifying, for a second use being refused while the account stays verified, and for an expired token being refused.
- [x] 3.7 Assert email tokens are stored hashed; verify a test that the stored value cannot be used to construct a working link.

## 4. Sessions

- [x] 4.1 `POST /auth/login` issuing an access token in the body and a refresh cookie that is httpOnly, Secure and SameSite=Strict; verify tests for each cookie attribute and that the refresh token is absent from the body.
- [x] 4.2 Refuse sign-in for an unverified account; verify a test that no session is issued.
- [x] 4.3 Make an unknown address and a wrong password indistinguishable; verify a test comparing both responses.
- [x] 4.4 `POST /auth/refresh` rotating the token; verify tests for a new access token, a replaced refresh token, and the presented one ceasing to work.
- [x] 4.5 `POST /auth/logout` invalidating the token and clearing the cookie; verify a test that refreshing afterwards is refused.
- [x] 4.6 Distinguish an expired access token from a malformed one; verify a test that a client can tell "refresh" from "sign in again".

## 5. The switchover

- [x] 5.1 Replace `current_owner` with session resolution; verify that no handler changed, by diffing the routers.
- [x] 5.2 Refuse owner-scoped endpoints without a session, while leaving auth and health endpoints open; verify a table-driven test over every route asserting which require a session and which do not.
- [ ] 5.3 Remove `default_owner_id` and the seeded owner; verify nothing imports it and the suite is green.
- [ ] 5.4 **Decide what happens to Streamlit, and do it.** It resolves an owner through the seeded row and will break outright. Either give it a development-only sign-in or retire it in favour of the API. Surface the choice rather than picking silently — it is the control client the migration has leaned on, and retiring it early costs that. Verify whichever is chosen actually works end to end.

## 6. Password reset

- [ ] 6.1 `POST /auth/reset/request` sending a single-use, time-limited link, answering identically for unregistered addresses; verify tests for both cases and that nothing is sent to an address with no account.
- [ ] 6.2 `POST /auth/reset/confirm` setting a new password and invalidating every existing session; verify tests for the password changing, the token not working twice, and prior sessions being refused afterwards.
- [ ] 6.3 Invalidate an outstanding reset token when a second is requested; verify a test that a link found later cannot be used.

## 7. Spend control

- [ ] 7.1 Record tokens and cost per run in `usage_events`, including runs that fail after spending; verify tests for a successful run, a failed one, and a provider reporting no cost — where unknown must stay distinguishable from zero.
- [ ] 7.2 Add the quota guard reading the owner's tier; verify tests for a run below the allowance proceeding, one at the allowance being refused before any model call, the period rolling over, and a second tier applying without a code change.
- [ ] 7.3 Add the global daily spend cap; verify tests that it refuses every run including for owners with allowance left, that its refusal is distinguishable from a personal quota, and that a new day clears it.
- [ ] 7.4 Add per-IP rate limits on register, login and reset; verify tests for ordinary use passing, hammering being refused with a retry-after, and the refusal not differing for registered versus unregistered addresses.
- [ ] 7.5 Give each refusal its own machine-readable type in the problem-details shape; verify a test asserting all four — personal quota, global cap, rate limit, unauthenticated — are mutually distinguishable.
- [ ] 7.6 Record that nothing calls the quota guard yet, because run endpoints do not exist, and add wiring it in as a task of the change that introduces them; verify the note reads accurately against what is actually wired.

## 8. Closing the gaps

- [ ] 8.1 Rewrite the endpoint tenancy table to register two accounts and issue requests as each; verify it fails when a route is made to ignore the session's owner, and remove the dependency override the previous change relied on.
- [ ] 8.2 Strike `M27` as resolved with today's date, and record the per-process rate-limit limitation and the frontend contract that refresh must not be retried blindly; verify identifiers and dates against the file's conventions.
- [ ] 8.3 Update the README: registration and sign-in, the new settings, and whatever became of Streamlit; verify every command runs as written on a clean clone.
- [ ] 8.4 Run `openspec validate add-auth --strict`, the full suite including the `ui` tier, and ruff; verify all three are clean.
