from __future__ import annotations

import ast
import importlib.util
import json
import sys
from collections.abc import Iterable
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_write_design_gates.py"
SPEC = importlib.util.spec_from_file_location("audit_write_design_gates", SCRIPT_PATH)
assert SPEC is not None
audit_write_design_gates = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["audit_write_design_gates"] = audit_write_design_gates
SPEC.loader.exec_module(audit_write_design_gates)

import audit_mutation_gates


def _constant_dict_keys(name: str) -> list[str]:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id != name:
                continue
            assert isinstance(node.value, ast.Dict)
            return [
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
    raise AssertionError(f"{name} not found")


def test_write_design_gate_contract_maps_have_unique_paths() -> None:
    for name in ("REQUIRED_CURRENT_DOC_TEXT", "REQUIRED_CURRENT_SOURCE_TEXT"):
        keys = _constant_dict_keys(name)
        assert len(keys) == len(set(keys)), name


def test_current_project_write_design_gate_audit_passes() -> None:
    payload = audit_write_design_gates.audit_write_design_gates(
        Path(__file__).resolve().parents[1]
    )

    assert payload["status"] == "ok"
    assert payload["write_design_gate"] is True
    assert payload["design_docs_checked"] == len(
        audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert payload["approved_preview_tools"] == [
        "calendar_plan_calendar",
        "calendar_plan_calendar_change",
        "calendar_plan",
        "calendar_plan_change",
        "contacts_plan",
        "contacts_plan_change",
        "filesystem_plan",
        "filesystem_plan_change",
        "icloud_drive_plan",
        "icloud_drive_plan_change",
        "mail_plan",
        "mail_plan_change",
        "mail_plan_cleanup",
        "mail_plan_mailbox",
        "mail_plan_mailbox_change",
        "mail_plan_search_triage",
        "messages_plan",
        "messages_plan_change",
        "notes_plan",
        "notes_plan_change",
        "photos_plan",
        "photos_plan_change",
        "reminders_plan_list",
        "reminders_plan_list_change",
        "reminders_plan_change",
        "shortcuts_plan",
        "shortcuts_plan_run",
    ]
    assert payload["approved_write_tools"] == [
        "calendar_apply_calendar",
        "calendar_apply_calendar_change",
        "calendar_apply",
        "calendar_apply_change",
        "contacts_apply",
        "contacts_apply_change",
        "filesystem_apply",
        "filesystem_apply_change",
        "icloud_drive_apply",
        "icloud_drive_apply_change",
        "mail_apply",
        "mail_apply_change",
        "mail_apply_cleanup",
        "mail_apply_mailbox",
        "mail_apply_mailbox_change",
        "messages_apply",
        "messages_apply_change",
        "notes_apply",
        "notes_apply_change",
        "photos_apply",
        "photos_apply_change",
        "reminders_apply_list",
        "reminders_apply_list_change",
        "reminders_apply",
        "reminders_apply_change",
        "shortcuts_apply",
        "shortcuts_apply_run",
    ]
    assert payload["findings"] == []
    assert "messages_risky_mutation_source_review_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "icloud_drive_replace_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "icloud_drive_folder_create_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "icloud_drive_trash_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "icloud_drive_rename_copy_move_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "icloud_drive_folder_rename_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "icloud_drive_folder_trash_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "icloud_drive_folder_delete_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "icloud_drive_delete_text_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "notes_folder_move_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "reminders_list_move_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "reminders_list_crud_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "reminders_absolute_display_alarm_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "contacts_method_update_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "contacts_note_append_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "messages_participants_metadata_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "mail_search_discovery_read_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "calendar_target_calendar_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "calendar_absolute_alarm_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "calendar_recurrence_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "calendar_recurrence_update_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "calendar_event_url_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert "calendar_safe_non_http_event_url_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert (
        "calendar_selected_occurrence_event_url_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_recurring_occurrence_delete_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_recurring_series_delete_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_weekly_weekday_recurrence_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_monthly_weekday_recurrence_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_set_positions_recurrence_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_recurrence_clear_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_recurrence_replacement_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_future_series_reschedule_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_unbounded_recurrence_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_yearly_month_recurrence_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert (
        "calendar_yearly_month_nth_weekday_recurrence_write_v1"
        in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    )
    assert "icloud_drive_import_file_write_v1" in audit_write_design_gates.REQUIRED_DESIGN_DOCS
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["icloud_drive_replace_write_v1"]["path"]
        == "docs/V1_51_ICLOUD_DRIVE_REPLACE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["icloud_drive_folder_create_write_v1"]["path"]
        == "docs/V1_52_ICLOUD_DRIVE_FOLDER_CREATE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["icloud_drive_trash_write_v1"]["path"]
        == "docs/V1_53_ICLOUD_DRIVE_TRASH_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["icloud_drive_rename_copy_move_write_v1"]["path"]
        == "docs/V1_54_ICLOUD_DRIVE_RENAME_COPY_MOVE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["icloud_drive_folder_rename_write_v1"]["path"]
        == "docs/V1_60_ICLOUD_DRIVE_FOLDER_RENAME_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["icloud_drive_folder_trash_write_v1"]["path"]
        == "docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["icloud_drive_folder_delete_write_v1"]["path"]
        == "docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["icloud_drive_delete_text_write_v1"]["path"]
        == "docs/V1_68_ICLOUD_DRIVE_DELETE_TEXT_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["icloud_drive_import_file_write_v1"]["path"]
        == "docs/V1_129_ICLOUD_DRIVE_IMPORT_FILE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["notes_folder_move_write_v1"]["path"]
        == "docs/V1_158_NOTES_FOLDER_MOVE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["reminders_list_move_write_v1"]["path"]
        == "docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "reminders_absolute_display_alarm_write_v1"
        ]["path"]
        == "docs/V1_137_REMINDERS_ABSOLUTE_DISPLAY_ALARM_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "reminders_relative_display_alarm_write_v1"
        ]["path"]
        == "docs/V1_138_REMINDERS_RELATIVE_DISPLAY_ALARM_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "contacts_method_update_write_v1"
        ]["path"]
        == "docs/V1_69_CONTACTS_METHOD_UPDATE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "contacts_note_append_write_v1"
        ]["path"]
        == "docs/V1_70_CONTACTS_BACKUP_AND_NOTE_APPEND_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS["mail_search_discovery_read_v1"][
            "path"
        ]
        == "docs/V1_77_MAIL_SEARCH_DISCOVERY_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "messages_participants_metadata_v1"
        ]["path"]
        == "docs/V1_64_MESSAGES_PARTICIPANTS_METADATA.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_target_calendar_write_v1"
        ]["path"]
        == "docs/V1_86_CALENDAR_TARGET_CALENDAR_MOVE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_absolute_alarm_write_v1"
        ]["path"]
        == "docs/V1_88_CALENDAR_ABSOLUTE_ALARM_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_recurrence_write_v1"
        ]["path"]
        == "docs/V1_89_CALENDAR_RECURRENCE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_recurrence_update_write_v1"
        ]["path"]
        == "docs/V1_93_CALENDAR_RECURRENCE_UPDATE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_event_url_write_v1"
        ]["path"]
        == "docs/V1_94_CALENDAR_EVENT_URL_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_safe_non_http_event_url_write_v1"
        ]["path"]
        == "docs/V1_133_CALENDAR_SAFE_NON_HTTP_EVENT_URL_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_selected_occurrence_event_url_write_v1"
        ]["path"]
        == "docs/V1_117_CALENDAR_SELECTED_OCCURRENCE_EVENT_URL_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_selected_occurrence_structured_location_write_v1"
        ]["path"]
        == "docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_recurring_occurrence_delete_write_v1"
        ]["path"]
        == "docs/V1_96_CALENDAR_RECURRING_OCCURRENCE_DELETE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_recurring_future_delete_write_v1"
        ]["path"]
        == "docs/V1_97_CALENDAR_RECURRING_FUTURE_DELETE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_recurring_series_delete_write_v1"
        ]["path"]
        == "docs/V1_98_CALENDAR_RECURRING_SERIES_DELETE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_weekly_weekday_recurrence_write_v1"
        ]["path"]
        == "docs/V1_99_CALENDAR_WEEKLY_WEEKDAY_RECURRENCE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_recurrence_clear_write_v1"
        ]["path"]
        == "docs/V1_100_CALENDAR_RECURRENCE_CLEAR_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_recurrence_replacement_write_v1"
        ]["path"]
        == "docs/V1_126_CALENDAR_RECURRENCE_REPLACEMENT_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_future_series_scalar_update_write_v1"
        ]["path"]
        == "docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_unbounded_recurrence_write_v1"
        ]["path"]
        == "docs/V1_139_CALENDAR_UNBOUNDED_RECURRENCE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_yearly_month_recurrence_write_v1"
        ]["path"]
        == "docs/V1_106_CALENDAR_YEARLY_MONTH_RECURRENCE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_yearly_month_nth_weekday_recurrence_write_v1"
        ]["path"]
        == "docs/V1_111_CALENDAR_YEARLY_MONTH_NTH_WEEKDAY_RECURRENCE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_yearly_month_day_recurrence_write_v1"
        ]["path"]
        == "docs/V1_112_CALENDAR_YEARLY_MONTH_DAY_RECURRENCE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_monthly_weekday_recurrence_write_v1"
        ]["path"]
        == "docs/V1_113_CALENDAR_MONTHLY_WEEKDAY_RECURRENCE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_monthday_recurrence_write_v1"
        ]["path"]
        == "docs/V1_101_CALENDAR_MONTHDAY_RECURRENCE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_structured_location_write_v1"
        ]["path"]
        == "docs/V1_102_CALENDAR_STRUCTURED_LOCATION_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_structured_location_clear_write_v1"
        ]["path"]
        == "docs/V1_107_CALENDAR_STRUCTURED_LOCATION_CLEAR_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_email_alarm_write_v1"
        ]["path"]
        == "docs/V1_108_CALENDAR_EMAIL_ALARM_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_set_positions_recurrence_write_v1"
        ]["path"]
        == "docs/V1_123_CALENDAR_SET_POSITIONS_RECURRENCE_WRITE_DESIGN.md"
    )
    assert (
        audit_write_design_gates.REQUIRED_DESIGN_DOCS[
            "calendar_calendar_management_write_v1"
        ]["path"]
        == "docs/V1_124_CALENDAR_CALENDAR_MANAGEMENT_WRITE_DESIGN.md"
    )
    cli_contract = audit_write_design_gates.REQUIRED_CURRENT_SOURCE_TEXT[
        "tests/test_cli_metadata.py"
    ]
    assert "test_cli_icloud_drive_apply_rejects_root_override_without_test_opt_in" in cli_contract
    assert "test_cli_icloud_drive_plan_and_apply_rename_folder" in cli_contract
    assert "test_cli_icloud_drive_plan_and_apply_trash_folder" in cli_contract
    assert "import-file" in cli_contract
    assert "replace-file" in cli_contract
    assert "--source-file" in cli_contract
    assert "test_cli_calendar_plan_and_apply_create_all_day" in cli_contract
    assert "test_cli_calendar_plan_and_apply_weekly_weekday_recurrence" in cli_contract
    assert "--recurrence-weekdays" in cli_contract
    assert "--recurrence-unbounded" in cli_contract
    assert "test_cli_calendar_plan_and_apply_unbounded_recurrence" in cli_contract
    assert (
        "test_cli_calendar_plan_and_apply_update_unbounded_recurrence"
        in cli_contract
    )
    assert "--recurrence-month-days" in cli_contract
    assert "--recurrence-year-months" in cli_contract
    assert "--recurrence-year-month-days" in cli_contract
    assert "test_cli_calendar_plan_and_apply_clear_recurrence" in cli_contract
    assert "test_cli_calendar_plan_and_apply_mid_series_recurrence_replacement" in cli_contract
    assert "--clear-recurrence" in cli_contract
    assert "--recurrence-update-scope" in cli_contract
    assert "test_cli_calendar_plan_and_apply_structured_location" in cli_contract
    assert "test_cli_calendar_clear_structured_location_forwards_to_plan_and_apply" in cli_contract
    assert "test_cli_calendar_plan_and_apply_email_alarm_hash" in cli_contract
    assert "--structured-location" in cli_contract
    assert "--clear-structured-location" in cli_contract
    assert "--alarm-email-address" in cli_contract
    runtime_contract = audit_write_design_gates.REQUIRED_CURRENT_SOURCE_TEXT[
        "scripts/verify_runtime.py"
    ]
    assert "calendar_recurrence_apply_read_back_count" in runtime_contract
    assert "calendar_structured_location_apply_verified" in runtime_contract
    assert "calendar_structured_location_clear_apply_verified" in runtime_contract
    assert "calendar_email_alarm_apply_verified" in runtime_contract
    assert "mcp_calendar_email_alarm_apply_warning" in runtime_contract
    assert "calendar_update_recurrence_apply_read_back_count" in runtime_contract
    assert "calendar_update_recurrence_existing_apply_warning" in runtime_contract
    assert "calendar_mid_series_recurrence_replace_apply_verified" in runtime_contract
    assert "mcp_calendar_mid_series_recurrence_replace_apply_verified" in runtime_contract
    assert "calendar_unbounded_recurrence_plan_unbounded" in runtime_contract
    assert "calendar_unbounded_recurrence_apply_read_back_unbounded" in runtime_contract
    assert "mcp_calendar_unbounded_recurrence_plan_unbounded" in runtime_contract
    assert "mcp_calendar_unbounded_recurrence_apply_warning" in runtime_contract
    assert "calendar_weekday_recurrence_apply_read_back_weekdays" in runtime_contract
    assert "mcp_calendar_weekday_recurrence_plan_weekdays" in runtime_contract
    assert "calendar_recurrence_plan_month_days" in runtime_contract
    assert "calendar_recurrence_apply_read_back_month_days" in runtime_contract
    assert "mcp_calendar_recurrence_plan_month_days" in runtime_contract
    assert "calendar_monthly_weekday_recurrence_apply_read_back_weekdays" in runtime_contract
    assert "calendar_set_positions_recurrence_apply_read_back_set_positions" in runtime_contract
    assert "mcp_calendar_set_positions_recurrence_plan_set_positions" in runtime_contract
    assert "calendar_monthly_weekday_update_recurrence_apply_read_back_weekdays" in runtime_contract
    assert "mcp_calendar_monthly_weekday_recurrence_plan_weekdays" in runtime_contract
    assert "mcp_calendar_monthly_weekday_update_recurrence_plan_weekdays" in runtime_contract
    assert "calendar_year_month_recurrence_apply_read_back_year_months" in runtime_contract
    assert "mcp_calendar_year_month_recurrence_plan_year_months" in runtime_contract
    assert "calendar_year_month_day_recurrence_apply_read_back_year_month_days" in runtime_contract
    assert "calendar_year_month_day_update_recurrence_apply_read_back_year_month_days" in runtime_contract
    assert "mcp_calendar_year_month_day_recurrence_plan_year_month_days" in runtime_contract
    assert "mcp_calendar_year_month_day_update_recurrence_plan_year_month_days" in runtime_contract
    assert "calendar_year_month_weekday_recurrence_apply_read_back_year_month_weekdays" in runtime_contract
    assert "calendar_year_month_weekday_update_recurrence_apply_read_back_year_month_weekdays" in runtime_contract
    assert "mcp_calendar_year_month_weekday_recurrence_plan_year_month_weekdays" in runtime_contract
    assert "mcp_calendar_year_month_weekday_update_recurrence_plan_year_month_weekdays" in runtime_contract
    assert "calendar_year_day_recurrence_apply_read_back_year_days" in runtime_contract
    assert "calendar_year_week_update_recurrence_apply_read_back_year_weeks" in runtime_contract
    assert "calendar_year_week_update_recurrence_apply_read_back_weekdays" in runtime_contract
    assert "mcp_calendar_year_day_recurrence_plan_year_days" in runtime_contract
    assert "mcp_calendar_year_week_update_recurrence_plan_year_weeks" in runtime_contract
    assert "mcp_calendar_year_week_update_recurrence_plan_weekdays" in runtime_contract
    assert "calendar_recurrence_clear_apply_verified" in runtime_contract
    assert "mcp_calendar_recurrence_clear_apply_verified" in runtime_contract
    assert "calendar_recurrence_future_delete_apply_previous_present" in runtime_contract
    assert "calendar_event_url_apply_verified" in runtime_contract
    assert "calendar_recurrence_delete_apply_verified_absent" in runtime_contract
    assert "mcp_calendar_event_url_apply_warning" in runtime_contract
    assert "mcp_calendar_structured_location_clear_apply_warning" in runtime_contract
    assert "mcp_calendar_recurrence_delete_live_apply_fail_closed" in runtime_contract
    assert "mcp_calendar_recurrence_delete_apply_selected_absent" in runtime_contract
    assert "mcp_calendar_recurrence_delete_apply_adjacent_present" in runtime_contract
    assert "mcp_calendar_recurrence_apply_warning" in runtime_contract
    assert "mcp_calendar_update_recurrence_apply_warning" in runtime_contract
    assert "mcp_calendar_recurrence_update_availability_plan_status" in runtime_contract
    assert "mcp_calendar_recurrence_update_availability_plan_name" in runtime_contract
    assert "mcp_calendar_recurrence_update_availability_plan_scope" in runtime_contract
    assert "mcp_calendar_recurrence_update_availability_plan_expected_name" in runtime_contract
    assert "mcp_calendar_recurrence_update_availability_apply_status" in runtime_contract
    assert "mcp_calendar_recurrence_update_availability_apply_read_back_name" in runtime_contract
    assert "mcp_calendar_recurrence_update_availability_apply_selected_verified" in runtime_contract
    assert "calendar_recurrence_update_event_url_plan_status" in runtime_contract
    assert "calendar_recurrence_update_event_url_plan_sha256" in runtime_contract
    assert "calendar_recurrence_update_event_url_apply_verified" in runtime_contract
    assert "calendar_recurrence_update_event_url_apply_sha256" in runtime_contract
    assert "calendar_recurrence_update_event_url_replace_plan_status" in runtime_contract
    assert "calendar_recurrence_update_event_url_replace_apply_verified" in runtime_contract
    assert "calendar_recurrence_update_event_url_stale_warning" in runtime_contract
    assert "calendar_recurrence_update_event_url_clear_plan_requested" in runtime_contract
    assert "calendar_recurrence_update_event_url_clear_apply_verified" in runtime_contract
    assert "mcp_calendar_recurrence_update_event_url_plan_status" in runtime_contract
    assert "mcp_calendar_recurrence_update_event_url_plan_scope" in runtime_contract
    assert "mcp_calendar_recurrence_update_event_url_plan_sha256" in runtime_contract
    assert "mcp_calendar_recurrence_update_event_url_apply_verified" in runtime_contract
    assert "mcp_calendar_recurrence_update_event_url_apply_sha256" in runtime_contract
    assert "mcp_calendar_recurrence_update_event_url_clear_plan_requested" in runtime_contract
    assert "mcp_calendar_recurrence_update_event_url_clear_apply_verified" in runtime_contract
    assert "mcp_icloud_import_plan_status" in runtime_contract
    assert "mcp_icloud_import_apply_source_path_returned" in runtime_contract
    assert "mcp_icloud_import_source_hash_hidden" in runtime_contract
    assert "mcp_icloud_import_stale_warning" in runtime_contract
    assert "icloud_import_file_plan_status" in runtime_contract
    assert "icloud_import_file_apply_source_hash_returned" in runtime_contract
    assert "icloud_import_file_stale_warning" in runtime_contract
    assert '"+15550100" not in str(listing)' in runtime_contract
    mcp_contract = audit_write_design_gates.REQUIRED_CURRENT_SOURCE_TEXT[
        "tests/test_mcp_server.py"
    ]
    assert "reminders_search_lists" in mcp_contract
    assert "reminders_get_list" in mcp_contract
    assert "test_mcp_icloud_drive_plan_rename_folder_without_content_text" in mcp_contract
    assert "test_mcp_icloud_drive_plan_trash_folder_without_content_text" in mcp_contract
    assert "test_mcp_icloud_drive_plan_delete_folder_without_content_text" in mcp_contract
    assert "test_mcp_icloud_drive_apply_rename_copy_move_without_content_text" in mcp_contract
    assert "source_file" in mcp_contract
    assert "import_file" in mcp_contract
    assert "test_mcp_icloud_drive_apply_copy_folder_without_content_text" in mcp_contract
    assert "test_mcp_messages_participant_wrappers_preserve_exact_detail_gate" in mcp_contract
    assert "test_mcp_calendar_all_day_plan_and_apply_bind_flags_without_eventkit" in mcp_contract
    assert "test_mcp_calendar_recurrence_plan_and_apply_bind_without_eventkit" in mcp_contract
    assert (
        "test_mcp_calendar_unbounded_recurrence_plan_and_apply_bind_without_eventkit"
        in mcp_contract
    )
    assert (
        "test_mcp_calendar_update_unbounded_recurrence_plan_and_apply_bind_without_eventkit"
        in mcp_contract
    )
    assert "test_mcp_calendar_month_day_recurrence_plan_and_apply_bind_without_eventkit" in mcp_contract
    assert "test_mcp_calendar_monthly_weekday_recurrence_plan_and_apply_bind_without_eventkit" in mcp_contract
    assert "test_mcp_calendar_set_positions_recurrence_plan_and_apply_bind_without_eventkit" in mcp_contract
    assert "test_mcp_calendar_update_monthly_weekday_recurrence_plan_and_apply_bind_without_eventkit" in mcp_contract
    assert "test_mcp_calendar_yearly_month_recurrence_plan_and_apply_bind_without_eventkit" in mcp_contract
    assert "test_mcp_calendar_yearly_month_nth_weekday_recurrence_plan_and_apply_bind_without_eventkit" in mcp_contract
    assert "test_mcp_calendar_update_recurrence_plan_and_apply_bind_without_eventkit" in mcp_contract
    assert "test_mcp_calendar_event_url_plan_and_apply_bind_without_eventkit" in mcp_contract
    assert (
        "test_mcp_calendar_clear_structured_location_plan_and_apply_bind_without_eventkit"
        in mcp_contract
    )
    assert (
        "test_mcp_calendar_delete_recurring_occurrence_fails_closed_without_occurrence_identity"
        in mcp_contract
    )
    assert "test_mcp_mail_tools_redact_unexpected_errors" in mcp_contract
    assert "test_mcp_contacts_tools_redact_unexpected_errors" in mcp_contract
    assert "test_mcp_stdio_mail_error_keeps_contacts_available" in mcp_contract
    assert "test_mcp_contacts_update_forwards_exact_binding" in mcp_contract
    messages_contract = audit_write_design_gates.REQUIRED_CURRENT_SOURCE_TEXT[
        "tests/test_messages_adapter.py"
    ]
    assert "test_message_participant_detail_refuses_cross_chat_handle_binding" in messages_contract
    assert "test_messages_send_plan_and_apply_reject_participant_handles" in messages_contract
    contacts_contract = audit_write_design_gates.REQUIRED_CURRENT_SOURCE_TEXT[
        "tests/test_contacts_adapter.py"
    ]
    assert "test_plan_contact_change_update_replaces_contact_methods" in contacts_contract
    assert "test_apply_contact_change_replaces_contact_methods_and_reads_back" in contacts_contract
    assert "test_plan_contact_change_append_note_returns_exact_preview" in contacts_contract
    assert "note_safe_sha256" in contacts_contract
    calendar_contract = audit_write_design_gates.REQUIRED_CURRENT_SOURCE_TEXT[
        "tests/test_calendar_adapter.py"
    ]
    assert "test_plan_calendar_change_create_recurrence_binds_preview_and_token" in calendar_contract
    assert (
        "test_plan_calendar_change_create_unbounded_recurrence_binds_preview_and_token"
        in calendar_contract
    )
    assert (
        "test_plan_calendar_change_update_unbounded_recurrence_binds_preview_and_token"
        in calendar_contract
    )
    assert "test_plan_calendar_change_create_weekly_recurrence_weekdays_binds_preview" in calendar_contract
    assert "test_plan_calendar_change_create_monthly_recurrence_month_days_binds_preview" in calendar_contract
    assert "test_plan_calendar_change_create_monthly_weekday_recurrence_binds_preview" in calendar_contract
    assert "test_plan_calendar_change_create_set_positions_recurrence_binds_preview" in calendar_contract
    assert "test_apply_calendar_change_creates_weekly_weekday_recurrence_and_reads_back" in calendar_contract
    assert "test_apply_calendar_change_creates_monthly_weekday_recurrence_and_reads_back" in calendar_contract
    assert "test_apply_calendar_change_creates_set_positions_recurrence_and_reads_back" in calendar_contract
    assert "test_apply_calendar_change_creates_monthly_month_day_recurrence_and_reads_back" in calendar_contract
    assert "test_apply_calendar_change_creates_yearly_month_recurrence_and_reads_back" in calendar_contract
    assert "test_plan_calendar_change_update_weekly_weekday_recurrence_binds_preview" in calendar_contract
    assert "test_plan_calendar_change_update_monthly_month_day_recurrence_binds_preview" in calendar_contract
    assert "test_apply_calendar_change_updates_monthly_weekday_recurrence_and_reads_back" in calendar_contract
    assert "test_apply_calendar_change_creates_unbounded_recurrence_and_reads_back" in calendar_contract
    assert "test_apply_calendar_change_updates_unbounded_recurrence_and_reads_back" in calendar_contract
    assert (
        "test_apply_calendar_change_replaces_mid_series_recurrence_with_unbounded_rule"
        in calendar_contract
    )
    assert "test_plan_calendar_change_create_event_url_binds_preview_and_token" in calendar_contract
    assert "test_apply_calendar_change_creates_event_url_and_reads_back_hash" in calendar_contract
    assert (
        "test_apply_calendar_change_updates_selected_recurring_occurrence_event_url"
        in calendar_contract
    )
    assert (
        "test_apply_calendar_change_clears_selected_recurring_occurrence_event_url"
        in calendar_contract
    )
    assert (
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_mismatch_fails_unknown"
        in calendar_contract
    )
    assert (
        "test_apply_calendar_change_replaces_selected_recurring_occurrence_event_url"
        in calendar_contract
    )
    assert (
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_preserves_adjacent_url"
        in calendar_contract
    )
    assert (
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_refuses_stale_adjacent_url"
        in calendar_contract
    )
    assert (
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_clear_mismatch_fails_unknown"
        in calendar_contract
    )
    assert (
        "test_apply_calendar_change_selected_recurring_occurrence_adjacent_event_url_mismatch_fails_unknown"
        in calendar_contract
    )
    assert "recurrence_unbounded" in calendar_contract
    assert '"unbounded": True' in calendar_contract
    assert "unsupported_recurrence_for_operation" in calendar_contract


