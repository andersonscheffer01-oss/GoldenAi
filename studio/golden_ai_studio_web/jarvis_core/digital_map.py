"""Bounded, read-only inventory for an explicitly approved project root."""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


EXCLUDED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
    "build", "dist", "__pycache__", ".pytest_cache", ".mypy_cache",
    "cache", "caches", "tmp", "temp", "logs", "log",
})
SECRET_NAMES = frozenset({
    ".env", ".env.local", ".env.production", "api_keys.json",
    "credentials.json", "credentials.yaml", "secrets.json", "wallet.dat",
})
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
RUNTIME_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-shm", ".db-wal")
TEXT_SUFFIXES = frozenset({
    ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".py", ".js", ".ts", ".tsx", ".jsx", ".html",
    ".css", ".scss", ".bat", ".cmd", ".ps1", ".mq5", ".sql",
})


def _stable_id(root: Path, relative: str) -> str:
    value = "%s:%s" % (str(root).casefold(), relative.casefold())
    return "file_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _safe_relative(root: Path, path: Path) -> Optional[str]:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return None


def _is_secret_name(name: str) -> bool:
    lowered = str(name or "").lower()
    return (lowered in SECRET_NAMES or lowered.startswith(".env.") or
            lowered.endswith(SECRET_SUFFIXES) or
            bool(re.search(r"(^|[_.-])(secret|credential|password|token)([_.-]|$)",
                           lowered)))


def _file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".mq5"}:
        return "source"
    if suffix in {".md", ".txt", ".rst", ".pdf", ".doc", ".docx"}:
        return "document"
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        return "photo"
    if suffix in {".mp4", ".mov", ".avi", ".mkv"}:
        return "video"
    if suffix in {".wav", ".mp3", ".flac", ".ogg"}:
        return "audio"
    if suffix in {".zip", ".7z", ".rar", ".tar", ".gz"}:
        return "archive"
    return "other"


def _read_text(path: Path, max_bytes: int) -> str:
    try:
        data = path.read_bytes()[:max(0, int(max_bytes))]
        return data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _bounded_hash(path: Path, max_bytes: int) -> str:
    try:
        stat = path.stat()
        if stat.st_size > max(0, int(max_bytes)):
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


