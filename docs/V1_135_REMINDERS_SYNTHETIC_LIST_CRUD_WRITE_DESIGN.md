# v1.135 Reminders Synthetic List CRUD Write Design

Status: Superseded by `docs/V1_155_REMINDERS_LIST_CRUD_WRITE_DESIGN.md`.

This historical gate first approved `reminders apply-list` and
`reminders_apply_list_change` for fixture-safe Reminders list create, rename,
and empty-list delete. The current release is governed by v1.155, which
allows ordinary exact Reminders list create, rename, and empty-list delete
through the same plan/apply/read-back tools.

The durable safety rules carried forward:

- Exact opaque `reminders:list:eventkit:v1:` source list handle for create.
- Exact opaque `reminders:list:eventkit:v1:` target list handle for rename/delete.
- Source or target safe-hash binding in the approval fingerprint.
- Duplicate-title refusal inside the selected source.
- Writable, non-subscribed, non-immutable, reminder-only target checks.
- Empty-list proof for rename/delete.
- `reminders-apply:v1:<approval_fingerprint>` plus `confirm_apply:true`.
- Public EventKit only: `EKCalendar(for: .reminder, eventStore:)`,
  `EKEventStore.saveCalendar(_:commit:)`, `EKEventStore.removeCalendar(_:commit:)`,
  and public reminder-count fetch predicates.
- No Reminders database writes, Reminders UI automation, iCloud.com, private
  iCloud APIs, raw EventKit identifier input, browser/keychain path, account or
  source management, sharing mutation, cross-source management, non-empty list
  delete, reminder migration, or bulk list mutation.
