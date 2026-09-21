---
name: golden-trading
description: Regras para trading e estratégias no projeto Golden AI. Usar ao modificar Scanner, Risk Engine, Validation, ou estratégias.
---

# Golden Trading

## Componentes de Trading

### Scanner (golden_scanner.py)
- 47 setups com IDs únicos
- SCALP (22), DAY TRADE (15), SWING (10)
- Scoring com confluência multi-timeframe
- Normalização por ATR

### Risk Engine (risk_engine.py)
- Position sizing automático
- Daily max loss
- Consecutive loss limit
- Cooldown entre operações
- Correlation exposure
- News filter

### Validation Engine (validation_engine.py)
- Backtest simulation
- Monte Carlo (1000+ simulações)
- Robustness test
- Walk-Forward
- Mode comparison (SCALP vs DAY vs SWING)

### Trade Journal (trade_journal.py)
- Registro de todas as operações
- Histórico de sinais
- Performance por estratégia

## Regras

### NUNCA alterar risk engine sem confirmação
- Position sizing é crítico
- Daily loss limits protegem a conta
- Correlation evita exposição excessiva

### NUNCA remover proteções
- Stop loss
- Take profit
- Breakeven
- Trailing stop
- Daily limits

### Ao modificar estratégia
1. Verificar se a lógica de entrada continua correta
2. Verificar se o risk management não foi afetado
3. Rodar validação antes de considerar pronto
4. Atualizar `docs/agent-context/CURRENT_WORK.md`
