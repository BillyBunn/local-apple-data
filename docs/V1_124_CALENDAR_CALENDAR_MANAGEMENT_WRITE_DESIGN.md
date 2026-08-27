# V1.124 Calendar Synthetic Calendar Management Write Design

Status: Apply-capable implementation.

This gate adds Calendar calendar create, rename, and delete for synthetic
`LAD-TEST-*` calendars only. It uses public EventKit calendar APIs and keeps
calendar source/account selection exact-handle gated.

Apple's public EventKit SDK exposes `EKCalendar(for:eventStore:)`,
`EKCalendar.source`, and `EKEventStore.saveCalendar(_:commit:)`. The local SDK
also exposes `EKEventStore.removeCalendar(_:commit:)`, but the public headers
state that `predicateForEventsWithStartDate:endDate:calendars:` will "only
return events within a four year timespan" while `removeCalendar` deletes all
events and reminders. In other words, the predicate can only return events
within a bounded window, but removeCalendar deletes all events and reminders.
Audit phrase: EventKit can only return events within a four year timespan; public EventKit headers say only return events within a four year timespan; fixed 1900-01-01 through 2100-01-01.
This gate does not approve real/non-synthetic calendar delete. It approves only
synthetic `LAD-TEST-*` calendar delete after exact-handle binding, event-only
calendar proof, non-default/writable/non-subscribed/non-immutable checks,
bounded 1900-01-01 through 2100-01-01 empty-event proof, and post-delete
absence proof.

## Approved Shape

- `calendar plan-calendar --operation create-calendar --source-calendar-handle
  <calendar:calendar:v1:...> --calendar-title LAD-TEST-*`
- `calendar apply-calendar --operation create-calendar ... --approval-token
  calendar-apply:v1:<fingerprint> --confirm-apply`
- `calendar plan-calendar --operation rename-calendar --calendar-handle
  <calendar:calendar:v1:...> --new-calendar-title LAD-TEST-*`
- `calendar apply-calendar --operation rename-calendar ...`
- `calendar plan-calendar --operation delete-calendar --calendar-handle
  <calendar:calendar:v1:...>`
- `calendar apply-calendar --operation delete-calendar ...`
- MCP equivalents are `calendar_plan_calendar_change` and
  `calendar_apply_calendar_change`.

Create selects an EventKit source by an exact existing
`calendar:calendar:v1:` handle and creates a new calendar in that same source.
The selected source calendar must not be subscribed, birthday-backed,
immutable, or read-only.
No raw source/account identifier is accepted or returned.

Rename targets one exact `calendar:calendar:v1:` handle. The target must be non-default, non-subscribed, non-immutable, writable, titled `LAD-TEST-*`, and empty in the bounded safety window.

Delete targets one exact `calendar:calendar:v1:` handle. The target must be
non-default, non-subscribed, non-immutable, writable, titled `LAD-TEST-*`,
event-only, and empty in the bounded safety window.

## Planning Contract

Planning is non-mutating. It resolves the exact source or target calendar,
checks synthetic title shape, refuses subscribed/birthday/immutable/read-only
create source calendars, checks duplicate title in the same source, binds safe
calendar/source hashes into the approval fingerprint, and returns only safe
metadata. Raw EventKit calendar/source identifiers are not exposed.

Rename and delete planning request EventKit safety counts for the fixed
1900-01-01 through 2100-01-01 event window and refuse non-empty calendars.
Delete planning also refuses calendars whose `allowedEntityTypes` may contain
reminders.

## Apply Contract

Apply requires the exact `calendar-apply:v1:<approval_fingerprint>` token,
`confirm_apply:true`, the same approved inputs, and current calendar/source
safe-hash re-resolution. Stale targets are refused before mutation.

Create uses `EKCalendar(for:eventStore:)`, sets the approved title and selected
source, saves with `saveCalendar`, then proves title and source read-back.

Rename updates only the approved synthetic empty calendar title, saves with
`saveCalendar`, then proves the new title and empty state.

Delete removes only the approved synthetic, event-only, empty calendar with
`removeCalendar`, then proves the selected calendar handle is absent. Missing
or mixed allowed-entity-type proof is refused before mutation. Failed absence
proof reports `apply_unknown` with `mutation_applied:true`.

## Verification

Fixture-backed runtime verifier proves direct create, rename, and delete
planning/apply read-back plus MCP wrapper create/apply proof. Direct keys are
`calendar_management_create_plan_status`,
`calendar_management_create_apply_status`,
`calendar_management_create_source_verified`,
`calendar_management_rename_plan_status`,
`calendar_management_rename_apply_status`,
`calendar_management_rename_title`,
`calendar_management_delete_plan_status`,
`calendar_management_delete_apply_status`,
`calendar_management_delete_mutation_applied`, and
`calendar_management_delete_absent_verified`,
`calendar_management_delete_empty_verified`. MCP keys are
`mcp_calendar_management_create_plan_status`,
`mcp_calendar_management_create_apply_status`,
`mcp_calendar_management_create_source_verified`,
`mcp_calendar_management_delete_plan_status`,
`mcp_calendar_management_delete_apply_status`, and
`mcp_calendar_management_delete_absent_verified`,
`mcp_calendar_management_delete_empty_verified`.

Source tests cover adapter validation, stale-token refusal, synthetic title
guards, read-only/subscribed/immutable create-source refusal, empty-calendar
refusal, mixed event/reminder calendar delete refusal, delete absence proof,
CLI routing, MCP wrapper routing, Swift helper
typecheck, runtime verifier receipts, surface-contract audit coverage, and
mutation/write-design audit coverage.

## Audit Anchors

- Calendar synthetic `LAD-TEST-*` calendar create/rename/delete apply.
- `calendar_plan_calendar_change` is plan-only/read-only.
- `calendar_apply_calendar_change` is destructive write and approval-gated.
- Create uses one exact source `calendar:calendar:v1:` handle, not a raw source
  identifier.
- Create refuses subscribed, birthday-backed, immutable, or read-only source
  calendars.
- Rename requires one exact `calendar:calendar:v1:` handle.
- Delete requires one exact `calendar:calendar:v1:` handle.
- delete-calendar targets one exact synthetic event-only calendar.
- Delete returns `calendar_absent_verified` after apply.
- Raw EventKit source/calendar identifiers are not returned.

## Still Out Of Scope

- Real/non-synthetic calendar create, rename, or delete.
- Calendar account/source management.
- Default calendar mutation.
- Calendar delete outside the synthetic event-only bounded-empty gate.
- Calendar sharing, subscriptions, attendees, and invitations.
- Calendar color changes.
- Calendar geofence/email/procedure alarm broadening outside existing event
  gates.
