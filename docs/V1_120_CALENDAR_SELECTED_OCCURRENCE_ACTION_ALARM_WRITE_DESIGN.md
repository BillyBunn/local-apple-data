# V1.120 Calendar Selected Recurring Occurrence Action Alarm Write Design

Status: Apply-capable implementation.

This gate extends the selected recurring occurrence alarm update surface to
audio, email, and structured geofence alarm action set/clear. It stays
local-only, EventKit-only, exact-handle gated, occurrence-bound,
approval-token gated, and metadata-only.

Uses public EventKit `saveEvent:span:commit:` with `EKSpanThisEvent` to mutate
only the selected occurrence. Uses public `EKAlarm.soundName`,
`EKAlarm.emailAddress`, `EKAlarm.proximity`, and `EKAlarm.structuredLocation`.
Email alarm output is hash-only; raw email addresses are accepted only as
plan/apply input and never returned.

This is the selected recurring occurrence action alarm set/clear gate.

## Approved Shape

- `recurrence_update_scope`: adapter/MCP string, currently only `this_event`.
- `--recurrence-update-scope this-event`: CLI spelling.
- Operation must be `update`.
- Target must be an exact occurrence-bound `calendar:event:v1:` handle from
  Calendar metadata output.
- Setting audio alarms uses exact `alarm_offsets_minutes` or
  `alarm_absolute_dates` plus bounded `alarm_sound_name`.
- Setting email alarms uses exact `alarm_offsets_minutes` or
  `alarm_absolute_dates` plus bounded raw `alarm_email_address` as plan/apply
  input and hash-only `alarm_email_address_sha256` in preview/read-back.
- Setting structured geofence alarms uses exact `alarm_proximity` plus bounded
  `alarm_structured_location`.
- Clearing an action while keeping a display trigger passes the exact proposed
  display trigger and omits action fields.
- Clearing all alarms passes an explicit empty proposed trigger list.
- Omitted proposed alarm trigger and action fields preserve the expected alarm
  state for selected recurring occurrence updates.
- Expected-state binding uses display trigger state plus
  `expected_alarm_sound_name`, `expected_alarm_email_address_sha256`, or
  `expected_alarm_proximity` plus `expected_alarm_structured_location` when
  current action state exists.
- Optional title, plain notes, timed start/end/time-zone, availability, event
  URL, or structured-location changes may be included only through the already
  approved selected occurrence gates.
- Proposed and expected `all_day` must both be false.
- Target calendar and recurrence fields must match the expected state or be
  absent as required.

## Planning Contract

Planning resolves the selected occurrence from the current EventKit event list,
proves the handle binds start/end identity, proves the event is recurring with a supported bounded recurrence payload, and binds a sibling occurrence for
preservation proof.

The preview includes:

- `preview.target.expected_state.alarm_offsets_minutes` or
  `preview.target.expected_state.alarm_absolute_dates`.
- Expected action state with `alarm_action`, `alarm_sound_name`,
  `alarm_email_address_sha256`, or geofence fields when present.
- Proposed trigger/action state with raw email redacted to
  `alarm_email_address_sha256`.
- `preview.proposed.alarm_action_update_requested:true` when action state is
  explicitly set or cleared.
- `preview.proposed.selected_occurrence_alarm_update_requested:true` when any
  selected occurrence alarm trigger or action field is explicitly proposed.
- `preview.proposed.recurrence_update_scope:"this_event"`.
- `preview.proposed.occurrence_start_date` / `occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_start_date` /
  `adjacent_occurrence_end_date`.
- Hash-only sibling URL, plain-location, structured-location, and alarm-state
  preservation fields.

