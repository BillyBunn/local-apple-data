# v1.176 Reminders Mixed Display Alarm Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.

This gate approves exact Reminder mixed absolute-plus-relative display-alarm set for one exact local EventKit Reminder after plan-token and explicit-confirmation checks. It also broadens `clear_display_alarm` so it can clear a current mixed absolute-plus-relative display-alarm state after the same expected-state binding. It approves exact mixed absolute-plus-relative display-alarm set/clear mutation with exact Reminder handle, expected title, expected completed state, expected alarm count, expected alarm-state SHA-256 when present, bounded relative offsets plus timezone-explicit absolute alarm dates, EventKit apply, exact mixed offset/date read-back or absence proof, and no raw alarm state return.

No audio, email, geofence, procedure, attachment, image, sharing, rich-content, or bulk alarm mutation is approved. Mixed states that include audio, email, geofence, or procedure alarms stay refused.

## Approved Operations

- `set_mixed_display_alarm`
- `clear_display_alarm`

CLI aliases are `set-mixed-display-alarm` and `clear-display-alarm`.

## Inputs

- Exact opaque `reminders:reminder:eventkit:v1:` handle.
- `expected_title`.
- `expected_completed`.
- `expected_alarms_count`.
- `expected_alarms_sha256` when current alarms are present.
- `alarm_offsets_minutes` for set.
- `alarm_absolute_dates` for set.
- Matching approval token.
- Explicit `confirm_apply`.

`set_mixed_display_alarm` requires both a non-empty `alarm_offsets_minutes` list and a non-empty `alarm_absolute_dates` list. `alarm_offsets_minutes` accepts integer minute offsets only; the adapter sorts and deduplicates offsets, caps the list at eight values, and refuses values outside -40320 through 40320 minutes. `alarm_absolute_dates` accepts timezone-explicit absolute date-times only; the adapter normalizes them to UTC second precision, sorts and deduplicates them, and caps the list at eight dates. The combined proposed alarm set is capped at eight alarms. `clear_display_alarm` accepts no proposed offsets or dates and requires current alarms to be present.

## Plan Contract

Planning is non-mutating. It validates the operation, exact handle shape, expected title/completion fields, expected alarm-state fields, and proposed mixed display-alarm offsets and dates. It returns preview metadata, `mutation_applied:false`, `apply_available:true`, and an approval token whose fingerprint binds the exact proposed and expected state.

The preview does not return raw Reminder alarm state. Proposed set previews may show the normalized relative offsets and normalized absolute dates the caller supplied.

## Apply Contract

Apply recomputes the plan and requires the matching approval token plus explicit confirmation.

Before mutation, the adapter fetches the exact current Reminder through EventKit with hash-only alarm proof. The Swift EventKit helper must recheck title, completion state, alarm count, and alarm-state hash before mutation. If current alarms exist and are not pure absolute, pure relative, or mixed absolute-plus-relative display alarms, apply fails closed with `unsupported_alarm_state`.

For `set_mixed_display_alarm`, apply replaces the Reminder alarm list with relative-offset plus absolute-date `EKAlarm` display alarms in one save. Read-back for set is exact order-independent mixed offset and date proof. Success requires `read_back.display_alarm_verified:true`.

For `clear_display_alarm`, apply removes all current alarms only after the expected alarm state matches. Read-back for clear accepts pure absolute, pure relative, or mixed absolute-plus-relative display-alarm state and returns alarm absence proof. Success requires `read_back.display_alarm_cleared_verified:true`.

No raw alarm state is returned in previews, read-back, warnings, logs, or runtime summaries. Apply returns `alarm_state_raw_returned:false`.

## Runtime Synthetic Smoke

Runtime synthetic smoke covers direct CLI-style adapter flow and MCP wrapper flow:

- Set mixed display alarm plan returns `status:"ok"`.
- Set mixed display alarm apply returns `status:"ok"`, `display_alarm_verified:true`, the exact normalized offset list, and the exact normalized date list.
- Clear mixed display alarm plan returns `status:"ok"`.
- Clear mixed display alarm apply returns `status:"ok"` and `display_alarm_cleared_verified:true`.

## Non-Goals

This release allows only exact-handle Reminder mixed absolute-plus-relative display-alarm set and broadened mixed display-alarm clear through the plan/apply/read-back gates above. Audio alarms, email alarms, geofence alarms, procedure alarms, mixed states that include audio/email/geofence/procedure alarms, raw alarm-state retrieval, attachment mutation, image mutation, sharing mutation, rich-content mutation, and bulk alarm mutation remain blocked.
