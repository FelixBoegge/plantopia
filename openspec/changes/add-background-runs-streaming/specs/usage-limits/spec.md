## MODIFIED Requirements

### Requirement: A person has a ceiling on how much they can run

The system SHALL refuse to start a run when the owner has reached the allowance for their
tier within the current period. The refusal SHALL carry enough structure for an interface
to explain it — what the limit is, how much is used, and when it resets — rather than a
bare error.

This ceiling SHALL be applied at the point a run is requested, before the run is created
and before any model call is made. A run that is refused SHALL NOT exist afterwards: it
SHALL NOT appear among the owner's runs, and SHALL NOT count towards the allowance that
refused it.

#### Scenario: Within the allowance

- **WHEN** an owner below their allowance starts a run
- **THEN** it proceeds

#### Scenario: At the allowance

- **WHEN** an owner who has reached their allowance starts a run
- **THEN** it is refused before any model call is made
- **AND** the refusal states the limit, the amount used, and when it resets

#### Scenario: A refused run leaves nothing behind

- **WHEN** a run is refused by the allowance
- **THEN** no run record is created
- **AND** the owner's usage is unchanged by the attempt

#### Scenario: A new period

- **WHEN** the period rolls over
- **THEN** the owner's usage counts from zero again

#### Scenario: Tiers

- **WHEN** an owner's tier is changed
- **THEN** the allowance applied is the one for the new tier
- **AND** no code change is required to introduce a second tier

### Requirement: What every run costs is recorded against the person who started it

The system SHALL record tokens consumed and money spent for every run, attributed to the
owner who started it, **whether or not the run produced a result**.

Attributing spend to the diagnosis it produced would mean a run that consumed vision and
reasoning calls and then failed is recorded nowhere — and a quota that cannot see failed
runs is a quota somebody can exhaust the budget through by failing repeatedly.

Recording SHALL happen when the run reaches a terminal status, and SHALL happen for every
terminal status including cancellation and timeout. A run that was cancelled after spending
SHALL be recorded with what it spent, because the money is gone whether or not anybody read
the result.

#### Scenario: A run that succeeds

- **WHEN** a run completes and produces a diagnosis
- **THEN** its token counts and cost are recorded against its owner

#### Scenario: A run that fails after spending

- **WHEN** a run makes model calls and then fails to produce a result
- **THEN** its token counts and cost are still recorded against its owner

#### Scenario: A run that is cancelled after spending

- **WHEN** a run is cancelled after making model calls
- **THEN** what it spent before the cancellation is recorded against its owner

#### Scenario: A run abandoned in a restart

- **WHEN** a run is failed by the timeout sweeper rather than by its own execution
- **THEN** whatever was recorded for it stands, and it is not recorded twice

#### Scenario: A provider that reports no cost

- **WHEN** a run's provider reports token counts but no cost
- **THEN** the tokens are recorded and the cost is recorded as unknown
- **AND** unknown is distinguishable from zero, so an unmeasured run cannot be read as a free one
