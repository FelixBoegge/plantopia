## Purpose

What weather a diagnosis is read against: which days, at what resolution, taken from where,
what is written down, and what happens when none of it can be had. Weather frequently *is*
the diagnosis for an outdoor plant — a late frost, a heatwave, three weeks of rain — and an
aggregate is precisely the form that cannot say when.

## ADDED Requirements

### Requirement: Weather is kept day by day

The system SHALL record the daily minimum temperature, maximum temperature and precipitation
for each day of the window it fetches, and SHALL NOT reduce them to summary figures before
anything has read them.

A plant responds to when. "Two frost days in three weeks" cannot distinguish last night from
a fortnight ago, and that distinction is the difference between frost damage and something
else. "Fourteen millimetres" cannot distinguish a fortnight of drizzle from one storm on a
plant that has been dry since.

#### Scenario: A window of weather

- **WHEN** weather is fetched for a diagnosis
- **THEN** each day in the window is recorded with its own figures

#### Scenario: A day the service has no figures for

- **WHEN** the service returns no data for a day in the window
- **THEN** that day is absent rather than recorded as zero

#### Scenario: Summary figures

- **WHEN** a summary of the window is needed
- **THEN** it is derived from the days rather than fetched separately

### Requirement: The window ends when the photograph was taken

The system SHALL end the historical window on the day before the photograph was taken, and
SHALL fetch the forecast from the present regardless.

These are two different questions with two different anchors. What happened to the plant is
asked about the days up to the photograph — a plant photographed on Sunday did not stand in
Wednesday's weather. What to do about it is asked about the days ahead of *now*, because that
is when somebody will be doing it.

#### Scenario: A photograph taken today

- **WHEN** the photograph was taken today
- **THEN** the history ends yesterday and the forecast begins today

#### Scenario: A photograph taken three days ago

- **WHEN** the photograph was taken three days ago
- **THEN** the history ends four days ago
- **AND** the forecast still begins today

### Requirement: The days ahead are fetched as well as the days behind

The system SHALL fetch a forecast covering at least the coming week, and SHALL make it
available to the diagnosis alongside the history.

Every diagnosis ends in a plan — water less, move it, feed it next week — and a plan that
does not know a frost is coming on Thursday is advice with a hole in it. The forecast costs
nothing: no key, the same service, one more request.

#### Scenario: Planning against the week ahead

- **WHEN** a diagnosis is made for an outdoor plant with a known place
- **THEN** the coming week's forecast is available to it

#### Scenario: A forecast that cannot be had

- **WHEN** the forecast cannot be fetched
- **THEN** the diagnosis proceeds with the history alone

### Requirement: The agent is shown what is notable, not everything

The system SHALL present weather to the diagnosis as the notable events in the window, the
most recent days in full, and the forecast in full — rather than as every day it holds.

Thirty-seven unremarkable rows bury the one frost date that explains the plant. What a model
reads well is a short list of what was unusual, followed by enough recent detail to place it.
The full series is recorded and available; the prompt is a reading of it.

#### Scenario: A window containing a frost

- **WHEN** the window contains a frost and the rest is unremarkable
- **THEN** the frost is stated with its date
- **AND** the unremarkable days are not enumerated

#### Scenario: A window with nothing notable

- **WHEN** no day in the window is unusual
- **THEN** the block says so rather than listing every day

### Requirement: A diagnosis's weather can be read back

The system SHALL record the weather series against the observation it belongs to.

Somebody asking in three weeks why a diagnosis blamed heat stress cannot see what heat it
saw, unless it was written down. This is the same gap the species provenance closed: a
diagnosis whose evidence cannot be recovered cannot be argued with.

#### Scenario: Reading a past diagnosis's weather

- **WHEN** an observation with recorded weather is read
- **THEN** the days it was diagnosed against are available

#### Scenario: An observation from before this existed

- **WHEN** an observation recorded no weather
- **THEN** it reports none rather than an empty window

### Requirement: A position is used where a photograph gave one

The system SHALL use a coarse position from a photograph to fetch weather when the place has
not been changed by the owner, and SHALL fall back to resolving the place name otherwise.

A position that was turned into a name and then back into a position has been round-tripped
through a geocoder to arrive where it started, losing precision at each end. But a name the
owner *corrected* is a correction, and it has to win — otherwise somebody fixes a wrong town
and the diagnosis quietly proceeds on the coordinates behind it.

#### Scenario: The detected place was left alone

- **WHEN** the owner submits the place the photograph gave
- **THEN** the coarse position is used directly

#### Scenario: The place was corrected

- **WHEN** the owner replaces the detected place with another
- **THEN** what they typed is resolved and used

#### Scenario: No position at all

- **WHEN** no photograph gave a position
- **THEN** the place name is resolved as before

### Requirement: Weather never blocks a diagnosis

The system SHALL complete a diagnosis when weather is unavailable, partial, or refused.

Weather widens what a diagnosis can explain; its absence narrows that and nothing else. This
is unchanged from before this capability existed, and stated here because there is now more
of it to fail.

#### Scenario: The service is unavailable

- **WHEN** neither history nor forecast can be fetched
- **THEN** the diagnosis proceeds without weather

#### Scenario: Only the history could be had

- **WHEN** the history succeeds and the forecast fails
- **THEN** the diagnosis proceeds with what was fetched

#### Scenario: An indoor plant

- **WHEN** the plant lives indoors
- **THEN** no weather is fetched

### Requirement: Somebody can ask about the weather in conversation

The system SHALL let the chat agent answer questions about a plant's weather from what was
recorded, and from the service for a window that was not recorded.

"Was it cold last week?" is a question a person asks about their own plant, and answering it
from a recollection of a diagnosis is answering it from the wrong thing.

#### Scenario: Asking about a window that was recorded

- **WHEN** somebody asks about weather the observation recorded
- **THEN** the answer comes from the record

#### Scenario: Asking about a window that was not

- **WHEN** somebody asks about a window outside what was recorded
- **THEN** it is fetched

#### Scenario: Saying where the answer came from

- **WHEN** the agent answers from a weather lookup
- **THEN** the lookup is named among the sources of that reply