class ReadOnlyDigitalMap:
    """Inventory only the approved root, with deterministic scale guards."""

    def __init__(self, approved_root: Path | str, *, max_files: int = 2000,
                 max_bytes: int = 512 * 1024 * 1024,
                 text_max_bytes: int = 64 * 1024,
                 hash_max_bytes: int = 8 * 1024 * 1024):
        raw = Path(approved_root).expanduser().resolve()
        if not raw.exists() or not raw.is_dir():
            raise ValueError("approved root must be an existing directory")
        self.root = raw
        self.max_files = max(1, int(max_files))
        self.max_bytes = max(0, int(max_bytes))
        self.text_max_bytes = max(0, int(text_max_bytes))
        self.hash_max_bytes = max(0, int(hash_max_bytes))

    def _walk(self):
        stack = [self.root]
        while stack:
            current = stack.pop()
            try:
                children = sorted(os.scandir(current),
                                  key=lambda item: item.name.casefold(),
                                  reverse=True)
            except OSError:
                continue
            for entry in children:
                path = Path(entry.path)
                if entry.is_symlink():
                    yield path, "SYMLINK_NOT_TRAVERSED"
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.casefold() in EXCLUDED_DIRECTORIES:
                        yield path, "EXCLUDED_DIRECTORY"
                    else:
                        stack.append(path)
                    continue
                yield path, "FILE"

    def scan(self, previous_manifest: Optional[Dict[str, Dict[str, Any]]] = None,
             *, extract_text: bool = False, calculate_hash: bool = True) -> Dict[str, Any]:
        previous = dict(previous_manifest or {})
        entries = []
        excluded = []
        discovered = 0
        represented_bytes = 0
        total_seen = 0
        started = time.perf_counter()
        for path, walk_kind in self._walk():
            if total_seen >= self.max_files:
                break
            total_seen += 1
            if walk_kind != "FILE":
                continue
            discovered += 1
            relative = _safe_relative(self.root, path)
            if not relative:
                excluded.append({"relative_path": str(path), "reason": "OUTSIDE_ROOT"})
                continue
            name = path.name.lower()
            if (_is_secret_name(name) or name.endswith(RUNTIME_SUFFIXES) or
                    path.suffix.lower() in RUNTIME_SUFFIXES):
                excluded.append({"relative_path": relative, "reason": "SECRET_OR_RUNTIME"})
                continue
            try:
                stat = path.stat()
            except OSError:
                excluded.append({"relative_path": relative, "reason": "STAT_FAILED"})
                continue
            if represented_bytes + stat.st_size > self.max_bytes:
                excluded.append({"relative_path": relative, "reason": "BYTE_BUDGET"})
                continue
            represented_bytes += stat.st_size
            key = _stable_id(self.root, relative)
            old = previous.get(key) or {}
            fingerprint = {"size": stat.st_size, "modified": stat.st_mtime}
            state = "UNCHANGED" if old.get("size") == stat.st_size and \
                old.get("modified") == stat.st_mtime else ("MODIFIED" if old else "NEW")
            suffix = path.suffix.lower()
            content = ""
            content_status = "METADATA_ONLY"
            if extract_text and suffix in TEXT_SUFFIXES and stat.st_size <= self.text_max_bytes:
                content = _read_text(path, self.text_max_bytes)
                content_status = "TEXT_EXTRACTED" if content else "METADATA_ONLY"
            item = {
                "entity_id": key,
                "name": path.name,
                "type": _file_kind(path),
                "path": str(path),
                "reference": str(path),
                "approved_root": str(self.root),
                "relative_path": relative,
                "parent": str(path.parent),
                "size": stat.st_size,
                "created": stat.st_ctime,
                "modified": stat.st_mtime,
                "indexed_at": time.time(),
                "content_status": content_status,
                "classification": "INTERNAL",
                "hash": (_bounded_hash(path, self.hash_max_bytes)
                         if calculate_hash else ""),
                "relationships": [],
                "state": state,
                "text_preview": content[:2000],
                **fingerprint,
            }
            entries.append(item)
        current_ids = {item["entity_id"] for item in entries}
        missing = [dict(value, state="MISSING") for key, value in previous.items()
                   if key not in current_ids]
        return {
            "approved_root": str(self.root),
            "files_discovered": discovered,
            "files_indexed": len(entries),
            "files_excluded": len(excluded),
            "bytes_represented": represented_bytes,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "entries": entries,
            "excluded": excluded,
            "missing": missing,
            "manifest": {item["entity_id"]: item for item in entries},
        }

    @staticmethod
    def render_projection(report: Dict[str, Any]) -> str:
        lines = [
            "---", "managed_by: jarvis-digital-map", "schema_version: 1",
            "approved_root: %s" % report["approved_root"], "---", "",
            "# Golden Project File Map", "",
            "Read-only references; original files remain in place.", "",
            "- Indexed: %d" % report["files_indexed"],
            "- Excluded: %d" % report["files_excluded"],
            "- Missing: %d" % len(report["missing"]), "",
        ]
        for item in report["entries"][:500]:
            lines.append("- [%s] `%s` (%d bytes, %s)" % (
                item["type"], item["relative_path"], item["size"], item["state"]))
        return "\n".join(lines) + "\n"

    @classmethod
    def project_to_vault(cls, report: Dict[str, Any], vault_root: Path | str,
                         relative_note: str = "08_Golden/PC File Map.md") -> Path:
        vault = Path(vault_root).expanduser().resolve()
        marker = vault / "README.md"
        if not marker.exists() or "Golden Memory Vault" not in marker.read_text(
                encoding="utf-8", errors="replace"):
            raise ValueError("vault is not an approved Golden Memory Vault")
        target = (vault / relative_note).resolve()
        target.relative_to(vault)
        if target.exists() and "managed_by: jarvis-digital-map" not in target.read_text(
                encoding="utf-8", errors="replace"):
            raise FileExistsError("refusing to overwrite unrelated vault note")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(cls.render_projection(report), encoding="utf-8")
        return target
