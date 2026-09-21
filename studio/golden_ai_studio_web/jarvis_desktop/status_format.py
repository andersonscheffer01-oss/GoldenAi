"""Formatacao honesta de status: nunca inventa dado; usa N/D e NO DATA."""
from __future__ import annotations


def mask_account(value):
    """Mascara conta sensivel: mostra so os 2 ultimos digitos."""
    text = "" if value is None else str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return "N/D"
    return "****" + digits[-2:]


def provider_badge(state):
    return {"ONLINE": "● ONLINE", "RATE_LIMITED": "! RATE LIMITED",
            "DEGRADED": "! DEGRADED", "TIMEOUT": "! TIMEOUT",
            "AUTH_ERROR": "! AUTH ERROR", "OFFLINE": "○ OFFLINE"}.get(
        str(state), "? UNKNOWN")


def radar_display(payload):
    """{'label','active'} a partir do /api/radar/status real."""
    if not isinstance(payload, dict) or not payload.get("ok"):
        return {"label": "○ NO DATA", "active": False}
    if payload.get("running"):
        return {"label": "● ACTIVE", "active": True}
    return {"label": "○ NO DATA", "active": False}


def mt5_display(status):
    """{'label','broker','server','account','balance'} a partir do /api/status."""
    con = (status or {}).get("connections", {}) if isinstance(status, dict) else {}
    mt5 = con.get("mt5", {}) if isinstance(con, dict) else {}
    if not (isinstance(mt5, dict) and mt5.get("ok")):
        return {"label": "○ DISCONNECTED", "connected": False, "broker": "N/D",
                "server": "N/D", "account": "N/D", "balance": None}
    server = str(mt5.get("server") or "N/D")
    broker = str(mt5.get("broker") or server.split("-")[0] if server != "N/D" else "N/D")
    return {"label": "● CONNECTED", "connected": True, "broker": broker,
            "server": server, "account": mask_account(mt5.get("account")),
            "balance": mt5.get("balance")}


def voice_display(voice):
    if not isinstance(voice, dict) or not voice.get("ok"):
        return "○ OFF"
    state = str(voice.get("state", "")).upper()
    mapping = {"WAITING_WAKE": "● WAITING", "LISTENING": "● LISTENING",
               "WAKE_DETECTED": "● WAKE", "TRANSCRIBING": "● TRANSCRIBING",
               "PROCESSING": "● PROCESSING", "SPEAKING": "● SPEAKING",
               "ERROR": "! ERROR", "OFF": "○ OFF"}
    if state in mapping:
        return mapping[state]
    if "OUV" in state or "LISTEN" in state:
        return "● LISTENING"
    if "ERR" in state:
        return "! ERROR"
    return "● LISTENING" if voice.get("running") else "○ OFF"


def task_counts(tasks):
    active_s = {"QUEUED", "RUNNING", "WAITING_CONFIRMATION", "CANCEL_REQUESTED"}
    active = waiting = errors = 0
    for t in tasks or []:
        s = str(t.get("status"))
        if s in active_s:
            active += 1
        if s == "WAITING_CONFIRMATION":
            waiting += 1
        if s in ("FAILED", "INTERRUPTED"):
            errors += 1
    return {"active": active, "waiting": waiting, "errors": errors}


def gpu_text(gpu):
    """Texto honesto da GPU: nome real; N/D quando indisponivel."""
    if not isinstance(gpu, dict) or not gpu.get("name"):
        return {"name": "N/D", "util": None, "vram": "N/D"}
    vram = gpu.get("vram_total_human") or "N/D"
    return {"name": str(gpu["name"]), "util": gpu.get("util_percent"), "vram": vram}


def bar_blocks(percent):
    """10 blocos discretos para CPU/RAM/GPU. None => vazios."""
    if percent is None:
        return "░░░░░░░░░░ N/D"
    try:
        pct = max(0, min(100, float(percent)))
    except (TypeError, ValueError):
        return "░░░░░░░░░░ N/D"
    full = int(round(pct / 10))
    return "█" * full + "░" * (10 - full) + f" {pct:.0f}%"
