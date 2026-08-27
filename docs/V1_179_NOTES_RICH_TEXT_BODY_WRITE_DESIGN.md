# v1.179 Notes Rich-Text Body Read + Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data notes apply` and `notes_apply_change`.

No new mutating tool names are approved or exposed by this document. The existing `local-apple-data notes plan` and `notes_plan_change` tools now support `operation:create_html` and `operation:replace_html` as non-mutating previews, and the existing apply tools now support the matching approved rich-text create/replace operations. The existing exact-content read tools `local-apple-data notes content` / `notes_get_content` gain a `content_format:html` mode that reads the note's rich-text body.

This document is the required operator approval gate for reading and writing Apple Notes rich-text bodies. The prior release kept Notes bodies plaintext-only and never returned the rich-text HTML body. The operator has explicitly authorized "read + rich-text write" for Notes bodies (reversing the prior metadata/plaintext-only policy); this change is operator-authorized.

## Scope

Allowed:

- Read one note's rich-text body for one exact opaque `notes:note:v2:` handle. `content_format:html` returns a bounded HTML body plus its extracted visible text, behind the same exact-handle gate as the plaintext content path, with a documented content cap and an explicit truncation flag.
- Create one note with a sanitized rich-text HTML body in the default folder or one exact selected folder (`operation:create_html`).
- Replace one unlocked, non-deleted, non-shared note's body with sanitized rich-text HTML for one exact `notes:note:v2:` handle (`operation:replace_html`), with expected-current-state binding.

Blocked:

- Broad or bulk body dumps, broad body search, body content outside the exact-handle gate, checklist state, attachment mutation, locked-note mutation, shared-note mutation, Recently Deleted management, raw Notes identifiers, raw local database paths, durable content caches, and background indexing.
- Private Notes store writes, iCloud.com, browser sessions, keychain credentials, and private iCloud web APIs.

## Body Read Scope and Cap

- Metadata-first defaults are unchanged: `content_format` defaults to `text` and body HTML is only returned when the caller explicitly requests `content_format:html` for an exact handle.
- The returned HTML body is bounded to a documented maximum (24000 characters) with an explicit `content_html_truncated` flag and `content_html_total_chars`. The extracted plain text remains bounded by the existing `content_text` cap (12000 characters) and paging.
- Raw note body content is sensitive personal content; it stays behind the exact-handle gate and is never returned by search, folder listing, or any broad body search.

## HTML Sanitization

Rich-text create/replace input HTML is sanitized before it is passed to Notes.app so a stored note can never carry active or externally fetched content. Body HTML containing a NUL (U+0000) or any other C0/DEL control character (everything except tab, newline, and carriage return) is rejected fail-closed before parsing, at both plan and apply time, so a control byte embedded in a tag or attribute name (for example a NUL inside `<script>`) cannot evade the element/attribute matching. The sanitizer then strips or rejects `<script>`, event-handler (`on*`) attributes, and `javascript:`/`vbscript:`/`data:` URIs, and drops embedded `<style>`, `<iframe>`, `<object>`, `<embed>`, `<link>`, `<meta>`, `<base>`, `<form>`, `<svg>`, and `<math>` element contents while preserving visible text and safe formatting tags. Input HTML is bounded (24000 characters). If, after sanitization, the body still contains active content, or has no visible text, apply is refused.

## Semantic (Extracted-Text) Read-Back Proof

Notes.app normalizes stored HTML on save (it reorders attributes, wraps text, and strips/re-adds tags), so an exact-string HTML read-back will not match what was set. The read-back proof is therefore a semantic read-back proof: after save, the note's body is re-read, its plain text is extracted from the stored HTML, and that extracted visible text is proven equal (normalized) to the proposed body's extracted visible text. The proof is designed around extracted-plain-text equivalence so it is deterministic, plus proof that the note exists at the expected handle. A mismatch returns a read-back error.

Because HTML does not round-trip exactly, `replace_html` binds and rechecks the note's expected/observed visible text: `expected_current_sha256` binds the extracted visible-text SHA-256 (from exact `local-apple-data notes content` / `notes_get_content`), not raw HTML.

## Tool Contract

Every Notes rich-text mutation keeps the same three-step shape:

- `preview`: validate and sanitize inputs and return the planned change without touching Notes.app or reading Notes data.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through the normal exact Notes content adapter with `content_format:html`.

The apply payload requires an approval token generated from the preview. The token binds the operation, exact note handle or folder target, expected current extracted-text SHA-256 for replace, the proposed body's sanitized HTML hash and extracted-text hash, and idempotency key, so an agent cannot apply different content or a stale preview.

## Implemented Preview

- CLI: `local-apple-data notes plan --operation create-html` / `--operation replace-html`
- MCP: `notes_plan_change(operation="create_html"|"replace_html", ...)`

Preview requirements:

- Return `mode:"plan"`, `mutation_applied:false`, `apply_available:true`.
- Require bounded, sanitized, non-empty `body_html`; reject plain `body_text` for these operations.
- For `replace_html`, require an exact opaque `notes:note:v2:` handle and `expected_current_sha256` (extracted visible-text SHA-256).
- Do not call Notes.app, read note content, or mutate Notes data.
- Do not log handles, content, content hashes, titles, approval fingerprints, or approval tokens.

## Implemented Apply

- CLI: `local-apple-data notes apply --operation create-html` / `--operation replace-html`
- MCP: `notes_apply_change(operation="create_html"|"replace_html", ...)`

Apply requirements:

- Require the matching approval token and explicit confirmation (`confirm_apply=true`).
- Re-sanitize the body HTML at apply time; never trust apply-time input drift for the title (taken from the approved preview).
- For `replace_html`, recompute the current note's extracted-text SHA-256 and refuse when it differs from `expected_current_sha256`.
- Refuse password-protected and shared-note mutation.
- Prove the semantic read-back visible text equals the approved body before reporting success; otherwise return a read-back mismatch.

MCP annotations are static per tool. Rich-text create is idempotent-guarded (matching note detection); rich-text replace is destructive, non-idempotent.

## Synthetic Tests Required

Adapter and MCP tests cover bounded body read plus truncation, rich-text create, rich-text replace with expected-state binding, stale rejection, semantic read-back, HTML sanitization (script/handler/`javascript:`/`data:` rejected or stripped), and unchanged plaintext-op regressions. Runtime verification covers direct and MCP lanes for read-body, rich-text create, and rich-text replace with read-back.

The current release allows Notes create-note in the default folder or one exact selected folder, exact child-folder creation under one selected parent folder, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, move-to-folder, and exact-note delete apply only.
