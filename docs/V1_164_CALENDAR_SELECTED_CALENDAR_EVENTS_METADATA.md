# v1.164 Calendar Selected-Calendar Event Metadata

Status: implemented.

## Surface

- MCP: `calendar_list_calendar_events(handle, start_date, end_date, limit=20)`
- CLI: `local-apple-data calendar events --json --handle <calendar:calendar:v1:...> --start <YYYY-MM-DD-or-ISO> --end <YYYY-MM-DD-or-ISO> [--limit 20]`
- Adapter: `list_calendar_events_for_calendar()`
- Helper: `calendar_events_for_calendar`

The command returns capped event metadata for one exact selected Calendar target:
opaque `calendar:event:v1:` event handles, title, calendar title, start/end,
all-day, availability, presence/count flags, and recurrence metadata. It returns
no raw EventKit calendar ID, raw event ID, event notes, event location text,
attendee names/URLs, event URL value, raw alarm detail, or mutation capability.

## Safety Rules

- Requires one opaque `calendar:calendar:v1:` handle returned by
  `calendar calendars` / `calendar_search_calendars`.
- Requires explicit `start_date` and `end_date`; both must be date-only values or
  both timestamps with time zones.
- Rejects reversed/empty windows and caps one request to 366 days.
- Caps output at 50 events and slices again in the adapter even if the helper
  over-returns.
- Resolves the signed calendar handle against live EventKit calendar metadata
  before fetching events.
- Uses public EventKit `predicateForEvents(withStart:end:calendars:)` with the
  selected calendar only.
- Returns metadata only through the existing `_event_metadata` redaction path.
- Does not create a mutation target from raw calendar names or raw EventKit
  identifiers.
- No Gmail, iCloud.com, browser, keychain, private API, network, direct DB, or
  broad Calendar dump fallback.

## Regression Proof

- Adapter tests prove exact calendar-handle gating, explicit date-window
  validation, metadata-only output, raw helper-ID stripping, and adapter-side cap
  enforcement when the helper over-returns.
- CLI tests cover `calendar events --json`.
- MCP tests cover `calendar_list_calendar_events`.
- Runtime verifier expects the new MCP tool and proves direct/MCP selected
  calendar event listing returns opaque event handles with metadata-only output.
- Surface and mutation-gate audits include the new read-only CLI and MCP tool.

## Remaining Gaps

- Broad Calendar dumps, raw EventKit identifiers, event notes/location/URL
  values outside exact selected event detail, attendee/invitation mutation,
  organizer mutation, travel-time mutation, procedure alarms, real/non-synthetic
  calendar management, default-calendar mutation, source/account management,
  and calendar delete outside the synthetic event-only bounded-empty gate remain
  blocked.
