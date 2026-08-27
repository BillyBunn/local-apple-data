#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HEADER_ROOT_CANDIDATES = [
    Path(
        "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/EventKit.framework/Headers"
    ),
    Path(
        "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/System/Library/Frameworks/EventKit.framework/Headers"
    ),
]


def _header_root() -> Path | None:
    for root in HEADER_ROOT_CANDIDATES:
        if root.exists():
            return root
    return None


def _read(root: Path, name: str) -> str:
    path = root / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def audit_calendar_public_surface(root: Path | None = None) -> dict[str, Any]:
    header_root = root or _header_root()
    if header_root is None:
        return {
            "status": "error",
            "finding_count": 1,
            "findings": [
                {
                    "code": "eventkit_headers_missing",
                    "message": "EventKit SDK headers were not found.",
                }
            ],
            "calendar_public_surface_reviewed": False,
        }

    event = _read(header_root, "EKEvent.h")
    event_store = _read(header_root, "EKEventStore.h")
    item = _read(header_root, "EKCalendarItem.h")
    alarm = _read(header_root, "EKAlarm.h")
    structured_location = _read(header_root, "EKStructuredLocation.h")
    recurrence_rule = _read(header_root, "EKRecurrenceRule.h")
    recurrence_end = _read(header_root, "EKRecurrenceEnd.h")
    recurrence_day_of_week = _read(header_root, "EKRecurrenceDayOfWeek.h")
    calendar = _read(header_root, "EKCalendar.h")
    source = _read(header_root, "EKSource.h")

    facts = {
        "attendees_readonly": "@property(nonatomic, readonly" in item and "*attendees" in item,
        "organizer_readonly": "@property(nonatomic, readonly" in event and "*organizer" in event,
        "availability_writable": "@property(nonatomic) EKEventAvailability" in event,
        "calendar_writable": "@property(nonatomic, strong" in item and "EKCalendar *calendar" in item,
        "time_zone_writable": "@property(nonatomic, copy, nullable) NSTimeZone *timeZone" in item,
        "recurrence_rules_writable": "@property(nonatomic, copy, nullable) NSArray<EKRecurrenceRule *> *recurrenceRules" in item,
        "url_writable": "@property(nonatomic, copy, nullable) NSURL *URL" in item,
        "event_structured_location_writable": "@property(nonatomic, copy, nullable) EKStructuredLocation *structuredLocation" in event,
        "alarm_structured_location_writable": "@property(nonatomic, copy, nullable) EKStructuredLocation" in alarm,
        "alarm_proximity_writable": "@property(nonatomic) EKAlarmProximity" in alarm,
        "email_alarm_writable": "@property(nonatomic, copy, nullable) NSString *emailAddress" in alarm,
        "audio_alarm_writable": "@property(nonatomic, copy, nullable) NSString *soundName" in alarm,
        "procedure_alarm_deprecated": "NS_DEPRECATED" in alarm and "NSURL *url" in alarm,
        "procedure_alarm_save_error_documented": "not possible to create new procedure alarms" in alarm,
        "structured_location_geo_writable": "CLLocation   *geoLocation" in structured_location,
        "structured_location_radius_writable": "double                radius" in structured_location,
        "recurrence_designated_initializer_present": "daysOfTheWeek" in recurrence_rule and "daysOfTheMonth" in recurrence_rule,
        "recurrence_rule_nullable_end_present": (
            "end:(nullable EKRecurrenceEnd *)end" in recurrence_rule
            and "@property(nonatomic, copy, nullable) EKRecurrenceEnd *recurrenceEnd" in recurrence_rule
        ),
        "recurrence_end_nil_unbounded_documented": (
            "set to never" in recurrence_end
            and "EKRecurrenceEnd set to nil" in recurrence_end
        ),
        "recurrence_end_date_present": "recurrenceEndWithEndDate" in recurrence_end and "endDate" in recurrence_end,
        "recurrence_weekdays_present": "daysOfTheWeek" in recurrence_rule,
        "recurrence_year_months_present": "monthsOfTheYear" in recurrence_rule,
        "recurrence_year_month_days_present": "daysOfTheMonth" in recurrence_rule,
        "recurrence_year_days_present": "daysOfTheYear" in recurrence_rule,
        "recurrence_year_weeks_present": "weeksOfTheYear" in recurrence_rule,
        "recurrence_set_positions_present": "setPositions" in recurrence_rule,
        "recurrence_set_positions_range_documented": (
            "setPositions" in recurrence_rule and "1 to 366" in recurrence_rule
        ),
        "recurrence_day_week_number_present": "weekNumber" in recurrence_day_of_week and "dayOfWeek:weekNumber:" in recurrence_day_of_week,
        "ekspan_this_event_present": "EKSpanThisEvent" in event_store,
        "save_event_span_commit_present": "saveEvent" in event_store and "span:(EKSpan)span" in event_store and "commit:(BOOL)commit" in event_store,
        "calendar_factory_present": "calendarForEntityType" in calendar and "eventStore" in calendar,
        "calendar_source_writable": "@property" in calendar and "strong" in calendar and "EKSource" in calendar and "*source" in calendar,
        "calendar_source_create_only_documented": (
            "only settable when initially creating a calendar" in calendar
            and "you cannot move it to another source" in calendar
        ),
        "calendar_identifier_lookup_present": "calendarWithIdentifier" in event_store,
        "calendar_save_present": "saveCalendar" in event_store and "commit:(BOOL)commit" in event_store,
        "calendar_remove_present": "removeCalendar" in event_store and "commit:(BOOL)commit" in event_store,
        "calendar_remove_deletes_events_documented": (
            "all of the events and reminders in the calendar" in event_store
            or "events in the calendar will be removed" in event_store
        ),
        "default_calendar_readonly": (
            "@property(nullable, nonatomic, readonly) EKCalendar *defaultCalendarForNewEvents"
            in event_store
        ),
        "source_identifier_readonly": "@property(nonatomic, readonly) NSString" in source and "sourceIdentifier" in source,
        "travel_time_property_present": "travelTime" in event or "travelTime" in item,
    }
    expected = {
        "attendees_readonly": True,
        "organizer_readonly": True,
        "availability_writable": True,
        "calendar_writable": True,
        "time_zone_writable": True,
        "recurrence_rules_writable": True,
        "url_writable": True,
        "event_structured_location_writable": True,
        "alarm_structured_location_writable": True,
        "alarm_proximity_writable": True,
        "email_alarm_writable": True,
        "audio_alarm_writable": True,
        "structured_location_geo_writable": True,
        "structured_location_radius_writable": True,
        "recurrence_designated_initializer_present": True,
        "recurrence_rule_nullable_end_present": True,
        "recurrence_end_nil_unbounded_documented": True,
        "recurrence_end_date_present": True,
        "recurrence_weekdays_present": True,
        "recurrence_year_months_present": True,
        "recurrence_year_month_days_present": True,
        "recurrence_year_days_present": True,
        "recurrence_year_weeks_present": True,
        "recurrence_set_positions_present": True,
        "recurrence_set_positions_range_documented": True,
        "recurrence_day_week_number_present": True,
        "ekspan_this_event_present": True,
        "save_event_span_commit_present": True,
        "calendar_factory_present": True,
        "calendar_source_writable": True,
        "calendar_source_create_only_documented": True,
        "calendar_identifier_lookup_present": True,
        "calendar_save_present": True,
        "calendar_remove_present": True,
        "calendar_remove_deletes_events_documented": True,
        "default_calendar_readonly": True,
        "source_identifier_readonly": True,
        "procedure_alarm_save_error_documented": True,
        "travel_time_property_present": False,
    }
    findings: list[dict[str, str]] = []
    for key, expected_value in expected.items():
        if facts[key] != expected_value:
            findings.append(
                {
                    "code": f"unexpected_{key}",
                    "message": f"Expected {key} to be {expected_value!r}.",
                }
            )

    blocked_risky_operations = [
        "attendee mutation",
        "invitation mutation",
        "organizer mutation",
        "travel time mutation",
        "procedure alarm mutation",
        "default calendar mutation",
        "calendar source/account mutation",
        "calendar delete without all-time emptiness proof",
    ]
    candidate_separate_gates: list[str] = []
    approved_public_write_properties = [
        "availability",
        "calendar",
        "time zone",
        "recurrence rules",
        "finite recurrence end date",
        "explicit unbounded recurrence",
        "monthly weekday recurrence",
        "monthly nth-weekday recurrence",
        "yearly month recurrence",
        "yearly month day-of-month recurrence",
        "yearly month nth-weekday recurrence",
        "yearly day-of-year recurrence",
        "yearly week-of-year recurrence",
        "selector-backed set-position recurrence",
        "selected recurring occurrence scalar update",
        "selected recurring occurrence timed reschedule",
        "selected recurring occurrence availability update",
        "selected recurring occurrence event URL set/clear",
        "selected recurring occurrence structured location set/clear",
        "synthetic calendar create/rename/delete",
        "event URL",
        "structured event location",
        "audio alarm",
        "email alarm",
        "structured geofence alarm",
    ]
    return {
        "status": "ok" if not findings else "error",
        "calendar_public_surface_reviewed": True,
        "header_root": str(header_root),
        "facts": facts,
        "blocked_risky_operations": blocked_risky_operations,
        "candidate_separate_gates": candidate_separate_gates,
        "approved_public_write_properties": approved_public_write_properties,
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args()
    result = audit_calendar_public_surface()
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result["status"])
        for finding in result["findings"]:
            print(f"- {finding['code']}: {finding['message']}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
