from __future__ import annotations

import subprocess
from dataclasses import asdict

from .models import ProcessInfo


def list_processes(filter_name: str = "", limit: int = 80) -> list[dict]:
    cmd = ["tasklist", "/FO", "CSV", "/NH"]
    output = subprocess.check_output(cmd, text=True, errors="replace", timeout=8)
    rows: list[dict] = []
    needle = str(filter_name or "").lower()
    for line in output.splitlines():
        parts = [part.strip().strip('"') for part in line.split('","')]
        if len(parts) < 2:
            continue
        name = parts[0]
        if needle and needle not in name.lower():
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            pid = 0
        rows.append(asdict(ProcessInfo(pid=pid, name=name, status="running")))
        if len(rows) >= limit:
            break
    return rows
