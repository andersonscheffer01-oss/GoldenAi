from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..audit import registrar_auditoria
from ..config import Settings
from ..dependencies import client_ip, get_current_user, get_db
from ..models import AnaliseComprovante, Arquivo, Usuario
from ..schemas import ReceiptAnalysisPublic, ReceiptConfirmRequest
from ..services.receipt_analyzer import analyze_document
from ..services.receipt_parser import ReceiptParserError, prepare_document


router = APIRouter(prefix="/api", tags=["comprovantes"])
_processing_files: set[int] = set()
_MAX_ATTEMPTS = 3


def _now():
    return datetime.now(timezone.utc)


def _public(analysis: AnaliseComprovante) -> ReceiptAnalysisPublic:
    extracted = None
    if analysis.dados_extraidos_json:
        try:
            extracted = json.loads(analysis.dados_extraidos_json)
        except json.JSONDecodeError:
            extracted = None
    return ReceiptAnalysisPublic(
        id=analysis.id, arquivo_id=analysis.arquivo_id, tipo_documento=analysis.tipo_documento,
        status=analysis.status, dados_extraidos=extracted, confianca_geral=analysis.confianca_geral,
        erro_codigo=analysis.erro_codigo, erro_mensagem=analysis.erro_mensagem,
        tentativas=analysis.tentativas, criado_em=analysis.criado_em, atualizado_em=analysis.atualizado_em,
        confirmado_em=analysis.confirmado_em, cancelado_em=analysis.cancelado_em,
    )


def _owned_file(db: Session, file_id: int, user: Usuario) -> Arquivo:
    arquivo = db.query(Arquivo).filter(Arquivo.id == file_id, Arquivo.usuario_id == user.id).first()
    if not arquivo:
        raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "Arquivo nao encontrado."})
    if arquivo.status == "excluido":
        raise HTTPException(status_code=400, detail={"code": "FILE_NOT_FOUND", "message": "O arquivo foi excluido."})
    return arquivo


async def _run_analysis(analysis: AnaliseComprovante, arquivo: Arquivo, user: Usuario, request: Request, db: Session) -> ReceiptAnalysisPublic:
    settings = Settings()
    analysis.status = "processando"
    analysis.tentativas += 1
    analysis.erro_codigo = None
    analysis.erro_mensagem = None
    db.commit()
    try:
        if not Path(arquivo.caminho_seguro).is_file():
            raise ReceiptParserError("FILE_NOT_FOUND", "Arquivo fisico nao encontrado.")
        prepared = prepare_document(arquivo.caminho_seguro, arquivo.mime_type, settings)
        extracted, raw = await analyze_document(prepared, settings)
        analysis.tipo_documento = extracted.tipo_documento
        analysis.resposta_bruta = raw
        analysis.dados_extraidos_json = extracted.model_dump_json()
        analysis.confianca_geral = extracted.confianca.geral
        analysis.status = "requer_confirmacao" if extracted.confianca.geral < 0.9 or extracted.valor_total is None or extracted.tipo_documento == "documento_desconhecido" else "concluida"
        db.commit()
        registrar_auditoria(db, user.id, "comprovante_analisado", "comprovantes", f"Analise {analysis.id} concluida", client_ip(request), True)
    except ReceiptParserError as error:
        analysis.status = "erro"
        analysis.erro_codigo = error.code
        analysis.erro_mensagem = error.public_message
        db.commit()
        registrar_auditoria(db, user.id, "analise_comprovante_erro", "comprovantes", error.code, client_ip(request), False)
    except Exception as error:
        analysis.status = "erro"
        analysis.erro_codigo = "INVALID_EXTRACTED_DATA"
        analysis.erro_mensagem = "Nao foi possivel concluir a analise do comprovante."
        db.commit()
        registrar_auditoria(db, user.id, "analise_comprovante_erro", "comprovantes", str(error), client_ip(request), False)
    finally:
        _processing_files.discard(arquivo.id)
    return _public(analysis)


