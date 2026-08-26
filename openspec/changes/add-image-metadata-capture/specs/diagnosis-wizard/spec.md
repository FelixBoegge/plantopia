## MODIFIED Requirements

### Requirement: Starting a diagnosis is one deliberate step

The wizard SHALL accept one or more photographs, a name for the plant, where it lives, and
optionally the species, and SHALL start a run only when a person asks it to. Where a
photograph declares when or where it was taken, the wizard SHALL show what was detected and
allow it to be corrected or cleared before the run starts.

A run costs real money and takes a minute and a half. Starting one as a side effect of
choosing a file is a bill somebody did not agree to.

The species field is optional and stays optional. Most people asking what is wrong with a
plant do not know what it is — that is frequently why they are asking — so a required field
would stop the people this exists for. Somebody who does know should not have to wait while
two machines work it out.

What was detected is shown rather than applied quietly, and for a reason beyond politeness: a
photograph forwarded from a message carries its sender's date and place, not the uploader's.
Silently dating an observation to somebody else's Tuesday, or placing a plant in somebody
else's town, produces a confident wrong answer that nothing downstream can question.

#### Scenario: Starting

- **WHEN** a person supplies photographs and confirms
- **THEN** a run is started and the wizard begins showing its progress

#### Scenario: Choosing a photograph

- **WHEN** a person selects photographs
- **THEN** nothing is started until they confirm
- **AND** what they selected is shown back to them

#### Scenario: A photograph that cannot be used

- **WHEN** the server refuses an upload
- **THEN** the reason is shown and the person can choose another
- **AND** no run appears in their history

#### Scenario: Naming the species

- **WHEN** a person supplies a species before starting
- **THEN** it is carried into the run as one candidate among the identified ones

#### Scenario: Not naming the species

- **WHEN** the species field is left empty
- **THEN** the run starts and behaves exactly as it did before the field existed

#### Scenario: A photograph that knows when and where

- **WHEN** a chosen photograph declares a capture date or a position
- **THEN** what was detected is shown before the run is started
- **AND** each can be corrected or cleared

#### Scenario: Correcting what was detected

- **WHEN** the person changes or clears a detected value
- **THEN** the run is started with what they left rather than what was detected

#### Scenario: A photograph that knows nothing

- **WHEN** no photograph declares a date or a position
- **THEN** the wizard shows nothing about either
- **AND** the run starts exactly as it did before

#### Scenario: An outdoor plant whose photograph gave its place

- **WHEN** a place was detected and the plant lives outdoors
- **THEN** the run does not stop to ask where the plant is
