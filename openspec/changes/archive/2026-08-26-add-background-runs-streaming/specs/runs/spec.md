## Purpose

Defines what a run is: how a diagnosis or recheck is started, what states it moves through
while it works, how it asks for more information part-way and is answered, how it is
abandoned, and what a client may rely on about all of that.

## ADDED Requirements

### Requirement: Starting a run returns immediately and does not produce a result

The system SHALL accept a request to start a run, create a record of it, and answer without
waiting for the work. The answer SHALL carry the run's identifier and its status, and SHALL
NOT carry a diagnosis.

A run takes on the order of a minute and a half. A request that waits for it holds a
connection open long enough for a proxy, a browser, or a laptop lid to end it, and gives the
owner nothing to look at in the meantime.

#### Scenario: Starting a diagnosis

- **WHEN** an owner starts a run for their plant with one or more photographs
- **THEN** the response is immediate and carries a run identifier and a status
- **AND** the response contains no diagnosis
- **AND** the run is afterwards retrievable by that identifier

#### Scenario: Starting a run for another owner's plant

- **WHEN** a request starts a run naming a plant belonging to somebody else
- **THEN** the response is 404
- **AND** no run is created

#### Scenario: Starting a run without a session

- **WHEN** a request starts a run without a valid session
- **THEN** it is refused
- **AND** no run is created

### Requirement: A run's status is stated, never inferred

The system SHALL expose a run's status as an explicit value, and SHALL move it only through
the defined transitions: `queued` to `running`, `running` to `awaiting_answers`,
`awaiting_answers` to `running`, and `running` to `completed`, `failed` or `cancelled`.

A client SHALL never have to conclude anything from the absence of activity. Silence is
indistinguishable from a crashed worker, a slow model, and a finished run whose last event
was lost.

#### Scenario: Reading a run

- **WHEN** an owner requests a run they started
- **THEN** the response carries its status, its kind, when it started, and what it produced if anything

#### Scenario: A completed run names its diagnosis

- **WHEN** a run completes
- **THEN** its status is `completed`
- **AND** it carries the identifier of the diagnosis it produced

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

### Requirement: A run that needs more information asks, and waits

When the agent requires clarifying answers before it can continue, the system SHALL place
the run in `awaiting_answers`, SHALL make the questions available, and SHALL hold the run
until they are answered.

This is a state, not a failure. Expressing it as an error would mean a client cannot tell a
run that needs a person from a run that broke.

#### Scenario: The agent asks

- **WHEN** a run reaches the point where clarifying answers are required
- **THEN** its status becomes `awaiting_answers`
- **AND** the questions are available to the owner

#### Scenario: Answering

- **WHEN** an owner submits answers to a run awaiting them
- **THEN** the run returns to `running`
- **AND** it continues from where it paused rather than starting again

#### Scenario: Answering twice

- **WHEN** answers are submitted to a run that has already been answered
- **THEN** the second submission is refused as a conflict
- **AND** no second run is started
- **AND** the first run is unaffected

#### Scenario: Answering a run that is not waiting

- **WHEN** answers are submitted to a run that is `queued`, `running`, `completed`, `failed` or `cancelled`
- **THEN** the submission is refused as a conflict

#### Scenario: Answering another owner's run

- **WHEN** answers are submitted to a run belonging to somebody else
- **THEN** the response is 404
- **AND** the run is unaffected

### Requirement: A run can be abandoned

The system SHALL allow an owner to cancel a run that has not finished, and SHALL stop doing
further work for it.

An abandoned tab otherwise keeps spending on the reasoning tier for a result nobody will
read.

#### Scenario: Cancelling

- **WHEN** an owner cancels a run that is `queued`, `running` or `awaiting_answers`
- **THEN** its status becomes `cancelled`
- **AND** no further work is performed for it

#### Scenario: Work already in flight

- **WHEN** a run is cancelled while a step is executing
- **THEN** that step is allowed to finish
- **AND** no subsequent step begins

#### Scenario: Cancelling a finished run

- **WHEN** a run that has already completed or failed is cancelled
- **THEN** the request is refused as a conflict
- **AND** its status is unchanged

### Requirement: A run cannot remain unfinished forever

The system SHALL fail runs that have exceeded a configured wall-clock ceiling without
reaching a terminal status.

A process that is restarted mid-run leaves rows saying `running` that nothing is running.
Without this, a client waits on them indefinitely and they count against their owner's
allowance while producing nothing.

#### Scenario: A run that overran

- **WHEN** a run has been in a non-terminal status for longer than the ceiling
- **THEN** it is moved to `failed`
- **AND** the reason recorded distinguishes it from a run that failed while working

#### Scenario: A run still within the ceiling

- **WHEN** a run has been working for less than the ceiling
- **THEN** it is left alone

#### Scenario: A run waiting for a person

- **WHEN** a run is `awaiting_answers`
- **THEN** the ceiling applied is the one for waiting on a person, not the one for working
- **AND** it is measured from when the questions were asked

### Requirement: A run is refused before it starts if it cannot be afforded

The system SHALL apply the spend ceilings before creating a run, and SHALL refuse a run
that either ceiling forbids without performing any model call.

#### Scenario: An owner at their allowance

- **WHEN** an owner who has reached their allowance starts a run
- **THEN** it is refused
- **AND** no run is created
- **AND** no model call is made

#### Scenario: The daily cap reached

- **WHEN** the day's total spend has reached the cap and any owner starts a run
- **THEN** it is refused, distinguishably from a personal allowance
- **AND** no run is created

#### Scenario: What a run spent is recorded

- **WHEN** a run reaches a terminal status
- **THEN** the tokens and cost it consumed are recorded against its owner
- **AND** this happens whether it completed, failed or was cancelled
