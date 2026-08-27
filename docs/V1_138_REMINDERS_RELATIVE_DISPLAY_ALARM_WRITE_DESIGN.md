# v1.138 Reminders Relative Display Alarm Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.

This gate approves exact Reminder relative display-alarm set for one exact local EventKit Reminder after plan-token and explicit-confirmation checks. It also broadens `clear_display_alarm` so it can clear a current pure absolute or pure relative display-alarm state after the same expected-state binding.

No mixed absolute-plus-relative Reminder alarm state, audio, email, geofence, procedure, attachment, image, sharing, rich-content, or bulk alarm mutation is approved.

## Approved Operations

- `set_relative_display_alarm`
- `clear_display_alarm`

CLI aliases are `set-relative-display-alarm` and `clear-display-alarm`.

## Inputs

- Exact opaque `reminders:reminder:eventkit:v1:` handle.
- `expected_title`.
- `expected_completed`.
- `expected_alarms_count`.
- `expected_alarms_sha256` when current alarms are present.
- `alarm_offsets_minutes` for set.
- Matching approval token.
- Explicit `confirm_apply`.

`alarm_offsets_minutes` accepts integer minute offsets only. The adapter sorts and deduplicates offsets, caps the list at eight values, and refuses values outside -40320 through 40320 minutes. `clear_display_alarm` accepts no proposed offsets and requires current alarms to be present.

## Plan Contract

Planning is non-mutating. It validates the operation, exact handle shape, expected title/completion fields, expected alarm-state fields, and proposed relative display-alarm offsets. It returns preview metadata, `mutation_applied:false`, `apply_available:true`, and an approval token whose fingerprint binds the exact proposed and expected state.

The preview does not return raw Reminder alarm state. Proposed set previews may show the normalized relative offsets the caller supplied.

## Apply Contract

Apply recomputes the plan and requires the matching approval token plus explicit confirmation.

Before mutation, the adapter fetches the exact current Reminder through EventKit with hash-only alarm proof. The Swift EventKit helper must recheck title, completion state, alarm count, and alarm-state hash before mutation. If current alarms exist and are not pure absolute display alarms or pure relative display alarms, apply fails closed with `unsupported_alarm_state`.

For `set_relative_display_alarm`, apply replaces the Reminder alarm list with relative-offset `EKAlarm` display alarms. Read-back for set is exact relative-offset proof. Success requires `read_back.display_alarm_verified:true`.

For `clear_display_alarm`, apply removes all current alarms only after the expected alarm state matches. Read-back for clear accepts pure absolute or pure relative display-alarm state and returns alarm absence proof. Success requires `read_back.display_alarm_cleared_verified:true`.

No raw alarm state is returned in previews, read-back, warnings, logs, or runtime summaries. Apply returns `alarm_state_raw_returned:false`.

## Runtime Synthetic Smoke

Runtime synthetic smoke covers direct CLI-style adapter flow and MCP wrapper flow:

- Set relative display alarm plan returns `status:"ok"`.
- Set relative display alarm apply returns `status:"ok"`, `display_alarm_verified:true`, and the exact normalized offset list.
- Clear pure relative display alarm plan returns `status:"ok"`.
- Clear pure relative display alarm apply returns `status:"ok"` and `display_alarm_cleared_verified:true`.
- Clear display alarm plan returns `status:"ok"`.
- Clear display alarm apply returns `status:"ok"` and `display_alarm_cleared_verified:true`.

## Non-Goals

This release allows only exact-handle Reminder relative display-alarm set and broadened pure display-alarm clear through the plan/apply/read-back gates above. Mixed absolute-plus-relative Reminder alarm state, audio alarms, email alarms, geofence alarms, procedure alarms, raw alarm-state retrieval, attachment mutation, image mutation, sharing mutation, rich-content mutation, and bulk alarm mutation remain blocked.
