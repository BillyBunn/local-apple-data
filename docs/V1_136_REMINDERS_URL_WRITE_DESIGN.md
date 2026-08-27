# v1.136 Reminders URL Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.

This gate approves exact Reminder URL update and clear for one exact local EventKit Reminder after plan-token and explicit-confirmation checks. It does not approve broad Reminder URL search, URL retrieval, attachment mutation, image mutation, alarm mutation, sharing mutation, or bulk URL mutation.

No broad Reminder URL search, URL retrieval, attachment mutation, image mutation, alarm mutation, sharing mutation, or bulk URL mutation is approved.

## Scope

Allowed:

- `local-apple-data reminders plan --operation update-url`
- `reminders_plan_change(operation="update_url")`
- `local-apple-data reminders apply --operation update-url`
- `reminders_apply_change(operation="update_url")`
- `local-apple-data reminders plan --operation clear-url`
- `reminders_plan_change(operation="clear_url")`
- `local-apple-data reminders apply --operation clear-url`
- `reminders_apply_change(operation="clear_url")`

Required inputs:

- Exact opaque `reminders:reminder:eventkit:v1:` handle.
- `expected_title` from a recent read-only result.
- `expected_completed` from a recent read-only result.
- `expected_url_present` from a recent exact read or apply proof.
- `expected_url_sha256` when `expected_url_present:true`.
- Replacement `url` only for `update_url`.
- Matching `reminders-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply:true`.

Allowed schemes are `http`, `https`, `mailto`, and `tel`.

Out of scope:

- Raw EventKit identifiers.
- Raw Reminder URL return.
- Broad Reminder URL search.
- URL retrieval outside exact hash-only proof.
- Non-allow-listed schemes.
- URL credentials, whitespace/control characters, or URLs over 2048 characters.
- Bulk URL mutation.
- Reminder attachment, image, alarm, sharing, or rich-content mutation.
- Any UI automation, browser/iCloud path, keychain path, external connector, or network service.

## Source Review

The implementation uses public EventKit APIs:

- `EKReminder` inherits from `EKCalendarItem`.
- `EKCalendarItem.url` is a public mutable `URL?` property.
- `EKEventStore.save(_:commit:)` persists the changed Reminder.

Current proof:

- Apple docs: `https://developer.apple.com/documentation/eventkit/ekreminder`
- Apple docs: `https://developer.apple.com/documentation/eventkit/ekcalendaritem/url`
- Local SDK: `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/EventKit.framework/Headers/EKReminder.h`
- Local SDK: `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/EventKit.framework/Headers/EKCalendarItem.h`

No Reminders database writes, Reminders UI automation, iCloud.com, private iCloud APIs, raw EventKit identifier input, or browser/keychain path is used.

## Planning Contract

Planning is non-mutating.

`update_url` planning requires:

- Exact Reminder handle.
- Expected title.
- Exact `expected_url_present`.
- Exact `expected_url_sha256` when a current URL is present.
- Replacement URL with an allowed scheme.
- No raw URL in public preview.
- Hash-only proposed URL proof through `url_safe_sha256`.
- Public `url_scheme` and safe `url_domain` only.

`clear_url` planning requires:

- Exact Reminder handle.
- Expected title.
- `expected_url_present:true`.
- Exact `expected_url_sha256`.
- No replacement URL.
- Public `url_clear_requested:true` only.

Both operations include URL state in the approval fingerprint so stale or swapped approvals cannot mutate a different URL state.

## Apply Contract

Apply recomputes the plan, requires a matching approval token, requires explicit confirmation, resolves the Reminder through EventKit, and rechecks the expected URL state before mutation.

The Swift EventKit helper must recheck title, completion state, URL presence, and URL hash before mutation. It must set only `reminder.url` for `update_url`, set `reminder.url = nil` for `clear_url`, and save through EventKit.

Read-back for update is hash-only URL proof.

Successful `update_url` requires:

- `mutation_applied:true`
- `operation:"update_url"`
- `read_back.url_present:true`
- `read_back.url_safe_sha256` equal to the approved proposed URL hash.
- `read_back.url_verified:true`
- `url_raw_returned:false`

Read-back for clear is absence proof.

Successful `clear_url` requires:

- `mutation_applied:true`
- `operation:"clear_url"`
- `read_back.url_present:false`
- `read_back.url_absent_verified:true`
- `url_raw_returned:false`

If EventKit save succeeds but read-back cannot prove the approved state, apply must return `apply_unknown` with `mutation_applied:true`.

No raw URL is returned in previews, read-back, warnings, logs, or runtime summaries.

## Idempotency

`update_url` is idempotent only while the current URL state still matches the approved expected URL state. A retry after a successful URL update requires a fresh plan unless the fresh expected URL state matches the current state and the proposed URL hash matches.

`clear_url` is idempotent only when the approved expected state was URL-present and apply can prove the URL is absent after the clear. A stale clear against an already-clear Reminder without the approved present-state binding is refused.

No durable personal-content operation ledger is added.

## Synthetic Tests Required

Required tests:

- Plan success for `update_url` with hash-only proposed URL proof and no raw URL return.
- Plan refusal for unsafe schemes, credentials, whitespace/control characters, non-ASCII characters, and overlong URLs.
- Plan success for `clear_url` only with `expected_url_present:true` and `expected_url_sha256`.
- Search metadata strips any helper-supplied `url_safe_sha256` and returns only `url_present`.
- Apply refusal before helper call when confirmation or approval token is missing.
- Apply refusal before helper call when current URL state is stale.
- Apply success for `update_url` with hash read-back proof and `url_raw_returned:false`.
- Apply success for `clear_url` with absence proof.
- Apply unknown when EventKit save reports success but URL read-back mismatches.
- CLI routing for `--url`, `--expected-url-present`, and `--expected-url-sha256`.
- MCP wrapper routing for `url`, `expected_url_present`, and `expected_url_sha256`.
- Runtime synthetic smoke for direct and MCP URL update plus direct URL clear.
- Redaction checks proving raw URLs are not returned.

## Current Release Gate

This release allows only exact-handle Reminder URL update and clear through the plan/apply/read-back gates above. Broad Reminder URL search, raw URL retrieval, non-ASCII or non-allow-listed URL schemes, attachment mutation, image mutation, alarm mutation, sharing mutation, rich-content mutation, and bulk URL mutation remain blocked.
