import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from ..orchestrator.models import DataClassification, PlanStep, Route
from .background import (BackgroundTask, BackgroundTaskStatus, MisfirePolicy,
                          RunStatus, TriggerType)
from .models import StepRecord, StepStatus, TaskPlan, TaskRecord, TaskStatus


class TaskDatabase:
    SCHEMA_VERSION = 3

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
            current = int(row[0]) if row else 0
            if current < 2:
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS background_tasks(
                        task_id TEXT PRIMARY KEY,
                        user_request TEXT NOT NULL,
                        task_type TEXT NOT NULL,
                        trigger_type TEXT NOT NULL,
                        trigger_config TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        next_run_at REAL,
                        last_run_at REAL,
                        timezone TEXT NOT NULL,
                        enabled INTEGER NOT NULL,
                        run_count INTEGER NOT NULL,
                        max_runs INTEGER,
                        misfire_policy TEXT NOT NULL,
                        security_scope TEXT NOT NULL,
                        paused_from_status TEXT,
                        schema_version INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS task_runs(
                        run_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        scheduled_for REAL NOT NULL,
                        status TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        started_at REAL,
                        finished_at REAL,
                        mission_id TEXT,
                        claim_token TEXT,
                        claimed_by TEXT,
                        claim_expires_at REAL,
                        error_code TEXT,
                        error_message TEXT,
                        UNIQUE(task_id, scheduled_for),
                        FOREIGN KEY(task_id) REFERENCES background_tasks(task_id)
                    );
                    CREATE TABLE IF NOT EXISTS task_approvals(
                        approval_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        mission_id TEXT,
                        scope TEXT NOT NULL,
                        target TEXT NOT NULL,
                        granted_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        single_use INTEGER NOT NULL,
                        consumed_at REAL,
                        status TEXT NOT NULL,
                        FOREIGN KEY(task_id) REFERENCES background_tasks(task_id),
                        FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_background_due
                        ON background_tasks(enabled, status, next_run_at);
                    CREATE INDEX IF NOT EXISTS idx_runs_claim
                        ON task_runs(status, claim_expires_at);
                    CREATE INDEX IF NOT EXISTS idx_approvals_scope
                        ON task_approvals(task_id, run_id, status);
                """)
            if current < 3:
                columns = {item[1] for item in db.execute(
                    "PRAGMA table_info(background_tasks)").fetchall()}
                if "paused_from_status" not in columns:
                    db.execute("ALTER TABLE background_tasks ADD COLUMN paused_from_status TEXT")
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

    # Persistent background-task store. All scheduler claims happen inside
    # BEGIN IMMEDIATE transactions so two service processes cannot own a run.
    def create_background_task(self, task: BackgroundTask):
        with self._lock, self.connect() as db:
            db.execute("""INSERT INTO background_tasks(
                task_id,user_request,task_type,trigger_type,trigger_config,status,
                created_at,updated_at,next_run_at,last_run_at,timezone,enabled,
                run_count,max_runs,misfire_policy,security_scope,paused_from_status,schema_version)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task.task_id, task.user_request, task.task_type, task.trigger_type.value,
                 self._dump(task.trigger_config), task.status.value, task.created_at,
                 task.updated_at, task.next_run_at, task.last_run_at, task.timezone,
                 int(task.enabled), task.run_count, task.max_runs, task.misfire_policy.value,
                 self._dump(task.security_scope),
                 getattr(task.paused_from_status, "value", task.paused_from_status),
                 task.schema_version))
        return task.task_id

    def get_background_task(self, task_id):
        with self.connect(rows=True) as db:
            row = db.execute("SELECT * FROM background_tasks WHERE task_id=?", (task_id,)).fetchone()
            return self._background_task(row) if row else None

    def list_background_tasks(self, limit=200, enabled=None):
        sql, params = "SELECT * FROM background_tasks", []
        if enabled is not None:
            sql += " WHERE enabled=?"
            params.append(int(bool(enabled)))
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self.connect(rows=True) as db:
            return [self._background_task(row) for row in db.execute(sql, params).fetchall()]

    def update_background_task(self, task_id, **fields):
        allowed = {"status", "updated_at", "next_run_at", "last_run_at", "enabled",
                   "run_count", "max_runs", "trigger_config", "security_scope",
                   "paused_from_status"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if "status" in values:
            values["status"] = getattr(values["status"], "value", values["status"])
        for key in ("trigger_config", "security_scope"):
            if key in values:
                values[key] = self._dump(values[key])
        if "paused_from_status" in values:
            values["paused_from_status"] = getattr(
                values["paused_from_status"], "value", values["paused_from_status"])
        values.setdefault("updated_at", time.time())
        if "enabled" in values:
            values["enabled"] = int(bool(values["enabled"]))
        with self._lock, self.connect() as db:
            columns = ",".join(f"{key}=?" for key in values)
            db.execute(f"UPDATE background_tasks SET {columns} WHERE task_id=?",
                       tuple(values.values()) + (task_id,))

    def ensure_task_run(self, task_id, scheduled_for, now=None):
        now = time.time() if now is None else float(now)
        run_id = str(uuid.uuid4())
        with self._lock, self.connect(rows=True) as db:
            task = db.execute("SELECT status,enabled FROM background_tasks WHERE task_id=?",
                              (task_id,)).fetchone()
            if not task or task["status"] in {
                    BackgroundTaskStatus.PAUSED.value,
                    BackgroundTaskStatus.CANCELLED.value}:
                return None
            db.execute("""INSERT OR IGNORE INTO task_runs(
                run_id,task_id,scheduled_for,status,created_at)
                VALUES(?,?,?,?,?)""", (run_id, task_id, float(scheduled_for),
                                        RunStatus.PENDING.value, now))
            row = db.execute("SELECT * FROM task_runs WHERE task_id=? AND scheduled_for=?",
                             (task_id, float(scheduled_for))).fetchone()
            return dict(row)

    def control_background_task(self, task_id, action):
        """Apply one atomic task-level control transition."""
        action = str(action).lower()
        event_names = {"pause": "BACKGROUND_TASK_PAUSED",
                       "resume": "BACKGROUND_TASK_RESUMED",
                       "cancel": "BACKGROUND_TASK_CANCELLED"}
        if action not in event_names:
            return {"success": False, "code": "UNKNOWN_CONTROL_ACTION",
                    "task_id": str(task_id), "requested_action": action}
        with self._lock, self.connect(rows=True) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM background_tasks WHERE task_id=?",
                             (str(task_id),)).fetchone()
            if not row:
                return {"success": False, "code": "TASK_NOT_FOUND",
                        "task_id": str(task_id), "requested_action": action}
            task = dict(row)
            previous = task["status"]
            terminal = {BackgroundTaskStatus.COMPLETED.value,
                        BackgroundTaskStatus.EXPIRED.value,
                        BackgroundTaskStatus.FAILED.value,
                        BackgroundTaskStatus.DISABLED.value}
            if action == "pause":
                if previous == BackgroundTaskStatus.PAUSED.value:
                    code, success, new_status = "ALREADY_PAUSED", True, previous
                elif previous in terminal or previous == BackgroundTaskStatus.CANCELLED.value:
                    code, success, new_status = "INVALID_STATE_TRANSITION", False, previous
                else:
                    code, success, new_status = "PAUSED", True, BackgroundTaskStatus.PAUSED.value
                    db.execute("""UPDATE background_tasks SET status=?,enabled=0,
                        paused_from_status=?,updated_at=? WHERE task_id=?""",
                               (new_status, previous, time.time(), str(task_id)))
            elif action == "resume":
                if previous != BackgroundTaskStatus.PAUSED.value:
                    code = ("INVALID_STATE_TRANSITION" if previous in terminal
                            or previous == BackgroundTaskStatus.CANCELLED.value
                            else "NOT_PAUSED")
                    success, new_status = False, previous
                else:
                    restored = task.get("paused_from_status") or BackgroundTaskStatus.SCHEDULED.value
                    if restored in {BackgroundTaskStatus.PAUSED.value,
                                    BackgroundTaskStatus.CANCELLED.value}:
                        restored = BackgroundTaskStatus.SCHEDULED.value
                    code, success, new_status = "RESUMED", True, restored
                    db.execute("""UPDATE background_tasks SET status=?,enabled=1,
                        paused_from_status=NULL,updated_at=? WHERE task_id=?""",
                               (new_status, time.time(), str(task_id)))
            else:
                if previous == BackgroundTaskStatus.CANCELLED.value:
                    code, success, new_status = "ALREADY_CANCELLED", True, previous
                elif previous in terminal:
                    code, success, new_status = "INVALID_STATE_TRANSITION", False, previous
                else:
                    code, success, new_status = "CANCELLED", True, BackgroundTaskStatus.CANCELLED.value
                    db.execute("""UPDATE background_tasks SET status=?,enabled=0,
                        paused_from_status=NULL,updated_at=? WHERE task_id=?""",
                               (new_status, time.time(), str(task_id)))
            latest = db.execute("""SELECT run_id,status FROM task_runs
                WHERE task_id=? ORDER BY COALESCE(started_at,created_at) DESC LIMIT 1""",
                                (str(task_id),)).fetchone()
            active_run_state = dict(latest) if latest else None
            if success and new_status != previous:
                self._event_db(db, str(task_id), event_names[action], {
                    "action": action, "previous_status": previous,
                    "new_status": new_status})
            return {"success": success, "code": code, "task_id": str(task_id),
                    "requested_action": action, "previous_state": previous,
                    "new_state": new_status, "active_run_state": active_run_state}

    def get_task_run(self, run_id):
        with self.connect(rows=True) as db:
            row = db.execute("SELECT * FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def list_task_runs(self, task_id, limit=100):
        with self.connect(rows=True) as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM task_runs WHERE task_id=? ORDER BY scheduled_for DESC LIMIT ?",
                (task_id, max(1, min(int(limit), 500)))).fetchall()]

    def list_all_task_runs(self, limit=5000):
        """Read background run history in one query for observability consumers."""
        with self.connect(rows=True) as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM task_runs "
                "ORDER BY COALESCE(started_at, created_at) DESC, run_id DESC LIMIT ?",
                (max(1, min(int(limit), 5000)),)).fetchall()]

    def claim_task_run(self, run_id, worker_id, now, lease_seconds=30.0,
                       allow_waiting_user_idle=False):
        token = str(uuid.uuid4())
        now = float(now)
        with self._lock, self.connect(rows=True) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                return None
            row = dict(row)
            task = db.execute("SELECT status,enabled FROM background_tasks WHERE task_id=?",
                              (row["task_id"],)).fetchone()
            if not task or not bool(task["enabled"]) or task["status"] in {
                    BackgroundTaskStatus.PAUSED.value,
                    BackgroundTaskStatus.CANCELLED.value,
                    BackgroundTaskStatus.DISABLED.value,
                    BackgroundTaskStatus.COMPLETED.value,
                    BackgroundTaskStatus.EXPIRED.value,
                    BackgroundTaskStatus.FAILED.value,
                    BackgroundTaskStatus.WAITING_CONFIRMATION.value}:
                return None
            terminal_statuses = {RunStatus.COMPLETED.value, RunStatus.CANCELLED.value,
                                 RunStatus.WAITING_CONFIRMATION.value}
            if not allow_waiting_user_idle:
                terminal_statuses.add(RunStatus.WAITING_USER_IDLE.value)
            if row["status"] in terminal_statuses:
                return None
            if row["mission_id"] and row["status"] in {RunStatus.CLAIMED.value,
                                                         RunStatus.RUNNING.value}:
                # A durable mission may be resumed by its existing owner; never
                # create a second mission merely because its scheduler lease expired.
                return None
            active_claim = (row["claim_token"] and row["claim_expires_at"]
                            and float(row["claim_expires_at"]) > now
                            and row["claimed_by"] != worker_id)
            if active_claim:
                return None
            db.execute("""UPDATE task_runs SET status=?,claim_token=?,claimed_by=?,
                claim_expires_at=? WHERE run_id=?""",
                       (RunStatus.CLAIMED.value, token, worker_id,
                        now + float(lease_seconds), run_id))
            result = db.execute("SELECT * FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
            return dict(result)

    def update_task_run(self, run_id, **fields):
        allowed = {"status", "started_at", "finished_at", "mission_id", "claim_token",
                    "claimed_by", "claim_expires_at", "error_code", "error_message"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if "status" in values:
            values["status"] = getattr(values["status"], "value", values["status"])
        if not values:
            return
        with self._lock, self.connect() as db:
            columns = ",".join(f"{key}=?" for key in values)
            db.execute(f"UPDATE task_runs SET {columns} WHERE run_id=?",
                       tuple(values.values()) + (run_id,))

    def recover_background_runs(self, now, lease_timeout=0.0):
        """Release stale claims without duplicating durable mission states."""
        cutoff = float(now) - float(lease_timeout)
        with self._lock, self.connect() as db:
            cursor = db.execute("""UPDATE task_runs SET status=?,claim_token=NULL,
                claimed_by=NULL,claim_expires_at=NULL,error_code=?,error_message=?
                WHERE status IN (?,?) AND (claim_expires_at IS NULL OR claim_expires_at<?)
                AND mission_id IS NULL""", (RunStatus.PENDING.value, "STALE_CLAIM",
                    "claim recovered after restart", RunStatus.CLAIMED.value,
                    RunStatus.RUNNING.value, cutoff))
            return cursor.rowcount

    def create_task_approval(self, task_id, run_id, scope, target, granted_at,
                             expires_at, mission_id=None, single_use=True):
        approval_id = str(uuid.uuid4())
        with self._lock, self.connect() as db:
            db.execute("""INSERT INTO task_approvals(
                approval_id,task_id,run_id,mission_id,scope,target,granted_at,
                expires_at,single_use,status) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (approval_id, task_id, run_id, mission_id, scope, target,
                 float(granted_at), float(expires_at), int(bool(single_use)), "ACTIVE"))
        return approval_id

    def list_task_approvals(self, task_id=None, run_id=None, status=None, limit=1000):
        """Return approvals without consuming or otherwise changing them."""
        sql, params = "SELECT * FROM task_approvals", []
        clauses = []
        if task_id is not None:
            clauses.append("task_id=?")
            params.append(str(task_id))
        if run_id is not None:
            clauses.append("run_id=?")
            params.append(str(run_id))
        if status is not None:
            clauses.append("status=?")
            params.append(str(status))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY granted_at DESC, approval_id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 5000)))
        with self.connect(rows=True) as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def consume_task_approval(self, approval_id, task_id, run_id, scope, target, now):
        with self._lock, self.connect(rows=True) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM task_approvals WHERE approval_id=?",
                             (approval_id,)).fetchone()
            if not row or row["task_id"] != task_id or row["run_id"] != run_id:
                return False
            if row["status"] != "ACTIVE" or float(row["expires_at"]) < float(now):
                return False
            if row["scope"] != scope or row["target"] != target:
                return False
            if row["single_use"] and row["consumed_at"] is not None:
                return False
            if row["single_use"]:
                db.execute("UPDATE task_approvals SET consumed_at=?,status='CONSUMED' WHERE approval_id=?",
                           (float(now), approval_id))
            return True

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

    def _background_task(self, row):
        return BackgroundTask(
            task_id=row["task_id"], user_request=row["user_request"], task_type=row["task_type"],
            trigger_type=TriggerType(row["trigger_type"]),
            trigger_config=self._load(row["trigger_config"], {}),
            status=BackgroundTaskStatus(row["status"]), created_at=row["created_at"],
            updated_at=row["updated_at"], next_run_at=row["next_run_at"],
            last_run_at=row["last_run_at"], timezone=row["timezone"],
            enabled=bool(row["enabled"]), run_count=row["run_count"],
            max_runs=row["max_runs"], misfire_policy=MisfirePolicy(row["misfire_policy"]),
            security_scope=self._load(row["security_scope"], {}),
            paused_from_status=(BackgroundTaskStatus(row["paused_from_status"])
                                if row["paused_from_status"] else None),
            schema_version=row["schema_version"])
