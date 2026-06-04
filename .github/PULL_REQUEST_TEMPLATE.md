## Summary

- 

## Privacy And Scope

- [ ] This change does not add live personal data, real handles, raw local paths, secrets, credentials, browser data, or local Apple store rows to docs, tests, fixtures, logs, or examples.
- [ ] Automated tests use synthetic fixtures or mocked Apple framework helpers only.
- [ ] New or changed content/detail/export paths require exact opaque handles returned by the matching metadata flow.
- [ ] New or changed search paths reject empty, wildcard-only, and broad queries before touching local stores or frameworks.
- [ ] New or changed warnings use stable warning codes and avoid raw exceptions, raw identifiers, raw paths, stack traces, and personal content.

## Mutation Gate

- [ ] This PR does not add write-like CLI or MCP tools.
- [ ] If this PR intentionally adds a write-like tool, the corresponding design, preview/apply/read-back tests, MCP annotations, docs, and `scripts/audit_mutation_gates.py` changes are included.

## Verification

- [ ] `uv run pytest`
- [ ] `uv run python -m compileall src tests scripts`
- [ ] `uv run python scripts/redaction_scan.py .`
- [ ] `uv run python scripts/public_release_scan.py`
- [ ] `uv run python scripts/audit_mutation_gates.py`
- [ ] `uv run python scripts/audit_surface_contract.py`
- [ ] `uv run python scripts/audit_release_readiness.py --json`
- [ ] `uv run python scripts/verify_runtime.py`

## Notes

- 
