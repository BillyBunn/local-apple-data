# V1.94 Calendar Event URL Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the existing Calendar create/update gate to set one allow-listed event URL/meeting link on an exact Calendar event. The current allow-list is `http`, `https`, `mailto`, and `tel`. URL clearing is covered separately by `docs/V1_95_CALENDAR_EVENT_URL_CLEAR_WRITE_DESIGN.md`. This document does not approve attendee or invitation mutation, organizer mutation, travel time, recurrence delete, existing-recurring-event update/delete, custom/unbounded recurrence, email/procedure alarms, non-allow-listed URL schemes, calendar creation/deletion, account management, or bulk operations.

## EventKit Source Review

EventKit source review is limited to public SDK headers shipped on this Mac plus official Apple EventKit documentation.

- `EKCalendarItem.URL` is a mutable nullable `NSURL`.
- `EKCalendarItem.attendees` and `EKEvent.organizer` are readonly, so attendee/invitation/organizer mutation remains blocked.
- This Mac's public EventKit SDK headers do not expose a writable travel-time property. `scripts/audit_calendar_public_surface.py --json` is the deterministic local proof for this blocker.
- `EKAlarm.url` procedure alarms remain deprecated and documented as not creatable on this platform, so procedure alarms remain blocked.

## Plan Contract

`calendar_plan_change` and `local-apple-data calendar plan` accept:

- `event_url` / `--event-url`: optional allow-listed `http`, `https`, `mailto`, or `tel` URL for `operation=create` or `operation=update`.
- `expected_event_url_present` / `--expected-event-url-present`: optional current-state binding for `operation=update` or `operation=delete`.
- `expected_event_url_sha256` / `--expected-event-url-sha256`: required when `expected_event_url_present=true`.

Planning:

- Rejects non-allow-listed URL schemes, whitespace, control characters, embedded credentials, and values longer than 2048 characters.
- For `http` and `https`, rejects missing or malformed hosts and invalid ports so Python planning stays fail-closed with Swift/Foundation URL parsing.
- For `mailto`, accepts exactly one recipient address and rejects queries, fragments, and non-address payloads.
- For `tel`, accepts exactly one bounded dial string and rejects queries, fragments, and non-dial payloads.
- Rejects `expected_event_url_sha256` unless `expected_event_url_present=true`; SHA-256 input must be exact lowercase 64-character hex with no trim or case normalization.
- Rejects `expected_event_url_present` and `expected_event_url_sha256` for `operation=create`.
- Rejects `event_url` for `operation=delete`.
- Stores the caller-provided URL in the private approval fingerprint for exact apply-token binding.
- Adds `event_url_scheme`, `event_url_domain`, `event_url_safe_sha256`, `event_url_requested`, and `url_present` to `preview.proposed`. `event_url_domain` is empty for `mailto` and `tel`.
- It never returns the raw URL in public plan output.
- Adds exact expected URL presence and SHA-256 to update/delete expected state.
- Stays non-mutating.

## Apply Contract

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, resolves exactly one target event by opaque handle for update/delete, and sends the URL to the Swift EventKit helper only after token verification.

Apply:

- Rechecks exact expected current state before mutation, including expected URL presence and SHA-256 when URL presence is true.
- Refuses existing unsupported attendee, alarm, or recurrence states using the existing bounded Calendar mutation guards.
- Sets `event.url` only when `event_url_requested=true`; URL clearing is covered separately by v1.95.
- Saves one event with `.thisEvent`.
- Returns bounded metadata read-back only. It returns URL presence and `event_url_safe_sha256`, not the raw existing Calendar URL.
- Adds `event_url_verified:true` only when read-back URL SHA-256 matches the approved URL.

If EventKit saves the mutation but read-back URL proof does not match the approved value, the adapter returns `status:"apply_unknown"`, `mutation_applied:true`, and warning code `event_url_read_back_mismatch`.

## Synthetic Tests Required

- Adapter plan tests proving event URL preview and approval fingerprint binding.
- Adapter plan tests proving `mailto` and `tel` allow-list support without raw URL echo, and rejecting non-allow-listed URL schemes, whitespace, control characters, embedded credentials, missing/malformed HTTP/HTTPS hosts, invalid ports, unsafe `mailto` forms, unsafe `tel` forms, uppercase SHA-256, and trimmed SHA-256 input.
- Adapter plan tests rejecting create-time expected URL state and delete-time URL mutation input.
- Adapter plan tests proving expected URL presence requires expected URL SHA-256.
- Adapter apply tests proving create/update URL helper payload forwarding and hash-only read-back verification.
- Adapter apply tests proving URL read-back mismatch returns `apply_unknown` with `mutation_applied:true`.
- Adapter detail tests proving exact event detail returns URL hash proof without raw URL.
- CLI tests proving event URL arguments are forwarded for plan/apply and operation mismatches are rejected.
- MCP tests proving event URL plan plus invalid-token apply preview binding without live EventKit mutation and operation mismatches are rejected.
- Swift source assertions for `event.url`, expected URL SHA-256 binding, URL parser validation, `includeURLProof`, and `event_url_read_back_mismatch`.
- Runtime synthetic smoke proving direct allow-listed event URL plan/apply hash proof, direct safe non-HTTP URL plan/apply hash proof, MCP event URL plan plus invalid-token apply, and MCP safe non-HTTP URL plan plus invalid-token apply.

## Still Blocked

Attendees, invitations, organizer mutation, travel time, recurrence delete, existing-recurring-event update/delete, custom/unbounded recurrence rules, recurrence exception editing, email/procedure alarms, non-allow-listed event URL schemes, calendar creation/deletion, account management, and bulk Calendar mutation remain blocked. URL clearing is handled by v1.95, not this set-URL gate.
