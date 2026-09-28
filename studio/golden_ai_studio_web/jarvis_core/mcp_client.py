"""Bounded, explicitly configured MCP stdio client.

MCP servers are capability providers only. This module owns transport and
schema hygiene; JarvisService remains the only application execution boundary.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .models import Risk, SideEffectClass, Tool


class McpClientError(RuntimeError):
    """A bounded MCP transport or protocol failure."""


class McpCancelled(McpClientError):
    """The host cancelled the request and the owned process was stopped."""


@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    display_name: str
    command: tuple[str, ...]
    transport: str = "stdio"
    cwd: Optional[str] = None
    enabled: bool = True
    trust_state: str = "approved"
    request_timeout: float = 15.0
    protocol_version: str = "2025-11-25"
    configuration_provenance: str = "explicit_runtime_configuration"
    environment: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "command", tuple(str(item) for item in self.command))
        if self.transport != "stdio":
            raise ValueError("only explicitly configured stdio MCP is supported")
        if not self.server_id or any(char.isspace() for char in self.server_id):
            raise ValueError("server_id must be non-empty and whitespace-free")
        if not self.command:
            raise ValueError("command is required")
        if self.request_timeout <= 0 or self.request_timeout > 120:
            raise ValueError("request_timeout must be between 0 and 120 seconds")


@dataclass(frozen=True)
class McpToolDescriptor:
    server_id: str
    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]
    provider: str
    provenance: str
    declared_annotations: dict[str, Any] = field(default_factory=dict)

    @property
    def namespaced_name(self) -> str:
        return f"mcp:{self.server_id}:{self.name}"


def _schema_type(value: str):
    return {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }.get(value)


def _validate_schema(schema: Any, path: str = "schema") -> None:
    if not isinstance(schema, dict):
        raise McpClientError(f"invalid {path}: expected object")
    schema_type = schema.get("type", "object")
    if not isinstance(schema_type, str) or _schema_type(schema_type) is None:
        raise McpClientError(f"invalid {path}.type")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise McpClientError(f"invalid {path}.properties")
    for name, child in properties.items():
        if not isinstance(name, str) or not name:
            raise McpClientError(f"invalid {path}.properties name")
        _validate_schema(child, f"{path}.properties.{name}")
    required = schema.get("required", [])
    if (not isinstance(required, list) or
            any(not isinstance(item, str) or item not in properties for item in required)):
        raise McpClientError(f"invalid {path}.required")
    additional = schema.get("additionalProperties", True)
    if not isinstance(additional, bool):
        raise McpClientError(f"invalid {path}.additionalProperties")


def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    if not isinstance(arguments, dict):
        raise McpClientError("MCP arguments must be an object")
    properties = schema.get("properties", {})
    missing = [name for name in schema.get("required", []) if name not in arguments]
    if missing:
        raise McpClientError("missing MCP arguments: " + ", ".join(missing))
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            raise McpClientError("unknown MCP arguments: " + ", ".join(unknown))
    for name, value in arguments.items():
        expected = _schema_type(properties.get(name, {}).get("type", "object"))
        if expected is None:
            raise McpClientError(f"unsupported MCP argument schema for {name}")
        if expected is int and isinstance(value, bool):
            raise McpClientError(f"invalid MCP argument type for {name}")
        if not isinstance(value, expected):
            raise McpClientError(f"invalid MCP argument type for {name}")


class McpClient:
    """Own one explicitly approved stdio MCP subprocess."""

    def __init__(self, config: McpServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.server_info: dict[str, Any] = {}
        self.server_capabilities: dict[str, Any] = {}
        self.tools: dict[str, McpToolDescriptor] = {}
        self.quarantined_tools: dict[str, str] = {}
        self.last_health = "unknown"
        self.last_error = ""
        self._next_id = 0
        self._io_lock = threading.RLock()
        self._lines: queue.Queue = queue.Queue()
        self._stderr_lines: list[str] = []
        self._reader_threads: list[threading.Thread] = []

    @property
    def server_id(self) -> str:
        return self.config.server_id

    def _safe_environment(self) -> dict[str, str]:
        # Do not inherit API keys or the full user environment into a provider.
        allowed = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR")
                   if os.environ.get(key)}
        allowed.update({str(key): str(value) for key, value in self.config.environment.items()})
        return allowed

    def start(self) -> dict[str, Any]:
        with self._io_lock:
            if self.process is not None and self.process.poll() is None:
                return self.health()
            if not self.config.enabled:
                raise McpClientError("MCP server is disabled")
            if self.config.trust_state != "approved":
                raise McpClientError("MCP server is not explicitly approved")
            cwd = Path(self.config.cwd).resolve() if self.config.cwd else None
            if cwd is not None and not cwd.is_dir():
                raise McpClientError("MCP server cwd does not exist")
            try:
                self.process = subprocess.Popen(
                    list(self.config.command), cwd=str(cwd) if cwd else None,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    shell=False, env=self._safe_environment())
            except OSError as exc:
                self.last_health, self.last_error = "unavailable", str(exc)
                self.process = None
                raise McpClientError("MCP server failed to start") from exc
            self._start_readers()
            try:
                result = self._request("initialize", {
                    "protocolVersion": self.config.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "golden-jarvis", "version": "1"},
                })
                self.server_info = dict(result.get("serverInfo") or {})
                self.server_capabilities = dict(result.get("capabilities") or {})
                self._notify("notifications/initialized", {})
                self.last_health, self.last_error = "healthy", ""
                return self.health()
            except Exception as exc:
                self.last_health, self.last_error = "unavailable", str(exc)
                self.stop()
                if isinstance(exc, McpClientError):
                    raise
                raise McpClientError("MCP initialization failed") from exc

    def _start_readers(self):
        assert self.process is not None

        def read_stdout():
            try:
                for line in self.process.stdout:
                    self._lines.put(line)
            finally:
                self._lines.put(None)

        def read_stderr():
            try:
                for line in self.process.stderr:
                    self._stderr_lines.append(line.rstrip()[-500:])
                    del self._stderr_lines[:-20]
            except Exception:
                pass

        for target in (read_stdout, read_stderr):
            thread = threading.Thread(target=target, daemon=True)
            self._reader_threads.append(thread)
            thread.start()

    def _send(self, payload: dict[str, Any]):
        if self.process is None or self.process.poll() is not None or self.process.stdin is None:
            raise McpClientError("MCP server is not running")
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _notify(self, method: str, params: dict[str, Any]):
        with self._io_lock:
            self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, Any],
                 cancel_event: Optional[threading.Event] = None) -> dict[str, Any]:
        with self._io_lock:
            self._next_id += 1
            request_id = self._next_id
            self._send({"jsonrpc": "2.0", "id": request_id,
                        "method": method, "params": params})
            deadline = time.monotonic() + self.config.request_timeout
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    self.stop()
                    raise McpCancelled("MCP request cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.stop()
                    raise McpClientError("MCP request timed out")
                try:
                    line = self._lines.get(timeout=min(remaining, 0.05))
                except queue.Empty:
                    continue
                if line is None:
                    self.stop()
                    raise McpClientError("MCP server disconnected")
                try:
                    message = json.loads(line)
                except (TypeError, json.JSONDecodeError) as exc:
                    self.stop()
                    raise McpClientError("MCP server returned invalid JSON") from exc
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise McpClientError("MCP server returned an error")
                result = message.get("result")
                if not isinstance(result, dict):
                    raise McpClientError("MCP result must be an object")
                return result

    def list_tools(self) -> list[McpToolDescriptor]:
        result = self._request("tools/list", {})
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            raise McpClientError("MCP tools/list returned no tool list")
        descriptors = []
        seen = set()
        for raw in raw_tools:
            name = str(raw.get("name") or "<unnamed>") if isinstance(raw, dict) else "<invalid>"
            try:
                if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
                    raise McpClientError("MCP tool missing a valid name")
                name = raw["name"]
                if not name or name in seen or any(char.isspace() for char in name):
                    raise McpClientError("MCP tool name is invalid or duplicated")
                schema = raw.get("inputSchema", {"type": "object", "properties": {}})
                _validate_schema(schema, f"tool {name}")
                seen.add(name)
                descriptor = McpToolDescriptor(
                    server_id=self.server_id, server_name=self.config.display_name,
                    name=name, description=str(raw.get("description") or ""),
                    input_schema=schema, provider=f"mcp:{self.server_id}",
                    provenance=self.config.configuration_provenance,
                    declared_annotations=dict(raw.get("annotations") or {}),
                )
                descriptors.append(descriptor)
            except McpClientError as exc:
                self.quarantined_tools[name] = str(exc)
                self.last_health, self.last_error = "degraded", str(exc)
                raise
        self.tools = {item.name: item for item in descriptors}
        return descriptors

    def _call_tool(self, descriptor: McpToolDescriptor, arguments: dict[str, Any],
                   cancel_event: Optional[threading.Event] = None) -> dict[str, Any]:
        if descriptor.server_id != self.server_id or descriptor.name not in self.tools:
            raise McpClientError("MCP tool is not registered by this server")
        _validate_arguments(descriptor.input_schema, arguments)
        result = self._request("tools/call", {"name": descriptor.name,
                                               "arguments": arguments}, cancel_event)
        content = result.get("content", [])
        if not isinstance(content, list):
            raise McpClientError("MCP tool result content must be a list")
        return {
            "ok": not bool(result.get("isError")),
            "provider": descriptor.provider,
            "server_id": self.server_id,
            "server_name": self.config.display_name,
            "tool": descriptor.name,
            "content": content,
            "structured_content": result.get("structuredContent"),
            "provenance": descriptor.provenance,
        }

    def health(self) -> dict[str, Any]:
        running = self.process is not None and self.process.poll() is None
        return {"server_id": self.server_id, "display_name": self.config.display_name,
                "transport": self.config.transport, "enabled": self.config.enabled,
                "trust_state": self.config.trust_state, "running": running,
                "health": self.last_health, "last_error": self.last_error,
                "server_info": dict(self.server_info)}

    def stop(self):
        with self._io_lock:
            process, self.process = self.process, None
            if process is None:
                return
            try:
                if process.stdin:
                    process.stdin.close()
            except OSError:
                pass
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=1.0)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            self.last_health = "stopped"


class McpClientManager:
    """Own explicitly configured MCP clients; never auto-discovers servers."""

    def __init__(self):
        self._clients: dict[str, McpClient] = {}

    def register_server(self, config: McpServerConfig) -> McpClient:
        if config.server_id in self._clients:
            raise ValueError(f"MCP server already registered: {config.server_id}")
        client = McpClient(config)
        self._clients[config.server_id] = client
        return client

    def get(self, server_id: str) -> Optional[McpClient]:
        return self._clients.get(server_id)

    def start(self, server_id: str) -> dict[str, Any]:
        client = self._require(server_id)
        return client.start()

    def list_tools(self, server_id: str) -> list[McpToolDescriptor]:
        return self._require(server_id).list_tools()

    def health(self) -> list[dict[str, Any]]:
        return [client.health() for client in self._clients.values()]

    def stop(self, server_id: Optional[str] = None):
        clients = ([self._require(server_id)] if server_id else list(self._clients.values()))
        for client in clients:
            client.stop()

    def register_tools(self, service, server_id: str,
                       read_only_tools: set[str] | None = None) -> list[str]:
        """Import validated tools into the canonical Jarvis ToolRegistry.

        ``read_only_tools`` is host policy, not server metadata. Unlisted MCP
        tools remain confirmation-gated even if a server claims they are safe.
        """
        client = self._require(server_id)
        descriptors = client.list_tools()
        safe_read_only = set(read_only_tools or ())
        registered = []
        for descriptor in descriptors:
            is_read_only = descriptor.name in safe_read_only
            tool_name = descriptor.namespaced_name
            schema = descriptor.input_schema
            parameters = {name: _schema_type(value.get("type", "object"))
                          for name, value in schema.get("properties", {}).items()}
            parameters = {name: value for name, value in parameters.items() if value is not None}

            def handler(_descriptor=descriptor, **arguments):
                return client._call_tool(_descriptor, arguments)

            service.registry.register(Tool(
                tool_name, descriptor.description or f"MCP tool {descriptor.name}", handler,
                Risk.LOW if is_read_only else Risk.MEDIUM,
                confirmation=not is_read_only, timeout=int(client.config.request_timeout),
                parameters=parameters, llm_enabled=False, category="mcp",
                provider=descriptor.provider,
                side_effect_class=(SideEffectClass.READ_ONLY.value if is_read_only
                                    else SideEffectClass.SENSITIVE_OPERATION.value),
                security_requirements=("SecurityManager",),
                approval_requirements=(() if is_read_only else ("human_confirmation",)),
                availability="configured", health=client.last_health,
                provenance=descriptor.provenance,
            ))
            registered.append(tool_name)
        return registered

    def _require(self, server_id: str) -> McpClient:
        client = self.get(server_id)
        if client is None:
            raise KeyError(f"unknown MCP server: {server_id}")
        return client

    def close(self):
        self.stop()
