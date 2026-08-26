# run-streaming Specification

## Purpose
Defines how a client watches work in progress: what it is told while a run or a chat reply
is being produced, in what order, what happens when the connection drops part-way, and what
about that stream is a contract rather than an implementation detail.

## Requirements

### Requirement: Progress is published as an ordered stream of events

The system SHALL publish an event for each step of a run's progress, SHALL give each event
a sequence number that increases within its run, and SHALL make the stream readable by the
run's owner.

A stream whose ordering is not guaranteed cannot be replayed, and a stream that cannot be
replayed is one a dropped connection loses.

#### Scenario: Watching a run

- **WHEN** an owner opens the event stream for their run
- **THEN** events arrive as the run progresses
- **AND** each carries a sequence number greater than the one before it

#### Scenario: Watching another owner's run

- **WHEN** a request opens the event stream for a run belonging to somebody else
- **THEN** the response is 404
- **AND** no events are delivered

#### Scenario: Watching without a session

- **WHEN** a request opens an event stream without a valid session
- **THEN** it is refused

### Requirement: A dropped connection loses nothing

The system SHALL persist every event before publishing it, and SHALL, when a client
reconnects naming the last event it received, deliver every event after that one before
resuming live delivery.

The owner has already paid for the run and waited for it. A reload, a tunnel, or a laptop
lid must not cost them the result.

#### Scenario: Reconnecting mid-run

- **WHEN** a client reconnects naming the last event it received
- **THEN** it receives every event since, in order
- **AND** then continues to receive new ones on the same connection

#### Scenario: Reconnecting after the run finished

- **WHEN** a client opens the stream for a run that has already reached a terminal status
- **THEN** it receives the run's events from the beginning
- **AND** the stream then closes rather than waiting for events that will never come

#### Scenario: Opening a stream from the start

- **WHEN** a client opens the stream without naming a last event
- **THEN** it receives the run's events from the beginning

### Requirement: The stream survives the pause for clarifying answers

The system SHALL keep an event stream open while its run is `awaiting_answers`, and SHALL
continue delivering events on the same connection once the run resumes.

The pause is the middle of the run, not the end of it. A client that has to reconnect to
see the second half has to be written as though every run happens twice.

#### Scenario: The run pauses

- **WHEN** a run reaches `awaiting_answers` while a client is watching
- **THEN** an event carries the questions
- **AND** the connection remains open

#### Scenario: The run resumes

- **WHEN** the run is answered
- **THEN** events for the remaining steps arrive on the same connection
- **AND** their sequence numbers continue from the ones before the pause

### Requirement: An idle stream is kept alive

The system SHALL send periodic keep-alive traffic on an open stream that has no events to
deliver.

A run can spend a minute inside one model call. Intermediaries close connections that look
idle, and the client cannot distinguish that from a run that stopped.

#### Scenario: A long step

- **WHEN** a stream has delivered no event for longer than the keep-alive interval
- **THEN** keep-alive traffic is sent
- **AND** it is not delivered to the client as an event

### Requirement: Events describe progress in the product's language, not the graph's

The system SHALL NOT expose internal node, function or module names in an event. Each event
SHALL carry a stable machine-readable kind and a human-readable description of what is
happening.

A client rendering "identify_plant" is a client coupled to the graph's internals, and
renaming a node then becomes a breaking change to the interface.

#### Scenario: A step begins

- **WHEN** an event describes a step of the run
- **THEN** it carries a stable identifier for that step and a description a person can read
- **AND** no internal name appears in it

#### Scenario: A step that has no meaningful description

- **WHEN** a step occurs that has no description defined for it
- **THEN** the event is still delivered with its sequence number and a neutral description
- **AND** no internal name is substituted

### Requirement: A failure ends the stream as an event, not as a broken connection

The system SHALL deliver a terminal event stating how a run ended, and SHALL close the
stream afterwards.

A connection that simply stops is indistinguishable from a network failure, and a client
that cannot tell them apart must either retry forever or give up on runs that succeeded.

#### Scenario: A run completes

- **WHEN** a run reaches `completed`
- **THEN** a terminal event says so and names the diagnosis produced
- **AND** the stream closes

#### Scenario: A run fails

- **WHEN** a run reaches `failed`
- **THEN** a terminal event says so, carrying a description that exposes no internal detail
- **AND** the stream closes

#### Scenario: A run is cancelled while being watched

- **WHEN** a run is cancelled
- **THEN** a terminal event says so
- **AND** the stream closes

### Requirement: A chat reply can be watched as it is produced

The system SHALL offer a streaming form of sending a chat message, carrying the reply as it
is produced and the lookups the agent performs as they happen.

The existing single-request form SHALL continue to work unchanged.

Chat has the same problem in miniature: a message that consults the corpus and then the web
is silent for several seconds, and silence reads as a failure.

#### Scenario: Sending a message and watching the reply

- **WHEN** an owner sends a message on the streaming endpoint
- **THEN** the reply arrives progressively
- **AND** the message and the completed reply are afterwards in the transcript

#### Scenario: Lookups are visible

- **WHEN** the agent consults a source while answering
- **THEN** an event says so before the reply continues

#### Scenario: Sending a message about another owner's plant

- **WHEN** a streaming request names a plant belonging to a different owner
- **THEN** the response is 404
- **AND** nothing is recorded against that plant

#### Scenario: The connection drops mid-reply

- **WHEN** the connection is lost while a reply is being produced
- **THEN** the reply is still recorded in the transcript
- **AND** the owner can read it by fetching the transcript
