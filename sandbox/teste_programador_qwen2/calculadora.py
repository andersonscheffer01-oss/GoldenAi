#!/usr/bin/env python3
"""
Calculadora Básica em Python
Contém funções para as operações básicas de adição, subtração, multiplicação e divisão.
"""

def adicao(x, y):
    """Retorna a soma de x e y."""
    return x + y

def subtracao(x, y):
    """Retorna a diferença entre x e y."""
    return x - y

def multiplicacao(x, y):
    """Retorna o produto de x e y."""
    return x * y

def divisao(x, y):
    """Retorna o quociente de x dividido por y."""
    if y == 0:
        raise ValueError("Não é possível dividir por zero!")
    return x / y

def main():
    """Função principal para demonstrar as operações da calculadora."""
    print("Calculadora Básica")
    print("-" * 20)
    
    # Exemplos de uso
    a = 10
    b = 5
    
    print(f"Adição: {a} + {b} = {adicao(a, b)}")
    print(f"Subtração: {a} - {b} = {subtracao(a, b)}")
    print(f"Multiplicação: {a} * {b} = {multiplicacao(a, b)}")
    print(f"Divisão: {a} / {b} = {divisao(a, b)}")

if __name__ == "__main__":
    main()