## ADDED Requirements

### Requirement: An owner can export and delete their own account

The system SHALL expose, on the account surface, a way for an owner to retrieve everything
held about them and a way to delete their account. Both SHALL act only on the account making
the request.

Neither takes an identifier. An endpoint that accepted one would be an endpoint that could be
pointed at somebody else, and the only defence would be a check that must never be forgotten.

#### Scenario: Requesting an export

- **WHEN** a signed-in owner requests their export
- **THEN** the response carries their data as a downloadable archive
- **AND** it describes what it contains well enough to be saved to a file

#### Scenario: Requesting an export while signed out

- **WHEN** an export is requested without a valid session
- **THEN** it is refused as unauthenticated

#### Scenario: Deleting the account

- **WHEN** a signed-in owner submits their password and confirmation to the deletion endpoint
- **THEN** the account is deleted and the response carries no content

#### Scenario: Deleting with a wrong or missing password

- **WHEN** the deletion request omits the password or supplies the wrong one
- **THEN** it is refused as a client error
- **AND** the account is unchanged

#### Scenario: Refreshing a session after its account was deleted

- **WHEN** a refresh is attempted for a deleted account
- **THEN** it is refused

#### Scenario: Reading with an access token that outlived its account

- **WHEN** a read endpoint is called with an access token issued before deletion
- **THEN** it reports that the records do not exist
