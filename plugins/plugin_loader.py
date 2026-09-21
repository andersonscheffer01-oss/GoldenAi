"""
Plugin Loader — carrega e gerencia plugins dinamicamente.

Cada plugin é um arquivo Python no diretório plugins/ com:
  - name: str           (nome da tool)
  - description: str    (descrição para o LLM)
  - parameters: dict    (schema JSON dos parâmetros)
  - execute: Callable   (função que executa a tool)

Opção V2 (plugin kernel):
  - manifest: PluginManifest  (metadados do plugin)
  - start/stop/health         (lifecycle)
  - permissions               (metadados de permissão)

Exemplo de plugin:
    name = "cotacao_bolsa"
    description = "Busca cotação de ações na B3"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Código da ação"}
        },
        "required": ["ticker"]
    }
    def execute(args):
        return {"preco": 28.50}
"""

import importlib
import importlib.util
import os
import sys
import time
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("golden.plugins")


# ═══════════════════════════════════════════════════════════════
# PLUGIN KERNEL V1 — Lifecycle, Health, Permissions
# ═══════════════════════════════════════════════════════════════

class PluginState(str, Enum):
    """Estados do ciclo de vida de um plugin."""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    DEGRADED = "degraded"
    FAILED = "failed"


class PluginHealthStatus(str, Enum):
    """Status de saúde de um plugin."""
    OK = "ok"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class PluginHealth:
    """Resultado de health check de um plugin."""
    status: PluginHealthStatus = PluginHealthStatus.UNKNOWN
    message: str = ""
    checked_at: float = 0.0
    details: dict = field(default_factory=dict)


@dataclass
class PluginManifest:
    """Metadados de um plugin V2 (kernel)."""
    id: str = ""
    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    capabilities: list = field(default_factory=list)
    permissions: list = field(default_factory=list)
    enabled: bool = True
    dependencies: list = field(default_factory=list)

    def validate(self) -> list:
        """Valida o manifest. Retorna lista de erros (vazia = válido)."""
        errors = []
        if not self.id:
            errors.append("manifest.id is required")
        if not self.name:
            errors.append("manifest.name is required")
        return errors


# ═══════════════════════════════════════════════════════════════
# PLUGIN DATACLASS — Backward compatible
# ═══════════════════════════════════════════════════════════════

@dataclass
class Plugin:
    """Representa um plugin carregado.

    Campos originais (preservados):
      name, description, parameters, execute, source_file, enabled

    Campos V2 (kernel, opcionais):
      manifest, state, health, _start_fn, _stop_fn, _health_fn
    """
    name: str
    description: str
    parameters: Dict[str, Any]
    execute: Callable
    source_file: str = ""
    enabled: bool = True
    # V2 — kernel fields
    manifest: Optional[PluginManifest] = None
    state: PluginState = PluginState.LOADED
    health: PluginHealth = field(default_factory=PluginHealth)
    permissions: list = field(default_factory=list)
    _start_fn: Optional[Callable] = field(default=None, repr=False)
    _stop_fn: Optional[Callable] = field(default=None, repr=False)
    _health_fn: Optional[Callable] = field(default=None, repr=False)


# ═══════════════════════════════════════════════════════════════
# PLUGIN REGISTRY — Extended with lifecycle
# ═══════════════════════════════════════════════════════════════

