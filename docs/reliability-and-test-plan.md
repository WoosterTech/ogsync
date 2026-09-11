# Reliability and Test Plan

This plan turns the code review into a focused reliability pass for `ogsync`.

The default test suite must use mocks, fakes, and temporary databases. It must not require live Google credentials, Outlook, or network access. The `typings/` directory is explicitly out of scope.

## Goals

- Prevent credential contents from appearing in logs.
- Fail clearly when required configuration is missing.
- Keep sync state isolated by source and destination.
- Make the `list_synced` command match its displayed data.
- Establish executable coverage for models, persistence, sync orchestration, adapters, authentication, and CLI behavior.
- Define predictable behavior when a remote operation or local state update fails.

## Phase 1: Correctness and Safety

### 1. Protect credentials

Update `src/ogsync/connections/gcal.py` to remove or redact the credential object from trace logging. Preserve useful diagnostics such as whether credentials were loaded, refreshed, or obtained through the OAuth flow, without logging access tokens or refresh tokens.

Add a test that captures logs and verifies token contents are absent.

### 2. Validate required settings

Add fail-fast validation for required settings, especially `google_calendar_id`, before constructing or using `GCalSink`.

Prefer reusable settings validation invoked at the CLI boundary so importing the settings module remains safe. Test the error message and confirm no Google API call is attempted when the setting is invalid.

### 3. Scope sync-store identity

Review `src/ogsync/store.py` so rows cannot be mixed between different source/destination pairs. The current store contract is pair-specific, but the event ID lookup and primary-key behavior must be checked against that contract.

Choose a migration-compatible approach, such as a scoped uniqueness key or composite identity. Add a migration or compatibility test if existing state databases must continue to work.

### 4. Correct `list_synced`

Make `list_synced` display data that actually exists. Either:

- Extend the adapter API to return native IDs and summaries, or
- Remove the unused summary column and show only IDs.

Remove the unused dry-run local unless dry-run behavior is intentionally added to this command.

### 5. Keep recurrence scope explicit

Do not expand recurrence support in this pass unless it is wired into `OutlookSource`. Document the currently supported behavior and test only the path that is actually used.

## Phase 2: Foundation Tests

### 6. Calendar model tests

Add tests for `src/ogsync/models.py` and `src/ogsync/identity.py` covering:

- Naive datetime localization.
- Timezone-aware datetime handling.
- UTC normalization.
- All-day event conversion to an exclusive end boundary.
- Repeated validation remaining idempotent.
- Invalid end times.
- Missing all-day end times.
- Empty IDs.
- Deterministic generated IDs.
- Changes to identity fields producing the expected ID changes.

### 7. Sync-store tests

Use a temporary SQLite database and test:

- Database and table initialization.
- Recording a synced event.
- Retrieving known IDs and external IDs.
- First and last sync timestamps.
- Re-recording an event without losing its first-sync timestamp.
- Detecting stale IDs.
- Forgetting events.
- Empty `forget` input.
- Isolation between source/destination pairs.
- Behavior with existing database state.

## Phase 3: Sync Orchestration Tests

Add tests for `src/ogsync/sync.py` using small fakes for the source, sink, store, console, and events.

Cover:

- Fetching events with the requested `days_ahead` value.
- Upserting every current event.
- Recording each successful mapping.
- Deleting stale destination events.
- Forgetting stale mappings after successful deletion.
- Empty source results.
- Dry-run upserts without sink or store writes.
- Dry-run stale deletions without sink or store writes.
- Console output for normal and dry-run operations.

Before implementing failure-path tests, decide the intended contract for each case:

- Sink upsert fails.
- Store recording fails after the remote upsert succeeds.
- Stale-event deletion fails.

The chosen behavior should be documented and tested, especially what the next sync run is expected to retry.

## Phase 4: Adapter and Boundary Tests

### 8. Google Calendar adapter

Mock the discovery resource and verify:

- Timed event request bodies.
- All-day event request bodies.
- Confirmed, tentative, and cancelled status behavior.
- Existing event update versus new event insert.
- Private extended-property lookup.
- Pagination in `list_synced_ids`.
- Missing or malformed response IDs.
- Delete requests use the native event ID.

### 9. Outlook adapter and connection

Use fake COM appointment objects to test:

- Category matching and whitespace handling.
- Appointment-to-`CalendarEvent` conversion.
- UTC conversion.
- All-day event fields.
- Response and meeting status mapping.
- Empty appointment collections.
- Errors at the Outlook connection boundary.
- Recurrence behavior currently supported by the source.

### 10. Authentication

Mock Google authentication flows and test:

- Reusing a valid token.
- Refreshing an expired token with a refresh token.
- Starting the client-secret flow when no usable token exists.
- Persisting refreshed or newly obtained credentials.
- Authentication errors.
- Log output never contains token values.

### 11. CLI and configuration

Test:

- `--dry-run` propagation.
- Verbosity propagation.
- `days_ahead` propagation.
- Missing `google_calendar_id` validation.
- `list_synced` output and column consistency.
- CLI help loading without requiring live credentials.

## Phase 5: Verification

Run the following after implementation:

```text
uv run pytest -q
uv run ruff check .
uv run basedpyright
```

The test run must collect actual tests and must not exit with pytest's no-tests-collected status. Type checking and linting should use the existing project configuration without adding broad ignores. `typings/` should not be modified as part of this plan.

Perform a manual smoke check for:

- `uv run ogsync --help`.
- A clear failure when `google_calendar_id` is empty.
- Dry-run mode without remote writes.

Keep real Google and Outlook checks as an opt-in manual suite. Do not commit credentials, token files, or service-dependent fixtures.

## Suggested Test Layout

```text
tests/
    test_models.py
    test_identity.py
    test_store.py
    test_sync.py
    test_adapters_gcal.py
    test_adapters_outlook.py
    test_connections_gcal.py
    test_connections_outlook.py
    test_cli.py
```

The files can be consolidated if the resulting test modules remain focused. The placeholder test should be replaced once the first executable tests are added.

## Relevant Source Files

- `src/ogsync/connections/gcal.py`
- `src/ogsync/settings.py`
- `src/ogsync/ogsync.py`
- `src/ogsync/store.py`
- `src/ogsync/sync.py`
- `src/ogsync/models.py`
- `src/ogsync/identity.py`
- `src/ogsync/adapters/gcal.py`
- `src/ogsync/adapters/outlook.py`
- `src/ogsync/connections/outlook.py`
- `tests/`

`typings/` is excluded from implementation and test work.
