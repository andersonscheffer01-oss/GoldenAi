import unittest
from calculadora.operacoes import soma, subtracao, multiplicacao, divisao

class TestOperacoes(unittest.TestCase):
    
    def test_soma(self):
        self.assertEqual(soma(2, 3), 5)
        
    def test_subtracao(self):
        self.assertEqual(subtracao(5, 3), 2)
        
    def test_multiplicacao(self):
        self.assertEqual(multiplicacao(2, 3), 6)
        
    def test_divisao(self):
        self.assertEqual(divisao(6, 2), 3)
        with self.assertRaises(ValueError):
            divisao(5, 0)

if __name__ == '__main__':
    unittest.main()