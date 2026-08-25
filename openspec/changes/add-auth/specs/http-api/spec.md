## MODIFIED Requirements

### Requirement: Every request is attributed to exactly one owner

The system SHALL resolve every request to a single owner before any handler runs, and SHALL
pass that owner into the service layer. No handler SHALL read a resource identifier from a
request and act on it without an owner.

The owner SHALL be established from an authenticated session presented with the request. A
request to an owner-scoped endpoint without a valid session SHALL be refused, and SHALL NOT
be served as anybody — there is no longer a default person for a request to belong to.

The mechanism of resolution remains a single point. What changed is what it consults: a
presented token rather than a seeded row.

#### Scenario: A request arrives

- **WHEN** any endpoint that reads or writes an owner's records is called with a valid session
- **THEN** the request is attributed to that session's owner before the handler runs
- **AND** the same owner is used for every service call the handler makes

#### Scenario: A request arrives without a session

- **WHEN** an owner-scoped endpoint is called with no session, or an invalid one
- **THEN** the request is refused as unauthenticated
- **AND** no service call is made
- **AND** the refusal is distinguishable from a missing resource, so a client knows to sign in rather than to give up

#### Scenario: Resolution changes

The property this scenario protected has been exercised once — a seeded row became a
presented token, and no handler changed — and it is kept because it will be exercised
again, by social login or by an API key.

- **WHEN** the mechanism that establishes an owner is replaced
- **THEN** handlers require no modification
- **AND** the behaviour of every endpoint is unchanged for a request resolving to the same owner

#### Scenario: Endpoints that are not owner-scoped

- **WHEN** registration, sign-in, password reset, or a health probe is called without a session
- **THEN** it is served, because it does not read or write anybody's records

#### Scenario: Two owners, one deployment

- **WHEN** two registered people make the same request with their own sessions
- **THEN** each sees only their own records
- **AND** neither can reach the other's by any identifier
