# diagnosis-wizard Specification

## Purpose
Defines the flow that produces a diagnosis: choosing photographs, watching the agent work,
answering what it asks part-way through, and reading the result — and what happens to work
somebody has already paid for when the connection between them and it fails.

## Requirements

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

### Requirement: The agent's progress is visible while it works

The wizard SHALL show each step as it happens, in the words the server sends, and SHALL
make clear that work is continuing between steps.

This is the whole reason the run reports steps. A spinner over ninety seconds tells somebody
only that nothing has crashed yet, and it hid the most interesting thing this system does.

#### Scenario: Watching a run work

- **WHEN** a run reports a step
- **THEN** it appears in the panel as it arrives
- **AND** earlier steps remain visible

#### Scenario: A long step

- **WHEN** no step has arrived for some time
- **THEN** the interface still indicates the run is working
- **AND** does not suggest it has stopped

#### Scenario: What the panel never shows

- **WHEN** any step is displayed
- **THEN** it shows the description the server sent
- **AND** no internal name from the agent appears

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

### Requirement: A lost connection does not lose the run

The wizard SHALL reconnect to a run whose stream has dropped, resuming from the last event
it received, and SHALL be able to show a run opened fresh in another tab or after a reload.

The person has already paid for the run and waited for it. A closed laptop must cost them
the view, not the diagnosis.

#### Scenario: The connection drops mid-run

- **WHEN** the stream fails while a run is working
- **THEN** the wizard reconnects and continues from where it left off
- **AND** no step is shown twice

#### Scenario: Reloading during a run

- **WHEN** a person reloads while a run is working
- **THEN** the wizard shows the steps so far and continues

#### Scenario: Opening a run that has already finished

- **WHEN** a person opens a run that completed while they were away
- **THEN** its result is shown without waiting

#### Scenario: A run that failed while away

- **WHEN** a person returns to a run that failed
- **THEN** they are told it failed and can start another

### Requirement: The result is a ranked differential, not a verdict

The wizard SHALL present the candidates in order with their confidence, the evidence for and
against each, and the quick confirming test where one exists. It SHALL NOT present the
leading candidate as the only answer.

The system is frequently right about the top candidate and not always, and the tail of the
differential is measurably less stable than its head. Showing one answer would present a
ranking as a fact.

#### Scenario: Reading a result

- **WHEN** a diagnosis is shown
- **THEN** every candidate is listed in order with its confidence
- **AND** each carries the evidence for and against it

#### Scenario: A confirming test

- **WHEN** a candidate has a quick confirming test
- **THEN** it is shown with that candidate

#### Scenario: The care plan

- **WHEN** a diagnosis has produced a plan
- **THEN** its steps are shown as a dated checklist that can be marked off

#### Scenario: A run that produced no diagnosis

- **WHEN** a run finished because the photograph could not be used
- **THEN** the reason is shown
- **AND** it is not presented as a failure of the system

### Requirement: A finished run leads to the plant it produced

When a run completes, the wizard SHALL offer the plant the diagnosis belongs to.

A person who has just diagnosed a plant is one step from wanting its history, its plan and
its conversation, and a result screen that is a dead end sends them back to a grid to hunt
for what they just made.

#### Scenario: After a diagnosis

- **WHEN** a run completes
- **THEN** the plant it produced or updated can be opened from the result

### Requirement: A run can be abandoned from the wizard

The wizard SHALL let a person stop a run in progress, and SHALL say what stopping does.

#### Scenario: Abandoning

- **WHEN** a person stops a run
- **THEN** the wizard reports it as cancelled and stops showing progress

#### Scenario: What stopping does not undo

- **WHEN** a person is offered the option to stop
- **THEN** the interface does not imply that work already done is unbilled
