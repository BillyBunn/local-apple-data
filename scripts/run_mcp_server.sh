#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  exec "${ROOT}/.venv/bin/python" -m local_apple_data.mcp_server
fi

if [[ -n "${LOCAL_APPLE_DATA_PROJECT_VENV:-}" && -x "${LOCAL_APPLE_DATA_PROJECT_VENV}" ]]; then
  exec "${LOCAL_APPLE_DATA_PROJECT_VENV}" -m local_apple_data.mcp_server
fi

exec uv run --no-project --with "mcp>=1.0" python -m local_apple_data.mcp_server
