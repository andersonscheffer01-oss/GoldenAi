# Jarvis Plugin Kernel V1

> Plugin system do Jarvis — manifest, lifecycle, health, permissions.
> Backward compatible com plugins existentes.

---

## Arquitetura

```
plugins/
├── plugin_loader.py    # Registry único (estendido com V2)
├── __init__.py         # Exporta tipos V2
├── crypto_price.py     # Plugin existente (compatível)
├── system_info.py      # Plugin existente (compatível)
└── backups/            # Backups antes de alterações
```

**UM registry oficial:** `PluginRegistry` em `plugins/plugin_loader.py`

**NÃO existe segundo sistema paralelo.**

---

## Plugin V1 (Legado — continua funcionando)

Plugins existentes usam este contrato mínimo:

```python
# plugins/meu_plugin.py
name = "minha_tool"
description = "Descrição para o LLM"
parameters = {
    "type": "object",
    "properties": {
        "input": {"type": "string", "description": "Entrada"}
    },
    "required": []
}

def execute(args):
    return {"result": args.get("input", "")}
```

Sem necessidade de manifest, lifecycle ou permissions.

---

## Plugin V2 (Kernel — opcional)

Plugins V2 adicionam manifest, lifecycle e permissions:

```python
# plugins/meu_plugin_v2.py
from plugin_loader import PluginManifest, PluginHealth, PluginHealthStatus
import time

name = "minha_tool_v2"
description = "Descrição para o LLM"
parameters = {
    "type": "object",
    "properties": {
        "query": {"type": "string"}
    },
    "required": []
}

# Manifest (obrigatório para V2)
manifest = PluginManifest(
    id="meu_plugin_v2",
    name="minha_tool_v2",
    version="1.0.0",
    description="Meu plugin V2",
    capabilities=["data_retrieval"],
    permissions=["read_only"],
)

# Permissions (lista de strings)
permissions = ["read_only"]

# Lifecycle (opcionais)
def plugin_start():
    """Chamado quando o plugin é iniciado."""
    pass

def plugin_stop():
    """Chamado quando o plugin é parado."""
    pass

def plugin_health():
    """Health check customizado."""
    return PluginHealth(
        status=PluginHealthStatus.OK,
        message="Saudável",
        checked_at=time.time(),
    )

def execute(args):
    return {"result": "ok"}
```

---

## Manifest

```python
@dataclass
class PluginManifest:
    id: str           # ID único (obrigatório)
    name: str         # Nome (obrigatório)
    version: str      # Versão (default: "0.1.0")
    description: str  # Descrição
    author: str       # Autor
    capabilities: list  # Capacidades do plugin
    permissions: list   # Permissões necessárias
    enabled: bool       # Habilitado (default: True)
    dependencies: list  # Dependências
```

Validação: `manifest.validate()` retorna lista de erros.

---

## Lifecycle States

```
DISCOVERED → LOADED → STARTING → RUNNING
                                  ↓
                             STOPPING → STOPPED
                                  ↓
                               FAILED
                                  ↓
                              DEGRADED
```

| State | Descrição |
|-------|-----------|
| DISCOVERED | Plugin encontrado no disco |
| LOADED | Módulo Python carregado |
| STARTING | Iniciando (chamando plugin_start) |
| RUNNING | Rodando e saudável |
| STOPPING | Parando (chamando plugin_stop) |
| STOPPED | Parado |
| DEGRADED | Funcionando com problemas |
| FAILED | Falhou (execução ou start/stop) |

---

## Health Status

| Status | Descrição |
|--------|-----------|
| ok | Saudável |
| degraded | Funcionando com problemas |
| unhealthy | Não saudável |
| unknown | Sem informação |

Health check customizado via `plugin_health()` retorna `PluginHealth` ou `dict`.

---

## Permissions

Permissions são strings declaradas no plugin:

```python
permissions = ["read_only", "network", "high_risk"]
```

**Permissions são METADADOS apenas.**

