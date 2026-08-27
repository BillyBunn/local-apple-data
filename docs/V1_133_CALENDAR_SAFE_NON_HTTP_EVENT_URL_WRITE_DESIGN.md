# V1.133 Calendar Safe Non-HTTP Event URL Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the v1.94/v1.117 Calendar event URL gates from an earlier `http`/`https` policy to a strict allow-list: `http`, `https`, `mailto`, and `tel`. It does not approve arbitrary app schemes, `file`, `javascript`, `data`, `webcal`, private Apple schemes, raw URL output, attendees, invitations, travel time, procedure alarms, or bulk Calendar mutation.

## Source Review

- `EKCalendarItem.URL` is public and writable; `scripts/audit_calendar_public_surface.py --json` proves `url_writable:true` against this Mac's public EventKit headers.
- EventKit stores a nullable `URL`; URL scheme policy is a plugin privacy/safety gate, not an EventKit blocker.
- Attendees/organizer remain read-only in the audited headers, travel time has no writable public property, and procedure alarms remain deprecated/save-error-prone.

## Plan Contract

Planning accepts the existing `event_url` input for create/update and selected-occurrence update.

- `http` and `https` require a host, valid port, no embedded credentials, no whitespace, no control characters, and length at most 2048 characters.
- `mailto` requires exactly one recipient address and no query or fragment.
- `tel` requires exactly one bounded dial string and no query or fragment.
- All other schemes fail with `invalid_event_url`.
- Preview returns `event_url_scheme`, `event_url_domain`, `event_url_safe_sha256`, `event_url_requested`, and `url_present`; it never returns the raw URL. `event_url_domain` is empty for `mailto` and `tel`.
- Approval fingerprint binds the exact raw URL privately so apply must provide the same URL.

## Apply Contract

Apply recomputes the plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token and explicit confirmation, reruns the same URL validation, then sends the approved URL to the Swift EventKit helper.

Swift validation mirrors Python validation for the same scheme allow-list. Read-back remains hash-only through `event_url_safe_sha256` and `event_url_verified:true`; raw event URLs are not returned.

## Tests And Proof

- Adapter tests prove `mailto` and `tel` planning, raw URL non-disclosure, invalid-scheme refusal, unsafe `mailto` refusal, unsafe `tel` refusal, and apply payload binding/read-back hash proof.
- CLI tests prove `mailto` forwarding without raw URL preview.
- MCP tests prove `tel` plan binding and invalid-token apply without live EventKit mutation.
- Runtime verifier proves direct `tel` plan/apply hash proof and MCP `tel` plan plus invalid-token apply through the plugin runner.
- Swift helper source is typechecked and mirrors Python scheme validation.

## Still Blocked

Non-allow-listed event URL schemes, raw event URL return, attendee/invitation/organizer mutation, travel time, procedure alarms, custom recurrence shapes beyond approved selector-backed finite EventKit rules, silent default-calendar mutation, non-synthetic calendar management, and bulk Calendar mutation remain blocked.
