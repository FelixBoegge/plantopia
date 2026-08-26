## MODIFIED Requirements

### Requirement: Starting a diagnosis is one deliberate step

The wizard SHALL accept one or more photographs, a name for the plant, where it lives, and
optionally the species, and SHALL start a run only when a person asks it to.

A run costs real money and takes a minute and a half. Starting one as a side effect of
choosing a file is a bill somebody did not agree to.

The species field is optional and stays optional. Most people asking what is wrong with a
plant do not know what it is — that is frequently why they are asking — so a required field
would stop the people this exists for. Somebody who does know should not have to wait while
two machines work it out.

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

### Requirement: The questions are answered without leaving the run

When a run asks for clarifying answers, the wizard SHALL present them in place, submit them,
and continue showing the same run. Where the run also asks which identification is right, the
wizard SHALL present that choice with the questions and submit it with the answers.

The pause is the middle of the run, not the end of it. Sending somebody elsewhere to answer
and back again would make every run feel like two — and that argument applies twice over to
adding a second pause of its own for the species.

#### Scenario: Being asked

- **WHEN** a run reports that it needs answers
- **THEN** the questions appear in the wizard
- **AND** the progress already shown remains

#### Scenario: Being asked which plant it is

- **WHEN** a run offers more than one identification
- **THEN** the candidates appear with the questions, each with where it came from and how
  confident it is
- **AND** choosing one is not required in order to submit

#### Scenario: When the identifications agree

- **WHEN** a run offers only one identification
- **THEN** no choice is presented and the questions appear alone

#### Scenario: Answering

- **WHEN** the answers are submitted
- **THEN** the wizard continues showing the same run as it resumes
- **AND** the steps that follow are added to the ones before

#### Scenario: Answering twice

- **WHEN** a submission is refused because the run is no longer waiting
- **THEN** the person is shown the run's current state rather than an error
- **AND** no second run is started
