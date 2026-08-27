from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_release_readiness.py"
SPEC = importlib.util.spec_from_file_location("audit_release_readiness", SCRIPT_PATH)
assert SPEC is not None
audit_release_readiness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["audit_release_readiness"] = audit_release_readiness
SPEC.loader.exec_module(audit_release_readiness)
mutation_gate = sys.modules["audit_mutation_gates"]
surface_contract = sys.modules["audit_surface_contract"]
write_design_gate = sys.modules["audit_write_design_gates"]


def _make_minimal_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    for relative in audit_release_readiness.REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative}\n", encoding="utf-8")

    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "local-apple-data"',
                'version = "0.1.0"',
                'description = "Synthetic"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "local-apple-data",
                "version": "0.1.0+test",
                "description": _plugin_description(),
                "interface": {
                    "capabilities": ["Read", "Search", "Write", "MCP", "Local"],
                    "longDescription": _plugin_long_description(),
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 0.1.0+test\n",
        encoding="utf-8",
    )
    (root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"local-apple-data": {"command": "./scripts/run_mcp_server.sh"}}}),
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(
        ".DS_Store\n.venv/\n__pycache__/\n.pytest_cache/\n.claude/\n.env\n.env.*\n",
        encoding="utf-8",
    )
    (root / mutation_gate.AGENTS_DOC).write_text(
        mutation_gate.REQUIRED_MUTATION_GATE_TEXT[mutation_gate.AGENTS_DOC]
        + ".\n"
        + "\n".join(mutation_gate.REQUIRED_MUTATION_DETAIL_TEXT[mutation_gate.AGENTS_DOC])
        + "\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "The only apply-capable mutation surfaces are "
        + mutation_gate.CANONICAL_APPLY_SURFACE_SUMMARY
        + ".\n"
        + mutation_gate.REQUIRED_MUTATION_GATE_TEXT["README.md"]
        + ".\n"
        + "\n".join(mutation_gate.REQUIRED_MUTATION_DETAIL_TEXT["README.md"])
        + "\n"
        "The Reminders exact same-source list-move write design gate is documented in `docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md`.\n"
        "The Reminders exact URL update/clear write design gate is documented in `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`.\n"
        "The Reminders exact absolute display-alarm set/clear write design gate is documented in `docs/V1_137_REMINDERS_ABSOLUTE_DISPLAY_ALARM_WRITE_DESIGN.md`.\n"
        "The Reminders exact relative display-alarm set and broadened pure display-alarm clear write design gate is documented in `docs/V1_138_REMINDERS_RELATIVE_DISPLAY_ALARM_WRITE_DESIGN.md`.\n"
        "local-apple-data notes apply --json --operation create-folder\n"
        "The Notes exact child-folder create write design gate is documented in `docs/V1_57_NOTES_FOLDER_CREATE_WRITE_DESIGN.md`.\n"
        "The Notes exact empty child-folder move write design gate is documented in `docs/V1_158_NOTES_FOLDER_MOVE_WRITE_DESIGN.md`.\n"
        "The Notes exact-folder rename write design gate is documented in `docs/V1_58_NOTES_FOLDER_RENAME_WRITE_DESIGN.md`.\n",
        encoding="utf-8",
    )
    (root / "docs/MUTATION_GATES.md").write_text(
        mutation_gate.REQUIRED_MUTATION_GATE_TEXT["docs/MUTATION_GATES.md"] + ".\n"
        + "\n".join(mutation_gate.REQUIRED_MUTATION_DETAIL_TEXT["docs/MUTATION_GATES.md"])
        + "\n"
        + "\n".join(write_design_gate.REQUIRED_CURRENT_DOC_TEXT["docs/MUTATION_GATES.md"])
        + "\n"
        "Calendar simple count-bound daily/weekly/monthly/yearly recurrence create and date-only all-day inference through the plan/apply/read-back contract in `docs/V1_90_CALENDAR_RECURRENCE_DATE_ONLY_WRITE_DESIGN.md`.\n"
        "Calendar explicit default-calendar create planning through the plan-only exact-handle resolver in `docs/V1_91_CALENDAR_DEFAULT_CALENDAR_CREATE_WRITE_DESIGN.md`.\n"
        "Calendar exact availability create/update through the plan/apply/read-back contract in `docs/V1_92_CALENDAR_AVAILABILITY_WRITE_DESIGN.md`.\n"
        "Calendar simple count-bound recurrence add-to-non-recurring-event update through the plan/apply/read-back contract in `docs/V1_93_CALENDAR_RECURRENCE_UPDATE_WRITE_DESIGN.md`.\n"
        "Calendar exact allow-listed event URL create/update through the plan/apply/read-back contract in `docs/V1_94_CALENDAR_EVENT_URL_WRITE_DESIGN.md`.\n"
        "Calendar safe non-HTTP event URL schemes through the plan/apply/read-back contract in `docs/V1_133_CALENDAR_SAFE_NON_HTTP_EVENT_URL_WRITE_DESIGN.md`.\n"
        "Calendar weekly weekday recurrence selection through the plan/apply/read-back contract in `docs/V1_99_CALENDAR_WEEKLY_WEEKDAY_RECURRENCE_WRITE_DESIGN.md`.\n"
        "Calendar first-visible and mid-series recurrence clearing through the plan/apply/read-back contract in `docs/V1_100_CALENDAR_RECURRENCE_CLEAR_WRITE_DESIGN.md`.\n"
        "Calendar mid-series recurrence replacement through the plan/apply/read-back contract in `docs/V1_126_CALENDAR_RECURRENCE_REPLACEMENT_WRITE_DESIGN.md`.\n"
        "Calendar monthly weekday recurrence selection through the plan/apply/read-back contract in `docs/V1_113_CALENDAR_MONTHLY_WEEKDAY_RECURRENCE_WRITE_DESIGN.md`.\n"
        "Calendar monthly day-of-month recurrence selection through the plan/apply/read-back contract in `docs/V1_101_CALENDAR_MONTHDAY_RECURRENCE_WRITE_DESIGN.md`.\n"
        "Calendar structured event location create/update through the plan/apply/read-back contract in `docs/V1_102_CALENDAR_STRUCTURED_LOCATION_WRITE_DESIGN.md`.\n"
        "Calendar structured event location clearing through the plan/apply/read-back contract in `docs/V1_107_CALENDAR_STRUCTURED_LOCATION_CLEAR_WRITE_DESIGN.md`.\n"
        "Calendar exact audio alarms through the plan/apply/read-back contract in `docs/V1_103_CALENDAR_AUDIO_ALARM_WRITE_DESIGN.md`.\n"
        "Calendar exact email alarms through the plan/apply/read-back contract in `docs/V1_108_CALENDAR_EMAIL_ALARM_WRITE_DESIGN.md`.\n"
        "Calendar recurrence end-date bounds through the plan/apply/read-back contract in `docs/V1_109_CALENDAR_RECURRENCE_END_DATE_WRITE_DESIGN.md`.\n"
        "Calendar yearly day-of-year and week-of-year recurrence selection through the plan/apply/read-back contract in `docs/V1_110_CALENDAR_YEARLY_DAY_WEEK_RECURRENCE_WRITE_DESIGN.md`.\n"
        "Calendar yearly month nth-weekday recurrence selection through the plan/apply/read-back contract in `docs/V1_111_CALENDAR_YEARLY_MONTH_NTH_WEEKDAY_RECURRENCE_WRITE_DESIGN.md`.\n"
        "Calendar yearly month day-of-month recurrence selection through the plan/apply/read-back contract in `docs/V1_112_CALENDAR_YEARLY_MONTH_DAY_RECURRENCE_WRITE_DESIGN.md`.\n"
        "Calendar exact structured geofence alarms through the plan/apply/read-back contract in `docs/V1_104_CALENDAR_GEOFENCE_ALARM_WRITE_DESIGN.md`.\n"
        "Calendar monthly nth-weekday recurrence selection through the plan/apply/read-back contract in `docs/V1_105_CALENDAR_MONTHLY_NTH_WEEKDAY_RECURRENCE_WRITE_DESIGN.md`.\n"
        "Calendar yearly month recurrence selection through the plan/apply/read-back contract in `docs/V1_106_CALENDAR_YEARLY_MONTH_RECURRENCE_WRITE_DESIGN.md`.\n"
        "Calendar explicit unbounded recurrence through the plan/apply/read-back contract in `docs/V1_139_CALENDAR_UNBOUNDED_RECURRENCE_WRITE_DESIGN.md`.\n"
        "For recurrence create they require a matching approval token, explicit confirmation, `recurrence_frequency` of daily, weekly, monthly, or yearly, optional `recurrence_weekdays` only for weekly recurrence, monthly recurrence, or yearly week-of-year recurrence, optional `recurrence_month_days` only for monthly recurrence, optional `recurrence_month_weekdays` only for monthly recurrence, monthly selectors never mixed with each other, optional `recurrence_year_month_days` only with `recurrence_year_months`, optional `recurrence_year_month_weekdays` only with `recurrence_year_months`, optional exactly one of `recurrence_year_months`, `recurrence_year_days`, or `recurrence_year_weeks` only when recurrence is yearly, `recurrence_year_weeks` only with exact `recurrence_weekdays`, `recurrence_interval` from 1 through 4, exactly one recurrence bound using either `recurrence_count` from 2 through 52, timezone `recurrence_end_date` within 3650 days of `start_date`, or explicit `recurrence_unbounded:true`, EventKit apply, and read-back recurrence metadata.\n"
        "For recurrence update they require an exact event handle, expected current state, a currently non-recurring EventKit event, a matching approval token, explicit confirmation, `recurrence_frequency` of daily, weekly, monthly, or yearly, optional `recurrence_weekdays` only for weekly recurrence, monthly recurrence, or yearly week-of-year recurrence, optional `recurrence_month_days` only for monthly recurrence, optional `recurrence_month_weekdays` only for monthly recurrence, monthly selectors never mixed with each other, optional `recurrence_year_month_days` only with `recurrence_year_months`, optional `recurrence_year_month_weekdays` only with `recurrence_year_months`, optional exactly one of `recurrence_year_months`, `recurrence_year_days`, or `recurrence_year_weeks` only when recurrence is yearly, `recurrence_year_weeks` only with exact `recurrence_weekdays`, `recurrence_interval` from 1 through 4, exactly one recurrence bound using either `recurrence_count` from 2 through 52, timezone `recurrence_end_date` within 3650 days of `start_date`, or explicit `recurrence_unbounded:true`, EventKit apply, and read-back recurrence metadata.\n"
        "For explicit default-calendar create planning, `use_default_calendar` is accepted only on plan, resolves the current default calendar to an exact `calendar:calendar:v1:` handle, and apply must use that approved `calendar_handle` rather than re-reading the default calendar.\n"
        "For availability create/update they require a matching approval token, explicit confirmation, `availability` of busy, free, tentative, or unavailable, update-only `expected_availability` drift binding, EventKit calendar support-mask validation, EventKit apply, and read-back availability metadata.\n"
        "For event URL create/update they require a matching approval token, explicit confirmation, an allow-listed `event_url`, update/delete `expected_event_url_present` and `expected_event_url_sha256` binding when a current URL exists, EventKit apply, and hash-only URL read-back proof.\n"
        "Calendar exact event URL clearing through the plan/apply/read-back contract in `docs/V1_95_CALENDAR_EVENT_URL_CLEAR_WRITE_DESIGN.md`.\n"
        "For event URL clearing they require update-only `clear_event_url:true`, no `event_url`, exact `expected_event_url_present:true`, exact `expected_event_url_sha256`, a matching approval token, explicit confirmation, EventKit apply, and read-back absence proof with `event_url_cleared_verified:true`.\n"
        "Calendar selected recurring occurrence delete through the plan/apply/read-back contract in `docs/V1_96_CALENDAR_RECURRING_OCCURRENCE_DELETE_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence delete they require delete-only `recurrence_delete_scope:this_event`, expected recurrence presence binding, occurrence start/end identity binding, adjacent occurrence identity binding, a matching approval token, explicit confirmation, EventKit `.thisEvent` removal, selected-occurrence absence proof, and adjacent-occurrence preservation proof.\n"
        "Calendar selected recurring occurrence scalar update through the plan/apply/read-back contract in `docs/V1_114_CALENDAR_SELECTED_OCCURRENCE_UPDATE_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence scalar update they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity binding, title/plain-location/notes-only mutation, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence read-back proof, and adjacent-occurrence preservation proof.\n"
        "Calendar selected recurring occurrence timed reschedule through the plan/apply/read-back contract in `docs/V1_115_CALENDAR_SELECTED_OCCURRENCE_RESCHEDULE_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence timed reschedule they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity binding, timed start/end/time-zone mutation, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence read-back proof at the approved new time, original occurrence absence proof, and adjacent-occurrence preservation proof.\n"
        "Calendar selected recurring occurrence availability update through the plan/apply/read-back contract in `docs/V1_116_CALENDAR_SELECTED_OCCURRENCE_AVAILABILITY_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence availability update they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity binding, proposed `availability`, required `expected_availability`, target-calendar support-mask validation, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence availability read-back proof, and adjacent-occurrence preservation proof.\n"
        "Calendar selected recurring occurrence event URL set/clear through the plan/apply/read-back contract in `docs/V1_117_CALENDAR_SELECTED_OCCURRENCE_EVENT_URL_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence event URL set/clear they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity and hash-only URL-state binding, exact allow-listed `event_url` or update-only `clear_event_url:true`, required URL expected-state binding for clear, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence hash-only event URL read-back or absence proof, no raw URL return, and adjacent-occurrence presence/recurrence/URL-state preservation proof.\n"
        "Calendar selected recurring occurrence structured location set/clear through the plan/apply/read-back contract in `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence structured location set/clear they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location state binding, bounded `structured_location` with explicit expected structured-location absence or exact `expected_structured_location` replacement binding, update-only `clear_structured_location:true` with exact `expected_structured_location`, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence structured-location read-back or structured/plain-location absence proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location preservation proof.\n"
        "Calendar selected recurring occurrence display alarm set/clear through the plan/apply/read-back contract in `docs/V1_119_CALENDAR_SELECTED_OCCURRENCE_DISPLAY_ALARM_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence display alarm set/clear they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact `expected_alarm_offsets_minutes` or `expected_alarm_absolute_dates` binding, relative or absolute display-alarm-only proposed state, no audio/email/geofence alarm action state, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence display-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof.\n"
        "Calendar selected recurring occurrence action alarm set/clear through the plan/apply/read-back contract in `docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence action alarm set/clear they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state for set or clear, raw email input accepted only as plan/apply input and no raw email output, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence action-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof.\n"
        "Calendar selected recurring occurrence all-day set/clear/date-only reschedule through the plan/apply/read-back contract in `docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence all-day set/clear/date-only reschedule they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected all-day/time-zone state binding, date-only proposed start/end for all-day set or same-state all-day date-only reschedule, explicit proposed time zone for all-day-to-timed clear, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence all-day read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof.\n"
        "Calendar future-event recurring span delete through the plan/apply/read-back contract in `docs/V1_97_CALENDAR_RECURRING_FUTURE_DELETE_WRITE_DESIGN.md`.\n"
        "For future-event recurring span delete they require delete-only `recurrence_delete_scope:future_events`, expected recurrence presence binding, selected occurrence start/end identity binding, previous occurrence identity binding, future occurrence identity binding, a matching approval token, explicit confirmation, EventKit `.futureEvents` removal, selected/future occurrence absence proof, and previous-occurrence preservation proof.\n"
        "Calendar whole-series recurring-event delete through the plan/apply/read-back contract in `docs/V1_98_CALENDAR_RECURRING_SERIES_DELETE_WRITE_DESIGN.md`.\n"
        "For whole-series recurring-event delete they require delete-only `recurrence_delete_scope:all_events`, expected recurrence presence binding, selected occurrence start/end identity binding, future occurrence identity binding, bounded previous-occurrence absence proof, a matching approval token, explicit confirmation, EventKit `.futureEvents` removal from the selected first visible occurrence, selected/future occurrence absence proof, and bounded previous-occurrence absence proof.\n"
        "For recurrence clearing they require update-only `clear_recurrence:true`, no scalar, calendar move, URL, alarm, availability, or recurrence-add co-mutation, exact recurrence shape binding, selected occurrence start/end identity binding, future occurrence identity binding, bounded previous-occurrence absence proof for first-visible clearing or exact previous-occurrence identity/preservation proof for mid-series `recurrence_update_scope:future_events`, a matching approval token, explicit confirmation, EventKit `.futureEvents` recurrence clear from the selected occurrence, selected-occurrence non-recurring read-back, future occurrence absence proof, and previous-occurrence absence or preservation proof.\n"
        "For mid-series recurrence replacement they require update-only `recurrence_update_scope:future_events`, no scalar, calendar move, URL, alarm, availability, structured-location, or clear-recurrence co-mutation, exact expected recurrence shape binding, exact approved replacement recurrence binding, selected occurrence start/end identity binding, previous occurrence identity binding, future occurrence identity binding, a matching approval token, explicit confirmation, EventKit `.futureEvents` save with a new `EKRecurrenceRule`, selected-occurrence replacement recurrence read-back, future occurrence replacement recurrence proof, original future-slot absent-or-replaced proof, and previous-occurrence preservation proof.\n"
        "For structured event location create/update they require a matching approval token, explicit confirmation, a bounded `structured_location` object with title plus optional paired latitude/longitude and radius, conflict refusal against plain `location`, optional update/delete `expected_structured_location` binding, EventKit `EKStructuredLocation` apply, and read-back structured-location proof.\n"
        "For structured event location clearing they require update-only `clear_structured_location:true`, no `structured_location`, empty proposed `location`, exact `expected_structured_location`, a matching approval token, explicit confirmation, EventKit apply, and read-back absence proof with `structured_location_present:false`, `location_present:false`, and `structured_location_cleared_verified:true`.\n"
        "For audio alarms they require relative or absolute alarm triggers, a bounded bare `alarm_sound_name`, optional update/delete `expected_alarm_sound_name`, EventKit `EKAlarm.soundName` apply, and read-back sound-name proof.\n"
        "For email alarms they require relative or absolute alarm triggers, a bounded `alarm_email_address`, optional update/delete `expected_alarm_email_address_sha256`, EventKit `EKAlarm.emailAddress` apply, hash-only preview and read-back proof, and no raw email address output.\n"
        "For structured geofence alarms they require exactly one `alarm_proximity` of enter or leave, one bounded `alarm_structured_location` object with title plus optional paired latitude/longitude and radius, no relative/absolute/audio/email alarm co-mutation, optional update/delete `expected_alarm_proximity` and `expected_alarm_structured_location` binding, EventKit `EKAlarm.proximity` plus `EKAlarm.structuredLocation` apply, and read-back geofence proof.\n"
        "For monthly weekday recurrence selection they require a matching approval token, explicit confirmation, `recurrence_frequency` of monthly, one or more exact `recurrence_weekdays`, no `recurrence_month_days` or `recurrence_month_weekdays`, `recurrence_interval` from 1 through 4, exactly one recurrence bound using either `recurrence_count` from 2 through 52, timezone `recurrence_end_date` within 3650 days of `start_date`, or explicit `recurrence_unbounded:true`, EventKit `EKRecurrenceDayOfWeek` values without week numbers through `daysOfTheWeek`, and read-back recurrence metadata.\n"
        "For yearly month recurrence selection they require a matching approval token, explicit confirmation, `recurrence_frequency` of yearly, one or more `recurrence_year_months` integers from 1 through 12, `recurrence_interval` from 1 through 4, exactly one recurrence bound using either `recurrence_count` from 2 through 52, timezone `recurrence_end_date` within 3650 days of `start_date`, or explicit `recurrence_unbounded:true`, EventKit `monthsOfTheYear` apply, and read-back recurrence metadata.\n"
        "For yearly month day-of-month recurrence selection they require a matching approval token, explicit confirmation, `recurrence_frequency` of yearly, one or more `recurrence_year_months` integers from 1 through 12, one or more `recurrence_year_month_days` integers from -31 through -1 or 1 through 31, no `recurrence_year_month_weekdays`, `recurrence_year_days`, or `recurrence_year_weeks`, `recurrence_interval` from 1 through 4, exactly one recurrence bound using either `recurrence_count` from 2 through 52, timezone `recurrence_end_date` within 3650 days of `start_date`, or explicit `recurrence_unbounded:true`, EventKit `monthsOfTheYear` plus `daysOfTheMonth` apply, and read-back recurrence metadata.\n"
        "For yearly day/week recurrence selection they require a matching approval token, explicit confirmation, `recurrence_frequency` of yearly, exactly one of `recurrence_year_days` integers from -366 through -1 or 1 through 366 or `recurrence_year_weeks` integers from -53 through -1 or 1 through 53, exact `recurrence_weekdays` when `recurrence_year_weeks` is used, `recurrence_interval` from 1 through 4, exactly one recurrence bound using either `recurrence_count` from 2 through 52, timezone `recurrence_end_date` within 3650 days of `start_date`, or explicit `recurrence_unbounded:true`, EventKit `daysOfTheYear` or `weeksOfTheYear` plus `daysOfTheWeek` apply, and read-back recurrence metadata.\n"
        "For yearly month nth-weekday recurrence selection they require a matching approval token, explicit confirmation, `recurrence_frequency` of yearly, one or more `recurrence_year_months` integers from 1 through 12, one or more `recurrence_year_month_weekdays` weekday plus week-number selectors from -5 through -1 or 1 through 5, no `recurrence_year_days` or `recurrence_year_weeks`, `recurrence_interval` from 1 through 4, exactly one recurrence bound using either `recurrence_count` from 2 through 52, timezone `recurrence_end_date` within 3650 days of `start_date`, or explicit `recurrence_unbounded:true`, EventKit `monthsOfTheYear` plus `daysOfTheWeek` apply, and read-back recurrence metadata.\n"
        "For monthly nth-weekday recurrence selection they require a matching approval token, explicit confirmation, `recurrence_frequency` of monthly, one or more `recurrence_month_weekdays` values with weekday plus week number, no `recurrence_month_days`, `recurrence_interval` from 1 through 4, exactly one recurrence bound using either `recurrence_count` from 2 through 52, timezone `recurrence_end_date` within 3650 days of `start_date`, or explicit `recurrence_unbounded:true`, EventKit `EKRecurrenceDayOfWeek` apply through `daysOfTheWeek`, and read-back recurrence metadata.\n"
        "Calendar custom recurrence shapes beyond approved selector-backed EventKit rules, implicit unbounded recurrence, attendees, invitations, silent default-calendar guessing or default-calendar mutation, timed-event time-zone inference, travel time, availability outside explicit support-mask validation, non-allow-listed event URL schemes, procedure alarms, and bulk Calendar mutation remain blocked.\n"
        "recurrence outside simple count-, end-date-, or explicit-unbounded daily/weekly/monthly/yearly create, add-to-non-recurring-event update, weekly weekday selection, monthly weekday selection, monthly day-of-month selection, monthly nth-weekday selection, yearly month/month-day/month-nth-weekday/day-of-year/week-of-year plus explicit weekday selection for week-of-year and selector-backed set-position filtering, selected-occurrence title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, selected-occurrence delete, future-event recurring span delete, whole-series recurring-event delete, or first-visible or mid-series recurrence clearing, mid-series recurrence replacement.\n"
        "custom recurrence shapes beyond approved selector-backed EventKit rules.\n"
        "Reminders exact same-source list move through the plan/apply/read-back contract in `docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md`.\n"
        "For list-move they require a matching approval token, explicit confirmation, exact opaque reminder handle, exact opaque expected current-list handle, exact opaque same-source target-list handle, expected title, expected completion state, expected current list name checked before any already-target shortcut, EventKit apply, and `target_list_verified:true` identity proof.\n"
        "iCloud Drive exact folder Trash through the plan/apply/read-back metadata and absence-proof contracts in `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md` and `docs/V1_146_ICLOUD_DRIVE_NON_EMPTY_FOLDER_TRASH_WRITE_DESIGN.md`.\n"
        "For trash-folder they require a matching approval token, explicit confirmation, exact opaque directory handle, expected directory metadata SHA-256, metadata drift refusal, recoverable Trash move, original absence proof, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, `non_empty_allowed:true`, and metadata-only read-back.\n"
        "iCloud Drive exact folder move, including non-empty directories, through the plan/apply/read-back metadata-proof contract in `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md` and `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`.\n"
        "For move-folder they require a matching approval token, explicit confirmation, exact opaque directory handle, exact opaque target parent handle, expected directory metadata SHA-256, metadata drift refusal, descendant-parent refusal, no-overwrite target proof, source/target presence proof, `non_empty_allowed:true`, and metadata-only read-back.\n"
        "iCloud Drive exact selected-folder copy through the plan/apply/read-back metadata-proof contracts in `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md` and `docs/V1_147_ICLOUD_DRIVE_NON_EMPTY_FOLDER_COPY_WRITE_DESIGN.md`.\n"
        "For copy-folder they require a matching approval token, explicit confirmation, exact opaque directory handle, exact opaque target parent handle, expected directory metadata SHA-256, private bounded source-tree binding, metadata/tree drift refusal, hidden/symlink/package/tree-size refusal, descendant-parent refusal, no-overwrite target proof, source preservation proof, target presence proof, `non_empty_allowed:true`, no child listing, and metadata-only read-back.\n"
        "iCloud Drive exact selected-folder permanent delete through the plan/apply/read-back metadata, hidden-staging, and absence-proof contract in `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`.\n"
        "For delete-folder they require a matching approval token, explicit confirmation, one exact directory handle, expected directory metadata SHA-256, private bounded source-tree binding, metadata/tree drift refusal, hidden/symlink/package/tree-size refusal, hidden staging identity proof, bounded permanent staged-tree removal, original absence proof, `verified_absent:true`, `permanently_deleted:true` only on successful removal, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, `non_empty_allowed:true`, no child listing, and metadata-only read-back.\n"
        "iCloud Drive exact text-file permanent delete through the plan/apply/read-back content-hash, exact file identity, random-only hidden-staging, and absence-proof contract in `docs/V1_68_ICLOUD_DRIVE_DELETE_TEXT_WRITE_DESIGN.md`.\n"
        "For delete-text they require a matching approval token, explicit confirmation, one exact supported text-file handle, expected current SHA-256, approval fingerprint binding to exact file identity, stale identity/token replay refusal, current-content drift refusal, no-follow/package/symlink traversal refusal, random-only hidden staging identity proof, permanent unlink, original absence proof, `verified_absent:true`, `permanently_deleted:true` only on successful removal, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, and no raw path return.\n"
        "iCloud Drive exact regular-file rename/copy/move through the plan/apply/read-back metadata-proof contract in `docs/V1_127_ICLOUD_DRIVE_REGULAR_FILE_RENAME_COPY_MOVE_WRITE_DESIGN.md`.\n"
        "For rename-file/copy-file/move-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected file metadata SHA-256, metadata drift refusal, no-overwrite target proof, source/target presence proof, metadata-only read-back, `content_text_returned:false`, `content_hash_returned:false`, no content hash return, and no raw path return.\n"
        "iCloud Drive exact local regular-file import through the plan/apply/read-back metadata-proof contract in `docs/V1_129_ICLOUD_DRIVE_IMPORT_FILE_WRITE_DESIGN.md`.\n"
        "For import-file they require a matching approval token, explicit confirmation, one caller-selected local non-text non-package regular file outside the configured iCloud Drive root, one exact target parent handle, private source identity/content binding, no-overwrite target proof, source preservation proof, metadata-only target read-back, `source_path_returned:false`, `source_hash_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no source path/hash return, no content hash return, and no raw path return.\n"
        "iCloud Drive exact regular-file replace through the plan/apply/read-back metadata-proof contract in `docs/V1_130_ICLOUD_DRIVE_REPLACE_FILE_WRITE_DESIGN.md`.\n"
        "For replace-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected target metadata SHA-256, one caller-selected local non-text non-package regular file outside the configured iCloud Drive root, private source identity/content binding, source/target extension match, target metadata drift refusal, source preservation proof, byte replacement proof, metadata-only target read-back, `source_path_returned:false`, `source_hash_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no source path/hash return, no content hash return, and no raw path return.\n"
        "iCloud Drive exact regular-file Trash through the plan/apply/read-back metadata-proof contract in `docs/V1_131_ICLOUD_DRIVE_TRASH_FILE_WRITE_DESIGN.md`.\n"
        "For trash-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected target metadata SHA-256, target metadata drift refusal, no-follow/package/symlink traversal refusal, recoverable Trash move, original absence proof, metadata-only read-back, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no content hash return, and no raw path return.\n"
        "iCloud Drive exact regular-file permanent delete through the plan/apply/read-back metadata-proof contract in `docs/V1_132_ICLOUD_DRIVE_DELETE_FILE_WRITE_DESIGN.md`.\n"
        "For delete-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected target metadata SHA-256, target metadata drift refusal, no-follow/package/symlink traversal refusal, hidden staging identity proof, permanent unlink, original absence proof, metadata-only read-back, `staging_path_returned:false`, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no content hash return, and no raw path return.\n"
        "Reminders exact URL update/clear through the plan/apply/read-back contract in `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`.\n"
        "For Reminder URL update/clear they require a matching approval token, explicit confirmation, exact opaque reminder handle, expected title, exact expected URL presence, exact expected URL SHA-256 when a URL is present, allow-listed URL scheme, ASCII-only URL input, EventKit apply, hash-only URL read-back proof for update, absence proof for clear, and no raw URL return.\n"
        "Reminders exact absolute display-alarm set/clear through the plan/apply/read-back contract in `docs/V1_137_REMINDERS_ABSOLUTE_DISPLAY_ALARM_WRITE_DESIGN.md`.\n"
        "For Reminder absolute display-alarm set/clear they require a matching approval token, explicit confirmation, exact opaque reminder handle, expected title, expected completed state, exact expected alarm count, exact expected alarm-state SHA-256 when alarms are present, bounded timezone-explicit absolute alarm dates, EventKit apply, exact date read-back proof for set, absence proof for clear, and no raw alarm state return.\n"
        "Reminders exact relative display-alarm set and broadened pure display-alarm clear through the plan/apply/read-back contract in `docs/V1_138_REMINDERS_RELATIVE_DISPLAY_ALARM_WRITE_DESIGN.md`.\n"
        "For Reminder relative display-alarm set and pure display-alarm clear they require a matching approval token, explicit confirmation, exact opaque reminder handle, expected title, expected completed state, exact expected alarm count, exact expected alarm-state SHA-256 when alarms are present, bounded integer minute offsets for set, EventKit apply, exact offset read-back proof for set, absence proof for pure display-alarm clear, and no raw alarm state return.\n"
        "| Contacts | Create contact; exact scalar/method/rich-field/image update; exact group membership; exact group create/rename/delete; exact batch; exact-contact delete | Contacts.framework helper | Approved live for the listed non-note operations. Confirm exact handle plus `delete_safe_sha256` current-state binding and absence proof for delete, exact group membership, exact group create/rename/delete, exact batch, omitted method-array preservation, provided method-array replacement, and explicit empty-array clears. Exact note append/set/clear/merge is designed and synthetic-testable, but the live helper fails closed with `contacts_note_unavailable` before mutation. |\n"
        "- Deleting Contacts outside the approved exact-contact delete gate.\n"
        "- Contacts update outside the approved exact name/organization/email/phone/URL update gate, note mutation outside the approved exact note append gate, delete outside the approved exact-contact delete gate, or bulk operations.\n"
        "- Reminders delete outside the approved exact-handle delete gate.\n"
        "caller-selected local file attachments for draft/send/reply/reply-all/forward\n"
        "- Mail attachments outside the approved draft/send/reply/reply-all/forward local-file attachment gates.\n"
        "Mail synthetic `LAD-TEST-*` mailbox create/rename, plus source-gated synthetic mailbox delete/cleanup only when public Mail.app deletion plus exact target-state binding, mailbox-scoped absence proof, and Mail-idle guards succeed through the plan/apply/read-back contract.\n"
        "- Mail source attachment/non-body-part forwarding remains blocked.\n",
        encoding="utf-8",
    )
    (root / "docs/V1_33_FULL_CRUD_PRIORITY_PLAN.md").write_text(
        _write_design_doc_text(),
        encoding="utf-8",
    )
    (root / "docs/WRITE_TOOL_ROADMAP.md").write_text(
        mutation_gate.CANONICAL_APPLY_SURFACE_SUMMARY
        + " are the only approved write surfaces.\n",
        encoding="utf-8",
    )
    (root / "docs/PRIVACY_MODEL.md").write_text(
        "non-mutating iCloud Drive append-text, replace-text, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file planning for exact requested file handles or parent handles plus expected current content, metadata hash, or private source-file binding\n"
        "non-mutating iCloud Drive exact folder rename planning for exact requested directory handles plus `metadata_sha256`\n"
        "Rejects unexpected `content_text`, file handles, expected-current SHA input, hidden names, path separators, and package suffixes.\n"
        "Rejects hidden CLI iCloud Drive `--root` overrides outside `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`\n"
        "trash folders outside the exact folder Trash gate, move folders outside the exact folder move gate, copy folders outside the exact selected-folder copy gate\n"
        "The v1.52 apply implementation:\n"
        "Returns metadata-only read-back with `privacy.content_inspected:false`, no content hash, and no child listing.\n"
        "Never logs folder names, handles, raw paths, approval fingerprints, or approval tokens.\n"
        "Never logs folder names, handles, metadata hashes, raw paths, approval fingerprints, or approval tokens.\n"
        "Sender search matching is limited to returned-safe masked account labels and masked email previews\n"
        "The v1.82 phase extends exact sender selection to `send_message`, `reply_message`, `reply_all_message`, and `forward_message`\n"
        "The implemented v1.136 Reminders URL update/clear gate is `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`\n"
        "binds exact Reminder handle, expected title, expected URL presence, expected URL SHA-256 when present, allow-listed URL input with ASCII-only validation, EventKit apply, hash-only URL read-back or absence proof, and no raw URL return\n"
        "The implemented v1.176 Reminders mixed display-alarm set/clear gate is `docs/V1_176_REMINDERS_MIXED_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "exact mixed absolute-plus-relative display-alarm set/clear mutation with exact Reminder handle, expected title, expected completed state, expected alarm count, expected alarm-state SHA-256 when present, bounded relative offsets plus timezone-explicit absolute alarm dates, EventKit apply, exact mixed offset/date read-back or absence proof, and no raw alarm state return\n"
        "The implemented v1.177 Reminders start-date set/clear gate is `docs/V1_177_REMINDERS_START_DATE_WRITE_DESIGN.md`\n"
        "binds exact Reminder handle for update, expected title, exact expected current start-date state for update, a date-only or timezone-explicit start date that is on or before the due date when both are present, EventKit apply, exact start-date read-back proof for set, and start-date absence proof for clear\n"
        "The implemented v1.177 Reminders recurrence create/update/clear gate is `docs/V1_177_REMINDERS_RECURRENCE_WRITE_DESIGN.md`\n"
        "reuses the exact Calendar recurrence payload contract and shared `_normalize_recurrence` builder, binds exact Reminder handle for update, expected title, exact expected recurrence shape for update, a due date anchor for any recurring reminder, bounded recurrence selectors identical to Calendar recurrence, EventKit apply, exact recurrence-shape read-back proof for create or replace, and recurrence absence proof for clear\n"
        "The implemented v1.137 Reminders absolute display-alarm set/clear gate is `docs/V1_137_REMINDERS_ABSOLUTE_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "binds exact Reminder handle, expected title, expected completed state, expected alarm count, expected alarm-state SHA-256 when present, timezone-explicit absolute alarm dates, EventKit apply, exact date read-back or absence proof, and no raw alarm state return\n"
        "The implemented v1.114 Calendar selected recurring occurrence scalar update gate is `docs/V1_114_CALENDAR_SELECTED_OCCURRENCE_UPDATE_WRITE_DESIGN.md`\n"
        "binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, title/plain-location/notes-only mutation, EventKit `.thisEvent` save, selected-occurrence read-back proof, and adjacent-occurrence preservation proof\n"
        "The implemented v1.115 Calendar selected recurring occurrence reschedule gate is `docs/V1_115_CALENDAR_SELECTED_OCCURRENCE_RESCHEDULE_WRITE_DESIGN.md`\n"
        "The implemented v1.116 Calendar selected recurring occurrence availability gate is `docs/V1_116_CALENDAR_SELECTED_OCCURRENCE_AVAILABILITY_WRITE_DESIGN.md`\n"
        "The implemented v1.117 Calendar selected recurring occurrence event URL gate is `docs/V1_117_CALENDAR_SELECTED_OCCURRENCE_EVENT_URL_WRITE_DESIGN.md`\n"
        "binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only URL-state binding, exact allow-listed event URL or `clear_event_url`, expected URL state binding for clear, EventKit `.thisEvent` save, selected-occurrence hash-only URL read-back or absence proof, no raw URL return, and adjacent-occurrence presence/recurrence/URL-state preservation proof\n"
        "binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, timed start/end/time-zone mutation, EventKit `.thisEvent` save, selected-occurrence read-back proof at the approved new time, original occurrence absence proof, and adjacent-occurrence preservation proof\n"
        "future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update\n"
        "The implemented v1.167 Calendar future-series scalar update gate is `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`\n"
        "The implemented v1.168 Calendar future-series timed reschedule gate is `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`\n"
        "The implemented v1.169 Calendar future-series availability gate is `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`\n"
        "The implemented v1.170 Calendar future-series event URL gate is `docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`\n"
        "The implemented v1.171 Calendar future-series structured-location gate is `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event structured-location set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded structured-location input or `clear_structured_location`, expected structured-location binding for clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus structured-location read-back or absence proof, and previous-occurrence preservation proof\n"
        "The implemented v1.172 Calendar future-series display-alarm gate is `docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event display-alarm set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded relative or absolute display-alarm input or display-alarm clear, exact expected display-alarm state binding, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus display-alarm read-back or absence proof, and previous-occurrence preservation proof\n"
        "The implemented v1.173 Calendar future-series action-alarm gate is `docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event action-alarm set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state, raw email input accepted only as plan/apply input, no raw email output, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus action-alarm read-back or absence proof, and previous-occurrence preservation proof\n"
        "The implemented v1.174 Calendar future-series all-day gate is `docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event all-day set/clear/date-only reschedule mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected all-day/time-zone state binding, date-only proposed start/end for all-day set or same-state all-day date-only reschedule, explicit proposed time zone for all-day-to-timed clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus all-day read-back proof, original selected/future slot absence-or-approved-replacement proof, and previous-occurrence preservation proof\n"
        "The implemented v1.175 Calendar future-series target-calendar move gate is `docs/V1_175_CALENDAR_FUTURE_SERIES_CALENDAR_MOVE_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event target-calendar move mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact `calendar:calendar:v1:` target handle, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus target-calendar read-back proof, and previous-occurrence original-calendar preservation proof\n"
        "original selected/future slot absence-or-approved-replacement proof when dates move\n"
        "The implemented v1.118 Calendar selected recurring occurrence structured-location gate is `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        "binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location state binding, expected structured-location absence or exact expected structured-location binding, EventKit `.thisEvent` save, selected-occurrence structured-location read-back or structured/plain-location absence proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location preservation proof\n"
        "The implemented v1.119 Calendar selected recurring occurrence display-alarm gate is `docs/V1_119_CALENDAR_SELECTED_OCCURRENCE_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected display-alarm state binding, EventKit `.thisEvent` save, selected-occurrence display-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof\n"
        "The implemented v1.120 Calendar selected recurring occurrence action-alarm gate is `docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`\n"
        "binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state, raw email input accepted only as plan/apply input, no raw email output, EventKit `.thisEvent` save, selected-occurrence action-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof\n"
        "## v1.53 iCloud Drive Trash Planning And Apply\n",
        encoding="utf-8",
    )
    (root / "docs/THREAT_MODEL.md").write_text(
        "No content replacement outside the exact replace-text or replace-file gates, folder creation outside the exact create-folder or bounded create-folder-path gates, folder rename outside the exact folder rename gate, folder move outside the exact folder move gate, folder copy outside the exact selected-folder copy gate, folder delete outside the exact selected-folder delete gate, trash/delete outside the exact trash-text, exact folder trash, exact regular-file trash, or exact delete-file gates, file permanent delete outside the exact delete-text or delete-file gates, import outside the exact import-file gate, rename/copy/move outside the exact text-file or regular-file gates, empty Trash, binary/document content generation, regular-file mutation outside exact import-file, exact replace-file, exact trash-file, exact delete-file, or metadata-only rename/copy/move gates, unbounded recursive folder write/copy/delete, hidden-file write, symlink/package traversal, raw path write, unbounded folder copy, or broad folder copy is approved.\n"
        "use fd-based no-follow exclusive `mkdir` plus metadata-only directory read-back and existing-directory idempotency for create-folder\n"
        "iCloud Drive bounded folder path creation through the plan/apply/read-back contract in `docs/V1_157_ICLOUD_DRIVE_FOLDER_PATH_CREATE_WRITE_DESIGN.md`\n"
        "For create-folder-path they require a matching approval token, explicit confirmation, exact opaque parent directory handle, plan-time stable parent identity binding, stale-parent token mismatch, one to three bounded folder components, fd-based no-follow `mkdir` or existing-directory idempotency per component, partial reporting if mutation begins before a later failure, final directory metadata read-back, `content_text_returned:false`, `content_hash_returned:false`, no raw path return, and no content return.\n"
        "Hidden CLI iCloud Drive `--root` overrides are rejected outside `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`\n"
        "append-text is governed separately by v1.18, replace-text by v1.51, create-folder by v1.52, create-folder-path by v1.157, trash-text by v1.53, text-file rename/copy/move by v1.54, exact folder rename by v1.60 plus v1.145, exact folder Trash by v1.61 plus v1.146, exact folder move by v1.62 plus v1.145, exact empty folder copy by v1.63, bounded non-empty selected-folder copy by v1.147, and exact selected-folder delete by v1.67, exact text-file delete by v1.68, regular-file rename/copy/move by v1.127, import-file by v1.129, replace-file by v1.130, trash-file by v1.131, and delete-file by v1.132\n"
        "create-folder is governed separately by `docs/V1_52_ICLOUD_DRIVE_FOLDER_CREATE_WRITE_DESIGN.md`; create-folder-path is governed separately by `docs/V1_157_ICLOUD_DRIVE_FOLDER_PATH_CREATE_WRITE_DESIGN.md`\n"
        "create only one child folder under one exact normal parent folder with same-parent idempotency and metadata-only read-back\n"
        "resolves exact non-Trash/Junk `mail:mailbox:v1:` targets for `move_message` including cross-account exact targets\n"
        "exposes only opaque source/target account refs\n"
        "scopes Mail.app automation to selected accounts/nested-mailboxes/messages\n"
        "exact target mailbox\n"
        "optional bounded caller-selected local file attachments\n"
        "caller-selected local file attachments for draft/send/reply/reply-all/forward\n"
        "Mail attachment mutation outside the approved draft/send/reply/reply-all/forward local-file attachment gates remains blocked.\n"
        "Mail source attachment/non-body-part forwarding remains blocked.\n"
        "optional exact allow-listed event URL with hash-only read-back proof and update-only exact URL clearing\n"
        "update-only selected recurring occurrence title/plain-location/notes with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, EventKit `.thisEvent` save, selected-occurrence read-back proof, and adjacent-occurrence preservation proof\n"
        "update-only selected recurring occurrence timed start/end/time-zone mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, EventKit `.thisEvent` save, selected-occurrence read-back proof at the approved new time, original occurrence absence proof, and adjacent-occurrence preservation proof\n"
        "update-only selected recurring occurrence availability mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, required `expected_availability`, EventKit `.thisEvent` save, selected-occurrence availability read-back proof, and adjacent-occurrence preservation proof\n"
        "The implemented v1.114 Calendar selected recurring occurrence scalar update gate is `docs/V1_114_CALENDAR_SELECTED_OCCURRENCE_UPDATE_WRITE_DESIGN.md`\n"
        "The implemented v1.115 Calendar selected recurring occurrence reschedule gate is `docs/V1_115_CALENDAR_SELECTED_OCCURRENCE_RESCHEDULE_WRITE_DESIGN.md`\n"
        "The implemented v1.116 Calendar selected recurring occurrence availability gate is `docs/V1_116_CALENDAR_SELECTED_OCCURRENCE_AVAILABILITY_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence event URL set/clear mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only URL-state binding, exact allow-listed event URL or `clear_event_url`, expected URL state binding for clear, EventKit `.thisEvent` save, selected-occurrence hash-only URL read-back or absence proof, no raw URL return, and adjacent-occurrence presence/recurrence/URL-state preservation proof\n"
        "The implemented v1.117 Calendar selected recurring occurrence event URL gate is `docs/V1_117_CALENDAR_SELECTED_OCCURRENCE_EVENT_URL_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence structured-location set/clear mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location state binding, expected structured-location absence or exact expected structured-location binding, EventKit `.thisEvent` save, selected-occurrence structured-location read-back or structured/plain-location absence proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location preservation proof\n"
        "The implemented v1.118 Calendar selected recurring occurrence structured-location gate is `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence display alarm set/clear mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected display-alarm state binding, EventKit `.thisEvent` save, selected-occurrence display-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof\n"
        "The implemented v1.119 Calendar selected recurring occurrence display-alarm gate is `docs/V1_119_CALENDAR_SELECTED_OCCURRENCE_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence action alarm set/clear mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state, raw email input accepted only as plan/apply input, no raw email output, EventKit `.thisEvent` save, selected-occurrence action-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof\n"
        "The implemented v1.120 Calendar selected recurring occurrence action-alarm gate is `docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence all-day set/clear/date-only reschedule mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected all-day/time-zone state binding, date-only proposed start/end for all-day set or same-state all-day date-only reschedule, explicit proposed time zone for all-day-to-timed clear, EventKit `.thisEvent` save, selected-occurrence all-day read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof\n"
        "The implemented v1.121 Calendar selected recurring occurrence all-day gate is `docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence target-calendar move mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact `calendar:calendar:v1:` target handle, EventKit `.thisEvent` save, selected-occurrence target-calendar read-back proof, and adjacent-occurrence original-calendar preservation proof\n"
        "The implemented v1.122 Calendar selected recurring occurrence target-calendar move gate is `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event title/plain-location/notes mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus scalar read-back proof, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event timed reschedule mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, explicit expected/proposed time zones, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus timed read-back proof, original selected/future slot absence-or-approved-replacement proof when dates move, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event availability mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, expected/proposed availability, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus availability read-back proof, and previous-occurrence preservation proof\n"
        "The implemented v1.167 Calendar future-series scalar update gate is `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`\n"
        "The implemented v1.168 Calendar future-series timed reschedule gate is `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`\n"
        "The implemented v1.169 Calendar future-series availability gate is `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event event URL set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact allow-listed event URL or `clear_event_url`, expected URL state binding for clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus hash-only URL read-back or absence proof, no raw URL return, and previous-occurrence preservation proof\n"
        "The implemented v1.170 Calendar future-series event URL gate is `docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event structured-location set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded structured-location input or `clear_structured_location`, expected structured-location binding for clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus structured-location read-back or absence proof, and previous-occurrence preservation proof\n"
        "The implemented v1.171 Calendar future-series structured-location gate is `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event display-alarm set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded relative or absolute display-alarm input or display-alarm clear, exact expected display-alarm state binding, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus display-alarm read-back or absence proof, and previous-occurrence preservation proof\n"
        "The implemented v1.172 Calendar future-series display-alarm gate is `docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event action-alarm set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state, raw email input accepted only as plan/apply input, no raw email output, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus action-alarm read-back or absence proof, and previous-occurrence preservation proof\n"
        "The implemented v1.173 Calendar future-series action-alarm gate is `docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event all-day set/clear/date-only reschedule mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected all-day/time-zone state binding, date-only proposed start/end for all-day set or same-state all-day date-only reschedule, explicit proposed time zone for all-day-to-timed clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus all-day read-back proof, original selected/future slot absence-or-approved-replacement proof, and previous-occurrence preservation proof\n"
        "The implemented v1.174 Calendar future-series all-day gate is `docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event target-calendar move mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact `calendar:calendar:v1:` target handle, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus target-calendar read-back proof, and previous-occurrence original-calendar preservation proof\n"
        "The implemented v1.175 Calendar future-series target-calendar move gate is `docs/V1_175_CALENDAR_FUTURE_SERIES_CALENDAR_MOVE_WRITE_DESIGN.md`\n"
        "non-allow-listed event URL schemes\n"
        "raw event URL return\n",
        encoding="utf-8",
    )
    (root / "docs/CODEX_PLUGIN.md").write_text(
        "metadata-only read-back with `parent_folder_confirmed:true`\n"
        "exact child-folder create apply under one exact normal parent folder with metadata-only parent proof\n"
        "Rename-folder planning validates one exact directory `icloud:file:v1:` handle, expected directory `metadata_sha256`, bounded target folder name, no parent handle, and no content text\n"
        "Rename-folder apply requires the matching token, explicit confirmation, one exact directory handle, expected directory `metadata_sha256`, current metadata recheck, fd-relative no-overwrite rename, metadata-only source/target presence proof, `non_empty_allowed:true`, and no content hash or text return.\n"
        "Trash-folder apply requires the matching token, explicit confirmation, one exact directory handle, expected directory `metadata_sha256`, current metadata recheck, recoverable Trash move, metadata-only original absence proof, `empty_folder_confirmed` boolean read-back, `non_empty_allowed:true`, no raw Trash path return, and no content hash or text return.\n"
        "Move-folder apply requires the matching token, explicit confirmation, one exact directory handle, one exact target parent handle, expected directory `metadata_sha256`, current metadata recheck, descendant-parent refusal, fd-relative no-overwrite move, metadata-only source/target presence proof, `non_empty_allowed:true`, and no content hash or text return.\n"
        "Copy-folder apply requires the matching token, explicit confirmation, one exact directory handle, one exact target parent handle, expected directory `metadata_sha256`, private source-tree binding, current metadata/tree recheck, hidden/symlink/package/tree-size refusal, descendant-parent refusal, no-overwrite recursive copy, source preservation proof, metadata-only target presence proof, `empty_folder_confirmed` boolean read-back, `non_empty_allowed:true`, no child listing, and no content hash or text return.\n"
        "Delete-folder apply requires the matching token, explicit confirmation, one exact directory handle, expected directory `metadata_sha256`, private bounded source-tree binding, current metadata/tree recheck, hidden/symlink/package/tree-size refusal, hidden staging identity proof, bounded permanent staged-tree removal, metadata-only original absence proof, `verified_absent:true`, `permanently_deleted:true` only after successful removal, `empty_folder_confirmed` boolean read-back, `non_empty_allowed:true`, no raw Trash path return, no staging path return, no child listing, and no content hash or text return.\n"
        "Delete-text apply requires the matching token, explicit confirmation, one exact supported text-file handle, expected current SHA-256, root-aware preview recomputation, exact file identity approval binding, stale token replay refusal for recreated same-path/same-content files, current content recheck, no-follow/package/symlink refusal, random-only hidden staging identity proof, permanent unlink, original absence proof, `verified_absent:true`, `permanently_deleted:true` only after successful unlink, no raw Trash path return, no staging path return, and no content hash or text return.\n"
        "Regular-file rename/copy/move planning validates handle shape, expected `metadata_sha256`, bounded target filename, exact target parent handle when required, and no content text; apply resolves and enforces one exact non-text non-package regular file.\n"
        "Regular-file rename/copy/move apply requires the matching token, explicit confirmation, one exact non-text non-package regular-file handle, expected file `metadata_sha256`, current metadata recheck, no-overwrite target proof, metadata-only source/target presence proof, `content_text_returned:false`, `content_hash_returned:false`, no raw path return, and no content hash or text return.\n"
        "Delete-file planning validates one exact target regular-file handle, expected `metadata_sha256`, no parent handle, no filename, no source file, and no content text without resolving or writing iCloud Drive files.\n"
        "Delete-file apply requires the matching token, explicit confirmation, one exact non-text non-package regular-file handle, expected target `metadata_sha256`, current metadata recheck, no-follow hidden staging identity proof, permanent unlink, metadata-only original absence proof, `verified_absent:true`, `permanently_deleted:true` only after successful unlink, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no raw target path return, no raw Trash path return, no raw staging path return, and no content hash or text return.\n"
        "mid-series recurrence replacement with selected replacement recurrence read-back, future replacement proof, original future-slot absent-or-replaced proof, and previous preservation proof\n"
        "future-series recurring-event title/plain-location/notes update through `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`\n"
        "future-series recurring-event timed reschedule through `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`\n"
        "future-series recurring-event availability update through `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`\n"
        "future-series recurring-event event URL set/clear through `docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`\n"
        "future-series recurring-event structured-location set/clear through `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        "future-series recurring-event display-alarm set/clear through `docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "future-series recurring-event action-alarm set/clear through `docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`\n"
        "future-series recurring-event all-day set/clear/date-only reschedule through `docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`\n"
        "future-series recurring-event target-calendar move through `docs/V1_175_CALENDAR_FUTURE_SERIES_CALENDAR_MOVE_WRITE_DESIGN.md`\n"
        "`docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`\n"
        "`docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`\n"
        "`docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`\n"
        "`docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        "`docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "`docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`\n"
        "`docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`\n"
        "`docs/V1_175_CALENDAR_FUTURE_SERIES_CALENDAR_MOVE_WRITE_DESIGN.md`\n"
        "update-only future-series recurring-event title/plain-location/notes mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus scalar read-back proof, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event timed reschedule mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, explicit expected/proposed time zones, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus timed read-back proof, original selected/future slot absence-or-approved-replacement proof when dates move, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event availability mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, expected/proposed availability, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus availability read-back proof, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event event URL set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact allow-listed event URL or `clear_event_url`, expected URL state binding for clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus hash-only URL read-back or absence proof, no raw URL return, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event structured-location set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded structured-location input or `clear_structured_location`, expected structured-location binding for clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus structured-location read-back or absence proof, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event display-alarm set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded relative or absolute display-alarm input or display-alarm clear, exact expected display-alarm state binding, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus display-alarm read-back or absence proof, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event action-alarm set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state, raw email input accepted only as plan/apply input, no raw email output, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus action-alarm read-back or absence proof, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event all-day set/clear/date-only reschedule mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected all-day/time-zone state binding, date-only proposed start/end for all-day set or same-state all-day date-only reschedule, explicit proposed time zone for all-day-to-timed clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus all-day read-back proof, original selected/future slot absence-or-approved-replacement proof, and previous-occurrence preservation proof\n"
        "update-only future-series recurring-event target-calendar move mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact `calendar:calendar:v1:` target handle, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus target-calendar read-back proof, and previous-occurrence original-calendar preservation proof\n"
        "selected recurring occurrence title/plain-location/notes scalar update through `docs/V1_114_CALENDAR_SELECTED_OCCURRENCE_UPDATE_WRITE_DESIGN.md`, selected recurring occurrence timed reschedule through `docs/V1_115_CALENDAR_SELECTED_OCCURRENCE_RESCHEDULE_WRITE_DESIGN.md`, selected recurring occurrence availability update through `docs/V1_116_CALENDAR_SELECTED_OCCURRENCE_AVAILABILITY_WRITE_DESIGN.md`, selected recurring occurrence event URL set/clear through `docs/V1_117_CALENDAR_SELECTED_OCCURRENCE_EVENT_URL_WRITE_DESIGN.md`, selected recurring occurrence structured-location set/clear through `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`, selected recurring occurrence display-alarm set/clear through `docs/V1_119_CALENDAR_SELECTED_OCCURRENCE_DISPLAY_ALARM_WRITE_DESIGN.md`, selected recurring occurrence action-alarm set/clear through `docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`, and selected recurring occurrence all-day set/clear/date-only reschedule through `docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`, and selected recurring occurrence target-calendar move through `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence title/plain-location/notes with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, EventKit `.thisEvent` save, selected-occurrence read-back proof, and adjacent-occurrence preservation proof\n"
        "update-only selected recurring occurrence timed start/end/time-zone mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, EventKit `.thisEvent` save, selected-occurrence read-back proof at the approved new time, original occurrence absence proof, and adjacent-occurrence preservation proof\n"
        "update-only selected recurring occurrence availability mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, required `expected_availability`, EventKit `.thisEvent` save, selected-occurrence availability read-back proof, and adjacent-occurrence preservation proof\n"
        "update-only selected recurring occurrence event URL set/clear mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only URL-state binding, exact allow-listed event URL or `clear_event_url`, expected URL state binding for clear, EventKit `.thisEvent` save, selected-occurrence hash-only URL read-back or absence proof, no raw URL return, and adjacent-occurrence presence/recurrence/URL-state preservation proof\n"
        "selected recurring occurrence structured-location set/clear through `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence structured-location set/clear mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location state binding, expected structured-location absence or exact expected structured-location binding, EventKit `.thisEvent` save, selected-occurrence structured-location read-back or structured/plain-location absence proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location preservation proof\n"
        "selected recurring occurrence display-alarm set/clear through `docs/V1_119_CALENDAR_SELECTED_OCCURRENCE_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence display alarm set/clear mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected display-alarm state binding, EventKit `.thisEvent` save, selected-occurrence display-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof\n"
        "selected recurring occurrence action-alarm set/clear through `docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence action alarm set/clear mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state, raw email input accepted only as plan/apply input, no raw email output, EventKit `.thisEvent` save, selected-occurrence action-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof\n"
        "selected recurring occurrence all-day set/clear/date-only reschedule through `docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`, and selected recurring occurrence target-calendar move through `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`\n"
        "update-only selected recurring occurrence all-day set/clear/date-only reschedule mutation with `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected all-day/time-zone state binding, date-only proposed start/end for all-day set or same-state all-day date-only reschedule, explicit proposed time zone for all-day-to-timed clear, EventKit `.thisEvent` save, selected-occurrence all-day read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof\n"
        "selected recurring occurrence mutations outside title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move remain blocked\n"
        "including cross-account exact targets only through the v1.66 plan/apply gate with opaque source/target account refs\n"
        "same-account Archive/Trash resolution\n"
        "exact non-Trash/Junk target-mailbox resolution for `move_message` including cross-account exact targets\n"
        "sender search matching is limited to returned-safe masked account labels and masked email previews\n"
        "no raw account identifiers\n",
        encoding="utf-8",
    )
    (root / "docs/CAPABILITY_MATRIX.md").write_text(
        "Calendar v1.108-v1.175 gates are also current\n"
        "`docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        "`docs/V1_119_CALENDAR_SELECTED_OCCURRENCE_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "`docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`\n"
        "`docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`\n"
        "`docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`\n"
        "`docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`\n"
        "`docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`\n"
        "`docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`\n"
        "`docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        "`docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "`docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`\n"
        "`docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`\n"
        "`docs/V1_175_CALENDAR_FUTURE_SERIES_CALENDAR_MOVE_WRITE_DESIGN.md`\n"
        "future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update\n"
        "future-series recurring-event title/plain-location/notes update\n"
        "future-series recurring-event timed reschedule\n"
        "Reminders exact URL update/clear is governed by `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`\n"
        "Reminders exact absolute display-alarm set/clear is governed by `docs/V1_137_REMINDERS_ABSOLUTE_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        "Reminders exact relative display-alarm set and broadened pure display-alarm clear is governed by `docs/V1_138_REMINDERS_RELATIVE_DISPLAY_ALARM_WRITE_DESIGN.md`\n",
        encoding="utf-8",
    )
    (root / "docs/MACOS_SUPPORT.md").write_text(
        "mutate unbounded folder copy, recursive folder writes, or unbounded recursive folder delete\n",
        encoding="utf-8",
    )
    (root / "docs/FRESH_CHAT_HANDOFF.md").write_text(
        "Latest Calendar tranche: v1.175 adds update-only future-series recurring-event target-calendar move\n"
        "future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update\n"
        "Latest Calendar tranche: v1.167 adds update-only future-series recurring-event\n"
        "selected-occurrence recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update\n"
        "future-series recurring-event title/plain-location/notes update\n"
        "\n",
        encoding="utf-8",
    )
    (root / "docs/" "CROSS_AGENT_ROUTING.md").write_text(
        "one exact directory handle plus expected directory `metadata_sha256` plus bounded target folder name plus no parent/content input for rename-folder\n"
        "one exact directory handle plus exact target parent handle plus expected directory `metadata_sha256` plus optional bounded target folder name plus no content input for move-folder\n"
        "one exact directory handle plus exact target parent handle plus expected directory `metadata_sha256` plus private bounded source-tree binding plus optional bounded target folder name plus no content input for copy-folder\n"
        "one exact directory handle plus expected directory `metadata_sha256` plus private bounded source-tree binding plus no parent/filename/content input for delete-folder\n"
        "one exact supported text-file handle plus expected current SHA-256 plus no parent/filename/content input for delete-text\n"
        "with metadata-only directory proof, read-back, absence-proof, source/target presence verification, or source-preservation verification\n"
        "Mid-series recurrence replacement additionally requires a current occurrence-bound handle, expected recurrence binding, approved replacement recurrence fields, previous/selected/future occurrence identity, EventKit `.futureEvents` save with a replacement recurrence rule, selected replacement proof, future replacement proof, original future-slot absent-or-replaced proof, and previous-occurrence preservation proof\n"
        "future-series recurring-event availability update with `recurrence_update_scope:future_events`\n"
        "no scalar/calendar/availability/event-URL/alarm/structured-location co-mutation\n",
        encoding="utf-8",
    )
    (root / "docs/TESTING.md").write_text(
        "synthetic iCloud Drive file retrieval and create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file plan/apply\n"
        "iCloud Drive content/detail plus create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply flows\n"
        "folder directory metadata read-back, no folder content-hash return, already-applied retry\n"
        "hidden CLI `--root` refusal outside `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`\n"
        "wrong returned folder-id refusal\n"
        "Notes default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, move-to-folder, and exact-note delete\n"
        "exact allow-listed event URL create/update/delete plan/apply plus update-only event URL clearing\n"
        "event URL raw-preview non-disclosure\n"
        "invalid-token raw-URL non-disclosure\n"
        "Reminder URL update/clear plan/apply with hash-only read-back and no raw URL return\n"
        "Reminder absolute/relative/mixed display-alarm set/clear plan/apply with exact date/offset read-back or absence proof and no raw alarm state return\n"
        "Mail body/advanced/attachment discovery requires date bounds and returns only capped snippets, masked header metadata, or attachment filename/MIME metadata. Regression tests also enforce subject-only advanced search without `.emlx` parsing, metadata-only attachment paths without nonmatching payload reads, ISO date bounds matching Unix-scale local Mail timestamps, Mail MCP wrapper failures returning redacted `mcp_tool_error` payloads, and a same-stdio-session Mail MCP error followed by a successful Contacts response.\n",
        encoding="utf-8",
    )
    (root / "skills/local-apple-data/SKILL.md").write_text(
        "future iCloud Drive create-folder, bounded create-folder-path, exact folder rename, exact folder Trash, exact selected-folder permanent delete, exact folder move, exact folder copy, text-file create, append-text, replace-text, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, or delete-file\n"
        "approved iCloud Drive create-folder, bounded create-folder-path, exact folder rename, exact folder Trash, exact selected-folder permanent delete, exact folder move, exact folder copy, text-file create, append-text, replace-text, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, or delete-file\n"
        "same parent handle/folder name for create-folder\n"
        "same parent handle/folder_components stable parent identity token binding for create-folder-path\n"
        "Text-file rename/move use no-overwrite target reservation, no-follow swap, post-swap SHA/identity proof\n"
        "Regular-file rename/move use no-overwrite target reservation, no-follow swap, post-swap metadata/identity proof\n"
        "regular-file copy uses exclusive create, target identity/size/internal byte proof, and post-copy source metadata recheck\n"
        "future Notes create-note, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, move-to-folder, or exact-note delete operation\n"
        "metadata-only parent proof\n"
        "Notes folder/account targeting outside exact note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, and move-to-folder gates\n"
        "optional exact allow-listed `event_url`, update-only `clear_event_url`\n"
        "expected_event_url_present\n"
        "expected_event_url_sha256\n"
        "future-series recurring-event title/plain-location/notes update with `recurrence_update_scope:future_events`\n"
        "future-series recurring-event availability update with `recurrence_update_scope:future_events`\n"
        "future-series recurring-event event URL set/clear with `recurrence_update_scope:future_events`\n"
        "future-series recurring-event structured-location set/clear with `recurrence_update_scope:future_events`\n"
        "update-only `recurrence_update_scope:this_event` for selected recurring occurrence title/plain-location/notes, timed start/end/time-zone, availability, event URL set/clear, structured-location set/clear, display-alarm set/clear, action-alarm set/clear, all-day set/clear/date-only reschedule, or exact target-calendar move mutation with exact occurrence, adjacent-occurrence identity, target-calendar handle for moves, and hash-only adjacent URL/plain-location/structured-location/alarm-state binding\n"
        "update one selected recurring occurrence's title/plain location/notes, timed start/end/time-zone, availability, event URL, structured location, display-alarm set/clear, action-alarm set/clear, or all-day set/clear/date-only reschedule through `recurrence_update_scope:this_event` with recurrence, selected occurrence, and adjacent occurrence identity proof plus hash-only adjacent URL/plain-location/structured-location/alarm-state preservation, EventKit `.thisEvent` read-back, and original occurrence absence proof when rescheduled\n"
        "selected recurring occurrence title/plain-location/notes, timed start/end/time-zone, availability, event URL set/clear, structured-location set/clear, display-alarm set/clear, action-alarm set/clear, all-day set/clear/date-only reschedule, or exact target-calendar move update with `recurrence_update_scope:this_event`\n"
        "hash-only event URL read-back or absence proof\n"
        "Event URL non-allow-listed URL schemes\n",
        encoding="utf-8",
    )
    for contract in write_design_gate.REQUIRED_DESIGN_DOCS.values():
        (root / str(contract["path"])).write_text(
            _write_design_doc_text(),
            encoding="utf-8",
        )
    _write_surface_contract_files(root)
    _write_current_source_contract_files(root)
    return root


