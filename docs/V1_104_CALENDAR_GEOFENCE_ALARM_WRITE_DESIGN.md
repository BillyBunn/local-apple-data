# V1.104 Calendar Geofence Alarm Write Design

## Scope

Status: Apply-capable implementation.

This gate extends the bounded Calendar alarm write surface with exact structured geofence alarms through public EventKit `EKAlarm.proximity` and public EventKit `EKAlarm.structuredLocation`.

Approved inputs:

- `alarm_proximity`: optional geofence trigger with `enter` or `leave`.
- `alarm_structured_location`: required bounded structured location object when `alarm_proximity` is set.
- `expected_alarm_proximity`: optional update/delete drift binding.
- `expected_alarm_structured_location`: optional update/delete drift binding.

This gate approves one geofence alarm per event. It does not approve email-alarm co-mutation, procedure alarms, multiple geofence alarms, or mixing geofence alarms with relative, absolute, audio, or email alarms.

## Source Review

The local macOS SDK EventKit headers expose `EKAlarm.proximity` and `EKAlarm.structuredLocation` as writable public properties. `EKStructuredLocation` exposes title, optional `geoLocation`, and optional `radius`. The same headers expose email alarms and deprecated procedure/URL alarms. Email alarms are governed separately by v1.108; procedure alarms remain blocked because they add local procedure side effects beyond this bounded geofence gate.

## Planning Contract

Plan stays non-mutating. It validates:

- `alarm_proximity` is `enter` or `leave`
- `alarm_structured_location` has a bounded title plus optional paired latitude/longitude and radius
- proximity and structured location are supplied together
- Rejects relative offsets, absolute dates, audio sound names, or email addresses when a geofence alarm is requested.
- expected geofence state follows the same rules for update/delete
- Binds the full canonical geofence into the approval fingerprint and idempotency key.

Preview returns metadata-only `alarm_proximity`, canonical `alarm_structured_location`, `alarm_kind:geofence`, and `alarm_action:geofence`.

## Apply Contract

Apply requires the existing matching approval token and `confirm_apply:true`. The Swift helper re-validates proximity and structured location, rejects malformed payloads, rejects email/procedure/audio mixed alarm state, rejects multiple geofence alarms, applies one `EKAlarm` with the approved proximity and structured location, and saves through EventKit.

Read-back must prove matching `alarm_proximity` and `alarm_structured_location` before reporting `alarm_geofence_verified:true`. If read-back is missing or mismatched, apply returns `apply_unknown` with `mutation_applied:true`.

Runtime verifier proves direct plan/apply read-back and MCP plan plus invalid-token apply proof.

## Out Of Scope

- email alarms outside `docs/V1_108_CALENDAR_EMAIL_ALARM_WRITE_DESIGN.md`
- procedure/URL alarms
- multiple geofence alarms
- mixing geofence alarms with relative, absolute, audio, or email alarms
- background geofence delivery verification beyond EventKit property read-back
- broad alarm search or bulk mutation
