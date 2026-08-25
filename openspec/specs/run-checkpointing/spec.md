# run-checkpointing Specification

## Purpose
Defines how a diagnosis paused for the owner's answers, and an ongoing chat about a plant,
survive between requests — and who is permitted to resume one.

## Requirements

### Requirement: A paused diagnosis survives independently of the process

A diagnosis that has paused to ask the owner clarifying questions SHALL be resumable after the
application process has been stopped, replaced or redeployed, with the work already done — the
identification, the extracted symptoms, the questions chosen — intact.

#### Scenario: Resuming after a restart

- **WHEN** a diagnosis pauses for clarifying answers and the application is restarted before they arrive
- **THEN** submitting the answers resumes that same diagnosis
- **AND** the identification and symptoms established before the pause are unchanged
- **AND** the owner is not asked to upload the photographs again

#### Scenario: Resuming a chat after a restart

- **WHEN** a chat about a plant has several turns and the application is restarted
- **THEN** the next message continues the same conversation
- **AND** the earlier turns are still available to the agent

### Requirement: Only the owner may resume their run

The system SHALL verify ownership before resuming any paused run or continuing any chat thread. A
handle belonging to another owner SHALL behave exactly as an unknown handle.

#### Scenario: Presenting another owner's handle

- **WHEN** an owner presents a valid handle for a run belonging to a different owner
- **THEN** the run is not resumed and no state is disclosed
- **AND** the system responds as it would to a handle that identifies nothing

### Requirement: Run handles are not derivable from an owner's own data

A handle that identifies a run or chat thread SHALL NOT be constructible from information
available to another owner, such as a plant identifier or a sequence number.

#### Scenario: Attempting to construct a handle

- **WHEN** a party attempts to build a run handle from identifiers and counters available to them
- **THEN** the constructed handle does not resume any run belonging to another owner

### Requirement: An abandoned attempt never merges into a later one

When an owner abandons an attempt — rejecting the result, or retaking the photographs — the
state of that attempt SHALL NOT contribute to the next one. A second attempt SHALL begin from
the owner's new input alone.

#### Scenario: Retaking photographs after a rejected upload

- **WHEN** an upload is rejected and the owner uploads different photographs
- **THEN** the new attempt reflects only the new photographs
- **AND** nothing established during the abandoned attempt appears in its result

#### Scenario: Re-checking a plant twice without a diagnosis in between

- **WHEN** an owner abandons a re-check of a plant and starts another
- **THEN** the second re-check does not resume the abandoned one

### Requirement: An owner's run state can be removed completely

The system SHALL be able to delete all persisted run and chat state belonging to one owner, so
that no paused run of theirs remains resumable and no conversation of theirs remains readable.

#### Scenario: Removing everything for one owner

- **WHEN** deletion of an owner's run state is requested
- **THEN** none of that owner's runs can be resumed afterwards
- **AND** none of that owner's chat threads returns prior turns
- **AND** other owners' runs and threads are unaffected
