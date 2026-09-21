from __future__ import annotations

import re
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.config import load_settings
from core.execution import ExecutionService

from .models import WebContent, DownloadResult
from .url_validator import (
    validate_url,
    validate_download_url,
    is_executable_extension,
    MAX_DOWNLOAD_SIZE,
    MAX_FETCH_SIZE,
)
from .content_sanitizer import (
    extract_text_from_html,
    sanitize_content,
    detect_injection_attempts,
)


class InternetService:
    def __init__(self, root=r"C:\GoldenAI"):
        self.root = Path(root)
        self.settings = load_settings()
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self.downloads_dir = self.root / "sandbox" / "downloads"
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self._internet_enabled = getattr(self.settings, "internet_enabled", False)

    def is_enabled(self):
        return self._internet_enabled

    def _record(self, action, status, target, summary, tool="internet", permission="READ", risk="LOW"):
        try:
            self.execution.record_event(
                task_id="internet", category="INTERNET", action=action,
                status=status, summary=summary[:600], target=str(target)[:300],
                tool_name=tool, permission_level=permission, risk_level=risk,
            )
            self.audit.record({
                "action_type": action, "status": status,
                "agent": "core.internet.service",
                "target": str(target)[:300], "result": summary[:600],
            })
        except Exception:
            pass

    def web_search(self, query, max_results=5):
        if not self.is_enabled():
            self._record("INTERNET_SEARCH_BLOCKED", "BLOCKED", query, "Internet desativado")
            return {"ok": False, "erro": "Acesso a Internet desativado."}
        if not query or not query.strip():
            return {"ok": False, "erro": "Consulta vazia."}
        query = query.strip()
        self._record("INTERNET_SEARCH_STARTED", "STARTED", query, "Buscando: " + query[:100])
        try:
            url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
            req = urllib.request.Request(url, headers={"User-Agent": "GoldenAI/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read(MAX_FETCH_SIZE).decode("utf-8", errors="replace")
            results = self._parse_search_results(html, max_results)
            self._record("INTERNET_SEARCH_COMPLETED", "COMPLETED", query, str(len(results)) + " resultados")
            return {"ok": True, "query": query, "results": results, "is_untrusted": True}
        except urllib.error.URLError as e:
            self._record("INTERNET_SEARCH_FAILED", "FAILED", query, "Erro de rede: " + str(e))
            return {"ok": False, "erro": "Nao foi possivel conectar. Verifique a Internet. Detalhe: " + str(e)}
        except Exception as e:
            self._record("INTERNET_SEARCH_FAILED", "FAILED", query, "Erro: " + str(e))
            return {"ok": False, "erro": "Erro ao pesquisar: " + str(e)}

    def _parse_search_results(self, html, max_results):
        results = []
        pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</',
            re.DOTALL,
        )
        for match in pattern.finditer(html):
            if len(results) >= max_results:
                break
            url = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
            domain = ""
            try:
                domain = urllib.parse.urlparse(url).hostname or ""
            except Exception:
                pass
            results.append({"url": url, "title": title, "snippet": snippet, "domain": domain})
        return results

    def web_fetch(self, url, max_bytes=MAX_FETCH_SIZE):
        if not self.is_enabled():
            self._record("INTERNET_FETCH_BLOCKED", "BLOCKED", url, "Internet desativado")
            return WebContent(url=url, domain="", error="Acesso a Internet desativado.")
        validation = validate_url(url)
        if not validation.valid:
            self._record("INTERNET_FETCH_BLOCKED", "BLOCKED", url, validation.blocked_reason)
            return WebContent(url=url, domain="", error=validation.blocked_reason)
        self._record("INTERNET_FETCH_STARTED", "STARTED", url, "Buscando: " + validation.domain)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GoldenAI/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                status_code = resp.getcode()
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read(max_bytes)
                encoding = "utf-8"
                if "charset=" in content_type:
                    try:
                        encoding = content_type.split("charset=")[-1].split(";")[0].strip()
                    except Exception:
                        pass
                html = raw.decode(encoding, errors="replace")
            text = extract_text_from_html(html)
            if len(text) > max_bytes:
                text = text[:max_bytes] + "...[truncado]"
            injections = detect_injection_attempts(text)
            content = WebContent(
                url=url, domain=validation.domain, text=text,
                status_code=status_code, content_type=content_type, sanitized=True,
            )
            self._record("INTERNET_FETCH_COMPLETED", "COMPLETED", url, "Pagina obtida: " + str(len(text)) + " chars")
            return content
        except urllib.error.URLError as e:
            self._record("INTERNET_FETCH_FAILED", "FAILED", url, "Erro de rede: " + str(e))
            return WebContent(url=url, domain=validation.domain, error="Erro de rede: " + str(e))
        except Exception as e:
            self._record("INTERNET_FETCH_FAILED", "FAILED", url, "Erro: " + str(e))
            return WebContent(url=url, domain=validation.domain, error="Erro ao obter pagina: " + str(e))

    def safe_download(self, url, dest_dir="", max_size=MAX_DOWNLOAD_SIZE):
        if not self.is_enabled():
            self._record("INTERNET_DOWNLOAD_BLOCKED", "BLOCKED", url, "Internet desativado", permission="WRITE", risk="HIGH")
            return DownloadResult(False, url=url, error="Acesso a Internet desativado.")
        validation = validate_download_url(url, max_size)
        if not validation.valid:
            self._record("INTERNET_DOWNLOAD_BLOCKED", "BLOCKED", url, validation.blocked_reason, permission="WRITE", risk="HIGH")
            return DownloadResult(False, url=url, error=validation.blocked_reason, is_executable=validation.is_executable)
        if validation.is_executable:
            self._record("INTERNET_DOWNLOAD_BLOCKED", "BLOCKED", url, "Executavel bloqueado: " + validation.extension, permission="WRITE", risk="HIGH")
            return DownloadResult(False, url=url, domain=validation.domain, error="Download de executaveis bloqueado: " + validation.extension, is_executable=True)
        dest = Path(dest_dir) if dest_dir else self.downloads_dir
        dest.mkdir(parents=True, exist_ok=True)
        dest_resolved = dest.resolve()
        allowed = tuple(p.resolve() for p in self.settings.allowed_paths if p.exists())
        if not any(self._is_under(dest_resolved, root) for root in allowed):
            self._record("INTERNET_DOWNLOAD_BLOCKED", "BLOCKED", str(dest_resolved), "Destino fora das pastas autorizadas", permission="WRITE", risk="HIGH")
            return DownloadResult(False, url=url, error="Destino fora das pastas autorizadas.")
        filename = validation.filename or "download.bin"
        dest_path = dest_resolved / filename
        self._record("INTERNET_DOWNLOAD_STARTED", "STARTED", url, "Baixando " + filename + " de " + validation.domain, permission="WRITE", risk="HIGH")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GoldenAI/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                content_type = resp.headers.get("Content-Type", "")
                content_length = resp.headers.get("Content-Length")
                if content_length:
                    try:
                        cl = int(content_length)
                        if cl > max_size:
                            return DownloadResult(False, url=url, domain=validation.domain, error="Arquivo muito grande: " + str(cl) + " bytes")
                    except ValueError:
                        pass
                data = resp.read(max_size + 1)
                if len(data) > max_size:
                    return DownloadResult(False, url=url, domain=validation.domain, error="Arquivo excede tamanho maximo: " + str(max_size) + " bytes")
            dest_path.write_bytes(data)
            is_exec = is_executable_extension(filename)
            self._record("INTERNET_DOWNLOAD_COMPLETED", "COMPLETED", url, "Baixado: " + filename + " (" + str(len(data)) + " bytes). Execucao NAO autorizada.", permission="WRITE", risk="HIGH")
            return DownloadResult(success=True, url=url, domain=validation.domain, saved_path=str(dest_path), filename=filename, size_bytes=len(data), content_type=content_type, is_executable=is_exec)
        except urllib.error.URLError as e:
            self._record("INTERNET_DOWNLOAD_FAILED", "FAILED", url, "Erro de rede: " + str(e), permission="WRITE", risk="HIGH")
            return DownloadResult(False, url=url, domain=validation.domain, error="Erro de rede: " + str(e))
        except Exception as e:
            self._record("INTERNET_DOWNLOAD_FAILED", "FAILED", url, "Erro: " + str(e), permission="WRITE", risk="HIGH")
            return DownloadResult(False, url=url, domain=validation.domain, error="Erro ao baixar: " + str(e))

    @staticmethod
    def _is_under(path, root):
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
