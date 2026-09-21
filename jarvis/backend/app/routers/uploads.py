from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..config import Settings
from ..dependencies import client_ip, get_current_user, get_db
from ..models import Arquivo, Usuario
from ..schemas import ArquivoPublic, MessageResponse
from ..services.file_storage import remove_physical_file, save_upload_file


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


def _public(arquivo: Arquivo, mensagem: str | None = None) -> ArquivoPublic:
    return ArquivoPublic(
        id=arquivo.id,
        status=arquivo.status,
        nome_original=arquivo.nome_original,
        tamanho_bytes=arquivo.tamanho_bytes,
        mime_type=arquivo.mime_type,
        hash_sha256=arquivo.hash_sha256,
        criado_em=arquivo.criado_em,
        atualizado_em=arquivo.atualizado_em,
        mensagem=mensagem,
    )


@router.post("", response_model=ArquivoPublic, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = Settings()
    try:
        saved = await save_upload_file(file, settings.upload_max_bytes)
        arquivo = Arquivo(usuario_id=usuario.id, status="recebido", **saved)
        db.add(arquivo)
        db.commit()
        db.refresh(arquivo)
        registrar_auditoria(db, usuario.id, "upload_recebido", "uploads", f"Arquivo recebido: {arquivo.nome_original}", client_ip(request), True)
        public = _public(arquivo, "Arquivo recebido e aguardando analise.")
        return public
    except HTTPException as exc:
        registrar_auditoria(db, usuario.id, "upload_recusado", "uploads", str(exc.detail), client_ip(request), False)
        raise
    except Exception as exc:
        registrar_auditoria(db, usuario.id, "erro_interno", "uploads", str(exc), client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao salvar arquivo")


@router.get("", response_model=list[ArquivoPublic])
def list_uploads(usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    arquivos = (
        db.query(Arquivo)
        .filter(Arquivo.usuario_id == usuario.id, Arquivo.status != "excluido")
        .order_by(Arquivo.id.desc())
        .all()
    )
    return [_public(item) for item in arquivos]


@router.get("/{arquivo_id}", response_model=ArquivoPublic)
def get_upload(arquivo_id: int, usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    arquivo = db.query(Arquivo).filter(Arquivo.id == arquivo_id, Arquivo.usuario_id == usuario.id, Arquivo.status != "excluido").first()
    if not arquivo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo nao encontrado")
    return _public(arquivo)


@router.get("/{arquivo_id}/content")
def get_upload_content(arquivo_id: int, usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    arquivo = db.query(Arquivo).filter(Arquivo.id == arquivo_id, Arquivo.usuario_id == usuario.id, Arquivo.status != "excluido").first()
    if not arquivo or not Path(arquivo.caminho_seguro).is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo nao encontrado")
    return FileResponse(arquivo.caminho_seguro, media_type=arquivo.mime_type, filename=arquivo.nome_original)


@router.delete("/{arquivo_id}", response_model=MessageResponse)
def delete_upload(
    arquivo_id: int,
    request: Request,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    arquivo = db.query(Arquivo).filter(Arquivo.id == arquivo_id, Arquivo.usuario_id == usuario.id, Arquivo.status != "excluido").first()
    if not arquivo:
        registrar_auditoria(db, usuario.id, "exclusao_upload_negada", "uploads", f"Arquivo nao encontrado: {arquivo_id}", client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo nao encontrado")

    try:
        remove_physical_file(arquivo.caminho_seguro)
        arquivo.status = "excluido"
        db.commit()
        registrar_auditoria(db, usuario.id, "upload_excluido", "uploads", f"Arquivo excluido: {arquivo.nome_original}", client_ip(request), True)
        return {"ok": True, "message": "Arquivo excluido"}
    except Exception as exc:
        registrar_auditoria(db, usuario.id, "erro_exclusao_upload", "uploads", str(exc), client_ip(request), False)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao excluir arquivo")
