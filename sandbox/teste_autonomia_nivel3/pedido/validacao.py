def validar_preco(preco):
    if preco < 0:
        return False
    return True

def validar_quantidade(quantidade):
    if quantidade <= 0:
        return False
    return True