def _write_current_source_contract_files(root: Path) -> None:
    (root / "scripts/verify_runtime.py").write_text(
        "LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT\n"
        "icloud_folder_path_plan_status\n"
        "icloud_folder_path_apply_status\n"
        "icloud_folder_path_apply_final_verified\n"
        "mcp_icloud_folder_path_plan_status\n"
        "mcp_icloud_folder_path_apply_status\n"
        "mcp_icloud_folder_path_apply_final_verified\n"
        "mail_cross_account_move_plan_status\n"
        "mail_cross_account_move_relation\n"
        "mail_cross_account_move_source_ref_opaque\n"
        "mail_cross_account_move_target_ref_opaque\n"
        "mail_cross_account_move_refs_distinct\n"
        "mail_cross_account_move_raw_account_absent\n"
        "mail_cross_account_move_apply_status\n"
        "mail_cross_account_move_apply_read_back_moved\n"
        "mail_sender_search_status\n"
        "mail_sender_opaque_handle\n"
        "mail_sender_search_full_email_returned\n"
        "mail_sender_hidden_local_match_count\n"
        "mail_sender_hidden_full_email_match_count\n"
        "mail_sender_detail_status\n"
        "mail_sender_detail_full_email_returned\n"
        "mail_sender_draft_plan_status\n"
        "mail_sender_draft_plan_mode\n"
        "mail_sender_draft_plan_retry_safe\n"
        "mail_sender_draft_plan_full_email_returned\n"
        "mail_sender_send_plan_status\n"
        "mail_sender_send_plan_mode\n"
        "mail_sender_send_plan_full_email_returned\n"
        "mail_sender_send_plan_warning\n"
        "mail_sender_send_apply_status\n"
        "mail_sender_send_apply_mutation_applied\n"
        "mail_sender_send_apply_confirmed\n"
        "mail_sender_send_apply_full_email_returned\n"
        "mail_sender_reply_plan_mode\n"
        "mail_sender_reply_apply_confirmed\n"
        "mail_sender_reply_apply_full_email_returned\n"
        "mail_sender_reply_all_plan_mode\n"
        "mail_sender_reply_all_apply_confirmed\n"
        "mail_sender_reply_all_apply_full_email_returned\n"
        "mail_sender_forward_plan_mode\n"
        "mail_sender_forward_apply_confirmed\n"
        "reminders_list_create_plan_status\n"
        "reminders_list_create_apply_status\n"
        "reminders_list_rename_apply_status\n"
        "reminders_list_delete_apply_status\n"
        "mcp_reminders_list_create_apply_status\n"
        "calendar_set_positions_recurrence_plan_status\n"
        "calendar_set_positions_recurrence_plan_weekdays\n"
        "calendar_set_positions_recurrence_plan_set_positions\n"
        "calendar_set_positions_recurrence_apply_status\n"
        "calendar_set_positions_recurrence_apply_read_back_weekdays\n"
        "calendar_set_positions_recurrence_apply_read_back_set_positions\n"
        "mcp_calendar_set_positions_recurrence_plan_status\n"
        "mcp_calendar_set_positions_recurrence_plan_weekdays\n"
        "mcp_calendar_set_positions_recurrence_plan_set_positions\n"
        "mcp_calendar_set_positions_recurrence_apply_status\n"
        "mcp_calendar_set_positions_recurrence_apply_warning\n"
        "calendar_management_create_plan_status\n"
        "calendar_management_create_apply_status\n"
        "calendar_management_create_source_verified\n"
        "calendar_management_rename_plan_status\n"
        "calendar_management_rename_apply_status\n"
        "calendar_management_rename_title\n"
        "calendar_management_delete_plan_status\n"
        "calendar_management_delete_apply_status\n"
        "calendar_management_delete_mutation_applied\n"
        "calendar_management_delete_absent_verified\n"
        "calendar_management_delete_empty_verified\n"
        "mcp_calendar_management_create_plan_status\n"
        "mcp_calendar_management_create_apply_status\n"
        "mcp_calendar_management_create_source_verified\n"
        "mcp_calendar_management_delete_plan_status\n"
        "mcp_calendar_management_delete_apply_status\n"
        "mcp_calendar_management_delete_absent_verified\n"
        "mcp_calendar_management_delete_empty_verified\n"
        "mail_sender_forward_apply_full_email_returned\n"
        "calendar_recurrence_end_date_plan_status\n"
        "calendar_recurrence_end_date_plan_end_date\n"
        "calendar_recurrence_end_date_apply_status\n"
        "calendar_recurrence_end_date_apply_read_back_end_date\n"
        "mcp_calendar_recurrence_end_date_plan_status\n"
        "mcp_calendar_recurrence_end_date_plan_end_date\n"
        "mcp_calendar_recurrence_end_date_apply_status\n"
        "mcp_calendar_recurrence_end_date_apply_warning\n"
        "calendar_unbounded_recurrence_plan_status\n"
        "calendar_unbounded_recurrence_plan_unbounded\n"
        "calendar_unbounded_recurrence_apply_status\n"
        "calendar_unbounded_recurrence_apply_read_back_unbounded\n"
        "mcp_calendar_unbounded_recurrence_plan_status\n"
        "mcp_calendar_unbounded_recurrence_plan_unbounded\n"
        "mcp_calendar_unbounded_recurrence_apply_status\n"
        "mcp_calendar_unbounded_recurrence_apply_warning\n"
        "calendar_monthly_weekday_recurrence_plan_status\n"
        "calendar_monthly_weekday_recurrence_plan_weekdays\n"
        "calendar_monthly_weekday_recurrence_apply_status\n"
        "calendar_monthly_weekday_recurrence_apply_read_back_weekdays\n"
        "calendar_monthly_weekday_update_recurrence_plan_status\n"
        "calendar_monthly_weekday_update_recurrence_plan_weekdays\n"
        "calendar_monthly_weekday_update_recurrence_plan_expected_recurrence_present\n"
        "calendar_monthly_weekday_update_recurrence_apply_status\n"
        "calendar_monthly_weekday_update_recurrence_apply_read_back_weekdays\n"
        "mcp_calendar_monthly_weekday_recurrence_plan_status\n"
        "mcp_calendar_monthly_weekday_recurrence_plan_weekdays\n"
        "mcp_calendar_monthly_weekday_recurrence_apply_status\n"
        "mcp_calendar_monthly_weekday_recurrence_apply_warning\n"
        "mcp_calendar_monthly_weekday_update_recurrence_plan_status\n"
        "mcp_calendar_monthly_weekday_update_recurrence_plan_weekdays\n"
        "mcp_calendar_monthly_weekday_update_recurrence_plan_expected_recurrence_present\n"
        "mcp_calendar_monthly_weekday_update_recurrence_apply_status\n"
        "mcp_calendar_monthly_weekday_update_recurrence_apply_warning\n"
        "calendar_year_month_day_recurrence_plan_year_months\n"
        "calendar_year_month_day_recurrence_plan_year_month_days\n"
        "calendar_year_month_day_recurrence_apply_status\n"
        "calendar_year_month_day_recurrence_apply_read_back_year_months\n"
        "calendar_year_month_day_recurrence_apply_read_back_year_month_days\n"
        "calendar_year_month_day_update_recurrence_plan_year_months\n"
        "calendar_year_month_day_update_recurrence_plan_year_month_days\n"
        "calendar_year_month_day_update_recurrence_plan_expected_recurrence_present\n"
        "calendar_year_month_day_update_recurrence_apply_status\n"
        "calendar_year_month_day_update_recurrence_apply_read_back_year_months\n"
        "calendar_year_month_day_update_recurrence_apply_read_back_year_month_days\n"
        "mcp_calendar_year_month_day_recurrence_plan_year_months\n"
        "mcp_calendar_year_month_day_recurrence_plan_year_month_days\n"
        "mcp_calendar_year_month_day_recurrence_apply_status\n"
        "mcp_calendar_year_month_day_recurrence_apply_warning\n"
        "mcp_calendar_year_month_day_update_recurrence_plan_year_months\n"
        "mcp_calendar_year_month_day_update_recurrence_plan_year_month_days\n"
        "mcp_calendar_year_month_day_update_recurrence_plan_expected_recurrence_present\n"
        "mcp_calendar_year_month_day_update_recurrence_apply_status\n"
        "mcp_calendar_year_month_day_update_recurrence_apply_warning\n"
        "calendar_year_month_weekday_recurrence_plan_year_months\n"
        "calendar_year_month_weekday_recurrence_plan_year_month_weekdays\n"
        "calendar_year_month_weekday_recurrence_apply_status\n"
        "calendar_year_month_weekday_recurrence_apply_read_back_year_months\n"
        "calendar_year_month_weekday_recurrence_apply_read_back_year_month_weekdays\n"
        "calendar_year_month_weekday_update_recurrence_plan_year_months\n"
        "calendar_year_month_weekday_update_recurrence_plan_year_month_weekdays\n"
        "calendar_year_month_weekday_update_recurrence_plan_expected_recurrence_present\n"
        "calendar_year_month_weekday_update_recurrence_apply_status\n"
        "calendar_year_month_weekday_update_recurrence_apply_read_back_year_months\n"
        "calendar_year_month_weekday_update_recurrence_apply_read_back_year_month_weekdays\n"
        "mcp_calendar_year_month_weekday_recurrence_plan_year_months\n"
        "mcp_calendar_year_month_weekday_recurrence_plan_year_month_weekdays\n"
        "mcp_calendar_year_month_weekday_recurrence_apply_status\n"
        "mcp_calendar_year_month_weekday_recurrence_apply_warning\n"
        "mcp_calendar_year_month_weekday_update_recurrence_plan_year_months\n"
        "mcp_calendar_year_month_weekday_update_recurrence_plan_year_month_weekdays\n"
        "mcp_calendar_year_month_weekday_update_recurrence_plan_expected_recurrence_present\n"
        "mcp_calendar_year_month_weekday_update_recurrence_apply_status\n"
        "mcp_calendar_year_month_weekday_update_recurrence_apply_warning\n"
        "mail_sender_draft_apply_status\n"
        "mail_sender_draft_apply_mutation_applied\n"
        "mail_sender_draft_apply_confirmed\n"
        "mail_sender_draft_apply_full_email_returned\n"
        "mail_sender_race_apply_status\n"
        "mail_sender_race_apply_warning\n"
        "mail_sender_saturated_apply_status\n"
        "mail_sender_saturated_apply_warning\n"
        "mcp_icloud_folder_apply_status\n"
        "mcp_icloud_folder_apply_read_back_kind\n"
        "mcp_icloud_folder_retry_warning\n"
        "mcp_icloud_rename_folder_plan_status\n"
        "mcp_icloud_rename_folder_plan_empty_required\n"
        "mcp_icloud_rename_folder_plan_non_empty_allowed\n"
        "mcp_icloud_rename_folder_apply_status\n"
        "mcp_icloud_rename_folder_apply_source_present\n"
        "mcp_icloud_rename_folder_apply_target_present\n"
        "mcp_icloud_rename_folder_apply_content_hash_returned\n"
        "mcp_icloud_rename_folder_apply_empty_confirmed\n"
        "mcp_icloud_rename_folder_apply_non_empty_allowed\n"
        "mcp_icloud_rename_folder_child_preserved\n"
        "mcp_icloud_trash_folder_plan_status\n"
        "mcp_icloud_trash_folder_plan_empty_required\n"
        "mcp_icloud_trash_folder_plan_non_empty_allowed\n"
        "mcp_icloud_trash_folder_apply_status\n"
        "mcp_icloud_trash_folder_apply_original_present\n"
        "mcp_icloud_trash_folder_apply_content_hash_returned\n"
        "mcp_icloud_trash_folder_apply_empty_confirmed\n"
        "mcp_icloud_trash_folder_apply_non_empty_allowed\n"
        "mcp_icloud_trash_folder_child_preserved\n"
        "mcp_icloud_delete_folder_plan_status\n"
        "mcp_icloud_delete_folder_plan_empty_required\n"
        "mcp_icloud_delete_folder_plan_non_empty_allowed\n"
        "mcp_icloud_delete_folder_plan_recursive_delete\n"
        "mcp_icloud_delete_folder_plan_source_tree_binding\n"
        "mcp_icloud_delete_folder_apply_status\n"
        "mcp_icloud_delete_folder_apply_original_present\n"
        "mcp_icloud_delete_folder_apply_verified_absent\n"
        "mcp_icloud_delete_folder_apply_permanently_deleted\n"
        "mcp_icloud_delete_folder_apply_staging_path_returned\n"
        "mcp_icloud_delete_folder_apply_content_hash_returned\n"
        "mcp_icloud_delete_folder_apply_empty_confirmed\n"
        "mcp_icloud_delete_folder_apply_non_empty_allowed\n"
        "mcp_icloud_delete_folder_apply_warning_count\n"
        "mcp_icloud_delete_folder_apply_child_name_returned\n"
        "mcp_icloud_move_folder_plan_status\n"
        "mcp_icloud_move_folder_plan_empty_required\n"
        "mcp_icloud_move_folder_plan_non_empty_allowed\n"
        "mcp_icloud_move_folder_apply_status\n"
        "mcp_icloud_move_folder_apply_source_present\n"
        "mcp_icloud_move_folder_apply_target_present\n"
        "mcp_icloud_move_folder_apply_content_hash_returned\n"
        "mcp_icloud_move_folder_apply_empty_confirmed\n"
        "mcp_icloud_move_folder_apply_non_empty_allowed\n"
        "mcp_icloud_move_folder_child_preserved\n"
        "mcp_icloud_move_folder_apply_warning_count\n"
        "icloud_copy_folder_plan_status\n"
        "icloud_copy_folder_plan_empty_required\n"
        "icloud_copy_folder_plan_non_empty_allowed\n"
        "icloud_copy_folder_apply_status\n"
        "icloud_copy_folder_apply_source_present\n"
        "icloud_copy_folder_apply_target_present\n"
        "icloud_copy_folder_apply_content_hash_returned\n"
        "icloud_copy_folder_apply_empty_confirmed\n"
        "icloud_copy_folder_apply_non_empty_allowed\n"
        "icloud_copy_folder_child_preserved\n"
        "icloud_copy_folder_apply_warning_count\n"
        "mcp_icloud_copy_folder_plan_status\n"
        "mcp_icloud_copy_folder_plan_empty_required\n"
        "mcp_icloud_copy_folder_plan_non_empty_allowed\n"
        "mcp_icloud_copy_folder_apply_status\n"
        "mcp_icloud_copy_folder_apply_source_present\n"
        "mcp_icloud_copy_folder_apply_target_present\n"
        "mcp_icloud_copy_folder_apply_content_hash_returned\n"
        "mcp_icloud_copy_folder_apply_empty_confirmed\n"
        "mcp_icloud_copy_folder_apply_non_empty_allowed\n"
        "mcp_icloud_copy_folder_child_preserved\n"
        "mcp_icloud_copy_folder_apply_warning_count\n"
        "mcp_icloud_trash_apply_status\n"
        "mcp_icloud_trash_apply_original_present\n"
        "mcp_icloud_trash_apply_trash_path_returned\n"
        "mcp_icloud_delete_plan_status\n"
        "mcp_icloud_delete_apply_status\n"
        "mcp_icloud_delete_apply_original_present\n"
        "mcp_icloud_delete_apply_verified_absent\n"
        "mcp_icloud_delete_apply_permanently_deleted\n"
        "mcp_icloud_delete_apply_trash_path_returned\n"
        "mcp_icloud_delete_apply_staging_path_returned\n"
        "mcp_icloud_delete_apply_content_hash_returned\n"
        "mcp_icloud_delete_stale_status\n"
        "mcp_icloud_delete_stale_mutation_applied\n"
        "mcp_icloud_delete_stale_warning\n"
        "mcp_icloud_delete_stale_content_inspected\n"
        "mcp_icloud_delete_stale_file_unchanged\n"
        "mcp_icloud_delete_identity_race_status\n"
        "mcp_icloud_delete_identity_race_mutation_applied\n"
        "mcp_icloud_delete_identity_race_warning\n"
        "mcp_icloud_delete_identity_race_content_inspected\n"
        "mcp_icloud_delete_identity_race_file_unchanged\n"
        "mcp_icloud_rename_apply_status\n"
        "mcp_icloud_rename_apply_content_text_returned\n"
        "mcp_icloud_rename_apply_sha_matches_expected\n"
        "mcp_icloud_rename_stale_warning\n"
        "mcp_icloud_rename_stale_target_missing\n"
        "mcp_icloud_rename_exists_warning\n"
        "mcp_icloud_copy_apply_status\n"
        "mcp_icloud_copy_apply_content_text_returned\n"
        "mcp_icloud_copy_apply_sha_matches_expected\n"
        "mcp_icloud_copy_stale_warning\n"
        "mcp_icloud_copy_stale_target_missing\n"
        "mcp_icloud_copy_exists_warning\n"
        "mcp_icloud_move_apply_status\n"
        "mcp_icloud_move_apply_content_text_returned\n"
        "mcp_icloud_move_apply_sha_matches_expected\n"
        "mcp_icloud_move_stale_warning\n"
        "mcp_icloud_move_stale_target_missing\n"
        "mcp_icloud_move_exists_warning\n"
        "icloud_trash_apply_status\n"
        "icloud_trash_apply_original_present\n"
        "icloud_trash_stale_warning\n"
        "icloud_delete_plan_status\n"
        "icloud_delete_apply_status\n"
        "icloud_delete_apply_original_present\n"
        "icloud_delete_apply_verified_absent\n"
        "icloud_delete_apply_permanently_deleted\n"
        "icloud_delete_apply_trash_path_returned\n"
        "icloud_delete_apply_staging_path_returned\n"
        "icloud_delete_apply_content_hash_returned\n"
        "icloud_delete_stale_warning\n"
        "icloud_delete_stale_content_inspected\n"
        "icloud_delete_identity_race_status\n"
        "icloud_delete_identity_race_mutation_applied\n"
        "icloud_delete_identity_race_warning\n"
        "icloud_delete_identity_race_content_inspected\n"
        "icloud_delete_identity_race_file_unchanged\n"
        "icloud_rename_folder_plan_status\n"
        "icloud_rename_folder_plan_empty_required\n"
        "icloud_rename_folder_plan_non_empty_allowed\n"
        "icloud_rename_folder_apply_status\n"
        "icloud_rename_folder_apply_source_present\n"
        "icloud_rename_folder_apply_target_present\n"
        "icloud_rename_folder_apply_content_hash_returned\n"
        "icloud_rename_folder_apply_empty_confirmed\n"
        "icloud_rename_folder_apply_non_empty_allowed\n"
        "icloud_rename_folder_child_preserved\n"
        "icloud_trash_folder_plan_status\n"
        "icloud_trash_folder_plan_empty_required\n"
        "icloud_trash_folder_plan_non_empty_allowed\n"
        "icloud_trash_folder_apply_status\n"
        "icloud_trash_folder_apply_original_present\n"
        "icloud_trash_folder_apply_content_hash_returned\n"
        "icloud_trash_folder_apply_empty_confirmed\n"
        "icloud_trash_folder_apply_non_empty_allowed\n"
        "icloud_trash_folder_child_preserved\n"
        "icloud_delete_folder_plan_status\n"
        "icloud_delete_folder_plan_empty_required\n"
        "icloud_delete_folder_plan_non_empty_allowed\n"
        "icloud_delete_folder_plan_recursive_delete\n"
        "icloud_delete_folder_plan_source_tree_binding\n"
        "icloud_delete_folder_apply_status\n"
        "icloud_delete_folder_apply_original_present\n"
        "icloud_delete_folder_apply_verified_absent\n"
        "icloud_delete_folder_apply_permanently_deleted\n"
        "icloud_delete_folder_apply_staging_path_returned\n"
        "icloud_delete_folder_apply_content_hash_returned\n"
        "icloud_delete_folder_apply_empty_confirmed\n"
        "icloud_delete_folder_apply_non_empty_allowed\n"
        "icloud_delete_folder_apply_warning_count\n"
        "icloud_delete_folder_apply_child_name_returned\n"
        "icloud_move_folder_plan_status\n"
        "icloud_move_folder_plan_empty_required\n"
        "icloud_move_folder_plan_non_empty_allowed\n"
        "icloud_move_folder_apply_status\n"
        "icloud_move_folder_apply_source_present\n"
        "icloud_move_folder_apply_target_present\n"
        "icloud_move_folder_apply_content_hash_returned\n"
        "icloud_move_folder_apply_empty_confirmed\n"
        "icloud_move_folder_apply_non_empty_allowed\n"
        "icloud_move_folder_child_preserved\n"
        "icloud_move_folder_apply_warning_count\n"
        "icloud_copy_folder_plan_status\n"
        "icloud_copy_folder_plan_empty_required\n"
        "icloud_copy_folder_plan_non_empty_allowed\n"
        "icloud_copy_folder_apply_status\n"
        "icloud_copy_folder_apply_source_present\n"
        "icloud_copy_folder_apply_target_present\n"
        "icloud_copy_folder_apply_content_hash_returned\n"
        "icloud_copy_folder_apply_empty_confirmed\n"
        "icloud_copy_folder_apply_non_empty_allowed\n"
        "icloud_copy_folder_child_preserved\n"
        "icloud_copy_folder_apply_warning_count\n"
        "icloud_rename_apply_status\n"
        "icloud_rename_apply_content_text_returned\n"
        "icloud_rename_apply_sha_matches_expected\n"
        "icloud_rename_stale_warning\n"
        "icloud_rename_stale_target_missing\n"
        "icloud_copy_apply_status\n"
        "icloud_copy_apply_content_text_returned\n"
        "icloud_copy_apply_sha_matches_expected\n"
        "icloud_copy_stale_warning\n"
        "icloud_copy_stale_target_missing\n"
        "icloud_move_apply_status\n"
        "icloud_move_apply_content_text_returned\n"
        "icloud_move_apply_sha_matches_expected\n"
        "icloud_move_stale_warning\n"
        "icloud_move_stale_target_missing\n"
        "mcp_icloud_import_plan_status\n"
        "mcp_icloud_import_apply_status\n"
        "mcp_icloud_import_apply_mutation_applied\n"
        "mcp_icloud_import_apply_target_present\n"
        "mcp_icloud_import_apply_source_path_returned\n"
        "mcp_icloud_import_apply_source_hash_returned\n"
        "mcp_icloud_import_apply_content_hash_returned\n"
        "mcp_icloud_import_apply_bytes_preserved\n"
        "mcp_icloud_import_source_still_exists\n"
        "mcp_icloud_import_plan_source_path_hidden\n"
        "mcp_icloud_import_apply_source_path_hidden\n"
        "mcp_icloud_import_source_hash_hidden\n"
        "mcp_icloud_import_stale_status\n"
        "mcp_icloud_import_stale_mutation_applied\n"
        "mcp_icloud_import_stale_warning\n"
        "mcp_icloud_import_stale_source_unchanged\n"
        "mcp_icloud_import_stale_target_missing\n"
        "mcp_icloud_replace_file_plan_status\n"
        "mcp_icloud_replace_file_apply_status\n"
        "mcp_icloud_replace_file_apply_mutation_applied\n"
        "mcp_icloud_replace_file_apply_target_present\n"
        "mcp_icloud_replace_file_apply_source_path_returned\n"
        "mcp_icloud_replace_file_apply_source_hash_returned\n"
        "mcp_icloud_replace_file_apply_content_hash_returned\n"
        "mcp_icloud_replace_file_apply_bytes_replaced\n"
        "mcp_icloud_replace_file_source_still_exists\n"
        "mcp_icloud_replace_file_plan_source_path_hidden\n"
        "mcp_icloud_replace_file_apply_source_path_hidden\n"
        "mcp_icloud_replace_file_source_hash_hidden\n"
        "mcp_icloud_replace_file_stale_status\n"
        "mcp_icloud_replace_file_stale_mutation_applied\n"
        "mcp_icloud_replace_file_stale_warning\n"
        "mcp_icloud_replace_file_stale_source_unchanged\n"
        "mcp_icloud_replace_file_stale_target_unchanged\n"
        "mcp_icloud_trash_file_plan_status\n"
        "mcp_icloud_trash_file_apply_status\n"
        "mcp_icloud_trash_file_apply_mutation_applied\n"
        "mcp_icloud_trash_file_apply_original_present\n"
        "mcp_icloud_trash_file_apply_trash_path_returned\n"
        "mcp_icloud_trash_file_apply_content_hash_returned\n"
        "mcp_icloud_trash_file_apply_content_text_returned\n"
        "mcp_icloud_trash_file_apply_bytes_trashed\n"
        "mcp_icloud_trash_file_stale_status\n"
        "mcp_icloud_trash_file_stale_mutation_applied\n"
        "mcp_icloud_trash_file_stale_warning\n"
        "mcp_icloud_trash_file_stale_target_unchanged\n"
        "mcp_icloud_delete_file_plan_status\n"
        "mcp_icloud_delete_file_apply_status\n"
        "mcp_icloud_delete_file_apply_mutation_applied\n"
        "mcp_icloud_delete_file_apply_original_present\n"
        "mcp_icloud_delete_file_apply_verified_absent\n"
        "mcp_icloud_delete_file_apply_permanently_deleted\n"
        "mcp_icloud_delete_file_apply_trash_path_returned\n"
        "mcp_icloud_delete_file_apply_staging_path_returned\n"
        "mcp_icloud_delete_file_apply_content_hash_returned\n"
        "mcp_icloud_delete_file_apply_content_text_returned\n"
        "mcp_icloud_delete_file_apply_old_missing\n"
        "mcp_icloud_delete_file_stale_status\n"
        "mcp_icloud_delete_file_stale_mutation_applied\n"
        "mcp_icloud_delete_file_stale_warning\n"
        "mcp_icloud_delete_file_stale_target_unchanged\n"
        "icloud_import_file_plan_status\n"
        "icloud_import_file_apply_status\n"
        "icloud_import_file_apply_mutation_applied\n"
        "icloud_import_file_apply_target_present\n"
        "icloud_import_file_apply_source_path_returned\n"
        "icloud_import_file_apply_source_hash_returned\n"
        "icloud_import_file_apply_content_hash_returned\n"
        "icloud_import_file_apply_bytes_preserved\n"
        "icloud_import_file_source_still_exists\n"
        "icloud_import_file_plan_source_path_hidden\n"
        "icloud_import_file_apply_source_path_hidden\n"
        "icloud_import_file_source_hash_hidden\n"
        "icloud_import_file_stale_status\n"
        "icloud_import_file_stale_mutation_applied\n"
        "icloud_import_file_stale_warning\n"
        "icloud_import_file_stale_source_unchanged\n"
        "icloud_import_file_stale_target_missing\n"
        "icloud_replace_file_plan_status\n"
        "icloud_replace_file_apply_status\n"
        "icloud_replace_file_apply_mutation_applied\n"
        "icloud_replace_file_apply_target_present\n"
        "icloud_replace_file_apply_source_path_returned\n"
        "icloud_replace_file_apply_source_hash_returned\n"
        "icloud_replace_file_apply_content_hash_returned\n"
        "icloud_replace_file_apply_bytes_replaced\n"
        "icloud_replace_file_source_still_exists\n"
        "icloud_replace_file_plan_source_path_hidden\n"
        "icloud_replace_file_apply_source_path_hidden\n"
        "icloud_replace_file_source_hash_hidden\n"
        "icloud_replace_file_stale_status\n"
        "icloud_replace_file_stale_mutation_applied\n"
        "icloud_replace_file_stale_warning\n"
        "icloud_replace_file_stale_source_unchanged\n"
        "icloud_replace_file_stale_target_unchanged\n"
        "icloud_trash_file_plan_status\n"
        "icloud_trash_file_apply_status\n"
        "icloud_trash_file_apply_mutation_applied\n"
        "icloud_trash_file_apply_original_present\n"
        "icloud_trash_file_apply_trash_path_returned\n"
        "icloud_trash_file_apply_content_hash_returned\n"
        "icloud_trash_file_apply_content_text_returned\n"
        "icloud_trash_file_apply_old_missing\n"
        "icloud_trash_file_apply_bytes_trashed\n"
        "icloud_trash_file_stale_status\n"
        "icloud_trash_file_stale_mutation_applied\n"
        "icloud_trash_file_stale_warning\n"
        "icloud_trash_file_stale_target_unchanged\n"
        "icloud_delete_file_plan_status\n"
        "icloud_delete_file_apply_status\n"
        "icloud_delete_file_apply_mutation_applied\n"
        "icloud_delete_file_apply_original_present\n"
        "icloud_delete_file_apply_verified_absent\n"
        "icloud_delete_file_apply_permanently_deleted\n"
        "icloud_delete_file_apply_trash_path_returned\n"
        "icloud_delete_file_apply_staging_path_returned\n"
        "icloud_delete_file_apply_content_hash_returned\n"
        "icloud_delete_file_apply_content_text_returned\n"
        "icloud_delete_file_apply_old_missing\n"
        "icloud_delete_file_stale_status\n"
        "icloud_delete_file_stale_mutation_applied\n"
        "icloud_delete_file_stale_warning\n"
        "icloud_delete_file_stale_target_unchanged\n"
        "calendar_all_day_plan_status\n"
        "calendar_all_day_apply_status\n"
        "calendar_all_day_apply_read_back_flag\n"
        "calendar_alarm_plan_status\n"
        "calendar_alarm_apply_status\n"
        "calendar_alarm_apply_read_back_offsets\n"
        "calendar_time_zone_plan_status\n"
        "calendar_time_zone_apply_read_back_zone\n"
        "calendar_time_zone_update_apply_read_back_zone\n"
        "calendar_recurrence_plan_status\n"
        "calendar_recurrence_plan_frequency\n"
        "calendar_recurrence_plan_count\n"
        "calendar_recurrence_plan_month_days\n"
        "calendar_recurrence_apply_status\n"
        "calendar_recurrence_apply_read_back_frequency\n"
        "calendar_recurrence_apply_read_back_count\n"
        "calendar_recurrence_apply_read_back_month_days\n"
        "calendar_month_weekday_recurrence_plan_status\n"
        "calendar_month_weekday_recurrence_plan_month_weekdays\n"
        "calendar_month_weekday_recurrence_apply_status\n"
        "calendar_month_weekday_recurrence_apply_read_back_month_weekdays\n"
        "calendar_monthly_weekday_recurrence_plan_status\n"
        "calendar_monthly_weekday_recurrence_plan_weekdays\n"
        "calendar_monthly_weekday_recurrence_apply_status\n"
        "calendar_monthly_weekday_recurrence_apply_read_back_weekdays\n"
        "calendar_year_month_recurrence_plan_status\n"
        "calendar_year_month_recurrence_plan_year_months\n"
        "calendar_year_month_recurrence_apply_status\n"
        "calendar_year_month_recurrence_apply_read_back_year_months\n"
        "calendar_year_day_recurrence_plan_status\n"
        "calendar_year_day_recurrence_plan_year_days\n"
        "calendar_year_day_recurrence_apply_status\n"
        "calendar_year_day_recurrence_apply_read_back_year_days\n"
        "calendar_update_recurrence_plan_status\n"
        "calendar_update_recurrence_plan_frequency\n"
        "calendar_update_recurrence_plan_count\n"
        "calendar_update_recurrence_plan_expected_recurrence_present\n"
        "calendar_update_recurrence_apply_status\n"
        "calendar_update_recurrence_apply_read_back_frequency\n"
        "calendar_update_recurrence_apply_read_back_count\n"
        "calendar_month_weekday_update_recurrence_plan_status\n"
        "calendar_month_weekday_update_recurrence_plan_month_weekdays\n"
        "calendar_month_weekday_update_recurrence_plan_expected_recurrence_present\n"
        "calendar_month_weekday_update_recurrence_apply_status\n"
        "calendar_month_weekday_update_recurrence_apply_read_back_month_weekdays\n"
        "calendar_monthly_weekday_update_recurrence_plan_status\n"
        "calendar_monthly_weekday_update_recurrence_plan_weekdays\n"
        "calendar_monthly_weekday_update_recurrence_plan_expected_recurrence_present\n"
        "calendar_monthly_weekday_update_recurrence_apply_status\n"
        "calendar_monthly_weekday_update_recurrence_apply_read_back_weekdays\n"
        "calendar_year_month_update_recurrence_plan_status\n"
        "calendar_year_month_update_recurrence_plan_year_months\n"
        "calendar_year_month_update_recurrence_plan_expected_recurrence_present\n"
        "calendar_year_month_update_recurrence_apply_status\n"
        "calendar_year_month_update_recurrence_apply_read_back_year_months\n"
        "calendar_year_week_update_recurrence_plan_status\n"
        "calendar_year_week_update_recurrence_plan_year_weeks\n"
        "calendar_year_week_update_recurrence_plan_weekdays\n"
        "calendar_year_week_update_recurrence_plan_expected_recurrence_present\n"
        "calendar_year_week_update_recurrence_apply_status\n"
        "calendar_year_week_update_recurrence_apply_read_back_year_weeks\n"
        "calendar_year_week_update_recurrence_apply_read_back_weekdays\n"
        "calendar_update_recurrence_existing_apply_status\n"
        "calendar_update_recurrence_existing_apply_mutation_applied\n"
        "calendar_update_recurrence_existing_apply_warning\n"
        "calendar_weekday_recurrence_plan_status\n"
        "calendar_weekday_recurrence_plan_weekdays\n"
        "calendar_weekday_recurrence_apply_status\n"
        "calendar_weekday_recurrence_apply_read_back_weekdays\n"
        "calendar_recurrence_clear_plan_status\n"
        "calendar_recurrence_clear_plan_requested\n"
        "calendar_recurrence_clear_plan_expected_frequency\n"
        "calendar_recurrence_clear_apply_status\n"
        "calendar_recurrence_clear_apply_verified\n"
        "calendar_recurrence_clear_apply_recurrence_present\n"
        "calendar_recurrence_clear_apply_future_absent\n"
        "calendar_recurrence_clear_apply_previous_absent\n"
        "calendar_mid_series_recurrence_clear_plan_status\n"
        "calendar_mid_series_recurrence_clear_plan_scope\n"
        "calendar_mid_series_recurrence_clear_plan_previous_start\n"
        "calendar_mid_series_recurrence_clear_plan_future_start\n"
        "calendar_mid_series_recurrence_clear_apply_status\n"
        "calendar_mid_series_recurrence_clear_apply_verified\n"
        "calendar_mid_series_recurrence_clear_apply_recurrence_present\n"
        "calendar_mid_series_recurrence_clear_apply_future_absent\n"
        "calendar_mid_series_recurrence_clear_apply_previous_present\n"
        "calendar_mid_series_recurrence_replace_apply_verified\n"
        "calendar_mid_series_recurrence_replace_apply_future_present\n"
        "calendar_mid_series_recurrence_replace_apply_previous_present\n"
        "calendar_mid_series_recurrence_replace_apply_original_future_slot_replaced_or_absent\n"
        "calendar_recurrence_update_plan_status\n"
        "calendar_recurrence_update_plan_scope\n"
        "calendar_recurrence_update_plan_expected_frequency\n"
        "calendar_recurrence_update_plan_adjacent_start\n"
        "calendar_recurrence_update_apply_status\n"
        "calendar_recurrence_update_apply_scope\n"
        "calendar_recurrence_update_apply_selected_verified\n"
        "calendar_recurrence_update_apply_rescheduled_verified\n"
        "calendar_recurrence_update_apply_original_absent\n"
        "calendar_recurrence_update_apply_adjacent_present\n"
        "calendar_event_url_plan_status\n"
        "calendar_event_url_apply_verified\n"
        "calendar_event_url_apply_sha256\n"
        "calendar_event_url_clear_plan_status\n"
        "calendar_event_url_clear_apply_verified\n"
        "calendar_event_url_clear_apply_url_present\n"
        "calendar_recurrence_update_event_url_plan_status\n"
        "calendar_recurrence_update_event_url_plan_sha256\n"
        "calendar_recurrence_update_event_url_apply_status\n"
        "calendar_recurrence_update_event_url_apply_verified\n"
        "calendar_recurrence_update_event_url_apply_sha256\n"
        "calendar_recurrence_update_event_url_replace_plan_status\n"
        "calendar_recurrence_update_event_url_replace_plan_expected_present\n"
        "calendar_recurrence_update_event_url_replace_apply_status\n"
        "calendar_recurrence_update_event_url_replace_apply_verified\n"
        "calendar_recurrence_update_event_url_replace_apply_sha256\n"
        "calendar_recurrence_update_event_url_stale_apply_status\n"
        "calendar_recurrence_update_event_url_stale_mutation_applied\n"
        "calendar_recurrence_update_event_url_stale_warning\n"
        "calendar_recurrence_update_event_url_clear_plan_status\n"
        "calendar_recurrence_update_event_url_clear_plan_requested\n"
        "calendar_recurrence_update_event_url_clear_apply_status\n"
        "calendar_recurrence_update_event_url_clear_apply_verified\n"
        "calendar_recurrence_update_display_alarm_plan_status\n"
        "calendar_recurrence_update_display_alarm_plan_requested\n"
        "calendar_recurrence_update_display_alarm_apply_status\n"
        "calendar_recurrence_update_display_alarm_apply_verified\n"
        "calendar_recurrence_update_display_alarm_apply_offsets\n"
        "calendar_recurrence_update_absolute_display_alarm_plan_status\n"
        "calendar_recurrence_update_absolute_display_alarm_plan_requested\n"
        "calendar_recurrence_update_absolute_display_alarm_apply_status\n"
        "calendar_recurrence_update_absolute_display_alarm_apply_verified\n"
        "calendar_recurrence_update_absolute_display_alarm_apply_dates\n"
        "calendar_recurrence_update_display_alarm_clear_plan_status\n"
        "calendar_recurrence_update_display_alarm_clear_plan_requested\n"
        "calendar_recurrence_update_display_alarm_clear_apply_status\n"
        "calendar_recurrence_update_display_alarm_clear_apply_verified\n"
        "calendar_recurrence_update_display_alarm_clear_apply_offsets\n"
        "calendar_recurrence_update_audio_alarm_plan_status\n"
        "calendar_recurrence_update_audio_alarm_plan_requested\n"
        "calendar_recurrence_update_audio_alarm_apply_status\n"
        "calendar_recurrence_update_audio_alarm_apply_verified\n"
        "calendar_recurrence_update_audio_alarm_apply_sound\n"
        "calendar_recurrence_update_email_alarm_plan_status\n"
        "calendar_recurrence_update_email_alarm_plan_sha256\n"
        "calendar_recurrence_update_email_alarm_apply_status\n"
        "calendar_recurrence_update_email_alarm_apply_verified\n"
        "calendar_recurrence_update_email_alarm_apply_sha256\n"
        "calendar_recurrence_update_geofence_alarm_plan_status\n"
        "calendar_recurrence_update_geofence_alarm_plan_proximity\n"
        "calendar_recurrence_update_geofence_alarm_apply_status\n"
        "calendar_recurrence_update_geofence_alarm_apply_verified\n"
        "calendar_recurrence_update_geofence_alarm_apply_proximity\n"
        "calendar_recurrence_update_audio_alarm_clear_plan_status\n"
        "calendar_recurrence_update_audio_alarm_clear_apply_status\n"
        "calendar_recurrence_update_audio_alarm_clear_apply_verified\n"
        "calendar_recurrence_update_audio_alarm_clear_apply_action\n"
        "calendar_recurrence_update_email_alarm_clear_plan_status\n"
        "calendar_recurrence_update_email_alarm_clear_apply_status\n"
        "calendar_recurrence_update_email_alarm_clear_apply_verified\n"
        "calendar_recurrence_update_email_alarm_clear_apply_action\n"
        "calendar_recurrence_update_email_alarm_clear_apply_sha256\n"
        "calendar_recurrence_update_geofence_alarm_clear_plan_status\n"
        "calendar_recurrence_update_geofence_alarm_clear_apply_status\n"
        "calendar_recurrence_update_geofence_alarm_clear_apply_verified\n"
        "calendar_recurrence_update_geofence_alarm_clear_apply_action\n"
        "calendar_recurrence_update_geofence_alarm_clear_apply_proximity\n"
        "calendar_recurrence_update_all_day_plan_status\n"
        "calendar_recurrence_update_all_day_plan_requested\n"
        "calendar_recurrence_update_all_day_apply_status\n"
        "calendar_recurrence_update_all_day_apply_verified\n"
        "calendar_recurrence_update_all_day_apply_all_day\n"
        "calendar_recurrence_update_all_day_clear_plan_status\n"
        "calendar_recurrence_update_all_day_clear_plan_requested\n"
        "calendar_recurrence_update_all_day_clear_apply_status\n"
        "calendar_recurrence_update_all_day_clear_apply_verified\n"
        "calendar_recurrence_update_all_day_clear_apply_all_day\n"
        "calendar_recurrence_update_all_day_reschedule_plan_status\n"
        "calendar_recurrence_update_all_day_reschedule_plan_requested\n"
        "calendar_recurrence_update_all_day_reschedule_apply_status\n"
        "calendar_recurrence_update_all_day_reschedule_apply_verified\n"
        "calendar_recurrence_update_all_day_reschedule_apply_rescheduled\n"
        "calendar_recurrence_update_all_day_reschedule_apply_all_day\n"
        "calendar_recurrence_update_calendar_move_plan_status\n"
        "calendar_recurrence_update_calendar_move_plan_requested\n"
        "calendar_recurrence_update_calendar_move_apply_status\n"
        "calendar_recurrence_update_calendar_move_apply_target_verified\n"
        "calendar_recurrence_update_calendar_move_apply_selected_verified\n"
        "calendar_recurrence_update_calendar_move_apply_adjacent_calendar\n"
        "calendar_recurrence_update_calendar_move_apply_calendar\n"
        "calendar_structured_location_plan_status\n"
        "calendar_structured_location_apply_verified\n"
        "calendar_structured_location_apply_title\n"
        "calendar_structured_location_clear_plan_status\n"
        "calendar_structured_location_clear_plan_requested\n"
        "calendar_structured_location_clear_apply_status\n"
        "calendar_structured_location_clear_apply_verified\n"
        "calendar_structured_location_clear_apply_present\n"
        "calendar_structured_location_clear_apply_location_present\n"
        "calendar_email_alarm_plan_status\n"
        "calendar_email_alarm_plan_sha256\n"
        "calendar_email_alarm_apply_status\n"
        "calendar_email_alarm_apply_verified\n"
        "calendar_email_alarm_apply_sha256\n"
        "calendar_recurrence_delete_plan_status\n"
        "calendar_recurrence_delete_plan_scope\n"
        "calendar_recurrence_delete_plan_expected_recurrence_present\n"
        "calendar_recurrence_delete_apply_status\n"
        "calendar_recurrence_delete_apply_verified_absent\n"
        "calendar_recurrence_delete_unscoped_recurring_status\n"
        "calendar_recurrence_delete_unscoped_recurring_mutation_applied\n"
        "calendar_recurrence_delete_unscoped_recurring_warning\n"
        "calendar_recurrence_delete_scoped_nonrecurring_status\n"
        "calendar_recurrence_delete_scoped_nonrecurring_mutation_applied\n"
        "calendar_recurrence_delete_scoped_nonrecurring_warning\n"
        "calendar_recurrence_future_delete_plan_status\n"
        "calendar_recurrence_future_delete_plan_scope\n"
        "calendar_recurrence_future_delete_plan_previous_start\n"
        "calendar_recurrence_future_delete_plan_future_start\n"
        "calendar_recurrence_future_delete_apply_status\n"
        "calendar_recurrence_future_delete_apply_verified_absent\n"
        "calendar_recurrence_future_delete_apply_selected_absent\n"
        "calendar_recurrence_future_delete_apply_future_absent\n"
        "calendar_recurrence_future_delete_apply_previous_present\n"
        "priority_mcp_tool_count\n"
        "priority_mcp_tools_present\n"
        "priority_mcp_missing_tools\n"
        "mcp_mail_search_mailbox_handle_schema_present\n"
        "mcp_mail_advanced_iso_status\n"
        "mcp_mail_advanced_iso_count_positive\n"
        "mcp_mail_advanced_iso_after\n"
        "mcp_mail_advanced_iso_before\n"
        "mcp_mail_error_status\n"
        "mcp_mail_error_warning\n"
        "mcp_mail_error_output_redacted\n"
        "mcp_mail_error_log_redacted\n"
        "mcp_mail_error_transport_survived_contacts_status\n"
        "mcp_mail_error_transport_survived_contacts_count\n"
        "mail_advanced_iso_status\n"
        "mail_advanced_iso_count\n"
        "mail_advanced_iso_after\n"
        "mail_advanced_iso_before\n"
        "mcp_contacts_count_status\n"
        "mcp_contacts_count_result_count\n"
        "mcp_contacts_count_result_positive\n"
        "mcp_contacts_count_complete\n"
        "mcp_contacts_count_warning\n"
        "calendar_yearly_recurrence_plan_status\n"
        "calendar_yearly_recurrence_plan_frequency\n"
        "calendar_yearly_recurrence_plan_count\n"
        "calendar_yearly_recurrence_apply_status\n"
        "calendar_yearly_recurrence_apply_read_back_frequency\n"
        "calendar_yearly_recurrence_apply_read_back_count\n"
        "calendar_date_only_plan_status\n"
        "calendar_date_only_plan_all_day\n"
        "calendar_date_only_plan_flag\n"
        "calendar_date_only_plan_start\n"
        "calendar_date_only_apply_status\n"
        "calendar_date_only_apply_read_back_all_day\n"
        "calendar_date_only_apply_read_back_start\n"
        "mcp_calendar_recurrence_plan_status\n"
        "mcp_calendar_recurrence_plan_frequency\n"
        "mcp_calendar_recurrence_plan_month_days\n"
        "mcp_calendar_recurrence_apply_status\n"
        "mcp_calendar_recurrence_apply_warning\n"
        "mcp_calendar_month_weekday_recurrence_plan_status\n"
        "mcp_calendar_month_weekday_recurrence_plan_month_weekdays\n"
        "mcp_calendar_month_weekday_recurrence_apply_status\n"
        "mcp_calendar_month_weekday_recurrence_apply_warning\n"
        "mcp_calendar_monthly_weekday_recurrence_plan_status\n"
        "mcp_calendar_monthly_weekday_recurrence_plan_weekdays\n"
        "mcp_calendar_monthly_weekday_recurrence_apply_status\n"
        "mcp_calendar_monthly_weekday_recurrence_apply_warning\n"
        "mcp_calendar_update_recurrence_plan_status\n"
        "mcp_calendar_update_recurrence_plan_frequency\n"
        "mcp_calendar_update_recurrence_plan_expected_recurrence_present\n"
        "mcp_calendar_update_recurrence_apply_status\n"
        "mcp_calendar_update_recurrence_apply_warning\n"
        "mcp_calendar_month_weekday_update_recurrence_plan_status\n"
        "mcp_calendar_month_weekday_update_recurrence_plan_month_weekdays\n"
        "mcp_calendar_month_weekday_update_recurrence_plan_expected_recurrence_present\n"
        "mcp_calendar_month_weekday_update_recurrence_apply_status\n"
        "mcp_calendar_month_weekday_update_recurrence_apply_warning\n"
        "mcp_calendar_monthly_weekday_update_recurrence_plan_status\n"
        "mcp_calendar_monthly_weekday_update_recurrence_plan_weekdays\n"
        "mcp_calendar_monthly_weekday_update_recurrence_plan_expected_recurrence_present\n"
        "mcp_calendar_monthly_weekday_update_recurrence_apply_status\n"
        "mcp_calendar_monthly_weekday_update_recurrence_apply_warning\n"
        "mcp_calendar_year_month_recurrence_plan_status\n"
        "mcp_calendar_year_month_recurrence_plan_year_months\n"
        "mcp_calendar_year_month_recurrence_apply_status\n"
        "mcp_calendar_year_month_recurrence_apply_warning\n"
        "mcp_calendar_year_day_recurrence_plan_status\n"
        "mcp_calendar_year_day_recurrence_plan_year_days\n"
        "mcp_calendar_year_day_recurrence_apply_status\n"
        "mcp_calendar_year_day_recurrence_apply_warning\n"
        "mcp_calendar_year_month_update_recurrence_plan_status\n"
        "mcp_calendar_year_month_update_recurrence_plan_year_months\n"
        "mcp_calendar_year_month_update_recurrence_plan_expected_recurrence_present\n"
        "mcp_calendar_year_month_update_recurrence_apply_status\n"
        "mcp_calendar_year_month_update_recurrence_apply_warning\n"
        "mcp_calendar_year_week_update_recurrence_plan_status\n"
        "mcp_calendar_year_week_update_recurrence_plan_year_weeks\n"
        "mcp_calendar_year_week_update_recurrence_plan_weekdays\n"
        "mcp_calendar_year_week_update_recurrence_plan_expected_recurrence_present\n"
        "mcp_calendar_year_week_update_recurrence_apply_status\n"
        "mcp_calendar_year_week_update_recurrence_apply_warning\n"
        "mcp_calendar_weekday_recurrence_plan_status\n"
        "mcp_calendar_weekday_recurrence_plan_weekdays\n"
        "mcp_calendar_recurrence_clear_apply_status\n"
        "mcp_calendar_recurrence_clear_apply_verified\n"
        "mcp_calendar_recurrence_clear_apply_future_absent\n"
        "mcp_calendar_recurrence_clear_apply_previous_absent\n"
        "mcp_calendar_mid_series_recurrence_clear_apply_status\n"
        "mcp_calendar_mid_series_recurrence_clear_apply_verified\n"
        "mcp_calendar_mid_series_recurrence_clear_apply_future_absent\n"
        "mcp_calendar_mid_series_recurrence_clear_apply_previous_present\n"
        "mcp_calendar_mid_series_recurrence_replace_apply_status\n"
        "mcp_calendar_mid_series_recurrence_replace_apply_verified\n"
        "mcp_calendar_mid_series_recurrence_replace_apply_future_present\n"
        "mcp_calendar_mid_series_recurrence_replace_apply_previous_present\n"
        "mcp_calendar_mid_series_recurrence_replace_apply_original_future_slot_replaced_or_absent\n"
        "mcp_calendar_recurrence_update_apply_status\n"
        "mcp_calendar_recurrence_update_apply_scope\n"
        "mcp_calendar_recurrence_update_apply_selected_verified\n"
        "mcp_calendar_recurrence_update_apply_rescheduled_verified\n"
        "mcp_calendar_recurrence_update_apply_original_absent\n"
        "mcp_calendar_recurrence_update_apply_adjacent_present\n"
        "mcp_calendar_recurrence_update_availability_plan_status\n"
        "mcp_calendar_recurrence_update_availability_plan_name\n"
        "mcp_calendar_recurrence_update_availability_plan_scope\n"
        "mcp_calendar_recurrence_update_availability_plan_expected_name\n"
        "mcp_calendar_recurrence_update_availability_apply_status\n"
        "mcp_calendar_recurrence_update_availability_apply_read_back_name\n"
        "mcp_calendar_recurrence_update_availability_apply_selected_verified\n"
        "mcp_calendar_recurrence_update_event_url_plan_status\n"
        "mcp_calendar_recurrence_update_event_url_plan_scope\n"
        "mcp_calendar_recurrence_update_event_url_plan_sha256\n"
        "mcp_calendar_recurrence_update_event_url_apply_status\n"
        "mcp_calendar_recurrence_update_event_url_apply_verified\n"
        "mcp_calendar_recurrence_update_event_url_apply_sha256\n"
        "mcp_calendar_recurrence_update_event_url_clear_plan_status\n"
        "mcp_calendar_recurrence_update_event_url_clear_plan_requested\n"
        "mcp_calendar_recurrence_update_event_url_clear_apply_status\n"
        "mcp_calendar_recurrence_update_event_url_clear_apply_verified\n"
        "mcp_calendar_recurrence_update_display_alarm_plan_status\n"
        "mcp_calendar_recurrence_update_display_alarm_apply_status\n"
        "mcp_calendar_recurrence_update_display_alarm_apply_verified\n"
        "mcp_calendar_recurrence_update_absolute_display_alarm_plan_status\n"
        "mcp_calendar_recurrence_update_absolute_display_alarm_apply_status\n"
        "mcp_calendar_recurrence_update_absolute_display_alarm_apply_verified\n"
        "mcp_calendar_recurrence_update_display_alarm_clear_plan_status\n"
        "mcp_calendar_recurrence_update_display_alarm_clear_apply_status\n"
        "mcp_calendar_recurrence_update_display_alarm_clear_apply_verified\n"
        "mcp_calendar_recurrence_update_audio_alarm_plan_status\n"
        "mcp_calendar_recurrence_update_audio_alarm_apply_status\n"
        "mcp_calendar_recurrence_update_audio_alarm_apply_verified\n"
        "mcp_calendar_recurrence_update_email_alarm_plan_status\n"
        "mcp_calendar_recurrence_update_email_alarm_apply_status\n"
        "mcp_calendar_recurrence_update_email_alarm_apply_verified\n"
        "mcp_calendar_recurrence_update_geofence_alarm_plan_status\n"
        "mcp_calendar_recurrence_update_geofence_alarm_apply_status\n"
        "mcp_calendar_recurrence_update_geofence_alarm_apply_verified\n"
        "mcp_calendar_recurrence_update_audio_alarm_clear_plan_status\n"
        "mcp_calendar_recurrence_update_audio_alarm_clear_apply_status\n"
        "mcp_calendar_recurrence_update_audio_alarm_clear_apply_verified\n"
        "mcp_calendar_recurrence_update_email_alarm_clear_plan_status\n"
        "mcp_calendar_recurrence_update_email_alarm_clear_apply_status\n"
        "mcp_calendar_recurrence_update_email_alarm_clear_apply_verified\n"
        "mcp_calendar_recurrence_update_geofence_alarm_clear_plan_status\n"
        "mcp_calendar_recurrence_update_geofence_alarm_clear_apply_status\n"
        "mcp_calendar_recurrence_update_geofence_alarm_clear_apply_verified\n"
        "mcp_calendar_recurrence_update_all_day_plan_status\n"
        "mcp_calendar_recurrence_update_all_day_apply_status\n"
        "mcp_calendar_recurrence_update_all_day_apply_verified\n"
        "mcp_calendar_recurrence_update_all_day_apply_all_day\n"
        "mcp_calendar_recurrence_update_all_day_clear_plan_status\n"
        "mcp_calendar_recurrence_update_all_day_clear_apply_status\n"
        "mcp_calendar_recurrence_update_all_day_clear_apply_verified\n"
        "mcp_calendar_recurrence_update_all_day_clear_apply_all_day\n"
        "mcp_calendar_recurrence_update_all_day_reschedule_plan_status\n"
        "mcp_calendar_recurrence_update_all_day_reschedule_apply_status\n"
        "mcp_calendar_recurrence_update_all_day_reschedule_apply_verified\n"
        "mcp_calendar_recurrence_update_all_day_reschedule_apply_rescheduled\n"
        "mcp_calendar_recurrence_update_all_day_reschedule_apply_all_day\n"
        "mcp_calendar_recurrence_update_calendar_move_plan_status\n"
        "mcp_calendar_recurrence_update_calendar_move_plan_requested\n"
        "mcp_calendar_recurrence_update_calendar_move_apply_status\n"
        "mcp_calendar_recurrence_update_calendar_move_apply_target_verified\n"
        "mcp_calendar_recurrence_update_calendar_move_apply_selected_verified\n"
        "mcp_calendar_recurrence_update_calendar_move_apply_adjacent_calendar\n"
        "mcp_calendar_recurrence_update_calendar_move_apply_calendar\n"
        "mcp_calendar_event_url_plan_status\n"
        "mcp_calendar_event_url_apply_warning\n"
        "mcp_calendar_event_url_clear_plan_status\n"
        "mcp_calendar_event_url_clear_apply_warning\n"
        "mcp_calendar_structured_location_plan_status\n"
        "mcp_calendar_structured_location_apply_warning\n"
        "mcp_calendar_structured_location_clear_plan_status\n"
        "mcp_calendar_structured_location_clear_plan_requested\n"
        "mcp_calendar_structured_location_clear_apply_status\n"
        "mcp_calendar_structured_location_clear_apply_warning\n"
        "mcp_calendar_email_alarm_plan_status\n"
        "mcp_calendar_email_alarm_plan_sha256\n"
        "mcp_calendar_email_alarm_apply_status\n"
        "mcp_calendar_email_alarm_apply_warning\n"
        "mcp_calendar_recurrence_delete_live_plan_status\n"
        "mcp_calendar_recurrence_delete_live_plan_fail_closed\n"
        "mcp_calendar_recurrence_delete_live_apply_status\n"
        "mcp_calendar_recurrence_delete_live_apply_fail_closed\n"
        "mcp_calendar_recurrence_delete_apply_status\n"
        "mcp_calendar_recurrence_delete_apply_verified_absent\n"
        "mcp_calendar_recurrence_delete_apply_selected_absent\n"
        "mcp_calendar_recurrence_delete_apply_adjacent_present\n"
        "mcp_calendar_recurrence_future_delete_apply_status\n"
        "mcp_calendar_recurrence_future_delete_apply_verified_absent\n"
        "mcp_calendar_recurrence_future_delete_apply_selected_absent\n"
        "mcp_calendar_recurrence_future_delete_apply_future_absent\n"
        "mcp_calendar_recurrence_future_delete_apply_previous_present\n"
        "mcp_calendar_yearly_recurrence_plan_status\n"
        "mcp_calendar_yearly_recurrence_plan_frequency\n"
        "mcp_calendar_yearly_recurrence_apply_status\n"
        "mcp_calendar_yearly_recurrence_apply_warning\n"
        "mcp_calendar_date_only_plan_status\n"
        "mcp_calendar_date_only_plan_all_day\n"
        "mcp_calendar_date_only_plan_flag\n"
        "mcp_calendar_date_only_apply_status\n"
        "mcp_calendar_date_only_apply_warning\n"
        "calendar_target_search_status\n"
        "calendar_target_handle_plan_status\n"
        "calendar_target_handle_apply_status\n"
        "calendar_target_handle_apply_calendar\n"
        "calendar_default_calendar_plan_status\n"
        "calendar_default_calendar_plan_mode\n"
        "calendar_default_calendar_plan_verified\n"
        "calendar_default_calendar_resolution_verified\n"
        "calendar_default_calendar_apply_status\n"
        "calendar_default_calendar_apply_calendar\n"
        "calendar_default_calendar_apply_verified\n"
        "calendar_move_plan_status\n"
        "calendar_move_apply_status\n"
        "calendar_move_apply_calendar\n"
        "mcp_calendar_time_zone_plan_zone\n"
        "mcp_calendar_time_zone_apply_zone\n"
        "contacts_update_apply_email_value\n"
        "contacts_update_apply_phone_value\n"
        "contacts_update_apply_url_count\n"
        "contacts_append_note_plan_status\n"
        "contacts_append_note_apply_status\n"
        "contacts_append_note_apply_note_chars\n"
        "contacts_append_note_stale_warning\n"
        "notes_create_folder_plan_status\n"
        "notes_create_folder_apply_status\n"
        "notes_create_folder_apply_parent_confirmed\n"
        "notes_create_folder_apply_content_returned\n"
        "notes_rename_folder_plan_status\n"
        "notes_rename_folder_apply_status\n"
        "notes_rename_folder_apply_renamed\n"
        "notes_rename_folder_apply_content_returned\n"
        "notes_rename_folder_retry_warning\n"
        "notes_delete_folder_plan_status\n"
        "notes_delete_folder_apply_status\n"
        "notes_delete_folder_apply_verified_absent\n"
        "notes_delete_folder_apply_content_returned\n"
        "notes_move_folder_plan_status\n"
        "notes_move_folder_apply_status\n"
        "notes_move_folder_apply_target_confirmed\n"
        "notes_move_folder_apply_content_returned\n"
        "notes_body_read_status\n"
        "notes_body_read_html_present\n"
        "notes_body_read_text_match\n"
        "notes_body_create_apply_status\n"
        "notes_body_create_apply_verified\n"
        "notes_body_create_read_back_text_match\n"
        "notes_body_create_sanitized_script_absent\n"
        "notes_body_create_nul_rejected\n"
        "notes_body_replace_apply_status\n"
        "notes_body_replace_apply_verified\n"
        "notes_body_replace_read_back_text_match\n"
        "notes_body_replace_stale_warning\n"
        "mcp_notes_body_read_status\n"
        "mcp_notes_body_read_html_present\n"
        "mcp_notes_body_read_text_match\n"
        "mcp_notes_body_create_apply_status\n"
        "mcp_notes_body_create_apply_verified\n"
        "mcp_notes_body_create_read_back_text_match\n"
        "mcp_notes_body_replace_apply_status\n"
        "mcp_notes_body_replace_apply_verified\n"
        "mcp_notes_body_replace_read_back_text_match\n"
        "contacts_freeform_label_plan_status\n"
        "contacts_freeform_label_preserved\n"
        "contacts_freeform_label_apply_status\n"
        "contacts_freeform_label_apply_verified\n"
        "contacts_freeform_label_255_allowed\n"
        "contacts_freeform_label_oversize_refused\n"
        "contacts_freeform_label_control_refused\n"
        "contacts_freeform_label_case_space_distinct\n"
        "shortcuts_run_plan_status\n"
        "shortcuts_run_plan_effects_unverifiable\n"
        "shortcuts_run_plan_identifier_bound\n"
        "shortcuts_run_apply_status\n"
        "shortcuts_run_apply_verified\n"
        "shortcuts_run_invocation_confirmed\n"
        "shortcuts_run_side_effects_unverified\n"
        "shortcuts_run_missing_confirm_refused\n"
        "shortcuts_run_bad_token_refused\n"
        "shortcuts_run_spoofed_handle_refused\n"
        "shortcuts_run_folder_handle_refused\n"
        "shortcuts_run_injection_input_inert\n"
        "mcp_shortcuts_run_spoofed_handle_refused\n"
        "mcp_shortcuts_run_unconfirmed_refused\n"
        "mcp_messages_participant_list_status\n"
        "mcp_messages_participant_opaque_handle\n"
        "mcp_messages_participant_list_preview_absent\n"
        "mcp_messages_participant_list_identifier_absent\n"
        '"+15550100" not in str(listing)\n'
        '"15550100" not in str(listing)\n'
        "mcp_messages_participant_detail_status\n"
        "mcp_messages_participant_detail_matches\n"
        "mcp_messages_participant_invalid_warning\n"
        "_messages_mcp_participant_smoke\n"
        "messages_participant_list_identifier_absent\n"
        "messages_participant_cross_chat_status\n"
        "messages_participant_cross_chat_id_returned\n"
        "reminders_list_search_status\n"
        "reminders_get_list_status\n"
        "reminders_list_handle_opaque\n"
        "reminders_list_raw_id_absent\n"
        "reminders_move_to_list_plan_status\n"
        "reminders_move_to_list_apply_status\n"
        "reminders_move_to_list_read_back_list\n"
        "reminders_move_to_list_target_verified\n"
        "reminders_move_to_list_wrong_current_warning\n"
        "reminders_move_to_list_wrong_current_mutation_applied\n"
        "reminders_move_to_list_wrong_current_preview_returned\n"
        "reminders_move_to_list_wrong_current_fingerprint_returned\n"
        "reminders_update_url_plan_status\n"
        "reminders_update_url_plan_scheme\n"
        "reminders_update_url_apply_status\n"
        "reminders_update_url_apply_verified\n"
        "reminders_update_url_raw_returned\n"
        "reminders_clear_url_plan_status\n"
        "reminders_clear_url_apply_status\n"
        "reminders_clear_url_apply_absent_verified\n"
        "reminders_set_absolute_display_alarm_plan_status\n"
        "reminders_set_absolute_display_alarm_apply_status\n"
        "reminders_set_absolute_display_alarm_apply_verified\n"
        "reminders_set_absolute_display_alarm_apply_dates\n"
        "reminders_clear_display_alarm_plan_status\n"
        "reminders_clear_display_alarm_apply_status\n"
        "reminders_clear_display_alarm_apply_verified\n"
        "reminders_set_relative_display_alarm_plan_status\n"
        "reminders_set_relative_display_alarm_apply_status\n"
        "reminders_set_relative_display_alarm_apply_verified\n"
        "reminders_set_relative_display_alarm_apply_offsets\n"
        "reminders_clear_relative_display_alarm_plan_status\n"
        "reminders_clear_relative_display_alarm_apply_status\n"
        "reminders_clear_relative_display_alarm_apply_verified\n"
        "reminders_mixed_display_alarm_plan_status\n"
        "reminders_mixed_display_alarm_apply_status\n"
        "reminders_mixed_display_alarm_apply_verified\n"
        "reminders_mixed_display_alarm_apply_offsets\n"
        "reminders_mixed_display_alarm_apply_dates\n"
        "reminders_mixed_display_alarm_raw_alarm_state_returned\n"
        "reminders_mixed_display_alarm_clear_plan_status\n"
        "reminders_mixed_display_alarm_clear_apply_status\n"
        "reminders_mixed_display_alarm_clear_apply_verified\n"
        "reminders_mixed_display_alarm_clear_raw_alarm_state_returned\n"
        "reminders_apply_missing_confirmation_preview_returned\n"
        "reminders_apply_missing_confirmation_fingerprint_returned\n"
        "mcp_reminders_list_search_status\n"
        "mcp_reminders_get_list_status\n"
        "mcp_reminders_move_to_list_plan_status\n"
        "mcp_reminders_move_to_list_apply_status\n"
        "mcp_reminders_move_to_list_read_back_list\n"
        "mcp_reminders_move_to_list_target_verified\n"
        "mcp_reminders_move_to_list_wrong_current_warning\n"
        "mcp_reminders_move_to_list_wrong_current_mutation_applied\n"
        "mcp_reminders_move_to_list_wrong_current_preview_returned\n"
        "mcp_reminders_move_to_list_wrong_current_fingerprint_returned\n"
        "mcp_reminders_update_url_plan_status\n"
        "mcp_reminders_update_url_plan_scheme\n"
        "mcp_reminders_update_url_apply_status\n"
        "mcp_reminders_update_url_apply_verified\n"
        "mcp_reminders_update_url_raw_returned\n"
        "mcp_reminders_clear_url_plan_status\n"
        "mcp_reminders_clear_url_apply_status\n"
        "mcp_reminders_clear_url_apply_absent_verified\n"
        "mcp_reminders_clear_url_raw_returned\n"
        "mcp_reminders_set_absolute_display_alarm_plan_status\n"
        "mcp_reminders_set_absolute_display_alarm_apply_status\n"
        "mcp_reminders_set_absolute_display_alarm_apply_verified\n"
        "mcp_reminders_clear_display_alarm_plan_status\n"
        "mcp_reminders_clear_display_alarm_apply_status\n"
        "mcp_reminders_clear_display_alarm_apply_verified\n"
        "mcp_reminders_set_relative_display_alarm_plan_status\n"
        "mcp_reminders_set_relative_display_alarm_apply_status\n"
        "mcp_reminders_set_relative_display_alarm_apply_verified\n"
        "mcp_reminders_set_relative_display_alarm_apply_offsets\n"
        "mcp_reminders_clear_relative_display_alarm_plan_status\n"
        "mcp_reminders_clear_relative_display_alarm_apply_status\n"
        "mcp_reminders_clear_relative_display_alarm_apply_verified\n"
        "mcp_reminders_mixed_display_alarm_plan_status\n"
        "mcp_reminders_mixed_display_alarm_apply_status\n"
        "mcp_reminders_mixed_display_alarm_apply_verified\n"
        "mcp_reminders_mixed_display_alarm_apply_offsets\n"
        "mcp_reminders_mixed_display_alarm_apply_dates\n"
        "mcp_reminders_mixed_display_alarm_raw_alarm_state_returned\n"
        "mcp_reminders_mixed_display_alarm_clear_plan_status\n"
        "mcp_reminders_mixed_display_alarm_clear_apply_status\n"
        "mcp_reminders_mixed_display_alarm_clear_apply_verified\n"
        "mcp_reminders_mixed_display_alarm_clear_raw_alarm_state_returned\n"
        "LOCAL_APPLE_DATA_FS_ROOT\n"
        "filesystem_create_apply_verified\n"
        "filesystem_delete_apply_verified\n"
        "filesystem_outside_home_rejected\n"
        "filesystem_symlink_escape_rejected\n"
        "filesystem_credential_path_rejected\n"
        "filesystem_credential_compose_rejected\n"
        "mcp_filesystem_create_apply_verified\n"
        "mcp_filesystem_delete_apply_verified\n"
        "mcp_filesystem_credential_path_rejected\n"
        "mcp_filesystem_credential_compose_rejected\n",
        encoding="utf-8",
    )
    (root / "src/local_apple_data/adapters/reminders.py").write_text(
        'PLAN_OPERATIONS = {"create", "create_with_start_date", "create_with_recurrence", "complete", "uncomplete", "update_due_date", "update_start_date", "update_recurrence", "update_title", "update_notes", "update_priority", "update_url", "clear_url", "set_absolute_display_alarm", "set_relative_display_alarm", "set_mixed_display_alarm", "clear_display_alarm", "move_to_list", "delete"}\n'
        'LIST_MANAGEMENT_OPERATIONS = {"create_list", "rename_list", "delete_list", "delete_list_with_migration"}\n'
        "MAX_REMINDER_LIST_MIGRATION_COUNT\n"
        "delete_list_with_migration\n"
        "target_count_after\n"
        "list_migrated_verified\n"
        "source_list_empty_verified\n"
        "MAX_REMINDER_ALARMS\n"
        "ALARM_OPERATIONS\n"
        "SAFE_REMINDER_URL_SCHEMES\n"
        "expected_url_present\n"
        "expected_url_sha256\n"
        "url_safe_sha256\n"
        "url_verified\n"
        "url_absent_verified\n"
        "url_read_back_mismatch\n"
        "url_raw_returned\n"
        "alarm_absolute_dates\n"
        "expected_alarms_count\n"
        "expected_alarms_sha256\n"
        "alarms_safe_sha256\n"
        "set_relative_display_alarm\n"
        "set_mixed_display_alarm\n"
        "too_many_alarms\n"
        "alarm_offsets_minutes\n"
        "_normalize_alarm_offsets\n"
        "display_alarm_verified\n"
        "display_alarm_cleared_verified\n"
        "alarm_state_raw_returned\n"
        "_normalize_reminder_list_title\n"
        "list_create_read_back_mismatch\n"
        "source_safe_sha256\n"
        "plan_reminder_list_change\n"
        "apply_reminder_list_change\n"
        "create_list\n"
        "rename_list\n"
        "delete_list\n"
        "EVENTKIT_REMINDER_LIST_HANDLE_PREFIX\n"
        "LIST_TARGET_OPERATIONS\n"
        "search_reminder_lists\n"
        "get_reminder_list\n"
        "_eventkit_reminder_lists_response\n"
        "_eventkit_reminder_list_metadata\n"
        "_resolve_eventkit_list_id\n"
        "move_to_list\n"
        "expected_list_handle\n"
        "target_list_handle\n"
        "expected_list_id\n"
        "target_list_title\n"
        "expected_list_name\n"
        "expected_list_not_found\n"
        "target_list_not_found\n"
        "read_back_target_mismatch\n",
        encoding="utf-8",
    )
    (root / "scripts/eventkit_helper.swift").write_text(
        "dateOnlyString(from date: Date)\n"
        "eventDateString(from date: Date, allDay: Bool)\n"
        '"start_date": eventDateString(from: event.startDate, allDay: event.isAllDay)\n'
        '"end_date": eventDateString(from: event.endDate, allDay: event.isAllDay)\n'
        "case .daily:\n"
        "case .weekly:\n"
        "case .monthly:\n"
        "case .yearly:\n"
        'case "daily":\n'
        'case "weekly":\n'
        'case "monthly":\n'
        'case "yearly":\n'
        "recurrenceRequest\n"
        "recurrenceUpdateRequested\n"
        "applyRecurrence\n"
        "applyRecurrence(event, recurrence: proposedRecurrence)\n"
        "recurrencePayload\n"
        "recurrenceWeekdaysPayload\n"
        "recurrenceSetPositionsPayload\n"
        "recurrenceSetPositionsArrayValue\n"
        "setPositions: recurrenceSetPositions\n"
        "reminder_list_apply_change\n"
        "create_list\n"
        "rename_list\n"
        "delete_list\n"
        "listIsReminderOnly(sourceList)\n"
        "expected_empty_list\n"
        "list_empty_verified\n"
        "list_absent_verified\n"
        "payload[\"set_positions\"] = setPositions\n"
        "current[\"set_positions\"]\n"
        "recurrenceMonthDaysPayload\n"
        "recurrenceYearMonthsPayload\n"
        "monthDayArrayValue\n"
        "yearMonthArrayValue\n"
        "recurrenceMatches\n"
        "event.url = proposedEventURL\n"
        "expected_event_url_sha256\n"
        "includeURLProof\n"
        "proposedEventURLRequested\n"
        "proposedEventURLClearRequested\n"
        "readBackEventURLPresent\n"
        "readBackEventURLSHA256\n"
        "event_url_clear_read_back_mismatch\n"
        "adjacent_occurrence_event_url_present\n"
        "adjacent_occurrence_event_url_sha256\n"
        "adjacent_occurrence_event_url_read_back_mismatch\n"
        "adjacent_occurrence_event_url_verified\n"
        "include_url_proof\n"
        "recurrenceMatches(event, proposedRecurrence)\n"
        "EKRecurrenceRule(recurrenceWith: frequency, interval: interval, end: end)\n"
        "daysOfTheMonth: monthDays.map\n"
        "daysOfTheMonth: yearMonthDays.isEmpty ? nil : yearMonthDays.map\n"
        "monthsOfTheYear: yearMonths.map\n"
        '"year_month_days"\n'
        "guard yearMonthDays.isEmpty || yearMonthWeekdayValues.isEmpty\n"
        "EKRecurrenceDayOfWeek\n"
        "daysOfTheWeek: weekdays\n"
        "EKRecurrenceEnd(occurrenceCount: count)\n"
        "EKRecurrenceEnd(end: endDate)\n"
        "stringValue(recurrence, \"end_date\")\n"
        "event.recurrenceRules = [\n"
        "unsupported_recurrence_for_operation\n"
        "invalid_recurrence\n"
        "Calendar recurrence must be a bounded daily, weekly, monthly, or yearly rule.\n"
        "Calendar recurrence is not supported for delete operations.\n"
        "reminderListPayload\n"
        "reminder_lists\n"
        "move_to_list\n"
        "target_list_id\n"
        "expected_list_id\n"
        "expected_list_name\n"
        "Reminder list move requires target list and exact expected current list.\n"
        "Reminder current list identity did not match expected state.\n"
        "Reminder target list was not found.\n"
        "Reminder list did not match expected state.\n"
        "cross_account_list_move\n"
        "Reminder list-move read-back did not return the changed reminder.\n"
        "reminderAlarmStateSafeSHA256\n"
        "reminderAbsoluteAlarmDates\n"
        "reminderRelativeAlarmOffsets\n"
        "reminderMixedDisplayAlarmState\n"
        "reminderDisplayAlarmStateSupported\n"
        "set_mixed_display_alarm\n"
        "EKAlarm(absoluteDate:\n"
        "EKAlarm(relativeOffset:\n"
        "includeAlarmOffsets\n"
        "includeAlarmProof\n"
        "expected_alarms_sha256\n"
        "unsupported_alarm_state\n",
        encoding="utf-8",
    )
    (root / "tests/test_messages_adapter.py").write_text(
        "test_list_message_participants_returns_opaque_handles_without_identifiers\n"
        "test_get_message_participant_returns_exact_detail\n"
        "test_message_participant_detail_refuses_cross_chat_handle_binding\n"
        "test_messages_send_plan_and_apply_reject_participant_handles\n"
        "_assert_no_participant_list_identifier_leak\n"
        "id_preview\n"
        "participant_id\n"
        "+15550100\n",
        encoding="utf-8",
    )
    (root / "tests/test_cli_messages.py").write_text(
        "test_cli_messages_participants_and_participant_use_exact_handles\n"
        "test_cli_messages_participant_rejects_cross_chat_participant_handle\n"
        "events.jsonl\n"
        "messages:participant:v1:\n"
        "Expected messages:participant\n",
        encoding="utf-8",
    )
    (root / "tests/test_contacts_adapter.py").write_text(
        "test_plan_contact_change_update_replaces_contact_methods\n"
        "test_plan_contact_change_update_can_clear_contact_methods\n"
        "test_apply_contact_change_replaces_contact_methods_and_reads_back\n"
        "test_plan_contact_change_append_note_returns_exact_preview\n"
        "test_apply_contact_change_appends_note_and_reads_back_hash_only\n"
        "email_addresses\n"
        "phone_numbers\n"
        "url_addresses\n"
        "note_safe_sha256\n"
        "replace_email_addresses\n"
        "replace_phone_numbers\n"
        "replace_url_addresses\n",
        encoding="utf-8",
    )
    (root / "tests/test_cli_contacts.py").write_text(
        "test_cli_contacts_update_omitted_methods_preserve\n"
        "test_cli_contacts_update_method_replacements\n"
        "test_cli_contacts_update_clear_method_arrays\n"
        "test_cli_contacts_update_rejects_clear_and_replacement_conflict\n"
        "test_cli_contacts_append_note_forwards_exact_text\n"
        "--clear-emails\n"
        "--clear-phones\n"
        "--clear-urls\n",
        encoding="utf-8",
    )
    (root / "tests/test_reminders_adapter.py").write_text(
        "test_search_reminder_lists_returns_opaque_handles_without_ids\n"
        "test_get_reminder_list_returns_exact_metadata\n"
        "test_get_reminder_list_rejects_reminder_handle\n"
        "test_plan_reminder_change_move_to_list_binds_exact_handles\n"
        "test_plan_reminder_change_move_to_list_requires_exact_list_handle\n"
        "test_plan_reminder_change_move_to_list_requires_exact_current_list_handle\n"
        "test_plan_reminder_change_move_to_list_requires_expected_completed\n"
        "test_apply_reminder_change_move_to_list_resolves_exact_handles_and_applies\n"
        "test_apply_reminder_change_move_to_list_rejects_unverified_target_identity\n"
        "invalid_expected_list_handle\n"
        "target_list_verified\n"
        "test_eventkit_helper_rejects_cross_account_list_move\n"
        "test_eventkit_helper_checks_expected_list_before_already_applied\n"
        "test_plan_reminder_list_create_binds_source_and_list_title\n"
        "test_plan_reminder_list_rename_requires_exact_empty_list\n"
        "test_apply_reminder_list_create_calls_eventkit_and_reads_back\n"
        "test_apply_reminder_list_delete_requires_absence_proof\n"
        "test_search_reminders_eventkit_strips_url_hash_from_metadata\n"
        "test_plan_reminder_change_update_url_binds_hash_without_raw_url\n"
        "test_plan_reminder_change_update_url_rejects_unsafe_shapes\n"
        "test_plan_reminder_change_url_requires_expected_completed\n"
        "test_apply_reminder_change_updates_url_with_hash_read_back\n"
        "test_apply_reminder_change_clears_url_with_absence_proof\n"
        "test_apply_reminder_change_update_url_refuses_stale_current_url\n"
        "test_apply_reminder_change_update_url_mismatch_is_apply_unknown\n"
        "test_plan_reminder_change_set_absolute_display_alarm_binds_dates\n"
        "test_plan_reminder_change_absolute_display_alarm_rejects_invalid_dates\n"
        "test_plan_reminder_change_set_relative_display_alarm_binds_offsets\n"
        "test_plan_reminder_change_relative_display_alarm_rejects_invalid_offsets\n"
        "test_plan_reminder_change_clear_display_alarm_requires_expected_hash\n"
        "test_apply_reminder_change_sets_absolute_display_alarm_with_read_back\n"
        "test_apply_reminder_change_sets_relative_display_alarm_with_read_back\n"
        "test_apply_reminder_change_clears_display_alarm_with_absence_proof\n"
        "test_apply_reminder_change_clears_relative_display_alarm_with_absence_proof\n"
        "test_plan_reminder_change_set_mixed_display_alarm_binds_offsets_and_dates\n"
        "test_plan_reminder_change_mixed_display_alarm_rejects_invalid_shapes\n"
        "test_apply_reminder_change_sets_mixed_display_alarm_with_read_back\n"
        "test_apply_reminder_change_sets_mixed_display_alarm_from_absolute_state\n"
        "test_apply_reminder_change_clears_mixed_display_alarm_with_absence_proof\n"
        "test_apply_reminder_change_mixed_alarm_refuses_stale_current_state\n"
        "test_apply_reminder_change_mixed_alarm_mismatch_is_apply_unknown\n"
        "test_apply_reminder_change_clear_display_alarm_refuses_unsupported_alarm_state\n"
        "test_apply_reminder_change_alarm_refuses_stale_current_state\n"
        "test_apply_reminder_change_alarm_mismatch_is_apply_unknown\n"
        "test_apply_reminder_change_relative_alarm_mismatch_is_apply_unknown\n",
        encoding="utf-8",
    )
    (root / "tests/test_cli_reminders.py").write_text(
        "test_cli_reminders_lists_and_list\n"
        "test_cli_reminders_plan_and_apply_list\n"
        "test_cli_reminders_plan_and_apply_update_url\n"
        "test_cli_reminders_plan_and_apply_absolute_display_alarm\n"
        "test_cli_reminders_plan_and_apply_relative_display_alarm\n"
        "test_cli_reminders_plan_and_apply_mixed_display_alarm\n"
        "set-mixed-display-alarm\n"
        "plan-list\n"
        "apply-list\n"
        "--target-list-handle\n"
        "--expected-list-handle\n"
        "--expected-list-name\n"
        "--expected-url-present\n"
        "--expected-url-sha256\n"
        "--alarm-absolute-dates\n"
        "--alarm-offsets-minutes\n"
        "--expected-alarms-count\n"
        "--expected-alarms-sha256\n"
        "Synthetic Target List\n",
        encoding="utf-8",
    )
    (root / "tests/test_icloud_drive_adapter.py").write_text(
        "\n".join(
            [
                "create_folder",
                "rename_folder",
                "trash_folder",
                "delete_folder",
                "move_folder",
                "copy_folder",
                "trash_text",
                "delete_text",
                "rename_text",
                "copy_text",
                "move_text",
                "rename_file",
                "copy_file",
                "move_file",
                "import_file",
                "replace_file",
                "trash_file",
                "delete_file",
                "test_plan_icloud_drive_change_import_file_returns_preview_without_path_or_hash",
                "test_apply_icloud_drive_change_import_file_copies_to_exact_parent",
                "test_apply_icloud_drive_change_import_file_rejects_stale_source_token",
                "test_plan_icloud_drive_change_import_file_rejects_unsafe_sources",
                "test_plan_icloud_drive_change_replace_file_returns_preview_without_path_or_hash",
                "test_plan_icloud_drive_change_replace_file_rejects_unsafe_sources",
                "test_apply_icloud_drive_change_replace_file_replaces_exact_target",
                "test_apply_icloud_drive_change_replace_file_rejects_stale_source_token",
                "test_apply_icloud_drive_change_replace_file_reports_source_drift_during_stream",
                "test_apply_icloud_drive_change_replace_file_rejects_stale_target_metadata",
                "test_apply_icloud_drive_change_trash_file_moves_exact_regular_file_to_trash",
                "test_apply_icloud_drive_change_trash_file_rejects_stale_metadata",
                "test_apply_icloud_drive_change_trash_file_rejects_text_handle",
                "test_apply_icloud_drive_change_trash_file_rejects_symlink_handle",
                "test_apply_icloud_drive_change_delete_file_removes_exact_regular_file",
                "test_apply_icloud_drive_change_delete_file_rejects_stale_metadata",
                "test_apply_icloud_drive_change_delete_file_rechecks_before_staging",
                "test_apply_icloud_drive_change_delete_file_rollback_does_not_claim_success",
                "test_apply_icloud_drive_change_delete_file_rejects_text_handle",
                "test_apply_icloud_drive_change_delete_file_rejects_symlink_handle",
                "test_apply_icloud_drive_change_delete_file_rejects_package_member",
                "test_apply_icloud_drive_change_delete_file_rejects_non_regular_handle",
                "already_applied",
                '"content_sha256" not in result["read_back"]',
                "metadata_sha256",
                "content_hash_returned",
                "trash_path_returned",
                "test_plan_icloud_drive_change_rename_copy_move_file_returns_preview_only",
                "test_plan_icloud_drive_change_rename_copy_move_file_reject_wrong_inputs",
                "test_plan_icloud_drive_change_rename_folder_returns_preview_only",
                "test_plan_icloud_drive_change_trash_folder_returns_preview_only",
                "test_plan_icloud_drive_change_delete_folder_returns_preview_only",
                "test_plan_icloud_drive_change_delete_folder_rejects_wrong_inputs",
                "test_plan_icloud_drive_change_move_folder_returns_preview_only",
                "test_plan_icloud_drive_change_copy_folder_returns_preview_only",
                "test_apply_icloud_drive_change_renames_folder_and_preserves_child",
                "test_apply_icloud_drive_change_rename_folder_rejects_stale_metadata",
                "test_apply_icloud_drive_change_rename_folder_allows_non_empty_folder",
                "test_apply_icloud_drive_change_non_empty_folder_probe_does_not_list_children",
                "test_apply_icloud_drive_change_rename_folder_reports_partial_if_folder_changes_during_apply",
                "test_apply_icloud_drive_change_rename_folder_refuses_existing_target",
                "test_apply_icloud_drive_change_rename_folder_rejects_file_handle",
                "test_apply_icloud_drive_change_trashes_empty_folder_and_reads_back_absence",
                "test_apply_icloud_drive_change_trash_folder_rejects_stale_metadata",
                "test_apply_icloud_drive_change_trash_folder_allows_non_empty_folder",
                "test_apply_icloud_drive_change_trash_folder_allows_apply_time_non_empty_race",
                "test_apply_icloud_drive_change_trash_folder_reports_partial_if_cleanup_fails",
                "test_apply_icloud_drive_change_trash_folder_rollback_does_not_claim_trash",
                "test_apply_icloud_drive_change_trash_folder_rejects_file_handle",
                "test_apply_icloud_drive_change_deletes_empty_folder_and_reads_back_absence",
                "test_apply_icloud_drive_change_delete_folder_rejects_stale_metadata",
                "test_apply_icloud_drive_change_delete_folder_allows_non_empty_folder",
                "test_apply_icloud_drive_change_delete_folder_rolls_back_if_folder_races_non_empty",
                "test_apply_icloud_drive_change_delete_folder_reports_partial_if_race_rollback_fails",
                "test_apply_icloud_drive_change_delete_folder_rolls_back_after_staged_rmdir_failure",
                "test_apply_icloud_drive_change_delete_folder_reports_partial_if_staged_rmdir_rollback_fails",
                "test_apply_icloud_drive_change_delete_folder_rejects_file_handle",
                "test_apply_icloud_drive_change_delete_folder_rejects_fabricated_handle",
                "test_apply_icloud_drive_change_delete_folder_rejects_symlink_target",
                "test_apply_icloud_drive_change_delete_folder_rejects_package_component",
                "test_plan_icloud_drive_change_delete_folder_rejects_unsafe_or_too_large_tree",
                "test_apply_icloud_drive_change_moves_folder_and_preserves_child",
                "test_apply_icloud_drive_change_move_folder_rejects_stale_metadata",
                "test_apply_icloud_drive_change_move_folder_allows_non_empty_folder",
                "test_apply_icloud_drive_change_move_folder_refuses_existing_target",
                "test_apply_icloud_drive_change_move_folder_rejects_self_parent",
                "test_apply_icloud_drive_change_move_folder_rejects_descendant_parent",
                "test_apply_icloud_drive_change_move_folder_reports_partial_if_folder_changes_during_apply",
                "test_apply_icloud_drive_change_copies_empty_folder_and_reads_back_metadata",
                "test_apply_icloud_drive_change_copy_folder_rejects_stale_metadata",
                "test_apply_icloud_drive_change_copy_folder_allows_non_empty_folder",
                "test_apply_icloud_drive_change_copy_folder_refuses_existing_target",
                "test_apply_icloud_drive_change_copy_folder_rejects_self_parent",
                "test_apply_icloud_drive_change_copy_folder_rejects_descendant_parent",
                "test_plan_icloud_drive_change_copy_folder_rejects_unsafe_or_too_large_tree",
                "test_apply_icloud_drive_change_copy_folder_rolls_back_if_source_races_after_copy",
                "test_apply_icloud_drive_change_copy_folder_reports_partial_if_race_cleanup_fails",
                "test_apply_icloud_drive_change_copy_folder_reports_error_after_cleaned_target_identity_race",
                "test_copy_folder_tree_and_cleanup_do_not_use_unbounded_os_walk",
                "test_copy_folder_tree_cleanup_refuses_unexpected_target_entries",
                "test_folder_copy_tree_snapshot_sorts_bounded_names_without_builtin_sorted",
                "test_apply_icloud_drive_change_copy_folder_rejects_swapped_child_directory_before_file_copy",
                "test_apply_icloud_drive_change_trash_text_rejects_invalid_utf8_target",
                "test_apply_icloud_drive_change_trash_text_rejects_package_member_after_resolution",
                "test_apply_icloud_drive_change_trash_text_rejects_unsafe_parent_reopen",
                "test_apply_icloud_drive_change_trash_text_rechecks_after_swap",
                "test_apply_icloud_drive_change_trash_text_reports_partial_after_cleanup_failure",
                "test_plan_icloud_drive_change_delete_text_returns_preview_only",
                "test_plan_icloud_drive_change_delete_text_rejects_unsupported_target_without_approval",
                "test_apply_icloud_drive_change_deletes_text_and_reads_back_absence",
                "test_apply_icloud_drive_change_delete_text_refuses_hash_drift",
                "test_apply_icloud_drive_change_delete_text_refuses_content_drift_after_identity_check",
                "test_apply_icloud_drive_change_delete_text_rejects_recreated_same_content_with_stale_token",
                "test_apply_icloud_drive_change_delete_text_rejects_same_content_identity_race_after_token_validation",
                "test_apply_icloud_drive_change_delete_text_rolls_back_after_staged_unlink_failure",
                "test_apply_icloud_drive_change_delete_text_reports_partial_if_staged_unlink_rollback_fails",
                "test_apply_icloud_drive_change_delete_text_rejects_unsupported_target",
                "test_apply_icloud_drive_change_delete_text_rejects_invalid_utf8_target",
                "test_apply_icloud_drive_change_renames_text_and_reads_back_absence",
                "test_apply_icloud_drive_change_rename_text_refuses_existing_target",
                "test_apply_icloud_drive_change_rename_text_rechecks_after_swap",
                "test_apply_icloud_drive_change_copy_text_refuses_hash_drift",
                "test_apply_icloud_drive_change_copy_text_rechecks_source_after_copy",
                "test_apply_icloud_drive_change_copies_text_and_preserves_source",
                "test_apply_icloud_drive_change_move_text_refuses_hash_drift",
                "test_apply_icloud_drive_change_move_text_rechecks_after_swap",
                "test_apply_icloud_drive_change_moves_text_to_exact_parent",
                "test_apply_icloud_drive_change_renames_file_metadata_only",
                "test_apply_icloud_drive_change_copies_file_metadata_only",
                "test_apply_icloud_drive_change_moves_file_to_exact_parent_metadata_only",
                "test_apply_icloud_drive_change_copy_file_refuses_metadata_drift",
                "test_apply_icloud_drive_change_rename_file_rechecks_after_swap",
                "test_apply_icloud_drive_change_move_file_rechecks_after_swap",
                "test_apply_icloud_drive_change_copy_file_rechecks_target_bytes",
                "test_apply_icloud_drive_change_file_operations_reject_text_source",
                "test_apply_icloud_drive_change_rename_copy_move_file_refuses_existing_target",
                "test_apply_icloud_drive_change_rename_copy_move_refuse_symlink_targets",
                "test_apply_icloud_drive_change_rename_copy_move_file_refuse_symlink_targets",
                "test_apply_icloud_drive_change_copy_cleanup_preserves_racing_replacement",
                "test_apply_icloud_drive_change_rename_reports_partial_when_rollback_fails",
                "test_apply_icloud_drive_change_move_reports_partial_when_rollback_fails",
                "test_apply_icloud_drive_change_rename_preserves_verified_target_when_source_cleanup_races",
                "test_apply_icloud_drive_change_move_preserves_verified_target_when_source_cleanup_races",
                "test_trash_root_for_configured_default_uses_home_trash",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "tests/test_cli_metadata.py").write_text(
        "test_cli_icloud_drive_search_rejects_root_override_without_test_opt_in\n"
        "test_cli_icloud_drive_get_rejects_root_override_without_test_opt_in\n"
        "test_cli_icloud_drive_content_rejects_root_override_without_test_opt_in\n"
        "test_cli_icloud_drive_apply_rejects_root_override_without_test_opt_in\n"
        "test_cli_icloud_drive_plan_and_apply_create_folder\n"
        "test_cli_icloud_drive_plan_and_apply_rename_folder\n"
        "test_cli_icloud_drive_plan_and_apply_trash_folder\n"
        "test_cli_icloud_drive_plan_and_apply_delete_folder\n"
        "test_cli_icloud_drive_plan_and_apply_move_folder\ntest_cli_icloud_drive_plan_and_apply_copy_folder\n"
        "test_cli_icloud_drive_plan_and_apply_trash_text\n"
        "test_cli_icloud_drive_plan_and_apply_delete_text\n"
        "test_cli_icloud_drive_plan_delete_text_rejects_unsupported_without_approval\n"
        "test_cli_icloud_drive_delete_text_rejects_same_content_stale_token\n"
        "test_cli_icloud_drive_plan_and_apply_rename_copy_move_text\n"
        "test_cli_icloud_drive_plan_and_apply_rename_copy_move_file\n"
        "import-file\n"
        "replace-file\n"
        "--source-file\n"
        "test_cli_icloud_drive_rename_copy_move_tokens_bind_exact_plan\n"
        "test_cli_notes_plan_rejects_icloud_drive_only_operations\n"
        "test_cli_notes_plan_and_apply_create_folder\n"
        "test_cli_notes_plan_and_apply_rename_folder\n"
        "test_cli_notes_plan_and_apply_delete_folder\n"
        "test_cli_notes_plan_and_apply_move_folder\n"
        "test_cli_icloud_drive_create_folder_rejects_conflicting_name_aliases\n"
        "test_cli_calendar_plan_and_apply_create_all_day\n"
        "test_cli_calendar_plan_and_apply_alarm_offsets\n"
        "test_cli_calendar_plan_and_apply_absolute_alarm_dates\n"
        "test_cli_calendar_plan_and_apply_recurrence\n"
        "test_cli_calendar_plan_and_apply_recurrence_end_date\n"
        "test_cli_calendar_plan_and_apply_unbounded_recurrence\n"
        "test_cli_calendar_plan_and_apply_update_recurrence\n"
        "test_cli_calendar_plan_and_apply_update_unbounded_recurrence\n"
        "test_cli_calendar_plan_and_apply_weekly_weekday_recurrence\n"
        "test_cli_calendar_plan_and_apply_monthly_nth_weekday_recurrence\n"
        "test_cli_calendar_plan_and_apply_update_monthly_nth_weekday_recurrence\n"
        "test_cli_calendar_plan_and_apply_yearly_month_recurrence\n"
        "test_cli_calendar_plan_and_apply_update_yearly_month_recurrence\n"
        "test_cli_calendar_plan_and_apply_clear_recurrence\n"
        "test_cli_calendar_plan_and_apply_monthly_weekday_recurrence\n"
        "test_cli_calendar_plan_and_apply_structured_location\n"
        "test_cli_calendar_plan_and_apply_email_alarm_hash\n"
        "test_cli_calendar_clear_structured_location_forwards_to_plan_and_apply\n"
        "test_cli_calendar_calendars_and_calendar_use_exact_handle\n"
        "test_cli_calendar_plan_and_apply_target_calendar_handles\n"
        "test_cli_calendar_plan_and_apply_use_default_calendar\n"
        "test_cli_mail_sender_handle_forwards_to_plan_and_apply\n"
        "test_cli_calendar_plan_and_apply_mid_series_recurrence_replacement\n"
        "--all-day\n"
        "--expected-all-day\n"
        "--alarm-offsets-minutes\n"
        "--expected-alarm-offsets-minutes\n"
        "--alarm-absolute-dates\n"
        "--expected-alarm-absolute-dates\n"
        "--alarm-email-address\n"
        "--expected-alarm-email-address-sha256\n"
        "--recurrence-frequency\n"
        "--recurrence-interval\n"
        "--recurrence-count\n"
        "--recurrence-end-date\n"
        "--recurrence-unbounded\n"
        "--recurrence-weekdays\n"
        "--recurrence-month-days\n"
        "--recurrence-month-weekdays\n"
        "--recurrence-year-months\n"
        "--recurrence-year-month-days\n"
        "--clear-recurrence\n"
        "--recurrence-update-scope\n"
        "--structured-location\n"
        "--clear-structured-location\n"
        "--expected-structured-location\n"
        "--use-default-calendar\n"
        "test_cli_calendar_plan_and_apply_event_url\n"
        "test_cli_calendar_event_url_rejects_operation_mismatches\n"
        "test_cli_calendar_plan_and_apply_clear_event_url\n"
        "test_cli_calendar_plan_and_apply_delete_recurring_occurrence\n"
        "test_cli_calendar_plan_and_apply_yearly_month_day_recurrence\n"
        "test_cli_calendar_plan_and_apply_update_yearly_month_day_recurrence\n"
        "--event-url\n"
        "--clear-event-url\n"
        "--recurrence-delete-scope\n"
        "--recurrence-set-positions\n"
        "--expected-event-url-present\n"
        "--expected-event-url-sha256\n",
        encoding="utf-8",
    )
    (root / "tests/test_mcp_server.py").write_text(
        "test_mcp_icloud_drive_plan_create_folder_without_content_text\n"
        "test_mcp_icloud_drive_plan_rename_folder_without_content_text\n"
        "test_mcp_icloud_drive_plan_trash_folder_without_content_text\n"
        "test_mcp_icloud_drive_plan_delete_folder_without_content_text\n"
        "test_mcp_icloud_drive_plan_move_folder_without_content_text\ntest_mcp_icloud_drive_plan_copy_folder_without_content_text\n"
        "test_mcp_icloud_drive_plan_trash_text_without_content_text\n"
        "test_mcp_icloud_drive_plan_delete_text_without_content_text\n"
        "test_mcp_icloud_drive_plan_delete_text_rejects_unsupported_without_approval\n"
        "test_mcp_icloud_drive_plan_rename_copy_move_without_content_text\n"
        "rename_file\n"
        "copy_file\n"
        "move_file\n"
        "source_file\n"
        "import_file\n"
        "replace_file\n"
        "trash_file\n"
        "test_mcp_icloud_drive_apply_rename_copy_move_without_content_text\ntest_mcp_icloud_drive_apply_copy_folder_without_content_text\n"
        "test_mcp_icloud_drive_delete_text_rejects_same_content_stale_token\n"
        "test_mcp_messages_participant_wrappers_preserve_exact_detail_gate\n"
        "reminders_search_lists\n"
        "reminders_get_list\n"
        "test_mcp_reminders_list_management_wrappers_preserve_gate\n"
        "reminders_plan_list_change\n"
        "reminders_apply_list_change\n"
        "test_mcp_reminders_list_move_wrappers_preserve_exact_gate\n"
        "test_mcp_reminders_url_wrappers_preserve_exact_gate\n"
        "test_mcp_reminders_absolute_display_alarm_wrappers_preserve_exact_gate\n"
        "test_mcp_reminders_relative_display_alarm_wrappers_preserve_exact_gate\n"
        "test_mcp_calendar_all_day_plan_and_apply_bind_flags_without_eventkit\n"
        "test_mcp_calendar_alarm_offsets_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_absolute_alarms_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_recurrence_end_date_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_unbounded_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_update_unbounded_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_month_day_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_monthly_weekday_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_monthly_nth_weekday_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_yearly_month_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_yearly_month_day_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_yearly_month_nth_weekday_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_update_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_update_monthly_weekday_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_update_monthly_nth_weekday_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_update_yearly_month_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_update_yearly_month_day_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_update_yearly_month_nth_weekday_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_clear_recurrence_fails_closed_without_occurrence_identity\n"
        "test_mcp_calendar_event_url_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_event_url_rejects_operation_mismatches\n"
        "test_mcp_calendar_clear_event_url_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_structured_location_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_clear_structured_location_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_email_alarm_plan_and_apply_hash_without_eventkit\n"
        "test_mcp_calendar_set_positions_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_calendar_management_wrappers_forward_exact_inputs\n"
        "alarm_email_address=\"Notify@Example.Invalid\"\n"
        "recurrence_set_positions=[-1]\n"
        "recurrence_end_date=\"2026-08-01T17:00:00Z\"\n"
        "event_url=\"http://meet.example.invalid/runtime?id=42\"\n"
        "structured_location={\n"
        "recurrence_month_days=[1, 15, -1]\n"
        "recurrence_year_month_days=[15, 1, -1]\n"
        "recurrence_month_weekdays=[{\"weekday\": \"tuesday\", \"week_number\": 3}]\n"
        "clear_recurrence=True\n"
        "test_mcp_calendar_delete_recurring_occurrence_fails_closed_without_occurrence_identity\n"
        "test_mcp_mail_tools_redact_unexpected_errors\n"
        "test_mcp_contacts_tools_redact_unexpected_errors\n"
        "test_mcp_stdio_mail_error_keeps_contacts_available\n"
        "recurrence_delete_scope=\"this-event\"\n"
        "test_mcp_calendar_date_only_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_default_calendar_flag_forwards_to_adapter\n"
        "test_mcp_calendar_target_calendar_handles_bind_without_eventkit\n"
        "test_mcp_contacts_update_forwards_exact_binding\n"
        "test_mcp_contacts_append_note_forwards_exact_binding\n"
        "test_mcp_notes_create_folder_forwards_exact_parent\n"
        "test_mcp_notes_rename_folder_forwards_exact_binding\n"
        "test_mcp_notes_delete_folder_forwards_exact_binding\n"
        "test_mcp_notes_move_folder_forwards_exact_binding\n"
        "test_mcp_mail_move_forwards_exact_target_mailbox\n"
        "target_mailbox_handle\n"
        "mail:mailbox:v1:target\n"
        "test_mcp_mail_sender_handle_forwards_exact_inputs\n"
        "alarm_offsets_minutes=[0, -10]\n"
        "alarm_absolute_dates=[\"2026-06-05T16:45:00Z\"]\n"
        "recurrence_frequency=\"yearly\"\n"
        "recurrence_count=3\n"
        "event_url=\"http://meet.example.invalid/runtime?id=42\"\n"
        "all_day=True\n"
        "create_folder\nrename_folder\ntrash_folder\ndelete_folder\nmove_folder\ncopy_folder\ntrash_text\ndelete_text\nrename_text\ncopy_text\nmove_text\n",
        encoding="utf-8",
    )
    (root / "src/local_apple_data/adapters/messages.py").write_text(
        'PLAN_OPERATIONS = {"send_text", "send_file"}\n'
        'MESSAGE_PARTICIPANT_HANDLE_PREFIX = "messages:participant"\n'
        "def list_message_participants():\n"
        "    return {'participant_id_returned': False}\n"
        "def get_message_participant():\n"
        "    return {'participant_id_returned': True}\n"
        "def _find_participant_row():\n"
        "    return None\n"
        "SOURCE_CONTRACT = '''\n"
        "\"participant_id_returned\": False\n"
        "include_identifier=False\n"
        "include_identifier=True\n"
        "Messages send planning requires a messages:chat:v1 handle.\n"
        "'''\n",
        encoding="utf-8",
    )
    (root / "tests/test_notes_adapter.py").write_text(
        "test_plan_notes_change_create_folder_requires_exact_parent\n"
        "test_plan_notes_change_create_folder_rejects_body_note_target_and_smart_parent\n"
        "test_apply_notes_change_creates_child_folder_and_reads_back\n"
        "test_apply_notes_change_create_folder_rejects_wrong_returned_folder_id\n"
        "test_apply_notes_change_create_folder_rejects_returned_smart_folder_id\n"
        "test_apply_notes_change_create_folder_is_idempotent_for_existing_child\n"
        "test_apply_notes_change_create_folder_ignores_existing_smart_child\n"
        "test_apply_notes_change_create_folder_requires_parent_readback\n"
        "test_notes_create_folder_script_targets_only_exact_parent_folder\n"
        "test_plan_notes_change_rename_folder_returns_exact_preview\n"
        "test_plan_notes_change_rename_folder_rejects_bad_targets\n"
        "test_apply_notes_change_renames_folder_and_reads_back\n"
        "test_apply_notes_change_rename_folder_rejects_stale_title\n"
        "test_apply_notes_change_rename_folder_retry_is_idempotent\n"
        "test_notes_rename_folder_script_targets_only_exact_folder\n"
        "test_plan_notes_change_delete_folder_returns_exact_empty_child_preview\n"
        "test_plan_notes_change_delete_folder_rejects_note_smart_root_and_non_empty_targets\n"
        "test_plan_notes_change_delete_folder_rejects_child_folders\n"
        "test_plan_notes_change_move_folder_returns_exact_empty_child_preview\n"
        "test_plan_notes_change_move_folder_requires_hash_source_and_target\n"
        "test_plan_notes_change_move_folder_rejects_unsafe_targets\n"
        "test_apply_notes_change_deletes_empty_child_folder_and_reads_absence\n"
        "test_apply_notes_change_delete_folder_rejects_stale_title\n"
        "test_apply_notes_change_delete_folder_rejects_new_note_before_write\n"
        "test_apply_notes_change_delete_folder_rejects_smart_folder_drift\n"
        "test_apply_notes_change_delete_folder_rejects_new_child_folder_before_write\n"
        "test_apply_notes_change_delete_folder_handles_automation_not_empty\n"
        "test_apply_notes_change_delete_folder_handles_automation_shared_folder\n"
        "test_apply_notes_change_delete_folder_reports_unavailable_absence_readback\n"
        "test_apply_notes_change_delete_folder_requires_absence_readback\n"
        "test_apply_notes_change_move_folder_moves_empty_child_and_verifies_parent\n"
        "test_apply_notes_change_move_folder_rejects_stale_title\n"
        "test_apply_notes_change_move_folder_rejects_new_note_before_write\n"
        "test_apply_notes_change_move_folder_fails_closed_after_prior_move\n"
        "test_apply_notes_change_move_folder_requires_matching_read_back\n"
        "test_notes_delete_folder_script_targets_only_exact_empty_folder\n"
        "test_notes_move_folder_script_moves_only_exact_empty_source_folder\n"
        "_notes_create_folder_script\n"
        "_notes_rename_folder_script\n"
        "_notes_delete_folder_script\n"
        "_notes_move_folder_script\n"
        "make new folder at targetFolder\n"
        "set name of targetFolder\n"
        "delete targetFolder\n"
        "move sourceFolder to targetFolder\n"
        "parent_folder_confirmed\n"
        "target_folder_confirmed\n"
        "folder_content_returned\n",
        encoding="utf-8",
    )
    (root / "src/local_apple_data/adapters/notes.py").write_text(
        'PLAN_OPERATIONS = {"create", "create_html", "create_folder", "rename_folder", "delete_folder", "move_folder", "append_text", "replace_text", "replace_html", "move_to_folder", "delete"}\n'
        '"create_folder"\n'
        '"rename_folder"\n'
        '"delete_folder"\n'
        '"move_folder"\n'
        "_apply_notes_create_folder\n"
        "_apply_notes_rename_folder\n"
        "_apply_notes_delete_folder\n"
        "_apply_notes_move_folder\n"
        "_notes_create_folder_script\n"
        "_notes_rename_folder_script\n"
        "_notes_delete_folder_script\n"
        "_notes_move_folder_script\n"
        "_notes_folder_rename_read_back\n"
        "_notes_folder_delete_read_back\n"
        "_notes_folder_move_read_back\n"
        "_folder_delete_safety_warning\n"
        "_folder_move_safety_warning\n"
        "_resolve_folder_move_plan_target\n"
        "_find_matching_child_folder\n"
        "_created_folder_row_has_expected_identity\n"
        "SQL_SMART_FILTER = \"COALESCE(f.ZSMARTFOLDERQUERYJSON, '') = ''\"\n"
        "parent_folder_confirmed\n"
        "folder_content_returned\n"
        "note_content_returned\n",
        encoding="utf-8",
    )
    (root / "tests/test_calendar_adapter.py").write_text(
        "test_plan_calendar_change_create_all_day_binds_preview\n"
        "test_plan_calendar_change_create_rejects_string_boolean\n"
        "test_apply_calendar_change_creates_all_day_event_and_reads_back\n"
        "test_apply_calendar_change_updates_all_day_event_and_reads_back\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_all_day\n"
        "test_apply_calendar_change_clears_selected_recurring_occurrence_all_day\n"
        "test_apply_calendar_change_reschedules_selected_recurring_occurrence_all_day_date_only\n"
        "test_plan_calendar_change_selected_recurring_occurrence_all_day_requires_date_only\n"
        "test_plan_calendar_change_selected_recurring_occurrence_all_day_set_requires_expected_time_zone\n"
        "test_plan_calendar_change_selected_recurring_occurrence_all_day_clear_requires_time_zone\n"
        "test_plan_calendar_change_update_rejects_string_boolean_flags\n"
        "test_apply_calendar_change_deletes_all_day_event_and_binds_expected_flag\n"
        "test_plan_calendar_change_delete_rejects_string_expected_all_day\n"
        "test_eventkit_update_checks_expected_state_before_already_applied\n"
        "test_plan_calendar_change_create_alarm_offsets_binds_preview\n"
        "test_plan_calendar_change_create_absolute_alarms_binds_preview\n"
        "test_plan_calendar_change_create_recurrence_binds_preview_and_token\n"
        "test_plan_calendar_change_create_recurrence_end_date_binds_preview_and_token\n"
        "test_plan_calendar_change_create_unbounded_recurrence_binds_preview_and_token\n"
        "test_plan_calendar_change_all_day_recurrence_end_date_uses_bounded_compare\n"
        "test_plan_calendar_change_create_monthly_recurrence_binds_preview\n"
        "test_plan_calendar_change_create_monthly_weekday_recurrence_binds_preview\n"
        "test_plan_calendar_change_create_monthly_recurrence_month_days_binds_preview\n"
        "test_plan_calendar_change_create_monthly_nth_weekday_recurrence_binds_preview\n"
        "test_plan_calendar_change_create_yearly_month_recurrence_binds_preview\n"
        "test_plan_calendar_change_create_yearly_month_day_recurrence_binds_preview\n"
        "test_plan_calendar_change_create_weekly_recurrence_weekdays_binds_preview\n"
        "test_apply_calendar_change_creates_yearly_recurring_event_and_reads_back\n"
        "test_apply_calendar_change_creates_yearly_month_day_recurrence_and_reads_back\n"
        "test_apply_calendar_change_creates_recurrence_end_date_and_reads_back\n"
        "test_apply_calendar_change_updates_recurrence_end_date_and_reads_back\n"
        "test_apply_calendar_change_clears_recurrence_with_end_date_series_proof\n"
        "test_apply_calendar_change_deletes_end_date_recurring_occurrence_and_binds_scope\n"
        "test_plan_calendar_change_create_date_only_infers_all_day\n"
        "test_plan_calendar_change_rejects_mixed_date_only_and_timestamp\n"
        "test_plan_calendar_change_rejects_time_zone_for_inferred_date_only_all_day\n"
        "test_plan_calendar_change_rejects_unsupported_recurrence_shapes\n"
        "test_plan_calendar_change_update_recurrence_binds_preview_and_token\n"
        "test_plan_calendar_change_update_unbounded_recurrence_binds_preview_and_token\n"
        "test_plan_calendar_change_update_weekly_weekday_recurrence_binds_preview\n"
        "test_plan_calendar_change_update_monthly_month_day_recurrence_binds_preview\n"
        "test_apply_calendar_change_updates_yearly_month_day_recurrence_and_reads_back\n"
        "test_plan_calendar_change_create_event_url_binds_preview_and_token\n"
        "test_plan_calendar_change_update_event_url_binds_expected_state_and_token\n"
        "test_plan_calendar_change_update_clear_event_url_binds_expected_state_and_token\n"
        "test_plan_calendar_change_clear_event_url_rejects_unsafe_shapes\n"
        "test_plan_calendar_change_update_clear_recurrence_binds_series_proof_and_token\n"
        "test_plan_calendar_change_update_clear_recurrence_rejects_unsafe_shapes\n"
        "test_plan_calendar_change_create_rejects_expected_event_url_state\n"
        "test_plan_calendar_change_delete_rejects_event_url_input\n"
        "test_plan_calendar_change_rejects_non_exact_expected_event_url_sha\n"
        "test_apply_calendar_change_creates_event_url_and_reads_back_hash\n"
        "test_apply_calendar_change_updates_event_url_with_expected_state\n"
        "test_apply_calendar_change_clears_event_url_with_expected_state\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_event_url\n"
        "test_apply_calendar_change_clears_selected_recurring_occurrence_event_url\n"
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_mismatch_fails_unknown\n"
        "test_apply_calendar_change_replaces_selected_recurring_occurrence_event_url\n"
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_preserves_adjacent_url\n"
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_refuses_stale_adjacent_url\n"
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_clear_mismatch_fails_unknown\n"
        "test_apply_calendar_change_selected_recurring_occurrence_adjacent_event_url_mismatch_fails_unknown\n"
        "test_apply_calendar_change_clears_recurrence_with_series_proof\n"
        "test_apply_calendar_change_clear_recurrence_requires_proof_read_back\n"
        "test_apply_calendar_change_flags_event_url_read_back_mismatch\n"
        "test_apply_calendar_change_flags_event_url_clear_read_back_mismatch\n"
        "test_apply_calendar_change_flags_event_url_clear_missing_absence_proof\n"
        "test_get_calendar_event_returns_url_hash_proof_without_raw_url\n"
        "test_plan_calendar_change_delete_recurring_scope_binds_preview_and_token\n"
        "test_apply_calendar_change_deletes_recurring_occurrence_and_binds_scope\n"
        "test_apply_calendar_change_deletes_future_recurring_span_and_binds_scope\n"
        "test_apply_calendar_change_requires_span_proof_for_future_recurring_delete\n"
        "test_apply_calendar_change_rejects_unscoped_recurring_delete\n"
        "test_apply_calendar_change_rejects_scoped_nonrecurring_delete\n"
        "event_url_read_back_mismatch\n"
        "event_url_clear_requested\n"
        "event_url_clear_read_back_mismatch\n"
        "test_plan_calendar_change_delete_rejects_recurrence\n"
        "test_plan_calendar_change_rejects_mixed_alarm_modes\n"
        "test_plan_calendar_change_rejects_invalid_alarm_offsets\n"
        "test_apply_calendar_change_creates_alarm_offsets_and_reads_back\n"
        "test_apply_calendar_change_creates_absolute_alarm_and_reads_back\n"
        "test_apply_calendar_change_creates_recurring_event_and_reads_back\n"
        "test_apply_calendar_change_creates_unbounded_recurrence_and_reads_back\n"
        "test_apply_calendar_change_creates_monthly_weekday_recurrence_and_reads_back\n"
        "test_apply_calendar_change_creates_monthly_month_day_recurrence_and_reads_back\n"
        "test_apply_calendar_change_creates_monthly_nth_weekday_recurrence_and_reads_back\n"
        "test_apply_calendar_change_creates_yearly_month_recurrence_and_reads_back\n"
        "test_apply_calendar_change_creates_weekly_weekday_recurrence_and_reads_back\n"
        "test_apply_calendar_change_updates_recurrence_and_reads_back\n"
        "test_apply_calendar_change_updates_unbounded_recurrence_and_reads_back\n"
        "test_apply_calendar_change_replaces_mid_series_recurrence_with_unbounded_rule\n"
        "test_apply_calendar_change_updates_monthly_weekday_recurrence_and_reads_back\n"
        "test_apply_calendar_change_updates_monthly_nth_weekday_recurrence_and_reads_back\n"
        "test_apply_calendar_change_updates_yearly_month_recurrence_and_reads_back\n"
        "test_plan_calendar_change_create_set_positions_recurrence_binds_preview\n"
        "test_apply_calendar_change_creates_set_positions_recurrence_and_reads_back\n"
        "test_apply_calendar_change_updates_set_positions_recurrence_and_reads_back\n"
        "test_plan_calendar_change_set_positions_requires_recurrence_selector\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_scalars\n"
        "test_apply_calendar_change_reschedules_selected_recurring_occurrence\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_alarm_offsets\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_absolute_alarm\n"
        "test_apply_calendar_change_clears_selected_recurring_occurrence_alarm_offsets\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_alarm_preserves_adjacent_alarm_state\n"
        "test_apply_calendar_change_selected_recurring_occurrence_adjacent_alarm_read_back_mismatch_is_unknown\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_audio_alarm\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_email_alarm_without_echo\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_geofence_alarm\n"
        "test_apply_calendar_change_selected_recurring_occurrence_clears_email_action_to_display_alarm\n"
        "test_apply_calendar_change_selected_recurring_occurrence_clears_geofence_action\n"
        "test_apply_calendar_change_selected_recurring_occurrence_action_alarm_read_back_mismatch_is_unknown\n"
        "selected_occurrence_rescheduled_verified\n"
        "original_occurrence_verified_absent\n"
        "selectedReadBackStartDate\n"
        "originalRemaining\n"
        "test_apply_calendar_change_update_recurrence_requires_matching_read_back\n"
        "test_apply_calendar_change_creates_date_only_event_and_binds_all_day\n"
        "test_apply_calendar_change_updates_date_only_event_and_binds_expected_all_day\n"
        "test_apply_calendar_change_deletes_date_only_event_and_binds_expected_all_day\n"
        "test_apply_calendar_change_updates_alarm_offsets_and_binds_expected_state\n"
        "test_apply_calendar_change_deletes_event_and_binds_expected_alarm_offsets\n"
        "test_apply_calendar_change_deletes_event_and_binds_expected_absolute_alarm\n"
        "test_eventkit_bounded_calendar_mutation_binds_alarm_offsets\n"
        "test_plan_calendar_change_create_time_zone_binds_preview\n"
        "test_plan_calendar_change_rejects_invalid_time_zone\n"
        "test_plan_calendar_change_rejects_path_like_time_zones\n"
        "test_plan_calendar_change_rejects_path_like_expected_time_zones_for_update\n"
        "test_plan_calendar_change_rejects_path_like_expected_time_zones_for_delete\n"
        "test_plan_calendar_change_rejects_time_zone_for_all_day\n"
        "test_plan_calendar_change_update_binds_time_zone_expected_state\n"
        "test_apply_calendar_change_creates_timed_event_with_time_zone\n"
        "test_apply_calendar_change_updates_timed_event_with_time_zone_binding\n"
        "test_search_calendar_calendars_returns_metadata_only_and_default\n"
        "test_get_calendar_calendar_returns_exact_metadata\n"
        "test_apply_calendar_change_creates_event_with_exact_calendar_handle\n"
        "test_apply_calendar_change_moves_event_to_exact_calendar_handle\n"
        "test_plan_calendar_change_create_with_default_calendar_binds_exact_target\n"
        "test_plan_calendar_change_create_default_calendar_requires_single_default\n"
        "test_apply_calendar_change_creates_event_with_default_calendar_target\n"
        "test_apply_calendar_change_default_calendar_apply_uses_bound_handle\n"
        "test_apply_calendar_change_rejects_default_calendar_apply_without_eventkit\n"
        "test_eventkit_calendar_target_selection_uses_public_eventkit_apis\n"
        "test_plan_calendar_calendar_create_binds_source_calendar_handle\n"
        "test_apply_calendar_calendar_create_requires_matching_token_and_reads_back\n"
        "test_apply_calendar_calendar_rename_reads_back_title\n"
        "test_plan_calendar_calendar_delete_requires_synthetic_empty_calendar\n"
        "test_plan_calendar_calendar_delete_refuses_mixed_event_reminder_calendar\n"
        "test_plan_calendar_calendar_delete_refuses_missing_entity_type_proof\n"
        "test_apply_calendar_calendar_delete_reads_back_absence\n"
        "test_plan_calendar_change_create_email_alarm_hashes_without_echo\n"
        "test_plan_calendar_change_rejects_email_alarm_without_trigger\n"
        "test_plan_calendar_change_rejects_email_alarm_conflicts\n"
        "test_apply_calendar_change_creates_email_alarm_and_reads_back_without_echo\n"
        "state.offsets == nil\n"
        "state.absoluteDates == nil\n"
        "state.emailAddressSHA256 == nil\n"
        "currentAlarmOffsetsMinutes == expectedAlarmOffsetsMinutes\n"
        "currentAlarmAbsoluteDates == expectedAlarmAbsoluteDates\n"
        "currentAlarmEmailAddressSHA256 == expectedAlarmEmailAddressSHA256\n"
        "dateStringArrayValue(request, \"expected_alarm_absolute_dates\")\n"
        "alarmEmailAddressValue(request, \"alarm_email_address\")\n"
        "expected_alarm_email_address_sha256\n"
        "alarm.emailAddress = emailAddress\n"
        "applyAlarms(event, offsets: proposedAlarmOffsetsMinutes, absoluteDates: proposedAlarmAbsoluteDates, soundName: proposedAlarmSoundName, emailAddress: proposedAlarmEmailAddress, proximity: proposedAlarmProximity, structuredLocation: proposedAlarmStructuredLocation)\n"
        '"time_zone" not in event\n'
        "includeTimeZone: Bool = false\n"
        'payload["time_zone"] = eventTimeZoneIdentifier(event)\n'
        "eventTimeZoneIdentifier(event) == expectedTimeZone\n"
        "event.timeZone = proposedTimeZone\n"
        "EKRecurrenceRule(recurrenceWith: frequency, interval: interval, end: end)\n"
        "EKRecurrenceEnd(occurrenceCount: count)\n"
        "EKRecurrenceEnd(end: endDate)\n"
        "recurrence_end_date\n"
        "recurrence_unbounded\n"
        '"unbounded": True\n'
        "event.recurrenceRules = [\n"
        "recurrenceRequest(request)\n"
        "recurrenceUpdateRequested\n"
        "recurrenceMatches(event, proposedRecurrence)\n"
        "recurrenceWeekdaysPayload\n"
        "recurrenceMonthDaysPayload\n"
        "recurrenceMonthWeekdaysPayload\n"
        "monthWeekdayArrayValue\n"
        "EKRecurrenceDayOfWeek\n"
        "daysOfTheWeek: weekdays\n"
        "daysOfTheWeek: monthWeekdays\n"
        "daysOfTheMonth: monthDays.map\n"
        "applyRecurrence(event, recurrence: proposedRecurrence)\n"
        "event.url = nil\n"
        "unsupported_recurrence_for_operation\n"
        "recurrence_delete_scope\n"
        "expected_recurrence_present\n"
        "unsupported_recurrence_delete_scope\n"
        "recurrenceDeleteScope == \"this_event\"\n"
        "recurrenceDeleteScope == \"future_events\"\n"
        ".futureEvents\n"
        "try store.remove(event, span: .thisEvent, commit: true)\n"
        "expected_all_day\n"
        "expected_alarm_offsets_minutes\n",
        encoding="utf-8",
    )
    (root / "tests/test_mail_content.py").write_text(
        "test_mail_search_returns_hashed_account_ref_and_no_raw_account_id\n"
        "test_apply_mail_change_move_message_uses_exact_same_account_mailbox\n"
        "test_plan_mail_change_move_message_allows_exact_cross_account_mailbox\n"
        "test_apply_mail_change_move_message_uses_exact_cross_account_mailbox\n"
        "test_plan_mail_change_move_message_refuses_trash_like_target\n"
        "test_apply_mail_change_move_message_refuses_stale_target_mailbox\n"
        "test_mail_sender_search_does_not_match_hidden_email_or_full_name\n"
        "test_apply_mail_change_create_draft_refuses_ambiguous_new_sender_matches\n"
        "test_apply_mail_change_create_draft_refuses_saturated_sender_read_back\n"
        "target_account_relation\n"
        "source_account_ref\n"
        "target_account_ref\n"
        "stale_mailbox_target\n",
        encoding="utf-8",
    )


def _write_surface_contract_files(root: Path) -> None:
    root.joinpath("src/local_apple_data/adapters").mkdir(parents=True, exist_ok=True)
    (root / "src/local_apple_data/adapters/icloud_drive.py").write_text(
        'PLAN_OPERATIONS = {"create_text", "append_text", "replace_text", "create_folder", "create_folder_path", "rename_folder", "trash_folder", "delete_folder", "move_folder", "copy_folder", "trash_text", "delete_text", "rename_text", "copy_text", "move_text", "rename_file", "copy_file", "move_file", "import_file", "replace_file", "trash_file", "delete_file"}\n',
        encoding="utf-8",
    )
    (root / "src/local_apple_data/adapters/filesystem.py").write_text(
        'PLAN_OPERATIONS = {"create_text", "append_text", "replace_text", "create_folder", "create_folder_path", "rename_folder", "trash_folder", "delete_folder", "move_folder", "copy_folder", "trash_text", "delete_text", "rename_text", "copy_text", "move_text", "rename_file", "copy_file", "move_file", "import_file", "replace_file", "trash_file", "delete_file"}\n',
        encoding="utf-8",
    )
    adapter_contracts = {
        "calendar.py": (
            'PLAN_OPERATIONS = {"create", "update", "delete"}\n'
            'RECURRENCE_FREQUENCIES = {"daily", "weekly", "monthly", "yearly"}\n'
            "DATE_ONLY_PATTERN\n"
            "_date_only_pair_warning\n"
            "MAX_RECURRENCE_INTERVAL\n"
            "MIN_RECURRENCE_OCCURRENCES\n"
            "MAX_RECURRENCE_OCCURRENCES\n"
            "MAX_RECURRENCE_END_DAYS\n"
            "_normalize_recurrence_end_date\n"
            "_resolve_default_calendar_for_plan\n"
            "default_calendar_plan_only\n"
            '"default_calendar_resolution"\n'
            "apply_with_calendar_handle\n"
            "unsupported_default_calendar_for_operation\n"
            "RECURRENCE_WEEKDAY_ALIASES\n"
            "_normalize_recurrence_weekdays\n"
            "_normalize_recurrence_month_days\n"
            "_normalize_recurrence_month_weekdays\n"
            "_normalize_recurrence_year_months\n"
            "_normalize_recurrence_signed_ints\n"
            "_normalize_structured_location\n"
            "_normalize_recurrence\n"
            "unsupported_recurrence_for_operation\n"
            "invalid_recurrence\n"
            "# recurrence_weekdays is supported only for weekly recurrence, monthly recurrence, or yearly recurrence with recurrence_year_weeks.\n"
            "# recurrence_year_weeks requires recurrence_weekdays to bind exact weekdays inside the selected weeks.\n"
            "# Use recurrence_weekdays, recurrence_month_days, or recurrence_month_weekdays for monthly recurrence, not more than one.\n"
            "# recurrence_month_days is supported only when recurrence_frequency is monthly.\n"
            "# recurrence_month_weekdays is supported only when recurrence_frequency is monthly.\n"
            "# recurrence_year_months is supported only when recurrence_frequency is yearly.\n"
            "# recurrence_year_month_days is supported only when recurrence_frequency is yearly.\n"
            "# recurrence_year_month_days requires recurrence_year_months to bind exact months.\n"
            "# recurrence_year_month_weekdays is supported only when recurrence_frequency is yearly.\n"
            "# recurrence_year_month_weekdays requires recurrence_year_months to bind exact months.\n"
            "# recurrence_year_days is supported only when recurrence_frequency is yearly.\n"
            "# recurrence_year_weeks is supported only when recurrence_frequency is yearly.\n"
            "# recurrence_set_positions requires another recurrence selector\n"
            '# recurrence["weekdays"] = normalized_weekdays\n'
            '# recurrence["month_days"] = normalized_month_days\n'
            '# recurrence["month_weekdays"] = normalized_month_weekdays\n'
            '# recurrence["year_months"] = normalized_year_months\n'
            '# recurrence["year_month_days"] = normalized_year_month_days\n'
            '# recurrence["year_month_weekdays"] = normalized_year_month_weekdays\n'
            '# recurrence["year_days"] = normalized_year_days\n'
            '# recurrence["year_weeks"] = normalized_year_weeks\n'
            '# recurrence["set_positions"] = normalized_set_positions\n'
            '# recurrence["end_date"] = normalized_end_date\n'
            "recurrence_end_date\n"
            '# "recurrence": normalized_recurrence\n'
            '# "recurrence_present": bool(\n'
            '# "structured_location": normalized_structured_location\n'
            "clear_structured_location\n"
            '# "structured_location_clear_requested"\n'
            "structured_location_cleared_verified\n"
            "structured_location_clear_read_back_mismatch\n"
            "structured_location_read_back_mismatch\n"
            "_normalize_alarm_email_address\n"
            '"alarm_email_address_sha256"\n'
            "alarm_email_read_back_mismatch\n"
            "alarm_email_address_sha256_verified\n"
            'CALENDAR_MANAGEMENT_OPERATIONS = {"create_calendar", "rename_calendar", "delete_calendar"}\n'
        ),
        "contacts.py": 'PLAN_OPERATIONS = {"create", "update", "append_note", "set_note", "replace_note", "overwrite_note", "clear_note", "delete_note", "merge_note", "add_group_member", "remove_group_member", "create_group", "rename_group", "delete_group", "batch", "delete"}\n',
        "mail.py": 'PLAN_OPERATIONS = {"create_draft", "send_message", "reply_message", "reply_all_message", "forward_message", "mark_read", "mark_unread", "flag_message", "unflag_message", "archive_message", "trash_message", "move_message"}\n',
        "messages.py": 'PLAN_OPERATIONS = {"send_text", "send_file"}\n',
        "notes.py": (
            'PLAN_OPERATIONS = {"create", "create_folder", "rename_folder", "delete_folder", "move_folder", "append_text", "replace_text", "move_to_folder", "delete"}\n'
            '"create_folder"\n'
            '"rename_folder"\n'
            '"delete_folder"\n'
            '"move_folder"\n'
            "_apply_notes_create_folder\n"
            "_apply_notes_rename_folder\n"
            "_apply_notes_delete_folder\n"
            "_apply_notes_move_folder\n"
            "_notes_create_folder_script\n"
            "_notes_rename_folder_script\n"
            "_notes_delete_folder_script\n"
            "_notes_move_folder_script\n"
            "_notes_folder_rename_read_back\n"
            "_notes_folder_delete_read_back\n"
            "_notes_folder_move_read_back\n"
            "_folder_delete_safety_warning\n"
            "_folder_move_safety_warning\n"
            "_resolve_folder_move_plan_target\n"
            "_find_matching_child_folder\n"
            "_created_folder_row_has_expected_identity\n"
            "SQL_SMART_FILTER = \"COALESCE(f.ZSMARTFOLDERQUERYJSON, '') = ''\"\n"
            "parent_folder_confirmed\n"
            "folder_content_returned\n"
            "note_content_returned\n"
        ),
        "photos.py": 'PLAN_OPERATIONS = {"import", "update_flags", "delete", "add_to_album", "remove_from_album", "create_album", "rename_album", "delete_album"}\n',
        "reminders.py": (
            'PLAN_OPERATIONS = {"create", "create_with_start_date", "create_with_recurrence", "complete", "uncomplete", "update_due_date", "update_start_date", "update_recurrence", "update_title", "update_notes", "update_priority", "update_url", "clear_url", "set_absolute_display_alarm", "set_relative_display_alarm", "set_mixed_display_alarm", "clear_display_alarm", "move_to_list", "delete"}\n'
            "create_with_start_date\n"
            "create_with_recurrence\n"
            "update_start_date\n"
            "update_recurrence\n"
            "START_DATE_OPERATIONS\n"
            "RECURRENCE_OPERATIONS\n"
            "_normalize_start_date\n"
            "_normalize_recurrence\n"
            "expected_start_date\n"
            "start_date_verified\n"
            "start_date_absent_verified\n"
            "start_date_read_back_mismatch\n"
            "recurrence_verified\n"
            "recurrence_cleared_verified\n"
            "recurrence_read_back_mismatch\n"
            "stale_recurrence_state\n"
            'LIST_MANAGEMENT_OPERATIONS = {"create_list", "rename_list", "delete_list", "delete_list_with_migration"}\n'
            "delete_list_with_migration\n"
            "MAX_REMINDER_LIST_MIGRATION_COUNT\n"
            "target_count_after\n"
            "list_migrated_verified\n"
            "source_list_empty_verified\n"
            "MAX_REMINDER_ALARMS\n"
            "ALARM_OPERATIONS\n"
            "SAFE_REMINDER_URL_SCHEMES\n"
            "expected_url_present\n"
            "expected_url_sha256\n"
            "url_safe_sha256\n"
            "url_verified\n"
            "url_absent_verified\n"
            "url_read_back_mismatch\n"
            "url_raw_returned\n"
            "alarm_absolute_dates\n"
            "alarm_offsets_minutes\n"
            "_normalize_alarm_offsets\n"
            "expected_alarms_count\n"
            "expected_alarms_sha256\n"
            "alarms_safe_sha256\n"
            "display_alarm_verified\n"
            "display_alarm_cleared_verified\n"
            "alarm_state_raw_returned\n"
            "_normalize_reminder_list_title\n"
            "plan_reminder_list_change\n"
            "apply_reminder_list_change\n"
            "create_list\n"
            "rename_list\n"
            "delete_list\n"
            "EVENTKIT_REMINDER_LIST_HANDLE_PREFIX\n"
            "LIST_TARGET_OPERATIONS\n"
            "search_reminder_lists\n"
            "get_reminder_list\n"
            "_eventkit_reminder_lists_response\n"
            "_eventkit_reminder_list_metadata\n"
            "_resolve_eventkit_list_id\n"
            "move_to_list\n"
            "target_list_handle\n"
            "target_list_title\n"
            "expected_list_name\n"
            "target_list_not_found\n"
            "read_back_target_mismatch\n"
        ),
        "shortcuts.py": 'PLAN_OPERATIONS = {"run"}\n',
    }
    for filename, text in adapter_contracts.items():
        (root / "src/local_apple_data/adapters" / filename).write_text(
            text,
            encoding="utf-8",
        )

    tools = list(surface_contract.CORE_MCP_TOOLS)
    for contract in surface_contract.SURFACE_CONTRACTS:
        tools.extend(contract.mcp_tools)
    mcp_lines = [
        "from typing import Literal",
        "from mcp.server.fastmcp import FastMCP",
        f"ICloudDriveOperation = Literal[{_literal_values('ICloudDriveOperation')}]",
        f"FilesystemOperation = Literal[{_literal_values('FilesystemOperation')}]",
        'ICLOUD_DRIVE_IMPORT_FILE_SOURCE_FIELD = "source_file"',
        "READ_ONLY_ANNOTATIONS = object()",
        "WRITE_ANNOTATIONS = object()",
        "DESTRUCTIVE_WRITE_ANNOTATIONS = object()",
        'INSTRUCTIONS = "'
        + mutation_gate.CONTACTS_NOTE_FAIL_CLOSED_CONTRACT
        + ' The only apply-capable mutation surfaces are '
        + mutation_gate.CANONICAL_APPLY_SURFACE_SUMMARY
        + ', each with a matching plan approval token and explicit confirmation."',
        'mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)',
    ]
    destructive_tools = {
        "calendar_apply_calendar_change",
        "calendar_apply_change",
        "contacts_apply_change",
        "filesystem_apply_change",
        "icloud_drive_apply_change",
        "mail_apply_change",
        "mail_apply_cleanup",
        "mail_apply_mailbox_change",
        "mail_delete_template",
        "notes_apply_change",
        "photos_apply_change",
        "reminders_apply_list_change",
        "reminders_apply_change",
        "shortcuts_apply_run",
    }
    for tool in tools:
        write_tools = {
            "calendar_apply_calendar_change",
            "calendar_apply_change",
            "contacts_apply_change",
            "filesystem_apply_change",
            "icloud_drive_apply_change",
            "mail_apply_change",
            "mail_apply_cleanup",
            "mail_apply_mailbox_change",
            "messages_apply_change",
            "notes_apply_change",
            "photos_apply_change",
            "reminders_apply_list_change",
            "reminders_apply_change",
            "shortcuts_apply_run",
        }
        if tool in destructive_tools:
            annotation = "DESTRUCTIVE_WRITE_ANNOTATIONS"
        elif tool in write_tools or tool in mutation_gate.APPROVED_LOCAL_CACHE_WRITE_MCP_TOOLS:
            annotation = "WRITE_ANNOTATIONS"
        else:
            annotation = "READ_ONLY_ANNOTATIONS"
        mcp_lines.extend(
            [
                f"@mcp.tool(annotations={annotation})",
                f"def {tool}() -> dict:",
                "    return {}",
                "",
            ]
        )
    (root / "src/local_apple_data/mcp_server.py").write_text(
        "\n".join(mcp_lines) + "\n",
        encoding="utf-8",
    )

    cli_lines = [
        "def _health_command(args):",
        "    return 0",
        "",
        "_icloud_drive_root_override_allowed = object()",
        'LOCAL_APPLE_DATA_ALLOW_TEST_ROOT = "1"',
        'unsupported_test_root = "unsupported_test_root"',
        "",
        "def build_parser():",
        "    import argparse",
        "    parser = argparse.ArgumentParser()",
        "    subparsers = parser.add_subparsers()",
    ]
    for command in surface_contract.CORE_CLI_COMMANDS:
        cli_lines.append(f'    subparsers.add_parser("{command}")')
    for contract in surface_contract.SURFACE_CONTRACTS:
        cli_lines.extend(
            [
                f'    {contract.name} = subparsers.add_parser("{contract.cli_group}")',
                f"    {contract.cli_subparser} = {contract.name}.add_subparsers()",
            ]
        )
        for command in contract.cli_commands:
            cli_lines.append(f'    {contract.cli_subparser}.add_parser("{command}")')
    cli_lines.append("    return parser")
    cli_lines.extend(_cli_operation_choice_lines())
    cli_lines.append('choices=["daily", "weekly", "monthly", "yearly"]')
    cli_lines.append('choices=["daily", "weekly", "monthly", "yearly"]')
    cli_lines.append("_calendar_recurrence_set_positions_arg")
    cli_lines.append("--event-url")
    cli_lines.append("--recurrence-set-positions")
    cli_lines.append("--expected-event-url-present")
    cli_lines.append("--expected-event-url-sha256")
    cli_lines.append("--source-file")
    cli_lines.append("--alarm-email-address")
    cli_lines.append("--expected-alarm-email-address-sha256")
    cli_lines.append("--recurrence-end-date")
    cli_lines.append("--recurrence-unbounded")
    cli_lines.append("--clear-structured-location")
    cli_lines.append("_calendar_structured_location_arg")
    cli_lines.append("_calendar_recurrence_year_months_arg")
    cli_lines.append("_calendar_recurrence_year_month_days_arg")
    cli_lines.append("_calendar_recurrence_year_days_arg")
    cli_lines.append("_calendar_recurrence_year_weeks_arg")
    cli_lines.append("--recurrence-year-months")
    cli_lines.append("--recurrence-year-month-days")
    cli_lines.append("--recurrence-year-days")
    cli_lines.append("--recurrence-year-weeks")
    (root / "src/local_apple_data/cli.py").write_text(
        "\n".join(cli_lines) + "\n",
        encoding="utf-8",
    )

    surface_names = [contract.name for contract in surface_contract.SURFACE_CONTRACTS]
    access_lines = ",\n".join(f'    {{"surface": "{surface}"}}' for surface in surface_names)
    summary_lines = ",\n".join(f'        "{surface}": {{}}' for surface in surface_names)
    (root / "src/local_apple_data/health.py").write_text(
        f"""
ACCESS_REQUIREMENTS = [
{access_lines}
]


def _surface_summary():
    return {{
{summary_lines}
    }}
""".lstrip(),
        encoding="utf-8",
    )

    matrix_lines = [
        "# Capability Matrix",
        "",
        "| Surface | Local source | Search/list support | Exact detail support | Write support | Permissions | Current limits |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for contract in surface_contract.SURFACE_CONTRACTS:
        matrix_lines.append(
            f"| {contract.label} | Synthetic | Search | Detail | Not implemented | Local | Synthetic |"
        )
    (root / "docs/CAPABILITY_MATRIX.md").write_text(
        "\n".join(matrix_lines)
        + "\n"
        + "docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md\n"
        + "docs/V1_68_ICLOUD_DRIVE_DELETE_TEXT_WRITE_DESIGN.md\n"
        + "docs/V1_127_ICLOUD_DRIVE_REGULAR_FILE_RENAME_COPY_MOVE_WRITE_DESIGN.md\n"
        + "docs/V1_129_ICLOUD_DRIVE_IMPORT_FILE_WRITE_DESIGN.md\n"
        + "docs/V1_130_ICLOUD_DRIVE_REPLACE_FILE_WRITE_DESIGN.md\n"
        + "docs/V1_131_ICLOUD_DRIVE_TRASH_FILE_WRITE_DESIGN.md\n"
        + "docs/V1_132_ICLOUD_DRIVE_DELETE_FILE_WRITE_DESIGN.md\n"
        + "delete-text requires exact supported text-file handle binding\n"
        + "rename-file/copy-file/move-file require exact non-text non-package regular-file handle binding\n"
        + "import-file requires exact target parent handle plus private source-file binding\n"
        + "replace-file requires exact non-text non-package regular-file handle plus private source-file binding\n"
        + "trash-file requires exact non-text non-package regular-file handle binding\n"
        + "delete-file requires exact non-text non-package regular-file handle binding\n"
        + "file permanent delete outside the exact delete-text or delete-file gates\n"
        + "Calendar v1.108-v1.175 gates are also current\n"
        + "`docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        + "`docs/V1_119_CALENDAR_SELECTED_OCCURRENCE_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        + "`docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`\n"
        + "`docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`\n"
        + "`docs/V1_124_CALENDAR_CALENDAR_MANAGEMENT_WRITE_DESIGN.md`\n"
        + "`docs/V1_126_CALENDAR_RECURRENCE_REPLACEMENT_WRITE_DESIGN.md`\n"
        + "`docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`\n"
        + "`docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`\n"
        + "`docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`\n"
        + "`docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`\n"
        + "`docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`\n"
        + "`docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        + "`docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`\n"
        + "`docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`\n"
        + "`docs/V1_175_CALENDAR_FUTURE_SERIES_CALENDAR_MOVE_WRITE_DESIGN.md`\n"
        + "future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update\n"
        + "future-series recurring-event title/plain-location/notes update\n"
        + "future-series recurring-event timed reschedule\n"
        + "Reminders exact URL update/clear is governed by `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`\n"
        + "Reminders exact absolute display-alarm set/clear is governed by `docs/V1_137_REMINDERS_ABSOLUTE_DISPLAY_ALARM_WRITE_DESIGN.md`\n"
        + "Reminders exact relative display-alarm set and broadened pure display-alarm clear is governed by `docs/V1_138_REMINDERS_RELATIVE_DISPLAY_ALARM_WRITE_DESIGN.md`\n",
        encoding="utf-8",
    )
    (root / "docs/MACOS_SUPPORT.md").write_text(
        "exact text-file create/append/replace/trash/delete/rename/copy/move\n"
        "exact regular-file rename/copy/move\n"
        "exact local regular-file import\n"
        "exact regular-file replace\n"
        "exact regular-file trash\n"
        "exact regular-file delete\n"
        "exact folder rename/trash/move/copy/delete\n"
        "does not permanently delete files outside the exact delete-text or delete-file gates\n"
        "mutate unbounded folder copy, recursive folder writes, or unbounded recursive folder delete\n",
        encoding="utf-8",
    )


def _write_design_doc_text() -> str:
    phrases = []
    for contract in write_design_gate.REQUIRED_DESIGN_DOCS.values():
        phrases.extend(contract["phrases"])
    for current_phrases in write_design_gate.REQUIRED_CURRENT_DOC_TEXT.values():
        phrases.extend(current_phrases)
    return "\n".join(str(phrase) for phrase in phrases) + "\n"


def _plugin_description() -> str:
    return (
        mutation_gate.CONTACTS_NOTE_FAIL_CLOSED_CONTRACT
        + " Local-first Apple data access with "
        + mutation_gate.REQUIRED_PLUGIN_DESCRIPTION_TEXT
    )


def _plugin_long_description() -> str:
    return " ".join(mutation_gate.REQUIRED_PLUGIN_LONG_DESCRIPTION_TEXT)


def _literal_values(name: str) -> str:
    return ", ".join(
        f'"{value}"' for value in sorted(mutation_gate.REQUIRED_MCP_OPERATION_LITERALS[name])
    )


def _cli_operation_choice_lines() -> list[str]:
    lines = [
        "",
        "class _AuditParser:",
        "    def add_argument(self, *args, **kwargs):",
        "        return None",
        "",
    ]
    for parser_name, choices in sorted(mutation_gate.REQUIRED_CLI_OPERATION_CHOICES.items()):
        choices_text = ", ".join(f'"{choice}"' for choice in sorted(choices))
        lines.extend(
            [
                f"{parser_name} = _AuditParser()",
                f'{parser_name}.add_argument("--operation", choices=[{choices_text}])',
                "",
            ]
        )
    return lines


def _init_and_commit_all(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=local-apple-data release test",
            "-c",
            "user.email=" + "release-test@" + "example.invalid",
            "commit",
            "-m",
            "Initial release fixture",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )


def test_required_files_cover_release_tooling_tests() -> None:
    expected = {
        "tests/test_build_public_release_tree.py",
        "tests/test_generate_release_receipt.py",
        "tests/test_messages_public_surface_audit.py",
        "tests/test_mutation_gate_audit.py",
        "tests/test_plugin_artifact_hygiene_audit.py",
        "tests/test_plugin_packaging.py",
        "tests/test_prepare_public_git_checkout.py",
        "tests/test_public_release_scan.py",
        "tests/test_redaction_scan_script.py",
        "tests/test_release_readiness_audit.py",
        "tests/test_render_mcp_client_config.py",
        "tests/test_surface_contract_audit.py",
        "tests/test_sync_personal_plugin.py",
        "tests/test_verify_cross_agent_sync.py",
        "tests/test_write_design_gate_audit.py",
    }

    assert expected <= set(audit_release_readiness.REQUIRED_FILES)


def test_required_files_include_all_write_design_contracts() -> None:
    expected = {
        str(contract["path"])
        for contract in write_design_gate.REQUIRED_DESIGN_DOCS.values()
    }

    assert expected <= set(audit_release_readiness.REQUIRED_FILES)


def test_required_files_include_source_ignore_file() -> None:
    assert ".gitignore" in audit_release_readiness.REQUIRED_FILES
    assert audit_release_readiness.REQUIRED_GITIGNORE_LINES == (".claude/", ".env", ".env.*")


def test_audit_fails_when_gitignore_policy_is_missing(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    root.joinpath(".gitignore").write_text(".DS_Store\n.venv/\n", encoding="utf-8")

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is False
    assert "gitignore_policy" in payload["blockers"]
    assert checks["gitignore_policy"]["status"] == "error"
    assert ".claude/" in checks["gitignore_policy"]["message"]


def test_audit_reports_local_ready_and_missing_remote(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["messages_public_surface_audit"]["status"] == "ok"
    assert "missing_git_remote" in payload["blockers"]


def test_audit_fails_when_messages_public_surface_drifts(tmp_path: Path, monkeypatch) -> None:
    root = _make_minimal_project(tmp_path)

    monkeypatch.setattr(
        audit_release_readiness,
        "audit_messages_public_surface",
        lambda: {
            "status": "error",
            "commands": ["delete", "login", "logout", "send"],
            "blocked_risky_operations": ["message delete"],
            "finding_count": 1,
            "findings": [
                {
                    "kind": "messages_unreviewed_public_command",
                    "name": "delete",
                    "message": "Messages exposes an unreviewed public scripting command.",
                }
            ],
        },
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is False
    assert payload["github_publication_ready"] is False
    assert checks["messages_public_surface_audit"] == {
        "message": "1 findings; first delete:messages_unreviewed_public_command",
        "name": "messages_public_surface_audit",
        "status": "error",
    }
    assert "messages_public_surface_audit" in payload["blockers"]


def test_git_remote_check_degrades_when_git_remote_times_out(
    tmp_path: Path, monkeypatch
) -> None:
    def fake_run(command, **kwargs):
        if command == ["git", "remote", "-v"]:
            raise subprocess.TimeoutExpired(command, 10)
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(audit_release_readiness.subprocess, "run", fake_run)

    check = audit_release_readiness._git_remote_check(tmp_path)

    assert check == audit_release_readiness.Check(
        "git_remote",
        "warning",
        "not a git checkout or git remote unavailable",
    )


def test_audit_fails_when_required_file_is_missing(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    root.joinpath("README.md").unlink()

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is False
    assert checks["required_files"]["status"] == "error"


def test_audit_redacts_required_file_read_errors(tmp_path: Path, monkeypatch) -> None:
    root = _make_minimal_project(tmp_path)
    readme = root / "README.md"
    original_read_bytes = Path.read_bytes

    def fake_read_bytes(path: Path) -> bytes:
        if path == readme:
            raise OSError("permission denied for /private/local/readme")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is False
    assert checks["required_files"]["status"] == "error"
    assert "README.md" in checks["required_files"]["message"]
    assert "permission denied" not in checks["required_files"]["message"]
    assert "/private/" not in checks["required_files"]["message"]


def test_audit_fails_when_git_worktree_is_dirty(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    readme = root.joinpath("README.md")
    readme.write_text(readme.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is False
    assert checks["git_worktree_clean"]["status"] == "error"
    assert "git_worktree_clean" in payload["blockers"]


def test_audit_fails_when_redaction_scan_finds_secret(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    alias = "synthetic_alias_42" + "@" + "icloud.com"
    root.joinpath("docs/INSTALL.md").write_text(f"alias={alias}\n", encoding="utf-8")

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is False
    assert checks["redaction_scan"]["status"] == "error"
    assert checks["redaction_scan"]["message"].endswith(":apple_private_alias")
    assert alias not in checks["redaction_scan"]["message"]
    assert "redaction_scan" in payload["blockers"]


def test_public_git_checkout_runtime_errors_are_redacted(tmp_path: Path, monkeypatch) -> None:
    def fake_prepare_public_git_checkout(*args, **kwargs):
        raise RuntimeError("git failed in /private/local/public-checkout")

    monkeypatch.setattr(
        audit_release_readiness,
        "prepare_public_git_checkout",
        fake_prepare_public_git_checkout,
    )

    check = audit_release_readiness._public_git_checkout_check(tmp_path)

    assert check == audit_release_readiness.Check(
        "public_git_checkout",
        "error",
        "public checkout failed: RuntimeError",
    )


def test_public_git_checkout_value_errors_are_redacted(tmp_path: Path, monkeypatch) -> None:
    def fake_prepare_public_git_checkout(*args, **kwargs):
        raise ValueError("bad source path /private/local/public-checkout")

    monkeypatch.setattr(
        audit_release_readiness,
        "prepare_public_git_checkout",
        fake_prepare_public_git_checkout,
    )

    check = audit_release_readiness._public_git_checkout_check(tmp_path)

    assert check == audit_release_readiness.Check(
        "public_git_checkout",
        "error",
        "public checkout failed: ValueError",
    )


def test_public_git_checkout_os_errors_are_redacted(tmp_path: Path, monkeypatch) -> None:
    def fake_prepare_public_git_checkout(*args, **kwargs):
        raise OSError("permission denied for /private/local/public-checkout")

    monkeypatch.setattr(
        audit_release_readiness,
        "prepare_public_git_checkout",
        fake_prepare_public_git_checkout,
    )

    check = audit_release_readiness._public_git_checkout_check(tmp_path)

    assert check == audit_release_readiness.Check(
        "public_git_checkout",
        "error",
        "public checkout failed: OSError",
    )


def _mark_origin_main_contains_head(root: Path) -> None:
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=root,
        check=True,
    )


def _head_sha(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _stub_live_ls_remote(
    monkeypatch,
    *,
    stdout: str,
    returncode: int = 0,
    visibility: str = "PUBLIC",
    gh_returncode: int = 0,
    capture: dict[str, object] | None = None,
) -> None:
    real_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        if list(command[:3]) == ["gh", "repo", "view"]:
            if capture is not None:
                capture["gh_env"] = kwargs.get("env", {})
            return subprocess.CompletedProcess(
                command,
                gh_returncode,
                stdout=f"{visibility}\n" if gh_returncode == 0 else "",
                stderr="" if gh_returncode == 0 else "synthetic gh failure",
            )
        if list(command[:4]) == ["git", "ls-remote", "--heads", "--tags"]:
            if capture is not None:
                capture["ls_remote_env"] = kwargs.get("env", {})
            return subprocess.CompletedProcess(
                command,
                returncode,
                stdout=stdout,
                stderr="" if returncode == 0 else "synthetic ls-remote failure",
            )
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(audit_release_readiness.subprocess, "run", fake_run)


def test_audit_reports_github_ready_when_live_remote_advertises_head(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )
    capture: dict[str, object] = {}
    _stub_live_ls_remote(
        monkeypatch,
        stdout=f"{_head_sha(root)}\trefs/heads/main\n",
        capture=capture,
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is True
    assert payload["project_root"] == "<redacted>"
    assert str(root) not in json.dumps(payload)
    assert checks["git_publication_sync"] == {
        "message": "current HEAD is advertised by origin",
        "name": "git_publication_sync",
        "status": "ok",
    }
    assert capture["gh_env"]["GH_PROMPT_DISABLED"] == "1"  # type: ignore[index]
    assert capture["ls_remote_env"]["GIT_TERMINAL_PROMPT"] == "0"  # type: ignore[index]
    assert "BatchMode=yes" in capture["ls_remote_env"]["GIT_SSH_COMMAND"]  # type: ignore[index]
    assert "missing_git_remote" not in payload["blockers"]
    assert "unpublished_git_commit" not in payload["blockers"]


def test_audit_rejects_unpublished_head_for_github_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )
    _stub_live_ls_remote(
        monkeypatch,
        stdout="0" * 40 + "\trefs/heads/main\n",
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_remote"]["status"] == "ok"
    assert checks["git_publication_sync"] == {
        "message": "current HEAD was not advertised by live public GitHub remote refs",
        "name": "git_publication_sync",
        "status": "warning",
    }
    assert "missing_git_remote" not in payload["blockers"]
    assert "unpublished_git_commit" in payload["blockers"]


def test_require_github_ready_cli_rejects_unpublished_head(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )
    _stub_live_ls_remote(monkeypatch, stdout="")

    status = audit_release_readiness.main(
        ["--project-root", str(root), "--require-github-ready", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert status == 1
    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert "unpublished_git_commit" in payload["blockers"]


def test_audit_ignores_forged_remote_tracking_ref_without_live_remote_proof(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )
    _mark_origin_main_contains_head(root)
    _stub_live_ls_remote(monkeypatch, stdout="")

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_publication_sync"] == {
        "message": "current HEAD was not advertised by live public GitHub remote refs",
        "name": "git_publication_sync",
        "status": "warning",
    }
    assert "unpublished_git_commit" in payload["blockers"]


def test_audit_rejects_private_github_remote_for_github_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example/private-release.git"],
        cwd=root,
        check=True,
    )
    _stub_live_ls_remote(
        monkeypatch,
        stdout=f"{_head_sha(root)}\trefs/heads/main\n",
        visibility="PRIVATE",
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_remote"] == {
        "message": "no publication-safe public GitHub remote configured",
        "name": "git_remote",
        "status": "warning",
    }
    assert "missing_git_remote" in payload["blockers"]


def test_audit_rejects_unverified_github_visibility_for_github_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )
    _stub_live_ls_remote(
        monkeypatch,
        stdout=f"{_head_sha(root)}\trefs/heads/main\n",
        gh_returncode=1,
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_remote"] == {
        "message": "GitHub remote public visibility could not be verified",
        "name": "git_remote",
        "status": "warning",
    }
    assert "missing_git_remote" in payload["blockers"]


def test_audit_reports_remote_unavailable_separately_from_unpublished_head(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )
    _stub_live_ls_remote(monkeypatch, stdout="", returncode=128)

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_remote"]["status"] == "ok"
    assert checks["git_publication_sync"] == {
        "message": "live public GitHub remote refs unavailable for publication sync check",
        "name": "git_publication_sync",
        "status": "warning",
    }
    assert "github_remote_unavailable" in payload["blockers"]
    assert "unpublished_git_commit" not in payload["blockers"]


def test_audit_rejects_safe_non_github_remote_for_github_ready(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://gitlab.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_remote"] == {
        "message": "no publication-safe GitHub remote configured",
        "name": "git_remote",
        "status": "warning",
    }
    assert "missing_git_remote" in payload["blockers"]


def test_audit_rejects_option_like_remote_name_for_github_ready(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "--",
            "-origin",
            "https://github.com/example/local-apple-data.git",
        ],
        cwd=root,
        check=True,
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_remote"] == {
        "message": "no publication-safe GitHub remote configured",
        "name": "git_remote",
        "status": "warning",
    }
    assert "missing_git_remote" in payload["blockers"]


def test_audit_rejects_local_path_remote_for_github_ready(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", str(tmp_path / "local-remote.git")],
        cwd=root,
        check=True,
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_remote"] == {
        "message": "no publication-safe GitHub remote configured",
        "name": "git_remote",
        "status": "warning",
    }
    assert "missing_git_remote" in payload["blockers"]


def test_audit_rejects_insecure_remote_for_github_ready(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "http://github.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_remote"]["status"] == "warning"
    assert "missing_git_remote" in payload["blockers"]


def test_audit_rejects_mixed_safe_fetch_unsafe_push_remote(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "set-url", "--push", "origin", str(tmp_path / "local-push.git")],
        cwd=root,
        check=True,
    )

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert checks["git_remote"]["status"] == "warning"
    assert "missing_git_remote" in payload["blockers"]


def test_audit_accepts_ssh_shorthand_remote_for_github_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example/local-apple-data.git"],
        cwd=root,
        check=True,
    )
    _stub_live_ls_remote(monkeypatch, stdout=f"{_head_sha(root)}\trefs/heads/main\n")

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is True
    assert checks["git_remote"] == {
        "message": "configured GitHub publication remotes: origin",
        "name": "git_remote",
        "status": "ok",
    }
    assert "missing_git_remote" not in payload["blockers"]


def test_audit_accepts_case_insensitive_github_shorthand_host(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _make_minimal_project(tmp_path)
    _init_and_commit_all(root)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@GITHUB.com:example/local-apple-data.git"],
        cwd=root,
        check=True,
    )
    _stub_live_ls_remote(monkeypatch, stdout=f"{_head_sha(root)}\trefs/heads/main\n")

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["github_publication_ready"] is True
    assert checks["git_remote"]["status"] == "ok"
