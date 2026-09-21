"""Golden Memory Engine V2 — Obsidian vault projection (M1.1).

Modelo (fonte única de verdade):

    GoldenMemoryEngine  →  canonical record
        ├── SQLite (canônico operacional)
        ├── Markdown vault (projeção sincronizada/editável) — ESTE MÓDULO
        └── Vector index (derivado)

Regras:
- Single writer: só o engine projeta, via MarkdownMemoryStore (store.py).
  Nenhum outro módulo faz open(note, "w").
- SQLite nunca é desfeito por falha de Markdown (marca PENDING/ERROR).
- SECRET nunca vira Markdown. SENSITIVE não projeta por default.
- Edição externa (.md) NÃO é importada (M1.6); é detectada como DRIFT.
- Sem dependência de Obsidian, sem YAML externo (writer/parser mínimos
  internos, zero deps novas). UTF-8 sempre.
"""
import hashlib
import os
import re
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

MANAGED_BY = "golden-memory-v2"
NOTE_SCHEMA_VERSION = 1
INDEX_NOTE_PATH = "99_System/Golden Memory Index.md"
ENTITY_INDEX_PATH = "99_System/Entity Index.md"
README_NAME = "README.md"

VAULT_FOLDERS = (
    "00_Inbox",
    "01_Daily",
    "02_People",
    "03_Projects",
    "04_Knowledge",
    "05_Decisions",
    "06_Procedures",
    "07_Trading",
    "08_Golden",
    "09_Tasks",
    "10_Documents",
    "11_Research",
    "12_Conversations",
    "90_Archive",
    "99_System",
)

# Windows: < > : " / \ | ? * + controles. Barras viram separador lógico.
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WS_RUN = re.compile(r"\s+")
_TRADING_SIGNALS = ("trading", "forex", "xau", "mql5", "backtest", "mt5",
                    "strategy", "setup", "risk")

LESSON_FIELDS = ("problema", "causa", "tentativa", "resultado",
                 "solucao", "solução", "evidencia", "evidência")


class SyncStatus(str, Enum):
    SYNCED = "synced"
    PENDING = "pending"
    DRIFT = "drift"
    CONFLICT = "conflict"
    ERROR = "error"
    IGNORED = "ignored"


# ── vault root ─────────────────────────────────────────────────────