def test_write_design_gate_flags_missing_design_doc(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("docs/V1_11_REMINDERS_WRITE_DESIGN.md").unlink()

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "write_design_doc_missing", "reminders_write_v1")


def test_minimal_project_write_design_gate_baseline_is_clean(tmp_path: Path) -> None:
    payload = audit_write_design_gates.audit_write_design_gates(
        _minimal_project(tmp_path)
    )

    assert payload["status"] == "ok"
    assert payload["write_design_gate"] is True
    assert payload["findings"] == []


def test_write_design_gate_flags_missing_crud_priority_plan(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("docs/V1_33_FULL_CRUD_PRIORITY_PLAN.md").unlink()

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "write_design_doc_missing", "full_crud_priority_plan_v1")


def test_write_design_gate_flags_incomplete_design_doc(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    path = root / "docs/V1_11_REMINDERS_WRITE_DESIGN.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "Status: Apply-capable implementation.",
            "Status: Draft.",
        ),
        encoding="utf-8",
    )

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "write_design_doc_contract_missing", "reminders_write_v1")


def test_write_design_gate_flags_write_phase_mcp_tool(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path, mcp_tool_name="mail_preview")

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "write_phase_mcp_tool", "mail_preview")


def test_write_design_gate_flags_write_phase_cli_handler(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path, cli_handler_name="_reminders_preview_command")

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "write_phase_cli_handler", "_reminders_preview_command")


