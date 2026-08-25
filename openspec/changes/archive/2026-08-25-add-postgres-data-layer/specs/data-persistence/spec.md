## Purpose

Defines how Plantopia stores the records that make up a plant's history — plants, observations,
diagnoses, roadmap steps, feedback, learned facts about the owner and chat messages — and how it
guarantees that each owner can reach only their own.

## ADDED Requirements

### Requirement: Every record belongs to exactly one owner

The system SHALL associate every stored domain record with exactly one owner, and SHALL scope
every read and write to the owner making the request. No read or write path SHALL exist that is
not scoped to an owner.

A record belonging to another owner SHALL be indistinguishable from a record that does not
exist. The system SHALL NOT confirm the existence of another owner's record by any means,
including differing error responses, response timing categories, or error text.

#### Scenario: Reading another owner's record

- **WHEN** an owner requests a record identified by a valid identifier belonging to a different owner
- **THEN** the system reports that the record was not found
- **AND** the response is identical to the response for an identifier that matches no record at all

#### Scenario: Listing records

- **WHEN** an owner lists their plants, diagnoses, roadmap steps, learned facts or chat messages
- **THEN** the result contains only records belonging to that owner
- **AND** records belonging to other owners are absent regardless of how many exist

#### Scenario: Writing to another owner's record

- **WHEN** an owner attempts to modify or delete a record belonging to a different owner
- **THEN** no change is made
- **AND** the system reports that the record was not found

### Requirement: Record identifiers reveal nothing

Record identifiers SHALL be non-sequential and SHALL NOT be derivable from another identifier.
Possession of one identifier SHALL give no information about the existence, identifier or count
of any other record.

#### Scenario: Attempting to enumerate records

- **WHEN** a party holds a valid record identifier and derives further candidate identifiers from it
- **THEN** those candidates do not correspond to records
- **AND** no identifier discloses how many records the system holds

### Requirement: Learned facts are unique per owner, not globally

The system SHALL permit the same learned fact to exist for more than one owner, and SHALL treat a
fact as a duplicate only within a single owner's set.

#### Scenario: Two owners learn the same thing

- **WHEN** the system learns "tends to overwater" about one owner and later about a second owner
- **THEN** both facts are stored
- **AND** each owner sees only their own

#### Scenario: One owner learns the same thing twice

- **WHEN** the system learns a fact already held for that owner
- **THEN** the existing fact is updated rather than duplicated
- **AND** its last-confirmed time advances

### Requirement: Times are stored as absolute instants

The system SHALL store every timestamp as an unambiguous instant including its offset from UTC,
and SHALL order records by comparing instants rather than their textual form.

#### Scenario: Ordering records created in different offsets

- **WHEN** two records are created at known instants recorded under different UTC offsets
- **THEN** they are returned in true chronological order
- **AND** the order does not depend on how either timestamp was written

### Requirement: The schema can change without losing data

The system SHALL provide a versioned, repeatable upgrade path that brings a database at any
earlier version to the current one. Applying it to a populated database SHALL preserve every
existing record.

#### Scenario: Upgrading a populated database

- **WHEN** the upgrade path is applied to a database holding plants, diagnoses and learned facts
- **THEN** every pre-existing record is still present and readable afterwards
- **AND** the database reports the current schema version

#### Scenario: Upgrading an empty database

- **WHEN** the upgrade path is applied to a database with no schema at all
- **THEN** the full current schema is created
- **AND** the application starts without further manual steps

### Requirement: Records outlive the application process

Stored records SHALL survive restarting, replacing or redeploying the application, and SHALL NOT
depend on the lifetime of any single application instance or its local filesystem.

#### Scenario: Restarting the application

- **WHEN** the application process is stopped and started again
- **THEN** every plant, diagnosis, roadmap step, learned fact and chat message is still present
- **AND** no record needs to be recreated
