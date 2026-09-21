"""
Golden AI - Wrappers Browser / Documentos / Audio / Video / Vision

Extraído de golden_ai.py (linhas 8466-8600).
Wrappers para os serviços de mídia do core.
"""

from .context import SERVICES, ROOT_GOLDENAI


# ============================================================
# BROWSER
# ============================================================

def browser_search(query=None, max_results=5):
    """Busca na web usando o BrowserService."""
    if not SERVICES.BROWSER:
        return dict(ok=False, erro="Browser indisponivel.")
    result = SERVICES.BROWSER.search_web(query or "", int(max_results))
    if result.status != "COMPLETED":
        return dict(ok=False, erro=result.error or result.status)
    return dict(
        ok=True,
        query=query or "",
        results=result.metadata.get("results", []),
        engine=result.metadata.get("engine", ""),
        is_untrusted=True,
    )


def browser_fetch(url=None, screenshot=False):
    """Busca conteúdo de uma URL com browser headless."""
    if not SERVICES.BROWSER:
        return dict(ok=False, erro="Browser indisponivel.")
    result = SERVICES.BROWSER.fetch_page(url or "", screenshot=bool(screenshot))
    if result.status != "COMPLETED":
        return dict(ok=False, erro=result.error or result.status)
    return dict(
        ok=True,
        url=result.url,
        title=result.title,
        content=result.text[:120000],
        screenshot_path=result.screenshot_path or "",
        duration_ms=result.duration_ms,
        is_untrusted=True,
    )


# ============================================================
# DOCUMENTOS
# ============================================================

def document_extract(nome=None):
    """Extrai texto de documentos (PDF, DOCX, etc)."""
    if not SERVICES.DOCUMENT:
        return dict(ok=False, erro="Docling indisponivel.")
    result = SERVICES.DOCUMENT.extract(nome or "")
    if result.status != "COMPLETED":
        return dict(ok=False, erro=result.error or result.status)
    return dict(
        ok=True,
        nome=nome or "",
        title=result.title,
        file_type=result.file_type,
        page_count=result.page_count,
        char_count=result.char_count,
        content=result.text,
        duration_ms=result.duration_ms,
    )


# ============================================================
# AUDIO
# ============================================================

def audio_transcribe(nome=None, language=None):
    """Transcreve áudio usando Whisper."""
    if not SERVICES.AUDIO:
        return dict(ok=False, erro="Whisper indisponivel.")
    result = SERVICES.AUDIO.transcribe(nome or "", language=language)
    if result.status != "COMPLETED":
        return dict(ok=False, erro=result.error or result.status)
    return dict(
        ok=True,
        nome=nome or "",
        text=result.text,
        language=result.language,
        language_probability=result.language_probability,
        duration_sec=result.duration_sec,
        segments=result.segments,
        duration_ms=result.duration_ms,
    )


# ============================================================
# VIDEO
# ============================================================

def video_analyze(nome=None, max_frames=6):
    """Analisa vídeo usando FFmpeg + Whisper + Vision."""
    if not SERVICES.VIDEO:
        return dict(ok=False, erro="Video indisponivel.")
    result = SERVICES.VIDEO.analyze(nome or "", max_frames=int(max_frames))
    if result.status != "COMPLETED":
        return dict(ok=False, erro=result.error or result.status)
    return dict(
        ok=True,
        nome=nome or "",
        text=result.text,
        transcript=result.transcript,
        scene_notes=result.scene_notes,
        duration_sec=result.duration_sec,
        frames=result.frames,
        duration_ms=result.duration_ms,
    )


# ============================================================
# VISION
# ============================================================

def vision_analyze_image(imagem=None, pergunta=None):
    """Analisa imagem usando VisionService."""
    if not SERVICES.VISION:
        return dict(ok=False, erro="Vision indisponivel.")

    alvo = imagem or ""
    if not alvo:
        return dict(ok=False, erro="Nenhuma imagem informada.")

    result = SERVICES.VISION.analyze_images([alvo], pergunta or "Descreva a imagem.")
    if result.status != "COMPLETED":
        return dict(ok=False, erro=result.status)

    return dict(ok=True, texto=result.text, latency_ms=result.latency_ms, imagem=alvo)


# ============================================================
# VECTOR MEMORY (Qdrant)
# ============================================================

def memory_vector_store(texto=None, fonte="", tipo="nota", tags=None):
    """Armazena texto na memória vetorial."""
    if not SERVICES.VECTOR_MEMORY:
        return dict(ok=False, erro="Qdrant indisponivel.")
    if not texto:
        return dict(ok=False, erro="Texto vazio.")
    result = SERVICES.VECTOR_MEMORY.store(texto, source=fonte, kind=tipo, tags=tags)
    return dict(ok=result.get("status") == "COMPLETED", **result)


def memory_vector_search(consulta=None, limite=5, tipo=None):
    """Busca na memória vetorial."""
    if not SERVICES.VECTOR_MEMORY:
        return dict(ok=False, erro="Qdrant indisponivel.")
    result = SERVICES.VECTOR_MEMORY.search(consulta or "", limit=int(limite), kind=tipo)
    if result.status != "COMPLETED":
        return dict(ok=False, erro=result.error or result.status)
    return dict(
        ok=True,
        query=consulta or "",
        results=result.matches,
        duration_ms=result.duration_ms,
    )


# ============================================================
# STATUS DOS MÓDULOS
# ============================================================

def status_modulos_v110():
    """Retorna status de todos os módulos V1.10."""
    linhas = []
    for nome, svc in (
        ("Browser", SERVICES.BROWSER),
        ("Documentos", SERVICES.DOCUMENT),
        ("Audio", SERVICES.AUDIO),
        ("Video", SERVICES.VIDEO),
        ("Vision", SERVICES.VISION),
        ("Qdrant", SERVICES.VECTOR_MEMORY),
    ):
        try:
            st = svc.status() if svc else {}
            chave = [k for k in st if "SUPPORTED" in k or "AVAILABLE" in k or "VISION_AVAILABLE" in k]
            flag = st.get(chave[0]) if chave else bool(svc)
            linhas.append(f'{nome}: {"OK" if flag else "INDISPONIVEL"}')
        except Exception:
            linhas.append(f"{nome}: INDISPONIVEL")

    return "\n".join(linhas)
