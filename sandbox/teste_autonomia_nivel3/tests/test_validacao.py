import unittest
from pedido.validacao import validar_preco, validar_quantidade

class TestValidacao(unittest.TestCase):
    
    def test_validar_preco_com_valor_positivo(self):
        self.assertTrue(validar_preco(10.0))
        
    def test_validar_preco_com_valor_zero(self):
        self.assertTrue(validar_preco(0))
        
    def test_validar_preco_com_valor_negativo(self):
        self.assertFalse(validar_preco(-5.0))
        
    def test_validar_quantidade_com_valor_positivo(self):
        self.assertTrue(validar_quantidade(5))
        
    def test_validar_quantidade_com_valor_zero(self):
        self.assertFalse(validar_quantidade(0))
        
    def test_validar_quantidade_com_valor_negativo(self):
        self.assertFalse(validar_quantidade(-2))

if __name__ == '__main__':
    unittest.main()