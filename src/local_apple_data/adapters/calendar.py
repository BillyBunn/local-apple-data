from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import hashlib
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from . import _signing
from .sqlite_store import has_minimum_query_quality
from .warning_safety import safe_warning_payloads


DEFAULT_DAYS_BACK = 365
DEFAULT_DAYS_FORWARD = 730
DEFAULT_LIMIT = 20
DEFAULT_MAX_SCAN_EVENTS = 2000
MAX_SELECTED_CALENDAR_EVENT_WINDOW_DAYS = 366
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MAX_PREVIEW_TITLE_CHARS = 512
MAX_PREVIEW_CALENDAR_CHARS = 512
MAX_PARTICIPANT_NAME_CHARS = 512
MAX_PARTICIPANT_URL_CHARS = 2048
MAX_LOCATION_CHARS = 1000
MAX_STRUCTURED_LOCATION_RADIUS_METERS = 100000.0
MAX_ALARM_OFFSETS = 8
MAX_ALARM_SOUND_NAME_CHARS = 128
MAX_ALARM_EMAIL_ADDRESS_CHARS = 254
MAX_TIME_ZONE_CHARS = 128
MAX_EVENT_URL_CHARS = 2048
SAFE_EVENT_URL_SCHEMES = {"http", "https", "mailto", "tel"}
MAILTO_EVENT_URL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
TEL_EVENT_URL_RE = re.compile(r"^\+?[0-9][0-9().-]{1,31}(?:;ext=[0-9]{1,10})?$")
MIN_ALARM_OFFSET_MINUTES = -40320
MAX_ALARM_OFFSET_MINUTES = 40320
MAX_RECURRENCE_INTERVAL = 4
MIN_RECURRENCE_OCCURRENCES = 2
MAX_RECURRENCE_OCCURRENCES = 52
MAX_RECURRENCE_END_DAYS = 3650
RECURRENCE_FREQUENCIES = {"daily", "weekly", "monthly", "yearly"}
RECURRENCE_DELETE_SCOPES = {"this_event", "future_events", "all_events"}
RECURRENCE_UPDATE_SCOPES = {"this_event", "future_events"}
RECURRENCE_WEEKDAY_ALIASES = {
    "1": "sunday",
    "sun": "sunday",
    "sunday": "sunday",
    "2": "monday",
    "mon": "monday",
    "monday": "monday",
    "3": "tuesday",
    "tue": "tuesday",
    "tues": "tuesday",
    "tuesday": "tuesday",
    "4": "wednesday",
    "wed": "wednesday",
    "wednesday": "wednesday",
    "5": "thursday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "thursday": "thursday",
    "6": "friday",
    "fri": "friday",
    "friday": "friday",
    "7": "saturday",
    "sat": "saturday",
    "saturday": "saturday",
}
RECURRENCE_WEEKDAY_ORDER = {
    "sunday": 1,
    "monday": 2,
    "tuesday": 3,
    "wednesday": 4,
    "thursday": 5,
    "friday": 6,
    "saturday": 7,
}
SETTABLE_AVAILABILITIES = {
    "busy": 0,
    "free": 1,
    "tentative": 2,
    "unavailable": 3,
}
ALARM_PROXIMITIES = {"enter", "leave"}
EXPECTED_AVAILABILITIES = {
    **SETTABLE_AVAILABILITIES,
    "not_supported": -1,
    "not-supported": -1,
}
AVAILABILITY_NAMES = {
    -1: "not_supported",
    0: "busy",
    1: "free",
    2: "tentative",
    3: "unavailable",
}
DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ALARM_SOUND_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _.-]+$")
ALARM_EMAIL_ADDRESS_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$"
)
EVENTKIT_TIMEOUT_SECONDS = 10.0
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENTKIT_HELPER = PROJECT_ROOT / "scripts/eventkit_helper.swift"
EVENTKIT_HELPER_BUNDLE_ID = os.environ.get(
    "LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID",
    "com.local-apple-data.eventkit-helper",
)


def _eventkit_helper_bundle_id() -> str:
    return os.environ.get(
        "LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID",
        EVENTKIT_HELPER_BUNDLE_ID,
    )
PLAN_OPERATIONS = {"create", "update", "delete"}
CALENDAR_MANAGEMENT_OPERATIONS = {"create_calendar", "rename_calendar", "delete_calendar"}
CALENDAR_TEST_PREFIX = "LAD-TEST-"
APPROVAL_TOKEN_PREFIX = "calendar-apply:v1:"
CALENDAR_PARTICIPANT_HANDLE_PREFIX = "calendar:participant"
EventKitRunner = Callable[[dict[str, Any], float], dict[str, Any]]


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _content_privacy(*, content_inspected: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content",
    }


def _participant_privacy(*, detail_returned: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "name_returned": detail_returned,
        "url_returned": detail_returned,
        "output_tier": "detail" if detail_returned else "metadata",
    }


def _preview_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "preview",
    }


def _mutation_privacy(*, content_inspected: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "mutation",
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _normalize_bool_flag(value: Any, *, field: str) -> tuple[bool | None, dict[str, str] | None]:
    if isinstance(value, bool):
        return value, None
    return None, _warning("invalid_boolean", f"{field} must be a JSON boolean.")


def _normalize_alarm_offsets(
    value: Any,
    *,
    field: str,
) -> tuple[list[int] | None, dict[str, str] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list):
        return None, _warning(
            "invalid_alarm_offsets",
            f"{field} must be a JSON array of integer minute offsets.",
        )
    if len(value) > MAX_ALARM_OFFSETS:
        return None, _warning(
            "too_many_alarm_offsets",
            f"{field} supports at most {MAX_ALARM_OFFSETS} offsets.",
        )
    normalized: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            return None, _warning(
                "invalid_alarm_offsets",
                f"{field} must contain only integer minute offsets.",
            )
        if item < MIN_ALARM_OFFSET_MINUTES or item > MAX_ALARM_OFFSET_MINUTES:
            return None, _warning(
                "invalid_alarm_offset_range",
                f"{field} offsets must be between {MIN_ALARM_OFFSET_MINUTES} and {MAX_ALARM_OFFSET_MINUTES} minutes.",
            )
        normalized.append(item)
    return sorted(set(normalized)), None


def _normalize_alarm_absolute_dates(
    value: Any,
    *,
    field: str,
) -> tuple[list[str] | None, dict[str, str] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list):
        return None, _warning(
            "invalid_alarm_absolute_dates",
            f"{field} must be a JSON array of ISO 8601 timestamps with timezones.",
        )
    if len(value) > MAX_ALARM_OFFSETS:
        return None, _warning(
            "too_many_alarm_absolute_dates",
            f"{field} supports at most {MAX_ALARM_OFFSETS} timestamps.",
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None, _warning(
                "invalid_alarm_absolute_dates",
                f"{field} must contain only ISO 8601 timestamp strings.",
            )
        parsed, parse_warning = _normalize_event_datetime(item, field=field)
        if parse_warning is not None or parsed is None:
            return None, _warning(
                "invalid_alarm_absolute_dates",
                f"{field} must contain only ISO 8601 timestamps with timezones.",
            )
        normalized.append(parsed)
    return sorted(set(normalized)), None


def _normalize_alarm_sound_name(
    value: Any,
    *,
    field: str,
) -> tuple[str | None, dict[str, str] | None]:
    if value is None:
        return "", None
    if not isinstance(value, str):
        return None, _warning(
            "invalid_alarm_sound_name",
            f"{field} must be a bounded system sound name.",
        )
    normalized = value.strip()
    if not normalized:
        return "", None
    if len(normalized) > MAX_ALARM_SOUND_NAME_CHARS:
        return None, _warning(
            "invalid_alarm_sound_name",
            f"{field} exceeds {MAX_ALARM_SOUND_NAME_CHARS} characters.",
        )
    if not ALARM_SOUND_NAME_PATTERN.fullmatch(normalized):
        return None, _warning(
            "invalid_alarm_sound_name",
            f"{field} must be a bare system sound name, not a path.",
        )
    return normalized, None


def _normalize_alarm_email_address(
    value: Any,
    *,
    field: str,
) -> tuple[str | None, str, dict[str, str] | None]:
    if value is None:
        return "", "", None
    if not isinstance(value, str):
        return None, "", _warning(
            "invalid_alarm_email_address",
            f"{field} must be a bounded email address.",
        )
    normalized = value.strip().lower()
    if not normalized:
        return "", "", None
    if (
        len(normalized) > MAX_ALARM_EMAIL_ADDRESS_CHARS
        or any(ord(ch) < 33 or ord(ch) > 126 for ch in normalized)
        or ALARM_EMAIL_ADDRESS_PATTERN.fullmatch(normalized) is None
    ):
        return None, "", _warning(
            "invalid_alarm_email_address",
            f"{field} must be a bounded plain email address.",
        )
    return normalized, hashlib.sha256(normalized.encode("utf-8")).hexdigest(), None


def _is_date_only_input(value: str) -> bool:
    return DATE_ONLY_PATTERN.fullmatch(value.strip()) is not None


def _date_only_pair_warning(
    first_value: str,
    second_value: str,
    *,
    first_field: str,
    second_field: str,
) -> dict[str, str] | None:
    if bool(first_value) and bool(second_value) and _is_date_only_input(
        first_value
    ) != _is_date_only_input(second_value):
        return _warning(
            "mixed_date_only_datetime",
            f"{first_field} and {second_field} must both be date-only values or both be timestamps.",
        )
    return None


def _alarm_kind(
    offsets: list[int] | None,
    absolute_dates: list[str] | None,
    proximity: str | None = "",
    email_sha256: str | None = "",
) -> str:
    if proximity:
        return "geofence"
    if offsets:
        return "email_relative" if email_sha256 else "relative"
    if absolute_dates:
        return "email_absolute" if email_sha256 else "absolute"
    return "none"


def _alarm_action(
    sound_name: str | None,
    proximity: str | None = "",
    email_sha256: str | None = "",
) -> str:
    if proximity:
        return "geofence"
    if email_sha256:
        return "email"
    return "audio" if sound_name else "display"


def _alarm_conflict_warning(
    offsets: list[int] | None,
    absolute_dates: list[str] | None,
    proximity: str | None = "",
) -> dict[str, str] | None:
    trigger_count = int(bool(offsets)) + int(bool(absolute_dates)) + int(bool(proximity))
    if trigger_count > 1:
        return _warning(
            "conflicting_alarm_fields",
            "Use only one alarm trigger: alarm_offsets_minutes, alarm_absolute_dates, or alarm_proximity.",
        )
    return None


def _alarm_sound_trigger_warning(
    sound_name: str | None,
    offsets: list[int] | None,
    absolute_dates: list[str] | None,
    *,
    field: str,
) -> dict[str, str] | None:
    if sound_name and not (offsets or absolute_dates):
        return _warning(
            "missing_alarm_trigger",
            f"{field} requires alarm_offsets_minutes or alarm_absolute_dates.",
        )
    return None


def _alarm_email_trigger_warning(
    email_sha256: str | None,
    offsets: list[int] | None,
    absolute_dates: list[str] | None,
    *,
    field: str,
) -> dict[str, str] | None:
    if email_sha256 and not (offsets or absolute_dates):
        return _warning(
            "missing_alarm_trigger",
            f"{field} requires alarm_offsets_minutes or alarm_absolute_dates.",
        )
    return None


def _alarm_action_conflict_warning(
    sound_name: str | None,
    proximity: str | None,
    email_sha256: str | None,
    *,
    prefix: str = "",
) -> dict[str, str] | None:
    action_count = int(bool(sound_name)) + int(bool(proximity)) + int(bool(email_sha256))
    if action_count > 1:
        return _warning(
            "conflicting_alarm_fields",
            f"Use only one {prefix}alarm action: sound, geofence, or email.",
        )
    return None


def _normalize_alarm_proximity(
    value: Any,
    *,
    field: str,
) -> tuple[str | None, dict[str, str] | None]:
    if value is None:
        return "", None
    if not isinstance(value, str):
        return None, _warning(
            "invalid_alarm_proximity",
            f"{field} must be enter or leave.",
        )
    normalized = value.strip().lower().replace("-", "_")
    if not normalized:
        return "", None
    if normalized not in ALARM_PROXIMITIES:
        return None, _warning(
            "invalid_alarm_proximity",
            f"{field} must be enter or leave.",
        )
    return normalized, None


def _alarm_geofence_location_warning(
    proximity: str | None,
    structured_location: dict[str, Any] | None,
    *,
    proximity_field: str,
    location_field: str,
) -> dict[str, str] | None:
    if proximity and not structured_location:
        return _warning(
            "missing_alarm_structured_location",
            f"{proximity_field} requires {location_field}.",
        )
    if structured_location and not proximity:
        return _warning(
            "missing_alarm_proximity",
            f"{location_field} requires {proximity_field}.",
        )
    return None


def _alarm_count(
    offsets: list[int] | None,
    absolute_dates: list[str] | None,
    proximity: str | None = "",
) -> int:
    if proximity:
        return 1
    return len(offsets or absolute_dates or [])


def _normalize_time_zone(
    value: str,
    *,
    field: str,
) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip()
    if not normalized:
        return "", None
    if len(normalized) > MAX_TIME_ZONE_CHARS:
        return "", _warning("input_too_large", f"Field exceeds maximum length: {field}.")
    try:
        return ZoneInfo(normalized).key, None
    except (ZoneInfoNotFoundError, ValueError):
        return "", _warning(
            "invalid_time_zone",
            f"{field} must be an IANA time zone identifier, for example America/Los_Angeles.",
        )


def _normalize_availability(
    value: str,
    *,
    field: str,
    allow_not_supported: bool = False,
) -> tuple[str, int | None, dict[str, str] | None]:
    normalized = value.strip().lower().replace(" ", "_")
    if not normalized:
        return "", None, None
    allowed = EXPECTED_AVAILABILITIES if allow_not_supported else SETTABLE_AVAILABILITIES
    if normalized not in allowed:
        allowed_names = (
            "busy, free, tentative, unavailable, or not_supported"
            if allow_not_supported
            else "busy, free, tentative, or unavailable"
        )
        return "", None, _warning(
            "invalid_availability",
            f"{field} must be {allowed_names}.",
        )
    value_int = allowed[normalized]
    return AVAILABILITY_NAMES[value_int], value_int, None


def _availability_name(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return AVAILABILITY_NAMES.get(value, "")
    return ""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_event_url(
    value: str,
    *,
    field: str,
) -> tuple[str, str, str, str, dict[str, str] | None]:
    normalized = value
    if not normalized:
        return "", "", "", "", None
    if len(normalized) > MAX_EVENT_URL_CHARS:
        return "", "", "", "", _warning("input_too_large", f"Field exceeds maximum length: {field}.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
        return "", "", "", "", _warning("invalid_event_url", f"{field} must not contain control characters.")
    if any(ch.isspace() for ch in normalized):
        return "", "", "", "", _warning("invalid_event_url", f"{field} must not contain whitespace.")
    try:
        parsed = urlparse(normalized)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return "", "", "", "", _warning(
            "invalid_event_url",
            f"{field} must be an allowed event URL.",
        )
    scheme = parsed.scheme.lower()
    if scheme not in SAFE_EVENT_URL_SCHEMES:
        return "", "", "", "", _warning(
            "invalid_event_url",
            f"{field} must use http, https, mailto, or tel.",
        )
    if scheme in {"http", "https"}:
        if not parsed.netloc or not hostname:
            return "", "", "", "", _warning(
                "invalid_event_url",
                f"{field} must include a host.",
            )
        if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
            return "", "", "", "", _warning(
                "invalid_event_url",
                f"{field} must not include embedded credentials.",
            )
        return normalized, scheme, hostname, _sha256_text(normalized), None
    if scheme == "mailto":
        if parsed.netloc or parsed.params or parsed.query or parsed.fragment:
            return "", "", "", "", _warning(
                "invalid_event_url",
                f"{field} mailto URLs must contain only one recipient address.",
            )
        address = parsed.path
        if not MAILTO_EVENT_URL_RE.fullmatch(address):
            return "", "", "", "", _warning(
                "invalid_event_url",
                f"{field} mailto URL must contain one valid recipient address.",
            )
        return normalized, scheme, "", _sha256_text(normalized), None
    if scheme == "tel":
        if parsed.netloc or parsed.query or parsed.fragment or not parsed.path:
            return "", "", "", "", _warning(
                "invalid_event_url",
                f"{field} tel URLs must contain only one dial string.",
            )
        dial_string = parsed.path
        if parsed.params:
            dial_string = f"{dial_string};{parsed.params}"
        if not TEL_EVENT_URL_RE.fullmatch(dial_string):
            return "", "", "", "", _warning(
                "invalid_event_url",
                f"{field} tel URL must contain one bounded dial string.",
            )
        return normalized, scheme, "", _sha256_text(normalized), None
    return "", "", "", "", _warning("invalid_event_url", f"{field} must be an allowed event URL.")


def _normalize_structured_location(
    value: Any,
    *,
    field: str,
) -> tuple[dict[str, Any], dict[str, str] | None]:
    if value in (None, {}):
        return {}, None
    if not isinstance(value, dict):
        return {}, _warning(
            "invalid_structured_location",
            f"{field} must be a JSON object with title and optional latitude/longitude/radius_meters.",
        )

    title_value = value.get("title")
    if not isinstance(title_value, str):
        return {}, _warning(
            "invalid_structured_location",
            f"{field}.title must be non-empty text.",
        )
    title, title_warning = _bounded_preview_value(
        title_value,
        field=f"{field}.title",
        max_chars=MAX_LOCATION_CHARS,
        required=True,
    )
    if title_warning is not None:
        return {}, title_warning

    latitude = value.get("latitude")
    longitude = value.get("longitude")
    radius = value.get("radius_meters", 0.0)
    if (latitude is None) != (longitude is None):
        return {}, _warning(
            "invalid_structured_location",
            f"{field} requires latitude and longitude together.",
        )
    if isinstance(radius, bool) or not isinstance(radius, int | float):
        return {}, _warning(
            "invalid_structured_location",
            f"{field}.radius_meters must be a number.",
        )
    radius_value = float(radius)
    if radius_value < 0 or radius_value > MAX_STRUCTURED_LOCATION_RADIUS_METERS:
        return {}, _warning(
            "invalid_structured_location",
            f"{field}.radius_meters must be between 0 and {int(MAX_STRUCTURED_LOCATION_RADIUS_METERS)}.",
        )

    normalized: dict[str, Any] = {"title": title, "geo_present": False}
    if latitude is not None:
        if (
            isinstance(latitude, bool)
            or isinstance(longitude, bool)
            or not isinstance(latitude, int | float)
            or not isinstance(longitude, int | float)
        ):
            return {}, _warning(
                "invalid_structured_location",
                f"{field}.latitude and {field}.longitude must be numbers.",
            )
        latitude_value = float(latitude)
        longitude_value = float(longitude)
        if latitude_value < -90 or latitude_value > 90:
            return {}, _warning(
                "invalid_structured_location",
                f"{field}.latitude must be between -90 and 90.",
            )
        if longitude_value < -180 or longitude_value > 180:
            return {}, _warning(
                "invalid_structured_location",
                f"{field}.longitude must be between -180 and 180.",
            )
        normalized.update(
            {
                "geo_present": True,
                "latitude": latitude_value,
                "longitude": longitude_value,
                "radius_meters": radius_value,
            }
        )
    elif radius_value:
        return {}, _warning(
            "invalid_structured_location",
            f"{field}.radius_meters requires latitude and longitude.",
        )
    return normalized, None


def _normalize_sha256(value: str, *, field: str) -> tuple[str, dict[str, str] | None]:
    normalized = value
    if not normalized:
        return "", None
    if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
        return "", _warning("invalid_sha256", f"{field} must be a lowercase SHA-256 hex digest.")
    return normalized, None


def _empty_recurrence() -> dict[str, Any]:
    return {
        "frequency": "",
        "interval": 0,
        "count": 0,
        "recurrence_present": False,
    }


def _normalize_recurrence_end_date(value: str) -> tuple[str, dict[str, str] | None]:
    raw = "" if value is None else str(value).strip()
    if not raw:
        return "", None
    if _is_date_only_input(raw):
        return "", _warning(
            "invalid_recurrence",
            "recurrence_end_date must be an ISO 8601 timestamp with timezone, not a date-only value.",
        )
    return _normalize_event_datetime(
        raw,
        field="recurrence_end_date",
        allow_date_only=False,
    )


def _recurrence_end_date_range_warning(
    recurrence: dict[str, Any] | None,
    start_date: str,
) -> dict[str, str] | None:
    if not recurrence or not recurrence.get("recurrence_present"):
        return None
    recurrence_end_date = str(recurrence.get("end_date") or "")
    if not recurrence_end_date or not start_date:
        return None
    if _is_date_only_input(start_date):
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
    else:
        start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    recurrence_end_dt = datetime.fromisoformat(recurrence_end_date.replace("Z", "+00:00"))
    if recurrence_end_dt <= start_dt:
        return _warning(
            "invalid_recurrence",
            "recurrence_end_date must be after start_date.",
        )
    if recurrence_end_dt > start_dt + timedelta(days=MAX_RECURRENCE_END_DAYS):
        return _warning(
            "invalid_recurrence",
            f"recurrence_end_date must be within {MAX_RECURRENCE_END_DAYS} days of start_date.",
        )
    return None


def _normalize_recurrence_weekdays(
    weekdays: list[str | int] | str | None,
) -> tuple[list[str] | None, dict[str, str] | None]:
    if weekdays is None or weekdays == "":
        return [], None
    raw_values: list[str | int]
    if isinstance(weekdays, str):
        raw_values = [token for token in weekdays.split(",") if token.strip()]
    elif isinstance(weekdays, list):
        raw_values = weekdays
    else:
        return None, _warning(
            "invalid_recurrence",
            "recurrence_weekdays must be a comma-separated string or list.",
        )
    normalized: set[str] = set()
    for raw in raw_values:
        if isinstance(raw, bool):
            return None, _warning(
                "invalid_recurrence",
                "recurrence_weekdays values must be weekday names or integers 1 through 7.",
            )
        token = str(raw).strip().lower().replace("-", "_")
        if not token:
            continue
        weekday = RECURRENCE_WEEKDAY_ALIASES.get(token)
        if weekday is None:
            return None, _warning(
                "invalid_recurrence",
                "recurrence_weekdays values must be weekday names or integers 1 through 7.",
            )
        normalized.add(weekday)
    return sorted(normalized, key=lambda item: RECURRENCE_WEEKDAY_ORDER[item]), None


def _normalize_recurrence_month_days(
    month_days: list[int] | str | None,
    *,
    field: str = "recurrence_month_days",
) -> tuple[list[int] | None, dict[str, str] | None]:
    if month_days is None or month_days == "":
        return [], None
    raw_values: list[int | str]
    string_input = isinstance(month_days, str)
    if string_input:
        raw_values = [token for token in month_days.split(",") if token.strip()]
    elif isinstance(month_days, list):
        raw_values = month_days
    else:
        return None, _warning(
            "invalid_recurrence",
            f"{field} must be a comma-separated string or integer list.",
        )
    normalized: set[int] = set()
    for raw in raw_values:
        if isinstance(raw, bool):
            return None, _warning(
                "invalid_recurrence",
                f"{field} values must be integers from -31 through -1 or 1 through 31.",
            )
        if isinstance(raw, int):
            day = raw
        elif string_input and isinstance(raw, str):
            try:
                day = int(raw.strip())
            except ValueError:
                return None, _warning(
                    "invalid_recurrence",
                    f"{field} values must be integers from -31 through -1 or 1 through 31.",
                )
        else:
            return None, _warning(
                "invalid_recurrence",
                f"{field} values must be integers from -31 through -1 or 1 through 31.",
            )
        if day == 0 or day < -31 or day > 31:
            return None, _warning(
                "invalid_recurrence",
                f"{field} values must be integers from -31 through -1 or 1 through 31.",
            )
        normalized.add(day)
    return sorted(normalized), None


def _normalize_recurrence_month_weekdays(
    month_weekdays: list[dict[str, Any]] | str | None,
    *,
    field: str = "recurrence_month_weekdays",
) -> tuple[list[dict[str, Any]] | None, dict[str, str] | None]:
    if month_weekdays is None or month_weekdays == "":
        return [], None
    raw_values: list[dict[str, Any] | str]
    string_input = isinstance(month_weekdays, str)
    if string_input:
        raw_values = [token for token in month_weekdays.split(",") if token.strip()]
    elif isinstance(month_weekdays, list):
        raw_values = month_weekdays
    else:
        return None, _warning(
            "invalid_recurrence",
            f"{field} must be a comma-separated weekday:week_number string or list of objects.",
        )
    normalized: set[tuple[str, int]] = set()
    for raw in raw_values:
        if string_input and isinstance(raw, str):
            parts = raw.strip().split(":", 1)
            if len(parts) != 2:
                return None, _warning(
                    "invalid_recurrence",
                    f"{field} values must use weekday:week_number.",
                )
            weekday_token = parts[0].strip().lower().replace("-", "_")
            try:
                week_number = int(parts[1].strip())
            except ValueError:
                return None, _warning(
                    "invalid_recurrence",
                    f"{field} week_number values must be integers from -5 through -1 or 1 through 5.",
                )
        elif isinstance(raw, dict):
            weekday_token = str(raw.get("weekday") or "").strip().lower().replace("-", "_")
            week_number_value = raw.get("week_number")
            if isinstance(week_number_value, bool) or not isinstance(week_number_value, int):
                return None, _warning(
                    "invalid_recurrence",
                    f"{field} week_number values must be integers from -5 through -1 or 1 through 5.",
                )
            week_number = week_number_value
        else:
            return None, _warning(
                "invalid_recurrence",
                f"{field} values must use weekday and week_number.",
            )
        weekday = RECURRENCE_WEEKDAY_ALIASES.get(weekday_token)
        if weekday is None:
            return None, _warning(
                "invalid_recurrence",
                f"{field} weekday values must be weekday names or integers 1 through 7.",
            )
        if week_number == 0 or week_number < -5 or week_number > 5:
            return None, _warning(
                "invalid_recurrence",
                f"{field} week_number values must be integers from -5 through -1 or 1 through 5.",
            )
        normalized.add((weekday, week_number))
    return [
        {"weekday": weekday, "week_number": week_number}
        for weekday, week_number in sorted(
            normalized,
            key=lambda item: (item[1], RECURRENCE_WEEKDAY_ORDER[item[0]]),
        )
    ], None


def _normalize_recurrence_year_months(
    year_months: list[int] | str | None,
) -> tuple[list[int] | None, dict[str, str] | None]:
    if year_months is None or year_months == "":
        return [], None
    raw_values: list[int | str]
    string_input = isinstance(year_months, str)
    if string_input:
        raw_values = [token for token in year_months.split(",") if token.strip()]
    elif isinstance(year_months, list):
        raw_values = year_months
    else:
        return None, _warning(
            "invalid_recurrence",
            "recurrence_year_months must be a comma-separated string or integer list.",
        )
    normalized: set[int] = set()
    for raw in raw_values:
        if isinstance(raw, bool):
            return None, _warning(
                "invalid_recurrence",
                "recurrence_year_months values must be integers from 1 through 12.",
            )
        if isinstance(raw, int):
            month = raw
        elif string_input and isinstance(raw, str):
            try:
                month = int(raw.strip())
            except ValueError:
                return None, _warning(
                    "invalid_recurrence",
                    "recurrence_year_months values must be integers from 1 through 12.",
                )
        else:
            return None, _warning(
                "invalid_recurrence",
                "recurrence_year_months values must be integers from 1 through 12.",
            )
        if month < 1 or month > 12:
            return None, _warning(
                "invalid_recurrence",
                "recurrence_year_months values must be integers from 1 through 12.",
            )
        normalized.add(month)
    return sorted(normalized), None


def _normalize_recurrence_signed_ints(
    value: list[int] | str | None,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> tuple[list[int] | None, dict[str, str] | None]:
    if value is None or value == "":
        return [], None
    raw_values: list[int | str]
    string_input = isinstance(value, str)
    if string_input:
        raw_values = [token for token in value.split(",") if token.strip()]
    elif isinstance(value, list):
        raw_values = value
    else:
        return None, _warning(
            "invalid_recurrence",
            f"{field} must be a comma-separated string or integer list.",
        )
    normalized: set[int] = set()
    range_message = f"{field} values must be integers from {minimum} through -1 or 1 through {maximum}."
    for raw in raw_values:
        if isinstance(raw, bool):
            return None, _warning("invalid_recurrence", range_message)
        if isinstance(raw, int):
            item = raw
        elif string_input and isinstance(raw, str):
            try:
                item = int(raw.strip())
            except ValueError:
                return None, _warning("invalid_recurrence", range_message)
        else:
            return None, _warning("invalid_recurrence", range_message)
        if item == 0 or item < minimum or item > maximum:
            return None, _warning("invalid_recurrence", range_message)
        normalized.add(item)
    return sorted(normalized), None


def _normalize_recurrence(
    *,
    frequency: str,
    interval: int | None,
    count: int | None,
    end_date: str = "",
    unbounded: bool = False,
    weekdays: list[str | int] | str | None = None,
    month_days: list[int] | str | None = None,
    month_weekdays: list[dict[str, Any]] | str | None = None,
    year_months: list[int] | str | None = None,
    year_month_days: list[int] | str | None = None,
    year_month_weekdays: list[dict[str, Any]] | str | None = None,
    year_days: list[int] | str | None = None,
    year_weeks: list[int] | str | None = None,
    set_positions: list[int] | str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    normalized_unbounded, unbounded_warning = _normalize_bool_flag(
        unbounded,
        field="recurrence_unbounded",
    )
    if unbounded_warning is not None:
        return None, unbounded_warning
    normalized_end_date, end_date_warning = _normalize_recurrence_end_date(end_date)
    if end_date_warning is not None:
        return None, end_date_warning
    normalized_weekdays, weekdays_warning = _normalize_recurrence_weekdays(weekdays)
    if weekdays_warning is not None:
        return None, weekdays_warning
    normalized_month_days, month_days_warning = _normalize_recurrence_month_days(month_days)
    if month_days_warning is not None:
        return None, month_days_warning
    normalized_month_weekdays, month_weekdays_warning = (
        _normalize_recurrence_month_weekdays(month_weekdays)
    )
    if month_weekdays_warning is not None:
        return None, month_weekdays_warning
    normalized_year_months, year_months_warning = _normalize_recurrence_year_months(
        year_months
    )
    if year_months_warning is not None:
        return None, year_months_warning
    normalized_year_month_days, year_month_days_warning = _normalize_recurrence_month_days(
        year_month_days,
        field="recurrence_year_month_days",
    )
    if year_month_days_warning is not None:
        return None, year_month_days_warning
    normalized_year_month_weekdays, year_month_weekdays_warning = (
        _normalize_recurrence_month_weekdays(
            year_month_weekdays,
            field="recurrence_year_month_weekdays",
        )
    )
    if year_month_weekdays_warning is not None:
        return None, year_month_weekdays_warning
    normalized_year_days, year_days_warning = _normalize_recurrence_signed_ints(
        year_days,
        field="recurrence_year_days",
        minimum=-366,
        maximum=366,
    )
    if year_days_warning is not None:
        return None, year_days_warning
    normalized_year_weeks, year_weeks_warning = _normalize_recurrence_signed_ints(
        year_weeks,
        field="recurrence_year_weeks",
        minimum=-53,
        maximum=53,
    )
    if year_weeks_warning is not None:
        return None, year_weeks_warning
    normalized_set_positions, set_positions_warning = _normalize_recurrence_signed_ints(
        set_positions,
        field="recurrence_set_positions",
        minimum=-366,
        maximum=366,
    )
    if set_positions_warning is not None:
        return None, set_positions_warning
    normalized_frequency = frequency.strip().lower().replace("-", "_")
    has_recurrence_input = bool(
        normalized_frequency
        or interval is not None
        or count is not None
        or normalized_end_date
        or normalized_unbounded is True
        or normalized_weekdays
        or normalized_month_days
        or normalized_month_weekdays
        or normalized_year_months
        or normalized_year_month_days
        or normalized_year_month_weekdays
        or normalized_year_days
        or normalized_year_weeks
        or normalized_set_positions
    )
    if not has_recurrence_input:
        return _empty_recurrence(), None
    if normalized_frequency not in RECURRENCE_FREQUENCIES:
        return None, _warning(
            "invalid_recurrence",
            "recurrence_frequency must be daily, weekly, monthly, or yearly.",
        )
    normalized_interval = 1 if interval is None else interval
    if isinstance(normalized_interval, bool) or not isinstance(normalized_interval, int):
        return None, _warning("invalid_recurrence", "recurrence_interval must be an integer.")
    if normalized_interval < 1 or normalized_interval > MAX_RECURRENCE_INTERVAL:
        return None, _warning(
            "invalid_recurrence",
            f"recurrence_interval must be between 1 and {MAX_RECURRENCE_INTERVAL}.",
        )

    recurrence_bound_count = sum(
        1
        for present in (
            count is not None,
            bool(normalized_end_date),
            normalized_unbounded is True,
        )
        if present
    )
    if recurrence_bound_count > 1:
        return None, _warning(
            "invalid_recurrence",
            "Use exactly one of recurrence_count, recurrence_end_date, or recurrence_unbounded.",
        )
    if recurrence_bound_count == 0:
        return None, _warning(
            "invalid_recurrence",
            "recurrence requires recurrence_count, recurrence_end_date, or recurrence_unbounded:true.",
        )

    normalized_count = 0 if count is None else count
    if isinstance(normalized_count, bool) or not isinstance(normalized_count, int):
        return None, _warning(
            "invalid_recurrence",
            "recurrence_count must be an integer.",
        )
    if count is not None and (
        normalized_count < MIN_RECURRENCE_OCCURRENCES
        or normalized_count > MAX_RECURRENCE_OCCURRENCES
    ):
        return None, _warning(
            "invalid_recurrence",
            f"recurrence_count must be between {MIN_RECURRENCE_OCCURRENCES} and {MAX_RECURRENCE_OCCURRENCES}.",
        )
    monthly_weekday_selector = normalized_frequency == "monthly" and bool(
        normalized_weekdays
    )
    yearly_week_with_weekdays = normalized_frequency == "yearly" and bool(
        normalized_year_weeks
    )
    if normalized_weekdays and not (
        normalized_frequency == "weekly"
        or monthly_weekday_selector
        or yearly_week_with_weekdays
    ):
        return None, _warning(
            "invalid_recurrence",
            "recurrence_weekdays is supported only for weekly recurrence, monthly recurrence, or yearly recurrence with recurrence_year_weeks.",
        )
    if normalized_month_days and normalized_frequency != "monthly":
        return None, _warning(
            "invalid_recurrence",
            "recurrence_month_days is supported only when recurrence_frequency is monthly.",
        )
    if normalized_month_weekdays and normalized_frequency != "monthly":
        return None, _warning(
            "invalid_recurrence",
            "recurrence_month_weekdays is supported only when recurrence_frequency is monthly.",
        )
    if normalized_year_months and normalized_frequency != "yearly":
        return None, _warning(
            "invalid_recurrence",
            "recurrence_year_months is supported only when recurrence_frequency is yearly.",
        )
    if normalized_year_month_days and normalized_frequency != "yearly":
        return None, _warning(
            "invalid_recurrence",
            "recurrence_year_month_days is supported only when recurrence_frequency is yearly.",
        )
    if normalized_year_month_days and not normalized_year_months:
        return None, _warning(
            "invalid_recurrence",
            "recurrence_year_month_days requires recurrence_year_months to bind exact months.",
        )
    if normalized_year_month_weekdays and normalized_frequency != "yearly":
        return None, _warning(
            "invalid_recurrence",
            "recurrence_year_month_weekdays is supported only when recurrence_frequency is yearly.",
        )
    if normalized_year_month_weekdays and not normalized_year_months:
        return None, _warning(
            "invalid_recurrence",
            "recurrence_year_month_weekdays requires recurrence_year_months to bind exact months.",
        )
    if normalized_year_days and normalized_frequency != "yearly":
        return None, _warning(
            "invalid_recurrence",
            "recurrence_year_days is supported only when recurrence_frequency is yearly.",
        )
    if normalized_year_weeks and normalized_frequency != "yearly":
        return None, _warning(
            "invalid_recurrence",
            "recurrence_year_weeks is supported only when recurrence_frequency is yearly.",
        )
    if normalized_year_weeks and not normalized_weekdays:
        return None, _warning(
            "invalid_recurrence",
            "recurrence_year_weeks requires recurrence_weekdays to bind exact weekdays inside the selected weeks.",
        )
    if normalized_month_days and normalized_month_weekdays:
        return None, _warning(
            "invalid_recurrence",
            "Use either recurrence_month_days or recurrence_month_weekdays, not both.",
        )
    if monthly_weekday_selector and (normalized_month_days or normalized_month_weekdays):
        return None, _warning(
            "invalid_recurrence",
            "Use recurrence_weekdays, recurrence_month_days, or recurrence_month_weekdays for monthly recurrence, not more than one.",
        )
    if normalized_year_month_days and normalized_year_month_weekdays:
        return None, _warning(
            "invalid_recurrence",
            "Use either recurrence_year_month_days or recurrence_year_month_weekdays, not both.",
        )
    if normalized_year_month_days and (normalized_year_days or normalized_year_weeks):
        return None, _warning(
            "invalid_recurrence",
            "Use recurrence_year_month_days only with recurrence_year_months, not recurrence_year_days or recurrence_year_weeks.",
        )
    if normalized_year_month_weekdays and (normalized_year_days or normalized_year_weeks):
        return None, _warning(
            "invalid_recurrence",
            "Use recurrence_year_month_weekdays only with recurrence_year_months, not recurrence_year_days or recurrence_year_weeks.",
        )
    yearly_selector_count = sum(
        1
        for selector in (
            normalized_year_months,
            normalized_year_days,
            normalized_year_weeks,
        )
        if selector
    )
    if yearly_selector_count > 1:
        return None, _warning(
            "invalid_recurrence",
            "Use only one yearly recurrence selector: recurrence_year_months, recurrence_year_days, or recurrence_year_weeks.",
        )
    recurrence_selector_present = bool(
        normalized_weekdays
        or normalized_month_days
        or normalized_month_weekdays
        or normalized_year_months
        or normalized_year_month_days
        or normalized_year_month_weekdays
        or normalized_year_days
        or normalized_year_weeks
    )
    if normalized_set_positions and not recurrence_selector_present:
        return None, _warning(
            "invalid_recurrence",
            "recurrence_set_positions requires another recurrence selector such as recurrence_weekdays, recurrence_month_days, recurrence_month_weekdays, recurrence_year_months, recurrence_year_days, or recurrence_year_weeks.",
        )

    recurrence = {
        "frequency": normalized_frequency,
        "interval": normalized_interval,
        "count": normalized_count,
        "recurrence_present": True,
    }
    if normalized_end_date:
        recurrence["end_date"] = normalized_end_date
    if normalized_unbounded:
        recurrence["unbounded"] = True
    if normalized_weekdays:
        recurrence["weekdays"] = normalized_weekdays
    if normalized_month_days:
        recurrence["month_days"] = normalized_month_days
    if normalized_month_weekdays:
        recurrence["month_weekdays"] = normalized_month_weekdays
    if normalized_year_months:
        recurrence["year_months"] = normalized_year_months
    if normalized_year_month_days:
        recurrence["year_month_days"] = normalized_year_month_days
    if normalized_year_month_weekdays:
        recurrence["year_month_weekdays"] = normalized_year_month_weekdays
    if normalized_year_days:
        recurrence["year_days"] = normalized_year_days
    if normalized_year_weeks:
        recurrence["year_weeks"] = normalized_year_weeks
    if normalized_set_positions:
        recurrence["set_positions"] = normalized_set_positions
    return recurrence, None


def _normalize_recurrence_delete_scope(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip().lower().replace("-", "_")
    if not normalized:
        return "", None
    if normalized not in RECURRENCE_DELETE_SCOPES:
        return "", _warning(
            "unsupported_recurrence_delete_scope",
            "Calendar recurring-event delete supports recurrence_delete_scope=this_event, future_events, or all_events.",
        )
    return normalized, None


def _normalize_recurrence_update_scope(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip().lower().replace("-", "_")
    if not normalized:
        return "", None
    if normalized not in RECURRENCE_UPDATE_SCOPES:
        return "", _warning(
            "unsupported_recurrence_update_scope",
            "Calendar recurring-event update supports recurrence_update_scope=this_event, or future_events for recurrence clear/replacement, title/location/notes, timed reschedule, availability updates, or event URL updates.",
        )
    return normalized, None


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Calendar search requires a non-empty event title query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Calendar search requires at least two letters or digits.",
            )
        ],
    }


def _empty_calendar_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Calendar target selection requires a non-empty title query or include_default=true.",
            )
        ],
    }


def _broad_calendar_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Calendar target selection requires at least two letters or digits.",
            )
        ],
    }


