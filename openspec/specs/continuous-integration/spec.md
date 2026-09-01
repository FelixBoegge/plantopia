# continuous-integration Specification

## Purpose
What must be verified before a change is trusted, and what that verification may depend on.

The project has two suites in two toolchains, and passing one says nothing about the other:
nothing in the Python gate compiles TypeScript, runs a component test, or opens a browser.
Verification that depends on somebody remembering five commands is verification that a tired
person skips, and the defects that reach a repository that way are the ones no local run would
have caught anyway — they are environment-dependent by construction.

Two constraints keep it honest. The checks are the commands a developer runs, because two
definitions of "the tests pass" drift and the way anybody finds out is a change that satisfied
one of them. And no check may require a secret, which is only possible because the suites make
no model calls at all — that is what lets a contribution from a fork be verified identically,
and what keeps the evaluation harness, which bills, out of it entirely.

## Requirements

### Requirement: Every change is verified before it is trusted

The project SHALL verify each pushed change automatically, and that verification SHALL cover
the linting, the Python suite, the frontend typecheck, the frontend unit suite, a production
frontend build, and the browser tests.

A green Python suite says nothing about the frontend: nothing in it compiles TypeScript, runs
a component test, or opens a browser. Three defects reached the repository that way, and the
person who found each of them was a person, not a machine.

#### Scenario: A change is pushed

- **WHEN** a change is pushed to the repository
- **THEN** all six checks run
- **AND** the result is reported against that change

#### Scenario: A proposed change

- **WHEN** a change is proposed for merging
- **THEN** the same checks run
- **AND** a failure is visible before the change is merged rather than after

#### Scenario: Any one check fails

- **WHEN** any check fails
- **THEN** the verification as a whole is reported as failed

### Requirement: The checks are the commands a developer runs

The verification SHALL invoke the same commands documented for local use, and SHALL NOT
maintain a separate set of equivalent ones.

Two definitions of "the tests pass" drift, and the way anybody finds out is a change that
passed one and broke the other. The documented commands are the contract; the machine follows
it rather than restating it.

#### Scenario: A command changes

- **WHEN** the documented way to run a suite changes
- **THEN** the verification runs the changed command
- **AND** no second definition of that suite exists to be updated separately

#### Scenario: Thresholds

- **WHEN** a suite enforces a coverage floor or similar threshold locally
- **THEN** the same threshold applies during verification
- **AND** it is not restated in the verification's own configuration

### Requirement: Verification needs no secret

The verification SHALL complete without any credential, API key, or access to a paid service.

The suites already hold themselves to this — they make no model calls at all — and a
verification that needed a key would be one that could not run for a contribution from
outside, and one whose configuration would be worth stealing.

#### Scenario: A contribution from a fork

- **WHEN** a change is proposed from a fork of the repository
- **THEN** it is verified exactly as a change from a branch is

#### Scenario: No keys configured

- **WHEN** the repository has no secrets configured at all
- **THEN** every check still runs and can still pass

### Requirement: The evaluation harness is never run automatically

The verification SHALL NOT run the evaluation harness.

It makes real model calls against real keys and costs money per run. A machine that ran it on
every push would spend continuously and without anybody deciding to.

#### Scenario: A change that touches the harness

- **WHEN** a change modifies the evaluation harness
- **THEN** the harness itself is still not run
- **AND** the tests covering it run as they do for any other change

### Requirement: The database the suites need is provided

The verification SHALL provide a PostgreSQL with the vector extension available, in which the
suites may create and drop their own databases.

Both suites do exactly that: the Python one creates and drops a test database per run, and the
browser one creates and drops its own. Neither can run against a database they may only read.

#### Scenario: The suites create their databases

- **WHEN** the Python suite or the browser suite runs during verification
- **THEN** it can create its database, enable the vector extension, and drop it afterwards

#### Scenario: The database is unavailable

- **WHEN** the database cannot be reached
- **THEN** the verification fails and says so
- **AND** it does not report the suites as passing