def test_write_design_gate_flags_missing_read_only_contract(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("README.md").write_text("Synthetic README.\n", encoding="utf-8")

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "read_only_contract_missing", "README.md")


def test_write_design_gate_flags_missing_current_doc_contract(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("docs/TESTING.md").write_text(
        "Synthetic testing doc without current iCloud Drive folder-create wording.\n",
        encoding="utf-8",
    )

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "current_doc_contract_missing", "docs/TESTING.md")


def test_write_design_gate_flags_missing_skill_create_folder_contract(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("skills/local-apple-data/SKILL.md").write_text(
        "icloud_drive_plan_change supports text-file create, append-text, or replace-text only.\n",
        encoding="utf-8",
    )

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "current_doc_contract_missing", "skills/local-apple-data/SKILL.md")


def test_write_design_gate_flags_stale_privacy_create_folder_hash_contract(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("docs/PRIVACY_MODEL.md").write_text(
        "non-mutating iCloud Drive create-folder planning for exact requested parent handles plus "
        "non-mutating iCloud Drive create-text planning for exact requested parent folder handles, "
        "non-mutating iCloud Drive append-text, replace-text, and trash-text planning for exact requested file handles "
        "plus expected current content hash\n"
        "Rejects unexpected `content_text`, file handles, expected-current SHA input, hidden names, path separators, and package suffixes.\n"
        "The v1.52 apply implementation:\n"
        "Returns metadata-only read-back with `privacy.content_inspected:false`, no content hash, and no child listing.\n"
        "Never logs folder names, handles, raw paths, approval fingerprints, or approval tokens.\n"
        "Requires the caller to obtain `expected_current_sha256` from exact-handle iCloud Drive content retrieval.\n"
        "## v1.53 iCloud Drive Trash Planning And Apply\n",
        encoding="utf-8",
    )

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "current_doc_contract_forbidden_text", "docs/PRIVACY_MODEL.md")


def test_write_design_gate_flags_stale_icloud_delete_current_doc_text(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    for relative, forbidden_phrases in audit_write_design_gates.FORBIDDEN_CURRENT_DOC_TEXT.items():
        path = root / relative
        required = audit_write_design_gates.REQUIRED_CURRENT_DOC_TEXT.get(relative, ())
        path.write_text(
            "\n".join(required) + "\n" + forbidden_phrases[0] + "\n",
            encoding="utf-8",
        )

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "current_doc_contract_forbidden_text", "docs/CAPABILITY_MATRIX.md")
    assert _finding(payload, "current_doc_contract_forbidden_text", "docs/MACOS_SUPPORT.md")
    assert _finding(
        payload,
        "current_doc_contract_forbidden_text",
        "docs/V1_33_FULL_CRUD_PRIORITY_PLAN.md",
    )
    assert _finding(payload, "current_doc_contract_forbidden_text", "docs/FRESH_CHAT_HANDOFF.md")
    assert _finding(payload, "current_doc_contract_forbidden_text", "README.md")
    assert _finding(payload, "current_doc_contract_forbidden_text", "src/local_apple_data/cli.py")


def test_write_design_gate_flags_missing_current_source_contract(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("scripts/verify_runtime.py").write_text(
        "runtime verifier without mcp create-folder apply proof keys\n",
        encoding="utf-8",
    )

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "current_source_contract_missing", "scripts/verify_runtime.py")


def test_write_design_gate_flags_missing_mail_move_stale_target_regression(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("tests/test_mail_content.py").write_text(
        "test_apply_mail_change_move_message_uses_exact_same_account_mailbox\n"
        "test_plan_mail_change_move_message_allows_exact_cross_account_mailbox\n"
        "test_plan_mail_change_move_message_refuses_trash_like_target\n",
        encoding="utf-8",
    )

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "current_source_contract_missing", "tests/test_mail_content.py")


def test_write_design_gate_flags_missing_calendar_all_day_regression(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("tests/test_calendar_adapter.py").write_text(
        "test_plan_calendar_change_create_all_day_binds_preview\n",
        encoding="utf-8",
    )

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "current_source_contract_missing", "tests/test_calendar_adapter.py")


def _finding(payload: dict, kind: str, name: str) -> bool:
    return any(
        finding["kind"] == kind and finding["name"] == name
        for finding in payload["findings"]
    )


