from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProjectFileInfo:
    path: str
    kind: str
    extension: str
    size_bytes: int
    language: str
    line_count: int = 0
    modified_at: str = ""
    sha256: str = ""


@dataclass(frozen=True)
class ProjectSearchMatch:
    path: str
    line: int
    snippet: str


@dataclass(frozen=True)
class ProjectSymbol:
    path: str
    name: str
    symbol_type: str
    line: int
    column: int = 0
    parent: str = ""


@dataclass(frozen=True)
class ProjectReadResult:
    path: str
    start_line: int
    end_line: int
    total_lines: int
    text: str


@dataclass(frozen=True)
class DependencyNode:
    path: str
    module: str


@dataclass(frozen=True)
class DependencyEdge:
    source: str
    target: str
    import_type: str
    symbol: str
    line: int
    resolved: bool


@dataclass(frozen=True)
class DependencyGraph:
    project_root: str
    nodes: list[DependencyNode] = field(default_factory=list)
    edges: list[DependencyEdge] = field(default_factory=list)
