from __future__ import annotations

import os
from urllib.parse import urlparse, unquote

from .models import URLValidationResult


ALLOWED_PROTOCOLS = {"http", "https"}

BLOCKED_PROTOCOLS = {
    "file", "ftp", "ftps", "sftp", "smb", "cifs",
    "javascript", "data", "vbscript", "ldap", "ldaps",
    "gopher", "ws", "wss", "dict", "tftp",
}

EXECUTABLE_EXTENSIONS = {
    ".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".scr",
    ".com", ".cpl", ".hta", ".msc", ".sh", ".app",
    ".jar", ".wsf", ".wsh", ".mst", ".msp", ".inf",
    ".reg", ".lnk", ".url", ".pdb", ".dll", ".ocx",
    ".drv", ".sys", ".ax",
}

SAFE_DOWNLOAD_EXTENSIONS = {
    ".txt", ".csv", ".json", ".xml", ".html", ".htm",
    ".py", ".mq5", ".mqh", ".mq4", ".ex4", ".ex5",
    ".pdf", ".md", ".rst", ".log", ".yaml", ".yml",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".mp3", ".mp4", ".wav", ".avi", ".mkv",
    ".srt", ".vtt",
}

MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024
MAX_FETCH_SIZE = 200_000


def is_dangerous_protocol(protocol):
    return protocol.lower() in BLOCKED_PROTOCOLS


def is_executable_extension(filename):
    if not filename:
        return False
    ext = os.path.splitext(filename.lower())[1]
    return ext in EXECUTABLE_EXTENSIONS


def is_allowed_download_extension(filename):
    if not filename:
        return True
    ext = os.path.splitext(filename.lower())[1]
    if not ext:
        return True
    if ext in EXECUTABLE_EXTENSIONS:
        return False
    return True


def validate_url(url, allow_executable=False):
    if not url or not isinstance(url, str):
        return URLValidationResult(False, blocked_reason="URL vazia ou invalida")
    url = url.strip()
    if not url:
        return URLValidationResult(False, blocked_reason="URL vazia")
    try:
        parsed = urlparse(url)
    except Exception as e:
        return URLValidationResult(False, url=url, blocked_reason="URL malformada: " + str(e))
    protocol = (parsed.scheme or "").lower()
    if not protocol:
        return URLValidationResult(False, url=url, blocked_reason="Protocolo ausente")
    if protocol in BLOCKED_PROTOCOLS:
        return URLValidationResult(False, url=url, protocol=protocol, blocked_reason="Protocolo " + repr(protocol) + " bloqueado")
    if protocol not in ALLOWED_PROTOCOLS:
        return URLValidationResult(False, url=url, protocol=protocol, blocked_reason="Protocolo " + repr(protocol) + " nao permitido")
    domain = (parsed.hostname or "").lower()
    if not domain:
        return URLValidationResult(False, url=url, protocol=protocol, blocked_reason="Dominio ausente")
    if domain in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return URLValidationResult(False, url=url, protocol=protocol, domain=domain, blocked_reason="localhost bloqueado")
    path = unquote(parsed.path or "")
    filename = os.path.basename(path) if path else ""
    extension = os.path.splitext(filename)[1].lower() if filename else ""
    is_exec = is_executable_extension(filename)
    if is_exec and not allow_executable:
        return URLValidationResult(False, url=url, protocol=protocol, domain=domain, path=path, filename=filename, extension=extension, is_executable=True, blocked_reason="Extensao " + repr(extension) + " executavel bloqueada")
    return URLValidationResult(True, url=url, protocol=protocol, domain=domain, path=path, filename=filename, extension=extension, is_executable=is_exec)


def validate_download_url(url, max_size=MAX_DOWNLOAD_SIZE):
    result = validate_url(url, allow_executable=False)
    if not result.valid:
        return result
    if result.is_executable:
        return URLValidationResult(False, url=url, protocol=result.protocol, domain=result.domain, path=result.path, filename=result.filename, extension=result.extension, is_executable=True, blocked_reason="Download de executaveis (" + result.extension + ") bloqueado")
    return result