def search_calendar_calendars(
    query: str = "",
    *,
    limit: int = DEFAULT_LIMIT,
    include_default: bool = False,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query and not include_default:
        return _empty_calendar_query_result()
    if query and not has_minimum_query_quality(query):
        return _broad_calendar_query_result()

    bounded_limit = max(1, min(limit, 50))
    response = _calendar_calendars_response(
        query=query,
        limit=bounded_limit,
        include_default=include_default,
        include_all=False,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return _helper_degraded_result(response, content=False)

    results = [_calendar_metadata(calendar) for calendar in response.get("calendars", [])]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "calendar_title",
            "limit": bounded_limit,
            "include_default": include_default,
        },
        "results": results,
        "result_count": len(results),
        "warnings": _safe_warnings(response),
    }


def get_calendar_calendar(
    handle: str,
    *,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, "calendar:calendar"):
        return _invalid_calendar_handle_result()

    response = _calendar_calendars_response(
        query="",
        limit=10000,
        include_default=True,
        include_all=True,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return _helper_degraded_result(response, content=False)

    calendar_id = _resolve_calendar_id(handle, response.get("calendars", []))
    calendar = _find_calendar_by_id(response.get("calendars", []), calendar_id or "")
    if calendar is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "privacy": _privacy(),
            "result": None,
            "warnings": _safe_warnings(response),
        }

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _privacy(),
        "result": _calendar_detail(calendar),
        "result_count": 1,
        "warnings": _safe_warnings(response),
    }


def list_calendar_events_for_calendar(
    handle: str,
    *,
    start_date: str,
    end_date: str,
    limit: int = DEFAULT_LIMIT,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    bounded_limit = max(1, min(limit, 50))
    if not is_opaque_handle(handle, "calendar:calendar"):
        return _calendar_event_list_error(
            [
                _warning(
                    "invalid_handle",
                    "Expected calendar:calendar:v1 opaque handle from calendar selection output.",
                )
            ],
            limit=bounded_limit,
        )

    normalized_start, start_warning = _normalize_event_datetime(
        start_date,
        field="start_date",
        allow_date_only=True,
    )
    if start_warning is not None or normalized_start is None:
        return _calendar_event_list_error([start_warning], limit=bounded_limit)
    normalized_end, end_warning = _normalize_event_datetime(
        end_date,
        field="end_date",
        allow_date_only=True,
    )
    if end_warning is not None or normalized_end is None:
        return _calendar_event_list_error([end_warning], limit=bounded_limit)
    pair_warning = _date_only_pair_warning(
        normalized_start,
        normalized_end,
        first_field="start_date",
        second_field="end_date",
    )
    if pair_warning is not None:
        return _calendar_event_list_error([pair_warning], limit=bounded_limit)
    start_dt = _event_window_datetime(normalized_start)
    end_dt = _event_window_datetime(normalized_end)
    if end_dt <= start_dt:
        return _calendar_event_list_error(
            [
                _warning(
                    "invalid_date_window",
                    "Calendar selected-calendar event listing requires end_date after start_date.",
                )
            ],
            limit=bounded_limit,
        )
    if end_dt - start_dt > timedelta(days=MAX_SELECTED_CALENDAR_EVENT_WINDOW_DAYS):
        return _calendar_event_list_error(
            [
                _warning(
                    "date_window_too_large",
                    f"Calendar selected-calendar event listing is capped at {MAX_SELECTED_CALENDAR_EVENT_WINDOW_DAYS} days per request.",
                )
            ],
            limit=bounded_limit,
        )

    calendars_response = _calendar_calendars_response(
        query="",
        limit=10000,
        include_default=True,
        include_all=True,
        eventkit_runner=eventkit_runner,
    )
    if calendars_response["status"] != "ok":
        return _helper_degraded_result(calendars_response, content=False)

    calendar_id = _resolve_calendar_id(handle, calendars_response.get("calendars", []))
    calendar = _find_calendar_by_id(calendars_response.get("calendars", []), calendar_id or "")
    if calendar is None or calendar_id is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "privacy": _privacy(),
            "authorization_status": calendars_response.get("authorization_status"),
            "calendar": None,
            "results": [],
            "result_count": 0,
            "warnings": _safe_warnings(calendars_response),
        }

    response = _calendar_events_for_calendar_response(
        calendar_id=calendar_id,
        start_date=normalized_start,
        end_date=normalized_end,
        limit=bounded_limit,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "privacy": _privacy(),
            "authorization_status": response.get("authorization_status"),
            "calendar": _calendar_metadata(calendar),
            "results": [],
            "result_count": 0,
            "warnings": _safe_warnings(calendars_response) + _safe_warnings(response),
        }
    if response["status"] != "ok":
        return _helper_degraded_result(response, content=False)

    raw_events = [event for event in response.get("events", []) if isinstance(event, dict)]
    results = [
        _selected_calendar_event_metadata(event)
        for event in raw_events[:bounded_limit]
    ]
    warnings = _safe_warnings(calendars_response) + _safe_warnings(response)
    truncated = bool(response.get("truncated")) or len(raw_events) > bounded_limit
    if truncated:
        warnings.append(
            _warning(
                "events_truncated",
                "Calendar selected-calendar events were truncated to the requested limit.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "selected_calendar_events",
            "calendar_handle": handle,
            "start_date": normalized_start,
            "end_date": normalized_end,
            "limit": bounded_limit,
        },
        "calendar": _calendar_metadata(calendar),
        "results": results,
        "result_count": len(results),
        "truncated": truncated,
        "warnings": warnings,
    }


def request_calendar_full_access(
    *,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    """Trigger the EventKit Calendar full-access prompt from the same Swift helper used for reads."""

    runner = eventkit_runner or _run_eventkit_helper
    if eventkit_runner is None:
        # Real request-access path only: provision a stable signing identity and
        # rebuild the helper stably signed so TCC actually presents the prompt.
        _prepare_eventkit_helper_signing()
    try:
        response = runner({"command": "request_calendar_full_access"}, 190.0)
    except subprocess.TimeoutExpired:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "calendar",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "request_result": "timeout",
            "warnings": [
                _warning(
                    "calendar_access_request_timeout",
                    "Calendar access prompt did not complete before timeout.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "calendar",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "request_result": "unavailable",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Calendar access request is unavailable through the local EventKit helper.",
                )
            ],
        }
    return {
        "schema_version": 1,
        "status": response.get("status", "error"),
        "source": "calendar",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "request_result": response.get("request_result"),
        "warnings": _safe_warnings(response),
    }


def check_calendar_authorization(
    *,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    """Check Calendar EventKit read authorization without prompting or reading events."""

    runner = eventkit_runner or _run_eventkit_helper
    try:
        response = runner({"command": "calendar_authorization_status"}, EVENTKIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "calendar",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "prompts": False,
            "prompt_command": "local-apple-data calendar request-access --json",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Calendar authorization check timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "calendar",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "prompts": False,
            "prompt_command": "local-apple-data calendar request-access --json",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Calendar authorization check is unavailable through the local EventKit helper.",
                )
            ],
        }
    return {
        "schema_version": 1,
        "status": response.get("status", "error"),
        "source": "calendar",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "prompts": False,
        "prompt_command": "local-apple-data calendar request-access --json",
        "warnings": _safe_warnings(response),
    }


