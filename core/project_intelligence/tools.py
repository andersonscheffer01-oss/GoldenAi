from __future__ import annotations

import ast
import fnmatch
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.config import load_settings
from core.execution import ExecutionService, ExecutionStatus
from core.permissions import PermissionManager
from core.tools.hashing import sha256_file
from core.tools.registry import ToolDefinition, ToolRegistry

from .models import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    ProjectFileInfo,
    ProjectReadResult,
    ProjectSearchMatch,
    ProjectSymbol,
)


SKIP_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv", "workspace", "build", "dist"}
TEXT_SUFFIXES = {
    ".py", ".mq5", ".mqh", ".txt", ".md", ".json", ".csv", ".log", ".srt", ".vtt",
    ".ini", ".cfg", ".toml", ".yaml", ".yml",
}


class ProjectIntelligenceService:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root).resolve()
        self.settings = load_settings()
        self.permissions = PermissionManager(self.settings)
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self.registry = ToolRegistry(self.permissions)
        self.last_results: dict[str, Any] = {}
        self._register_tools()

    def execute(self, name: str, **kwargs: Any) -> Any:
        return self.registry.execute(name, **kwargs)

    def project_list(self, project_root: str | Path, pattern: str = "*", include_hash: bool = False) -> list[ProjectFileInfo]:
        root = self._authorize_project_root(project_root)
        started = time.perf_counter()
        items: list[ProjectFileInfo] = []
        for path in self._iter_project(root):
            rel = path.relative_to(root).as_posix()
            if pattern and pattern not in {"*", ""} and not self._matches_filter(rel, pattern):
                continue
            if path.is_dir():
                items.append(ProjectFileInfo(rel, "directory", "", 0, "directory"))
                continue
            stat = path.stat()
            suffix = path.suffix.lower()
            items.append(ProjectFileInfo(
                path=rel,
                kind="file",
                extension=suffix,
                size_bytes=stat.st_size,
                language=self._language_for(path),
                line_count=self._line_count(path) if suffix in TEXT_SUFFIXES else 0,
                modified_at=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                sha256=sha256_file(path) if include_hash else "",
            ))
        self._record("PROJECT_LIST", root, f"Projeto listado - {len(items)} itens", started, {"pattern": pattern})
        self.last_results["project_list"] = items
        return items

    def project_search(self, project_root: str | Path, query: str, pattern: str = "*", use_rg: bool = True, max_results: int = 200) -> dict[str, Any]:
        root = self._authorize_project_root(project_root)
        started = time.perf_counter()
        matches = self._search_rg(root, query, pattern, max_results) if use_rg else []
        backend = "rg" if matches else "python"
        if not matches:
            matches = self._search_python(root, query, pattern, max_results)
        result = {"query": query, "backend": backend, "total": len(matches), "matches": matches}
        self._record("PROJECT_SEARCH", root, f'Busca "{query}" - {len(matches)} ocorrencias', started, {"backend": backend})
        self.last_results["project_search"] = result
        return result

    def project_find_symbol(self, project_root: str | Path, symbol: str, pattern: str = "*") -> list[ProjectSymbol]:
        root = self._authorize_project_root(project_root)
        started = time.perf_counter()
        symbols: list[ProjectSymbol] = []
        for path in self._iter_project_files(root, pattern):
            rel = path.relative_to(root).as_posix()
            if path.suffix.lower() == ".py":
                symbols.extend(s for s in self._python_symbols(path, rel) if s.name == symbol or symbol in s.name)
            elif path.suffix.lower() in TEXT_SUFFIXES:
                for match in self._search_text_file(path, symbol):
                    symbols.append(ProjectSymbol(rel, symbol, "text", match.line, 0))
        self._record("PROJECT_FIND_SYMBOL", root, f"Simbolo {symbol} - {len(symbols)} resultados", started)
        self.last_results["project_find_symbol"] = symbols
        return symbols

    def project_read_file(self, project_root: str | Path, path: str, max_bytes: int = 80_000) -> ProjectReadResult:
        root = self._authorize_project_root(project_root)
        target = self._safe_child(root, path)
        if target.stat().st_size > max_bytes:
            return self.project_read_range(root, path, 1, 300)
        return self.project_read_range(root, path, 1, self._line_count(target))

    def project_read_range(self, project_root: str | Path, path: str, start_line: int, end_line: int) -> ProjectReadResult:
        root = self._authorize_project_root(project_root)
        target = self._safe_child(root, path)
        started = time.perf_counter()
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)
        start = max(1, int(start_line))
        end = min(max(start, int(end_line)), total)
        selected = lines[start - 1:end]
        result = ProjectReadResult(target.relative_to(root).as_posix(), start, end, total, "\n".join(selected))
        self._record("PROJECT_READ_RANGE", target, f"Lidas linhas {start}-{end} de {result.path}", started)
        self.last_results["project_read_range"] = result
        return result

    def project_file_metadata(self, project_root: str | Path, path: str, include_hash: bool = True) -> ProjectFileInfo:
        root = self._authorize_project_root(project_root)
        target = self._safe_child(root, path)
        stat = target.stat()
        info = ProjectFileInfo(
            path=target.relative_to(root).as_posix(),
            kind="directory" if target.is_dir() else "file",
            extension=target.suffix.lower(),
            size_bytes=stat.st_size if target.is_file() else 0,
            language=self._language_for(target),
            line_count=self._line_count(target) if target.is_file() and target.suffix.lower() in TEXT_SUFFIXES else 0,
            modified_at=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            sha256=sha256_file(target) if include_hash and target.is_file() else "",
        )
        self._record("PROJECT_FILE_METADATA", target, f"Metadata calculada - {info.path}", time.perf_counter())
        return info

    def project_find_references(self, project_root: str | Path, symbol: str) -> dict[str, Any]:
        definitions = self.project_find_symbol(project_root, symbol)
        search = self.project_search(project_root, symbol, use_rg=False)
        result = {"symbol": symbol, "definitions": definitions, "references": search["matches"], "total": search["total"]}
        self.last_results["project_find_references"] = result
        return result

    def project_dependency_graph(self, project_root: str | Path) -> DependencyGraph:
        root = self._authorize_project_root(project_root)
        started = time.perf_counter()
        py_files = list(self._iter_project_files(root, "*.py"))
        module_by_path = {p.relative_to(root).as_posix(): self._module_name(p, root) for p in py_files}
        path_by_module = {module: rel for rel, module in module_by_path.items()}
        nodes = [DependencyNode(rel, module) for rel, module in sorted(module_by_path.items())]
        edges: list[DependencyEdge] = []
        for path in py_files:
            rel = path.relative_to(root).as_posix()
            for edge in self._python_import_edges(path, root, rel, path_by_module):
                edges.append(edge)
        graph = DependencyGraph(str(root), nodes, edges)
        self._record("PROJECT_DEPENDENCY_GRAPH", root, f"Grafo local - {len(nodes)} modulos / {len(edges)} dependencias", started)
        self.last_results["project_dependency_graph"] = graph
        return graph

    def project_reverse_dependencies(self, project_root: str | Path, path: str) -> list[DependencyEdge]:
        graph = self.project_dependency_graph(project_root)
        normalized = self._normalize_rel(path)
        return [edge for edge in graph.edges if edge.target == normalized]

    def project_dependencies_of(self, project_root: str | Path, path: str) -> list[DependencyEdge]:
        graph = self.project_dependency_graph(project_root)
        normalized = self._normalize_rel(path)
        return [edge for edge in graph.edges if edge.source == normalized]

    def project_related_files(self, project_root: str | Path, seed_path: str = "", symbol: str = "", stack_trace: str = "") -> list[dict[str, Any]]:
        root = self._authorize_project_root(project_root)
        started = time.perf_counter()
        scores: dict[str, dict[str, Any]] = {}

        def add(path: str, points: int, reason: str) -> None:
            entry = scores.setdefault(path, {"path": path, "score": 0, "reasons": []})
            entry["score"] += points
            if reason not in entry["reasons"]:
                entry["reasons"].append(reason)

        if seed_path:
            seed = self._normalize_rel(seed_path)
            add(seed, 10, "arquivo semente")
            for edge in self.project_dependencies_of(root, seed):
                if edge.resolved:
                    add(edge.target, 8, "import direto")
            for edge in self.project_reverse_dependencies(root, seed):
                add(edge.source, 8, "import reverso")
            base = Path(seed).stem
            for item in self.project_list(root, pattern="tests"):
                if base in item.path:
                    add(item.path, 5, "teste relacionado")
        if symbol:
            for match in self.project_search(root, symbol, use_rg=False)["matches"]:
                add(match.path, 4, "referencia de simbolo")
        if stack_trace:
            for item in self.project_list(root, pattern="*.py"):
                if item.path in stack_trace or Path(item.path).name in stack_trace:
                    add(item.path, 6, "stack trace")
        for item in self.project_list(root):
            if item.path in {"pyproject.toml", "pytest.ini", "setup.cfg", "requirements.txt"}:
                add(item.path, 2, "config")
            if item.path.endswith(("pipeline.py", "__main__.py")):
                add(item.path, 2, "entry point")
        ranked = sorted(scores.values(), key=lambda row: (-row["score"], row["path"]))
        self._record("PROJECT_RELATED_FILES", root, f"{len(ranked)} arquivos relacionados identificados", started)
        self.last_results["project_related_files"] = ranked
        return ranked

    def _register_tools(self) -> None:
        for name, handler in (
            ("project_list", self.project_list),
            ("project_search", self.project_search),
            ("project_find_symbol", self.project_find_symbol),
            ("project_read_file", self.project_read_file),
            ("project_read_range", self.project_read_range),
            ("project_file_metadata", self.project_file_metadata),
            ("project_find_references", self.project_find_references),
            ("project_dependency_graph", self.project_dependency_graph),
            ("project_related_files", self.project_related_files),
        ):
            self.registry.register(ToolDefinition(name, name, {}, "READ", handler, classification="read"))

    def _authorize_project_root(self, project_root: str | Path) -> Path:
        root = Path(project_root).resolve()
        decision = self.permissions.can_read(root)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        if not root.is_dir():
            raise FileNotFoundError(str(root))
        return root

    def _safe_child(self, root: Path, path: str | Path) -> Path:
        target = Path(path)
        if not target.is_absolute():
            target = root / target
        target = target.resolve()
        target.relative_to(root)
        decision = self.permissions.can_read(target)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        if not target.exists():
            raise FileNotFoundError(str(target))
        return target

    def _iter_project(self, root: Path):
        for path in sorted(root.rglob("*")):
            rel_parts = path.relative_to(root).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            yield path

    def _iter_project_files(self, root: Path, pattern: str = "*"):
        for path in self._iter_project(root):
            if path.is_file() and self._matches_filter(path.relative_to(root).as_posix(), pattern):
                yield path

    def _matches_filter(self, rel: str, pattern: str) -> bool:
        if not pattern or pattern == "*":
            return True
        if any(ch in pattern for ch in "*?[]"):
            return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(Path(rel).name, pattern)
        return pattern.lower() in rel.lower()

    def _search_rg(self, root: Path, query: str, pattern: str, max_results: int) -> list[ProjectSearchMatch]:
        if not shutil.which("rg"):
            return []
        cmd = ["rg", "--line-number", "--no-heading", "--fixed-strings", query, str(root)]
        if pattern and pattern != "*":
            cmd[1:1] = ["--glob", pattern]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
        except Exception:
            return []
        matches = []
        for raw in proc.stdout.splitlines()[:max_results]:
            parts = raw.split(":", 2)
            if len(parts) != 3:
                continue
            path, line, snippet = parts
            try:
                rel = Path(path).resolve().relative_to(root).as_posix()
            except ValueError:
                continue
            matches.append(ProjectSearchMatch(rel, int(line), snippet.strip()[:240]))
        return matches

    def _search_python(self, root: Path, query: str, pattern: str, max_results: int) -> list[ProjectSearchMatch]:
        matches: list[ProjectSearchMatch] = []
        for path in self._iter_project_files(root, pattern):
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            matches.extend(self._search_text_file(path, query, root))
            if len(matches) >= max_results:
                return matches[:max_results]
        return matches

    def _search_text_file(self, path: Path, query: str, root: Path | None = None) -> list[ProjectSearchMatch]:
        matches = []
        rel = path.relative_to(root).as_posix() if root else path.name
        for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if query in line:
                matches.append(ProjectSearchMatch(rel, index, line.strip()[:240]))
        return matches

    def _python_symbols(self, path: Path, rel: str) -> list[ProjectSymbol]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return []
        symbols: list[ProjectSymbol] = []
        parents: list[str] = []

        class Visitor(ast.NodeVisitor):
            def visit_ClassDef(visitor_self, node: ast.ClassDef) -> None:
                symbols.append(ProjectSymbol(rel, node.name, "class", node.lineno, node.col_offset, ".".join(parents)))
                parents.append(node.name)
                visitor_self.generic_visit(node)
                parents.pop()

            def visit_FunctionDef(visitor_self, node: ast.FunctionDef) -> None:
                kind = "method" if parents else "function"
                symbols.append(ProjectSymbol(rel, node.name, kind, node.lineno, node.col_offset, ".".join(parents)))
                parents.append(node.name)
                visitor_self.generic_visit(node)
                parents.pop()

            def visit_AsyncFunctionDef(visitor_self, node: ast.AsyncFunctionDef) -> None:
                symbols.append(ProjectSymbol(rel, node.name, "async_function", node.lineno, node.col_offset, ".".join(parents)))
                visitor_self.generic_visit(node)

            def visit_Import(visitor_self, node: ast.Import) -> None:
                for alias in node.names:
                    symbols.append(ProjectSymbol(rel, alias.asname or alias.name, "import", node.lineno, node.col_offset, ""))

            def visit_ImportFrom(visitor_self, node: ast.ImportFrom) -> None:
                for alias in node.names:
                    symbols.append(ProjectSymbol(rel, alias.asname or alias.name, "import", node.lineno, node.col_offset, node.module or ""))

            def visit_Assign(visitor_self, node: ast.Assign) -> None:
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        symbols.append(ProjectSymbol(rel, target.id, "assignment", node.lineno, node.col_offset, ".".join(parents)))
                visitor_self.generic_visit(node)

        Visitor().visit(tree)
        return symbols

    def _python_import_edges(self, path: Path, root: Path, rel: str, path_by_module: dict[str, str]) -> list[DependencyEdge]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return []
        current_module = self._module_name(path, root)
        package = ".".join(current_module.split(".")[:-1])
        edges: list[DependencyEdge] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = self._resolve_module(alias.name, path_by_module)
                    edges.append(DependencyEdge(rel, target or alias.name, "import", alias.name, node.lineno, bool(target)))
            elif isinstance(node, ast.ImportFrom):
                base = self._relative_module(package, node.module or "", node.level)
                names = [alias.name for alias in node.names]
                candidates = [base] + [f"{base}.{name}" for name in names if base]
                target = next((self._resolve_module(c, path_by_module) for c in candidates if self._resolve_module(c, path_by_module)), "")
                edges.append(DependencyEdge(rel, target or base, "from", ",".join(names), node.lineno, bool(target)))
        return edges

    def _resolve_module(self, module: str, path_by_module: dict[str, str]) -> str:
        if module in path_by_module:
            return path_by_module[module]
        init = module + ".__init__"
        return path_by_module.get(init, "")

    def _relative_module(self, package: str, module: str, level: int) -> str:
        if level <= 0:
            return module
        parts = package.split(".") if package else []
        prefix = ".".join(parts[: max(0, len(parts) - level + 1)])
        return ".".join(part for part in (prefix, module) if part)

    def _module_name(self, path: Path, root: Path) -> str:
        return ".".join(path.relative_to(root).with_suffix("").parts)

    def _normalize_rel(self, path: str) -> str:
        return str(path).replace("\\", "/").lstrip("/")

    def _language_for(self, path: Path) -> str:
        suffix = path.suffix.lower()
        return {
            ".py": "python",
            ".mq5": "mql5",
            ".mqh": "mql5",
            ".json": "json",
            ".csv": "csv",
            ".md": "markdown",
            ".txt": "text",
            ".log": "log",
            ".srt": "subtitle",
            ".vtt": "subtitle",
            ".pdf": "pdf",
        }.get(suffix, suffix.lstrip(".") or "unknown")

    def _line_count(self, path: Path) -> int:
        if not path.is_file():
            return 0
        with path.open("rb") as handle:
            return sum(1 for _ in handle)

    def _record(self, action: str, target: Path, summary: str, started: float, metadata: dict[str, Any] | None = None) -> None:
        duration = int((time.perf_counter() - started) * 1000)
        self.execution.authorize_action(
            task_id="project-intelligence",
            permission_level="READ",
            action=action.lower(),
            target=str(target),
            reason="Ferramenta de investigacao de projeto em modo leitura.",
            tool_name=action.lower(),
        )
        self.execution.record_event(
            task_id="project-intelligence",
            category="SEARCH" if "SEARCH" in action or "SYMBOL" in action else "READ",
            action=action,
            status=ExecutionStatus.COMPLETED.value,
            summary=summary,
            target=str(target),
            tool_name=action.lower(),
            permission_level="READ",
            risk_level="LOW",
            duration_ms=duration,
            metadata=metadata or {},
        )
        self.audit.record({
            "action_type": action,
            "status": "COMPLETED",
            "agent": "core.project_intelligence",
            "target": str(target),
            "result": summary,
            "input_summary": json.dumps(metadata or {}, ensure_ascii=False),
            "duration_ms": duration,
        })
