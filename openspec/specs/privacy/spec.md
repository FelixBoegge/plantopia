# privacy Specification

## Purpose
What an owner may do with the data held about them: take a copy of it, and have it removed.
Consent that can be given and never acted on is a record of permission rather than a control.

The demanding half is deletion, and specifically what "removed" is required to mean. A read
path that misses a table fails visibly the first time somebody looks; a delete path that
misses one fails silently and forever, and the person who asked to be forgotten has no way to
find out they were not. So completeness here is a property proven against the schema rather
than a list somebody maintains — and its counterpart matters just as much: data belonging to
nobody is not an owner's to delete.

## Requirements

### Requirement: An owner can take out everything held about them

The system SHALL provide an owner with a copy of every record it holds about them, in a form
that can be read without this application, together with the photographs they uploaded.

Consent that can be given and never inspected is not a control. A person who agreed to
photographs and text being sent to a model is entitled to see what accumulated as a result.

#### Scenario: Exporting an account

- **WHEN** an owner requests their data
- **THEN** they receive their plants, observations, diagnoses, treatment plans, chat messages,
  learned profile facts and usage records
- **AND** the photographs they uploaded are included

#### Scenario: The export is another owner's business

- **WHEN** an owner requests their data
- **THEN** nothing belonging to any other owner is included

#### Scenario: An account with nothing in it

- **WHEN** an owner who has created nothing requests their data
- **THEN** they receive a valid, empty export rather than an error

#### Scenario: Reading it elsewhere

- **WHEN** an export is opened outside this application
- **THEN** its records are readable without reference to internal identifiers alone

### Requirement: An owner can delete their account, and nothing of it remains

The system SHALL remove every record belonging to an owner when they delete their account,
including records reachable only through another record, the photographs they uploaded, and
any conversation state held outside the application's own schema.

A read path that misses a table fails visibly the first time somebody looks. A delete path
that misses one fails silently and forever, and the person who asked to be forgotten cannot
find out that they were not.

#### Scenario: Deleting an account

- **WHEN** an owner deletes their account
- **THEN** no record belonging to them remains anywhere in the system
- **AND** their photographs are gone
- **AND** the stored state of their conversations is gone

#### Scenario: Signing in afterwards

- **WHEN** somebody attempts to sign in to a deleted account
- **THEN** it is refused in the same way as an address that never had an account

#### Scenario: The session cannot be extended

- **WHEN** an account is deleted
- **THEN** every refresh token issued to it is revoked
- **AND** no new access token can be obtained for it

#### Scenario: An access token already in the deleted owner's hands

- **WHEN** a request is made with an access token issued before the account was deleted
- **THEN** it reads nothing, because nothing belonging to that owner remains
- **AND** it writes nothing, because no owner exists for a new record to belong to

#### Scenario: Another owner is unaffected

- **WHEN** one owner deletes their account
- **THEN** every record belonging to every other owner is untouched

#### Scenario: Deletion is one operation

- **WHEN** any part of a deletion cannot be completed
- **THEN** none of it is applied
- **AND** the account remains as it was

### Requirement: Deleting is deliberate

The system SHALL require an owner to re-enter their password and to state their intent
explicitly before deleting their account.

This is the only action in the system that cannot be undone. A single control that destroys
everything is a control somebody will use by accident, and re-authenticating also means an
unattended browser cannot be used to destroy somebody's account.

#### Scenario: Confirming properly

- **WHEN** an owner supplies their current password and confirms their intent
- **THEN** the account is deleted

#### Scenario: The wrong password

- **WHEN** the password supplied does not match
- **THEN** nothing is deleted
- **AND** the failure does not reveal anything beyond the password being wrong

#### Scenario: Intent not confirmed

- **WHEN** the confirmation is missing or does not match what was asked for
- **THEN** nothing is deleted

### Requirement: Data belonging to nobody is not deleted

The system SHALL distinguish records belonging to an owner from reference data belonging to no
one, and SHALL NOT remove the latter when an account is deleted.

The disorder corpus and the researched species care baselines describe plants, not people.
Deleting an account must not degrade the system for everybody else, and "delete everything
with no owner column" would do exactly that.

#### Scenario: Reference data after a deletion

- **WHEN** an owner deletes their account
- **THEN** the disorder corpus and the species care baselines are unchanged

#### Scenario: Another owner's diagnosis afterwards

- **WHEN** another owner runs a diagnosis after an account was deleted
- **THEN** it works exactly as it did before

### Requirement: Completeness is proven against the schema, not asserted

The system SHALL verify deletion by enumerating every table it defines and requiring each to
be either empty of the deleted owner's records or explicitly classified as reference data.

A list of tables written by hand is a list that goes stale the first time somebody adds one,
and the failure is invisible. Deriving the check from the schema means a new table has to be
classified before it can pass, which is the only version of this that stays true.

#### Scenario: Verifying a deletion

- **WHEN** deletion is verified
- **THEN** every table defined by the system is checked
- **AND** the set of tables checked is derived from the schema rather than listed separately

#### Scenario: A table added later

- **WHEN** a new table is added to the schema
- **THEN** it must be classified as owned or as reference data for the verification to pass
