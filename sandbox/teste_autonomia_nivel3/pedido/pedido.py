from pedido.produto import Produto

class Pedido:
    def __init__(self):
        self.produtos = []
        self.desconto_percentual = 0
        self.taxa_percentual = 0
    
    def adicionar_produto(self, produto):
        self.produtos.append(produto)
    
    def calcular_subtotal(self):
        total = 0
        for produto in self.produtos:
            total += produto.subtotal()
        return total
    
    def aplicar_desconto(self):
        subtotal = self.calcular_subtotal()
        desconto = subtotal * (self.desconto_percentual / 100)
        return subtotal - desconto
    
    def adicionar_taxa(self):
        total_com_desconto = self.aplicar_desconto()
        taxa = total_com_desconto * (self.taxa_percentual / 100)
        return total_com_desconto + taxa
    
    def calcular_total(self):
        return self.adicionar_taxa()
