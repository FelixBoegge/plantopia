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