def _minimal_project(
    tmp_path: Path,
    *,
    mcp_tool_name: str = "apple_data_health",
    cli_handler_name: str = "_health_command",
) -> Path:
    root = tmp_path / "project"
    root.joinpath("src/local_apple_data").mkdir(parents=True)
    root.joinpath("src/local_apple_data/adapters").mkdir(parents=True)
    root.joinpath(".codex-plugin").mkdir()
    root.joinpath("docs").mkdir()
    root.joinpath("scripts").mkdir()
    root.joinpath("tests").mkdir()
    root.joinpath("skills/local-apple-data").mkdir(parents=True)

    (root / "README.md").write_text(
        "Its plan/apply surfaces cover approved exact operations in Reminders, iCloud Drive, Calendar, Contacts excluding note mutation, Notes, Mail, Photos, Messages, Filesystem, and Shortcuts.\n"
        "Contacts note plan/apply contracts are designed and synthetic-testable, but live operations fail closed with `contacts_note_unavailable` before mutation.\n"
        "The Reminders exact same-source list-move write design gate is documented in `docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md`.\n"
        "local-apple-data notes apply --json --operation create-folder\n"
        "The Notes exact child-folder create write design gate is documented in `docs/V1_57_NOTES_FOLDER_CREATE_WRITE_DESIGN.md`.\n"
        "The Notes exact empty child-folder move write design gate is documented in `docs/V1_158_NOTES_FOLDER_MOVE_WRITE_DESIGN.md`.\n"
        "The Notes exact-folder rename write design gate is documented in `docs/V1_58_NOTES_FOLDER_RENAME_WRITE_DESIGN.md`.\n",
        encoding="utf-8",
    )
    (root / "docs/CAPABILITY_MATRIX.md").write_text(
        "docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md\n"
        "docs/V1_68_ICLOUD_DRIVE_DELETE_TEXT_WRITE_DESIGN.md\n"
        "docs/V1_132_ICLOUD_DRIVE_DELETE_FILE_WRITE_DESIGN.md\n"
        "delete-text requires exact supported text-file handle binding\n"
        "delete-file requires exact non-text non-package regular-file handle binding\n"
        "file permanent delete outside the exact delete-text or delete-file gates\n",
        encoding="utf-8",
    )
    (root / "docs/MACOS_SUPPORT.md").write_text(
        "exact text-file create/append/replace/trash/delete/rename/copy/move\n"
        "exact folder rename/trash/move, exact selected-folder delete, and exact empty folder copy\n"
        "exact regular-file delete\n"
        "does not permanently delete files outside the exact delete-text or delete-file gates\n"
        "mutate unbounded folder copy, recursive folder writes, or unbounded recursive folder delete\n",
        encoding="utf-8",
    )
    (root / "docs/MUTATION_GATES.md").write_text(
        "Approved write tools: `reminders apply`, `reminders_apply_change`, `icloud-drive apply`, `icloud_drive_apply_change`, `calendar apply`, `calendar_apply_change`, `contacts apply`, `contacts_apply_change`, `notes apply`, `notes_apply_change`, `mail apply`, `mail_apply_change`, `mail apply-mailbox`, `mail_apply_mailbox_change`, `mail apply-cleanup`, `mail_apply_cleanup`, `photos apply`, `photos_apply_change`, `messages apply`, `messages_apply_change`, `filesystem apply`, `filesystem_apply_change`, `shortcuts apply`, and `shortcuts_apply_run`.\n"
        "Reminders exact same-source list move through the plan/apply/read-back contract in `docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md`.\n"
        "For list-move they require a matching approval token, explicit confirmation, exact opaque reminder handle, exact opaque expected current-list handle, exact opaque same-source target-list handle, expected title, expected completion state, expected current list name checked before any already-target shortcut, EventKit apply, and `target_list_verified:true` identity proof.\n"
        "iCloud Drive exact folder Trash through the plan/apply/read-back metadata and absence-proof contracts in `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md` and `docs/V1_146_ICLOUD_DRIVE_NON_EMPTY_FOLDER_TRASH_WRITE_DESIGN.md`.\n"
        "For trash-folder they require a matching approval token, explicit confirmation, exact opaque directory handle, expected directory metadata SHA-256, metadata drift refusal, recoverable Trash move, original absence proof, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, `non_empty_allowed:true`, and metadata-only read-back.\n"
        "iCloud Drive exact folder move, including non-empty directories, through the plan/apply/read-back metadata-proof contract in `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md` and `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`.\n"
        "For move-folder they require a matching approval token, explicit confirmation, exact opaque directory handle, exact opaque target parent handle, expected directory metadata SHA-256, metadata drift refusal, descendant-parent refusal, no-overwrite target proof, source/target presence proof, `non_empty_allowed:true`, and metadata-only read-back.\n"
        "iCloud Drive exact empty folder copy through the plan/apply/read-back metadata-proof contract in `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md`.\n"
        "For copy-folder they require a matching approval token, explicit confirmation, exact opaque empty directory handle, exact opaque target parent handle, expected directory metadata SHA-256, metadata drift refusal, empty-folder refusal, no-overwrite target proof, source preservation proof, target presence proof, and metadata-only read-back.\n"
        "iCloud Drive exact selected-folder permanent delete through the plan/apply/read-back metadata, hidden-staging, and absence-proof contract in `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`.\n"
        "For delete-folder they require a matching approval token, explicit confirmation, one exact selected directory handle, expected directory metadata SHA-256, private bounded tree binding, metadata/tree drift refusal, hidden/symlink/package/tree-size refusal, hidden staging identity proof, bounded permanent staged-tree removal, original absence proof, `verified_absent:true`, `permanently_deleted:true` only on successful removal, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, and metadata-only read-back.\n"
        "iCloud Drive exact text-file permanent delete through the plan/apply/read-back content-hash, exact file identity, random-only hidden-staging, and absence-proof contract in `docs/V1_68_ICLOUD_DRIVE_DELETE_TEXT_WRITE_DESIGN.md`.\n"
        "For delete-text they require a matching approval token, explicit confirmation, one exact supported text-file handle, expected current SHA-256, approval fingerprint binding to exact file identity, stale identity/token replay refusal, current-content drift refusal, no-follow/package/symlink traversal refusal, random-only hidden staging identity proof, permanent unlink, original absence proof, `verified_absent:true`, `permanently_deleted:true` only on successful removal, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, and no raw path return.\n"
        "iCloud Drive exact regular-file replace through the plan/apply/read-back metadata-proof contract in `docs/V1_130_ICLOUD_DRIVE_REPLACE_FILE_WRITE_DESIGN.md`.\n"
        "For replace-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected target metadata SHA-256, one caller-selected local non-text non-package regular file outside the configured iCloud Drive root, private source identity/content binding, source/target extension match, target metadata drift refusal, source preservation proof, byte replacement proof, metadata-only target read-back, `source_path_returned:false`, `source_hash_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no source path/hash return, no content hash return, and no raw path return.\n"
        "iCloud Drive exact regular-file Trash through the plan/apply/read-back metadata-proof contract in `docs/V1_131_ICLOUD_DRIVE_TRASH_FILE_WRITE_DESIGN.md`.\n"
        "For trash-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected target metadata SHA-256, target metadata drift refusal, no-follow/package/symlink traversal refusal, recoverable Trash move, original absence proof, metadata-only read-back, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no content hash return, and no raw path return.\n"
        "iCloud Drive exact regular-file permanent delete through the plan/apply/read-back metadata-proof contract in `docs/V1_132_ICLOUD_DRIVE_DELETE_FILE_WRITE_DESIGN.md`.\n"
        "For delete-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected target metadata SHA-256, target metadata drift refusal, no-follow/package/symlink traversal refusal, hidden staging identity proof, permanent unlink, original absence proof, metadata-only read-back, `staging_path_returned:false`, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no content hash return, and no raw path return.\n"
        "Calendar selected recurring occurrence event URL set/clear through the plan/apply/read-back contract in `docs/V1_117_CALENDAR_SELECTED_OCCURRENCE_EVENT_URL_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence event URL set/clear they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity and hash-only URL-state binding, exact allow-listed `event_url` or update-only `clear_event_url:true`, required URL expected-state binding for clear, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence hash-only event URL read-back or absence proof, no raw URL return, and adjacent-occurrence presence/recurrence/URL-state preservation proof.\n"
        "Calendar selected recurring occurrence structured location set/clear through the plan/apply/read-back contract in `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`.\n"
        "For selected recurring occurrence structured location set/clear they require update-only `recurrence_update_scope:this_event`, exact recurrence shape binding, selected occurrence start/end identity binding, adjacent occurrence identity binding, bounded `structured_location` with explicit expected structured-location absence or exact `expected_structured_location` replacement binding, update-only `clear_structured_location:true` with exact `expected_structured_location`, a matching approval token, explicit confirmation, EventKit `.thisEvent` save, selected-occurrence structured-location read-back or structured/plain-location absence proof, and adjacent-occurrence preservation proof.\n"
        "| Contacts | Create contact; exact scalar/method/rich-field/image update; exact group membership; exact group create/rename/delete; exact batch; exact-contact delete | Contacts.framework helper | Approved except note mutation; live note operations fail closed with `contacts_note_unavailable` before mutation. |\n"
        "- Deleting Contacts outside the approved exact-contact delete gate.\n"
        "- Contacts note contracts are synthetic-testable, but live note mutation is unavailable and fails closed with `contacts_note_unavailable` before mutation.\n"
        "- Reminders delete outside the approved exact-handle delete gate.\n"
        "- Mail attachments outside the approved draft/send/reply/reply-all/forward local-file attachment gates.\n"
        "- Mail source attachment/non-body-part forwarding remains blocked.\n",
        encoding="utf-8",
    )
    (root / "docs/WRITE_TOOL_ROADMAP.md").write_text(
        audit_write_design_gates.CANONICAL_APPLY_SURFACE_SUMMARY
        + " are the only approved write surfaces.\n",
        encoding="utf-8",
    )
    (root / "docs/PRIVACY_MODEL.md").write_text(
        "non-mutating iCloud Drive append-text, replace-text, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file planning for exact requested file handles or parent handles plus expected current content, metadata hash, or private source-file binding\n"
        "Rejects unexpected `content_text`, file handles, expected-current SHA input, hidden names, path separators, and package suffixes.\n"
        "Rejects hidden CLI iCloud Drive `--root` overrides outside `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`\n"
        "trash folders outside the exact folder Trash gate, move folders outside the exact folder move gate, copy folders outside the exact empty-folder copy gate\n"
        "The v1.52 apply implementation:\n"
        "Returns metadata-only read-back with `privacy.content_inspected:false`, no content hash, and no child listing.\n"
        "Never logs folder names, handles, raw paths, approval fingerprints, or approval tokens.\n"
        "Never logs folder names, handles, metadata hashes, raw paths, approval fingerprints, or approval tokens.\n"
        "Sender search matching is limited to returned-safe masked account labels and masked email previews\n"
        "## v1.53 iCloud Drive Trash Planning And Apply\n",
        encoding="utf-8",
    )
    (root / "docs/THREAT_MODEL.md").write_text(
        "No content replacement outside the exact replace-text or replace-file gates, folder creation outside the exact create-folder gate, folder rename outside the exact folder rename gate, folder move outside the exact folder move gate, folder copy outside the exact empty-folder copy or bounded selected-folder copy gates, folder delete outside the exact selected-folder delete gate, trash/delete outside the exact trash-text, exact folder trash, exact regular-file trash, or exact delete-file gates, file permanent delete outside the exact delete-text or delete-file gates, import outside the exact import-file gate, rename/copy/move outside the exact text-file or regular-file gates, empty Trash, binary/document content generation, regular-file mutation outside exact import-file, exact replace-file, exact trash-file, exact delete-file, or metadata-only rename/copy/move gates, unbounded recursive folder write, copy, or delete, hidden-file write, symlink/package traversal, raw path write, or broad folder copy/delete is approved.\n"
        "use fd-based no-follow exclusive `mkdir` plus metadata-only directory read-back and existing-directory idempotency for create-folder\n"
        "Hidden CLI iCloud Drive `--root` overrides are rejected outside `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`\n"
        "append-text is governed separately by v1.18, replace-text by v1.51, create-folder by v1.52, trash-text by v1.53, text-file rename/copy/move by v1.54, exact folder rename by v1.60 plus v1.145, exact folder Trash by v1.61 plus v1.146, exact folder move by v1.62 plus v1.145, exact empty folder copy by v1.63 and bounded non-empty selected-folder copy by v1.147, exact selected-folder delete by v1.67, exact text-file delete by v1.68, regular-file rename/copy/move by v1.127, import-file by v1.129, replace-file by v1.130, trash-file by v1.131, and delete-file by v1.132\n"
        "create-folder is governed separately by `docs/V1_52_ICLOUD_DRIVE_FOLDER_CREATE_WRITE_DESIGN.md`\n"
        "create only one child folder under one exact normal parent folder with same-parent idempotency and metadata-only read-back\n"
        "Mail mutation supports optional bounded caller-selected local file attachments only for create-draft.\n"
        "Mail attachment mutation outside the approved draft/send/reply/reply-all/forward local-file attachment gates remains blocked.\n"
        "Mail source attachment/non-body-part forwarding remains blocked.\n",
        encoding="utf-8",
    )
    (root / "docs/CODEX_PLUGIN.md").write_text(
        "metadata-only read-back with `parent_folder_confirmed:true`\n"
        "exact child-folder create apply under one exact normal parent folder with metadata-only parent proof\n"
        "Rename-folder planning validates one exact directory `icloud:file:v1:` handle, expected directory `metadata_sha256`, bounded target folder name, no parent handle, and no content text\n"
        "Rename-folder apply requires the matching token, explicit confirmation, one exact directory handle, expected directory `metadata_sha256`, current metadata recheck, fd-relative no-overwrite rename, metadata-only source/target presence proof, `non_empty_allowed:true`, and no content hash or text return.\n"
        "Trash-folder apply requires the matching token, explicit confirmation, one exact directory handle, expected directory `metadata_sha256`, current metadata recheck, recoverable Trash move, metadata-only original absence proof, `empty_folder_confirmed` boolean read-back, `non_empty_allowed:true`, no raw Trash path return, and no content hash or text return.\n"
        "Move-folder apply requires the matching token, explicit confirmation, one exact directory handle, one exact target parent handle, expected directory `metadata_sha256`, current metadata recheck, descendant-parent refusal, fd-relative no-overwrite move, metadata-only source/target presence proof, `non_empty_allowed:true`, and no content hash or text return.\n"
        "Copy-folder apply requires the matching token, explicit confirmation, one exact empty directory handle, one exact target parent handle, expected directory `metadata_sha256`, current metadata recheck, empty-folder recheck, fd-relative no-overwrite create, source preservation proof, metadata-only target presence proof, `empty_folder_confirmed:true`, and no content hash or text return.\n"
        "Delete-folder apply requires the matching token, explicit confirmation, one exact directory handle, expected directory `metadata_sha256`, private bounded source-tree binding, current metadata/tree recheck, hidden/symlink/package/tree-size refusal, hidden staging identity proof, bounded permanent staged-tree removal, metadata-only original absence proof, `verified_absent:true`, `permanently_deleted:true` only after successful removal, `empty_folder_confirmed` boolean read-back, `non_empty_allowed:true`, no raw Trash path return, no staging path return, no child listing, and no content hash or text return.\n"
        "Delete-text apply requires the matching token, explicit confirmation, one exact supported text-file handle, expected current SHA-256, current content recheck, no-follow/package/symlink refusal, hidden staging identity proof, permanent unlink, original absence proof, `verified_absent:true`, `permanently_deleted:true` only after successful unlink, no raw Trash path return, no staging path return, and no content hash or text return.\n"
        "Regular-file rename/copy/move planning validates handle shape, expected `metadata_sha256`, bounded target filename, exact target parent handle when required, and no content text; apply resolves and enforces one exact non-text non-package regular file.\n"
        "Regular-file rename/copy/move apply requires the matching token, explicit confirmation, one exact non-text non-package regular-file handle, expected file `metadata_sha256`, current metadata recheck, no-overwrite target proof, metadata-only source/target presence proof, `content_text_returned:false`, `content_hash_returned:false`, no raw path return, and no content hash or text return.\n"
        "Delete-file planning validates one exact target regular-file handle, expected `metadata_sha256`, no parent handle, no filename, no source file, and no content text without resolving or writing iCloud Drive files.\n"
        "Delete-file apply requires the matching token, explicit confirmation, one exact non-text non-package regular-file handle, expected target `metadata_sha256`, current metadata recheck, no-follow hidden staging identity proof, permanent unlink, metadata-only original absence proof, `verified_absent:true`, `permanently_deleted:true` only after successful unlink, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no raw target path return, no raw Trash path return, no raw staging path return, and no content hash or text return.\n"
        "sender search matching is limited to returned-safe masked account labels and masked email previews\n",
        encoding="utf-8",
    )
    (root / "docs/" "CROSS_AGENT_ROUTING.md").write_text(
        "one exact directory handle plus expected directory `metadata_sha256` plus bounded target folder name plus no parent/content input for rename-folder\n"
        "one exact directory handle plus exact target parent handle plus expected directory `metadata_sha256` plus optional bounded target folder name plus no content input for move-folder\n"
        "one exact empty directory handle plus exact target parent handle plus expected directory `metadata_sha256` plus optional bounded target folder name plus no content input for copy-folder\n"
        "one exact selected directory handle plus expected directory `metadata_sha256` plus private bounded tree binding plus no parent/filename/content input for delete-folder\n"
        "one exact supported text-file handle plus expected current SHA-256 plus no parent/filename/content input for delete-text\n"
        "with metadata-only directory proof, read-back, absence-proof, source/target presence verification, or source-preservation verification\n",
        encoding="utf-8",
    )
    (root / "docs/TESTING.md").write_text(
        "synthetic iCloud Drive file retrieval and create-folder/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file plan/apply\n"
        "iCloud Drive content/detail plus create-folder/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply flows\n"
        "folder directory metadata read-back, no folder content-hash return, already-applied retry\n"
        "hidden CLI `--root` refusal outside `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`\n"
        "wrong returned folder-id refusal\n"
        "Notes default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, move-to-folder, and exact-note delete\n"
        "exact allow-listed event URL create/update/delete plan/apply plus update-only event URL clearing\n"
        "event URL raw-preview non-disclosure\n"
        "invalid-token raw-URL non-disclosure\n",
        encoding="utf-8",
    )
    (root / "skills/local-apple-data/SKILL.md").write_text(
        "future iCloud Drive create-folder, bounded create-folder-path, exact folder rename, exact folder Trash, exact selected-folder permanent delete, exact folder move, exact empty folder copy, text-file create, append-text, replace-text, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, or delete-file\n"
        "approved iCloud Drive create-folder, bounded create-folder-path, exact folder rename, exact folder Trash, exact selected-folder permanent delete, exact folder move, exact empty folder copy, text-file create, append-text, replace-text, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, or delete-file\n"
        "same parent handle/folder name for create-folder\n"
        "same parent handle/folder_components stable parent identity token binding for create-folder-path\n"
        "Rename/move use no-overwrite target reservation, no-follow swap, post-swap SHA/identity proof\n"
        "future Notes create-note, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, move-to-folder, or exact-note delete operation\n"
        "metadata-only parent proof\n"
        "Notes folder/account targeting outside exact note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, and move-to-folder gates\n"
        "optional exact allow-listed `event_url`\n"
        "expected_event_url_present\n"
        "expected_event_url_sha256\n"
        "update-only `recurrence_update_scope:this_event` for selected recurring occurrence title/plain-location/notes, timed start/end/time-zone, availability, event URL set/clear, or structured-location set/clear mutation with exact occurrence, adjacent-occurrence identity, and hash-only adjacent URL-state binding\n"
        "update one selected recurring occurrence's title/plain location/notes, timed start/end/time-zone, availability, event URL, or structured location through `recurrence_update_scope:this_event` with recurrence, selected occurrence, and adjacent occurrence identity proof plus hash-only adjacent URL-state preservation for event URL set/clear, EventKit `.thisEvent` read-back, and original occurrence absence proof when rescheduled\n"
        "selected recurring occurrence title/plain-location/notes, timed start/end/time-zone, availability, event URL set/clear, or structured-location set/clear update with `recurrence_update_scope:this_event`\n"
        "hash-only event URL read-back or absence proof\n"
        "Event URL non-allow-listed URL schemes\n",
        encoding="utf-8",
    )
    for contract in audit_write_design_gates.REQUIRED_DESIGN_DOCS.values():
        path = root / str(contract["path"])
        path.write_text(_design_doc_text(), encoding="utf-8")
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"interface": {"capabilities": ["Read", "Search", "MCP", "Local"]}}),
        encoding="utf-8",
    )
    (root / "src/local_apple_data/mcp_server.py").write_text(
        f"""
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
INSTRUCTIONS = {("The only apply-capable mutation surfaces are " + audit_write_design_gates.CANONICAL_APPLY_SURFACE_SUMMARY)!r}
mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)
@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def {mcp_tool_name}() -> dict:
    return {{}}
""".lstrip(),
        encoding="utf-8",
    )
    (root / "src/local_apple_data/adapters/icloud_drive.py").write_text(
        'PLAN_OPERATIONS = {"create_text", "append_text", "replace_text", "create_folder", "rename_folder", "trash_folder", "delete_folder", "move_folder", "copy_folder", "trash_text", "delete_text", "rename_text", "copy_text", "move_text", "rename_file", "copy_file", "move_file", "import_file", "replace_file", "trash_file", "delete_file"}\n',
        encoding="utf-8",
    )
    (root / "src/local_apple_data/adapters/calendar.py").write_text(
        'PLAN_OPERATIONS = {"create", "update", "delete"}\n'
        "RECURRENCE_FREQUENCIES\n"
        "MAX_RECURRENCE_INTERVAL\n"
        "MIN_RECURRENCE_OCCURRENCES\n"
        "MAX_RECURRENCE_OCCURRENCES\n"
        "_normalize_recurrence\n"
        "unsupported_recurrence_for_operation\n"
        "invalid_recurrence\n"
        "recurrence_set_positions requires another recurrence selector\n"
        'recurrence["set_positions"] = normalized_set_positions\n'
        '# "recurrence": normalized_recurrence\n'
        '# "recurrence_present": bool(\n',
        encoding="utf-8",
    )
    (root / "src/local_apple_data/cli.py").write_text(
        f"""
_icloud_drive_root_override_allowed = object()
LOCAL_APPLE_DATA_ALLOW_TEST_ROOT = "1"
unsupported_test_root = "unsupported_test_root"
_calendar_recurrence_year_months_arg
_calendar_recurrence_year_month_days_arg
_calendar_recurrence_year_days_arg
_calendar_recurrence_year_weeks_arg
_calendar_recurrence_set_positions_arg
CLI_MARKERS = [
    "--recurrence-end-date",
    "--clear-structured-location",
    "--recurrence-year-months",
    "--recurrence-year-month-days",
    "--recurrence-year-days",
    "--recurrence-year-weeks",
    "--recurrence-set-positions",
    "--event-url",
    "--expected-event-url-present",
    "--expected-event-url-sha256",
    "--source-file",
]

def {cli_handler_name}(args):
    return 0
""".lstrip(),
        encoding="utf-8",
    )
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
        "mail_sender_forward_apply_full_email_returned\n"
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
        "mcp_icloud_rename_folder_apply_status\n"
        "mcp_icloud_rename_folder_apply_source_present\n"
        "mcp_icloud_rename_folder_apply_target_present\n"
        "mcp_icloud_rename_folder_apply_content_hash_returned\n"
        "mcp_icloud_rename_folder_apply_empty_confirmed\n"
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
        "mcp_icloud_delete_folder_apply_content_hash_returned\n"
        "mcp_icloud_delete_folder_apply_empty_confirmed\n"
        "mcp_icloud_delete_folder_apply_non_empty_allowed\n"
        "mcp_icloud_delete_folder_apply_warning_count\n"
        "mcp_icloud_delete_folder_apply_child_name_returned\n"
        "mcp_icloud_move_folder_plan_status\n"
        "mcp_icloud_move_folder_apply_status\n"
        "mcp_icloud_move_folder_apply_source_present\n"
        "mcp_icloud_move_folder_apply_target_present\n"
        "mcp_icloud_move_folder_apply_content_hash_returned\n"
        "mcp_icloud_move_folder_apply_empty_confirmed\n"
        "mcp_icloud_move_folder_apply_warning_count\n"
        "icloud_copy_folder_plan_status\n"
        "icloud_copy_folder_apply_status\n"
        "icloud_copy_folder_apply_source_present\n"
        "icloud_copy_folder_apply_target_present\n"
        "icloud_copy_folder_apply_content_hash_returned\n"
        "icloud_copy_folder_apply_empty_confirmed\n"
        "icloud_copy_folder_apply_warning_count\n"
        "mcp_icloud_copy_folder_plan_status\n"
        "mcp_icloud_copy_folder_apply_status\n"
        "mcp_icloud_copy_folder_apply_source_present\n"
        "mcp_icloud_copy_folder_apply_target_present\n"
        "mcp_icloud_copy_folder_apply_content_hash_returned\n"
        "mcp_icloud_copy_folder_apply_empty_confirmed\n"
        "mcp_icloud_copy_folder_apply_warning_count\n"
        "mcp_icloud_trash_apply_status\n"
        "mcp_icloud_trash_apply_original_present\n"
        "mcp_icloud_trash_apply_trash_path_returned\n"
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
        "icloud_trash_apply_status\n"
        "icloud_trash_apply_original_present\n"
        "icloud_trash_stale_warning\n"
        "icloud_rename_apply_status\n"
        "icloud_rename_apply_content_text_returned\n"
        "icloud_rename_apply_sha_matches_expected\n"
        "icloud_rename_stale_warning\n"
        "icloud_rename_stale_target_missing\n"
        "icloud_rename_folder_plan_status\n"
        "icloud_rename_folder_apply_status\n"
        "icloud_rename_folder_apply_source_present\n"
        "icloud_rename_folder_apply_target_present\n"
        "icloud_rename_folder_apply_content_hash_returned\n"
        "icloud_rename_folder_apply_empty_confirmed\n"
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
        "icloud_delete_folder_apply_content_hash_returned\n"
        "icloud_delete_folder_apply_empty_confirmed\n"
        "icloud_delete_folder_apply_non_empty_allowed\n"
        "icloud_delete_folder_apply_warning_count\n"
        "icloud_delete_folder_apply_child_name_returned\n"
        "icloud_move_folder_plan_status\n"
        "icloud_move_folder_apply_status\n"
        "icloud_move_folder_apply_source_present\n"
        "icloud_move_folder_apply_target_present\n"
        "icloud_move_folder_apply_content_hash_returned\n"
        "icloud_move_folder_apply_empty_confirmed\n"
        "icloud_move_folder_apply_warning_count\n"
        "icloud_copy_folder_plan_status\n"
        "icloud_copy_folder_apply_status\n"
        "icloud_copy_folder_apply_source_present\n"
        "icloud_copy_folder_apply_target_present\n"
        "icloud_copy_folder_apply_content_hash_returned\n"
        "icloud_copy_folder_apply_empty_confirmed\n"
        "icloud_copy_folder_apply_warning_count\n"
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
        "calendar_all_day_plan_status\n"
        "calendar_all_day_apply_status\n"
        "calendar_all_day_apply_read_back_flag\n"
        "calendar_alarm_plan_status\n"
        "calendar_alarm_apply_status\n"
        "calendar_alarm_apply_read_back_offsets\n"
        "calendar_recurrence_plan_status\n"
        "calendar_recurrence_plan_frequency\n"
        "calendar_recurrence_plan_count\n"
        "calendar_recurrence_plan_month_days\n"
        "calendar_recurrence_apply_status\n"
        "calendar_recurrence_apply_read_back_frequency\n"
        "calendar_recurrence_apply_read_back_count\n"
        "calendar_recurrence_apply_read_back_month_days\n"
        "calendar_set_positions_recurrence_plan_status\n"
        "calendar_set_positions_recurrence_plan_weekdays\n"
        "calendar_set_positions_recurrence_plan_set_positions\n"
        "calendar_set_positions_recurrence_apply_status\n"
        "calendar_set_positions_recurrence_apply_read_back_weekdays\n"
        "calendar_set_positions_recurrence_apply_read_back_set_positions\n"
        "calendar_update_recurrence_plan_status\n"
        "calendar_update_recurrence_plan_frequency\n"
        "calendar_update_recurrence_plan_count\n"
        "calendar_update_recurrence_apply_status\n"
        "calendar_update_recurrence_apply_read_back_frequency\n"
        "calendar_update_recurrence_apply_read_back_count\n"
        "calendar_update_recurrence_existing_apply_status\n"
        "calendar_update_recurrence_existing_apply_mutation_applied\n"
        "calendar_update_recurrence_existing_apply_warning\n"
        "calendar_event_url_plan_status\n"
        "calendar_event_url_apply_verified\n"
        "calendar_event_url_apply_sha256\n"
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
        "mcp_calendar_recurrence_plan_status\n"
        "mcp_calendar_recurrence_plan_frequency\n"
        "mcp_calendar_recurrence_plan_month_days\n"
        "mcp_calendar_recurrence_apply_status\n"
        "mcp_calendar_recurrence_apply_warning\n"
        "calendar_unbounded_recurrence_plan_status\n"
        "calendar_unbounded_recurrence_plan_unbounded\n"
        "calendar_unbounded_recurrence_apply_status\n"
        "calendar_unbounded_recurrence_apply_read_back_unbounded\n"
        "mcp_calendar_unbounded_recurrence_plan_status\n"
        "mcp_calendar_unbounded_recurrence_plan_unbounded\n"
        "mcp_calendar_unbounded_recurrence_apply_status\n"
        "mcp_calendar_unbounded_recurrence_apply_warning\n"
        "mcp_calendar_set_positions_recurrence_plan_status\n"
        "mcp_calendar_set_positions_recurrence_plan_weekdays\n"
        "mcp_calendar_set_positions_recurrence_plan_set_positions\n"
        "mcp_calendar_set_positions_recurrence_apply_status\n"
        "mcp_calendar_set_positions_recurrence_apply_warning\n"
        "mcp_calendar_update_recurrence_plan_status\n"
        "mcp_calendar_update_recurrence_plan_frequency\n"
        "mcp_calendar_update_recurrence_apply_status\n"
        "mcp_calendar_update_recurrence_apply_warning\n"
        "mcp_calendar_event_url_plan_status\n"
        "mcp_calendar_event_url_apply_warning\n"
        "mcp_calendar_recurrence_delete_live_plan_status\n"
        "mcp_calendar_recurrence_delete_live_plan_fail_closed\n"
        "mcp_calendar_recurrence_delete_live_apply_status\n"
        "mcp_calendar_recurrence_delete_live_apply_fail_closed\n"
        "mcp_calendar_recurrence_delete_apply_status\n"
        "mcp_calendar_recurrence_delete_apply_verified_absent\n"
        "mcp_calendar_recurrence_delete_apply_selected_absent\n"
        "mcp_calendar_recurrence_delete_apply_adjacent_present\n"
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
        "calendar_target_search_status\n"
        "calendar_target_handle_plan_status\n"
        "calendar_target_handle_apply_status\n"
        "calendar_target_handle_apply_calendar\n"
        "calendar_move_plan_status\n"
        "calendar_move_apply_status\n"
        "calendar_move_apply_calendar\n"
        "contacts_update_apply_email_value\n"
        "contacts_update_apply_phone_value\n"
        "contacts_update_apply_url_count\n"
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
        "mcp_reminders_move_to_list_wrong_current_fingerprint_returned\n",
        encoding="utf-8",
    )
    (root / "src/local_apple_data/adapters/reminders.py").write_text(
        'PLAN_OPERATIONS = {"create", "complete", "uncomplete", "update_due_date", "update_title", "update_notes", "update_priority", "move_to_list", "delete"}\n'
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
        "recurrenceRequest\n"
        "recurrenceUpdateRequested\n"
        "applyRecurrence\n"
        "applyRecurrence(event, recurrence: proposedRecurrence)\n"
        "recurrencePayload\n"
        "recurrenceSetPositionsPayload\n"
        "recurrenceSetPositionsArrayValue\n"
        "setPositions: recurrenceSetPositions\n"
        "payload[\"set_positions\"] = setPositions\n"
        "current[\"set_positions\"]\n"
        "recurrenceMatches\n"
        "recurrenceMatches(event, proposedRecurrence)\n"
        "EKRecurrenceRule(recurrenceWith: frequency, interval: interval, end: end)\n"
        "EKRecurrenceEnd(occurrenceCount: count)\n"
        "recurrence_unbounded\n"
        '"unbounded": True\n'
        "event.recurrenceRules = [\n"
        "unsupported_recurrence_for_operation\n"
        "invalid_recurrence\n"
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
        "event.url = proposedEventURL\n"
        "expected_event_url_sha256\n"
        "includeURLProof\n"
        "proposedEventURLRequested\n"
        "proposedEventURLClearRequested\n"
        "readBackEventURLPresent\n"
        "readBackEventURLSHA256\n"
        "event_url_clear_read_back_mismatch\n",
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
        "test_eventkit_helper_checks_expected_list_before_already_applied\n",
        encoding="utf-8",
    )
    (root / "tests/test_cli_reminders.py").write_text(
        "test_cli_reminders_lists_and_list\n"
        "--target-list-handle\n"
        "--expected-list-handle\n"
        "--expected-list-name\n"
        "Synthetic Target List\n",
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
    (root / "tests/test_icloud_drive_adapter.py").write_text(
        'create_folder\nrename_folder\ntrash_folder\ndelete_folder\nmove_folder\ncopy_folder\ntrash_text\ndelete_text\nrename_text\ncopy_text\nmove_text\nrename_file\ncopy_file\nmove_file\nimport_file\nreplace_file\ntrash_file\ndelete_file\nalready_applied\n"content_sha256" not in result["read_back"]\nmetadata_sha256\ncontent_hash_returned\ntrash_path_returned\ntest_plan_icloud_drive_change_import_file_returns_preview_without_path_or_hash\ntest_apply_icloud_drive_change_import_file_copies_to_exact_parent\ntest_apply_icloud_drive_change_import_file_rejects_stale_source_token\ntest_plan_icloud_drive_change_import_file_rejects_unsafe_sources\ntest_plan_icloud_drive_change_replace_file_returns_preview_without_path_or_hash\ntest_apply_icloud_drive_change_replace_file_replaces_exact_target\ntest_apply_icloud_drive_change_replace_file_rejects_stale_source_token\ntest_apply_icloud_drive_change_replace_file_rejects_stale_target_metadata\ntest_apply_icloud_drive_change_trash_file_moves_exact_regular_file_to_trash\ntest_apply_icloud_drive_change_trash_file_rejects_stale_metadata\ntest_apply_icloud_drive_change_trash_file_rejects_text_handle\ntest_apply_icloud_drive_change_trash_file_rejects_symlink_handle\ntest_apply_icloud_drive_change_delete_file_removes_exact_regular_file\ntest_apply_icloud_drive_change_delete_file_rejects_stale_metadata\ntest_apply_icloud_drive_change_delete_file_rollback_does_not_claim_success\ntest_apply_icloud_drive_change_delete_file_rejects_text_handle\ntest_apply_icloud_drive_change_delete_file_rejects_symlink_handle\ntest_plan_icloud_drive_change_rename_folder_returns_preview_only\ntest_plan_icloud_drive_change_trash_folder_returns_preview_only\ntest_plan_icloud_drive_change_delete_folder_returns_preview_only\ntest_plan_icloud_drive_change_move_folder_returns_preview_only\ntest_plan_icloud_drive_change_copy_folder_returns_preview_only\ntest_apply_icloud_drive_change_renames_folder_and_preserves_child\ntest_apply_icloud_drive_change_rename_folder_rejects_stale_metadata\ntest_apply_icloud_drive_change_rename_folder_allows_non_empty_folder\ntest_apply_icloud_drive_change_non_empty_folder_probe_does_not_list_children\ntest_apply_icloud_drive_change_rename_folder_reports_partial_if_folder_changes_during_apply\ntest_apply_icloud_drive_change_rename_folder_reports_partial_if_folder_changes_during_apply\ntest_apply_icloud_drive_change_rename_folder_refuses_existing_target\ntest_apply_icloud_drive_change_rename_folder_rejects_file_handle\ntest_apply_icloud_drive_change_trashes_empty_folder_and_reads_back_absence\ntest_apply_icloud_drive_change_trash_folder_rejects_stale_metadata\ntest_apply_icloud_drive_change_trash_folder_allows_non_empty_folder\ntest_apply_icloud_drive_change_trash_folder_allows_apply_time_non_empty_race\ntest_apply_icloud_drive_change_trash_folder_reports_partial_if_cleanup_fails\ntest_apply_icloud_drive_change_trash_folder_rollback_does_not_claim_trash\ntest_apply_icloud_drive_change_trash_folder_rejects_file_handle\ntest_apply_icloud_drive_change_deletes_empty_folder_and_reads_back_absence\ntest_apply_icloud_drive_change_delete_folder_rejects_stale_metadata\ntest_apply_icloud_drive_change_delete_folder_rejects_non_empty_folder\ntest_apply_icloud_drive_change_delete_folder_rolls_back_if_folder_races_non_empty\ntest_apply_icloud_drive_change_delete_folder_reports_partial_if_race_rollback_fails\ntest_apply_icloud_drive_change_delete_folder_rejects_file_handle\ntest_apply_icloud_drive_change_moves_folder_and_preserves_child\ntest_apply_icloud_drive_change_move_folder_rejects_stale_metadata\ntest_apply_icloud_drive_change_move_folder_allows_non_empty_folder\ntest_apply_icloud_drive_change_move_folder_refuses_existing_target\ntest_apply_icloud_drive_change_move_folder_rejects_self_parent\ntest_apply_icloud_drive_change_move_folder_rejects_descendant_parent\ntest_apply_icloud_drive_change_move_folder_reports_partial_if_folder_changes_during_apply\ntest_apply_icloud_drive_change_copies_empty_folder_and_reads_back_metadata\ntest_apply_icloud_drive_change_copy_folder_rejects_stale_metadata\ntest_apply_icloud_drive_change_copy_folder_allows_non_empty_folder\ntest_apply_icloud_drive_change_copy_folder_refuses_existing_target\ntest_apply_icloud_drive_change_copy_folder_rejects_self_parent\ntest_apply_icloud_drive_change_copy_folder_rejects_descendant_parent\ntest_plan_icloud_drive_change_copy_folder_rejects_unsafe_or_too_large_tree\ntest_apply_icloud_drive_change_copy_folder_rolls_back_if_source_races_after_copy\ntest_apply_icloud_drive_change_copy_folder_reports_partial_if_race_cleanup_fails\ntest_apply_icloud_drive_change_copy_folder_reports_error_after_cleaned_target_identity_race\ntest_copy_folder_tree_and_cleanup_do_not_use_unbounded_os_walk\ntest_copy_folder_tree_cleanup_refuses_unexpected_target_entries\ntest_apply_icloud_drive_change_trash_text_rejects_invalid_utf8_target\ntest_apply_icloud_drive_change_trash_text_rejects_package_member_after_resolution\ntest_apply_icloud_drive_change_trash_text_rejects_unsafe_parent_reopen\ntest_apply_icloud_drive_change_trash_text_rechecks_after_swap\ntest_apply_icloud_drive_change_trash_text_reports_partial_after_cleanup_failure\ntest_apply_icloud_drive_change_renames_text_and_reads_back_absence\ntest_apply_icloud_drive_change_rename_text_refuses_existing_target\ntest_apply_icloud_drive_change_rename_text_rechecks_after_swap\ntest_apply_icloud_drive_change_copy_text_refuses_hash_drift\ntest_apply_icloud_drive_change_copy_text_rechecks_source_after_copy\ntest_apply_icloud_drive_change_copies_text_and_preserves_source\ntest_apply_icloud_drive_change_move_text_refuses_hash_drift\ntest_apply_icloud_drive_change_move_text_rechecks_after_swap\ntest_apply_icloud_drive_change_moves_text_to_exact_parent\ntest_apply_icloud_drive_change_rename_copy_move_refuse_symlink_targets\ntest_apply_icloud_drive_change_copy_cleanup_preserves_racing_replacement\ntest_apply_icloud_drive_change_rename_reports_partial_when_rollback_fails\ntest_apply_icloud_drive_change_move_reports_partial_when_rollback_fails\ntest_apply_icloud_drive_change_rename_preserves_verified_target_when_source_cleanup_races\ntest_apply_icloud_drive_change_move_preserves_verified_target_when_source_cleanup_races\ntest_trash_root_for_configured_default_uses_home_trash\n',
        encoding="utf-8",
    )
    with (root / "tests/test_icloud_drive_adapter.py").open("a", encoding="utf-8") as handle:
        handle.write(
            "test_apply_icloud_drive_change_delete_file_rechecks_before_staging\n"
            "test_apply_icloud_drive_change_delete_file_rejects_package_member\n"
            "test_apply_icloud_drive_change_delete_file_rejects_non_regular_handle\n"
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
        "test_cli_icloud_drive_plan_and_apply_rename_copy_move_text\n"
        "test_cli_icloud_drive_plan_and_apply_rename_copy_move_file\n"
        "test_cli_icloud_drive_rename_copy_move_tokens_bind_exact_plan\n"
        "import-file\n"
        "replace-file\n"
        "--source-file\n"
        "test_cli_notes_plan_rejects_icloud_drive_only_operations\n"
        "test_cli_icloud_drive_create_folder_rejects_conflicting_name_aliases\n"
        "test_cli_calendar_plan_and_apply_create_all_day\n"
        "test_cli_calendar_plan_and_apply_alarm_offsets\n"
        "test_cli_calendar_plan_and_apply_absolute_alarm_dates\n"
        "test_cli_calendar_plan_and_apply_recurrence\n"
        "test_cli_calendar_plan_and_apply_unbounded_recurrence\n"
        "test_cli_calendar_plan_and_apply_monthly_weekday_recurrence\n"
        "test_cli_calendar_plan_and_apply_update_recurrence\n"
        "test_cli_calendar_plan_and_apply_update_unbounded_recurrence\n"
        "test_cli_calendar_plan_and_apply_event_url\n"
        "test_cli_calendar_event_url_rejects_operation_mismatches\n"
        "test_cli_calendar_calendars_and_calendar_use_exact_handle\n"
        "test_cli_calendar_plan_and_apply_target_calendar_handles\n"
        "test_cli_mail_sender_handle_forwards_to_plan_and_apply\n"
        "--all-day\n"
        "--expected-all-day\n"
        "--alarm-offsets-minutes\n"
        "--expected-alarm-offsets-minutes\n"
        "--alarm-absolute-dates\n"
        "--expected-alarm-absolute-dates\n"
        "--recurrence-frequency\n"
        "--recurrence-interval\n"
        "--recurrence-count\n"
        "--recurrence-unbounded\n"
        "--recurrence-month-days\n"
        "--recurrence-month-weekdays\n"
        "--recurrence-set-positions\n"
        "--recurrence-year-months\n"
        "--recurrence-year-month-days\n"
        "--recurrence-year-days\n"
        "--recurrence-year-weeks\n"
        "--event-url\n"
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
        "test_mcp_icloud_drive_plan_rename_copy_move_without_content_text\n"
        "test_mcp_icloud_drive_apply_rename_copy_move_without_content_text\nsource_file\nimport_file\ntest_mcp_icloud_drive_apply_copy_folder_without_content_text\n"
        "test_mcp_messages_participant_wrappers_preserve_exact_detail_gate\n"
        "reminders_search_lists\n"
        "reminders_get_list\n"
        "test_mcp_reminders_list_move_wrappers_preserve_exact_gate\n"
        "test_mcp_calendar_all_day_plan_and_apply_bind_flags_without_eventkit\n"
        "test_mcp_calendar_alarm_offsets_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_absolute_alarms_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_unbounded_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_set_positions_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_update_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_update_unbounded_recurrence_plan_and_apply_bind_without_eventkit\n"
        "test_mcp_calendar_event_url_plan_and_apply_bind_without_eventkit\n"
            "test_mcp_calendar_delete_recurring_occurrence_fails_closed_without_occurrence_identity\n"
            "test_mcp_mail_tools_redact_unexpected_errors\n"
            "test_mcp_contacts_tools_redact_unexpected_errors\n"
            "test_mcp_stdio_mail_error_keeps_contacts_available\n"
            "test_mcp_calendar_event_url_rejects_operation_mismatches\n"
        "test_mcp_calendar_target_calendar_handles_bind_without_eventkit\n"
        "test_mcp_contacts_update_forwards_exact_binding\n"
        "test_mcp_mail_move_forwards_exact_target_mailbox\n"
        "target_mailbox_handle\n"
        "mail:mailbox:v1:target\n"
        "test_mcp_mail_sender_handle_forwards_exact_inputs\n"
        "alarm_offsets_minutes=[0, -10]\n"
        "alarm_absolute_dates=[\"2026-06-05T16:45:00Z\"]\n"
        "recurrence_frequency=\"weekly\"\n"
        "recurrence_count=5\n"
        "recurrence_unbounded=True\n"
        "recurrence_set_positions=[-1]\n"
        "event_url=\"http://meet.example.invalid/runtime?id=42\"\n"
        "all_day=True\n"
        "create_folder\nrename_folder\ntrash_folder\ndelete_folder\nmove_folder\ncopy_folder\ntrash_text\ndelete_text\nrename_text\ncopy_text\nmove_text\nrename_file\ncopy_file\nmove_file\nimport_file\nreplace_file\ntrash_file\ndelete_file\n",
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
    (root / "tests/test_calendar_adapter.py").write_text(
        "test_plan_calendar_change_create_all_day_binds_preview\n"
        "test_plan_calendar_change_create_rejects_string_boolean\n"
        "test_apply_calendar_change_creates_all_day_event_and_reads_back\n"
        "test_apply_calendar_change_updates_all_day_event_and_reads_back\n"
        "test_plan_calendar_change_update_rejects_string_boolean_flags\n"
        "test_apply_calendar_change_deletes_all_day_event_and_binds_expected_flag\n"
        "test_plan_calendar_change_delete_rejects_string_expected_all_day\n"
        "test_eventkit_update_checks_expected_state_before_already_applied\n"
        "test_plan_calendar_change_create_alarm_offsets_binds_preview\n"
        "test_plan_calendar_change_create_absolute_alarms_binds_preview\n"
        "test_plan_calendar_change_create_recurrence_binds_preview_and_token\n"
        "test_plan_calendar_change_create_unbounded_recurrence_binds_preview_and_token\n"
        "test_plan_calendar_change_update_unbounded_recurrence_binds_preview_and_token\n"
        "test_plan_calendar_change_create_set_positions_recurrence_binds_preview\n"
        "test_plan_calendar_change_set_positions_requires_recurrence_selector\n"
        "test_plan_calendar_change_rejects_unsupported_recurrence_shapes\n"
        "test_plan_calendar_change_update_recurrence_binds_preview_and_token\n"
        "test_plan_calendar_change_create_event_url_binds_preview_and_token\n"
        "test_plan_calendar_change_update_event_url_binds_expected_state_and_token\n"
        "test_plan_calendar_change_create_rejects_expected_event_url_state\n"
        "test_plan_calendar_change_delete_rejects_event_url_input\n"
        "test_plan_calendar_change_rejects_non_exact_expected_event_url_sha\n"
        "test_apply_calendar_change_creates_event_url_and_reads_back_hash\n"
        "test_apply_calendar_change_updates_event_url_with_expected_state\n"
        "test_apply_calendar_change_flags_event_url_read_back_mismatch\n"
        "test_apply_calendar_change_updates_selected_recurring_occurrence_event_url\n"
        "test_apply_calendar_change_clears_selected_recurring_occurrence_event_url\n"
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_mismatch_fails_unknown\n"
        "test_apply_calendar_change_replaces_selected_recurring_occurrence_event_url\n"
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_preserves_adjacent_url\n"
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_refuses_stale_adjacent_url\n"
        "test_apply_calendar_change_selected_recurring_occurrence_event_url_clear_mismatch_fails_unknown\n"
        "test_apply_calendar_change_selected_recurring_occurrence_adjacent_event_url_mismatch_fails_unknown\n"
        "test_get_calendar_event_returns_url_hash_proof_without_raw_url\n"
        "test_plan_calendar_change_delete_rejects_recurrence\n"
        "test_plan_calendar_change_rejects_mixed_alarm_modes\n"
        "test_plan_calendar_change_rejects_invalid_alarm_offsets\n"
        "test_apply_calendar_change_creates_alarm_offsets_and_reads_back\n"
        "test_apply_calendar_change_creates_absolute_alarm_and_reads_back\n"
        "test_apply_calendar_change_creates_recurring_event_and_reads_back\n"
        "test_apply_calendar_change_creates_unbounded_recurrence_and_reads_back\n"
        "test_apply_calendar_change_updates_unbounded_recurrence_and_reads_back\n"
        "test_apply_calendar_change_replaces_mid_series_recurrence_with_unbounded_rule\n"
        "test_apply_calendar_change_creates_set_positions_recurrence_and_reads_back\n"
        "test_apply_calendar_change_updates_recurrence_and_reads_back\n"
        "test_apply_calendar_change_updates_set_positions_recurrence_and_reads_back\n"
        "test_apply_calendar_change_update_recurrence_requires_matching_read_back\n"
        "test_plan_calendar_change_delete_recurring_scope_binds_preview_and_token\n"
        "test_apply_calendar_change_deletes_recurring_occurrence_and_binds_scope\n"
        "test_apply_calendar_change_rejects_unscoped_recurring_delete\n"
        "test_apply_calendar_change_rejects_scoped_nonrecurring_delete\n"
        "test_apply_calendar_change_updates_alarm_offsets_and_binds_expected_state\n"
        "test_apply_calendar_change_deletes_event_and_binds_expected_alarm_offsets\n"
        "test_apply_calendar_change_deletes_event_and_binds_expected_absolute_alarm\n"
        "test_eventkit_bounded_calendar_mutation_binds_alarm_offsets\n"
        "test_search_calendar_calendars_returns_metadata_only_and_default\n"
        "test_get_calendar_calendar_returns_exact_metadata\n"
        "test_apply_calendar_change_creates_event_with_exact_calendar_handle\n"
        "test_apply_calendar_change_moves_event_to_exact_calendar_handle\n"
        "test_eventkit_calendar_target_selection_uses_public_eventkit_apis\n"
        "alarmOffsetsMinutes(event) == nil\n"
        "state.offsets == nil\n"
        "state.absoluteDates == nil\n"
        "currentAlarmOffsetsMinutes == expectedAlarmOffsetsMinutes\n"
        "currentAlarmAbsoluteDates == expectedAlarmAbsoluteDates\n"
        "dateStringArrayValue(request, \"expected_alarm_absolute_dates\")\n"
        "applyAlarms(event, offsets: proposedAlarmOffsetsMinutes, absoluteDates: proposedAlarmAbsoluteDates)\n"
        "EKRecurrenceRule(recurrenceWith: frequency, interval: interval, end: end)\n"
        "EKRecurrenceEnd(occurrenceCount: count)\n"
        "event.recurrenceRules = [\n"
        "recurrenceRequest(request)\n"
        "recurrenceUpdateRequested\n"
        "recurrenceMatches(event, proposedRecurrence)\n"
        "applyRecurrence(event, recurrence: proposedRecurrence)\n"
        "event_url_read_back_mismatch\n"
        "event_url_clear_read_back_mismatch\n"
        "unsupported_recurrence_for_operation\n"
        "recurrence_delete_scope\n"
        "expected_recurrence_present\n"
        "unsupported_recurrence_delete_scope\n"
        "recurrenceDeleteScope == \"this_event\"\n"
        "try store.remove(event, span: .thisEvent, commit: true)\n"
        "applyAlarmOffsets(event, proposedAlarmOffsetsMinutes)\n"
        "expected_all_day\n"
        "expected_alarm_offsets_minutes\n",
        encoding="utf-8",
    )
    (root / "tests/test_mail_content.py").write_text(
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
    _refresh_minimal_project_contracts(
        root,
        mcp_tool_name=mcp_tool_name,
        cli_handler_name=cli_handler_name,
    )
    return root


def _design_doc_text() -> str:
    phrases = []
    for contract in audit_write_design_gates.REQUIRED_DESIGN_DOCS.values():
        phrases.extend(contract["phrases"])
    for current_phrases in audit_write_design_gates.REQUIRED_CURRENT_DOC_TEXT.values():
        phrases.extend(current_phrases)
    return "\n".join(str(phrase) for phrase in phrases) + "\n"


def _refresh_minimal_project_contracts(
    root: Path,
    *,
    mcp_tool_name: str,
    cli_handler_name: str,
) -> None:
    document_lines: dict[str, list[str]] = {}

    for contract in audit_write_design_gates.REQUIRED_DESIGN_DOCS.values():
        _extend_unique(
            document_lines.setdefault(str(contract["path"]), []),
            contract["phrases"],
        )
    for relative, required_text in audit_write_design_gates.REQUIRED_MUTATION_GATE_TEXT.items():
        _extend_unique(document_lines.setdefault(relative, []), (required_text,))
    for relative, required_phrases in audit_write_design_gates.REQUIRED_CURRENT_DOC_TEXT.items():
        _extend_unique(document_lines.setdefault(relative, []), required_phrases)
    for relative, required_text in audit_mutation_gates.REQUIRED_MUTATION_GATE_TEXT.items():
        if relative.startswith("src/"):
            continue
        _extend_unique(document_lines.setdefault(relative, []), (required_text,))
    for relative, required_phrases in audit_mutation_gates.REQUIRED_MUTATION_DETAIL_TEXT.items():
        if relative.startswith("src/"):
            continue
        _extend_unique(document_lines.setdefault(relative, []), required_phrases)

    privacy_lines = document_lines.setdefault("docs/PRIVACY_MODEL.md", [])
    _extend_unique(
        privacy_lines,
        (
            "The v1.52 apply implementation:",
            "Metadata-only create-folder read-back.",
            "## v1.53 iCloud Drive Trash Planning And Apply",
        ),
    )
    for relative, lines in document_lines.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    source_by_path: dict[str, list[str]] = {}
    for relative, constants in audit_mutation_gates.REQUIRED_OPERATION_SETS.items():
        lines = source_by_path.setdefault(relative, [])
        for constant_name, values in constants.items():
            lines.append(f"{constant_name} = {sorted(values)!r}")

    calendar_lines = source_by_path.setdefault(
        "src/local_apple_data/adapters/calendar.py", []
    )
    calendar_lines.append(
        "RECURRENCE_FREQUENCIES = "
        f"{list(audit_write_design_gates.CALENDAR_RECURRENCE_FREQUENCY_CONTRACT)!r}"
    )

    cli_lines = [
        "class _Parser:",
        "    def add_argument(self, *args, **kwargs):",
        "        return None",
        "",
    ]
    for parser_name, choices in audit_mutation_gates.REQUIRED_CLI_OPERATION_CHOICES.items():
        cli_lines.extend(
            (
                f"{parser_name} = _Parser()",
                f"{parser_name}.add_argument('--operation', choices={sorted(choices)!r})",
            )
        )
    recurrence_choices = 'choices=["daily", "weekly", "monthly", "yearly"]'
    cli_lines.extend(
        (
            f"# {recurrence_choices}",
            f"# {recurrence_choices}",
            "",
            f"def {cli_handler_name}(args):",
            "    return 0",
        )
    )
    source_by_path["src/local_apple_data/cli.py"] = cli_lines

    mcp_lines = [
        "from typing import Literal",
        "",
        "class _Mcp:",
        "    def tool(self, **kwargs):",
        "        return lambda function: function",
        "",
        "mcp = _Mcp()",
        "READ_ONLY_ANNOTATIONS = object()",
    ]
    for literal_name, values in audit_mutation_gates.REQUIRED_MCP_OPERATION_LITERALS.items():
        literal_values = ", ".join(repr(value) for value in sorted(values))
        mcp_lines.append(f"{literal_name} = Literal[{literal_values}]")
    mcp_lines.extend(
        (
            "",
            "@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)",
            f"def {mcp_tool_name}() -> dict:",
            "    return {}",
        )
    )
    for required_text in (
        audit_mutation_gates.REQUIRED_MUTATION_GATE_TEXT[
            "src/local_apple_data/mcp_server.py"
        ],
        *audit_mutation_gates.REQUIRED_MUTATION_DETAIL_TEXT.get(
            "src/local_apple_data/mcp_server.py", ()
        ),
    ):
        mcp_lines.append(f"# {required_text}")
    source_by_path["src/local_apple_data/mcp_server.py"] = mcp_lines

    swift_lines = source_by_path.setdefault("scripts/eventkit_helper.swift", [])
    for frequency in audit_write_design_gates.CALENDAR_RECURRENCE_FREQUENCY_CONTRACT:
        swift_lines.extend((f"// case .{frequency}:", f'// case "{frequency}":'))

    for relative, required_phrases in audit_write_design_gates.REQUIRED_CURRENT_SOURCE_TEXT.items():
        prefix = "// " if relative.endswith(".swift") else "# "
        lines = source_by_path.setdefault(relative, [])
        lines.extend(f"{prefix}{phrase}" for phrase in required_phrases)

    for relative, lines in source_by_path.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = {
        "description": (
            audit_mutation_gates.REQUIRED_PLUGIN_DESCRIPTION_TEXT
            + " "
            + audit_mutation_gates.CONTACTS_NOTE_FAIL_CLOSED_CONTRACT
        ),
        "interface": {
            "capabilities": sorted(audit_mutation_gates.EXPECTED_MANIFEST_CAPABILITIES),
            "longDescription": "\n".join(
                audit_mutation_gates.REQUIRED_PLUGIN_LONG_DESCRIPTION_TEXT
            ),
        },
    }
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def _extend_unique(target: list[str], values: Iterable[object]) -> None:
    for value in values:
        text = str(value)
        if text not in target:
            target.append(text)
