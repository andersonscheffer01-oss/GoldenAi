from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from .models import DateTimeInfo


def get_current_datetime() -> dict:
    now = datetime.now().astimezone()
    info = DateTimeInfo(
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M:%S"),
        weekday=now.strftime("%A"),
        timezone=str(now.tzinfo),
        iso_timestamp=now.isoformat(),
    )
    return asdict(info)
