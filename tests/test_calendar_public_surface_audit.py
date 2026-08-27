from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/audit_calendar_public_surface.py"
SPEC = importlib.util.spec_from_file_location("audit_calendar_public_surface", SCRIPT_PATH)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
audit_calendar_public_surface = MODULE.audit_calendar_public_surface


def _write_headers(
    root: Path,
    *,
    travel_time: bool = False,
    attendees_readonly: bool = True,
    url_writable: bool = True,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "EKEvent.h").write_text(
        "\n".join(
            [
                "@property(nonatomic, copy, nullable) EKStructuredLocation *structuredLocation;",
                "@property(nonatomic, readonly, nullable) EKParticipant *organizer;",
                "@property(nonatomic) EKEventAvailability    availability;",
                "@property(nonatomic) NSTimeInterval travelTime;" if travel_time else "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "EKCalendarItem.h").write_text(
        "\n".join(
            [
                "@property(nonatomic, strong, null_unspecified) EKCalendar *calendar;",
                "@property(nonatomic, copy, nullable) NSURL *URL;" if url_writable else "",
                "@property(nonatomic, copy, nullable) NSTimeZone *timeZone  NS_AVAILABLE(10_8, 5_0);",
                "@property(nonatomic, copy, nullable) NSArray<EKRecurrenceRule *> *recurrenceRules NS_AVAILABLE(10_8, 5_0);",
                (
                    "@property(nonatomic, readonly, nullable) NSArray<__kindof EKParticipant *> *attendees;"
                    if attendees_readonly
                    else "@property(nonatomic, nullable) NSArray<__kindof EKParticipant *> *attendees;"
                ),
            ]
        ),
        encoding="utf-8",
    )
    (root / "EKEventStore.h").write_text(
        "@property(nullable, nonatomic, readonly) EKCalendar *defaultCalendarForNewEvents; "
        "typedef NS_ENUM(NSInteger, EKSpan) { EKSpanThisEvent }; "
        "- (nullable EKCalendar *)calendarWithIdentifier:(NSString *)identifier; "
        "- (BOOL)saveEvent:(EKEvent *)event span:(EKSpan)span commit:(BOOL)commit error:(NSError **)error; "
        "- (BOOL)saveCalendar:(EKCalendar *)calendar commit:(BOOL)commit error:(NSError **)error; "
        "- (BOOL)removeCalendar:(EKCalendar *)calendar commit:(BOOL)commit error:(NSError **)error; "
        "All events in the calendar will be removed.",
        encoding="utf-8",
    )
    (root / "EKCalendar.h").write_text(
        "\n".join(
            [
                "+ (EKCalendar *)calendarForEntityType:(EKEntityType)entityType eventStore:(EKEventStore *)eventStore;",
                "This is only settable when initially creating a calendar and then effectively read-only after that. That is, you can create a calendar, but you cannot move it to another source.",
                "@property(nonatomic, strong, null_unspecified) EKSource *source;",
            ]
        ),
        encoding="utf-8",
    )
    (root / "EKSource.h").write_text(
        "@property(nonatomic, readonly) NSString *sourceIdentifier;",
        encoding="utf-8",
    )
    (root / "EKAlarm.h").write_text(
        "\n".join(
            [
                "@property(nonatomic, copy, nullable) EKStructuredLocation   *structuredLocation;",
                "@property(nonatomic) EKAlarmProximity    proximity;",
                "@property(nonatomic, copy, nullable) NSString *emailAddress NS_AVAILABLE(10_8, NA);",
                "@property(nonatomic, copy, nullable) NSString *soundName NS_AVAILABLE(10_8, NA);",
                "Note: Starting with OS X 10.9, it is not possible to create new procedure alarms or view URLs for existing procedure alarms.",
                "@property(nonatomic, copy, nullable) NSURL *url NS_DEPRECATED(10_8, 10_9, NA, NA);",
            ]
        ),
        encoding="utf-8",
    )
    (root / "EKStructuredLocation.h").write_text(
        "\n".join(
            [
                "@property(nonatomic, strong, nullable) CLLocation   *geoLocation;",
                "@property(nonatomic) double                radius;",
            ]
        ),
        encoding="utf-8",
    )
    (root / "EKRecurrenceRule.h").write_text(
        "daysOfTheWeek daysOfTheMonth monthsOfTheYear weeksOfTheYear daysOfTheYear "
        "setPositions 1 to 366 "
        "- (instancetype)initRecurrenceWithFrequency:(EKRecurrenceFrequency)type interval:(NSInteger)interval end:(nullable EKRecurrenceEnd *)end; "
        "@property(nonatomic, copy, nullable) EKRecurrenceEnd *recurrenceEnd;",
        encoding="utf-8",
    )
    (root / "EKRecurrenceEnd.h").write_text(
        "An event which is set to never end should have its EKRecurrenceEnd set to nil. "
        "recurrenceEndWithEndDate endDate occurrenceCount",
        encoding="utf-8",
    )
    (root / "EKRecurrenceDayOfWeek.h").write_text(
        "dayOfWeek:weekNumber: @property(nonatomic, readonly) NSInteger weekNumber;",
        encoding="utf-8",
    )


def test_calendar_public_surface_audit_reports_expected_blockers(tmp_path: Path) -> None:
    _write_headers(tmp_path)

    result = audit_calendar_public_surface(tmp_path)

    assert result["status"] == "ok"
    assert result["facts"]["attendees_readonly"] is True
    assert result["facts"]["organizer_readonly"] is True
    assert result["facts"]["travel_time_property_present"] is False
    assert result["facts"]["url_writable"] is True
    assert "attendee mutation" in result["blocked_risky_operations"]
    assert "travel time mutation" in result["blocked_risky_operations"]
    assert "structured geofence alarm" not in result["candidate_separate_gates"]
    assert "structured event location" not in result["candidate_separate_gates"]
    assert "structured event location" in result["approved_public_write_properties"]
    assert "event URL" not in result["candidate_separate_gates"]
    assert "event URL" in result["approved_public_write_properties"]
    assert "structured geofence alarm" in result["approved_public_write_properties"]
    assert "email alarm" not in result["candidate_separate_gates"]
    assert "email alarm" in result["approved_public_write_properties"]
    assert result["facts"]["recurrence_designated_initializer_present"] is True
    assert result["facts"]["recurrence_rule_nullable_end_present"] is True
    assert result["facts"]["recurrence_end_nil_unbounded_documented"] is True
    assert result["facts"]["recurrence_end_date_present"] is True
    assert result["facts"]["recurrence_weekdays_present"] is True
    assert result["facts"]["recurrence_year_months_present"] is True
    assert result["facts"]["recurrence_year_month_days_present"] is True
    assert result["facts"]["recurrence_year_days_present"] is True
    assert result["facts"]["recurrence_year_weeks_present"] is True
    assert result["facts"]["recurrence_set_positions_present"] is True
    assert result["facts"]["recurrence_set_positions_range_documented"] is True
    assert result["facts"]["calendar_factory_present"] is True
    assert result["facts"]["calendar_source_writable"] is True
    assert result["facts"]["calendar_source_create_only_documented"] is True
    assert result["facts"]["calendar_identifier_lookup_present"] is True
    assert result["facts"]["calendar_save_present"] is True
    assert result["facts"]["calendar_remove_present"] is True
    assert result["facts"]["calendar_remove_deletes_events_documented"] is True
    assert result["facts"]["default_calendar_readonly"] is True
    assert result["facts"]["source_identifier_readonly"] is True
    assert result["facts"]["recurrence_day_week_number_present"] is True
    assert "monthly weekday recurrence" in result["approved_public_write_properties"]
    assert "monthly nth-weekday recurrence" in result["approved_public_write_properties"]
    assert "yearly month recurrence" in result["approved_public_write_properties"]
    assert "yearly month day-of-month recurrence" in result["approved_public_write_properties"]
    assert "yearly month nth-weekday recurrence" in result["approved_public_write_properties"]
    assert "yearly day-of-year recurrence" in result["approved_public_write_properties"]
    assert "yearly week-of-year recurrence" in result["approved_public_write_properties"]
    assert (
        "selector-backed set-position recurrence"
        in result["approved_public_write_properties"]
    )
    assert "finite recurrence end date" in result["approved_public_write_properties"]
    assert "explicit unbounded recurrence" in result["approved_public_write_properties"]
    assert "selected recurring occurrence scalar update" in result["approved_public_write_properties"]
    assert (
        "selected recurring occurrence timed reschedule"
        in result["approved_public_write_properties"]
    )
    assert (
        "selected recurring occurrence availability update"
        in result["approved_public_write_properties"]
    )
    assert (
        "selected recurring occurrence event URL set/clear"
        in result["approved_public_write_properties"]
    )
    assert (
        "selected recurring occurrence structured location set/clear"
        in result["approved_public_write_properties"]
    )
    assert "synthetic calendar create/rename/delete" in result["approved_public_write_properties"]
    assert "default calendar mutation" in result["blocked_risky_operations"]
    assert "calendar source/account mutation" in result["blocked_risky_operations"]
    assert "calendar delete without all-time emptiness proof" in result["blocked_risky_operations"]


def test_calendar_public_surface_audit_fails_when_blocker_assumption_changes(
    tmp_path: Path,
) -> None:
    _write_headers(tmp_path, travel_time=True, attendees_readonly=False)

    result = audit_calendar_public_surface(tmp_path)

    assert result["status"] == "error"
    codes = {finding["code"] for finding in result["findings"]}
    assert "unexpected_attendees_readonly" in codes
    assert "unexpected_travel_time_property_present" in codes


def test_calendar_public_surface_audit_fails_without_event_url_setter(
    tmp_path: Path,
) -> None:
    _write_headers(tmp_path, url_writable=False)

    result = audit_calendar_public_surface(tmp_path)

    assert result["status"] == "error"
    codes = {finding["code"] for finding in result["findings"]}
    assert "unexpected_url_writable" in codes


def test_calendar_public_surface_audit_fails_when_calendar_blocker_docs_change(
    tmp_path: Path,
) -> None:
    _write_headers(tmp_path)
    (tmp_path / "EKEventStore.h").write_text(
        "typedef NS_ENUM(NSInteger, EKSpan) { EKSpanThisEvent }; "
        "- (nullable EKCalendar *)calendarWithIdentifier:(NSString *)identifier; "
        "- (BOOL)saveEvent:(EKEvent *)event span:(EKSpan)span commit:(BOOL)commit error:(NSError **)error; "
        "- (BOOL)saveCalendar:(EKCalendar *)calendar commit:(BOOL)commit error:(NSError **)error; "
        "- (BOOL)removeCalendar:(EKCalendar *)calendar commit:(BOOL)commit error:(NSError **)error; "
        "All events in the calendar will be removed.",
        encoding="utf-8",
    )
    (tmp_path / "EKCalendar.h").write_text(
        "\n".join(
            [
                "+ (EKCalendar *)calendarForEntityType:(EKEntityType)entityType eventStore:(EKEventStore *)eventStore;",
                "@property(nonatomic, strong, null_unspecified) EKSource *source;",
            ]
        ),
        encoding="utf-8",
    )

    result = audit_calendar_public_surface(tmp_path)

    assert result["status"] == "error"
    codes = {finding["code"] for finding in result["findings"]}
    assert "unexpected_default_calendar_readonly" in codes
    assert "unexpected_calendar_source_create_only_documented" in codes


def test_calendar_public_surface_audit_fails_without_nil_unbounded_documentation(
    tmp_path: Path,
) -> None:
    _write_headers(tmp_path)
    (tmp_path / "EKRecurrenceEnd.h").write_text(
        "recurrenceEndWithEndDate endDate occurrenceCount",
        encoding="utf-8",
    )

    result = audit_calendar_public_surface(tmp_path)

    assert result["status"] == "error"
    codes = {finding["code"] for finding in result["findings"]}
    assert "unexpected_recurrence_end_nil_unbounded_documented" in codes
