"""
Golden AI Plugin System
Carrega plugins dinamicamente do diretório plugins/

V2 — Plugin Kernel: manifest, lifecycle, health, permissions
"""
from .plugin_loader import (
    PluginRegistry,
    get_plugin_registry,
    Plugin,
    PluginManifest,
    PluginState,
    PluginHealth,
    PluginHealthStatus,
)

__all__ = [
    'PluginRegistry',
    'get_plugin_registry',
    'Plugin',
    'PluginManifest',
    'PluginState',
    'PluginHealth',
    'PluginHealthStatus',
]
