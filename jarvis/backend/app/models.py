from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nome: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    sessoes: Mapped[list["Sessao"]] = relationship(back_populates="usuario")


class Sessao(Base):
    __tablename__ = "sessoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    token_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    usuario: Mapped[Usuario] = relationship(back_populates="sessoes")


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    acao: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    modulo: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sucesso: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Arquivo(Base):
    __tablename__ = "arquivos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    nome_original: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_interno: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    caminho_seguro: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="recebido", nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class Conversa(Base):
    __tablename__ = "conversas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(80), default="Nova conversa", nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    mensagens: Mapped[list["Mensagem"]] = relationship(
        back_populates="conversa", cascade="all, delete-orphan", order_by="Mensagem.id"
    )


class Mensagem(Base):
    __tablename__ = "mensagens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversa_id: Mapped[int] = mapped_column(ForeignKey("conversas.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    papel: Mapped[str] = mapped_column(String(20), nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    modelo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tokens_estimados: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tempo_resposta_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="enviada", nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    conversa: Mapped[Conversa] = relationship(back_populates="mensagens")


class AnaliseComprovante(Base):
    __tablename__ = "analises_comprovantes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    arquivo_id: Mapped[int] = mapped_column(ForeignKey("arquivos.id"), nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="aguardando", nullable=False)
    resposta_bruta: Mapped[str | None] = mapped_column(Text, nullable=True)
    dados_extraidos_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confianca_geral: Mapped[float | None] = mapped_column(nullable=True)
    erro_codigo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    erro_mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)
    tentativas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Categoria(Base):
    __tablename__ = "categorias"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    cor: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    categoria_pai_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), nullable=True, index=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    arquivada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    limite_mensal_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ContaFinanceira(Base):
    __tablename__ = "contas_financeiras"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    banco: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Cartao(Base):
    __tablename__ = "cartoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    banco: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    ultimos_quatro_digitos: Mapped[str | None] = mapped_column(String(4), nullable=True)
    limite_total_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dia_fechamento: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dia_vencimento: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class LancamentoFinanceiro(Base):
    __tablename__ = "lancamentos_financeiros"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    descricao: Mapped[str] = mapped_column(String(180), nullable=False)
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    data_compra: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    hora_compra: Mapped[str | None] = mapped_column(String(8), nullable=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False, index=True)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("contas_financeiras.id"), nullable=True, index=True)
    cartao_id: Mapped[int | None] = mapped_column(ForeignKey("cartoes.id"), nullable=True, index=True)
    forma_pagamento: Mapped[str | None] = mapped_column(String(30), nullable=True)
    estabelecimento: Mapped[str | None] = mapped_column(String(180), nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(30), nullable=True)
    local: Mapped[str | None] = mapped_column(String(180), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    origem: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)
    analise_comprovante_id: Mapped[int | None] = mapped_column(ForeignKey("analises_comprovantes.id"), nullable=True, unique=True, index=True)
    numero_parcela: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_parcelas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valor_parcela_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ativo", nullable=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Orcamento(Base):
    __tablename__ = "orcamentos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    valor_limite_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    periodicidade: Mapped[str] = mapped_column(String(20), default="mensal", nullable=False)
    data_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alerta_50: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alerta_80: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alerta_100: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alerta_110: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Parcelamento(Base):
    __tablename__ = "parcelamentos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(String(180), nullable=False)
    estabelecimento: Mapped[str | None] = mapped_column(String(180), nullable=True)
    valor_total_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    total_parcelas: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_parcela_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    data_compra: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cartao_id: Mapped[int | None] = mapped_column(ForeignKey("cartoes.id"), nullable=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Parcela(Base):
    __tablename__ = "parcelas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    parcelamento_id: Mapped[int] = mapped_column(ForeignKey("parcelamentos.id"), nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    data_prevista: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="sem_data", nullable=False)
    lancamento_id: Mapped[int | None] = mapped_column(ForeignKey("lancamentos_financeiros.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class AlertaFinanceiro(Base):
    __tablename__ = "alertas_financeiros"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    titulo: Mapped[str] = mapped_column(String(180), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), nullable=True)
    orcamento_id: Mapped[int | None] = mapped_column(ForeignKey("orcamentos.id"), nullable=True)
    cartao_id: Mapped[int | None] = mapped_column(ForeignKey("cartoes.id"), nullable=True)
    parcela_id: Mapped[int | None] = mapped_column(ForeignKey("parcelas.id"), nullable=True)
    data_agendada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    percentual_gatilho: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canal: Mapped[str] = mapped_column(String(20), default="dentro_app", nullable=False)
    repeticao: Mapped[str] = mapped_column(String(20), default="nenhuma", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ativo", nullable=False)
    ultima_execucao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    subscription_json: Mapped[str] = mapped_column(Text, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class NotificacaoPreferencia(Base):
    __tablename__ = "notificacao_preferencias"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), unique=True, nullable=False)
    alertas_financeiros: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alertas_orcamento: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alertas_parcelas: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    resumo_diario: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resumo_semanal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    horario: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
    push_ativado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AcaoPendente(Base):
    __tablename__ = "acoes_pendentes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    resumo: Mapped[str] = mapped_column(Text, nullable=False)
    hash_acao: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="aguardando_confirmacao", nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DispositivoPC(Base):
    __tablename__ = "dispositivos_pc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    identificador: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    sistema_operacional: Mapped[str | None] = mapped_column(String(80), nullable=True)
    versao_agente: Mapped[str] = mapped_column(String(40), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="aguardando", nullable=False, index=True)
    ultimo_ping: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_rede: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ComandoPC(Base):
    __tablename__ = "comandos_pc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dispositivo_id: Mapped[int] = mapped_column(ForeignKey("dispositivos_pc.id"), nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="aguardando_confirmacao", nullable=False, index=True)
    resultado_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    erro_codigo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    erro_mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)
    solicitado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PareamentoPC(Base):
    __tablename__ = "pareamento_pc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    codigo_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class OpenFinanceConnection(Base):
    __tablename__ = "open_finance_connections"
    __table_args__ = (UniqueConstraint("usuario_id", "external_link_id", name="uq_of_connection_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(30), default="pluggy", nullable=False)
    environment: Mapped[str] = mapped_column(String(20), default="personal", nullable=False)
    external_link_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    external_consent_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    institution_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    institution_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="connected", nullable=False, index=True)
    consent_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    consent_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class OpenFinanceAccount(Base):
    __tablename__ = "open_finance_accounts"
    __table_args__ = (UniqueConstraint("usuario_id", "connection_id", "external_id", name="uq_of_account_item_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("open_finance_connections.id"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    subtype: Mapped[str | None] = mapped_column(String(60), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    current_balance_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    available_balance_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credit_limit_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class OpenFinanceBill(Base):
    __tablename__ = "open_finance_bills"
    __table_args__ = (UniqueConstraint("usuario_id", "connection_id", "external_id", name="uq_of_bill_item_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("open_finance_connections.id"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(80), nullable=False)
    account_external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class OpenFinanceTransaction(Base):
    __tablename__ = "open_finance_transactions"
    __table_args__ = (UniqueConstraint("usuario_id", "connection_id", "external_id", name="uq_of_transaction_item_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("open_finance_connections.id"), nullable=False, index=True)
    account_external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_id: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    flow_type: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    import_status: Mapped[str] = mapped_column(String(30), default="available", nullable=False, index=True)
    imported_entry_id: Mapped[int | None] = mapped_column(ForeignKey("lancamentos_financeiros.id"), nullable=True, unique=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class OpenFinanceSync(Base):
    __tablename__ = "open_finance_syncs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("open_finance_connections.id"), nullable=True, index=True)
    event_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    resource: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class OpenFinanceImport(Base):
    __tablename__ = "open_finance_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    transaction_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    expense_category_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), nullable=True)
    income_category_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_confirmation", nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
