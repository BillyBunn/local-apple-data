# V1.107 Calendar Structured Location Clear Write Design

Status: Apply-capable implementation.

This gate extends the existing Calendar exact-event update surface with explicit structured-location clearing. It stays local-only, EventKit-only, exact-event gated, and metadata-first. Source proof is the public EventKit `EKEvent.structuredLocation` nullable writable property in the local macOS SDK; the same header documents that plain `location` maps to a title-only structured location, so clearing must set both `structuredLocation` and `location` to nil.

## Scope

- `clear_structured_location`: adapter/MCP boolean for update only.
- `--clear-structured-location`: CLI flag for update only.
- `expected_structured_location` / `--expected-structured-location` is required so clear binds the current structured location before mutation.
- Proposed `location` must be omitted or empty. Non-empty `location` is rejected because EventKit stores plain location as a structured-location title.
- `structured_location` and `clear_structured_location` are mutually exclusive.

## Plan Contract

Planning is non-mutating and returns `mutation_applied:false`.

- Rejects non-update operations with `unsupported_structured_location_for_operation`.
- Rejects set+clear conflicts with `conflicting_structured_location_fields`.
- Rejects non-empty proposed `location` with `conflicting_location_fields`.
- Requires `expected_structured_location` with `missing_required_field`.
- Adds `structured_location_clear_requested:true` to proposed state.
- Binds the clear request and expected structured location into the approval fingerprint and idempotency key.

## Apply Contract

Apply requires the existing exact matching `calendar-apply:v1:<approval_fingerprint>` token and explicit confirmation.

- Recomputes the plan before apply.
- Rechecks the exact event expected state before mutation.
- Sets `event.structuredLocation = nil` and `event.location = nil` through the public EventKit helper.
- Reports `structured_location_cleared_verified:true` only after read-back explicitly returns `structured_location_present:false` and `location_present:false`.
- If EventKit apply succeeds but absence proof is missing or malformed, apply returns `apply_unknown` with `mutation_applied:true` and warning `structured_location_clear_read_back_mismatch`.

## Verification

Covered checks:

- Adapter plan binds `structured_location_clear_requested:true` and expected structured location.
- Adapter rejects create/delete clear, set+clear, non-empty proposed location, and missing expected structured location.
- Adapter apply forwards `structured_location_clear_requested:true`, sends empty `structured_location`, sends empty `location`, and requires read-back absence proof for both structured and plain location.
- CLI accepts `--clear-structured-location` for plan/apply.
- MCP accepts `clear_structured_location` for plan/apply and preserves invalid-token fail-closed behavior.
- Swift helper typechecks with explicit `event.structuredLocation = nil` and `event.location = nil`.
- Runtime verifier proves direct clear plan/apply/read-back absence and MCP plan plus invalid-token apply proof.

## Still Blocked

- Mid-series recurrence replacement.
- Existing-recurring-event update beyond first-visible/mid-series recurrence clear and selected/future-span/whole-series occurrence delete.
- Attendee/invitation mutation.
- Travel time.
- Email/procedure alarms.
- Non-allow-listed URLs.
- Calendar creation/deletion and account management.
- Bulk Calendar mutation.
