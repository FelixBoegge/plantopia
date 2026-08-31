# image-metadata Specification

## Purpose
What a photograph is allowed to tell the system about itself: when it was taken and roughly
where, what is deliberately thrown away before anything is written down, and what happens
when a photograph says nothing at all — which is most of them.

## Requirements

### Requirement: Every diagnosis carries a date somebody has seen

The system SHALL ask when the photograph was taken on every diagnosis, SHALL offer the date
the photograph declared or today's date as the answer, SHALL require an answer, and SHALL
anchor the weather window and date the observation by it.

An observation dated by its upload is wrong whenever somebody photographs a plant and gets
round to uploading it later, and the error is invisible: the two dates are indistinguishable
once the file is stored. It propagates, because the weather window is anchored on the
observation's date — a three-day delay diagnoses the plant against weather it never had.

**Always asked, and never empty.** Asked even when the photograph declared a date, because a
photograph forwarded from a message carries its sender's and one from a camera with an unset
clock carries nonsense — neither is distinguishable from a right answer automatically. Asked
even when it declared nothing, because today is then a guess, and a guess somebody can see is
a guess somebody can fix. Never empty, because an empty date is not a smaller answer than a
wrong one: it is no weather at all.

#### Scenario: A photograph that knows when it was taken

- **WHEN** an uploaded photograph declares a capture date
- **THEN** that date is offered as the answer
- **AND** where it came from is stated

#### Scenario: A photograph that does not

- **WHEN** an uploaded photograph declares no capture date
- **THEN** today's date is offered as the answer
- **AND** it is stated that the photograph did not say

#### Scenario: Accepting what was offered

- **WHEN** the owner submits without changing the date
- **THEN** the observation is dated by it
- **AND** the weather window is anchored on it

#### Scenario: Correcting it

- **WHEN** the owner gives a different date
- **THEN** the observation and the weather window use theirs

#### Scenario: Leaving it empty

- **WHEN** the owner clears the date
- **THEN** the answers cannot be submitted until one is given

#### Scenario: Several photographs with different dates

- **WHEN** photographs in one upload declare different capture dates
- **THEN** the earliest is offered
- **AND** the others do not change it

#### Scenario: A date that cannot be true

- **WHEN** a declared capture date is in the future, or implausibly old
- **THEN** it is ignored and today's date is offered instead

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

#### Scenario: The stored photograph itself

- **WHEN** a photograph declaring a position is stored
- **THEN** the stored copy declares none
- **AND** its picture is unchanged

#### Scenario: A position that cannot be removed

- **WHEN** a position cannot be taken out of an upload
- **THEN** the upload is refused rather than stored

### Requirement: A coarse position is given a name a person recognises

The system SHALL attempt to describe a coarsened position by the name of a nearby place, and
SHALL fall back to the position itself when it cannot. Where the owner accepts that name, the
system SHALL use the position rather than resolving the name back into one.

A pair of decimal numbers is not something somebody can confirm or correct. A town name is.
So the name exists for the person, and the position for the machinery — and a position that
was turned into a name and then back into a position has made two round trips through a
geocoder to arrive where it started, losing a little at each end.

The name still wins whenever it was *changed*. A correction that lost to the coordinates
behind it would be a correction nobody could make: somebody who fixes a wrong town and
watches the diagnosis proceed on the wrong weather anyway has been given a control that does
nothing.

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

#### Scenario: The name was accepted

- **WHEN** the owner leaves the detected place as it was offered
- **THEN** the position it came from is what is used to look anything up

#### Scenario: The name was corrected

- **WHEN** the owner replaces the detected place
- **THEN** what they typed is resolved, and the position it came from is not used

### Requirement: A detected place is offered as the answer, not imposed as a fact

The system SHALL put a place detected from a photograph into the location question as its
answer, SHALL allow that answer to be changed, and SHALL use whatever the owner leaves.

Detected is not the same as true. A photograph forwarded from a message carries its original
sender's position; a picture taken at somebody else's house carries theirs. Neither can be
told apart from the owner's own automatically, so the correction has to be available — and it
has to be somewhere a person will see it, which is the pause they are already answering
questions at rather than a screen they clicked past.

Offered *as the answer* rather than as a suggestion beside an empty field, because that is
what it is: it will be used unless somebody says otherwise. A suggestion asks the common case
to do work; a filled field asks only the uncommon one.

#### Scenario: A place was detected

- **WHEN** a place is detected from an upload
- **THEN** the location question is asked with that place as its answer

#### Scenario: Leaving it alone

- **WHEN** the owner submits without changing the detected place
- **THEN** the run proceeds on that place

#### Scenario: Correcting it

- **WHEN** the owner changes the location answer
- **THEN** the run uses what they left, not what was detected

#### Scenario: Nothing was detected

- **WHEN** no place is detected from an upload
- **THEN** the location question is asked with no answer filled in

### Requirement: An outdoor plant must end up with a place

The system SHALL require an answer to the location question when the plant lives outdoors and
no place was detected, and SHALL treat the answer as optional when it lives indoors.

Weather frequently is the diagnosis for an outdoor plant — a late frost, a heatwave, three
weeks of rain — and without a place there is no weather to read. Indoors the connection is
weak enough that demanding an answer would be demanding it for nothing.

#### Scenario: Outdoors with nothing detected

- **WHEN** an outdoor plant's run pauses and no place was detected
- **THEN** the answers cannot be submitted until a place is given

#### Scenario: Outdoors with a place detected

- **WHEN** an outdoor plant's run pauses and a place was detected
- **THEN** the requirement is already satisfied by the detected answer

#### Scenario: Indoors

- **WHEN** an indoor plant's run pauses
- **THEN** the answers can be submitted with no place given

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

### Requirement: A photograph old enough to mislead says so

The system SHALL compare a photograph's capture date against the present, SHALL tell the
owner when the difference exceeds a configured threshold, SHALL tell the agent so that the
diagnosis can account for it, and SHALL complete the diagnosis either way.

A plant changes. A photograph three weeks old shows a plant that no longer exists, and a
diagnosis of it is a diagnosis of the past presented as advice about the present — confident,
detailed, and about something that has since recovered or got considerably worse.

Said rather than refused. Somebody whose plant died last week and who has only last week's
photograph is exactly who needs an answer, and refusing them one to protect the accuracy of a
number would be protecting the wrong thing.

#### Scenario: A photograph older than the threshold

- **WHEN** the capture date is further from today than the threshold allows
- **THEN** the owner is told, where they can still act on it
- **AND** they are asked for a more recent photograph

#### Scenario: The diagnosis knows

- **WHEN** a diagnosis is made from a photograph older than the threshold
- **THEN** the agent is told how old it is
- **AND** the result says the answer is less reliable for it

#### Scenario: A recent photograph

- **WHEN** the capture date is within the threshold
- **THEN** nothing is said about it

#### Scenario: Carrying on anyway

- **WHEN** the owner proceeds with an old photograph
- **THEN** the diagnosis completes

#### Scenario: A date the owner corrected

- **WHEN** the owner changes the capture date
- **THEN** the age is judged by what they left, not by what the camera said
