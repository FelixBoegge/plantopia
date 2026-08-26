## MODIFIED Requirements

### Requirement: A run's status is stated, never inferred

The system SHALL expose a run's status as an explicit value, and SHALL move it only through
the defined transitions: `queued` to `running`, `running` to `awaiting_answers`,
`awaiting_answers` to `running`, and `running` to `completed`, `failed` or `cancelled`.

A client SHALL never have to conclude anything from the absence of activity. Silence is
indistinguishable from a crashed worker, a slow model, and a finished run whose last event
was lost.

A completed run SHALL also name the plant its diagnosis belongs to, including when the run
created that plant itself. A run started without naming a plant makes one; a client handed
only a diagnosis identifier has no way to reach the thing it just produced.

#### Scenario: Reading a run

- **WHEN** an owner requests a run they started
- **THEN** the response carries its status, its kind, when it started, and what it produced if anything

#### Scenario: A completed run names its diagnosis

- **WHEN** a run completes
- **THEN** its status is `completed`
- **AND** it carries the identifier of the diagnosis it produced

#### Scenario: A completed run names its plant

- **WHEN** a run completes, having created a plant rather than being given one
- **THEN** it carries the identifier of the plant it created
- **AND** that plant is reachable by its owner

#### Scenario: A run that produced nothing

- **WHEN** a run completes without producing a diagnosis
- **THEN** it says why
- **AND** it is not reported as a failure

#### Scenario: A failed run says so rather than staying silent

- **WHEN** a run fails
- **THEN** its status is `failed`
- **AND** it carries a description of the failure that does not expose internal detail

#### Scenario: Another owner's run is absent

- **WHEN** a request reads a run belonging to a different owner
- **THEN** the response is 404 rather than 403

#### Scenario: Listing runs

- **WHEN** an owner lists their runs
- **THEN** only their own are returned, most recent first
