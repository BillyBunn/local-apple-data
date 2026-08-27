# v1.79 Mail Attachment Content Search Design

Status: Source read-capable implementation.

This document extends the v1.77 Mail attachment discovery surface with explicit, date-bounded attachment content snippet search. It is read-only. It does not approve durable content indexing, broad attachment export, inline attachment bytes, source attachment forwarding, attachment mutation, or Mail mutation.

## Approved Read Tools

- CLI: `local-apple-data mail attachment-search --include-content`
- CLI OCR option: `local-apple-data mail attachment-search --include-content --include-ocr`
- MCP: `mail_search_attachments(include_content=True)`
- MCP OCR option: `mail_search_attachments(include_content=True, include_ocr=True)`

## Privacy Contract

- A caller must still provide `after` or `before`.
- Query text must still pass the minimum quality guard.
- Results remain capped at 50 and each scan page remains bounded.
- Attachment content is searched only when `include_content` is true.
- OCR is attempted only when both `include_content` and `include_ocr` are true. OCR attempts are capped per search.
- Text-like attachment payloads are decoded locally and bounded before search; declared or encoded oversize payloads are refused before content decode.
- PDF text extraction uses local `pdftotext` when available.
- PDF OCR fallback uses local `ocrmypdf` only when explicitly requested.
- Private temporary files are used for PDF tooling and are deleted before the tool returns.
- Output may include a capped redacted `snippet`, `snippet_chars`, and `attachment_text_extractor`.
- Snippet redaction covers email addresses, local path-like strings, raw-ID-like fields, UUID/long-hex identifiers, and common phone-number shapes.
- Output query metadata includes `ocr_attempt_count` and `ocr_attempt_limit`; the tool returns `ocr_attempt_limit_reached` if additional PDF OCR candidates were skipped.
- Output returns exact `mail:attachment:v1:` handles and safe attachment metadata.
- Output returns no attachment bytes, source `.emlx` paths, temporary paths, raw MIME, full headers, full email addresses, raw account identifiers, raw row IDs, durable index paths, or local attachment source paths.
- Unsupported, oversized, unavailable, or tool-unavailable attachments are skipped safely.

## Explicit Non-Goals

- No durable body or attachment FTS cache in this v1.79 gate; an opt-in private local FTS cache later landed under `docs/V1_81_MAIL_FTS_INDEX_DESIGN.md`.
- No background indexing.
- No broad unbounded Mail content search.
- No arbitrary document extraction beyond text-like attachment payloads, PDF embedded text, and opt-in PDF OCR snippets.
- No attachment export beyond the existing exact selected attachment export gate.
- No mutation is introduced by this gate.

## Synthetic Tests Required

- Attachment content search does not run unless `include_content` is true.
- Text attachment content search returns a redacted bounded snippet and no full email address.
- Text attachment content search redacts embedded local paths, raw-ID-like values, UUID/long-hex identifiers, and phone numbers.
- Declared oversized attachment content search refuses before payload decode.
- PDF attachment content search uses the PDF text extractor path.
- PDF attachment OCR search uses the OCR fallback only when `include_ocr` is true.
- PDF attachment OCR search stops at the per-search OCR attempt limit and reports `ocr_attempt_limit_reached`.
- Nonmatching metadata-only attachment search still does not read nonmatching payload bytes.
- CLI forwards `--include-content`, `--include-ocr`, and `--max-snippet-chars`.
- MCP forwards `include_content`, `include_ocr`, and `max_snippet_chars`.
- Runtime verifier proves synthetic attachment-content search over one exact Mail attachment.

## Current Blockers

Opt-in Mail FTS/body or attachment indexing later landed under `docs/V1_81_MAIL_FTS_INDEX_DESIGN.md` as an explicit-confirmation private cache. Background indexing, unbounded/bulk body search, broad attachment export, and arbitrary document extraction remain blocked until separate gates land. Opt-in source attachment-like part forwarding later landed under `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`; source attachment/non-body forwarding outside explicit `include_source_attachments` remains blocked.
