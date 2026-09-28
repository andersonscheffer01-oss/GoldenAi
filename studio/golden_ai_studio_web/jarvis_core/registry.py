import inspect

from .models import Risk, SideEffectClass, Tool

class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, tool: Tool):
        if tool.name in self._tools:
            raise ValueError(f"Ferramenta duplicada: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name):
        return self._tools.get(name)

    @staticmethod
    def _effective_side_effect(tool: Tool) -> str:
        """Return impact metadata without turning metadata into authority."""
        if tool.side_effect_class:
            return str(tool.side_effect_class)
        name = str(tool.name or "").casefold()
        local_mutations = (
            "browser_click", "browser_type", "browser_navigate", "keyboard_",
            "mouse_", "clipboard_set", "ui_type_", "ui_invoke_", "ui_focus_",
            "open_", "close_", "move_", "copy_", "rename_", "delete_",
            "create_", "volume_", "lock_", "shutdown", "restart", "kill_",
            "memory_remember", "web_research_learn",
        )
        if name.startswith(local_mutations):
            return SideEffectClass.LOCAL_MUTATION.value
        if tool.risk in (Risk.HIGH, Risk.CRITICAL) or tool.confirmation:
            return SideEffectClass.SENSITIVE_OPERATION.value
        return SideEffectClass.READ_ONLY.value

    @classmethod
    def capability_descriptor(cls, tool: Tool) -> dict:
        """Normalize provider metadata for governance and future adapters."""
        return {
            "id": tool.name,
            "name": tool.name,
            "description": tool.description,
            "source": tool.provider,
            "provider": tool.provider,
            "input_schema": {
                "type": "object",
                "properties": {
                    name: {"type": cls._json_type(value_type)}
                    for name, value_type in tool.parameters.items()
                },
                "required": cls._required(tool),
                "additionalProperties": False,
            },
            "output_semantics": tool.response_policy.value,
            "side_effect_class": cls._effective_side_effect(tool),
            "security_requirements": list(tool.security_requirements),
            "approval_requirements": list(tool.approval_requirements),
            "availability": tool.availability,
            "health": tool.health,
            "timeout": tool.timeout,
            "provenance": tool.provenance,
        }

    def capability_catalog(self, names=None):
        allowed = set(names) if names is not None else None
        return [self.capability_descriptor(tool) for tool in self._tools.values()
                if allowed is None or tool.name in allowed]

    def public_catalog(self):
        return [{"name": t.name, "description": t.description, "risk": t.risk.value,
                 "confirmation": t.confirmation, "timeout": t.timeout,
                 "llm_enabled": t.llm_enabled, "parameters": list(t.parameters),
                 "provider": t.provider,
                 "side_effect_class": self._effective_side_effect(t),
                 "availability": t.availability, "health": t.health,
                 "provenance": t.provenance}
                | {"response_policy": t.response_policy.value,
                   "expected_latency_ms": t.expected_latency_ms}
                for t in self._tools.values()]

    @staticmethod
    def _json_type(value):
        return {str: "string", int: "integer", float: "number", bool: "boolean",
                list: "array", dict: "object"}.get(value)

    @staticmethod
    def _required(tool):
        signature = inspect.signature(tool.handler)
        return [name for name in tool.parameters
                if name in signature.parameters
                and signature.parameters[name].default is inspect.Parameter.empty]

    def get_llm_tools(self, names=None):
        allowed = set(names) if names is not None else None
        tools = []
        for tool in self._tools.values():
            if not tool.llm_enabled or (allowed is not None and tool.name not in allowed):
                continue
            properties = {}
            for name, value_type in tool.parameters.items():
                properties[name] = {"type": self._json_type(value_type)}
                description = tool.parameter_descriptions.get(name)
                if description:
                    properties[name]["description"] = description
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": {"type": "object", "properties": properties,
                               "required": self._required(tool),
                               "additionalProperties": False},
            })
        return tools

    def validate(self):
        issues = []
        for name, tool in self._tools.items():
            if not callable(tool.handler):
                issues.append(f"{name}: handler inválido")
            if not isinstance(tool.risk, Risk):
                issues.append(f"{name}: risco inválido")
            if (tool.risk in (Risk.HIGH, Risk.CRITICAL)
                    and not tool.confirmation and not tool.dynamic_risk):
                issues.append(f"{name}: risco alto sem confirmação explícita")
            if tool.llm_enabled:
                for parameter, value_type in tool.parameters.items():
                    if self._json_type(value_type) is None:
                        issues.append(f"{name}.{parameter}: tipo sem schema JSON")
                if set(tool.parameters) - set(inspect.signature(tool.handler).parameters):
                    issues.append(f"{name}: schema diverge do handler")
        return issues
