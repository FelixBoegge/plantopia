# web-client Specification

## Purpose
Defines what a person can do in a browser: which screens exist, what each is responsible
for, how a signed-in session is held and renewed, what a refusal looks like on a screen
rather than in a response body, and which accessibility properties are part of the contract.

## Requirements

### Requirement: A person can reach every part of their account from a browser

The system SHALL provide a browser interface covering registration, address verification,
sign-in, password reset, the plants a person owns, one plant in detail, starting and
watching a diagnosis, and an account screen.

No capability of the API that belongs to an ordinary person SHALL be reachable only by
constructing a request by hand.

#### Scenario: Registering and verifying

- **WHEN** a person completes the registration form
- **THEN** they are told to check their email rather than being signed in
- **AND** following the verification link signs them in or invites them to

#### Scenario: Signing in

- **WHEN** a person signs in with correct credentials
- **THEN** they arrive at their plants
- **AND** the session survives a page reload

#### Scenario: A refusal a person can act on

- **WHEN** any request is refused
- **THEN** the screen says what happened in a sentence a person can read
- **AND** no raw error, status code, or identifier is shown as the explanation

### Requirement: The access token is never put anywhere it will be logged

The access token SHALL be held in memory and sent as an `Authorization` header. It SHALL
NOT be placed in a URL, including the query string of an event stream, and SHALL NOT be
written to `localStorage` or `sessionStorage`.

A token in a URL is a token in the browser's history, in the server's access log, and in
the `Referer` header of anything the page later loads. A token in `localStorage` is one any
injected script can read, which is the reason the refresh token is an httpOnly cookie.

#### Scenario: Watching a run

- **WHEN** the interface opens a run's event stream
- **THEN** the token travels as a request header
- **AND** the URL contains no credential

#### Scenario: Reloading the page

- **WHEN** a signed-in person reloads
- **THEN** the session is re-established from the refresh cookie
- **AND** no token was persisted in browser storage to make that work

### Requirement: An expired session renews itself once, silently

When a request is refused because the access token has expired, the system SHALL obtain a
new one using the refresh cookie and retry the original request once. When the refusal says
the session has ended rather than expired, it SHALL send the person to sign in.

The API distinguishes those two refusals precisely so a client can. A client that treated
them alike would either sign people out every fifteen minutes or retry a sign-in that will
never succeed.

#### Scenario: A token expires mid-session

- **WHEN** a request is refused as expired
- **THEN** the interface renews and retries once
- **AND** the person sees no interruption

#### Scenario: The session has ended

- **WHEN** a request is refused as unauthenticated
- **THEN** the person is sent to sign in
- **AND** no renewal is attempted

#### Scenario: Renewal fails

- **WHEN** renewal is itself refused
- **THEN** the person is sent to sign in
- **AND** the original request is not retried again

Refresh SHALL NOT be retried. Each use rotates the token, so presenting a spent one is
indistinguishable from a stolen one being used and ends the session for everybody holding
it.

### Requirement: Server state is read from the server, not mirrored

Every screen SHALL render from a cache of what the server owns, invalidated when the client
changes something. The interface SHALL NOT keep a parallel copy of a person's plants,
diagnoses, roadmap or transcript that could disagree with the server's.

The only state the client owns is the access token and a form somebody is part-way through
filling in.

#### Scenario: A change made in one place shows in another

- **WHEN** a roadmap step is marked done on a plant screen
- **THEN** what that screen shows of the plant reflects it without a manual reload

#### Scenario: Returning to a screen

- **WHEN** a person navigates away and back
- **THEN** what they see reflects the server, including changes made elsewhere

### Requirement: A person can see what the system has learned about them

The account screen SHALL show the facts the system has inferred about the person, when each
was learned and how confident it is, and SHALL let any of them be forgotten. It SHALL show
which version of the privacy notice was agreed and when.

A system that infers durable facts about somebody and offers no way to see or remove them
is one they cannot correct.

#### Scenario: Reading the learned profile

- **WHEN** a person opens their account screen
- **THEN** every fact learned about them is listed
- **AND** each says when it was learned

#### Scenario: Forgetting a fact

- **WHEN** a person forgets a fact
- **THEN** it disappears from the list
- **AND** it is not used in a later conversation

#### Scenario: The consent record

- **WHEN** a person opens their account screen
- **THEN** the notice version they agreed to and when are shown

### Requirement: A person can see how much of their allowance is left

The interface SHALL show how many runs the person has used against their allowance and when
it resets, and SHALL say so before a run is started rather than only when one is refused.

Being told "you have used your twenty runs" by a failed diagnosis is being told too late.

#### Scenario: Approaching the allowance

- **WHEN** a person has used most of their allowance
- **THEN** the remaining count and reset date are visible before they start a run

#### Scenario: At the allowance

- **WHEN** a person at their allowance opens the wizard
- **THEN** they are told they cannot start one and when they can
- **AND** the refusal names the limit rather than reporting a failure

### Requirement: Colour is never the only carrier of meaning

Any state distinguished by colour SHALL also be distinguished by text or shape. Severity in
particular SHALL carry a written label.

Roughly one in twelve men cannot reliably separate the red and green a severity badge uses,
and a diagnosis whose seriousness is conveyed only by hue is one they cannot read.

#### Scenario: Reading a severity

- **WHEN** a severity is displayed
- **THEN** it carries a text label as well as a colour

#### Scenario: Reading a run's status

- **WHEN** a run's status is displayed
- **THEN** it is stated in words

### Requirement: Every path is reachable from the keyboard

The system SHALL make every interactive element reachable and operable by keyboard, SHALL
move focus deliberately when a screen changes what a person is expected to do, and SHALL
announce content that changes without a navigation.

#### Scenario: Completing a diagnosis without a mouse

- **WHEN** a person uses only a keyboard
- **THEN** every step of starting, answering and reading a diagnosis is reachable

#### Scenario: Focus after a step changes

- **WHEN** the wizard moves from one step to the next
- **THEN** focus moves to the new step rather than staying where it was

#### Scenario: Content arriving without a navigation

- **WHEN** progress or a reply arrives on an open screen
- **THEN** it is announced to assistive technology rather than appearing silently

### Requirement: One screen is not for everybody

The evaluation screen SHALL be reachable only by a person whose account permits it, and
SHALL be indistinguishable from a route that does not exist for anybody else.

#### Scenario: An ordinary person finds the route

- **WHEN** somebody without permission navigates to the evaluation screen
- **THEN** they are shown the same thing as for any unknown route
- **AND** no part of the interface reveals that the screen exists

#### Scenario: A permitted person

- **WHEN** somebody whose account permits it opens the evaluation screen
- **THEN** the newest harness result is shown
- **AND** before any harness has run, the screen says so rather than failing
