## ADDED Requirements

### Requirement: A person choosing between machine judgements is told what they are choosing between

Where the interface asks somebody to choose between candidates produced by different methods,
it SHALL show, for each candidate, which method produced it and how confident that method is,
and SHALL make plain that not choosing is permitted.

This is the first place in the application where a person is asked to arbitrate between two
machines. A list of names with no provenance asks somebody to pick on nothing, and a required
choice makes "I do not know" — the honest answer for most people asking what is wrong with
their plant — impossible to give. Confidence is stated in words as well as any number, on the
same reasoning that keeps a probability from being read as a certainty.

#### Scenario: Choosing between identifications

- **WHEN** more than one identification is offered
- **THEN** each candidate shows the method that produced it and how confident it is
- **AND** the person can submit without choosing

#### Scenario: Reading a confidence

- **WHEN** a candidate's confidence is shown
- **THEN** it is expressed in words, not as a bare number

#### Scenario: Choosing by keyboard

- **WHEN** a person uses only a keyboard
- **THEN** every candidate is reachable and selectable
- **AND** which candidate is selected is conveyed by more than colour

### Requirement: Third-party data is credited where it is shown

Where the interface displays data obtained from an external service whose terms require
attribution, it SHALL display that attribution on the same surface.

A term of use honoured on the one screen somebody remembered is not honoured. Tying the
attribution to the data rather than to a page means a new screen showing that data cannot
quietly omit it.

#### Scenario: Showing an attributed result

- **WHEN** a result from an attributed service is displayed
- **THEN** the attribution appears on the same surface

#### Scenario: Showing nothing from that service

- **WHEN** no result from the service is displayed
- **THEN** no attribution appears