@router.post("/comprovantes/{arquivo_id}/analisar", response_model=ReceiptAnalysisPublic, status_code=202)
async def analyze_receipt(arquivo_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    arquivo = _owned_file(db, arquivo_id, user)
    if arquivo_id in _processing_files:
        raise HTTPException(status_code=409, detail={"code": "FILE_ALREADY_PROCESSING", "message": "Este arquivo ja esta sendo analisado."})
    analysis = db.query(AnaliseComprovante).filter(AnaliseComprovante.arquivo_id == arquivo_id, AnaliseComprovante.usuario_id == user.id).order_by(AnaliseComprovante.id.desc()).first()
    if analysis and analysis.tentativas >= _MAX_ATTEMPTS and analysis.status == "erro":
        raise HTTPException(status_code=429, detail={"code": "MAX_ATTEMPTS_REACHED", "message": "Limite de tentativas atingido."})
    if analysis is None:
        analysis = AnaliseComprovante(arquivo_id=arquivo_id, usuario_id=user.id, status="aguardando")
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
    _processing_files.add(arquivo_id)
    return await _run_analysis(analysis, arquivo, user, request, db)


@router.get("/comprovantes/{arquivo_id}/analise", response_model=ReceiptAnalysisPublic)
def get_receipt_analysis(arquivo_id: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned_file(db, arquivo_id, user)
    analysis = db.query(AnaliseComprovante).filter(AnaliseComprovante.arquivo_id == arquivo_id, AnaliseComprovante.usuario_id == user.id).order_by(AnaliseComprovante.id.desc()).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analise nao encontrada")
    return _public(analysis)


@router.post("/analises/{analise_id}/confirmar", response_model=ReceiptAnalysisPublic)
def confirm_receipt(analise_id: int, payload: ReceiptConfirmRequest, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(AnaliseComprovante).filter(AnaliseComprovante.id == analise_id, AnaliseComprovante.usuario_id == user.id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analise nao encontrada")
    data = payload.dados
    if data.valor_total is None or data.valor_total < 0:
        raise HTTPException(status_code=422, detail="Informe um valor total valido antes de confirmar.")
    if data.data:
        try:
            datetime.strptime(data.data, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Data invalida. Use YYYY-MM-DD.") from exc
    if data.ultimos_quatro_digitos and len(data.ultimos_quatro_digitos) > 4:
        raise HTTPException(status_code=422, detail="Armazene somente os quatro ultimos digitos do cartao.")
    analysis.tipo_documento = data.tipo_documento
    analysis.dados_extraidos_json = data.model_dump_json()
    analysis.confianca_geral = data.confianca.geral
    analysis.status = "confirmada"
    analysis.confirmado_em = _now()
    analysis.cancelado_em = None
    db.commit()
    registrar_auditoria(db, user.id, "analise_comprovante_confirmada", "comprovantes", f"Analise {analise_id} confirmada", client_ip(request), True)
    return _public(analysis)


@router.post("/analises/{analise_id}/cancelar", response_model=ReceiptAnalysisPublic)
def cancel_receipt(analise_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(AnaliseComprovante).filter(AnaliseComprovante.id == analise_id, AnaliseComprovante.usuario_id == user.id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analise nao encontrada")
    analysis.status = "cancelada"
    analysis.cancelado_em = _now()
    db.commit()
    registrar_auditoria(db, user.id, "analise_comprovante_cancelada", "comprovantes", f"Analise {analise_id} cancelada", client_ip(request), True)
    return _public(analysis)


@router.post("/analises/{analise_id}/reanalisar", response_model=ReceiptAnalysisPublic, status_code=202)
async def retry_receipt(analise_id: int, request: Request, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(AnaliseComprovante).filter(AnaliseComprovante.id == analise_id, AnaliseComprovante.usuario_id == user.id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analise nao encontrada")
    arquivo = _owned_file(db, analysis.arquivo_id, user)
    if analysis.tentativas >= _MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail={"code": "MAX_ATTEMPTS_REACHED", "message": "Limite de tentativas atingido."})
    if analysis.arquivo_id in _processing_files:
        raise HTTPException(status_code=409, detail={"code": "FILE_ALREADY_PROCESSING", "message": "Este arquivo ja esta sendo analisado."})
    _processing_files.add(analysis.arquivo_id)
    return await _run_analysis(analysis, arquivo, user, request, db)
