# V1.102 Calendar Structured Location Write Design

Status: Apply-capable implementation.

This gate extends the existing Calendar create/update surface with one bounded structured event location. It stays local-only, EventKit-only, exact-target gated, and metadata-first. It uses public EventKit `EKEvent.structuredLocation`, `EKStructuredLocation.locationWithTitle`, writable `geoLocation`, and writable `radius` support. It does not add email alarms, email alarms, procedure alarms, attendee/invitation mutation, travel time, calendar creation/deletion, or bulk Calendar mutation; audio alarms are governed separately by `docs/V1_103_CALENDAR_AUDIO_ALARM_WRITE_DESIGN.md`.

## Scope

- `structured_location`: adapter/MCP object with `title` and optional `latitude`, `longitude`, and `radius_meters`.
- `--structured-location`: CLI JSON object with the same fields.
- `expected_structured_location`: adapter/MCP expected-state object for update/delete drift binding.
- `--expected-structured-location`: CLI JSON object with the same expected-state fields.
- Coordinates are optional, but latitude and longitude must be provided together.
- `radius_meters` is optional, must be non-negative, and may only be non-zero when coordinates are present.
- `title` is bounded by the existing Calendar location length cap.

## Plan Contract

Planning is non-mutating and returns `mutation_applied:false`.

- Normalizes structured location into a canonical object containing `title`, `geo_present`, optional `latitude`, optional `longitude`, and `radius_meters`.
- Rejects conflicting `location` and `structured_location.title` values with `conflicting_location_fields`.
- Sets the proposed plain `location` to the structured location title so existing EventKit location metadata and stale-state checks stay coherent.
- Binds the full canonical structured location into the approval fingerprint and idempotency key.
- For update/delete, binds `expected_structured_location` into `preview.target.expected_state`.
- Rejects raw non-object values, missing title, unpaired coordinates, out-of-range coordinates, boolean numeric fields, negative radius, and oversized radius.

## Apply Contract

Apply requires the existing exact matching `calendar-apply:v1:<approval_fingerprint>` token and explicit confirmation.

- For create/update, creates an `EKStructuredLocation` from the normalized title.
- If coordinates are provided, applies `CLLocation(latitude:longitude:)`.
- If `radius_meters` is provided, applies the bounded radius.
- Rechecks expected structured location before update/delete when provided.
- Applies only to the selected exact create/update event through the existing Calendar apply gate.
- Reports `structured_location_verified:true` only after EventKit read-back returns the same canonical structured location.
- If EventKit apply succeeds but read-back cannot prove the requested structured location, apply returns `structured_location_read_back_mismatch` rather than claiming success.

## Verification

Covered checks:

- Adapter create plan binds structured location preview, plain location title, approval fingerprint, and idempotency key.
- Adapter rejects invalid structured location shapes and conflicting plain location values.
- Adapter apply forwards structured location to the helper and requires read-back verification.
- CLI accepts `--structured-location` and `--expected-structured-location` for plan/apply.
- In-process MCP plan/apply forwards structured location and preserves invalid-token fail-closed behavior.
- Runtime verifier proves direct plan/apply read-back for synthetic title plus coordinates and MCP plan plus invalid-token apply proof.
- Swift source imports CoreLocation, writes `event.structuredLocation`, and compares read-back title, coordinates, and radius.

## Still Blocked

- structured geofence alarms are governed by `docs/V1_104_CALENDAR_GEOFENCE_ALARM_WRITE_DESIGN.md`
- email/procedure alarms
- attendee/invitation mutation
- travel time
- mid-series recurrence replacement
- existing-recurring-event update beyond first-visible clear and selected/future-span/whole-series occurrence delete
- custom monthly recurrence components beyond monthly BYDAY/BYMONTHDAY/monthly nth-weekday
- custom yearly recurrence rules
- unbounded recurrence
- non-allow-listed URL schemes
- calendar creation/deletion
- bulk Calendar mutation
