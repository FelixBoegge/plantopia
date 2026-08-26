## ADDED Requirements

### Requirement: A signed-in person can ask who they are

The system SHALL expose the identity of the account making a request: its address, when it
was created, its tier, its role, which privacy notice it agreed to and when, and how much of
its run allowance is used against what limit and when that resets.

Without it a client cannot render an account screen, cannot decide whether to offer an
administrative route, and cannot warn somebody that their next run will be refused — it
would find out by having one refused.

#### Scenario: Asking

- **WHEN** a signed-in person asks who they are
- **THEN** the response carries their address, tier, role and consent record
- **AND** it carries their usage against their allowance and when it resets

#### Scenario: Asking without a session

- **WHEN** the request carries no valid session
- **THEN** it is refused like any other owner-scoped request

#### Scenario: What it never carries

- **WHEN** the response is returned
- **THEN** it contains no password hash, no token, and no other account's details

### Requirement: A diagnosis can be fetched directly

The system SHALL return one diagnosis by its identifier to the owner of the plant it belongs
to, carrying its differential, its evidence, its severity and the plan it produced.

A run reports the identifier of the diagnosis it produced. A client given an identifier it
cannot resolve has been given a receipt rather than a result.

#### Scenario: Fetching a diagnosis

- **WHEN** an owner requests a diagnosis belonging to their plant
- **THEN** its candidates, confidences, evidence and plan are returned

#### Scenario: Fetching another owner's diagnosis

- **WHEN** the diagnosis belongs to somebody else's plant
- **THEN** the response is 404 rather than 403

### Requirement: The newest evaluation result is available to those permitted

The system SHALL return the most recent evaluation harness result to an account holding the
administrative role, and SHALL say plainly when no harness has run rather than failing.

#### Scenario: Reading the newest result

- **WHEN** a permitted account requests it
- **THEN** the most recent result is returned

#### Scenario: Before any harness has run

- **WHEN** a permitted account requests it and none exists
- **THEN** the response says so
- **AND** it is not reported as an error

#### Scenario: Somebody not permitted

- **WHEN** an account without the administrative role requests it
- **THEN** the response is 404
