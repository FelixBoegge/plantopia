## Context

See `proposal.md` — Why. Requirements are in `specs/identity`, `specs/usage-limits` and the
`specs/http-api` delta.

What the previous changes left, which this one either uses or replaces:

- **`current_owner` is one function** returning the seeded owner. Replacing its body is the
  central edit; no handler changes.
- **Repositories refuse another owner already.** Authentication decides *who* is asking.
  Nothing downstream trusts the answer more than it trusted the seeded one.
- **`users` exists** with an email and a created timestamp, and nothing else.
- **`M27` records** that endpoint tenancy is exercised by overriding a dependency because
  there is no second person. This change is what closes it.
- **Errors are RFC 9457 problem details**, mapped centrally. New refusals join that shape
  rather than inventing one.
- **The data layer is synchronous**, and stays so.

## Goals / Non-Goals

**Goals:**

- A person can register, prove their address, sign in, stay signed in, sign out, and
  recover a forgotten password.
- A stolen refresh token is detectable and its damage bounded.
- No endpoint reveals who has an account.
- Neither one person nor everybody together can spend without a ceiling.

**Non-Goals:**

- Social login, MFA, or account linking. The token layer leaves room; none is built.
- Roles or permissions. There is one kind of person, and `tier` affects quota, not access.
- Session management UI — listing devices, revoking one remotely. Reuse detection covers
  the case that matters; the rest is product work with no demand yet.
- Distributed rate limiting. One process, in-memory, and the limitation recorded.

## Decisions

### argon2id, at the library's defaults

`argon2-cffi` with its default parameters, which track current guidance.

*Alternative rejected: bcrypt.* Adequate, but argon2id is the current recommendation and
there is no legacy hash to stay compatible with — this is the one moment the choice is
free.

*Alternative rejected: tuning the cost parameters by hand.* A number chosen once from a
blog post and never revisited is worse than a maintained default, because it looks
deliberate.

### Access token in the body, refresh token in an httpOnly cookie

The access token is short-lived and returned in the response body for the client to hold in
memory. The refresh token is long-lived, `httpOnly`, `Secure`, `SameSite=Strict`.

*Alternative rejected: both tokens in `localStorage`.* The most common SPA shape, and it
hands the session to any XSS on the page. The cost of avoiding it is one silent-refresh
interceptor in the frontend.

*Alternative rejected: a session cookie and no access token.* Simpler, and it makes every
request a CSRF consideration. `SameSite=Strict` on a cookie used *only* by the refresh
endpoint is a much smaller surface to reason about.

### Refresh tokens are hashed, rotated, and tracked in families

Each sign-in starts a family. Each refresh issues a new token in that family and marks the
previous one used. Presenting a used token invalidates the family.

*Alternative rejected: refusing only the reused token.* If a thief has a copy, refusing the
victim's request while the thief's newer token keeps working protects nobody. The whole
family goes, and the account signs in again.

**Consequence, accepted:** a client that retries a refresh after a dropped response can
invalidate its own session. That is the same signal as a theft and cannot be distinguished
from it — so the frontend must not retry refresh blindly, which the tasks record.

### Enumeration-safety is asserted, not intended

Registration, sign-in and reset return the same response for known and unknown addresses.
Registration for an existing address sends *that address* a "someone tried to register"
message rather than answering differently.

Timing is deliberately not claimed. Hashing a password takes far longer than any branch
here, so the *responses* are identical and the timing is not argued about — a claim about
timing that no test measures is a claim not worth making.

### Quotas guard the service, not the endpoint

The guard is a service-layer object consulted before a run starts. Diagnosis endpoints do
not exist yet.

*Alternative rejected: waiting for the run endpoints.* The reason to build it now is that
registration opens in this change, and a limit that arrives afterwards has a window with no
limit in it. It is tested where it lives, and the tasks record that nothing calls it in
anger until runs exist — including a task in the *next* change to wire it in.

### Rate limiting is in-process and approximate

A small in-memory limiter on the three unauthenticated endpoints.

*Alternative rejected: Redis.* A second service to deploy, for a workload of one container.
*Alternative rejected: a Postgres-backed counter.* Every login attempt becomes a write on
the path an attacker is hammering, which is the wrong end to add work to.

**Consequence, recorded:** with several processes the effective limit multiplies by the
process count, and limits reset when a process restarts. Correct for one container;
revisited when there is a reason to have more.

### The JWT secret has no default

Absent configuration, the application refuses to start.

*Alternative rejected: generating one at startup.* Every restart would invalidate every
session, and it would work perfectly in development — so the failure would first appear as
users being logged out at random in production.

## Risks / Trade-offs

- **A defect here is a security defect**, not a bug → the three things most likely to be
  wrong get direct tests rather than review: reuse detection, enumeration-safety, and
  tenancy across two real accounts.
- **Quotas guard a door that does not exist yet** → tested at the service boundary, with
  the wiring recorded as a task in the change that adds run endpoints. Not claimed as
  working protection until then.
- **Rate limits are per process** → recorded in `known-limitations.md` rather than
  described as if they were global.
- **A refresh retry can log somebody out** → inherent to reuse detection, and the frontend
  contract is written down rather than discovered.
- **Streamlit has no login** → it is still wired to a session-less path and would break
  outright. The tasks either give it a development sign-in or retire it; deciding that is
  part of the work, not a surprise at the end.
- **Email arrives from an unverified domain** → verification mail may land in spam until
  DNS is configured at deployment. Real, and it belongs to the deployment change; noted so
  the first person to test signup is not baffled.

## Migration Plan

The seeded owner disappears, and the existing development database has records belonging to
it. Those records stay, owned by that row — the first real account registers alongside
rather than inheriting them. Nothing migrates: it is development data, and pretending an
anonymous seed is a person would be a worse story than leaving it.

Order, which is also the order the risk retires:

1. Schema: password and verification columns, `refresh_tokens`, `email_tokens`,
   `usage_events`, and the migration.
2. Hashing and tokens, tested in isolation before anything routes to them.
3. Registration and verification, with the email port and a console adapter.
4. Sign-in, refresh, rotation, reuse detection, sign-out.
5. `current_owner` switches over; Streamlit is dealt with in the same step, because that is
   where it breaks.
6. Password reset.
7. Quotas, the daily cap, rate limits.
8. The endpoint tenancy table, re-run against two registered accounts, closing `M27`.

**Rollback** is reverting the branch. The API is not deployed and has no users.

## Open Questions

- **Whether a verification message should be re-sendable without signing in.** It has to be
  possible — mail gets lost — but doing it from an unauthenticated endpoint makes a mail
  cannon. Rate limiting probably suffices; the shape can be decided when the frontend has
  somewhere to put the button.
- **How long a session should actually last.** Thirty days is a guess. It changes one
  setting and nothing else, which is why it is safe to leave until somebody is annoyed.
