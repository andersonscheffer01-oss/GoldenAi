"""Closed registry of operations callable by Jarvis commands."""

ALLOWED_TOOLS = frozenset({
    "consultar_resumo_financeiro", "consultar_lancamentos", "consultar_gastos_por_categoria",
    "consultar_maior_gasto", "consultar_progresso_orcamento", "consultar_parcelamentos",
    "consultar_alertas", "criar_lancamento_pendente", "criar_orcamento_pendente",
    "criar_lembrete_pendente", "editar_lancamento_pendente", "excluir_lancamento_pendente",
    "confirmar_acao", "cancelar_acao",
})


def is_allowed(name: str) -> bool:
    return name in ALLOWED_TOOLS
