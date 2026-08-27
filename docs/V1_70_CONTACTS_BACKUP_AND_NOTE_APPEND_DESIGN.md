Status: Apply-capable implementation.

# v1.70 Contacts Backup And Note Append Design

This release fixes the Contacts cleanup Phase 0 blocker by adding intentional Contacts count/export tools, and adds one narrow Phase 2 mutation: exact note append on one selected contact.

Approved read-only tools:

- CLI: `local-apple-data contacts count`
- CLI: `local-apple-data contacts export`
- MCP: `contacts_count`
- MCP: `contacts_export_archive`

Approved write tools: `local-apple-data contacts apply` and `contacts_apply_change`.

No new apply tool names are approved. `contacts plan` / `contacts_plan_change` support `operation:append_note` as a non-mutating preview. `contacts apply` / `contacts_apply_change` support the matching approved exact note append only after matching approval token and explicit confirmation.

## Source Review

Official Apple Contacts.framework documentation and the local macOS SDK headers show that `CNContactStore` supports enumerating contacts with `enumerateContacts(with:usingBlock:)`, `CNContactVCardSerialization` supports vCard serialization with `descriptorForRequiredKeys()` and `data(with:)`, `CNMutableContact` exposes a mutable `note` field, and `CNSaveRequest.update(_:)` applies a contact update.

## Read-Only Backup Contract

`contacts count` / `contacts_count` enumerate local unified Contacts records through Contacts.framework and return only:

- `live_count`
- `count_complete`
- `max_contacts`
- authorization status
- safe warning codes

They do not return names, emails, phone numbers, note text, raw Contacts identifiers, or raw database rows.

`contacts export` / `contacts_export_archive` write three files under a caller-selected output directory:

- `<prefix>.vcf`
- `<prefix>.json`
- `<prefix>-manifest.json`

The tool returns only archive metadata: live count, JSON contact count, vCard contact count, `counts_match`, `archive_verified`, file paths, byte counts, SHA-256 hashes, and safe warning codes. The tool does not echo contact data in the response. The JSON and vCard files are the caller-requested backup artifact and may contain contact details and note text when Contacts.framework permits note access.

If the live count, JSON count, and vCard count do not match, or if enumeration truncates at `max_contacts`, the archive response is not verified and returns a safe warning. A cleanup workflow must not proceed past Phase 0 unless `archive_verified:true` and `counts_match:true`.

## Note Append Plan

`contacts plan --operation append-note` and `contacts_plan_change(operation="append_note")` require:

- Exact opaque `contacts:contact:v1:` handle.
- `expected_current_sha256` from exact `contacts get` / `contacts_get` output field `note_safe_sha256`.
- Exact `note_text` to append.

Planning resolves the handle through Contacts.framework, reads the current note internally, computes the current note SHA-256, refuses stale state, and returns a preview with:

- `effect: append_contact_note`
- `append_text`
- `append_chars`
- `append_preview_text`
- `resulting_note_chars`
- `resulting_note_sha256`
- matching `contacts-apply:v1:<approval_fingerprint>` token format

The current existing note text is never returned by the plan. The proposed append text is returned because it is the exact user-approved mutation payload.

## Note Append Apply

`contacts apply --operation append-note` and `contacts_apply_change(operation="append_note")` require:

- The same exact handle.
- The same `expected_current_sha256`.
- The same `note_text`.
- Matching `contacts-apply:v1:<approval_fingerprint>` approval token.
- `confirm_apply:true`.

Apply recomputes the plan before mutation, verifies the approval token, re-reads the current note through Contacts.framework, refuses stale state, appends the exact approved text to the existing note, applies through Contacts.framework `CNSaveRequest.update`, and then reads back note state.

The apply read-back returns hash-only note state: handle, `note_status`, `note_chars`, `note_safe_sha256`, and appended character count. It does not return the existing or resulting full note text.

## Superseded Limits

This v1.70 document describes the older backup/count/export and exact note-append gate. v1.71 separately approves exact note set/clear/merge, exact rich-field/image update, exact group membership, and capped exact batch through `docs/V1_71_CONTACTS_RICH_UPDATE_GROUP_BATCH_DESIGN.md`.

Contact group create/rename/delete, duplicate merge automation, custom label expansion, broad contact mutation, raw identifier input, and direct database writes remain blocked.

Contacts count/export do not authorize broad in-chat dumps of contact data. Export content is written only to the explicit local backup directory selected by the caller.

## Synthetic Tests Required

- Adapter tests cover count metadata-only response, export file creation with count matching, append-note plan preview, append-note stale hash refusal, and append-note apply hash-only read-back.
- CLI tests cover count/export argument forwarding and append-note exact text forwarding.
- MCP wrapper tests cover count/export forwarding and append-note plan/apply exact binding.
- Runtime verifier proves synthetic count/export and append-note plan/apply without live Contacts mutation.

This document allows Contacts count/export read-only backup and exact-contact note append apply only through the approved gates.
