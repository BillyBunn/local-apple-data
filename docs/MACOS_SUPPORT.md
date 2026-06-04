# macOS Support

## Current Test Baseline

- Local development smoke: macOS 26.5, build 25F71.
- CI: GitHub Actions `macos-latest`, synthetic fixtures only.

The project is expected to need macOS because it depends on local Apple stores and Apple frameworks. Older macOS releases may work when the local database schemas and framework permissions match, but support should be verified with the test suite and `health` command before relying on a surface. Health checks are non-prompting: they verify local store presence/readability and supported schema fingerprints where practical, and they report framework access requirements without requesting Calendar, Reminders, Contacts, Photos, or Automation permission.

## Framework And Store Map

| Surface | Local mechanism | Permission class |
| --- | --- | --- |
| Mail | Mail.app local metadata and `.emlx` content files plus save-only Mail.app automation for approved create-draft apply | Full Disk Access and Automation may be required |
| Messages | Messages local `chat.db` | Full Disk Access may be required |
| Hide My Email | Inferred local Mail address metadata | Full Disk Access may be required |
| Voice Memos | Voice Memos local database and embedded transcript atom | Full Disk Access may be required |
| Notes | Local Notes SQLite plus bounded Notes.app automation for exact content and approved create/append-text apply; local Notes media files for exact attachment export | Full Disk Access and Automation may be required |
| Calendar | EventKit helper | Calendar permission |
| Reminders | EventKit helper plus legacy SQLite metadata | Reminders permission |
| Contacts | Contacts.framework helper | Contacts permission |
| Photos | PhotoKit helper | Photos permission |
| iCloud Drive | Local filesystem under the user's iCloud Drive location | Local file access |

## Degraded Behavior

Permission, schema, or local sync problems should return structured warning codes. They should not print raw database rows, raw framework identifiers, local file paths, private content, or raw system exception strings.

Expected degraded cases include:

- Local store unavailable.
- Permission not granted.
- Private Apple schema changed.
- Requested iCloud Drive file is not downloaded locally.
- Requested content type is intentionally unsupported.
- Exact handle is invalid, stale, or fabricated.

## Public Support Notes

- This is not an iCloud web client.
- It does not manage iCloud account state.
- Hide My Email support is inferred from local Mail evidence, not an authoritative iCloud inventory.
- Photos support returns asset/resource metadata, can export one exact selected asset to a caller-selected output directory, and can import one caller-selected image/video source file after plan approval. It does not return image or video bytes inline and does not edit, delete, target albums, mutate metadata, or fetch iCloud media over the network.
- Voice Memos support returns existing embedded transcript text when present and can export one exact selected `.m4a` to a caller-selected output directory; it does not generate transcripts.
- Write and mutation tools require separate approval gates before implementation. The current Mail write gate is limited to save-only draft creation; it does not send mail. The current Photos write gate is limited to importing one local image or video file; it does not edit or delete Photos assets.
