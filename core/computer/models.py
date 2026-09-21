from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DateTimeInfo:
    date: str
    time: str
    weekday: str
    timezone: str
    iso_timestamp: str


@dataclass
class SystemInfo:
    hostname: str
    windows_version: str
    architecture: str
    cpu_model: str
    logical_cpus: int
    ram_total_bytes: int
    ram_available_bytes: int
    user: str
    python: str
    goldenai_root: str


@dataclass
class DiskUsageInfo:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent_used: float


@dataclass
class ProcessInfo:
    pid: int
    name: str
    status: str = ""


@dataclass
class ApplicationInfo:
    name: str
    found: bool
    path: str = ""
    source: str = ""


@dataclass
class MT5InstallationInfo:
    name: str
    path: str
    kind: str
