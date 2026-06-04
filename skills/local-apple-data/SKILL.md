---
name: local-apple-data
description: Use when a user asks Codex to search or inspect locally synced Mail.app mail, Messages chats, inferred Hide My Email aliases, Voice Memos, Apple Notes, Apple Calendar, Apple Contacts, Apple Photos, Apple Reminders, or iCloud Drive files on this Mac without the Gmail connector. The skill uses the local MCP server, stays metadata-first, retrieves or exports Mail, Messages, inferred Hide My Email, Voice Memos, Notes, Calendar, Contacts, Photos, Reminders, or iCloud Drive content/detail only by exact opaque handle, and allows only approved Reminders apply, iCloud Drive create-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create-note apply, Mail create-draft apply, or Photos import apply after plan-token confirmation.
---

# Local Apple Data

Use the `local-apple-data` MCP server for the user's locally synced Mail.app mail, Messages chats, inferred Hide My Email aliases, Voice Memos, Apple Notes, Apple Calendar, Apple Contacts, Apple Photos, Apple Reminders, and iCloud Drive files. Do not use the Gmail connector, Gmail API, IMAP, OAuth, app passwords, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, or network mail access for these workflows unless the user explicitly asks for those external paths.

## Workflow

1. Start with `apple_data_health` or `apple_data_doctor` if current local readiness has not been checked in this session.
2. Use narrow, user-requested searches only. Do not run broad dumps or empty searches.
3. Keep limits small unless the user asks for a larger result set.
4. Treat search results as local metadata that may include subjects, Messages chat display names, inferred Hide My Email alias previews, Voice Memo titles, note titles/snippets, calendar event titles, contact names/organizations, Photos filenames, iCloud Drive filenames, or reminder titles. Summarize only the minimum useful facts in chat.
5. Use exact opaque handles from search results for metadata fetches. Do not fabricate handles or retry old raw row-ID handles.
6. If the user asks for Mail message content and you are selecting from search results, prefer a result whose `content_status` is `available`. Treat `unavailable` or `unknown` as a reason to skip that handle or report that local content may not be retrievable.
7. Call `mail_get_content` only on an exact `mail:message:v2:` handle the user selected, provided, or approved from the metadata results. Keep `max_chars` bounded; use 4000 unless the user asks for a smaller limit, and never above 12000.
8. Call `messages_get_chat` only on an exact `messages:chat:v1:` handle the user selected, provided, or approved from Messages chat display-name metadata results. Keep `max_messages` and `max_chars` bounded.
9. Call `hide_my_email_get_alias` only on an exact `hide_my_email:alias:v1:` handle the user selected, provided, or approved from inferred Hide My Email metadata results. Treat it as inferred local Mail evidence, not authoritative iCloud inventory. Do not use iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, or network services for Hide My Email.
10. Call `voice_memos_get_recording` only on an exact `voice_memos:recording:v1:` handle the user selected, provided, or approved from Voice Memos title/filename metadata results. Keep `max_chars` bounded; use 4000 unless the user asks for a smaller limit, and never above 12000. This may return an existing Apple-generated transcript only; it does not return audio bytes or generate new transcription. Use `voice_memos_export_audio` only when the user asks to export the selected recording, and provide a caller-selected output directory.
11. Call `notes_get_content` only on an exact `notes:note:v2:` handle the user selected, provided, or approved from the metadata results. Keep `max_chars` bounded; use 4000 unless the user asks for a smaller limit, never above 12000, and follow `next_offset` when the user asks for a full long/imported note.
12. Call `icloud_drive_get_content` only on an exact `icloud:file:v1:` handle the user selected, provided, or approved from filename metadata results. Keep `max_chars` bounded; use 4000 unless the user asks for a smaller limit, and never above 12000.
13. Call `calendar_get_event` only on an exact `calendar:event:v1:` handle the user selected, provided, or approved from event-title metadata results. Keep `max_chars` bounded; use 4000 unless the user asks for a smaller limit, and never above 12000.
14. Call `contacts_get` only on an exact `contacts:contact:v1:` handle the user selected, provided, or approved from Contacts name/organization metadata results. Keep `max_chars` bounded; use 4000 unless the user asks for a smaller limit, and never above 12000.
15. Call `photos_get_asset` only on an exact `photos:asset:v1:` handle the user selected, provided, or approved from Photos original-filename metadata results. This returns asset/resource metadata only. Use `photos_export_asset` only when the user asks to export the selected asset, and provide a caller-selected output directory.
16. Call `reminders_get_content` only on an exact `reminders:reminder:eventkit:v1:` handle the user selected, provided, or approved from EventKit reminder-title metadata results. Keep `max_chars` bounded; use 4000 unless the user asks for a smaller limit, and never above 12000.
17. Call `reminders_plan_change` only when the user asks to plan a future Reminder create, complete, or due-date update. This is non-mutating: it returns `mutation_applied:false` and `apply_available:true`, does not call EventKit, and does not modify Reminders.
18. Call `reminders_apply_change` only after a matching Reminders plan, an exact `reminders-apply:v1:<approval_fingerprint>` approval token, explicit user approval for that exact operation, and operation-specific expected state.
19. Call `icloud_drive_plan_change` only when the user asks to plan a future iCloud Drive text-file create in a selected folder. This is non-mutating: it returns `mutation_applied:false` and `apply_available:true`, does not resolve the parent handle, and does not modify iCloud Drive.
20. Call `icloud_drive_apply_change` only after a matching iCloud Drive plan, an exact `icloud-drive-apply:v1:<approval_fingerprint>` approval token, explicit user approval for that exact operation, and the same parent handle, filename, and content text. It may only create one supported text-like file by exclusive create under the exact opaque parent folder handle.
21. Call `calendar_plan_change` only when the user asks to plan a future Calendar timed-event create in an explicit target calendar. This is non-mutating: it returns `mutation_applied:false` and `apply_available:true`, does not call EventKit, and does not modify Calendar data.
22. Call `calendar_apply_change` only after a matching Calendar plan, an exact `calendar-apply:v1:<approval_fingerprint>` approval token, explicit user approval for that exact operation, and the same calendar title, title, start date, end date, location, and notes. It may only create one timed event in the explicit target calendar.
23. Call `contacts_plan_change` only when the user asks to plan a future Contacts contact create with bounded person or organization fields. This is non-mutating: it returns `mutation_applied:false` and `apply_available:true`, does not call Contacts.framework, and does not modify Contacts data.
24. Call `contacts_apply_change` only after a matching Contacts plan, an exact `contacts-apply:v1:<approval_fingerprint>` approval token, explicit user approval for that exact operation, and the same contact type, name/organization fields, and labeled email/phone/URL values. It may only create one contact through Contacts.framework.
25. Call `notes_plan_change` only when the user asks to plan a future Notes note create with bounded title/body text. This is non-mutating: it returns `mutation_applied:false` and `apply_available:true`, does not call Notes.app, and does not modify Notes data.
26. Call `notes_apply_change` only after a matching Notes plan, an exact `notes-apply:v1:<approval_fingerprint>` approval token, explicit user approval for that exact operation, and the same title and body text. It may only create one plaintext note through Notes.app automation.
27. Call `mail_plan_change` only when the user asks to plan a future Mail draft create with bounded recipients, subject, and body text. This is non-mutating: it returns `mutation_applied:false` and `apply_available:true`, does not call Mail.app, and does not modify Mail data.
28. Call `mail_apply_change` only after a matching Mail plan, an exact `mail-apply:v1:<approval_fingerprint>` approval token, explicit user approval for that exact operation, and the same recipients, subject, and body text. It may only save one plaintext draft through Mail.app automation and must not send mail.
29. Call `photos_plan_change` only when the user asks to plan a future Photos image/video import from a caller-selected local source file. This is non-mutating: it returns `mutation_applied:false` and `apply_available:true`, does not call PhotoKit, does not modify Photos, and does not echo the raw source path.
30. Call `photos_apply_change` only after a matching Photos plan, an exact `photos-apply:v1:<approval_fingerprint>` approval token, explicit user approval for that exact operation, and the same source file. It may only import one local image or video through PhotoKit and must not edit, delete, target albums, mutate metadata, or fetch iCloud media over the network.
31. If the user asks for attachments, broad content search, Gmail fallback, broad Calendar/Contacts/Photos/Reminder dumps, broad Messages text search, broad Voice Memos transcript search, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, private iCloud web/API access, browser/keychain credential access, generated Voice Memos transcription, Contact update/delete/merge/move/group membership/postal-address/birthday/relationship/social-profile/notes/image mutation, Notes append/update/delete/move/folder-account/rich-text/attachment mutation, Mail send/reply/forward/archive/move/delete/mark/flag/mailbox-account mutation, Photos edit/delete/album/hidden/favorite/metadata mutation, arbitrary document/binary extraction, unsupported UI automation, iCloud Drive append/overwrite/delete/binary/document writes, Calendar update/delete/recurrence/attendees/alarms/all-day/default-calendar guessing, or mutation other than approved Reminders create/complete/due-date apply, iCloud Drive create-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create-note apply, Mail create-draft apply, or Photos import apply, stop and explain that those are outside this plugin's approved surface.

