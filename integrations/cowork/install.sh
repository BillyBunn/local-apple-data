#!/usr/bin/env bash
#
# Register the local-apple-data MCP server with Cowork (the Claude desktop
# app's local agent mode) and Claude Code.
#
# Both read their global MCP server list from ~/.claude.json under the
# top-level "mcpServers" key (stdio servers). This script adds — or repairs —
# the "local-apple-data" entry there, idempotently and non-destructively:
#
#   * It never touches any other key in ~/.claude.json.
#   * It only writes when the entry is missing or differs from canonical.
#   * It backs up the file before any write (~/.claude.json.bak.YYYYMMDD-HHMMSS).
#   * It writes atomically (temp file + mv) so a crash can't truncate the config.
#
# IMPORTANT: Quit Cowork / Claude Code before running. Those apps may hold
# ~/.claude.json open and overwrite it on exit, clobbering this change.
#
# Usage:
#   integrations/cowork/install.sh            # apply (idempotent)
#   integrations/cowork/install.sh --dry-run  # show what would change, write nothing
#
# Override the target for testing: CLAUDE_CONFIG=/tmp/foo.json install.sh
#
set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" || "${1:-}" == "-n" ]] && DRY_RUN=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LAUNCHER="${REPO_ROOT}/scripts/run_mcp_server.sh"
TARGET="${CLAUDE_CONFIG:-${HOME}/.claude.json}"
SERVER_NAME="local-apple-data"

die() { echo "error: $*" >&2; exit 1; }

command -v jq >/dev/null 2>&1 || die "jq is required but not found on PATH."
[[ -f "${LAUNCHER}" ]]   || die "launcher not found: ${LAUNCHER}"
[[ -x "${LAUNCHER}" ]]   || die "launcher is not executable: ${LAUNCHER} (run: chmod +x \"${LAUNCHER}\")"

# Canonical entry, with the absolute launcher path for THIS checkout.
DESIRED="$(jq -n --arg cmd "${LAUNCHER}" \
  '{type:"stdio", command:$cmd, args:[], env:{}}')"

echo "Target config : ${TARGET}"
echo "Server name   : ${SERVER_NAME}"
echo "Launcher      : ${LAUNCHER}"
echo

# If the file is missing, we'll create a minimal one holding just this server;
# Claude Code/Cowork will re-populate its other defaults on next launch.
if [[ ! -f "${TARGET}" ]]; then
  echo "${TARGET} does not exist — will create a minimal config with only ${SERVER_NAME}."
  CURRENT="null"
else
  jq -e . "${TARGET}" >/dev/null 2>&1 || die "${TARGET} is not valid JSON; aborting (no changes made)."
  CURRENT="$(jq --arg n "${SERVER_NAME}" '.mcpServers[$n] // null' "${TARGET}")"
fi

if [[ "${CURRENT}" != "null" ]] && [[ "$(jq -S . <<<"${CURRENT}")" == "$(jq -S . <<<"${DESIRED}")" ]]; then
  echo "✓ Already registered and identical to canonical. No change needed."
  exit 0
fi

echo "Change to apply:"
if [[ "${CURRENT}" == "null" ]]; then
  echo "  (add new entry)"
else
  echo "  (replace existing entry)"
fi
diff <(echo "${CURRENT}" | jq -S . 2>/dev/null || echo "  <absent>") \
     <(echo "${DESIRED}" | jq -S .) || true
echo

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[dry-run] No files written."
  exit 0
fi

TS="$(date +%Y%m%d-%H%M%S)"
TMP="$(mktemp "${TMPDIR:-/tmp}/claude-config.XXXXXX.json")"
trap 'rm -f "${TMP}"' EXIT

if [[ -f "${TARGET}" ]]; then
  BACKUP="${TARGET}.bak.${TS}"
  cp -p "${TARGET}" "${BACKUP}"
  echo "Backup written: ${BACKUP}"
  jq --arg n "${SERVER_NAME}" --argjson v "${DESIRED}" \
    '.mcpServers = (.mcpServers // {}) | .mcpServers[$n] = $v' "${TARGET}" > "${TMP}"
else
  jq -n --arg n "${SERVER_NAME}" --argjson v "${DESIRED}" \
    '{mcpServers: {($n): $v}}' > "${TMP}"
fi

# Validate the rendered file before swapping it in.
jq -e . "${TMP}" >/dev/null || die "internal: rendered config is invalid JSON; original left untouched."
mv "${TMP}" "${TARGET}"
trap - EXIT
echo "✓ Wrote ${SERVER_NAME} entry to ${TARGET}"
echo
echo "Next: fully quit and reopen Cowork / Claude Code, then verify (see README.md)."