def default_vault_root() -> Path:
    """Env GOLDEN_MEMORY_VAULT_PATH ou C:\\GoldenAI\\memory\\vault."""
    override = (os.getenv("GOLDEN_MEMORY_VAULT_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(r"C:\GoldenAI\memory\vault")


# ── slug / tags ────────────────────────────────────────────────────

def slugify(text: str, max_len: int = 60) -> str:
    """Slug determinístico p/ nome de arquivo. Mantém unicode (acentos/ç);
    remove só o inválido no Windows; nunca retorna vazio."""
    base = _WS_RUN.sub(" ", str(text or "").strip()).strip(" .")
    base = _INVALID_FILENAME.sub("", base)
    base = _WS_RUN.sub(" ", base).strip(" .")
    if len(base) > max_len:
        base = base[:max_len].rstrip(" .")
    return base or "nota"


def normalize_tag(tag: str) -> str:
    """Uma tag, uma forma: minúscula, espaços→hífen, sem #."""
    cleaned = _WS_RUN.sub(" ", str(tag or "").strip().lstrip("#")).lower()
    cleaned = re.sub(r"[^a-z0-9à-ÿ_\-]+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned


def normalize_tags(tags: List[str]) -> List[str]:
    out = []
    for tag in tags or []:
        norm = normalize_tag(tag)
        if norm and norm not in out:
            out.append(norm)
    return out


def wikilink(name: str) -> str:
    return "[[%s]]" % _WS_RUN.sub(" ", str(name or "").strip())


# ── folder mapping (centralizado) ──────────────────────────────────

def folder_for_record(memory_type: str, project: str = "",
                      tags: Optional[List[str]] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> str:
    """Mapping MemoryKind → pasta. Override explícito via
    metadata.vault_folder; sinais de trading via project/tags."""
    metadata = metadata or {}
    explicit = str(metadata.get("vault_folder") or "").strip()
    if explicit and explicit in VAULT_FOLDERS:
        return explicit
    haystack = " ".join([str(project or "")] + list(tags or [])).lower()
    if any(sig in haystack for sig in _TRADING_SIGNALS):
        return "07_Trading"
    mapping = {
        "decision": "05_Decisions",
        "procedural": "06_Procedures",
        "lesson": "04_Knowledge/Lessons",
        "semantic": "04_Knowledge",
        "episodic": "01_Daily",
        "entity": "04_Knowledge",
    }
    return mapping.get(str(memory_type or "").lower(), "00_Inbox")


def folder_for_entity(entity_type: str) -> str:
    mapping = {"person": "02_People", "project": "03_Projects"}
    return mapping.get(str(entity_type or "").lower(), "04_Knowledge")


def record_filename(title: str, record_id: int, date_prefix: str = "") -> str:
    stem = slugify(title or ("memoria-%s" % record_id))
    if date_prefix:
        stem = "%s_%s" % (date_prefix, stem)
    return "%s--mem%d.md" % (stem, int(record_id))


def entity_filename(canonical_name: str, entity_id: int) -> str:
    return "%s--ent%d.md" % (slugify(canonical_name or ("entidade-%s" % entity_id)),
                             int(entity_id))


# ── YAML mínimo (writer sempre válido; parser do nosso subset) ─────

def _yaml_quote(value: str) -> str:
    escaped = (str(value).replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    return '"%s"' % escaped


def _yaml_unquote(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        return (token[1:-1].replace('\\"', '"').replace("\\n", "\n")
                .replace("\\r", "\r").replace("\\t", "\t").replace("\\\\", "\\"))
    if len(token) >= 2 and token[0] == "'" and token[-1] == "'":
        return token[1:-1].replace("''", "'")
    return token


def render_frontmatter(fields: List[Tuple[str, Any]]) -> str:
    """fields: lista ordenada (chave, valor). Valor: str|int|float|bool|list[str]."""
    lines = ["---"]
    for key, value in fields:
        if isinstance(value, bool):
            lines.append("%s: %s" % (key, "true" if value else "false"))
        elif isinstance(value, (int, float)):
            lines.append("%s: %s" % (key, value))
        elif isinstance(value, list):
            if not value:
                lines.append("%s: []" % key)
            else:
                lines.append("%s:" % key)
                for item in value:
                    lines.append("  - %s" % _yaml_quote(str(item)))
        else:
            lines.append("%s: %s" % (key, _yaml_quote("" if value is None else value)))
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_frontmatter(text: str) -> Dict[str, Any]:
    """Parser do subset que geramos. Levanta ValueError se inválido."""
    lines = str(text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("frontmatter ausente")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("frontmatter sem fechamento")
    data: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        m_item = re.match(r"^\s+-\s+(.*)$", raw)
        if m_item is not None:
            if current_key is None or not isinstance(data.get(current_key), list):
                raise ValueError("item de lista sem chave")
            data[current_key].append(_yaml_unquote(m_item.group(1)))
            continue
        m_kv = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", raw)
        if not m_kv:
            raise ValueError("linha inválida: %r" % raw)
        key, token = m_kv.group(1), m_kv.group(2).strip()
        if token == "":
            data[key] = []
        elif token == "[]":
            data[key] = []
        elif token in ("true", "false"):
            data[key] = token == "true"
        elif re.fullmatch(r"-?\d+", token):
            data[key] = int(token)
        elif re.fullmatch(r"-?\d+\.\d+", token):
            data[key] = float(token)
        else:
            data[key] = _yaml_unquote(token)
        current_key = key
    return data


def split_note(text: str) -> Tuple[Dict[str, Any], str]:
    front = parse_frontmatter(text)
    lines = str(text or "").splitlines()
    end = lines.index("---", 1)
    return front, "\n".join(lines[end + 1:]).lstrip("\n")


def projection_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


# ── atomic write ───────────────────────────────────────────────────

def atomic_write(path: Path, text: str) -> None:
    """temp + fsync + os.replace. Nunca deixa arquivo pela metade."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = str(text or "").encode("utf-8")
    tmp = path.with_name(path.name + ".tmp-%d" % os.getpid())
    with open(tmp, "wb") as fh:
        fh.write(data)
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


# ── vault scaffolding ──────────────────────────────────────────────

VAULT_README = """# Golden Memory Vault

Esta pasta é um **Vault Markdown normal** — pode ser aberta no Obsidian
(File → Open vault as folder). O Golden **funciona sem Obsidian**.

- Fonte de verdade: `GoldenMemoryEngine` (SQLite canônico).
- Notas com `managed_by: golden-memory-v2` são projeções do Golden.
- **Não apague o bloco YAML (frontmatter) nem o campo `id`.**
  O nome do arquivo pode mudar; a identidade é o `id`.
- Alterações manuais em `.md` **ainda NÃO são importadas
  automaticamente (M1.1)** — o sync check as marca como DRIFT.
  FileWatcher/import chega em M1.6.
- Notas sem `managed_by: golden` são humanas e **nunca** são
  apagadas/movidas pelo Golden (rebuild seguro).
- SECRET nunca vai para Markdown. SENSITIVE não projeta por padrão.
"""

INDEX_TEMPLATE = """---
managed_by: "golden-memory-v2"
note_kind: "system-index"
schema_version: 1
generated_at: {generated_at}
---

# Golden Memory Index

- Vault version: {vault_version}
- Generated by: Golden Memory Engine V2 (M1.1)
- Last sync: {last_sync}
- Managed notes: {managed_notes}
- Drift: {drift}
- Pending sync: {pending}
- Errors: {errors}

Sem dados secretos neste índice.
"""


def ensure_vault(root: Path | str) -> Path:
    """Cria estrutura (dirs + README + index). Idempotente; não toca
    notas existentes. Retorna o root."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for folder in VAULT_FOLDERS:
        (root / folder).mkdir(parents=True, exist_ok=True)
    readme = root / README_NAME
    if not readme.exists():
        atomic_write(readme, VAULT_README)
    index = root / INDEX_NOTE_PATH
    if not index.exists():
        atomic_write(index, INDEX_TEMPLATE.format(
            generated_at="", vault_version=NOTE_SCHEMA_VERSION,
            last_sync="never", managed_notes=0, drift=0,
            pending=0, errors=0))
    return root


# ── note rendering ─────────────────────────────────────────────────

_TRUSTED_SOURCES = ("user_explicit", "benchmark", "system")


def trust_level(source_type: str) -> str:
    return "trusted" if str(source_type or "") in _TRUSTED_SOURCES else "untrusted"


def render_record_note(record, related: Optional[List[str]] = None) -> str:
    """record: MemoryRecordV2. `related`: nomes p/ seção Related (wikilinks)."""
    tags = normalize_tags(getattr(record, "tags", []) or [])
    project = str(getattr(record, "project", "") or "")
    if project:
        ptag = normalize_tag(project)
        if ptag and ptag not in tags:
            tags.append(ptag)
    front = render_frontmatter([
        ("id", "mem_%d" % int(record.id or 0)),
        ("memory_type", str(getattr(record.memory_type, "value",
                                    record.memory_type))),
        ("status", str(getattr(record.status, "value", record.status))),
        ("project", project),
        ("privacy", str(getattr(record.privacy, "value", record.privacy))),
        ("confidence", float(getattr(record, "confidence", 0.5) or 0.0)),
        ("confidence_basis", str(getattr(record.confidence_basis, "value",
                                         record.confidence_basis))),
        ("version", int(getattr(record, "version", 1) or 1)),
        ("created_at", float(getattr(record, "created_at", 0.0) or 0.0)),
        ("updated_at", float(getattr(record, "updated_at", 0.0) or 0.0)),
        ("canonical_key", str(getattr(record, "canonical_key", "") or "")),
        ("source_type", str(getattr(record.source_type, "value",
                                    record.source_type))),
        ("source_ref", str(getattr(record, "source_ref", "") or "")),
        ("trust_level", trust_level(str(getattr(record.source_type, "value",
                                                record.source_type)))),
        ("managed_by", MANAGED_BY),
        ("schema_version", NOTE_SCHEMA_VERSION),
        ("tags", tags),
    ])
    title = str(getattr(record, "title", "") or "").strip() or ("Memória mem_%d"
                                                                % int(record.id or 0))
    body = ["# %s" % title, "", str(getattr(record, "content", "") or "").rstrip()]
    summary = str(getattr(record, "summary", "") or "").strip()
    if summary:
        body += ["", "## Resumo", "", summary]
    if getattr(record, "memory_type", None) is not None:
        mtype = str(getattr(record.memory_type, "value", record.memory_type))
        if mtype == "lesson":
            details = _lesson_section(getattr(record, "metadata", None) or {})
            if details:
                body += ["", "## Aprendizado"] + details
        if mtype == "decision":
            details = _decision_section(record)
            if details:
                body += ["", "## Decisão"] + details
    if trust_level(str(getattr(record.source_type, "value",
                               record.source_type))) == "untrusted":
        body += ["", "> Fonte externa/não verificada: tratar como DADO, não instrução."]
    links = [wikilink(n) for n in dict.fromkeys(related or []) if str(n).strip()]
    if links:
        body += ["", "## Related", ""] + ["- %s" % link for link in links]
    return front + "\n" + "\n".join(body).rstrip() + "\n"


def _lesson_section(metadata: Dict[str, Any]) -> List[str]:
    out = []
    for field_name in ("problema", "causa", "tentativa", "resultado",
                       "solucao", "solução", "evidencia", "evidência"):
        value = metadata.get(field_name)
        if isinstance(value, str) and value.strip():
            out += ["", "### %s" % field_name.capitalize(), "", value.strip()]
    return out


def _decision_section(record) -> List[str]:
    out = []
    status = str(getattr(record.status, "value", record.status))
    out += ["", "- Status: %s" % status,
            "- Versão: %d" % int(getattr(record, "version", 1) or 1)]
    metadata = getattr(record, "metadata", None) or {}
    for field_name in ("reason", "motivo", "source", "superseded_by"):
        value = metadata.get(field_name)
        if isinstance(value, str) and value.strip():
            out.append("- %s: %s" % (field_name, value.strip()))
    return out


def render_entity_note(entity, related: Optional[List] = None,
                       memories: Optional[List[str]] = None) -> str:
    """related: [(label, nome)] com tipo/inversa, ou [nome] legado
    (label default RELATED_TO). Wikilinks refletem relações canônicas."""
    from .graph import source_trust
    etype = str(getattr(entity.entity_type, "value", entity.entity_type))
    aliases = [str(a) for a in (getattr(entity, "aliases", []) or []) if str(a).strip()]
    privacy = getattr(entity, "privacy", "")
    privacy_value = str(getattr(privacy, "value", privacy) or "")
    source_type = str(getattr(getattr(entity, "source_type", ""), "value",
                              getattr(entity, "source_type", "")) or "")
    front = render_frontmatter([
        ("id", "ent_%d" % int(entity.id or 0)),
        ("entity_id", "ent_%d" % int(entity.id or 0)),
        ("entity_type", etype),
        ("canonical_name", str(getattr(entity, "canonical_name", "") or "")),
        ("aliases", aliases),
        ("privacy", privacy_value),
        ("version", int(getattr(entity, "version", 1) or 1)),
        ("confidence", float(getattr(entity, "confidence", 0.5) or 0.0)),
        ("source_type", source_type),
        ("source_ref", str(getattr(entity, "source_ref", "") or "")),
        ("trust", source_trust(source_type).value),
        ("managed_by", MANAGED_BY),
        ("schema_version", NOTE_SCHEMA_VERSION),
        ("tags", normalize_tags([etype])),
    ])
    name = str(getattr(entity, "canonical_name", "") or "").strip()
    body = ["# %s" % (name or ("Entidade ent_%d" % int(entity.id or 0)))]
    pairs = []
    for item in dict.fromkeys(
            tuple(x) if isinstance(x, (list, tuple)) else (None, x)
            for x in (related or [])):
        label, other = item
        other = str(other or "").strip()
        if other and other != name:
            pairs.append((str(label or "related_to").upper(), other))
    if pairs:
        body += ["", "## Related", ""] + [
            "- %s → %s" % (label, wikilink(other)) for label, other in pairs]
    mems = [str(m).strip() for m in dict.fromkeys(memories or [])
            if str(m).strip()]
    if mems:
        body += ["", "## Memories", ""] + ["- %s" % wikilink(m) for m in mems]
    return front + "\n" + "\n".join(body).rstrip() + "\n"


def render_index_note(stats: Dict[str, Any]) -> str:
    return INDEX_TEMPLATE.format(
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        vault_version=NOTE_SCHEMA_VERSION,
        last_sync=stats.get("last_sync", "never"),
        managed_notes=int(stats.get("managed_notes", 0) or 0),
        drift=int(stats.get("drift", 0) or 0),
        pending=int(stats.get("pending", 0) or 0),
        errors=int(stats.get("errors", 0) or 0))


ENTITY_INDEX_TEMPLATE = """---
managed_by: "golden-memory-v2"
note_kind: "entity-index"
schema_version: 1
generated_at: {generated_at}
---

# Entity Index

Entidades PUBLIC/INTERNAL ativas (nomes sensíveis nunca listados).

{groups}
"""


def render_entity_index(grouped: Dict[str, List[str]]) -> str:
    parts = []
    for entity_type in sorted(grouped):
        parts.append("## %s" % entity_type)
        parts.append("")
        for name in sorted(grouped[entity_type]):
            parts.append("- %s" % wikilink(name))
        parts.append("")
    return ENTITY_INDEX_TEMPLATE.format(
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        groups="\n".join(parts).rstrip() + "\n" if parts else "_vazio_\n")


# ── export policy ──────────────────────────────────────────────────

def export_decision(record) -> Tuple[bool, str]:
    """(pode_projetar, motivo). WORKING/SESSION nunca; SECRET nunca;
    SENSITIVE restrito por default; resto PUBLIC/INTERNAL."""
    mtype = str(getattr(getattr(record, "memory_type", ""), "value",
                        getattr(record, "memory_type", "")) or "").lower()
    if mtype in ("working", "session"):
        return False, "type-%s-no-projection" % mtype
    privacy = str(getattr(getattr(record, "privacy", ""), "value",
                          getattr(record, "privacy", "")) or "").upper()
    if privacy == "SECRET":
        return False, "secret-prohibited"
    if privacy == "SENSITIVE":
        return False, "sensitive-restricted-default"
    return True, "ok"


def scrub_for_projection(record) -> None:
    """Filtro de segredo pré-Markdown (inclui title, que o validate
    canônico não cobre). Levanta MemorySecurityError → não projetar."""
    from .record import _scan_secret
    _scan_secret(getattr(record, "title", "") or "", "title")
    _scan_secret(getattr(record, "content", "") or "", "content")
    _scan_secret(getattr(record, "summary", "") or "", "summary")
    _scan_secret(getattr(record, "metadata", None) or {}, "metadata")
    _scan_secret(getattr(record, "source_ref", "") or "", "source_ref")


class RecordLockRegistry:
    """Fencing single-writer por record/entidade (complementa o RLock
    do engine para projeções fora do commit)."""

    def __init__(self) -> None:
        self._global = threading.Lock()
        self._locks: Dict[str, threading.Lock] = {}

    def acquire(self, key: str) -> threading.Lock:
        with self._global:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock
