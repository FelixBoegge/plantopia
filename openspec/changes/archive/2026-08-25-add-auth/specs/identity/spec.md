## Purpose

Defines who a person is to Plantopia and how a request proves it: registering, proving an
address, holding a session, ending one, recovering a forgotten password — and what the
system refuses to reveal about who has an account.

## ADDED Requirements

### Requirement: Anyone can register, and nothing is usable until the address is proven

The system SHALL accept a registration from any email address and password, and SHALL
create an unverified account. An unverified account SHALL NOT be able to sign in or reach
any owner-scoped endpoint.

Passwords SHALL be stored only as an argon2id hash. The system SHALL NOT store, log, or
return a password in any form, at any point.

#### Scenario: Registering

- **WHEN** an unregistered address is submitted with a password
- **THEN** an account is created in an unverified state
- **AND** a verification message is sent to that address
- **AND** the response does not contain the password or its hash

#### Scenario: Signing in before verifying

- **WHEN** an account that has not verified its address attempts to sign in
- **THEN** the attempt is refused
- **AND** no session is issued

#### Scenario: A password that is too weak to accept

- **WHEN** a password shorter than the required minimum is submitted
- **THEN** registration is refused with a client error naming the requirement
- **AND** no account is created

#### Scenario: Passwords are never recoverable

- **WHEN** any account exists
- **THEN** no stored value permits recovering its password
- **AND** two accounts choosing the same password have different stored values

### Requirement: The system does not reveal who has an account

Registration, sign-in and password-reset requests SHALL respond identically whether or not
the address is registered. No status code, message, or field SHALL differ on that basis.

An endpoint that answers "no such account" is a way to ask the system who has one, and the
answer is worth more to somebody enumerating addresses than the convenience is worth to a
person who mistyped theirs.

#### Scenario: Registering an address that already exists

- **WHEN** registration is attempted for an address that is already registered
- **THEN** the response is indistinguishable from registering a new address
- **AND** no second account is created
- **AND** the existing account is unchanged

#### Scenario: Requesting a reset for an address with no account

- **WHEN** a password reset is requested for an unregistered address
- **THEN** the response is indistinguishable from requesting one for a registered address
- **AND** no message is sent

#### Scenario: Signing in with an unknown address

- **WHEN** sign-in is attempted with an address that has no account
- **THEN** the refusal is indistinguishable from signing in with a wrong password

### Requirement: A session is an access token and a rotating refresh token

On successful sign-in the system SHALL issue a short-lived access token, carried by the
client and presented on each request, and a long-lived refresh token, delivered as an
`httpOnly` cookie that scripts cannot read.

Refresh tokens SHALL be stored as a hash, never in plain form. Each use SHALL issue a new
refresh token and invalidate the one presented.

#### Scenario: Signing in

- **WHEN** a verified account signs in with the correct password
- **THEN** an access token is returned in the response body
- **AND** a refresh token is set as an httpOnly cookie
- **AND** the refresh token is not present in the response body

#### Scenario: Refreshing

- **WHEN** a valid refresh token is presented
- **THEN** a new access token is issued
- **AND** a new refresh token replaces it
- **AND** the presented token no longer works

#### Scenario: An expired access token

- **WHEN** a request presents an access token past its lifetime
- **THEN** the request is refused
- **AND** the refusal is distinguishable from a malformed token, so a client knows to refresh rather than to sign in again

### Requirement: A reused refresh token invalidates its whole family

When a refresh token that has already been rotated is presented, the system SHALL treat
every token descended from the same sign-in as compromised and invalidate all of them,
requiring a fresh sign-in.

A rotated token being presented a second time has one likely explanation: two parties hold
it, and only one of them should. Refusing that single request while leaving the thief's
newer token working would protect nothing.

#### Scenario: A token is used twice

- **WHEN** a refresh token is used, and then the same token is presented again
- **THEN** the second attempt is refused
- **AND** the token issued by the first use also stops working
- **AND** the account must sign in again

#### Scenario: One session is compromised, another is not

- **WHEN** a person is signed in on two devices and one device's token family is invalidated
- **THEN** the other device's session continues to work

### Requirement: Signing out ends the session

The system SHALL invalidate the presented refresh token and clear its cookie on sign-out.
An access token already issued SHALL be allowed to expire on its own.

#### Scenario: Signing out

- **WHEN** a signed-in person signs out
- **THEN** the refresh token is invalidated and its cookie cleared
- **AND** refreshing with it afterwards is refused

### Requirement: A forgotten password can be reset

The system SHALL send a single-use reset link, valid for a limited time, to a registered
address on request. Using it SHALL set a new password and invalidate every existing
session for that account.

#### Scenario: Resetting

- **WHEN** a valid reset token is submitted with a new password
- **THEN** the password is changed
- **AND** the token cannot be used again
- **AND** every session that existed before the reset is invalidated

#### Scenario: An expired reset token

- **WHEN** a reset token past its lifetime is submitted
- **THEN** it is refused and no password is changed

#### Scenario: Requesting a second reset

- **WHEN** a second reset is requested before the first is used
- **THEN** the first token no longer works, so a link found later cannot be used against the person who abandoned it

### Requirement: Verification and reset tokens are single-use and hashed

Tokens sent by email SHALL be stored as hashes, SHALL expire, and SHALL be consumed on
first successful use. A token SHALL be unguessable from any other token or from the
address it was sent to.

#### Scenario: Using a verification link twice

- **WHEN** a verification link is followed a second time
- **THEN** it is refused
- **AND** the account remains verified from the first use

#### Scenario: A token in the database

- **WHEN** verification or reset tokens are stored
- **THEN** the stored value cannot be sent in an email to make a working link

### Requirement: What is consented to at signup is recorded

The system SHALL record which version of the privacy notice was agreed and when, at the
moment of registration. Registration SHALL be refused without that agreement.

Consent that cannot be evidenced afterwards is not consent, and registration is the only
moment it can be captured.

#### Scenario: Registering with consent

- **WHEN** an account is created
- **THEN** the version agreed to and the time of agreement are stored against it

#### Scenario: Registering without consent

- **WHEN** registration is submitted without agreeing to the notice
- **THEN** it is refused and no account is created

### Requirement: Email is sent through a replaceable port

The system SHALL send email through an interface with more than one implementation, and
SHALL NOT send real messages in development or in tests.

#### Scenario: Sending in development

- **WHEN** the application runs without a mail provider configured
- **THEN** messages are written where a developer can read them
- **AND** nothing is delivered to a real address

#### Scenario: A provider failing

- **WHEN** the mail provider cannot be reached during registration
- **THEN** the account is still created
- **AND** the failure is logged
- **AND** the person can request the verification message again
