# v1.69 Contacts Method Update Write Design

Date: 2026-06-23
Status: Apply-capable implementation.

## Approved Tools

Approved write tools: `local-apple-data contacts apply` and `contacts_apply_change`.

`local-apple-data contacts plan` and `contacts_plan_change` remain non-mutating plan tools for create, exact-contact update, and exact-contact delete previews.

No other mutating CLI or MCP tools are approved or exposed by this document.

## Source Review

Official Apple Contacts.framework documentation and the local macOS SDK headers show that `CNMutableContact` exposes mutable `emailAddresses`, `phoneNumbers`, and `urlAddresses` arrays, and that `CNSaveRequest.update(_:)` / `updateContact:` updates an existing contact through Contacts.framework.

The implementation still uses Contacts.framework only. It does not use raw Contacts database writes, browser sessions, keychain credentials, iCloud.com, private APIs, or network services.

## Scope

This document approves one additional Contacts update surface inside the existing exact-contact update operation:

- update email address arrays for one exact existing contact
- update phone number arrays for one exact existing contact
- update URL address arrays for one exact existing contact

The update target must be one opaque `contacts:contact:v1:` handle returned by metadata or exact-detail flows. The caller must provide `expected_current_sha256` from exact `contacts get` / `contacts_get` output field `update_safe_sha256`.

Omitted method arrays are preserved. Provided method arrays replace the selected array. Explicit empty arrays clear the selected array.

This gate keeps the v1.48 scalar name and organization update behavior. It does not approve Contacts merge, move/container management, group membership, notes, image data, postal addresses, birthdays, dates, relationships, social profiles, instant messaging addresses, arbitrary custom labels beyond bounded local labels, raw framework identifiers, direct database writes, broad dumps, or bulk operations.

## Plan Contract

Planning resolves the handle through Contacts.framework, fetches only exact update-state fields for the target, computes the current update-state hash over scalar name/organization fields plus email/phone/URL method arrays, refuses stale state, preserves omitted fields, refuses no-op updates, and returns a bounded preview.

The preview must not return raw Contacts identifiers, container identifiers, notes, image data, postal addresses, birthday data, relation data, social profiles, instant message addresses, raw framework errors, approval fingerprints outside the plan payload, or approval tokens.

The plan response returns `mutation_applied:false`, `apply_available:true`, and an approval fingerprint/token that binds:

- operation
- exact opaque handle
- expected current SHA-256
- scalar replacements
- method-array replacements and explicit clears

## Apply Contract

Apply recomputes the plan from current local state and requires:

- the matching `contacts-apply:v1:<approval_fingerprint>` token
- explicit confirmation
- one exact `contacts:contact:v1:` handle
- matching `expected_current_sha256`
- at least one real scalar or method-array change

The Swift helper rechecks the expected current update-state before mutating. It converts the exact contact to `CNMutableContact`, applies scalar field changes from v1.48, conditionally replaces `emailAddresses`, `phoneNumbers`, and `urlAddresses` only when the corresponding replace flag is present, then saves through `CNSaveRequest.update(_:)`.

Read-back is through Contacts.framework exact detail/state retrieval. Apply returns `mutation_applied:true`, a bounded `read_back` object, and safe warning codes only.

## Synthetic Tests Required

- plan succeeds for replacing email, phone, and URL arrays
- plan succeeds for explicit empty-array clears
- plan preserves omitted method arrays
- plan refuses stale `update_safe_sha256`
- plan refuses no-op updates
- apply succeeds and reads back method-array replacements
- apply refuses missing confirmation or stale approval token
- CLI supports method replacement and clear flags without broad dumps
- MCP forwards exact method-array arguments without broad dumps
- runtime verifier proves the synthetic method replacement and clear flow
- write-design, mutation-gate, redaction, and plugin-artifact audits cover the new gate

## Boundary

This document allows Contacts create-contact, exact-contact name/organization update, exact-contact email/phone/URL method-array update, and exact-contact delete apply only through the approved gates. Every other Contacts mutation remains blocked until a separate design, explicit approval, synthetic tests, read-back verification, installed-cache verification, and redaction scan land.
