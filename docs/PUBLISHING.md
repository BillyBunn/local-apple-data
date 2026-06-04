# Publishing Checklist

This repo is close to publishable as a local-only Apple data MCP plugin, but publication should be treated as a release gate, not just a push.

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
- Synthetic sample outputs.
- Versioned changelog.
- Security policy.
- Contributor guide and GitHub issue/PR templates with privacy, synthetic-test, and mutation-gate checks.
- macOS support notes.
- Public author/license metadata in the Codex plugin manifest and Python project metadata.
- Public write-tool roadmap that keeps mutation support gated.
- Public release scanner for local-path and operator-term leakage in public files.
- Mutation-gate auditor that fails if write-like CLI/MCP surfaces appear before an approved mutation gate.
- Write-design gate auditor that requires first-tranche write designs and allows only the approved Reminders, iCloud Drive, Calendar, Contacts, Notes, Mail draft, and Photos import apply surfaces.
- Surface-contract auditor that fails if MCP tools, CLI commands, health surfaces, access requirements, or the capability matrix drift out of alignment.
- Release-readiness auditor that separates local package readiness from GitHub publication readiness.
- MCP client config renderer for generic stdio, Claude Code, Cursor, and OpenClaw config.
- Public release tree builder that stages the publishable file set outside the working repo and re-runs the public scan there.
- Public git-checkout preparer that stages and can commit the sanitized public file set in a local git repo without pushing.
- Path-redacted release receipt generator for reviewer handoff before a push or tag.

## Required Before Public Release

- Confirm CI passes on GitHub, then add a CI badge.
- Confirm no local caches, virtualenvs, event logs, real handles, local paths, aliases, or personal terms are tracked.
- Stage the public tree with `scripts/build_public_release_tree.py`, then publish from that tree or a branch with the same file set.
- For a new public GitHub repository, prepare a local checkout with `scripts/prepare_public_git_checkout.py --init-git --commit`, inspect it, add the intended remote, then push after CI expectations are clear.
- Run `scripts/audit_release_readiness.py --require-github-ready` only after a real remote exists and you want the remote gate to be enforced.
- Add README and release-page badges after the first pushed GitHub CI run.
- Add screenshots only if they use synthetic fixtures or redacted tool output.

## Public README Boundary

The public README should explain:

- What the plugin does.
- What local permissions may be required.
- That search is metadata-first and exact content/detail is handle-gated.
- That only Reminders create/complete/due-date apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, and Photos import apply are currently available, and only after plan approval-token and explicit-confirmation checks.
- That Hide My Email support is inferred local Mail evidence, not iCloud account management.
- That the plugin does not use Gmail API, IMAP, OAuth, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, telemetry, or network mail services.

## Public Docs

Current public-facing docs:

- `README.md`
- `CONTRIBUTING.md`
- `docs/INSTALL.md`
- `docs/SAMPLE_OUTPUTS.md`
- `docs/MACOS_SUPPORT.md`
- `docs/ECOSYSTEM_REVIEW.md`
- `docs/PUBLIC_RELEASE_MANIFEST.md`
- `docs/CAPABILITY_MATRIX.md`
- `docs/MUTATION_GATES.md`
- `docs/WRITE_TOOL_ROADMAP.md`
- `docs/V1_11_REMINDERS_WRITE_DESIGN.md`
- `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`
- `docs/V1_13_CALENDAR_WRITE_DESIGN.md`
- `docs/V1_14_CONTACTS_WRITE_DESIGN.md`
- `docs/V1_15_NOTES_WRITE_DESIGN.md`
- `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md`
- `docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md`
- `docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md`
- `docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md`
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
uv run python scripts/redaction_scan.py .
uv run python scripts/public_release_scan.py
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

Then verify the staged public tree itself:

```bash
cd /tmp/local-apple-data-public
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py .
uv run python scripts/public_release_scan.py
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_surface_contract.py
uv run python scripts/generate_release_receipt.py --json
uv run python scripts/verify_runtime.py
```

For a configured personal installed-plugin release candidate, also run:

```bash
codex plugin add local-apple-data@personal
cd /absolute/path/to/installed/local-apple-data/<version>
uv run python scripts/verify_runtime.py
cd /absolute/path/to/local-apple-data
uv run python scripts/verify_cross_agent_sync.py
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
