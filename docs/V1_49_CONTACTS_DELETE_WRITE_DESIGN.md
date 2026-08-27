# v1.49 Contacts Exact Delete Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data contacts apply` and `contacts_apply_change`.

This document approves one destructive Contacts operation: delete one exact existing contact selected by an opaque `contacts:contact:v1:` handle. It reuses the existing Contacts `plan` / `apply` CLI and `contacts_plan_change` / `contacts_apply_change` MCP tools.

## Source Review

- Local SDK header `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/Contacts.framework/Versions/A/Headers/CNSaveRequest.h` exposes public Contacts.framework `deleteContact:`.
- The Swift helper uses Contacts.framework only. It does not write Contacts databases, use private APIs, scrape UI, use iCloud.com, use browser sessions, or use Keychain material.
- Delete is hard deletion through Contacts.framework. It is not exposed as a broad cleanup, group edit, merge, or account/container management operation.

## Plan Contract

`contacts plan --operation delete` and `contacts_plan_change(operation="delete")` are non-mutating.

Required inputs:

- Exact opaque `contacts:contact:v1:` handle from Contacts search output.
- `expected_current_sha256` from exact `contacts get` / `contacts_get` output field `delete_safe_sha256`.

Planning resolves the handle through Contacts.framework exact detail, computes the current delete-safe full-detail state hash, refuses stale state, rejects extra scalar/email/phone/URL fields, and returns a destructive preview without raw Contacts identifiers or contact body/rich fields.

## Apply Contract

`contacts apply --operation delete` and `contacts_apply_change(operation="delete")` require:

- Matching approval token from the delete plan.
- `confirm_apply=true`.
- The same exact handle and `expected_current_sha256`.

Apply recomputes the plan, re-resolves the exact handle, rechecks the delete-safe full-detail state immediately before helper execution, sends the raw Contacts identifier only to the local Swift helper, and the helper rechecks current delete state again before calling Contacts.framework `CNSaveRequest.delete`. Read-back for delete is absence proof. Success requires `read_back.deleted:true` and `read_back.verified_absent:true`.

MCP tool annotations are static per tool. Because `contacts_apply_change` can now delete one exact selected contact, it is marked non-read-only, destructive and non-idempotent, and closed-world.

## Explicit Non-Goals

- No delete by search query, name, email, phone number, raw identifier, account, container, group, or broad match.
- No bulk delete.
- No Contacts merge, group membership, account/container management, notes/image/postal-address/birthday/relationship/social-profile mutation, or method-array mutation outside the v1.69 exact email/phone/URL update gate.
- No live personal-data mutation during tests.
- No database writes, private APIs, browser/keychain/network paths, or UI scraping.

## Synthetic Tests Required

- Preview requires exact handle and `expected_current_sha256`.
- Preview rejects stale hashes and extra delete fields.
- Preview uses the exact-detail helper path so `delete_safe_sha256` binds scalar fields, detail counters, and bounded exact-detail payloads.
- Apply requires explicit confirmation and matching approval token.
- Apply rechecks current state and rejects drift.
- Apply calls the helper with exact contact binding and expected current state.
- Apply succeeds only with absence proof.
- Runtime synthetic smoke covers plan/apply/stale-state delete.
- Mutation, write-design, release-readiness, surface-contract, redaction, public-release, installed-cache, and cross-agent gates remain green.

This release allows Contacts create-contact, exact-contact name/organization/email/phone/URL update, and exact-contact delete apply only.
