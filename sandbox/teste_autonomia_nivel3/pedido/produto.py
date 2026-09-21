class Produto:
    def __init__(self, nome, preco_unitario, quantidade):
        self.nome = nome
        self.preco_unitario = preco_unitario
        self.quantidade = quantidade
    
    def subtotal(self):
        return self.preco_unitario * self.quantidade
