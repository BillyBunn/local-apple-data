# Publishing Checklist

The sanitized public project already exists on GitHub. Publication remains a release gate, not just a push: the canonical private source checkout intentionally has no publication-safe public remote, so public updates must be generated, audited, and pushed from a sanitized public tree or equivalent clean checkout.

The local source checkout is not the publishable artifact. It may contain
operator-only history and machine-specific maintenance docs. Generate and push a
sanitized public tree, or a branch with exactly the same file set, after the
pre-publication audit passes. Build the public tree with
`scripts/build_public_release_tree.py` and confirm it with
`scripts/public_release_scan.py` and `scripts/redaction_scan.py`.

## Ready Now

- Local CLI and MCP server.
- Codex plugin manifest and bundled skill.
- Synthetic unit, CLI, MCP, runtime, and packaging tests.
- macOS GitHub Actions workflow.
- Repo-local redaction scan.
- Capability matrix, privacy model, threat model, testing plan, and cross-agent routing notes.
- Ecosystem review explaining why this plugin is broad-surface, local-only, and exact-handle rather than a clone of a single-surface MCP server.
- MIT license.
- Public install guide.
- Existing sanitized public GitHub repository, verified through its configured remote and live visibility gate.
- Synthetic sample outputs.
- Versioned changelog.
- Security policy.
- Contributor guide and GitHub issue/PR templates with privacy, synthetic-test, and mutation-gate checks.
- macOS support notes.
- Public author/license metadata in the Codex plugin manifest and Python project metadata.
- Public write-tool roadmap that keeps mutation support gated.
- Public release scanner for local-path and operator-term leakage in public files.
- Mutation-gate auditor that fails if write-like CLI/MCP surfaces appear before an approved mutation gate.
- Write-design gate auditor that requires operation-specific designs and permits only the 14 approved MCP apply tools. The Contacts note sub-gates remain designed and synthetic-tested but are not live-usable on the current local helper because they fail closed with `contacts_note_unavailable`.
- Surface-contract auditor that fails if MCP tools, CLI commands, health surfaces, access requirements, or the capability matrix drift out of alignment.
- Release-readiness auditor that separates local package readiness from GitHub publication readiness and blocks dirty git worktrees, redaction findings, public leakage, gate drift, or public checkout failures from clean release handoffs.
- MCP client config renderer for generic stdio, Claude Code, Cursor, and OpenClaw config.
- Public release tree builder that stages the publishable file set outside the working repo and re-runs the public scan there.
- Public git-checkout preparer that stages and can commit the sanitized public file set in a local git repo without pushing.
- Path-redacted release receipt generator for reviewer handoff before a push or tag, with source git traceability and file output restricted to paths outside the source checkout.
- Pre-publication audit runbook and fresh-agent review prompt.

## Required Before Public Release

- Confirm CI passes on GitHub, then add a CI badge.
- Commit or otherwise clear all source checkout changes before treating release-readiness output or a generated release receipt as a clean handoff.
- Confirm no local caches, virtualenvs, event logs, real handles, local paths, aliases, or personal terms are tracked.
- Stage the public tree with `scripts/build_public_release_tree.py`, then publish from that tree or a branch with the same file set.
- For a replacement or newly prepared public checkout, use `scripts/prepare_public_git_checkout.py --init-git --commit`, inspect it, attach the sanitized public repository remote, then push after CI expectations are clear.
- Do not attach a public remote to the private source checkout unless it has
  first been reduced to exactly the sanitized public file set.
- Run `scripts/audit_release_readiness.py --require-github-ready` from the sanitized public checkout only after its real GitHub remote exists and the release commit has been pushed. The private source checkout is expected to lack a publication-safe public remote.
- Add README and release-page badges after the first pushed GitHub CI run.
- Add screenshots only if they use synthetic fixtures or redacted tool output.

## Public README Boundary

The public README should explain:

- What the plugin does.
- What local permissions may be required.
- That search is metadata-first and exact content/detail is handle-gated.
- That Mail attachment export is exact-message-handle plus exact-attachment-handle gated and never returns inline bytes.
- That Messages attachment export is exact-chat-handle plus exact-attachment-handle gated and never returns inline bytes.
- That Notes attachment export is exact-note-handle plus exact-attachment-handle gated and never returns inline bytes.
- That the release is metadata-first/read-mostly and exposes exactly 14 approved MCP apply tools: `reminders_apply_change`, `reminders_apply_list_change`, `icloud_drive_apply_change`, `filesystem_apply_change`, `calendar_apply_change`, `calendar_apply_calendar_change`, `contacts_apply_change`, `notes_apply_change`, `mail_apply_change`, `mail_apply_mailbox_change`, `mail_apply_cleanup`, `photos_apply_change`, `messages_apply_change`, and `shortcuts_apply_run`. Every apply requires the matching plan approval token plus explicit confirmation and operation-specific read-back or bounded invocation proof. Current shipped gates include the bounded home-directory Filesystem, Notes rich-text body create/replace and exact empty child-folder move, and exact identifier-bound Shortcuts run. Contacts note append/set/clear/merge remain designed and synthetic-tested inside `contacts_apply_change` but are live-unavailable on the current helper with `contacts_note_unavailable`; other approved Contacts operations remain usable.
- That Hide My Email support is inferred local Mail evidence, not iCloud account management.
- That the plugin does not use Gmail API, IMAP, OAuth, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, telemetry, or network mail services.

