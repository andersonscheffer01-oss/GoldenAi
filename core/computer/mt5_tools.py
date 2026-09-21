from __future__ import annotations

import os
import shutil
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from core.permissions import PermissionManager
from .app_tools import find_installed_app
from .models import MT5InstallationInfo
from .process_tools import list_processes


APPDATA_TERMINAL = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"


@dataclass
class MT5TerminalInfo:
    """Informações sobre uma instalação MT5 com dados."""
    terminal_id: str
    path: str
    name: str
    mql5_path: str
    experts_path: str
    indicators_path: str
    scripts_path: str
    terminal_exe: str
    metaeditor_exe: str
    is_running: bool = False


def find_mt5_installations() -> list[dict]:
    """
    Encontra todas as instalações MT5 e MetaEditor no sistema.
    Retorna lista de dicionários com informações sobre cada instalação.
    """
    found = []
    for name in ("metatrader 5", "metaeditor"):
        info = find_installed_app(name)
        if info.get("found"):
            found.append(asdict(MT5InstallationInfo(name=name, path=info["path"], kind="application")))
    return found


def get_mt5_status() -> dict:
    processes = list_processes("terminal", limit=20)
    metaeditor = list_processes("metaeditor", limit=20)
    return {
        "mt5_running": bool(processes),
        "metaeditor_running": bool(metaeditor),
        "mt5_processes": processes,
        "metaeditor_processes": metaeditor,
        "installations": find_mt5_installations(),
    }


def list_mt5_terminals() -> list[dict]:
    manager = PermissionManager()
    decision = manager.can_read_external_safe("mt5_read", APPDATA_TERMINAL)
    if not decision.allowed or not APPDATA_TERMINAL.exists():
        return []
    return [
        {"path": str(path), "name": path.name}
        for path in APPDATA_TERMINAL.iterdir()
        if path.is_dir()
    ]


def list_mt5_eas() -> list[str]:
    manager = PermissionManager()
    decision = manager.can_read_external_safe("mt5_read", APPDATA_TERMINAL)
    if not decision.allowed or not APPDATA_TERMINAL.exists():
        return []
    results: list[str] = []
    for file in APPDATA_TERMINAL.glob("*/MQL5/Experts/**/*.mq*"):
        if file.suffix.lower() in (".mq5", ".mqh"):
            results.append(str(file))
    return sorted(results)


def read_mt5_file(path: str, max_bytes: int = 120000) -> dict:
    target = Path(path)
    manager = PermissionManager()
    decision = manager.can_read_external_safe("mt5_read", target)
    if not decision.allowed:
        return {"ok": False, "error": decision.reason, "path": path}
    if target.suffix.lower() not in (".mq5", ".mqh"):
        return {"ok": False, "error": "Only .mq5/.mqh files are allowed", "path": path}
    data = target.read_bytes()[:max_bytes]
    return {
        "ok": True,
        "path": str(target),
        "truncated": target.stat().st_size > max_bytes,
        "text": data.decode("utf-8", errors="replace"),
    }


# ============================================================
# NOVAS FUNCOES PARA DETECCAO DE INSTALACOES COMPLETAS
# ============================================================

def detect_all_mt5_installations() -> list[MT5TerminalInfo]:
    """
    Detecta todas as instalações MT5 com informações completas.
    Cada instalação inclui: terminal_id, caminho, MQL5, Experts, Indicators, Scripts, executáveis.
    """
    installations = []
    
    # Primeiro, encontra o MetaEditor para obter o caminho base
    metaeditor_info = find_installed_app("metaeditor")
    terminal_info = find_installed_app("metatrader 5")
    
    metaeditor_exe = metaeditor_info.get("path", "") if metaeditor_info.get("found") else ""
    terminal_exe = terminal_info.get("path", "") if terminal_info.get("found") else ""
    
    # Determina o diretório base do MT5
    if terminal_exe:
        mt5_base = Path(terminal_exe).parent
    elif metaeditor_exe:
        mt5_base = Path(metaeditor_exe).parent
    else:
        mt5_base = Path(r"C:\Program Files\MetaTrader 5")
    
    # Lista todos os terminais em AppData
    if APPDATA_TERMINAL.exists():
        for terminal_dir in APPDATA_TERMINAL.iterdir():
            if not terminal_dir.is_dir():
                continue
            
            terminal_id = terminal_dir.name
            mql5_path = terminal_dir / "MQL5"
            experts_path = mql5_path / "Experts"
            indicators_path = mql5_path / "Indicators"
            scripts_path = mql5_path / "Scripts"
            
            # Verifica se os executáveis existem
            term_exe = str(mt5_base / "terminal64.exe")
            me_exe = str(mt5_base / "metaeditor64.exe")
            
            # Verifica se o terminal está rodando
            is_running = any(
                proc.get("name", "").lower().startswith("terminal")
                for proc in list_processes("terminal", limit=10)
            )
            
            installation = MT5TerminalInfo(
                terminal_id=terminal_id,
                path=str(terminal_dir),
                name=f"MT5 Terminal {terminal_id[:8]}",
                mql5_path=str(mql5_path) if mql5_path.exists() else "",
                experts_path=str(experts_path) if experts_path.exists() else "",
                indicators_path=str(indicators_path) if indicators_path.exists() else "",
                scripts_path=str(scripts_path) if scripts_path.exists() else "",
                terminal_exe=term_exe if Path(term_exe).exists() else "",
                metaeditor_exe=me_exe if Path(me_exe).exists() else "",
                is_running=is_running,
            )
            installations.append(installation)
    
    return installations


