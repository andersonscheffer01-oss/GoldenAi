from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from ..config import ROOT_DIR


UPLOAD_ROOT = ROOT_DIR / "uploads"
PENDING_DIR = UPLOAD_ROOT / "pending"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def ensure_upload_dirs() -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)


def detect_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _safe_extension(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Extensao de arquivo nao permitida")
    return suffix


async def save_upload_file(upload: UploadFile, max_bytes: int) -> dict:
    ensure_upload_dirs()
    original_name = Path(upload.filename or "arquivo").name
    suffix = _safe_extension(original_name)
    content = await upload.read()
    size = len(content)
    if size <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo vazio")
    if size > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Arquivo acima do limite permitido")

    real_mime = detect_mime(content)
    if real_mime not in ALLOWED_MIME:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo real do arquivo nao permitido")
    if upload.content_type and upload.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MIME type informado nao permitido")

    internal_name = f"{uuid4().hex}{suffix}"
    destination = (PENDING_DIR / internal_name).resolve()
    if not str(destination).startswith(str(PENDING_DIR.resolve())):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Caminho de arquivo invalido")

    with open(destination, "xb") as file:
        file.write(content)

    return {
        "nome_original": original_name,
        "nome_interno": internal_name,
        "caminho_seguro": str(destination),
        "mime_type": real_mime,
        "tamanho_bytes": size,
        "hash_sha256": hashlib.sha256(content).hexdigest(),
    }


def remove_physical_file(path: str) -> bool:
    resolved = Path(path).resolve()
    upload_root = UPLOAD_ROOT.resolve()
    if not str(resolved).startswith(str(upload_root)):
        raise ValueError("Caminho fora da pasta de uploads")
    if resolved.exists() and resolved.is_file():
        os.remove(resolved)
        return True
    return False
