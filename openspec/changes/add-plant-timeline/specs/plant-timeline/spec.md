## ADDED Requirements

### Requirement: A plant's history is one chronological sequence

The system SHALL present a plant's observations, diagnoses and treatment steps as a single
sequence ordered by when each happened, rather than as separate lists grouped by kind.

The question an owner has after the second diagnosis is whether the plant is getting better.
That question is about *sequence* — what was seen, what it was judged to be, what was done,
what happened next — and four lists side by side make the reader do the interleaving.

#### Scenario: A plant with a history

- **WHEN** an owner opens a plant that has observations, diagnoses and treatment steps
- **THEN** all of them appear in one sequence, ordered by when they happened
- **AND** each event says what kind of event it is

#### Scenario: A plant with nothing yet

- **WHEN** an owner opens a plant with no history beyond its first upload
- **THEN** the page says so plainly rather than showing an empty frame

#### Scenario: Reaching the diagnosis behind an event

- **WHEN** an owner selects a diagnosis on the timeline
- **THEN** they reach that diagnosis in full

### Requirement: Events are dated by when they happened, not when they were recorded

The system SHALL date an observation by the capture date of its photographs where one is
known, and by the upload otherwise.

These differ for anybody who does not upload immediately, and a history ordered by upload puts
events in an order the plant never experienced — the same defect the weather window had before
capture dates were read.

#### Scenario: A photograph uploaded later than it was taken

- **WHEN** an observation carries a capture date earlier than its upload
- **THEN** the timeline places and dates it by the capture date

#### Scenario: An observation with no capture date

- **WHEN** an observation carries no capture date
- **THEN** it is placed and dated by its upload
- **AND** nothing claims a capture date it does not have

### Requirement: Weather is shown where it explains the plant

The system SHALL show the recorded daily weather for an observation that carries one, and
SHALL show nothing where none was recorded.

Weather frequently *is* the diagnosis for an outdoor plant, and a person reads a series better
than a prose summary of one. A diagnosis made in a fortnight of frost is a different thing from
the same diagnosis made in a mild week, and only the series says which.

#### Scenario: An observation with a recorded series

- **WHEN** an observation carries a daily weather series
- **THEN** that series is shown against it, day by day

#### Scenario: An observation with no recorded series

- **WHEN** an observation carries no weather
- **THEN** no weather is shown for it
- **AND** nothing is drawn as zero or as absent-meaning-none

#### Scenario: Weather without colour

- **WHEN** weather is shown
- **THEN** its values are available to somebody who cannot distinguish the colours used
- **AND** to somebody using a screen reader

### Requirement: A chat escalation is an event in the plant's history

The system SHALL show, as an event, each occasion the agent judged a described symptom to
warrant a fresh look, with the reason it gave.

Everything else a conversation contains belongs to the conversation. This one does not: it is
the agent saying the plant's condition has changed enough to need looking at, which is exactly
what a history is for.

#### Scenario: The agent flagged a fresh look

- **WHEN** a chat reply flagged that a fresh diagnosis was warranted
- **THEN** that appears on the timeline at the time it happened
- **AND** the reason given is shown

#### Scenario: An ordinary conversation

- **WHEN** a chat exchange raised no such flag
- **THEN** nothing from it appears on the timeline

### Requirement: A history missing most of its data still reads

The system SHALL render an event from whatever it holds, and SHALL NOT require any optional
part of it.

Most observations recorded before this predate capture dates and weather entirely. A timeline
that needed them would be a timeline that worked only for plants photographed after a
particular week.

#### Scenario: An observation from before the newer columns existed

- **WHEN** an observation has no capture date, no position and no weather
- **THEN** it still appears, dated by its upload, with what it does have

#### Scenario: A diagnosis whose species provenance was never recorded

- **WHEN** a diagnosis carries no record of how its species was identified
- **THEN** it still appears
- **AND** nothing claims a provenance it does not have
