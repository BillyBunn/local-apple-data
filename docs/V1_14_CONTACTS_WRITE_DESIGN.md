# v1.14 Contacts Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data contacts apply` and `contacts_apply_change`.

No other mutating CLI or MCP tools are approved or exposed by this document. The current implementation also exposes `local-apple-data contacts plan` and `contacts_plan_change`; those tools validate and preview future changes without writing Contacts data.

This document defines the first Contacts write lane: create one contact in the default Contacts container through Contacts.framework, with preview as the default behavior and independent read_back verification after apply.

## Scope

Candidate operation:

- Create one contact with bounded name, organization, department, job title, nickname, email, phone, and URL fields.

Out of scope:

- Contact update, delete, merge, move, group membership, postal addresses, birthdays, dates, relationships, social profiles, instant messaging addresses, notes, image data, custom labels beyond bounded local labels, and bulk operations.
- Raw Contacts identifiers or container identifiers as user inputs.
- Mutations through iCloud.com, browser sessions, keychain credentials, private iCloud APIs, OAuth, IMAP, or external connectors.

## Tool Contract

Every future Contacts write operation must keep the same three-step shape:

- `preview`: validate input and return the planned change without touching Contacts.framework.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through the normal Contacts.framework-backed Contacts adapter.

The preview payload must include the operation, normalized contact type, bounded name and organization fields, bounded labeled email/phone/URL values, warning codes, and a deterministic idempotency key. It must not include raw Contacts identifiers, container identifiers, account identifiers, unrelated contact content, notes, image data, or framework exception text.

The apply payload must require an approval token or equivalent explicit approval artifact generated from the preview. The token must bind the operation, normalized contact type, normalized fields, labeled values, and idempotency key so an agent cannot apply a different mutation with a stale preview.

The read_back payload must return Contacts.framework contact details through the same bounded public fields used by `contacts_get`. It must not trust the write call alone.

## Current Tools

Implemented preview tools:

- CLI: `local-apple-data contacts plan`
- MCP: `contacts_plan_change`

These tools:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Accept only `create`.
- Require `contact_type` to be `person` or `organization`.
- Require person contacts to include `given_name` or `family_name`.
- Require organization contacts to include `organization_name`.
- Cap email, phone, and URL lists at five entries each.
- Return a deterministic `contacts-plan:v1:` idempotency key.
- Return an approval fingerprint for approval token binding.
- Do not call Contacts.framework, read Contacts data, or mutate Contacts data.

Implemented apply tools:

- CLI: `local-apple-data contacts apply`
- MCP: `contacts_apply_change`

These tools:

- Return `mode: "apply"`.
- Require a matching `contacts-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Use Contacts.framework to create one contact in the default container.
- Treat an existing contact with matching approved fields as `already_applied`.
- Return `mutation_applied:true` only after Contacts.framework save succeeds and read_back data is available.
- Use non-read-only, non-destructive, idempotent, closed-world MCP annotations.

## Implementation Choice

Use the existing Swift Contacts.framework helper path for Contacts writes:

- Swift owns Contacts.framework calls, permission checks, create/save calls, idempotency matching, and framework error normalization.
- Python owns CLI/MCP request validation, approval-token verification, logging, redaction, and JSON response shape.
- The MCP server stays stdio and local-only.

Contacts.framework is the right boundary for Contacts write calls because it is native, typed, permission-aware, and already required for Contacts reads. Python remains the right boundary for the plugin because the current CLI, tests, redaction scanners, release gates, and MCP server already wrap narrow helper calls cheaply.

## Data Model

Required create input:

- `operation`: `create`.
- `contact_type`: `person` or `organization`.
- `given_name` or `family_name` for person contacts.
- `organization_name` for organization contacts.

Optional create input:

- `organization_name`, `department_name`, `job_title`, and `nickname`.
- `email_addresses`, `phone_numbers`, and `url_addresses` as bounded labeled values.

All inputs are bounded. Contact notes, image data, postal addresses, birthdays, relationships, social profiles, instant messages, group membership, update, delete, and merge behavior are not accepted in this tranche.

## Approval Gate

Before any additional apply-capable Contacts tool is exposed:

- `docs/MUTATION_GATES.md` must name the approved operation.
- `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
- `scripts/audit_mutation_gates.py` must allow only the exact approved CLI and MCP names.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `contacts_plan_change` remains read-only; `contacts_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin manifest must describe the new state consistently.

## Idempotency

The apply path must be retry-safe:

- Create uses a deterministic idempotency key derived from the normalized contact type, bounded fields, labeled values, and approval token.
- The Swift helper treats an existing contact with matching approved fields and labeled values as `already_applied`.
- Existing partial or different contacts do not satisfy idempotency.

No implementation may create durable personal-content caches to solve idempotency. Any local operation ledger must store only opaque operation IDs, warning codes, timestamps, and hashes of normalized approved fields.

## Logging And Redaction

The redaction requirement applies to previews, applies, runtime smoke, tests, and release receipts.

Logs may include:

- Tool name.
- Status.
- Warning code.
- Counts.
- Duration.

Logs must not include:

- Contact names.
- Organization names.
- Email addresses.
- Phone numbers.
- URLs.
- Raw Contacts identifiers.
- Account or container identifiers.
- Approval tokens or fingerprints.
- Framework exception text.

## Synthetic Tests Required

Before exposure, the Contacts write implementation must add:

- Preview success tests for create.
- Preview validation tests for missing required identity, invalid contact type, oversized fields, and too many labeled values.
- Apply/read_back success tests using mocked Contacts.framework helper responses.
- Missing-confirmation and invalid-token tests.
- Contacts authorization-denied tests.
- Idempotency tests for retry after success.
- Redaction tests proving logs do not contain names, organizations, email addresses, phone numbers, URLs, approval fingerprints, tokens, raw Contacts identifiers, or raw exceptions.
- MCP annotation tests proving write tools are not marked read-only.

## Current Release Gate

The current release allows only this Contacts create-contact apply surface. Contacts update, delete, merge, move, group membership, postal addresses, birthdays, dates, relationships, social profiles, instant messaging addresses, notes, image data, custom labels beyond bounded local labels, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.