def plan_calendar_calendar_change(
    operation: str,
    *,
    source_calendar_handle: str = "",
    calendar_handle: str = "",
    calendar_title: str = "",
    new_calendar_title: str = "",
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    if normalized_operation not in CALENDAR_MANAGEMENT_OPERATIONS:
        return _preview_error(
            [
                _warning(
                    "invalid_operation",
                    "Expected operation create_calendar, rename_calendar, or delete_calendar.",
                )
            ]
        )

    if normalized_operation == "create_calendar":
        return _plan_calendar_calendar_create(
            source_calendar_handle=source_calendar_handle,
            calendar_title=calendar_title,
            new_calendar_title=new_calendar_title,
            calendar_handle=calendar_handle,
            eventkit_runner=eventkit_runner,
        )
    if normalized_operation == "rename_calendar":
        return _plan_calendar_calendar_rename(
            calendar_handle=calendar_handle,
            new_calendar_title=new_calendar_title,
            source_calendar_handle=source_calendar_handle,
            calendar_title=calendar_title,
            eventkit_runner=eventkit_runner,
        )
    if normalized_operation == "delete_calendar":
        return _plan_calendar_calendar_delete(
            calendar_handle=calendar_handle,
            source_calendar_handle=source_calendar_handle,
            calendar_title=calendar_title,
            new_calendar_title=new_calendar_title,
            eventkit_runner=eventkit_runner,
        )
    raise AssertionError(f"unhandled calendar management operation: {normalized_operation}")


def apply_calendar_calendar_change(
    operation: str,
    *,
    source_calendar_handle: str = "",
    calendar_handle: str = "",
    calendar_title: str = "",
    new_calendar_title: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    runner = eventkit_runner or _run_eventkit_helper
    plan = plan_calendar_calendar_change(
        operation,
        source_calendar_handle=source_calendar_handle,
        calendar_handle=calendar_handle,
        calendar_title=calendar_title,
        new_calendar_title=new_calendar_title,
        eventkit_runner=runner,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan.get("preview")
    if not isinstance(preview, dict):
        return _apply_error(
            [_warning("invalid_plan", "Calendar calendar apply requires a valid plan preview.")],
            plan=plan,
        )
    approval = preview.get("approval")
    fingerprint = approval.get("approval_fingerprint") if isinstance(approval, dict) else None
    expected_token = _approval_token(str(fingerprint or ""))
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Calendar calendar apply requires confirm_apply=true.")],
            plan=plan,
        )
    if not approval_token.strip() or approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Calendar calendar apply approval token did not match the plan.")],
            plan=plan,
        )

    resolve_result = _resolve_calendar_for_management_apply(preview, eventkit_runner=runner)
    if resolve_result["status"] != "ok":
        return _apply_error(
            resolve_result["warnings"],
            plan=plan,
            status=resolve_result["status"],
        )

    helper_payload = _calendar_calendar_apply_helper_payload(preview, resolve_result)
    try:
        applied = runner(helper_payload, EVENTKIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("eventkit_timeout", "Calendar calendar apply timed out through EventKit.")],
            plan=plan,
        )
    except (OSError, ValueError):
        return _apply_error(
            [_warning("eventkit_unavailable", "Calendar calendar apply is unavailable through EventKit.")],
            plan=plan,
        )

    if applied.get("status") != "ok":
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("eventkit_apply_failed", "Calendar calendar apply failed.")],
            plan=plan,
            status=str(applied.get("status") or "error"),
            mutation_applied=bool(applied.get("mutation_applied")),
            authorization_status=applied.get("authorization_status"),
        )

    operation_name = str(preview["operation"])
    if operation_name == "delete_calendar":
        helper_read_back = applied.get("read_back")
        if not isinstance(helper_read_back, dict):
            return _apply_error(
                [
                    _warning(
                        "read_back_unavailable",
                        "Calendar delete succeeded but absence read-back was unavailable.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        if (
            helper_read_back.get("calendar_deleted_verified") is not True
            or helper_read_back.get("calendar_absent_verified") is not True
            or helper_read_back.get("calendar_empty_verified") is not True
        ):
            return _apply_error(
                [
                    _warning(
                        "calendar_delete_read_back_mismatch",
                        "Calendar delete succeeded but absence proof did not match the approved state.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back = {
            "calendar_handle": preview["target"]["calendar_handle"],
            "calendar_title": preview["target"]["calendar_title"],
            "synthetic_title_verified": True,
            "calendar_empty_verified": True,
            "calendar_deleted_verified": True,
            "calendar_absent_verified": True,
        }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": _mutation_privacy(content_inspected=False),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": operation_name,
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": read_back,
            "result_count": 0,
            "warnings": _safe_warnings(applied),
        }

    calendar = applied.get("calendar")
    if not isinstance(calendar, dict):
        return _apply_error(
            [
                _warning(
                    "read_back_unavailable",
                    "Calendar calendar apply succeeded but read-back was unavailable.",
                )
            ],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )
    read_back = _calendar_detail(calendar)
    expected_title = (
        preview["proposed"]["calendar_title"]
        if operation_name == "create_calendar"
        else preview["proposed"]["new_calendar_title"]
    )
    if read_back.get("title") != expected_title:
        return _apply_error(
            [
                _warning(
                    "calendar_title_read_back_mismatch",
                    "Calendar calendar apply succeeded but title read-back did not match the approved value.",
                )
            ],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )
    if operation_name == "create_calendar":
        read_back["source_calendar_handle"] = preview["target"]["source_calendar_handle"]
        read_back["source_calendar_verified"] = True
    else:
        helper_read_back = applied.get("read_back")
        if not isinstance(helper_read_back, dict):
            return _apply_error(
                [
                    _warning(
                        "read_back_unavailable",
                        "Calendar calendar apply succeeded but read-back was unavailable.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        if (
            helper_read_back.get("calendar_renamed_verified") is not True
            or helper_read_back.get("calendar_empty_verified") is not True
            or int(read_back.get("event_count_in_safety_window") or 0) != 0
        ):
            return _apply_error(
                [
                    _warning(
                        "calendar_rename_read_back_mismatch",
                        "Calendar calendar rename succeeded but read-back safety proof did not match the approved state.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["calendar_handle"] = preview["target"]["calendar_handle"]
        read_back["synthetic_title_verified"] = True
        read_back["empty_calendar_verified"] = True

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _mutation_privacy(content_inspected=False),
        "authorization_status": applied.get("authorization_status"),
        "mode": "apply",
        "operation": operation_name,
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": _safe_warnings(applied),
    }


def _plan_calendar_calendar_create(
    *,
    source_calendar_handle: str,
    calendar_title: str,
    new_calendar_title: str,
    calendar_handle: str,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    if calendar_handle.strip() or new_calendar_title.strip():
        return _preview_error(
            [
                _warning(
                    "unexpected_calendar_field",
                    "Calendar create-calendar accepts source_calendar_handle and calendar_title only.",
                )
            ]
        )
    normalized_title, title_warning = _normalize_calendar_test_title(
        calendar_title,
        field="calendar_title",
    )
    if title_warning is not None:
        return _preview_error([title_warning])
    source_result = _resolve_calendar_for_management(
        source_calendar_handle,
        eventkit_runner=eventkit_runner,
        include_safety_counts=False,
    )
    if source_result["status"] != "ok":
        return _preview_error(source_result["warnings"])
    source_calendar = source_result["calendar"]
    source_id = str(source_calendar.get("source_id") or "")
    source_warning = _calendar_management_source_warning(source_calendar)
    if source_warning is not None:
        return _preview_error([source_warning])
    if _calendar_title_exists_in_source(
        source_result["calendars"],
        source_id=source_id,
        title=normalized_title,
    ):
        return _preview_error(
            [_warning("calendar_already_exists", "A calendar with that title already exists in the selected source.")]
        )

    target = {
        "source_calendar_handle": source_calendar_handle.strip(),
        "source_calendar_title": str(source_calendar.get("title") or ""),
        "source_calendar_safe_sha256": _calendar_safe_sha256(source_calendar),
        "source_type": str(source_calendar.get("source_type") or ""),
    }
    proposed = {
        "calendar_title": normalized_title,
        "synthetic_title_required": CALENDAR_TEST_PREFIX,
    }
    return _calendar_calendar_plan("create_calendar", target, proposed)


def _plan_calendar_calendar_rename(
    *,
    calendar_handle: str,
    new_calendar_title: str,
    source_calendar_handle: str,
    calendar_title: str,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    if source_calendar_handle.strip() or calendar_title.strip():
        return _preview_error(
            [
                _warning(
                    "unexpected_calendar_field",
                    "Calendar rename-calendar accepts calendar_handle and new_calendar_title only.",
                )
            ]
        )
    normalized_title, title_warning = _normalize_calendar_test_title(
        new_calendar_title,
        field="new_calendar_title",
    )
    if title_warning is not None:
        return _preview_error([title_warning])
    target_result = _resolve_calendar_for_management(
        calendar_handle,
        eventkit_runner=eventkit_runner,
        include_safety_counts=True,
    )
    if target_result["status"] != "ok":
        return _preview_error(target_result["warnings"])
    calendar = target_result["calendar"]
    safety_warning = _calendar_management_target_warning(
        calendar,
        require_empty=True,
        require_event_only=False,
    )
    if safety_warning is not None:
        return _preview_error([safety_warning])
    if _calendar_title_exists_in_source(
        target_result["calendars"],
        source_id=str(calendar.get("source_id") or ""),
        title=normalized_title,
        excluding_calendar_id=str(calendar.get("calendar_id") or ""),
    ):
        return _preview_error(
            [_warning("calendar_already_exists", "A calendar with that title already exists in the selected source.")]
        )

    target = _calendar_management_target(calendar_handle, calendar)
    proposed = {
        "new_calendar_title": normalized_title,
        "synthetic_title_required": CALENDAR_TEST_PREFIX,
    }
    return _calendar_calendar_plan("rename_calendar", target, proposed)


def _plan_calendar_calendar_delete(
    *,
    calendar_handle: str,
    source_calendar_handle: str,
    calendar_title: str,
    new_calendar_title: str,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    if source_calendar_handle.strip() or calendar_title.strip() or new_calendar_title.strip():
        return _preview_error(
            [
                _warning(
                    "unexpected_calendar_field",
                    "Calendar delete-calendar accepts calendar_handle only.",
                )
            ]
        )
    target_result = _resolve_calendar_for_management(
        calendar_handle,
        eventkit_runner=eventkit_runner,
        include_safety_counts=True,
    )
    if target_result["status"] != "ok":
        return _preview_error(target_result["warnings"])
    calendar = target_result["calendar"]
    safety_warning = _calendar_management_target_warning(
        calendar,
        require_empty=True,
        require_event_only=True,
    )
    if safety_warning is not None:
        return _preview_error([safety_warning])
    target = _calendar_management_target(calendar_handle, calendar)
    proposed = {
        "delete_requested": True,
        "synthetic_title_required": CALENDAR_TEST_PREFIX,
        "absence_proof_required": True,
    }
    return _calendar_calendar_plan("delete_calendar", target, proposed)


def _calendar_calendar_plan(
    operation: str,
    target: dict[str, Any],
    proposed: dict[str, Any],
) -> dict[str, Any]:
    fingerprint_payload = {
        "operation": operation,
        "target": target,
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": operation,
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _calendar_calendar_apply_helper_payload(
    preview: dict[str, Any],
    resolve_result: dict[str, Any],
) -> dict[str, Any]:
    operation = str(preview["operation"])
    target = preview["target"]
    proposed = preview["proposed"]
    payload: dict[str, Any] = {
        "command": "calendar_calendar_apply_change",
        "operation": operation,
    }
    if operation == "create_calendar":
        payload.update(
            {
                "source_calendar_id": resolve_result["calendar_id"],
                "calendar_title": proposed["calendar_title"],
            }
        )
    else:
        payload.update(
            {
                "calendar_id": resolve_result["calendar_id"],
                "expected_calendar_title": target["calendar_title"],
                "expected_source_type": target["source_type"],
                "expected_empty_calendar": True,
            }
        )
        if operation == "rename_calendar":
            payload["new_calendar_title"] = proposed["new_calendar_title"]
        if operation == "delete_calendar":
            payload["delete_calendar"] = True
    return payload


def _resolve_calendar_for_management_apply(
    preview: dict[str, Any],
    *,
    eventkit_runner: EventKitRunner,
) -> dict[str, Any]:
    operation = str(preview["operation"])
    target = preview["target"]
    if operation == "create_calendar":
        handle = str(target["source_calendar_handle"])
        expected_sha = str(target["source_calendar_safe_sha256"])
        include_safety_counts = False
    else:
        handle = str(target["calendar_handle"])
        expected_sha = str(target["calendar_safe_sha256"])
        include_safety_counts = True
    resolved = _resolve_calendar_for_management(
        handle,
        eventkit_runner=eventkit_runner,
        include_safety_counts=include_safety_counts,
    )
    if resolved["status"] != "ok":
        return resolved
    calendar = resolved["calendar"]
    current_sha = _calendar_safe_sha256(calendar)
    if current_sha != expected_sha:
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "current_calendar_changed",
                    "Calendar target changed since the approved plan; re-plan before applying.",
                )
            ],
        }
    if operation == "create_calendar":
        source_warning = _calendar_management_source_warning(calendar)
        if source_warning is not None:
            return {"status": "error", "warnings": [source_warning]}
    if operation != "create_calendar":
        safety_warning = _calendar_management_target_warning(
            calendar,
            require_empty=True,
            require_event_only=operation == "delete_calendar",
        )
        if safety_warning is not None:
            return {"status": "error", "warnings": [safety_warning]}
    return {
        "status": "ok",
        "calendar_id": str(calendar.get("calendar_id") or ""),
        "calendar": calendar,
        "warnings": [],
    }


def _resolve_calendar_for_management(
    handle: str,
    *,
    eventkit_runner: EventKitRunner | None,
    include_safety_counts: bool,
) -> dict[str, Any]:
    normalized_handle = handle.strip()
    if not is_opaque_handle(normalized_handle, "calendar:calendar"):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "invalid_calendar_handle",
                    "Expected calendar:calendar:v1 opaque handle from calendar selection output.",
                )
            ],
        }
    response = _calendar_calendars_response(
        query="",
        limit=10000,
        include_default=True,
        include_all=True,
        include_safety_counts=include_safety_counts,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return {
            "status": "degraded",
            "warnings": _safe_warnings(response),
        }
    calendar_id = _resolve_calendar_id(normalized_handle, response.get("calendars", []))
    calendar = _find_calendar_by_id(response.get("calendars", []), calendar_id or "")
    if calendar is None:
        return {
            "status": "not_found",
            "warnings": [_warning("target_calendar_not_found", "Calendar target was not found.")],
        }
    return {
        "status": "ok",
        "calendar": calendar,
        "calendars": response.get("calendars", []),
        "warnings": _safe_warnings(response),
    }


def _normalize_calendar_test_title(value: str, *, field: str) -> tuple[str, dict[str, str] | None]:
    normalized, warning = _bounded_preview_value(
        value,
        field=field,
        max_chars=MAX_PREVIEW_CALENDAR_CHARS,
        required=True,
    )
    if warning is not None:
        return "", warning
    if not normalized.startswith(CALENDAR_TEST_PREFIX):
        return "", _warning(
            "non_synthetic_calendar_title",
            f"Calendar calendar management is limited to {CALENDAR_TEST_PREFIX}* titles.",
        )
    return normalized, None


def _calendar_management_target_warning(
    calendar: dict[str, Any],
    *,
    require_empty: bool,
    require_event_only: bool = False,
) -> dict[str, str] | None:
    title = str(calendar.get("title") or "")
    if not title.startswith(CALENDAR_TEST_PREFIX):
        return _warning(
            "non_synthetic_calendar_title",
            f"Calendar calendar management is limited to {CALENDAR_TEST_PREFIX}* titles.",
        )
    if calendar.get("is_default_calendar"):
        return _warning("default_calendar_refused", "Calendar calendar management refuses default calendars.")
    if calendar.get("is_subscribed") or calendar.get("is_immutable"):
        return _warning(
            "unsupported_calendar_state",
            "Calendar calendar management refuses subscribed or immutable calendars.",
        )
    if not calendar.get("allows_content_modifications"):
        return _warning(
            "target_calendar_not_writable",
            "Calendar target does not allow changes.",
        )
    if require_event_only and _calendar_allowed_entity_types(calendar) != ["event"]:
        return _warning(
            "unsupported_calendar_state",
            "Calendar delete-calendar refuses calendars that may contain reminders.",
        )
    if require_empty and int(calendar.get("event_count_in_safety_window") or 0) != 0:
        return _warning(
            "calendar_not_empty",
            "Calendar calendar management refuses non-empty calendars.",
        )
    return None


def _calendar_management_source_warning(calendar: dict[str, Any]) -> dict[str, str] | None:
    source_type = str(calendar.get("source_type") or "")
    if source_type in {"subscribed", "birthdays"} or calendar.get("is_subscribed") or calendar.get("is_immutable"):
        return _warning(
            "unsupported_calendar_source",
            "Calendar create-calendar refuses subscribed, birthday, or immutable sources.",
        )
    if not calendar.get("allows_content_modifications"):
        return _warning(
            "target_calendar_not_writable",
            "Calendar source target does not allow changes.",
        )
    return None


def _calendar_allowed_entity_types(calendar: dict[str, Any]) -> list[str]:
    value = calendar.get("allowed_entity_types")
    if not isinstance(value, list):
        return []
    names = sorted(str(item) for item in value if str(item))
    return names


def _calendar_management_target(handle: str, calendar: dict[str, Any]) -> dict[str, Any]:
    return {
        "calendar_handle": handle.strip(),
        "calendar_title": str(calendar.get("title") or ""),
        "calendar_safe_sha256": _calendar_safe_sha256(calendar),
        "source_type": str(calendar.get("source_type") or ""),
        "source_safe_sha256": _calendar_source_safe_sha256(calendar),
        "event_count_in_safety_window": int(calendar.get("event_count_in_safety_window") or 0),
        "safety_window_start": str(calendar.get("safety_window_start") or ""),
        "safety_window_end": str(calendar.get("safety_window_end") or ""),
    }


def _calendar_title_exists_in_source(
    calendars: Any,
    *,
    source_id: str,
    title: str,
    excluding_calendar_id: str = "",
) -> bool:
    if not isinstance(calendars, list):
        return False
    for calendar in calendars:
        if not isinstance(calendar, dict):
            continue
        if excluding_calendar_id and str(calendar.get("calendar_id") or "") == excluding_calendar_id:
            continue
        if str(calendar.get("source_id") or "") != source_id:
            continue
        if str(calendar.get("title") or "") == title:
            return True
    return False


def search_calendar_events(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
    max_scan_events: int = DEFAULT_MAX_SCAN_EVENTS,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, 50))
    response = _calendar_events_response(
        query=query,
        limit=bounded_limit,
        days_back=days_back,
        days_forward=days_forward,
        max_scan_events=max_scan_events,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return _helper_degraded_result(response, content=False)

    results = [_event_metadata(event, include_alarm_offsets=False) for event in response.get("events", [])]

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "title",
            "limit": bounded_limit,
            "days_back": _bounded_days(days_back),
            "days_forward": _bounded_days(days_forward),
            "max_scan_events": _bounded_max_scan(max_scan_events),
        },
        "results": results,
        "result_count": len(results),
        "warnings": _safe_warnings(response),
    }


def get_calendar_event(
    handle: str,
    *,
    max_chars: int = DEFAULT_CONTENT_CHARS,
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
    max_scan_events: int = DEFAULT_MAX_SCAN_EVENTS,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, "calendar:event"):
        return _invalid_handle_result()

    response = _calendar_events_response(
        query="",
        limit=_bounded_max_scan(max_scan_events),
        days_back=days_back,
        days_forward=days_forward,
        max_scan_events=max_scan_events,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return _helper_degraded_result(response, content=True)

    event_ref = _resolve_event_reference(handle, response.get("events", []))
    if event_ref is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": _safe_warnings(response),
        }

    runner = eventkit_runner or _run_eventkit_helper
    detail_payload = {"command": "calendar_event_by_id", "event_id": event_ref["event_id"]}
    if event_ref.get("start_date") and event_ref.get("end_date"):
        detail_payload = {
            "command": "calendar_event_by_occurrence",
            "event_id": event_ref["event_id"],
            "start_date": event_ref["start_date"],
            "end_date": event_ref["end_date"],
        }
    try:
        detail = runner(
            detail_payload,
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _content_unavailable_result(
            None,
            "eventkit_read_error",
            "Calendar event could not be read safely.",
        )

    if detail.get("status") == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": _safe_warnings(detail),
        }
    if detail.get("status") != "ok":
        return _helper_degraded_result(detail, content=True)

    event = detail.get("event")
    if not isinstance(event, dict):
        return _content_unavailable_result(
            None,
            "eventkit_read_error",
            "Calendar event could not be read safely.",
        )

    result = _event_metadata(event, include_alarm_offsets=True, include_time_zone=True)
    notes_text, notes_truncated = _bounded_text(
        str(event.get("notes") or ""),
        max_chars,
    )
    location_text, location_truncated = _bounded_text(
        str(event.get("location") or ""),
        min(max_chars, 1000),
    )
    result.update(
        {
            "location": location_text,
            "location_truncated": location_truncated,
            "notes_text": notes_text,
            "notes_chars": len(notes_text),
            "notes_truncated": notes_truncated,
        }
    )
    warnings = _safe_warnings(response) + _safe_warnings(detail)
    if notes_truncated:
        warnings.append(
            _warning(
                "content_truncated",
                "Calendar event notes were truncated to the requested limit.",
            )
        )
    if location_truncated:
        warnings.append(
            _warning(
                "location_truncated",
                "Calendar event location was truncated to the requested limit.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": warnings,
    }


def list_calendar_participants(
    handle: str,
    *,
    limit: int = DEFAULT_LIMIT,
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
    max_scan_events: int = DEFAULT_MAX_SCAN_EVENTS,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    bounded_limit = max(1, min(limit, 50))
    event, error, warnings, authorization_status = _calendar_event_for_participants(
        handle,
        days_back=days_back,
        days_forward=days_forward,
        max_scan_events=max_scan_events,
        detail=False,
        eventkit_runner=eventkit_runner,
    )
    if error is not None:
        return error

    participants = _calendar_participants(event or {})
    results = [
        _calendar_participant_metadata(event or {}, participant, include_detail=False)
        for participant in participants[:bounded_limit]
    ]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _participant_privacy(detail_returned=False),
        "authorization_status": authorization_status,
        "query": {"scope": "event_participants", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }
    if len(participants) > bounded_limit:
        payload["warnings"].append(
            _warning(
                "participants_truncated",
                "Calendar participants were truncated to the requested limit.",
            )
        )
    return payload


def get_calendar_participant(
    event_handle: str,
    participant_handle: str,
    *,
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
    max_scan_events: int = DEFAULT_MAX_SCAN_EVENTS,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(participant_handle, CALENDAR_PARTICIPANT_HANDLE_PREFIX):
        return _calendar_participant_error(
            [_warning("invalid_handle", "Expected calendar:participant:v1 opaque handle from participant list output.")],
            detail=True,
        )

    event, error, warnings, authorization_status = _calendar_event_for_participants(
        event_handle,
        days_back=days_back,
        days_forward=days_forward,
        max_scan_events=max_scan_events,
        detail=True,
        eventkit_runner=eventkit_runner,
    )
    if error is not None:
        return error

    participant = _find_calendar_participant(event or {}, participant_handle)
    if participant is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "privacy": _participant_privacy(detail_returned=False),
            "authorization_status": authorization_status,
            "result": None,
            "warnings": warnings,
        }

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _participant_privacy(detail_returned=True),
        "authorization_status": authorization_status,
        "result": _calendar_participant_metadata(event or {}, participant, include_detail=True),
        "result_count": 1,
        "warnings": warnings,
    }


def plan_calendar_change(
    operation: str,
    *,
    title: str = "",
    calendar_title: str = "",
    calendar_handle: str = "",
    use_default_calendar: bool = False,
    target_calendar_handle: str = "",
    start_date: str = "",
    end_date: str = "",
    time_zone: str = "",
    all_day: bool = False,
    availability: str = "",
    alarm_offsets_minutes: list[int] | None = None,
    alarm_absolute_dates: list[str] | None = None,
    alarm_sound_name: str = "",
    alarm_email_address: str = "",
    alarm_proximity: str = "",
    alarm_structured_location: dict[str, Any] | None = None,
    recurrence_frequency: str = "",
    recurrence_interval: int | None = None,
    recurrence_count: int | None = None,
    recurrence_end_date: str = "",
    recurrence_unbounded: bool = False,
    recurrence_weekdays: list[str | int] | str | None = None,
    recurrence_month_days: list[int] | str | None = None,
    recurrence_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_months: list[int] | str | None = None,
    recurrence_year_month_days: list[int] | str | None = None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_days: list[int] | str | None = None,
    recurrence_year_weeks: list[int] | str | None = None,
    recurrence_set_positions: list[int] | str | None = None,
    recurrence_delete_scope: str = "",
    recurrence_update_scope: str = "",
    clear_recurrence: bool = False,
    event_url: str = "",
    clear_event_url: bool = False,
    location: str = "",
    structured_location: dict[str, Any] | None = None,
    clear_structured_location: bool = False,
    notes: str = "",
    handle: str = "",
    expected_title: str = "",
    expected_calendar_title: str = "",
    expected_start_date: str = "",
    expected_end_date: str = "",
    expected_time_zone: str = "",
    expected_all_day: bool = False,
    expected_availability: str = "",
    expected_alarm_offsets_minutes: list[int] | None = None,
    expected_alarm_absolute_dates: list[str] | None = None,
    expected_alarm_sound_name: str = "",
    expected_alarm_email_address_sha256: str = "",
    expected_alarm_proximity: str = "",
    expected_alarm_structured_location: dict[str, Any] | None = None,
    expected_event_url_present: bool = False,
    expected_event_url_sha256: str = "",
    expected_location: str = "",
    expected_structured_location: dict[str, Any] | None = None,
    expected_notes: str = "",
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation create, update, or delete."))
        return _preview_error(warnings)
    if normalized_operation == "create" and (
        expected_event_url_present is not False or expected_event_url_sha256 != ""
    ):
        warnings.append(
            _warning(
                "unsupported_expected_state_for_operation",
                "Calendar expected_event_url fields are supported only for update and delete operations.",
            )
        )
        return _preview_error(warnings)
    normalized_clear_event_url, clear_event_url_warning = _normalize_bool_flag(
        clear_event_url,
        field="clear_event_url",
    )
    if clear_event_url_warning is not None:
        warnings.append(clear_event_url_warning)
    normalized_clear_recurrence, clear_recurrence_warning = _normalize_bool_flag(
        clear_recurrence,
        field="clear_recurrence",
    )
    if clear_recurrence_warning is not None:
        warnings.append(clear_recurrence_warning)
    normalized_clear_structured_location, clear_structured_location_warning = _normalize_bool_flag(
        clear_structured_location,
        field="clear_structured_location",
    )
    if clear_structured_location_warning is not None:
        warnings.append(clear_structured_location_warning)
    if event_url != "" and normalized_clear_event_url:
        warnings.append(
            _warning(
                "conflicting_event_url_fields",
                "Use either event_url or clear_event_url, not both.",
            )
        )
        return _preview_error(warnings)
    if normalized_operation != "update" and normalized_clear_event_url:
        warnings.append(
            _warning(
                "unsupported_event_url_for_operation",
                "Calendar clear_event_url is supported only during update operations.",
            )
        )
        return _preview_error(warnings)
    if normalized_operation != "update" and normalized_clear_recurrence:
        warnings.append(
            _warning(
                "unsupported_recurrence_for_operation",
                "Calendar clear_recurrence is supported only during update operations.",
            )
        )
        return _preview_error(warnings)
    if normalized_operation != "update" and normalized_clear_structured_location:
        warnings.append(
            _warning(
                "unsupported_structured_location_for_operation",
                "Calendar clear_structured_location is supported only during update operations.",
            )
        )
        return _preview_error(warnings)
    if structured_location is not None and normalized_clear_structured_location:
        warnings.append(
            _warning(
                "conflicting_structured_location_fields",
                "Use either structured_location or clear_structured_location, not both.",
            )
        )
        return _preview_error(warnings)
    has_recurrence_fields = bool(
        recurrence_frequency.strip()
        or recurrence_interval is not None
        or recurrence_count is not None
        or str(recurrence_end_date or "").strip()
        or recurrence_unbounded
        or recurrence_weekdays
        or recurrence_month_days
        or recurrence_month_weekdays
        or recurrence_year_months
        or recurrence_year_month_days
        or recurrence_year_month_weekdays
        or recurrence_year_days
        or recurrence_year_weeks
        or recurrence_set_positions
    )
    if normalized_clear_recurrence and has_recurrence_fields:
        warnings.append(
            _warning(
                "conflicting_recurrence_fields",
                "Use either recurrence fields or clear_recurrence, not both.",
            )
        )
        return _preview_error(warnings)
    if normalized_operation == "delete" and event_url != "":
        warnings.append(
            _warning(
                "unsupported_event_url_for_operation",
                "Calendar event_url can be set only during create or update operations.",
            )
        )
        return _preview_error(warnings)
    if warnings:
        return _preview_error(warnings)
    if normalized_operation == "delete" and has_recurrence_fields:
        warnings.append(
            _warning(
                "unsupported_recurrence_for_operation",
                "Calendar recurrence cannot be changed during delete operations.",
            )
        )
        return _preview_error(warnings)
    normalized_recurrence_delete_scope, recurrence_delete_scope_warning = (
        _normalize_recurrence_delete_scope(recurrence_delete_scope)
    )
    if recurrence_delete_scope_warning is not None:
        warnings.append(recurrence_delete_scope_warning)
    if normalized_operation != "delete" and normalized_recurrence_delete_scope:
        warnings.append(
            _warning(
                "unsupported_recurrence_delete_scope",
                "Calendar recurrence_delete_scope is supported only during delete operations.",
            )
        )
        return _preview_error(warnings)
    if warnings:
        return _preview_error(warnings)
    normalized_recurrence_update_scope, recurrence_update_scope_warning = (
        _normalize_recurrence_update_scope(recurrence_update_scope)
    )
    if recurrence_update_scope_warning is not None:
        warnings.append(recurrence_update_scope_warning)
    if normalized_operation != "update" and normalized_recurrence_update_scope:
        warnings.append(
            _warning(
                "unsupported_recurrence_update_scope",
                "Calendar recurrence_update_scope is supported only during update operations.",
            )
        )
        return _preview_error(warnings)
    if warnings:
        return _preview_error(warnings)
    if normalized_operation != "create" and use_default_calendar:
        warnings.append(
            _warning(
                "unsupported_default_calendar_for_operation",
                "Default-calendar targeting is currently supported only for create operations.",
            )
        )
        return _preview_error(warnings)

    if normalized_operation == "update":
        return _plan_calendar_update(
            title=title,
            start_date=start_date,
            end_date=end_date,
            time_zone=time_zone,
            all_day=all_day,
            availability=availability,
            alarm_offsets_minutes=alarm_offsets_minutes,
            alarm_absolute_dates=alarm_absolute_dates,
            alarm_sound_name=alarm_sound_name,
            alarm_email_address=alarm_email_address,
            alarm_proximity=alarm_proximity,
            alarm_structured_location=alarm_structured_location,
            recurrence_frequency=recurrence_frequency,
            recurrence_interval=recurrence_interval,
            recurrence_count=recurrence_count,
            recurrence_end_date=recurrence_end_date,
            recurrence_unbounded=recurrence_unbounded,
            recurrence_weekdays=recurrence_weekdays,
            recurrence_month_days=recurrence_month_days,
            recurrence_month_weekdays=recurrence_month_weekdays,
            recurrence_year_months=recurrence_year_months,
            recurrence_year_month_days=recurrence_year_month_days,
            recurrence_year_month_weekdays=recurrence_year_month_weekdays,
            recurrence_year_days=recurrence_year_days,
            recurrence_year_weeks=recurrence_year_weeks,
            recurrence_set_positions=recurrence_set_positions,
            recurrence_update_scope=normalized_recurrence_update_scope,
            clear_recurrence=normalized_clear_recurrence,
            event_url=event_url,
            clear_event_url=normalized_clear_event_url,
            location=location,
            structured_location=structured_location,
            clear_structured_location=normalized_clear_structured_location,
            notes=notes,
            handle=handle,
            target_calendar_handle=target_calendar_handle,
            expected_title=expected_title,
            expected_calendar_title=expected_calendar_title,
            expected_start_date=expected_start_date,
            expected_end_date=expected_end_date,
            expected_time_zone=expected_time_zone,
            expected_all_day=expected_all_day,
            expected_availability=expected_availability,
            expected_alarm_offsets_minutes=expected_alarm_offsets_minutes,
            expected_alarm_absolute_dates=expected_alarm_absolute_dates,
            expected_alarm_sound_name=expected_alarm_sound_name,
            expected_alarm_email_address_sha256=expected_alarm_email_address_sha256,
            expected_alarm_proximity=expected_alarm_proximity,
            expected_alarm_structured_location=expected_alarm_structured_location,
            expected_event_url_present=expected_event_url_present,
            expected_event_url_sha256=expected_event_url_sha256,
            expected_location=expected_location,
            expected_structured_location=expected_structured_location,
            expected_notes=expected_notes,
            eventkit_runner=eventkit_runner,
        )
    if normalized_operation == "delete":
        return _plan_calendar_delete(
            handle=handle,
            expected_title=expected_title,
            expected_calendar_title=expected_calendar_title,
            expected_start_date=expected_start_date,
            expected_end_date=expected_end_date,
            expected_time_zone=expected_time_zone,
            expected_all_day=expected_all_day,
            expected_availability=expected_availability,
            expected_alarm_offsets_minutes=expected_alarm_offsets_minutes,
            expected_alarm_absolute_dates=expected_alarm_absolute_dates,
            expected_alarm_sound_name=expected_alarm_sound_name,
            expected_alarm_email_address_sha256=expected_alarm_email_address_sha256,
            expected_alarm_proximity=expected_alarm_proximity,
            expected_alarm_structured_location=expected_alarm_structured_location,
            expected_event_url_present=expected_event_url_present,
            expected_event_url_sha256=expected_event_url_sha256,
            expected_location=expected_location,
            expected_structured_location=expected_structured_location,
            expected_notes=expected_notes,
            recurrence_delete_scope=normalized_recurrence_delete_scope,
            eventkit_runner=eventkit_runner,
        )

    return _plan_calendar_create(
        title=title,
        calendar_title=calendar_title,
        calendar_handle=calendar_handle,
        use_default_calendar=use_default_calendar,
        start_date=start_date,
        end_date=end_date,
        time_zone=time_zone,
        all_day=all_day,
        availability=availability,
        alarm_offsets_minutes=alarm_offsets_minutes,
        alarm_absolute_dates=alarm_absolute_dates,
        alarm_sound_name=alarm_sound_name,
        alarm_email_address=alarm_email_address,
        alarm_proximity=alarm_proximity,
        alarm_structured_location=alarm_structured_location,
        recurrence_frequency=recurrence_frequency,
        recurrence_interval=recurrence_interval,
        recurrence_count=recurrence_count,
        recurrence_end_date=recurrence_end_date,
        recurrence_unbounded=recurrence_unbounded,
        recurrence_weekdays=recurrence_weekdays,
        recurrence_month_days=recurrence_month_days,
        recurrence_month_weekdays=recurrence_month_weekdays,
        recurrence_year_months=recurrence_year_months,
        recurrence_year_month_days=recurrence_year_month_days,
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
        recurrence_year_days=recurrence_year_days,
        recurrence_year_weeks=recurrence_year_weeks,
        recurrence_set_positions=recurrence_set_positions,
        event_url=event_url,
        location=location,
        structured_location=structured_location,
        notes=notes,
        eventkit_runner=eventkit_runner,
    )


def _plan_calendar_create(
    *,
    title: str,
    calendar_title: str,
    calendar_handle: str,
    use_default_calendar: bool,
    start_date: str,
    end_date: str,
    time_zone: str,
    all_day: bool,
    availability: str,
    alarm_offsets_minutes: list[int] | None,
    alarm_absolute_dates: list[str] | None,
    alarm_sound_name: str,
    alarm_email_address: str,
    alarm_proximity: str,
    alarm_structured_location: dict[str, Any] | None,
    recurrence_frequency: str,
    recurrence_interval: int | None,
    recurrence_count: int | None,
    recurrence_end_date: str,
    recurrence_unbounded: bool,
    recurrence_weekdays: list[str | int] | str | None,
    recurrence_month_days: list[int] | str | None,
    recurrence_month_weekdays: list[dict[str, Any]] | str | None,
    recurrence_year_months: list[int] | str | None,
    recurrence_year_month_days: list[int] | str | None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | str | None,
    recurrence_year_days: list[int] | str | None,
    recurrence_year_weeks: list[int] | str | None,
    recurrence_set_positions: list[int] | str | None,
    event_url: str,
    location: str,
    structured_location: dict[str, Any] | None,
    notes: str,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    normalized_title, title_warning = _bounded_preview_value(
        title,
        field="title",
        max_chars=MAX_PREVIEW_TITLE_CHARS,
        required=True,
    )
    if title_warning is not None:
        warnings.append(title_warning)

    normalized_use_default_calendar, default_calendar_warning = _normalize_bool_flag(
        use_default_calendar,
        field="use_default_calendar",
    )
    if default_calendar_warning is not None:
        warnings.append(default_calendar_warning)

    normalized_calendar_handle = calendar_handle.strip()
    normalized_calendar, calendar_warning = _bounded_preview_value(
        calendar_title,
        field="calendar_title",
        max_chars=MAX_PREVIEW_CALENDAR_CHARS,
        required=not bool(normalized_calendar_handle or normalized_use_default_calendar),
    )
    if calendar_warning is not None:
        warnings.append(calendar_warning)

    if normalized_calendar_handle and not is_opaque_handle(
        normalized_calendar_handle, "calendar:calendar"
    ):
        warnings.append(
            _warning(
                "invalid_calendar_handle",
                "Expected calendar:calendar:v1 opaque handle from calendar selection output.",
            )
        )
    if normalized_calendar and normalized_calendar_handle:
        warnings.append(
            _warning(
                "conflicting_target_calendar",
                "Use either calendar_title or calendar_handle, not both.",
            )
        )
    if normalized_use_default_calendar and (normalized_calendar or normalized_calendar_handle):
        warnings.append(
            _warning(
                "conflicting_target_calendar",
                "Use only one Calendar target: calendar_title, calendar_handle, or use_default_calendar.",
            )
        )
    normalized_location, location_warning = _bounded_preview_value(
        location,
        field="location",
        max_chars=MAX_LOCATION_CHARS,
        required=False,
    )
    if location_warning is not None:
        warnings.append(location_warning)
    normalized_structured_location, structured_location_warning = (
        _normalize_structured_location(
            structured_location,
            field="structured_location",
        )
    )
    if structured_location_warning is not None:
        warnings.append(structured_location_warning)
    if normalized_structured_location:
        if normalized_location and normalized_location != normalized_structured_location["title"]:
            warnings.append(
                _warning(
                    "conflicting_location_fields",
                    "Calendar location must match structured_location.title when both are provided.",
                )
            )
        normalized_location = normalized_structured_location["title"]

    normalized_notes, notes_warning = _bounded_preview_value(
        notes,
        field="notes",
        max_chars=MAX_CONTENT_CHARS,
        required=False,
    )
    if notes_warning is not None:
        warnings.append(notes_warning)

    start_date_only = _is_date_only_input(start_date)
    end_date_only = _is_date_only_input(end_date)
    date_pair_warning = _date_only_pair_warning(
        start_date,
        end_date,
        first_field="start_date",
        second_field="end_date",
    )
    if date_pair_warning is not None:
        warnings.append(date_pair_warning)

    normalized_start, start_warning = _normalize_event_datetime(
        start_date,
        field="start_date",
        allow_date_only=True,
    )
    if start_warning is not None:
        warnings.append(start_warning)

    normalized_end, end_warning = _normalize_event_datetime(
        end_date,
        field="end_date",
        allow_date_only=True,
    )
    if end_warning is not None:
        warnings.append(end_warning)

    if normalized_start and normalized_end and date_pair_warning is None:
        start_dt = datetime.fromisoformat(normalized_start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(normalized_end.replace("Z", "+00:00"))
        if end_dt <= start_dt:
            warnings.append(
                _warning("invalid_time_range", "Calendar event end_date must be after start_date.")
            )

    normalized_time_zone, time_zone_warning = _normalize_time_zone(
        time_zone,
        field="time_zone",
    )
    if time_zone_warning is not None:
        warnings.append(time_zone_warning)

    normalized_all_day, all_day_warning = _normalize_bool_flag(all_day, field="all_day")
    if all_day_warning is not None:
        warnings.append(all_day_warning)
    if start_date_only and end_date_only and normalized_all_day is False:
        normalized_all_day = True
    if normalized_all_day and normalized_time_zone:
        warnings.append(
            _warning(
                "unsupported_time_zone_for_all_day",
                "Calendar time_zone is supported only for timed events.",
            )
        )

    normalized_availability_name, normalized_availability, availability_warning = (
        _normalize_availability(availability, field="availability")
    )
    if availability_warning is not None:
        warnings.append(availability_warning)

    normalized_alarm_offsets, alarm_warning = _normalize_alarm_offsets(
        alarm_offsets_minutes,
        field="alarm_offsets_minutes",
    )
    if alarm_warning is not None:
        warnings.append(alarm_warning)

    normalized_alarm_absolute_dates, alarm_absolute_warning = _normalize_alarm_absolute_dates(
        alarm_absolute_dates,
        field="alarm_absolute_dates",
    )
    if alarm_absolute_warning is not None:
        warnings.append(alarm_absolute_warning)
    normalized_alarm_sound_name, alarm_sound_warning = _normalize_alarm_sound_name(
        alarm_sound_name,
        field="alarm_sound_name",
    )
    if alarm_sound_warning is not None:
        warnings.append(alarm_sound_warning)
    normalized_alarm_email_address, alarm_email_sha256, alarm_email_warning = (
        _normalize_alarm_email_address(
            alarm_email_address,
            field="alarm_email_address",
        )
    )
    if alarm_email_warning is not None:
        warnings.append(alarm_email_warning)
    normalized_alarm_proximity, alarm_proximity_warning = _normalize_alarm_proximity(
        alarm_proximity,
        field="alarm_proximity",
    )
    if alarm_proximity_warning is not None:
        warnings.append(alarm_proximity_warning)
    normalized_alarm_structured_location, alarm_structured_location_warning = (
        _normalize_structured_location(
            alarm_structured_location,
            field="alarm_structured_location",
        )
    )
    if alarm_structured_location_warning is not None:
        warnings.append(alarm_structured_location_warning)
    alarm_sound_trigger = _alarm_sound_trigger_warning(
        normalized_alarm_sound_name,
        normalized_alarm_offsets,
        normalized_alarm_absolute_dates,
        field="alarm_sound_name",
    )
    if alarm_sound_trigger is not None:
        warnings.append(alarm_sound_trigger)
    alarm_email_trigger = _alarm_email_trigger_warning(
        alarm_email_sha256,
        normalized_alarm_offsets,
        normalized_alarm_absolute_dates,
        field="alarm_email_address",
    )
    if alarm_email_trigger is not None:
        warnings.append(alarm_email_trigger)
    alarm_action_conflict = _alarm_action_conflict_warning(
        normalized_alarm_sound_name,
        normalized_alarm_proximity,
        alarm_email_sha256,
    )
    if alarm_action_conflict is not None:
        warnings.append(alarm_action_conflict)
    alarm_geofence_location = _alarm_geofence_location_warning(
        normalized_alarm_proximity,
        normalized_alarm_structured_location,
        proximity_field="alarm_proximity",
        location_field="alarm_structured_location",
    )
    if alarm_geofence_location is not None:
        warnings.append(alarm_geofence_location)
    alarm_conflict = _alarm_conflict_warning(
        normalized_alarm_offsets,
        normalized_alarm_absolute_dates,
        normalized_alarm_proximity,
    )
    if alarm_conflict is not None:
        warnings.append(alarm_conflict)

    normalized_recurrence, recurrence_warning = _normalize_recurrence(
        frequency=recurrence_frequency,
        interval=recurrence_interval,
        count=recurrence_count,
        end_date=recurrence_end_date,
        unbounded=recurrence_unbounded,
        weekdays=recurrence_weekdays,
        month_days=recurrence_month_days,
        month_weekdays=recurrence_month_weekdays,
        year_months=recurrence_year_months,
        year_month_days=recurrence_year_month_days,
        year_month_weekdays=recurrence_year_month_weekdays,
        year_days=recurrence_year_days,
        year_weeks=recurrence_year_weeks,
        set_positions=recurrence_set_positions,
    )
    if recurrence_warning is not None:
        warnings.append(recurrence_warning)
    recurrence_end_range_warning = _recurrence_end_date_range_warning(
        normalized_recurrence,
        normalized_start,
    )
    if recurrence_end_range_warning is not None:
        warnings.append(recurrence_end_range_warning)

    (
        normalized_event_url,
        event_url_scheme,
        event_url_domain,
        event_url_sha256,
        event_url_warning,
    ) = (
        _normalize_event_url(event_url, field="event_url")
    )
    if event_url_warning is not None:
        warnings.append(event_url_warning)

    if warnings:
        return _preview_error(warnings)

    default_calendar_target: dict[str, Any] | None = None
    if normalized_use_default_calendar:
        default_calendar_result = _resolve_default_calendar_for_plan(
            eventkit_runner=eventkit_runner,
        )
        if default_calendar_result["status"] != "ok":
            return _preview_error(default_calendar_result["warnings"])
        default_calendar_target = default_calendar_result["target"]

    target = {
        "calendar_title": "" if default_calendar_target is not None else normalized_calendar,
        "calendar_handle": (
            default_calendar_target["calendar_handle"]
            if default_calendar_target is not None
            else normalized_calendar_handle
        ),
        "target_mode": "calendar_handle"
        if default_calendar_target is not None
        else ("calendar_handle" if normalized_calendar_handle else "calendar_title"),
    }
    default_calendar_resolution: dict[str, Any] | None = None
    if default_calendar_target is not None:
        default_calendar_resolution = {
            "resolved": True,
            "calendar_title": default_calendar_target["calendar_title"],
            "calendar_handle": default_calendar_target["calendar_handle"],
            "target_mode": "calendar_handle",
            "use_default_calendar": True,
            "is_default_calendar": True,
            "allows_content_modifications": default_calendar_target[
                "allows_content_modifications"
            ],
            "default_calendar_verified": True,
            "apply_with_calendar_handle": True,
        }
    proposed = {
        "title": normalized_title,
        "start_date": normalized_start,
        "end_date": normalized_end,
        "time_zone": normalized_time_zone,
        "time_zone_bound": bool(normalized_time_zone),
        "all_day": normalized_all_day,
        "date_only_input": start_date_only and end_date_only,
        "availability": normalized_availability,
        "availability_name": normalized_availability_name,
        "availability_requested": normalized_availability is not None,
        "location": normalized_location,
        "location_present": bool(normalized_location),
        "structured_location": normalized_structured_location,
        "structured_location_requested": bool(normalized_structured_location),
        "notes_text": normalized_notes,
        "notes_chars": len(normalized_notes),
        "notes_present": bool(normalized_notes),
        "attendees_count": 0,
        "alarm_offsets_minutes": normalized_alarm_offsets,
        "alarm_absolute_dates": normalized_alarm_absolute_dates,
        "alarm_sound_name": normalized_alarm_sound_name,
        "alarm_email_address_sha256": alarm_email_sha256,
        "alarm_proximity": normalized_alarm_proximity,
        "alarm_structured_location": normalized_alarm_structured_location,
        "alarm_action": _alarm_action(
            normalized_alarm_sound_name,
            normalized_alarm_proximity,
            alarm_email_sha256,
        ),
        "alarm_kind": _alarm_kind(
            normalized_alarm_offsets,
            normalized_alarm_absolute_dates,
            normalized_alarm_proximity,
            alarm_email_sha256,
        ),
        "alarms_count": _alarm_count(
            normalized_alarm_offsets,
            normalized_alarm_absolute_dates,
            normalized_alarm_proximity,
        ),
        "recurrence": normalized_recurrence,
        "recurrence_present": bool(
            normalized_recurrence and normalized_recurrence["recurrence_present"]
        ),
        "event_url_requested": bool(normalized_event_url),
        "event_url_clear_requested": False,
        "event_url_scheme": event_url_scheme,
        "event_url_domain": event_url_domain,
        "event_url_safe_sha256": event_url_sha256,
        "url_present": bool(normalized_event_url),
    }
    fingerprint_proposed = {**proposed, "event_url": normalized_event_url}
    fingerprint_payload = {
        "operation": "create",
        "target": target,
        "proposed": fingerprint_proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    preview = {
        "operation": "create",
        "target": target,
        "proposed": proposed,
        "idempotency_key": idempotency_key,
        "approval": {
            "required_for_apply": True,
            "apply_tool_available": True,
            "approval_fingerprint": approval_fingerprint,
            "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
        },
        "read_back_required_after_apply": True,
    }
    if default_calendar_resolution is not None:
        preview["default_calendar_resolution"] = default_calendar_resolution

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": preview,
        "result_count": 1,
        "warnings": [],
    }


def _plan_calendar_update(
    *,
    title: str,
    start_date: str,
    end_date: str,
    time_zone: str,
    all_day: bool,
    availability: str,
    alarm_offsets_minutes: list[int] | None,
    alarm_absolute_dates: list[str] | None,
    alarm_sound_name: str,
    alarm_email_address: str,
    alarm_proximity: str,
    alarm_structured_location: dict[str, Any] | None,
    recurrence_frequency: str,
    recurrence_interval: int | None,
    recurrence_count: int | None,
    recurrence_end_date: str,
    recurrence_unbounded: bool,
    recurrence_weekdays: list[str | int] | str | None,
    recurrence_month_days: list[int] | str | None,
    recurrence_month_weekdays: list[dict[str, Any]] | str | None,
    recurrence_year_months: list[int] | str | None,
    recurrence_year_month_days: list[int] | str | None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | str | None,
    recurrence_year_days: list[int] | str | None,
    recurrence_year_weeks: list[int] | str | None,
    recurrence_set_positions: list[int] | str | None,
    recurrence_update_scope: str,
    clear_recurrence: bool,
    event_url: str,
    clear_event_url: bool,
    location: str,
    structured_location: dict[str, Any] | None,
    clear_structured_location: bool,
    notes: str,
    handle: str,
    target_calendar_handle: str,
    expected_title: str,
    expected_calendar_title: str,
    expected_start_date: str,
    expected_end_date: str,
    expected_time_zone: str,
    expected_all_day: bool,
    expected_availability: str,
    expected_alarm_offsets_minutes: list[int] | None,
    expected_alarm_absolute_dates: list[str] | None,
    expected_alarm_sound_name: str,
    expected_alarm_email_address_sha256: str,
    expected_alarm_proximity: str,
    expected_alarm_structured_location: dict[str, Any] | None,
    expected_event_url_present: bool,
    expected_event_url_sha256: str,
    expected_location: str,
    expected_structured_location: dict[str, Any] | None,
    expected_notes: str,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    normalized_handle = handle.strip()
    if not is_opaque_handle(normalized_handle, "calendar:event"):
        warnings.append(
            _warning(
                "invalid_handle",
                "Expected calendar:event:v1 opaque handle from search output.",
            )
        )

    normalized_target_calendar_handle = target_calendar_handle.strip()
    if normalized_target_calendar_handle and not is_opaque_handle(
        normalized_target_calendar_handle, "calendar:calendar"
    ):
        warnings.append(
            _warning(
                "invalid_calendar_handle",
                "Expected calendar:calendar:v1 opaque handle from calendar selection output.",
            )
        )

    normalized_title, title_warning = _bounded_preview_value(
        title,
        field="title",
        max_chars=MAX_PREVIEW_TITLE_CHARS,
        required=True,
    )
    if title_warning is not None:
        warnings.append(title_warning)

    normalized_expected_title, expected_title_warning = _bounded_preview_value(
        expected_title,
        field="expected_title",
        max_chars=MAX_PREVIEW_TITLE_CHARS,
        required=True,
    )
    if expected_title_warning is not None:
        warnings.append(expected_title_warning)

    normalized_expected_calendar, expected_calendar_warning = _bounded_preview_value(
        expected_calendar_title,
        field="expected_calendar_title",
        max_chars=MAX_PREVIEW_CALENDAR_CHARS,
        required=True,
    )
    if expected_calendar_warning is not None:
        warnings.append(expected_calendar_warning)

    normalized_location, location_warning = _bounded_preview_value(
        location,
        field="location",
        max_chars=MAX_LOCATION_CHARS,
        required=False,
    )
    if location_warning is not None:
        warnings.append(location_warning)
    normalized_structured_location, structured_location_warning = (
        _normalize_structured_location(
            structured_location,
            field="structured_location",
        )
    )
    if structured_location_warning is not None:
        warnings.append(structured_location_warning)
    if normalized_structured_location:
        if normalized_location and normalized_location != normalized_structured_location["title"]:
            warnings.append(
                _warning(
                    "conflicting_location_fields",
                    "Calendar location must match structured_location.title when both are provided.",
                )
            )
        normalized_location = normalized_structured_location["title"]
    if clear_structured_location and normalized_structured_location:
        warnings.append(
            _warning(
                "conflicting_structured_location_fields",
                "Use either structured_location or clear_structured_location, not both.",
            )
        )
    if clear_structured_location and normalized_location:
        warnings.append(
            _warning(
                "conflicting_location_fields",
                "Calendar clear_structured_location requires empty location because EventKit stores location as structured title.",
            )
        )

    normalized_expected_location, expected_location_warning = _bounded_preview_value(
        expected_location,
        field="expected_location",
        max_chars=MAX_LOCATION_CHARS,
        required=False,
    )
    if expected_location_warning is not None:
        warnings.append(expected_location_warning)
    normalized_expected_structured_location, expected_structured_location_warning = (
        _normalize_structured_location(
            expected_structured_location,
            field="expected_structured_location",
        )
    )
    if expected_structured_location_warning is not None:
        warnings.append(expected_structured_location_warning)
    if normalized_expected_structured_location:
        if (
            normalized_expected_location
            and normalized_expected_location != normalized_expected_structured_location["title"]
        ):
            warnings.append(
                _warning(
                    "conflicting_location_fields",
                    "Calendar expected_location must match expected_structured_location.title when both are provided.",
                )
            )
        normalized_expected_location = normalized_expected_structured_location["title"]

    normalized_notes, notes_warning = _bounded_preview_value(
        notes,
        field="notes",
        max_chars=MAX_CONTENT_CHARS,
        required=False,
    )
    if notes_warning is not None:
        warnings.append(notes_warning)

    normalized_expected_notes, expected_notes_warning = _bounded_preview_value(
        expected_notes,
        field="expected_notes",
        max_chars=MAX_CONTENT_CHARS,
        required=False,
    )
    if expected_notes_warning is not None:
        warnings.append(expected_notes_warning)

    start_date_only = _is_date_only_input(start_date)
    end_date_only = _is_date_only_input(end_date)
    date_pair_warning = _date_only_pair_warning(
        start_date,
        end_date,
        first_field="start_date",
        second_field="end_date",
    )
    if date_pair_warning is not None:
        warnings.append(date_pair_warning)

    expected_start_date_only = _is_date_only_input(expected_start_date)
    expected_end_date_only = _is_date_only_input(expected_end_date)
    expected_date_pair_warning = _date_only_pair_warning(
        expected_start_date,
        expected_end_date,
        first_field="expected_start_date",
        second_field="expected_end_date",
    )
    if expected_date_pair_warning is not None:
        warnings.append(expected_date_pair_warning)

    normalized_start, start_warning = _normalize_event_datetime(
        start_date,
        field="start_date",
        allow_date_only=True,
    )
    if start_warning is not None:
        warnings.append(start_warning)

    normalized_end, end_warning = _normalize_event_datetime(
        end_date,
        field="end_date",
        allow_date_only=True,
    )
    if end_warning is not None:
        warnings.append(end_warning)

    normalized_expected_start, expected_start_warning = _normalize_event_datetime(
        expected_start_date,
        field="expected_start_date",
        allow_date_only=True,
    )
    if expected_start_warning is not None:
        warnings.append(expected_start_warning)

    normalized_expected_end, expected_end_warning = _normalize_event_datetime(
        expected_end_date,
        field="expected_end_date",
        allow_date_only=True,
    )
    if expected_end_warning is not None:
        warnings.append(expected_end_warning)

    if normalized_start and normalized_end and date_pair_warning is None:
        start_dt = datetime.fromisoformat(normalized_start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(normalized_end.replace("Z", "+00:00"))
        if end_dt <= start_dt:
            warnings.append(
                _warning("invalid_time_range", "Calendar event end_date must be after start_date.")
            )
    if (
        normalized_expected_start
        and normalized_expected_end
        and expected_date_pair_warning is None
    ):
        expected_start_dt = datetime.fromisoformat(
            normalized_expected_start.replace("Z", "+00:00")
        )
        expected_end_dt = datetime.fromisoformat(normalized_expected_end.replace("Z", "+00:00"))
        if expected_end_dt <= expected_start_dt:
            warnings.append(
                _warning(
                    "invalid_expected_state",
                    "Calendar expected_end_date must be after expected_start_date.",
                )
            )

    normalized_time_zone, time_zone_warning = _normalize_time_zone(
        time_zone,
        field="time_zone",
    )
    if time_zone_warning is not None:
        warnings.append(time_zone_warning)

    normalized_expected_time_zone, expected_time_zone_warning = _normalize_time_zone(
        expected_time_zone,
        field="expected_time_zone",
    )
    if expected_time_zone_warning is not None:
        warnings.append(expected_time_zone_warning)

    normalized_all_day, all_day_warning = _normalize_bool_flag(all_day, field="all_day")
    if all_day_warning is not None:
        warnings.append(all_day_warning)
    if start_date_only and end_date_only and normalized_all_day is False:
        normalized_all_day = True

    normalized_expected_all_day, expected_all_day_warning = _normalize_bool_flag(
        expected_all_day, field="expected_all_day"
    )
    if expected_all_day_warning is not None:
        warnings.append(expected_all_day_warning)
    if (
        expected_start_date_only
        and expected_end_date_only
        and normalized_expected_all_day is False
    ):
        normalized_expected_all_day = True
    if normalized_all_day and normalized_time_zone:
        warnings.append(
            _warning(
                "unsupported_time_zone_for_all_day",
                "Calendar time_zone is supported only for timed events.",
            )
        )
    if normalized_expected_all_day and normalized_expected_time_zone:
        warnings.append(
            _warning(
                "unsupported_time_zone_for_all_day",
                "Calendar expected_time_zone is supported only for timed events.",
            )
        )

    normalized_availability_name, normalized_availability, availability_warning = (
        _normalize_availability(availability, field="availability")
    )
    if availability_warning is not None:
        warnings.append(availability_warning)
    (
        normalized_expected_availability_name,
        normalized_expected_availability,
        expected_availability_warning,
    ) = _normalize_availability(
        expected_availability,
        field="expected_availability",
        allow_not_supported=True,
    )
    if expected_availability_warning is not None:
        warnings.append(expected_availability_warning)
    if normalized_availability is not None and normalized_expected_availability is None:
        warnings.append(
            _warning(
                "missing_required_field",
                "Calendar availability update requires expected_availability.",
            )
        )

    proposed_alarm_offsets_present = alarm_offsets_minutes is not None
    proposed_alarm_absolute_dates_present = alarm_absolute_dates is not None
    normalized_alarm_offsets, alarm_warning = _normalize_alarm_offsets(
        alarm_offsets_minutes,
        field="alarm_offsets_minutes",
    )
    if alarm_warning is not None:
        warnings.append(alarm_warning)
    normalized_alarm_absolute_dates, alarm_absolute_warning = _normalize_alarm_absolute_dates(
        alarm_absolute_dates,
        field="alarm_absolute_dates",
    )
    if alarm_absolute_warning is not None:
        warnings.append(alarm_absolute_warning)
    normalized_alarm_sound_name, alarm_sound_warning = _normalize_alarm_sound_name(
        alarm_sound_name,
        field="alarm_sound_name",
    )
    if alarm_sound_warning is not None:
        warnings.append(alarm_sound_warning)
    normalized_alarm_email_address, alarm_email_sha256, alarm_email_warning = (
        _normalize_alarm_email_address(
            alarm_email_address,
            field="alarm_email_address",
        )
    )
    if alarm_email_warning is not None:
        warnings.append(alarm_email_warning)
    normalized_alarm_proximity, alarm_proximity_warning = _normalize_alarm_proximity(
        alarm_proximity,
        field="alarm_proximity",
    )
    if alarm_proximity_warning is not None:
        warnings.append(alarm_proximity_warning)
    normalized_alarm_structured_location, alarm_structured_location_warning = (
        _normalize_structured_location(
            alarm_structured_location,
            field="alarm_structured_location",
        )
    )
    if alarm_structured_location_warning is not None:
        warnings.append(alarm_structured_location_warning)
    alarm_sound_trigger = _alarm_sound_trigger_warning(
        normalized_alarm_sound_name,
        normalized_alarm_offsets,
        normalized_alarm_absolute_dates,
        field="alarm_sound_name",
    )
    if alarm_sound_trigger is not None:
        warnings.append(alarm_sound_trigger)
    alarm_email_trigger = _alarm_email_trigger_warning(
        alarm_email_sha256,
        normalized_alarm_offsets,
        normalized_alarm_absolute_dates,
        field="alarm_email_address",
    )
    if alarm_email_trigger is not None:
        warnings.append(alarm_email_trigger)
    alarm_action_conflict = _alarm_action_conflict_warning(
        normalized_alarm_sound_name,
        normalized_alarm_proximity,
        alarm_email_sha256,
    )
    if alarm_action_conflict is not None:
        warnings.append(alarm_action_conflict)
    alarm_geofence_location = _alarm_geofence_location_warning(
        normalized_alarm_proximity,
        normalized_alarm_structured_location,
        proximity_field="alarm_proximity",
        location_field="alarm_structured_location",
    )
    if alarm_geofence_location is not None:
        warnings.append(alarm_geofence_location)
    alarm_conflict = _alarm_conflict_warning(
        normalized_alarm_offsets,
        normalized_alarm_absolute_dates,
        normalized_alarm_proximity,
    )
    if alarm_conflict is not None:
        warnings.append(alarm_conflict)

    normalized_expected_alarm_offsets, expected_alarm_warning = _normalize_alarm_offsets(
        expected_alarm_offsets_minutes,
        field="expected_alarm_offsets_minutes",
    )
    if expected_alarm_warning is not None:
        warnings.append(expected_alarm_warning)
    normalized_expected_alarm_absolute_dates, expected_alarm_absolute_warning = (
        _normalize_alarm_absolute_dates(
            expected_alarm_absolute_dates,
            field="expected_alarm_absolute_dates",
        )
    )
    if expected_alarm_absolute_warning is not None:
        warnings.append(expected_alarm_absolute_warning)
    normalized_expected_alarm_sound_name, expected_alarm_sound_warning = (
        _normalize_alarm_sound_name(
            expected_alarm_sound_name,
            field="expected_alarm_sound_name",
        )
    )
    if expected_alarm_sound_warning is not None:
        warnings.append(expected_alarm_sound_warning)
    normalized_expected_alarm_email_sha256, expected_alarm_email_warning = _normalize_sha256(
        expected_alarm_email_address_sha256,
        field="expected_alarm_email_address_sha256",
    )
    if expected_alarm_email_warning is not None:
        warnings.append(expected_alarm_email_warning)
    normalized_expected_alarm_proximity, expected_alarm_proximity_warning = (
        _normalize_alarm_proximity(
            expected_alarm_proximity,
            field="expected_alarm_proximity",
        )
    )
    if expected_alarm_proximity_warning is not None:
        warnings.append(expected_alarm_proximity_warning)
    (
        normalized_expected_alarm_structured_location,
        expected_alarm_structured_location_warning,
    ) = _normalize_structured_location(
        expected_alarm_structured_location,
        field="expected_alarm_structured_location",
    )
    if expected_alarm_structured_location_warning is not None:
        warnings.append(expected_alarm_structured_location_warning)
    expected_alarm_sound_trigger = _alarm_sound_trigger_warning(
        normalized_expected_alarm_sound_name,
        normalized_expected_alarm_offsets,
        normalized_expected_alarm_absolute_dates,
        field="expected_alarm_sound_name",
    )
    if expected_alarm_sound_trigger is not None:
        warnings.append(expected_alarm_sound_trigger)
    expected_alarm_email_trigger = _alarm_email_trigger_warning(
        normalized_expected_alarm_email_sha256,
        normalized_expected_alarm_offsets,
        normalized_expected_alarm_absolute_dates,
        field="expected_alarm_email_address_sha256",
    )
    if expected_alarm_email_trigger is not None:
        warnings.append(expected_alarm_email_trigger)
    expected_alarm_action_conflict = _alarm_action_conflict_warning(
        normalized_expected_alarm_sound_name,
        normalized_expected_alarm_proximity,
        normalized_expected_alarm_email_sha256,
        prefix="expected ",
    )
    if expected_alarm_action_conflict is not None:
        warnings.append(expected_alarm_action_conflict)
    expected_alarm_geofence_location = _alarm_geofence_location_warning(
        normalized_expected_alarm_proximity,
        normalized_expected_alarm_structured_location,
        proximity_field="expected_alarm_proximity",
        location_field="expected_alarm_structured_location",
    )
    if expected_alarm_geofence_location is not None:
        warnings.append(expected_alarm_geofence_location)
    expected_alarm_conflict = _alarm_conflict_warning(
        normalized_expected_alarm_offsets,
        normalized_expected_alarm_absolute_dates,
        normalized_expected_alarm_proximity,
    )
    if expected_alarm_conflict is not None:
        warnings.append(expected_alarm_conflict)
    if (
        not proposed_alarm_offsets_present
        and not proposed_alarm_absolute_dates_present
        and normalized_expected_alarm_offsets is not None
        and normalized_expected_alarm_absolute_dates is not None
    ):
        normalized_alarm_offsets = normalized_expected_alarm_offsets
        normalized_alarm_absolute_dates = normalized_expected_alarm_absolute_dates
    proposed_alarm_action_present = bool(
        normalized_alarm_sound_name
        or alarm_email_sha256
        or normalized_alarm_proximity
        or normalized_alarm_structured_location
    )
    if (
        recurrence_update_scope
        and not proposed_alarm_offsets_present
        and not proposed_alarm_absolute_dates_present
        and not proposed_alarm_action_present
    ):
        normalized_alarm_sound_name = normalized_expected_alarm_sound_name
        alarm_email_sha256 = normalized_expected_alarm_email_sha256
        normalized_alarm_proximity = normalized_expected_alarm_proximity
        normalized_alarm_structured_location = normalized_expected_alarm_structured_location
    normalized_recurrence, recurrence_warning = _normalize_recurrence(
        frequency=recurrence_frequency,
        interval=recurrence_interval,
        count=recurrence_count,
        end_date=recurrence_end_date,
        unbounded=recurrence_unbounded,
        weekdays=recurrence_weekdays,
        month_days=recurrence_month_days,
        month_weekdays=recurrence_month_weekdays,
        year_months=recurrence_year_months,
        year_month_days=recurrence_year_month_days,
        year_month_weekdays=recurrence_year_month_weekdays,
        year_days=recurrence_year_days,
        year_weeks=recurrence_year_weeks,
        set_positions=recurrence_set_positions,
    )
    if recurrence_warning is not None:
        warnings.append(recurrence_warning)
    recurrence_end_range_warning = _recurrence_end_date_range_warning(
        normalized_recurrence,
        normalized_start,
    )
    if recurrence_end_range_warning is not None:
        warnings.append(recurrence_end_range_warning)
    if clear_recurrence and normalized_recurrence and normalized_recurrence["recurrence_present"]:
        warnings.append(
            _warning(
                "conflicting_recurrence_fields",
                "Use either recurrence fields or clear_recurrence, not both.",
            )
        )

    (
        normalized_event_url,
        event_url_scheme,
        event_url_domain,
        event_url_sha256,
        event_url_warning,
    ) = (
        _normalize_event_url(event_url, field="event_url")
    )
    if event_url_warning is not None:
        warnings.append(event_url_warning)

    normalized_expected_event_url_present, expected_event_url_present_warning = (
        _normalize_bool_flag(
            expected_event_url_present,
            field="expected_event_url_present",
        )
    )
    if expected_event_url_present_warning is not None:
        warnings.append(expected_event_url_present_warning)
    normalized_expected_event_url_sha256, expected_event_url_sha256_warning = (
        _normalize_sha256(
            expected_event_url_sha256,
            field="expected_event_url_sha256",
        )
    )
    if expected_event_url_sha256_warning is not None:
        warnings.append(expected_event_url_sha256_warning)
    if normalized_expected_event_url_present and not normalized_expected_event_url_sha256:
        warnings.append(
            _warning(
                "missing_required_field",
                "Calendar expected_event_url_sha256 is required when expected_event_url_present=true.",
            )
        )
    if not normalized_expected_event_url_present and normalized_expected_event_url_sha256:
        warnings.append(
            _warning(
                "invalid_expected_state",
                "Calendar expected_event_url_sha256 requires expected_event_url_present=true.",
            )
        )
    if clear_event_url and not normalized_expected_event_url_present:
        warnings.append(
            _warning(
                "missing_required_field",
                "Calendar clear_event_url requires expected_event_url_present=true.",
            )
        )
    if clear_event_url and not normalized_expected_event_url_sha256:
        warnings.append(
            _warning(
                "missing_required_field",
                "Calendar clear_event_url requires expected_event_url_sha256.",
            )
        )
    if clear_structured_location and not normalized_expected_structured_location:
        warnings.append(
            _warning(
                "missing_required_field",
                "Calendar clear_structured_location requires expected_structured_location.",
            )
        )
    selected_structured_location_set_requested = bool(
        recurrence_update_scope and normalized_structured_location
    )
    structured_location_state_bound = bool(normalized_expected_structured_location) or (
        selected_structured_location_set_requested and not clear_structured_location
    )
    selected_display_alarm_update_requested = bool(recurrence_update_scope) and (
        normalized_alarm_offsets != normalized_expected_alarm_offsets
        or normalized_alarm_absolute_dates != normalized_expected_alarm_absolute_dates
    )
    selected_alarm_action_update_requested = bool(recurrence_update_scope) and (
        normalized_alarm_sound_name != normalized_expected_alarm_sound_name
        or alarm_email_sha256 != normalized_expected_alarm_email_sha256
        or normalized_alarm_proximity != normalized_expected_alarm_proximity
        or normalized_alarm_structured_location != normalized_expected_alarm_structured_location
    )
    selected_alarm_update_requested = (
        selected_display_alarm_update_requested or selected_alarm_action_update_requested
    )
    selected_all_day_update_requested = bool(recurrence_update_scope) and (
        normalized_all_day != normalized_expected_all_day
    )
    selected_all_day_date_reschedule_requested = bool(recurrence_update_scope) and (
        normalized_all_day
        and normalized_expected_all_day
        and (normalized_start != normalized_expected_start or normalized_end != normalized_expected_end)
    )
    selected_calendar_move_requested = bool(
        recurrence_update_scope == "this_event" and normalized_target_calendar_handle
    )
    mid_series_clear_requested = bool(
        clear_recurrence and recurrence_update_scope == "future_events"
    )
    mid_series_recurrence_replace_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and normalized_recurrence
        and normalized_recurrence["recurrence_present"]
    )
    future_series_structured_location_update_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and not mid_series_recurrence_replace_requested
        and (bool(normalized_structured_location) or clear_structured_location)
    )
    future_series_action_alarm_update_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and not mid_series_recurrence_replace_requested
        and not future_series_structured_location_update_requested
        and (
            normalized_alarm_sound_name != normalized_expected_alarm_sound_name
            or alarm_email_sha256 != normalized_expected_alarm_email_sha256
            or normalized_alarm_proximity != normalized_expected_alarm_proximity
            or normalized_alarm_structured_location
            != normalized_expected_alarm_structured_location
        )
    )
    future_series_display_alarm_update_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and not mid_series_recurrence_replace_requested
        and not future_series_structured_location_update_requested
        and not future_series_action_alarm_update_requested
        and (
            normalized_alarm_offsets != normalized_expected_alarm_offsets
            or normalized_alarm_absolute_dates != normalized_expected_alarm_absolute_dates
        )
    )
    future_series_all_day_update_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and not mid_series_recurrence_replace_requested
        and not future_series_structured_location_update_requested
        and not future_series_action_alarm_update_requested
        and not future_series_display_alarm_update_requested
        and (
            normalized_all_day != normalized_expected_all_day
            or (
                normalized_all_day
                and normalized_expected_all_day
                and (
                    normalized_start != normalized_expected_start
                    or normalized_end != normalized_expected_end
                )
            )
        )
    )
    future_series_scalar_update_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and not mid_series_recurrence_replace_requested
        and not future_series_structured_location_update_requested
        and not future_series_action_alarm_update_requested
        and not future_series_display_alarm_update_requested
        and not future_series_all_day_update_requested
        and (
            normalized_title != normalized_expected_title
            or normalized_location != normalized_expected_location
            or normalized_notes != normalized_expected_notes
        )
    )
    future_series_reschedule_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and not mid_series_recurrence_replace_requested
        and not future_series_all_day_update_requested
        and (
            normalized_start != normalized_expected_start
            or normalized_end != normalized_expected_end
            or normalized_time_zone != normalized_expected_time_zone
        )
    )
    future_series_availability_update_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and not mid_series_recurrence_replace_requested
        and not future_series_scalar_update_requested
        and not future_series_reschedule_requested
        and not future_series_action_alarm_update_requested
        and not future_series_display_alarm_update_requested
        and not future_series_all_day_update_requested
        and normalized_availability is not None
        and normalized_availability != normalized_expected_availability
    )
    future_series_event_url_update_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and not mid_series_recurrence_replace_requested
        and not future_series_scalar_update_requested
        and not future_series_reschedule_requested
        and not future_series_availability_update_requested
        and not future_series_structured_location_update_requested
        and not future_series_action_alarm_update_requested
        and not future_series_display_alarm_update_requested
        and not future_series_all_day_update_requested
        and (bool(normalized_event_url) or clear_event_url)
    )
    future_series_calendar_move_requested = bool(
        not clear_recurrence
        and recurrence_update_scope == "future_events"
        and not mid_series_recurrence_replace_requested
        and not future_series_scalar_update_requested
        and not future_series_reschedule_requested
        and not future_series_availability_update_requested
        and not future_series_event_url_update_requested
        and not future_series_structured_location_update_requested
        and not future_series_action_alarm_update_requested
        and not future_series_display_alarm_update_requested
        and not future_series_all_day_update_requested
        and normalized_target_calendar_handle
    )
    future_series_update_requested = (
        future_series_scalar_update_requested
        or future_series_reschedule_requested
        or future_series_availability_update_requested
        or future_series_event_url_update_requested
        or future_series_structured_location_update_requested
        or future_series_display_alarm_update_requested
        or future_series_action_alarm_update_requested
        or future_series_all_day_update_requested
        or future_series_calendar_move_requested
    )
    selected_occurrence_update_requested = bool(
        recurrence_update_scope == "this_event" and not clear_recurrence
    )
    if clear_recurrence and recurrence_update_scope not in {"", "future_events"}:
        warnings.append(
            _warning(
                "unsupported_recurrence_update_scope",
                "Calendar clear_recurrence supports no recurrence_update_scope for first-visible clearing, or future_events for mid-series clearing.",
            )
        )
    if recurrence_update_scope == "future_events" and not (
        clear_recurrence
        or mid_series_recurrence_replace_requested
        or future_series_update_requested
    ):
        warnings.append(
            _warning(
                "unsupported_recurrence_update_scope",
                "Calendar recurrence_update_scope=future_events requires clear_recurrence, replacement recurrence fields, a title/location/notes change, timed reschedule, availability update, event URL set/clear, structured-location set/clear, display-alarm set/clear, action-alarm set/clear, all-day set/clear/date-only reschedule, or target-calendar move.",
            )
        )

    occurrence_identity: dict[str, Any] = {}
    expected_recurrence = _empty_recurrence()
    if selected_occurrence_update_requested:
        if clear_recurrence or (normalized_recurrence and normalized_recurrence["recurrence_present"]):
            warnings.append(
                _warning(
                    "unsupported_recurring_occurrence_update_shape",
                    "Selected recurring occurrence update cannot change or clear recurrence.",
                )
            )
        if normalized_all_day and not (start_date_only and end_date_only):
            warnings.append(
                _warning(
                    "missing_required_field",
                    "Selected recurring occurrence all-day update requires date-only start_date and end_date.",
                )
            )
        selected_occurrence_reschedule_requested = (
            normalized_start != normalized_expected_start
            or normalized_end != normalized_expected_end
            or normalized_time_zone != normalized_expected_time_zone
        )
        if selected_occurrence_reschedule_requested:
            if normalized_all_day:
                if not normalized_expected_all_day and not normalized_expected_time_zone:
                    warnings.append(
                        _warning(
                            "missing_required_field",
                            "Selected recurring occurrence all-day update requires expected_time_zone when the current occurrence is timed.",
                        )
                    )
            elif normalized_expected_all_day:
                if not normalized_time_zone:
                    warnings.append(
                        _warning(
                            "missing_required_field",
                            "Selected recurring occurrence timed update from all-day requires explicit time_zone.",
                        )
                    )
            elif not normalized_time_zone or not normalized_expected_time_zone:
                warnings.append(
                    _warning(
                        "missing_required_field",
                        "Selected recurring occurrence reschedule requires explicit time_zone and expected_time_zone.",
                    )
                )
    if clear_recurrence:
        if normalized_target_calendar_handle or normalized_availability is not None:
            warnings.append(
                _warning(
                    "unsupported_clear_recurrence_shape",
                    "Calendar clear_recurrence is recurrence-only and cannot move calendars or change availability.",
                )
            )
        if normalized_event_url or clear_event_url:
            warnings.append(
                _warning(
                    "unsupported_clear_recurrence_shape",
                    "Calendar clear_recurrence is recurrence-only and cannot set or clear event URLs.",
                )
            )
        if clear_structured_location:
            warnings.append(
                _warning(
                    "unsupported_clear_recurrence_shape",
                    "Calendar clear_recurrence cannot also clear structured location.",
                )
            )
        if (
            normalized_title != normalized_expected_title
            or normalized_start != normalized_expected_start
            or normalized_end != normalized_expected_end
            or normalized_time_zone != normalized_expected_time_zone
            or normalized_all_day != normalized_expected_all_day
            or normalized_location != normalized_expected_location
            or normalized_structured_location != normalized_expected_structured_location
            or normalized_notes != normalized_expected_notes
            or normalized_alarm_offsets != normalized_expected_alarm_offsets
            or normalized_alarm_absolute_dates != normalized_expected_alarm_absolute_dates
            or normalized_alarm_sound_name != normalized_expected_alarm_sound_name
            or alarm_email_sha256 != normalized_expected_alarm_email_sha256
            or normalized_alarm_proximity != normalized_expected_alarm_proximity
            or normalized_alarm_structured_location
            != normalized_expected_alarm_structured_location
        ):
            warnings.append(
                _warning(
                    "unsupported_clear_recurrence_shape",
                    "Calendar clear_recurrence is recurrence-only; proposed scalar and alarm fields must match expected state.",
                )
            )

    if mid_series_recurrence_replace_requested:
        if normalized_target_calendar_handle or normalized_availability is not None:
            warnings.append(
                _warning(
                    "unsupported_recurrence_replacement_shape",
                    "Calendar mid-series recurrence replacement is recurrence-only and cannot move calendars or change availability.",
                )
            )
        if normalized_event_url or clear_event_url:
            warnings.append(
                _warning(
                    "unsupported_recurrence_replacement_shape",
                    "Calendar mid-series recurrence replacement is recurrence-only and cannot set or clear event URLs.",
                )
            )
        if clear_structured_location:
            warnings.append(
                _warning(
                    "unsupported_recurrence_replacement_shape",
                    "Calendar mid-series recurrence replacement cannot also clear structured location.",
                )
            )
        if (
            normalized_title != normalized_expected_title
            or normalized_start != normalized_expected_start
            or normalized_end != normalized_expected_end
            or normalized_time_zone != normalized_expected_time_zone
            or normalized_all_day != normalized_expected_all_day
            or normalized_location != normalized_expected_location
            or normalized_structured_location != normalized_expected_structured_location
            or normalized_notes != normalized_expected_notes
            or normalized_alarm_offsets != normalized_expected_alarm_offsets
            or normalized_alarm_absolute_dates != normalized_expected_alarm_absolute_dates
            or normalized_alarm_sound_name != normalized_expected_alarm_sound_name
            or alarm_email_sha256 != normalized_expected_alarm_email_sha256
            or normalized_alarm_proximity != normalized_expected_alarm_proximity
            or normalized_alarm_structured_location
            != normalized_expected_alarm_structured_location
        ):
            warnings.append(
                _warning(
                    "unsupported_recurrence_replacement_shape",
                    "Calendar mid-series recurrence replacement is recurrence-only; proposed scalar and alarm fields must match expected state.",
                )
            )

    if future_series_update_requested:
        if normalized_target_calendar_handle and not future_series_calendar_move_requested:
            if future_series_scalar_update_requested:
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series target-calendar move cannot co-mutate title, plain location, or notes.",
                    )
                )
            if (
                future_series_reschedule_requested
                or future_series_availability_update_requested
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series target-calendar move cannot co-mutate timed or availability fields.",
                    )
                )
            if (
                future_series_event_url_update_requested
                or future_series_structured_location_update_requested
                or future_series_display_alarm_update_requested
                or future_series_action_alarm_update_requested
                or future_series_all_day_update_requested
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series target-calendar move cannot co-mutate event URL, structured-location, alarm, or all-day fields.",
                    )
                )
        # No same-calendar no-op refusal exists here: the selected-occurrence
        # v1.122 gate accepts a move to the current calendar and this gate
        # mirrors it. No further co-mutation guards are reachable inside a
        # future_series_calendar_move_requested branch because the flag
        # itself requires every other future-series shape flag to be false;
        # the Swift helper keeps reachable equivalents against forged apply
        # payloads.
        if (
            normalized_availability is not None
            and not future_series_availability_update_requested
        ):
            warnings.append(
                _warning(
                    "unsupported_future_series_update_shape",
                    "Calendar future-series availability update requires availability different from expected_availability.",
                )
            )
        if (
            normalized_all_day != normalized_expected_all_day
            and not future_series_all_day_update_requested
        ):
            warnings.append(
                _warning(
                    "unsupported_future_series_update_shape",
                    "Calendar future-series update cannot change all-day state.",
                )
            )
        if future_series_reschedule_requested:
            if normalized_all_day or normalized_expected_all_day:
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series timed reschedule supports timed events only.",
                    )
                )
            if not normalized_time_zone or not normalized_expected_time_zone:
                warnings.append(
                    _warning(
                        "missing_required_field",
                        "Calendar future-series timed reschedule requires explicit time_zone and expected_time_zone.",
                    )
                )
        elif (
            not future_series_all_day_update_requested
            and (
                normalized_start != normalized_expected_start
                or normalized_end != normalized_expected_end
                or normalized_time_zone != normalized_expected_time_zone
            )
        ):
            warnings.append(
                _warning(
                    "unsupported_future_series_update_shape",
                    "Calendar future-series scalar update is limited to title, plain location, and notes.",
                )
            )
        if (normalized_event_url or clear_event_url) and not future_series_event_url_update_requested:
            warnings.append(
                _warning(
                    "unsupported_future_series_update_shape",
                    "Calendar future-series event URL update cannot co-mutate scalar, timed, availability, recurrence, calendar, structured-location, or alarm fields.",
                )
            )
        if future_series_event_url_update_requested:
            if normalized_event_url and normalized_expected_event_url_present and (
                event_url_sha256 == normalized_expected_event_url_sha256
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series event URL update requires a URL different from expected_event_url_sha256.",
                    )
                )
            if clear_event_url and not normalized_expected_event_url_present:
                warnings.append(
                    _warning(
                        "missing_required_field",
                        "Calendar future-series event URL clear requires expected_event_url_present=true.",
                    )
                )
        if future_series_structured_location_update_requested:
            if (
                future_series_reschedule_requested
                or future_series_availability_update_requested
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series structured-location update cannot co-mutate timed or availability fields.",
                    )
                )
            if (
                normalized_title != normalized_expected_title
                or normalized_notes != normalized_expected_notes
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series structured-location update cannot co-mutate title or notes.",
                    )
                )
            if (
                normalized_structured_location
                and normalized_expected_structured_location
                and normalized_structured_location == normalized_expected_structured_location
                and normalized_location == normalized_expected_location
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series structured-location update requires a value different from expected_structured_location.",
                    )
                )
            if clear_structured_location and not normalized_expected_structured_location:
                warnings.append(
                    _warning(
                        "missing_required_field",
                        "Calendar future-series structured-location clear requires expected_structured_location.",
                    )
                )
        if normalized_structured_location or clear_structured_location:
            if not future_series_structured_location_update_requested:
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series structured-location update cannot co-mutate scalar, timed, availability, event URL, recurrence, calendar, or alarm fields.",
                    )
                )
        if future_series_display_alarm_update_requested:
            if future_series_reschedule_requested or (
                normalized_availability is not None
                and normalized_availability != normalized_expected_availability
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series display-alarm update cannot co-mutate timed or availability fields.",
                    )
                )
            if (
                normalized_title != normalized_expected_title
                or normalized_notes != normalized_expected_notes
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series display-alarm update cannot co-mutate title or notes.",
                    )
                )
            if normalized_location != normalized_expected_location:
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series display-alarm update cannot co-mutate plain location.",
                    )
                )
            if (
                bool(normalized_event_url)
                or clear_event_url
                or bool(normalized_structured_location)
                or clear_structured_location
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series display-alarm update cannot co-mutate event URL or structured location.",
                    )
                )
            # Action-alarm field diffs cannot reach this branch: the display
            # flag itself requires future_series_action_alarm_update_requested
            # to be false, so any action-alarm diff routes to the action-alarm
            # branch instead. No-op and clear-without-expected shapes also
            # cannot reach this branch: the flag itself requires proposed
            # display-alarm state to differ from expected, so both fall
            # through to the generic unsupported_recurrence_update_scope
            # refusal. The Swift helper keeps reachable equivalents against
            # forged apply payloads.
        if future_series_action_alarm_update_requested:
            if future_series_reschedule_requested or (
                normalized_availability is not None
                and normalized_availability != normalized_expected_availability
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series action-alarm update cannot co-mutate timed or availability fields.",
                    )
                )
            if (
                normalized_title != normalized_expected_title
                or normalized_notes != normalized_expected_notes
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series action-alarm update cannot co-mutate title or notes.",
                    )
                )
            if normalized_location != normalized_expected_location:
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series action-alarm update cannot co-mutate plain location.",
                    )
                )
            if (
                bool(normalized_event_url)
                or clear_event_url
                or bool(normalized_structured_location)
                or clear_structured_location
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series action-alarm update cannot co-mutate event URL or structured location.",
                    )
                )
            # Display trigger fields (alarm_offsets_minutes /
            # alarm_absolute_dates) may change together with action-alarm
            # fields here because EventKit alarms are saved as a whole set;
            # the approved plan binds the complete proposed alarm state.
            # No-op shapes cannot reach this branch: the flag itself requires
            # proposed action-alarm state to differ from expected, so they
            # fall through to the generic unsupported_recurrence_update_scope
            # refusal. The Swift helper keeps reachable equivalents against
            # forged apply payloads.
        if future_series_all_day_update_requested:
            if normalized_all_day and not (start_date_only and end_date_only):
                warnings.append(
                    _warning(
                        "missing_required_field",
                        "Calendar future-series all-day update requires date-only start_date and end_date.",
                    )
                )
            if (
                normalized_all_day
                and not normalized_expected_all_day
                and not normalized_expected_time_zone
            ):
                warnings.append(
                    _warning(
                        "missing_required_field",
                        "Calendar future-series all-day update requires expected_time_zone when the current occurrence is timed.",
                    )
                )
            if not normalized_all_day and not normalized_time_zone:
                warnings.append(
                    _warning(
                        "missing_required_field",
                        "Calendar future-series timed update from all-day requires explicit time_zone.",
                    )
                )
            if (
                normalized_availability is not None
                and normalized_availability != normalized_expected_availability
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series all-day update cannot co-mutate availability fields.",
                    )
                )
            if (
                normalized_title != normalized_expected_title
                or normalized_notes != normalized_expected_notes
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series all-day update cannot co-mutate title or notes.",
                    )
                )
            if normalized_location != normalized_expected_location:
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series all-day update cannot co-mutate plain location.",
                    )
                )
            if (
                bool(normalized_event_url)
                or clear_event_url
                or bool(normalized_structured_location)
                or clear_structured_location
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series all-day update cannot co-mutate event URL or structured location.",
                    )
                )
            # Alarm-state co-mutation cannot reach this branch: any display or
            # action alarm diff routes to the display/action-alarm flags first
            # and the all-day flag excludes both, so the alarm blanket checks
            # below refuse the combined shape. No-op shapes also cannot reach
            # this branch: the flag itself requires an all-day flip or a
            # date-only all-day reschedule, so same-state requests fall
            # through to the generic unsupported_recurrence_update_scope
            # refusal. The Swift helper keeps reachable equivalents against
            # forged apply payloads.
        if (
            normalized_alarm_offsets != normalized_expected_alarm_offsets
            or normalized_alarm_absolute_dates != normalized_expected_alarm_absolute_dates
        ):
            if (
                not future_series_display_alarm_update_requested
                and not future_series_action_alarm_update_requested
            ):
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series display-alarm update cannot co-mutate scalar, timed, availability, event URL, structured-location, recurrence, or calendar fields.",
                    )
                )
        if (
            normalized_alarm_sound_name != normalized_expected_alarm_sound_name
            or alarm_email_sha256 != normalized_expected_alarm_email_sha256
            or normalized_alarm_proximity != normalized_expected_alarm_proximity
            or normalized_alarm_structured_location
            != normalized_expected_alarm_structured_location
        ):
            if not future_series_action_alarm_update_requested:
                warnings.append(
                    _warning(
                        "unsupported_future_series_update_shape",
                        "Calendar future-series action-alarm update cannot co-mutate scalar, timed, availability, event URL, structured-location, recurrence, or calendar fields.",
                    )
                )

    if warnings:
        return _preview_error(warnings)
    selected_target_calendar: dict[str, Any] = {}
    if selected_calendar_move_requested or future_series_calendar_move_requested:
        target_calendar_result = _resolve_calendar_target_for_plan(
            normalized_target_calendar_handle,
            eventkit_runner=eventkit_runner,
        )
        if target_calendar_result["status"] != "ok":
            return _preview_error(target_calendar_result["warnings"])
        selected_target_calendar = target_calendar_result["calendar"]
    if selected_occurrence_update_requested:
        occurrence_result = _resolve_event_occurrence_identity_for_plan(
            normalized_handle,
            eventkit_runner=eventkit_runner,
            require_adjacent_occurrence=True,
            require_adjacent_location_proof=True,
            require_adjacent_alarm_proof=True,
            require_supported_recurrence=True,
        )
        if occurrence_result["status"] != "ok":
            return _preview_error(occurrence_result["warnings"])
        expected_recurrence = occurrence_result["recurrence"]
        occurrence_identity = {
            "recurrence_update_scope": recurrence_update_scope,
            "occurrence_start_date": occurrence_result["occurrence_start_date"],
            "occurrence_end_date": occurrence_result["occurrence_end_date"],
            "adjacent_occurrence_start_date": occurrence_result[
                "adjacent_occurrence_start_date"
            ],
            "adjacent_occurrence_end_date": occurrence_result["adjacent_occurrence_end_date"],
            "adjacent_occurrence_event_url_present": occurrence_result.get(
                "adjacent_occurrence_event_url_present",
                False,
            ),
            "adjacent_occurrence_event_url_safe_sha256": occurrence_result.get(
                "adjacent_occurrence_event_url_safe_sha256",
                "",
            ),
            "adjacent_occurrence_location_present": occurrence_result.get(
                "adjacent_occurrence_location_present",
                False,
            ),
            "adjacent_occurrence_location_safe_sha256": occurrence_result.get(
                "adjacent_occurrence_location_safe_sha256",
                "",
            ),
            "adjacent_occurrence_structured_location_present": occurrence_result.get(
                "adjacent_occurrence_structured_location_present",
                False,
            ),
            "adjacent_occurrence_structured_location_safe_sha256": occurrence_result.get(
                "adjacent_occurrence_structured_location_safe_sha256",
                "",
            ),
            "adjacent_occurrence_alarm_state_present": occurrence_result.get(
                "adjacent_occurrence_alarm_state_present",
                False,
            ),
            "adjacent_occurrence_alarm_state_safe_sha256": occurrence_result.get(
                "adjacent_occurrence_alarm_state_safe_sha256",
                "",
            ),
        }
    if clear_recurrence:
        occurrence_result = _resolve_event_occurrence_identity_for_plan(
            normalized_handle,
            eventkit_runner=eventkit_runner,
            require_previous_occurrence=mid_series_clear_requested,
            require_no_previous_occurrence=not mid_series_clear_requested,
            require_future_occurrence=True,
            require_supported_recurrence=True,
        )
        if occurrence_result["status"] != "ok":
            return _preview_error(occurrence_result["warnings"])
        expected_recurrence = occurrence_result["recurrence"]
        occurrence_identity = {
            "occurrence_start_date": occurrence_result["occurrence_start_date"],
            "occurrence_end_date": occurrence_result["occurrence_end_date"],
            "future_occurrence_start_date": occurrence_result["future_occurrence_start_date"],
            "future_occurrence_end_date": occurrence_result["future_occurrence_end_date"],
            "recurrence_update_scope": "future_events" if mid_series_clear_requested else "",
            "first_occurrence_verified": not mid_series_clear_requested,
            "mid_series_recurrence_clear_requested": mid_series_clear_requested,
        }
        if mid_series_clear_requested:
            occurrence_identity.update(
                {
                    "previous_occurrence_start_date": occurrence_result[
                        "previous_occurrence_start_date"
                    ],
                    "previous_occurrence_end_date": occurrence_result[
                        "previous_occurrence_end_date"
                    ],
                }
            )
    if mid_series_recurrence_replace_requested:
        occurrence_result = _resolve_event_occurrence_identity_for_plan(
            normalized_handle,
            eventkit_runner=eventkit_runner,
            require_previous_occurrence=True,
            require_future_occurrence=True,
            require_supported_recurrence=True,
        )
        if occurrence_result["status"] != "ok":
            return _preview_error(occurrence_result["warnings"])
        expected_recurrence = occurrence_result["recurrence"]
        occurrence_identity = {
            "occurrence_start_date": occurrence_result["occurrence_start_date"],
            "occurrence_end_date": occurrence_result["occurrence_end_date"],
            "previous_occurrence_start_date": occurrence_result[
                "previous_occurrence_start_date"
            ],
            "previous_occurrence_end_date": occurrence_result["previous_occurrence_end_date"],
            "future_occurrence_start_date": occurrence_result["future_occurrence_start_date"],
            "future_occurrence_end_date": occurrence_result["future_occurrence_end_date"],
            "recurrence_update_scope": "future_events",
            "mid_series_recurrence_replace_requested": True,
        }
    if future_series_update_requested:
        occurrence_result = _resolve_event_occurrence_identity_for_plan(
            normalized_handle,
            eventkit_runner=eventkit_runner,
            require_previous_occurrence=True,
            require_future_occurrence=True,
            require_supported_recurrence=True,
        )
        if occurrence_result["status"] != "ok":
            return _preview_error(occurrence_result["warnings"])
        expected_recurrence = occurrence_result["recurrence"]
        occurrence_identity = {
            "occurrence_start_date": occurrence_result["occurrence_start_date"],
            "occurrence_end_date": occurrence_result["occurrence_end_date"],
            "previous_occurrence_start_date": occurrence_result[
                "previous_occurrence_start_date"
            ],
            "previous_occurrence_end_date": occurrence_result["previous_occurrence_end_date"],
            "future_occurrence_start_date": occurrence_result["future_occurrence_start_date"],
            "future_occurrence_end_date": occurrence_result["future_occurrence_end_date"],
            "recurrence_update_scope": "future_events",
            "future_series_scalar_update_requested": future_series_scalar_update_requested,
            "future_series_reschedule_requested": future_series_reschedule_requested,
            "future_series_availability_update_requested": future_series_availability_update_requested,
            "future_series_event_url_update_requested": future_series_event_url_update_requested,
            "future_series_structured_location_update_requested": (
                future_series_structured_location_update_requested
            ),
            "future_series_display_alarm_update_requested": (
                future_series_display_alarm_update_requested
            ),
            "future_series_action_alarm_update_requested": (
                future_series_action_alarm_update_requested
            ),
            "future_series_all_day_update_requested": (
                future_series_all_day_update_requested
            ),
            "future_series_calendar_move_requested": (
                future_series_calendar_move_requested
            ),
        }

    target = {
        "handle": normalized_handle,
        "expected_state": {
            "title": normalized_expected_title,
            "calendar_title": normalized_expected_calendar,
            "start_date": normalized_expected_start,
            "end_date": normalized_expected_end,
            "time_zone": normalized_expected_time_zone,
            "all_day": normalized_expected_all_day,
            "date_only_input": expected_start_date_only and expected_end_date_only,
            "availability": normalized_expected_availability,
            "availability_name": normalized_expected_availability_name,
            "availability_expected": normalized_expected_availability is not None,
            "alarm_offsets_minutes": normalized_expected_alarm_offsets,
            "alarm_absolute_dates": normalized_expected_alarm_absolute_dates,
            "alarm_sound_name": normalized_expected_alarm_sound_name,
            "alarm_email_address_sha256": normalized_expected_alarm_email_sha256,
            "alarm_proximity": normalized_expected_alarm_proximity,
            "alarm_structured_location": normalized_expected_alarm_structured_location,
            "alarm_action": _alarm_action(
                normalized_expected_alarm_sound_name,
                normalized_expected_alarm_proximity,
                normalized_expected_alarm_email_sha256,
            ),
            "alarm_kind": _alarm_kind(
                normalized_expected_alarm_offsets,
                normalized_expected_alarm_absolute_dates,
                normalized_expected_alarm_proximity,
                normalized_expected_alarm_email_sha256,
            ),
            "recurrence_expected": bool(
                normalized_recurrence and normalized_recurrence["recurrence_present"]
            )
            or clear_recurrence
            or bool(recurrence_update_scope),
            "recurrence_present": bool(clear_recurrence or recurrence_update_scope),
            "recurrence": (
                expected_recurrence
                if clear_recurrence or recurrence_update_scope
                else _empty_recurrence()
            ),
            "event_url_present": normalized_expected_event_url_present,
            "event_url_safe_sha256": normalized_expected_event_url_sha256,
            "location": normalized_expected_location,
            "structured_location_present": bool(normalized_expected_structured_location),
            "structured_location_present_bound": structured_location_state_bound,
            "structured_location": normalized_expected_structured_location,
            "structured_location_expected": bool(normalized_expected_structured_location),
            "notes_text": normalized_expected_notes,
        },
    }
    proposed = {
        "title": normalized_title,
        "calendar_title": normalized_expected_calendar,
        "target_calendar_handle": normalized_target_calendar_handle,
        "calendar_move_requested": bool(normalized_target_calendar_handle),
        "target_calendar_verified": bool(selected_target_calendar),
        "target_calendar_allows_content_modifications": bool(
            selected_target_calendar.get("allows_content_modifications")
        ),
        "target_calendar_title": str(selected_target_calendar.get("title") or ""),
        "start_date": normalized_start,
        "end_date": normalized_end,
        "time_zone": normalized_time_zone,
        "time_zone_bound": bool(normalized_time_zone),
        "all_day": normalized_all_day,
        "all_day_update_requested": selected_all_day_update_requested,
        "all_day_date_reschedule_requested": selected_all_day_date_reschedule_requested,
        "selected_occurrence_calendar_move_requested": selected_calendar_move_requested,
        "date_only_input": start_date_only and end_date_only,
        "availability": normalized_availability,
        "availability_name": normalized_availability_name,
        "availability_requested": normalized_availability is not None,
        "location": normalized_location,
        "location_present": bool(normalized_location),
        "structured_location": normalized_structured_location,
        "structured_location_requested": bool(normalized_structured_location),
        "structured_location_clear_requested": clear_structured_location,
        "notes_text": normalized_notes,
        "notes_chars": len(normalized_notes),
        "notes_present": bool(normalized_notes),
        "attendees_count": 0,
        "alarm_offsets_minutes": normalized_alarm_offsets,
        "alarm_absolute_dates": normalized_alarm_absolute_dates,
        "alarm_sound_name": normalized_alarm_sound_name,
        "alarm_email_address_sha256": alarm_email_sha256,
        "alarm_proximity": normalized_alarm_proximity,
        "alarm_structured_location": normalized_alarm_structured_location,
        "alarm_action": _alarm_action(
            normalized_alarm_sound_name,
            normalized_alarm_proximity,
            alarm_email_sha256,
        ),
        "alarm_kind": _alarm_kind(
            normalized_alarm_offsets,
            normalized_alarm_absolute_dates,
            normalized_alarm_proximity,
            alarm_email_sha256,
        ),
        "display_alarm_update_requested": selected_display_alarm_update_requested,
        "alarm_action_update_requested": selected_alarm_action_update_requested,
        "selected_occurrence_alarm_update_requested": selected_alarm_update_requested,
        "alarms_count": _alarm_count(
            normalized_alarm_offsets,
            normalized_alarm_absolute_dates,
            normalized_alarm_proximity,
        ),
        "recurrence": normalized_recurrence,
        "recurrence_present": bool(
            normalized_recurrence and normalized_recurrence["recurrence_present"]
        ),
        "recurrence_update_scope": recurrence_update_scope,
        "recurrence_clear_requested": clear_recurrence,
        "event_url_requested": bool(normalized_event_url),
        "event_url_clear_requested": clear_event_url,
        "event_url_scheme": event_url_scheme,
        "event_url_domain": event_url_domain,
        "event_url_safe_sha256": event_url_sha256,
        "url_present": bool(normalized_event_url),
        **occurrence_identity,
    }
    fingerprint_proposed = {**proposed, "event_url": normalized_event_url}
    fingerprint_payload = {
        "operation": "update",
        "target": target,
        "proposed": fingerprint_proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": "update",
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _plan_calendar_delete(
    *,
    handle: str,
    expected_title: str,
    expected_calendar_title: str,
    expected_start_date: str,
    expected_end_date: str,
    expected_time_zone: str,
    expected_all_day: bool,
    expected_availability: str,
    expected_alarm_offsets_minutes: list[int] | None,
    expected_alarm_absolute_dates: list[str] | None,
    expected_alarm_sound_name: str,
    expected_alarm_email_address_sha256: str,
    expected_alarm_proximity: str,
    expected_alarm_structured_location: dict[str, Any] | None,
    expected_event_url_present: bool,
    expected_event_url_sha256: str,
    expected_location: str,
    expected_structured_location: dict[str, Any] | None,
    expected_notes: str,
    recurrence_delete_scope: str,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    normalized_handle = handle.strip()
    if not is_opaque_handle(normalized_handle, "calendar:event"):
        warnings.append(
            _warning(
                "invalid_handle",
                "Expected calendar:event:v1 opaque handle from search output.",
            )
        )

    normalized_expected_title, expected_title_warning = _bounded_preview_value(
        expected_title,
        field="expected_title",
        max_chars=MAX_PREVIEW_TITLE_CHARS,
        required=True,
    )
    if expected_title_warning is not None:
        warnings.append(expected_title_warning)

    normalized_expected_calendar, expected_calendar_warning = _bounded_preview_value(
        expected_calendar_title,
        field="expected_calendar_title",
        max_chars=MAX_PREVIEW_CALENDAR_CHARS,
        required=True,
    )
    if expected_calendar_warning is not None:
        warnings.append(expected_calendar_warning)

    normalized_expected_location, expected_location_warning = _bounded_preview_value(
        expected_location,
        field="expected_location",
        max_chars=MAX_LOCATION_CHARS,
        required=False,
    )
    if expected_location_warning is not None:
        warnings.append(expected_location_warning)
    normalized_expected_structured_location, expected_structured_location_warning = (
        _normalize_structured_location(
            expected_structured_location,
            field="expected_structured_location",
        )
    )
    if expected_structured_location_warning is not None:
        warnings.append(expected_structured_location_warning)
    if normalized_expected_structured_location:
        if (
            normalized_expected_location
            and normalized_expected_location != normalized_expected_structured_location["title"]
        ):
            warnings.append(
                _warning(
                    "conflicting_location_fields",
                    "Calendar expected_location must match expected_structured_location.title when both are provided.",
                )
            )
        normalized_expected_location = normalized_expected_structured_location["title"]

    normalized_expected_notes, expected_notes_warning = _bounded_preview_value(
        expected_notes,
        field="expected_notes",
        max_chars=MAX_CONTENT_CHARS,
        required=False,
    )
    if expected_notes_warning is not None:
        warnings.append(expected_notes_warning)

    expected_start_date_only = _is_date_only_input(expected_start_date)
    expected_end_date_only = _is_date_only_input(expected_end_date)
    expected_date_pair_warning = _date_only_pair_warning(
        expected_start_date,
        expected_end_date,
        first_field="expected_start_date",
        second_field="expected_end_date",
    )
    if expected_date_pair_warning is not None:
        warnings.append(expected_date_pair_warning)

    normalized_expected_start, expected_start_warning = _normalize_event_datetime(
        expected_start_date,
        field="expected_start_date",
        allow_date_only=True,
    )
    if expected_start_warning is not None:
        warnings.append(expected_start_warning)

    normalized_expected_end, expected_end_warning = _normalize_event_datetime(
        expected_end_date,
        field="expected_end_date",
        allow_date_only=True,
    )
    if expected_end_warning is not None:
        warnings.append(expected_end_warning)

    if (
        normalized_expected_start
        and normalized_expected_end
        and expected_date_pair_warning is None
    ):
        expected_start_dt = datetime.fromisoformat(
            normalized_expected_start.replace("Z", "+00:00")
        )
        expected_end_dt = datetime.fromisoformat(normalized_expected_end.replace("Z", "+00:00"))
        if expected_end_dt <= expected_start_dt:
            warnings.append(
                _warning(
                    "invalid_expected_state",
                    "Calendar expected_end_date must be after expected_start_date.",
                )
            )

    normalized_expected_time_zone, expected_time_zone_warning = _normalize_time_zone(
        expected_time_zone,
        field="expected_time_zone",
    )
    if expected_time_zone_warning is not None:
        warnings.append(expected_time_zone_warning)

    normalized_expected_all_day, expected_all_day_warning = _normalize_bool_flag(
        expected_all_day, field="expected_all_day"
    )
    if expected_all_day_warning is not None:
        warnings.append(expected_all_day_warning)
    if (
        expected_start_date_only
        and expected_end_date_only
        and normalized_expected_all_day is False
    ):
        normalized_expected_all_day = True
    if normalized_expected_all_day and normalized_expected_time_zone:
        warnings.append(
            _warning(
                "unsupported_time_zone_for_all_day",
                "Calendar expected_time_zone is supported only for timed events.",
            )
        )

    (
        normalized_expected_availability_name,
        normalized_expected_availability,
        expected_availability_warning,
    ) = _normalize_availability(
        expected_availability,
        field="expected_availability",
        allow_not_supported=True,
    )
    if expected_availability_warning is not None:
        warnings.append(expected_availability_warning)

    normalized_expected_alarm_offsets, expected_alarm_warning = _normalize_alarm_offsets(
        expected_alarm_offsets_minutes,
        field="expected_alarm_offsets_minutes",
    )
    if expected_alarm_warning is not None:
        warnings.append(expected_alarm_warning)
    normalized_expected_alarm_absolute_dates, expected_alarm_absolute_warning = (
        _normalize_alarm_absolute_dates(
            expected_alarm_absolute_dates,
            field="expected_alarm_absolute_dates",
        )
    )
    if expected_alarm_absolute_warning is not None:
        warnings.append(expected_alarm_absolute_warning)
    normalized_expected_alarm_sound_name, expected_alarm_sound_warning = (
        _normalize_alarm_sound_name(
            expected_alarm_sound_name,
            field="expected_alarm_sound_name",
        )
    )
    if expected_alarm_sound_warning is not None:
        warnings.append(expected_alarm_sound_warning)
    normalized_expected_alarm_email_sha256, expected_alarm_email_warning = _normalize_sha256(
        expected_alarm_email_address_sha256,
        field="expected_alarm_email_address_sha256",
    )
    if expected_alarm_email_warning is not None:
        warnings.append(expected_alarm_email_warning)
    normalized_expected_alarm_proximity, expected_alarm_proximity_warning = (
        _normalize_alarm_proximity(
            expected_alarm_proximity,
            field="expected_alarm_proximity",
        )
    )
    if expected_alarm_proximity_warning is not None:
        warnings.append(expected_alarm_proximity_warning)
    (
        normalized_expected_alarm_structured_location,
        expected_alarm_structured_location_warning,
    ) = _normalize_structured_location(
        expected_alarm_structured_location,
        field="expected_alarm_structured_location",
    )
    if expected_alarm_structured_location_warning is not None:
        warnings.append(expected_alarm_structured_location_warning)
    expected_alarm_sound_trigger = _alarm_sound_trigger_warning(
        normalized_expected_alarm_sound_name,
        normalized_expected_alarm_offsets,
        normalized_expected_alarm_absolute_dates,
        field="expected_alarm_sound_name",
    )
    if expected_alarm_sound_trigger is not None:
        warnings.append(expected_alarm_sound_trigger)
    expected_alarm_email_trigger = _alarm_email_trigger_warning(
        normalized_expected_alarm_email_sha256,
        normalized_expected_alarm_offsets,
        normalized_expected_alarm_absolute_dates,
        field="expected_alarm_email_address_sha256",
    )
    if expected_alarm_email_trigger is not None:
        warnings.append(expected_alarm_email_trigger)
    expected_alarm_action_conflict = _alarm_action_conflict_warning(
        normalized_expected_alarm_sound_name,
        normalized_expected_alarm_proximity,
        normalized_expected_alarm_email_sha256,
        prefix="expected ",
    )
    if expected_alarm_action_conflict is not None:
        warnings.append(expected_alarm_action_conflict)
    expected_alarm_geofence_location = _alarm_geofence_location_warning(
        normalized_expected_alarm_proximity,
        normalized_expected_alarm_structured_location,
        proximity_field="expected_alarm_proximity",
        location_field="expected_alarm_structured_location",
    )
    if expected_alarm_geofence_location is not None:
        warnings.append(expected_alarm_geofence_location)
    expected_alarm_conflict = _alarm_conflict_warning(
        normalized_expected_alarm_offsets,
        normalized_expected_alarm_absolute_dates,
        normalized_expected_alarm_proximity,
    )
    if expected_alarm_conflict is not None:
        warnings.append(expected_alarm_conflict)

    normalized_expected_event_url_present, expected_event_url_present_warning = (
        _normalize_bool_flag(
            expected_event_url_present,
            field="expected_event_url_present",
        )
    )
    if expected_event_url_present_warning is not None:
        warnings.append(expected_event_url_present_warning)
    normalized_expected_event_url_sha256, expected_event_url_sha256_warning = (
        _normalize_sha256(
            expected_event_url_sha256,
            field="expected_event_url_sha256",
        )
    )
    if expected_event_url_sha256_warning is not None:
        warnings.append(expected_event_url_sha256_warning)
    if normalized_expected_event_url_present and not normalized_expected_event_url_sha256:
        warnings.append(
            _warning(
                "missing_required_field",
                "Calendar expected_event_url_sha256 is required when expected_event_url_present=true.",
            )
        )
    if not normalized_expected_event_url_present and normalized_expected_event_url_sha256:
        warnings.append(
            _warning(
                "invalid_expected_state",
                "Calendar expected_event_url_sha256 requires expected_event_url_present=true.",
            )
        )

    if warnings:
        return _preview_error(warnings)
    occurrence_identity: dict[str, str] = {}
    expected_recurrence = _empty_recurrence()
    if recurrence_delete_scope in RECURRENCE_DELETE_SCOPES:
        occurrence_result = _resolve_event_occurrence_identity_for_plan(
            normalized_handle,
            eventkit_runner=eventkit_runner,
            require_adjacent_occurrence=recurrence_delete_scope == "this_event",
            require_previous_occurrence=recurrence_delete_scope == "future_events",
            require_no_previous_occurrence=recurrence_delete_scope == "all_events",
            require_future_occurrence=recurrence_delete_scope
            in {"future_events", "all_events"},
            require_supported_recurrence=True,
        )
        if occurrence_result["status"] != "ok":
            return _preview_error(occurrence_result["warnings"])
        expected_recurrence = occurrence_result["recurrence"]
        occurrence_identity = {
            "occurrence_start_date": occurrence_result["occurrence_start_date"],
            "occurrence_end_date": occurrence_result["occurrence_end_date"],
        }
        if recurrence_delete_scope == "this_event":
            occurrence_identity.update(
                {
                    "adjacent_occurrence_start_date": occurrence_result[
                        "adjacent_occurrence_start_date"
                    ],
                    "adjacent_occurrence_end_date": occurrence_result[
                        "adjacent_occurrence_end_date"
                    ],
                }
            )
        if recurrence_delete_scope == "future_events":
            occurrence_identity.update(
                {
                    "previous_occurrence_start_date": occurrence_result[
                        "previous_occurrence_start_date"
                    ],
                    "previous_occurrence_end_date": occurrence_result[
                        "previous_occurrence_end_date"
                    ],
                    "future_occurrence_start_date": occurrence_result[
                        "future_occurrence_start_date"
                    ],
                    "future_occurrence_end_date": occurrence_result[
                        "future_occurrence_end_date"
                    ],
                }
            )
        if recurrence_delete_scope == "all_events":
            occurrence_identity.update(
                {
                    "future_occurrence_start_date": occurrence_result[
                        "future_occurrence_start_date"
                    ],
                    "future_occurrence_end_date": occurrence_result[
                        "future_occurrence_end_date"
                    ],
                    "first_occurrence_verified": True,
                }
            )

    target = {
        "handle": normalized_handle,
        "expected_state": {
            "title": normalized_expected_title,
            "calendar_title": normalized_expected_calendar,
            "start_date": normalized_expected_start,
            "end_date": normalized_expected_end,
            "time_zone": normalized_expected_time_zone,
            "all_day": normalized_expected_all_day,
            "date_only_input": expected_start_date_only and expected_end_date_only,
            "availability": normalized_expected_availability,
            "availability_name": normalized_expected_availability_name,
            "availability_expected": normalized_expected_availability is not None,
            "alarm_offsets_minutes": normalized_expected_alarm_offsets,
            "alarm_absolute_dates": normalized_expected_alarm_absolute_dates,
            "alarm_sound_name": normalized_expected_alarm_sound_name,
            "alarm_email_address_sha256": normalized_expected_alarm_email_sha256,
            "alarm_proximity": normalized_expected_alarm_proximity,
            "alarm_structured_location": normalized_expected_alarm_structured_location,
            "alarm_action": _alarm_action(
                normalized_expected_alarm_sound_name,
                normalized_expected_alarm_proximity,
                normalized_expected_alarm_email_sha256,
            ),
            "alarm_kind": _alarm_kind(
                normalized_expected_alarm_offsets,
                normalized_expected_alarm_absolute_dates,
                normalized_expected_alarm_proximity,
                normalized_expected_alarm_email_sha256,
            ),
            "event_url_present": normalized_expected_event_url_present,
            "event_url_safe_sha256": normalized_expected_event_url_sha256,
            "location": normalized_expected_location,
            "structured_location": normalized_expected_structured_location,
            "structured_location_expected": bool(normalized_expected_structured_location),
            "notes_text": normalized_expected_notes,
            "recurrence_expected": bool(recurrence_delete_scope),
            "recurrence_present": bool(recurrence_delete_scope),
            "recurrence": expected_recurrence,
        },
    }
    proposed = {
        "delete": True,
        "time_zone": normalized_expected_time_zone,
        "time_zone_bound": bool(normalized_expected_time_zone),
        "all_day": normalized_expected_all_day,
        "availability": normalized_expected_availability,
        "availability_name": normalized_expected_availability_name,
        "availability_expected": normalized_expected_availability is not None,
        "attendees_count": 0,
        "alarm_offsets_minutes": normalized_expected_alarm_offsets,
        "alarm_absolute_dates": normalized_expected_alarm_absolute_dates,
        "alarm_sound_name": normalized_expected_alarm_sound_name,
        "alarm_email_address_sha256": normalized_expected_alarm_email_sha256,
        "alarm_proximity": normalized_expected_alarm_proximity,
        "alarm_structured_location": normalized_expected_alarm_structured_location,
        "alarm_action": _alarm_action(
            normalized_expected_alarm_sound_name,
            normalized_expected_alarm_proximity,
            normalized_expected_alarm_email_sha256,
        ),
        "alarm_kind": _alarm_kind(
            normalized_expected_alarm_offsets,
            normalized_expected_alarm_absolute_dates,
            normalized_expected_alarm_proximity,
            normalized_expected_alarm_email_sha256,
        ),
        "alarms_count": _alarm_count(
            normalized_expected_alarm_offsets,
            normalized_expected_alarm_absolute_dates,
            normalized_expected_alarm_proximity,
        ),
        "event_url_present": normalized_expected_event_url_present,
        "event_url_safe_sha256": normalized_expected_event_url_sha256,
        "url_present": normalized_expected_event_url_present,
        "recurrence_delete_scope": recurrence_delete_scope,
        "recurrence_present": bool(recurrence_delete_scope),
        **occurrence_identity,
    }
    fingerprint_payload = {
        "operation": "delete",
        "target": target,
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": "delete",
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def apply_calendar_change(
    operation: str,
    *,
    title: str = "",
    calendar_title: str = "",
    calendar_handle: str = "",
    use_default_calendar: bool = False,
    target_calendar_handle: str = "",
    start_date: str = "",
    end_date: str = "",
    time_zone: str = "",
    all_day: bool = False,
    availability: str = "",
    alarm_offsets_minutes: list[int] | None = None,
    alarm_absolute_dates: list[str] | None = None,
    alarm_sound_name: str = "",
    alarm_email_address: str = "",
    alarm_proximity: str = "",
    alarm_structured_location: dict[str, Any] | None = None,
    recurrence_frequency: str = "",
    recurrence_interval: int | None = None,
    recurrence_count: int | None = None,
    recurrence_end_date: str = "",
    recurrence_unbounded: bool = False,
    recurrence_weekdays: list[str | int] | str | None = None,
    recurrence_month_days: list[int] | str | None = None,
    recurrence_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_months: list[int] | str | None = None,
    recurrence_year_month_days: list[int] | str | None = None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_days: list[int] | str | None = None,
    recurrence_year_weeks: list[int] | str | None = None,
    recurrence_set_positions: list[int] | str | None = None,
    recurrence_delete_scope: str = "",
    recurrence_update_scope: str = "",
    clear_recurrence: bool = False,
    event_url: str = "",
    clear_event_url: bool = False,
    location: str = "",
    structured_location: dict[str, Any] | None = None,
    clear_structured_location: bool = False,
    notes: str = "",
    handle: str = "",
    expected_title: str = "",
    expected_calendar_title: str = "",
    expected_start_date: str = "",
    expected_end_date: str = "",
    expected_time_zone: str = "",
    expected_all_day: bool = False,
    expected_availability: str = "",
    expected_alarm_offsets_minutes: list[int] | None = None,
    expected_alarm_absolute_dates: list[str] | None = None,
    expected_alarm_sound_name: str = "",
    expected_alarm_email_address_sha256: str = "",
    expected_alarm_proximity: str = "",
    expected_alarm_structured_location: dict[str, Any] | None = None,
    expected_event_url_present: bool = False,
    expected_event_url_sha256: str = "",
    expected_location: str = "",
    expected_structured_location: dict[str, Any] | None = None,
    expected_notes: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    if use_default_calendar:
        return _apply_error(
            [
                _warning(
                    "default_calendar_plan_only",
                    "Default-calendar resolution is plan-only; apply with the approved preview target calendar_handle.",
                )
            ],
            plan=None,
        )

    runner = eventkit_runner or _run_eventkit_helper
    plan = plan_calendar_change(
        operation,
        title=title,
        calendar_title=calendar_title,
        calendar_handle=calendar_handle,
        target_calendar_handle=target_calendar_handle,
        start_date=start_date,
        end_date=end_date,
        time_zone=time_zone,
        all_day=all_day,
        availability=availability,
        alarm_offsets_minutes=alarm_offsets_minutes,
        alarm_absolute_dates=alarm_absolute_dates,
        alarm_sound_name=alarm_sound_name,
        alarm_email_address=alarm_email_address,
        alarm_proximity=alarm_proximity,
        alarm_structured_location=alarm_structured_location,
        recurrence_frequency=recurrence_frequency,
        recurrence_interval=recurrence_interval,
        recurrence_count=recurrence_count,
        recurrence_end_date=recurrence_end_date,
        recurrence_unbounded=recurrence_unbounded,
        recurrence_weekdays=recurrence_weekdays,
        recurrence_month_days=recurrence_month_days,
        recurrence_month_weekdays=recurrence_month_weekdays,
        recurrence_year_months=recurrence_year_months,
        recurrence_year_month_days=recurrence_year_month_days,
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
        recurrence_year_days=recurrence_year_days,
        recurrence_year_weeks=recurrence_year_weeks,
        recurrence_set_positions=recurrence_set_positions,
        recurrence_delete_scope=recurrence_delete_scope,
        recurrence_update_scope=recurrence_update_scope,
        clear_recurrence=clear_recurrence,
        event_url=event_url,
        clear_event_url=clear_event_url,
        location=location,
        structured_location=structured_location,
        clear_structured_location=clear_structured_location,
        notes=notes,
        handle=handle,
        expected_title=expected_title,
        expected_calendar_title=expected_calendar_title,
        expected_start_date=expected_start_date,
        expected_end_date=expected_end_date,
        expected_time_zone=expected_time_zone,
        expected_all_day=expected_all_day,
        expected_availability=expected_availability,
        expected_alarm_offsets_minutes=expected_alarm_offsets_minutes,
        expected_alarm_absolute_dates=expected_alarm_absolute_dates,
        expected_alarm_sound_name=expected_alarm_sound_name,
        expected_alarm_email_address_sha256=expected_alarm_email_address_sha256,
        expected_alarm_proximity=expected_alarm_proximity,
        expected_alarm_structured_location=expected_alarm_structured_location,
        expected_event_url_present=expected_event_url_present,
        expected_event_url_sha256=expected_event_url_sha256,
        expected_location=expected_location,
        expected_structured_location=expected_structured_location,
        expected_notes=expected_notes,
        eventkit_runner=runner,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan.get("preview")
    if not isinstance(preview, dict):
        return _apply_error(
            [_warning("invalid_plan", "Calendar apply requires a valid plan preview.")],
            plan=plan,
        )
    approval = preview.get("approval")
    fingerprint = approval.get("approval_fingerprint") if isinstance(approval, dict) else None
    expected_token = _approval_token(str(fingerprint or ""))
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Calendar apply requires confirm_apply=true.")],
            plan=plan,
        )
    if not approval_token.strip() or approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Calendar apply approval token did not match the plan.")],
            plan=plan,
        )

    helper_event_url = ""
    if preview.get("operation") in {"create", "update"} and preview["proposed"].get(
        "event_url_requested"
    ):
        (
            helper_event_url,
            _helper_event_url_scheme,
            _helper_event_url_domain,
            helper_event_url_sha256,
            helper_event_url_warning,
        ) = _normalize_event_url(event_url, field="event_url")
        if helper_event_url_warning is not None:
            return _apply_error([helper_event_url_warning], plan=plan)
        if helper_event_url_sha256 != preview["proposed"].get("event_url_safe_sha256"):
            return _apply_error(
                [
                    _warning(
                        "invalid_plan",
                        "Calendar apply event_url did not match the approved preview.",
                    )
                ],
                plan=plan,
            )

    helper_alarm_email_address = ""
    selected_occurrence_email_preserve = (
        preview.get("operation") == "update"
        and preview["proposed"].get("recurrence_update_scope") == "this_event"
        and preview["proposed"].get("alarm_email_address_sha256")
        and not preview["proposed"].get("selected_occurrence_alarm_update_requested")
    )
    if (
        preview.get("operation") in {"create", "update"}
        and preview["proposed"].get("alarm_email_address_sha256")
        and not selected_occurrence_email_preserve
    ):
        (
            helper_alarm_email_address,
            helper_alarm_email_sha256,
            helper_alarm_email_warning,
        ) = _normalize_alarm_email_address(alarm_email_address, field="alarm_email_address")
        if helper_alarm_email_warning is not None:
            return _apply_error([helper_alarm_email_warning], plan=plan)
        if helper_alarm_email_sha256 != preview["proposed"].get("alarm_email_address_sha256"):
            return _apply_error(
                [
                    _warning(
                        "invalid_plan",
                        "Calendar apply alarm_email_address did not match the approved preview.",
                    )
                ],
                plan=plan,
            )

    if preview.get("operation") == "create" and preview["target"].get("calendar_handle"):
        calendar_id_result = _resolve_calendar_id_for_apply(
            str(preview["target"]["calendar_handle"]),
            eventkit_runner=runner,
        )
        if calendar_id_result["status"] != "ok":
            return _apply_error(
                calendar_id_result["warnings"],
                plan=plan,
                status=calendar_id_result["status"],
                authorization_status=calendar_id_result.get("authorization_status"),
            )
        preview = {**preview, "resolved_calendar_id": calendar_id_result["calendar_id"]}
    if preview.get("operation") == "update" and preview["proposed"].get(
        "target_calendar_handle"
    ):
        target_calendar_result = _resolve_calendar_id_for_apply(
            str(preview["proposed"]["target_calendar_handle"]),
            eventkit_runner=runner,
        )
        if target_calendar_result["status"] != "ok":
            return _apply_error(
                target_calendar_result["warnings"],
                plan=plan,
                status=target_calendar_result["status"],
                authorization_status=target_calendar_result.get("authorization_status"),
            )
        preview = {**preview, "resolved_target_calendar_id": target_calendar_result["calendar_id"]}
    if preview.get("operation") in {"update", "delete"}:
        recurrence_delete_scope = str(
            preview.get("proposed", {}).get("recurrence_delete_scope") or ""
        )
        recurrence_update_scope = str(
            preview.get("proposed", {}).get("recurrence_update_scope") or ""
        )
        recurrence_clear_requested = bool(
            preview.get("operation") == "update"
            and preview.get("proposed", {}).get("recurrence_clear_requested")
        )
        recurrence_replace_requested = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and preview.get("proposed", {}).get("recurrence_present")
        )
        mid_series_clear_requested = bool(
            recurrence_clear_requested and recurrence_update_scope == "future_events"
        )
        scoped_occurrence_update = (
            preview.get("operation") == "update"
            and recurrence_update_scope == "this_event"
            and not recurrence_clear_requested
        )
        future_series_scalar_update = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and not recurrence_replace_requested
            and preview.get("proposed", {}).get("future_series_scalar_update_requested")
        )
        future_series_reschedule = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and not recurrence_replace_requested
            and preview.get("proposed", {}).get("future_series_reschedule_requested")
        )
        future_series_availability_update = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and not recurrence_replace_requested
            and preview.get("proposed", {}).get(
                "future_series_availability_update_requested"
            )
        )
        future_series_event_url_update = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and not recurrence_replace_requested
            and preview.get("proposed", {}).get(
                "future_series_event_url_update_requested"
            )
        )
        future_series_structured_location_update = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and not recurrence_replace_requested
            and preview.get("proposed", {}).get(
                "future_series_structured_location_update_requested"
            )
        )
        future_series_display_alarm_update = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and not recurrence_replace_requested
            and preview.get("proposed", {}).get(
                "future_series_display_alarm_update_requested"
            )
        )
        future_series_action_alarm_update = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and not recurrence_replace_requested
            and preview.get("proposed", {}).get(
                "future_series_action_alarm_update_requested"
            )
        )
        future_series_all_day_update = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and not recurrence_replace_requested
            and preview.get("proposed", {}).get(
                "future_series_all_day_update_requested"
            )
        )
        future_series_calendar_move = bool(
            preview.get("operation") == "update"
            and recurrence_update_scope == "future_events"
            and not recurrence_clear_requested
            and not recurrence_replace_requested
            and preview.get("proposed", {}).get(
                "future_series_calendar_move_requested"
            )
        )
        future_series_update = (
            future_series_scalar_update
            or future_series_reschedule
            or future_series_availability_update
            or future_series_event_url_update
            or future_series_structured_location_update
            or future_series_display_alarm_update
            or future_series_action_alarm_update
            or future_series_all_day_update
            or future_series_calendar_move
        )
        scoped_occurrence_delete = (
            preview.get("operation") == "delete"
            and recurrence_delete_scope in RECURRENCE_DELETE_SCOPES
        )
        event_id_result = _resolve_event_id_for_apply(
            str(preview["target"]["handle"]),
            eventkit_runner=runner,
            require_occurrence_identity=scoped_occurrence_delete
            or recurrence_clear_requested
            or scoped_occurrence_update
            or recurrence_replace_requested
            or future_series_update,
            require_adjacent_occurrence=recurrence_delete_scope == "this_event"
            or scoped_occurrence_update,
            require_adjacent_location_proof=scoped_occurrence_update,
            require_adjacent_alarm_proof=scoped_occurrence_update,
            require_previous_occurrence=recurrence_delete_scope == "future_events"
            or mid_series_clear_requested
            or recurrence_replace_requested
            or future_series_update,
            require_no_previous_occurrence=recurrence_delete_scope == "all_events"
            or (recurrence_clear_requested and not mid_series_clear_requested),
            require_future_occurrence=recurrence_delete_scope
            in {"future_events", "all_events"}
            or recurrence_clear_requested
            or recurrence_replace_requested
            or future_series_update,
            require_supported_recurrence=recurrence_clear_requested
            or scoped_occurrence_update
            or recurrence_replace_requested
            or future_series_update,
        )
        if event_id_result["status"] != "ok":
            return _apply_error(
                event_id_result["warnings"],
                plan=plan,
                status=event_id_result["status"],
                authorization_status=event_id_result.get("authorization_status"),
            )
        identity_fields = [
            "occurrence_start_date",
            "occurrence_end_date",
            "adjacent_occurrence_start_date",
            "adjacent_occurrence_end_date",
            "previous_occurrence_start_date",
            "previous_occurrence_end_date",
            "future_occurrence_start_date",
            "future_occurrence_end_date",
        ]
        identity_mismatch = [
            field
            for field in identity_fields
            if preview.get("proposed", {}).get(field)
            and event_id_result.get(field) != preview.get("proposed", {}).get(field)
        ]
        if identity_mismatch:
            return _apply_error(
                [
                    _warning(
                        "stale_occurrence_identity",
                        "Calendar recurring proof identities no longer match the approved plan.",
                    )
                ],
                plan=plan,
                authorization_status=event_id_result.get("authorization_status"),
            )
        if scoped_occurrence_update and (
            event_id_result.get("adjacent_occurrence_event_url_present")
            != preview.get("proposed", {}).get("adjacent_occurrence_event_url_present")
            or event_id_result.get("adjacent_occurrence_event_url_safe_sha256", "")
            != preview.get("proposed", {}).get(
                "adjacent_occurrence_event_url_safe_sha256",
                "",
            )
            or event_id_result.get("adjacent_occurrence_location_present")
            != preview.get("proposed", {}).get("adjacent_occurrence_location_present")
            or event_id_result.get("adjacent_occurrence_location_safe_sha256", "")
            != preview.get("proposed", {}).get(
                "adjacent_occurrence_location_safe_sha256",
                "",
            )
            or event_id_result.get("adjacent_occurrence_structured_location_present")
            != preview.get("proposed", {}).get(
                "adjacent_occurrence_structured_location_present"
            )
            or event_id_result.get("adjacent_occurrence_structured_location_safe_sha256", "")
            != preview.get("proposed", {}).get(
                "adjacent_occurrence_structured_location_safe_sha256",
                "",
            )
            or event_id_result.get("adjacent_occurrence_alarm_state_present")
            != preview.get("proposed", {}).get("adjacent_occurrence_alarm_state_present")
            or event_id_result.get("adjacent_occurrence_alarm_state_safe_sha256", "")
            != preview.get("proposed", {}).get(
                "adjacent_occurrence_alarm_state_safe_sha256",
                "",
            )
        ):
            return _apply_error(
                [
                    _warning(
                        "stale_occurrence_identity",
                        "Calendar recurring sibling URL, location, or alarm state no longer matches the approved plan.",
                    )
                ],
                plan=plan,
                authorization_status=event_id_result.get("authorization_status"),
            )
        if (
            recurrence_clear_requested
            or scoped_occurrence_update
            or recurrence_replace_requested
            or future_series_update
        ) and event_id_result.get(
            "recurrence"
        ) != preview["target"]["expected_state"].get("recurrence"):
            return _apply_error(
                [
                    _warning(
                        "stale_recurrence_state",
                        "Calendar recurrence state no longer matches the approved plan.",
                    )
                ],
                plan=plan,
                authorization_status=event_id_result.get("authorization_status"),
            )
        preview = {**preview, "resolved_event_id": event_id_result["event_id"]}
        if event_id_result.get("occurrence_start_date") and event_id_result.get(
            "occurrence_end_date"
        ):
            preview = {
                **preview,
                "resolved_occurrence_start_date": event_id_result["occurrence_start_date"],
                "resolved_occurrence_end_date": event_id_result["occurrence_end_date"],
            }
        if event_id_result.get("adjacent_occurrence_start_date") and event_id_result.get(
            "adjacent_occurrence_end_date"
        ):
            preview = {
                **preview,
                "resolved_adjacent_occurrence_start_date": event_id_result[
                    "adjacent_occurrence_start_date"
                ],
                "resolved_adjacent_occurrence_end_date": event_id_result[
                    "adjacent_occurrence_end_date"
                ],
            }
        if event_id_result.get("previous_occurrence_start_date") and event_id_result.get(
            "previous_occurrence_end_date"
        ):
            preview = {
                **preview,
                "resolved_previous_occurrence_start_date": event_id_result[
                    "previous_occurrence_start_date"
                ],
                "resolved_previous_occurrence_end_date": event_id_result[
                    "previous_occurrence_end_date"
                ],
            }
        if event_id_result.get("future_occurrence_start_date") and event_id_result.get(
            "future_occurrence_end_date"
        ):
            preview = {
                **preview,
                "resolved_future_occurrence_start_date": event_id_result[
                    "future_occurrence_start_date"
                ],
                "resolved_future_occurrence_end_date": event_id_result[
                    "future_occurrence_end_date"
                ],
            }

    try:
        applied = runner(
            _apply_helper_payload(
                preview,
                event_url=helper_event_url,
                alarm_email_address=helper_alarm_email_address,
            ),
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("eventkit_timeout", "Calendar apply timed out through the local EventKit helper.")],
            plan=plan,
            status="apply_unknown",
        )
    except (OSError, ValueError):
        return _apply_error(
            [_warning("eventkit_unavailable", "Calendar apply is unavailable through the local EventKit helper.")],
            plan=plan,
        )

    if applied.get("status") != "ok":
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("eventkit_apply_failed", "Calendar event could not be changed safely.")],
            plan=plan,
            status=str(applied.get("status") or "error"),
            authorization_status=applied.get("authorization_status"),
        )

    if preview.get("operation") == "delete":
        read_back = applied.get("read_back")
        if not applied.get("deleted") or not isinstance(read_back, dict) or not read_back.get(
            "verified_absent"
        ):
            return _apply_error(
                [
                    _warning(
                        "read_back_unavailable",
                        "Calendar delete succeeded but absence proof was unavailable.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        if preview.get("proposed", {}).get("recurrence_delete_scope") == "this_event":
            if not read_back.get("selected_occurrence_verified_absent") or not read_back.get(
                "adjacent_occurrence_verified_present"
            ):
                return _apply_error(
                    [
                        _warning(
                            "read_back_unavailable",
                            "Calendar recurring occurrence delete lacked selected-absence plus adjacent-presence proof.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
        if preview.get("proposed", {}).get("recurrence_delete_scope") == "future_events":
            if (
                not read_back.get("selected_occurrence_verified_absent")
                or not read_back.get("future_occurrence_verified_absent")
                or not read_back.get("previous_occurrence_verified_present")
            ):
                return _apply_error(
                    [
                        _warning(
                            "read_back_unavailable",
                            "Calendar future recurring delete lacked selected/future absence plus previous-occurrence preservation proof.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
        if preview.get("proposed", {}).get("recurrence_delete_scope") == "all_events":
            if (
                not read_back.get("selected_occurrence_verified_absent")
                or not read_back.get("future_occurrence_verified_absent")
                or not read_back.get("previous_occurrence_verified_absent")
            ):
                return _apply_error(
                    [
                        _warning(
                            "read_back_unavailable",
                            "Calendar whole-series recurring delete lacked selected/future absence plus previous-occurrence absence proof.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
        read_back_payload: dict[str, Any] = {
            "handle": preview["target"]["handle"],
            "deleted": True,
            "verified_absent": True,
        }
        if preview.get("proposed", {}).get("recurrence_delete_scope") == "this_event":
            read_back_payload.update(
                {
                    "selected_occurrence_verified_absent": True,
                    "adjacent_occurrence_verified_present": True,
                }
            )
        if preview.get("proposed", {}).get("recurrence_delete_scope") == "future_events":
            read_back_payload.update(
                {
                    "selected_occurrence_verified_absent": True,
                    "future_occurrence_verified_absent": True,
                    "previous_occurrence_verified_present": True,
                }
            )
        if preview.get("proposed", {}).get("recurrence_delete_scope") == "all_events":
            read_back_payload.update(
                {
                    "selected_occurrence_verified_absent": True,
                    "future_occurrence_verified_absent": True,
                    "previous_occurrence_verified_absent": True,
                }
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": _mutation_privacy(content_inspected=False),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": "delete",
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": read_back_payload,
            "result_count": 1,
            "warnings": _safe_warnings(applied),
        }

    event = applied.get("event")
    if not isinstance(event, dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Calendar apply succeeded but read-back was unavailable.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )

    read_back = _event_metadata(event, include_alarm_offsets=True, include_time_zone=True)
    if preview["proposed"].get("event_url_requested"):
        proposed_url_sha256 = preview["proposed"].get("event_url_safe_sha256")
        if (
            not event.get("url_present")
            or event.get("event_url_safe_sha256") != proposed_url_sha256
        ):
            return _apply_error(
                [
                    _warning(
                        "event_url_read_back_mismatch",
                        "Calendar apply succeeded but event URL read-back did not match the approved value.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["event_url_verified"] = True
    if preview["proposed"].get("event_url_clear_requested"):
        if event.get("url_present") is not False:
            return _apply_error(
                [
                    _warning(
                        "event_url_clear_read_back_mismatch",
                        "Calendar apply succeeded but event URL absence was not verified on read-back.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["event_url_cleared_verified"] = True
    if preview["proposed"].get("alarm_email_address_sha256"):
        proposed_alarm_email_sha256 = preview["proposed"].get("alarm_email_address_sha256")
        if event.get("alarm_email_address_sha256") != proposed_alarm_email_sha256:
            return _apply_error(
                [
                    _warning(
                        "alarm_email_read_back_mismatch",
                        "Calendar apply succeeded but email alarm read-back did not match the approved value.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["alarm_email_address_sha256_verified"] = True
    if preview["proposed"].get("structured_location_clear_requested"):
        if (
            event.get("structured_location_present") is not False
            or event.get("location_present") is not False
        ):
            return _apply_error(
                [
                    _warning(
                        "structured_location_clear_read_back_mismatch",
                        "Calendar apply succeeded but structured/plain location absence was not verified on read-back.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["structured_location_cleared_verified"] = True
    if preview["proposed"].get("availability_requested") and event.get("availability") != preview[
        "proposed"
    ].get("availability"):
        return _apply_error(
            [
                _warning(
                    "availability_read_back_mismatch",
                    "Calendar apply succeeded but availability read-back did not match the approved value.",
                )
            ],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )
    if preview["proposed"].get("alarms_count") and event.get("alarm_sound_name", "") != preview[
        "proposed"
    ].get("alarm_sound_name", ""):
        return _apply_error(
            [
                _warning(
                    "alarm_sound_read_back_mismatch",
                    "Calendar apply succeeded but alarm sound read-back did not match the approved value.",
                )
            ],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )
    if preview["proposed"].get("alarm_sound_name"):
        read_back["alarm_sound_name_verified"] = True
    if preview["proposed"].get("alarm_proximity"):
        if event.get("alarm_proximity") != preview["proposed"].get("alarm_proximity"):
            return _apply_error(
                [
                    _warning(
                        "alarm_geofence_read_back_mismatch",
                        "Calendar apply succeeded but alarm geofence proximity read-back did not match the approved value.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        if event.get("alarm_structured_location") != preview["proposed"].get(
            "alarm_structured_location"
        ):
            return _apply_error(
                [
                    _warning(
                        "alarm_geofence_read_back_mismatch",
                        "Calendar apply succeeded but alarm geofence location read-back did not match the approved value.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["alarm_geofence_verified"] = True
    if preview["proposed"].get("recurrence_present") and event.get("recurrence") != preview[
        "proposed"
    ].get("recurrence"):
        return _apply_error(
            [
                _warning(
                    "recurrence_read_back_mismatch",
                    "Calendar apply succeeded but recurrence read-back did not match the approved value.",
                )
            ],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )
    if preview["proposed"].get("recurrence_clear_requested"):
        helper_read_back = applied.get("read_back")
        mid_series_clear_requested = (
            preview["proposed"].get("recurrence_update_scope") == "future_events"
        )
        previous_proof_key = (
            "previous_occurrence_verified_present"
            if mid_series_clear_requested
            else "previous_occurrence_verified_absent"
        )
        if (
            event.get("recurrence_present") is not False
            or not isinstance(helper_read_back, dict)
            or not helper_read_back.get("recurrence_cleared_verified")
            or not helper_read_back.get("future_occurrence_verified_absent")
            or not helper_read_back.get(previous_proof_key)
        ):
            return _apply_error(
                [
                    _warning(
                        "recurrence_clear_read_back_mismatch",
                        "Calendar apply succeeded but recurrence clear proof was incomplete.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["recurrence_cleared_verified"] = True
        read_back["future_occurrence_verified_absent"] = True
        read_back[previous_proof_key] = True
        if mid_series_clear_requested:
            read_back["recurrence_update_scope"] = "future_events"
    if (
        preview["proposed"].get("recurrence_update_scope") == "future_events"
        and preview["proposed"].get("recurrence_present")
        and not preview["proposed"].get("recurrence_clear_requested")
    ):
        helper_read_back = applied.get("read_back")
        if (
            not isinstance(helper_read_back, dict)
            or not helper_read_back.get("recurrence_replaced_verified")
            or not helper_read_back.get("previous_occurrence_verified_present")
            or not helper_read_back.get("future_occurrence_verified_present")
            or not helper_read_back.get(
                "future_original_slot_verified_replaced_or_absent"
            )
        ):
            return _apply_error(
                [
                    _warning(
                        "recurrence_replacement_read_back_mismatch",
                        "Calendar apply succeeded but mid-series recurrence replacement proof was incomplete.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["recurrence_update_scope"] = "future_events"
        read_back["recurrence_replaced_verified"] = True
        read_back["previous_occurrence_verified_present"] = True
        read_back["future_occurrence_verified_present"] = True
        read_back["future_original_slot_verified_replaced_or_absent"] = True
    if (
        preview["proposed"].get("future_series_scalar_update_requested")
        or preview["proposed"].get("future_series_reschedule_requested")
        or preview["proposed"].get("future_series_availability_update_requested")
        or preview["proposed"].get("future_series_event_url_update_requested")
        or preview["proposed"].get("future_series_structured_location_update_requested")
        or preview["proposed"].get("future_series_display_alarm_update_requested")
        or preview["proposed"].get("future_series_action_alarm_update_requested")
        or preview["proposed"].get("future_series_all_day_update_requested")
        or preview["proposed"].get("future_series_calendar_move_requested")
    ):
        helper_read_back = applied.get("read_back")
        future_series_rescheduled = bool(
            preview["proposed"].get("future_series_reschedule_requested")
        )
        future_series_availability_updated = bool(
            preview["proposed"].get("future_series_availability_update_requested")
        )
        future_series_event_url_updated = bool(
            preview["proposed"].get("future_series_event_url_update_requested")
        )
        future_series_structured_location_updated = bool(
            preview["proposed"].get(
                "future_series_structured_location_update_requested"
            )
        )
        future_series_display_alarm_updated = bool(
            preview["proposed"].get(
                "future_series_display_alarm_update_requested"
            )
        )
        future_series_action_alarm_updated = bool(
            preview["proposed"].get(
                "future_series_action_alarm_update_requested"
            )
        )
        future_series_all_day_updated = bool(
            preview["proposed"].get(
                "future_series_all_day_update_requested"
            )
        )
        future_series_calendar_moved = bool(
            preview["proposed"].get(
                "future_series_calendar_move_requested"
            )
        )
        future_series_dates_changed = (
            preview["proposed"].get("start_date")
            != preview["target"]["expected_state"].get("start_date")
            or preview["proposed"].get("end_date")
            != preview["target"]["expected_state"].get("end_date")
            or preview["proposed"].get("all_day")
            != preview["target"]["expected_state"].get("all_day")
        )
        original_slot_verified = bool(
            isinstance(helper_read_back, dict)
            and (
                helper_read_back.get("original_occurrence_verified_absent")
                or helper_read_back.get("original_occurrence_verified_absent_or_replaced")
            )
        )
        future_original_slot_verified = bool(
            isinstance(helper_read_back, dict)
            and (
                helper_read_back.get("future_original_occurrence_verified_absent")
                or helper_read_back.get(
                    "future_original_occurrence_verified_absent_or_replaced"
                )
            )
        )
        if (
            not isinstance(helper_read_back, dict)
            or not helper_read_back.get("selected_occurrence_updated_verified")
            or not helper_read_back.get("future_occurrence_updated_verified")
            or not helper_read_back.get("previous_occurrence_verified_present")
            or (
                preview["proposed"].get("future_series_scalar_update_requested")
                and not helper_read_back.get("future_series_scalar_updated_verified")
            )
            or (
                future_series_rescheduled
                and not helper_read_back.get("future_series_rescheduled_verified")
            )
            or (
                future_series_availability_updated
                and not helper_read_back.get(
                    "future_series_availability_updated_verified"
                )
            )
            or (
                future_series_event_url_updated
                and not helper_read_back.get(
                    "future_series_event_url_updated_verified"
                )
            )
            or (
                future_series_structured_location_updated
                and not helper_read_back.get(
                    "future_series_structured_location_updated_verified"
                )
            )
            or (
                future_series_display_alarm_updated
                and not helper_read_back.get(
                    "future_series_display_alarm_updated_verified"
                )
            )
            or (
                future_series_action_alarm_updated
                and not helper_read_back.get(
                    "future_series_action_alarm_updated_verified"
                )
            )
            or (
                future_series_all_day_updated
                and not helper_read_back.get(
                    "future_series_all_day_updated_verified"
                )
            )
            or (
                future_series_calendar_moved
                and not helper_read_back.get(
                    "future_series_calendar_move_verified"
                )
            )
            or (
                future_series_calendar_moved
                and not helper_read_back.get(
                    "previous_occurrence_calendar_verified"
                )
            )
            or (
                future_series_dates_changed
                and (not original_slot_verified or not future_original_slot_verified)
            )
        ):
            return _apply_error(
                [
                    _warning(
                        "future_series_update_read_back_mismatch",
                        "Calendar apply succeeded but future-series update proof was incomplete.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["recurrence_update_scope"] = "future_events"
        if preview["proposed"].get("future_series_scalar_update_requested"):
            read_back["future_series_scalar_updated_verified"] = True
        if future_series_rescheduled:
            read_back["future_series_rescheduled_verified"] = True
        if future_series_availability_updated:
            read_back["future_series_availability_updated_verified"] = True
        if future_series_event_url_updated:
            read_back["future_series_event_url_updated_verified"] = True
        if future_series_structured_location_updated:
            read_back["future_series_structured_location_updated_verified"] = True
        if future_series_display_alarm_updated:
            read_back["future_series_display_alarm_updated_verified"] = True
        if future_series_action_alarm_updated:
            read_back["future_series_action_alarm_updated_verified"] = True
        if future_series_all_day_updated:
            read_back["future_series_all_day_updated_verified"] = True
        if future_series_calendar_moved:
            read_back["future_series_calendar_move_verified"] = True
            read_back["previous_occurrence_calendar_verified"] = True
        if future_series_dates_changed:
            read_back["original_occurrence_verified_absent"] = bool(
                helper_read_back.get("original_occurrence_verified_absent")
            )
            read_back["future_original_occurrence_verified_absent"] = bool(
                helper_read_back.get("future_original_occurrence_verified_absent")
            )
            read_back["original_occurrence_verified_absent_or_replaced"] = (
                original_slot_verified
            )
            read_back["future_original_occurrence_verified_absent_or_replaced"] = (
                future_original_slot_verified
            )
        read_back["selected_occurrence_updated_verified"] = True
        read_back["future_occurrence_updated_verified"] = True
        read_back["previous_occurrence_verified_present"] = True
    if preview["proposed"].get("recurrence_update_scope") == "this_event":
        helper_read_back = applied.get("read_back")
        if (
            not isinstance(helper_read_back, dict)
            or not helper_read_back.get("selected_occurrence_updated_verified")
            or not helper_read_back.get("adjacent_occurrence_verified_present")
            or (
                helper_read_back.get("selected_occurrence_rescheduled_verified")
                and not helper_read_back.get("original_occurrence_verified_absent")
            )
        ):
            return _apply_error(
                [
                    _warning(
                        "recurring_occurrence_update_read_back_mismatch",
                        "Calendar apply succeeded but selected recurring occurrence update proof was incomplete.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        if not helper_read_back.get("adjacent_occurrence_event_url_verified"):
            return _apply_error(
                [
                    _warning(
                        "adjacent_occurrence_event_url_read_back_mismatch",
                        "Calendar apply succeeded but adjacent occurrence URL state was not preserved.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        if not helper_read_back.get("adjacent_occurrence_location_verified"):
            return _apply_error(
                [
                    _warning(
                        "adjacent_occurrence_location_read_back_mismatch",
                        "Calendar apply succeeded but adjacent occurrence location state was not preserved.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        if not helper_read_back.get("adjacent_occurrence_alarm_verified"):
            return _apply_error(
                [
                    _warning(
                        "adjacent_occurrence_alarm_read_back_mismatch",
                        "Calendar apply succeeded but adjacent occurrence alarm state was not preserved.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["recurrence_update_scope"] = "this_event"
        read_back["selected_occurrence_updated_verified"] = True
        read_back["adjacent_occurrence_verified_present"] = True
        read_back["adjacent_occurrence_event_url_verified"] = True
        read_back["adjacent_occurrence_location_verified"] = True
        read_back["adjacent_occurrence_alarm_verified"] = True
        if preview["proposed"].get("selected_occurrence_calendar_move_requested"):
            if not helper_read_back.get("selected_occurrence_calendar_move_verified"):
                return _apply_error(
                    [
                        _warning(
                            "target_calendar_read_back_mismatch",
                            "Calendar apply succeeded but selected occurrence target calendar proof was incomplete.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            if not helper_read_back.get("adjacent_occurrence_calendar_verified"):
                return _apply_error(
                    [
                        _warning(
                            "adjacent_occurrence_calendar_read_back_mismatch",
                            "Calendar apply succeeded but adjacent occurrence calendar state was not preserved.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["selected_occurrence_calendar_move_verified"] = True
            read_back["adjacent_occurrence_calendar_verified"] = True
        if preview["proposed"].get("all_day_update_requested") or preview["proposed"].get(
            "all_day_date_reschedule_requested"
        ):
            if not helper_read_back.get("all_day_verified"):
                return _apply_error(
                    [
                        _warning(
                            "all_day_read_back_mismatch",
                            "Calendar apply succeeded but selected occurrence all-day proof was incomplete.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["all_day_verified"] = True
        if helper_read_back.get("selected_occurrence_rescheduled_verified"):
            read_back["selected_occurrence_rescheduled_verified"] = True
            read_back["original_occurrence_verified_absent"] = bool(
                helper_read_back.get("original_occurrence_verified_absent")
            )
        if preview["proposed"].get("structured_location_requested"):
            if not helper_read_back.get("structured_location_verified"):
                return _apply_error(
                    [
                        _warning(
                            "structured_location_read_back_mismatch",
                            "Calendar apply succeeded but selected occurrence structured location proof was incomplete.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["structured_location_verified"] = True
        if preview["proposed"].get("structured_location_clear_requested"):
            if not helper_read_back.get("structured_location_cleared_verified"):
                return _apply_error(
                    [
                        _warning(
                            "structured_location_clear_read_back_mismatch",
                            "Calendar apply succeeded but selected occurrence structured location clear proof was incomplete.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["structured_location_cleared_verified"] = True
        if preview["proposed"].get("display_alarm_update_requested"):
            if not helper_read_back.get("display_alarm_verified"):
                return _apply_error(
                    [
                        _warning(
                            "display_alarm_read_back_mismatch",
                            "Calendar apply succeeded but selected occurrence display alarm proof was incomplete.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["display_alarm_verified"] = True
        if preview["proposed"].get("alarm_action_update_requested"):
            if not helper_read_back.get("action_alarm_verified"):
                return _apply_error(
                    [
                        _warning(
                            "alarm_action_read_back_mismatch",
                            "Calendar apply succeeded but selected occurrence action alarm proof was incomplete.",
                        )
                    ],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["alarm_action_verified"] = True
    if preview["proposed"].get("structured_location_requested"):
        if event.get("structured_location") != preview["proposed"].get("structured_location"):
            return _apply_error(
                [
                    _warning(
                        "structured_location_read_back_mismatch",
                        "Calendar apply succeeded but structured location read-back did not match the approved value.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["structured_location_verified"] = True
    target_calendar_handle = ""
    target_calendar_id = ""
    if preview.get("operation") == "create" and preview["target"].get("calendar_handle"):
        target_calendar_handle = str(preview["target"]["calendar_handle"])
        target_calendar_id = str(preview.get("resolved_calendar_id") or "")
    elif preview.get("operation") == "update" and preview["proposed"].get(
        "target_calendar_handle"
    ):
        target_calendar_handle = str(preview["proposed"]["target_calendar_handle"])
        target_calendar_id = str(preview.get("resolved_target_calendar_id") or "")
    if target_calendar_handle:
        if not target_calendar_id or str(event.get("calendar_id") or "") != target_calendar_id:
            return _apply_error(
                [
                    _warning(
                        "target_calendar_read_back_mismatch",
                        "Calendar apply succeeded but target calendar read-back did not match the approved target.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["target_calendar_handle"] = target_calendar_handle
        read_back["target_calendar_verified"] = True

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _mutation_privacy(content_inspected=False),
        "authorization_status": applied.get("authorization_status"),
        "mode": "apply",
        "operation": str(preview["operation"]),
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": _safe_warnings(applied),
    }


def _resolve_event_id_for_apply(
    handle: str,
    *,
    eventkit_runner: EventKitRunner,
    require_occurrence_identity: bool = False,
    require_adjacent_occurrence: bool = False,
    require_adjacent_location_proof: bool = False,
    require_adjacent_alarm_proof: bool = False,
    require_previous_occurrence: bool = False,
    require_no_previous_occurrence: bool = False,
    require_future_occurrence: bool = False,
    require_supported_recurrence: bool = False,
) -> dict[str, Any]:
    response = _calendar_events_response(
        query="",
        limit=DEFAULT_MAX_SCAN_EVENTS,
        days_back=DEFAULT_DAYS_BACK,
        days_forward=DEFAULT_DAYS_FORWARD,
        max_scan_events=DEFAULT_MAX_SCAN_EVENTS,
        include_url_proof=require_adjacent_occurrence,
        include_location_proof=require_adjacent_location_proof,
        include_structured_location_proof=require_adjacent_location_proof,
        include_alarm_proof=require_adjacent_alarm_proof,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return {
            "status": "degraded",
            "authorization_status": response.get("authorization_status"),
            "warnings": _safe_warnings(response),
        }
    event_ref = _resolve_event_reference(handle, response.get("events", []))
    if event_ref is None:
        return {
            "status": "not_found",
            "authorization_status": response.get("authorization_status"),
            "warnings": [_warning("target_not_found", "Calendar target was not found.")],
        }
    if require_occurrence_identity and not (
        event_ref.get("start_date") and event_ref.get("end_date")
    ):
        return {
            "status": "error",
            "authorization_status": response.get("authorization_status"),
            "warnings": [
                _warning(
                    "missing_occurrence_identity",
                    "Selected recurring occurrence delete requires a current calendar:event handle that binds event start and end.",
                )
            ],
        }
    if require_occurrence_identity and event_ref.get("recurrence_present") is not True:
        return {
            "status": "error",
            "authorization_status": response.get("authorization_status"),
            "warnings": [
                _warning(
                    "expected_state_mismatch",
                    "Calendar event did not match expected recurrence state.",
                )
            ],
        }
    if require_supported_recurrence:
        recurrence = event_ref.get("recurrence")
        if not isinstance(recurrence, dict) or recurrence.get("recurrence_present") is not True:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "unsupported_event_state",
                        "Calendar event recurrence is not a supported bounded simple rule.",
                    )
                ],
            }
    result = {
        "status": "ok",
        "authorization_status": response.get("authorization_status"),
        "event_id": event_ref["event_id"],
        "occurrence_start_date": event_ref.get("start_date", ""),
        "occurrence_end_date": event_ref.get("end_date", ""),
        "warnings": _safe_warnings(response),
    }
    if require_supported_recurrence:
        result["recurrence"] = event_ref["recurrence"]
    if require_adjacent_occurrence:
        adjacent = _find_adjacent_event_occurrence(response.get("events", []), event_ref)
        if adjacent is None:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "adjacent_occurrence_not_found",
                        "Selected recurring occurrence delete requires a sibling occurrence for read-back preservation proof.",
                    )
                ],
            }
        adjacent_event_url_present = bool(adjacent.get("url_present"))
        adjacent_event_url_sha256 = str(adjacent.get("event_url_safe_sha256") or "")
        if adjacent_event_url_present and not adjacent_event_url_sha256:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "adjacent_occurrence_url_proof_unavailable",
                        "Selected recurring occurrence update requires hash-only sibling URL proof.",
                    )
                ],
            }
        adjacent_identity = {
            "adjacent_occurrence_start_date": adjacent["start_date"],
            "adjacent_occurrence_end_date": adjacent["end_date"],
            "adjacent_occurrence_event_url_present": adjacent_event_url_present,
            "adjacent_occurrence_event_url_safe_sha256": adjacent_event_url_sha256,
        }
        if require_adjacent_location_proof:
            adjacent_location_present = bool(adjacent.get("location_present"))
            adjacent_location_sha256 = str(adjacent.get("location_safe_sha256") or "")
            if adjacent_location_present and not adjacent_location_sha256:
                return {
                    "status": "error",
                    "authorization_status": response.get("authorization_status"),
                    "warnings": [
                        _warning(
                            "adjacent_occurrence_location_proof_unavailable",
                            "Selected recurring occurrence update requires hash-only sibling location proof.",
                        )
                    ],
                }
            adjacent_structured_location_present = bool(
                adjacent.get("structured_location_present")
            )
            adjacent_structured_location_sha256 = str(
                adjacent.get("structured_location_safe_sha256") or ""
            )
            if (
                adjacent_structured_location_present
                and not adjacent_structured_location_sha256
            ):
                return {
                    "status": "error",
                    "authorization_status": response.get("authorization_status"),
                    "warnings": [
                        _warning(
                            "adjacent_occurrence_structured_location_proof_unavailable",
                            "Selected recurring occurrence update requires hash-only sibling structured-location proof.",
                        )
                    ],
                }
            adjacent_identity.update(
                {
                    "adjacent_occurrence_location_present": adjacent_location_present,
                    "adjacent_occurrence_location_safe_sha256": adjacent_location_sha256,
                    "adjacent_occurrence_structured_location_present": (
                        adjacent_structured_location_present
                    ),
                    "adjacent_occurrence_structured_location_safe_sha256": (
                        adjacent_structured_location_sha256
                    ),
                }
            )
        if require_adjacent_alarm_proof:
            adjacent_alarm_present = bool(adjacent.get("alarm_state_present"))
            adjacent_alarm_sha256 = str(adjacent.get("alarm_state_safe_sha256") or "")
            if adjacent_alarm_present and not adjacent_alarm_sha256:
                return {
                    "status": "error",
                    "authorization_status": response.get("authorization_status"),
                    "warnings": [
                        _warning(
                            "adjacent_occurrence_alarm_proof_unavailable",
                            "Selected recurring occurrence update requires hash-only sibling alarm-state proof.",
                        )
                    ],
                }
            adjacent_identity.update(
                {
                    "adjacent_occurrence_alarm_state_present": adjacent_alarm_present,
                    "adjacent_occurrence_alarm_state_safe_sha256": adjacent_alarm_sha256,
                }
            )
        result.update(adjacent_identity)
    if require_previous_occurrence:
        previous = _find_relative_event_occurrence(
            response.get("events", []),
            event_ref,
            direction="previous",
        )
        if previous is None:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "previous_occurrence_not_found",
                        "Future recurring occurrence delete requires a previous same-series occurrence for preservation proof.",
                    )
                ],
            }
        result.update(
            {
                "previous_occurrence_start_date": previous["start_date"],
                "previous_occurrence_end_date": previous["end_date"],
            }
        )
    if require_no_previous_occurrence:
        previous = _find_relative_event_occurrence(
            response.get("events", []),
            event_ref,
            direction="previous",
        )
        if previous is not None:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "previous_occurrence_present",
                        "Whole-series recurring delete requires selecting the first same-series occurrence.",
                    )
                ],
            }
    if require_future_occurrence:
        future = _find_relative_event_occurrence(
            response.get("events", []),
            event_ref,
            direction="future",
        )
        if future is None:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "future_occurrence_not_found",
                        "Future recurring occurrence delete requires a future same-series occurrence for absence proof.",
                    )
                ],
            }
        result.update(
            {
                "future_occurrence_start_date": future["start_date"],
                "future_occurrence_end_date": future["end_date"],
            }
        )
    return result


def _resolve_event_occurrence_identity_for_plan(
    handle: str,
    *,
    eventkit_runner: EventKitRunner | None,
    require_adjacent_occurrence: bool = False,
    require_adjacent_location_proof: bool = False,
    require_adjacent_alarm_proof: bool = False,
    require_previous_occurrence: bool = False,
    require_no_previous_occurrence: bool = False,
    require_future_occurrence: bool = False,
    require_supported_recurrence: bool = False,
) -> dict[str, Any]:
    response = _calendar_events_response(
        query="",
        limit=DEFAULT_MAX_SCAN_EVENTS,
        days_back=DEFAULT_DAYS_BACK,
        days_forward=DEFAULT_DAYS_FORWARD,
        max_scan_events=DEFAULT_MAX_SCAN_EVENTS,
        include_url_proof=require_adjacent_occurrence,
        include_location_proof=require_adjacent_location_proof,
        include_structured_location_proof=require_adjacent_location_proof,
        include_alarm_proof=require_adjacent_alarm_proof,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return {
            "status": "degraded",
            "authorization_status": response.get("authorization_status"),
            "warnings": _safe_warnings(response),
        }
    event_ref = _resolve_event_reference(handle, response.get("events", []))
    if event_ref is None:
        return {
            "status": "not_found",
            "authorization_status": response.get("authorization_status"),
            "warnings": [_warning("target_not_found", "Calendar target was not found.")],
        }
    if not (event_ref.get("start_date") and event_ref.get("end_date")):
        return {
            "status": "error",
            "authorization_status": response.get("authorization_status"),
            "warnings": [
                _warning(
                    "missing_occurrence_identity",
                    "Selected recurring occurrence delete requires a current calendar:event handle that binds event start and end.",
                )
            ],
        }
    if event_ref.get("recurrence_present") is not True:
        return {
            "status": "error",
            "authorization_status": response.get("authorization_status"),
            "warnings": [
                _warning(
                    "expected_state_mismatch",
                    "Calendar event did not match expected recurrence state.",
                )
            ],
        }
    if require_supported_recurrence:
        recurrence = event_ref.get("recurrence")
        if not isinstance(recurrence, dict) or recurrence.get("recurrence_present") is not True:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "unsupported_event_state",
                        "Calendar event recurrence is not a supported bounded simple rule.",
                    )
                ],
            }
    result = {
        "status": "ok",
        "authorization_status": response.get("authorization_status"),
        "occurrence_start_date": event_ref["start_date"],
        "occurrence_end_date": event_ref["end_date"],
        "warnings": _safe_warnings(response),
    }
    if require_supported_recurrence:
        result["recurrence"] = event_ref["recurrence"]
    if require_adjacent_occurrence:
        adjacent = _find_adjacent_event_occurrence(response.get("events", []), event_ref)
        if adjacent is None:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "adjacent_occurrence_not_found",
                        "Selected recurring occurrence delete requires a same-series sibling occurrence for preservation proof.",
                    )
                ],
            }
        adjacent_event_url_present = bool(adjacent.get("url_present"))
        adjacent_event_url_sha256 = str(adjacent.get("event_url_safe_sha256") or "")
        if adjacent_event_url_present and not adjacent_event_url_sha256:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "adjacent_occurrence_url_proof_unavailable",
                        "Selected recurring occurrence update requires hash-only sibling URL proof.",
                    )
                ],
            }
        adjacent_identity = {
            "adjacent_occurrence_start_date": adjacent["start_date"],
            "adjacent_occurrence_end_date": adjacent["end_date"],
            "adjacent_occurrence_event_url_present": adjacent_event_url_present,
            "adjacent_occurrence_event_url_safe_sha256": adjacent_event_url_sha256,
        }
        if require_adjacent_location_proof:
            adjacent_location_present = bool(adjacent.get("location_present"))
            adjacent_location_sha256 = str(adjacent.get("location_safe_sha256") or "")
            if adjacent_location_present and not adjacent_location_sha256:
                return {
                    "status": "error",
                    "authorization_status": response.get("authorization_status"),
                    "warnings": [
                        _warning(
                            "adjacent_occurrence_location_proof_unavailable",
                            "Selected recurring occurrence update requires hash-only sibling location proof.",
                        )
                    ],
                }
            adjacent_structured_location_present = bool(
                adjacent.get("structured_location_present")
            )
            adjacent_structured_location_sha256 = str(
                adjacent.get("structured_location_safe_sha256") or ""
            )
            if (
                adjacent_structured_location_present
                and not adjacent_structured_location_sha256
            ):
                return {
                    "status": "error",
                    "authorization_status": response.get("authorization_status"),
                    "warnings": [
                        _warning(
                            "adjacent_occurrence_structured_location_proof_unavailable",
                            "Selected recurring occurrence update requires hash-only sibling structured-location proof.",
                        )
                    ],
                }
            adjacent_identity.update(
                {
                    "adjacent_occurrence_location_present": adjacent_location_present,
                    "adjacent_occurrence_location_safe_sha256": adjacent_location_sha256,
                    "adjacent_occurrence_structured_location_present": (
                        adjacent_structured_location_present
                    ),
                    "adjacent_occurrence_structured_location_safe_sha256": (
                        adjacent_structured_location_sha256
                    ),
                }
            )
        if require_adjacent_alarm_proof:
            adjacent_alarm_present = bool(adjacent.get("alarm_state_present"))
            adjacent_alarm_sha256 = str(adjacent.get("alarm_state_safe_sha256") or "")
            if adjacent_alarm_present and not adjacent_alarm_sha256:
                return {
                    "status": "error",
                    "authorization_status": response.get("authorization_status"),
                    "warnings": [
                        _warning(
                            "adjacent_occurrence_alarm_proof_unavailable",
                            "Selected recurring occurrence update requires hash-only sibling alarm-state proof.",
                        )
                    ],
                }
            adjacent_identity.update(
                {
                    "adjacent_occurrence_alarm_state_present": adjacent_alarm_present,
                    "adjacent_occurrence_alarm_state_safe_sha256": adjacent_alarm_sha256,
                }
            )
        result.update(adjacent_identity)
    if require_previous_occurrence:
        previous = _find_relative_event_occurrence(
            response.get("events", []),
            event_ref,
            direction="previous",
        )
        if previous is None:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "previous_occurrence_not_found",
                        "Future recurring occurrence delete requires a previous same-series occurrence for preservation proof.",
                    )
                ],
            }
        result.update(
            {
                "previous_occurrence_start_date": previous["start_date"],
                "previous_occurrence_end_date": previous["end_date"],
            }
        )
    if require_no_previous_occurrence:
        previous = _find_relative_event_occurrence(
            response.get("events", []),
            event_ref,
            direction="previous",
        )
        if previous is not None:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "previous_occurrence_present",
                        "Whole-series recurring delete requires selecting the first same-series occurrence.",
                    )
                ],
            }
    if require_future_occurrence:
        future = _find_relative_event_occurrence(
            response.get("events", []),
            event_ref,
            direction="future",
        )
        if future is None:
            return {
                "status": "error",
                "authorization_status": response.get("authorization_status"),
                "warnings": [
                    _warning(
                        "future_occurrence_not_found",
                        "Future recurring occurrence delete requires a future same-series occurrence for absence proof.",
                    )
                ],
            }
        result.update(
            {
                "future_occurrence_start_date": future["start_date"],
                "future_occurrence_end_date": future["end_date"],
            }
        )
    return result


def _resolve_calendar_id_for_apply(
    handle: str,
    *,
    eventkit_runner: EventKitRunner,
) -> dict[str, Any]:
    response = _calendar_calendars_response(
        query="",
        limit=10000,
        include_default=True,
        include_all=True,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return {
            "status": "degraded",
            "authorization_status": response.get("authorization_status"),
            "warnings": _safe_warnings(response),
        }
    calendar_id = _resolve_calendar_id(handle, response.get("calendars", []))
    if calendar_id is None:
        return {
            "status": "not_found",
            "authorization_status": response.get("authorization_status"),
            "warnings": [_warning("target_calendar_not_found", "Calendar target was not found.")],
        }
    return {
        "status": "ok",
        "authorization_status": response.get("authorization_status"),
        "calendar_id": calendar_id,
        "warnings": _safe_warnings(response),
    }


def _resolve_calendar_target_for_plan(
    handle: str,
    *,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    response = _calendar_calendars_response(
        query="",
        limit=10000,
        include_default=True,
        include_all=True,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return {
            "status": "degraded",
            "warnings": _safe_warnings(response),
        }
    calendar_id = _resolve_calendar_id(handle, response.get("calendars", []))
    calendar = _find_calendar_by_id(response.get("calendars", []), calendar_id or "")
    if calendar is None:
        return {
            "status": "not_found",
            "warnings": [_warning("target_calendar_not_found", "Calendar target was not found.")],
        }
    if not calendar.get("allows_content_modifications"):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "target_calendar_not_writable",
                    "Calendar target does not allow event changes.",
                )
            ],
        }
    return {
        "status": "ok",
        "calendar": _calendar_metadata(calendar),
        "warnings": _safe_warnings(response),
    }


def _resolve_default_calendar_for_plan(
    *,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    response = search_calendar_calendars(
        "",
        include_default=True,
        limit=50,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return {
            "status": response["status"],
            "warnings": _safe_warnings(response),
        }
    default_calendars = [
        calendar
        for calendar in response.get("results", [])
        if isinstance(calendar, dict) and calendar.get("is_default_calendar")
    ]
    if not default_calendars:
        return {
            "status": "not_found",
            "warnings": [
                _warning(
                    "default_calendar_not_found",
                    "Current default Calendar target was not found.",
                )
            ],
        }
    if len(default_calendars) > 1:
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "ambiguous_default_calendar",
                    "More than one default Calendar target was returned.",
                )
            ],
        }
    default_calendar = default_calendars[0]
    if not default_calendar.get("allows_content_modifications"):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "target_calendar_not_writable",
                    "Current default Calendar target does not allow event changes.",
                )
            ],
        }
    calendar_handle = str(default_calendar.get("handle") or "")
    if not calendar_handle or not is_opaque_handle(calendar_handle, "calendar:calendar"):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "invalid_calendar_handle",
                    "Current default Calendar target did not return a valid opaque handle.",
                )
            ],
        }
    return {
        "status": "ok",
        "target": {
            "calendar_title": str(default_calendar.get("title") or ""),
            "calendar_handle": calendar_handle,
            "allows_content_modifications": True,
        },
        "warnings": _safe_warnings(response),
    }


def _calendar_calendars_response(
    *,
    query: str,
    limit: int,
    include_default: bool,
    include_all: bool,
    eventkit_runner: EventKitRunner | None,
    include_safety_counts: bool = False,
) -> dict[str, Any]:
    runner = eventkit_runner or _run_eventkit_helper
    try:
        return runner(
            {
                "command": "calendar_calendars",
                "query": query,
                "limit": max(1, min(limit, 10000)),
                "include_default": include_default,
                "include_all": include_all,
                "include_safety_counts": include_safety_counts,
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Calendar target selection timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Calendar target selection is unavailable through the local EventKit helper.",
                )
            ],
        }


def _calendar_events_response(
    *,
    query: str,
    limit: int,
    days_back: int,
    days_forward: int,
    max_scan_events: int,
    eventkit_runner: EventKitRunner | None,
    include_url_proof: bool = False,
    include_location_proof: bool = False,
    include_structured_location_proof: bool = False,
    include_alarm_proof: bool = False,
) -> dict[str, Any]:
    runner = eventkit_runner or _run_eventkit_helper
    try:
        return runner(
            {
                "command": "calendar_events",
                "query": query,
                "limit": max(1, min(limit, _bounded_max_scan(max_scan_events))),
                "days_back": _bounded_days(days_back),
                "days_forward": _bounded_days(days_forward),
                "max_events": _bounded_max_scan(max_scan_events),
                "include_url_proof": include_url_proof,
                "include_location_proof": include_location_proof,
                "include_structured_location_proof": include_structured_location_proof,
                "include_alarm_proof": include_alarm_proof,
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Calendar access timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Calendar access is unavailable through the local EventKit helper.",
                )
            ],
        }


def _calendar_events_for_calendar_response(
    *,
    calendar_id: str,
    start_date: str,
    end_date: str,
    limit: int,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    runner = eventkit_runner or _run_eventkit_helper
    try:
        return runner(
            {
                "command": "calendar_events_for_calendar",
                "calendar_id": calendar_id,
                "start_date": start_date,
                "end_date": end_date,
                "limit": max(1, min(limit, 50)),
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Calendar selected-calendar event listing timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Calendar selected-calendar event listing is unavailable through the local EventKit helper.",
                )
            ],
        }


def _eventkit_helper_app_root() -> Path:
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "local-apple-data"
        / "EventKitHelper.app"
    )


def _eventkit_helper_source_digest() -> str:
    return hashlib.sha256(DEFAULT_EVENTKIT_HELPER.read_bytes()).hexdigest()


def _eventkit_helper_info_plist() -> dict[str, Any]:
    return {
        "CFBundleExecutable": "eventkit_helper",
        "CFBundleIdentifier": _eventkit_helper_bundle_id(),
        "CFBundleName": "Local Apple Data EventKit Helper",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "14.0",
        "NSCalendarsFullAccessUsageDescription": (
            "Allow local-apple-data to read and write local Calendar data only when explicitly requested."
        ),
        "NSCalendarsWriteOnlyAccessUsageDescription": (
            "Allow local-apple-data to create local Calendar events only when explicitly approved."
        ),
        "NSRemindersFullAccessUsageDescription": (
            "Allow local-apple-data to read and write local Reminders only when explicitly requested."
        ),
    }


def _eventkit_helper_entitlements() -> dict[str, bool]:
    # Personal-information entitlements are required for the EventKit TCC prompt
    # to be presented on macOS 14+; without them requestFullAccessToEvents /
    # requestFullAccessToReminders returns not_determined without ever showing
    # UI. Mirrors the Photos helper, which carries the photos-library entitlement.
    return {
        "com.apple.security.personal-information.calendars": True,
        "com.apple.security.personal-information.reminders": True,
    }


# Signing identity resolution / codesign command building / provisioning are
# shared with the Photos helper via adapters._signing. The public names below
# are thin re-exports kept for backward compatibility with existing references.
EVENTKIT_SIGNING_IDENTITY_ENV = _signing.SIGNING_IDENTITY_ENV
DEFAULT_LOCAL_SIGNING_IDENTITY = _signing.DEFAULT_LOCAL_SIGNING_IDENTITY


def _eventkit_signing_identity() -> str | None:
    """Return a stable code-signing identity name if one is available.

    EventKit only presents its TCC prompt to a process signed with a *stable*
    identity: an ad-hoc signature (``codesign -s -``) has no stable designated
    requirement, so tccd cannot attribute the request and the prompt never
    appears. Delegates to the shared resolver (env override, then a
    conventionally-named local self-signed identity, else ``None``).
    """
    return _signing.signing_identity()


def _eventkit_codesign_command(
    codesign: str, entitlements_file: Path, staged_app: Path
) -> list[str]:
    # Stable identity + hardened runtime + entitlements so EventKit's TCC prompt
    # presents; ad-hoc fallback otherwise (see adapters._signing). Actual signing
    # goes through _signing.sign_helper_app, which retries ad-hoc when a resolved
    # stable identity turns out to be unusable; this builds the command for the
    # resolved identity for inspection/back-compat.
    return _signing.codesign_command(
        codesign, entitlements_file, staged_app, _signing.signing_identity()
    )


def _provision_local_signing_identity() -> str | None:
    """Provision the conventional local self-signed identity if none exists.

    Idempotent and non-raising: returns the already-available identity when one
    is resolvable, otherwise creates it in the login keychain when ``openssl``
    and ``security`` are available, else ``None``. See adapters._signing.
    """
    return _signing.provision_local_signing_identity()


def _prepare_eventkit_helper_signing() -> None:
    """Provision a stable identity and invalidate a stale-signed helper app.

    Invoked only from the request-access paths (never from read/mutation paths,
    which must not provision or block on prompts). Provisions the conventional
    identity when absent, then removes the on-disk helper if its signature no
    longer matches the resolved identity so ``_ensure_eventkit_helper_app``
    rebuilds it stably signed before the prompt is shown. Non-raising.
    """
    try:
        identity = _provision_local_signing_identity()
        _signing.invalidate_app_if_signing_mismatch(
            _eventkit_helper_app_root(), identity
        )
    except (OSError, ValueError):
        return


def _ensure_eventkit_helper_app() -> Path:
    app_root = _eventkit_helper_app_root()
    digest = _eventkit_helper_source_digest()
    if _eventkit_helper_app_valid(app_root, digest):
        return app_root

    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise ValueError("EventKit helper compiler unavailable.")
    codesign = shutil.which("codesign")
    if not codesign:
        raise ValueError("EventKit helper signer unavailable.")

    parent = app_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    os.chmod(parent, 0o700)
    staging_root = Path(tempfile.mkdtemp(prefix=".EventKitHelper.", dir=parent))
    staged_app = staging_root / "EventKitHelper.app"
    contents = staged_app / "Contents"
    executable = contents / "MacOS" / "eventkit_helper"
    digest_file = contents / "Resources" / "source.sha256"
    entitlements_file = contents / "Resources" / "entitlements.plist"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(parents=True, exist_ok=True)
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(_eventkit_helper_info_plist(), handle)
    with entitlements_file.open("wb") as handle:
        plistlib.dump(_eventkit_helper_entitlements(), handle)
    digest_file.write_text(digest)
    completed = subprocess.run(
        [swiftc, str(DEFAULT_EVENTKIT_HELPER), "-o", str(executable)],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise ValueError("EventKit helper app build failed.")

    # Sign with the resolved stable identity, falling back to ad-hoc if that
    # identity is present but unusable (locked keychain, missing/duplicate key,
    # unrelated leftover cert). An ad-hoc helper still builds and runs for
    # non-prompting reads; only the TCC prompt requires a usable stable identity.
    sign = _signing.sign_helper_app(codesign, entitlements_file, staged_app)
    if sign.returncode != 0 or not _eventkit_helper_app_valid(staged_app, digest):
        shutil.rmtree(staging_root, ignore_errors=True)
        raise ValueError("EventKit helper app signing failed.")

    if app_root.is_symlink():
        app_root.unlink()
    elif app_root.exists():
        shutil.rmtree(app_root)
    staged_app.rename(app_root)
    shutil.rmtree(staging_root, ignore_errors=True)
    return app_root


def _eventkit_helper_app_valid(app_root: Path, digest: str) -> bool:
    contents = app_root / "Contents"
    executable = contents / "MacOS" / "eventkit_helper"
    digest_file = contents / "Resources" / "source.sha256"
    info_plist = contents / "Info.plist"
    entitlements_file = contents / "Resources" / "entitlements.plist"
    if not executable.is_file() or not digest_file.is_file() or not info_plist.is_file():
        return False
    if not entitlements_file.is_file():
        return False
    try:
        if digest_file.read_text().strip() != digest:
            return False
        with info_plist.open("rb") as handle:
            if plistlib.load(handle) != _eventkit_helper_info_plist():
                return False
        with entitlements_file.open("rb") as handle:
            if plistlib.load(handle) != _eventkit_helper_entitlements():
                return False
    except (OSError, plistlib.InvalidFileException):
        return False

    codesign = shutil.which("codesign")
    if not codesign:
        return False
    verified = subprocess.run(
        [codesign, "--verify", "--deep", "--strict", str(app_root)],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    return verified.returncode == 0


def _run_eventkit_helper(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    app_root = _ensure_eventkit_helper_app()
    opener = shutil.which("open") or "/usr/bin/open"
    with tempfile.TemporaryDirectory(prefix="local-apple-data-eventkit-") as directory:
        os.chmod(directory, 0o700)
        input_path = Path(directory) / "input.json"
        output_path = Path(directory) / "output.json"
        input_fd = os.open(input_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(input_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
        output_fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(output_fd)
        completed = subprocess.run(
            [
                opener,
                "-W",
                "-n",
                str(app_root),
                "--args",
                "--input-json-file",
                str(input_path),
                "--output-json-file",
                str(output_path),
            ],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if not output_path.exists():
            raise ValueError("EventKit helper app failed.")
        output_text = output_path.read_text()
        if not output_text:
            raise ValueError("EventKit helper app returned no output.")
        parsed = json.loads(output_text)
    if not isinstance(parsed, dict):
        raise ValueError("EventKit helper returned invalid JSON.")
    return parsed


def _run_eventkit_helper_script(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        ["swift", str(DEFAULT_EVENTKIT_HELPER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("EventKit helper failed.")
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("EventKit helper returned invalid JSON.")
    return parsed


def _event_metadata(
    event: dict[str, Any],
    *,
    include_alarm_offsets: bool = False,
    include_time_zone: bool = False,
) -> dict[str, Any]:
    event_id = str(event.get("event_id") or "")
    start_date = str(event.get("start_date") or "")
    end_date = str(event.get("end_date") or "")
    payload = {
        "handle": _event_handle(event_id, start_date, end_date),
        "title": event.get("title"),
        "calendar_title": event.get("calendar_title"),
        "start_date": start_date,
        "end_date": end_date,
        "all_day": bool(event.get("all_day")),
        "availability": event.get("availability"),
        "availability_name": _availability_name(event.get("availability")),
        "location_present": bool(event.get("location_present")),
        "notes_present": bool(event.get("notes_present")),
        "url_present": bool(event.get("url_present")),
        "alarms_count": event.get("alarms_count"),
        "attendees_count": event.get("attendees_count"),
        "recurrence_present": bool(event.get("recurrence_present")),
    }
    if include_time_zone:
        payload["time_zone"] = event.get("time_zone") or ""
    if include_alarm_offsets and "alarm_offsets_minutes" in event:
        payload["alarm_offsets_minutes"] = event.get("alarm_offsets_minutes")
    if include_alarm_offsets and "alarm_absolute_dates" in event:
        payload["alarm_absolute_dates"] = event.get("alarm_absolute_dates")
    if include_alarm_offsets and "alarm_sound_name" in event:
        payload["alarm_sound_name"] = event.get("alarm_sound_name") or ""
        payload["alarm_action"] = _alarm_action(
            payload["alarm_sound_name"],
            str(event.get("alarm_proximity") or ""),
            str(event.get("alarm_email_address_sha256") or ""),
        )
    if include_alarm_offsets and "alarm_email_address_sha256" in event:
        payload["alarm_email_address_sha256"] = event.get("alarm_email_address_sha256") or ""
    if include_alarm_offsets and "alarm_proximity" in event:
        payload["alarm_proximity"] = event.get("alarm_proximity") or ""
    if include_alarm_offsets and isinstance(event.get("alarm_structured_location"), dict):
        payload["alarm_structured_location"] = event["alarm_structured_location"]
    if "recurrence" in event:
        payload["recurrence"] = event.get("recurrence") or _empty_recurrence()
    if event.get("event_url_safe_sha256"):
        payload["event_url_safe_sha256"] = event.get("event_url_safe_sha256")
    if isinstance(event.get("structured_location"), dict):
        payload["structured_location"] = event["structured_location"]
        payload["structured_location_present"] = True
    elif event.get("structured_location_present") is False:
        payload["structured_location_present"] = False
    return payload


def _selected_calendar_event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event.get("event_id") or "")
    start_date = str(event.get("start_date") or "")
    end_date = str(event.get("end_date") or "")
    payload = {
        "handle": _event_handle(event_id, start_date, end_date),
        "title": event.get("title"),
        "calendar_title": event.get("calendar_title"),
        "start_date": start_date,
        "end_date": end_date,
        "all_day": bool(event.get("all_day")),
        "availability": event.get("availability"),
        "availability_name": _availability_name(event.get("availability")),
        "location_present": bool(event.get("location_present")),
        "notes_present": bool(event.get("notes_present")),
        "url_present": bool(event.get("url_present")),
        "alarms_count": event.get("alarms_count"),
        "attendees_count": event.get("attendees_count"),
        "recurrence_present": bool(event.get("recurrence_present")),
    }
    if "recurrence" in event:
        payload["recurrence"] = event.get("recurrence") or _empty_recurrence()
    return payload


def _calendar_participants(event: dict[str, Any]) -> list[dict[str, Any]]:
    participants = event.get("participants")
    if not isinstance(participants, list):
        return []
    return [participant for participant in participants if isinstance(participant, dict)]


def _calendar_participant_metadata(
    event: dict[str, Any],
    participant: dict[str, Any],
    *,
    include_detail: bool,
) -> dict[str, Any]:
    name = str(participant.get("name") or "")
    url = str(participant.get("url") or "")
    payload: dict[str, Any] = {
        "handle": _calendar_participant_handle(event, participant),
        "event_handle": _event_handle(
            str(event.get("event_id") or ""),
            str(event.get("start_date") or ""),
            str(event.get("end_date") or ""),
        ),
        "participant_index": int(participant.get("index") or 0),
        "participant_kind": str(participant.get("participant_kind") or ""),
        "organizer": bool(participant.get("organizer")),
        "current_user": bool(participant.get("current_user")),
        "participant_status": participant.get("participant_status"),
        "participant_status_name": participant.get("participant_status_name"),
        "participant_role": participant.get("participant_role"),
        "participant_role_name": participant.get("participant_role_name"),
        "participant_type": participant.get("participant_type"),
        "participant_type_name": participant.get("participant_type_name"),
        "name_present": bool(name),
        "url_present": bool(url),
        "name_returned": False,
        "url_returned": False,
    }
    if include_detail:
        name_text, name_truncated = _bounded_text(name, MAX_PARTICIPANT_NAME_CHARS)
        url_text, url_truncated = _bounded_text(url, MAX_PARTICIPANT_URL_CHARS)
        payload.update(
            {
                "name": name_text,
                "name_truncated": name_truncated,
                "url": url_text,
                "url_truncated": url_truncated,
                "name_returned": True,
                "url_returned": True,
            }
        )
    return payload


def _calendar_metadata(calendar: dict[str, Any]) -> dict[str, Any]:
    calendar_id = str(calendar.get("calendar_id") or "")
    return {
        "handle": make_opaque_handle("calendar:calendar", calendar_id),
        "title": calendar.get("title"),
        "is_default_calendar": bool(calendar.get("is_default_calendar")),
        "allows_content_modifications": bool(calendar.get("allows_content_modifications")),
        "is_subscribed": bool(calendar.get("is_subscribed")),
        "is_immutable": bool(calendar.get("is_immutable")),
        "calendar_type": calendar.get("calendar_type"),
        "source_type": calendar.get("source_type"),
        "supported_event_availabilities": calendar.get("supported_event_availabilities", []),
    }


def _calendar_detail(calendar: dict[str, Any]) -> dict[str, Any]:
    result = _calendar_metadata(calendar)
    result["calendar_safe_sha256"] = _calendar_safe_sha256(calendar)
    result["source_safe_sha256"] = _calendar_source_safe_sha256(calendar)
    if "event_count_in_safety_window" in calendar:
        result["event_count_in_safety_window"] = int(
            calendar.get("event_count_in_safety_window") or 0
        )
        result["safety_window_start"] = str(calendar.get("safety_window_start") or "")
        result["safety_window_end"] = str(calendar.get("safety_window_end") or "")
    return result


def _calendar_safe_sha256(calendar: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "calendar_id": str(calendar.get("calendar_id") or ""),
                "title": str(calendar.get("title") or ""),
                "source_id": str(calendar.get("source_id") or ""),
                "source_type": str(calendar.get("source_type") or ""),
                "is_default_calendar": bool(calendar.get("is_default_calendar")),
                "allows_content_modifications": bool(calendar.get("allows_content_modifications")),
                "is_subscribed": bool(calendar.get("is_subscribed")),
                "is_immutable": bool(calendar.get("is_immutable")),
                "calendar_type": str(calendar.get("calendar_type") or ""),
                "allowed_entity_types": _calendar_allowed_entity_types(calendar),
                "event_count_in_safety_window": int(
                    calendar.get("event_count_in_safety_window") or 0
                ),
            }
        ).encode("utf-8")
    ).hexdigest()


def _calendar_source_safe_sha256(calendar: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "source_id": str(calendar.get("source_id") or ""),
                "source_type": str(calendar.get("source_type") or ""),
            }
        ).encode("utf-8")
    ).hexdigest()


def _event_handle(event_id: str, start_date: str, end_date: str) -> str:
    return make_opaque_handle(
        "calendar:event",
        event_id,
        _canonical_event_handle_date(start_date),
        _canonical_event_handle_date(end_date),
    )


def _calendar_participant_handle(event: dict[str, Any], participant: dict[str, Any]) -> str:
    return make_opaque_handle(
        CALENDAR_PARTICIPANT_HANDLE_PREFIX,
        str(event.get("event_id") or ""),
        _canonical_event_handle_date(str(event.get("start_date") or "")),
        _canonical_event_handle_date(str(event.get("end_date") or "")),
        int(participant.get("index") or 0),
        str(participant.get("participant_kind") or ""),
        str(participant.get("url") or ""),
        str(participant.get("name") or ""),
        str(participant.get("participant_status") or ""),
        str(participant.get("participant_role") or ""),
        str(participant.get("participant_type") or ""),
        bool(participant.get("current_user")),
        bool(participant.get("organizer")),
    )


def _calendar_participant_handle_matches(
    handle: str,
    event: dict[str, Any],
    participant: dict[str, Any],
) -> bool:
    return opaque_handle_matches(
        handle,
        CALENDAR_PARTICIPANT_HANDLE_PREFIX,
        str(event.get("event_id") or ""),
        _canonical_event_handle_date(str(event.get("start_date") or "")),
        _canonical_event_handle_date(str(event.get("end_date") or "")),
        int(participant.get("index") or 0),
        str(participant.get("participant_kind") or ""),
        str(participant.get("url") or ""),
        str(participant.get("name") or ""),
        str(participant.get("participant_status") or ""),
        str(participant.get("participant_role") or ""),
        str(participant.get("participant_type") or ""),
        bool(participant.get("current_user")),
        bool(participant.get("organizer")),
    )


def _canonical_event_handle_date(value: str) -> str:
    normalized = value.strip()
    if not normalized or _is_date_only_input(normalized):
        return normalized
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return normalized
    if parsed.tzinfo is None:
        return normalized
    return parsed.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _event_recurrence_present(event: dict[str, Any]) -> bool:
    recurrence = event.get("recurrence")
    return bool(
        event.get("recurrence_present")
        or (
            isinstance(recurrence, dict)
            and recurrence.get("recurrence_present") is True
        )
    )


def _resolve_event_reference(handle: str, events: Any) -> dict[str, Any] | None:
    if not isinstance(events, list):
        return None
    fallback_event_id = ""
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or "")
        if not event_id:
            continue
        start_date = str(event.get("start_date") or "")
        end_date = str(event.get("end_date") or "")
        if opaque_handle_matches(
            handle,
            "calendar:event",
            event_id,
            _canonical_event_handle_date(start_date),
            _canonical_event_handle_date(end_date),
        ):
            event_ref = {
                "event_id": event_id,
                "start_date": start_date,
                "end_date": end_date,
                "recurrence_present": _event_recurrence_present(event),
            }
            if isinstance(event.get("recurrence"), dict):
                event_ref["recurrence"] = event["recurrence"]
            return event_ref
        if not fallback_event_id and opaque_handle_matches(handle, "calendar:event", event_id):
            fallback_event_id = event_id
    if fallback_event_id:
        return {"event_id": fallback_event_id, "start_date": "", "end_date": ""}
    return None


def _calendar_event_for_participants(
    handle: str,
    *,
    days_back: int,
    days_forward: int,
    max_scan_events: int,
    detail: bool,
    eventkit_runner: EventKitRunner | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, str]], Any]:
    if not is_opaque_handle(handle, "calendar:event"):
        return (
            None,
            _calendar_participant_error(
                [_warning("invalid_handle", "Expected calendar:event:v1 opaque handle from search output.")],
                detail=detail,
            ),
            [],
            None,
        )

    response = _calendar_events_response(
        query="",
        limit=_bounded_max_scan(max_scan_events),
        days_back=days_back,
        days_forward=days_forward,
        max_scan_events=max_scan_events,
        eventkit_runner=eventkit_runner,
    )
    authorization_status = response.get("authorization_status")
    if response["status"] != "ok":
        return (
            None,
            _calendar_participant_error(
                _safe_warnings(response),
                detail=detail,
                status="degraded",
                authorization_status=authorization_status,
            ),
            [],
            authorization_status,
        )

    event_ref = _resolve_event_reference(handle, response.get("events", []))
    if event_ref is None:
        return (
            None,
            _calendar_participant_error(
                _safe_warnings(response),
                detail=detail,
                status="not_found",
                authorization_status=authorization_status,
            ),
            [],
            authorization_status,
        )

    runner = eventkit_runner or _run_eventkit_helper
    detail_payload = {
        "command": "calendar_event_participants_by_id",
        "event_id": event_ref["event_id"],
    }
    if event_ref.get("start_date") and event_ref.get("end_date"):
        detail_payload = {
            "command": "calendar_event_participants_by_occurrence",
            "event_id": event_ref["event_id"],
            "start_date": event_ref["start_date"],
            "end_date": event_ref["end_date"],
        }
    try:
        detail_response = runner(detail_payload, EVENTKIT_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return (
            None,
            _calendar_participant_error(
                [_warning("eventkit_read_error", "Calendar event participants could not be read safely.")],
                detail=detail,
                status="content_unavailable",
                authorization_status=authorization_status,
            ),
            [],
            authorization_status,
        )

    warnings = _safe_warnings(response) + _safe_warnings(detail_response)
    if detail_response.get("status") == "not_found":
        return (
            None,
            _calendar_participant_error(
                warnings,
                detail=detail,
                status="not_found",
                authorization_status=authorization_status,
            ),
            [],
            authorization_status,
        )
    if detail_response.get("status") != "ok":
        return (
            None,
            _calendar_participant_error(
                warnings,
                detail=detail,
                status="degraded",
                authorization_status=authorization_status,
            ),
            [],
            authorization_status,
        )

    event = detail_response.get("event")
    if not isinstance(event, dict):
        return (
            None,
            _calendar_participant_error(
                [_warning("eventkit_read_error", "Calendar event participants could not be read safely.")],
                detail=detail,
                status="content_unavailable",
                authorization_status=authorization_status,
            ),
            [],
            authorization_status,
        )
    return event, None, warnings, authorization_status


def _find_calendar_participant(
    event: dict[str, Any],
    participant_handle: str,
) -> dict[str, Any] | None:
    for participant in _calendar_participants(event):
        if _calendar_participant_handle_matches(participant_handle, event, participant):
            return participant
    return None


def _find_adjacent_event_occurrence(
    events: Any,
    selected: dict[str, str],
) -> dict[str, Any] | None:
    if not isinstance(events, list):
        return None
    event_id = selected.get("event_id", "")
    selected_start = selected.get("start_date", "")
    selected_end = selected.get("end_date", "")
    candidates: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        candidate_id = str(event.get("event_id") or "")
        start_date = str(event.get("start_date") or "")
        end_date = str(event.get("end_date") or "")
        if candidate_id != event_id or not start_date or not end_date:
            continue
        if start_date == selected_start and end_date == selected_end:
            continue
        candidates.append(
            {
                "event_id": candidate_id,
                "start_date": start_date,
                "end_date": end_date,
                "url_present": bool(event.get("url_present")),
                "event_url_safe_sha256": str(event.get("event_url_safe_sha256") or ""),
                "location_present": bool(event.get("location_present")),
                "location_safe_sha256": str(event.get("location_safe_sha256") or ""),
                "structured_location_present": bool(event.get("structured_location_present")),
                "structured_location_safe_sha256": str(
                    event.get("structured_location_safe_sha256") or ""
                ),
                "alarm_state_present": bool(event.get("alarm_state_present")),
                "alarm_state_safe_sha256": str(event.get("alarm_state_safe_sha256") or ""),
            }
        )
    if not candidates:
        return None
    selected_key = selected_start or ""
    return sorted(
        candidates,
        key=lambda candidate: (
            abs(_event_sort_distance(candidate["start_date"], selected_key)),
            candidate["start_date"],
            candidate["end_date"],
        ),
    )[0]


def _find_relative_event_occurrence(
    events: Any,
    selected: dict[str, str],
    *,
    direction: str,
) -> dict[str, str] | None:
    if not isinstance(events, list):
        return None
    event_id = selected.get("event_id", "")
    selected_start = selected.get("start_date", "")
    selected_end = selected.get("end_date", "")
    candidates: list[tuple[int, dict[str, str]]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        candidate_id = str(event.get("event_id") or "")
        start_date = str(event.get("start_date") or "")
        end_date = str(event.get("end_date") or "")
        if candidate_id != event_id or not start_date or not end_date:
            continue
        if start_date == selected_start and end_date == selected_end:
            continue
        distance = _event_sort_distance(start_date, selected_start)
        if direction == "previous" and distance < 0:
            candidates.append(
                (
                    distance,
                    {
                        "event_id": candidate_id,
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                )
            )
        if direction == "future" and distance > 0:
            candidates.append(
                (
                    distance,
                    {
                        "event_id": candidate_id,
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                )
            )
    if not candidates:
        return None
    if direction == "previous":
        return sorted(candidates, key=lambda item: (abs(item[0]), item[1]["start_date"]))[0][1]
    return sorted(candidates, key=lambda item: (item[0], item[1]["start_date"]))[0][1]


def _event_sort_distance(candidate_start: str, selected_start: str) -> int:
    try:
        candidate_dt = datetime.fromisoformat(candidate_start.replace("Z", "+00:00"))
        selected_dt = datetime.fromisoformat(selected_start.replace("Z", "+00:00"))
    except ValueError:
        return 0 if candidate_start == selected_start else 1
    return int((candidate_dt - selected_dt).total_seconds())


def _resolve_calendar_id(handle: str, calendars: Any) -> str | None:
    if not isinstance(calendars, list):
        return None
    for calendar in calendars:
        if not isinstance(calendar, dict):
            continue
        calendar_id = str(calendar.get("calendar_id") or "")
        if calendar_id and opaque_handle_matches(handle, "calendar:calendar", calendar_id):
            return calendar_id
    return None


def _find_calendar_by_id(calendars: Any, calendar_id: str) -> dict[str, Any] | None:
    if not isinstance(calendars, list):
        return None
    for calendar in calendars:
        if isinstance(calendar, dict) and str(calendar.get("calendar_id") or "") == calendar_id:
            return calendar
    return None


def _invalid_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected calendar:event:v1 opaque handle from search output.",
            )
        ],
    }


def _invalid_calendar_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected calendar:calendar:v1 opaque handle from calendar selection output.",
            )
        ],
    }


def _calendar_event_list_error(
    warnings: list[dict[str, str]],
    *,
    limit: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _privacy(),
        "query": {
            "scope": "selected_calendar_events",
            "limit": limit,
        },
        "calendar": None,
        "results": [],
        "result_count": 0,
        "warnings": warnings,
    }


def _calendar_participant_error(
    warnings: list[dict[str, str]],
    *,
    detail: bool,
    status: str = "error",
    authorization_status: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "source": "calendar",
        "privacy": _participant_privacy(detail_returned=False),
        "warnings": warnings,
    }
    if authorization_status is not None:
        payload["authorization_status"] = authorization_status
    if detail:
        payload["result"] = None
    else:
        payload["results"] = []
        payload["result_count"] = 0
    return payload


def _preview_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": None,
        "result_count": 0,
        "warnings": warnings,
    }


def _apply_error(
    warnings: list[dict[str, str]],
    *,
    plan: dict[str, Any] | None,
    status: str = "error",
    mutation_applied: bool = False,
    authorization_status: Any = None,
) -> dict[str, Any]:
    preview = plan.get("preview") if isinstance(plan, dict) else None
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "source": "calendar",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "preview": preview if isinstance(preview, dict) else None,
        "read_back": None,
        "result_count": 0,
        "warnings": warnings,
    }
    if authorization_status is not None:
        payload["authorization_status"] = authorization_status
    return payload


def _helper_degraded_result(response: dict[str, Any], *, content: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "calendar",
        "privacy": _content_privacy(content_inspected=False) if content else _privacy(),
        "authorization_status": response.get("authorization_status"),
        "results": [] if not content else None,
        "result": None if content else None,
        "result_count": 0 if not content else None,
        "warnings": _safe_warnings(response),
    }


def _content_unavailable_result(
    result: dict[str, Any] | None,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "content_unavailable",
        "source": "calendar",
        "privacy": _content_privacy(content_inspected=False),
        "result": result,
        "warnings": [_warning(code, message)],
    }


def _safe_warnings(response: dict[str, Any]) -> list[dict[str, str]]:
    return safe_warning_payloads(
        response,
        _warning,
        fallback_message="Calendar warning detail was redacted.",
    )


def _bounded_days(days: int) -> int:
    return max(0, min(days, 3650))


def _bounded_max_scan(max_scan_events: int) -> int:
    return max(1, min(max_scan_events, 10000))


def _bounded_text(text: str, max_chars: int) -> tuple[str, bool]:
    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) <= bounded_chars:
        return normalized, False
    return normalized[:bounded_chars], True


def _bounded_preview_value(
    value: str,
    *,
    field: str,
    max_chars: int,
    required: bool,
) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip().replace("\r\n", "\n").replace("\r", "\n")
    if required and not normalized:
        return "", _warning("missing_required_field", f"Missing required field: {field}.")
    if len(normalized) > max_chars:
        return "", _warning("input_too_large", f"Field exceeds maximum length: {field}.")
    return normalized, None


def _normalize_event_datetime(
    value: Any,
    *,
    field: str,
    allow_date_only: bool = False,
) -> tuple[str | None, dict[str, str] | None]:
    if value is None:
        return None, _warning("missing_required_field", f"Missing required field: {field}.")
    if not isinstance(value, str):
        return None, _warning(
            "invalid_datetime",
            (
                f"{field} must be a valid YYYY-MM-DD date or ISO 8601 timestamp with a timezone."
                if allow_date_only
                else f"{field} must be an ISO 8601 timestamp with a timezone."
            ),
        )
    stripped = value.strip()
    if not stripped:
        return None, _warning("missing_required_field", f"Missing required field: {field}.")
    if allow_date_only and _is_date_only_input(stripped):
        try:
            datetime.strptime(stripped, "%Y-%m-%d")
        except ValueError:
            return None, _warning(
                "invalid_datetime",
                f"{field} must be a valid YYYY-MM-DD date or ISO 8601 timestamp with a timezone.",
            )
        return stripped, None
    try:
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return None, _warning(
            "invalid_datetime",
            (
                f"{field} must be a valid YYYY-MM-DD date or ISO 8601 timestamp with a timezone."
                if allow_date_only
                else f"{field} must be an ISO 8601 timestamp with a timezone."
            ),
        )
    if parsed.tzinfo is None:
        return None, _warning(
            "invalid_datetime",
            f"{field} must include a timezone.",
        )
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"), None


def _event_window_datetime(value: str) -> datetime:
    if _is_date_only_input(value):
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _apply_helper_payload(
    preview: dict[str, Any],
    *,
    event_url: str = "",
    alarm_email_address: str = "",
) -> dict[str, Any]:
    proposed = preview["proposed"]
    payload = {
        "command": "calendar_apply_change",
        "operation": preview["operation"],
    }
    target = preview["target"]
    if preview["operation"] == "create":
        payload.update(
            {
                "title": proposed["title"],
                "start_date": proposed["start_date"],
                "end_date": proposed["end_date"],
                "time_zone": proposed["time_zone"],
                "all_day": proposed["all_day"],
                "location": proposed["location"],
                "structured_location": proposed["structured_location"],
                "notes": proposed["notes_text"],
                "calendar_title": target["calendar_title"],
                "calendar_id": preview.get("resolved_calendar_id", ""),
                "event_url": event_url if proposed["event_url_requested"] else "",
                "event_url_requested": proposed["event_url_requested"],
                "event_url_clear_requested": False,
            }
        )
        if proposed.get("availability_requested"):
            payload["availability"] = proposed["availability"]
        payload.update(
            {
                "alarm_offsets_minutes": proposed["alarm_offsets_minutes"],
                "alarm_absolute_dates": proposed["alarm_absolute_dates"],
                "alarm_sound_name": proposed["alarm_sound_name"],
                "alarm_email_address": (
                    alarm_email_address if proposed["alarm_email_address_sha256"] else ""
                ),
                "alarm_proximity": proposed["alarm_proximity"],
                "alarm_structured_location": proposed["alarm_structured_location"],
                "recurrence": proposed["recurrence"],
            }
        )
    else:
        expected = target["expected_state"]
        payload.update(
            {
                "event_id": preview["resolved_event_id"],
                "occurrence_start_date": preview.get("resolved_occurrence_start_date", ""),
                "occurrence_end_date": preview.get("resolved_occurrence_end_date", ""),
                "adjacent_occurrence_start_date": preview.get(
                    "resolved_adjacent_occurrence_start_date",
                    "",
                ),
                "adjacent_occurrence_end_date": preview.get(
                    "resolved_adjacent_occurrence_end_date",
                    "",
                ),
                "adjacent_occurrence_event_url_present": proposed.get(
                    "adjacent_occurrence_event_url_present",
                    False,
                ),
                "adjacent_occurrence_event_url_sha256": proposed.get(
                    "adjacent_occurrence_event_url_safe_sha256",
                    "",
                ),
                "adjacent_occurrence_location_present": proposed.get(
                    "adjacent_occurrence_location_present",
                    False,
                ),
                "adjacent_occurrence_location_sha256": proposed.get(
                    "adjacent_occurrence_location_safe_sha256",
                    "",
                ),
                "adjacent_occurrence_structured_location_present": proposed.get(
                    "adjacent_occurrence_structured_location_present",
                    False,
                ),
                "adjacent_occurrence_structured_location_sha256": proposed.get(
                    "adjacent_occurrence_structured_location_safe_sha256",
                    "",
                ),
                "adjacent_occurrence_alarm_state_present": proposed.get(
                    "adjacent_occurrence_alarm_state_present",
                    False,
                ),
                "adjacent_occurrence_alarm_state_sha256": proposed.get(
                    "adjacent_occurrence_alarm_state_safe_sha256",
                    "",
                ),
                "previous_occurrence_start_date": preview.get(
                    "resolved_previous_occurrence_start_date",
                    "",
                ),
                "previous_occurrence_end_date": preview.get(
                    "resolved_previous_occurrence_end_date",
                    "",
                ),
                "future_occurrence_start_date": preview.get(
                    "resolved_future_occurrence_start_date",
                    "",
                ),
                "future_occurrence_end_date": preview.get(
                    "resolved_future_occurrence_end_date",
                    "",
                ),
                "expected_title": expected["title"],
                "expected_calendar_title": expected["calendar_title"],
                "expected_start_date": expected["start_date"],
                "expected_end_date": expected["end_date"],
                "expected_time_zone": expected["time_zone"],
                "expected_all_day": expected["all_day"],
                "expected_event_url_present": expected["event_url_present"],
                "expected_event_url_sha256": expected["event_url_safe_sha256"],
                "expected_location": expected["location"],
                "expected_structured_location": expected["structured_location"],
                "expected_notes": expected["notes_text"],
            }
        )
        if expected.get("structured_location_present_bound"):
            payload["expected_structured_location_present"] = expected[
                "structured_location_present"
            ]
        if expected.get("availability_expected"):
            payload["expected_availability"] = expected["availability"]
        if preview.get("operation") == "update" and proposed.get("availability_requested"):
            payload["availability"] = proposed["availability"]
        if preview.get("operation") == "update" and expected.get("recurrence_expected"):
            payload["expected_recurrence_present"] = expected["recurrence_present"]
            payload["expected_recurrence"] = expected.get("recurrence", _empty_recurrence())
        if preview.get("operation") == "update" and (
            proposed.get("recurrence_present") or proposed.get("recurrence_clear_requested")
        ):
            payload["recurrence"] = proposed["recurrence"]
        if preview.get("operation") == "update" and proposed.get("recurrence_clear_requested"):
            payload["clear_recurrence"] = True
        if preview.get("operation") == "update" and proposed.get("recurrence_update_scope"):
            payload["recurrence_update_scope"] = proposed.get("recurrence_update_scope", "")
            payload["selected_occurrence_alarm_update_requested"] = proposed.get(
                "selected_occurrence_alarm_update_requested",
                False,
            )
            payload["future_series_scalar_update_requested"] = proposed.get(
                "future_series_scalar_update_requested",
                False,
            )
            payload["future_series_reschedule_requested"] = proposed.get(
                "future_series_reschedule_requested",
                False,
            )
            payload["future_series_availability_update_requested"] = proposed.get(
                "future_series_availability_update_requested",
                False,
            )
            payload["future_series_event_url_update_requested"] = proposed.get(
                "future_series_event_url_update_requested",
                False,
            )
            payload["future_series_structured_location_update_requested"] = proposed.get(
                "future_series_structured_location_update_requested",
                False,
            )
            payload["future_series_display_alarm_update_requested"] = proposed.get(
                "future_series_display_alarm_update_requested",
                False,
            )
            payload["future_series_action_alarm_update_requested"] = proposed.get(
                "future_series_action_alarm_update_requested",
                False,
            )
            payload["future_series_all_day_update_requested"] = proposed.get(
                "future_series_all_day_update_requested",
                False,
            )
            payload["future_series_calendar_move_requested"] = proposed.get(
                "future_series_calendar_move_requested",
                False,
            )
        if preview.get("operation") == "delete":
            payload["recurrence_delete_scope"] = proposed.get("recurrence_delete_scope", "")
            if expected.get("recurrence_expected"):
                payload["expected_recurrence_present"] = expected["recurrence_present"]
                payload["expected_recurrence"] = expected.get("recurrence", _empty_recurrence())
        payload.update(
            {
                "expected_alarm_offsets_minutes": expected["alarm_offsets_minutes"],
                "expected_alarm_absolute_dates": expected["alarm_absolute_dates"],
                "expected_alarm_sound_name": expected["alarm_sound_name"],
                "expected_alarm_email_address_sha256": expected[
                    "alarm_email_address_sha256"
                ],
                "expected_alarm_proximity": expected["alarm_proximity"],
                "expected_alarm_structured_location": expected["alarm_structured_location"],
            }
        )
        if preview["operation"] == "update":
            payload.update(
                {
                    "title": proposed["title"],
                    "start_date": proposed["start_date"],
                    "end_date": proposed["end_date"],
                    "time_zone": proposed["time_zone"],
                    "all_day": proposed["all_day"],
                    "alarm_offsets_minutes": proposed["alarm_offsets_minutes"],
                    "alarm_absolute_dates": proposed["alarm_absolute_dates"],
                    "alarm_sound_name": proposed["alarm_sound_name"],
                    "alarm_email_address": (
                        alarm_email_address if proposed["alarm_email_address_sha256"] else ""
                    ),
                    "alarm_proximity": proposed["alarm_proximity"],
                    "alarm_structured_location": proposed["alarm_structured_location"],
                    "event_url": event_url if proposed["event_url_requested"] else "",
                    "event_url_requested": proposed["event_url_requested"],
                    "event_url_clear_requested": proposed["event_url_clear_requested"],
                    "location": proposed["location"],
                    "structured_location": proposed["structured_location"],
                    "structured_location_clear_requested": proposed[
                        "structured_location_clear_requested"
                    ],
                    "notes": proposed["notes_text"],
                    "target_calendar_id": preview.get("resolved_target_calendar_id", ""),
                }
            )
    return payload


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"calendar-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
