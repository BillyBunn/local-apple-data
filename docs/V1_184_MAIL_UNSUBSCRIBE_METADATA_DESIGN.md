# v1.184 Exact Mail Unsubscribe Metadata

Date: 2026-07-15
Status: Implemented, source-verified, synced to the personal plugin, and
installed as `0.1.0+codex.20260715201000`.

## Objective

Give a downstream unsubscribe executor the minimum exact-message evidence it
needs without adding Mail mutation or broad header access.

Surfaces:

- CLI: `local-apple-data mail unsubscribe-metadata --json --handle <mail:message:v2:...> [--include-body-links]`
- MCP: `mail_get_unsubscribe_metadata(handle, include_body_links=false)`

## Gate

- Input is one valid opaque `mail:message:v2:` handle from the existing Mail
  metadata flow. Raw row IDs, legacy handles, mailbox refs, paths, and
  fabricated handles fail with `invalid_handle`.
- The adapter resolves the live non-deleted Envelope Index row read-only and
  reads at most the existing 64 KiB `.emlx` header prefix.
- Only `List-Unsubscribe`, `List-Unsubscribe-Post`, and `List-Help` are
  inspected. Message body, sender/recipient headers, unrelated headers, raw
  MIME, raw account IDs, and local paths are not returned.
- Result identity is limited to the exact message handle, Envelope Index
  subject, hashed `account_ref`, and hashed `mailbox_ref`.

## Endpoint policy

- URI order is preserved and duplicates are removed.
- Only angle-bracketed `http`, `https`, and `mailto` endpoints are returned.
- Literal or percent-decoded control characters, whitespace-bearing values,
  credential-bearing web URLs, malformed ports/hosts, and all other schemes
  are omitted with a count plus a safe warning code. Rejected values are never
  echoed.
- One-click classification requires both an HTTPS unsubscribe endpoint and an
  exact case-insensitive `List-Unsubscribe=One-Click` value in
  `List-Unsubscribe-Post`. Its request method is `POST`.
  The endpoint record supplies the fixed RFC 8058 form content type and body;
  non-one-click records return no request body.
- HTTP(S) links without that proof and all mailto endpoints are
  `manual_required`. Every `List-Help` URI is `action:help`,
  `manual_required:true`, and `one_click:false`, even when the RFC 8058 header
  is present.

## Opt-in body-link fallback

- Disabled by default. `include_body_links:true` / `--include-body-links`
  inspects only HTML anchors in the exact selected local MIME body.
- MIME input is capped at 10 MiB. Output is capped at five ordered,
  deduplicated URLs and returns no body text, anchor labels, or unrelated URLs.
- An anchor qualifies only when its visible text explicitly says unsubscribe,
  opt-out, or stop receiving; its href path/query explicitly contains
  unsubscribe or optout; or its visible text says click here within 150 prior
  visible characters of an unsubscribe phrase.
- Generic manage/preferences/login/resubscribe hrefs are rejected unless the
  anchor text itself explicitly says unsubscribe.
- Every accepted endpoint is `classification:body_link`, uses only an
  allowlisted http(s)/mailto URL, has `manual_required:true`, and has
  `one_click:false`. Body HTML can never enter the RFC 8058 POST lane.
- `match_reason` is a bounded enum only: `explicit_unsubscribe_text`,
  `unsubscribe_url`, or `adjacent_unsubscribe_phrase`. Explicit anchor wording
  wins when multiple signals match. No anchor text or free-form evidence is
  returned.

## Privacy contract

The output tier is `exact_header_detail`. Privacy flags prove that the header
was inspected, the message body was not inspected, endpoint URLs may be
returned for the exact selected item, and raw/unrelated headers, raw rows,
credentials, raw account IDs, and local paths were not returned. Redacted
event logs contain only command/status/count/warning-code/privacy summaries;
handles, subjects, and endpoint URLs are excluded.

When and only when body-link mode is requested and parsing succeeds,
`message_body_inspected` and `content_inspected` are true. Body content and
anchor labels remain absent.

## Non-goals

- No unsubscribe HTTP request, browser action, mailto send, or Mail mutation.
- No sender-wide or query-result header scan.
- No broad/full header retrieval.
- No endpoint persistence, network access, Gmail connector, IMAP, OAuth, Mail
  UI automation, plugin install, installed-cache sync, or service restart.

## Verification

Synthetic tests cover exact-handle success, ordered/deduplicated endpoints,
strict RFC 8058 classification, `List-Help` isolation, unsafe endpoint
omission, body/unrelated-header non-disclosure, invalid handles,
missing-local-file fail-closed behavior, CLI routing, MCP exposure, and
redacted logs.

The completed integration verification passed the full 2,123-test source suite
and the full 2,123-test installed-cache suite. Source and installed runtime,
mutation-gate, write-design, surface-contract, redaction, public-release, and
Mail health checks passed. The source checkout remains intentionally dirty
during this integration and has no publication-safe remote, so GitHub release
readiness is not claimed.
