import unittest
from pedido.pedido import Pedido
from pedido.produto import Produto

class TestPedido(unittest.TestCase):
    
    def test_calcular_subtotal(self):
        pedido = Pedido()
        produto1 = Produto("Produto A", 10.0, 2)
        produto2 = Produto("Produto B", 15.0, 1)
        
        pedido.adicionar_produto(produto1)
        pedido.adicionar_produto(produto2)
        
        self.assertEqual(pedido.calcular_subtotal(), 35.0)
    
    def test_aplicar_desconto(self):
        pedido = Pedido()
        pedido.desconto_percentual = 10
        
        produto1 = Produto("Produto A", 10.0, 2)
        pedido.adicionar_produto(produto1)
        
        # Com desconto de 10% sobre subtotal 20
        self.assertEqual(pedido.aplicar_desconto(), 18.0)  # Bug: retorna 20 em vez de 18
    
    def test_adicionar_taxa(self):
        pedido = Pedido()
        pedido.taxa_percentual = 5
        
        produto1 = Produto("Produto A", 10.0, 2)
        pedido.adicionar_produto(produto1)
        
        # Com taxa de 5% sobre subtotal 20
        self.assertEqual(pedido.adicionar_taxa(), 21.0)  # Bug: retorna 20 em vez de 21
    
    def test_calcular_total(self):
        pedido = Pedido()
        produto1 = Produto("Produto A", 10.0, 2)
        pedido.adicionar_produto(produto1)
        pedido.desconto_percentual = 10
        pedido.taxa_percentual = 5
        
        # Cálculo correto: subtotal=20, desconto=2, total_com_desconto=18, taxa=0.9, total_final=18.9
        self.assertEqual(pedido.calcular_total(), 18.9)  # Bug: retornaria 20 em vez de 18.9

if __name__ == '__main__':
    unittest.main()