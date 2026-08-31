# species-care Specification

## Purpose
What is known about a species baseline care needs, where that knowledge may come from, and
which source wins when several have an answer. This is what grounds "is this normal for this
plant?" — a fern dropping fronds in dry air is a different situation from a succulent doing
the same thing, and without a baseline the differential reasons about a generic plant.

A hand-written set cannot cover the long tail an identification service can name, so the
knowledge behind this is partly researched rather than curated. That makes honesty the
capability defining constraint: a guess in the shape of an answer must say which it is, and
must be refused outright when the material it would be built from describes a different
plant.

## Requirements

### Requirement: A curated care profile always wins

The system SHALL prefer a hand-written care profile over any other source, and SHALL NOT
allow a generated profile to replace, shadow, or be returned in place of one.

The hand-written set is small and correct. Everything else in this capability is a guess made
from search results by a model, and a guess that can displace a known answer turns a reliable
lookup into an unreliable one for the cases that used to work.

#### Scenario: A species the curated set covers

- **WHEN** baseline care is requested for a species with a hand-written profile
- **THEN** the hand-written profile is returned
- **AND** no search or generation is attempted

#### Scenario: A generated profile already exists for a curated species

- **WHEN** a stored generated profile and a hand-written profile name the same species
- **THEN** the hand-written profile is returned

#### Scenario: Names that differ only in form

- **WHEN** a species is requested by a common name, a scientific name, or in different casing
- **THEN** the same profile is found as for any other form of that name

### Requirement: An unknown species is researched once

The system SHALL research the baseline care of a species it holds no profile for, SHALL record
what it produces, and SHALL answer later requests for that species from the record rather than
researching again.

Research costs a web search and a model call. Paying that on the first diagnosis of a species
is worth a baseline that grounds every later one; paying it on every diagnosis is not.

#### Scenario: A species nothing holds

- **WHEN** baseline care is requested for a species with neither a curated nor a stored profile
- **THEN** the species' care requirements are researched
- **AND** what is produced is recorded

#### Scenario: The same species again

- **WHEN** baseline care is requested for a species already researched
- **THEN** the stored profile is returned
- **AND** no further research is performed

#### Scenario: A profile is a fact about a species, not about an owner

- **WHEN** one owner's run has caused a species to be researched
- **THEN** another owner's run for that species uses the same stored profile

### Requirement: A profile is refused rather than invented

The system SHALL produce a profile only for the species that was asked about, and SHALL
produce none where the material it found does not describe that species.

Web search answers near misses as though they were hits: asked about *Ocimum africanum* it
returns *Ocimum basilicum*. Confidently describing a cousin defeats the point of the lookup —
a caller told nothing is known widens its differential and lowers its confidence, and a caller
told the wrong thing does neither.

#### Scenario: The material is about a different species

- **WHEN** research returns material describing a species other than the one asked about
- **THEN** no profile is produced

#### Scenario: Nothing is found

- **WHEN** research returns no usable material
- **THEN** no profile is produced
- **AND** the request is answered as unknown, exactly as it would have been before

#### Scenario: Research fails

- **WHEN** the search or the extraction fails for any reason
- **THEN** the request is answered as unknown
- **AND** nothing about the run that asked fails

#### Scenario: A refusal is not cached as an answer

- **WHEN** research produced no profile for a species
- **THEN** a later request for that species is not answered with an empty or partial profile

### Requirement: A generated profile says that it is generated

The system SHALL record the origin of every profile and the sources a generated one was built
from, and SHALL make the origin visible wherever the profile's content is shown to a person.

The same honesty rule the differential already follows. A person reading care advice has no
way to tell a curated baseline from one a model wrote out of four search results ten seconds
ago, and the two deserve different amounts of trust.

#### Scenario: Reading a generated profile

- **WHEN** a person is shown care guidance drawn from a generated profile
- **THEN** they are told it was researched rather than curated

#### Scenario: Reading a curated profile

- **WHEN** a person is shown care guidance drawn from a hand-written profile
- **THEN** it is not described as researched

#### Scenario: Where it came from

- **WHEN** a generated profile is recorded
- **THEN** the sources it was built from are recorded with it

### Requirement: Search results are treated as data

The system SHALL fence retrieved search material as untrusted content before any model reads
it, and SHALL NOT act on instructions contained in it.

Search results are attacker-controllable in the same way retrieved passages are, and the
existing fencing exists for exactly this.

#### Scenario: Material containing instructions

- **WHEN** retrieved material contains text directing the model to do something
- **THEN** that text is not followed
- **AND** the profile produced describes care requirements only

### Requirement: A missing profile never fails a run

The system SHALL treat the absence of a care profile as a normal outcome.

Unchanged from today, and stated here because this change introduces two new ways to arrive at
it — a refusal and a failure — and both must land where the existing miss lands.

#### Scenario: A diagnosis for a species with no profile

- **WHEN** a diagnosis is made for a species no profile can be produced for
- **THEN** the diagnosis completes
- **AND** it proceeds without a baseline, as it does today
