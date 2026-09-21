"""Tool capability constants for the external tools infrastructure.

Capabilities are METADATA only. Declaring a capability does NOT grant
the tool any permission. The PermissionManager remains the sole
authority for all security decisions.
"""
from __future__ import annotations


class ToolCapability:
    """String constants representing what a tool can potentially do.

    These are descriptive labels, not permissions. A tool declaring
    ``execute_commands`` still needs explicit PermissionManager
    approval before any command is run.
    """

    READ_FILES = "read_files"
    WRITE_FILES = "write_files"
    EXECUTE_COMMANDS = "execute_commands"
    RUN_TESTS = "run_tests"
    COMPILE = "compile"
    BROWSE_WEB = "browse_web"
    DOWNLOAD = "download"
    PARSE_DOCUMENTS = "parse_documents"
    TRANSCRIBE_AUDIO = "transcribe_audio"
    PROCESS_VIDEO = "process_video"
    ANALYZE_IMAGES = "analyze_images"
    VECTOR_SEARCH = "vector_search"
    CHAT = "chat"
    TOOL_CALLING = "tool_calling"
    CODING_AGENT = "coding_agent"

    @classmethod
    def all(cls) -> list[str]:
        """Return all known capability strings."""
        return [
            cls.READ_FILES,
            cls.WRITE_FILES,
            cls.EXECUTE_COMMANDS,
            cls.RUN_TESTS,
            cls.COMPILE,
            cls.BROWSE_WEB,
            cls.DOWNLOAD,
            cls.PARSE_DOCUMENTS,
            cls.TRANSCRIBE_AUDIO,
            cls.PROCESS_VIDEO,
            cls.ANALYZE_IMAGES,
            cls.VECTOR_SEARCH,
            cls.CHAT,
            cls.TOOL_CALLING,
            cls.CODING_AGENT,
        ]

    @classmethod
    def is_valid(cls, capability: str) -> bool:
        """Check whether a capability string is recognized."""
        return capability in cls.all()