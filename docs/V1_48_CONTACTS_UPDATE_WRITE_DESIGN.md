# v1.48 Contacts Scalar Update Write Design

Date: 2026-06-17
Status: Apply-capable implementation.

This v1.48 document covers the original scalar name/organization subset. Exact email/phone/URL method-array replacement is governed separately by `docs/V1_69_CONTACTS_METHOD_UPDATE_WRITE_DESIGN.md`.

Approved write tools: `local-apple-data contacts apply` and `contacts_apply_change`.

This document approves one additional Contacts operation: update scalar name and organization fields for one exact existing contact selected by an opaque `contacts:contact:v1:` handle. It reuses the existing Contacts `plan` / `apply` CLI and `contacts_plan_change` / `contacts_apply_change` MCP tools.

## Scope

Approved operation: `update`.

Allowed fields:

- `given_name`
- `family_name`
- `organization_name`
- `department_name`
- `job_title`
- `nickname`

Still blocked:

- Contact delete outside the separate exact-contact delete gate, merge, move, group membership, notes, image data, postal addresses, birthdays, dates, relationships, social profiles, instant messaging addresses, method-array replacement outside the v1.69 email/phone/URL gate, custom labels beyond the existing create gate, and bulk operations.
- Raw Contacts identifiers or container identifiers as user inputs.
- Direct Contacts database writes.

## Plan

`contacts plan --operation update` and `contacts_plan_change(operation="update")` are non-mutating. They require:

- Exact opaque `contacts:contact:v1:` handle from Contacts search/detail flow.
- `expected_current_sha256` from exact `contacts get` / `contacts_get` output field `update_safe_sha256`.
- At least one replacement scalar field.

Planning resolves the handle through Contacts.framework, fetches only scalar update-state fields for the exact target, computes the current scalar update-state hash, refuses stale state, preserves omitted scalar fields, refuses no-op updates, and returns a bounded preview. The preview must not return raw Contacts identifiers, container identifiers, notes, image data, postal addresses, birthday data, relation data, social profiles, instant message addresses, method-array values outside the v1.69 gate, or raw framework errors.

## Apply

`contacts apply --operation update` and `contacts_apply_change(operation="update")` require:

- Same exact handle, expected current SHA-256, and replacement scalar fields as the approved plan.
- Matching `contacts-apply:v1:<approval_fingerprint>` approval token.
- Explicit confirmation.

Apply recomputes the plan, re-resolves the exact handle, rechecks the update-safe scalar state immediately before helper execution, sends the raw Contacts identifier only to the local Swift helper, and the helper rechecks current scalar state again before calling Contacts.framework `CNSaveRequest.update`. Success requires read-back through Contacts.framework.

## Implementation

- Python owns handle validation, preview shaping, `update_safe_sha256`, approval-token verification, stale-state refusal, privacy-safe JSON, and tests.
- Swift owns Contacts.framework scalar-state fetch, current-state recheck, `CNMutableContact` scalar assignment, `CNSaveRequest.update`, and read-back.
- The helper never updates notes, images, postal addresses, birthday/date fields, relationships, social profiles, instant message addresses, groups, containers, or raw database state.

## Synthetic Tests Required

- Plan success for exact handle plus matching `update_safe_sha256`.
- Invalid handle and missing/invalid/stale hash refusal.
- No-op refusal.
- Unsupported array replacement outside the v1.69 email/phone/URL gate refusal.
- Apply success with mocked Contacts.framework helper and read-back.
- Stale state refusal before apply.
- CLI and MCP wrapper coverage.
- Runtime verifier coverage for update plan/apply/stale refusal.
- Mutation/write-design/release gates updated.
- Redaction scan coverage.

This document allows Contacts create-contact and exact-contact scalar update apply. Exact-contact email/phone/URL method-array update is governed separately by `docs/V1_69_CONTACTS_METHOD_UPDATE_WRITE_DESIGN.md`. Exact-contact delete is governed separately by `docs/V1_49_CONTACTS_DELETE_WRITE_DESIGN.md`. Contacts merge, move/container management, group membership, notes, image data, postal addresses, birthdays, dates, relationships, social profiles, instant messaging addresses, method-array replacement outside the v1.69 gate, and bulk operations remain blocked.
