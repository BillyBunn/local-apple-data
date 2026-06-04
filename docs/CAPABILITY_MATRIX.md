# Capability Matrix

This matrix describes the current public surface and the intended approval gates for future expansion. The plugin is local-only and metadata-first. The only apply-capable mutation surface is Reminders apply.

For install instructions, see `docs/INSTALL.md`. For macOS support and permission behavior, see `docs/MACOS_SUPPORT.md`. For future write sequencing, see `docs/WRITE_TOOL_ROADMAP.md` and `docs/V1_11_REMINDERS_WRITE_DESIGN.md`.

| Surface | Local source | Search/list support | Exact detail support | Write support | Permissions | Current limits |
| --- | --- | --- | --- | --- | --- | --- |
| Mail | Mail.app local Envelope Index plus local `.emlx` files | Subject metadata with `content_status` hints | Plain text by `mail:message:v2:` handle | Not implemented | Full Disk Access may be required for local stores | No attachments, raw MIME, full headers, body search, account mutation, or network mail |
| Messages | Local Messages `chat.db` | Chat display-name metadata | Bounded transcript by `messages:chat:v1:` handle | Not implemented | Full Disk Access may be required | No participant identifiers, attachments, reactions, broad text search, send/edit/delete, or Messages.app automation |
| Hide My Email | Local Mail address metadata inference | Masked alias previews by specific substring | Full selected alias by `hide_my_email:alias:v1:` handle | Not implemented | Full Disk Access may be required for Mail store | Not authoritative iCloud inventory; no creation, deactivation, deletion, private iCloud APIs, browser sessions, or keychain access |
| Voice Memos | Voice Memos `CloudRecordings.db` plus local `.m4a` files | Title/filename metadata | Existing embedded transcript and caller-selected `.m4a` export by `voice_memos:recording:v1:` handle | Not implemented | Full Disk Access may be required | No generated transcription, broad transcript search, source recording paths, raw identifiers, or mutation |
| Notes | Local Notes SQLite plus exact Notes.app automation | Title/snippet metadata | Plain text by `notes:note:v2:` handle | Not implemented | Full Disk Access and Automation permission may be required | No attachments, locked/deleted notes, broad exports, raw database rows, or mutation |
| iCloud Drive | Local filesystem under iCloud Drive | Filename metadata | Supported text-file content by `icloud:file:v1:` handle | Not implemented | Local file access | No binary/document extraction, hidden files, symlinks, raw paths, broad content search, or mutation |
| Calendar | EventKit helper | Event title metadata | Event detail by `calendar:event:v1:` handle | Not implemented | Calendar permission | No broad dumps, attendees/URLs, raw EventKit IDs, or mutation |
| Reminders | EventKit helper plus legacy SQLite metadata | Title/due metadata | Notes by `reminders:reminder:eventkit:v1:` handle | Approved create, complete, and due-date apply after plan approval token and explicit confirmation | Reminders permission | EventKit exact handles only for notes and apply targets; no broad dumps, raw EventKit IDs, delete, bulk, list/account, URL, attachment, or rich-content mutation |
| Contacts | Contacts.framework helper | Name/organization metadata | Contact detail by `contacts:contact:v1:` handle | Not implemented | Contacts permission | No contact notes entitlement, image bytes, broad dumps, raw identifiers, or mutation |
| Photos | PhotoKit helper | Original-filename metadata | Asset/resource metadata and caller-selected asset export by `photos:asset:v1:` handle | Not implemented | Photos permission | No inline asset bytes, thumbnails, raw identifiers, broad dumps, network iCloud fetch, or mutation |

## Handle Policy

- Search/list tools return opaque handles only.
- Exact content/detail tools require handles returned by the corresponding metadata flow.
- Raw database row IDs, framework identifiers, file paths, recording identifiers, alias identifiers, mailbox refs, and fabricated handles must fail closed.
- Handles are local, signed, and not reusable credentials.

## Publication Requirements

Before a surface is described as supported in a public release:

- Synthetic unit tests cover search, exact-get, invalid handles, broad-query rejection, and degraded-store behavior.
- Runtime smoke covers the surface without touching live personal content.
- Privacy/threat/testing docs describe returned fields, forbidden fields, permission behavior, and non-goals.
- The MCP server, CLI, skill, manifest, and README agree on the surface.
- `scripts/audit_surface_contract.py` passes for the MCP tools, CLI parser, health summary, access requirements, and this matrix.
- `scripts/audit_write_design_gates.py` passes when a write design or write-support claim is present.
- Redaction scan passes.
