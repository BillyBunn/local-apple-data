from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "audit_plugin_artifact_hygiene.py"
)
SPEC = importlib.util.spec_from_file_location("audit_plugin_artifact_hygiene", SCRIPT_PATH)
assert SPEC is not None
audit_plugin_artifact_hygiene = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["audit_plugin_artifact_hygiene"] = audit_plugin_artifact_hygiene
SPEC.loader.exec_module(audit_plugin_artifact_hygiene)


def test_audit_plugin_artifact_hygiene_reports_clean_roots(tmp_path: Path) -> None:
    personal_root = tmp_path / "personal" / "local-apple-data"
    installed_root = tmp_path / "cache" / "0.1.0+test"
    personal_root.mkdir(parents=True)
    installed_root.mkdir(parents=True)
    personal_root.joinpath(".codex-plugin").mkdir()
    personal_root.joinpath(".codex-plugin", "plugin.json").write_text("{}", encoding="utf-8")

    payload = audit_plugin_artifact_hygiene.audit_plugin_artifact_hygiene(
        personal_root=personal_root,
        cache_root=tmp_path / "cache",
        version="0.1.0+test",
    )

    assert payload["status"] == "ok"
    assert payload["finding_count"] == 0
    assert {root["name"]: root["artifact_count"] for root in payload["roots"]} == {
        "installed_cache": 0,
        "personal_root": 0,
    }


def test_audit_plugin_artifact_hygiene_finds_generated_and_local_config(
    tmp_path: Path,
) -> None:
    personal_root = tmp_path / "personal" / "local-apple-data"
    installed_root = tmp_path / "cache" / "0.1.0+test"
    personal_root.mkdir(parents=True)
    installed_root.joinpath("src/pkg/__pycache__").mkdir(parents=True)
    personal_root.joinpath(".env.private").write_text("secret=redacted\n", encoding="utf-8")
    personal_root.joinpath(".claude").mkdir()
    installed_root.joinpath(".venv").mkdir()
    installed_root.joinpath("module.pyc").write_bytes(b"\0\0")
    installed_root.joinpath("src/pkg/__pycache__/module.pyc").write_bytes(b"\0\0")

    payload = audit_plugin_artifact_hygiene.audit_plugin_artifact_hygiene(
        personal_root=personal_root,
        cache_root=tmp_path / "cache",
        version="0.1.0+test",
    )

    patterns = {finding["pattern"] for finding in payload["findings"]}
    assert payload["status"] == "error"
    assert payload["finding_count"] == 5
    assert patterns == {".claude", ".env.*", ".venv", "__pycache__", "*.pyc"}


def test_audit_plugin_artifact_hygiene_derives_manifest_version(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.joinpath(".codex-plugin").mkdir(parents=True)
    project_root.joinpath(".codex-plugin", "plugin.json").write_text(
        '{"version":"0.1.0+derived"}',
        encoding="utf-8",
    )
    personal_root = tmp_path / "personal" / "local-apple-data"
    installed_root = tmp_path / "cache" / "0.1.0+derived"
    personal_root.mkdir(parents=True)
    installed_root.mkdir(parents=True)
    monkeypatch.setattr(audit_plugin_artifact_hygiene, "PROJECT_ROOT", project_root)

    payload = audit_plugin_artifact_hygiene.audit_plugin_artifact_hygiene(
        personal_root=personal_root,
        cache_root=tmp_path / "cache",
    )

    assert payload["status"] == "ok"
    assert payload["version"] == "0.1.0+derived"


def test_audit_plugin_artifact_hygiene_reports_missing_installed_cache(
    tmp_path: Path,
) -> None:
    personal_root = tmp_path / "personal" / "local-apple-data"
    personal_root.mkdir(parents=True)

    payload = audit_plugin_artifact_hygiene.audit_plugin_artifact_hygiene(
        personal_root=personal_root,
        cache_root=tmp_path / "cache",
        version="0.1.0+test",
    )

    assert payload["status"] == "error"
    assert payload["findings"] == [
        {
            "kind": "missing_root",
            "pattern": "",
            "relative_path": "",
            "root": "installed_cache",
        }
    ]


def test_audit_plugin_artifact_hygiene_cli_redacts_roots(
    tmp_path: Path,
    capsys,
) -> None:
    personal_root = tmp_path / "personal" / "local-apple-data"
    installed_root = tmp_path / "cache" / "0.1.0+test"
    personal_root.mkdir(parents=True)
    installed_root.mkdir(parents=True)
    installed_root.joinpath(".pytest_cache").mkdir()

    exit_code = audit_plugin_artifact_hygiene.main(
        [
            "--personal-root",
            str(personal_root),
            "--cache-root",
            str(tmp_path / "cache"),
            "--version",
            "0.1.0+test",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "<personal-root>" in captured.out
    assert "<installed-cache>" in captured.out
    assert str(tmp_path) not in captured.out
    assert captured.err == ""


def test_runtime_verifier_disables_bytecode_for_installed_cache_hygiene() -> None:
    verifier_source = (
        Path(__file__).resolve().parents[1] / "scripts" / "verify_runtime.py"
    ).read_text(encoding="utf-8")

    assert "sys.dont_write_bytecode = True" in verifier_source
    assert 'env["PYTHONDONTWRITEBYTECODE"] = "1"' in verifier_source
    assert '"PYTHONDONTWRITEBYTECODE": env["PYTHONDONTWRITEBYTECODE"]' in verifier_source


def test_mcp_runner_disables_bytecode_for_installed_cache_hygiene() -> None:
    root = Path(__file__).resolve().parents[1]
    runner_source = (root / "scripts" / "run_mcp_server.sh").read_text(
        encoding="utf-8"
    )
    server_source = (root / "src" / "local_apple_data" / "mcp_server.py").read_text(
        encoding="utf-8"
    )

    assert "export PYTHONDONTWRITEBYTECODE=1" in runner_source
    assert "sys.dont_write_bytecode = True" in server_source
