## MODIFIED Requirements

### Requirement: An owner's plants are readable

The system SHALL expose an owner's plants as a list, and each plant individually with the
history a plant page needs — its observations, its diagnoses, the roadmap steps of its
current plan, and whether feedback is outstanding.

An observation SHALL carry what it knows about itself: when its photographs were taken, where
they were taken, and the weather recorded against it. All three are held on the observation
already and none of them were readable; the weather was reachable only through a diagnosis
made from that observation, which is the wrong way round for a history whose spine is the
observations themselves.

Each is optional and absent means unknown, not zero. An observation recorded before any of
these were captured says so by omitting them.

#### Scenario: Listing plants

- **WHEN** an owner requests their plants
- **THEN** every plant they own is returned, newest first
- **AND** each carries its latest diagnosis and its count of outstanding steps
- **AND** no plant belonging to another owner appears

#### Scenario: Reading one plant

- **WHEN** an owner requests one of their plants by identifier
- **THEN** the response carries the plant, its observations, its diagnoses, and its current roadmap steps

#### Scenario: What an observation carries

- **WHEN** an observation is returned
- **THEN** it carries the date its photographs were taken, where they were taken, and the weather recorded against it, wherever each is known

#### Scenario: An observation that knows none of it

- **WHEN** an observation has no capture date, no position and no recorded weather
- **THEN** those fields are absent rather than defaulted
- **AND** the observation is still returned

#### Scenario: An owner with no plants

- **WHEN** an owner with no plants requests their plants
- **THEN** the response is an empty list rather than an error
