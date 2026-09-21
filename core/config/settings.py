from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\GoldenAI")


@dataclass(frozen=True)
class ToolsConfig:
    """Configuration for the external tools infrastructure."""

    enabled: bool = True
    auto_discovery: bool = True
    allow_remote_paid: bool = False
    default_cost_policy: str = "free_or_local"


@dataclass(frozen=True)
class CodingAgentConfig:
    """Configuration for the Codex CLI coding agent integration."""

    enabled: bool = True
    provider: str = "codex_cli"
    local_only: bool = True
    paid_fallback: bool = False
    model_provider: str = "ollama"
    self_development_enabled: bool = True
    checkpoint_enabled: bool = True
    backup_before_edit: bool = True
    rollback_on_failure: bool = True
    timeout_seconds: int = 300


@dataclass(frozen=True)
class GoldenAISettings:
    root: Path = ROOT
    projects_dir: Path = ROOT / "projetos"
    backups_dir: Path = ROOT / "backups"
    logs_dir: Path = ROOT / "logs"
    experiments_dir: Path = ROOT / "experiments"
    sandbox_dir: Path = ROOT / "sandbox"
    data_dir: Path = ROOT / "data"
    read_only: bool = True
    write_enabled: bool = False
    command_execution_enabled: bool = False
    mt5_integration_enabled: bool = True
    trading_mode: str = "demo"
    media_enabled: bool = False
    internet_enabled: bool = False
    allowed_paths: tuple[Path, ...] = field(default_factory=lambda: (
        ROOT / "projetos",
        ROOT / "sandbox",
        ROOT / "experiments",
        ROOT / "knowledge",
        ROOT / "data",
        ROOT / "logs",
    ))
    protected_paths: tuple[Path, ...] = field(default_factory=lambda: (
        ROOT / "app",
        ROOT / "studio",
        ROOT / "backups",
    ))
    # Multi-Model Local V1
    model_routing_enabled: bool = True
    ollama_api_url: str = "http://127.0.0.1:11434"
    model_profiles: dict[str, str] = field(default_factory=lambda: {
        "FAST": "qwen2.5-coder:14b",
        "CODER": "qwen2.5-coder:14b",
        "EXPERT": "orcarouter/Qwen3.8-27B-Uncensored:iq4_xs",
    })
    model_timeout_fast: int = 60
    model_timeout_coder: int = 120
    model_timeout_expert: int = 300
    model_circuit_failure_threshold: int = 3
    model_circuit_cooldown_seconds: int = 60
    model_auto_download: bool = False
    # Multi-provider fallback (external first, local fallback)
    external_first: bool = False
    nvidia_api_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_api_key: str = ""
    nvidia_model_name: str = "z-ai/glm-5.2"
    nvidia_timeout_seconds: int = 180
    # OpenCode agent integration (Free models -> local Qwen fallback)
    opencode_enabled: bool = True
    opencode_cmd: str = r"C:\Users\Anderson\AppData\Roaming\npm\opencode.cmd"
    opencode_models: list[str] = field(default_factory=lambda: [
        "opencode/deepseek-v4-flash-free",
        "opencode/hy3-free",
        "opencode/nemotron-3.5-lightning-free",
    ])
    opencode_timeout_seconds: int = 900
    opencode_work_dir: str = r"C:\GoldenAI\sandbox\opencode"
    # External Tools Infrastructure
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    # Codex CLI Coding Agent
    coding_agent: CodingAgentConfig = field(default_factory=CodingAgentConfig)


def _parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    """Load the small project YAML file without requiring PyYAML.

    Supports one level of nesting: top-level keys can have either
    list children (``  - item``) or dict children (``  key: value``).
    """
    data: dict[str, Any] = {}
    if not path.exists():
        return data

    current_key: str | None = None
    current_list: list[str] | None = None
    current_dict: dict[str, Any] | None = None
    section_type: str | None = None  # "list" or "dict"

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        # List item: "  - value"
        if line.startswith("  - ") and current_key is not None:
            if section_type is None:
                section_type = "list"
                current_list = []
                data[current_key] = current_list
            if section_type == "list" and current_list is not None:
                current_list.append(line[4:].strip().strip('"').strip("'"))
            continue

        # Dict entry: "  key: value" (indented, has colon, not a list item)
        if line.startswith("  ") and ":" in line and current_key is not None:
            if section_type is None:
                section_type = "dict"
                current_dict = {}
                data[current_key] = current_dict
            if section_type == "dict" and current_dict is not None:
                sub_key, sub_value = line.strip().split(":", 1)
                sub_key = sub_key.strip()
                sub_value = sub_value.strip()
                current_dict[sub_key] = _parse_scalar(sub_value)
            continue

        # Top-level key: value
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                current_key = key
                section_type = None
                current_list = None
                current_dict = None
                data[key] = []
            else:
                current_key = None
                section_type = None
                current_list = None
                current_dict = None
                data[key] = _parse_scalar(value)
    return data


def _path(value: Any, default: Path) -> Path:
    if not value:
        return default
    return Path(str(value))


def _path_tuple(values: Any, default: tuple[Path, ...]) -> tuple[Path, ...]:
    if not isinstance(values, list):
        return default
    return tuple(Path(str(v)) for v in values)