O `SecurityManager` continua sendo a autoridade.
Permissions são usadas para:
- Classificar risk level da tool
- Metadata em `list_plugins()` e `snapshot()`
- Decisão de approval (futuro)

| Permission | Efeito no Risk |
|-----------|---------------|
| `high_risk` | Risk.HIGH → requer confirmação |
| `medium_risk` | Risk.MEDIUM |
| `read_only` | Risk.LOW (default) |
| `network` | Risk.LLOW (default) |

---

## API do Registry

### Original (preservada)

```python
registry = get_plugin_registry("plugins/")

registry.register(name, description, parameters, execute)
registry.get(name)                    # → Plugin
registry.execute(name, args)          # → Any
registry.list_tools()                 # → list (Ollama format)
registry.list_plugins()               # → list
registry.enable(name)                 # → bool
registry.disable(name)                # → bool
registry.reload()                     # → None
```

### V2 (kernel)

```python
# Lifecycle
registry.start(name)                  # → bool
registry.stop(name)                   # → bool
registry.start_all()                  # → dict
registry.stop_all()                   # → dict

# Health
registry.health_check(name)           # → PluginHealth
registry.health_check_all()           # → dict
registry.get_health(name)             # → dict

# Permissions
registry.get_permissions(name)        # → list
registry.has_permission(name, perm)   # → bool

# Manifest
registry.get_manifest(name)           # → PluginManifest

# Snapshot
registry.snapshot()                   # → dict

# Register V2 plugin
registry.register_plugin(plugin)      # → None

# Integration with ToolRegistry
registry.register_tools_in_registry(tool_registry)  # → None
```

---

## Integração com ToolRegistry

```python
from jarvis_core.registry import ToolRegistry
from plugins.plugin_loader import get_plugin_registry

tool_registry = ToolRegistry()
plugin_registry = get_plugin_registry()

# Iniciar plugins
plugin_registry.start_all()

# Registrar tools dos plugins no ToolRegistry
plugin_registry.register_tools_in_registry(tool_registry)

# Agora as tools estão disponíveis para o JarvisBrain
```

---

## Criar um Plugin

### Passo 1: Criar arquivo .py

```python
# plugins/meu_plugin.py
name = "minha_tool"
description = "O que minha tool faz"
parameters = {
    "type": "object",
    "properties": {
        "input": {"type": "string"}
    },
    "required": []
}

def execute(args):
    return {"result": "ok"}
```

### Passo 2: Recarregar

```python
registry.reload()
```

### Passo 3: Verificar

```python
registry.list_plugins()  # deve incluir "minha_tool"
registry.execute("minha_tool", {"input": "teste"})
```

---

## Criar um Plugin V2

### Passo 1: Criar arquivo com manifest

```python
# plugins/meu_v2.py
from plugin_loader import PluginManifest, PluginHealth, PluginHealthStatus
import time

name = "meu_v2"
description = "Plugin V2"
parameters = {"type": "object", "properties": {"q": {"type": "string"}}}

manifest = PluginManifest(
    id="meu_v2", name="meu_v2", version="1.0.0",
    description="Meu plugin V2",
    capabilities=["search"],
    permissions=["read_only"],
)
permissions = ["read_only"]

def plugin_start():
    print("Plugin started!")

def plugin_stop():
    print("Plugin stopped!")

def plugin_health():
    return PluginHealth(
        status=PluginHealthStatus.OK,
        message="OK",
        checked_at=time.time(),
    )

def execute(args):
    return {"q": args.get("q", "")}
```

### Passo 2: Recarregar e iniciar

```python
registry.reload()
registry.start("meu_v2")
registry.health_check("meu_v2")
```

---

## Compatibilidade

- Plugins V1 continuam funcionando sem alterações
- `list_plugins()` retorna campos originais + novos (`state`, `health`)
- `execute()` funciona igual
- `get()` retorna Plugin com campos V2 como opcionais
- Nenhum plugin existente precisa de migração

---

## Backups

Antes de alterar `plugin_loader.py`, backups são criados em:
`plugins/backups/pre_kernel_YYYYMMDD_HHMMSS/`
