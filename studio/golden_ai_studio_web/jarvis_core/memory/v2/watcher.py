"""M1.6 — Vault file watcher (polling-based, zero external deps).

Detecta alterações externas no Vault Markdown:
- Arquivo criado/modificado/removido
- Debounce para múltiplos eventos do editor
- Self-write loop protection (origem Jarvis ignorada)

Observação: Usa polling (não watchdog) para evitar dependência externa.
Thread-safe. Leve: apenas stat() + hash comparação.
"""
import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .vault import MANAGED_BY, SyncStatus, parse_frontmatter, projection_hash


class FileEvent(str, Enum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass
class VaultFileEvent:
    event: FileEvent
    path: Path
    old_path: Optional[Path] = None
    timestamp: float = 0.0
    note_id: Optional[str] = None
    managed: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


class SelfWriteToken:
    """Thread-local token para marcar escritas Jarvis.

    Quando o engine projeta uma nota, ele registra o path neste token.
    O watcher ignora eventos para paths registrados.
    """

    def __init__(self):
        self._local = threading.local()

    def _get_set(self) -> Set[str]:
        if not hasattr(self._local, "paths"):
            self._local.paths = set()
        return self._local.paths

    def mark(self, path: Path) -> None:
        self._get_set().add(str(Path(path).resolve()))

    def is_self_write(self, path: Path) -> bool:
        resolved = str(Path(path).resolve())
        paths = self._get_set()
        if resolved in paths:
            paths.discard(resolved)
            return True
        return False

    def clear(self) -> None:
        self._get_set().clear()


class VaultWatcher:
    """Polling-based file watcher para o Vault Markdown.

    Uso:
        watcher = VaultWatcher(vault_root, on_event=my_handler)
        watcher.start()
        ...
        watcher.stop()
    """

    def __init__(self, vault_root: Path,
                 on_event: Callable[[VaultFileEvent], None],
                 poll_interval: float = 2.0,
                 debounce_ms: float = 500.0,
                 self_write_token: Optional[SelfWriteToken] = None):
        self.vault_root = Path(vault_root)
        self.on_event = on_event
        self.poll_interval = max(0.5, float(poll_interval))
        self.debounce_ms = max(100.0, float(debounce_ms))
        self.self_write = self_write_token or SelfWriteToken()
        self._snapshots: Dict[str, _FileSnapshot] = {}
        self._debounce_timers: Dict[str, threading.Timer] = {}
        self._pending_events: Dict[str, VaultFileEvent] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._take_snapshot()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True,
            name="vault-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.poll_interval * 2)
        self._thread = None
        with self._lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()
            self._pending_events.clear()

    @property
    def is_running(self) -> bool:
        return self._running

    def _take_snapshot(self) -> None:
        snap: Dict[str, _FileSnapshot] = {}
        if not self.vault_root.exists():
            self._snapshots = snap
            return
        for path in self.vault_root.rglob("*.md"):
            try:
                resolved = str(path.resolve())
                stat = path.stat()
                snap[resolved] = _FileSnapshot(
                    path=path,
                    mtime=stat.st_mtime,
                    size=stat.st_size,
                )
            except (OSError, PermissionError):
                continue
        self._snapshots = snap

    def _poll_loop(self) -> None:
        while self._running:
            try:
                self._detect_changes()
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def detectChanges(self) -> List[VaultFileEvent]:
        """Detecta mudanças desde a última snapshot. Retorna eventos."""
        current: Dict[str, _FileSnapshot] = {}
        if self.vault_root.exists():
            for path in self.vault_root.rglob("*.md"):
                try:
                    resolved = str(path.resolve())
                    stat = path.stat()
                    current[resolved] = _FileSnapshot(
                        path=path,
                        mtime=stat.st_mtime,
                        size=stat.st_size,
                    )
                except (OSError, PermissionError):
                    continue

        events: List[VaultFileEvent] = []
        old_keys = set(self._snapshots.keys())
        new_keys = set(current.keys())

        for created_path in new_keys - old_keys:
            snap = current[created_path]
            event = self._make_event(FileEvent.CREATED, snap.path)
            if event:
                events.append(event)

        for deleted_path in old_keys - new_keys:
            snap = self._snapshots[deleted_path]
            event = self._make_event(FileEvent.DELETED, snap.path)
            if event:
                events.append(event)

        for common in old_keys & new_keys:
            old_snap = self._snapshots[common]
            new_snap = current[common]
            if (new_snap.mtime != old_snap.mtime
                    or new_snap.size != old_snap.size):
                event = self._make_event(FileEvent.MODIFIED, new_snap.path)
                if event:
                    events.append(event)

        self._snapshots = current

        for event in events:
            self._debounce_and_dispatch(event)

        return events

    def _make_event(self, event_type: FileEvent,
                    path: Path) -> Optional[VaultFileEvent]:
        if self.self_write.is_self_write(path):
            return None
        managed = False
        note_id = None
        try:
            text = path.read_text(encoding="utf-8")
            front = parse_frontmatter(text)
            managed = front.get("managed_by") == MANAGED_BY
            note_id = str(front.get("id", "")) or None
        except Exception:
            pass
        return VaultFileEvent(
            event=event_type,
            path=path,
            timestamp=time.time(),
            note_id=note_id,
            managed=managed,
        )

    def _debounce_and_dispatch(self, event: VaultFileEvent) -> None:
        key = str(event.path.resolve())
        with self._lock:
            existing = self._debounce_timers.get(key)
            if existing:
                existing.cancel()
            self._pending_events[key] = event
            timer = threading.Timer(
                self.debounce_ms / 1000.0,
                self._fire_event,
                args=(key,))
            self._debounce_timers[key] = timer
            timer.start()

    def _fire_event(self, key: str) -> None:
        with self._lock:
            event = self._pending_events.pop(key, None)
            self._debounce_timers.pop(key, None)
        if event:
            try:
                self.on_event(event)
            except Exception:
                pass


@dataclass
class _FileSnapshot:
    path: Path
    mtime: float
    size: int
