# Contributing

This project exposes local Apple data through a local-first MCP server. Contributions are welcome when they preserve the privacy model, read-only default, and synthetic-first test posture.

## Ground Rules

- Keep automated tests synthetic-only. Do not add fixtures copied from real Mail, Messages, Notes, Reminders, Calendar, Contacts, Photos, Voice Memos, iCloud Drive, or Hide My Email data.
- Do not commit live handles, local account names, full email addresses, phone numbers, contact records, message text, note bodies, reminder notes, calendar locations, file contents, media bytes, local store paths, credentials, tokens, cookies, OAuth artifacts, keychain data, or browser profile data.
- Keep search metadata-first. Exact content, detail, and export tools must require opaque handles returned by the matching metadata flow.
- Keep broad content search, background indexing, durable personal-content caches, network mail, private iCloud web/API use, browser automation, and keychain access out of scope unless a separate public design explicitly approves them.
- Keep mutation tools out of the read-only release. Future write tools must follow `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.
- Return stable warning codes and bounded output. Do not return raw exceptions, raw database rows, raw framework identifiers, raw file paths, stack traces, or secret values.

## Development Setup

```bash
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py .
uv run python scripts/public_release_scan.py
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_surface_contract.py
uv run python scripts/verify_runtime.py
```

Swift helper typechecks are separate top-level script checks:

```bash
swiftc -typecheck scripts/eventkit_helper.swift
swiftc -typecheck scripts/contacts_helper.swift
swiftc -typecheck scripts/photos_helper.swift
```

## Adding A Read Surface

Before describing a new surface as supported:

- Add adapter, CLI, and MCP paths using opaque handles for exact reads.
- Add synthetic unit tests for search, exact get/content/detail, invalid handles, broad-query rejection, and degraded stores or permissions.
- Update `docs/CAPABILITY_MATRIX.md`, `docs/PRIVACY_MODEL.md`, `docs/THREAT_MODEL.md`, `docs/TESTING.md`, README, plugin metadata, and the bundled skill.
- Update `scripts/verify_runtime.py` with synthetic runtime coverage.
- Update `scripts/audit_surface_contract.py` if the surface changes the public contract.

## Adding A Write Surface

Do not add write-like CLI or MCP names until the mutation gate is intentionally updated. A write tranche needs:

- A specific design for one surface and operation class.
- Preview or dry-run behavior.
- Explicit apply behavior.
- Independent read-back verification.
- Synthetic tests for preview, apply, read-back, refusal, and retry/idempotency behavior.
- MCP annotations that accurately mark non-read-only or destructive tools.
- Updated docs, tests, runtime smoke, release audits, and installed-cache verification.

## Pull Request Checklist

Before opening a PR, run:

```bash
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py .
uv run python scripts/public_release_scan.py
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_surface_contract.py
uv run python scripts/audit_release_readiness.py --json
uv run python scripts/build_public_release_tree.py --dest /tmp/local-apple-data-public --force
```

If the change touches Swift helpers, run the three Swift typechecks shown above. If the change touches plugin packaging or installed runtime behavior, reinstall the plugin locally and run `scripts/verify_cross_agent_sync.py` in a configured environment.