def _tools_config(values: Any, default: ToolsConfig) -> ToolsConfig:
    if not isinstance(values, dict):
        return default
    return ToolsConfig(
        enabled=bool(values.get("enabled", default.enabled)),
        auto_discovery=bool(values.get("auto_discovery", default.auto_discovery)),
        allow_remote_paid=bool(values.get("allow_remote_paid", default.allow_remote_paid)),
        default_cost_policy=str(values.get("default_cost_policy", default.default_cost_policy)),
    )


def _coding_agent_config(values: Any, default: CodingAgentConfig) -> CodingAgentConfig:
    if not isinstance(values, dict):
        return default
    return CodingAgentConfig(
        enabled=bool(values.get("enabled", default.enabled)),
        provider=str(values.get("provider", default.provider)),
        local_only=bool(values.get("local_only", default.local_only)),
        paid_fallback=bool(values.get("paid_fallback", default.paid_fallback)),
        model_provider=str(values.get("model_provider", default.model_provider)),
        self_development_enabled=bool(values.get("self_development_enabled", default.self_development_enabled)),
        checkpoint_enabled=bool(values.get("checkpoint_enabled", default.checkpoint_enabled)),
        backup_before_edit=bool(values.get("backup_before_edit", default.backup_before_edit)),
        rollback_on_failure=bool(values.get("rollback_on_failure", default.rollback_on_failure)),
        timeout_seconds=int(values.get("timeout_seconds", default.timeout_seconds)),
    )


def load_settings(path: str | Path | None = None) -> GoldenAISettings:
    config_path = Path(path) if path else ROOT / "config" / "golden_ai.yaml"
    raw = _load_simple_yaml(config_path)
    defaults = GoldenAISettings()
    return GoldenAISettings(
        root=_path(raw.get("root"), defaults.root),
        projects_dir=_path(raw.get("projects_dir"), defaults.projects_dir),
        backups_dir=_path(raw.get("backups_dir"), defaults.backups_dir),
        logs_dir=_path(raw.get("logs_dir"), defaults.logs_dir),
        experiments_dir=_path(raw.get("experiments_dir"), defaults.experiments_dir),
        sandbox_dir=_path(raw.get("sandbox_dir"), defaults.sandbox_dir),
        data_dir=_path(raw.get("data_dir"), defaults.data_dir),
        read_only=bool(raw.get("read_only", defaults.read_only)),
        write_enabled=bool(raw.get("write_enabled", defaults.write_enabled)),
        command_execution_enabled=bool(
            raw.get("command_execution_enabled", defaults.command_execution_enabled)
        ),
        mt5_integration_enabled=bool(
            raw.get("mt5_integration_enabled", defaults.mt5_integration_enabled)
        ),
        trading_mode=str(raw.get("trading_mode", defaults.trading_mode)),
        media_enabled=bool(raw.get("media_enabled", defaults.media_enabled)),
        internet_enabled=bool(raw.get("internet_enabled", defaults.internet_enabled)),
        allowed_paths=_path_tuple(raw.get("allowed_paths"), defaults.allowed_paths),
        protected_paths=_path_tuple(raw.get("protected_paths"), defaults.protected_paths),
        model_routing_enabled=bool(raw.get("model_routing_enabled", defaults.model_routing_enabled)),
        ollama_api_url=str(raw.get("ollama_api_url", defaults.ollama_api_url)),
        model_profiles=raw.get("model_profiles", defaults.model_profiles) if isinstance(raw.get("model_profiles"), dict) else defaults.model_profiles,
        model_timeout_fast=int(raw.get("model_timeout_fast", defaults.model_timeout_fast)),
        model_timeout_coder=int(raw.get("model_timeout_coder", defaults.model_timeout_coder)),
        model_timeout_expert=int(raw.get("model_timeout_expert", defaults.model_timeout_expert)),
        model_circuit_failure_threshold=int(raw.get("model_circuit_failure_threshold", defaults.model_circuit_failure_threshold)),
        model_circuit_cooldown_seconds=int(raw.get("model_circuit_cooldown_seconds", defaults.model_circuit_cooldown_seconds)),
        model_auto_download=bool(raw.get("model_auto_download", defaults.model_auto_download)),
        external_first=bool(raw.get("external_first", defaults.external_first)),
        nvidia_api_url=str(raw.get("nvidia_api_url", defaults.nvidia_api_url)),
        nvidia_api_key=str(raw.get("nvidia_api_key", defaults.nvidia_api_key)),
        nvidia_model_name=str(raw.get("nvidia_model_name", defaults.nvidia_model_name)),
        nvidia_timeout_seconds=int(raw.get("nvidia_timeout_seconds", defaults.nvidia_timeout_seconds)),
        opencode_enabled=bool(raw.get("opencode_enabled", defaults.opencode_enabled)),
        opencode_cmd=str(raw.get("opencode_cmd", defaults.opencode_cmd)),
        opencode_models=list(raw.get("opencode_models", defaults.opencode_models))
        if isinstance(raw.get("opencode_models"), list) else defaults.opencode_models,
        opencode_timeout_seconds=int(raw.get("opencode_timeout_seconds", defaults.opencode_timeout_seconds)),
        opencode_work_dir=str(raw.get("opencode_work_dir", defaults.opencode_work_dir)),
        tools=_tools_config(raw.get("tools"), defaults.tools),
        coding_agent=_coding_agent_config(raw.get("coding_agent"), defaults.coding_agent),
    )