## Public Docs

Current public-facing docs:

- `README.md`
- `CONTRIBUTING.md`
- `docs/INSTALL.md`
- `docs/SAMPLE_OUTPUTS.md`
- `docs/MACOS_SUPPORT.md`
- `docs/PUBLIC_RELEASE_MANIFEST.md`
- `docs/CAPABILITY_MATRIX.md`
- `docs/MUTATION_GATES.md`
- `docs/WRITE_TOOL_ROADMAP.md`
- `docs/V1_33_FULL_CRUD_PRIORITY_PLAN.md`
- `docs/V1_11_REMINDERS_WRITE_DESIGN.md`
- `docs/V1_35_REMINDERS_DELETE_WRITE_DESIGN.md`
- `docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md`
- `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`
- `docs/V1_13_CALENDAR_WRITE_DESIGN.md`
- `docs/V1_34_CALENDAR_UPDATE_WRITE_DESIGN.md`
- `docs/V1_36_CALENDAR_DELETE_WRITE_DESIGN.md`
- `docs/V1_55_CALENDAR_ALL_DAY_WRITE_DESIGN.md`
- `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`
- `docs/V1_14_CONTACTS_WRITE_DESIGN.md`
- `docs/V1_48_CONTACTS_UPDATE_WRITE_DESIGN.md`
- `docs/V1_49_CONTACTS_DELETE_WRITE_DESIGN.md`
- `docs/V1_15_NOTES_WRITE_DESIGN.md`
- `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md`
- `docs/V1_37_MAIL_FLAG_WRITE_DESIGN.md`
- `docs/V1_40_MAIL_ARCHIVE_WRITE_DESIGN.md`
- `docs/V1_41_MAIL_TRASH_WRITE_DESIGN.md`
- `docs/V1_46_MAIL_MOVE_WRITE_DESIGN.md`
- `docs/V1_66_MAIL_CROSS_ACCOUNT_MOVE_WRITE_DESIGN.md`
- `docs/V1_43_MAIL_SEND_WRITE_DESIGN.md`
- `docs/V1_44_MAIL_REPLY_WRITE_DESIGN.md`
- `docs/V1_50_MAIL_FORWARD_WRITE_DESIGN.md`
- `docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md`
- `docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md`
- `docs/V1_51_ICLOUD_DRIVE_REPLACE_WRITE_DESIGN.md`
- `docs/V1_52_ICLOUD_DRIVE_FOLDER_CREATE_WRITE_DESIGN.md`
- `docs/V1_53_ICLOUD_DRIVE_TRASH_WRITE_DESIGN.md`
- `docs/V1_54_ICLOUD_DRIVE_RENAME_COPY_MOVE_WRITE_DESIGN.md`
- `docs/V1_60_ICLOUD_DRIVE_FOLDER_RENAME_WRITE_DESIGN.md`
- `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md`
- `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md`
- `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md`
- `docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md`
- `docs/V1_34_NOTES_REPLACE_WRITE_DESIGN.md`
- `docs/V1_39_NOTES_FOLDER_CREATE_WRITE_DESIGN.md`
- `docs/V1_57_NOTES_FOLDER_CREATE_WRITE_DESIGN.md`
- `docs/V1_58_NOTES_FOLDER_RENAME_WRITE_DESIGN.md`
- `docs/V1_59_NOTES_FOLDER_DELETE_WRITE_DESIGN.md`
- `docs/V1_42_NOTES_DELETE_WRITE_DESIGN.md`
- `docs/V1_45_NOTES_MOVE_WRITE_DESIGN.md`
- `docs/V1_20_NOTES_ATTACHMENT_EXPORT.md`
- `docs/V1_21_MAIL_ATTACHMENT_EXPORT.md`
- `docs/V1_22_MESSAGES_ATTACHMENT_EXPORT.md`
- `docs/V1_23_MESSAGES_ATTRIBUTED_BODY.md`
- `docs/V1_64_MESSAGES_PARTICIPANTS_METADATA.md`
- `docs/V1_24_MESSAGES_SEND_TEXT_WRITE_DESIGN.md`
- `docs/V1_38_MESSAGES_SEND_FILE_WRITE_DESIGN.md`
- `docs/V1_47_MESSAGES_RISKY_MUTATION_SOURCE_REVIEW.md`
- `docs/V1_25_SAFARI_BOOKMARKS.md`
- `docs/V1_26_SHORTCUTS_METADATA.md`
- `docs/V1_27_BOOKS_METADATA.md`
- `docs/V1_28_PODCASTS_METADATA.md`
- `docs/V1_29_MUSIC_METADATA.md`
- `docs/V1_30_TV_METADATA.md`
- `docs/V1_31_FREEFORM_METADATA.md`
- `docs/PRIVACY_MODEL.md`
- `docs/THREAT_MODEL.md`
- `docs/TESTING.md`
- `SECURITY.md`
- `CHANGELOG.md`
- `LICENSE`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/feature_request.md`

## Release Verification

Run before tagging:

```bash
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py --json .
uv run python scripts/public_release_scan.py --json
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_surface_contract.py
uv run python scripts/audit_release_readiness.py --json
uv run python scripts/generate_release_receipt.py --json
uv run python scripts/render_mcp_client_config.py --client generic
uv run python scripts/render_mcp_client_config.py --client claude-code
uv run python scripts/render_mcp_client_config.py --client cursor
uv run python scripts/render_mcp_client_config.py --client openclaw --server-only --compact
uv run python scripts/build_public_release_tree.py --dest /tmp/local-apple-data-public --force
uv run python scripts/prepare_public_git_checkout.py --dest /tmp/local-apple-data-public-git --force --init-git --commit
swiftc -typecheck scripts/eventkit_helper.swift
swiftc -typecheck scripts/contacts_helper.swift
swiftc -typecheck scripts/photos_helper.swift
uv run python scripts/verify_runtime.py
python3 /absolute/path/to/plugin-creator/scripts/validate_plugin.py /absolute/path/to/local-apple-data
cd skills/local-apple-data && python3 /absolute/path/to/skill-creator/scripts/quick_validate.py .
```

The release-readiness auditor checks the source checkout's git status when the
source root is a git worktree. A dirty worktree is a local package blocker even
if the synthetic tests and public scans pass.

GitHub publication readiness also requires at least one publication-safe public
`github.com` git remote with a plain remote name, `gh repo view` visibility
proof of `PUBLIC`, and a live `git ls-remote` result advertising the current
`HEAD` SHA. Local remote-tracking refs alone do not count, and private GitHub
repositories do not count as public-release ready. The remote gate uses the same
HTTPS/SSH URL validation as `prepare_public_git_checkout.py`; local paths,
non-GitHub hosts, insecure transports, credentialed URLs, option-like values,
option-like or non-plain remote names, whitespace-bearing values, malformed
remotes, and unverified GitHub visibility do not count as GitHub
publication-ready.

When saving a release receipt with `scripts/generate_release_receipt.py --output`,
write it to `/tmp` or another artifact directory outside the source checkout.
Project-local output paths are rejected so generated receipts cannot dirty a
release candidate.
Receipt source git traceability includes commit and dirty state, not local
branch names.

The public release scanner accepts an optional root path, so automated receipts
can scan the source checkout, staged public tree, or prepared public git checkout
explicitly. Use `--json` when a machine-readable, matched-text-free finding list
is needed.

Then verify the staged public tree itself:

```bash
cd /tmp/local-apple-data-public
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py --json .
uv run python scripts/public_release_scan.py --json .
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_surface_contract.py
uv run python scripts/generate_release_receipt.py --json
uv run python scripts/verify_runtime.py
```

For a configured personal installed-plugin release candidate, also run:

```bash
uv run python scripts/sync_personal_plugin.py --json
codex plugin add local-apple-data@personal
cd /absolute/path/to/installed/local-apple-data/<version>
uv run python scripts/verify_runtime.py
cd /absolute/path/to/local-apple-data
uv run python scripts/verify_cross_agent_sync.py
uv run python scripts/audit_plugin_artifact_hygiene.py --json
```

If Cursor is part of the target operator setup, require the Cursor config explicitly:

```bash
uv run python scripts/verify_cross_agent_sync.py --cursor-config .cursor/mcp.json --require-cursor
```

## Do Not Publish

Do not publish if any of these are present:

- Live personal content or exact private aliases in docs, tests, fixtures, logs, or examples.
- Raw database rows, raw framework identifiers, or raw local file paths in examples.
- Secrets, credentials, cookies, OAuth artifacts, keychain references, or browser profile data.
- Mutation tools without the design gates in `docs/MUTATION_GATES.md`.
- Claims of authoritative Hide My Email inventory or management.
- Claims that CI covers live Apple permissions or live local stores.
