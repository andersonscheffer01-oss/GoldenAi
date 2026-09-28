from pathlib import Path

from jarvis_core.digital_map import ReadOnlyDigitalMap


def test_allowlisted_read_only_scan_excludes_secrets_runtime_and_build(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("safe project", encoding="utf-8")
    (root / ".env").write_text("API_KEY=hidden", encoding="utf-8")
    (root / "api_keys.json").write_text("{}", encoding="utf-8")
    (root / "runtime.db").write_bytes(b"sqlite")
    (root / "build").mkdir()
    (root / "build" / "ignored.py").write_text("ignored", encoding="utf-8")

    report = ReadOnlyDigitalMap(root).scan(extract_text=True)

    assert report["files_indexed"] == 1
    assert report["files_excluded"] >= 3
    assert all("API_KEY" not in str(item) for item in report["entries"])
    assert report["entries"][0]["content_status"] == "TEXT_EXTRACTED"


def test_incremental_scan_marks_unchanged_modified_and_missing(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    keep = root / "keep.txt"
    remove = root / "remove.txt"
    keep.write_text("one", encoding="utf-8")
    remove.write_text("two", encoding="utf-8")
    scanner = ReadOnlyDigitalMap(root)
    first = scanner.scan()
    keep.write_text("changed", encoding="utf-8")
    remove.unlink()
    second = scanner.scan(first["manifest"])

    states = {item["relative_path"]: item["state"] for item in second["entries"]}
    assert states["keep.txt"] == "MODIFIED"
    assert second["missing"][0]["state"] == "MISSING"


def test_projection_is_reference_only_and_preserves_human_note(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('ok')", encoding="utf-8")
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "README.md").write_text("# Golden Memory Vault", encoding="utf-8")
    human = vault / "04_Knowledge" / "Human.md"
    human.parent.mkdir()
    human.write_text("human content", encoding="utf-8")

    report = ReadOnlyDigitalMap(root).scan()
    target = ReadOnlyDigitalMap.project_to_vault(report, vault)

    assert target.exists()
    assert human.read_text(encoding="utf-8") == "human content"
    assert "main.py" in target.read_text(encoding="utf-8")
    assert (root / "main.py").read_text(encoding="utf-8") == "print('ok')"
