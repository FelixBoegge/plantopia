## Purpose

Defines how Plantopia is reached over HTTP: what a client may ask for, how a request is
attributed to an owner, what a failure looks like, and which of those a client may rely on
not changing underneath it.

## ADDED Requirements

### Requirement: Every request is attributed to exactly one owner

The system SHALL resolve every request to a single owner before any handler runs, and SHALL
pass that owner into the service layer. No handler SHALL read a resource identifier from a
request and act on it without an owner.

While authentication is absent, the owner resolved SHALL be a single seeded one. The
mechanism of resolution SHALL be a single replaceable point, so that introducing real
sessions changes how an owner is determined and nothing about what happens afterwards.

#### Scenario: A request arrives

- **WHEN** any endpoint that reads or writes an owner's records is called
- **THEN** the request is attributed to an owner before the handler runs
- **AND** the same owner is used for every service call the handler makes

#### Scenario: Resolution changes

- **WHEN** owner resolution is replaced by a real authenticated session
- **THEN** handlers require no modification
- **AND** the behaviour of every endpoint below is unchanged for a request that resolves to the same owner

### Requirement: Another owner's resource is absent, not forbidden

For every endpoint that accepts a resource identifier, a resource belonging to a different
owner SHALL produce the same response as an identifier that matches no resource at all —
including the status code, which SHALL be 404 and SHALL NOT be 403.

A 403 asserts that the thing exists and is being withheld, which tells a stranger it
exists. The storage layer already refuses the read; this requirement is that the HTTP
layer does not undo that refusal by describing it.

#### Scenario: Requesting another owner's plant

- **WHEN** a request names a plant identifier belonging to a different owner
- **THEN** the response is 404
- **AND** it is indistinguishable from the response for an identifier no plant has

#### Scenario: Modifying another owner's record

- **WHEN** a request attempts to modify or delete a record belonging to a different owner
- **THEN** the response is 404
- **AND** no change is made to that record

#### Scenario: An identifier that is not well formed

- **WHEN** a request names an identifier that is not a valid identifier at all
- **THEN** the response reports a client error
- **AND** it does not reveal whether any resource exists

### Requirement: Failures are reported in one machine-readable shape

Every error response SHALL carry the same structure, including a stable machine-readable
type, a human-readable title, and the status code. Handlers SHALL NOT return bare strings,
and SHALL NOT leak stack traces, database messages, or internal identifiers.

A client is expected to branch on the type. It is therefore part of the interface, and
SHALL NOT change for a given failure without that being a change to this specification.

#### Scenario: A resource is not found

- **WHEN** any endpoint reports that a resource does not exist
- **THEN** the response body carries the shared error structure
- **AND** its type identifies the failure as "not found"

#### Scenario: A request is malformed

- **WHEN** a request body fails validation
- **THEN** the response carries the shared error structure with a client-error status
- **AND** it names which fields were rejected

#### Scenario: A handler fails unexpectedly

- **WHEN** an unhandled error occurs inside a handler
- **THEN** the response carries the shared error structure with a server-error status
- **AND** the body contains no stack trace, database message, or internal identifier
- **AND** the detail is recorded in the application's logs rather than sent to the client

### Requirement: An owner's plants are readable

The system SHALL expose an owner's plants as a list, and each plant individually with the
history a plant page needs — its observations, its diagnoses, the roadmap steps of its
current plan, and whether feedback is outstanding.

#### Scenario: Listing plants

- **WHEN** an owner requests their plants
- **THEN** every plant they own is returned, newest first
- **AND** each carries its latest diagnosis and its count of outstanding steps
- **AND** no plant belonging to another owner appears

#### Scenario: Reading one plant

- **WHEN** an owner requests one of their plants by identifier
- **THEN** the response carries the plant, its observations, its diagnoses, and its current roadmap steps

#### Scenario: An owner with no plants

- **WHEN** an owner with no plants requests their plants
- **THEN** the response is an empty list rather than an error

### Requirement: A plant can be renamed and removed

The system SHALL allow an owner to rename one of their plants and to delete it. A blank or
whitespace-only name SHALL be rejected: a plant with no name renders as an unlabelled card
with no way back to correct it.

#### Scenario: Renaming a plant

- **WHEN** an owner submits a new name for their plant
- **THEN** the plant's name is changed
- **AND** its species is not changed — what the owner calls a plant and what it is are separate

#### Scenario: Submitting a blank name

