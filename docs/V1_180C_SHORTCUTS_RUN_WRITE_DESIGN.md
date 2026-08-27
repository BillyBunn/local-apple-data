# v1.180C Shortcuts Run Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data shortcuts apply` and `shortcuts_apply_run`.

The new `local-apple-data shortcuts plan` and `shortcuts_plan_run` tools preview an
exact identifier-bound shortcut run as a non-mutating preview, and the matching apply
tools invoke the approved shortcut and report the invocation proof. No new mutating
tool names are approved or exposed by this document beyond the shortcuts plan/apply
run pair.

This is an operator-authorized reversal of the metadata-only Shortcuts policy for the
narrow, hard-gated `operation:run` case only. Reading Shortcuts metadata
(`shortcuts_search` / `shortcuts_get_item` / `shortcuts_list_folder_items`) is
unchanged, and shortcut bodies are still never returned.

## Why this is the most dangerous gate in the plugin

Running a shortcut executes arbitrary user-defined actions. A shortcut can do
anything the operator can: run shell scripts, delete files, send messages, post to
the network, mutate other apps. The gate therefore CANNOT prove what a shortcut did;
it can only prove that the exact named shortcut was invoked with the exact bound
input. It is treated exactly like the most dangerous existing mutation gates
(send/delete): plan/apply with a matching approval token plus explicit confirmation.

## Scope

Allowed:

- `operation:run` of exactly one shortcut, resolved by an exact
  `shortcuts:item:v1:` metadata handle whose kind is `shortcut` and which carries a
  stable identifier.
- An optional bounded plaintext input (capped at 4000 characters, NUL-rejected)
  passed to the shortcut.

Blocked:

- Auto-run: apply requires `confirm_apply=true` plus a matching
  `shortcuts-apply:v1:<approval_fingerprint>` token from the plan.
- Fuzzy-name / raw-name run: the shortcut is resolved by an exact metadata handle,
  never a caller-supplied name that could be spoofed. The resolved identifier is
  bound into the approval fingerprint.
- Running arbitrary inline shortcut definitions, importing shortcuts, editing
  shortcuts, or running a folder handle.
- Shell interpretation of any argument: the shortcut is invoked by argv, never a
  shell string.

## Exact-handle resolution and anti-spoofing

The plan resolves the `shortcuts:item:v1:` handle against live `shortcuts list
--show-identifiers` output. Resolution requires the handle to map to an item whose
kind is `shortcut` (not a folder) and which has an identifier-backed handle; a folder
handle is refused with `unsupported_item_kind`, and an identifier-less handle is
refused with `shortcut_identifier_unavailable`. The resolved identifier is what apply
runs (`shortcuts run <identifier>`), and the identifier plus the input SHA-256 are
bound into the approval fingerprint, so a plan approved for one shortcut cannot be
replayed to run a different shortcut.

## Input validation (no shell metacharacter injection)

Input is bounded (`MAX_RUN_INPUT_CHARS`) and NUL-rejected at plan and apply time.
The shortcut is invoked with an argv list, never a shell string, so nothing the
caller supplies is ever interpolated into a shell. When input is present it is
written to a private temp file and passed to the shortcut by `--input-path <path>`
(argv), then unlinked; the input value never becomes a command argument itself. This
means input like `; rm -rf ~ && echo pwned` is carried as inert data, not executed.

## Hard timeout

Apply invokes the run under a hard wall-clock timeout (`RUN_TIMEOUT_SECONDS`). A
hung shortcut surfaces as a `degraded` apply with `shortcuts_run_timeout` and
`mutation_applied:false` rather than blocking the caller indefinitely.

## Preview

`plan_shortcuts_run` returns `mutation_applied:false`, the resolved target (title +
identifier), the proposed input preview, and a plain-language warning that applying
will run the exact shortcut named and that its effects are arbitrary and cannot be
proven by read-back. It carries `effects_arbitrary:true` and
`effects_verifiable_by_read_back:false`. The preview states the exact shortcut name
to be run and any input.

## Apply

`apply_shortcuts_run` re-plans, requires `confirm_apply=true` and a matching approval
token, resolves the identifier again, and invokes `shortcuts run <identifier>` by
argv under the hard timeout. On a zero exit it returns the captured stdout (bounded
and truncation-flagged) with `invocation_confirmed:true` and
`side_effects_verified:false`. A non-zero exit returns `partial` with
`shortcuts_run_nonzero_exit` and `mutation_applied:true`. The apply return always
carries a `side_effects_unverifiable` warning.

## Read Back

There is no true read-back: side effects cannot be proven. The gate proves invocation
of the named shortcut only. The apply result records `invocation_confirmed`,
`side_effects_verified:false`, `exit_code`, and the bounded captured output. This is
documented as an inherent limitation, not a gap to close.

## Synthetic Tests Required

- Plan resolves an exact identifier-bound shortcut handle and binds the identifier
  into the approval fingerprint.
- Apply of a synthetic no-op shortcut through a mock runner proves invocation with
  `invocation_confirmed:true` and `side_effects_verified:false`.
- Refusal: missing `confirm_apply`, mismatched approval token, spoofed/invalid handle
  (wrong prefix or folder handle), and identifier-less handle are each refused.
- Injection: caller input containing shell metacharacters is carried as inert data
  and never interpolated into a shell string.
- Redaction scan proves no approval token, raw identifier, or unbounded output leaks.

## Gate contract summary

- No new mutating tool names are approved or exposed by this document beyond the shortcuts plan/apply run pair.
- operation:run is resolved by an exact `shortcuts:item:v1:` handle, never a raw caller-supplied name.
- the resolved shortcut identifier is bound into the approval fingerprint.
- apply requires a matching `shortcuts-apply:v1:<approval_fingerprint>` approval token plus explicit `confirm_apply=true`.
- the shortcut is invoked by argv, never a shell string, and bounded input is passed by temp-file path.
- a hard execution timeout guards against a hung shortcut.
- the gate proves invocation of the named shortcut only; a shortcut's arbitrary side effects are not verifiable by read-back.

The current release allows Shortcuts run apply of one exact identifier-bound shortcut through the plan/apply approval-token/confirm gate only.
