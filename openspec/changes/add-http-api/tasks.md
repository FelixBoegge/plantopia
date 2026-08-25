## 1. Application skeleton

- [x] 1.1 Add `fastapi` and `uvicorn` (not `python-multipart` — nothing here receives an upload); verify `uv sync` succeeds and the app module imports.
- [x] 1.2 Add `api/main.py` with an application factory, the `/api/v1` prefix and CORS from settings; verify a test asserting the prefix appears on every registered route and that an unconfigured origin is not permitted.
- [x] 1.3 Add `cors_origins` and `api_root_path` to `Settings` with `.env.example` documentation, defaulting to no permitted origins; verify `tests/unit/core/test_config.py` covers the default and an override, constructed with `_env_file=None`.
- [x] 1.4 Add the RFC 9457 error handlers — `RecordNotFoundError` to 404, service `ValueError` to 400, unhandled to 500 — registered on the app; verify tests that each produces the shared shape, and that the 500 body carries no exception text while the log does.

## 2. Request scope

- [x] 2.1 Add a per-request session dependency that opens a session and closes it after the response; verify a test that two requests receive different sessions and that the session is closed even when the handler raises.
- [x] 2.2 Add the `current_owner` dependency resolving to the seeded owner; verify a test asserting it returns the same owner across requests and that it is the only place resolution happens (no handler calls `default_owner_id`).
- [x] 2.3 Add dependencies constructing `PlantService`, `ChatService` and `ProfileService` per request around the resolved owner; verify a test that services are not shared between requests.

## 3. Plants

- [x] 3.1 `GET /plants` returning the owner's plants newest first with latest diagnosis and outstanding step count; verify a test covering ordering, the counts, and an empty list for an owner with no plants.
- [x] 3.2 `GET /plants/{id}` returning the detail a plant page needs; verify a test asserting observations, diagnoses and current roadmap steps are present, and a 404 for an unknown identifier.
- [x] 3.3 `PATCH /plants/{id}` renaming a plant; verify tests that the name changes, that the species does not, and that a blank or whitespace-only name is a client error leaving the name unchanged.
- [x] 3.4 `DELETE /plants/{id}`; verify a test that the plant and its history are gone and that fetching it afterwards reports it does not exist.
- [x] 3.5 Write response schemas for plant, plant detail and summary rather than returning repository dataclasses; verify a test asserting the response body carries exactly the documented fields — a storage column added later must not appear by accident.

## 4. Care actions and profile

- [x] 4.1 `PATCH /roadmap-steps/{id}` setting status; verify tests for done, skipped, reopening to pending (which clears the completion time), and a client error for an unrecognised status.
- [x] 4.2 `POST /diagnoses/{id}/feedback`; verify a test that feedback is recorded and that the diagnosis afterwards reports feedback exists.
- [x] 4.3 `GET /profile/facts` and `DELETE /profile/facts`; verify tests that facts come back with source, confidence and last-confirmed, that forgetting removes one, and that forgetting something not held succeeds rather than erroring.

## 5. Photographs

- [x] 5.1 `GET /photos/{key}` serving bytes with the stored content type; verify a test round-tripping an uploaded image and one asserting an unknown key is 404. This handler talks to the `BlobStore` directly rather than through a service — the one deliberate exception, because no service owns photograph bytes; it takes the owner the same way every other handler does.

## 6. Chat

- [x] 6.1 `GET /plants/{id}/messages` returning the transcript oldest first; verify a test covering ordering and the fields each message carries.
- [x] 6.2 `POST /plants/{id}/messages` running the agent and returning the reply; verify a test using the scripted model that the reply comes back and that both message and reply are in the transcript afterwards. No LLM call.

## 7. Tenancy across the surface

- [x] 7.1 Add a table-driven test walking every route that takes a resource identifier, invoking its handler with a second owner, asserting 404 and no change; verify it fails when a route is made to pass the wrong owner into its service.
- [x] 7.2 Assert the status code, not merely the absence of data: a handler that turned the repository's refusal into 403 would satisfy a data-only check while telling a stranger the resource exists.
- [x] 7.3 Record in the change and in `docs/known-limitations.md` that endpoint tenancy is exercised below HTTP because only one owner can be resolved, and that the end-to-end version arrives with authentication; verify the row reads accurately against what the tests actually do.

## 8. Health, and running it

- [x] 8.1 `GET /health` returning immediately and `GET /ready` executing one query; verify a test that readiness fails when the database is unreachable while liveness still succeeds.
- [x] 8.2 Add the uvicorn command to the README's Development section alongside Streamlit, and note that Streamlit continues to work with the API stopped; verify by running both.
- [x] 8.3 Run `openspec validate add-http-api --strict`, the full suite including the `ui` tier, and ruff; verify all three are clean, and that a Streamlit diagnosis still completes end to end.
