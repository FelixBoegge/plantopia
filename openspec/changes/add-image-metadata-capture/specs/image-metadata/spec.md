## Purpose

What a photograph is allowed to tell the system about itself: when it was taken and roughly
where, what is deliberately thrown away before anything is written down, and what happens
when a photograph says nothing at all — which is most of them.

## ADDED Requirements

### Requirement: A photograph's capture date dates the observation

The system SHALL use the date a photograph declares it was taken as the date of the
observation it belongs to, and SHALL fall back to the upload date when the photograph
declares none.

An observation dated by its upload is wrong whenever somebody photographs a plant and gets
round to uploading it later, and the error is invisible: the two dates are indistinguishable
once the file is stored. It also propagates, because the weather window is anchored on the
observation's date, so a three-day delay diagnoses the plant against weather it never
experienced.

#### Scenario: A photograph that knows when it was taken

- **WHEN** an uploaded photograph declares a capture date
- **THEN** the observation is dated by it
- **AND** the weather window is anchored on it

#### Scenario: A photograph that does not

- **WHEN** an uploaded photograph declares no capture date
- **THEN** the observation is dated by its upload, as before

#### Scenario: Several photographs with different dates

- **WHEN** photographs in one upload declare different capture dates
- **THEN** the earliest is used
- **AND** the others do not change it

#### Scenario: A date that cannot be true

- **WHEN** a declared capture date is in the future, or implausibly old
- **THEN** it is ignored and the upload date is used

### Requirement: A precise position is never stored

The system SHALL coarsen any position read from a photograph before it is recorded, to a
precision no finer than approximately ten kilometres, and SHALL NOT write the original
position to any store or log.

Weather at ten kilometres is indistinguishable from weather at the doorstep, which is the
only thing this position is for. The alternative is a database holding people's home
addresses next to photographs of their interiors — and the only reliable protection against
leaking that is never to have it.

#### Scenario: A photograph carrying a position

- **WHEN** an uploaded photograph declares a position
- **THEN** a coarsened position is recorded
- **AND** the precise position is not recorded anywhere

#### Scenario: Reading a stored position back

- **WHEN** a recorded position is read
- **THEN** it is no more precise than the coarsening allows

### Requirement: A coarse position is given a name a person recognises

The system SHALL attempt to describe a coarsened position by the name of a nearby place, and
SHALL fall back to the position itself when it cannot.

A pair of decimal numbers is not something somebody can confirm or correct. A town name is.

#### Scenario: A place that can be named

- **WHEN** a coarsened position can be resolved to a nearby place
- **THEN** that name is what the owner is shown

#### Scenario: A naming service that is unavailable

- **WHEN** the naming lookup fails, times out, or returns nothing
- **THEN** the coarsened position is used in its place
- **AND** nothing about the upload fails

#### Scenario: Crediting the source

- **WHEN** a place name obtained from an external source is displayed
- **THEN** that source is credited on the same surface

### Requirement: What was detected is shown and can be corrected

The system SHALL show the owner any date or place it detected before a run starts, SHALL
allow either to be changed or cleared, and SHALL use what the owner leaves in place.

Detected is not the same as true. A photograph copied from a message carries its original
sender's metadata; a picture of a plant at somebody else's house carries their address, not
the owner's. Showing what was read is what makes those correctable rather than silently wrong.

#### Scenario: Something was detected

- **WHEN** a date or place is detected from an upload
- **THEN** it is shown before the run is started
- **AND** it can be edited or removed

#### Scenario: Correcting it

- **WHEN** the owner changes or clears a detected value
- **THEN** the run uses what they left, not what was detected

#### Scenario: The photograph already answered a question

- **WHEN** a place was detected for an outdoor plant
- **THEN** the run does not also ask the owner where the plant is

### Requirement: A photograph that says nothing changes nothing

The system SHALL complete an upload and a diagnosis identically to today when a photograph
carries no metadata, carries metadata that cannot be read, or carries metadata that is
malformed.

Most photographs are in this position. Messaging apps strip metadata, browser camera capture
frequently has none, and a screen grab never did. This is enrichment, and the path without it
is the ordinary path rather than a fallback.

#### Scenario: No metadata at all

- **WHEN** a photograph carries no metadata
- **THEN** the upload and the run behave exactly as they did before this existed

#### Scenario: Metadata that cannot be parsed

- **WHEN** a photograph's metadata is malformed or unreadable
- **THEN** it is ignored
- **AND** the upload is not refused for it

#### Scenario: A photograph that is not accepted

- **WHEN** an upload is refused by validation
- **THEN** nothing is read from it
