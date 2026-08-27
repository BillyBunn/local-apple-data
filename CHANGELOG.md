# Changelog

All notable public-release changes are tracked here.

## 0.1.0+codex.20260827004316 - 2026-08-26

Recovery-closeout truth reconciliation and release hardening. No tool or Apple
data surface was added.

### Fixed

- Reconciled the README, agent instructions, installed skill, plugin metadata,
  privacy/threat/testing guidance, capability matrix, routing docs, CRUD plans,
  and handoff records with the live 151-tool / 153-CLI surface. The current
  public MCP inventory has 14 apply-capable tools.
- Removed Contacts note mutation from every current live-surface summary.
  Contacts note contracts remain designed and synthetic-testable, but the local
  signed helper fails closed with `contacts_note_unavailable` before mutation
  because Apple's restricted entitlement requires a provisioning profile.
- Expanded the surface-contract audit so exact identifier-bound Shortcuts run,
  bounded home-directory Filesystem apply, Contacts-note fail-closed wording,
  current tool counts, and normative-document parity cannot drift silently.
- Made sanitized public-tree rebuilds idempotent by excluding the builder's own
  `.public-release-tree.json` marker from the copied source set, with two-pass
  regression coverage.
- Updated release-readiness fixtures to derive their current mutation contracts
  from the auditors instead of preserving stale live Contacts-note language.

### Verified

- The source suite passes 2,205 tests. Plugin/skill validation, runtime proof,
  mutation/write-design/surface audits, Calendar and Messages public-surface
  audits, redaction scan, and public-release scan pass for this cachebuster.

## 0.1.0+codex.20260812184740 - 2026-08-12

Adds a CLI-only Contacts permission-recovery surface without changing the MCP
tool count.

### Added

- `local-apple-data contacts request-access --json` now provisions or reuses the
  stable local signing identity, launches one signed Contacts helper for both
  consent and normal operations, and returns metadata-only authorization state.
  It is intentionally absent from MCP so ordinary tool calls cannot prompt.
- The locally self-signed Contacts helper omits Apple's restricted
  provisioning-profile-only notes entitlement. Contact-note operations fail
  closed, while archive export retries without notes and retains a JSON result
  if vCard serialization cannot be verified.

## 0.1.0+codex.20260812043234 - 2026-08-11

Post-recovery client-routing restoration and machine-local signed-helper identity
hardening. No tool surface change.

### Fixed

- Restored the personal Codex installation after the home-directory recovery
  conclusively omitted it, and restored the user-scope Claude Code MCP route;
  recovery is the high-confidence explanation for the latter loss, but no
  immediate post-recovery Claude receipt proves its exact timing.
- Direct CLI, source MCP, personal-root, and installed-cache launches now parse
  the same private machine-local helper-ID file. The parser accepts only the two
  allowlisted bundle-ID assignments and rejects shell syntax, unsafe file modes,
  symlinks, wrong ownership, invalid values, and missing explicit overrides.
- EventKit and Photos helper bundle IDs resolve after entrypoint configuration is
  loaded, preventing import-time defaults from silently overriding the pinned
  machine identity.
- Test isolation redirects signed-helper application roots away from the live
  operator apps, and installed-cache launchers retain no bytecode or local config.
- Codex skill metadata fields now stay within platform length limits while the
  full safety contract remains in the skill body.

### Added

- Health reports the operator-environment override name and active state without
  returning its private value.

## 0.1.0+codex.20260730194025 - 2026-07-30

Documentation accuracy pass plus a hardened public-tree test. No tool surface change.

### Fixed

- The approved-write-tool list under-reported the live mutation surface. `docs/INSTALL.md`
  claimed 12 approved MCP write tools and `docs/MUTATION_GATES.md` listed the matching
  names; both omitted `filesystem_apply_change` (v1.178) and `shortcuts_apply_run`
  (v1.180C). A safety document that under-reports two live mutation surfaces is the worst
  kind of stale, because the surface it hides is exactly the surface a reader is deciding
  whether to allow. The sentence is pinned verbatim by both `audit_mutation_gates.py` and
  `audit_write_design_gates.py`, so the docs, both pins, and the synthetic test fixtures
  were updated together. The longer canonical apply-surface summary already covered both.
- `skills/local-apple-data/SKILL.md` contradicted itself on Shortcuts: two refusal lists
  told an agent to refuse shortcut *runs*, while the same file documents the approved
  `shortcuts_plan_run` / `shortcuts_apply_run` gate. Both lists now refuse unbounded or
  name-resolved runs and defer to the exact-handle gate.
- The health sample in `docs/SAMPLE_OUTPUTS.md` showed 15 surfaces; the surface-contract
  audit enforces 18. Added `filesystem`, `tv`, and `freeform`. The same Filesystem
  omission was corrected in the repo's own agent brief.
- The "next priority is Calendar agent-ready scheduling" claim in
  `docs/WRITE_TOOL_ROADMAP.md` was a 2026-07-03 snapshot contradicted by six tranches of
  non-Calendar work. It is now labelled as dated and says plainly that no current next
  priority is agreed; picking one is an operator decision. Session-kickoff notes that
  hard-coded a plugin version and tool count now point at the live record instead.

### Changed

- `is_sanitized_public_tree()` now requires a positive marker written by the tree builder,
  not just the absence of operator docs. See the previous entry for why absence alone was
  the wrong test.

## 0.1.0+codex.20260730185508 - 2026-07-30

Makes the generated public tree pass its own gates. No runtime or surface change.

### Fixed

- The public release tree builder omits every file in `LOCAL_OPERATOR_DOCS` by design,
  but the release audit, the mutation-gate audit, the write-design-gate audit, and the
  packaging test all still required those files to exist. The generated tree therefore
  shipped a test suite and a release audit that demanded documents the same generator
  refuses to ship. Anyone cloning the public tree and running its checks would have hit
  four failures that had nothing to do with their checkout.

  `public_release_scan.is_sanitized_public_tree()` is now the single source of truth for
  "this is a generated tree, not the source checkout", and the four checks skip
  operator-only docs there. It keys on *all* operator docs being absent rather than any
  one of them, so a source checkout that has merely lost one still fails loudly instead
  of quietly downgrading to public-tree rules.

  Verified both ways: the source checkout still enforces every contract, and the
  generated tree now passes `audit_mutation_gates`, `audit_write_design_gates`,
  `audit_surface_contract`, `audit_release_readiness`, and `tests/test_plugin_packaging.py`.

## 0.1.0+codex.20260730173609 - 2026-07-30

Hardening pass over the three isolation gaps the previous release recorded as
known-but-unfixed. No new tools or surfaces.

### Changed

- `provision_local_signing_identity` refuses to run under pytest. It is the only
  code here that mutates a keychain, and nothing but the habit of mocking
  `subprocess` kept a test from importing a second signing identity into the
  operator's real login keychain. Tests that exercise provisioning opt in through
  a named `provisioning_allowed()` seam. The guard also protects the helper-app
  deletion path, which is what orphans Calendar/Reminders/Photos permissions.
- The contributor guide now states that the code-signing subsystem is audited
  read-only, and why: `security delete-certificate` defaults to the login
  keychain, and each helper's designated requirement pins to the certificate's
  leaf hash, so removing it silently invalidates permissions the user granted.
- `DEFAULT_FS_ROOT` and `DEFAULT_ICLOUD_DRIVE_ROOT` resolve per call instead of
  binding at import as default argument values. `LOCAL_APPLE_DATA_FS_ROOT` and
  `LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT` previously had no effect if set after
  import, which meant the test suite could not be isolated from the operator's
  real home directory and iCloud Drive. Both are now isolated in `tests/conftest.py`.
- `_provision_lock_path()` honors `LOCAL_APPLE_DATA_STATE_DIR`; it was the one
  path in the signing module written into the operator's real home.

### Added

- Health reports an `environment_overrides` block: which overrides are active, and
  which of them weaken a guard rather than relocate state. Names and booleans only,
  never values. `LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS` disables the
  credential-path denylist and was previously invisible at runtime.

## 0.1.0+codex.20260730165943 - 2026-07-30

v1.184 exact Mail unsubscribe metadata plus bounded Mail bulk-triage
performance/read-back hardening, landed together with three correctness fixes
found while measuring what MCP clients actually receive: client-truncated
server instructions, test-suite writes into the operator's real state, and the
event log's file mode. Design:
`docs/V1_184_MAIL_UNSUBSCRIBE_METADATA_DESIGN.md`.

### Added

- `mail_get_unsubscribe_metadata` MCP tool and `local-apple-data mail
  unsubscribe-metadata` CLI command for one exact `mail:message:v2:` handle.
  The default reads only the bounded local message-header prefix and returns
  allowlisted `List-Unsubscribe`, `List-Unsubscribe-Post`, and `List-Help`
  endpoints with strict RFC 8058 one-click classification. Raw/full headers,
  unrelated headers, bodies, local paths, and raw account identifiers remain
  excluded.
- Explicit `include_body_links` / `--include-body-links` fallback for bounded
  exact-message HTML-anchor inspection. It returns at most five conservatively
  matched endpoints, never returns body text or anchor labels, and always marks
  body-derived links manual-only.

### Changed

- The MCP server `instructions` string now leads with the mutation gating rule.
  Clients truncate this field — Claude Code cuts it at 2048 characters — and the
  gating sentence previously sat last, at character 6284, so it was never
  delivered. The apply-surface enumeration is unchanged and still satisfies
  `scripts/audit_mutation_gates.py`; it is simply the part now left beyond the
  cut, since it is redundant with `tools/list`. A 593-character exact-handle
  surface enumeration was replaced with a 199-character rule. The gating
  sentence is scoped to the `*_plan_change` / `*_apply_change` pair rather than
  claiming every write is plan-then-apply, which was not true of the Mail
  template and FTS-index tools.
- The redacted event log at `~/.local/state/local-apple-data/events.jsonl` is
  now kept `0600` inside a `0700` directory, matching `handle-secret.key` and
  `mail-fts.sqlite` beside it. Applied only at the default location and skipped
  for a symlinked log, so an operator-chosen `LOCAL_APPLE_DATA_LOG_DIR` keeps
  whatever modes its owner set. `docs/PRIVACY_MODEL.md` documents the log's
  permissions, a `jq` triage command, and why the log is deliberately not
  rotated.
- The test suite no longer writes to the operator's real state. The autouse
  fixture in `tests/conftest.py` now isolates `LOCAL_APPLE_DATA_LOG_DIR`,
  `LOCAL_APPLE_DATA_MAIL_FTS_INDEX`, and `LOCAL_APPLE_DATA_MAIL_TEMPLATE_STATE`.
  A full run previously appended 368 events to the operator's event log and left
  the real Mail FTS index one missing argument away from being overwritten.

- Exact capped bulk Mail triage now resolves message handles in one read-only
  database pass instead of reopening the Envelope Index for every handle. The
  approval fingerprint, per-message mutation semantics, and exact account and
  mailbox bindings are unchanged.
- Archive/move/trash read-back now resolves the exact destination mailbox and
  RFC Message-ID with bounded SQL instead of enumerating the destination and
  recursively rescanning the Mail tree. Duplicate identity remains a
  fail-closed result.

## 0.1.0+codex.20260714101408 - 2026-07-14

v1.183 Mail discovery performance and index state (read-side; driven by a
downstream Codex agent field report of slow scans, silent false negatives,
never-finishing FTS builds, `content_unavailable` for visible messages, and
reply identity failures). Design:
`docs/V1_183_MAIL_DISCOVERY_PERFORMANCE_AND_INDEX_STATE_DESIGN.md`.

### Added

- `mail_fts_status` MCP tool and `local-apple-data mail fts-status` CLI
  command: read-only Mail FTS index state (`missing`/`building`/`partial`/
  `ready`/`stale`) with `indexed_docs_total`, in-range Envelope message count,
  built range, `checkpoint_cursor` resume token, `last_build_at`, and
  stale-fingerprint row count. `mail_build_fts_index` now records the same
  build state and checkpoint in `mail_fts_meta` transactionally with every
  page, and `mail_search_fts` embeds an `index_state` block plus a
  `mail_fts_partial_coverage` warning whenever coverage is not `ready`, so an
  interrupted index can no longer answer zero rows silently.
- `max_seconds` scan time budget (default 20s, bounded 1-120) on
  `mail_search_body`, `mail_search_attachments`, `mail_search_advanced`, and
  `mail_build_fts_index` (CLI `--max-seconds`), stopping cleanly with an
  accurate `next_cursor` and a `scan_time_budget_reached` warning. All Mail
  discovery payloads gain a `scan` block: `scanned`, `range_total` (Envelope
  messages inside the date bounds), `elapsed_ms`, and `stopped_reason`
  (`exhausted`/`result_limit`/`scan_limit`/`build_limit`/`time_budget`).
- Partial-download honesty: `{rowid}.partial.emlx` message files (majority of
  a live IMAP store) are now discovered. `content_status` gains `"partial"`,
  `mail_get_content` reads partial bodies with a `partial_download` warning,
  and reply/triage identity recovers the RFC Message-ID from partial files'
  headers. `message_identity_unavailable` plan warnings now say whether the
  local file is missing entirely or lacks an RFC Message-ID header.
- Per-account attribution: search/content results now include the hashed
  `account_ref` (the same pseudonymous ref plan flows already exposed) and
  `mailbox_path` alongside `mailbox_name`/`mailbox_ref`.

### Changed

- Replaced the per-message full-tree `glob("**/Messages/{rowid}.emlx")` with a
  single `os.walk` message-file index shared by body/attachment/advanced
  search, FTS build/search verification, content-status annotation, and exact
  content reads. Measured on the live store (126k messages, ~500k tree
  entries): advanced body search 200 rows/149s -> 2000 rows/6.5s per page;
  FTS build ~500 messages/20-30min -> 1000 messages/3.9s per page; subject
  search 5.2s -> 2.4s. `MAX_MAIL_DISCOVERY_SCAN_ROWS` raised 200 -> 2000 under
  the time budget. The FTS build also reads each message file once instead of
  three times.

## 0.1.0+codex.20260710052535 - 2026-07-09

v1.182 Notes folder content export (operator-requested: unlocks the approved
Tier-7 Notes ingestion into the operator's private downstream store; revises
the prior "no broad or bulk body dumps" Notes boundary under the 2026-07-07
body-level ingest approval and the 2026-07-09 green light).

### Added

- `notes_export_folder_content` MCP tool and `local-apple-data notes
  export-content` CLI command: bounded (limit <= 20 notes/page, <= 12000
  chars/note), offset-paged (`next_cursor`), date-bounded (`modified_after`
  required ISO-8601), `confirm_bulk`-gated plain-text export for one exact
  normal `notes:folder:v1:` folder. Each exported note returns folder-item
  metadata plus bounded `content_text` and a full-text `content_sha256` for
  downstream incremental sync; unreadable notes come back as metadata-only
  `content_status:"skipped"` entries and the page continues. Password-protected
  and deleted notes are excluded in SQL; smart folders fail closed; the server
  persists nothing. Privacy payload adds `bulk_content_returned` so the
  redacted event log distinguishes bulk reads from exact-handle reads. Design:
  `docs/V1_182_NOTES_FOLDER_CONTENT_EXPORT_DESIGN.md`; 7 synthetic-fixture
  tests in `tests/test_notes_export_content.py`.

### Changed

- Operator docs and `docs/PRIVACY_MODEL.md` Notes boundaries revised to carve
  out exactly this gate ("No other broad or bulk body dumps and no broad body
  search" stands).

## 0.1.0+codex.20260707094952 - 2026-07-07

v1.181 Reminders list enumeration + sharing visibility (operator-requested
after a real incident where an agent, unable to enumerate lists, wrote items
onto a shared list and could not diagnose the failed move out of it).

### Added

- `reminders_list_lists` MCP tool and `local-apple-data reminders lists` without
  `--query`: read-only, capped (default 20, max 50) enumeration of ALL Reminders
  lists with the same metadata shape as `reminders_search_lists` results, plus a
  `results_truncated` warning when more lists exist than the requested limit.
- Reminders list metadata now includes `is_shared` and `sharee_count` everywhere
  list metadata is returned (`reminders_search_lists`, `reminders_list_lists`,
  `reminders_get_list`, selected-list and list-management read-backs). Detection
  probes EventKit's `EKCalendar` sharing accessors (`sharingStatus`, `sharees`,
  `sharedOwnerName`) behind responds-to guards; only the boolean and the count
  are returned, never sharee identities. When no accessor is available,
  `is_shared` is `null` (unknown), never a false "not shared".

### Changed

- `reminders_apply_change` `move_to_list`: when EventKit rejects the save and
  the source list is detected as shared, the failure now returns the specific
  `shared_list_move_unsupported` warning recommending the create-on-target plus
  guarded-delete fallback, instead of the generic `eventkit_apply_failed`. The
  `reminders_plan_change`/`reminders_apply_change` tool descriptions document
  the limitation.

## 0.1.0+codex.20260705124117 - 2026-07-05

### Fixed

- Signing is now resilient and non-destructive when a stable identity is
  configured but not currently usable by `codesign` (locked login keychain,
  missing/duplicate private key, or an unrelated leftover certificate):
  - `_ensure_*_helper_app` signs through the new `_signing.sign_helper_app`,
    which retries with an ad-hoc signature when the stable attempt fails rather
    than raising. The helper still builds and runs for non-prompting reads; only
    the TCC prompt requires a usable stable identity. Previously a stable-but-
    unusable identity bricked the whole access path with no self-healing.
  - `invalidate_app_if_signing_mismatch` never removes a working helper when no
    usable stable identity is available (it would only force an ad-hoc rebuild
    that orphans an existing TCC grant), and is now authority-*name* aware, so
    switching to a different identity via `LOCAL_APPLE_DATA_SIGNING_IDENTITY`
    (e.g. an Apple Development cert) forces a rebuild instead of being ignored.
- `signing_identity()` matches the conventional certificate by *exact* common
  name instead of `security find-certificate`'s case-insensitive substring, so
  an unrelated cert whose name merely contains "Local Apple Data Signing" is no
  longer mistaken for it.

### Security

- The provisioned code-signing key is now imported with `-T /usr/bin/codesign`
  only (the `-A` "any application" flag was removed), scoping its keychain ACL
  to `codesign` rather than granting silent use of the trusted signing identity
  to every process running as the user. The first `codesign` use triggers a
  one-time keychain "Always Allow" prompt (documented one-time setup).

### Changed

- Identity provisioning is serialized with a filesystem lock and re-checks for
  an existing identity after acquiring it, so two concurrent request-access
  calls can no longer create duplicate same-CN identities (which would make
  `codesign -s <name>` ambiguous).
- Added a Reminders request-access provisioning-gate test mirroring the Calendar
  and Photos coverage, and made the helper bundle-id assertions tolerant of an
  operator bundle-id override.

## 0.1.0+codex.20260705103507 - 2026-07-05

### Fixed

- The EventKit (Calendar/Reminders) TCC permission prompt now presents on
  macOS 26. Two changes were required together: (1) the helper app runs a
  real `NSApplication`/`NSApplicationDelegate` lifecycle (the access request
  is issued from `applicationDidFinishLaunching` and the process is driven by
  `NSApplication.run()`), and (2) the helper is signed with a stable
  code-signing identity instead of ad-hoc. An ad-hoc signature has no stable
  designated requirement, so `tccd` never presented the EventKit prompt
  (PhotoKit tolerated the ad-hoc path; EventKit did not). This supersedes the
  prior release's "Known limitation". Proven end to end with a minimal
  proof-of-concept app (full grant obtained) and confirmed the shipping
  helper presents the system prompt.

### Added

- `src/local_apple_data/adapters/_signing.py`: shared signing helpers used by
  both the EventKit and Photos helpers. `signing_identity()` resolves the
  identity (the `LOCAL_APPLE_DATA_SIGNING_IDENTITY` env override, else a
  conventional self-signed `Local Apple Data Signing` certificate, else
  ad-hoc). `codesign_command()` emits a hardened-runtime entitled sign command
  when an identity exists and an ad-hoc fallback otherwise.
  `provision_local_signing_identity()` idempotently creates the conventional
  self-signed code-signing certificate in the login keychain (via `openssl` +
  `security import`) so a fresh machine can obtain a stable identity with no
  manual certificate setup; it never raises and no-ops when `openssl` or
  `security` are unavailable.

### Changed

- The Photos helper is now signed with the same stable identity as the
  EventKit helper (previously ad-hoc), so a granted Photos authorization
  survives helper rebuilds instead of being orphaned by code-directory-hash
  churn.
- `calendar request-access` and `reminders request-access` provision the
  signing identity and rebuild the helper with the stable signature before
  presenting the prompt. Read and mutation paths are unchanged and never
  provision.

### One-time setup

- Obtaining the live Calendar/Reminders (and Photos) grant is a one-time user
  action: run `local-apple-data calendar request-access` (and `reminders`,
  `photos`) once, approve the login-keychain "Always Allow" dialog for the new
  signing key, then click "Allow Full Access" on the system prompt. See
  `docs/MACOS_SUPPORT.md`. Operators who prefer an Apple Development identity
  can set `LOCAL_APPLE_DATA_SIGNING_IDENTITY` instead.

## 0.1.0+codex.20260704211937 - 2026-07-04

### Changed

