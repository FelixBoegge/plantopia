## ADDED Requirements

### Requirement: An account carries a role, and one route depends on it

The system SHALL record a role against every account, defaulting to the ordinary one, and
SHALL refuse the evaluation results to any account that does not hold the administrative
role.

This is the first thing here that is about *authorisation* rather than authentication, and
it is deliberately the smallest possible version of it: two roles, one protected resource,
and a default that means every account that exists today is unchanged. Tenancy remains the
mechanism for everything a person owns — a role decides access to something nobody owns,
which is why it could not be expressed as ownership.

#### Scenario: An ordinary account

- **WHEN** an account is created
- **THEN** it holds the ordinary role
- **AND** nothing about what it may reach has changed

#### Scenario: An ordinary account asks for the evaluation results

- **WHEN** an account without the administrative role requests them
- **THEN** the response is 404, not 403
- **AND** it is indistinguishable from a resource that does not exist

#### Scenario: An administrative account

- **WHEN** an account holding the administrative role requests the evaluation results
- **THEN** they are returned

#### Scenario: Reading one's own role

- **WHEN** a signed-in person asks who they are
- **THEN** their role is included
- **AND** an interface can use it to decide what to offer

#### Scenario: A role is not a tier

- **WHEN** an account's tier is changed
- **THEN** its role is unaffected
- **AND** the reverse also holds
