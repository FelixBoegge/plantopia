## MODIFIED Requirements

### Requirement: Starting a diagnosis is one deliberate step

The wizard SHALL accept one or more photographs, a name for the plant, whether it lives
indoors or outdoors, and optionally the species, and SHALL start a run only when a person
asks it to. It SHALL NOT ask where the plant is before the run starts.

A run costs real money and takes a minute and a half. Starting one as a side effect of
choosing a file is a bill somebody did not agree to.

The species field is optional and stays optional. Most people asking what is wrong with a
plant do not know what it is — that is frequently why they are asking — so a required field
would stop the people this exists for. Somebody who does know should not have to wait while
two machines work it out.

**Where the plant is is no longer asked here.** The photograph usually knows, and asking
somebody to type what the file already says is asking them to do the machine's work. Where
the photograph does not know, the question is put at the pause the run already makes — one
interruption rather than two, and by then it is one field among several rather than a
question standing on its own.

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

#### Scenario: Nobody is asked where the plant is

- **WHEN** the upload step is shown
- **THEN** it does not ask where the plant is
- **AND** a run can be started without anybody saying

### Requirement: The questions are answered without leaving the run

When a run asks for clarifying answers, the wizard SHALL present them in place, submit them,
and continue showing the same run. Where the run also asks which identification is right, the
wizard SHALL present that choice with the questions and submit it with the answers.

The pause is the middle of the run, not the end of it. Sending somebody elsewhere to answer
and back again would make every run feel like two — and that argument applies twice over to
adding a second pause of its own for the species.

**Where the plant is is asked here, in a field the run has already filled in where it could.**
A place read from the photograph appears as the answer rather than as a suggestion beside an
empty box: it is what will be used, and it is there to be corrected. Somebody who recognises
their own town confirms it by doing nothing, which is the right amount of work for the common
case.

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

#### Scenario: A place the photograph knew

- **WHEN** a place was detected from the photographs
- **THEN** the location field appears already holding it
- **AND** submitting without touching it uses that place

#### Scenario: Correcting the place

- **WHEN** the person changes what the location field holds
- **THEN** the run uses what they left rather than what was detected

#### Scenario: A place nobody knows, outdoors

- **WHEN** no place was detected and the plant lives outdoors
- **THEN** the location field appears empty
- **AND** the answers cannot be submitted until it is filled in

#### Scenario: A place nobody knows, indoors

- **WHEN** no place was detected and the plant lives indoors
- **THEN** the location field appears empty
- **AND** the answers can be submitted with it still empty

#### Scenario: Answering

- **WHEN** the answers are submitted
- **THEN** the wizard continues showing the same run as it resumes
- **AND** the steps that follow are added to the ones before

#### Scenario: Answering twice

- **WHEN** a submission is refused because the run is no longer waiting
- **THEN** the person is shown the run's current state rather than an error
- **AND** no second run is started
