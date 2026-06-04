# Mutation Gates

The current plugin is read-only. Write tools are intentionally absent until each mutation class has a separate design, explicit user approval, synthetic tests, and independent read-back verification.

For sequencing and first-tranche candidates, see `docs/WRITE_TOOL_ROADMAP.md`. For the first Reminders write design gate and current preview-only planning tools, see `docs/V1_11_REMINDERS_WRITE_DESIGN.md`.

## Global Requirements

Every future mutating tool must satisfy all of these before exposure through CLI or MCP:

- Separate design doc for the specific surface and operation.
- Explicit user approval for the exact mutation class.
- Dry-run or preview mode that returns the planned change without applying it.
- Independent read-back after mutation.
- Idempotency story for retries and partial failures.
- Narrow input schema with no broad batch mutation by default.
- Stable warning/error codes with no raw paths, identifiers, stack traces, or personal content in logs.
- MCP annotations marking the tool as non-read-only and destructive when applicable.
- Tests using synthetic fixtures or mocked Apple framework helpers only.
- Redaction scan and runtime smoke passing before install.

The current `reminders plan` CLI command and `reminders_plan_change` MCP tool are not mutating tools. They return `mutation_applied:false`, `apply_available:false`, and approval metadata only.

## First Candidate Write Surfaces

| Surface | Candidate operations | Preferred API | Extra approval checks |
| --- | --- | --- | --- |
| Reminders | Create reminder, complete reminder, update due date | EventKit helper | Confirm target list, title, due date, and completion state before apply |
| Calendar | Create event, update event, delete event | EventKit helper | Confirm calendar, time zone, attendees excluded by default, and recurrence behavior |
| Notes | Create note, append to note | Notes.app automation or local app bridge | Confirm account/folder, exact note handle for append, and plain-text/HTML conversion |
| Mail | Create draft only | Mail.app automation | Confirm sender account, recipients, subject, and draft-only behavior; no send in plugin v1 |
| Contacts | Create/update contact | Contacts.framework helper | Confirm display name and changed fields; no contact notes/image data |
| Photos | None in first write phase | PhotoKit change requests later | Exact read-only asset export is implemented; edits/import/delete need a separate mutation design |
| Messages | None in first write phase | Messages.app automation later | Sending/editing must remain outside the plugin until identity/account confirmation is solved |
| Hide My Email | None | No approved local public API | Authoritative inventory or mutation requires a new source review and explicit approval |
| iCloud Drive | Create text file, append text file | Local filesystem | Confirm exact path by opaque parent handle; no overwrite/delete in first write phase |

## Default Refusals

Until a specific mutation gate is implemented and approved, the plugin must refuse:

- Sending mail or messages.
- Deleting, archiving, moving, or marking Mail/Messages.
- Creating, deleting, deactivating, or managing Hide My Email aliases.
- Deleting Calendar events, Contacts, Photos, Notes, Reminders, Voice Memos, or iCloud Drive files.
- Bulk mutation.
- Mutation through iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, OAuth, IMAP, or connector fallbacks.

## Verification Shape

A mutation tranche is not done until:

- The read-only tools still pass all existing tests.
- New preview/apply/read-back tests pass.
- `uv run python scripts/audit_mutation_gates.py` is updated for the approved tool names and passes.
- `uv run python scripts/audit_write_design_gates.py` is updated from design-only to approved-with-tests for the exact operation and passes.
- Runtime smoke proves the tool list annotations and refusal behavior.
- The skill, privacy model, threat model, testing doc, capability matrix, README, and plugin manifest all describe the new mutation state consistently.
- Installed cache and cross-agent sync verification pass.
