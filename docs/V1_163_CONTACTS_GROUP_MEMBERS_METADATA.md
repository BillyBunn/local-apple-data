# v1.163 Contacts Selected-Group Member Metadata

Status: implemented, synced, installed, and verified.

## Surface

- MCP: `contacts_list_group_members(handle, limit=20)`
- CLI: `local-apple-data contacts group-members --json --handle <contacts:group:v1:...> [--limit 20]`
- Adapter: `list_contact_group_members()`
- Helper: `contact_group_members`

The command returns capped contact metadata for one exact Contacts group:
opaque `contacts:contact:v1:` handles, display names, organization/job
metadata, count/presence metadata, and the selected group's safe metadata.
It returns no raw group ID, raw member IDs, email/phone/postal/URL values,
note text, image bytes, or contact detail values.

## Safety Rules

- Requires one opaque `contacts:group:v1:` handle returned by
  `contacts groups` / `contacts_search_groups`.
- Resolves the group through the existing signed-handle verifier before any
  helper call.
- Uses the public Contacts.framework
  `CNContact.predicateForContactsInGroup(withIdentifier:)` API through the
  existing local helper.
- Caps output at 50 contacts.
- Returns metadata only through the existing `_contact_metadata` redaction
  path.
- Does not create a mutation target from raw group names or raw Contacts
  identifiers.
- No Gmail, iCloud.com, browser, keychain, private API, network, direct DB, or
  broad Contacts dump fallback.

## Regression Proof

- Adapter tests prove exact group-handle gating, metadata-only output, raw
  member-ID stripping, raw contact-detail stripping, and degraded response
  shape.
- CLI tests cover `contacts group-members --json`.
- MCP tests cover `contacts_list_group_members`.
- Runtime verifier expects `tool_count:133` and proves direct group-member
  status, one returned opaque contact handle, no raw helper member ID, and no
  helper-provided detail value.
- Surface and mutation-gate audits include the new read-only CLI and MCP tool.

## Remaining Gaps

- Broad Contacts dumps, raw identifier input, contact detail values outside
  exact selected contact detail, note text in chat output, image bytes,
  duplicate merge automation, custom labels beyond bounded local labels, direct
  database writes, and complete Contacts management remain blocked.
