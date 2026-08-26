## MODIFIED Requirements

### Requirement: A plant's conversation is readable and can be continued

The system SHALL expose the chat transcript for one plant, oldest first, and accept a new
message which is answered by the agent.

Sending a message SHALL be possible in two forms, and both SHALL leave the same transcript
behind: a single request that returns the completed reply, and a streamed form that
delivers the reply as it is produced. Which form a client uses SHALL NOT change what is
recorded.

The single-request form remains, and remains the simpler thing to call. It is what the
evaluation harness and every non-interactive caller use, and a streaming-only interface
would make them assemble a reply from fragments in order to ignore the fragments.

#### Scenario: Reading a transcript

- **WHEN** an owner requests the messages for their plant
- **THEN** every message for that plant is returned, oldest first
- **AND** each carries its role, its content, and when it was written

#### Scenario: Sending a message

- **WHEN** an owner sends a message about their plant
- **THEN** the response carries the agent's reply
- **AND** both the message and the reply are afterwards present in the transcript

#### Scenario: Sending a message and watching the reply arrive

- **WHEN** an owner sends a message on the streamed form
- **THEN** the reply is delivered progressively rather than at the end
- **AND** the message and the completed reply are afterwards present in the transcript
- **AND** the transcript is indistinguishable from one left by the single-request form

#### Scenario: Sending a message about another owner's plant

- **WHEN** a request sends a message naming a plant belonging to a different owner
- **THEN** the response is 404
- **AND** no message is recorded against that plant

## ADDED Requirements

### Requirement: Long-running work is addressed as a resource, not as a slow request

The system SHALL NOT expose any endpoint that performs a model-driven diagnosis within the
lifetime of a single request. Work of that duration SHALL be started, addressed and watched
as a resource.

Ninety seconds inside one request is a connection that proxies close, that a reload
abandons, and that has no way to report what it is doing. It also cannot express a pause
for clarifying answers as anything other than a failure.

#### Scenario: Asking for a diagnosis

- **WHEN** a client asks for a diagnosis
- **THEN** it is given a run to watch rather than a reply to wait for

#### Scenario: No synchronous equivalent exists

- **WHEN** the interface is enumerated
- **THEN** no endpoint performs a diagnosis and returns its result in the same response
