import unittest
from calculadora.validacao import eh_numero, validar_divisor

class TestValidacao(unittest.TestCase):
    
    def test_eh_numero(self):
        self.assertTrue(eh_numero(5))
        self.assertTrue(eh_numero(3.14))
        self.assertFalse(eh_numero("5"))
        
    def test_validar_divisor_com_numero_valido(self):
        self.assertTrue(validar_divisor(5))
        
    def test_validar_divisor_com_zero(self):
        self.assertFalse(validar_divisor(0))  # Deve falhar com o bug

if __name__ == '__main__':
    unittest.main()