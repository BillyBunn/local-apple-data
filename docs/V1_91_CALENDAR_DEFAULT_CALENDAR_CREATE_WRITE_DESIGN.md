# V1.91 Calendar Default Calendar Create Write Design

Status: Apply-capable implementation.

This document covers explicit default-calendar create planning. It adds a plan-only resolver for the user's current default event calendar and reuses the existing exact `calendar_handle` create/apply path. It does not add silent default-calendar guessing, apply-time default-calendar re-resolution, default-calendar mutation, update/delete by default-calendar, calendar creation/deletion, account management, attendees, invitations, travel time, or custom monthly/yearly recurrence components.

## EventKit Source Review

EventKit source review is limited to public SDK headers shipped on this Mac plus official Apple EventKit documentation.

- `EKEventStore.defaultCalendarForNewEvents` exposes the current default event calendar.
- `EKCalendar.allowsContentModifications` indicates whether the resolved calendar can accept event changes.
- Existing v1.86 target-calendar apply already resolves an exact `calendar:calendar:v1:` handle after approval-token verification and read-back checks the selected target calendar.

## Plan Contract

`calendar_plan_change` and `local-apple-data calendar plan` accept `use_default_calendar` / `--use-default-calendar` only for `operation=create`.

Plan-only resolver behavior:

- It calls the bounded Calendar target metadata flow with `include_default=true`.
- It requires exactly one default calendar result.
- It requires `allows_content_modifications:true`.
- It resolves the current default calendar to an exact `calendar:calendar:v1:` handle.
- It rejects simultaneous `calendar_title`, `calendar_handle`, and `use_default_calendar` target inputs.
- It returns `preview.default_calendar_resolution` with bounded metadata and `default_calendar_verified:true`.
- It sets `preview.target` to the same exact-handle shape used by normal `calendar_handle` create plans.

The approval fingerprint is identical to the exact `calendar_handle` create plan for the resolved handle. That keeps default-calendar planning as UX sugar over exact target selection instead of a new mutation target mode.

## Apply Contract

Apply does not accept `use_default_calendar`. If a caller tries it, the adapter returns `default_calendar_plan_only` before EventKit helper access.

To apply a default-calendar plan, the caller must use the approved preview target `calendar_handle` with the matching `calendar-apply:v1:<approval_fingerprint>` token and explicit confirmation. In other words, apply must use the approved preview target `calendar_handle`.

Apply resolves the target calendar handle only after the approval token and explicit confirmation pass. The resolved raw EventKit calendar identifier remains process-local helper proof only and is not returned to the caller. Read-back must verify `target_calendar_verified:true` against the approved handle.

If the user's default calendar changes after planning, apply still targets the originally approved exact handle. It does not re-read or reselect the default calendar during apply.

## Synthetic Tests Required

- Adapter tests for default-calendar planning, exact-handle fingerprint equivalence, explicit-target conflict refusal, missing/ambiguous default refusal, non-writable default refusal, apply with the bound handle, default drift after planning, and `default_calendar_plan_only` before EventKit helper access.
- CLI tests for plan `--use-default-calendar` and apply with the returned `--calendar-handle`.
- MCP tests for forwarding `use_default_calendar` on plan only and applying with the exact returned handle.
- Runtime verifier keys for default-calendar plan status/mode, resolution verification, exact-handle apply status, read-back calendar title, and target-calendar verification.

## Still Blocked

Silent default-calendar guessing, apply-time default-calendar re-resolution, default-calendar mutation, update/delete by default-calendar, calendar creation/deletion, and account management remain blocked.

Recurrence delete, existing-recurring-event update/delete, custom monthly/yearly recurrence rules, unbounded recurrence, attendees, invitations, travel time, timed-event time-zone inference, email/procedure alarms, and bulk Calendar mutation remain blocked.
