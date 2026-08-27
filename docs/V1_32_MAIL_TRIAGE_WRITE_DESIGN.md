# v1.32 Mail Triage Write Design

Status: Stage 1 apply-capable implementation for `mark_read` and `mark_unread`; `archive_message` later landed under `docs/V1_40_MAIL_ARCHIVE_WRITE_DESIGN.md`; `trash_message` later landed under `docs/V1_41_MAIL_TRASH_WRITE_DESIGN.md`; exact target-mailbox move later landed under `docs/V1_46_MAIL_MOVE_WRITE_DESIGN.md`; cross-account exact target extension later landed under `docs/V1_66_MAIL_CROSS_ACCOUNT_MOVE_WRITE_DESIGN.md`. This is the design-gate artifact required by `docs/WRITE_TOOL_ROADMAP.md` and
`docs/MUTATION_GATES.md` before any additional Mail triage apply operation is implemented and exposed.

This document defines the next Mail write lane after `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md` (create-draft):
bounded, **reversible** triage of one exact existing message — mark read/unread, move to an exact existing
mailbox, archive, and move-to-Trash — through Mail.app automation, with preview as the default behavior and
independent read_back verification after apply.

It is the enabler for an assisted "inbox zero" flow: an agent searches the inbox, previews a triage action on
one exact message, applies only after explicit approval, and reads the message back through the normal
metadata path to confirm the new state.

## Hard Safety Invariant — No Permanent Deletion

This tranche never permanently deletes mail. The only "delete" operation is `trash_message`, which **moves**
the message to the account's Trash mailbox, where it remains recoverable until the user (not the plugin)
empties Trash from Mail.app. The generated automation must never:

- Call any permanent-delete / erase verb (no `delete` on a message that bypasses Trash, no "Erase Deleted
  Messages", no emptying of any Trash/Junk mailbox).
- Move a message already in Trash anywhere except back out (no compounding toward permanent loss).
- Operate on more than one exact message per apply (no bulk delete).

Permanent deletion of mail is out of scope for this plugin and is not unlocked by any approval token. Every
operation in this tranche is reversible by the user from Mail.app.

## Scope

Candidate operations (each on exactly one existing message identified by an opaque `mail:message:v2:` handle):

- `mark_read` — set the message's read flag to read.
- `mark_unread` — set the message's read flag to unread.
- `move_message` — move the message to one exact existing target mailbox identified by an opaque mailbox
  marker (see Mailbox Targeting). Cross-account exact targets are governed by `docs/V1_66_MAIL_CROSS_ACCOUNT_MOVE_WRITE_DESIGN.md`.
- `archive_message` — move the message to the resolved Archive mailbox of the message's own account. A named
  convenience over `move_message`.
- `trash_message` — move the message to the resolved Trash mailbox of the message's own account (the reversible
  "delete"). Never a permanent delete.

