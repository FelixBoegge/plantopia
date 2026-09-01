## ADDED Requirements

### Requirement: A conversation does not grow without bound

The system SHALL limit how much of a conversation is sent to the model, and that limit SHALL
NOT depend on how many turns the conversation has had.

Every turn replays what came before, so an unbounded history is a cost that compounds: turn
*N* pays for turns 1..*N*. A conversation about one plant should not become more expensive to
continue than the diagnosis that started it.

#### Scenario: A long conversation

- **WHEN** a conversation has run long enough to exceed the configured limit
- **THEN** what is sent to the model stays within a bounded size
- **AND** it does not keep growing with each further turn

#### Scenario: A short conversation

- **WHEN** a conversation is below the limit
- **THEN** everything in it is sent to the model unchanged

### Requirement: Stale tool output is dropped before anything a person said

The system SHALL discard the output of older tool calls before condensing the conversation
itself, and SHALL keep the most recent tool results intact.

Tool output is most of the weight and the least of the meaning: a web-search result is roughly
six times the size of what a person and the agent said in the same turn, and a search made
twenty turns ago is not what the current question is about. Discarding it costs nothing and
loses nothing anybody chose to say.

#### Scenario: Old tool output

- **WHEN** the conversation exceeds the limit and contains older tool results
- **THEN** those results are no longer sent to the model
- **AND** it is evident to the model that something was there rather than that nothing happened

#### Scenario: Recent tool output

- **WHEN** tool results are among the most recent exchanges
- **THEN** they are sent to the model in full

#### Scenario: The cheaper measure is enough

- **WHEN** dropping stale tool output brings the conversation within the limit
- **THEN** nothing anybody said is condensed

### Requirement: What a person said is summarised rather than dropped

The system SHALL replace older exchanges with a summary of them when the conversation is still
too large, and SHALL keep the most recent exchanges verbatim.

An agent that silently forgot what it was told would contradict itself and could not be argued
with. Recent turns stay whole because they are what the current question depends on.

#### Scenario: A conversation still too large

- **WHEN** the conversation exceeds the higher limit after tool output has been dropped
- **THEN** older exchanges are replaced by a summary of them
- **AND** the most recent exchanges remain word for word

#### Scenario: Continuing afterwards

- **WHEN** somebody asks a follow-up question after their conversation has been condensed
- **THEN** the reply reflects what was established earlier in it

### Requirement: The stored transcript is never altered

The system SHALL change only what is sent to the model, and SHALL NOT modify, truncate or
delete the conversation it has recorded.

What a person reads is a record of what was said. A record that quietly rewrote itself to save
money would be a different thing from a transcript, and the owner has been promised they can
export it.

#### Scenario: Reading a condensed conversation

- **WHEN** somebody reads a conversation whose context has been condensed
- **THEN** every message appears exactly as it was recorded

#### Scenario: Exporting it

- **WHEN** somebody exports their data after a conversation has been condensed
- **THEN** the export carries the full conversation

#### Scenario: What a reply consulted

- **WHEN** a reply was produced before the conversation was condensed
- **THEN** what that reply consulted is still recorded against it