## Tools

- `apple_data_health`: redacted readiness and schema-only local checks.
- `apple_data_doctor`: redacted diagnostics and remediation guidance.
- `mail_search`: capped subject-metadata search across local Mail.app stores, with a metadata-only `content_status` hint.
- `mail_get_metadata`: exact Mail metadata by opaque handle.
- `mail_get_content`: exact Mail plain-text content by opaque `mail:message:v2:` handle, capped and read-only.
- `mail_plan_change`: non-mutating future Mail draft create preview, with idempotency and approval metadata only.
- `mail_apply_change`: approved Mail draft create, requiring a matching plan approval token, explicit confirmation, save-only Mail.app automation, and local Drafts read-back verification when available.
- `messages_search`: capped Messages chat display-name metadata search.
- `messages_get_chat`: exact Messages chat transcript by opaque `messages:chat:v1:` handle, capped and read-only.
- `hide_my_email_search`: capped inferred Hide My Email alias search from local Mail address metadata; masked alias previews only.
- `hide_my_email_get_alias`: exact inferred alias detail by opaque `hide_my_email:alias:v1:` handle, capped and read-only, with provenance and `authoritative_inventory:false`.
- `voice_memos_search`: capped Voice Memos title/filename metadata search.
- `voice_memos_get_recording`: exact Voice Memos metadata and existing embedded transcript by opaque `voice_memos:recording:v1:` handle, capped and read-only.
- `voice_memos_export_audio`: exact Voice Memos `.m4a` export by opaque `voice_memos:recording:v1:` handle to a caller-selected output directory, read-only.
- `notes_search`: capped Notes title/snippet metadata search.
- `notes_get_metadata`: exact Notes metadata by opaque handle.
- `notes_get_content`: exact Notes plain-text content by opaque `notes:note:v2:` handle, capped, paged, and read-only.
- `notes_plan_change`: non-mutating future Notes note create preview, with idempotency and approval metadata only.
- `notes_apply_change`: approved Notes note create, requiring a matching plan approval token, explicit confirmation, Notes.app automation, and exact-content read-back verification.
- `icloud_drive_search`: capped iCloud Drive filename metadata search.
- `icloud_drive_get_metadata`: exact iCloud Drive metadata by opaque handle.
- `icloud_drive_get_content`: exact iCloud Drive text-file content by opaque `icloud:file:v1:` handle, capped and read-only.
- `icloud_drive_plan_change`: non-mutating future iCloud Drive text-file create preview, with idempotency and approval metadata only.
- `icloud_drive_apply_change`: approved iCloud Drive text-file create, requiring a matching plan approval token, explicit confirmation, exact parent folder handle, exclusive create, and read-back verification.
- `calendar_search`: capped Calendar event title metadata search through EventKit.
- `calendar_get_event`: exact Calendar event details by opaque `calendar:event:v1:` handle, capped and read-only.
- `calendar_plan_change`: non-mutating future Calendar timed-event create preview, with idempotency and approval metadata only.
- `calendar_apply_change`: approved Calendar timed-event create, requiring a matching plan approval token, explicit confirmation, explicit calendar title, EventKit apply, and read-back verification.
- `contacts_search`: capped Contacts name/organization metadata search through Contacts.framework.
- `contacts_get`: exact Contact details by opaque `contacts:contact:v1:` handle, capped and read-only.
- `contacts_plan_change`: non-mutating future Contacts contact create preview, with idempotency and approval metadata only.
- `contacts_apply_change`: approved Contacts contact create, requiring a matching plan approval token, explicit confirmation, Contacts.framework apply, and read-back verification.
- `photos_search`: capped Photos original-filename metadata search through PhotoKit.
- `photos_get_asset`: exact Photos asset/resource metadata by opaque `photos:asset:v1:` handle, capped and read-only.
- `photos_export_asset`: exact Photos asset export by opaque `photos:asset:v1:` handle to a caller-selected output directory, read-only.
- `photos_plan_change`: non-mutating future Photos image/video import preview, with source-file hash binding, idempotency, and approval metadata only.
- `photos_apply_change`: approved Photos image/video import, requiring a matching plan approval token, explicit confirmation, PhotoKit apply, and created-asset read-back verification.
- `reminders_search`: capped Reminders title metadata search.
- `reminders_due`: bounded due-window Reminders metadata search.
- `reminders_eventkit_search`: capped Reminders title metadata search through EventKit.
- `reminders_get_content`: exact Reminder notes by opaque `reminders:reminder:eventkit:v1:` handle, capped and read-only.
- `reminders_plan_change`: non-mutating future Reminder create/complete/due-date preview, with idempotency and approval metadata only.
- `reminders_apply_change`: approved Reminder create/complete/due-date apply, requiring a matching plan approval token, explicit confirmation, expected state, EventKit apply, and read-back verification.

