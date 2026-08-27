# V1.103 Calendar Audio Alarm Write Design

## Scope

This gate extends the existing bounded Calendar alarm write surface with optional audio alarms through public EventKit `EKAlarm.soundName`.

Approved inputs:

- `alarm_sound_name`: optional bare system sound name for create/update.
- `expected_alarm_sound_name`: optional bare system sound name for update/delete drift checks.

`alarm_sound_name` never creates an alarm by itself. It is valid only with `alarm_offsets_minutes` or `alarm_absolute_dates`. Empty sound name keeps the existing display-alarm behavior.

## Source Review

The local macOS SDK EventKit headers expose `EKAlarm.soundName` as the public property that changes an alarm to `EKAlarmTypeAudio`. The same headers expose `emailAddress` for email alarms, `structuredLocation` plus `proximity` for geofence/proximity alarms, and deprecated `url` procedure alarms. This gate approves only the sound-name property; structured geofence alarms are governed separately by v1.104, email alarms are governed separately by v1.108, and procedure alarms remain blocked.

## Planning Contract

Plan stays non-mutating. It validates:

- sound name is bounded text, not a path, and at most 128 characters
- sound name is supplied only when relative or absolute alarm triggers are supplied
- expected sound state follows the same rule for update/delete
- sound name is included in the idempotency key and approval fingerprint

Preview returns `alarm_sound_name` and `alarm_action` (`display` or `audio`) without reading private event content.

## Apply Contract

Apply requires the existing matching approval token and `confirm_apply:true`. The Swift helper re-validates `alarm_sound_name` and `expected_alarm_sound_name`, rejects malformed payloads, rejects email co-mutation and procedure alarms, rejects existing custom/path-like sound names before update/delete, rejects mixed display/audio alarm state in either order, applies the approved sound name to each newly written relative or absolute alarm, and saves through EventKit.

Read-back must prove the same `alarm_sound_name` on all alarms. If read-back is missing or mismatched, apply returns `apply_unknown` with `mutation_applied:true`.

## Out Of Scope

- email alarms outside `docs/V1_108_CALENDAR_EMAIL_ALARM_WRITE_DESIGN.md`
- geofence/proximity alarms outside `docs/V1_104_CALENDAR_GEOFENCE_ALARM_WRITE_DESIGN.md`
- procedure/URL alarms
- mixed display/audio alarms in one event
- sound playback verification beyond EventKit property read-back
- custom sound file paths
- broad alarm search or bulk mutation
