"""Configuracao centralizada de chaves de API do Golden.

Le de config/api_keys.json (se existir) e de variavel de ambiente.
Nao imprime, nao armazena, nao duplica chaves.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

_GOLDEN_ROOT = Path(r"C:\GoldenAI")
_KEYS_CACHE: Optional[dict] = None


def _load_keys_file() -> dict:
    """Le config/api_keys.json uma vez (cache em memoria)."""
    global _KEYS_CACHE
    if _KEYS_CACHE is not None:
        return _KEYS_CACHE
    try:
        path = _GOLDEN_ROOT / "config" / "api_keys.json"
        if path.exists():
            _KEYS_CACHE = json.loads(path.read_text(encoding="utf-8"))
        else:
            _KEYS_CACHE = {}
    except Exception:
        _KEYS_CACHE = {}
    return _KEYS_CACHE


def resolve_api_key(env_var: str, json_key: str) -> Optional[str]:
    """Resolve uma chave de API seguindo a precedencia do Golden.

    Precedencia:
      1. Variavel de ambiente ``env_var``
      2. ``config/api_keys.json[json_key]``

    Retorna a chave encontrada ou None.  Nunca imprime o valor.
    """
    if os.environ.get("JARVIS_TEST_MODE") == "1":
        return os.environ.get(f"TEST_{env_var}", "").strip() or None

    env_val = os.environ.get(env_var, "").strip()
    if env_val:
        return env_val
    keys = _load_keys_file()
    file_val = str(keys.get(json_key) or "").strip()
    if file_val:
        return file_val
    if os.name == "nt":
        try:
            import winreg
            locations = (
                (winreg.HKEY_CURRENT_USER, r"Environment"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            )
            for root, path in locations:
                try:
                    with winreg.OpenKey(root, path) as key:
                        value = str(winreg.QueryValueEx(key, env_var)[0] or "").strip()
                    if value:
                        return value
                except OSError:
                    continue
        except (ImportError, OSError):
            pass
    return None
