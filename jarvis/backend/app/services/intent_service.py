from __future__ import annotations

import re
from datetime import date
from decimal import Decimal


def money(text: str) -> int | None:
    values = re.findall(r"R\$\s*([\d.]+(?:,[\d]{1,2})?)", text, re.I)
    if len(values) != 1: return None
    raw = values[0].replace('.', '').replace(',', '.')
    value = Decimal(raw)
    return int(value * 100) if value > 0 else None


def _number_after(text: str, *words: str) -> int | None:
    labels = "|".join(map(re.escape, words))
    pattern = rf"(?:{labels})\s*(?:de\s*)?(\d+)|\b(\d+)\s+(?:{labels})\b"
    match = re.search(pattern, text, re.I)
    return int(match.group(1) or match.group(2)) if match else None


def detect(text: str) -> dict:
    normalized = ' '.join(text.lower().split())
    amount = money(text)
    if normalized in {'confirmar', 'sim', 'executar', 'pode registrar', 'confirmar lançamento', 'confirmar lancamento'}:
        intent = 'confirmar_acao'
    elif normalized in {'cancelar', 'não', 'nao', 'não registrar', 'nao registrar'}:
        intent = 'cancelar_acao'
    elif any(word in normalized for word in ('computador', 'pc', 'memoria', 'memória', 'cpu', 'disco', 'ollama', 'golden', 'jarvis', 'mt5', 'metatrader')):
        if any(word in normalized for word in ('abra', 'abrir', 'ligue', 'inicie', 'iniciar')):
            intent = 'pc_abrir_aplicativo'
        elif 'ollama' in normalized:
            intent = 'pc_verificar_ollama'
        elif 'mt5' in normalized or 'metatrader' in normalized:
            intent = 'pc_verificar_mt5'
        elif 'golden' in normalized or 'jarvis' in normalized:
            intent = 'pc_verificar_jarvis'
        else:
            intent = 'pc_status'
    elif any(word in normalized for word in ('quanto gastei', 'resumo', 'maior despesa', 'maior gasto', 'quais foram meus gastos')):
        intent = 'consultar_maior_gasto' if 'maior' in normalized else 'consultar_gastos_categoria' if ' com ' in normalized else 'consultar_gastos_periodo'
    elif 'parcel' in normalized:
        if any(word in normalized for word in ('marque', 'marcar', 'paga', 'paguei')):
            intent = 'marcar_parcela_paga'
        elif amount and any(word in normalized for word in ('crie', 'criar', 'compra', 'parcel')):
            intent = 'criar_parcelamento'
        else:
            intent = 'consultar_parcelas'
    elif 'alerta' in normalized or 'lembre' in normalized:
        intent = 'consultar_lembretes' if any(word in normalized for word in ('tenho', 'quais', 'mostre', 'listar', 'consultar')) else 'criar_lembrete'
    elif 'orçamento' in normalized or 'orcamento' in normalized:
        intent = 'criar_orcamento' if amount else 'consultar_orcamento'
    elif 'corrija' in normalized or 'altere' in normalized or 'editar' in normalized:
        intent = 'editar_lancamento'
    elif 'exclua' in normalized or 'apague' in normalized:
        intent = 'excluir_lancamento'
    elif any(word in normalized for word in ('gastei', 'registre', 'paguei', 'comprei', 'lance uma despesa', 'recebi')): intent = 'criar_lancamento'
    elif normalized in {'ajuda', 'help'}: intent = 'ajuda'
    else: intent = 'desconhecida'
    parameters = {
        'valor_centavos': amount,
        'data_compra': date.today().isoformat(),
        'data_inicio': date.today().isoformat(),
        'descricao': text.strip(),
        'texto_normalizado': normalized,
        'lancamento_id': _number_after(normalized, 'lançamento', 'lancamento', 'id') or None,
        'parcela_numero': _number_after(normalized, 'parcela') or None,
        'total_parcelas': _number_after(normalized, 'parcelas') or None,
        'novo_valor_centavos': amount,
        'programa': 'golden_jarvis' if 'golden' in normalized or 'jarvis' in normalized else 'metatrader' if 'mt5' in normalized or 'metatrader' in normalized else 'navegador' if 'navegador' in normalized or 'chrome' in normalized else None,
    }
    return {'intent': intent, 'confidence': .9 if intent != 'desconhecida' else .2, 'parameters': parameters}
