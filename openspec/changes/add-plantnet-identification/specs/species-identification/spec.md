## Purpose

How a plant's species is decided: two independent methods, what feeds each of them, what
happens when they disagree or when either is unavailable, who settles it, and what is
recorded afterwards about which method was right. Everything downstream rests on the species,
so a wrong one is not a wrong field — it is a wrong diagnosis that reads as a confident one.

## ADDED Requirements

### Requirement: Two independent methods identify the plant

The system SHALL attempt identification by a general-purpose vision model and by a specialist
identification service, and SHALL treat neither as authoritative over the other.

One model asked one question produces an answer that nothing can check. Two methods built on
different evidence produce either agreement, which is worth more than either alone, or a
disagreement, which is a question worth putting to the person standing in front of the plant.

#### Scenario: Both methods answer

- **WHEN** a diagnosis begins with photographs
- **THEN** both methods are asked
- **AND** each candidate is carried with the method that produced it and its confidence

#### Scenario: The methods agree

- **WHEN** both methods name the same species
- **THEN** the agreement is recorded and presented as one candidate rather than two

#### Scenario: The methods disagree

- **WHEN** the two methods name different species
- **THEN** both candidates are carried forward
- **AND** the disagreement is not resolved by the system on its own

### Requirement: A photograph's organ is reported and used

The system SHALL determine which part of the plant each photograph shows — leaf, flower,
fruit, bark, or the whole plant — and SHALL supply it to the identification service.

The service accepts the organ as an input and is measurably more accurate given it. Reporting
it costs nothing extra: it rides on the vision request that already examines the same
photographs.

#### Scenario: Organs accompany the photographs

- **WHEN** photographs are sent for identification
- **THEN** each is accompanied by the organ it was determined to show

#### Scenario: An organ cannot be determined

- **WHEN** the organ of a photograph is unclear
- **THEN** it is sent without a claimed organ rather than with a guessed one

### Requirement: A person may state the species themselves

The system SHALL accept an optional species from the person starting a diagnosis, and SHALL
carry it as a third candidate rather than as a fact.

Somebody who knows what their plant is should not have to watch two machines work it out. But
a typed name is a claim like the others: people mislabel plants, and shop labels are wrong
often enough that treating it as settled would import the error silently.

#### Scenario: A species is typed

- **WHEN** a person supplies a species when starting a diagnosis
- **THEN** it is offered as a candidate alongside the two identified ones

#### Scenario: No species is typed

- **WHEN** the field is left empty
- **THEN** the diagnosis proceeds exactly as it would have without it

### Requirement: The owner settles the identification

The system SHALL present the candidates to the owner at the point where the diagnosis already
pauses, and SHALL use the one they choose.

The pause for clarifying questions already exists and is already the moment the person is
being asked to contribute what only they can see. Adding a second interruption for this would
double the cost of the one thing a diagnosis asks of somebody.

#### Scenario: The owner chooses

- **WHEN** the owner selects one of the candidates
- **THEN** the diagnosis proceeds on that species
- **AND** the choice is recorded as confirmed by a person

#### Scenario: The owner does not choose

- **WHEN** the owner answers the other questions without choosing a species
- **THEN** the diagnosis proceeds on the highest-confidence candidate
- **AND** it is recorded as unconfirmed rather than as chosen

#### Scenario: There is nothing to choose between

- **WHEN** only one candidate exists
- **THEN** no choice is presented

### Requirement: Identification never blocks a diagnosis

The system SHALL complete a diagnosis when the identification service is unconfigured,
unreachable, slow, over its quota, or returns something unusable.

This is the first external service on the diagnosis critical path that is not the model
provider. A diagnosis that a third party can stop is a diagnosis somebody paid for and did
not get.

#### Scenario: No key is configured

- **WHEN** no credential for the identification service is present
- **THEN** the diagnosis proceeds with the vision model's identification alone
- **AND** nothing in the interface offers or mentions the service

#### Scenario: The service fails or times out

- **WHEN** the identification service errors, times out, or refuses the request
- **THEN** the failure is recorded against the run
- **AND** the diagnosis proceeds with the candidates it does have

#### Scenario: The free allowance is exhausted

- **WHEN** the service reports that the request allowance is spent
- **THEN** the diagnosis proceeds without it, exactly as when it fails

#### Scenario: Neither method identifies anything

- **WHEN** no method produces a species
- **THEN** the diagnosis proceeds with the species unknown, as it does today

### Requirement: A diagnosis records where its species came from

The system SHALL record, with each diagnosis, which method produced the species it used and
whether a person confirmed it.

A wrong diagnosis has two possible causes: bad reasoning about the right plant, or good
reasoning about the wrong one. Without this, they are indistinguishable afterwards — which is
what makes identification accuracy unmeasurable today rather than merely unmeasured.

#### Scenario: Reading how a diagnosis was reached

- **WHEN** a stored diagnosis is read
- **THEN** the method that produced its species is available
- **AND** whether a person confirmed it is available

#### Scenario: An older diagnosis

- **WHEN** a diagnosis made before this change is read
- **THEN** it reports that its provenance is unknown rather than claiming one

### Requirement: The identification service is credited wherever its data appears

The system SHALL display attribution for the identification service on every surface that
shows a result derived from it.

The free tier permits commercial use on the condition that the service is credited. This is a
term of use, so it is a requirement rather than a matter of taste — and a term that is only
honoured on the screen somebody happened to think of is not honoured.

#### Scenario: A candidate is shown

- **WHEN** a candidate produced by the identification service is displayed
- **THEN** attribution for the service is visible on the same surface

#### Scenario: The service produced nothing

- **WHEN** no result from the service is displayed
- **THEN** no attribution is required