- **WHEN** an owner submits a name that is empty or only whitespace
- **THEN** the request is rejected as a client error
- **AND** the plant's name is unchanged

#### Scenario: Deleting a plant

- **WHEN** an owner deletes their plant
- **THEN** the plant and everything hanging off it are removed
- **AND** requesting it afterwards reports that it does not exist

### Requirement: A plant's conversation is readable and can be continued

The system SHALL expose the chat transcript for one plant, oldest first, and accept a new
message which is answered by the agent.

Sending a message is a single request that returns the reply. Streaming the reply as it is
produced is deliberately not part of this requirement.

#### Scenario: Reading a transcript

- **WHEN** an owner requests the messages for their plant
- **THEN** every message for that plant is returned, oldest first
- **AND** each carries its role, its content, and when it was written

#### Scenario: Sending a message

- **WHEN** an owner sends a message about their plant
- **THEN** the response carries the agent's reply
- **AND** both the message and the reply are afterwards present in the transcript

#### Scenario: Sending a message about another owner's plant

- **WHEN** a request sends a message naming a plant belonging to a different owner
- **THEN** the response is 404
- **AND** no message is recorded against that plant

### Requirement: Care actions can be recorded

The system SHALL allow an owner to mark a roadmap step as done, skipped or pending, and to
submit feedback against a diagnosis.

#### Scenario: Marking a step

- **WHEN** an owner marks one of their roadmap steps as done
- **THEN** the step's status changes
- **AND** its completion time is recorded

#### Scenario: Reopening a step

- **WHEN** an owner marks a completed step as pending again
- **THEN** its status changes back
- **AND** its completion time is cleared

#### Scenario: An unknown status

- **WHEN** a request names a status that is not one of the permitted values
- **THEN** the request is rejected as a client error
- **AND** the step is unchanged

#### Scenario: Submitting feedback

- **WHEN** an owner submits feedback against one of their diagnoses
- **THEN** the feedback is recorded
- **AND** that diagnosis afterwards reports that feedback exists

### Requirement: Learned facts are readable and can be forgotten

The system SHALL expose the facts learned about an owner, and SHALL allow any one of them
to be deleted on request. A record of what a system has inferred about a person SHALL be
reachable and removable by that person.

#### Scenario: Listing facts

- **WHEN** an owner requests what has been learned about them
- **THEN** every fact held about them is returned with its source, its confidence and when it was last confirmed
- **AND** no fact about another owner appears

#### Scenario: Forgetting a fact

- **WHEN** an owner asks for one fact to be forgotten
- **THEN** it is removed
- **AND** listing afterwards does not include it

#### Scenario: Forgetting something not held

- **WHEN** an owner asks for a fact that is not held to be forgotten
- **THEN** the request succeeds without error, because the desired state already holds

### Requirement: A photograph is served to its owner

The system SHALL serve a stored photograph by its key, with a content type matching the
stored image, to the owner it belongs to and to nobody else.

#### Scenario: Fetching a photograph

- **WHEN** an owner requests a photograph they uploaded
- **THEN** the image bytes are returned with the content type they were stored under

#### Scenario: Fetching another owner's photograph

- **WHEN** a request names a photograph key belonging to a different owner
- **THEN** the response is 404
- **AND** no bytes are returned

### Requirement: Liveness and readiness are reported separately

The system SHALL expose whether the process is running and, separately, whether it can
serve requests. A process that is alive but cannot reach its database SHALL report itself
live and not ready.

Conflating the two makes a deployment restart a container that is merely waiting for its
database, which turns a delay into a crash loop.

#### Scenario: The process is running and its database is reachable

- **WHEN** liveness and readiness are checked
- **THEN** both report success

#### Scenario: The database is unreachable

- **WHEN** the database cannot be reached and readiness is checked
- **THEN** readiness reports failure
- **AND** liveness still reports success

### Requirement: The interface is versioned and cross-origin requests are configurable

Every endpoint SHALL be served beneath a version prefix, so that a later incompatible
interface can exist alongside this one rather than replacing it underneath a running
client. Permitted cross-origin origins SHALL come from configuration rather than being
fixed in code, and SHALL NOT default to permitting every origin.

#### Scenario: Reaching an endpoint

- **WHEN** any endpoint in this specification is called
- **THEN** its path begins with the version prefix

#### Scenario: A browser client on another origin

- **WHEN** a configured origin makes a cross-origin request
- **THEN** the response permits it
- **AND** an origin that is not configured is not permitted
