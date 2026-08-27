# Public Release Manifest

This repo has two documentation classes:

- Public release docs and runtime files that are intended to be published.
- Local operator history that records machine-specific installation receipts and should not ship in a public release branch or package.

Run this before publishing:

```bash
uv run python scripts/redaction_scan.py --json .
uv run python scripts/public_release_scan.py --json
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_messages_public_surface.py --json
uv run python scripts/audit_surface_contract.py
uv run python scripts/audit_release_readiness.py --json
uv run python scripts/generate_release_receipt.py --json
uv run python scripts/build_public_release_tree.py --dest /tmp/local-apple-data-public --force
uv run python scripts/prepare_public_git_checkout.py --dest /tmp/local-apple-data-public-git --force --init-git --commit
```

Rebuild and rescan the public tree before attaching a public remote. The
source-checkout vs sanitized-public-tree boundary is enforced by
`scripts/build_public_release_tree.py` (which excludes operator/session docs)
and verified by `scripts/public_release_scan.py`.

The public release scanner also accepts an explicit root path for staged public
trees and emits matched-text-free JSON with `--json`.

## Public Release Files

Public release files include:

- `README.md`
- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `LICENSE`
- `SECURITY.md`
- `.codex-plugin/plugin.json`
- `.mcp.json`
- `.github/workflows/ci.yml`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/feature_request.md`
- `pyproject.toml`
- `uv.lock`
- `src/`
- `scripts/`
- `skills/`
- `tests/`
- Public docs under `docs/`, except local operator-only maintenance docs.

## Local Operator Docs

These files are useful for local maintenance history, but they contain machine-specific receipts, local install paths, or historical prompts. They include repo guidance, cross-agent routing notes, implementation logs, and historical implementation planning prompts. They should be excluded, rewritten, or moved before publishing the whole repo as a public GitHub repository.

The public scan excludes only the operator-only docs named in the release scanner. Everything else must be free of local paths, live handles, private note titles, private aliases, generated caches, operator-specific wording, and references back to excluded operator docs.
Local environment files and key/certificate-like artifacts are treated as
non-public inputs and are excluded from the generated public tree. The private
source checkout still must pass the redaction scan before release.

## Staged Release Tree

Use `scripts/build_public_release_tree.py` to create the tree that should be pushed to a public GitHub repository or release branch. The builder:

- Copies public release files into a destination outside the project root.
- Excludes local operator docs, local caches, virtualenvs, generated logs, binary local data, and git internals.
- Runs the public release scan against the staged tree before reporting success.
- Refuses to overwrite a non-empty destination unless `--force` is passed.

Use `scripts/prepare_public_git_checkout.py` when you want a local git-ready public checkout. It builds the same sanitized tree, optionally runs `git init`, stages the files, can create an initial local commit with `--commit`, and can attach an `origin` remote when `--remote-url` is provided. Remote URLs are limited to `https://`, `ssh://`, or `user@host:path` forms. It never pushes.

Use `scripts/generate_release_receipt.py` when you want a path-redacted JSON receipt containing version metadata, source git commit and dirty-state proof, readiness status, redaction scan status, mutation gate status, write-design gate status, surface-contract status, blockers, and committed public checkout proof. Source branch names are intentionally omitted. If you pass `--output`, write to `/tmp` or another artifact directory outside the source checkout; project-local output paths are rejected.

Use `scripts/audit_mutation_gates.py` when you want to prove the public CLI and MCP surfaces expose only intentionally approved mutation tools.

Use `scripts/audit_write_design_gates.py` when you want to prove first-tranche write design docs are present and current CLI/MCP surfaces expose only approved preview/apply/read_back tools.

Use `scripts/audit_messages_public_surface.py` when you want to prove the public Messages scripting surface still exposes only reviewed commands/signatures and keeps direct-recipient/new-chat/edit/delete/reaction/tapback/mark-read work blocked until a separate design gate is approved.

Use `scripts/audit_surface_contract.py` when you want to prove the supported Apple data surfaces are aligned across MCP tools, CLI commands, health output, access requirements, and `docs/CAPABILITY_MATRIX.md`.

Use `scripts/audit_release_readiness.py` when you want one machine-readable gate. It runs the public scan, mutation-gate audit, write-design gate audit, Messages public-surface audit, surface-contract audit, and staged checkout check, then reports `local_package_ready` separately from `github_publication_ready` so a missing/non-GitHub/private/unverified remote or an unpushed local HEAD cannot be mistaken for a completed GitHub public release. `github_publication_ready:true` requires a publication-safe public GitHub remote, `gh repo view` visibility proof of `PUBLIC`, and a live `git ls-remote` result advertising the current `HEAD` SHA.