Out of scope (remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`):

- Permanent delete, emptying Trash/Junk, or any erase verb.
- Flag/unflag, junk/not-junk classification, and any flag other than the read state (deferred to a later
  design).
- Send, reply, forward, redirect, draft mutation (covered or deferred elsewhere).
- Cross-account moves outside the V1.66 exact target-mailbox gate, mailbox/folder creation, rename, deletion, or account management.
- Bulk or batch triage over query results, threads, or conversations.
- Raw Mail database row IDs, mailbox URLs, local `.emlx`/SQLite paths, or account identifiers as user inputs.
- Mutations through Gmail, IMAP, OAuth, iCloud.com, browser sessions, keychain credentials, private iCloud
  APIs, network mail APIs, or external connectors.

## Tool Contract

Every operation keeps the same three-step shape used by the approved write surfaces:

- `preview`: validate input and return the planned change without touching Mail.app or the local Mail
  database.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through the normal Mail metadata adapter.

These reuse the existing `mail plan` / `mail_plan_change` and `mail apply` / `mail_apply_change` surfaces by
adding the new operations to the Mail operation set; no new tool names are introduced. `mail_plan_change`
stays read-only; `mail_apply_change` keeps non-read-only annotations and gains a destructive annotation for
`trash_message` (see MCP Annotations).

### Preview payload

The preview payload must include: the operation; the opaque target message handle (echoed, not resolved to a
raw id); for moves, the opaque target mailbox marker and its resolved kind (`archive` / `trash` / `named`);
the message's bound expected-state fingerprint (see Expected State); warning codes; and a deterministic
idempotency key. It must not include raw Mail identifiers, local database/`.emlx` paths, mailbox URLs, account
identifiers, subjects, senders, unrelated mail content, or AppleScript exception text.

### Apply payload

The apply payload must require an approval token (`mail-apply:v1:<approval_fingerprint>`) generated from the
preview. The token must bind the operation, the message handle, the target mailbox marker (for moves), and the
expected-state fingerprint, so an agent cannot apply a different mutation, on a different message, or against a
drifted message, with a stale preview. Apply must additionally require an explicit confirmation flag, recompute
the plan, and re-check expected state immediately before mutating.

### Read_back payload

The read_back payload must return the message's post-mutation state through the existing Mail metadata shape,
using opaque `mail:message:v2:` handles. For `mark_read`/`mark_unread` it confirms the new read flag. For
`move_message`/`archive_message`/`trash_message` it confirms the message now resolves inside the target
mailbox (located by stable message-id within the destination, because a move can re-key the local handle). It
must not trust the AppleScript call alone.

## Implementation Choice

Reuse the existing Python Mail adapter plus Mail.app AppleScript automation, exactly as create-draft does:

- Python owns CLI/MCP request validation, approval-token verification, expected-state binding and drift
  refusal, Mail.app AppleScript generation, idempotency through the existing local Mail read path, logging,
  redaction, and JSON response shape.
- Mail.app automation owns the actual read-flag set and mailbox move, because Apple Mail exposes
  `read status` and `mailbox` assignment for a message through its local scripting dictionary.
- The MCP server stays stdio and local-only.

Two automation primitives cover all five operations: set a message's `read status`, and set a message's
`mailbox` (move). `archive_message` and `trash_message` are `move_message` to the account's resolved special
mailboxes. This keeps the mutating surface minimal and auditable.

## Mailbox Targeting

Moves never accept a raw mailbox URL or path. A read-only mailbox-listing helper returns opaque
`mail:mailbox:v1:` markers bound to `(account, mailbox-name, kind)`; `move_message` accepts exactly one such
marker. `archive_message`/`trash_message` accept no mailbox input and resolve the special mailbox of the
message's own account. V1.66 extends this for exact cross-account targets only through opaque source/target account refs; raw account identifiers remain forbidden.

## Expected State (drift refusal)

Edits to an existing object require an exact handle plus an expected current-state fingerprint, mirroring the
iCloud Drive / Notes append "expected current SHA-256" pattern. The fingerprint is a SHA-256 over the message's
stable identity and mutable state at preview time: message-id, current mailbox marker, current read flag, and
account marker. Apply recomputes the fingerprint immediately before mutating and refuses with a
`stale_message_state` warning if it differs (the message was moved, read, or changed since preview). This
prevents triaging the wrong message or re-triaging a message a human already moved.

## Idempotency

The apply path must be retry-safe and must not create durable personal-content caches:

- `mark_read`/`mark_unread`: if the message is already in the requested read state, return `already_applied`
  without running automation.
- `move_message`/`archive_message`/`trash_message`: if the message already resolves inside the target mailbox,
  return `already_applied` without running automation.
- The idempotency key is derived from the operation, message-id, target mailbox marker (for moves), and
  approval token. Any local operation ledger stores only opaque operation IDs, warning codes, timestamps, and
  fingerprints — never subjects, senders, mailbox names, or handles.

## MCP Annotations

- `mail_plan_change` stays read-only (`mutation_applied:false`, `apply_available:true`).
- `mail_apply_change` stays non-read-only. MCP annotations are static per tool, so once `trash_message` is
  exposed the whole tool is annotated **destructive** and non-idempotent as an honest signal that the same
  apply surface can move a message to Trash, even though `mark_read`, `mark_unread`, `flag_message`,
  `unflag_message`, and `archive_message` remain bounded and recoverable by the user.
- The runtime verifier and MCP tests must prove the destructive annotation is present for `mail_apply_change`.

## Logging And Redaction

Same requirement as `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md`, applied to previews, applies, runtime smoke,
tests, and release receipts.

Logs may include: tool name, operation, status, warning code, counts, duration.

Logs must not include: subjects, senders, recipients, body text, mailbox names or URLs, opaque message/mailbox
handles, raw Mail identifiers, local Mail database or `.emlx` paths, account identifiers, expected-state
fingerprints, approval tokens or fingerprints, or AppleScript exception text.

## Synthetic Tests Required

Before exposure, the implementation must add (using synthetic SQLite/`.emlx` rows and mocked Mail.app
automation only — no real Mail writes in tests):

- Preview success tests for each of `mark_read`, `mark_unread`, `move_message`, `archive_message`,
  `trash_message`.
- Preview validation tests: invalid/unknown operation, missing or malformed message handle, missing mailbox
  marker for `move_message`, malformed mailbox marker, and raw-account/fabricated target refusal and V1.66 exact cross-account target success.
- Apply/read_back success tests per operation with mocked automation responses and synthetic post-state rows.
- Missing-confirmation and invalid/mismatched-token tests.
- Stale-handle / expected-state-drift refusal tests (message moved or read since preview).
- Automation timeout/error tests.
- Idempotency tests: re-apply when already in target read state / target mailbox returns `already_applied`.
- **Permanent-deletion-refusal test**: assert the generated automation for `trash_message` contains only a
  move to the Trash mailbox and never a permanent-delete/erase/empty verb, and that no operation deletes a
  message already in Trash.
- Redaction tests proving logs contain no subjects, senders, body text, mailbox names, handles, fingerprints,
  tokens, raw identifiers, raw paths, or raw exceptions.
- MCP annotation tests proving `mail_apply_change` is not read-only and is statically destructive because the
  tool can run `trash_message`.

## Approval Gate

Before any apply-capable Mail triage tool is exposed (per `docs/MUTATION_GATES.md`), staged so that
non-destructive writes are proven before the Trash move:

1. `docs/MUTATION_GATES.md` must name each approved operation.
2. `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
3. `scripts/audit_mutation_gates.py` must continue to allow only the exact approved CLI and MCP names
   (`mail apply` / `mail_apply_change`), now covering the new operations.
4. `scripts/audit_write_design_gates.py` must move each operation from design-only to approved-with-tests.
5. Runtime smoke must prove the write annotations are non-read-only, and that `mail_apply_change` is statically destructive once `trash_message` is exposed.
6. The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin
   manifest must describe the new state consistently.

### Staged rollout (prove non-destructive first)

- Stage 1 — `mark_read` / `mark_unread`: pure reversible read-state toggle, lowest risk. Implement and prove first.
- Stage 2 — `archive_message`: landed separately in `docs/V1_40_MAIL_ARCHIVE_WRITE_DESIGN.md`.
- Stage 3 — `trash_message`: landed separately in `docs/V1_41_MAIL_TRASH_WRITE_DESIGN.md`; reversible move-to-Trash, annotated destructive, gated last.
- Stage 4 — `move_message`: landed separately in `docs/V1_46_MAIL_MOVE_WRITE_DESIGN.md`; exact target mailbox handles, with cross-account exact targets governed by `docs/V1_66_MAIL_CROSS_ACCOUNT_MOVE_WRITE_DESIGN.md` and Trash/Junk-class target refusal.

Each stage lands with its full test matrix and auditor coverage before the next stage's apply path is exposed.

## Implementation Plan (Stage 1: mark read/unread)

This is the executable spec for the first stage, sequenced so the safe, fully-testable pieces land before
the one step that needs real Mail.app validation. Investigation 2026-06-12 confirmed the technical pieces.

### Confirmed technical facts

- The message opaque handle is `make_int_handle("mail:message", ROWID)` (Envelope Index `messages.ROWID`),
  validated by `is_int_handle(handle, "mail:message")` and resolved by `_resolve_mail_handle_rowid`.
- The read flag is `messages.read`; the mailbox is `messages.mailbox` → `mailboxes.url`
  (`imap://<account-UUID>/<mailbox>`). Read-flag read + read-back work straight from the DB.
- **CORRECTION from real-Mail validation 2026-06-12 (supersedes an earlier claim that `messages.message_id`
  is the RFC Message-ID):** it is NOT. `messages.message_id` is an INTEGER hash (e.g.
  `-3543720719788426468`), not the RFC Message-ID string. AppleScript addresses a message by its RFC
  `message id` (string) — which the Envelope Index does not store as text and `get_mail_content` does not
  expose — OR by AppleScript's integer `id`, which does NOT equal the Envelope Index ROWID (verified:
  AppleScript ids 1251-1253 vs DB ROWIDs 1299-1301, different spaces and ordering). **There is no shared
  integer key between the Envelope Index and Mail.app.** The correct bridge must read the RFC Message-ID from
  the message's `.emlx` headers; the V10 `.emlx` path for non-iCloud-local mailboxes still needs to be pinned
  down (content was `content_unavailable` for the validated message). This is the one unsolved piece.
