from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import httpx

from ..config import Settings


class PluggyError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 502, provider_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.status_code = status_code
        self.provider_status = provider_status


def safe_error(exc: Exception) -> str:
    return exc.safe_message[:240] if isinstance(exc, PluggyError) else "Falha temporaria na comunicacao com o Meu Pluggy."


def cents(value: Any) -> int | None:
    try:
        return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if value is not None else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        return None


class PluggyClient:
    def __init__(self, settings: Settings):
        if not settings.pluggy_configured:
            raise PluggyError("not_configured", "Credenciais do Meu Pluggy ainda nao configuradas no servidor.", 503)
        self.base_url = settings.pluggy_base_url
        self.client_id = settings.pluggy_client_id
        self.client_secret = settings.pluggy_client_secret
        self.timeout = httpx.Timeout(35.0, connect=10.0)
        self._api_key: str | None = None

    async def _authenticate(self) -> str:
        if self._api_key:
            return self._api_key
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.post("/auth", json={"clientId": self.client_id, "clientSecret": self.client_secret})
        except httpx.HTTPError as exc:
            raise PluggyError("provider_unavailable", "Meu Pluggy indisponivel no momento.") from exc
        if response.status_code >= 400:
            raise PluggyError("invalid_credentials", "O Meu Pluggy recusou as credenciais configuradas.", 502)
        key = (response.json() or {}).get("apiKey")
        if not key:
            raise PluggyError("invalid_auth_response", "Resposta de autenticacao invalida do Meu Pluggy.")
        self._api_key = str(key)
        return self._api_key

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        key = await self._authenticate()
        headers = dict(kwargs.pop("headers", {})); headers["X-API-KEY"] = key
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise PluggyError("provider_unavailable", "Meu Pluggy indisponivel no momento.") from exc
        if response.status_code >= 400:
            code = "rate_limited" if response.status_code == 429 else "provider_rejected"
            try:
                provider = response.json()
                code = str(provider.get("code") or provider.get("codeDescription") or code)[:80]
            except ValueError:
                pass
            raise PluggyError(code, "O Meu Pluggy recusou a solicitacao.", provider_status=response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise PluggyError("invalid_provider_response", "Resposta invalida do Meu Pluggy.") from exc

    async def connect_token(self, user_id: int, webhook_url: str | None = None, item_id: str | None = None) -> str:
        options: dict[str, Any] = {"clientUserId": f"jarvis:{user_id}", "avoidDuplicates": True}
        if webhook_url and webhook_url.startswith("https://"):
            options["webhookUrl"] = webhook_url
        body: dict[str, Any] = {"options": options}
        if item_id: body["itemId"] = item_id
        data = await self.request("POST", "/connect_token", json=body)
        token = (data or {}).get("accessToken")
        if not token: raise PluggyError("missing_connect_token", "Meu Pluggy nao retornou o token temporario.")
        return str(token)

    async def item(self, item_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/items/{item_id}")

    async def update_item(self, item_id: str) -> dict[str, Any]:
        """Trigger a provider-side refresh without receiving or sending credentials."""
        data = await self.request("PATCH", f"/items/{item_id}", json={})
        return data if isinstance(data, dict) else {}

    async def list_results(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        current_path, current_params = path, params
        resource_path = path.split("?", 1)[0]
        for _ in range(50):
            data = await self.request("GET", current_path, params=current_params)
            if isinstance(data, list): items.extend(x for x in data if isinstance(x, dict)); break
            if not isinstance(data, dict): break
            items.extend(x for x in data.get("results", []) if isinstance(x, dict))
            if not data.get("next"): break
            next_path = str(data["next"])
            current_path = resource_path + next_path if next_path.startswith("?") else next_path
            current_params = None
        return items

    async def accounts(self, item_id: str) -> list[dict[str, Any]]:
        return await self.list_results("/accounts", {"itemId": item_id})

    async def transactions(self, account_id: str) -> list[dict[str, Any]]:
        return await self.list_results("/v2/transactions", {"accountId": account_id})

    async def bills(self, account_id: str) -> list[dict[str, Any]]:
        return await self.list_results("/bills", {"accountId": account_id})

    async def disconnect(self, item_id: str) -> None:
        await self.request("DELETE", f"/items/{item_id}")
