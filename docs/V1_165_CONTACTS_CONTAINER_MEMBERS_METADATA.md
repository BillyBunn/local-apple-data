# v1.165 Contacts Selected-Container Member Metadata

Status: implemented.

## Surface

- MCP: `contacts_list_container_members(handle, limit=20)`
- CLI: `local-apple-data contacts container-members --json --handle <contacts:container:v1:...> [--limit 20]`
- Adapter: `list_contact_container_members()`
- Helper: `contact_container_members`

The command returns capped contact metadata for one exact Contacts container:
opaque `contacts:contact:v1:` handles, display names, organization/job
metadata, count/presence metadata, and the selected container's safe metadata.
It returns no raw container ID, raw contact IDs, email/phone/postal/URL values,
note text, image bytes, or contact detail values.

## Safety Rules

- Requires one opaque `contacts:container:v1:` handle returned by
  `contacts containers` / `contacts_search_containers`.
- Resolves the container through the existing signed-handle verifier before any
  helper call.
- Uses the public Contacts.framework
  `CNContact.predicateForContactsInContainer(withIdentifier:)` API through the
  existing local helper.
- Caps output at 50 contacts.
- Returns metadata only through the existing `_contact_metadata` redaction
  path.
- Does not create a mutation target from raw container names or raw Contacts
  identifiers.
- No Gmail, iCloud.com, browser, keychain, private API, network, direct DB, or
  broad Contacts dump fallback.

## Regression Proof

- Adapter tests prove exact container-handle gating, metadata-only output, raw
  contact-ID stripping, raw contact-detail stripping, degraded response shape,
  and adapter-side cap enforcement when the helper over-returns.
- CLI parser/surface audits include `contacts container-members`.
- MCP tests cover `contacts_list_container_members`.
- Runtime verifier expects `tool_count:135` and proves direct container-member
  status, one returned opaque contact handle, no raw helper contact ID, and no
  helper-provided detail value.
- Surface and mutation-gate audits include the new read-only CLI and MCP tool.

## Remaining Gaps

- Broad Contacts dumps, raw identifier input, contact detail values outside
  exact selected contact detail, note text in chat output, image bytes,
  duplicate merge automation, custom labels beyond bounded local labels, direct
  database writes, and complete Contacts management remain blocked.
