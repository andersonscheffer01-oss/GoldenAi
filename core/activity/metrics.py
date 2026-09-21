from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .repository import ActivityRepository
from .tokens import token_usage_status


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def day_key(value: str) -> str:
    parsed = parse_iso(value)
    if not parsed:
        return ""
    return parsed.date().isoformat()


def streaks(days: set[str], today: date | None = None) -> tuple[int, int]:
    if not days:
        return 0, 0
    parsed_days = sorted(date.fromisoformat(day) for day in days)
    longest = 1
    current_run = 1
    for previous, current in zip(parsed_days, parsed_days[1:]):
        if current == previous + timedelta(days=1):
            current_run += 1
        else:
            longest = max(longest, current_run)
            current_run = 1
    longest = max(longest, current_run)

    cursor = today or datetime.now().date()
    current = 0
    while cursor.isoformat() in days:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def intensity(total: int) -> int:
    if total <= 0:
        return 0
    if total <= 2:
        return 1
    if total <= 6:
        return 2
    if total <= 14:
        return 3
    return 4


class ActivityMetrics:
    def __init__(self, repository: ActivityRepository):
        self.repo = repository

    def summary(self) -> dict:
        chats = self.repo.fetchone("SELECT COUNT(DISTINCT conversation_id) AS n FROM activity_events WHERE conversation_id <> ''")
        messages = self.repo.fetchall("SELECT actor, COUNT(*) AS n FROM activity_events WHERE event_type = 'message' GROUP BY actor")
        sessions = self.repo.fetchone("SELECT COUNT(*) AS n FROM chat_sessions")
        days = {
            day_key(row["timestamp"])
            for row in self.repo.fetchall("SELECT DISTINCT timestamp FROM activity_events")
            if day_key(row["timestamp"])
        }
        by_actor = {row["actor"]: row["n"] for row in messages}
        current, longest = streaks(days)
        return {
            "total_chats": chats["n"] if chats else 0,
            "total_messages": sum(by_actor.values()),
            "user_messages": by_actor.get("user", 0),
            "assistant_messages": by_actor.get("assistant", 0),
            "total_sessions": sessions["n"] if sessions else 0,
            "active_days": len(days),
            "current_streak_days": current,
            "longest_streak_days": longest,
        }

    def heatmap(self, days_back: int = 180) -> list[dict]:
        rows = self.repo.fetchall(
            """
            SELECT substr(timestamp, 1, 10) AS day,
                   SUM(CASE WHEN event_type = 'message' THEN 1 ELSE 0 END) AS messages,
                   SUM(CASE WHEN event_type = 'tool' THEN 1 ELSE 0 END) AS tools,
                   COUNT(DISTINCT CASE
                     WHEN lower(project_path) LIKE 'c:\\goldenai\\projetos%' THEN project_path
                     ELSE NULL
                   END) AS projects
            FROM activity_events
            WHERE timestamp >= ?
            GROUP BY substr(timestamp, 1, 10)
            """,
            ((datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat(),),
        )
        by_day = {row["day"]: row for row in rows}
        start = datetime.now().date() - timedelta(days=days_back - 1)
        result = []
        for offset in range(days_back):
            day = (start + timedelta(days=offset)).isoformat()
            row = by_day.get(day)
            messages = int(row["messages"] or 0) if row else 0
            tools = int(row["tools"] or 0) if row else 0
            projects = int(row["projects"] or 0) if row else 0
            total = messages + tools + projects
            result.append({
                "day": day,
                "messages": messages,
                "tools": tools,
                "projects": projects,
                "intensity": intensity(total),
            })
        return result

    def tool_ranking(self) -> list[dict]:
        rows = self.repo.fetchall(
            """
            SELECT tool,
                   COUNT(*) AS calls,
                   SUM(CASE WHEN status = 'ALLOWED' THEN 1 ELSE 0 END) AS allowed,
                   SUM(CASE WHEN status = 'DENIED' THEN 1 ELSE 0 END) AS denied,
                   SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed
            FROM activity_events
            WHERE event_type = 'tool' AND tool <> ''
            GROUP BY tool
            ORDER BY calls DESC, tool ASC
            LIMIT 12
            """
        )
        return [dict(row) for row in rows]

    def security(self) -> dict:
        row = self.repo.fetchone(
            """
            SELECT
              SUM(CASE WHEN status = 'ALLOWED' THEN 1 ELSE 0 END) AS allowed,
              SUM(CASE WHEN status = 'DENIED' THEN 1 ELSE 0 END) AS denied,
              SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
              SUM(CASE WHEN permission_class = 'WRITE' AND status = 'DENIED' THEN 1 ELSE 0 END) AS write_denied,
              SUM(CASE WHEN permission_class = 'CRITICAL' AND status = 'DENIED' THEN 1 ELSE 0 END) AS critical_denied
            FROM activity_events
            WHERE event_type = 'tool'
            """
        )
        if not row:
            return {}
        return {key: int(row[key] or 0) for key in row.keys()}

    def project_ranking(self) -> list[dict]:
        rows = self.repo.fetchall(
            """
            SELECT project_path,
                   COUNT(DISTINCT NULLIF(conversation_id, '')) AS conversations,
                   SUM(CASE WHEN event_type = 'message' THEN 1 ELSE 0 END) AS messages,
                   SUM(CASE WHEN event_type = 'tool' THEN 1 ELSE 0 END) AS tool_events
            FROM activity_events
            WHERE lower(project_path) LIKE 'c:\\goldenai\\projetos%'
            GROUP BY project_path
            ORDER BY conversations DESC, messages DESC
            LIMIT 10
            """
        )
        result = []
        for row in rows:
            data = dict(row)
            data["project_name"] = Path(data["project_path"]).name
            result.append(data)
        return result

    def categories(self) -> list[dict]:
        rows = self.repo.fetchall("SELECT event_type, tool, project_path FROM activity_events")
        counts = defaultdict(int)
        for row in rows:
            text = f"{row['tool']} {row['project_path']}".lower()
            if "mt5" in text or "mql5" in text or ".mq5" in text or ".mqh" in text:
                counts["MQL5/MT5"] += 1
            elif any(name in text for name in ("get_system_info", "get_disk_usage", "list_processes", "get_current_datetime")):
                counts["Sistema/PC"] += 1
            elif row["event_type"] == "message":
                counts["Conversa geral"] += 1
            else:
                counts["Programacao"] += 1
        base = [
            {"name": "Conversa geral", "count": counts.get("Conversa geral", 0), "status": "ativo"},
            {"name": "Programacao", "count": counts.get("Programacao", 0), "status": "ativo"},
            {"name": "MQL5/MT5", "count": counts.get("MQL5/MT5", 0), "status": "ativo"},
            {"name": "Sistema/PC", "count": counts.get("Sistema/PC", 0), "status": "ativo"},
            {"name": "Pesquisa Quant", "count": None, "status": "Ainda nao integrado"},
            {"name": "Mercado", "count": None, "status": "Ainda nao integrado"},
            {"name": "Media Study", "count": None, "status": "Ainda nao integrado"},
        ]
        return base

    def model_usage(self, current_model: str = "") -> list[dict]:
        rows = self.repo.fetchall(
            """
            SELECT COALESCE(NULLIF(model, ''), ?) AS model, COUNT(*) AS messages
            FROM activity_events
            WHERE event_type = 'message'
            GROUP BY COALESCE(NULLIF(model, ''), ?)
            ORDER BY messages DESC
            """,
            (current_model or "modelo atual", current_model or "modelo atual"),
        )
        return [dict(row) for row in rows]

    def session_time(self) -> dict:
        rows = self.repo.fetchall("SELECT started_at, ended_at FROM chat_sessions WHERE ended_at IS NOT NULL")
        durations = []
        for row in rows:
            start = parse_iso(row["started_at"])
            end = parse_iso(row["ended_at"])
            if start and end and end >= start:
                durations.append((end - start).total_seconds())
        if not durations:
            return {"known": False, "message": "Ainda sem sessoes finalizadas"}
        total = sum(durations)
        return {
            "known": True,
            "total_seconds": int(total),
            "average_seconds": int(total / len(durations)),
            "longest_seconds": int(max(durations)),
            "sessions_counted": len(durations),
        }

    def token_usage(self) -> dict:
        row = self.repo.fetchone("SELECT COUNT(*) AS n FROM token_usage")
        status = token_usage_status()
        status["records"] = int(row["n"] or 0) if row else 0
        return status
