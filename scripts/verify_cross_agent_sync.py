#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PERSONAL_ROOT = Path.home() / "plugins/local-apple-data"
DEFAULT_PLUGIN_CACHE_ROOT = Path.home() / ".codex/plugins/cache/personal/local-apple-data"
CURSOR_SERVER_NAME = "local-apple-data"
PROJECT_ROOT_ENV = "LOCAL_APPLE_DATA_PROJECT_ROOT"
MCP_SERVER_MODULE_NAME = "local_apple_data.mcp_server"

STATIC_SYNC_FILES = [
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "CHANGELOG.md",
    "SECURITY.md",
    "pyproject.toml",
    "uv.lock",
    ".codex-plugin/plugin.json",
    ".mcp.json",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    "skills/local-apple-data/SKILL.md",
    "skills/local-apple-data/agents/openai.yaml",
]

SYNC_GLOBS = [
    ".codex-plugin/**/*",
    ".github/**/*",
    "docs/**/*",
    "scripts/**/*",
    "skills/local-apple-data/**/*",
    "src/local_apple_data/**/*",
    "tests/**/*",
]

EXCLUDED_SYNC_NAMES = {".DS_Store"}
EXCLUDED_SYNC_PARTS = {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
EXCLUDED_SYNC_SUFFIXES = {".pyc", ".pyo"}
MAX_FILE_SYNC_MISMATCHES = 10
UNSAFE_ERROR_MESSAGE_PATTERNS = (
    re.compile(
        r"(?i)(?:file://|~/|/(?:Users|private|var|tmp|Library|Volumes|Applications|System|opt|usr|etc|Network)(?:/|\b))"
    ),
    re.compile(
        r"(?i)\b(?:traceback|exception|permission denied|no such file|sqlite|database)\b"
    ),
)

# Public for tests and quick inspection; `_sync_files` expands this with
# project-relative globs so future runtime or regression files are not silently
# omitted from source/personal/cache comparisons.
SYNC_FILES = STATIC_SYNC_FILES


class ToolNotAvailable(RuntimeError):
    """A required agent CLI is not installed on PATH — an optional, non-fatal condition."""


def _run(command: list[str], *, cwd: Path) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        # The CLI (codex/claude/openclaw/cursor) is not installed on this machine.
        # Surface a clear, path-free message so the verifier can mark the surface
        # "not_available" instead of crashing with an opaque FileNotFoundError.
        raise ToolNotAvailable(f"{command[0]} CLI not found on PATH") from None
    if result.returncode != 0:
        raise RuntimeError(f"{command[0]} exited {result.returncode}")
    return result.stdout


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_error_message(exc: Exception) -> str:
    if type(exc) is RuntimeError:
        message = str(exc).strip()
        if message and not any(pattern.search(message) for pattern in UNSAFE_ERROR_MESSAGE_PATTERNS):
            return message
    return type(exc).__name__


def _version(project_root: Path) -> str:
    return str(_load_json(project_root / ".codex-plugin/plugin.json")["version"])


def _sync_files(project_root: Path) -> list[str]:
    files = set(STATIC_SYNC_FILES)
    for pattern in SYNC_GLOBS:
        for path in project_root.glob(pattern):
            relative = path.relative_to(project_root)
            if (
                path.is_file()
                and path.name not in EXCLUDED_SYNC_NAMES
                and path.suffix not in EXCLUDED_SYNC_SUFFIXES
                and not any(part in EXCLUDED_SYNC_PARTS for part in relative.parts)
            ):
                files.add(path.relative_to(project_root).as_posix())
    return sorted(files)


def _assert_same_files(project_root: Path, personal_root: Path, cache_root: Path) -> int:
    sync_files = _sync_files(project_root)
    mismatches: list[str] = []
    for relative in sync_files:
        source = project_root / relative
        personal = personal_root / relative
        cache = cache_root / relative
        if not source.exists():
            mismatches.append(f"missing source file: {relative}")
            continue
        try:
            source_bytes = source.read_bytes()
        except OSError:
            mismatches.append(f"source unreadable: {relative}")
            continue
        if not personal.exists():
            mismatches.append(f"personal source missing: {relative}")
        else:
            try:
                personal_bytes = personal.read_bytes()
            except OSError:
                mismatches.append(f"personal source unreadable: {relative}")
            else:
                if source_bytes != personal_bytes:
                    mismatches.append(f"personal source mismatch: {relative}")
        if not cache.exists():
            mismatches.append(f"installed cache missing: {relative}")
        else:
            try:
                cache_bytes = cache.read_bytes()
            except OSError:
                mismatches.append(f"installed cache unreadable: {relative}")
            else:
                if source_bytes != cache_bytes:
                    mismatches.append(f"installed cache mismatch: {relative}")
    if mismatches:
        shown = mismatches[:MAX_FILE_SYNC_MISMATCHES]
        remaining = len(mismatches) - len(shown)
        suffix = f"; {remaining} more mismatch(es)" if remaining else ""
        raise RuntimeError(
            f"file sync mismatches ({len(mismatches)}): {'; '.join(shown)}{suffix}"
        )
    return len(sync_files)


def _check_codex(version: str, plugin_cache_root: Path) -> Path:
    cache_root = plugin_cache_root / version
    if not cache_root.exists():
        raise RuntimeError("installed Codex cache version is missing")
    listing = _run(["codex", "plugin", "list"], cwd=Path.home())
    found = False
    for line in listing.splitlines():
        fields = line.split()
        if fields and fields[0] == "local-apple-data@personal" and version in fields:
            found = True
            break
    if not found:
        raise RuntimeError("Codex plugin list does not show the expected installed version")
    return cache_root


def _check_claude() -> None:
    listing = _run(["claude", "mcp", "list"], cwd=Path.home())
    matching = [line for line in listing.splitlines() if line.startswith("local-apple-data:")]
    if not matching:
        raise RuntimeError("Claude MCP server local-apple-data is missing")
    if "Connected" not in matching[0]:
        raise RuntimeError("Claude MCP server local-apple-data is not connected")


def _path_matches(value: Any, expected: Path) -> bool:
    if not isinstance(value, str):
        return False
    return Path(value).expanduser().resolve() == expected.expanduser().resolve()


def _check_openclaw(project_root: Path) -> None:
    runner = (project_root / "scripts/run_mcp_server.sh").resolve()
    payload = _run(["openclaw", "mcp", "show", "local-apple-data", "--json"], cwd=project_root)
    config = json.loads(payload)
    if not _path_matches(config.get("command"), runner):
        raise RuntimeError(
            "OpenClaw MCP command does not match the project runner"
            + _project_root_hint_from_openclaw_config(config)
        )
    if config.get("args") != []:
        raise RuntimeError("OpenClaw MCP args should be empty")
    if not _path_matches(config.get("cwd"), project_root):
        raise RuntimeError(
            "OpenClaw MCP cwd does not match the project root"
            + _project_root_hint_from_openclaw_config(config)
        )


def _project_root_hint_from_openclaw_config(config: dict[str, Any]) -> str:
    command = config.get("command")
    cwd = config.get("cwd")
    if not isinstance(command, str) or not isinstance(cwd, str):
        return ""
    candidate = Path(cwd).expanduser().resolve()
    if not _path_matches(command, candidate / "scripts/run_mcp_server.sh"):
        return ""
    return f"; configured project root appears to be {candidate}; pass --project-root {candidate}"


def _configured_project_root_from_openclaw(default_root: Path) -> Path | None:
    try:
        payload = _run(["openclaw", "mcp", "show", "local-apple-data", "--json"], cwd=default_root)
        config = json.loads(payload)
    except Exception:
        return None

    command = config.get("command")
    cwd = config.get("cwd")
    if config.get("args") != [] or not isinstance(command, str) or not isinstance(cwd, str):
        return None

    candidate = Path(cwd).expanduser().resolve()
    if not _path_matches(command, candidate / "scripts/run_mcp_server.sh"):
        return None
    if not (candidate / ".codex-plugin/plugin.json").exists():
        return None
    return candidate


def _resolve_project_root(project_root: Path | None, *, skip_openclaw: bool) -> Path:
    if project_root is not None:
        return project_root.expanduser().resolve()
    env_project_root = os.environ.get(PROJECT_ROOT_ENV)
    if env_project_root:
        return Path(env_project_root).expanduser().resolve()
    if not skip_openclaw:
        configured_project_root = _configured_project_root_from_openclaw(DEFAULT_PROJECT_ROOT)
        if configured_project_root is not None:
            return configured_project_root
    return DEFAULT_PROJECT_ROOT.resolve()


def _cursor_config_candidates(project_root: Path, cursor_config: Path | None) -> list[Path]:
    if cursor_config is not None:
        return [cursor_config.expanduser().resolve()]
    return [
        (project_root / ".cursor/mcp.json").resolve(),
        (Path.home() / ".cursor/mcp.json").resolve(),
    ]


def _resolve_cursor_command(command: Any, *, config_path: Path) -> str | None:
    if not isinstance(command, str):
        return None
    if "${workspaceFolder}" not in command:
        return command
    if config_path.name != "mcp.json" or config_path.parent.name != ".cursor":
        return command
    workspace_root = config_path.parent.parent
    return command.replace("${workspaceFolder}", str(workspace_root))


def _check_cursor(
    project_root: Path,
    *,
    cursor_config: Path | None,
    require_cursor: bool,
) -> tuple[str, str | None]:
    runner = project_root / "scripts/run_mcp_server.sh"
    checked_existing_config = False
    for config_path in _cursor_config_candidates(project_root, cursor_config):
        if not config_path.exists():
            continue
        checked_existing_config = True
        payload = _load_json(config_path)
        servers = payload.get("mcpServers")
        if not isinstance(servers, dict):
            if cursor_config is not None:
                raise RuntimeError("Cursor MCP config is missing mcpServers")
            continue
        server = servers.get(CURSOR_SERVER_NAME)
        if server is None:
            if cursor_config is not None:
                raise RuntimeError("Cursor MCP server local-apple-data is missing")
            continue
        if not isinstance(server, dict):
            raise RuntimeError("Cursor MCP server local-apple-data is not an object")
        if server.get("type") not in (None, "stdio"):
            raise RuntimeError("Cursor MCP server local-apple-data is not stdio")
        if _resolve_cursor_command(server.get("command"), config_path=config_path) != str(runner):
            raise RuntimeError("Cursor MCP command does not match the project runner")
        if server.get("args", []) != []:
            raise RuntimeError("Cursor MCP args should be empty")
        return "mcp_configured", str(config_path)

    if require_cursor:
        if checked_existing_config:
            raise RuntimeError("Cursor MCP server local-apple-data is missing")
        raise RuntimeError("Cursor MCP config is missing")
    return "not_configured", None


def _process_rows() -> list[tuple[int, int, str]]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except FileNotFoundError:
        raise RuntimeError("ps CLI not found on PATH") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("ps timed out") from None
    if result.returncode != 0:
        raise RuntimeError("ps exited nonzero")

    rows: list[tuple[int, int, str]] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) < 3:
            continue
        try:
            pid = int(fields[0])
            ppid = int(fields[1])
        except ValueError:
            continue
        rows.append((pid, ppid, fields[2]))
    return rows


