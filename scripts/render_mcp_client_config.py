#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_NAME = "local-apple-data"
ClientName = Literal["claude-code", "cursor", "generic", "openclaw"]


def render_server_config(
    *,
    client: ClientName,
    project_root: Path = PROJECT_ROOT,
    absolute: bool = False,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    runner = project_root / "scripts" / "run_mcp_server.sh"
    if not runner.exists():
        raise ValueError("MCP runner script is missing")

    if client == "cursor":
        command = str(runner) if absolute else "${workspaceFolder}/scripts/run_mcp_server.sh"
        server: dict[str, Any] = {
            "type": "stdio",
            "command": command,
            "args": [],
        }
    elif client == "claude-code":
        server = {
            "command": str(runner),
            "args": [],
        }
    elif client == "generic":
        server = {
            "command": str(runner),
            "args": [],
            "cwd": str(project_root),
        }
    elif client == "openclaw":
        server = {
            "command": str(runner),
            "args": [],
            "cwd": str(project_root),
        }
    else:
        raise ValueError("unsupported MCP client")

    return server


def render_config(
    *,
    client: ClientName,
    project_root: Path = PROJECT_ROOT,
    absolute: bool = False,
) -> dict[str, Any]:
    server = render_server_config(
        client=client,
        project_root=project_root,
        absolute=absolute,
    )
    return {"mcpServers": {SERVER_NAME: server}}


def _exception_class_name(exc: Exception) -> str:
    return type(exc).__name__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render local-apple-data MCP client config JSON.")
    parser.add_argument(
        "--client",
        choices=["claude-code", "cursor", "generic", "openclaw"],
        default="generic",
        help="Client config shape to render.",
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--absolute",
        action="store_true",
        help="Use absolute runner path for Cursor instead of ${workspaceFolder}.",
    )
    parser.add_argument(
        "--server-only",
        action="store_true",
        help="Print only the selected MCP server object instead of the mcpServers wrapper.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print one-line compact JSON for shell command arguments.",
    )
    args = parser.parse_args(argv)

    try:
        if args.server_only:
            payload = render_server_config(
                client=args.client,
                project_root=args.project_root,
                absolute=args.absolute,
            )
        else:
            payload = render_config(
                client=args.client,
                project_root=args.project_root,
                absolute=args.absolute,
            )
    except ValueError as exc:
        print(f"MCP config render failed: {_exception_class_name(exc)}", file=sys.stderr)
        return 1

    if args.compact:
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
