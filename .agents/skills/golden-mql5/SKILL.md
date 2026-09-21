---
name: golden-mql5
description: Regras para trabalhar com MQL5 no projeto Golden AI. Usar ao modificar robôs, indicadores ou estratégias.
---

# Golden MQL5

## Estrutura

```
projetos/
├── EA_*.mq5                    ← Expert Advisors
├── Indicator_*.mq5             ← Indicadores
├── Script_*.mq5                ← Scripts
└── Include/                    ← Bibliotecas compartilhadas
```

## Regras Fundamentais

### NUNCA alterar lógica de entrada sem confirmação

Se a solicitação for APENAS gerenciamento (stop, take, trailing, etc.), NÃO toque na lógica de entrada.

### Separar claramente

```
ENTRADA         ← Quando e como entrar
GERENCIAMENTO   ← O que fazer depois de entrar
RISCO           ← Quanto arriscar
STOP            ← Onde sair com perda
TAKE            ← Onde sair com lucro
BREAKEVEN       ← Mover stop para entrada
TRAILING        ← Acompanhar preço
LIMITES         ← Máximo de operações/dia
```

### Risco Percentual

Ao calcular lote com risco percentual:
- Usar balance OU equity conforme regra da estratégia
- Verificar stop em pontos (não pips)
- Verificar tick_size e tick_value
- Verificar contract_size quando necessário
- Respeitar volume_min, volume_max, volume_step
- Normalizar lote conforme symbol_info

### Compilação

Sempre compilar após alteração:
```
metaeditor64.exe /compile:"arquivo.mq5" /include:"Include"
```

### Validação

Não considere código pronto porque compila sem erros ou parece correto.
SEMPRE teste no Strategy Tester antes de considerar pronto.
