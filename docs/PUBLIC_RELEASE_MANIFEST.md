# Public Release Manifest

This repo has two documentation classes:

- Public release docs and runtime files that are intended to be published.
- Local operator history that records machine-specific installation receipts and should not ship in a public release branch or package.

Run this before publishing:

```bash
uv run python scripts/public_release_scan.py
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_surface_contract.py
uv run python scripts/audit_release_readiness.py --json
uv run python scripts/generate_release_receipt.py --json
uv run python scripts/build_public_release_tree.py --dest /tmp/local-apple-data-public --force
uv run python scripts/prepare_public_git_checkout.py --dest /tmp/local-apple-data-public-git --force --init-git --commit
```

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
- Public docs under `docs/` except the local operator docs listed below.

## Local Operator Docs

These files are useful for local maintenance history, but they contain machine-specific receipts, local install paths, or historical prompts. They should be excluded, rewritten, or moved before publishing the whole repo as a public GitHub repository:

- `AGENTS.md`
- `docs/CROSS_AGENT_ROUTING.md`
- `docs/IMPLEMENTATION_LOG.md`
- `docs/V1_1_CONTENT_RETRIEVAL_PLAN.md`
- `docs/V1_1_KICKOFF_PROMPT.md`

The public scan excludes only those named operator docs. Everything else must be free of local paths, live handles, private note titles, private aliases, generated caches, and operator-specific wording.

## Staged Release Tree

Use `scripts/build_public_release_tree.py` to create the tree that should be pushed to a public GitHub repository or release branch. The builder:

- Copies public release files into a destination outside the project root.
- Excludes local operator docs, local caches, virtualenvs, generated logs, binary local data, and git internals.
- Runs the public release scan against the staged tree before reporting success.
- Refuses to overwrite a non-empty destination unless `--force` is passed.

Use `scripts/prepare_public_git_checkout.py` when you want a local git-ready public checkout. It builds the same sanitized tree, optionally runs `git init`, stages the files, can create an initial local commit with `--commit`, and can attach an `origin` remote when `--remote-url` is provided. It never pushes.

Use `scripts/generate_release_receipt.py` when you want a path-redacted JSON receipt containing version metadata, readiness status, mutation gate status, write-design gate status, surface-contract status, blockers, and committed public checkout proof.

Use `docs/ECOSYSTEM_REVIEW.md` when you want the public rationale for the project architecture and the comparison against other local Apple-data MCP tools.

Use `scripts/audit_mutation_gates.py` when you want to prove the public CLI and MCP surfaces remain read-only until a mutation gate is intentionally approved.

Use `scripts/audit_write_design_gates.py` when you want to prove first-tranche write design docs are present and current CLI/MCP surfaces still expose no preview/apply/read_back mutation tools.

Use `scripts/audit_surface_contract.py` when you want to prove the supported Apple data surfaces are aligned across MCP tools, CLI commands, health output, access requirements, and `docs/CAPABILITY_MATRIX.md`.

Use `scripts/audit_release_readiness.py` when you want one machine-readable gate. It runs the public scan, mutation-gate audit, write-design gate audit, surface-contract audit, and staged checkout check, then reports `local_package_ready` separately from `github_publication_ready` so a missing remote cannot be mistaken for a completed public release.
