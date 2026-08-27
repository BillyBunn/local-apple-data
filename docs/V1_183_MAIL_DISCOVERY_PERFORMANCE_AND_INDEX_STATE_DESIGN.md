# V1.183 Mail Discovery Performance and Index State (Read-Side Tranche)

## Goal

Make Mail discovery fast and honest. A downstream agent (Codex, 2026-07-13 field report)
hit five reproducible failures on the live store (126,450 Envelope Index messages,
128,577 `.emlx` files, 70,784 of them `.partial.emlx`):

1. Body/advanced/attachment searches scanned only 200 rows per call, took minutes, and
   reported `status: "ok"` with `result_count: 0` — a silent false negative for
   merchant-style queries (`WellnessPay`) whose match lives in the body.
2. FTS builds ran 20–30 minutes without visibly completing; after interruption,
   `mail_search_fts` returned zero rows with no partial/stale coverage signal.
3. Exact-handle content reads returned `content_unavailable` for messages plainly
   visible in Mail.app.
4. Reply planning failed `message_identity_unavailable` for messages Mail.app can reply to.
5. Search results carried no per-account attribution.

## Root causes (measured on the live store)

- `_find_message_file_candidates` ran `mail_root.glob(f"**/Messages/{rowid}.emlx")` —
  a full recursive walk of the ~500k-entry Mail tree **per message**. Body search paid
  it per scanned row (measured: 200 rows = 2m29s, 120s of it system time); the FTS
  build paid it three times per message (parse, hash, body), which is why a bounded
  one-year build could not finish; even FTS search paid it per candidate row for
  content-state verification. One `os.walk` pass of the same tree takes ~1.7s and
  yields a complete `rowid → path` index.
- The glob matched only `{rowid}.emlx`. 70,784 of 128,577 messages on this store exist
  only as `{rowid}.partial.emlx` (Mail downloaded headers + some parts, fetches the
  rest on demand). Every one of them read as `content_unavailable`, and reply identity
  (RFC Message-ID recovered from the local file's headers) failed with them.
- `mail_fts_meta` stored only `schema_version`: no build state, no checkpoint, no
  coverage counts. An interrupted build was indistinguishable from a complete one.
- Discovery scans stopped silently at `MAX_MAIL_DISCOVERY_SCAN_ROWS = 200` rows per
  page; the only signal was a `next_cursor` field that callers reasonably missed
  because the payload also said `status: "ok"`.

## Changes (all read-side; no new mutation surface)

### 1. One-walk message-file index (shared fix, all call paths)

`_scan_mail_message_files(mail_root)` walks the tree once with `os.walk`, collecting
both `{rowid}.emlx` and `{rowid}.partial.emlx` under `Messages/` directories into
`rowid → candidates`. Selection rule per rowid preserves the existing exactly-one
safety semantics, extended for partials: exactly one full match → that file
(status `available`); no full match and exactly one partial → the partial file
(status `partial`); anything else → `unavailable`.

Scan-shaped operations (body/attachment/advanced search, FTS build, FTS search
verification, subject-search content-status annotation) build the index once per call
and do O(1) lookups. Single-message operations (content read, triage resolve) use the
same walk restricted to their one rowid — same cost as the old single glob, now
partial-aware. No cross-call caching: every call observes the live tree, so there is
no staleness to manage.

### 2. Partial-download honesty

`content_status` gains the value `"partial"` (message file present as
`.partial.emlx`). `mail_get_content` reads partial files and returns whatever text
extracts, with warning `partial_download`; if the text part is not locally present it
still fails as `content_unavailable`, with a message that names the real cause
(message not fully downloaded locally). Reply/triage identity resolution reads RFC
Message-ID from partial files' headers (headers are always present), which removes
the dominant `message_identity_unavailable` failure class. When identity still fails,
the warning message now distinguishes “no local message file” from “file lacks an RFC
Message-ID header”; the plan fails closed as before — inventing an unproven
AppleScript addressing mode (subject/date matching) is rejected as unsafe.

### 3. Scan transparency and time budget (shared by CLI and MCP)

Body, attachment, advanced, and FTS searches plus the FTS build accept
`max_seconds` (default 20, bounded 1–120) and stop cleanly at the budget with an
accurate `next_cursor`. Every discovery payload now carries a `scan` block:
`{"scanned": n, "range_total": N, "elapsed_ms": t, "stopped_reason":
"exhausted" | "result_limit" | "scan_limit" | "time_budget"}` where `range_total` is
the Envelope Index message count inside the date bounds. A `scan_time_budget_reached`
warning accompanies budget stops. `MAX_MAIL_DISCOVERY_SCAN_ROWS` rises 200 → 2000,
which the per-row cost (now ~1–3 ms instead of ~700 ms) makes safe under the default
budget. Both CLI and MCP call the same adapter functions, so behavior is identical;
interruption (SIGINT, client timeout) needs no extra cleanup because discovery is
read-only and the FTS build commits per page with its checkpoint.

### 4. FTS build state, checkpoint, resume

`mail_fts_meta` now records `build_state` (`building` | `ready`), `built_after`,
`built_before`, `checkpoint_cursor`, `last_build_at`, and the Envelope schema
fingerprint, updated in the same transaction as each page commit. A new read-only
tool `mail_fts_status` (CLI: `mail fts-status`) reports
`missing | building | partial | ready | stale` plus `indexed_docs`,
`range_total`, `checkpoint_cursor` (resume token), built range, and stale-row counts.
`mail_search_fts` embeds the same `index_state` block and warns
(`mail_fts_partial_coverage`) whenever the state is not `ready`, so an interrupted
index can never silently answer “zero rows”. The build also reads each message file
once (previously three times: parse, hash, body-extract).

### 5. Attribution

`_row_to_metadata` adds `account_ref` (the existing hashed account reference already
used by mailbox metadata) and `mailbox_path` (the unquoted mailbox path, e.g.
`[Gmail]/All Mail`, same privacy class as the existing `mailbox_name` field) to every
search/content result.

## Privacy posture (unchanged)

Everything here is metadata-first and read-only. Snippets remain capped and redacted;
full content stays exact-handle only; the FTS index remains an explicit opt-in local
durable cache (`confirm_index=true`) in the same location; no new raw identifiers are
exposed (`account_ref` is a hash; `mailbox_path` is operator mailbox naming, per the
existing `mailbox_name` precedent). No Gmail/IMAP/network paths are introduced.

## Out of scope

- Reply addressing without an RFC Message-ID (unproven against live Mail; fails closed).
- Cross-call in-memory caching of the file index (revisit only if per-call walk cost
  ever dominates again).
- Spotlight/`mdfind`-backed discovery.
