# v1.182 Notes Folder Content Export

## Objective

Give the operator's approved downstream private store (PKOS, `sensitivity_tier='private'`,
ACL-gated, tripwired) a bounded, paged, date-bounded way to read note text folder-by-folder for
personal-knowledge ingestion, without per-note manual handle selection. This is the
operator-authorized revision of the prior "no broad or bulk body dumps" Notes boundary: the
operator approved body-level personal-data ingestion on 2026-07-07 (order Messages → Mail → Notes,
"no garbage bulk") and explicitly green-lit this surface on 2026-07-09.

## Supported Surface

- `notes_export_folder_content` MCP tool and `local-apple-data notes export-content` CLI command.
- Inputs: one exact `notes:folder:v1:` handle from folder metadata output; a REQUIRED parseable
  ISO-8601 `modified_after` date bound; `cursor` (zero-based page offset, default 0); `limit`
  (notes per page, default 10, hard cap 20); `max_chars_per_note` (default 4000, hard cap 12000);
  and a REQUIRED `confirm_bulk` acknowledgement.
- Output per note: the existing folder-item metadata shape (note handle, title, fallback title,
  dates, flags — no snippet) plus `content_status`, bounded `content_text`, `content_chars`,
  `content_total_chars`, a full-text `content_sha256` (for downstream incremental sync and
  change detection), and `truncated`. Page-level output adds `exported_count`, `skipped_count`,
  and `next_cursor` (integer offset cursor, `null` on the last page).
- Notes whose body cannot be read this page (automation timeout or read error) are returned as
  metadata-only entries with `content_status:"skipped"` and a `skip_reason`; the page continues
  and a `note_content_skipped` warning is added. Body fetch reuses the existing per-note
  Notes.app AppleScript path under the existing 10-second per-note timeout — this is the
  throughput ceiling and why the page cap stays small.

## Boundaries

- `confirm_bulk` is required on every call; without it the tool returns
  `bulk_export_not_confirmed` and no content.
- `modified_after` is required and must parse; there is no unbounded "export everything ever"
  form. Full backfill is expressed explicitly (e.g. `modified_after=2001-01-01`) and still pages.
- One exact normal folder per call. Smart folders fail closed (`unsupported_smart_folder`).
  Password-protected and deleted notes are excluded in SQL, same predicates as every other note
  row query. No attachments, no HTML bodies (plain extracted text only), no broad body SEARCH —
  discovery stays metadata-first.
- This server persists NOTHING: responses are transient; no cache, no index, no logged content
  (the redacted event log records command/status/counts only). Durable storage happens in the
  operator's downstream private-tier store, outside this repo, under its own privacy layers.
- Not permission for: bulk Notes mutation, Recently Deleted access, cross-folder or all-notes
  dumps in one call, or any new content class.

## Safety Properties

- Read-only adapter path (`connect_readonly`); the only automation used is the existing
  body-read AppleScript.
- Caps clamped server-side: `limit` ≤ 20, `max_chars_per_note` ≤ 12000, cursor ≥ 0.
- Ordering is `(modification_date, pk)` ASC so offset pagination is stable within a backfill
  session; a note edited mid-pagination may shift later, which downstream sync tolerates by
  deduplicating on `content_sha256`.
- Privacy payload: `output_tier:"content"` plus `bulk_content_returned:true` whenever at least
  one body was returned, so the event log distinguishes bulk reads from exact-handle reads.
- Handles in/out are opaque (`notes:folder:v1:` in; `notes:note:v2:` out); no raw identifiers,
  paths, or account identifiers.

## Verification

```bash
uv run pytest tests/test_notes_export_content.py -q
uv run pytest -q
python3 -m compileall -q src/local_apple_data
uv run python scripts/audit_surface_contract.py
uv run python scripts/redaction_scan.py
uv run python scripts/verify_runtime.py
```

Covered by tests: confirm gate, date-bound requirement and filtering, locked/deleted exclusion,
bounded text + sha output, pagination via `next_cursor`, per-note timeout skip with page
continuation, smart-folder rejection.

## Future Work

- Optional `content_format:"html"` page items if a downstream consumer ever needs rich text
  (would reuse the v1.179 sanitized-HTML machinery).
- A `since_sha` server-side skip (client sends known hashes; server omits unchanged bodies) if
  AppleScript throughput becomes the binding constraint for incremental syncs.
