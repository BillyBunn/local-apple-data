# V1.83 Mail Signature, Template, and Query-Triage Design

Status: Source apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.

Approved plugin-state write tools: `local-apple-data mail template-create`, `local-apple-data mail template-delete`, `mail_create_template`, and `mail_delete_template`.

Planning tools: `local-apple-data mail plan`, `local-apple-data mail plan-search-triage`, `mail_plan_change`, and `mail_plan_search_triage`.

Signature selection tools: `local-apple-data mail signatures`, `local-apple-data mail signature`, `mail_search_signatures`, and `mail_get_signature`.

Template tools: `local-apple-data mail template-create`, `local-apple-data mail templates`, `local-apple-data mail template`, `local-apple-data mail template-delete`, `mail_create_template`, `mail_search_templates`, `mail_get_template`, and `mail_delete_template`.

## Public Source Review

Local source review used `/System/Applications/Mail.app/Contents/Resources/Mail.sdef`.

Mail exposes class `signature` with `name` and `content`, and `outgoing message` exposes writable property `message signature` with type `signature`.

This gate uses signature `name` only. It never reads or returns signature `content`.

Mail exposes `outgoing message`, `reply`, and `forward` public automation already used by earlier write gates. This gate sets `message signature` only on newly created draft/send/reply/reply-all/forward outgoing messages and never mutates stored signature definitions.

## Signature Selection Contract

Signature handles are opaque `mail:signature:v1:` handles.

`mail_search_signatures` and `mail_get_signature` return signature name metadata, `signature_ref`, `selection_supported`, `body_returned:false`, `content_returned:false`, and `raw_identifier_returned:false`.

Plans accept `signature_handle` only for `create_draft`, `send_message`, `reply_message`, `reply_all_message`, and `forward_message`. Triage operations reject `signature_handle` with `unexpected_signature_handle`.

Plans bind `signature_handle`, `signature_ref`, operation inputs, current source-message state when applicable, body hash, attachment identities, and idempotency key into the approval fingerprint.

Apply recomputes the plan, requires the exact `mail-apply:v1:<approval_fingerprint>` token, requires `confirm_apply:true`, re-resolves the signature handle immediately before Mail automation, and refuses duplicate signature names with `ambiguous_signature_name`.

Apply clears the message signature by default. When a signature is selected, apply sets `message signature` to the selected signature before saving or sending.

Apply returns `signature_selection_confirmed:true` only when Mail automation reports the selected signature name before save/send returns.

Apply returns `partial` with `signature_read_back_unavailable` if Mail accepted the draft/send/reply/reply-all/forward but signature read-back did not confirm the selected signature.

Apply output may include `signature_ref`, `signature_selection_confirmed`, `signature_body_returned:false`, and `signature_content_returned:false`; it must not include the signature body.

## Template Contract

Templates are plugin-managed local state under `~/.local/state/local-apple-data/mail-templates.json` by default, with `LOCAL_APPLE_DATA_MAIL_TEMPLATE_STATE` available for tests.

Template handles are opaque `mail:template:v1:` handles.

Templates are created only from explicit caller-provided plain-text bodies. Template names are unique, template body length uses the existing Mail draft body cap, and template state writes are atomic with restrictive file permissions.

Template search returns metadata only: handle, `template_ref`, name, optional subject, body character count, body SHA-256, timestamps, `body_returned:false`, `content_returned:false`, and `raw_identifier_returned:false`.

`mail_get_template` returns the exact stored template body only when `include_body:true` is requested for one exact template handle.

`mail_delete_template` requires one exact `mail:template:v1:` handle plus `confirm_delete:true`.

Plans accept `template_handle` only for `create_draft`, `send_message`, `reply_message`, `reply_all_message`, and `forward_message`.

When `template_handle` is selected, the stored template body is the only body source. Direct `body_text` with a selected template is rejected with `unexpected_body_text_with_template`.

For `create_draft` and `send_message`, the template subject is used when present. If the template has a subject, direct `subject` with a selected template is rejected with `unexpected_subject_with_template`.

For `reply_message`, `reply_all_message`, and `forward_message`, source-message rules still determine the subject; template subject is not used.

Plans bind `template_handle`, `template_ref`, template body SHA-256, operation inputs, current source-message state when applicable, attachment identities, and idempotency key into the approval fingerprint.

Apply recomputes the plan, requires the exact approval token, re-resolves the template handle, and refuses stale template state with `stale_template_state`.

Apply output may include `template_ref`, `template_selection_confirmed`, `template_body_returned:false`, and `template_content_returned:false`.

## Query-Result Triage Contract

`mail_plan_search_triage` is plan-only. It never applies Mail changes directly from a query.

`local-apple-data mail plan-search-triage` and `mail_plan_search_triage` currently support durable FTS search results only.

FTS query-result triage reuses `mail_search_fts`, so it requires date bounds, validates the private FTS index, revalidates live Mail rows, and returns only exact current message handles from the capped search result set.

The query-result plan is capped at 20 messages and delegates to the existing exact bulk triage planner.

The approval fingerprint binds every selected exact message handle, current state fingerprint, and target state through the existing bulk triage contract. It does not bind a broad query as an apply target.

Preview includes `query_result_selection` with `search_source`, opaque `query_ref`, scopes, date bounds, cursor, selected count, search result count, and `raw_query_returned:false`.

Apply still uses `mail_apply_change` with the exact selected message handles from the plan and the matching approval token.

There is no query-result auto-apply and no unbounded bulk mutation. The approved v1.83 query-result path is preview-to-plan only: capped search results are converted into exact selected message handles for the existing bulk triage apply gate.

## Tests And Verification

Synthetic tests cover signature discovery/get privacy, duplicate signature-name refusal, signature selection for draft/send/reply/reply-all/forward, template create/search/get/delete, template-selected draft/send planning and apply, query-result FTS-to-bulk-triage planning, CLI forwarding, MCP forwarding, and bad-handle refusals.

Runtime verifier covers synthetic signature and template discovery/planning plus query-result triage planning with mocked FTS output.

## Still Blocked

Real/non-synthetic mailbox/account management, real/non-synthetic permanent delete, real/non-synthetic empty Trash/Junk, HTML/rich-text mutation, background indexing, Gmail/IMAP/OAuth/network mail paths, iCloud.com, browser/keychain access, and private API paths remain blocked until separate gates land. A later v1.84 gate approves only synthetic `LAD-TEST-*` mailbox management and synthetic-only cleanup.
