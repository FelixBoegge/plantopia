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

### Requirement: The model sees what the owner uploaded

The system SHALL deliver photographs to the vision model with their original pixel data intact,
apart from applying the orientation the photograph itself declares. It SHALL NOT downscale,
recompress or crop them.

#### Scenario: A photograph declaring a rotation

- **WHEN** a photograph whose metadata declares a rotation is uploaded
- **THEN** the pixels delivered to the model are turned to match that declaration
- **AND** no other alteration is made to the image

### Requirement: An owner's photographs can be removed completely

The system SHALL be able to delete every photograph belonging to one owner, such that the bytes
are no longer retrievable by any key.

#### Scenario: Removing everything for one owner

- **WHEN** deletion of an owner's photographs is requested
- **THEN** no key belonging to that owner returns bytes afterwards
- **AND** photographs belonging to other owners are unaffected
