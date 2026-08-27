# Security Policy

## Supported Versions

The initial public candidate is `0.1.x`. Security fixes should target the latest `0.1.x` release unless a later supported branch is documented.

## Security Model

`local-apple-data` is a local-only MCP server and CLI. It reads locally synced Apple data from macOS stores and public macOS frameworks where available. The current release is metadata-first and read-mostly; it exposes 14 narrowly scoped MCP apply tools whose mutations require the matching plan approval token, explicit confirmation, and operation-specific read-back or invocation proof.

The runtime does not use:

- Gmail connector paths, Gmail API, IMAP, OAuth, app passwords, or network mail services.
- iCloud.com scraping, private iCloud web APIs, browser sessions, cookies, or keychain credentials.
- Telemetry, remote analytics, or background indexing. The only durable personal-content cache is the explicit opt-in, date-bounded, locally private Mail FTS index governed by its separate design gate.

Search tools are metadata-first. Content and detail tools require exact opaque handles returned by prior metadata searches.

## Local Permissions

Depending on the requested surface, macOS may require Full Disk Access, Automation permission, Calendar permission, Contacts permission, Photos permission, or Reminders permission. Permission failures should degrade to structured warning codes and remediation text.

Do not grant broad macOS permissions to an MCP client you do not trust. A stdio MCP server inherits the local process permissions of the client that launches it.

## Reporting A Vulnerability

Use GitHub Security Advisories when available for the repository. If advisories are not enabled, open a minimal public issue that describes the vulnerable behavior without including live personal data, handles, local paths, account identifiers, credentials, or private aliases.

Good reports include:

- The affected command or MCP tool.
- The expected privacy boundary.
- The observed behavior.
- A synthetic reproduction when possible.

Do not include real Mail bodies, Notes, Messages, Reminder notes, Voice Memos transcripts, Contacts, Photos metadata from private libraries, full aliases, local database rows, raw file paths, tokens, cookies, OAuth artifacts, or keychain material in a report.