def _command_path_candidates(command: str) -> list[Path]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    candidates: list[Path] = []
    for token in tokens:
        values = [token]
        if "=" in token:
            values.append(token.split("=", 1)[1])
        for value in values:
            value = value.strip("'\"")
            if value.startswith("file://"):
                value = value[7:]
            if value.startswith("/") or value.startswith("~"):
                candidates.append(Path(value).expanduser())
    return candidates


def _process_cwd(pid: int) -> Path | None:
    try:
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("n/") or line.startswith("n~"):
            return Path(line[1:]).expanduser()
    return None


def _process_path_candidates(pid: int, command: str) -> list[Path]:
    candidates = _command_path_candidates(command)
    cwd = _process_cwd(pid)
    if cwd is not None:
        candidates.append(cwd)
    return candidates


def _is_mcp_server_command(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for index, token in enumerate(tokens[:-1]):
        if token == "-m" and tokens[index + 1] == MCP_SERVER_MODULE_NAME:
            return True
    return False


def _path_relative_to_root(path: Path, root: Path) -> Path | None:
    expanded_path = path.expanduser()
    expanded_root = root.expanduser()
    try:
        return expanded_path.relative_to(expanded_root)
    except ValueError:
        pass
    try:
        return expanded_path.resolve(strict=False).relative_to(expanded_root.resolve(strict=False))
    except (OSError, ValueError):
        return None


def _paths_have_path_under(paths: list[Path], root: Path) -> bool:
    return any(_path_relative_to_root(path, root) is not None for path in paths)


def _cache_version_for_paths(paths: list[Path], plugin_cache_root: Path) -> str | None:
    for path in paths:
        relative = _path_relative_to_root(path, plugin_cache_root)
        if relative is not None and relative.parts:
            return relative.parts[0]
    return None


def _check_live_mcp_processes(
    *,
    project_root: Path,
    personal_root: Path,
    plugin_cache_root: Path,
    version: str,
) -> dict[str, Any]:
    stale: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    running_count = 0
    current_cache_count = 0
    source_count = 0
    personal_count = 0

    for pid, ppid, command in _process_rows():
        if not _is_mcp_server_command(command):
            continue
        running_count += 1
        paths = _process_path_candidates(pid, command)
        cache_version = _cache_version_for_paths(paths, plugin_cache_root)
        if cache_version is not None:
            if cache_version == version:
                current_cache_count += 1
            else:
                stale.append(
                    {
                        "kind": "stale_installed_cache_process",
                        "pid": pid,
                        "ppid": ppid,
                        "version": cache_version,
                    }
                )
            continue
        if _paths_have_path_under(paths, project_root):
            source_count += 1
            continue
        if _paths_have_path_under(paths, personal_root):
            personal_count += 1
            continue
        unknown.append(
            {
                "kind": "unknown_mcp_process",
                "pid": pid,
                "ppid": ppid,
                "version": "",
            }
        )

    return {
        "current_cache_count": current_cache_count,
        "personal_count": personal_count,
        "project_root_count": source_count,
        "running_count": running_count,
        "stale_processes": stale,
        "unknown_processes": unknown,
        "status": "ok" if not stale and not unknown else "error",
    }


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify local-apple-data source, installed plugin, and MCP client sync."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help=(
            "Canonical project root. Defaults to LOCAL_APPLE_DATA_PROJECT_ROOT, "
            "then the configured OpenClaw runner when available, then this script's repo root."
        ),
    )
    parser.add_argument(
        "--personal-root",
        type=Path,
        default=_path_from_env("LOCAL_APPLE_DATA_PERSONAL_ROOT", DEFAULT_PERSONAL_ROOT),
        help="Personal plugin source root. Defaults to ~/plugins/local-apple-data.",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=_path_from_env("LOCAL_APPLE_DATA_CACHE_ROOT", DEFAULT_PLUGIN_CACHE_ROOT),
        help="Codex installed plugin cache root. Defaults to ~/.codex/plugins/cache/personal/local-apple-data.",
    )
    parser.add_argument("--skip-codex", action="store_true", help="Skip Codex install/cache checks.")
    parser.add_argument("--skip-claude", action="store_true", help="Skip Claude MCP connectivity checks.")
    parser.add_argument("--skip-openclaw", action="store_true", help="Skip OpenClaw MCP config checks.")
    parser.add_argument("--skip-cursor", action="store_true", help="Skip Cursor MCP config checks.")
    parser.add_argument(
        "--skip-live-processes",
        action="store_true",
        help="Skip live local-apple-data MCP process checks.",
    )
    parser.add_argument(
        "--require-cursor",
        action="store_true",
        help="Fail if no Cursor MCP config contains local-apple-data.",
    )
    parser.add_argument(
        "--cursor-config",
        type=Path,
        default=None,
        help="Specific Cursor mcp.json to verify. Defaults to project .cursor/mcp.json then ~/.cursor/mcp.json.",
    )
    parser.add_argument("--skip-file-sync", action="store_true", help="Skip source/personal/cache file comparison.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    project_root = _resolve_project_root(args.project_root, skip_openclaw=args.skip_openclaw)
    personal_root = args.personal_root.expanduser().resolve()
    plugin_cache_root = args.cache_root.expanduser().resolve()
    runner = project_root / "scripts/run_mcp_server.sh"

    version = _version(project_root)
    cache_root: Path | None = None
    surfaces: dict[str, str] = {}
    # Each surface is checked independently: a missing optional CLI (codex/claude/openclaw/
    # cursor not installed) is reported as "not_available" (non-fatal), a genuine mismatch as
    # "error: <msg>". One surface never aborts the others, so external users on machines without
    # every tool get a useful per-surface report instead of an opaque crash.
    errors: list[str] = []

    if args.skip_codex:
        surfaces["codex"] = "skipped"
    else:
        try:
            cache_root = _check_codex(version, plugin_cache_root)
            surfaces["codex"] = "installed_enabled"
        except ToolNotAvailable:
            surfaces["codex"] = "not_available"
        except Exception as exc:
            surfaces["codex"] = f"error: {_safe_error_message(exc)}"
            errors.append("codex")

    if args.skip_file_sync:
        file_sync = "skipped"
        checked_files = 0
    elif cache_root is None:
        file_sync = "unavailable_without_codex_cache"
        checked_files = 0
    else:
        try:
            checked_files = _assert_same_files(project_root, personal_root, cache_root)
            file_sync = "ok"
        except Exception as exc:
            file_sync = f"error: {_safe_error_message(exc)}"
            checked_files = 0
            errors.append("file_sync")

    if args.skip_claude:
        surfaces["claude"] = "skipped"
    else:
        try:
            _check_claude()
            surfaces["claude"] = "mcp_cli_connected"
        except ToolNotAvailable:
            surfaces["claude"] = "not_available"
        except Exception as exc:
            surfaces["claude"] = f"error: {_safe_error_message(exc)}"
            errors.append("claude")

    if args.skip_openclaw:
        surfaces["openclaw"] = "skipped"
    else:
        try:
            _check_openclaw(project_root)
            surfaces["openclaw"] = "mcp_configured"
        except ToolNotAvailable:
            surfaces["openclaw"] = "not_available"
        except Exception as exc:
            surfaces["openclaw"] = f"error: {_safe_error_message(exc)}"
            errors.append("openclaw")

    cursor_config: str | None = None
    if args.skip_cursor:
        surfaces["cursor"] = "skipped"
    else:
        try:
            cursor_status, cursor_config = _check_cursor(
                project_root,
                cursor_config=args.cursor_config,
                require_cursor=args.require_cursor,
            )
            surfaces["cursor"] = cursor_status
        except ToolNotAvailable:
            surfaces["cursor"] = "not_available"
        except Exception as exc:
            surfaces["cursor"] = f"error: {_safe_error_message(exc)}"
            errors.append("cursor")

    if args.skip_live_processes:
        live_mcp_processes = {"status": "skipped"}
    else:
        try:
            live_mcp_processes = _check_live_mcp_processes(
                project_root=project_root,
                personal_root=personal_root,
                plugin_cache_root=plugin_cache_root,
                version=version,
            )
            if live_mcp_processes["status"] != "ok":
                errors.append("live_mcp_processes")
        except ToolNotAvailable as exc:
            live_mcp_processes = {"message": _safe_error_message(exc), "status": "error"}
            errors.append("live_mcp_processes")
        except Exception as exc:
            live_mcp_processes = {"message": _safe_error_message(exc), "status": "error"}
            errors.append("live_mcp_processes")
    summary = {
        "status": "ok" if not errors else "degraded",
        "plugin": "local-apple-data",
        "version": version,
        "project_root": str(project_root),
        "personal_root": str(personal_root),
        "installed_cache": str(cache_root) if cache_root is not None else None,
        "runner": str(runner),
        "file_sync": file_sync,
        "checked_files": checked_files if not args.skip_file_sync else 0,
        "surfaces": surfaces,
        "cursor_config": cursor_config,
        "live_mcp_processes": live_mcp_processes,
    }
    if errors:
        summary["errors"] = errors
    print(json.dumps(summary, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ToolNotAvailable as exc:
        # Defensive: surface-level checks already convert these to "not_available", but if one
        # escapes (e.g. project-root resolution), report it cleanly rather than as a crash.
        print(json.dumps({"status": "degraded", "message": _safe_error_message(exc)}))
        raise SystemExit(0) from None
    except Exception as exc:
        print(json.dumps({"status": "error", "message": _safe_error_message(exc)}), file=sys.stderr)
        raise SystemExit(1) from None