Invalid scope, non-update operation, missing occurrence identity, non-recurring
target, missing adjacent occurrence, all-day mutation, recurrence mutation,
recurrence clearing, action/trigger conflict, missing expected action state for
clearing/replacing current action alarms, or raw email output returns an error
preview before mutation. Target-calendar move is governed by
`docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.

## Apply Contract

Apply re-plans, requires the exact approval token and explicit confirmation,
re-resolves the selected occurrence, re-checks recurrence shape,
occurrence/sibling identity, expected trigger/action state, and hash-only
sibling URL/plain-location/structured-location/alarm state, then sends the
occurrence identity plus proposed trigger/action state to the Swift EventKit
helper.

The Swift helper finds the selected occurrence by event identifier plus expected
start/end, validates exact expected state including action alarm state, applies
only approved action alarms or explicit action clearing, saves with `span:.thisEvent`, then reads back the selected occurrence and adjacent
occurrence at their approved times. The adjacent occurrence proof returns no raw
sibling location, URL, or email address.

Success requires:

- selected occurrence read-back matches the approved trigger and action state;
- selected occurrence read-back returns email alarm state only as SHA-256;
- selected occurrence read-back matches approved title/plain
  location/notes/start/end/time-zone/availability/event-URL/structured-location
  state;
- adjacent occurrence remains present and recurring with URL, plain-location,
  structured-location, and alarm-state hash-only state preserved;
- helper returns `selected_occurrence_updated_verified:true`,
  `action_alarm_verified:true`, and
  `adjacent_occurrence_verified_present:true`;
- adapter returns `alarm_action_verified:true` and
  `adjacent_occurrence_alarm_verified:true`.

If read-back proof is incomplete, apply returns `apply_unknown` with
`mutation_applied:true` instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct plan/apply for selected
occurrence audio alarm set, email alarm set, structured geofence alarm set,
audio-action clear to display alarm, email-action clear to display alarm, and
structured-geofence action clear to display alarm, plus MCP plan/apply for
audio, email, and structured geofence set and clear.

Direct keys include
`calendar_recurrence_update_audio_alarm_plan_status`,
`calendar_recurrence_update_audio_alarm_plan_requested`,
`calendar_recurrence_update_audio_alarm_apply_status`,
`calendar_recurrence_update_audio_alarm_apply_verified`,
`calendar_recurrence_update_audio_alarm_apply_sound`,
`calendar_recurrence_update_email_alarm_plan_status`,
`calendar_recurrence_update_email_alarm_plan_sha256`,
`calendar_recurrence_update_email_alarm_apply_status`,
`calendar_recurrence_update_email_alarm_apply_verified`,
`calendar_recurrence_update_email_alarm_apply_sha256`,
`calendar_recurrence_update_geofence_alarm_plan_status`,
`calendar_recurrence_update_geofence_alarm_plan_proximity`,
`calendar_recurrence_update_geofence_alarm_apply_status`,
`calendar_recurrence_update_geofence_alarm_apply_verified`,
`calendar_recurrence_update_geofence_alarm_apply_proximity`,
`calendar_recurrence_update_audio_alarm_clear_plan_status`,
`calendar_recurrence_update_audio_alarm_clear_apply_status`,
`calendar_recurrence_update_audio_alarm_clear_apply_verified`,
`calendar_recurrence_update_audio_alarm_clear_apply_action`,
`calendar_recurrence_update_email_alarm_clear_plan_status`,
`calendar_recurrence_update_email_alarm_clear_apply_status`,
`calendar_recurrence_update_email_alarm_clear_apply_verified`,
`calendar_recurrence_update_email_alarm_clear_apply_action`,
`calendar_recurrence_update_email_alarm_clear_apply_sha256`,
`calendar_recurrence_update_geofence_alarm_clear_plan_status`,
`calendar_recurrence_update_geofence_alarm_clear_apply_status`,
`calendar_recurrence_update_geofence_alarm_clear_apply_verified`,
`calendar_recurrence_update_geofence_alarm_clear_apply_action`, and
`calendar_recurrence_update_geofence_alarm_clear_apply_proximity`.

MCP keys include
`mcp_calendar_recurrence_update_audio_alarm_plan_status`,
`mcp_calendar_recurrence_update_audio_alarm_apply_status`,
`mcp_calendar_recurrence_update_audio_alarm_apply_verified`,
`mcp_calendar_recurrence_update_email_alarm_plan_status`,
`mcp_calendar_recurrence_update_email_alarm_apply_status`,
`mcp_calendar_recurrence_update_email_alarm_apply_verified`,
`mcp_calendar_recurrence_update_geofence_alarm_plan_status`,
`mcp_calendar_recurrence_update_geofence_alarm_apply_status`, and
`mcp_calendar_recurrence_update_geofence_alarm_apply_verified`,
`mcp_calendar_recurrence_update_audio_alarm_clear_plan_status`,
`mcp_calendar_recurrence_update_audio_alarm_clear_apply_status`,
`mcp_calendar_recurrence_update_audio_alarm_clear_apply_verified`,
`mcp_calendar_recurrence_update_email_alarm_clear_plan_status`,
`mcp_calendar_recurrence_update_email_alarm_clear_apply_status`,
`mcp_calendar_recurrence_update_email_alarm_clear_apply_verified`,
`mcp_calendar_recurrence_update_geofence_alarm_clear_plan_status`,
`mcp_calendar_recurrence_update_geofence_alarm_clear_apply_status`, and
`mcp_calendar_recurrence_update_geofence_alarm_clear_apply_verified`.

Source tests cover selected occurrence audio, email, and geofence alarm set,
omitted proposed alarm fields preserving existing email action state without raw
email re-entry, explicit audio/email/geofence action clear to display alarm,
Swift helper selected occurrence action read-back proof, raw email non-echo, and
write-design audit coverage.
