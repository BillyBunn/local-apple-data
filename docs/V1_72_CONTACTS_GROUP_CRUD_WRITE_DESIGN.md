# v1.72 Contacts Group CRUD Write Design

Status: Apply-capable implementation.

This release adds exact Contacts group create, rename, and delete through the existing Contacts plan/apply gate. It also adds read-only Contacts container selection so contact and group creates can target an exact `contacts:container:v1:` handle when needed.

Approved write tools: `local-apple-data contacts apply` and `contacts_apply_change`.

New read tools:

- CLI: `contacts containers`
- CLI: `contacts container`
- MCP: `contacts_search_containers`
- MCP: `contacts_get_container`

No new apply tool names are exposed. `contacts plan` / `contacts_plan_change` and `contacts apply` / `contacts_apply_change` now cover `create_group`, `rename_group`, and `delete_group`.

## Source Review

Official Apple Contacts.framework headers and local SDK typecheck confirm the public API supports these operations:

- `CNContactStore.containers(matching:)` reads Contacts containers.
- `CNContainer.identifier`, `CNContainer.name`, and `CNContainer.type` provide bounded container metadata.
- `CNMutableGroup` exposes mutable group names.
- `CNSaveRequest.add(_:toContainerWithIdentifier:)` creates a group in the default or selected container.
- `CNSaveRequest.update(_:)` renames an exact group.
- `CNSaveRequest.delete(_:)` deletes an exact group without deleting its contacts.
- `CNGroup.predicateForGroupsInContainer(withIdentifier:)` allows same-container duplicate-name checks.

No private Contacts database writes, raw identifiers, keychain access, iCloud.com, browser sessions, or network APIs are used.

## Approved Operations

This release approves:

- exact group create
- exact group rename
- exact group delete
- exact container-targeted contact create

Group create accepts a bounded `group_name` and optional exact `contacts:container:v1:` handle plus `container_safe_sha256`. Planning binds the selected container state when a container handle is provided. Apply re-resolves the container, rejects stale container state, rejects duplicate group names within the selected container, calls Contacts.framework, and returns metadata-only group read-back.

Group rename is limited to one exact `contacts:group:v1:` handle with `group_safe_sha256` and a bounded new `group_name`. Apply re-resolves the exact group, rejects stale group state, calls `CNSaveRequest.update(_:)`, and returns metadata-only group read-back.

Group delete is limited to one exact `contacts:group:v1:` handle with `group_safe_sha256`. Apply re-resolves the exact group, rejects stale group state, calls `CNSaveRequest.delete(_:)`, and returns absence proof with `verified_absent:true` and `contacts_deleted:false`.

Contact create may target the default Contacts container or one exact `contacts:container:v1:` handle. Exact container targeting binds `container_safe_sha256` into the plan fingerprint and rechecks it before Contacts.framework apply.

Batch remains limited to approved existing-contact operations. Group create, rename, and delete are not allowed inside batch.

## Privacy Contract

No raw Contacts identifiers are returned. Public outputs use opaque `contacts:contact:v1:`, `contacts:group:v1:`, and `contacts:container:v1:` handles only.

Contacts container search returns only container name/type metadata plus an opaque handle. Exact container detail returns `container_safe_sha256`; it does not return raw container identifiers or account identifiers.

Contacts group delete removes only the group object. It does not delete member contacts and reports `contacts_deleted:false`.

Broad in-chat Contacts dumps remain blocked. The backup export path remains the only broad contact-data export and writes only to the caller-selected local archive directory.

## Still Blocked

This release still does not approve broad contact dumps in chat, raw identifier input, direct database writes, duplicate merge automation, or complete Contacts management.

Custom labels remain bounded local labels. Contact image retrieval returns metadata only; image bytes are never returned inline.

## Required Tests

- Synthetic adapter tests for container search/detail and group create/rename/delete plan/apply.
- CLI forwarding tests for container tools and group create planning.
- MCP forwarding tests for container tools and group create planning.
- Runtime verifier proves container search/detail plus group create, rename, and delete plan/apply.
- Mutation, write-design, surface-contract, redaction, release-readiness, cross-agent sync, and artifact hygiene audits pass before install is accepted.

This document allows Contacts exact group create/rename/delete and exact container-targeted create apply only through the approved gates.