- The EventKit helper app is now signed with the
  `com.apple.security.personal-information.calendars` and `.reminders`
  entitlements (mirroring the Photos helper's photos-library entitlement),
  and its validity check requires them so a stale unentitled build rebuilds.

### Known limitation

- Live Calendar/Reminders TCC authorization still cannot be obtained on
  macOS 26 through this helper: the permission prompt is not reliably
  presented for the `open`-launched, ad-hoc-signed accessory app (PhotoKit's
  prompt presents on the same path; EventKit's does not). The entitlements
  above are necessary groundwork but not sufficient. A durable fix likely
  requires a properly-built/signed `.app` with a real NSApplicationMain/app
  lifecycle or an alternate grant path. Calendar/Reminders remain
  mock-validated only.

## 0.1.0+codex.20260704210830 - 2026-07-04

### Changed

- `scripts/run_mcp_server.sh` now sources an optional, gitignored
  `.env.local` from the project root before launching the server, so an
  operator can pin machine-specific values (e.g.
  `LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID` /
  `LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID`) to preserve an existing TCC
  grant across the generic-bundle-ID default. The file never ships.

## 0.1.0+codex.20260704142952 - 2026-07-04

### Fixed

- Photos helper no longer crashes (SIGTRAP) when an output write fails. The
  `emit` path in `scripts/photos_helper.swift` replaced both force-`try!`
  calls with graceful do/catch: JSON serialization falls back to a minimal
  error payload, and an output-file write failure (e.g. the caller's temp dir
  was removed after a timeout) falls back to stdout and a clean nonzero exit
  instead of trapping. Payloads are JSON-sanitized (dates → ISO8601, non-finite
  doubles dropped, keys stringified) so serialization cannot throw.

### Changed

- Photos read operations tolerate cold PhotoKit initialization: the helper
  timeout is raised to 60s and read operations retry once on timeout (the warm
  retry is fast). Apply/mutation operations do not retry on timeout — a single
  timeout surfaces as a degraded result with no second mutation attempt.

## 0.1.0+codex.20260704141250 - 2026-07-04

### Changed

- Publication sanitization: the public release artifact is now agnostic of any
  specific operator. Signed-helper bundle IDs default to a generic
  `com.local-apple-data.{eventkit,photos}-helper` and are overridable via
  `LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID` /
  `LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID` (set these to preserve an existing
  TCC grant across a bundle-ID change). Authorship in `LICENSE`,
  `pyproject.toml`, and `.codex-plugin/plugin.json` is now the neutral
  "local-apple-data contributors" / "The local-apple-data authors".
- Operator-only session/handoff docs are excluded from the public release tree
  (public tree: 305 files); retained user-facing docs were sanitized of
  personal bundle IDs and paths.

### Safety

- `scripts/public_release_scan.py` now fails on personal identifiers — the
  operator's name tokens, `com.<name>` bundle prefixes, the private remote
  name, unmasked personal `@icloud/@me/@mac.com` addresses, and non-generic
  `/Users/<name>` paths — while ignoring masked forms, the Apple privaterelay
  domain constant, and synthetic `@example.*` fixtures. The public tree is
  verified to contain zero personal identifiers across name, bundle ID, path,
  email, phone, host, and git-remote classes.

## 0.1.0+codex.20260703223047 - 2026-07-03

### Changed

- Contacts custom field labels are now free-form: preserved verbatim (exact
  case, spaces, punctuation) up to 255 chars instead of being lowercased and
  underscore-normalized at a 64-char cap. Control characters and NUL are
  rejected; oversize labels are rejected. Swift create-idempotency and
  read-back matching updated to compare labels verbatim to match.
- Added a gated Shortcuts run surface: new `shortcuts_plan_run` (read-only
  preview) and `shortcuts_apply_run` (destructive) MCP tools and `shortcuts
  plan` / `shortcuts apply` CLI verbs. Tool count 145 → 147.

### Safety

- Shortcuts run is arbitrary local code execution and is gated like the most
  dangerous mutations: plan/apply with a matching `shortcuts-apply:v1:`
  approval token plus explicit confirmation; the shortcut is resolved by an
  exact `shortcuts:item:v1:` handle (never a raw/fuzzy name) with the resolved
  identifier and input SHA bound into the approval fingerprint; input is
  bounded, NUL-rejected, and passed via a temp file over argv (never a shell
  string); invocation uses the absolute `/usr/bin/shortcuts` path; a hard
  timeout bounds hung runs. The preview states that a shortcut's side effects
  are arbitrary and not verifiable by read-back — the gate proves invocation
  of the named shortcut only.

### Not shipped

- Safari bookmark create/edit/delete was investigated and refused: Safari's
  scripting dictionary exposes no bookmark class or create/edit/delete
  commands (only an append-only Reading List item), and its `Bookmarks.plist`
  is CloudKit-synced, so a direct plist write risks account-wide sync
  corruption and has no safe, read-back-provable path. It remains deferred
  with this evidence.

## 0.1.0+codex.20260703212355 - 2026-07-03

### Changed

- Added Notes rich-text body read and write: `notes_get_content` gains a
  `content_format:html` mode returning the bounded HTML body plus extracted
  text for one exact note handle, and `notes_plan_change`/`notes_apply_change`
  gain `create_html` and `replace_html` operations. Existing plaintext note
  operations are unchanged. Operator-authorized reversal of the prior
  metadata/plaintext-only Notes body policy.

### Safety

- Body read stays behind the exact `notes:note:v2:` handle gate, capped at
  24000 HTML chars with a truncation flag; no broad body search.
- Rich-text create/replace sanitize the input HTML (strip
  script/style/iframe/object/embed/svg/math and event-handler attributes,
  drop javascript:/vbscript:/data: URIs) at both plan and apply time, and
  reject bodies containing NUL or C0 control characters so a control-byte tag
  cannot evade the sanitizer.
- Because Notes.app rewrites stored HTML, read-back proof is semantic: the
  saved body's extracted plain text must match the proposed body's extracted
  text at the expected handle. `replace_html` binds the expected
  extracted-plain-text SHA and refuses on drift.

## 0.1.0+codex.20260703202227 - 2026-07-03

### Changed

- Added a home-directory filesystem CRUD surface: new `filesystem_*` MCP tools
  and `filesystem` CLI verbs (search, root, metadata, list, tree, content,
  export, plan, apply) rooted at the operator home directory, reusing the
  iCloud Drive gate machinery with a distinct `fs:file:v1:` handle namespace
  and `filesystem-apply:v1:` approval tokens. The existing iCloud Drive tools
  and `icloud:file:v1:` handles are unchanged. Tool count 136 → 145.

### Safety

- Every target resolves within the home root after symlink resolution;
  out-of-home, other-user, and system paths, and dot-dot/symlink escapes, are
  refused.
- A credential denylist (~/.ssh, ~/.aws, ~/.gnupg, ~/.config/gh,
  ~/.config/gcloud, ~/.netrc, ~/.docker/config.json, ~/.kube,
  ~/Library/Keychains, ~/Library/Application Support/com.apple.TCC, and
  .env/.env.*) refuses content-read, export, and all mutation — checked
  against the composed effective destination (parent + filename /
  folder-components / rename-or-move target) and the source, not just raw
  handles, so writes cannot be composed into a sealed directory. Metadata-only
  listing is still allowed. The denylist is a pure in-adapter path-component
  guard (no reliance on OS permissions) and is operator-overridable via
  `LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS=1`.
- All existing per-operation gates are preserved: no-overwrite, expected
  metadata/SHA binding, reversible ~/.Trash for trash ops, and hidden-staging
  plus absence proof for permanent delete.

## 0.1.0+codex.20260703190506 - 2026-07-03

### Changed

- Added Reminders start-date set/clear and recurrence create/update/clear
  through new `create_with_start_date`, `update_start_date`,
  `create_with_recurrence`, and `update_recurrence` operations on the existing
  `reminders_plan_change` / `reminders_apply_change` gate, reusing the shared
  EventKit recurrence-rule builder.

### Safety

- Start-date set/clear binds expected current start-date state and proves the
  exact start date or absence on read-back; start date must not fall after the
  due date.
- Recurrence create/update/clear requires a due-date anchor (EventKit
  reminders only recur with a due date), binds expected recurrence state, and
  proves the resulting rule or its absence on read-back; recurrence operations
  never carry a start date.
- Existing Reminders operations are behavior-unchanged.

## 0.1.0+codex.20260703161320 - 2026-07-03

### Changed

- Added Reminders exact mixed absolute-plus-relative display-alarm set/clear
  through a new `set_mixed_display_alarm` operation on the existing
  `reminders_plan_change` / `reminders_apply_change` gate.

### Safety

- Mixed display-alarm set/clear requires one exact Reminder handle, expected
  title, expected completed state, expected alarm count, expected alarm-state
  SHA-256 when present, bounded relative offsets plus timezone-explicit
  absolute alarm dates under a combined cap, EventKit apply, exact mixed
  offset/date read-back or absence proof, and no raw alarm state return.
- Audio, email, geofence, procedure, and proximity-bearing Reminder alarm
  states stay refused; approved absolute-only and relative-only paths are
  behavior-unchanged.

## 0.1.0+codex.20260703152147 - 2026-07-03

### Changed

- Added Calendar future-series target-calendar move updates through
  `recurrence_update_scope:future_events` on the existing
  `calendar_plan_change` / `calendar_apply_change` gate, completing
  future-series parity with the selected-occurrence update family.

### Safety

- Future-series target-calendar move requires exact previous/selected/future
  occurrence identity binding, one exact `calendar:calendar:v1:` target
  handle, EventKit `.futureEvents` apply, selected/future recurrence-shape
  plus target-calendar read-back proof, and previous-occurrence
  original-calendar preservation proof.
- Recurrence clear and mid-series recurrence replacement now explicitly
  refuse target-calendar input at the helper layer.
- Scalar edits, timed reschedule, availability edits, event URL edits,
  structured-location edits, alarm changes, all-day conversion, and
  recurrence changes stay blocked on this path.

## 0.1.0+codex.20260703142041 - 2026-07-03

### Changed

- Added Calendar future-series all-day set, all-day-to-timed clear, and
  same-state all-day date-only reschedule updates through
  `recurrence_update_scope:future_events` on the existing
  `calendar_plan_change` / `calendar_apply_change` gate.

### Safety

- Future-series all-day set/clear/date-only reschedule requires exact
  previous/selected/future occurrence identity binding, exact expected
  all-day/time-zone state binding, date-only proposed start/end for all-day
  set or date-only reschedule, `expected_time_zone` for timed-to-all-day set,
  explicit proposed `time_zone` for all-day-to-timed clear, EventKit
  `.futureEvents` apply, selected/future recurrence-shape plus all-day
  read-back proof, original selected/future slot
  absence-or-approved-replacement proof, and previous-occurrence preservation
  proof.
- Future-occurrence read-back slots for all-day conversions use DST-safe
  calendar-day arithmetic instead of absolute time intervals.
- Scalar edits, timed co-reschedule, availability edits, event URL edits,
  structured-location edits, alarm changes, recurrence changes, and
  target-calendar moves stay blocked on this path.

## 0.1.0+codex.20260703130402 - 2026-07-03

### Changed

- Added Calendar future-series action-alarm set/clear updates (audio
  sound-name, email, and structured geofence alarms) through
  `recurrence_update_scope:future_events` on the existing
  `calendar_plan_change` / `calendar_apply_change` gate.

### Safety

- Future-series action-alarm set/clear requires exact
  previous/selected/future occurrence identity binding, exact expected
  display/audio/email/geofence alarm state binding, explicit proposed
  trigger/action state, EventKit `.futureEvents` apply, selected/future
  recurrence-shape plus action-alarm read-back or absence proof, and
  previous-occurrence preservation proof.
- Raw alarm email addresses are accepted only as plan/apply input; all
  preview, read-back, and log output carries only
  `alarm_email_address_sha256`.
- Scalar edits, timed reschedule, availability edits, event URL edits,
  structured-location edits, recurrence changes, all-day conversion,
  target-calendar moves, and procedure alarms stay blocked on this path.

## 0.1.0+codex.20260703120605 - 2026-07-03

### Changed

- Added Calendar future-series display-alarm set/clear updates through
  `recurrence_update_scope:future_events` on the existing
  `calendar_plan_change` / `calendar_apply_change` gate.
- Excluded local `.claude/` session state from the public release tree and
  public release scan.

### Safety

- Future-series display-alarm set/clear requires exact
  previous/selected/future occurrence identity binding, bounded relative
  `alarm_offsets_minutes` or absolute `alarm_absolute_dates` input or
  display-alarm clear with exact expected display-alarm state binding,
  EventKit `.futureEvents` apply, selected/future recurrence-shape plus
  display-alarm read-back or absence proof, and previous-occurrence
  preservation proof.
- Scalar edits, timed reschedule, availability edits, event URL edits,
  structured-location edits, action-alarm (audio/email/geofence) changes,
  recurrence changes, all-day conversion, and target-calendar moves stay
  blocked on this path.

## 0.1.0+codex.20260703105436 - 2026-07-03

### Changed

- Added Calendar future-series structured-location set/clear updates through
  `recurrence_update_scope:future_events` on the existing
  `calendar_plan_change` / `calendar_apply_change` gate.

### Safety

- Future-series structured-location set/clear requires exact
  previous/selected/future occurrence identity binding, bounded
  `structured_location` input or `clear_structured_location` with exact
  expected structured-location binding for clear, EventKit `.futureEvents`
  apply, selected/future recurrence-shape plus structured-location read-back or
  absence proof, and previous-occurrence preservation proof.
- Scalar edits, timed reschedule, availability edits, event URL edits,
  recurrence changes, all-day conversion, target-calendar moves, and alarm
  co-mutation stay blocked on this path.

## 0.1.0+codex.20260703095302 - 2026-07-03

### Changed

- Added Calendar future-series event URL set/clear updates through
  `recurrence_update_scope:future_events` on the existing
  `calendar_plan_change` / `calendar_apply_change` gate.

### Safety

- Future-series event URL set/clear requires exact previous/selected/future
  occurrence identity binding, exact expected/proposed URL state, EventKit
  `.futureEvents` apply, selected/future hash-only URL read-back or absence
  proof, no raw URL return, and previous-occurrence preservation proof.
- Scalar edits, timed reschedule, recurrence changes, all-day conversion,
  target-calendar moves, structured-location, alarm,
  attendee/invitation, travel time, procedure alarm, non-synthetic calendar
  management, and network/iCloud/browser fallback remain blocked on this path.

## 0.1.0+codex.20260703080910 - 2026-07-03

### Changed

- Added Calendar future-series timed reschedule through
  `recurrence_update_scope:future_events` on the existing
  `calendar_plan_change` / `calendar_apply_change` gate.

### Safety

- Future-series timed reschedule requires exact previous/selected/future
  occurrence identity binding, explicit expected/proposed time zones, EventKit
  `.futureEvents` apply, selected/future timed read-back proof, old selected
  and future slot absence-or-approved-replacement proof when dates move, and previous-occurrence
  preservation proof.
- All-day conversion, target-calendar moves, availability, event URL,
  structured-location, alarm, attendee/invitation, travel time, procedure
  alarm, non-synthetic calendar management, and network/iCloud/browser fallback
  remain blocked on this path.

## 0.1.0+codex.20260703071130 - 2026-07-03

### Changed

- Added Calendar future-series scalar updates through
  `recurrence_update_scope:future_events` on the existing
  `calendar_plan_change` / `calendar_apply_change` gate.

### Safety

- Future-series updates require one selected recurring occurrence, exact
  expected recurrence, previous/selected/future occurrence identity binding,
  EventKit `.futureEvents` apply, selected/future recurrence-shape plus scalar
  read-back proof, and previous-occurrence preservation proof.
- Recurrence changes, time/all-day/time-zone changes, target-calendar moves,
  availability, event URL, structured-location, alarms, attendees/invitations,
  travel time, procedure alarms, non-synthetic calendar management, and
  network/iCloud/browser fallback remain blocked on this path.

## 0.1.0+codex.20260703055927 - 2026-07-03

### Changed

- Added exact selected Mail mailbox message metadata through
  `mail_list_mailbox_messages` and
  `local-apple-data mail mailbox-messages`.

### Safety

- Selected-mailbox message listing requires one exact `mail:mailbox:v1:`
  handle plus an explicit date bound, caps output at 50, and returns message
  metadata only.
- Message bodies, full headers, raw Mail paths, raw account IDs, unbounded
  mailbox dumps, mutation shortcutting, and network/Gmail/iCloud/browser
  fallback remain blocked.

## 0.1.0+codex.20260703051912 - 2026-07-03

### Changed

- Added exact selected Contacts container member metadata through
  `contacts_list_container_members` and
  `local-apple-data contacts container-members`.

### Safety

- Container-member listing requires one exact `contacts:container:v1:` handle,
  caps output at 50, and returns only contact metadata with opaque contact
  handles.
- Raw container IDs, raw contact IDs, email/phone/postal/URL values, note text,
  image bytes, broad Contacts dumps, raw identifier input, direct database
  writes, duplicate merge automation, and network/iCloud/browser fallback remain
  blocked.

## 0.1.0+codex.20260703044915 - 2026-07-03

### Changed

- Added exact selected Calendar target event metadata through
  `calendar_list_calendar_events` and `local-apple-data calendar events`.

### Safety

- Selected-calendar event listing requires one exact `calendar:calendar:v1:`
  handle plus explicit start/end bounds, caps one request to 366 days and 50
  events, and returns only event metadata with opaque event handles.
- Raw EventKit calendar IDs, raw event IDs, event notes, event location text,
  attendee names/URLs, event URL values, raw alarm detail, broad Calendar dumps,
  mutation shortcutting, and network/iCloud/browser fallback remain blocked.

## 0.1.0+codex.20260703041310 - 2026-07-03

### Changed

- Added exact selected Contacts group member metadata through
  `contacts_list_group_members` and `local-apple-data contacts group-members`.

### Safety

- Group-member listing requires one exact `contacts:group:v1:` handle, caps
  output at 50, and returns only contact metadata with opaque contact handles.
- Raw group IDs, raw member IDs, email/phone/postal/URL values, note text, image
  bytes, broad Contacts dumps, raw identifier input, direct database writes,
  duplicate merge automation, and network/iCloud/browser fallback remain
  blocked.

## 0.1.0+codex.20260703034853 - 2026-07-03

### Changed

- Added exact iCloud Drive root metadata selection through
  `icloud_drive_get_root` and `local-apple-data icloud-drive root`.

### Safety

- Root selection returns an opaque `icloud:file:v1:` directory handle with
  `is_root:true` and no raw path or content.
- Root handles are allowed for read/list/tree and approved create/import parent
  targeting only; folder rename, Trash, delete, move, and copy reject the root
  as a source.
- Broad dumps, raw path selection, unbounded recursive listing, empty Trash,
  root mutation, and network/iCloud/browser fallback remain blocked.

## 0.1.0+codex.20260703031530 - 2026-07-03

### Changed

- Added exact selected Reminders list item metadata through
  `reminders_list_items` and `local-apple-data reminders list-items`.

### Safety

- List-items requires one exact `reminders:list:eventkit:v1:` handle, fetches
  only that EventKit list, caps output, defaults to incomplete reminders, and
  returns only reminder metadata with opaque handles.
- Reminder notes, raw EventKit identifiers, raw URLs, raw alarm detail, broad
  Reminder dumps, attachment/rich-content retrieval, mutation, and network or
  iCloud fallback remain blocked.

## 0.1.0+codex.20260703025124 - 2026-07-03

### Changed

- Added Notes selected-folder bounded child-folder tree listing through
  `notes_list_folder_tree` and `local-apple-data notes folder-tree`.

### Safety

- Tree listing requires one exact `notes:folder:v1:` handle, rejects invalid and
  smart-folder roots, caps depth and descendant count, and returns only
  descendant folder metadata.
- Notes, snippets, note bodies, attachment bytes, raw folder IDs, account
  identifiers, paths, account management, broad dumps, mutation, iCloud.com,
  private iCloud APIs, browser sessions, keychain credentials, and network
  fallback remain blocked.

## 0.1.0+codex.20260703020448 - 2026-07-03

### Changed

- Added Notes selected-folder direct item listing through
  `notes_list_folder_items` and `local-apple-data notes folder-items`.

### Safety

- Listing requires one exact `notes:folder:v1:` handle, rejects invalid and
  smart-folder handles, caps output, and returns only direct child folder
  metadata plus direct note metadata.
- Note bodies, snippets, attachment bytes, raw folder IDs, account identifiers, broad
  recursive folder dumps, raw database IDs, iCloud.com, private iCloud APIs,
  browser sessions, keychain credentials, and network fallback remain blocked.

## 0.1.0+codex.20260703012812 - 2026-07-03

### Changed

- Added Notes `move_folder` / `move-folder` for one exact empty child folder
  into one exact same-account destination folder through existing
  `notes plan/apply` and `notes_plan_change` / `notes_apply_change` gates.

### Safety

- Folder move requires exact source and destination `notes:folder:v1:` handles,
  a source title SHA-256 binding, matching approval token, explicit
  confirmation, same-account proof, empty-source proof, and destination-parent
  read-back proof.
- Root, smart, shared, non-empty, recursive, already-applied, cross-account,
  raw-ID, note-handle, body/title input, broad folder management, rich text,
  attachment mutation, iCloud.com, private iCloud APIs, browser sessions,
  keychain credentials, and network fallback remain blocked.

## 0.1.0+codex.20260702233348 - 2026-07-02

### Changed

- Added bounded iCloud Drive `create_folder_path` through the existing
  `icloud-drive plan/apply` CLI and `icloud_drive_plan_change` /
  `icloud_drive_apply_change` MCP gate.

### Safety

- Folder-path create requires one exact `icloud:file:v1:` parent directory
  handle, plan-time stable parent identity binding, one to three bounded
  `folder_components`, a matching approval token, and explicit confirmation.
- Apply uses fd-based no-follow `mkdir` per component, treats existing
  directories as idempotent, reports `partial` if a later failure happens after
  an earlier component was created, and returns final directory metadata only
  with `content_text_returned:false`, `content_hash_returned:false`, and no raw
  path or content return.
- Raw paths, slash-delimited path strings, hidden names, package names,
  symlinks, unsupported filesystem entries, unbounded recursive folder writes,
  overwrite, delete, copy, move, content writes, iCloud.com, private iCloud
  APIs, browser sessions, keychain credentials, and network fallback remain
  blocked.

## 0.1.0+codex.20260702222115 - 2026-07-02

### Changed

- Added exact Reminders `delete_list_with_migration` list management through
  `reminders plan-list` / `reminders apply-list` and MCP
  `reminders_plan_list_change` / `reminders_apply_list_change`.

### Safety

- Migration delete requires exact source and target
  `reminders:list:eventkit:v1:` handles, same EventKit source, writable
  non-subscribed reminder-only state, source/target safe-hash binding,
  source/target count binding, and a matching approval token plus explicit
  apply confirmation.
- Apply moves every source reminder to the exact target list, verifies the
  source list is empty and the target count increased, deletes the source list,
  and returns absence proof without raw EventKit identifiers or reminder
  content.
- Cross-source migration, account/source management, sharing, bulk list
  operations, attachments, images, and rich-content mutation remain blocked.

## 0.1.0+codex.20260702214458 - 2026-07-02

### Changed

- Broadened Reminders list management from synthetic-only `LAD-TEST-*` titles to
  exact ordinary list create/rename/empty-delete through the existing
  `reminders plan-list` / `reminders apply-list` gate and MCP
  `reminders_plan_list_change` / `reminders_apply_list_change`.

### Safety

- Create requires an exact source `reminders:list:eventkit:v1:` handle, bounded
  title, duplicate-title refusal, and source safe-hash binding.
- Rename/delete require an exact target list handle, writable non-subscribed
  reminder-only target state, empty-list proof, duplicate-title refusal for
  rename, EventKit apply, and source/title/absence read-back proof.
- Account/source management, sharing/cross-source management, non-empty list
  delete, reminder migration, attachments, images, rich-content mutation, and
  bulk list operations remain blocked.

## 0.1.0+codex.20260702201421 - 2026-07-02

### Changed

- Broadened Photos album management from synthetic-only to exact regular-album
  create/rename/delete through the existing `photos plan/apply` gate and
  `photos_apply_change` MCP tool.

### Safety

- Create/rename require bounded non-empty titles and duplicate-title absence
  proof. Rename/delete require an exact `photos:album:v1:` handle plus expected
  album-state binding. Delete remains limited to empty regular albums with
  absence proof.
- The helper now requires full Photos Library authorization for regular-album
  management; limited Photos access returns `photos_full_access_required`.
- Smart/shared/synced album targeting, permanent delete/Recently Deleted empty,
  content edits, raw PhotoKit identifiers, paths, thumbnails, inline asset
  bytes, network iCloud fetch, and bulk album membership remain blocked.

## 0.1.0+codex.20260702194816 - 2026-07-02

### Changed

- Added Photos synthetic `LAD-TEST-*` regular-album create/rename/delete
  through the existing `photos plan/apply` gate and `photos_apply_change` MCP
  tool.

### Safety

- Create/rename require synthetic `LAD-TEST-*` titles and duplicate-title
  absence proof. Rename/delete require an exact `photos:album:v1:` handle plus
  expected album-state binding. Delete requires an empty album and returns
  absence proof.
- The Swift PhotoKit helper rechecks duplicate titles at apply time and reports
  title-scan/result truncation so uniqueness cannot be guessed from a capped
  result set.
- Real/non-synthetic album management, smart/shared/synced albums, bulk album
  membership, permanent delete/Recently Deleted empty, content edits, raw
  PhotoKit identifiers, paths, thumbnails, and inline asset bytes remain
  blocked.

## 0.1.0+codex.20260702183018 - 2026-07-02

### Changed

- Added exact selected Photos regular-album asset metadata through
  `photos_list_album_assets` and `local-apple-data photos album-assets`.

### Safety

- The new Photos album-assets path requires one opaque `photos:album:v1:`
  handle from the regular-album metadata flow and returns capped child asset
  metadata only.
- It does not return asset resources, bytes, thumbnails, local paths, raw
  PhotoKit identifiers, or broad Photos dumps. Photos mutation remains limited
  to the existing approved plan/apply gates.

## 0.1.0+codex.20260702173732 - 2026-07-02

### Changed

- Added exact selected-folder Apple Shortcuts shortcut metadata through
  `shortcuts_list_folder_items` and `local-apple-data shortcuts folder-items`.
- Fixed exact Shortcuts metadata retrieval so handles from global,
  shortcut-only, and folder-only search flows resolve consistently.

### Safety

- The new Shortcuts folder-items path requires one opaque `shortcuts:item:v1:`
  folder handle from the Shortcuts metadata flow. It uses a privately resolved
  folder identifier internally, but callers never pass or receive raw
  identifiers.
- Output is limited to shortcut names, kinds, opaque handles, and
  identifier-presence booleans. Shortcut bodies/action graphs, raw identifiers,
  run/open/view/sign/export, arbitrary folder-name filters, SQLite scraping,
  and mutation remain blocked.

## 0.1.0+codex.20260702165916 - 2026-07-02

### Changed

- Added Safari bookmark-folder metadata search, exact folder detail, and exact
  selected-folder direct child listing through `safari_search_folders`,
  `safari_get_folder`, `safari_list_folder_items`, and
  `local-apple-data safari folders/folder/folder-items`.

### Safety

- The new Safari folder paths return folder titles/counts and direct child item
  metadata only. Full URLs remain exact `safari:item:v1:` detail only.
- Safari history, open tabs, private browsing data, passwords, cookies, page
  content, broad dumps, and bookmark/folder mutation remain blocked.

## 0.1.0+codex.20260702163249 - 2026-07-02

### Changed

- Added exact selected-folder Apple Freeform child-folder metadata through
  `freeform_list_child_folders` and `freeform child-folders`.

### Safety

- The new Freeform path requires one opaque `freeform:folder:v1:` handle from
  the folder metadata flow and returns capped direct child-folder metadata only.
- Board BLOBs, decoded board items, asset bytes, previews, collaboration
  payloads, raw Freeform identifiers, raw rows, broad Freeform dumps, and
  Freeform mutation remain blocked.

## 0.1.0+codex.20260702161003 - 2026-07-02

### Changed

- Added exact selected-folder Apple Freeform board metadata through
  `freeform_list_folder_boards` and `freeform folder-boards`.

### Safety

- The new Freeform path requires one opaque `freeform:folder:v1:` handle from
  the folder metadata flow and returns capped board metadata only for boards
  directly in that selected folder.
- Board BLOBs, decoded board items, asset bytes, previews, collaboration
  payloads, raw Freeform identifiers, raw rows, broad Freeform dumps, and
  Freeform mutation remain blocked.

## 0.1.0+codex.20260702154841 - 2026-07-02

### Changed

- Added exact selected-playlist Apple TV item metadata through
  `tv_list_playlist_items` and `tv playlist-items`.

### Safety

- The new TV path requires one opaque `tv:playlist:v1:` handle from the playlist
  metadata flow, returns capped item metadata only, and does not expose raw TV
  identifiers, file paths, video bytes, artwork, descriptions, playback state,
  watched state, or ratings.
- Broad TV library dumps, broad playlist item dumps, playback/queue control, TV
  mutation, raw `.tvdb` parsing, and iCloud media fetches remain blocked.

## 0.1.0+codex.20260702151319 - 2026-07-02

### Changed

- Added exact selected-playlist Apple Music track metadata through
  `music_list_playlist_tracks` and `music playlist-tracks`.

### Safety

- The new Music path requires one opaque `music:playlist:v1:` handle from the
  playlist metadata flow, returns capped track metadata only, and does not
  expose raw Music identifiers, file paths, audio bytes, lyrics, play history,
  or ratings.
- Broad Music library dumps, broad playlist track dumps, playback/queue
  control, Music mutation, raw `.musicdb` parsing, and iCloud media fetches
  remain blocked.

## 0.1.0+codex.20260702151030 - 2026-07-02

### Changed

- Added exact selected-event Calendar participant metadata through
  `calendar_list_participants`, `calendar_get_participant`,
  `calendar participants`, and `calendar participant`.

### Safety

- Participant lists return opaque `calendar:participant:v1:` handles plus
  role/status/type/current-user metadata and name/URL presence flags only.
- Exact participant detail requires the original event handle plus selected
  participant handle and returns only bounded selected name/URL.
- Participant reads use EventKit participant-only helper commands that avoid the
  event notes/location content path, and handle resolution scans the bounded
  `max_scan_events` window.
- Attendee, invitation, and organizer mutation remains blocked.

## 0.1.0+codex.20260702150939 - 2026-07-02

### Changed

- Added bounded Photos regular-album metadata selection through
  `photos_search_albums`, `photos_get_album`, `photos albums`, and
  `photos album`.
- Added exact selected Photos regular-album membership add/remove to the
  existing Photos plan/apply/read-back gate.
- Added `docs/V1_151_PHOTOS_ALBUM_MEMBERSHIP_WRITE_DESIGN.md`.

### Safety

- Album membership requires one exact `photos:asset:v1:` handle, one exact
  `photos:album:v1:` regular-album handle, expected membership-state binding,
  matching approval token, explicit confirmation, public PhotoKit add/remove
  support, and read-back membership proof.
- Output returns no raw PhotoKit asset identifiers, raw album identifiers, asset
  bytes, resource bytes, album item dumps, or Photos content.
- Album create/rename/delete, smart/shared/synced album targeting, bulk album
  membership changes, permanent purge, content edits, and Photos metadata writes
  beyond approved favorite/hidden/delete/album-membership gates remain blocked.

## 0.1.0+codex.20260702150100 - 2026-07-02

### Changed

- Added exact selected Photos asset delete to the existing Photos
  plan/apply/read-back gate.
- Added `docs/V1_149_PHOTOS_DELETE_WRITE_DESIGN.md`.

### Safety

- Delete requires one exact `photos:asset:v1:` handle, expected safe-state
  binding, matching approval token, explicit confirmation, public PhotoKit delete
  support, and read-back absence proof.
- Output returns no raw PhotoKit identifiers or asset bytes and does not empty
  Recently Deleted or permanently purge Photos assets.

## 0.1.0+codex.20260702133000 - 2026-07-02

### Changed

- Broadened iCloud Drive exact folder `delete_folder` apply from empty-only
  permanent delete to bounded selected-folder tree delete with exact opaque
  source handles.
- Extended existing delete-folder runtime proof so direct and MCP smokes delete
  non-empty synthetic folders while proving no child names or content are
  returned.

### Safety

- Bound selected folder trees privately into approval fingerprints and
  apply-time rechecks; output stays metadata-only with no child listing, raw
  path, content text, or content hash return.
- Refused hidden entries, symlinks, packages, unsupported entries, and
  tree-size over-cap before issuing an approval token.
- Staged selected folders through hidden no-follow identity proof, performs
  bounded staged-tree removal, rolls back pre-delete tree drift when possible,
  and reports unverified staged deletion as `partial`.
- Broad or unbounded recursive delete, empty Trash, package traversal, symlink
  traversal, hidden-file writes, raw path writes, and binary/document generation
  remain blocked.

## 0.1.0+codex.20260702110820 - 2026-07-02

### Changed

- Broadened iCloud Drive exact folder `copy_folder` apply from empty-only copy
  to bounded selected-folder tree copy with exact opaque source and target-parent
  handles.
- Added `docs/V1_147_ICLOUD_DRIVE_NON_EMPTY_FOLDER_COPY_WRITE_DESIGN.md`.

### Safety

- Bound source trees privately into approval fingerprints and apply-time
  rechecks; output stays metadata-only with no child listing, raw path, content
  text, or content hash return.
- Refused hidden entries, symlinks, packages, descendant-parent copies, tree-size
  over-cap, unbounded folder copy, and non-empty folder permanent delete.
- Created target directories and cleanup entries through no-follow parent file
  descriptors, verified only the expected bounded target tree, refused
  unexpected cleanup entries, and reported cleaned verification failures as
  `error` with `mutation_applied:false`.
- Bound nested file-copy target parents to the just-created directory stats and
  bounded directory-name scans before sorting.

## 0.1.0+codex.20260702085345 - 2026-07-02

### Changed

- Broadened iCloud Drive exact folder `trash_folder` apply to allow non-empty
  directories selected by exact opaque handles.
- Added `docs/V1_146_ICLOUD_DRIVE_NON_EMPTY_FOLDER_TRASH_WRITE_DESIGN.md`.

### Safety

- Kept Trash recoverable and metadata-only: no recursive content read, no child
  listing in output, no content text/hash return, and no raw Trash path return.
- Kept permanent folder delete and, at that version, folder copy empty-only.
  Folder copy was later broadened in `0.1.0+codex.20260702110820`. Recursive
  delete, empty Trash, package traversal, symlink traversal, hidden-file writes,
  raw path writes, and binary/document generation remain blocked.

## 0.1.0+codex.20260702080910 - 2026-07-02

### Changed

- Broadened iCloud Drive exact folder `rename_folder` and `move_folder` apply
  gates to allow non-empty directories selected by exact opaque handles.
- Added `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`.

### Safety

- Kept folder copy and folder delete empty-only. Folder Trash was later
  broadened in `0.1.0+codex.20260702085345`.
- Kept non-empty rename/move metadata-only: no child listing, no content text,
  no content hash, and no raw path return.
- Added descendant-parent refusal for folder move and regression coverage that
  forbids materialized child-name listing during non-empty folder read-back.

## 0.1.0+codex.20260701233937 - 2026-07-01

### Fixed

- Hardened `calendar request-access` so the EventKit helper keeps the run loop
  alive during `requestFullAccessToEvents` / `requestAccess(to: .event)`.
- Activated and finished launching the helper app through AppKit before the
  Calendar permission request so macOS has a foreground app identity for the
  consent path.
- Added `reminders request-access` so the same stable EventKit helper app can
  request macOS Reminders full access after TCC resets.
- Routed Reminders EventKit reads/writes through the app-bundled helper runner
  instead of the raw `swift` script so Reminders reads, writes, and permission
  prompts share `com.local-apple-data.eventkit-helper`.

### Live Proof

- Live Calendar access now returns `authorization_status:"full_access"` for the
  helper after the hardened request path and targeted public TCC reset. Calendar
  target listing returned `status:"ok"` with a default calendar result.
- Live Reminders access now returns `authorization_status:"full_access"` for
  the helper after `reminders request-access --json`. Synthetic `LAD-TEST-*`
  list create/delete and reminder create/delete apply paths returned
  `mutation_applied:true` with read-back absence proof.

## 0.1.0+codex.20260701190515 - 2026-07-01

### Added

- Added `icloud_drive_list_tree` and `local-apple-data icloud-drive tree` for
  bounded recursive metadata listing under one exact selected iCloud Drive
  folder handle.
- Added `docs/V1_142_ICLOUD_DRIVE_FOLDER_TREE.md`.

### Privacy

- Kept the new folder-tree surface read-only, metadata-only, exact-handle-only,
  depth-capped, result-capped, tree-scan-capped, and without content text,
  content hashes, inline bytes, raw local paths, symlink traversal, package
  traversal, or hidden entries.
- Bound queued child folders to the metadata SHA-256 observed during parent
  listing so replacement races fail closed before descendant metadata is
  returned.

## 0.1.0+codex.20260701180744 - 2026-07-01

### Added

- Added `icloud_drive_list_folder` and `local-apple-data icloud-drive list` for
  exact selected-folder direct child iCloud Drive metadata listing.

### Privacy

- Kept the new folder-list surface metadata-only, capped, non-recursive,
  read-only, exact-handle-only, and without content text, content hashes, raw
  local paths, hidden entries, symlink entries, or package traversal.

## 0.1.0+codex.20260701174001 - 2026-07-01

### Added

- Added `calendar request-access` and a stable app-bundled EventKit helper so
  macOS can grant Calendar full access to `com.local-apple-data.eventkit-helper`
  instead of the parent Codex process.

### Fixed

- Fixed local Calendar reads from Codex after TCC only granted write-only access
  to `com.openai.codex`; Calendar commands now launch the app-bundled helper
  with explicit JSON file input/output and keep normal reads non-prompting.
- Hardened the helper-app cache with strict bundle metadata validation,
  mandatory ad-hoc signing and verification, private `0600` temp IPC files, and
  safe degraded JSON for request-access failures/timeouts.
- Refreshed the Calendar public-surface blocker audit so default-calendar mutation
  is tied to readonly `defaultCalendarForNewEvents`, and source/account mutation
  is tied to EventKit's create-only calendar source documentation.
- Updated the fresh-chat handoff to make v1.139 explicit-unbounded recurrence the
  current installed baseline instead of the older v1.138 Reminder alarm tranche.

## 0.1.0+codex.20260701160337 - 2026-07-01

### Added

- Added explicit Calendar unbounded recurrence planning and apply through `recurrence_unbounded` / `--recurrence-unbounded` for create, add-to-non-recurring-event update, and mid-series recurrence replacement.
- Added public EventKit nil-`EKRecurrenceEnd` apply/read-back support, exact mutually-exclusive bound validation, adapter/CLI/MCP tests, and runtime verifier direct plus MCP proof keys.
- Added `docs/V1_139_CALENDAR_UNBOUNDED_RECURRENCE_WRITE_DESIGN.md`.

### Fixed

- Replaced current finite-only Calendar recurrence status text with count-, end-date-, or explicit-unbounded wording; implicit unbounded recurrence remains blocked.

## 0.1.0+codex.20260701150456 - 2026-07-01

### Added

- Added exact Reminders relative display-alarm set planning and apply through `reminders plan/apply --operation set-relative-display-alarm` and MCP `reminders_plan_change` / `reminders_apply_change`.
- Added exact integer minute-offset normalization, expected alarm-count/SHA-256 binding, EventKit apply through public `EKAlarm(relativeOffset:)`, exact offset read-back proof for set, and pure display-alarm clear support for absolute or relative alarm states.
- Added `docs/V1_138_REMINDERS_RELATIVE_DISPLAY_ALARM_WRITE_DESIGN.md`.

### Fixed

- Kept mixed absolute-plus-relative Reminder alarm state, audio, email, geofence, procedure, attachment, image, sharing, rich-content, raw alarm-state return, and bulk Reminder alarm mutation blocked.
- Updated runtime verifier, mutation/write-design gates, README, skill, privacy/threat/testing docs, capability matrix, and release fixtures for the exact relative alarm gate.

## 0.1.0+codex.20260701140855 - 2026-07-01

### Added

- Added exact Reminders absolute display-alarm set/clear planning and apply through `reminders plan/apply --operation set-absolute-display-alarm|clear-display-alarm` and MCP `reminders_plan_change` / `reminders_apply_change`.
- Added exact expected alarm-count/SHA-256 binding, timezone-explicit absolute date normalization, EventKit apply, exact date read-back proof for set, absence proof for clear, and `alarm_state_raw_returned:false`.
- Added `docs/V1_137_REMINDERS_ABSOLUTE_DISPLAY_ALARM_WRITE_DESIGN.md`.

### Fixed

- Kept relative, audio, email, geofence, procedure, attachment, image, sharing, rich-content, raw alarm-state return, and bulk Reminder alarm mutation blocked.
- Updated runtime verifier, mutation/write-design gates, README, skill, privacy/threat/testing docs, capability matrix, and release fixtures for the exact alarm gate.

## 0.1.0+codex.20260701130304 - 2026-07-01

### Added

- Added exact Reminders URL update/clear planning and apply through `reminders plan/apply --operation update-url|clear-url` and MCP `reminders_plan_change` / `reminders_apply_change`.
- Added exact expected URL presence/SHA-256 binding, ASCII-only `http`/`https`/`mailto`/`tel` URL validation, hash-only URL read-back proof for update, absence proof for clear, and explicit `url_raw_returned:false`.
- Added `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`.

### Fixed

- Kept broad Reminder search metadata to `url_present` only; URL hashes now appear only in exact content/detail and URL apply proof paths.
- Updated runtime verifier, mutation/write-design gates, README, skill, privacy/threat/testing docs, capability matrix, and handoff blockers so raw URL retrieval, broad URL search, non-ASCII/unsafe URL schemes, and bulk URL mutation remain blocked while exact URL update/clear is approved.

## 0.1.0+codex.20260701121956 - 2026-07-01

### Added

- Added exact Reminders list create/rename/empty-delete planning and apply through `reminders plan-list` / `reminders apply-list` and MCP `reminders_plan_list_change` / `reminders_apply_list_change`.
- Added exact source/target `reminders:list:eventkit:v1:` handle binding, synthetic-title enforcement, writable/source-state checks, empty-list proof for rename/delete, EventKit apply, and source/title, empty-list, or absence read-back verification.
- Added `docs/V1_135_REMINDERS_SYNTHETIC_LIST_CRUD_WRITE_DESIGN.md`.

### Fixed

- Updated runtime verifier, mutation/write-design/surface gates, README, skill, privacy/threat/testing docs, and release-readiness fixtures so exact Reminders list CRUD is approved while account/source management, sharing, non-empty delete, and bulk list mutation remain blocked.
- Hardened list rename/delete planning so missing empty-count proof fails closed with `list_count_unavailable`.

## 0.1.0+codex.20260701112349 - 2026-07-01

### Added

- Added exact Photos `update_flags` planning/apply for one exact `photos:asset:v1:` handle.
- Added expected favorite/hidden state binding, target favorite/hidden state binding, public PhotoKit property-edit support checks, read-back verification, and no raw PhotoKit identifier or asset-byte return.
- Added `docs/V1_134_PHOTOS_UPDATE_FLAGS_WRITE_DESIGN.md`.

### Fixed

- Updated CLI, MCP, runtime verifier, mutation/write-design gates, README, skill, privacy/threat/testing docs, and capability matrix so Photos favorite/hidden update is an approved exact-gated surface while album/delete/content edits remain blocked.
- Hardened `update_flags` so missing target flags fail before scanning Photos, large exact-handle scans honor the requested scan cap, and target-state read-back mismatch cannot report a successful mutation.

## 0.1.0+codex.20260701104916 - 2026-07-01

### Added

- Added safe non-HTTP Calendar event URL planning/apply for `mailto` and `tel` alongside existing `http` and `https`.
- Added `event_url_scheme` preview metadata while keeping raw event URLs out of public plan/apply output.
- Added `docs/V1_133_CALENDAR_SAFE_NON_HTTP_EVENT_URL_WRITE_DESIGN.md`.

### Fixed

- Mirrored allow-listed URL validation in Python and Swift, including strict `mailto` and `tel` validation and no silent `tel` parameter dropping.
- Updated runtime, write-design, mutation, packaging, README, skill, and handoff checks so Calendar event URL policy is allow-listed schemes rather than HTTP-only.

## 0.1.0+codex.20260701094030 - 2026-07-01

### Added

- Added exact iCloud Drive `delete-file` planning/apply for one exact existing non-text non-package regular file.
- Added expected target metadata binding, fd-relative no-follow regular-file validation, hidden staging identity proof, permanent unlink, original absence proof, metadata-only read-back, and no raw target path, staging path, Trash path, content, or content-hash return.
- Added `docs/V1_132_ICLOUD_DRIVE_DELETE_FILE_WRITE_DESIGN.md`.

### Fixed

- Added rollback regression coverage so an unverified staged-file rollback returns `partial` without falsely claiming `mutation_applied:true` or `permanently_deleted:true`.

## 0.1.0+codex.20260701091728 - 2026-07-01

### Added

- Added exact iCloud Drive `trash-file` planning/apply for one exact existing non-text non-package regular file.
- Added expected target metadata binding, fd-relative no-follow regular-file validation, recoverable Trash move, original absence proof, metadata-only read-back, and no raw Trash path, content, or content-hash return.
- Added `docs/V1_131_ICLOUD_DRIVE_TRASH_FILE_WRITE_DESIGN.md`.

### Fixed

- Added rollback regression coverage so an unverified Trash rollback returns `partial` without falsely claiming `mutation_applied:true` or `trashed:true`.

## 0.1.0+codex.20260701082803 - 2026-07-01

### Added

- Added exact iCloud Drive `replace-file` planning/apply for one exact existing non-text non-package regular file and one caller-selected local non-text non-package replacement file outside the configured iCloud Drive root.
- Added expected target metadata binding, private replacement source identity/content binding, source/target extension match, source preservation proof, byte-replacement proof, metadata-only target read-back, stale source-token/source-drift refusal, stale target metadata refusal, and no source path/hash or content hash/text return.
- Added `docs/V1_130_ICLOUD_DRIVE_REPLACE_FILE_WRITE_DESIGN.md`.

### Fixed

- Updated mutation/write-design/release audits and plugin manifest wording so exact regular-file replacement is approved only through the new `replace-file` gate while binary/document content generation or editing remains blocked.

## 0.1.0+codex.20260701065042 - 2026-07-01

### Added

- Added exact iCloud Drive `import-file` planning/apply for one caller-selected local non-text non-package regular file outside the configured iCloud Drive root, copied into one exact selected iCloud Drive folder.
- Added private source identity/content binding, no-overwrite target proof, metadata-only target read-back, byte-preservation proof, stale-source refusal, source-preservation proof, and no source path/hash or content hash/text return.
- Added `docs/V1_129_ICLOUD_DRIVE_IMPORT_FILE_WRITE_DESIGN.md`.

### Fixed

- Narrowed iCloud Drive docs so regular-file mutation outside exact `import-file` or metadata-only rename/copy/move gates remains blocked, while the safe exact import gate is approved.

## 0.1.0+codex.20260701052410 - 2026-07-01

### Added

- Added synthetic `LAD-TEST-*` Calendar calendar delete through `calendar plan-calendar/apply-calendar` and MCP `calendar_plan_calendar_change` / `calendar_apply_calendar_change`.
- Added exact target `calendar:calendar:v1:` binding, event-only calendar refusal, bounded empty-calendar proof, public EventKit `removeCalendar` apply, and post-delete absence proof.

### Fixed

- Narrowed the Calendar calendar-delete blocker: real/non-synthetic calendar delete and mixed event/reminder calendar delete remain blocked, while the synthetic event-only bounded-empty gate is approved.

## 0.1.0+codex.20260701045332 - 2026-07-01

### Added

- Added streamed regular-file copy verification for iCloud Drive `copy-file`, avoiding whole-file materialization while preserving fd-relative no-follow reads, target identity proof, internal byte proof, and source metadata recheck.
- Added deterministic package-member refusal and streaming-copy regression coverage for regular-file rename/copy/move.

### Fixed

- Corrected current iCloud Drive docs and audit fixtures so binary/document content generation or editing remains blocked while exact regular-file rename/copy/move remains approved through the v1.127 gate.
- Corrected regular-file planning docs to state that planning validates handle shape and approval fields, while apply resolves the handle and enforces non-text non-package regular-file status.

## 0.1.0+codex.20260701023500 - 2026-07-01

### Added

- Added Calendar mid-series recurrence replacement through update-only `recurrence_update_scope:future_events` plus finite replacement recurrence fields.
- Added exact previous/selected/future occurrence identity binding, public EventKit `.futureEvents` save with a new `EKRecurrenceRule`, replacement recurrence read-back, future occurrence replacement proof, and previous occurrence preservation proof.
- Added direct and MCP runtime verifier coverage for mid-series recurrence replacement plan/apply success.
- Added `docs/V1_126_CALENDAR_RECURRENCE_REPLACEMENT_WRITE_DESIGN.md`.

### Fixed

- Removed mid-series recurrence replacement from the current Calendar blocker taxonomy; custom recurrence shapes, unbounded recurrence, attendees/invitations, travel time, non-HTTP(S) URLs, procedure alarms, and non-synthetic calendar management remain blocked.

## 0.1.0+codex.20260701015852 - 2026-07-01

### Added

- Added Calendar mid-series recurrence clearing through update-only `clear_recurrence` plus `recurrence_update_scope:future_events`.
- Added exact previous/future occurrence identity binding, EventKit `.futureEvents` save after clearing recurrence rules, selected-occurrence non-recurring read-back, future occurrence absence proof, and previous occurrence preservation proof.
- Extended direct and MCP runtime verifier coverage for mid-series recurrence-clear plan/apply success.

### Fixed

- Narrowed the Calendar recurrence blocker: mid-series recurrence clearing is approved; mid-series recurrence replacement remains blocked.

## 0.1.0+codex.20260701005601 - 2026-07-01

### Added

- Added Calendar synthetic `LAD-TEST-*` calendar create/rename through `calendar plan-calendar` / `calendar apply-calendar` and MCP `calendar_plan_calendar_change` / `calendar_apply_calendar_change`.
- Added exact source/target `calendar:calendar:v1:` binding, source-safe-hash and target-safe-hash validation, duplicate-title refusal, empty-calendar rename proof, public EventKit `saveCalendar` apply, and source/title read-back proof.
- Added `docs/V1_124_CALENDAR_CALENDAR_MANAGEMENT_WRITE_DESIGN.md`.

### Fixed

- Blocked Calendar calendar delete with `unsupported_calendar_delete` before mutation because public EventKit only proves bounded event windows while `removeCalendar` deletes all events and reminders.

## 0.1.0+codex.20260630231525 - 2026-06-30

### Added

- Added Calendar selector-backed set-position recurrence through `recurrence_set_positions` / `--recurrence-set-positions`.
- Added public EventKit `EKRecurrenceRule.setPositions` source-surface proof, selector-required validation, plan-token binding, Swift read-back verification, and direct plus MCP runtime verifier coverage.
- Added `docs/V1_123_CALENDAR_SET_POSITIONS_RECURRENCE_WRITE_DESIGN.md`.

## 0.1.0+codex.20260630223000 - 2026-06-30

### Added

- Added Calendar selected recurring occurrence target-calendar move through `recurrence_update_scope:this_event` / `--recurrence-update-scope this-event`.
- Added exact target `calendar:calendar:v1:` handle binding, EventKit `.thisEvent` save, selected-occurrence target-calendar read-back proof, adjacent-occurrence original-calendar preservation proof, and direct plus MCP runtime verifier coverage.
- Added `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.

## 0.1.0+codex.20260630204047 - 2026-06-30

### Added

- Added Calendar selected recurring occurrence all-day set/clear/date-only reschedule through `recurrence_update_scope:this_event` / `--recurrence-update-scope this-event`.
- Added date-only proposed start/end enforcement for selected all-day occurrence set and same-state all-day date-only reschedule, expected time-zone binding for timed-to-all-day set, selected-occurrence all-day read-back proof, and direct plus MCP runtime verifier coverage for set, clear, and reschedule.
- Added `docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`.

## 0.1.0+codex.20260630201632 - 2026-06-30

### Added

- Added Calendar selected recurring occurrence audio, email, and structured geofence action-alarm set/clear through `recurrence_update_scope:this_event` / `--recurrence-update-scope this-event`.
- Added exact display/audio/email/geofence alarm expected-state binding, hash-only email output, selected-occurrence action-alarm read-back proof, adjacent sibling alarm-state hash preservation proof, and direct plus MCP runtime verifier coverage.
- Added direct runtime proof for audio/email/geofence action set and audio/email/geofence action clear.
- Added `docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`.

### Fixed

- Narrowed the selected-recurring-occurrence alarm blocker: action alarms are now approved for selected occurrence set/clear; selected-occurrence all-day/calendar-move mutation remains blocked.

## 0.1.0+codex.20260630190834 - 2026-06-30

### Added

- Added Calendar selected recurring occurrence relative and absolute display-alarm set/clear through `recurrence_update_scope:this_event` / `--recurrence-update-scope this-event`.
- Added exact display-alarm expected-state binding, selected-occurrence display-alarm read-back proof, adjacent sibling alarm-state hash preservation proof, and relative/absolute/clear direct plus MCP runtime verifier coverage.
- Added `docs/V1_119_CALENDAR_SELECTED_OCCURRENCE_DISPLAY_ALARM_WRITE_DESIGN.md`.

### Fixed

- Narrowed the selected-recurring-occurrence update blocker: display alarms are now approved; selected-occurrence all-day/calendar-move mutation remains blocked.

## 0.1.0+codex.20260630170525 - 2026-06-30

### Added

- Added Calendar selected recurring occurrence structured-location set/clear through `recurrence_update_scope:this_event` / `--recurrence-update-scope this-event`.
- Added selected-occurrence structured-location absence binding for set, exact expected structured-location binding for replacement/clear, selected-occurrence read-back proof, and structured/plain location absence proof for clear.
- Added direct and MCP runtime verifier smokes plus stale expected-absence and read-back mismatch regressions.
- Added `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`.

### Fixed

- Narrowed the selected-recurring-occurrence update blocker: structured-location set/clear is now approved; all-day/alarm/calendar-move mutation remains blocked.

## 0.1.0+codex.20260630154023 - 2026-06-30

### Added

- Added Calendar selected recurring occurrence HTTP(S) event URL set/clear through `recurrence_update_scope:this_event` / `--recurrence-update-scope this-event`.
- Added selected-occurrence event URL hash-only read-back proof, clear absence proof, existing-URL replacement proof, and adjacent-occurrence URL-state preservation proof.
- Added stale selected current-URL hash refusal, URL-present adjacent-occurrence preservation regression coverage, and EventKit URL-setter public-surface enforcement.
- Added `docs/V1_117_CALENDAR_SELECTED_OCCURRENCE_EVENT_URL_WRITE_DESIGN.md`.

### Fixed

- Narrowed the selected-recurring-occurrence update blocker: event URL set/clear is now approved; all-day/alarm/structured-location/calendar-move mutation remains blocked.

## 0.1.0+codex.20260630145840 - 2026-06-30

### Added

- Added Calendar selected recurring occurrence availability update through `recurrence_update_scope:this_event` / `--recurrence-update-scope this-event`.
- Added required `expected_availability`, target-calendar support-mask validation, selected-occurrence availability read-back, and adjacent-occurrence preservation proof.
- Added `docs/V1_116_CALENDAR_SELECTED_OCCURRENCE_AVAILABILITY_WRITE_DESIGN.md`.

### Fixed

- Narrowed the selected-recurring-occurrence update blocker: availability is now approved; all-day/calendar-move mutation remains blocked.

## 0.1.0+codex.20260630140427 - 2026-06-30

### Added

- Added Calendar selected recurring occurrence timed reschedule through `recurrence_update_scope:this_event` / `--recurrence-update-scope this-event`.
- Added timed `start_date`/`end_date`/`time_zone` mutation with selected-occurrence read-back at the approved new time, original occurrence absence proof, and adjacent-occurrence preservation proof.
- Added `docs/V1_115_CALENDAR_SELECTED_OCCURRENCE_RESCHEDULE_WRITE_DESIGN.md`.

### Fixed

- Narrowed the selected-recurring-occurrence update blocker: timed reschedule is now approved; all-day/alarm/URL/availability/structured-location/calendar-move mutation remains blocked.

## 0.1.0+codex.20260630130653 - 2026-06-30

### Added

- Added Calendar selected recurring occurrence scalar update through `recurrence_update_scope:this_event` / `--recurrence-update-scope this-event`.
- Added occurrence start/end identity binding, adjacent-occurrence preservation proof, expected recurrence-shape binding, EventKit `.thisEvent` save, selected-occurrence read-back proof, and adapter/CLI/MCP/runtime verifier coverage.
- Added `docs/V1_114_CALENDAR_SELECTED_OCCURRENCE_UPDATE_WRITE_DESIGN.md`.

### Fixed

- Narrowed the existing-recurring-event update blocker: selected occurrence title/plain-location/notes update is now approved; time/all-day/time-zone/alarm/URL/availability/structured-location/calendar-move mutation and mid-series recurrence replacement remain blocked.

## 0.1.0+codex.20260630121356 - 2026-06-30

### Added

- Added Calendar monthly weekday recurrence selection through `recurrence_weekdays` / `--recurrence-weekdays` when `recurrence_frequency` is `monthly`, for event create and add-to-non-recurring-event update.
- Added monthly selector mixing refusal across monthly weekdays, month days, and nth-weekdays, EventKit `daysOfTheWeek` apply without week numbers, and exact read-back proof.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, public-surface-audit, release-readiness, plugin-packaging, and docs coverage for v1.113.
- Added `docs/V1_113_CALENDAR_MONTHLY_WEEKDAY_RECURRENCE_WRITE_DESIGN.md`.

### Fixed

- Kept true month-week arrays blocked because public EventKit exposes no `weeksOfTheMonth`; kept mid-series recurrence replacement, existing-recurring-event update beyond approved clear/delete scopes, unbounded recurrence, attendees/invitations, travel time, non-HTTP(S) URLs, and procedure alarms blocked.

## 0.1.0+codex.20260630111826 - 2026-06-30

### Added

- Added Calendar yearly month day-of-month recurrence selection through `recurrence_year_month_days` / `--recurrence-year-month-days`, combined with `recurrence_year_months`, for yearly recurrence create and add-to-non-recurring-event update.
- Added yearly-only validation, required exact year-month binding, refusal to mix with year-month nth-weekday, year-day, or year-week selectors, EventKit `monthsOfTheYear` plus `daysOfTheMonth` apply, and exact read-back proof.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, public-surface-audit, release-readiness, and docs coverage for v1.112.
- Added `docs/V1_112_CALENDAR_YEARLY_MONTH_DAY_RECURRENCE_WRITE_DESIGN.md`.

### Fixed

- Kept mid-series recurrence replacement, existing-recurring-event update beyond approved clear/delete scopes, unbounded recurrence, attendees/invitations, travel time, non-HTTP(S) URLs, and procedure alarms blocked.

## 0.1.0+codex.20260630103756 - 2026-06-30

### Added

- Added Calendar yearly month nth-weekday recurrence selection through `recurrence_year_month_weekdays` / `--recurrence-year-month-weekdays`, combined with `recurrence_year_months`, for yearly recurrence create and add-to-non-recurring-event update.
- Added yearly-only validation, required exact year-month binding, refusal to mix with year-day/year-week selectors, EventKit `monthsOfTheYear` plus `daysOfTheWeek` apply, and exact read-back proof.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, public-surface-audit, release-readiness, and docs coverage for v1.111.
- Added `docs/V1_111_CALENDAR_YEARLY_MONTH_NTH_WEEKDAY_RECURRENCE_WRITE_DESIGN.md`.

### Fixed

- Kept mid-series recurrence replacement, existing-recurring-event update beyond approved clear/delete scopes, unbounded recurrence, attendees/invitations, travel time, non-HTTP(S) URLs, and procedure alarms blocked.

## 0.1.0+codex.20260630092602 - 2026-06-30

### Added

- Added Calendar yearly day-of-year and week-of-year recurrence selection through `recurrence_year_days` / `--recurrence-year-days` and `recurrence_year_weeks` / `--recurrence-year-weeks`.
- Added yearly-only range checks, exactly-one yearly selector enforcement across year months/days/weeks, EventKit `daysOfTheYear` / `weeksOfTheYear` apply, and exact read-back proof.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, public-surface-audit, release-readiness, and docs coverage for v1.110.
- Added `docs/V1_110_CALENDAR_YEARLY_DAY_WEEK_RECURRENCE_WRITE_DESIGN.md`.

### Fixed

- Updated Calendar recurrence docs to reflect v1.109 count-or-end-date bounds across existing weekly/monthly/yearly selector gates.
- Kept combining yearly selectors, yearly nth-weekday/set-position recurrence, custom yearly rules beyond yearly BYMONTH/BYYEARDAY/BYWEEK, unbounded recurrence, attendees/invitations, travel time, non-HTTP(S) URLs, and procedure alarms blocked.

## 0.1.0+codex.20260630084410 - 2026-06-30

### Added

- Added Calendar finite recurrence end dates through `recurrence_end_date` / `--recurrence-end-date` for event create and add-to-non-recurring-event update.
- Added count/end-date mutual exclusion, date-only end-date refusal, 3650-day horizon checks, EventKit `EKRecurrenceEnd(end:)` apply, and exact `end_date` read-back proof.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, public-surface-audit, release-readiness, and docs coverage for v1.109.
- Added `docs/V1_109_CALENDAR_RECURRENCE_END_DATE_WRITE_DESIGN.md`.

### Fixed

- Extended scoped recurring-event delete apply to bind exact `expected_recurrence` and reject recurrence drift before EventKit removal.
- Kept unbounded recurrence, date-only recurrence end values, existing-recurring-event update beyond approved clear/delete scopes, attendees/invitations, travel time, non-HTTP(S) URLs, and procedure alarms blocked.

## 0.1.0+codex.20260630073000 - 2026-06-30

### Added

- Added Calendar exact email alarms through `alarm_email_address` / `--alarm-email-address`, gated by existing relative or absolute alarm triggers.
- Added expected-state binding through `expected_alarm_email_address_sha256` / `--expected-alarm-email-address-sha256`, EventKit `EKAlarm.emailAddress` apply, hash-only preview/read-back, and exact read-back proof through `alarm_email_address_sha256_verified`.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, public-surface-audit, release-readiness, and docs coverage for v1.108.
- Added `docs/V1_108_CALENDAR_EMAIL_ALARM_WRITE_DESIGN.md`.

### Fixed

- Kept email alarm output hash-only: raw email input is accepted only as plan/apply input and is not returned in previews, read-back, runtime summaries, or docs.
- Removed current-doc blocker wording that treated email alarms as unimplemented. Procedure alarms, travel time, attendees/invitations, non-HTTP(S) URLs, and unsupported recurrence semantics remain blocked behind separate gates.

## 0.1.0+codex.20260630070000 - 2026-06-30

### Added

- Added Calendar structured-location clearing through `clear_structured_location` / `--clear-structured-location` for exact-event update.
- Added expected structured-location binding, set+clear conflict refusal, plain-location conflict refusal, EventKit `structuredLocation = nil` plus `location = nil` apply, and read-back absence proof through `structured_location_present:false`, `location_present:false`, and `structured_location_cleared_verified`.
- Added `docs/V1_107_CALENDAR_STRUCTURED_LOCATION_CLEAR_WRITE_DESIGN.md`.

### Fixed

- Kept structured-location clear fail-closed outside update operations and without exact `expected_structured_location` binding.
- Extended runtime verifier coverage for direct and MCP structured-location clear paths.

## 0.1.0+codex.20260630063000 - 2026-06-30

### Added

- Added Calendar yearly month recurrence selection through `recurrence_year_months` / `--recurrence-year-months` for yearly recurrence create and add-to-non-recurring-event update.
- Added adapter, CLI, MCP, Swift/EventKit, fixture-backed runtime-verifier, write-design-audit, public-surface-audit, release-readiness, and docs coverage for `monthsOfTheYear` binding and read-back proof.
- Hardened Swift helper numeric-array parsing so CFBoolean values cannot bridge as integer recurrence/alarm values.
- Added `docs/V1_106_CALENDAR_YEARLY_MONTH_RECURRENCE_WRITE_DESIGN.md`.

### Fixed

- Kept yearly month recurrence fail-closed outside yearly rules and kept custom yearly recurrence rules beyond yearly BYMONTH, mid-series recurrence clearing/replacement, existing-recurring-event update, unbounded recurrence, attendees/invitations, travel time, and procedure alarms blocked behind separate gates.

## 0.1.0+codex.20260630060000 - 2026-06-30

### Added

- Added Calendar monthly nth-weekday recurrence selection through `recurrence_month_weekdays` / `--recurrence-month-weekdays` for monthly recurrence create and add-to-non-recurring-event update.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, public-surface-audit, release-readiness, and docs coverage for canonical week-number weekday binding and read-back proof.
- Added `docs/V1_105_CALENDAR_MONTHLY_NTH_WEEKDAY_RECURRENCE_WRITE_DESIGN.md`.

### Fixed

- Kept monthly nth-weekday recurrence fail-closed outside monthly rules, mutually exclusive with monthly day-of-month rules, and kept mid-series recurrence clearing/replacement, existing-recurring-event update, custom yearly recurrence components beyond yearly BYMONTH, unbounded recurrence, attendees/invitations, travel time, and procedure alarms blocked behind separate gates.

## 0.1.0+codex.20260630053000 - 2026-06-30

### Added

- Added Calendar exact structured geofence alarms through `alarm_proximity` / `--alarm-proximity` plus `alarm_structured_location` / `--alarm-structured-location`.
- Added expected-state binding through `expected_alarm_proximity` and `expected_alarm_structured_location`, EventKit `EKAlarm.proximity` plus `EKAlarm.structuredLocation` apply, and exact read-back proof through `alarm_geofence_verified`.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, public-surface-audit, release-readiness, and docs coverage for v1.104.
- Added `docs/V1_104_CALENDAR_GEOFENCE_ALARM_WRITE_DESIGN.md`.

### Fixed

- Removed current-doc blocker wording that treated structured geofence alarms as unimplemented. Email/procedure alarms, travel time, attendees/invitations, non-HTTP(S) URLs, and unsupported recurrence semantics remain blocked behind separate gates.

## 0.1.0+codex.20260630043000 - 2026-06-30

### Added

- Added Calendar exact audio alarms through `alarm_sound_name` / `--alarm-sound-name`, gated by existing relative or absolute alarm triggers.
- Added expected-state binding through `expected_alarm_sound_name` / `--expected-alarm-sound-name`, EventKit `EKAlarm.soundName` apply, and exact read-back proof through `alarm_sound_name_verified`.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, public-surface-audit, release-readiness, and docs coverage for v1.103.
- Added `docs/V1_103_CALENDAR_AUDIO_ALARM_WRITE_DESIGN.md`.

### Fixed

- Made existing Calendar alarm-state validation fail closed on procedure alarms and mixed display/audio alarm state.
- Removed current-doc blocker wording that treated audio alarms as unimplemented. Structured geofence alarms were still future at v1.103; procedure alarms, travel time, attendees/invitations, non-HTTP(S) URLs, and unsupported recurrence semantics remained blocked behind separate gates.

## 0.1.0+codex.20260630035820 - 2026-06-30

### Added

- Added Calendar structured event location create/update through `structured_location` / `--structured-location` with optional paired latitude/longitude and radius.
- Added expected-state binding through `expected_structured_location` / `--expected-structured-location`, EventKit `EKStructuredLocation` apply, and exact read-back proof through `structured_location_verified`.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, release-readiness, and docs coverage for v1.102.
- Added `docs/V1_102_CALENDAR_STRUCTURED_LOCATION_WRITE_DESIGN.md`.

### Fixed

- Removed current-doc blocker wording that treated structured event location as unimplemented. Geofence/procedure alarms, travel time, attendees/invitations, non-HTTP(S) URLs, and unsupported recurrence semantics remain blocked behind separate gates.

## 0.1.0+codex.20260630032921 - 2026-06-30

### Added

- Added Calendar monthly day-of-month recurrence selection through `recurrence_month_days` / `--recurrence-month-days` for monthly recurrence create and add-to-non-recurring-event update.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, release-readiness, and docs coverage for canonical month-day binding and read-back proof.
- Added `docs/V1_101_CALENDAR_MONTHDAY_RECURRENCE_WRITE_DESIGN.md`.

### Fixed

- Kept month-day recurrence fail-closed outside monthly rules and kept mid-series recurrence clearing/replacement, existing-recurring-event update, custom monthly recurrence components beyond monthly BYMONTHDAY, custom yearly recurrence components beyond yearly BYMONTH, unbounded recurrence, attendees/invitations, travel time, and structured/geofence/procedure alarms blocked behind separate gates.

## 0.1.0+codex.20260630025929 - 2026-06-30

### Changed

- Broadened Calendar event URL create/update from HTTPS-only to exact HTTP(S) URLs through the existing hash-only plan/apply/read-back gate.
- Kept credentials, whitespace, missing hosts, invalid ports, file URLs, mailto URLs, and other non-HTTP(S) schemes rejected.
- Updated direct/MCP runtime verifier coverage to prove `http://` event URL planning/apply binding without returning raw URLs.

## 0.1.0+codex.20260629192059 - 2026-06-29

### Added

- Added Calendar first-visible recurrence clearing through `clear_recurrence` / `--clear-recurrence`.
- Added occurrence-bound first-visible proof, future-occurrence identity binding, bounded previous-occurrence absence proof, exact expected recurrence binding, EventKit `.futureEvents` apply, direct/MCP runtime proof keys, and adapter/CLI/MCP tests.
- Added `docs/V1_100_CALENDAR_RECURRENCE_CLEAR_WRITE_DESIGN.md`.

### Fixed

- Removed stale current docs that treated every recurrence-rule clear as blocked; mid-series recurrence clearing/replacement and existing-recurring-event mutation beyond first-visible clear plus selected/future/whole-series delete remain blocked behind separate gates.

## 0.1.0+codex.20260629183938 - 2026-06-29

### Added

- Added Calendar weekly weekday recurrence selection through `recurrence_weekdays` / `--recurrence-weekdays` for weekly recurrence create and add-to-non-recurring-event update.
- Added adapter, CLI, MCP, Swift/EventKit, runtime-verifier, write-design-audit, release-readiness, and docs coverage for canonical weekday binding and read-back proof.
- Added `docs/V1_99_CALENDAR_WEEKLY_WEEKDAY_RECURRENCE_WRITE_DESIGN.md`.

### Fixed

- Kept weekday recurrence fail-closed outside weekly rules and kept mid-series recurrence clearing/replacement, existing-recurring-event update, custom monthly/yearly recurrence components, unbounded recurrence, attendees/invitations, travel time, and structured/geofence/procedure alarms blocked behind separate gates.

## 0.1.0+codex.20260629163447 - 2026-06-29

### Added

- Added delete-only Calendar whole-series recurring-event delete through `recurrence_delete_scope:"all_events"` / `--recurrence-delete-scope all-events`.
- Added selected/future occurrence identity binding, bounded previous-occurrence absence proof, EventKit `.futureEvents` apply from the first visible occurrence, selected/future absence proof, bounded previous absence proof, and direct plus MCP runtime verifier keys.
- Added `docs/V1_98_CALENDAR_RECURRING_SERIES_DELETE_WRITE_DESIGN.md`.

### Fixed

- Removed stale current docs/audit wording that treated whole-series recurring-event delete as blocked. Recurrence-rule clearing and existing-recurring-event mutation beyond selected/future-span/whole-series delete remain blocked behind separate gates.

## 0.1.0+codex.20260629160000 - 2026-06-29

### Added

- Added delete-only Calendar future-event recurring span delete through `recurrence_delete_scope:"future_events"` / `--recurrence-delete-scope future-events`.
- Added exact selected, previous, and future occurrence identity binding, EventKit `.futureEvents` apply, selected/future absence proof, previous-occurrence preservation proof, and direct plus MCP runtime verifier keys.
- Added `docs/V1_97_CALENDAR_RECURRING_FUTURE_DELETE_WRITE_DESIGN.md`.

### Fixed

- Kept whole-series recurrence delete, mid-series recurrence clearing/replacement, and existing-recurring-event mutation beyond selected/future-span delete blocked behind separate gates.

## 0.1.0+codex.20260629154500 - 2026-06-29

### Changed

- Clarified the fresh-session kickoff prompt so the next agent sees the verified Mail/Contacts transport fix as a checkpoint, not a finish line.
- Added an explicit blocker taxonomy separating true local-public-API blockers from unimplemented but buildable Calendar/Files work.
- Updated durable handoff/operator guidance to prioritize the next safe implementation tranche instead of stopping after a verified cache/install checkpoint.

## 0.1.0+codex.20260629153000 - 2026-06-29

### Fixed

- Wrapped Contacts MCP tool bodies in the same redacted safe-error boundary so Contacts adapter failures return structured `mcp_tool_error` responses instead of risking stdio transport closure.

### Added

- Added all-Contacts MCP wrapper regression coverage proving path-bearing exceptions are redacted from both output and event logs.
- Added a same-stdio-session MCP regression and runtime verifier keys proving a Mail MCP `mcp_tool_error` response does not close transport before a following Contacts call.

## 0.1.0+codex.20260629150000 - 2026-06-29

### Fixed

- Fixed date-bounded Mail discovery ISO date parsing to compare against the local Mail `messages.date_received` / `date_sent` Unix-scale timestamps, resolving false-zero `mail advanced-search --scope subject --after 2026-06-26 --before 2026-06-30` results.
- Wrapped all Mail MCP tool bodies in a redacted safe-error boundary so unexpected Mail adapter failures return `mcp_tool_error` JSON instead of risking stdio transport closure while the CLI stays healthy.

### Added

- Added deterministic direct and MCP runtime verifier keys for ISO-bounded Mail advanced search: `mail_advanced_iso_*` and `mcp_mail_advanced_iso_*`.
- Added all-Mail MCP wrapper regression coverage proving path-bearing exceptions are redacted from both output and event logs.

## 0.1.0+codex.20260629141500 - 2026-06-29

### Added

- Added delete-only selected recurring Calendar occurrence support through `recurrence_delete_scope` / `--recurrence-delete-scope this-event`.
- Added expected recurrence-presence binding, occurrence start/end identity binding, adjacent same-series occurrence preservation binding, approval-token binding, EventKit `.thisEvent` removal, selected-occurrence absence proof, adjacent-occurrence preservation proof, and direct plus MCP runtime verifier keys.
- Added exact `mail:mailbox:v1:` filtering to Mail metadata search through CLI `--mailbox-handle` and MCP `mail_search(..., mailbox_handle=...)`.
- Added runtime verifier Contacts MCP liveness and full-count proof keys, plus sender-selected Mail reply/reply-all/forward proof keys.
- Added `docs/V1_96_CALENDAR_RECURRING_OCCURRENCE_DELETE_WRITE_DESIGN.md`.

### Fixed

- Rejected legacy event-id-only Calendar handles for selected recurring occurrence delete, required an adjacent same-series occurrence before apply, and required read-back proof that the selected occurrence is absent while the sibling still resolves.
- Removed stale current docs/audit wording that treated every recurrence delete as blocked. Future-event span delete, whole-series recurrence delete, mid-series recurrence clearing/replacement, and existing-recurring-event update beyond selected-occurrence delete remain blocked.

## 0.1.0+codex.20260629140000 - 2026-06-29

### Added

- Initial selected recurring Calendar occurrence delete tranche before adjacent-occurrence proof hardening.

## 0.1.0+codex.20260629134138 - 2026-06-29

### Added

- Added update-only exact Calendar event URL clearing through `clear_event_url` / `--clear-event-url`.
- Added exact expected URL state binding with `expected_event_url_present:true` plus `expected_event_url_sha256`, EventKit `event.url = nil` apply, and read-back absence proof through `event_url_cleared_verified:true`.
- Added adapter, CLI, MCP, runtime-verifier, write-design-audit, docs, skill, and plugin coverage for v1.95.
- Added `docs/V1_95_CALENDAR_EVENT_URL_CLEAR_WRITE_DESIGN.md`.

### Fixed

- Removed stale docs that treated URL clearing as blocked; non-HTTP(S) Calendar URLs remain blocked.

## 0.1.0+codex.20260629133000 - 2026-06-29

### Added

- Added exact HTTP(S) Calendar event URL create/update support through `event_url` / `--event-url`.
- Added update/delete `expected_event_url_present` plus `expected_event_url_sha256` binding for existing event URL state.
- Added hash-only EventKit URL read-back proof through `event_url_safe_sha256`, CLI/MCP forwarding, runtime-verifier keys, and deterministic adapter/CLI/MCP tests.
- Added `docs/V1_94_CALENDAR_EVENT_URL_WRITE_DESIGN.md`.

### Fixed

- Kept existing Calendar URLs out of detail/read-back output except for presence and SHA-256 proof. URL clearing landed later in v1.95; non-HTTP(S) URLs remain blocked.

## 0.1.0+codex.20260629124500 - 2026-06-29

### Added

- Added Calendar recurrence update for one exact currently non-recurring event through `recurrence_frequency`, `recurrence_interval`, and `recurrence_count`.
- Added adapter, CLI, MCP, Swift-source, runtime-verifier, write-design, release-readiness, docs, skill, and plugin coverage for recurrence-update binding.
- Added runtime verifier proof that existing-recurring-event recurrence update returns `expected_state_mismatch` with `mutation_applied:false`.
- Added `docs/V1_93_CALENDAR_RECURRENCE_UPDATE_WRITE_DESIGN.md`.

### Fixed

- Prevented existing-recurring Calendar events from reaching update/delete mutation or already-applied shortcuts inside the recurrence-update gate.
- Report `apply_unknown` mutation truth with `recurrence_read_back_mismatch` if EventKit saves an event but read-back recurrence does not match the approved value.

## 0.1.0+codex.20260629100100 - 2026-06-29

### Added

- Added exact Calendar availability create/update support through `availability` / `--availability` with busy, free, tentative, and unavailable values.
- Added update/delete `expected_availability` drift binding, EventKit target-calendar support-mask validation, Swift EventKit apply/read-back, CLI/MCP forwarding, runtime-verifier keys, and deterministic adapter/CLI/MCP tests.
- Added `docs/V1_92_CALENDAR_AVAILABILITY_WRITE_DESIGN.md` and write-design/mutation/release/doc/skill/plugin coverage for the availability gate.

### Fixed

- Validated availability changes against the destination calendar when an update also moves an event to a different calendar.
- Report `apply_unknown` mutation truth with `availability_read_back_mismatch` if EventKit saves an event but read-back availability does not match the approved value.

## 0.1.0+codex.20260629090039 - 2026-06-29

### Added

- Added explicit default-calendar Calendar create planning through `--use-default-calendar` and MCP `use_default_calendar`.
- Bound default-calendar planning to the resolved exact `calendar:calendar:v1:` handle so apply uses the approved `calendar_handle` and never re-resolves the live default calendar.
- Added adapter, CLI, MCP, runtime-verifier, write-design-audit, release-readiness, docs, skill, and capability-matrix coverage for the plan-only default-calendar gate.

### Fixed

- Rejected `use_default_calendar` on apply before EventKit access, keeping default-calendar selection as planning-only sugar over exact-handle create.

## 0.1.0+codex.20260629080119 - 2026-06-29

### Added

- Extended Calendar create-only recurrence to count-bound monthly/yearly in addition to daily/weekly.
- Added paired `YYYY-MM-DD` date-only Calendar start/end handling that infers all-day state for create, update expected/proposed state, and delete expected state.
- Added direct and MCP runtime verifier proof for monthly/yearly recurrence and date-only all-day binding.

### Fixed

- Hardened Swift date-only parsing to round-trip year/month/day so invalid dates cannot silently normalize in the EventKit helper.
- Fixed Calendar all-day EventKit read-back to serialize start/end values as `YYYY-MM-DD` instead of timestamp-shaped strings, and pinned the v1.90 runtime proof keys in release-readiness fixtures.
- Updated write-design, mutation, release-readiness, plugin, skill, README, threat model, and current operator docs to treat date-only all-day inference and daily/weekly/monthly/yearly recurrence create as current approved Calendar behavior.

## 0.1.0+codex.20260629053445 - 2026-06-29

### Added

- Added create-only simple Calendar recurrence through `recurrence_frequency`, `recurrence_interval`, and `recurrence_count`.
- Added EventKit `EKRecurrenceRule` apply/read-back, CLI/MCP forwarding, runtime verifier coverage, and write-design audit coverage for count-bound daily/weekly recurrence create.

### Changed

- Documented that recurrence update/delete, custom/monthly/yearly/unbounded recurrence rules, attendees/invitations, default-calendar guessing, date-only handling beyond explicit all-day, travel time, and structured/geofence/procedure alarms remain blocked.

## 0.1.0+codex.20260628210742 - 2026-06-28

### Added

- Added exact absolute display-alarm support for Calendar create/update/delete through `alarm_absolute_dates` and `expected_alarm_absolute_dates`.
- Added mutually exclusive relative/absolute alarm planning, approval-token binding, Swift EventKit apply/read-back, CLI/MCP forwarding, runtime verifier coverage, and write-design audit coverage.

### Changed

- Documented that structured-location, geofence, email, audio, and procedure alarms remain blocked pending separate source review and design gates.

## 0.1.0+codex.20260628091647 - 2026-06-28

### Fixed

- Hardened MCP startup so `scripts/run_mcp_server.sh` exports `PYTHONDONTWRITEBYTECODE=1` and `mcp_server.py` sets `sys.dont_write_bytecode = True`, preventing live installed-cache MCP servers from recreating `__pycache__` artifacts after hygiene proof.

## 0.1.0+codex.20260627223447 - 2026-06-27

### Added

- Added explicit timed-event Calendar `time_zone` and `expected_time_zone` support through `calendar plan/apply` and MCP `calendar_plan_change` / `calendar_apply_change`.
- Added EventKit `EKCalendarItem.timeZone` read-back metadata, Python `zoneinfo` validation, Swift `TimeZone(identifier:)` validation, all-day timezone refusal, CLI/MCP forwarding, runtime proof, and write-design audit coverage.

### Fixed

- Hardened `scripts/verify_runtime.py` so source and installed-cache runtime verification set `PYTHONDONTWRITEBYTECODE=1` and `sys.dont_write_bytecode = True`, preventing verifier-created bytecode from dirtying installed plugin artifact hygiene.

## 0.1.0+codex.20260627161548 - 2026-06-27

### Added

- Added metadata-only Calendar target-calendar selection through `calendar_search_calendars`, `calendar_get_calendar`, `local-apple-data calendar calendars`, and `local-apple-data calendar calendar`.
- Added exact Calendar create-by-`calendar:calendar:v1:` handle and exact event update/move-by-target-calendar handle through the existing plan/apply gate.
- Added runtime, CLI, MCP, Swift source-review, mutation-gate, write-design, and surface-contract coverage for Calendar target-calendar handles, duplicate source-calendar title refusal, and target-calendar read-back proof after EventKit calendar moves.

### Changed

- Raised the source and plugin surface count to 109 MCP tools and 109 CLI commands.
- Kept Calendar recurrence, attendees/invitations, default-calendar guessing, date-only/time-zone inference, travel time, richer alarms, calendar creation/deletion, and account management blocked pending separate design.

## 0.1.0+codex.20260626203049 - 2026-06-26

### Fixed

- Classified Codex app-server launched live MCP processes by process CWD as well as command-line paths, so pathless current-cache `uv run --no-project ... python -m local_apple_data.mcp_server` servers no longer fail live cross-agent freshness.
- Added deterministic coverage for pathless Codex MCP server processes running from the current installed cache.

## 0.1.0+codex.20260626142034 - 2026-06-26

### Fixed

- Hardened exact iCloud Drive content/export reads to bind the selected parent directory and file stat before byte reads, then refuse real-directory root replacement and selected-file replacement races.
- Added token-level direct live local-apple-data MCP process checking to `scripts/verify_cross_agent_sync.py`; stale running MCP servers from older installed Codex cache versions, unknown MCP server processes, and process-census failures now degrade cross-agent sync instead of being hidden behind clean file-sync checks.
- Added deterministic tests for stale installed-cache MCP process refusal, current source/cache MCP process acceptance, unknown/prefix-path MCP process refusal, shell-substring false-positive refusal, process-census failure refusal, real-directory source-root replacement refusal, and selected-file replacement refusal.

## 0.1.0+codex.20260626131635 - 2026-06-26

### Fixed

- Hardened exact iCloud Drive content/export reads to open selected file parents through the root-relative no-follow directory walker, closing source-root ancestor swap races.
- Hardened iCloud Drive export output writes to create/open output directories component-by-component without following arbitrary symlink ancestors, then write by stable directory fd with exclusive create and path identity proof.
- Added regressions for source ancestor swaps, direct and deep output symlink ancestors, nested output symlinks back into the iCloud root, oversized export caps, no-overwrite filename suffixes, post-write export path identity mismatch cleanup, macOS `/var` temp aliases, and CLI export root-override refusal.

## 0.1.0+codex.20260626123051 - 2026-06-26

### Added

- Added exact iCloud Drive regular-file export through `icloud_drive_export_file` and `local-apple-data icloud-drive export`.
- Export is read-only, exact `icloud:file:v1:` handle-gated, capped, and writes one selected non-package regular file to a caller-selected output directory outside the configured iCloud Drive root.
- Export returns no inline bytes and no source path, refuses symlinks, package-internal files, directories, output directories inside iCloud Drive, invalid byte caps, and oversized files, and is covered by source plus MCP runtime smokes.

## 0.1.0+codex.20260626104514 - 2026-06-26

### Fixed

- Hardened Mail synthetic cleanup after live Mail crash proof: cleanup now checks Mail background-idle state before destructive cleanup, binds exact empty Trash/Junk target sets plus subject/read/flag state in Mail.app automation, uses mailbox-scoped absence proof, and fails closed when Mail background activity is unavailable.
- Cleanup AppleScript timeout/write errors after the destructive command is invoked now return partial apply output with conservative `mutation_applied:true` and bounded absence read-back instead of claiming no mutation happened.
- Removed the temporary empty-on-quit account-setting fallback from synthetic cleanup.
- Fixed Mail empty-Trash/Junk AppleScript to delete synthetic messages one by one instead of coercing a message list.
- Preferred provider Trash/Bin mailboxes over generic Deleted Messages mailboxes when resolving Mail Trash targets.
- Updated runtime verifier, docs, and plugin metadata to reflect mailbox-scoped cleanup proof plus Mail-idle guards.

## 0.1.0+codex.20260626061653 - 2026-06-26

### Added

- Added Mail signature discovery/detail by opaque handle without returning signature bodies.
- Added plugin-managed Mail templates stored under local plugin state.
- Added FTS/query-result-to-plan Mail triage and synthetic `LAD-TEST-*` mailbox/cleanup plan/apply surfaces.
- Extended exact `mail:sender:v1:` sender selection to Mail send, reply, reply-all, and forward.

### Fixed

- Sent-copy read-back now tolerates Mail's quoted local rendering, Gmail-style `All Mail` sent copies, and local Mail sync lag before reporting sender-selected sends as partial.
- Synthetic cleanup success now requires mailbox-scoped absence proof plus Mail-idle guards.
- Template metadata no longer exposes a reusable body SHA-256 verifier.
- Live synthetic sender-selected send is proven for iCloud-to-Google and Google-to-iCloud. Synthetic mailbox delete and permanent Trash/Junk cleanup remain live-blocked on this host by public Mail.app delete behavior.

## 0.1.0+codex.20260625223346 - 2026-06-25

### Added

- Added opt-in private Mail FTS indexing through `mail fts-build` / `mail_build_fts_index` and date-bounded FTS search through `mail fts-search` / `mail_search_fts`.
- Added v1.81 Mail FTS design coverage plus adapter, CLI, MCP, mutation-gate, surface-contract, and runtime verifier proof.

### Fixed

- FTS build requires date bounds and explicit confirmation because it writes a local durable private content cache; output returns only counts, `next_cursor`, and an opaque index ref, not cache paths or raw indexed text.
- FTS build now paginates with cursors, refuses `reset` on continuation cursors, rejects symlink/non-regular index, ancestor, and sidecar paths, closes failed schema-initialization connections, and reset removes the private index plus WAL/SHM/journal sidecars before rebuilding so removed text is not left in ordinary SQLite free pages or sidecar files.
- FTS search requires date bounds, opens the existing index read-only, revalidates live Mail rows, current date bounds, and local content state before returning exact handles, returns capped redacted snippets only, and does not return full body text, attachment bytes, cache paths, raw MIME, full headers, or full email addresses.
- FTS attachment results now keep attachment counts, safe filenames, and MIME types in separate metadata fields so MIME strings are not exposed as filenames.
- Background indexing, unbounded/bulk Mail body search, query-result auto-apply, mailbox/account management, permanent delete, empty Trash/Junk, templates/signatures, and sender selection outside create-draft remain blocked behind separate gates.

## 0.1.0+codex.20260625203752 - 2026-06-25

### Added

- Added opt-in Mail source attachment-like part forwarding for exact `forward_message` / `forward-message` through `include_source_attachments` / `--include-source-attachments`.
- Added v1.80 source-forward write design coverage plus adapter, CLI, MCP, and runtime verifier proof.

### Fixed

- Default Mail forward still refuses source attachments/non-body MIME parts unless the explicit source-forward flag is present; apply now binds uncapped header-only source part state into the token, confirms Mail-derived total forwarded attachment count before send, and returns only counts/booleans without source attachment bytes, paths, raw MIME, source body, or per-part Sent identity/content proof.
- Post-review hardening added inline/fileless non-body source-part coverage and >50 source-part planning coverage so the source-forward gate no longer depends on the public attachment-list cap.
- Sender selection outside create-draft, templates/signatures beyond signature clearing, mailbox/account management, permanent delete, empty Trash/Junk, HTML/rich-text mutation, query-result auto-apply, and unbounded bulk mutation remain blocked behind separate gates. Opt-in private Mail FTS indexing is covered by v1.81.

## 0.1.0+codex.20260625130020 - 2026-06-25

### Added

- Added opt-in Mail attachment content discovery through `mail_search_attachments(..., include_content=True)` and `local-apple-data mail attachment-search --include-content`.
- Added optional PDF OCR fallback with `include_ocr` / `--include-ocr`; PDF embedded text uses local `pdftotext`, OCR fallback uses local `ocrmypdf`, and both return capped redacted snippets only.
- Added v1.79 Mail attachment content search design coverage plus adapter, CLI, MCP, and runtime verifier proof.

### Fixed

- Mail attachment discovery now covers body-only attachment signals without returning attachment bytes, temp paths, source `.emlx` paths, full email addresses, or durable index paths.
- Durable Mail FTS/body or attachment indexing, broad attachment export, arbitrary document extraction beyond v1.79 snippets, and unbounded/bulk body search remain blocked behind separate gates.

## 0.1.0+codex.20260625114841 - 2026-06-25

### Added

- Added capped exact Mail bulk triage for repeated `--message-handle` / MCP `message_handles` on `mark_read`, `mark_unread`, `flag_message`, `unflag_message`, `archive_message`, `trash_message`, and `move_message`.
- Added v1.78 Mail bulk triage write-design coverage plus synthetic adapter, CLI, MCP, and runtime verifier proof for mixed applied/already-satisfied batches.

### Fixed

- Bulk triage binds every exact message handle, current read/flag/mailbox state, and target state into one approval fingerprint; apply preflights the whole batch before mutation and reports `partial` on mid-batch failure.
- Durable FTS indexing, attachment content/PDF/OCR search, source attachment forwarding, sender selection outside create-draft, mailbox/account management, permanent delete, and templates/signatures remain blocked behind separate gates.

## 0.1.0+codex.20260625105206 - 2026-06-25

### Added

- Added date-bounded Mail body discovery (`mail_search_body`, `local-apple-data mail body-search`) with capped redacted snippets and no full-body search output.
- Added date-bounded Mail attachment metadata discovery (`mail_search_attachments`, `local-apple-data mail attachment-search`) by filename/MIME with exact `mail:attachment:v1:` handles and no attachment bytes.
- Added date-bounded advanced Mail discovery (`mail_search_advanced`, `local-apple-data mail advanced-search`) across subject, masked headers, body snippets, and attachment filenames.
- Added Mail content paging with `offset`/`next_offset` and richer exact Mail metadata with masked sender/recipient fields, hashed Message-ID refs, and attachment names/types.
- Added v1.77 Mail search discovery design coverage, synthetic adapter/CLI/MCP tests, and runtime verifier proof for 93 MCP tools.

### Fixed

- Updated plugin, skill, privacy/threat/testing docs, handoff docs, and auditors so body/attachment Mail discovery is no longer documented as blocked.
- Durable FTS indexing, attachment content/PDF/OCR search, source attachment forwarding, sender selection outside create-draft, mailbox/account management, permanent delete, templates/signatures, and bulk triage remain blocked behind separate gates.

## 0.1.0+codex.20260625102848 - 2026-06-25

### Added

- Extended bounded caller-selected local file attachments from Mail draft creation to `send_message`, `reply_message`, `reply_all_message`, and `forward_message` through the existing exact plan/apply gate.
- Added v1.76 outbound attachment design coverage, synthetic apply tests, and runtime verifier proof for send/reply/reply-all/forward attachment count confirmation with no source-path handoff.

### Fixed

- Updated plugin, skill, mutation/privacy/threat/testing docs, and auditors so current contracts no longer certify the superseded draft-only attachment boundary.
- Source attachment/non-body-part forwarding, sender selection outside create-draft, mailbox/account management, permanent delete, templates/signatures, durable/unbounded Mail search, and bulk triage remain blocked behind separate gates.

## 0.1.0+codex.20260625051244 - 2026-06-25

### Added

- Added the v1.75 Mail draft-only local-file attachment gate for `create_draft` / `create-draft` through the existing Mail plan/apply tools, with bounded caller-selected files, plan-token file-identity binding, no path/byte output, mocked Mail.app automation proof, and attachment-count read-back when available.

### Fixed

- Hardened exact Mail attachment export so stale same-size payload drift invalidates `mail:attachment:v1:` handles and caller-selected export writes reject symlink output directories and symlink target escapes.
- Hardened Mail draft attachment apply so approval binds local file content SHA-256, same-size restored-mtime drift invalidates stale tokens, and Mail automation receives a private validated temporary copy rather than the mutable caller-selected source path.
- Hardened Mail forward read-back so multiple new matching Sent copies return `partial` with `ambiguous_forward_read_back` instead of false success.
- Documented that Mail send/reply/reply-all/forward attachments, Mail source attachment/non-body forwarding outside explicit `include_source_attachments`, templates/signatures beyond draft signature clearing, mailbox/account management, permanent delete, and bulk triage remain blocked.

## 0.1.0+codex.20260624182642 - 2026-06-24

### Fixed

- Post-finish adversarial audit fixes: sender search now matches only returned-safe masked fields, sender-selected draft apply fails closed on multiple new matching Drafts or saturated exact-subject candidates, CLI/MCP sender-handle propagation is explicitly tested, stale iCloud Drive permanent-delete docs are guarded by the write-design audit, and duplicate current-doc/source contract keys are regression-tested.
- Finalized the v1.74 Mail sender draft-selection install receipt after adversarial review hardening.
- Resynced the personal plugin and installed Codex cache with the final handoff, implementation-log, runtime-verifier, and audit state for the exact sender-selected create-draft gate.
- Artifact-hygiene verification now explicitly cleans generated installed-cache test/runtime artifacts before the final gate.

## 0.1.0+codex.20260624174626 - 2026-06-24

### Added

- Added the v1.74 Mail sender draft-selection gate through `mail_search_senders` / `mail_get_sender` and `local-apple-data mail senders/sender`.
- Mail sender metadata uses exact opaque `mail:sender:v1:` handles, masked sender previews, and no raw account identifiers or full sender emails in tool output.
- `create_draft` planning/apply now accepts optional `sender_handle`, binds the selected sender into the approval fingerprint, sets the public Mail.app `outgoing message.sender` property, disables broad matching-body idempotency for explicit sender selection, and requires sender read-back confirmation.

### Fixed

- Updated the Mail adapter, CLI, MCP wrappers, runtime verifier, mutation/write-design/surface/release auditors, plugin manifest, skill, README, capability/privacy/threat/testing/Codex-plugin docs, roadmap, CRUD priority plan, and synthetic tests for exact draft sender selection.
- Hardened sender-selected draft apply after adversarial review: plans now report `retry_safe:false`, apply snapshots existing Draft handles before writing, and read-back excludes preexisting same-subject/same-body Drafts before confirming `sender_selection_confirmed:true`.
- Sender selection remains intentionally blocked for `send_message`, `reply_message`, `reply_all_message`, and `forward_message` until a separate durable read-back design lands; raw sender emails, raw account IDs, SMTP IDs, mailbox handles, account refs, and delivery-account mutation are refused as sender selectors.

## 0.1.0+codex.20260624164842 - 2026-06-24

### Added

- Added the v1.73 Mail reply-all gate through `reply_all_message` / `reply-all-message` on the existing Mail plan/apply path.
- Reply-all planning now requires one exact `mail:message:v2:` source handle and bounded plaintext body, rejects caller-supplied recipients and subject overrides, and binds reply mode into the approval fingerprint.
- Reply-all apply uses the reviewed public Mail.app `reply ... reply to all true` scripting surface, requires a matching approval token plus explicit confirmation, does not echo the sent body, and verifies a local Sent-copy read-back when available.

### Fixed

- Updated the adapter, CLI, MCP wrappers, runtime verifier, mutation/write-design/surface/release auditors, plugin manifest, skill, README, changelog, and durable docs for exact Mail reply-all support.
- Mail sender-account selection, attachment send/reply/forward, Mail source attachment/non-body forwarding outside explicit `include_source_attachments`, permanent delete, mailbox/account management, templates/signatures, and bulk triage remain blocked pending separate source review and design gates.

## 0.1.0+codex.20260623232643 - 2026-06-23

### Added

- Added read-only Contacts container metadata through `contacts_search_containers`, `contacts_get_container`, `local-apple-data contacts containers`, and `local-apple-data contacts container`.
- Added the v1.72 Contacts group CRUD gate for exact group create, rename, and delete through the existing plan/apply path, with exact group/container handles, safe-state hashes, plan tokens, explicit confirmation, metadata-only read-back, and group-delete absence proof.
- Contact create can now target an exact selected Contacts container while preserving the default-container path.

### Fixed

- Updated the Swift Contacts helper, adapter, CLI, MCP wrappers, runtime verifier, mutation/write-design/surface/release auditors, plugin manifest, skill, README, and durable docs for the group/container gate.
- Contacts group delete deletes only the selected group, returns `contacts_deleted:false`, and does not expose raw Contacts identifiers.
- Contacts raw identifier input, broad contact dumps in chat, direct database writes, duplicate merge automation, and custom labels beyond bounded local labels remain blocked.

## 0.1.0+codex.20260623223452 - 2026-06-23

### Fixed

- Fixed the Contacts update apply path to use slash-stable Swift JSON canonicalization, allowing approved rich-field updates with URL fields to pass exact current-state comparison.
- A live synthetic Contacts rich update applied and verified read-back for postal address, birthday, date, social profile, instant-message address, and relation fields.

## 0.1.0+codex.20260623222313 - 2026-06-23

### Fixed

- Fixed Contacts update-state planning against live Contacts records by fetching formatter-safe update keys, preventing Swift scalar JSON crashes, and canonicalizing helper JSON-state strings before hash comparison.
- Live synthetic Contacts rich-update planning now reaches a valid exact approval token after a user-approved dummy contact create; apply still requires the matching token and explicit confirmation.

## 0.1.0+codex.20260623190000 - 2026-06-23

### Added

- Added Contacts group metadata tools through `contacts_search_groups`, `contacts_get_group`, `local-apple-data contacts groups`, and `local-apple-data contacts group`.
- Added the v1.71 Contacts gate for exact scalar/method/rich-field/image update, exact note append/set/clear/merge, exact group membership, capped exact batch, and exact delete through the existing plan/apply path.
- Runtime verification now covers Contacts rich update, set-note, group membership, and exact batch plan/apply without live personal data mutation.

### Fixed

- Updated the Swift Contacts helper, adapter, CLI, MCP wrappers, runtime verifier, mutation/write-design/surface auditors, plugin manifest, skill, README, and durable docs for the expanded Contacts gate.
- Contacts still blocks raw identifier input, broad contact dumps in chat, direct database writes, contact group create/rename/delete, duplicate merge automation, and custom labels beyond bounded local labels.

## 0.1.0+codex.20260623181335 - 2026-06-23

### Added

- Added read-only Contacts count and archive backup support through `contacts_count`, `contacts_export_archive`, `local-apple-data contacts count`, and `local-apple-data contacts export`.
- Contacts backup export now writes JSON, vCard, and manifest files to a caller-selected directory, returns count/file/hash metadata only, and reports `archive_verified` plus `counts_match` so cleanup workflows do not need broad/empty `contacts_search`.
- Added the v1.70 Contacts exact note append gate through the existing plan/apply path, requiring one exact `contacts:contact:v1:` handle, `note_safe_sha256`, exact approved `note_text`, matching approval token, explicit confirmation, stale-note refusal, and hash-only note read-back.

### Fixed

- Updated the Swift Contacts helper, CLI, MCP wrappers, runtime verifier, mutation/write-design/surface/release auditors, plugin manifest, skill, and docs for Contacts backup/count/export plus exact note append.
- Contacts `contacts_get` now exposes note state metadata (`note_status`, `note_chars`, `note_safe_sha256`) without returning existing note text.
- This is not full CRUD. Contacts note overwrite/delete, merge, group membership, image data, postal-address/birthday/relationship/social-profile/instant-message mutation, bulk operation, raw identifier use, and direct database writes remain blocked.

## 0.1.0+codex.20260623171841 - 2026-06-23

### Added

- Added the v1.69 Contacts exact method update gate for email, phone, and URL method arrays on one exact `contacts:contact:v1:` handle with `update_safe_sha256` binding.
- Contacts update now preserves omitted method arrays, replaces provided method arrays, and supports explicit empty-array clears through the approved plan/apply path.
- Added CLI `--clear-emails`, `--clear-phones`, and `--clear-urls` controls with clear-vs-replacement conflict refusal.

### Fixed

- Updated the Swift Contacts helper, MCP wrappers, runtime verifier, write-design/mutation-gate auditors, plugin manifest, and docs for the new exact Contacts method update surface.
- This is not full CRUD. Contacts merge, move/container management, group membership, notes/image/postal-address/birthday/relationship/social-profile/instant-message mutation, custom labels beyond bounded local labels, and bulk operations remain blocked.

## 0.1.0+codex.20260623160853 - 2026-06-23

### Added

- Added approved iCloud Drive exact text-file permanent delete support through the existing `delete_text` / `delete-text` plan/apply gate and new `docs/V1_68_ICLOUD_DRIVE_DELETE_TEXT_WRITE_DESIGN.md`.
- Delete-text now requires one exact selected supported `icloud:file:v1:` text-file handle, expected current content SHA-256, matching approval token, explicit confirmation, root-aware plan recomputation, exact file identity approval binding, stale-token replay refusal for recreated same-path/same-content files, random-only hidden staging identity proof, permanent unlink, and original absence proof.
- Runtime verification now proves direct and MCP delete-text plan/apply success, mutation applied, original absent, `verified_absent:true`, `permanently_deleted:true`, stale-token replay refusal as `invalid_approval_token`, `content_inspected:false` on stale identity-token refusal, `staging_path_returned:false`, and no content hash or content text return.

### Fixed

- Added deterministic regressions for preview-only planning, wrong-input refusal, fabricated handles, symlink/package/unsupported file refusal, root-aware CLI/MCP planning, stale content refusal, stale same-path/same-content token replay refusal, and random-only hidden staging names.
- Hardened delete-text approval tokens so a file recreated at the same path with the same content cannot reuse an old approval token.
- Hardened delete-text apply so stale identity-token refusal happens before content inspection, including post-token same-path/same-content replacement races.
- Updated mutation/write-design/release gates, plugin/skill docs, README, cross-agent routing, privacy/threat/testing docs, roadmap, and public-release fixtures so exact text-file delete is approved while file permanent delete outside the exact delete-text gate, empty Trash, non-empty or recursive folder delete, binary/document writes, hidden/raw-path writes, packages, symlinks, and network/private API fallback remain blocked.

## 0.1.0+codex.20260623142229 - 2026-06-23

### Added

- Added approved iCloud Drive exact empty folder permanent delete support through the existing `delete_folder` / `delete-folder` plan/apply gate and new `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`.
- Delete-folder now requires one exact selected empty `icloud:file:v1:` directory handle, expected directory `metadata_sha256`, matching approval token, explicit confirmation, metadata drift refusal, empty-folder recheck, hidden staging identity proof, permanent `rmdir`, original absence proof, and metadata-only read-back.
- Runtime verification now proves direct and MCP delete-folder plan/apply success, mutation applied, original absent, `verified_absent:true`, `permanently_deleted:true`, `staging_path_returned:false`, `empty_folder_confirmed:true`, and no content hash return.

### Fixed

- Added deterministic regressions for stale metadata, missing/invalid SHA input, malformed and fabricated handles, non-empty folders, symlink/package targets, race-to-non-empty rollback, staged-rmdir rollback, rollback failure partials, file-handle refusal, direct hidden-staging residue checks, and hidden staging root cleanup after successful delete.
- Hardened partial delete reporting so unverified rollback failures do not claim `verified_absent:true` or `permanently_deleted:true`.
- Updated mutation/write-design/release gates, plugin/skill docs, README, cross-agent routing, privacy/threat/testing docs, capability matrix, roadmap, and public-release fixtures so exact empty-folder delete is approved while file permanent delete, empty Trash, non-empty or recursive folder delete, binary/document writes, hidden/raw-path writes, packages, symlinks, and network/private API fallback remain blocked.

## 0.1.0+codex.20260623132618 - 2026-06-23

### Added

- Added approved Mail cross-account exact target-mailbox move support through the existing `move_message` plan/apply gate and new `docs/V1_66_MAIL_CROSS_ACCOUNT_MOVE_WRITE_DESIGN.md`.
- Cross-account target moves now require one exact selected `mail:message:v2:` handle, one exact selected non-Trash/Junk `mail:mailbox:v1:` target handle, stale read/flag/mailbox-state binding, matching approval token, explicit confirmation, separate source/target Mail.app account scoping, and local mailbox read-back.
- Runtime verification now proves cross-account move plan/apply/read-back, `target_account_relation:"cross_account"`, opaque source/target account refs, distinct refs, and raw account absence.

### Fixed

- Replaced stale blanket "Mail cross-account move blocked" docs with the precise current boundary: cross-account moves are allowed only through the exact target-mailbox gate, while raw account identifiers, fabricated handles, Trash/Junk targets through `move_message`, permanent delete, empty Trash/Junk, mailbox/account management, sender-account selection, reply-all, Mail source attachment/non-body-part forwarding outside explicit `include_source_attachments`, and bulk operations remain blocked.
- Removed opaque account refs from broad Mail message metadata output; account refs now stay scoped to mailbox selection and `move_message` preview proof.
- Added MCP wrapper coverage proving `mail_plan_change` and `mail_apply_change` forward the exact `target_mailbox_handle`.

## 0.1.0+codex.20260623123417 - 2026-06-23

### Added

- Added approved Reminders exact same-source list-move through `local-apple-data reminders lists`, `local-apple-data reminders list`, `reminders_search_lists`, `reminders_get_list`, and the existing Reminders plan/apply gate.
- List-move now binds one exact `reminders:reminder:eventkit:v1:` handle to one exact expected current-list `reminders:list:eventkit:v1:` handle, one exact target-list `reminders:list:eventkit:v1:` handle, expected title, expected completion state, expected current list name, matching approval token, and explicit confirmation.
- Runtime and MCP verification now prove list-handle opacity, direct and MCP list-move plan/apply success, `read_back.list_name:"Synthetic Target List"`, `read_back.target_list_verified:true`, same-title wrong-current-list refusal with `expected_state_mismatch` plus `mutation_applied:false`, and no failed-apply preview/fingerprint echo.

### Fixed

- Hardened Reminders list-move stale-state and read-back proof so duplicate current-list or target-list titles cannot satisfy success; the Swift helper now requires exact expected current-list identity, re-fetches the reminder after save, and returns `target_list_verified:true` only when the persisted target list identifier matches the internally resolved target list.
- Hardened Reminders apply errors so failed apply responses return `preview:null` and cannot echo approval fingerprints or exact list-move target fields.
- Added deterministic regressions for unresolved target-list handles, same-title wrong-current-list handles, failed-apply preview/fingerprint leakage, unverified target identity after apply, cross-account/source move refusal, stale current-list refusal before the already-target shortcut, and stale audit wording.

## 0.1.0+codex.20260623104455 - 2026-06-23

### Added

- Added read-only Messages exact selected-chat participant metadata through `messages_list_participants`, `messages_get_participant`, `local-apple-data messages participants`, and `local-apple-data messages participant`.
- Participant lists now return opaque `messages:participant:v1:` handles plus service/count/timestamp metadata without phone/email previews; full participant identifiers are exact participant-handle detail only and are not approved mutation targets.
- Added synthetic adapter, CLI, MCP, runtime-verifier, surface-contract, write-design, privacy/threat/testing/docs, skill, and manifest coverage for the Messages participant metadata read gate in `docs/V1_64_MESSAGES_PARTICIPANTS_METADATA.md`, including cross-chat handle-binding refusal and serialized MCP-list identifier absence proof.

## 0.1.0+codex.20260623095023 - 2026-06-23

### Fixed

- Hardened iCloud Drive exact empty folder copy after adversarial review: source drift after target create now attempts identity-checked target cleanup, successful cleanup returns `error` without leaving a copied target, cleanup failure returns `partial` with `cleanup_unverified` and `copied:false`, and target identity races withhold target handle and metadata for unverified replacements.
- Added deterministic regressions for invalid copy-folder target names, missing/invalid directory metadata SHA-256, successful source-race cleanup, cleanup-failure partials, and target identity replacement without stale metadata overclaiming.

## 0.1.0+codex.20260623093425 - 2026-06-23

### Added

- Added approved iCloud Drive exact empty folder copy planning/apply support through the existing iCloud Drive gate, limited to one exact empty `icloud:file:v1:` directory handle, one exact target-parent `icloud:file:v1:` directory handle, optional bounded target folder name, `metadata_sha256` binding, empty-folder refusal, no-overwrite target proof, source-preservation proof, target identity/read-back proof, CLI/MCP/runtime/audit/docs coverage, and the new `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md` gate.

### Fixed

- Added deterministic regressions for stale folder metadata, wrong inputs, self-parent refusal, non-empty folders, existing targets, target identity replacement returning `partial` instead of a false clean success, and successful copy read-back with zero warnings and no content hash.

## 0.1.0+codex.20260623084913 - 2026-06-23

### Added

- Added approved iCloud Drive exact empty folder move planning/apply support through the existing iCloud Drive gate, limited to one exact `icloud:file:v1:` directory handle, one exact target-parent `icloud:file:v1:` directory handle, `metadata_sha256` binding, empty-folder refusal, no-overwrite target proof, source/target metadata-only read-back, CLI/MCP/runtime/audit/docs coverage, and the new `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md` gate.

### Fixed

- Added deterministic regressions for stale folder metadata, wrong inputs, self-parent refusal, non-empty folders, existing targets, a race where a folder becomes non-empty during move apply, verified rollback for that race, post-move identity mismatch as `partial`, post-move read-back failure as `partial` with `mutation_applied:true`, and successful move read-back with zero warnings and no content hash.

## 0.1.0+codex.20260623074319 - 2026-06-23

### Added

- Added approved iCloud Drive exact empty folder Trash planning/apply support through the existing iCloud Drive gate, limited to one exact `icloud:file:v1:` directory handle, `metadata_sha256` binding, empty-folder refusal, recoverable Trash move, metadata-only original absence proof, CLI/MCP/runtime/audit/docs coverage, and the new `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md` gate.

### Fixed

- Added deterministic regressions for stale folder metadata, non-empty folders, file-handle refusal, a race where a folder becomes non-empty during Trash apply, verified rollback for that race, partial reporting when rollback cannot be verified, and metadata-only read-back with no content hash or Trash path return.

## 0.1.0+codex.20260623070750 - 2026-06-23

### Added

- Added approved iCloud Drive exact empty folder rename planning/apply support through the existing iCloud Drive gate, limited to one exact `icloud:file:v1:` directory handle, `metadata_sha256` binding, empty-folder refusal, no-overwrite fd-relative `renameatx_np` with `RENAME_EXCL` and `RENAME_NOFOLLOW_ANY`, metadata-only read-back, CLI/MCP/runtime/audit/docs coverage, and the new `docs/V1_60_ICLOUD_DRIVE_FOLDER_RENAME_WRITE_DESIGN.md` gate.

### Fixed

- Added deterministic regressions for stale folder metadata, non-empty folders, existing targets, file-handle refusal, idempotent same-name retry, a race where a folder becomes non-empty during rename apply, verified rollback for that race, and partial reporting when rollback cannot be verified.

## 0.1.0+codex.20260623060941 - 2026-06-23

### Added

- Added approved Notes exact empty child-folder delete planning/apply support through the existing Notes gate, limited to one exact normal child `notes:folder:v1:` handle, expected folder-title SHA-256 binding, pre-automation empty/root/smart-folder refusal, scoped Notes.app `delete targetFolder` automation, absence read-back, CLI/MCP/runtime/audit/docs coverage, and the new `docs/V1_59_NOTES_FOLDER_DELETE_WRITE_DESIGN.md` gate.

### Fixed

- Added deterministic regressions for non-empty child folders, child-folder-containing folders, stale folder-title hashes, smart-folder drift before apply, and generated AppleScript that rechecks empty folder state before deleting the selected folder.

## 0.1.0+codex.20260622211422 - 2026-06-22

### Added

- Added approved Notes exact child-folder create planning/apply support through the existing Notes gate, limited to one exact normal parent `notes:folder:v1:` handle, same-parent idempotency, scoped Notes.app `make new folder at targetFolder` automation, metadata-only read-back, selected-parent proof, CLI/MCP/runtime/audit/docs coverage, and the new `docs/V1_57_NOTES_FOLDER_CREATE_WRITE_DESIGN.md` gate.
- Added approved Notes exact-folder rename planning/apply support through the existing Notes gate, limited to one exact normal `notes:folder:v1:` handle, expected folder-title SHA-256 binding, scoped Notes.app `set name of targetFolder` automation, metadata-only read-back, idempotent already-applied retry handling, CLI/MCP/runtime/audit/docs coverage, and the new `docs/V1_58_NOTES_FOLDER_RENAME_WRITE_DESIGN.md` gate.

### Fixed

- Hardened Notes folder-create read-back so wrong returned folder IDs cannot falsely satisfy success unless the returned folder identity matches the expected title/account and selected-parent proof passes.
- Hardened Notes folder-create idempotency/read-back so smart folders cannot satisfy the normal child-folder create gate.

## 0.1.0+codex.20260622205906 - 2026-06-22

### Added

- Added exact Calendar alarm-offset create/update/delete support inside the existing Calendar plan/apply gate, with `alarm_offsets_minutes` and `expected_alarm_offsets_minutes` bound into previews, approval fingerprints, helper payloads, CLI/MCP inputs, synthetic runtime proof, and the new `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md` gate.

## 0.1.0+codex.20260622202006 - 2026-06-22

### Fixed

- Hardened Calendar update/delete apply so alarm-bearing events are refused by the Swift EventKit bounded-mutation guard until a separate alarm-offset design gate exists.
- Added deterministic source and write-design gate regressions proving alarm-bearing Calendar events remain unsupported instead of silently passing through exact update/delete apply.

## 0.1.0+codex.20260621230233 - 2026-06-21

### Added

- Added explicit Calendar all-day create/update/delete support inside the existing Calendar plan/apply gate, with `all_day` and `expected_all_day` bound into previews, approval fingerprints, helper payloads, read-back proof, CLI flags, MCP inputs, runtime verifier coverage, and the new `docs/V1_55_CALENDAR_ALL_DAY_WRITE_DESIGN.md` gate.

### Fixed

- Rejected non-boolean Calendar `all_day` / `expected_all_day` inputs before approval fingerprinting so string values such as `"false"` cannot bind as truthy values.
- Hardened Calendar update apply ordering so stale expected-state mismatch is checked before `already_applied` handling.

## 0.1.0+codex.20260621223742 - 2026-06-21

### Fixed

- Added deterministic synthetic Mail move regressions for exact same-account mailbox moves, stale target-mailbox refusal before Mail.app automation, cross-account target refusal, Trash/Junk-class target refusal, and generated AppleScript safety assertions that prove `move_message` does not send, delete, erase, or operate outside the exact selected mailbox target.
- Extended the write-design and release-readiness audit fixtures so future Mail move regression drift fails both direct write-gate checks and release-readiness tests.

## 0.1.0+codex.20260621221808 - 2026-06-21

### Added

- Added `scripts/audit_messages_public_surface.py`, a machine-readable public Messages SDEF guard that verifies the reviewed local scripting surface still exposes only `send`, `login`, and `logout`, that `send` keeps the reviewed text/file-to-chat/participant signature, and that risky Messages direct-recipient/new-chat/edit/delete/reaction/tapback/mark-read work remains blocked until a separate design gate is approved.

### Fixed

- Wired the Messages public-surface audit into release readiness, CI, packaging tests, write-design docs, testing/publication docs, and the durable handoff so public scripting drift cannot be mistaken for approved Messages CRUD expansion.
- Corrected the v1.33 CRUD priority table to include the already-approved exact-chat Messages send-file surface.

## 0.1.0+codex.20260621205649 - 2026-06-21

### Fixed

- Hardened iCloud Drive `rename-text` and `move-text` against post-hash race windows by using a no-overwrite target reservation plus no-follow swap, then verifying target identity and SHA-256 before removing the placeholder; failed proof now rolls back with identity checks or reports `partial` when rollback cannot be verified.
- Hardened iCloud Drive `copy-text` by re-reading the source after target read-back proof and identity-cleaning only the created target when the source drifts.
- Blocked hidden CLI iCloud Drive `--root` overrides for search/get/content/apply outside `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`, preserving synthetic tests without allowing arbitrary-root reads or writes in normal CLI use.
- Extended mutation/write-design gates, runtime proof, docs, and cross-agent sync coverage for rename/copy/move stale/target-exists checks, root-override regression tests, precise Contacts manifest wording, and `.gitignore`/`uv.lock` sync drift.

## 0.1.0+codex.20260621183938 - 2026-06-21

### Added

- Added approved iCloud Drive exact-file `rename-text`, `copy-text`, and `move-text` planning/apply support through the existing iCloud Drive approval-token and explicit-confirmation gate, with exact `icloud:file:v1:` handles, expected-current-SHA-256 binding, no-overwrite targets, fd-based no-follow location operations, source/target presence proof, copy source preservation proof, rename/move original-handle absence proof, target hash read-back without content text, partial-state reporting for cleanup/rollback uncertainty, CLI/MCP/docs updates, synthetic direct and MCP runtime coverage, and operation-contract audit coverage.

### Fixed

- Hardened mutation/release gates so iCloud Drive operation contracts now check adapter `PLAN_OPERATIONS`, CLI `--operation` choices, MCP `ICloudDriveOperation` Literal values, plugin manifest safety wording, and release-readiness required design docs from the write-design gate instead of relying on hand-maintained lists.
- Added deterministic copy/move stale-SHA refusal regressions and runtime proof keys, and fixed the stale Contacts mutation-gate row so exact scalar update/delete support is documented with its current-state bindings instead of described as blocked.

## 0.1.0+codex.20260621171438 - 2026-06-21

### Added

- Added approved iCloud Drive exact-file `trash-text` planning/apply support through the existing iCloud Drive approval-token and explicit-confirmation gate, with exact `icloud:file:v1:` handles, expected-current-SHA-256 drift refusal, supported text-file validation, fd-based no-follow atomic swap into recoverable Trash, post-swap SHA verification with swap-back on drift, no permanent unlink of the selected file, no raw Trash path return, original-handle absence proof, v1.53 design coverage, CLI/MCP/docs updates, synthetic runtime coverage, and operation-contract audit coverage.

## 0.1.0+codex.20260621154012 - 2026-06-21

### Fixed

- Refreshed the durable fresh-chat handoff after post-review verification so the installed-cache version and full-suite test count match the current source truth.

## 0.1.0+codex.20260621114650 - 2026-06-21

### Fixed

- Hardened the iCloud Drive create-folder proof path so `verify_runtime.py` now exercises successful `icloud_drive_plan_change` / `icloud_drive_apply_change` over the MCP server against a synthetic iCloud Drive root.
- Added write-design audit contracts for installed skill create-folder wording, privacy-model create-folder hash drift, and required source/runtime test evidence.
- Fixed stale `icloud-drive plan/apply` parent help text and removed stale replace-text hash language from the v1.52 create-folder privacy section.

## 0.1.0+codex.20260621113207 - 2026-06-21

### Added

- Added `--folder-name` as a CLI alias for iCloud Drive `create-folder` plan/apply, with deterministic conflict refusal when both `--filename` and `--folder-name` disagree.

## 0.1.0+codex.20260621112800 - 2026-06-21

### Fixed

- Added deterministic write-design audit coverage for the iCloud Drive create-folder documentation contract so future stale testing, threat-model, or earlier-gate supersession wording fails the release gates instead of relying on manual review.

## 0.1.0+codex.20260621112423 - 2026-06-21

### Fixed

- Fixed adversarially found stale testing/threat-model and historical iCloud Drive gate wording so create-folder is reflected in current test inventories, unauthorized-apply controls, and supersession notes for the earlier iCloud Drive create-text and append-text design gates.

## 0.1.0+codex.20260621111811 - 2026-06-21

### Fixed

- Fixed installed-skill/operator documentation drift for the iCloud Drive create-folder gate, including the MCP skill tool list, testing contract, macOS support matrix, and CLI acceptance examples so fresh Codex/Claude sessions see create-folder as an approved iCloud Drive apply path.

## 0.1.0+codex.20260621111147 - 2026-06-21

### Added

- Added approved iCloud Drive exact-parent create-folder planning/apply support through the existing iCloud Drive approval-token and explicit-confirmation gate, with exact `icloud:file:v1:` parent handles, no-follow parent validation, fd-relative exclusive `mkdir`, metadata-only read-back, existing-directory idempotency, v1.52 design coverage, CLI/MCP/docs updates, synthetic runtime coverage, and operation-contract audit coverage.

## 0.1.0+codex.20260621104632 - 2026-06-21

### Fixed

- Hardened iCloud Drive create/append/replace text apply paths after adversarial review: create now uses no-follow fd-based exclusive create, append preserves existing bytes while using same-directory temp replacement with a final SHA recheck, invalid UTF-8 write input fails closed, stale/refusal privacy flags report content inspection accurately, and append read-back mismatch plus CRLF-preservation regressions are covered.

## 0.1.0+codex.20260621094742 - 2026-06-21

### Added

- Added approved iCloud Drive exact-file replace-text planning/apply support through the existing iCloud Drive approval-token and explicit-confirmation gate, with exact `icloud:file:v1:` handles, expected-current-SHA-256 drift refusal, bounded UTF-8 replacement, same-directory atomic `os.replace`, read-back hash verification, destructive MCP annotation coverage, v1.51 design coverage, CLI/MCP/docs updates, synthetic runtime coverage, and operation-contract audit coverage.

### Fixed

- Hardened Mail send/reply Sent-copy confirmation so stale pre-existing Sent messages cannot falsely satisfy read-back proof.

## 0.1.0+codex.20260618165912 - 2026-06-18

### Fixed

- Hardened the Mail exact-message forward gate after adversarial audit: apply error/partial paths no longer echo body previews or source content, source forwards now refuse attachments plus non-body MIME parts such as inline images and calendar parts, exact-source Mail scripts support nested mailbox paths, release-readiness requires a public GitHub remote plus live advertised `HEAD`, public-release operator-doc references are allowlisted only for exact sync-list entries, and runtime/docs/tests now prove the stricter forward and release gates.

## 0.1.0+codex.20260618084918 - 2026-06-18

### Added

- Added approved Mail exact-message forward planning/apply support through the existing Mail approval-token and explicit-confirmation gate, with exact `mail:message:v2:` source handles, explicit recipients, direct-subject refusal, non-empty bounded plaintext prepend text, source attachment refusal, current source-state plus source-content-state plus zero-attachment-state binding, scoped Mail.app `forward ... opening window false` automation, stale Sent-copy exclusion for read-back proof when local Mail indexes the forward, no body/source-content echo in apply output, destructive/non-idempotent MCP annotation coverage, v1.50 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260618002509 - 2026-06-17

### Added

- Added approved Contacts exact delete planning/apply support through the existing Contacts approval-token and explicit-confirmation gate, with exact `contacts:contact:v1:` handles, `delete_safe_sha256` full-detail current-state binding, Contacts.framework `CNSaveRequest.delete`, strict absence proof, destructive MCP annotation coverage, v1.49 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260617234510 - 2026-06-17

### Added

- Added approved Contacts exact scalar update planning/apply support through the existing Contacts approval-token and explicit-confirmation gate, with exact `contacts:contact:v1:` handles, `update_safe_sha256` current-state binding, name/organization scalar replacement only, Contacts.framework `CNSaveRequest.update`, read-back verification, v1.48 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260617232623 - 2026-06-17

### Added

- Added a machine-checked Messages risky-mutation source-review gate documenting that local Messages scripting exposes no durable public edit/delete/reaction/tapback/mark-read/new-chat path; no new Messages mutation is approved, and exact-chat `send_text` / `send_file` remain the only Messages apply operations.

## 0.1.0+codex.20260617231638 - 2026-06-17

### Added

- Added approved Mail exact-message same-account move planning/apply support through the existing Mail approval-token and explicit-confirmation gate, with bounded mailbox target search/detail, exact `mail:message:v2:` and `mail:mailbox:v1:` handles, current read/flag/mailbox state binding, same-account and Trash/Junk-class target refusal, scoped Mail.app move automation, local mailbox read-back verification, v1.46 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260616024851 - 2026-06-15

### Added

- Added approved Notes exact-note move-to-folder planning/apply support through the existing Notes approval-token and explicit-confirmation gate, with exact `notes:note:v2:` and `notes:folder:v1:` handles, expected-current-content SHA-256 binding, same-account and smart-folder refusal, scoped Notes.app `move targetNote to targetFolder` automation, target-folder read-back proof, `body_returned:false` apply output, v1.45 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260616022946 - 2026-06-15

### Added

- Added approved Mail exact-message sender-only reply planning/apply support through the existing Mail approval-token and explicit-confirmation gate, with exact `mail:message:v2:` source handles, direct-recipient and direct-subject refusal, current source-state binding, scoped Mail.app `reply ... reply to all false` automation, Sent-copy read-back proof when local Mail indexes the reply, no body echo in apply output, destructive/non-idempotent MCP annotation coverage, v1.44 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260616014445 - 2026-06-15

### Added

- Added approved Mail send-message planning/apply support through the existing Mail approval-token and explicit-confirmation gate, with bounded plaintext recipients/subject/body, irreversible-send preview metadata, scoped Mail.app send automation, Sent-copy read-back proof when local Mail indexes the sent message, no body echo in apply output, destructive MCP annotation for `mail_apply_change`, v1.43 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260616010932 - 2026-06-15

### Added

- Added approved Notes exact-note delete planning/apply support through the existing Notes approval-token and explicit-confirmation gate, with exact `notes:note:v2:` handles, expected-current-content SHA-256 binding, locked/shared-note refusal, scoped Notes.app delete automation, exact-handle absence read-back verification, destructive MCP annotation for `notes_apply_change`, v1.42 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260616004051 - 2026-06-15

### Added

- Added approved Mail exact-message move-to-Trash planning/apply support through the existing Mail approval-token and explicit-confirmation gate, with same-account Trash mailbox resolution, current read/flag/mailbox state binding, scoped Mail.app move automation, local mailbox read-back verification, destructive MCP annotation for `mail_apply_change`, v1.41 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260616001534 - 2026-06-15

### Added

- Added approved Mail exact-message archive planning/apply support through the existing Mail approval-token and explicit-confirmation gate, with same-account Archive mailbox resolution, current read/flag/mailbox state binding, scoped Mail.app move automation, local mailbox read-back verification, v1.40 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260616000158 - 2026-06-15

### Added

- Added approved Notes exact-folder create planning/apply support through the existing Notes approval-token and explicit-confirmation gate, with read-only folder metadata search/detail, opaque `notes:folder:v1:` handles, stale/smart-folder refusal, scoped Notes.app folder targeting, folder membership read-back proof, v1.39 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260615231812 - 2026-06-15

### Added

- Added approved Messages exact-chat send-file planning/apply support through the existing Messages approval-token and explicit-confirmation gate, with exact `messages:chat:v1:` handles, local file identity binding, scoped Messages.app file-send automation, local outgoing attachment read-back verification, v1.38 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260615230659 - 2026-06-15

### Added

- Added approved Mail exact-message flag/unflag planning/apply support through the existing Mail approval-token and explicit-confirmation gate, with exact `mail:message:v2:` handles, current read/flag state binding, scoped Mail.app `flagged status` automation, local read-back verification, v1.37 design coverage, CLI/MCP/docs updates, and synthetic runtime coverage.

## 0.1.0+codex.20260615223943 - 2026-06-15

### Added

- Added approved Calendar exact-event delete planning/apply support through the existing Calendar approval-token and explicit-confirmation gate, with exact `calendar:event:v1:` handles, expected current-state binding, unsupported-event refusal, EventKit removal, read-back absence proof, destructive MCP annotation for `calendar_apply_change`, and synthetic runtime coverage.

## 0.1.0+codex.20260615221016 - 2026-06-15

### Added

- Added approved Mail exact-message mark-read/mark-unread planning/apply support through the existing Mail plan approval-token, explicit-confirmation, scoped Mail.app automation, stale-state refusal, and local read-back path.
- Added approved Reminders title, notes, and priority update planning/apply support through the existing Reminders approval-token, explicit-confirmation, EventKit apply, notes-hash/priority expected-state checks, and read-back path.
- Added approved Reminders exact-handle delete planning/apply support through the existing Reminders approval-token and explicit-confirmation gate, with expected completed state, expected priority, current notes-hash drift refusal, EventKit removal, read-back absence proof, and destructive MCP annotation for `reminders_apply_change`.
- Added approved Calendar exact-event update planning/apply support through the existing Calendar plan approval-token, explicit-confirmation, EventKit apply, expected-state refusal, and read-back path.
- Added approved Notes replace-text planning/apply support through the existing Notes approval-token, explicit-confirmation, Notes.app automation, expected-current-SHA drift refusal, locked/shared-note refusal, and exact-content read-back path.

## 0.1.0+codex.20260615200540 - 2026-06-15

### Added

- Added the v1.33 full CRUD priority plan for Mail, Messages, Calendar, Reminders, and Notes, with staged exact-handle mutation priorities and explicit gate requirements.
- Added approved Reminders `uncomplete` planning/apply support through the existing plan approval-token, explicit-confirmation, EventKit apply, and read-back path.

### Changed

- Updated the Reminders write design, mutation gates, runtime verifier, skill, manifest, and operator docs so the approved Reminders write surface is stated as create, complete, uncomplete, and due-date update.

## 0.1.0+codex.20260615193405 - 2026-06-15

### Fixed

- Hardened the internal, unexposed Mail read-flag triage resolver so it recovers the RFC Message-ID from the selected local `.emlx` header and fails closed when that identity bridge is unavailable instead of using the Envelope Index integer hash.
- Removed public-release scanner wording hits from the v1.32 Mail triage design note.

## 0.1.0+codex.20260605130000 - 2026-06-05

### Fixed

- Documented that `verify_cross_agent_sync.py` verifies Claude MCP CLI/config state as `mcp_cli_connected` and does not replace a fresh Claude Desktop GUI health-tool proof.

## 0.1.0+codex.20260605125500 - 2026-06-05

### Fixed

- Renamed the Claude surface status reported by `verify_cross_agent_sync.py` from `mcp_connected` to `mcp_cli_connected` so release receipts do not imply a live Claude Desktop GUI tool invocation when the verifier checks the Claude MCP CLI connection.

## 0.1.0+codex.20260605124000 - 2026-06-05

### Fixed

- Required `.gitignore` and its local-secret/config ignore rules in release-readiness audits so `.env`, `.env.*`, and `.claude` exclusions remain present in release candidates.

## 0.1.0+codex.20260605123400 - 2026-06-05

### Fixed

- Added source `.gitignore` coverage and tests for local `.env*` and `.claude` paths so secret/config hygiene matches the personal-plugin sync and artifact-audit exclusions.

## 0.1.0+codex.20260605122200 - 2026-06-05

### Fixed

- Added a tested plugin artifact-hygiene audit for personal and installed plugin roots so stale `.env*`, `.claude`, `.venv`, generated cache, bytecode, `.DS_Store`, `dist`, and `build` artifacts are detected with redacted JSON output.

## 0.1.0+codex.20260605120600 - 2026-06-05

### Fixed

- Added a tested personal-plugin sync helper that uses `rsync --delete-excluded` and local-secret/config plus generated-file exclusions so stale `.env*`, `.claude`, `.venv`, cache, bytecode, and `.DS_Store` files do not linger in the personal plugin source or installed cache.

## 0.1.0+codex.20260605120000 - 2026-06-05

### Fixed

- Redacted unexpected MCP readiness tool failures for `apple_data_health` and `apple_data_doctor` to safe error payloads with exception class names only.

## 0.1.0+codex.20260605115600 - 2026-06-05

### Fixed

- Redacted unexpected top-level `local-apple-data` CLI command failures to exception class names instead of raw traceback or path-bearing exception text.

## 0.1.0+codex.20260605114800 - 2026-06-05

### Fixed

- Redacted path-bearing or exception-style top-level `verify_cross_agent_sync.py` `RuntimeError` messages while preserving curated safe mismatch summaries.

## 0.1.0+codex.20260605114200 - 2026-06-05

### Fixed

- Broadened adapter warning-message sanitizer coverage for glued local paths, additional Apple framework error-domain tokens, and all implemented opaque handle namespaces.

## 0.1.0+codex.20260605113500 - 2026-06-05

### Fixed

- Added shared adapter warning-message sanitization so helper or plan warning payloads with path-bearing or exception-style text are replaced before returning to callers.

## 0.1.0+codex.20260605113000 - 2026-06-05

### Fixed

- Redacted `scripts/render_mcp_client_config.py` CLI failure stderr to exception class names while preserving direct API exceptions for tests and callers.

## 0.1.0+codex.20260605112500 - 2026-06-05

### Fixed

- Replaced Reminders SQLite degraded store/schema/query warning messages with stable generic text instead of exception-derived text.

## 0.1.0+codex.20260605112000 - 2026-06-05

### Fixed

- Extended the synthetic runtime verifier to assert export privacy metadata for successful exports and legacy invalid export handles across Mail, Messages, Notes, Voice Memos, and Photos.

## 0.1.0+codex.20260605111200 - 2026-06-05

### Fixed

- Corrected Mail, Messages, Notes, Voice Memos, and Photos export privacy metadata so failed, degraded, invalid-handle, and unavailable export responses no longer claim content was exported.

## 0.1.0+codex.20260605111000 - 2026-06-05

### Fixed

- Replaced Messages, Voice Memos, and inferred Hide My Email degraded store warning messages with stable generic text, and corrected Voice Memos content/export degraded privacy shapes.

## 0.1.0+codex.20260605110500 - 2026-06-05

### Fixed

- Replaced Mail and Notes degraded store/schema warning messages with stable generic text instead of exception-derived text.

## 0.1.0+codex.20260605110000 - 2026-06-05

### Fixed

- Redacted public-release tree and public git-checkout CLI failure messages to exception class names instead of raw exception text.

## 0.1.0+codex.20260605105000 - 2026-06-05

### Fixed

- Redacted release-readiness required-file read failures and public-checkout failures to relative filenames or exception class names instead of raw filesystem exception text.

## 0.1.0+codex.20260605104000 - 2026-06-05

### Fixed

- Redacted unexpected top-level cross-agent verifier exceptions to exception class names while preserving the verifier's own safe `RuntimeError` diagnostics.

## 0.1.0+codex.20260605103000 - 2026-06-05

### Fixed

- Improved cross-agent file sync failures to report a bounded aggregate of source, personal plugin source, and installed-cache mismatches without printing file contents or raw filesystem errors.

## 0.1.0+codex.20260605101200 - 2026-06-05

### Fixed

- Expanded cross-agent sync verification to recursively compare dynamically discovered docs, scripts, skills, plugin manifests, GitHub templates, runtime package files, and tests across source, personal plugin source, and installed cache while excluding generated caches.

## 0.1.0+codex.20260605100600 - 2026-06-05

### Fixed

- Degraded raised Shortcuts runner OS and subprocess errors to a generic unavailable warning without returning raw runner details.

## 0.1.0+codex.20260605100000 - 2026-06-05

### Fixed

- Degraded Mail, Notes, and Messages AppleScript runner OS errors to safe read/write warning codes without returning raw exception details.

## 0.1.0+codex.20260605095300 - 2026-06-05

### Fixed

- Degraded raised Music and TV AppleScript runner OS errors to generic unavailable warning codes without returning raw exception details.

## 0.1.0+codex.20260605094400 - 2026-06-05

### Fixed

- Bounded the release-readiness git remote probe so unavailable or timed-out git remote checks degrade to a warning instead of stalling the audit.

## 0.1.0+codex.20260605093900 - 2026-06-05

### Fixed

- Rejected option-like or non-plain git remote names from the GitHub publication-readiness gate.

## 0.1.0+codex.20260605093300 - 2026-06-05

### Fixed

- Required the release-readiness GitHub publication gate to use a publication-safe `github.com` remote instead of any safe HTTPS/SSH git host.

## 0.1.0+codex.20260605092000 - 2026-06-05

### Fixed

- Required every URL for a git remote name to pass publication-safe validation before release-readiness counts that remote.

## 0.1.0+codex.20260605091100 - 2026-06-05

### Fixed

- Required a publication-safe HTTPS/SSH git remote before release-readiness reports GitHub publication readiness.

## 0.1.0+codex.20260605085700 - 2026-06-05

### Fixed

- Normalized cross-agent verifier OpenClaw runner path comparisons and expanded resolver rejection/precedence tests.

## 0.1.0+codex.20260605085000 - 2026-06-05

### Fixed

- Made the cross-agent sync verifier resolve the canonical source project from a configured OpenClaw runner when invoked from an installed plugin cache.

## 0.1.0+codex.20260605084500 - 2026-06-05

### Fixed

- Rejected percent-encoded dash-leading usernames or hosts in `ssh://` public checkout remotes and tightened the dash-user regression assertion.

## 0.1.0+codex.20260605084000 - 2026-06-05

### Fixed

- Rejected dash-leading usernames in `ssh://` public checkout remotes and tightened the remote transport helper typing.

## 0.1.0+codex.20260605083500 - 2026-06-05

### Fixed

- Rejected credentialed public checkout remotes, dash-leading remote hosts/users/paths, insecure transports, and malformed HTTPS/SSH remote URLs before staging release files.

## 0.1.0+codex.20260605083000 - 2026-06-05

### Fixed

- Limited public checkout remote URLs to HTTPS and SSH forms and rejected internal whitespace, non-ASCII, local-path, `file://`, and `ext::` transports before staging release files.

## 0.1.0+codex.20260605082300 - 2026-06-05

### Fixed

- Rejected public checkout remote URLs with control characters, surrounding whitespace, or whitespace-prefixed option-like values before staging release files.

## 0.1.0+codex.20260605081500 - 2026-06-05

### Fixed

- Rejected option-like public checkout remote URLs and expanded validation-failure tests to prove invalid branch inputs do not create destination trees.

## 0.1.0+codex.20260605081000 - 2026-06-05

### Fixed

- Validated public checkout Git options before staging release files so invalid branches, commit identities, or remotes cannot create or replace destination trees.

## 0.1.0+codex.20260605080400 - 2026-06-05

### Fixed

- Rejected reserved Git pseudo-ref names during public checkout branch validation and added explicit regression coverage for branch shorthand/ref-prefixed names.

## 0.1.0+codex.20260605075300 - 2026-06-05

### Fixed

- Made public Git checkout branch validation work from non-Git installed plugin cache directories while still rejecting invalid branch refnames.

## 0.1.0+codex.20260605075000 - 2026-06-05

### Fixed

- Hardened public Git checkout branch validation with Git refname checks and rejection of branch shorthand/ref-prefixed names before `git init`.

## 0.1.0+codex.20260605074300 - 2026-06-05

### Fixed

- Omitted source branch names from release receipts while preserving source commit and dirty-state traceability.

## 0.1.0+codex.20260605073800 - 2026-06-05

### Fixed

- Added source git commit and dirty-state traceability to path-redacted release receipts.

## 0.1.0+codex.20260605072800 - 2026-06-05

### Fixed

- Blocked release receipt `--output` paths inside the source checkout so generated artifacts cannot accidentally dirty a release candidate.

## 0.1.0+codex.20260605072200 - 2026-06-04

### Fixed

- Expanded release-readiness required-file coverage to include publication, redaction, receipt, and cross-agent regression tests.

## 0.1.0+codex.20260605071700 - 2026-06-04

### Fixed

- Added a top-level matched-value-free redaction scan summary to generated release receipts.

## 0.1.0+codex.20260605071300 - 2026-06-04

### Fixed

- Added the redaction scanner as a release-readiness blocker so high-confidence secret or alias findings fail local package readiness.

## 0.1.0+codex.20260605070900 - 2026-06-04

### Fixed

- Added matched-value-free JSON output to the redaction scanner for safer automated release logs.

## 0.1.0+codex.20260605070400 - 2026-06-04

### Fixed

- Added an explicit root argument and JSON output mode to the public-release scanner for safer automated release receipts and staged-tree checks.

## 0.1.0+codex.20260605065800 - 2026-06-04

### Fixed

- Kept local env files and key/certificate-like artifacts out of the public-release scanner and generated public tree.

## 0.1.0+codex.20260605065400 - 2026-06-04

### Fixed

- Expanded cross-agent source/personal/cache sync verification to include release and publication tooling regression tests.

## 0.1.0+codex.20260605063600 - 2026-06-04

### Fixed

- Added a clean-git-worktree gate to the release-readiness auditor so uncommitted source changes block local package readiness before a release receipt or public checkout is treated as clean.

## 0.1.0+codex.20260605054500 - 2026-06-04

### Fixed

- Added the Contacts.framework formatter-required key descriptor to the native Contacts helper so exact contact-detail reads cannot crash when formatting a selected contact display name.

### Documentation

- Documented that GUI MCP clients require their own macOS privacy grants, and that live local validation remains dependent on the host process identity that launches the MCP server.

## 0.1.0+codex.20260605053000 - 2026-06-04

### Fixed

- Reduced Codex plugin default prompts to the supported maximum of three prompts so fresh Codex sessions load the manifest without dropping prompt entries.

### Documentation

- Documented that GUI MCP clients such as Claude Desktop need their own macOS privacy grants; a connected MCP server can still report degraded health if the host app lacks Full Disk Access or framework permissions.

### Notes

- This is a packaging hygiene/cache-buster release. The v1.31 Apple Freeform metadata runtime surface is unchanged.

## 0.1.0+codex.20260605050000 - 2026-06-04

### Added

- Read-only Apple Freeform recent-board metadata listing through `local-apple-data freeform boards` and MCP `freeform_list_boards`.
- Exact selected Apple Freeform board metadata retrieval through `local-apple-data freeform get` and MCP `freeform_get_board`.
- Read-only Apple Freeform folder title metadata search through `local-apple-data freeform folders` and MCP `freeform_search_folders`.
- Exact selected Apple Freeform folder metadata retrieval through `local-apple-data freeform folder` and MCP `freeform_get_folder`.
- Synthetic Freeform SQLite fixtures, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Freeform metadata surface.

### Security

- Freeform board listing returns recency, favorite/collaborator-cursor flags, item counts, and asset-reference counts only; board titles are not returned because the title/content lives in BLOB/CRDT data.
- Freeform folder search returns folder-title metadata only for specific folder-title queries.
- Board BLOB decoding, board content export, asset export, previews, collaboration payloads, raw identifiers, raw `boards.db` rows, broad dumps, and Freeform mutation remain blocked.

## 0.1.0+codex.20260605040000 - 2026-06-04

### Added

- Read-only Apple TV item metadata search through `local-apple-data tv search` and MCP `tv_search`.
- Exact selected Apple TV item metadata retrieval through `local-apple-data tv get` and MCP `tv_get_item`.
- Read-only Apple TV playlist metadata search through `local-apple-data tv playlists` and MCP `tv_search_playlists`.
- Exact selected Apple TV playlist metadata retrieval through `local-apple-data tv playlist` and MCP `tv_get_playlist`.
- Synthetic TV.app automation runner, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the TV metadata surface.

### Security

- TV search returns item/playlist metadata and opaque handles only; raw TV identifiers, file paths, video bytes, artwork, descriptions, playback state, watched state, ratings, and broad playlist item dumps are not returned.
- The first TV tranche uses bounded read-only TV.app automation because the local `Library.tvdb` format is proprietary and not SQLite.
- TV playback, queue changes, playlist mutation, rating/favorite mutation, library import/delete, video export, file-path export, raw TV library parsing, iCloud media fetch, and broad library dumps remain blocked.

## 0.1.0+codex.20260605030000 - 2026-06-04

### Added

- Read-only Apple Music track metadata search through `local-apple-data music search` and MCP `music_search`.
- Exact selected Apple Music track metadata retrieval through `local-apple-data music get` and MCP `music_get_track`.
- Read-only Apple Music playlist metadata search through `local-apple-data music playlists` and MCP `music_search_playlists`.
- Exact selected Apple Music playlist metadata retrieval through `local-apple-data music playlist` and MCP `music_get_playlist`.
- Synthetic Music.app automation runner, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Music metadata surface.

### Security

- Music search returns track/playlist metadata and opaque handles only; raw Music identifiers, file paths, audio bytes, lyrics, play history, ratings, and playlist track dumps are not returned.
- The first Music tranche uses bounded read-only Music.app automation because the local `Library.musicdb` format is proprietary and not SQLite.
- Music playback, queue changes, playlist mutation, rating/favorite mutation, library import/delete, audio export, lyrics export, raw Music database parsing, and broad library dumps remain blocked.

## 0.1.0+codex.20260605020000 - 2026-06-04

### Added

- Read-only Apple Podcasts show metadata search through `local-apple-data podcasts search` and MCP `podcasts_search`.
- Exact selected Apple Podcasts show metadata retrieval through `local-apple-data podcasts get` and MCP `podcasts_get_show`.
- Bounded selected-show episode listing through `local-apple-data podcasts episodes` and MCP `podcasts_list_episodes`.
- Exact selected-episode bounded description retrieval through `local-apple-data podcasts episode` and MCP `podcasts_get_episode`.
- Synthetic Apple Podcasts SQLite fixtures, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Podcasts surface.

### Security

- Podcasts search returns show metadata and opaque handles only; raw show IDs, feed URLs, web URLs, local paths, and episode descriptions are not returned.
- Episode descriptions are returned only after an exact `podcasts:episode:v1:` handle from the selected-show episode flow.
- Transcript text/export, audio/video bytes, feed/enclosure URL extraction, broad episode-description dumps/search, raw Podcasts identifiers/paths, iCloud media fetch, Podcasts.app automation, and Podcasts mutation remain blocked.

## 0.1.0+codex.20260605010000 - 2026-06-04

### Added

- Read-only Apple Books library metadata search through `local-apple-data books search` and MCP `books_search`.
- Exact selected Apple Books metadata retrieval through `local-apple-data books get` and MCP `books_get`.
- Exact selected-book annotation listing through `local-apple-data books annotations` and MCP `books_list_annotations`, with bounded highlight/note text.
- Synthetic Apple Books SQLite fixtures, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Books surface.

### Security

- Books search returns title/author/genre metadata and opaque handles only; raw asset IDs, local paths, and annotation UUIDs are not returned.
- Annotation text is returned only after an exact `books:book:v1:` handle from the Books metadata flow.
- Book/chapter text extraction, PDF/EPUB parsing, broad annotation dumps/search, raw local book paths, iCloud fetch, and Books mutation remain blocked.

## 0.1.0+codex.20260605000000 - 2026-06-04

### Added

- Read-only Apple Shortcuts shortcut/folder metadata search through `local-apple-data shortcuts search` and MCP `shortcuts_search`.
- Exact selected Shortcuts metadata retrieval through `local-apple-data shortcuts get` and MCP `shortcuts_get_item`.
- Synthetic Shortcuts CLI runner, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Shortcuts metadata surface.

### Security

- Shortcuts search returns names and opaque handles only; raw Shortcuts identifiers are not returned.
- The Shortcuts surface does not run, open, view, sign, export, or return shortcut bodies/action graphs.
- Shortcut creation, update, delete, duplication, import, signing, dynamic run tools, folder-scoped handles, Shortcuts SQLite scraping, and mutation remain blocked.

## 0.1.0+codex.20260604235900 - 2026-06-04

### Added

- Read-only Safari bookmarks and Reading List search through `local-apple-data safari search` and MCP `safari_search`.
- Exact selected Safari bookmark or Reading List URL detail through `local-apple-data safari get` and MCP `safari_get_item`.
- Synthetic plist adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Safari read surface.

### Security

- Safari search returns title/domain metadata only and does not return full URLs.
- Full URLs are returned only by exact opaque `safari:item:v1:` handle.
- Safari history, open tabs/iCloud tabs, private browsing data, cookies, passwords, browser caches, page content, browser sessions, Safari UI automation, and bookmark mutation remain blocked.

## 0.1.0+codex.20260604230000 - 2026-06-04

### Added

- Approved Messages send-text apply through `local-apple-data messages apply` and MCP `messages_apply_change`.
- Non-mutating Messages send-text planning through `local-apple-data messages plan` and MCP `messages_plan_change`.
- Exact-existing-chat handle binding, body-hash approval tokens, explicit confirmation, stale chat-state refusal, Messages.app automation, ghost-row detection, and local `chat.db` read-back verification for Messages send-text apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Messages send-text apply surface.

### Security

- `messages_apply_change` is the only approved Messages mutation tool and is non-destructive, idempotent, and closed-world at the MCP annotation level.
- Apply output confirms the send by metadata and body SHA-256 but does not echo the sent body text.
- Direct-recipient sends, new chat creation, SMS fallback selection, outgoing-account selection, file sends, rich text/effects, reactions/tapbacks, edit, unsend, delete, group management, participant lookup, broad Messages text search, and Messages attachment mutation remain blocked by mutation gates.

## 0.1.0+codex.20260604220000 - 2026-06-04

### Added

- Exact Messages transcript fallback for modern local `message.attributedBody` typedstream rows when `message.text` is empty.
- Native Swift helper coverage for extracting bounded plaintext from exact selected Messages rows without returning raw attributed-body blobs or attributes.
- Synthetic unit, runtime, helper presence, release-readiness, and cross-agent sync coverage for the attributed-body fallback path.

### Security

- Messages `attributedBody` decoding remains exact-chat only, bounded by existing `max_messages` and `max_chars` caps, and never exposes raw typedstream payloads, participant identifiers, reactions, source paths, or message database row IDs.
- If one attributed-body value cannot be decoded safely, the adapter returns a stable warning and preserves any normal text rows plus any individually decodable fallback rows.

## 0.1.0+codex.20260604210000 - 2026-06-04

### Added

- Exact-handle Messages attachment metadata listing through `local-apple-data messages attachments` and MCP `messages_list_attachments`.
- Exact-handle local Messages attachment export through `local-apple-data messages export-attachment` and MCP `messages_export_attachment`.
- Synthetic Messages `chat.db` attachment metadata/export, unavailable-media, CLI, MCP, runtime, surface-contract, and redacted-log coverage.

### Security

- Messages attachment bytes are never returned inline, source media paths are never returned, and export writes only to a caller-selected output directory.
- Export requires both the selected `messages:chat:v1:` chat handle and selected `messages:attachment:v1:` attachment handle so a detached token cannot trigger a broad Messages media scan.
- Messages send/edit/delete, broad attachment export, participant identifiers, reactions, source paths, remote/iCloud media fetch, and attachment mutation remain blocked.

## 0.1.0+codex.20260604200000 - 2026-06-04

### Added

- Exact-handle Mail attachment metadata listing through `local-apple-data mail attachments` and MCP `mail_list_attachments`.
- Exact-handle local Mail MIME attachment export through `local-apple-data mail export-attachment` and MCP `mail_export_attachment`.
- Synthetic MIME attachment export, externalized/partial attachment unavailable, CLI, MCP, runtime, surface-contract, and redacted-log coverage for Mail attachment export.

### Security

- Mail attachment bytes are never returned inline, source `.emlx` or attachment paths are never returned, and remote or externalized missing attachments are not fetched.
- Export requires both the selected `mail:message:v2:` message handle and selected `mail:attachment:v1:` attachment handle so the tool does not scan the whole Mail store to resolve a detached token.
- Mail send/reply/forward, attachment mutation, broad attachment export, raw MIME/full-header exposure, and mailbox/account mutation remain blocked.

## 0.1.0+codex.20260604190000 - 2026-06-04

### Added

- Exact-handle Notes attachment metadata listing through `local-apple-data notes attachments` and MCP `notes_list_attachments`.
- Exact-handle local Notes attachment export through `local-apple-data notes export-attachment` and MCP `notes_export_attachment`.
- Synthetic media-file export, BLOB fallback, remote-only unavailable, CLI, MCP, runtime, surface-contract, and redacted-log coverage for Notes attachment export.

### Security

- Notes attachment bytes are never returned inline, source media paths are never returned, and remote attachment URLs are not fetched.
- Notes attachment creation, replacement, deletion, rename, move, OCR, transcription, broad export, and attachment mutation remain blocked.

## 0.1.0+codex.20260604180000 - 2026-06-04

### Added

- Approved Notes append-text apply through the existing `local-apple-data notes apply` and MCP `notes_apply_change` surfaces.
- Non-mutating Notes append-text planning through `local-apple-data notes plan` and MCP `notes_plan_change`.
- Exact-note-handle, expected-current-SHA-256, approval-token, explicit-confirmation, bounded plaintext append, drift-refusal, shared/locked-note refusal, and exact-content read-back verification checks for Notes append-text apply.
- Synthetic adapter, CLI, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the expanded Notes apply surface.

### Security

- `notes_apply_change` remains non-destructive, idempotent, and closed-world at the MCP annotation level; append-text refuses to apply when the current note content hash no longer matches the approved plan.
- Notes arbitrary update, delete, move, folder/account targeting, rich text, attachments, locked/shared-note mutation, Recently Deleted management, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604170000 - 2026-06-04

### Added

- Approved iCloud Drive append-text apply through the existing `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` surfaces.
- Non-mutating iCloud Drive append-text planning through `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change`.
- Exact-file-handle, expected-current-SHA-256, approval-token, explicit-confirmation, bounded UTF-8 append, drift-refusal, and read-back hash verification checks for iCloud Drive append-text apply.
- Synthetic adapter, CLI, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the expanded iCloud Drive text apply surface.

### Security

- `icloud_drive_apply_change` remains non-destructive, idempotent, and closed-world at the MCP annotation level; append-text refuses to apply when the current content hash no longer matches the approved plan.
- iCloud Drive overwrite, rename, move, copy, delete, binary/document writes, raw path writes, hidden-file writes, symlink/package traversal, and broad folder writes remain blocked by mutation gates.

## 0.1.0+codex.20260604160000 - 2026-06-04

### Added

- Approved Photos image/video import apply through `local-apple-data photos apply` and MCP `photos_apply_change`.
- Non-mutating Photos import planning through `local-apple-data photos plan` and MCP `photos_plan_change`.
- Approval-token, explicit-confirmation, source-file hash binding, PhotoKit change-block import, and created-asset read-back verification checks for Photos import apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Photos import apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, `calendar_apply_change`, `contacts_apply_change`, `notes_apply_change`, `mail_apply_change`, and `photos_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Photos permanent delete/Recently Deleted empty, album targeting, hidden/favorite mutation, metadata mutation, network iCloud fetch, thumbnails, inline asset bytes, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604150000 - 2026-06-04

### Added

- Approved Mail create-draft apply through `local-apple-data mail apply` and MCP `mail_apply_change`.
- Non-mutating Mail create-draft planning through `local-apple-data mail plan` and MCP `mail_plan_change`.
- Approval-token, explicit-confirmation, bounded recipient/subject/body, save-only Mail.app automation, best-effort idempotency, and local Drafts read-back verification checks for Mail create-draft apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Mail draft apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, `calendar_apply_change`, `contacts_apply_change`, `notes_apply_change`, and `mail_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Mail send, reply, forward, archive, move, delete, mark read/unread, flag, mailbox/account management, attachments, HTML/rich-text drafts, sender-account selection, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604140000 - 2026-06-04

### Added

- Approved Notes create-note apply through `local-apple-data notes apply` and MCP `notes_apply_change`.
- Non-mutating Notes create-note planning through `local-apple-data notes plan` and MCP `notes_plan_change`.
- Approval-token, explicit-confirmation, bounded title/body, idempotency, Notes.app automation, and exact-content read-back verification checks for Notes create-note apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Notes apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, `calendar_apply_change`, `contacts_apply_change`, and `notes_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Notes append, update, delete, move, folder/account targeting, rich text, attachments, locked/shared-note mutation, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604130000 - 2026-06-04

### Added

- Approved Contacts create-contact apply through `local-apple-data contacts apply` and MCP `contacts_apply_change`.
- Non-mutating Contacts create-contact planning through `local-apple-data contacts plan` and MCP `contacts_plan_change`.
- Approval-token, explicit-confirmation, bounded labeled email/phone/URL, idempotency, and read-back verification checks for Contacts create-contact apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Contacts apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, `calendar_apply_change`, and `contacts_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Contacts update, delete, merge, move, group membership, postal addresses, birthdays, relationships, social profiles, notes, image data, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604120000 - 2026-06-04

### Added

- Approved Calendar create-event apply through `local-apple-data calendar apply` and MCP `calendar_apply_change`.
- Non-mutating Calendar create-event planning through `local-apple-data calendar plan` and MCP `calendar_plan_change`.
- Approval-token, explicit-confirmation, explicit-calendar-title, timed-event, idempotency, and read-back verification checks for Calendar create-event apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, and `calendar_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Calendar update, delete, recurrence, attendees, invitations, alarms, all-day events, default-calendar guessing, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604110000 - 2026-06-04

### Added

- Approved iCloud Drive create-text apply through `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change`.
- Non-mutating iCloud Drive create-text planning through `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change`.
- Approval-token, explicit-confirmation, exact-parent-handle, exclusive-create, idempotency, and read-back verification checks for iCloud Drive create-text apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved apply surface.

### Security

- `reminders_apply_change` and `icloud_drive_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- iCloud Drive append, overwrite, rename, move, copy, delete, binary/document writes, broad folder writes, and raw path writes remain blocked by mutation gates.

## 0.1.0+codex.20260604100000 - 2026-06-04

### Added

- Approved Reminders apply through `local-apple-data reminders apply` and MCP `reminders_apply_change`.
- Apply support for Reminder create, complete, and due-date update through the Swift EventKit helper.
- Approval-token, explicit-confirmation, expected-state, idempotency, and read-back verification checks for Reminders apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved apply surface.

### Security

- `reminders_apply_change` is the only non-read-only MCP tool and is annotated non-destructive, idempotent, and closed-world.
- All non-Reminders mutation surfaces remain blocked by mutation gates.

## 0.1.0+codex.20260604090000 - 2026-06-04

### Added

- Preview-only Reminders planning through `local-apple-data reminders plan` and MCP `reminders_plan_change`.
- Deterministic `reminders-plan:v1:` idempotency keys plus approval fingerprints for future apply-token binding.
- Synthetic adapter, CLI, MCP, runtime, redacted-log, surface-contract, and packaging coverage for Reminders planning.

### Security

- Reminders planning returns `mutation_applied:false` and `apply_available:false`, does not call EventKit, and does not mutate Reminders.
- Apply-capable Reminders tools remain absent.

## 0.1.0+codex.20260604080000 - 2026-06-04

### Added

- Public Reminders write design gate for future create/complete/due-date operations through EventKit, with preview/apply/read_back contract language and explicit approval requirements.
- Write-design gate auditor that fails when required write design docs drift or preview/apply/read_back-style CLI/MCP tools appear before approval.
- Release-readiness, CI, staged-public-tree, cross-agent sync, and path-redacted release receipt coverage for the write-design gate.

### Security

- The current release remains read-only. The new Reminders write document is design-only and exposes no mutating CLI or MCP tools.

## 0.1.0+codex.20260604074000 - 2026-06-04

### Added

- Read-only local Apple data CLI and stdio MCP server.
- Codex plugin manifest, bundled skill, and MCP runner script.
- Metadata-first search plus exact opaque-handle detail/content flows for Mail, Messages, inferred Hide My Email aliases, Voice Memos, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive.
- Exact Mail plain-text content, Notes plain-text content, Reminder notes, Calendar details, Contact details, Photos asset/resource metadata, Messages bounded transcripts, Voice Memos existing embedded transcripts, iCloud Drive text-file content, and inferred Hide My Email selected alias detail.
- Synthetic unit, CLI, MCP, runtime, packaging, and redaction tests.
- macOS GitHub Actions workflow with tests, compile, Swift helper typechecks, runtime smoke, and redaction scan.
- Public capability matrix, mutation gates, publishing checklist, install guide, sample outputs, macOS support notes, security policy, and MIT license.
- Notes content pagination for long imported notes through `offset`, `content_total_chars`, and `next_offset`.
- Public release scan for local-path/operator-term leakage in publishable files.
- Release-readiness audit for required files, version/changelog consistency, public scan status, sanitized git-checkout prep, and git remote presence.
- Public release tree builder for staging the sanitized publishable file set outside the working repo.
- Public git-checkout preparer for creating a sanitized local GitHub-ready checkout without pushing, including optional initial local commit creation.
- MCP client config renderer for generic stdio, Claude Code, Cursor, and OpenClaw configuration, including compact server-object output for CLI registration commands.
- Optional Cursor MCP config verification in the cross-agent sync verifier, with explicit `--require-cursor` and `--cursor-config` controls.
- Exact-handle Photos asset export and Voice Memos `.m4a` export to caller-selected output directories without returning media bytes inline.
- Broad-surface health and doctor readiness covering Messages, Voice Memos, iCloud Drive, normalized per-surface summaries, and non-prompting access requirements in addition to Mail, Notes, and Reminders schema checks.
- Mutation-gate auditor that fails release readiness if write-like CLI/MCP surfaces appear before a mutation gate is intentionally approved.
- CI and staged-public-tree verification run the mutation-gate audit.
- Surface-contract auditor that fails release readiness if supported Apple data surfaces drift across MCP tools, CLI commands, health summaries, access requirements, and `docs/CAPABILITY_MATRIX.md`.
- CI and staged-public-tree verification run the surface-contract audit.
- Public contributor guide plus GitHub PR and issue templates that require synthetic fixtures, redaction checks, surface-contract checks, and explicit mutation-gate review for write-like changes.
- Path-redacted release receipt generator for reviewer handoff before a GitHub push or tag, with committed public checkout proof and CI coverage in source and staged public trees.
- Public ecosystem review comparing current Apple Notes, Messages, Voice Memos, iCloud Drive, and official Apple framework references against this plugin's broad-surface exact-handle architecture.

### Security

- The current release is read-only and local-only.
- Search is metadata-first; content/detail retrieval requires exact opaque handles returned by metadata tools.
- Runtime avoids Gmail API, IMAP, OAuth, app passwords, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, network mail services, telemetry, background indexing, and durable personal-content caches.

### Deferred

- Mutating tools.
- Attachments, broad content search, broad Messages text search, generated Voice Memos transcription, Contact notes/images, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, private iCloud web/API paths, and arbitrary binary/document extraction.
