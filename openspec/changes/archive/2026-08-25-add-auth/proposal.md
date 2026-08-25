## Why

Plantopia has one owner, seeded at startup, and every request resolves to it. That was the
right shape for the previous two changes — it let the data layer and the HTTP surface be
built and tested against a real owner without inventing sessions first — but it is not a
product. Nobody else can use this, and the React frontend has nobody to sign in.

The whole migration has been building the thing this change needs: repositories that refuse
another owner, an API whose every handler already takes one, and a single function that
decides who is asking. Replacing that function's body is most of the work; the rest is what
has to exist around it before strangers can register.

**Registration is open, and that is what makes spend control part of this change rather
than a later one.** Every diagnosis costs roughly five cents of somebody else's model
budget. Open registration without a ceiling is an unmetered bill with a signup form in
front of it, so identity and limits ship together — there is deliberately no commit where
one exists without the other.

## What Changes

- **Registration, open to anyone**, with argon2id password hashing and a verification email
  before the account can be used.
- **Email verification and password reset**, both single-use, hashed at rest, and expiring
  — 24 hours for verification, one hour for reset. Without reset there is no recovery path
  at all: nobody is handing out invitations, so a forgotten password would mean a lost
  account.
- **Sessions built from two tokens.** A short access token the client holds in memory, and
  a long refresh token in an `httpOnly` cookie, rotated on every use, stored as a hash,
  with **reuse detection**: presenting an already-rotated token invalidates its whole
  family, because that pattern means it was stolen.
- **`current_owner` resolves a real session.** The seeded owner disappears. This is the
  seam the previous change existed to leave behind — handlers do not change.
- **Per-user quotas and a global daily spend cap**, checked before a run starts and
  refusing with a structured reason a UI can render, not a bare error. Usage is recorded
  per *run* rather than per diagnosis, so a run that spends and then fails still counts.
- **Per-IP rate limits** on register, login and password reset — the three endpoints that
  are cheap to hammer and expensive to leave open.
- **Enumeration-safe responses.** Login, registration and reset all answer the same way
  whether or not an address is registered. An error that distinguishes them is a way to ask
  the system who has an account.
- **A consent record at signup**: which version of the privacy notice was agreed, and when.
  Registration is the only moment it can be captured.
- **Email behind a port**, with a Resend adapter and a console adapter. Development and
  tests never send anything real.

**Explicitly out of scope:**

- *The privacy notice's text, data export, and account deletion* — the privacy change. This
  one records **that** consent was given and to which version; what the notice says, and
  the rights it describes, are that change's subject.
- *Social login.* The token layer is built so a provider can be added without reworking
  sessions, and none is added here.
- *Subscription tiers and payment.* `users.tier` exists with one value, `free`, and quotas
  read it. No payment provider, no plans, no checkout.
- *Diagnosis and re-check endpoints.* Still waiting on background runs. Quotas are
  therefore written and tested against the service that will call them, and wired into the
  run endpoints when those exist — recorded as a known gap rather than pretended away.
- *Multi-process rate limiting.* Limits are per process, which is exact for one container
  and approximate for several. Recorded; revisit when there is more than one.

## Capabilities

### New Capabilities

- `identity`: who a person is and how a request proves it — registration, verification,
  sessions, rotation and revocation, password reset, and what the system refuses to reveal
  about who has an account.
- `usage-limits`: what stops one person, or everybody together, from spending an unbounded
  amount of somebody else's model budget.

### Modified Capabilities

- `http-api`: the requirement that every request is attributed to an owner currently says
  the owner is "a single seeded one". It becomes an authenticated session, and unauthenticated
  requests to owner-scoped endpoints are refused rather than served as somebody.

## Impact

**Code.** A new `identity/` package: password hashing, token issue and verification,
registration and reset flows, and the email port. `api/` gains auth routers and replaces
`current_owner`'s body. `data/models.py` gains password and verification columns on
`users`, plus `refresh_tokens`, `email_tokens` and `usage_events` tables, with an Alembic
migration. `agent/wiring.py` loses `default_owner_id`, which is what the seeded owner was.

**Dependencies.** `argon2-cffi` for hashing, `pyjwt` for tokens, and an HTTP call to Resend
through the existing `httpx`.

**Tests.** Identity gets its own tier: hashing, token lifetime, rotation, reuse detection,
expiry, enumeration-safety, and the quota and cap decisions. The endpoint tenancy table
stops overriding the owner dependency and issues requests as two genuinely different
registered users — closing `M27`.

**Operations.** New settings: a JWT secret, token lifetimes, the Resend key, quota limits
and the spend cap. A secret with no safe default is a startup failure rather than a
generated value, because a JWT secret that changes on restart silently logs everybody out.

**Risk.** The highest of any change so far, because this is the first one where a mistake
is a security defect rather than a bug. Three things are therefore not left to review:
reuse detection has its own tests, enumeration-safety is asserted on responses rather than
argued about, and the endpoint tenancy table is re-run against two real accounts.

The second risk is quotas guarding a door that is not yet built — diagnosis endpoints do
not exist, so nothing calls the guard in anger. It is tested at the service boundary and
recorded as a gap, rather than being claimed as protection it does not yet provide.
