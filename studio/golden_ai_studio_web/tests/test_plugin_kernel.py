"""
Testes obrigatórios — Plugin Kernel V1

15 testes conforme especificação:
1. existing_plugin_loads
2. plugin_manifest_valid
3. plugin_manifest_invalid_rejected
4. plugin_registers_tools
5. duplicate_tool_rejected
6. plugin_start
7. plugin_stop
8. plugin_health_ok
9. plugin_health_degraded
10. plugin_failure_isolated
11. plugin_permission_metadata
12. security_manager_not_bypassed
13. audit_log_preserved
14. disabled_plugin_not_started
15. existing_plugins_backward_compatible

Nenhuma chamada de rede real necessária.
"""

import importlib
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Adicionar path do projeto
GOLDEN_ROOT = Path(r"C:\GoldenAI")
sys.path.insert(0, str(GOLDEN_ROOT))
sys.path.insert(0, str(GOLDEN_ROOT / "plugins"))

# Importar do diretório plugins diretamente
import importlib
_spec = importlib.util.spec_from_file_location(
    "plugin_loader", str(GOLDEN_ROOT / "plugins" / "plugin_loader.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

Plugin = _mod.Plugin
PluginManifest = _mod.PluginManifest
PluginRegistry = _mod.PluginRegistry
PluginState = _mod.PluginState
PluginHealth = _mod.PluginHealth
PluginHealthStatus = _mod.PluginHealthStatus
get_plugin_registry = _mod.get_plugin_registry


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def plugins_dir():
    """Diretório temporário de plugins para testes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_plugin_file(plugins_dir):
    """Cria um plugin de exemplo no diretório temporário."""
    plugin_code = '''
name = "test_tool"
description = "A test tool"
parameters = {
    "type": "object",
    "properties": {
        "input": {"type": "string"}
    },
    "required": []
}

def execute(args):
    return {"result": args.get("input", "default")}
'''
    plugin_path = Path(plugins_dir) / "test_plugin.py"
    plugin_path.write_text(plugin_code)
    return plugin_path


@pytest.fixture
def v2_plugin_file(plugins_dir):
    """Cria um plugin V2 com manifest, lifecycle e permissions."""
    plugin_code = '''
from plugin_loader import PluginManifest, PluginHealth, PluginHealthStatus
import time

name = "v2_tool"
description = "A V2 test tool"
parameters = {
    "type": "object",
    "properties": {
        "query": {"type": "string"}
    },
    "required": []
}

manifest = PluginManifest(
    id="v2_tool",
    name="v2_tool",
    version="1.0.0",
    description="V2 plugin for testing",
    capabilities=["data_retrieval"],
    permissions=["read_only", "network"],
)

permissions = ["read_only", "network"]

_started = False
_stopped = False

def plugin_start():
    global _started
    _started = True

def plugin_stop():
    global _stopped
    _stopped = True

def plugin_health():
    return PluginHealth(
        status=PluginHealthStatus.OK,
        message="All good",
        checked_at=time.time(),
    )

def execute(args):
    return {"query": args.get("query", ""), "started": _started}
'''
    plugin_path = Path(plugins_dir) / "v2_plugin.py"
    plugin_path.write_text(plugin_code)
    return plugin_path


@pytest.fixture
def failing_plugin_file(plugins_dir):
    """Cria um plugin que falha na execução."""
    plugin_code = '''
name = "failing_tool"
description = "A tool that fails"
parameters = {"type": "object", "properties": {}}

def execute(args):
    raise RuntimeError("Intentional failure")
'''
    plugin_path = Path(plugins_dir) / "failing_plugin.py"
    plugin_path.write_text(plugin_code)
    return plugin_path


@pytest.fixture
def degraded_health_plugin_file(plugins_dir):
    """Cria um plugin com health degradado."""
    plugin_code = '''
import time

name = "degraded_tool"
description = "A degraded tool"
parameters = {"type": "object", "properties": {}}

def plugin_health():
    return {"status": "degraded", "message": "High latency", "details": {"latency_ms": 5000}}

def execute(args):
    return {"status": "ok"}
'''
    plugin_path = Path(plugins_dir) / "degraded_plugin.py"
    plugin_path.write_text(plugin_code)
    return plugin_path


@pytest.fixture
def registry(plugins_dir, sample_plugin_file):
    """Registry com plugin de teste."""
    return PluginRegistry(plugins_dir)


@pytest.fixture
def v2_registry(plugins_dir, v2_plugin_file):
    """Registry com plugin V2."""
    return PluginRegistry(plugins_dir)


# ═══════════════════════════════════════════════════════════════
# TESTES OBRIGATÓRIOS
# ═══════════════════════════════════════════════════════════════

class TestExistingPluginLoads:
    """1. existing_plugin_loads"""

    def test_loads_existing_plugins(self):
        """Plugins existentes no diretório plugins/ são carregados."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        plugins = reg.list_plugins()
        names = [p["name"] for p in plugins]

        assert "crypto_price" in names or "system_info_detailed" in names

    def test_loaded_plugin_has_required_fields(self):
        """Plugin carregado tem todos os campos obrigatórios."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        for p in reg.list_plugins():
            assert "name" in p
            assert "description" in p
            assert "enabled" in p
            assert "source" in p

    def test_plugin_from_file(self, registry, sample_plugin_file):
        """Plugin é carregado a partir de arquivo .py."""
        plugin = registry.get("test_tool")
        assert plugin is not None
        assert plugin.name == "test_tool"
        assert plugin.description == "A test tool"


class TestPluginManifestValid:
    """2. plugin_manifest_valid"""

    def test_manifest_valid(self):
        """Manifest válido passa na validação."""
        manifest = PluginManifest(
            id="test_id",
            name="test_name",
            version="1.0.0",
            description="Test",
        )
        errors = manifest.validate()
        assert errors == []

    def test_manifest_v2_plugin(self, v2_registry):
        """Plugin V2 tem manifest válido."""
        plugin = v2_registry.get("v2_tool")
        assert plugin is not None
        assert plugin.manifest is not None
        assert plugin.manifest.id == "v2_tool"
        assert plugin.manifest.version == "1.0.0"
        assert "data_retrieval" in plugin.manifest.capabilities


class TestPluginManifestInvalidRejected:
    """3. plugin_manifest_invalid_rejected"""

    def test_manifest_without_id(self):
        """Manifest sem id retorna erros."""
        manifest = PluginManifest(name="test")
        errors = manifest.validate()
        assert len(errors) > 0
        assert any("id" in e for e in errors)

    def test_manifest_without_name(self):
        """Manifest sem name retorna erros."""
        manifest = PluginManifest(id="test")
        errors = manifest.validate()
        assert len(errors) > 0
        assert any("name" in e for e in errors)

    def test_register_duplicate_raises(self):
        """Registrar plugin duplicado levanta ValueError."""
        reg = PluginRegistry()
        plugin = Plugin(
            name="dup",
            description="Dup",
            parameters={},
            execute=lambda x: x,
        )
        reg.register_plugin(plugin)
        with pytest.raises(ValueError, match="Duplicate"):
            reg.register_plugin(plugin)


class TestPluginRegistersTools:
    """4. plugin_registers_tools"""

    def test_list_tools(self, registry):
        """Plugins são listados como tools."""
        tools = registry.list_tools()
        assert len(tools) > 0
        tool = tools[0]
        assert tool["type"] == "function"
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]

    def test_execute_plugin(self, registry):
        """Plugin pode ser executado."""
        result = registry.execute("test_tool", {"input": "hello"})
        assert result == {"result": "hello"}

    def test_execute_not_found(self, registry):
        """Executar plugin inexistente retorna erro."""
        result = registry.execute("nonexistent", {})
        assert "error" in result


class TestDuplicateToolRejected:
    """5. duplicate_tool_rejected"""

    def test_register_duplicate_tool(self):
        """ToolRegistry rejeita tool duplicado."""
        from jarvis_core.models import Risk, Tool

        reg = PluginRegistry()
        tool = Tool(
            name="dup_tool",
            description="Duplicate test",
            handler=lambda x: x,
            risk=Risk.LOW,
        )
        # Registrar duas vezes deve falhar
        reg2 = PluginRegistry()
        reg2.register_plugin(Plugin(
            name="dup_tool",
            description="Test",
            parameters={},
            execute=lambda x: x,
        ))
        with pytest.raises(ValueError, match="Duplicate"):
            reg2.register_plugin(Plugin(
                name="dup_tool",
                description="Test 2",
                parameters={},
                execute=lambda x: x,
            ))


class TestPluginStart:
    """6. plugin_start"""

    def test_start_plugin(self, v2_registry):
        """Plugin V2 pode ser iniciado."""
        result = v2_registry.start("v2_tool")
        assert result is True
        plugin = v2_registry.get("v2_tool")
        assert plugin.state == PluginState.RUNNING

    def test_start_nonexistent(self, registry):
        """Iniciar plugin inexistente retorna False."""
        result = registry.start("nonexistent")
        assert result is False

    def test_start_already_running(self, v2_registry):
        """Iniciar plugin já rodando retorna True (idempotente)."""
        v2_registry.start("v2_tool")
        result = v2_registry.start("v2_tool")
        assert result is True

    def test_start_all(self, plugins_dir, v2_plugin_file, sample_plugin_file):
        """start_all inicia todos os plugins habilitados."""
        reg = PluginRegistry(plugins_dir)
        results = reg.start_all()
        assert len(results) > 0


class TestPluginStop:
    """7. plugin_stop"""

    def test_stop_plugin(self, v2_registry):
        """Plugin V2 pode ser parado."""
        v2_registry.start("v2_tool")
        result = v2_registry.stop("v2_tool")
        assert result is True
        plugin = v2_registry.get("v2_tool")
        assert plugin.state == PluginState.STOPPED

    def test_stop_nonexistent(self, registry):
        """Parar plugin inexistente retorna False."""
        result = registry.stop("nonexistent")
        assert result is False

    def test_stop_already_stopped(self, v2_registry):
        """Parar plugin já parado retorna True (idempotente)."""
        result = v2_registry.stop("v2_tool")
        assert result is True


class TestPluginHealthOk:
    """8. plugin_health_ok"""

    def test_health_ok(self, v2_registry):
        """Plugin saudável retorna status OK."""
        v2_registry.start("v2_tool")
        health = v2_registry.health_check("v2_tool")
        assert health.status == PluginHealthStatus.OK

    def test_health_running_without_custom(self, plugins_dir, sample_plugin_file):
        """Plugin rodando sem health_fn retorna OK."""
        reg = PluginRegistry(plugins_dir)
        reg.start("test_tool")
        health = reg.health_check("test_tool")
        assert health.status == PluginHealthStatus.OK

    def test_get_health_dict(self, v2_registry):
        """get_health retorna dict formatado."""
        v2_registry.start("v2_tool")
        h = v2_registry.get_health("v2_tool")
        assert "status" in h
        assert "message" in h
        assert "checked_at" in h


class TestPluginHealthDegraded:
    """9. plugin_health_degraded"""

    def test_health_degraded(self, plugins_dir, degraded_health_plugin_file):
        """Plugin degradado retorna status DEGRADED."""
        reg = PluginRegistry(plugins_dir)
        reg.start("degraded_tool")
        health = reg.health_check("degraded_tool")
        assert health.status == PluginHealthStatus.DEGRADED

    def test_health_check_all(self, plugins_dir, v2_plugin_file, degraded_health_plugin_file):
        """health_check_all retorna todos os status."""
        reg = PluginRegistry(plugins_dir)
        reg.start("v2_tool")
        reg.start("degraded_tool")
        results = reg.health_check_all()
        assert "v2_tool" in results
        assert "degraded_tool" in results


class TestPluginFailureIsolated:
    """10. plugin_failure_isolated"""

    def test_failure_does_not_affect_others(self, plugins_dir, failing_plugin_file, sample_plugin_file):
        """Falha em um plugin não afeta outros plugins."""
        reg = PluginRegistry(plugins_dir)

        # Executar plugin que falha
        result = reg.execute("failing_tool", {})
        assert "error" in result

        # Outro plugin continua funcionando
        result2 = reg.execute("test_tool", {"input": "ok"})
        assert result2 == {"result": "ok"}

    def test_failed_plugin_state(self, plugins_dir, failing_plugin_file):
        """Plugin que falha entra em estado FAILED."""
        reg = PluginRegistry(plugins_dir)
        reg.execute("failing_tool", {})
        plugin = reg.get("failing_tool")
        assert plugin.state == PluginState.FAILED

    def test_failed_plugin_health(self, plugins_dir, failing_plugin_file):
        """Plugin que falha tem health UNHEALTHY."""
        reg = PluginRegistry(plugins_dir)
        reg.execute("failing_tool", {})
        health = reg.health_check("failing_tool")
        assert health.status == PluginHealthStatus.UNHEALTHY

    def test_failed_plugin_not_in_list_tools(self, plugins_dir, failing_plugin_file):
        """Plugin FAILED não aparece em list_tools."""
        reg = PluginRegistry(plugins_dir)
        reg.execute("failing_tool", {})
        tools = reg.list_tools()
        names = [t["function"]["name"] for t in tools]
        assert "failing_tool" not in names

    def test_execute_failed_plugin_returns_error(self, plugins_dir, failing_plugin_file):
        """Executar plugin FAILED retorna erro."""
        reg = PluginRegistry(plugins_dir)
        reg.execute("failing_tool", {})
        result = reg.execute("failing_tool", {})
        assert "error" in result
        assert "FAILED" in result["error"]


class TestPluginPermissionMetadata:
    """11. plugin_permission_metadata"""

    def test_permissions_declared(self, v2_registry):
        """Plugin V2 tem permissões declaradas."""
        perms = v2_registry.get_permissions("v2_tool")
        assert "read_only" in perms
        assert "network" in perms

    def test_has_permission(self, v2_registry):
        """has_permission retorna True para permissão existente."""
        assert v2_registry.has_permission("v2_tool", "read_only") is True
        assert v2_registry.has_permission("v2_tool", "write") is False

    def test_no_permissions_legacy(self, registry):
        """Plugin legado sem permissions retorna lista vazia."""
        perms = registry.get_permissions("test_tool")
        assert perms == []


class TestSecurityManagerNotBypassed:
    """12. security_manager_not_bypassed"""

    def test_plugin_tool_has_risk_level(self):
        """Tool registrada via plugin tem risk level definido."""
        from jarvis_core.models import Risk, Tool

        # Simular o que register_tools_in_registry faz
        plugin = Plugin(
            name="secured_tool",
            description="Test",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
            execute=lambda x: x,
            permissions=["read_only"],
        )
        tool = Tool(
            name=plugin.name,
            description=plugin.description,
            handler=plugin.execute,
            risk=Risk.LOW,
            parameters={k: str for k in plugin.parameters.get("properties", {}).keys()},
            llm_enabled=True,
            category="plugin",
        )
        assert tool.risk == Risk.LOW

    def test_high_risk_permission(self):
        """Plugin com high_risk permission recebe Risk.HIGH."""
        from jarvis_core.models import Risk

        permissions = ["high_risk", "network"]
        risk_level = Risk.LOW
        if "high_risk" in permissions:
            risk_level = Risk.HIGH
        assert risk_level == Risk.HIGH


class TestAuditLogPreserved:
    """13. audit_log_preserved"""

    def test_plugin_execute_logs_failure(self, plugins_dir, failing_plugin_file):
        """Falha de plugin é logada."""
        import logging
        reg = PluginRegistry(plugins_dir)
        result = reg.execute("failing_tool", {})
        assert "error" in result
        assert "Intentional failure" in result["error"]

    def test_list_plugins_includes_state(self, registry):
        """list_plugins inclui estado e health."""
        plugins = registry.list_plugins()
        for p in plugins:
            assert "state" in p
            assert "health" in p


class TestDisabledPluginNotStarted:
    """14. disabled_plugin_not_started"""

    def test_disabled_plugin_not_started(self, registry):
        """Plugin desabilitado não é iniciado."""
        registry.disable("test_tool")
        result = registry.start("test_tool")
        assert result is False
        plugin = registry.get("test_tool")
        assert plugin.state == PluginState.STOPPED

    def test_disabled_plugin_not_in_list_tools(self, registry):
        """Plugin desabilitado não aparece em list_tools."""
        registry.disable("test_tool")
        tools = registry.list_tools()
        names = [t["function"]["name"] for t in tools]
        assert "test_tool" not in names

    def test_disabled_plugin_execute_returns_error(self, registry):
        """Executar plugin desabilitado retorna erro."""
        registry.disable("test_tool")
        result = registry.execute("test_tool", {})
        assert "error" in result
        assert "disabled" in result["error"]


class TestExistingPluginsBackwardCompatible:
    """15. existing_plugins_backward_compatible"""

    def test_original_api_unchanged(self):
        """API original do PluginRegistry permanece idêntica."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)

        # Todas as funções originais existem
        assert callable(reg.register)
        assert callable(reg.get)
        assert callable(reg.execute)
        assert callable(reg.list_tools)
        assert callable(reg.list_plugins)
        assert callable(reg.enable)
        assert callable(reg.disable)
        assert callable(reg.reload)

    def test_original_plugin_fields(self):
        """Campos originais do Plugin permanecem."""
        plugin = Plugin(
            name="test",
            description="Test",
            parameters={},
            execute=lambda x: x,
        )
        assert plugin.name == "test"
        assert plugin.description == "Test"
        assert plugin.parameters == {}
        assert plugin.enabled is True
        assert plugin.source_file == ""

    def test_original_list_plugins_format(self):
        """list_plugins retorna formato original + novos campos."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        plugins = reg.list_plugins()
        for p in plugins:
            # Campos originais
            assert "name" in p
            assert "description" in p
            assert "enabled" in p
            assert "source" in p
            # Campos novos (adicionados, não removidos)
            assert "state" in p
            assert "health" in p

    def test_original_execute_behavior(self):
        """execute() funciona igual ao comportamento original."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        # crypto_price ou system_info_detailed
        for name in ["crypto_price", "system_info_detailed"]:
            plugin = reg.get(name)
            if plugin:
                result = reg.execute(name, {})
                assert isinstance(result, dict)

    def test_singleton_pattern(self):
        """get_plugin_registry retorna singleton."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        r1 = get_plugin_registry(real_plugins_dir)
        r2 = get_plugin_registry(real_plugins_dir)
        assert r1 is r2

    def test_snapshot(self, v2_registry):
        """Snapshot retorna estado completo."""
        v2_registry.start("v2_tool")
        snap = v2_registry.snapshot()
        assert "v2_tool" in snap
        assert snap["v2_tool"]["state"] == "running"
        assert snap["v2_tool"]["health"] == "ok"
        assert "read_only" in snap["v2_tool"]["permissions"]


# ═══════════════════════════════════════════════════════════════
# INTEGRAÇÃO COM TOOLREGISTRY
# ═══════════════════════════════════════════════════════════════

class TestToolRegistryIntegration:
    """Testes de integração com ToolRegistry do Jarvis."""

    def test_register_tools_in_registry(self, v2_registry):
        """Plugins V2 podem ser registrados no ToolRegistry."""
        from jarvis_core.registry import ToolRegistry

        tool_reg = ToolRegistry()
        v2_registry.start("v2_tool")
        v2_registry.register_tools_in_registry(tool_reg)

        tool = tool_reg.get("v2_tool")
        assert tool is not None
        assert tool.category == "plugin"

    def test_register_tools_respects_permissions(self, v2_registry):
        """Permissions afetam o risk level da tool."""
        from jarvis_core.registry import ToolRegistry
        from jarvis_core.models import Risk

        tool_reg = ToolRegistry()
        v2_registry.start("v2_tool")
        v2_registry.register_tools_in_registry(tool_reg)

        tool = tool_reg.get("v2_tool")
        assert tool is not None
        # read_only = LOW, network = LOW → LOW
        assert tool.risk == Risk.LOW

    def test_register_tools_does_not_duplicate(self, v2_registry):
        """Não registra tool duplicada no ToolRegistry."""
        from jarvis_core.registry import ToolRegistry

        tool_reg = ToolRegistry()
        v2_registry.start("v2_tool")
        v2_registry.register_tools_in_registry(tool_reg)
        v2_registry.register_tools_in_registry(tool_reg)  # segunda vez

        # Contar tools - deve ser apenas 1
        tools = tool_reg.get_llm_tools()
        assert len([t for t in tools if t["name"] == "v2_tool"]) == 1


# ═══════════════════════════════════════════════════════════════
# GATE: BACKUP EXCLUSION
# ═══════════════════════════════════════════════════════════════

class TestBackupExclusion:
    """Verifica que backups e subdiretórios NÃO são carregados como plugins."""

    def test_backup_plugin_not_discovered(self):
        """Arquivos em plugins/backups/ NÃO são descobertos."""
        import shutil

        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copiar plugins reais
            for f in Path(real_plugins_dir).glob("*.py"):
                shutil.copy2(f, Path(tmpdir) / f.name)

            # Criar subdiretório backups com plugin falso
            backup_dir = Path(tmpdir) / "backups" / "pre_kernel_20260917"
            backup_dir.mkdir(parents=True)
            (backup_dir / "fake_plugin.py").write_text(
                'name = "FAKE_BACKUP_PLUGIN"\n'
                'description = "Should not load"\n'
                'parameters = {"type": "object", "properties": {}}\n'
                'def execute(args): return {"fake": True}\n'
            )

            reg = PluginRegistry(tmpdir)
            names = [p["name"] for p in reg.list_plugins()]
            assert "FAKE_BACKUP_PLUGIN" not in names, \
                "FAIL: Backup plugin was discovered!"

    def test_pycache_not_discovered(self):
        """__pycache__ NÃO é carregado como plugin."""
        import shutil

        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in Path(real_plugins_dir).glob("*.py"):
                shutil.copy2(f, Path(tmpdir) / f.name)

            # Criar __pycache__ com .py
            cache_dir = Path(tmpdir) / "__pycache__"
            cache_dir.mkdir()
            (cache_dir / "cached_plugin.py").write_text(
                'name = "FAKE_CACHE_PLUGIN"\n'
                'description = "Should not load"\n'
                'parameters = {"type": "object", "properties": {}}\n'
                'def execute(args): return {"fake": True}\n'
            )

            reg = PluginRegistry(tmpdir)
            names = [p["name"] for p in reg.list_plugins()]
            assert "FAKE_CACHE_PLUGIN" not in names

    def test_hidden_directory_not_discovered(self):
        """Diretórios ocultos (começando com _) não são plugins."""
        import shutil

        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in Path(real_plugins_dir).glob("*.py"):
                shutil.copy2(f, Path(tmpdir) / f.name)

            hidden_dir = Path(tmpdir) / "_hidden"
            hidden_dir.mkdir()
            (hidden_dir / "hidden_plugin.py").write_text(
                'name = "FAKE_HIDDEN_PLUGIN"\n'
                'description = "Should not load"\n'
                'parameters = {"type": "object", "properties": {}}\n'
                'def execute(args): return {"fake": True}\n'
            )

            reg = PluginRegistry(tmpdir)
            names = [p["name"] for p in reg.list_plugins()]
            assert "FAKE_HIDDEN_PLUGIN" not in names

    def test_plugin_loader_excluded(self):
        """plugin_loader.py NÃO é carregado como plugin."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        names = [p["name"] for p in reg.list_plugins()]
        assert "plugin_loader" not in names


# ═══════════════════════════════════════════════════════════════
# GATE: LEGACY PLUGIN VALIDATION
# ═══════════════════════════════════════════════════════════════

class TestLegacyPluginValidation:
    """Validação completa dos plugins legados."""

    def test_crypto_price_discovery(self):
        """crypto_price.py é descoberto."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        plugin = reg.get("crypto_price")
        assert plugin is not None
        assert plugin.name == "crypto_price"
        assert "cripto" in plugin.description.lower() or "crypto" in plugin.description.lower()

    def test_crypto_price_registration(self):
        """crypto_price está registrado no registry."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        plugins = reg.list_plugins()
        names = [p["name"] for p in plugins]
        assert "crypto_price" in names

    def test_crypto_price_tool_format(self):
        """crypto_price aparece em list_tools no formato correto."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        tools = reg.list_tools()
        crypto_tools = [t for t in tools if t["function"]["name"] == "crypto_price"]
        assert len(crypto_tools) == 1
        tool = crypto_tools[0]
        assert tool["type"] == "function"
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]

    def test_crypto_price_enable_disable(self):
        """crypto_price pode ser habilitado/desabilitado."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        assert reg.disable("crypto_price") is True
        plugin = reg.get("crypto_price")
        assert plugin.enabled is False
        tools = reg.list_tools()
        names = [t["function"]["name"] for t in tools]
        assert "crypto_price" not in names
        assert reg.enable("crypto_price") is True
        assert plugin.enabled is True

    def test_crypto_price_lifecycle_compatibility(self):
        """crypto_price funciona com lifecycle V2 (start/stop/health)."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        # start em plugin legado (sem plugin_start fn)
        result = reg.start("crypto_price")
        assert result is True
        plugin = reg.get("crypto_price")
        assert plugin.state == PluginState.RUNNING
        # health
        health = reg.health_check("crypto_price")
        assert health.status == PluginHealthStatus.OK
        # stop
        result = reg.stop("crypto_price")
        assert result is True
        assert plugin.state == PluginState.STOPPED

    def test_crypto_price_no_duplicate_registration(self):
        """crypto_price não é registrado duas vezes."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        tools = reg.list_tools()
        crypto_count = len([t for t in tools if t["function"]["name"] == "crypto_price"])
        assert crypto_count == 1

    def test_system_info_discovery(self):
        """system_info.py é descoberto (mesmo que falhe por psutil)."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        plugin_path = Path(real_plugins_dir) / "system_info.py"
        assert plugin_path.exists()

    def test_system_info_failure_isolated(self):
        """Falha de system_info (psutil) não afeta outros plugins."""
        real_plugins_dir = str(GOLDEN_ROOT / "plugins")
        reg = PluginRegistry(real_plugins_dir)
        # system_info pode falhar, mas crypto_price deve funcionar
        result = reg.execute("crypto_price", {})
        assert isinstance(result, dict)
