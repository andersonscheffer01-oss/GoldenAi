from pedido.pedido import Pedido
from pedido.produto import Produto

def main():
    # Criar um pedido de exemplo
    pedido = Pedido()
    
    # Adicionar produtos
    produto1 = Produto("Produto A", 10.0, 2)
    produto2 = Produto("Produto B", 15.0, 1)
    
    pedido.adicionar_produto(produto1)
    pedido.adicionar_produto(produto2)
    
    # Definir desconto e taxa
    pedido.desconto_percentual = 10
    pedido.taxa_percentual = 5
    
    # Calcular valores
    subtotal = pedido.calcular_subtotal()
    total_com_desconto = pedido.aplicar_desconto()
    total_com_taxa = pedido.adicionar_taxa()
    total_final = pedido.calcular_total()
    
    print("=== Resumo do Pedido ===")
    print(f"Subtotal: R$ {subtotal:.2f}")
    print(f"Desconto (10%): R$ {subtotal - total_com_desconto:.2f}")
    print(f"Total com desconto: R$ {total_com_desconto:.2f}")
    print(f"Taxa (5%): R$ {total_com_desconto * 0.05:.2f}")
    print(f"Total final: R$ {total_final:.2f}")

if __name__ == "__main__":
    main()