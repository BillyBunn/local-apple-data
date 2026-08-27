# v1.71 Contacts Rich Update Group Batch Design

Status: Apply-capable implementation.

This release expands Contacts write coverage without changing the core safety model: local-only, metadata-first, exact opaque handles, plan-token approval, explicit confirmation, synthetic fixtures only, and no raw Contacts identifiers in public output.

Approved write tools: `local-apple-data contacts apply` and `contacts_apply_change`.

New read tools:

- CLI: `contacts groups`
- CLI: `contacts group`
- MCP: `contacts_search_groups`
- MCP: `contacts_get_group`

No new apply tool names are exposed. `contacts plan` / `contacts_plan_change` and `contacts apply` / `contacts_apply_change` now cover the additional operations below.

## Source Review

Official Apple Contacts.framework headers and local SDK typecheck confirm the public API supports these operations:

- `CNMutableContact` exposes mutable `postalAddresses`, `birthday`, `dates`, `socialProfiles`, `instantMessageAddresses`, `contactRelations`, `note`, and `imageData`.
- `CNSaveRequest.update(_:)` applies selected contact edits.
- `CNSaveRequest.addMember(_:to:)` and `CNSaveRequest.removeMember(_:from:)` update Contacts group membership.
- `CNContactStore.groups(matching:)` and `CNContact.predicateForContactsInGroup(withIdentifier:)` allow group lookup and member-count verification.

No private Contacts database writes, raw identifiers, keychain access, iCloud.com, browser sessions, or network APIs are used.

## Approved Operations

This release approves:

- exact scalar/method/rich-field/image update
- exact note append/set/clear/merge
- exact group membership
- exact batch over approved existing-contact operations

Rich update is limited to one exact `contacts:contact:v1:` handle with `update_safe_sha256`. Omitted fields preserve current values. Provided arrays replace selected arrays. Empty arrays clear selected arrays. Image set reads a caller-selected local image file only to compute size/hash and apply `imageData`; public output never returns image bytes or source paths.

Note set/clear/merge is limited to one exact contact handle with `note_safe_sha256`. Apply returns hash-only note state. Merge never returns the existing note text in preview; it only returns the caller-supplied merge text and resulting hash/char metadata.

Group membership is limited to one exact contact handle and one exact `contacts:group:v1:` handle. Planning binds both the contact `update_safe_sha256` and group `group_safe_sha256`. Apply rechecks both before calling `CNSaveRequest.addMember(_:to:)` or `CNSaveRequest.removeMember(_:from:)`, then returns metadata-only group read-back.

Batch items are capped at 10. Batch allows only approved existing-contact operations, rejects nested batch and create, binds each child approval fingerprint into one batch approval fingerprint, and stops on first failed item. If earlier items applied before a later failure, apply returns partial status with applied count and safe child read-back metadata.

## Privacy Contract

No raw Contacts identifiers are returned. Public outputs use opaque `contacts:contact:v1:` and `contacts:group:v1:` handles only.

Contacts group search returns only group name, opaque handle, and member count. Exact group detail returns `group_safe_sha256`; it does not return member IDs.

Broad in-chat Contacts dumps remain blocked. The backup export path remains the only broad contact-data export and writes only to the caller-selected local archive directory.

## Still Blocked

This release still does not approve broad contact dumps in chat, raw identifier input, direct database writes, duplicate merge automation, or complete Contacts management. Exact group create/rename/delete is governed separately by `docs/V1_72_CONTACTS_GROUP_CRUD_WRITE_DESIGN.md`.

Custom labels remain bounded local labels. Contact image retrieval returns metadata only; image bytes are never returned inline.

## Required Tests

- Synthetic adapter tests for rich update, image set/clear, note set/clear/merge, group search/detail/membership, and batch plan/apply.
- CLI forwarding tests for rich JSON/image fields, group tools, group membership, note set, and batch items.
- MCP forwarding tests for rich fields, group tools, group membership, note set, and batch items.
- Runtime verifier proves rich update, set-note, group membership, and batch plan/apply.
- Mutation, write-design, surface-contract, redaction, release-readiness, cross-agent sync, and artifact hygiene audits pass before install is accepted.

This document allows Contacts rich update, exact note set/clear/merge, exact group membership, and exact batch apply only through the approved gates.
