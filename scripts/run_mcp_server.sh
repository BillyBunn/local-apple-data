#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONDONTWRITEBYTECODE=1

# Python strictly parses the machine-wide `.env.operator` and an optional
# checkout-local `.env.local` before serving. The shell never executes either
# file; only the two signed-helper bundle-ID assignments are accepted.

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  exec "${ROOT}/.venv/bin/python" -m local_apple_data.mcp_server
fi

if [[ -n "${LOCAL_APPLE_DATA_PROJECT_VENV:-}" && -x "${LOCAL_APPLE_DATA_PROJECT_VENV}" ]]; then
  exec "${LOCAL_APPLE_DATA_PROJECT_VENV}" -m local_apple_data.mcp_server
fi

# Keep this constraint in sync with pyproject.toml. Without the `<2` upper bound this
# fallback resolves to mcp 2.0.0, which removed `mcp.server.fastmcp` and kills the server
# at import on any checkout that reaches this path (no .venv, no LOCAL_APPLE_DATA_PROJECT_VENV).
exec uv run --no-project --with "mcp>=1.0,<2" python -m local_apple_data.mcp_server
