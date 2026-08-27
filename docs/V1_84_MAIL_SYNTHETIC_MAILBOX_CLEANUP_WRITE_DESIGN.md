# v1.84 Mail Synthetic Mailbox And Cleanup Write Design

Status: Source implementation with partial live proof and fail-closed degraded guard for destructive cleanup.

Approved write tools in source: `local-apple-data mail apply-mailbox`, `local-apple-data mail apply-cleanup`, `mail_apply_mailbox_change`, and `mail_apply_cleanup`.

Live proof on 2026-06-25 verified synthetic mailbox create/rename and synthetic draft-to-Trash setup through public Mail.app automation. Follow-up live proof on 2026-06-26 verified synthetic-only empty Trash and empty Junk cleanup, plus one exact permanent-delete cleanup, but the same run also produced a Mail crash report at `2026-06-26 09:02:29 -0700` (`SIGABRT` in Mail's message transfer path), and later Mail AppleEvents returned handler failures. A temporary empty-on-quit proof path was removed after adversarial review because it changed Mail account cleanup preferences. The implementation now fails closed when Mail background activity is not idle, activity status is unavailable, the Mail-script target set changes, or local absence proof cannot verify deletion. Do not claim this host is cleanup-release-green until a fresh live run has no new Mail crash reports, no synthetic leftovers, and normal AppleEvent health.

Planning tools: `local-apple-data mail plan-mailbox`, `local-apple-data mail plan-cleanup`, `mail_plan_mailbox_change`, and `mail_plan_cleanup`.

## Source Review

Local source review used `/System/Applications/Mail.app/Contents/Resources/Mail.sdef`.

Mail.app public scripting exposes the standard `delete` command, mailbox `name`, mailbox `account`, account `trash mailbox`, account `junk mailbox`, `background activity count`, and message `message id`, `subject`, `read status`, `flagged status`, `deleted status`, and `junk mail status`. The SDEF also exposes `quit` and account cleanup settings, but the implementation does not use those for cleanup because changing Mail account preferences is outside the approved synthetic cleanup surface. Live testing found that plain public `delete` is not consistently sufficient by itself for durable Trash/Junk cleanup on this host, so source success requires Mail-idle preflight, exact script-side target binding, exact subject/read/flag state checks, and local mailbox-scoped absence proof before reporting `permanently_deleted:true`.

The attempted `sdef /System/Applications/Mail.app` command was unavailable because the active developer directory is Command Line Tools, but the shipped Mail SDEF file is present locally and was used directly. No private framework, keychain, Gmail, IMAP, OAuth, iCloud.com, browser, or raw Mail database write path is used.

## Synthetic Mailbox Management

Mailbox management is limited to top-level synthetic mailboxes whose names start with `LAD-TEST-`.

Mailbox create uses one exact `mail:sender:v1:` handle only to select the target account.

Mailbox rename/delete use one exact `mail:mailbox:v1:` handle and require the current mailbox name to start with `LAD-TEST-`.

Mailbox rename/delete require an empty mailbox at plan time and apply time.

Apply recomputes the plan, requires the exact `mail-apply:v1:<approval_fingerprint>` token, and requires `confirm_apply:true`.

Mailbox apply returns success only after Mail.app read-back confirms create/rename or delete absence for the synthetic mailbox. Live proof currently passes create/rename and still treats mailbox delete as not release-green after earlier Mail.app AppleEvent `-10000`.

No raw account identifiers, raw mailbox paths, raw message IDs, message bodies, attachment bytes, or full account addresses are returned.

## Synthetic Cleanup

Permanent delete is limited to one exact `mail:message:v2:` handle already in Trash or Junk with subject prefix `LAD-TEST-`.

Empty Trash/Junk requires one exact `mail:sender:v1:` handle to select the account and refuses if any current Trash/Junk message subject does not start with `LAD-TEST-`.

Apply rechecks `LAD-TEST-` mailbox names or message subject prefixes through Mail.app automation before deletion.

Cleanup apply returns success only after local mailbox-scoped absence read-back confirms every planned synthetic message target is gone from the approved Trash/Junk mailbox; empty Trash/Junk additionally require that mailbox to be empty after apply. Before the first destructive Mail command, apply requires public Mail `background activity count` to become idle. Cleanup AppleScript binds the exact planned Message-ID set plus subject/read/flag state and refuses if the mailbox target set or target state changes between plan/apply and deletion. If Mail is busy, AppleEvents fail, the Trash/Junk mailbox has non-synthetic content, the target set changes, target state changes, or read-back cannot confirm absence, cleanup returns degraded/partial instead of claiming `permanently_deleted:true`. If Mail times out or reports an automation write error after the destructive script has been invoked, apply returns `partial` with conservative `mutation_applied:true` and bounded absence read-back.

Real non-synthetic messages, non-synthetic mailboxes, account settings, SMTP settings, passwords, keychain, Gmail/IMAP/OAuth/network mail paths, iCloud.com, browser access, raw Mail DB writes, unbounded emptying, and broad account management remain blocked.

## Verification

Runtime verifier covers synthetic mailbox create/rename/delete and synthetic cleanup planning/apply with mocked Mail runners.

Synthetic tests cover:

- non-`LAD-TEST-` mailbox refusal;
- exact sender-account mailbox create;
- exact empty `LAD-TEST-*` mailbox rename/delete;
- non-synthetic Trash message refusal;
- permanent delete mailbox-scoped absence proof;
- success when a same-RFC Message-ID copy remains outside the cleanup mailbox;
- empty Trash refusal when any real message is present;
- empty Trash apply over planned synthetic messages only;
- refusal to mutate while Mail background activity is still running;
- refusal when the Mail-script target set changes after planning;
- refusal when the Mail-script target state changes after planning;
- partial mutation reporting when Mail errors or times out after destructive script invocation;
- live-row read-back before header/file fallback when proving absence;
- preference for provider-specific Trash over generic Deleted Messages when both are exposed by Mail;
- public Mail.app scripting verbs for mailbox create/rename/delete and cleanup.
