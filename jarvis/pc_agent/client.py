from __future__ import annotations

import json
import urllib.error
import urllib.request


class JarvisAgentClient:
    def __init__(self, server_url: str, device_token: str, timeout: float = 15.0):
        self.server_url = server_url.rstrip("/")
        self.device_token = device_token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None, auth: bool = True) -> dict:
        body = None
        headers = {"Content-Type": "application/json"}
        if auth and self.device_token:
            headers["Authorization"] = f"Bearer {self.device_token}"
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(self.server_url + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc

    def confirm_pairing(self, codigo: str, nome: str, versao_agente: str, sistema_operacional: str) -> dict:
        return self._request(
            "POST",
            "/api/dispositivos/pareamento/confirmar",
            {
                "codigo": codigo,
                "nome": nome,
                "versao_agente": versao_agente,
                "sistema_operacional": sistema_operacional,
            },
            auth=False,
        )

    def heartbeat(self, payload: dict) -> dict:
        return self._request("POST", "/api/dispositivos/agente/heartbeat", payload)

    def next_command(self) -> dict:
        return self._request("GET", "/api/pc/agente/comandos/proximo")

    def send_result(self, command_id: int, result: dict) -> dict:
        payload = {
            "ok": bool(result.get("ok")),
            "resultado": result.get("resultado") or {},
            "erro_codigo": result.get("erro_codigo"),
            "erro_mensagem": result.get("erro_mensagem"),
        }
        return self._request("POST", f"/api/pc/agente/comandos/{command_id}/resultado", payload)
