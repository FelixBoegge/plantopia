## Purpose

Defines how the curated disorder corpus is searched during a diagnosis — both similarity search
over sections and retrieval of named documents by identifier, which is what lets the agent read
about a disorder it has reasoned its way to rather than one that merely resembles the wording of
a symptom description.

## ADDED Requirements

### Requirement: Similarity search returns ranked, scored sections

The system SHALL accept one or more query representations and return at most a requested number
of corpus sections, each carrying its document identifier, its section name, its text and a
comparable relevance score, ordered best first.

#### Scenario: Searching with a limit

- **WHEN** a search is made with a limit of six
- **THEN** at most six sections are returned
- **AND** each carries a document identifier, section name, text and score
- **AND** they are ordered from most to least relevant

#### Scenario: Restricting to particular sections

- **WHEN** a search names the sections it is interested in
- **THEN** only sections of those kinds appear in the result

### Requirement: Similarity search is deterministic

Given identical query representations and an unchanged corpus, the system SHALL return identical
results in identical order on every call. Ranking SHALL NOT vary between runs.

#### Scenario: Repeating the same search

- **WHEN** the same query is searched twice against an unchanged corpus
- **THEN** both calls return the same sections in the same order with the same scores

### Requirement: Documents can be fetched by identifier without ranking

The system SHALL return the named sections of explicitly identified documents, regardless of how
those documents would rank under similarity search. A document requested by identifier SHALL be
returned even if similarity search would never surface it.

This is what makes reasoning-before-retrieval work: the agent names the disorders worth reading
about and fetches them by name, so a correct document sitting at rank 21 of 43 still reaches the
model.

#### Scenario: Fetching named documents

- **WHEN** two document identifiers and a set of section names are requested
- **THEN** exactly those documents' sections of those kinds are returned
- **AND** no ranking is applied to them
- **AND** documents that were not named are absent

#### Scenario: Fetching a document that ranks poorly

- **WHEN** a document that similarity search places outside the top twenty is requested by identifier
- **THEN** its sections are returned in full

#### Scenario: Fetching an unknown identifier

- **WHEN** an identifier that no document carries is requested
- **THEN** it contributes nothing to the result
- **AND** the sections of any valid identifiers in the same request are still returned

### Requirement: The corpus's document identifiers are enumerable

The system SHALL report the complete set of document identifiers the corpus holds, so that the
agent can be constrained to name only disorders that exist.

#### Scenario: Listing the corpus

- **WHEN** the set of document identifiers is requested
- **THEN** every document in the corpus is represented exactly once

### Requirement: Retrieval results are unchanged by the storage move

Moving the corpus to different storage SHALL NOT change what retrieval returns. For every
recorded query, the system SHALL return the same document identifiers, the same sections, in the
same order, as the implementation being replaced.

#### Scenario: Replaying recorded queries

- **WHEN** the recorded query representations from the evaluation golden set are replayed against both the previous and the new implementation
- **THEN** both return identical document identifiers, section names and ordering for every query
- **AND** any difference fails the change

#### Scenario: Replaying recorded fetches by identifier

- **WHEN** the recorded fetch-by-identifier requests are replayed against both implementations
- **THEN** both return the same sections for the same documents

### Requirement: Searching by photograph is reported as unavailable

While no embedding model that accepts images is reachable, the system SHALL report that it cannot
search by photograph, rather than failing or silently returning text-only results as if they were
image matches.

#### Scenario: Asking whether image search is available

- **WHEN** a caller asks whether the corpus can be searched by photograph
- **THEN** the system answers that it cannot
- **AND** the caller skips the image search rather than attempting it

#### Scenario: Diagnosing while image search is unavailable

- **WHEN** a diagnosis runs with image search unavailable
- **THEN** no image search appears among the tools reported as used
- **AND** the model is told outright that no photograph-matched material is available
