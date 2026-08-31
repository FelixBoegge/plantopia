## MODIFIED Requirements

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

## ADDED Requirements

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