def get_mt5_installation_by_id(terminal_id: str) -> Optional[MT5TerminalInfo]:
    """Obtém uma instalação MT5 específica pelo ID do terminal."""
    for inst in detect_all_mt5_installations():
        if inst.terminal_id == terminal_id:
            return inst
    return None


def list_mt5_experts_for_terminal(terminal_id: str) -> list[str]:
    """Lista EAs de um terminal específico."""
    inst = get_mt5_installation_by_id(terminal_id)
    if not inst or not inst.experts_path:
        return []
    
    experts_path = Path(inst.experts_path)
    if not experts_path.exists():
        return []
    
    results = []
    for file in experts_path.glob("**/*.mq*"):
        if file.suffix.lower() in (".mq5", ".mqh"):
            results.append(str(file))
    return sorted(results)


def list_mt5_indicators_for_terminal(terminal_id: str) -> list[str]:
    """Lista indicadores de um terminal específico."""
    inst = get_mt5_installation_by_id(terminal_id)
    if not inst or not inst.indicators_path:
        return []
    
    indicators_path = Path(inst.indicators_path)
    if not indicators_path.exists():
        return []
    
    results = []
    for file in indicators_path.glob("**/*.mq*"):
        if file.suffix.lower() in (".mq5", ".mqh"):
            results.append(str(file))
    return sorted(results)


def list_mt5_scripts_for_terminal(terminal_id: str) -> list[str]:
    """Lista scripts de um terminal específico."""
    inst = get_mt5_installation_by_id(terminal_id)
    if not inst or not inst.scripts_path:
        return []
    
    scripts_path = Path(inst.scripts_path)
    if not scripts_path.exists():
        return []
    
    results = []
    for file in scripts_path.glob("**/*.mq*"):
        if file.suffix.lower() in (".mq5", ".mqh"):
            results.append(str(file))
    return sorted(results)


def find_mt5_file_by_name(filename: str, terminal_id: str = None) -> Optional[str]:
    """
    Localiza um arquivo .mq5/.mqh/.ex5 pelo nome em qualquer terminal MT5.
    Se terminal_id for fornecido, busca apenas nesse terminal.
    """
    filename_lower = filename.lower().strip()
    
    if terminal_id:
        # Busca apenas no terminal especificado
        inst = get_mt5_installation_by_id(terminal_id)
        if not inst:
            return None
        
        # Busca em Experts
        if inst.experts_path:
            for f in Path(inst.experts_path).glob("**/*"):
                if f.name.lower() == filename_lower or f.stem.lower() == filename_lower:
                    return str(f)
        
        # Busca em Indicators
        if inst.indicators_path:
            for f in Path(inst.indicators_path).glob("**/*"):
                if f.name.lower() == filename_lower or f.stem.lower() == filename_lower:
                    return str(f)
        
        # Busca em Scripts
        if inst.scripts_path:
            for f in Path(inst.scripts_path).glob("**/*"):
                if f.name.lower() == filename_lower or f.stem.lower() == filename_lower:
                    return str(f)
        
        return None
    
    # Busca em todos os terminais
    for inst in detect_all_mt5_installations():
        # Busca em Experts
        if inst.experts_path:
            for f in Path(inst.experts_path).glob("**/*"):
                if f.name.lower() == filename_lower or f.stem.lower() == filename_lower:
                    return str(f)
        
        # Busca em Indicators
        if inst.indicators_path:
            for f in Path(inst.indicators_path).glob("**/*"):
                if f.name.lower() == filename_lower or f.stem.lower() == filename_lower:
                    return str(f)
        
        # Busca em Scripts
        if inst.scripts_path:
            for f in Path(inst.scripts_path).glob("**/*"):
                if f.name.lower() == filename_lower or f.stem.lower() == filename_lower:
                    return str(f)
    
    return None


def find_mt5_ex5_by_name(filename: str, terminal_id: str = None) -> Optional[str]:
    """
    Localiza um arquivo .ex5 compilado pelo nome em qualquer terminal MT5.
    """
    filename_lower = filename.lower().strip()
    
    if terminal_id:
        inst = get_mt5_installation_by_id(terminal_id)
        if not inst:
            return None
        
        # Busca em Experts
        if inst.experts_path:
            for f in Path(inst.experts_path).glob("**/*.ex5"):
                if f.name.lower() == filename_lower or f.stem.lower() == filename_lower:
                    return str(f)
        
        return None
    
    # Busca em todos os terminais
    for inst in detect_all_mt5_installations():
        if inst.experts_path:
            for f in Path(inst.experts_path).glob("**/*.ex5"):
                if f.name.lower() == filename_lower or f.stem.lower() == filename_lower:
                    return str(f)
    
    return None


