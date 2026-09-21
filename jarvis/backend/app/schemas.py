from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, EmailStr, Field, field_validator


class UsuarioCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=180)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=200)


class UsuarioPublic(BaseModel):
    id: int
    nome: str
    email: EmailStr
    ativo: bool
    criado_em: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    usuario: UsuarioPublic


class MessageResponse(BaseModel):
    ok: bool
    message: str


class ArquivoPublic(BaseModel):
    id: int
    status: str
    nome_original: str
    tamanho_bytes: int
    mime_type: str
    hash_sha256: str
    criado_em: datetime
    atualizado_em: datetime
    mensagem: str | None = None

    model_config = {"from_attributes": True}


class ConversaCreate(BaseModel):
    titulo: str = Field(default="Nova conversa", min_length=1, max_length=80)


class ConversaPublic(BaseModel):
    id: int
    titulo: str
    ativa: bool
    criada_em: datetime
    atualizada_em: datetime

    model_config = {"from_attributes": True}


class MensagemPublic(BaseModel):
    id: int
    role: str = Field(validation_alias="papel")
    content: str = Field(validation_alias="conteudo")
    model: str | None = Field(default=None, validation_alias="modelo")
    status: str
    criada_em: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class ConversaDetalhe(ConversaPublic):
    mensagens: list[MensagemPublic]


class ChatMessageCreate(BaseModel):
    conversation_id: int | None = Field(default=None, ge=1)
    content: str = Field(min_length=1, max_length=4000)


class ReceiptItem(BaseModel):
    descricao: str | None = None
    quantidade: float | None = Field(default=None, ge=0)
    valor_unitario: float | None = Field(default=None, ge=0)
    valor_total: float | None = Field(default=None, ge=0)


class ReceiptConfidence(BaseModel):
    estabelecimento: float = Field(default=0, ge=0, le=1)
    data: float = Field(default=0, ge=0, le=1)
    hora: float = Field(default=0, ge=0, le=1)
    valor_total: float = Field(default=0, ge=0, le=1)
    forma_pagamento: float = Field(default=0, ge=0, le=1)
    itens: float = Field(default=0, ge=0, le=1)
    geral: float = Field(default=0, ge=0, le=1)


class ReceiptData(BaseModel):
    tipo_documento: str = "documento_desconhecido"
    estabelecimento: str | None = None
    cnpj: str | None = None
    endereco: str | None = None
    data: str | None = None
    hora: str | None = None
    valor_total: float | None = Field(default=None, ge=0)
    moeda: str = "BRL"
    forma_pagamento: str | None = None
    banco: str | None = None
    cartao: str | None = None
    ultimos_quatro_digitos: str | None = Field(default=None, max_length=4)
    parcelado: bool = False
    numero_parcela: int | None = Field(default=None, ge=1)
    total_parcelas: int | None = Field(default=None, ge=1)
    valor_parcela: float | None = Field(default=None, ge=0)
    itens: list[ReceiptItem] = Field(default_factory=list)
    codigo_transacao: str | None = None
    numero_documento: str | None = None
    observacoes: str | None = None
    confianca: ReceiptConfidence = Field(default_factory=ReceiptConfidence)


class ReceiptAnalysisPublic(BaseModel):
    id: int
    arquivo_id: int
    tipo_documento: str | None
    status: str
    dados_extraidos: ReceiptData | None = None
    confianca_geral: float | None
    erro_codigo: str | None
    erro_mensagem: str | None
    tentativas: int
    criado_em: datetime
    atualizado_em: datetime
    confirmado_em: datetime | None
    cancelado_em: datetime | None


class ReceiptConfirmRequest(BaseModel):
    dados: ReceiptData


class CategoriaAvancadaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    tipo: str = "despesa"
    cor: str | None = None
    icone: str | None = None
    categoria_pai_id: int | None = None
    ordem: int = 0
    limite_mensal_centavos: int | None = Field(default=None, ge=0)


class CategoriaAvancadaPublic(CategoriaAvancadaCreate):
    id: int
    ativa: bool
    arquivada_em: datetime | None
    model_config = {"from_attributes": True}


