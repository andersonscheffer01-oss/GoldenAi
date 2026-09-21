"""
Golden AI - Config Loader

Combina múltiplos arquivos YAML de configuração em um único dict.
Prioridade: ollama.yaml > tools.yaml > security.yaml > base.yaml > golden_ai.yaml

Uso:
    from config.config_loader import load_merged_config
    config = load_merged_config()
"""

import os
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

CONFIG_DIR = Path(__file__).parent


def _load_yaml(path):
    """Carrega um arquivo YAML de forma segura."""
    if not yaml:
        return {}
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _deep_merge(base, override):
    """Merge profundo: override sobrescreve base."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_merged_config():
    """
    Carrega e combina todos os arquivos de configuração.

    Ordem de prioridade (maior para menor):
    1. ollama.yaml    - Modelos e providers
    2. tools.yaml     - Ferramentas e coding agent
    3. security.yaml  - Permissões e paths
    4. base.yaml      - Caminhos gerais
    5. golden_ai.yaml - Fallback (arquivo original)
    """
    # Carrega cada arquivo
    base = _load_yaml(CONFIG_DIR / "base.yaml")
    security = _load_yaml(CONFIG_DIR / "security.yaml")
    ollama = _load_yaml(CONFIG_DIR / "ollama.yaml")
    tools = _load_yaml(CONFIG_DIR / "tools.yaml")
    legacy = _load_yaml(CONFIG_DIR / "golden_ai.yaml")

    # Flatten opencode/tools/coding_agent do legacy para compatibilidade
    if "opencode" in legacy:
        opencode = legacy.pop("opencode")
        for k, v in opencode.items():
            legacy[f"opencode_{k}"] = v
    if "tools" in legacy:
        legacy.pop("tools")  # Já temos em tools.yaml
    if "coding_agent" in legacy:
        legacy.pop("coding_agent")  # Já temos em tools.yaml

    # Merge na ordem de prioridade
    config = {}
    config = _deep_merge(config, legacy)     # 5. golden_ai.yaml (fallback)
    config = _deep_merge(config, base)       # 4. base.yaml
    config = _deep_merge(config, security)   # 3. security.yaml
    config = _deep_merge(config, tools)      # 2. tools.yaml
    config = _deep_merge(config, ollama)     # 1. ollama.yaml (maior prioridade)

    return config


def print_config_summary(config):
    """Imprime resumo da configuração carregada."""
    print("=" * 60)
    print("GOLDEN AI - CONFIGURACAO CARREGADA")
    print("=" * 60)
    print(f"Root: {config.get('root', '?')}")
    print(f"Read-only: {config.get('read_only', '?')}")
    print(f"Write enabled: {config.get('write_enabled', '?')}")
    print(f"Command exec: {config.get('command_execution_enabled', '?')}")
    print(f"MT5 integration: {config.get('mt5_integration_enabled', '?')}")
    print(f"Internet: {config.get('internet_enabled', '?')}")

    profiles = config.get("model_profiles", {})
    print(f"Model profiles: {list(profiles.keys())}")

    tools = config.get("tools", {})
    print(f"Tools enabled: {tools.get('enabled', '?')}")

    coding = config.get("coding_agent", {})
    print(f"Coding agent: {coding.get('enabled', '?')} ({coding.get('provider', '?')})")

    opencode = config.get("opencode_enabled", "?")
    print(f"OpenCode: {opencode}")

    print("=" * 60)


if __name__ == "__main__":
    config = load_merged_config()
    print_config_summary(config)