def get_mt5_file_metadata(path: str) -> dict:
    """Obtém metadados de um arquivo MT5 (.mq5, .mqh, .ex5)."""
    target = Path(path)
    
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": "File not found", "path": path}
    
    manager = PermissionManager()
    decision = manager.can_read_external_safe("mt5_read", target)
    if not decision.allowed:
        return {"ok": False, "error": decision.reason, "path": path}
    
    try:
        stat = target.stat()
        suffix = target.suffix.lower()
        
        # Determina o tipo do arquivo
        if suffix == ".mq5":
            file_type = "Expert Advisor"
        elif suffix == ".mqh":
            file_type = "Header/Library"
        elif suffix == ".ex5":
            file_type = "Compiled Expert"
        else:
            file_type = "Unknown"
        
        # Calcula hash SHA256
        h = hashlib.sha256()
        with open(target, "rb") as f:
            for bloco in iter(lambda: f.read(65536), b""):
                h.update(bloco)
        
        return {
            "ok": True,
            "path": str(target),
            "name": target.name,
            "stem": target.stem,
            "suffix": suffix,
            "type": file_type,
            "size_bytes": stat.st_size,
            "size_human": _format_size(stat.st_size),
            "sha256": h.hexdigest(),
            "modified": stat.st_mtime,
            "terminal_id": _extract_terminal_id(str(target)),
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "path": path}


def _format_size(bytes_val: int) -> str:
    """Formata tamanho em bytes para formato legível."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} TB"


def _extract_terminal_id(path: str) -> str:
    """Extrai o ID do terminal de um caminho MT5."""
    parts = Path(path).parts
    for i, part in enumerate(parts):
        if part == "Terminal" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def deploy_to_mt5(
    source_path: str,
    terminal_id: str,
    overwrite: bool = False
) -> dict:
    """
    Deploy de um arquivo compilado (.ex5) para o MT5.
    Requer permissão de escrita.
    """
    manager = PermissionManager()
    
    # Verifica permissão de escrita
    decision = manager.can_write(source_path, explicit_authorization=False)
    if not decision.allowed:
        return {
            "ok": False,
            "error": f"Permissão negada: {decision.reason}",
            "source": source_path,
        }
    
    # Obtém instalação
    inst = get_mt5_installation_by_id(terminal_id)
    if not inst:
        return {
            "ok": False,
            "error": f"Terminal MT5 não encontrado: {terminal_id}",
            "terminal_id": terminal_id,
        }
    
    if not inst.experts_path:
        return {
            "ok": False,
            "error": "Pasta Experts não encontrada no terminal",
            "terminal_id": terminal_id,
        }
    
    source = Path(source_path)
    if not source.exists():
        return {
            "ok": False,
            "error": f"Arquivo fonte não encontrado: {source_path}",
            "source": source_path,
        }
    
    if source.suffix.lower() != ".ex5":
        return {
            "ok": False,
            "error": "Apenas arquivos .ex5 podem ser implantados",
            "source": source_path,
        }
    
    dest_path = Path(inst.experts_path) / source.name
    
    # Verifica se já existe
    if dest_path.exists() and not overwrite:
        return {
            "ok": False,
            "error": "Arquivo já existe no destino",
            "source": source_path,
            "destination": str(dest_path),
            "exists": True,
            "overwrite_allowed": False,
        }
    
    try:
        # Calcula hash antes
        h_before = hashlib.sha256(source.read_bytes()).hexdigest()
        
        # Copia o arquivo
        shutil.copy2(source, dest_path)
        
        # Calcula hash depois
        h_after = hashlib.sha256(dest_path.read_bytes()).hexdigest()
        
        return {
            "ok": True,
            "source": str(source),
            "destination": str(dest_path),
            "hash_before": h_before,
            "hash_after": h_after,
            "size_bytes": dest_path.stat().st_size,
            "terminal_id": terminal_id,
            "experts_path": inst.experts_path,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "source": source_path,
            "destination": str(dest_path) if 'dest_path' in dir() else "",
        }


def list_mt5_ex5_files(terminal_id: str = None) -> list[str]:
    """Lista arquivos .ex5 compilados em qualquer terminal ou específico."""
    if terminal_id:
        return list_mt5_ex5_by_name("", terminal_id) if False else _list_ex5_for_terminal(terminal_id)
    
    results = []
    for inst in detect_all_mt5_installations():
        results.extend(_list_ex5_for_terminal(inst.terminal_id))
    return sorted(results)


def _list_ex5_for_terminal(terminal_id: str) -> list[str]:
    """Lista .ex5 de um terminal específico."""
    inst = get_mt5_installation_by_id(terminal_id)
    if not inst or not inst.experts_path:
        return []
    
    experts_path = Path(inst.experts_path)
    if not experts_path.exists():
        return []
    
    results = []
    for file in experts_path.glob("**/*.ex5"):
        results.append(str(file))
    return sorted(results)