## Boundaries

- Never print or persist raw MIME, full headers, Messages transcript text outside exact selected responses, full Hide My Email aliases outside exact selected responses, Voice Memos transcript text outside exact selected responses, exported Voice Memos audio outside the caller-selected export path, contact details outside exact selected responses, Photos asset/resource metadata outside exact selected responses, exported Photos assets outside the caller-selected export path, Photos import source paths/hashes outside transient preview/apply responses, reminder notes outside exact selected responses, Reminder plan titles/notes outside transient preview responses, attachments, credentials, raw database rows, local Mail file paths, raw Voice Memos source paths, raw Photos identifiers, raw iCloud Drive file paths, raw Hide My Email identifiers, or full account identifiers.
- Mail, Messages, inferred Hide My Email aliases, Voice Memos, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive content/detail may be summarized or quoted only from the exact selected handle response, and should not be copied into durable docs or logs.
- Do not mutate Mail outside the approved create-draft apply path, and do not mutate Notes, Hide My Email, Gmail, TCC, launchd, Codex config, or OpenClaw runtime state from this skill. Reminders mutation is limited to the approved create/complete/due-date apply path. iCloud Drive mutation is limited to the approved create-text apply path under an exact opaque parent folder handle. Calendar mutation is limited to the approved timed-event create path in an explicit target calendar. Contacts mutation is limited to the approved create-contact path through Contacts.framework. Notes mutation is limited to approved create-note apply. Photos mutation is limited to approved image/video import apply. Mail send, Mail management, Photos edit/delete/album/metadata mutation, and Photos network fetch remain outside scope.
- Do not retry by switching to Gmail plugin access unless the user explicitly asks for Gmail connector behavior.
- Report warning codes and remediation from the tool output when a local store is degraded or unavailable.