- **PROVEN against live Mail (reversibly, on the `iCloud test mailbox`):** the read-flag MUTATION itself —
  `set read status of (messages of mailbox "<name>" of account id "<UUID>" whose message id is "<rfc>")` —
  matches exactly one message and flips read↔unread, confirmed by read-back, restored to original. Accounts
  resolve via `id of every account` (id == the Envelope-Index account UUID). So once the resolver sources the
  RFC Message-ID correctly, the apply path is validated.
- The apply pattern, approval-token/fingerprint helpers (`_approval_fingerprint`, `_approval_token`,
  `_plan_idempotency_key`), injectable `ScriptRunner` (`script_runner=` for mocked tests), `_apply_success` /
  `_apply_error`, and `_run_osascript` already exist for create-draft and are reused verbatim.

### Sub-unit A — pure helpers (safe to land now; no exposed mutation)

- `_resolve_triage_target(connection, handle, *, mail_root) -> dict | None`: handle → ROWID → `SELECT m.read,
  mb.url` (join mailboxes); parse `mb.url` into account id + mailbox name; recover the RFC Message-ID from
  the exact local `.emlx` header for that ROWID; return `{message_id, mailbox_name, account_id, read,
  mailbox_ref}` or None for an unknown/deleted handle. If the selected local `.emlx` file or Message-ID
  header is unavailable, fail closed with `message_identity_unavailable`; do not use the Envelope Index
  `messages.message_id` integer hash as an AppleScript identity.
