# photo-storage Specification

## Purpose
Defines how photographs uploaded by an owner are stored, addressed and retrieved, and what the
diagnosis pipeline carries in their place while it runs.

## Requirements

### Requirement: Photographs are addressed by an opaque key

The system SHALL identify each stored photograph by a key that callers treat as opaque. Callers
SHALL NOT depend on a key's structure, and no caller SHALL construct a key itself. A key SHALL
NOT encode a location, a filename, an ordering, or a count.

#### Scenario: Storing a photograph

- **WHEN** an owner uploads a photograph
- **THEN** the system returns a key that retrieves exactly those bytes
- **AND** the key is usable without knowing where or how the bytes are held

#### Scenario: Changing where photographs are held

- **WHEN** the underlying storage medium is replaced
- **THEN** callers continue to store and retrieve photographs unchanged
- **AND** no caller requires modification to accommodate the new medium

### Requirement: Retrieving a photograph requires ownership

The system SHALL scope photograph retrieval to the owner who uploaded it. A key belonging to
another owner SHALL behave exactly as an unknown key.

#### Scenario: Requesting another owner's photograph

- **WHEN** an owner presents a valid key belonging to a different owner
- **THEN** the system reports that no such photograph exists
- **AND** the bytes are not returned

### Requirement: Run state carries keys, not image bytes

The agent's run state SHALL reference photographs by key only. Image bytes SHALL NOT be embedded
in run state at any point, so that the cost of persisting run state does not scale with the size
of the photographs a diagnosis was given.

#### Scenario: Completing a diagnosis with large photographs

- **WHEN** a diagnosis runs to completion on four photographs of several megabytes each
- **THEN** the persisted run state for that diagnosis contains no image bytes
- **AND** its total size is a small fraction of the size of the photographs

### Requirement: The model sees what the owner photographed

The system SHALL deliver photographs to the vision model with their subject and framing
intact, applying the orientation the photograph itself declares and capping the long edge
at a configured maximum. It SHALL NOT crop them, and it SHALL NOT recompress a photograph
that already fits within that cap.

The cap exists because the vision models downscale above it themselves, so pixels beyond it
are billed and discarded. It is a cost bound, not a judgement about what the model can see:
no measurement in this project reaches the vision layer (`M19`), so nothing here claims the
cap leaves a diagnosis unchanged.

Applying that orientation rewrites the file, and rewriting it destroys the metadata block —
the orientation tag is cleared deliberately, so nothing turns the image twice, and the rest
of the block frequently goes with it. So anything the system wants to know from a photograph
SHALL be read from the bytes as uploaded, before that normalisation.

This is an ordering constraint rather than a preference, and it is easy to reverse by
accident: the two operations look independent, both are one line, and swapping them produces
photographs that work perfectly and simply never carry a date or a place.

#### Scenario: A photograph declaring a rotation

- **WHEN** a photograph whose metadata declares a rotation is uploaded
- **THEN** the pixels delivered to the model are turned to match that declaration
- **AND** no other alteration is made to the image

#### Scenario: Reading what a photograph declares

- **WHEN** metadata is read from an upload
- **THEN** it is read from the bytes as they arrived
- **AND** not from the bytes that were stored after normalisation

#### Scenario: A photograph whose orientation was applied

- **WHEN** a photograph is normalised
- **THEN** what was read from it beforehand is unaffected by the normalisation

### Requirement: An owner's photographs can be removed completely

The system SHALL be able to delete every photograph belonging to one owner, such that the bytes
are no longer retrievable by any key.

#### Scenario: Removing everything for one owner

- **WHEN** deletion of an owner's photographs is requested
- **THEN** no key belonging to that owner returns bytes afterwards
- **AND** photographs belonging to other owners are unaffected

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
