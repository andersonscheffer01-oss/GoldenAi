"""Built-in external tool definitions for GoldenAI.

These definitions register the tools that GoldenAI will orchestrate
in future phases. In this phase, they are metadata only — nothing
is installed, downloaded, or executed.

Each definition includes discovery hints so the auto-discovery
module can detect whether the tool is already present on the
machine without scanning the disk.
"""
from __future__ import annotations

from .definitions import (
    CostPolicy,
    ExecutionMode,
    LocalOrRemote,
    ToolCategory,
    ToolDefinition,
)
from .capability import ToolCapability


def get_builtin_tool_definitions() -> list[ToolDefinition]:
    """Return the list of built-in external tool definitions."""
    return [
        # ----------------------------------------------------------------
        # Ollama — local LLM provider
        # ----------------------------------------------------------------
        ToolDefinition(
            id="ollama",
            name="Ollama",
            category=ToolCategory.LLM,
            description="Local LLM runtime for running models like Qwen, Llama, etc.",
            provider="Ollama",
            execution_mode=ExecutionMode.API,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="ollama",
            capabilities=[
                ToolCapability.CHAT,
                ToolCapability.TOOL_CALLING,
            ],
            permissions_required=["read"],
            cost_policy=CostPolicy.FREE_OR_LOCAL,
            enabled=True,
            priority=10,
            config_hints={
                "which_names": ["ollama", "ollama.exe"],
                "api_url": "http://127.0.0.1:11434",
                "known_paths": [
                    r"C:\Users\{user}\AppData\Local\Programs\Ollama\ollama.exe",
                ],
            },
        ),

        # ----------------------------------------------------------------
        # Codex CLI — coding agent
        # ----------------------------------------------------------------
        ToolDefinition(
            id="codex_cli",
            name="Codex CLI",
            category=ToolCategory.CODING_AGENT,
            description="OpenAI Codex CLI coding agent — supports OSS/local Ollama provider.",
            provider="OpenAI",
            execution_mode=ExecutionMode.CLI,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="codex",
            capabilities=[
                ToolCapability.READ_FILES,
                ToolCapability.WRITE_FILES,
                ToolCapability.EXECUTE_COMMANDS,
                ToolCapability.RUN_TESTS,
                ToolCapability.TOOL_CALLING,
            ],
            permissions_required=["write", "execute"],
            cost_policy=CostPolicy.FREE_OR_LOCAL,
            enabled=True,
            priority=20,
            config_hints={
                "which_names": ["codex", "codex.cmd", "codex.exe"],
                "oss_provider": "ollama",
                "local_only": True,
            },
        ),

        # ----------------------------------------------------------------
        # OpenRouter — external LLM API (free models available)
        # ----------------------------------------------------------------
        ToolDefinition(
            id="openrouter",
            name="OpenRouter",
            category=ToolCategory.LLM,
            description="External LLM API with free and paid models.",
            provider="OpenRouter",
            execution_mode=ExecutionMode.API,
            local_or_remote=LocalOrRemote.REMOTE,
            executable="",
            capabilities=[
                ToolCapability.CHAT,
                ToolCapability.TOOL_CALLING,
            ],
            permissions_required=["read", "internet"],
            cost_policy=CostPolicy.FREEMIUM,
            enabled=True,
            priority=30,
            config_hints={
                "api_url": "https://openrouter.ai/api/v1",
                "api_key_env": "OPENROUTER_API_KEY",
            },
        ),

        # ----------------------------------------------------------------
        # Playwright MCP — browser automation
        # ----------------------------------------------------------------
        ToolDefinition(
            id="playwright_mcp",
            name="Playwright",
            category=ToolCategory.BROWSER,
            description="Browser automation via Playwright (chromium headless) e servico core.browser.",
            provider="Microsoft",
            execution_mode=ExecutionMode.SDK,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="npx",
            capabilities=[
                ToolCapability.BROWSE_WEB,
                ToolCapability.DOWNLOAD,
            ],
            permissions_required=["read", "internet"],
            cost_policy=CostPolicy.FREE,
            enabled=True,
            priority=40,
            config_hints={
                "which_names": ["npx", "npx.cmd"],
                "import_name": "playwright",
                "known_paths": [
                    r"C:\Users\Anderson\AppData\Local\ms-playwright",
                ],
            },
        ),

        # ----------------------------------------------------------------
        # Docling — document parsing
        # ----------------------------------------------------------------
        ToolDefinition(
            id="docling",
            name="Docling",
            category=ToolCategory.DOCUMENT,
            description="Document parsing and conversion (PDF, DOCX, PPTX, XLSX).",
            provider="IBM",
            execution_mode=ExecutionMode.SDK,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="",
            capabilities=[
                ToolCapability.PARSE_DOCUMENTS,
                ToolCapability.READ_FILES,
            ],
            permissions_required=["read"],
            cost_policy=CostPolicy.FREE_OR_LOCAL,
            enabled=True,
            priority=50,
            config_hints={
                "import_name": "docling",
            },
        ),

        # ----------------------------------------------------------------
        # faster-whisper — audio transcription
        # ----------------------------------------------------------------
        ToolDefinition(
            id="whisper",
            name="faster-whisper",
            category=ToolCategory.AUDIO,
            description="Audio transcription via faster-whisper (CT2, local).",
            provider="Systran",
            execution_mode=ExecutionMode.SDK,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="",
            capabilities=[
                ToolCapability.TRANSCRIBE_AUDIO,
            ],
            permissions_required=["read"],
            cost_policy=CostPolicy.FREE_OR_LOCAL,
            enabled=True,
            priority=60,
            config_hints={
                "import_name": "faster_whisper",
            },
        ),

        # ----------------------------------------------------------------
        # FFmpeg — video and media processing (via imageio-ffmpeg)
        # ----------------------------------------------------------------
        ToolDefinition(
            id="ffmpeg",
            name="FFmpeg",
            category=ToolCategory.VIDEO,
            description="Video, audio, and media processing (binario via imageio-ffmpeg).",
            provider="FFmpeg",
            execution_mode=ExecutionMode.CLI,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="ffmpeg",
            capabilities=[
                ToolCapability.PROCESS_VIDEO,
            ],
            permissions_required=["read"],
            cost_policy=CostPolicy.FREE,
            enabled=True,
            priority=70,
            config_hints={
                "which_names": ["ffmpeg", "ffmpeg.exe"],
                "import_name": "imageio_ffmpeg",
                "known_paths": [
                    r"C:\GoldenAI\.venv\Lib\site-packages\imageio_ffmpeg\binaries",
                ],
            },
        ),

        # ----------------------------------------------------------------
        # Qdrant — vector memory database
        # ----------------------------------------------------------------
        ToolDefinition(
            id="qdrant",
            name="Qdrant",
            category=ToolCategory.MEMORY,
            description="Vector search database for semantic memory (modo local embutido).",
            provider="Qdrant",
            execution_mode=ExecutionMode.SDK,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="",
            capabilities=[
                ToolCapability.VECTOR_SEARCH,
            ],
            permissions_required=["read"],
            cost_policy=CostPolicy.FREE_OR_LOCAL,
            enabled=True,
            priority=80,
            config_hints={
                "which_names": ["qdrant", "qdrant.exe"],
                "import_name": "qdrant_client",
                "api_url": "http://127.0.0.1:6333",
            },
        ),

        # ----------------------------------------------------------------
        # Vision local — Ollama qwen2.5vl (multimodal)
        # ----------------------------------------------------------------
        ToolDefinition(
            id="ollama_vision",
            name="Ollama Vision (qwen2.5vl)",
            category=ToolCategory.VISION,
            description="Analise de imagens com modelo multimodal local via Ollama (qwen2.5vl).",
            provider="Ollama/Qwen",
            execution_mode=ExecutionMode.API,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="ollama",
            capabilities=[
                ToolCapability.ANALYZE_IMAGES,
            ],
            permissions_required=["read"],
            cost_policy=CostPolicy.FREE_OR_LOCAL,
            enabled=True,
            priority=45,
            config_hints={
                "which_names": ["ollama", "ollama.exe"],
                "api_url": "http://127.0.0.1:11434",
                "known_paths": [
                    r"C:\Users\Anderson\AppData\Local\Programs\Ollama\ollama.exe",
                ],
                "models": ["qwen2.5vl:7b"],
            },
        ),

        # ----------------------------------------------------------------
        # Python — runtime
        # ----------------------------------------------------------------
        ToolDefinition(
            id="python",
            name="Python",
            category=ToolCategory.RUNTIME,
            description="Python runtime for script execution and testing.",
            provider="Python",
            execution_mode=ExecutionMode.CLI,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="python",
            capabilities=[
                ToolCapability.EXECUTE_COMMANDS,
                ToolCapability.RUN_TESTS,
                ToolCapability.COMPILE,
            ],
            permissions_required=["execute"],
            cost_policy=CostPolicy.FREE,
            enabled=True,
            priority=5,
            config_hints={
                "which_names": ["python", "python.exe", "python3"],
            },
        ),

        # ----------------------------------------------------------------
        # MetaEditor — MQL5 compiler
        # ----------------------------------------------------------------
        ToolDefinition(
            id="metaeditor",
            name="MetaEditor",
            category=ToolCategory.COMPILER,
            description="MetaQuotes Language 5 editor and compiler.",
            provider="MetaQuotes",
            execution_mode=ExecutionMode.CLI,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="metaeditor64.exe",
            capabilities=[
                ToolCapability.COMPILE,
                ToolCapability.READ_FILES,
                ToolCapability.WRITE_FILES,
            ],
            permissions_required=["execute", "write"],
            cost_policy=CostPolicy.FREE,
            enabled=True,
            priority=90,
            config_hints={
                "which_names": ["metaeditor64.exe", "MetaEditor64.exe"],
                "known_paths": [
                    r"C:\Program Files\MetaTrader 5\metaeditor64.exe",
                    r"C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe",
                ],
                "app_name": "metaeditor",
            },
        ),

        # ----------------------------------------------------------------
        # MT5 — trading platform
        # ----------------------------------------------------------------
        ToolDefinition(
            id="mt5",
            name="MetaTrader 5",
            category=ToolCategory.TRADING,
            description="MetaTrader 5 trading platform for EA deployment and trading.",
            provider="MetaQuotes",
            execution_mode=ExecutionMode.SUBPROCESS,
            local_or_remote=LocalOrRemote.LOCAL,
            executable="terminal64.exe",
            capabilities=[
                ToolCapability.EXECUTE_COMMANDS,
                ToolCapability.READ_FILES,
                ToolCapability.WRITE_FILES,
            ],
            permissions_required=["execute", "write"],
            cost_policy=CostPolicy.FREE,
            enabled=True,
            priority=95,
            config_hints={
                "which_names": ["terminal64.exe", "terminal.exe"],
                "known_paths": [
                    r"C:\Program Files\MetaTrader 5\terminal64.exe",
                    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
                ],
                "app_name": "metatrader 5",
            },
        ),
    ]


def create_default_registry():
    """Create an ExternalToolRegistry pre-loaded with built-in tools."""
    from .registry import ExternalToolRegistry

    registry = ExternalToolRegistry()
    for tool in get_builtin_tool_definitions():
        registry.register(tool)
    return registry