- `_mail_set_read_status_script(*, message_id, account, mailbox_name, target_read) -> str`: AppleScript that
  scopes to `account id "<account-id>"` → `mailbox "<mailbox_name>"`, selects `(messages whose message id is
  "<rfc>")`, and sets `read status` to the target. Must AppleScript-escape every interpolated string (reuse
  `_applescript_string`) and must contain NO delete/move verb. (For Stage 2/3, `_mail_move_message_script`
  mirrors this with `move … to mailbox` and never a permanent-delete verb.)
  - **OPEN ITEM needing real Mail.app (the specific crux):** prove the `.emlx` lookup works for the selected
    real mailbox layout before exposure. Live validation already proved `account id "<UUID>"` from
    `mailboxes.url` scopes Mail.app correctly; the remaining bridge is the exact RFC Message-ID recovery path.
- `_triage_expected_state_fingerprint(target, *, operation) -> str`: SHA-256 over `(message_id, mailbox_ref,
  read, operation)`.
- Tests: synthetic SQLite (mirroring `tests/test_mail_adapter.py` fixtures) for the resolver; pure-string
  assertions for the script generator including a **permanent-deletion-refusal assertion** (no erase/empty/
  delete verb) and an injection-escape assertion.

### Sub-unit B — plan/apply implementation

