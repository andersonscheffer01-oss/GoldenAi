"""M1.6.1 — Context Index auto-update (deterministic, zero LLM).

Gera/atualiza os índices do Segundo Cerebro de forma determinística,
extraindo informação de arquivos existentes, metadata e estrutura.

NÃO usa LLM. NÃO pesquisa web. Gera a partir de:
- Estrutura de diretórios
- Metadata de arquivos (datas, tamanhos)
- Conteúdo de docs canônicos (CURRENT_WORK, HANDOFF, DECISIONS, KNOWN_ISSUES)
- Configuração do projeto
"""
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_VAULT = Path(r"C:\GoldenAI\vault\Segundo Cerebro")
DEFAULT_DOCS = Path(r"C:\GoldenAI\studio\golden_ai_studio_web\docs\agent-context")
DEFAULT_ROOT = Path(r"C:\GoldenAI")


def _read_file_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_frontmatter(text: str) -> Dict[str, Any]:
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("---", 3)
        block = text[3:end].strip()
        result = {}
        for line in block.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                result[key.strip()] = val.strip()
        return result
    except (ValueError, IndexError):
        return {}


def _truncate(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n... (truncated)"


def _scan_files(root: Path, pattern: str = "*.md") -> List[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob(pattern))


def _file_meta(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


class ContextIndexBuilder:
    """Gera índices do Segundo Cerebro de forma determinística."""

    def __init__(self, vault_root: Optional[Path] = None,
                 docs_root: Optional[Path] = None,
                 project_root: Optional[Path] = None):
        self.vault = Path(vault_root or DEFAULT_VAULT)
        self.docs = Path(docs_root or DEFAULT_DOCS)
        self.root = Path(project_root or DEFAULT_ROOT)

    def build_all(self) -> Dict[str, Any]:
        report = {
            "timestamp": datetime.now().isoformat(),
            "vault": str(self.vault),
            "files_written": [],
            "errors": [],
        }
        try:
            self.update_master_index()
            report["files_written"].append("00_INDEX.md")
        except Exception as e:
            report["errors"].append(f"master_index: {e}")

        try:
            self.update_project_index("Golden")
            report["files_written"].append("Projetos/Golden/INDEX.md")
        except Exception as e:
            report["errors"].append(f"project_index: {e}")

        try:
            self.update_current_state("Golden")
            report["files_written"].append("Projetos/Golden/CURRENT_STATE.md")
        except Exception as e:
            report["errors"].append(f"current_state: {e}")

        try:
            self.update_file_map("Golden")
            report["files_written"].append("Projetos/Golden/FILE_MAP.md")
        except Exception as e:
            report["errors"].append(f"file_map: {e}")

        return report

    def update_master_index(self) -> None:
        path = self.vault / "00_INDEX.md"
        content = self._render_master_index()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def update_project_index(self, project: str) -> None:
        path = self.vault / "Projetos" / project / "INDEX.md"
        content = self._render_project_index(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def update_current_state(self, project: str) -> None:
        path = self.vault / "Projetos" / project / "CURRENT_STATE.md"
        content = self._render_current_state(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def update_file_map(self, project: str) -> None:
        path = self.vault / "Projetos" / project / "FILE_MAP.md"
        content = self._render_file_map(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _render_master_index(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d")
        projects = self._scan_projects()
        domains = self._scan_domains()

        lines = [
            "---",
            f"last_updated: {now}",
            "source: auto-generated",
            "scope:全局路由",
            "status: CURRENT",
            "---",
            "",
            "# Segundo Cerebro — Roteador de Contexto",
            "",
            "Leia este índice ANTES de varrer o repositório.",
            "",
            "## Projetos ativos",
            "",
        ]
        for p in projects:
            lines.append(f"- **{p}** → [[Projetos/{p}/INDEX]]")
        lines.append("")
        lines.append("## Domínios")
        lines.append("")
        lines.append("| Domínio | Índice | Escopo |")
        lines.append("|---------|--------|--------|")
        domain_desc = {
            "Trading": "MQL5, EA, estratégias, MT5",
            "Coding": "Python, MQL5, HTML/JS, arquitetura",
            "Windows": "Automação, sistema, configuração",
            "Gaming": "Jogos, hardware, performance",
            "AMD": "GPU, drivers, Anti-Lag, FSR",
        }
        for d in domains:
            desc = domain_desc.get(d, "")
            lines.append(f"| {d} | [[{d}/INDEX]] | {desc} |")
        lines.append("")
        lines.append("## Contexto global")
        lines.append("")
        lines.append("| ÁREA | Índice | USO |")
        lines.append("|------|--------|-----|")
        globals_ = [
            ("Preferências", "Preferencias", "Como o agente deve operar"),
            ("Decisões", "Decisoes", "Decisões arquiteturais válidas"),
            ("Procedimentos", "Procedimentos", "Fluxos padrão"),
            ("Aprendizados", "Aprendizados", "Liçãos aprendidas"),
        ]
        for label, folder, desc in globals_:
            lines.append(f"| {label} | [[{folder}/INDEX]] | {desc} |")
        lines.append("")
        lines.append("## Como usar")
        lines.append("")
        lines.append("1. Identifique a tarefa")
        lines.append("2. Abra o índice do projeto ou domínio relacionado")
        lines.append("3. Abra CURRENT_STATE / FILE_MAP / DECISIONS somente se necessário")
        lines.append("4. Abra os arquivos de código envolvidos")
        lines.append("5. NÃO leia todo o Vault ou repositório sem necessidade")
        lines.append("")
        return "\n".join(lines)

    def _render_project_index(self, project: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d")
        lines = [
            "---",
            f"last_updated: {now}",
            "source: auto-generated",
            f"scope: {project} — Projeto",
            "status: CURRENT",
            "---",
            "",
            f"# {project} — Índice do Projeto",
            "",
        ]
        if project == "Golden":
            lines.extend([
                "Sistema de IA local para trading algoritmico, desenvolvimento MQL5 e automação de PC.",
                "",
                "→ Ver [[CURRENT_STATE]] para estado atual",
                "→ Ver [[FILE_MAP]] para paths",
                "→ Ver [[DECISIONS]] para decisões",
                "→ Ver [[KNOWN_ISSUES]] para problemas",
                "→ Ver [[HANDOFF]] para último estado",
            ])
        return "\n".join(lines)

    def _render_current_state(self, project: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d")
        current_work = _read_file_safe(self.docs / "CURRENT_WORK.md")
        handoff = _read_file_safe(self.docs / "HANDOFF.md")

        lines = [
            "---",
            f"last_updated: {now}",
            "source: auto-generated",
            f"scope: {project} — Estado atual",
            "status: CURRENT",
            "---",
            "",
            f"# {project} — Estado Atual",
            "",
        ]
        if current_work:
            lines.append("## Extraído de CURRENT_WORK.md")
            lines.append("")
            lines.append(_truncate(current_work, 40))
        if handoff:
            lines.append("")
            lines.append("## Último Handoff")
            lines.append("")
            lines.append(_truncate(handoff, 20))
        return "\n".join(lines)

    def _render_file_map(self, project: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d")
        lines = [
            "---",
            f"last_updated: {now}",
            "source: auto-generated",
            f"scope: {project} — Mapa de arquivos",
            "status: CURRENT",
            "---",
            "",
            f"# {project} — Mapa de Arquivos",
            "",
        ]
        if project == "Golden":
            studio = self.root / "studio" / "golden_ai_studio_web"
            core = studio / "jarvis_core"
            lines.extend([
                "## Core",
                "",
                "| Conceito | Path principal |",
                "|----------|---------------|",
            ])
            modules = [
                ("Memory V2", "jarvis_core/memory/v2/"),
                ("Research", "jarvis_core/memory/v2/research.py"),
                ("Config/secrets", "jarvis_core/config.py"),
                ("Service", "jarvis_core/service.py"),
                ("Brain", "jarvis_core/brain.py"),
                ("Importer", "jarvis_core/memory/v2/importer.py"),
                ("Watcher", "jarvis_core/memory/v2/watcher.py"),
            ]
            for name, path in modules:
                exists = "✅" if (core / path.replace("jarvis_core/", "")).exists() else "❓"
                lines.append(f"| {name} | `{path}` {exists} |")
            lines.extend([
                "",
                "## Docs",
                "",
                "| Conceito | Path |",
                "|----------|------|",
                "| Docs canônicos | `docs/agent-context/` |",
                "| CURRENT_WORK | `docs/agent-context/CURRENT_WORK.md` |",
                "| HANDOFF | `docs/agent-context/HANDOFF.md` |",
            ])
        return "\n".join(lines)

    def _scan_projects(self) -> List[str]:
        projects_dir = self.root / "studio" / "golden_ai_studio_web"
        result = []
        if projects_dir.exists():
            result.append("Golden")
        return result

    def _scan_domains(self) -> List[str]:
        domains = []
        vault = self.vault
        for name in ["Trading", "Coding", "Windows", "Gaming", "AMD"]:
            if (vault / name).exists():
                domains.append(name)
        return domains


def build_master_index(vault_root: Optional[Path] = None) -> Path:
    builder = ContextIndexBuilder(vault_root=vault_root)
    builder.update_master_index()
    return Path(builder.vault / "00_INDEX.md")


def build_project_index(project: str, vault_root: Optional[Path] = None) -> Path:
    builder = ContextIndexBuilder(vault_root=vault_root)
    builder.update_project_index(project)
    return Path(builder.vault / "Projetos" / project / "INDEX.md")


def build_current_state(project: str, vault_root: Optional[Path] = None) -> Path:
    builder = ContextIndexBuilder(vault_root=vault_root)
    builder.update_current_state(project)
    return Path(builder.vault / "Projetos" / project / "CURRENT_STATE.md")


def build_file_map(project: str, vault_root: Optional[Path] = None) -> Path:
    builder = ContextIndexBuilder(vault_root=vault_root)
    builder.update_file_map(project)
    return Path(builder.vault / "Projetos" / project / "FILE_MAP.md")


def update_context_index(vault_root: Optional[Path] = None) -> Dict[str, Any]:
    builder = ContextIndexBuilder(vault_root=vault_root)
    return builder.build_all()
