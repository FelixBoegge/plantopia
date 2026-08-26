## MODIFIED Requirements

### Requirement: The model sees what the owner uploaded

The system SHALL deliver photographs to the vision model with their original pixel data
intact, apart from applying the orientation the photograph itself declares. It SHALL NOT
downscale, recompress or crop them.

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
