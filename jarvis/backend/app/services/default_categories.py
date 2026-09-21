from __future__ import annotations

import unicodedata

from sqlalchemy.orm import Session

from ..models import Categoria


DEFAULT_CATEGORIES = [
    ("Alimentação", "despesa", "#ef4444", "utensils"),
    ("Supermercado", "despesa", "#f97316", "shopping-cart"),
    ("Mercado", "despesa", "#ea580c", "shopping-basket"),
    ("Casa e moradia", "despesa", "#0ea5e9", "house"),
    ("Água", "despesa", "#06b6d4", "droplets"),
    ("Energia elétrica", "despesa", "#eab308", "zap"),
    ("Gás", "despesa", "#f59e0b", "flame"),
    ("Internet e telefone", "despesa", "#6366f1", "wifi"),
    ("Condomínio", "despesa", "#64748b", "building"),
    ("Manutenção da casa", "despesa", "#78716c", "wrench"),
    ("Transporte", "despesa", "#3b82f6", "bus"),
    ("Combustível", "despesa", "#2563eb", "fuel"),
    ("Veículo", "despesa", "#1d4ed8", "car"),
    ("Aplicativos de transporte", "despesa", "#60a5fa", "map-pin"),
    ("Saude", "despesa", "#10b981", "heart-pulse"),
    ("Farmácia", "despesa", "#14b8a6", "pill"),
    ("Plano de saúde", "despesa", "#059669", "shield-plus"),
    ("Educação", "despesa", "#8b5cf6", "graduation-cap"),
    ("Cursos e livros", "despesa", "#7c3aed", "book-open"),
    ("Lazer", "despesa", "#ec4899", "party-popper"),
    ("Restaurantes", "despesa", "#f43f5e", "chef-hat"),
    ("Viagens", "despesa", "#0d9488", "plane"),
    ("Assinaturas e streaming", "despesa", "#a855f7", "play"),
    ("Compras pessoais", "despesa", "#d946ef", "shopping-bag"),
    ("Roupas e calçados", "despesa", "#c026d3", "shirt"),
    ("Cuidados pessoais", "despesa", "#db2777", "sparkles"),
    ("Filhos e família", "despesa", "#f97316", "users"),
    ("Animais de estimação", "despesa", "#84cc16", "paw-print"),
    ("Impostos e taxas", "despesa", "#dc2626", "landmark"),
    ("Seguros", "despesa", "#475569", "shield"),
    ("Dívidas e empréstimos", "despesa", "#b91c1c", "credit-card"),
    ("Obra e construção", "despesa", "#d97706", "hard-hat"),
    ("Material de construção", "despesa", "#b45309", "brick-wall"),
    ("Mão de obra", "despesa", "#92400e", "hammer"),
    ("Empresa e trabalho", "despesa", "#334155", "briefcase-business"),
    ("Trading e investimentos", "despesa", "#16a34a", "chart-candlestick"),
    ("Presentes e doações", "despesa", "#e11d48", "gift"),
    ("Outras despesas", "despesa", "#6b7280", "circle-ellipsis"),
    ("Outros", "despesa", "#6b7280", "circle-ellipsis"),
    ("Salário", "receita", "#16a34a", "wallet-cards"),
    ("Pró-labore", "receita", "#15803d", "briefcase"),
    ("Renda de serviços", "receita", "#059669", "hand-coins"),
    ("Vendas", "receita", "#0d9488", "badge-dollar-sign"),
    ("Aluguéis recebidos", "receita", "#0891b2", "key-round"),
    ("Rendimentos e dividendos", "receita", "#22c55e", "trending-up"),
    ("Reembolsos", "receita", "#65a30d", "receipt-text"),
    ("Outras receitas", "receita", "#4d7c0f", "circle-plus"),
]


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold().strip()


def ensure_default_categories(db: Session, user_id: int) -> list[Categoria]:
    existing = db.query(Categoria).filter(Categoria.usuario_id == user_id).all()
    keys = {_key(item.nome) for item in existing}
    next_order = max((item.ordem for item in existing), default=0) + 1
    created = []
    for name, category_type, color, icon in DEFAULT_CATEGORIES:
        if _key(name) in keys:
            continue
        item = Categoria(
            usuario_id=user_id,
            nome=name,
            tipo=category_type,
            cor=color,
            icone=icon,
            ordem=next_order,
            ativa=True,
        )
        db.add(item)
        created.append(item)
        keys.add(_key(name))
        next_order += 1
    if created:
        db.commit()
    return existing + created
