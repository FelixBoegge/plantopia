## ADDED Requirements

### Requirement: A single photograph can be removed

The system SHALL be able to delete one stored photograph by its key, and SHALL report
whether there was one to delete. A key that is unknown, or that belongs to a different
owner, SHALL be treated identically — nothing is removed, and the answer does not
distinguish the two.

Deleting a plant deletes its photographs, and nothing else relates those bytes back to
the plant: an upload exists before the plant it documents does, so a photograph is owned
by a person rather than by a plant and no cascade reaches it. Without this, "delete my
plant" would leave the photographs behind.

#### Scenario: Removing a photograph

- **WHEN** an owner's photograph is deleted by key
- **THEN** it is reported as removed
- **AND** fetching that key afterwards returns nothing

#### Scenario: Removing a photograph that is not there

- **WHEN** a key that matches no photograph is deleted
- **THEN** it is reported as not removed
- **AND** no error is raised, because the desired state already holds

#### Scenario: Removing another owner's photograph

- **WHEN** a key belonging to a different owner is deleted
- **THEN** it is reported as not removed
- **AND** the photograph is still retrievable by its own owner
- **AND** the answer is indistinguishable from the answer for a key that never existed
