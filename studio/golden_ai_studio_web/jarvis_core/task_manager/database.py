import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from ..orchestrator.models import DataClassification, PlanStep, Route
from .models import StepRecord, StepStatus, TaskPlan, TaskRecord, TaskStatus


class TaskDatabase:
    SCHEMA_VERSION = 1

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._migrate()
        self.recover_interrupted()

    @contextmanager
    def connect(self, rows=False):
        database = sqlite3.connect(self.path, timeout=10)
        if rows:
            database.row_factory = sqlite3.Row
        try:
            database.execute("PRAGMA journal_mode=WAL")
            database.execute("PRAGMA busy_timeout=10000")
            yield database
            database.commit()
        except Exception:
            database.rollback()
            raise
        finally:
            database.close()

    def _migrate(self):
        with self._lock, self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS task_schema_version(version INTEGER NOT NULL)")
            row = db.execute("SELECT version FROM task_schema_version ORDER BY version DESC LIMIT 1").fetchone()
            if row and int(row[0]) >= self.SCHEMA_VERSION:
                return
            db.execute("""CREATE TABLE IF NOT EXISTS tasks(
                id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                status TEXT NOT NULL, data_classification TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, started_at REAL,
                finished_at REAL, cancel_requested_at REAL, error TEXT NOT NULL,
                result TEXT, metadata TEXT NOT NULL, timeout_seconds REAL NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS task_steps(
                task_id TEXT NOT NULL, step_id TEXT NOT NULL, position INTEGER NOT NULL,
                intent TEXT NOT NULL, route TEXT NOT NULL, tool TEXT, args TEXT NOT NULL,
                dependencies TEXT NOT NULL, cancellable INTEGER NOT NULL,
                background INTEGER NOT NULL, status TEXT NOT NULL, started_at REAL,
                finished_at REAL, error TEXT NOT NULL, result TEXT,
                PRIMARY KEY(task_id, step_id), FOREIGN KEY(task_id) REFERENCES tasks(id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS task_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                timestamp REAL NOT NULL, event TEXT NOT NULL, details TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_steps_task_position ON task_steps(task_id,position)")
            db.execute("DELETE FROM task_schema_version")
            db.execute("INSERT INTO task_schema_version(version) VALUES(?)", (self.SCHEMA_VERSION,))

    def create_task(self, task_id: str, plan: TaskPlan):
        now = time.time()
        with self._lock, self.connect() as db:
            db.execute("""INSERT INTO tasks(id,title,description,status,data_classification,
                created_at,updated_at,error,metadata,timeout_seconds) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (task_id, plan.title, plan.description, TaskStatus.QUEUED.value,
                 plan.data_classification.value, now, now, "", self._dump(plan.metadata),
                 plan.timeout_seconds))
            for position, step in enumerate(plan.steps):
                db.execute("""INSERT INTO task_steps(task_id,step_id,position,intent,route,tool,
                    args,dependencies,cancellable,background,status,error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (task_id, step.id, position, step.intent, step.route.value, step.tool,
                     self._dump(step.args), self._dump(step.dependencies), int(step.cancellable),
                     int(step.background), StepStatus.PENDING.value, ""))
            self._event_db(db, task_id, "task_created", {"steps": len(plan.steps)})

    def get_task(self, task_id):
        with self.connect(rows=True) as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return self._task(row) if row else None

    def list_tasks(self, limit=50, status=None):
        limit = max(1, min(int(limit), 200))
        sql, params = "SELECT * FROM tasks", []
        if status:
            sql += " WHERE status=?"
            params.append(status.value if isinstance(status, TaskStatus) else str(status))
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect(rows=True) as db:
            return [self._task(row) for row in db.execute(sql, params).fetchall()]

    def get_steps(self, task_id):
        with self.connect(rows=True) as db:
            rows = db.execute("SELECT * FROM task_steps WHERE task_id=? ORDER BY position", (task_id,)).fetchall()
            return [self._step(row) for row in rows]

    def update_task(self, task_id, status, **fields):
        allowed = {"started_at", "finished_at", "cancel_requested_at", "error", "result"}
        values = {key: value for key, value in fields.items() if key in allowed}
        values.update({"status": status.value, "updated_at": time.time()})
        if "result" in values:
            values["result"] = self._dump(values["result"])
        self._update("tasks", "id", task_id, values)
        self.add_event(task_id, "task_" + status.value.lower(), {"error": fields.get("error", "")[:300]})

    def update_step(self, task_id, step_id, status, **fields):
        allowed = {"started_at", "finished_at", "error", "result"}
        values = {key: value for key, value in fields.items() if key in allowed}
        values["status"] = status.value
        if "result" in values:
            values["result"] = self._dump(values["result"])
        with self._lock, self.connect() as db:
            columns = ",".join(f"{key}=?" for key in values)
            db.execute(f"UPDATE task_steps SET {columns} WHERE task_id=? AND step_id=?",
                       tuple(values.values()) + (task_id, step_id))
            self._event_db(db, task_id, "step_" + status.value.lower(), {"step_id": step_id})

    def add_event(self, task_id, event, details=None):
        with self._lock, self.connect() as db:
            self._event_db(db, task_id, event, details or {})

    def events(self, task_id, limit=100):
        with self.connect(rows=True) as db:
            rows = db.execute("SELECT * FROM task_events WHERE task_id=? ORDER BY id DESC LIMIT ?",
                              (task_id, max(1, min(int(limit), 500)))).fetchall()
            return [{**dict(row), "details": self._load(row["details"], {})} for row in rows]

    def recover_interrupted(self):
        now = time.time()
        with self._lock, self.connect() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM tasks WHERE status IN (?,?)",
                (TaskStatus.RUNNING.value, TaskStatus.CANCEL_REQUESTED.value)).fetchall()]
            if ids:
                marks = ",".join("?" for _ in ids)
                db.execute(f"UPDATE tasks SET status=?,updated_at=?,error=? WHERE id IN ({marks})",
                           (TaskStatus.INTERRUPTED.value, now, "Processo reiniciado durante execução", *ids))
                db.execute(f"UPDATE task_steps SET status=?,error=? WHERE task_id IN ({marks}) AND status=?",
                           (StepStatus.INTERRUPTED.value, "Processo reiniciado durante execução", *ids,
                            StepStatus.RUNNING.value))
                for task_id in ids:
                    self._event_db(db, task_id, "task_interrupted", {"reason": "process_restart"})
        return ids

    def _update(self, table, key, identity, values):
        with self._lock, self.connect() as db:
            columns = ",".join(f"{name}=?" for name in values)
            db.execute(f"UPDATE {table} SET {columns} WHERE {key}=?", tuple(values.values()) + (identity,))

    def _event_db(self, db, task_id, event, details):
        db.execute("INSERT INTO task_events(task_id,timestamp,event,details) VALUES(?,?,?,?)",
                   (task_id, time.time(), event, self._dump(details)))

    @staticmethod
    def _dump(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _load(value, default=None):
        try:
            return json.loads(value) if value is not None else default
        except (TypeError, json.JSONDecodeError):
            return default

    def _task(self, row):
        return TaskRecord(row["id"], row["title"], row["description"], TaskStatus(row["status"]),
            DataClassification(row["data_classification"]), row["created_at"], row["updated_at"],
            row["started_at"], row["finished_at"], row["cancel_requested_at"], row["error"],
            self._load(row["result"]), self._load(row["metadata"], {}), row["timeout_seconds"])

    def _step(self, row):
        step = PlanStep(row["step_id"], row["intent"], Route(row["route"]), row["tool"],
            self._load(row["args"], {}), tuple(self._load(row["dependencies"], [])),
            row["status"], bool(row["cancellable"]), bool(row["background"]))
        return StepRecord(row["task_id"], step, row["position"], StepStatus(row["status"]),
            row["started_at"], row["finished_at"], row["error"], self._load(row["result"]))
