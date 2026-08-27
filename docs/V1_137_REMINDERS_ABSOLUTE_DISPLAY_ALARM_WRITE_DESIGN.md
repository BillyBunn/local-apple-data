# v1.137 Reminders Absolute Display Alarm Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.

This gate approves exact Reminder absolute display-alarm set and clear for one exact local EventKit Reminder after plan-token and explicit-confirmation checks. It does not approve relative, audio, email, geofence, procedure, attachment, image, sharing, rich-content, or bulk alarm mutation.

No relative, audio, email, geofence, procedure, attachment, image, sharing, rich-content, or bulk alarm mutation is approved.

## Approved Operations

- `set_absolute_display_alarm`
- `clear_display_alarm`

CLI aliases are `set-absolute-display-alarm` and `clear-display-alarm`.

## Inputs

- Exact opaque `reminders:reminder:eventkit:v1:` handle.
- `expected_title`.
- `expected_completed`.
- `expected_alarms_count`.
- `expected_alarms_sha256` when current alarms are present.
- `alarm_absolute_dates` for set.
- Matching approval token.
- Explicit `confirm_apply`.

`alarm_absolute_dates` accepts timezone-explicit absolute date-times only. The adapter normalizes them to UTC second precision, sorts and deduplicates them, and caps the list at eight dates. `clear_display_alarm` accepts no proposed dates and requires current alarms to be present.

## Plan Contract

Planning is non-mutating. It validates the operation, exact handle shape, expected title/completion fields, expected alarm-state fields, and proposed absolute display-alarm dates. It returns preview metadata, `mutation_applied:false`, `apply_available:true`, and an approval token whose fingerprint binds the exact proposed and expected state.

The preview does not return raw Reminder alarm state. Proposed set previews may show the normalized absolute dates the caller supplied.

## Apply Contract

Apply recomputes the plan and requires the matching approval token plus explicit confirmation.

Before mutation, the adapter fetches the exact current Reminder through EventKit with hash-only alarm proof. The Swift EventKit helper must recheck title, completion state, alarm count, and alarm-state hash before mutation. If current alarms exist and are not pure absolute display alarms, apply fails closed with `unsupported_alarm_state`.

For `set_absolute_display_alarm`, apply replaces the Reminder alarm list with absolute-date `EKAlarm` display alarms. Read-back for set is exact absolute-date proof. Success requires `read_back.display_alarm_verified:true`.

For `clear_display_alarm`, apply removes all current alarms only after the expected alarm state matches. Read-back for clear is alarm absence proof. Success requires `read_back.display_alarm_cleared_verified:true`.

No raw alarm state is returned in previews, read-back, warnings, logs, or runtime summaries. Apply returns `alarm_state_raw_returned:false`.

## Runtime Synthetic Smoke

Runtime synthetic smoke covers direct CLI-style adapter flow and MCP wrapper flow:

- Set absolute display alarm plan returns `status:"ok"`.
- Set absolute display alarm apply returns `status:"ok"`, `display_alarm_verified:true`, and the exact normalized date list.
- Clear display alarm plan returns `status:"ok"`.
- Clear display alarm apply returns `status:"ok"` and `display_alarm_cleared_verified:true`.

## Non-Goals

This release allows only exact-handle Reminder absolute display-alarm set and clear through the plan/apply/read-back gates above. Relative alarms, audio alarms, email alarms, geofence alarms, procedure alarms, raw alarm-state retrieval, attachment mutation, image mutation, sharing mutation, rich-content mutation, and bulk alarm mutation remain blocked.
