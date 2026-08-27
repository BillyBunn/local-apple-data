# V1.108 Calendar Email Alarm Write Design

## Scope

Status: Apply-capable implementation.

This gate extends the bounded Calendar alarm write surface with exact email alarms through public EventKit `EKAlarm.emailAddress`.

Approved inputs:

- `alarm_email_address`: optional bounded email address for create/update.
- `expected_alarm_email_address_sha256`: optional update/delete drift binding.

`alarm_email_address` never creates an alarm by itself. It is valid only with `alarm_offsets_minutes` or `alarm_absolute_dates`. Empty email address keeps the existing display-alarm behavior.

## Source Review

The local macOS SDK EventKit headers expose `EKAlarm.emailAddress` as the public property that changes an alarm to `EKAlarmTypeEmail`. `EKAlarmTypeEmail` is documented as an alarm that sends an email. This gate approves only the exact address-bound EventKit property behind the existing plan/apply approval token. Audio alarms remain governed by v1.103, structured geofence alarms by v1.104, and procedure/URL alarms remain blocked.

## Planning Contract

Plan stays non-mutating. It validates:

- email address is bounded text, ASCII-printable, and at most 254 characters
- email address is supplied only when relative or absolute alarm triggers are supplied
- email address is not mixed with audio or geofence alarm actions
- expected email state follows the same trigger/action rules for update/delete
- address SHA-256 is included in the idempotency key and approval fingerprint

Preview returns only `alarm_email_address_sha256`, `alarm_action:email`, and `alarm_kind` (`email_relative` or `email_absolute`). The raw email address is never returned in preview, read-back, logs, docs, or runtime summary.

## Apply Contract

Apply requires the existing matching approval token and `confirm_apply:true`. The Swift helper re-validates `alarm_email_address` and `expected_alarm_email_address_sha256`, rejects malformed payloads, rejects procedure alarms, rejects mixed display/audio/email alarm state in one event, applies the approved email address to each newly written relative or absolute alarm, and saves through EventKit.

Read-back must prove the same `alarm_email_address_sha256` on all alarms. It reports `alarm_email_address_sha256_verified:true` only after that proof. If read-back is missing or mismatched, apply returns `apply_unknown` with `alarm_email_read_back_mismatch` and `mutation_applied:true`.

Runtime verifier proves direct plan/apply hash-only read-back and MCP plan plus invalid-token apply proof.

## Out Of Scope

- audio alarms outside `docs/V1_103_CALENDAR_AUDIO_ALARM_WRITE_DESIGN.md`
- geofence/proximity alarms outside `docs/V1_104_CALENDAR_GEOFENCE_ALARM_WRITE_DESIGN.md`
- procedure/URL alarms
- mixed display/email alarms in one event
- delivery verification beyond EventKit property read-back
- broad alarm search or bulk mutation