- `plan_mail_triage(operation, *, message_handle, db_path=None)` for `mark_read`/`mark_unread`: validate
  operation + handle, resolve target, `already_satisfied` when the read flag already matches, build the
  expected-state-bound approval fingerprint, return the standard plan contract.
- `apply_mail_triage(..., approval_token, confirm_apply, script_runner=None, db_path=None)`: re-plan, verify
  confirm + token, re-resolve and refuse on `stale_message_state` drift, run the script via the injectable
  runner, then read-back via `get_mail_metadata(handle)` and confirm `read` flipped; `already_applied` short-
  circuit. Reuses `_apply_success`/`_apply_error`.
- Tests: preview success/validation, apply/read-back with a mocked runner + synthetic post-state row,
  missing-confirmation, invalid-token, drift refusal, automation error, idempotency, redaction.

### Sub-unit C — Stage 1 exposure

- Wire `mark_read`/`mark_unread` into the public `plan_mail_change`/`apply_mail_change` dispatch (accept
  `message_handle`), add to `PLAN_OPERATIONS`, thread through `cli.py` and `mcp_server.py`.
- Flip gates: add the operations to `docs/MUTATION_GATES.md`, move them candidate→approved in
  `WRITE_TOOL_ROADMAP.md`, register them in `scripts/audit_write_design_gates.py` REQUIRED_DESIGN_DOCS as
  approved-with-tests, and keep `scripts/audit_mutation_gates.py` green (tool names unchanged). Update skill,
  README, privacy/threat model, capability matrix, changelog, plugin manifest; bump version.
- **Real-Mail validation gate:** the mocked-runner tests prove the token/expected-state/read-back/idempotency
  contract but CANNOT prove the AppleScript addresses the correct real message (account+mailbox+message-id
  scoping). Stage 1 exposure is allowed only after the repo has a real-Mail `.emlx` RFC Message-ID bridge proof
  and synthetic tests. Archive exposure later landed under `docs/V1_40_MAIL_ARCHIVE_WRITE_DESIGN.md`; Trash
  exposure later landed under `docs/V1_41_MAIL_TRASH_WRITE_DESIGN.md`; exact target-mailbox move later landed under `docs/V1_46_MAIL_MOVE_WRITE_DESIGN.md`; cross-account exact target extension later landed under `docs/V1_66_MAIL_CROSS_ACCOUNT_MOVE_WRITE_DESIGN.md`.

Cross-account move, mailbox/account management, and permanent delete still require their own future gates.

## Current Release Gate

The current release exposes Stage 1 `mark_read` / `mark_unread`, v1.37 `flag_message` / `unflag_message`,
v1.40 `archive_message`, v1.41 `trash_message`, v1.43 `send_message`, v1.44 `reply_message`,
v1.46 `move_message`, v1.50 `forward_message`, v1.73 `reply_all_message`, and v1.78 capped exact bulk triage through `mail plan` / `mail apply` and
`mail_plan_change` / `mail_apply_change`. Mail reply outside the v1.44 sender-only gate or v1.73 reply-all gate, forward outside the
v1.50 exact-message default no-source-attachments/no-non-body-parts gate, source attachment/non-body-part forwarding outside explicit `include_source_attachments`, cross-account move outside the V1.66 exact target-mailbox gate,
mailbox/account management, sender-account selection outside the exact create-draft sender gate, attachment mutation outside approved draft/send/reply/reply-all/forward local-file gates, HTML/rich-text mutation, query-result auto-apply,
unbounded bulk operations, send outside the v1.43 send-message gate, and any permanent deletion remain blocked by
`docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.