class OrcamentoCreate(BaseModel):
    categoria_id: int
    nome: str = Field(min_length=1, max_length=120)
    valor_limite_centavos: int = Field(gt=0)
    periodicidade: str = "mensal"
    data_inicio: str
    data_fim: str | None = None
    alerta_50: bool = True
    alerta_80: bool = True
    alerta_100: bool = True
    alerta_110: bool = True


class OrcamentoPublic(OrcamentoCreate):
    id: int
    ativo: bool
    data_inicio: datetime
    data_fim: datetime | None = None
    model_config = {"from_attributes": True}


class ParcelamentoCreate(BaseModel):
    descricao: str = Field(min_length=1, max_length=180)
    estabelecimento: str | None = None
    valor_total_centavos: int = Field(gt=0)
    total_parcelas: int = Field(gt=0)
    valor_parcela_centavos: int = Field(gt=0)
    data_compra: str
    categoria_id: int
    cartao_id: int | None = None
    observacoes: str | None = None


class ParcelaCreate(BaseModel):
    numero: int = Field(ge=1)
    valor_centavos: int = Field(gt=0)
    data_prevista: str | None = None


class AlertaCreate(BaseModel):
    tipo: str = "lembrete_personalizado"
    titulo: str = Field(min_length=1, max_length=180)
    mensagem: str = Field(min_length=1)
    data_agendada: str | None = None
    categoria_id: int | None = None
    orcamento_id: int | None = None
    parcela_id: int | None = None
    percentual_gatilho: int | None = Field(default=None, ge=1, le=1000)
    canal: str = "dentro_app"
    repeticao: str = "nenhuma"


class PushSubscribe(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)
    keys: dict = {}


class CategoriaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    tipo: str = "despesa"
    cor: str | None = None


class CategoriaPublic(CategoriaCreate):
    id: int
    ativa: bool
    icone: str | None = None
    categoria_pai_id: int | None = None
    ordem: int = 0
    arquivada_em: datetime | None = None
    limite_mensal_centavos: int | None = None
    model_config = {"from_attributes": True}


class ContaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    banco: str | None = None
    tipo: str = "conta_corrente"


class ContaPublic(ContaCreate):
    id: int
    ativo: bool
    model_config = {"from_attributes": True}


class CartaoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    banco: str | None = None
    ultimos_quatro_digitos: str | None = Field(default=None, max_length=4, min_length=0)
    limite_total_centavos: int | None = Field(default=None, ge=0)
    dia_fechamento: int | None = Field(default=None, ge=1, le=31)
    dia_vencimento: int | None = Field(default=None, ge=1, le=31)


class CartaoPublic(CartaoCreate):
    id: int
    ativo: bool
    model_config = {"from_attributes": True}


class LancamentoCreate(BaseModel):
    tipo: str = "despesa"
    descricao: str = Field(min_length=1, max_length=180)
    valor: Decimal
    data_compra: str
    hora_compra: str | None = None
    categoria_id: int
    conta_id: int | None = None
    cartao_id: int | None = None
    forma_pagamento: str | None = None
    estabelecimento: str | None = None
    cnpj: str | None = None
    local: str | None = None
    observacoes: str | None = None
    numero_parcela: int | None = Field(default=None, ge=1)
    total_parcelas: int | None = Field(default=None, ge=1)

    @field_validator("valor", mode="before")
    @classmethod
    def parse_money(cls, value):
        if isinstance(value, str): value = value.replace(".", "").replace(",", ".") if "," in value else value
        try: return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc: raise ValueError("Valor invalido") from exc


class LancamentoPublic(BaseModel):
    id: int
    tipo: str
    descricao: str
    valor_centavos: int
    moeda: str
    data_compra: datetime
    hora_compra: str | None
    categoria_id: int
    conta_id: int | None
    cartao_id: int | None
    forma_pagamento: str | None
    estabelecimento: str | None
    cnpj: str | None
    local: str | None
    observacoes: str | None
    origem: str
    analise_comprovante_id: int | None
    numero_parcela: int | None
    total_parcelas: int | None
    valor_parcela_centavos: int | None
    status: str
    model_config = {"from_attributes": True}
