from app.services.default_categories import DEFAULT_CATEGORIES


def test_default_catalog_has_expenses_and_income():
    names = {name for name, *_ in DEFAULT_CATEGORIES}
    types = {category_type for _, category_type, *_ in DEFAULT_CATEGORIES}
    assert {"Casa e moradia", "Alimentação", "Saude", "Salário"}.issubset(names)
    assert types == {"despesa", "receita"}
    assert len(DEFAULT_CATEGORIES) >= 40
    assert {"Mercado", "Saude", "Outros"}.issubset(names)
