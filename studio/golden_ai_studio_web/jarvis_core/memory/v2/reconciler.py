"""M1.6 — Vault reconciliation coordinator.

Coordena FileWatcher + VaultImporter + GoldenMemoryEngine:
- Recebe eventos do watcher
- Debounce + classificação
- Importa via importer
- Mantém estado de reconciliação
- Expõe API para status e ações manuais
"""
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .importer import ImportDecision, ImportResult, VaultImporter
from .vault import SyncStatus, default_vault_root
from .watcher import SelfWriteToken, VaultFileEvent, VaultWatcher


class ReconciliationState:
    """Estado global de reconciliação do Vault."""

    def __init__(self):
        self._lock = threading.Lock()
        self._history: List[Dict[str, Any]] = []
        self._stats = {
            "total_events": 0,
            "accepted": 0,
            "drift": 0,
            "conflict": 0,
            "rejected": 0,
            "error": 0,
            "ignored": 0,
        }
        self._last_event_time: float = 0.0

    def record(self, result: ImportResult, event: Optional[VaultFileEvent] = None,
               detail: str = "") -> None:
        with self._lock:
            self._stats["total_events"] += 1
            self._stats[result.decision.value] = (
                self._stats.get(result.decision.value, 0) + 1)
            self._last_event_time = time.time()
            entry = {
                "time": self._last_event_time,
                "decision": result.decision.value,
                "memory_id": result.memory_id,
                "note_id": result.note_id,
                "detail": result.detail or detail,
            }
            if event:
                entry["path"] = str(event.path)
                entry["event_type"] = event.event.value
            self._history.append(entry)
            if len(self._history) > 200:
                self._history = self._history[-200:]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history[-limit:])

    @property
    def last_event_time(self) -> float:
        return self._last_event_time


class VaultReconciler:
    """Coordena watcher + importer + engine para reconciliação bidirecional.

    Uso:
        reconciler = VaultReconciler(engine)
        reconciler.start()
        ...
        reconciler.stop()

        # Status
        status = reconciler.status()

        # Import manual
        result = reconciler.import_file(path)

        # Resolver conflito (futuro)
        result = reconciler.resolve_conflict(memory_id, strategy="accept-external")
    """

    def __init__(self, engine: Any,
                 vault_root: Optional[Path] = None,
                 poll_interval: float = 2.0,
                 debounce_ms: float = 500.0,
                 auto_import: bool = True):
        self.engine = engine
        self.vault_root = Path(vault_root or default_vault_root())
        self.auto_import = auto_import
        self.self_write = SelfWriteToken()
        self.state = ReconciliationState()
        self._importer = VaultImporter(engine, self.vault_root)
        self._watcher = VaultWatcher(
            vault_root=self.vault_root,
            on_event=self._on_file_event,
            poll_interval=poll_interval,
            debounce_ms=debounce_ms,
            self_write_token=self.self_write,
        )
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._watcher.start()

    def stop(self) -> None:
        self._running = False
        self._watcher.stop()

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> Dict[str, Any]:
        """Status completo de reconciliação."""
        try:
            classifications = self._importer.classify_all()
        except Exception:
            classifications = []
        summary = {"synced": 0, "drift": 0, "conflict": 0,
                    "pending": 0, "error": 0, "ignored": 0}
        for c in classifications:
            s = c.get("sync_status", "error")
            summary[s] = summary.get(s, 0) + 1
        return {
            "running": self._running,
            "vault_root": str(self.vault_root),
            "stats": self.state.stats(),
            "summary": summary,
            "classifications": classifications,
            "history": self.state.history(limit=20),
        }

    def import_file(self, path: Path) -> ImportResult:
        """Importa um arquivo externo manualmente."""
        result = self._importer.import_file(path)
        self.state.record(result, detail="manual-import")
        return result

    def import_text(self, text: str) -> ImportResult:
        """Importa texto Markdown manualmente."""
        result = self._importer.import_text(text)
        self.state.record(result, detail="manual-import-text")
        return result

    def resolve_conflict(self, memory_id: int,
                         strategy: str = "accept-canonical") -> ImportResult:
        """Resolve um conflito de sincronização.

        Estratégias:
        - accept-canonical: mantém SQLite, reprojeta vault
        - accept-external: importa Markdown, sobrescreve SQLite
        - keep-both: cria versão separada (futuro)
        """
        if strategy == "accept-canonical":
            try:
                record = self.engine.store.load(memory_id)
                if record:
                    self.engine._project_best_effort(record)
                    return ImportResult(
                        decision=ImportDecision.ACCEPTED,
                        memory_id=memory_id,
                        detail="conflict-resolved-canonical")
            except Exception as exc:
                return ImportResult(
                    decision=ImportDecision.ERROR,
                    memory_id=memory_id,
                    detail="resolve-failed: %s" % type(exc).__name__)
        elif strategy == "accept-external":
            note_id = "mem_%d" % memory_id
            path = self._importer._find_path_for_note(note_id)
            if path:
                return self._importer.import_file(path)
            return ImportResult(
                decision=ImportDecision.ERROR,
                memory_id=memory_id,
                detail="external-file-not-found")
        return ImportResult(
            decision=ImportDecision.ERROR,
            memory_id=memory_id,
            detail="unknown-strategy: %s" % strategy)

    def _on_file_event(self, event: VaultFileEvent) -> None:
        """Handler para eventos do watcher."""
        if not self.auto_import:
            self.state.record(
                ImportResult(ImportDecision.IGNORED, detail="auto-import-disabled"),
                event=event)
            return
        if not event.managed:
            self.state.record(
                ImportResult(ImportDecision.IGNORED, detail="not-managed"),
                event=event)
            return
        if event.event.value == "deleted":
            self.state.record(
                ImportResult(ImportDecision.IGNORED, detail="delete-not-imported"),
                event=event)
            return
        if event.event.value in ("created", "modified"):
            self.self_write.mark(event.path)
            result = self._importer.import_file(event.path)
            self.state.record(result, event=event)

    def rebuild_vault(self) -> Dict[str, Any]:
        """Rebuild completo do Vault a partir do SQLite."""
        try:
            report = self.engine.rebuild_vault()
            return {"ok": True, "report": report}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}
