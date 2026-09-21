"""
Golden AI - Módulos extraídos do golden_ai.py

Estrutura:
  - context.py    : Estado compartilhado (globals)
  - utils.py      : Funções utilitárias (normalização, idioma, hashing)
  - mt5.py        : Operações MT5 (somente leitura)
  - files.py      : Operações de arquivo (listar, ler, metadados, backup)
  - intent.py     : Classificação de intenção do usuário
  - internet.py   : Chat de internet e busca web
  - browser.py    : Wrappers para Browser/Documentos/Audio/Video/Vision
  - panel.py      : Painel de comandos do Golden
"""

__all__ = [
    "context",
    "utils",
    "mt5",
    "files",
    "intent",
    "internet",
    "browser",
    "panel",
]
