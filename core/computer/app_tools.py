from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from core.permissions import PermissionManager
from .models import ApplicationInfo


KNOWN_APPS = {
    "notepad": ["notepad.exe"],
    "explorer": ["explorer.exe"],
    "browser": ["msedge.exe", "chrome.exe", "firefox.exe"],
    "metaeditor": ["metaeditor64.exe", "MetaEditor64.exe"],
    "metatrader 5": ["terminal64.exe", "terminal.exe"],
    "golden ai studio": [r"C:\GoldenAI\ABRIR_GOLDEN_AI_STUDIO.bat"],
    "git": ["git.exe"],
    "python": ["python.exe"],
    "vs code": ["Code.exe"],
}


def _candidate_roots() -> list[Path]:
    roots = [Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)"), Path(r"C:\GoldenAI")]
    return [root for root in roots if root.exists()]


def find_installed_app(name: str) -> dict:
    key = str(name).lower().strip()
    candidates = KNOWN_APPS.get(key, [name])
    for candidate in candidates:
        direct = shutil.which(candidate)
        if direct:
            return asdict(ApplicationInfo(name=name, found=True, path=direct, source="PATH"))
        p = Path(candidate)
        if p.is_absolute() and p.exists():
            return asdict(ApplicationInfo(name=name, found=True, path=str(p), source="known_path"))
        for root in _candidate_roots():
            try:
                matches = list(root.glob(f"**/{candidate}"))
            except Exception:
                matches = []
            if matches:
                return asdict(ApplicationInfo(name=name, found=True, path=str(matches[0]), source=str(root)))
    return asdict(ApplicationInfo(name=name, found=False))


def launch_allowed_app(name: str) -> dict:
    manager = PermissionManager()
    decision = manager.can_launch_allowed_app(name)
    if not decision.allowed:
        return {"ok": False, "error": decision.reason, "app": name}
    info = find_installed_app(name)
    if not info.get("found"):
        return {"ok": False, "error": "allowed app not found", "app": name}
    subprocess.Popen([info["path"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "app": name, "path": info["path"]}


def open_folder(path: str) -> dict:
    manager = PermissionManager()
    decision = manager.can_open_folder(path)
    if not decision.allowed:
        return {"ok": False, "error": decision.reason, "path": path}
    resolved = str(Path(path).resolve())
    os.startfile(resolved)
    return {"ok": True, "path": resolved}
