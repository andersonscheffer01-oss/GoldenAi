from calculadora.operacoes import soma, subtracao, multiplicacao, divisao
from calculadora.validacao import eh_numero, validar_divisor

print("Exemplos de operações:")
print(f"Soma: 5 + 3 = {soma(5, 3)}")
print(f"Subtração: 5 - 3 = {subtracao(5, 3)}")
print(f"Multiplicação: 5 * 3 = {multiplicacao(5, 3)}")
print(f"Divisão: 6 / 2 = {divisao(6, 2)}")

print("\nExemplos de validações:")
print(f"5 é número: {eh_numero(5)}")
print(f"Validar divisor 0: {validar_divisor(0)}")