# V1.175 Calendar Future Series Calendar Move Write Design

Status: Apply-capable implementation.

This gate moves the selected occurrence and all future occurrences of one exact recurring Calendar event to one exact writable target calendar. It is local-only, EventKit-only, exact-handle gated, and proof-bound.

## Scope

- `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events`.
- Update-only on one occurrence-bound `calendar:event:v1:` handle.
- Move-only mutation using an exact `calendar:calendar:v1:` `target_calendar_handle` / `--target-calendar-handle` from Calendar target metadata output, resolved to one writable target calendar.
- Uses public writable `EKEvent.calendar` with the existing exact target-calendar selection gate from `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.
- No recurrence fields, `clear_recurrence`, title/notes mutation, plain-location mutation, timed reschedule, availability mutation, event URL mutation, structured-location mutation, display/action alarm mutation, all-day mutation, or procedure alarms; every proposed field except the target calendar must equal the expected state.
- Mirroring the selected-occurrence v1.122 gate, a move to the calendar the event is already on is accepted rather than refused as a no-op.

## Plan Contract

- Requires exact current title, calendar title, start/end, notes, all-day, time-zone, event URL state, structured-location state, alarm state, and recurrence bindings already used by the Calendar update gate.
- Requires exact previous, selected, and future same-series occurrence identities.
- Resolves the exact `calendar:calendar:v1:` target handle to one readable, writable target calendar before returning a preview; invalid, unreadable, or unwritable targets return an error preview before mutation.
- Binds expected recurrence presence, expected recurrence payload, selected occurrence identity, previous occurrence identity, future occurrence identity, the exact target calendar handle, and the resolved target-calendar verification state into the approval fingerprint through `future_series_calendar_move_requested`, `target_calendar_handle`, `target_calendar_verified`, `target_calendar_allows_content_modifications`, and `target_calendar_title`.
- Returns a normal `calendar-apply:v1:<approval_fingerprint>` token and keeps the operation non-mutating.

## Apply Contract

- Requires the matching approval token and explicit confirmation.
- Revalidates the selected occurrence and expected recurrence before mutation.
- Revalidates the previous and future occurrence identities against the selected series before mutation.
- Re-resolves the exact target calendar handle and re-checks target-calendar writability before mutation.
- Refuses recurrence add/replacement, recurrence clear, scalar fields, plain-location mutation, timed reschedule, availability mutation, event URL mutation, structured-location mutation, display/action alarm mutation, all-day mutation, or co-mutation with any other future-series update flag.
- The Swift helper assigns the resolved target `EKCalendar` to `event.calendar` and saves with EventKit `.futureEvents`.

## Read-Back Proof

Apply must prove:

- selected occurrence recurrence shape still matches expected recurrence and the read-back calendar matches the approved target calendar by identifier and title;
- future occurrence recurrence shape still matches expected recurrence and the read-back calendar matches the approved target calendar by identifier and title;
- previous occurrence remains present on the original expected calendar with the original expected title, plain/structured location, notes, all-day/timed state, availability, URL hash state, alarm state, and recurrence;
- helper returns `future_series_calendar_move_verified:true` and `previous_occurrence_calendar_verified:true` only after real verification;
- `future_series_update_read_back_mismatch` is returned instead of success when any proof fails.

## Implementation Notes

- Adapter plan binds expected recurrence, selected occurrence identity, previous occurrence identity, future occurrence identity, and the exact resolved target calendar through `future_series_calendar_move_requested`; the flag is presence-triggered by `target_calendar_handle` under `recurrence_update_scope:future_events` and excludes every other future-series shape flag, so exactly one of the nine future-series shapes can be true.
- The this_event-scoped `selected_occurrence_calendar_move_requested` flag keeps routing selected-occurrence moves to the v1.122 gate; future_events routing goes only to this gate.
- Adapter apply requires calendar-move, previous-calendar, selected, future, and previous proof booleans before reporting success and re-verifies the resolved target calendar identifier against the read-back event.
- CLI accepts and forwards `--recurrence-update-scope future-events` with the existing `--target-calendar-handle` flag and no recurrence fields.
- The Swift helper verifies selected and future read-back occurrences against the proposed target calendar title, verifies the previous occurrence against the original expected calendar title and original calendar identifier, and searches occurrences without calendar scoping so moved events are found on the target calendar.
- Runtime verifier proves direct and MCP future-series target-calendar move plan/apply paths through `calendar_future_series_calendar_move_*` and `mcp_calendar_future_series_calendar_move_*` keys including `calendar_future_series_calendar_move_apply_verified`, target-calendar read-back title keys, and previous-calendar preservation keys, with no raw calendar identifier keys.
- Named regressions include `test_apply_calendar_change_moves_future_series_to_exact_calendar`, `test_apply_calendar_change_rejects_missing_future_series_calendar_move_proof`, `test_plan_calendar_change_update_future_series_calendar_move_rejects_co_mutations`, `test_plan_calendar_change_update_future_series_calendar_move_excludes_title_mutation`, `test_plan_calendar_change_update_future_series_calendar_move_excludes_timed_mutation`, and `test_plan_calendar_change_future_series_calendar_move_scope_routing_regression`.

## Still Blocked

- Future-series scalar update is handled by `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`.
- Future-series timed reschedule is handled by `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`.
- Future-series availability update is handled by `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`.
- Future-series event URL set/clear is handled by `docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`.
- Future-series structured-location set/clear is handled by `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`.
- Future-series display-alarm-only set/clear is handled by `docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`.
- Future-series action-alarm set/clear is handled by `docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`.
- Future-series all-day set/clear/date-only reschedule is handled by `docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`.
- With this gate, future-series parity with the selected-occurrence v1.114-v1.122 gate family is complete; no further future-series field gate is pending in that family.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.
- Custom recurrence shapes beyond approved selector-backed EventKit rules.