class PluginRegistry:
    """Registro central de plugins do Golden AI.

    API original (preservada):
      register, get, execute, list_tools, list_plugins,
      enable, disable, reload

    API V2 (kernel):
      start, stop, health_check, get_health,
      register_plugin, snapshot
    """

    def __init__(self, plugins_dir: str = None):
        self._plugins: Dict[str, Plugin] = {}
        if plugins_dir is None:
            plugins_dir = str(Path(__file__).parent)
        self._plugins_dir = plugins_dir
        self._load_plugins()

    # ─── Discovery & Loading (original, preservado) ──────────

    def _load_plugins(self):
        """Carrega automaticamente todos os .py do diretório plugins/."""
        plugins_path = Path(self._plugins_dir)
        if not plugins_path.exists():
            logger.warning(f"Plugins directory not found: {self._plugins_dir}")
            return

        for py_file in plugins_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if py_file.name in ("plugin_loader.py",):
                continue

            try:
                self._load_plugin_file(py_file)
            except Exception as e:
                logger.error(f"Failed to load plugin {py_file.name}: {e}")

    def _load_plugin_file(self, filepath: Path):
        """Carrega um arquivo de plugin individual."""
        module_name = f"golden_plugin_{filepath.stem}"

        spec = importlib.util.spec_from_file_location(module_name, str(filepath))
        if spec is None or spec.loader is None:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Extrair atributos obrigatórios
        name = getattr(module, "name", filepath.stem)
        description = getattr(module, "description", f"Plugin: {name}")
        parameters = getattr(module, "parameters", {"type": "object", "properties": {}})
        execute_fn = getattr(module, "execute", None)

        if execute_fn is None:
            logger.warning(f"Plugin {name} has no execute() function, skipping")
            return

        # Extrair atributos V2 (opcionais)
        manifest = getattr(module, "manifest", None)
        start_fn = getattr(module, "plugin_start", None)
        stop_fn = getattr(module, "plugin_stop", None)
        health_fn = getattr(module, "plugin_health", None)
        permissions = getattr(module, "permissions", [])

        # Construir manifest se não fornecido
        if manifest is None:
            manifest = PluginManifest(
                id=filepath.stem,
                name=name,
                description=description,
            )

        plugin = Plugin(
            name=name,
            description=description,
            parameters=parameters,
            execute=execute_fn,
            source_file=str(filepath),
            manifest=manifest,
            permissions=permissions,
            _start_fn=start_fn,
            _stop_fn=stop_fn,
            _health_fn=health_fn,
        )

        self._plugins[name] = plugin
        logger.info(f"Loaded plugin: {name}")

    # ─── Original API (preservada) ───────────────────────────

    def register(self, name: str, description: str, parameters: dict, execute: Callable):
        """Registra um plugin manualmente (por código)."""
        self._plugins[name] = Plugin(
            name=name,
            description=description,
            parameters=parameters,
            execute=execute,
        )

    def get(self, name: str) -> Optional[Plugin]:
        """Retorna um plugin pelo nome."""
        return self._plugins.get(name)

    def execute(self, name: str, args: dict) -> Any:
        """Executa um plugin pelo nome."""
        plugin = self._plugins.get(name)
        if plugin is None:
            return {"error": f"Plugin '{name}' not found"}
        if not plugin.enabled:
            return {"error": f"Plugin '{name}' is disabled"}
        if plugin.state == PluginState.FAILED:
            return {"error": f"Plugin '{name}' is in FAILED state"}
        try:
            return plugin.execute(args)
        except Exception as e:
            logger.error(f"Plugin {name} execution failed: {e}")
            plugin.state = PluginState.FAILED
            plugin.health = PluginHealth(
                status=PluginHealthStatus.UNHEALTHY,
                message=str(e),
                checked_at=time.time(),
            )
            return {"error": str(e)}

    def list_tools(self) -> list:
        """Retorna lista de tools no formato Ollama tool-calling."""
        tools = []
        for plugin in self._plugins.values():
            if plugin.enabled and plugin.state != PluginState.FAILED:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": plugin.name,
                        "description": plugin.description,
                        "parameters": plugin.parameters,
                    }
                })
        return tools

    def list_plugins(self) -> list:
        """Retorna informações de todos os plugins."""
        return [
            {
                "name": p.name,
                "description": p.description,
                "enabled": p.enabled,
                "source": p.source_file,
                "state": p.state.value,
                "health": p.health.status.value,
            }
            for p in self._plugins.values()
        ]

    def enable(self, name: str) -> bool:
        """Ativa um plugin."""
        plugin = self._plugins.get(name)
        if plugin:
            plugin.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Desativa um plugin."""
        plugin = self._plugins.get(name)
        if plugin:
            plugin.enabled = False
            return True
        return False

    def reload(self):
        """Recarrega todos os plugins do disco."""
        self._plugins.clear()
        self._load_plugins()

    # ─── V2 API — Lifecycle ──────────────────────────────────

    def start(self, name: str) -> bool:
        """Inicia um plugin (chama plugin_start se existe)."""
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        if plugin.state in (PluginState.RUNNING, PluginState.STARTING):
            return True
        if not plugin.enabled:
            plugin.state = PluginState.STOPPED
            return False

        plugin.state = PluginState.STARTING
        try:
            if plugin._start_fn:
                plugin._start_fn()
            plugin.state = PluginState.RUNNING
            plugin.health = PluginHealth(
                status=PluginHealthStatus.OK,
                message="Plugin started",
                checked_at=time.time(),
            )
            logger.info(f"Plugin started: {name}")
            return True
        except Exception as e:
            plugin.state = PluginState.FAILED
            plugin.health = PluginHealth(
                status=PluginHealthStatus.UNHEALTHY,
                message=f"Start failed: {e}",
                checked_at=time.time(),
            )
            logger.error(f"Plugin {name} start failed: {e}")
            return False

    def stop(self, name: str) -> bool:
        """Para um plugin (chama plugin_stop se existe)."""
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        if plugin.state in (PluginState.STOPPED, PluginState.STOPPING):
            return True

        plugin.state = PluginState.STOPPING
        try:
            if plugin._stop_fn:
                plugin._stop_fn()
            plugin.state = PluginState.STOPPED
            logger.info(f"Plugin stopped: {name}")
            return True
        except Exception as e:
            plugin.state = PluginState.FAILED
            plugin.health = PluginHealth(
                status=PluginHealthStatus.UNHEALTHY,
                message=f"Stop failed: {e}",
                checked_at=time.time(),
            )
            logger.error(f"Plugin {name} stop failed: {e}")
            return False

    def start_all(self) -> dict:
        """Inicia todos os plugins habilitados."""
        results = {}
        for name, plugin in self._plugins.items():
            if plugin.enabled:
                results[name] = self.start(name)
        return results

    def stop_all(self) -> dict:
        """Para todos os plugins."""
        results = {}
        for name in self._plugins:
            results[name] = self.stop(name)
        return results

    # ─── V2 API — Health ─────────────────────────────────────

    def health_check(self, name: str) -> PluginHealth:
        """Executa health check em um plugin."""
        plugin = self._plugins.get(name)
        if plugin is None:
            return PluginHealth(
                status=PluginHealthStatus.UNKNOWN,
                message=f"Plugin '{name}' not found",
                checked_at=time.time(),
            )

        if not plugin.enabled:
            return PluginHealth(
                status=PluginHealthStatus.UNKNOWN,
                message="Plugin disabled",
                checked_at=time.time(),
            )

        if plugin._health_fn:
            try:
                result = plugin._health_fn()
                if isinstance(result, PluginHealth):
                    plugin.health = result
                elif isinstance(result, dict):
                    plugin.health = PluginHealth(
                        status=PluginHealthStatus(result.get("status", "ok")),
                        message=result.get("message", ""),
                        checked_at=time.time(),
                        details=result.get("details", {}),
                    )
                else:
                    plugin.health = PluginHealth(
                        status=PluginHealthStatus.OK,
                        message=str(result) if result else "Healthy",
                        checked_at=time.time(),
                    )
            except Exception as e:
                plugin.health = PluginHealth(
                    status=PluginHealthStatus.UNHEALTHY,
                    message=f"Health check failed: {e}",
                    checked_at=time.time(),
                )
        else:
            # Sem health_fn: inferir do state
            if plugin.state == PluginState.RUNNING:
                plugin.health = PluginHealth(
                    status=PluginHealthStatus.OK,
                    message="Running (no custom health check)",
                    checked_at=time.time(),
                )
            elif plugin.state == PluginState.FAILED:
                plugin.health = PluginHealth(
                    status=PluginHealthStatus.UNHEALTHY,
                    message="Plugin in FAILED state",
                    checked_at=time.time(),
                )
            elif plugin.state == PluginState.DEGRADED:
                plugin.health = PluginHealth(
                    status=PluginHealthStatus.DEGRADED,
                    message="Plugin in DEGRADED state",
                    checked_at=time.time(),
                )
            else:
                plugin.health = PluginHealth(
                    status=PluginHealthStatus.UNKNOWN,
                    message=f"State: {plugin.state.value}",
                    checked_at=time.time(),
                )

        return plugin.health

    def health_check_all(self) -> dict:
        """Executa health check em todos os plugins."""
        return {name: self.health_check(name) for name in self._plugins}

    def get_health(self, name: str) -> Optional[dict]:
        """Retorna health de um plugin como dict."""
        health = self.health_check(name)
        return {
            "status": health.status.value,
            "message": health.message,
            "checked_at": health.checked_at,
            "details": health.details,
        }

    # ─── V2 API — Permissions ────────────────────────────────

    def get_permissions(self, name: str) -> list:
        """Retorna permissões declaradas de um plugin."""
        plugin = self._plugins.get(name)
        if plugin is None:
            return []
        return list(plugin.permissions)

    def has_permission(self, plugin_name: str, permission: str) -> bool:
        """Verifica se um plugin tem uma permissão específica."""
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return False
        return permission in plugin.permissions

    # ─── V2 API — Manifest & Snapshot ────────────────────────

    def get_manifest(self, name: str) -> Optional[PluginManifest]:
        """Retorna o manifest de um plugin."""
        plugin = self._plugins.get(name)
        if plugin is None:
            return None
        return plugin.manifest

    def snapshot(self) -> dict:
        """Retorna snapshot do estado atual de todos os plugins."""
        return {
            name: {
                "name": p.name,
                "description": p.description,
                "enabled": p.enabled,
                "state": p.state.value,
                "health": p.health.status.value,
                "permissions": list(p.permissions),
                "manifest": {
                    "id": p.manifest.id,
                    "name": p.manifest.name,
                    "version": p.manifest.version,
                } if p.manifest else None,
                "source": p.source_file,
            }
            for name, p in self._plugins.items()
        }

    # ─── V2 API — Register with manifest ─────────────────────

    def register_plugin(self, plugin: Plugin):
        """Registra um plugin V2 completo (com manifest/lifecycle)."""
        if plugin.name in self._plugins:
            raise ValueError(f"Duplicate plugin: {plugin.name}")
        self._plugins[plugin.name] = plugin

    # ─── V2 API — Integration with ToolRegistry ──────────────

    def register_tools_in_registry(self, tool_registry):
        """Registra tools de todos os plugins habilitados no ToolRegistry.

        Args:
            tool_registry: Instância de jarvis_core.registry.ToolRegistry
        """
        from jarvis_core.models import Risk, Tool

        for name, plugin in self._plugins.items():
            if not plugin.enabled or plugin.state == PluginState.FAILED:
                continue
            if tool_registry.get(name):
                continue  # tool já existe, não duplicar

            permissions = plugin.permissions
            risk_level = Risk.LOW
            requires_confirmation = False
            if "high_risk" in permissions:
                risk_level = Risk.HIGH
                requires_confirmation = True
            elif "medium_risk" in permissions:
                risk_level = Risk.MEDIUM

            tool = Tool(
                name=name,
                description=plugin.description,
                handler=plugin.execute,
                risk=risk_level,
                confirmation=requires_confirmation,
                parameters={k: str for k in plugin.parameters.get("properties", {}).keys()},
                llm_enabled=True,
                category="plugin",
            )
            tool_registry.register(tool)
            logger.info(f"Registered plugin tool: {name} (risk={risk_level.value})")


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

_registry: Optional[PluginRegistry] = None


def get_plugin_registry(plugins_dir: str = None) -> PluginRegistry:
    """Retorna a instância singleton do PluginRegistry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry(plugins_dir)
    return _registry
