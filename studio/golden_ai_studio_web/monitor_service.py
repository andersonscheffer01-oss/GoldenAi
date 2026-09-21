"""Monitor persistente do Radar do Golden AI.

O servico guarda estados e eventos no SQLite e nao envia ordens. A interface
apenas consulta o estado atual e os eventos novos.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(__file__).with_name("golden_runtime.db")


class MonitorService:
    def __init__(self, db_path=DB_PATH, interval_seconds=60):
        self.db_path = str(db_path)
        self.interval_seconds = max(15, int(interval_seconds))
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._busy = False
        self._last_run = None
        self._last_error = None
        self._init_db()

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS monitor_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    assets INTEGER DEFAULT 0,
                    opportunities INTEGER DEFAULT 0,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS signal_states (
                    signal_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    strategy_id TEXT,
                    strategy_name TEXT,
                    direction TEXT,
                    status TEXT NOT NULL,
                    score REAL DEFAULT 0,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    previous_status TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_signal_events_created ON signal_events(created_at DESC);
            """)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="golden-radar-monitor", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        self._wake.set()
        return True

    def is_running(self):
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def _loop(self):
        self.scan_once()
        while not self._stop.is_set():
            self._wake.wait(self.interval_seconds)
            self._wake.clear()
            if not self._stop.is_set():
                self.scan_once()

    def scan_once(self):
        if self._busy:
            return {"ok": False, "error": "varredura ja em andamento"}
        self._busy = True
        started = self._now()
        run_id = None
        try:
            with self._connect() as db:
                cursor = db.execute("INSERT INTO monitor_runs(started_at) VALUES (?)", (started,))
                run_id = cursor.lastrowid
            from meta_strategy import analyze_radar
            result = analyze_radar(limit=22)
            items = result.get("items", [])
            opportunities = 0
            for item in items:
                if not item.get("ok"):
                    continue
                if item.get("best_opportunity"):
                    opportunities += 1
                self._record_item(item)
            finished = self._now()
            with self._connect() as db:
                db.execute("UPDATE monitor_runs SET finished_at=?, assets=?, opportunities=? WHERE id=?",
                           (finished, len(items), opportunities, run_id))
            self._last_run = finished
            self._last_error = None
            return {"ok": True, "assets": len(items), "opportunities": opportunities, "finished_at": finished}
        except Exception as exc:
            self._last_error = str(exc)
            if run_id:
                with self._connect() as db:
                    db.execute("UPDATE monitor_runs SET finished_at=?, error=? WHERE id=?", (self._now(), str(exc), run_id))
            return {"ok": False, "error": str(exc)}
        finally:
            self._busy = False

    def _record_item(self, item):
        symbol = item.get("symbol", "")
        setup = item.get("best_opportunity") or item.get("top_candidate")
        if not setup:
            return
        strategy_id = setup.get("setup_id", "")
        direction = setup.get("direction", "")
        signal_id = "%s|%s|%s" % (symbol, strategy_id, direction)
        now = self._now()
        payload = json.dumps({"symbol": symbol, "regime": item.get("regime", {}), "setup": setup,
                              "risk": item.get("risk", {}), "market_snapshot": item.get("market_snapshot", {})},
                             ensure_ascii=False)
        with self._connect() as db:
            old = db.execute("SELECT status FROM signal_states WHERE signal_id=?", (signal_id,)).fetchone()
            previous = old["status"] if old else None
            status = setup.get("status", "MONITORAR")
            if not old or previous != status:
                event_type = "DETECTED" if not old else "STATUS_CHANGED"
                db.execute("INSERT INTO signal_events(signal_id,event_type,previous_status,status,created_at,payload) VALUES (?,?,?,?,?,?)",
                           (signal_id, event_type, previous, status, now, payload))
            db.execute("""INSERT INTO signal_states(signal_id,symbol,strategy_id,strategy_name,direction,status,score,first_seen,last_seen,payload)
                         VALUES (?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(signal_id) DO UPDATE SET status=excluded.status, score=excluded.score,
                         last_seen=excluded.last_seen, payload=excluded.payload""",
                       (signal_id, symbol, strategy_id, setup.get("name", ""), direction, status,
                        float(setup.get("final_score", 0) or 0), now, now, payload))

    def status(self):
        with self._connect() as db:
            run = db.execute("SELECT * FROM monitor_runs ORDER BY id DESC LIMIT 1").fetchone()
            states = db.execute("SELECT status, COUNT(*) AS total FROM signal_states GROUP BY status").fetchall()
            current = db.execute("SELECT payload FROM signal_states ORDER BY score DESC LIMIT 200").fetchall()
        item_by_symbol = {}
        for row in current:
            try:
                payload = json.loads(row["payload"])
                setup = payload.get("setup") or {}
                item = {"ok": True, "symbol": payload.get("symbol", ""), "regime": payload.get("regime", {}),
                              "risk": payload.get("risk", {}), "market_snapshot": payload.get("market_snapshot", {}),
                              "best_opportunity": setup if setup.get("status") != "BLOQUEADO" else None,
                              "top_candidate": setup}
                symbol = item["symbol"]
                old = item_by_symbol.get(symbol)
                priority = {"OPORTUNIDADE": 0, "PRE_ENTRADA": 1, "MONITORAR": 2, "BLOQUEADO": 3}
                if old is None or (priority.get(setup.get("status", "BLOQUEADO"), 9), -float(setup.get("final_score", 0) or 0)) < old["_sort"]:
                    item_by_symbol[symbol] = {**item, "_sort": (priority.get(setup.get("status", "BLOQUEADO"), 9), -float(setup.get("final_score", 0) or 0))}
            except (TypeError, ValueError):
                continue
        items = [{k: v for k, v in item.items() if k != "_sort"} for item in item_by_symbol.values()]
        return {"ok": True, "running": self.is_running(), "busy": self._busy,
                "interval_seconds": self.interval_seconds, "last_run": dict(run) if run else None,
                "last_error": self._last_error, "signal_counts": {r["status"]: r["total"] for r in states},
                "items": items}

    def history(self, limit=50):
        limit = max(1, min(200, int(limit)))
        with self._connect() as db:
            rows = db.execute("SELECT * FROM signal_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return {"ok": True, "events": [dict(row) for row in rows]}


_service = None


def get_monitor_service():
    global _service
    if _service is None:
        _service = MonitorService()
    return _service
