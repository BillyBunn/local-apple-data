from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import local_apple_data.adapters.filesystem as filesystem_adapter
from local_apple_data.adapters.filesystem import (
    apply_filesystem_change,
    export_filesystem_file,
    get_filesystem_content,
    get_filesystem_metadata,
    get_filesystem_root_metadata,
    list_filesystem_folder,
    list_filesystem_folder_tree,
    plan_filesystem_change,
    search_filesystem_metadata,
)
from local_apple_data.handles import make_opaque_handle


def _make_home_root(root: Path) -> None:
    (root / "Documents").mkdir(parents=True)
    (root / "Documents" / "notes.md").write_text("hello home\nline two\n", encoding="utf-8")
    (root / "Documents" / "data.bin").write_bytes(b"BINARY-BYTES")


def _content_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fs_handle_for(relative: str) -> str:
    icloud = make_opaque_handle("icloud:file", relative)
    return "fs:file:v1:" + icloud.split(":v1:")[1]


def _fs_approval_token(plan: dict) -> str:
    return "filesystem-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]


# ---------------------------------------------------------------------------
# Namespace and source rewriting
# ---------------------------------------------------------------------------


def test_search_uses_filesystem_source_and_fs_handle(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _make_home_root(root)
    result = search_filesystem_metadata("notes.md", root=root)
    assert result["status"] == "ok"
    assert result["source"] == "filesystem"
    assert result["result_count"] == 1
    assert result["results"][0]["handle"].startswith("fs:file:v1:")
    assert "icloud:file:v1:" not in json.dumps(result)


def test_root_and_listing_present_metadata(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _make_home_root(root)
    root_meta = get_filesystem_root_metadata(root=root)
    assert root_meta["status"] == "ok"
    assert root_meta["source"] == "filesystem"
    assert root_meta["result"]["handle"].startswith("fs:file:v1:")
    assert root_meta["result"]["is_root"] is True

    listing = list_filesystem_folder(root_meta["result"]["handle"], root=root)
    assert listing["status"] == "ok"
    assert listing["source"] == "filesystem"
    assert listing["result_count"] >= 1

    tree = list_filesystem_folder_tree(root_meta["result"]["handle"], root=root, depth=2)
    assert tree["status"] == "ok"
    assert tree["source"] == "filesystem"


# ---------------------------------------------------------------------------
# Full CRUD happy path
# ---------------------------------------------------------------------------


def test_full_crud_happy_path(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _make_home_root(root)

    parent = search_filesystem_metadata("Documents", root=root)["results"][0]["handle"]

    # Create text.
    create_plan = plan_filesystem_change(
        "create_text",
        parent_handle=parent,
        filename="draft.md",
        content_text="draft body",
        root=root,
    )
    assert create_plan["status"] == "ok"
    assert create_plan["source"] == "filesystem"
    create = apply_filesystem_change(
        "create_text",
        parent_handle=parent,
        filename="draft.md",
        content_text="draft body",
        approval_token=_fs_approval_token(create_plan),
        confirm_apply=True,
        root=root,
    )
    assert create["status"] == "ok"
    assert create["mutation_applied"] is True
    assert create["source"] == "filesystem"
    assert create["read_back"]["handle"].startswith("fs:file:v1:")
    assert (root / "Documents" / "draft.md").read_text(encoding="utf-8") == "draft body"

    # Read content back.
    draft_handle = search_filesystem_metadata("draft.md", root=root)["results"][0]["handle"]
    content = get_filesystem_content(draft_handle, root=root)
    assert content["status"] == "ok"
    assert content["result"]["content_chars"] == len("draft body")

    # Update via replace_text.
    replace_plan = plan_filesystem_change(
        "replace_text",
        handle=draft_handle,
        expected_current_sha256=_content_sha("draft body"),
        content_text="draft body v2",
        root=root,
    )
    replace = apply_filesystem_change(
        "replace_text",
        handle=draft_handle,
        expected_current_sha256=_content_sha("draft body"),
        content_text="draft body v2",
        approval_token=_fs_approval_token(replace_plan),
        confirm_apply=True,
        root=root,
    )
    assert replace["status"] == "ok"
    assert (root / "Documents" / "draft.md").read_text(encoding="utf-8") == "draft body v2"

    # Move draft to root parent.
    root_handle = get_filesystem_root_metadata(root=root)["result"]["handle"]
    move_plan = plan_filesystem_change(
        "move_text",
        handle=draft_handle,
        parent_handle=root_handle,
        expected_current_sha256=_content_sha("draft body v2"),
        root=root,
    )
    move = apply_filesystem_change(
        "move_text",
        handle=draft_handle,
        parent_handle=root_handle,
        expected_current_sha256=_content_sha("draft body v2"),
        approval_token=_fs_approval_token(move_plan),
        confirm_apply=True,
        root=root,
    )
    assert move["status"] == "ok"
    assert (root / "draft.md").exists()
    assert not (root / "Documents" / "draft.md").exists()

    # Trash the moved file (reversible ~/.Trash for home root).
    moved_handle = search_filesystem_metadata("draft.md", root=root)["results"][0]["handle"]
    trash_plan = plan_filesystem_change(
        "trash_text",
        handle=moved_handle,
        expected_current_sha256=_content_sha("draft body v2"),
        root=root,
    )
    trash = apply_filesystem_change(
        "trash_text",
        handle=moved_handle,
        expected_current_sha256=_content_sha("draft body v2"),
        approval_token=_fs_approval_token(trash_plan),
        confirm_apply=True,
        root=root,
    )
    assert trash["status"] == "ok"
    assert not (root / "draft.md").exists()
    assert (root / ".Trash").exists()


def test_permanent_delete_gate(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _make_home_root(root)
    (root / "Documents" / "gone.md").write_text("temporary", encoding="utf-8")
    handle = search_filesystem_metadata("gone.md", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=_content_sha("temporary"),
        root=root,
    )
    result = apply_filesystem_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=_content_sha("temporary"),
        approval_token=_fs_approval_token(plan),
        confirm_apply=True,
        root=root,
    )
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["permanently_deleted"] is True
    assert not (root / "Documents" / "gone.md").exists()


def test_apply_requires_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _make_home_root(root)
    parent = search_filesystem_metadata("Documents", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "create_text",
        parent_handle=parent,
        filename="x.md",
        content_text="x",
        root=root,
    )
    result = apply_filesystem_change(
        "create_text",
        parent_handle=parent,
        filename="x.md",
        content_text="x",
        approval_token=_fs_approval_token(plan),
        root=root,
    )
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"


# ---------------------------------------------------------------------------
# Hard safety boundaries
# ---------------------------------------------------------------------------


def test_dotdot_filename_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _make_home_root(root)
    root_handle = get_filesystem_root_metadata(root=root)["result"]["handle"]
    plan = plan_filesystem_change(
        "create_text",
        parent_handle=root_handle,
        filename="../escape.md",
        content_text="x",
        root=root,
    )
    assert plan["status"] == "error"
    assert any(w["code"] == "invalid_filename" for w in plan["warnings"])


def test_symlink_escape_not_resolvable(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _make_home_root(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("OUTSIDE", encoding="utf-8")
    (root / "escape.md").symlink_to(outside / "secret.md")
    (root / "escapedir").symlink_to(outside, target_is_directory=True)

    # Symlinks are skipped by the reused iterator: never surfaced.
    assert search_filesystem_metadata("escape", root=root)["result_count"] == 0
    assert search_filesystem_metadata("escapedir", root=root)["result_count"] == 0

    # A forged fs handle for the symlink target fails closed.
    forged = _fs_handle_for("escape.md")
    content = get_filesystem_content(forged, root=root)
    assert content["status"] == "not_found"
    assert content["source"] == "filesystem"
    # The outside file was never read.
    assert "OUTSIDE" not in json.dumps(content)


def test_target_outside_home_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _make_home_root(root)
    outside = tmp_path / "otheruser"
    outside.mkdir()
    # Forge a parent handle whose relative path escapes the home root.
    forged_parent = _fs_handle_for("../otheruser")
    plan = plan_filesystem_change(
        "create_text",
        parent_handle=forged_parent,
        filename="x.md",
        content_text="x",
        root=root,
    )
    # The forged parent does not resolve to a real in-root directory.
    assert plan["status"] == "error"

    apply_result = apply_filesystem_change(
        "create_text",
        parent_handle=forged_parent,
        filename="x.md",
        content_text="x",
        approval_token="filesystem-apply:v1:deadbeef",
        confirm_apply=True,
        root=root,
    )
    assert apply_result["status"] != "ok" or apply_result["mutation_applied"] is False
    assert not (outside / "x.md").exists()


def test_other_users_home_not_reachable(tmp_path: Path) -> None:
    root = tmp_path / "home"
    _make_home_root(root)
    # An absolute-path style component cannot be created; separators are rejected.
    root_handle = get_filesystem_root_metadata(root=root)["result"]["handle"]
    plan = plan_filesystem_change(
        "create_folder",
        parent_handle=root_handle,
        filename="/Users/otheruser",
        root=root,
    )
    assert plan["status"] == "error"


# ---------------------------------------------------------------------------
# Credential/secret denylist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative,denied",
    [
        (".ssh/id_rsa", True),
        (".ssh", True),
        (".aws/credentials", True),
        (".gnupg/secring.gpg", True),
        (".config/gh/hosts.yml", True),
        (".config/gcloud/token", True),
        (".netrc", True),
        (".docker/config.json", True),
        (".kube/config", True),
        ("Library/Keychains/login.keychain-db", True),
        ("Library/Application Support/com.apple.TCC/TCC.db", True),
        ("Library/Application Support/local-apple-data/.env.operator", True),
        (".env", True),
        (".env.local", True),
        (".env.production", True),
        (".SSH/id_rsa", True),
        (".ENV", True),
        (".zshrc", False),
        (".bashrc", False),
        (".envrc", False),
        (".docker/daemon.json", False),
        ("Documents/report.txt", False),
        ("Library/Docs/ok.txt", False),
    ],
)
def test_credential_denylist_predicate(relative: str, denied: bool) -> None:
    assert filesystem_adapter._is_credential_relative(relative) is denied


def test_credential_content_read_refused_metadata_allowed(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library" / "Keychains").mkdir(parents=True)
    (root / "Library" / "Keychains" / "login.txt").write_text("secret keychain", encoding="utf-8")

    hit = search_filesystem_metadata("login", root=root)
    assert hit["result_count"] == 1
    handle = hit["results"][0]["handle"]

    # Metadata-only access is allowed.
    meta = get_filesystem_metadata(handle, root=root)
    assert meta["status"] == "ok"
    assert meta["result"]["name"] == "login.txt"

    # Content read is refused.
    content = get_filesystem_content(handle, root=root)
    assert content["status"] == "error"
    assert content["warnings"][0]["code"] == "credential_path_blocked"
    assert "secret keychain" not in json.dumps(content)


def test_credential_mutation_refused(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library" / "Keychains").mkdir(parents=True)
    (root / "Library" / "Keychains" / "login.txt").write_text("secret keychain", encoding="utf-8")
    handle = search_filesystem_metadata("login", root=root)["results"][0]["handle"]

    plan = plan_filesystem_change(
        "replace_text",
        handle=handle,
        content_text="tampered",
        expected_current_sha256=_content_sha("secret keychain"),
        root=root,
    )
    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "credential_path_blocked"

    apply_result = apply_filesystem_change(
        "replace_text",
        handle=handle,
        content_text="tampered",
        expected_current_sha256=_content_sha("secret keychain"),
        approval_token="filesystem-apply:v1:deadbeef",
        confirm_apply=True,
        root=root,
    )
    assert apply_result["status"] == "error"
    assert apply_result["warnings"][0]["code"] == "credential_path_blocked"
    assert apply_result["mutation_applied"] is False
    # File is untouched.
    assert (root / "Library" / "Keychains" / "login.txt").read_text(encoding="utf-8") == "secret keychain"


def test_credential_override_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "home"
    (root / "Library" / "Keychains").mkdir(parents=True)
    (root / "Library" / "Keychains" / "login.txt").write_text("secret keychain", encoding="utf-8")
    handle = search_filesystem_metadata("login", root=root)["results"][0]["handle"]

    monkeypatch.setenv("LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS", "1")
    content = get_filesystem_content(handle, root=root)
    assert content["status"] == "ok"
    assert content["result"]["content_chars"] == len("secret keychain")


def test_ssh_private_key_content_refused(tmp_path: Path) -> None:
    # ~/.ssh is a hidden dir; it is not surfaced through search at all, and a
    # forged handle for its content is refused by the credential guard.
    root = tmp_path / "home"
    _make_home_root(root)
    (root / ".ssh").mkdir()
    (root / ".ssh" / "id_rsa").write_text("PRIVATE KEY MATERIAL", encoding="utf-8")

    assert search_filesystem_metadata("id_rsa", root=root)["result_count"] == 0

    forged = _fs_handle_for(".ssh/id_rsa")
    content = get_filesystem_content(forged, root=root)
    assert content["status"] == "error"
    assert content["warnings"][0]["code"] == "credential_path_blocked"
    assert "PRIVATE KEY MATERIAL" not in json.dumps(content)


def test_env_file_content_refused(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "project").mkdir(parents=True)
    (root / "project" / ".env").write_text("SECRET_TOKEN=abc123", encoding="utf-8")

    forged = _fs_handle_for("project/.env")
    content = get_filesystem_content(forged, root=root)
    assert content["status"] == "error"
    assert content["warnings"][0]["code"] == "credential_path_blocked"
    assert "SECRET_TOKEN" not in json.dumps(content)


def test_export_credential_path_refused(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library" / "Keychains").mkdir(parents=True)
    (root / "Library" / "Keychains" / "login.txt").write_text("secret", encoding="utf-8")
    handle = search_filesystem_metadata("login", root=root)["results"][0]["handle"]
    result = export_filesystem_file(
        handle,
        output_dir=tmp_path / "exports",
        root=root,
    )
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "credential_path_blocked"


# ---------------------------------------------------------------------------
# Composed effective-destination credential boundary (v1.178 security fix)
# ---------------------------------------------------------------------------


def _blocked_at_plan(plan: dict) -> bool:
    return (
        plan["status"] == "error"
        and bool(plan.get("warnings"))
        and plan["warnings"][0]["code"] == "credential_path_blocked"
    )


def test_compose_create_folder_path_into_keychains_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library").mkdir(parents=True)
    lib = search_filesystem_metadata("Library", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "create_folder_path",
        parent_handle=lib,
        folder_components=["Keychains", "injected"],
        root=root,
    )
    assert _blocked_at_plan(plan)
    # The intermediate denylisted component is caught before the trailing one.
    assert not (root / "Library" / "Keychains").exists()


def test_compose_create_folder_path_into_tcc_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library").mkdir(parents=True)
    lib = search_filesystem_metadata("Library", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "create_folder_path",
        parent_handle=lib,
        folder_components=["Application Support", "com.apple.TCC"],
        root=root,
    )
    assert _blocked_at_plan(plan)


def test_compose_create_folder_denylisted_folder_name_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library").mkdir(parents=True)
    lib = search_filesystem_metadata("Library", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "create_folder",
        parent_handle=lib,
        filename="Keychains",
        root=root,
    )
    assert _blocked_at_plan(plan)


def test_compose_create_folder_dot_ssh_under_home_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Documents").mkdir(parents=True)
    root_handle = get_filesystem_root_metadata(root=root)["result"]["handle"]
    plan = plan_filesystem_change(
        "create_folder",
        parent_handle=root_handle,
        filename=".ssh",
        root=root,
    )
    assert _blocked_at_plan(plan)


def test_compose_create_text_into_credential_dir_rejected(tmp_path: Path) -> None:
    # A reachable (non-hidden) parent that resolves to a credential dir: create
    # a real Library/Keychains dir, obtain its handle, and try to create a text
    # file inside it. The composed destination lands inside the sealed dir.
    root = tmp_path / "home"
    (root / "Library" / "Keychains").mkdir(parents=True)
    kc = search_filesystem_metadata("Keychains", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "create_text",
        parent_handle=kc,
        filename="notes.md",
        content_text="x",
        root=root,
    )
    assert _blocked_at_plan(plan)
    assert not (root / "Library" / "Keychains" / "notes.md").exists()


def test_compose_import_file_into_credential_dir_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library" / "Keychains").mkdir(parents=True)
    source = tmp_path / "external.bin"
    source.write_bytes(b"payload")
    kc = search_filesystem_metadata("Keychains", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "import_file",
        parent_handle=kc,
        filename="external.bin",
        source_file=str(source),
        root=root,
    )
    assert _blocked_at_plan(plan)


def test_compose_rename_to_denylisted_name_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library" / "NotSecret").mkdir(parents=True)
    ns = search_filesystem_metadata("NotSecret", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "rename_folder",
        handle=ns,
        filename="Keychains",
        expected_current_sha256="deadbeef",
        root=root,
    )
    assert _blocked_at_plan(plan)


def test_compose_move_file_target_inside_denylisted_dir_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library" / "Keychains").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "data.bin").write_bytes(b"X")
    kc = search_filesystem_metadata("Keychains", root=root)["results"][0]["handle"]
    source = search_filesystem_metadata("data.bin", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "move_file",
        handle=source,
        parent_handle=kc,
        expected_current_sha256="deadbeef",
        root=root,
    )
    assert _blocked_at_plan(plan)


def test_compose_copy_file_target_inside_denylisted_dir_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library" / "Keychains").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "data.bin").write_bytes(b"X")
    kc = search_filesystem_metadata("Keychains", root=root)["results"][0]["handle"]
    source = search_filesystem_metadata("data.bin", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "copy_file",
        handle=source,
        parent_handle=kc,
        expected_current_sha256="deadbeef",
        root=root,
    )
    assert _blocked_at_plan(plan)


def test_compose_move_file_source_secret_rejected(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library" / "Keychains").mkdir(parents=True)
    (root / "Library" / "Keychains" / "login.bin").write_bytes(b"SECRET")
    (root / "Documents").mkdir()
    source = search_filesystem_metadata("login.bin", root=root)["results"][0]["handle"]
    docs = search_filesystem_metadata("Documents", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "move_file",
        handle=source,
        parent_handle=docs,
        expected_current_sha256="deadbeef",
        root=root,
    )
    assert _blocked_at_plan(plan)


def test_compose_apply_also_rejects_before_mutation(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library").mkdir(parents=True)
    lib = search_filesystem_metadata("Library", root=root)["results"][0]["handle"]
    result = apply_filesystem_change(
        "create_folder_path",
        parent_handle=lib,
        folder_components=["Keychains", "injected"],
        approval_token="filesystem-apply:v1:deadbeef",
        confirm_apply=True,
        root=root,
    )
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "credential_path_blocked"
    assert result["mutation_applied"] is False
    assert not (root / "Library" / "Keychains").exists()


def test_compose_legit_create_under_library_notsecret_succeeds(tmp_path: Path) -> None:
    root = tmp_path / "home"
    (root / "Library" / "NotSecret").mkdir(parents=True)
    ns = search_filesystem_metadata("NotSecret", root=root)["results"][0]["handle"]
    plan = plan_filesystem_change(
        "create_text",
        parent_handle=ns,
        filename="ok.md",
        content_text="fine",
        root=root,
    )
    assert plan["status"] == "ok"
    lib = search_filesystem_metadata("Library", root=root)["results"][0]["handle"]
    plan2 = plan_filesystem_change(
        "create_folder_path",
        parent_handle=lib,
        folder_components=["NotSecret", "sub"],
        root=root,
    )
    assert plan2["status"] == "ok"


def test_compose_denylist_predicate_is_component_scoped() -> None:
    # Component match, not substring: `foo.ssh` must NOT match; `.ssh/x` must.
    assert filesystem_adapter._is_credential_relative("Documents/foo.ssh") is False
    assert filesystem_adapter._is_credential_relative("Documents/my.ssh.backup") is False
    assert filesystem_adapter._is_credential_relative(".ssh/x") is True
    assert filesystem_adapter._is_credential_relative("Library/Keychains") is True
    assert filesystem_adapter._is_credential_relative("LibraryKeychains") is False
