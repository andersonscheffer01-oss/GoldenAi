"""
Plugin: Informações do Sistema
Fornece informações detalhadas do sistema operacional.
"""
import platform
import psutil

name = "system_info_detailed"
description = "Fornece informações detalhadas do sistema (CPU, RAM, disco, rede)"
parameters = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
            "enum": ["full", "cpu", "memory", "disk", "network"],
            "description": "Nível de detalhe (default: full)"
        }
    },
    "required": []
}


def execute(args):
    detail = args.get("detail", "full")
    result = {"platform": platform.system(), "hostname": platform.node()}

    if detail in ("full", "cpu"):
        result["cpu"] = {
            "percent": psutil.cpu_percent(interval=0.1),
            "cores": psutil.cpu_count(),
            "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else None,
        }

    if detail in ("full", "memory"):
        mem = psutil.virtual_memory()
        result["memory"] = {
            "total_gb": round(mem.total / (1024**3), 1),
            "used_gb": round(mem.used / (1024**3), 1),
            "percent": mem.percent,
        }

    if detail in ("full", "disk"):
        disk = psutil.disk_usage("/")
        result["disk"] = {
            "total_gb": round(disk.total / (1024**3), 1),
            "used_gb": round(disk.used / (1024**3), 1),
            "percent": disk.percent,
        }

    if detail in ("full", "network"):
        net = psutil.net_io_counters()
        result["network"] = {
            "bytes_sent_mb": round(net.bytes_sent / (1024**2), 1),
            "bytes_recv_mb": round(net.bytes_recv / (1024**2), 1),
        }

    return result
