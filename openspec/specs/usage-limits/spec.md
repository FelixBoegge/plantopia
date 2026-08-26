# usage-limits Specification

## Purpose
Defines what stops one person, or everybody together, from spending an unbounded amount of
somebody else's model budget — and what a person is told when they reach a limit.

A diagnosis costs roughly five cents of real money. Registration is open. Without these,
the signup form is an unmetered bill.

## Requirements

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

### Requirement: Everybody together has a ceiling too

The system SHALL refuse to start any run when total spend for the current day has reached
a configured cap, regardless of whose run it is or how much of their own allowance they
have left.

Per-person quotas bound what one person can do. They do not bound what a thousand fresh
accounts can do together, and open registration means a thousand fresh accounts is a
morning's work.

#### Scenario: Below the daily cap

- **WHEN** the day's total spend is below the cap and a run starts
- **THEN** it proceeds

#### Scenario: At the daily cap

- **WHEN** the day's total spend has reached the cap
- **THEN** every run is refused, including for owners with allowance remaining
- **AND** the refusal is distinguishable from a personal quota refusal, because the person can do nothing about this one

#### Scenario: A new day

- **WHEN** the day rolls over
- **THEN** runs proceed again without intervention

### Requirement: Cheap endpoints to hammer are rate limited

The system SHALL limit how often registration, sign-in and password reset can be requested
from one source, and SHALL refuse beyond that limit with a response saying when to retry.

These three are singled out because they are unauthenticated, cost something to serve — a
hash, an email — and are the ones worth hammering: sign-in to guess passwords, registration
to create accounts, reset to send mail to somebody else's address.

#### Scenario: Ordinary use

- **WHEN** a person registers, signs in, or requests a reset a handful of times
- **THEN** none of it is refused

#### Scenario: Hammering sign-in

- **WHEN** sign-in is attempted from one source far more often than the limit permits
- **THEN** further attempts are refused
- **AND** the response says when to retry

#### Scenario: Limits do not leak who exists

- **WHEN** a limit is reached
- **THEN** the refusal is the same whether the addresses tried were registered or not

### Requirement: A refusal is never silent and never generic

Every refusal from this capability SHALL be distinguishable, by a machine-readable type,
from every other kind of failure — and from each other. A client SHALL be able to tell a
personal quota from the global cap from a rate limit without parsing prose.

#### Scenario: Distinguishing refusals

- **WHEN** a run is refused by a personal quota, by the global cap, or by a rate limit
- **THEN** each carries a different machine-readable type
- **AND** each is distinguishable from an authentication failure and from a missing resource
