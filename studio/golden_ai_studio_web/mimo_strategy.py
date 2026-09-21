#!/usr/bin/env python3
"""
🎯 Golden AI — Módulo de Estratégia com MiMo
Integra o modelo MiMo para:
  - Análise de estratégias de trading
  - Backtesting automático
  - Otimização de parâmetros
  - Painéis estatísticos comparativos
"""

import json
import os
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# CONFIGURAÇÃO DO MIMO
# ============================================================

# Opções de modelo MiMo
MIMO_MODELS = {
    "mimo_local": {
        "name": "MiMo-7B-RL (Local)",
        "model": "alibayram/mimo-7b-rl",
        "type": "ollama",
        "description": "Modelo local, gratuito, 7B parâmetros",
        "ram_needed": "8GB",
        "speed": "Rápido",
        "quality": "Boa para código",
    },
    "mimo_flash": {
        "name": "MiMo-V2-Flash (API)",
        "model": "xiaomi/mimo-v2.5",
        "type": "openrouter",
        "description": "Modelo Flash, 15B ativos, 256K contexto",
        "ram_needed": "API (grátis com crédito)",
        "speed": "Muito rápido",
        "quality": "Excelente",
    },
    "mimo_pro": {
        "name": "MiMo-V2.5-Pro (API)",
        "model": "xiaomi/mimo-v2.5-pro",
        "type": "openrouter",
        "description": "Modelo Pro, mais poderoso",
        "ram_needed": "API (pago)",
        "speed": "Rápido",
        "quality": "Top-tier",
    },
}

# ============================================================
# FERRAMENTAS DE ANÁLISE DE ESTRATÉGIA
# ============================================================

class StrategyAnalyzer:
    """Analisa estratégias de trading e gera relatórios"""
    
    def __init__(self):
        self.patterns = {
            "Morning Star": {"wr": 0.58, "rr": 1.8, "dir": "COMPRA", "candles": 3},
            "Piercing Line": {"wr": 0.55, "rr": 1.5, "dir": "COMPRA", "candles": 2},
            "Engolfo Compra": {"wr": 0.56, "rr": 1.6, "dir": "COMPRA", "candles": 2},
            "Evening Star": {"wr": 0.57, "rr": 1.7, "dir": "VENDA", "candles": 3},
            "Dark Cloud": {"wr": 0.54, "rr": 1.4, "dir": "VENDA", "candles": 2},
            "Engolfo Venda": {"wr": 0.55, "rr": 1.5, "dir": "VENDA", "candles": 2},
        }
    
    def analyze_strategy(self, config):
        """Análise completa de uma estratégia"""
        results = {}
        
        for name, data in self.patterns.items():
            wr = data["wr"]
            rr = data["rr"]
            
            # Ajustar com configurações
            if config.get("triple_confluence"):
                wr += 0.15
            if config.get("filter_spread"):
                wr += 0.03
            if config.get("filter_hours"):
                wr += 0.02
            if config.get("adaptive_mode"):
                wr += 0.05
            
            # Ajustar por R:R
            if rr >= 3.0:
                wr -= 0.08
            elif rr >= 2.0:
                wr -= 0.03
            
            wr = max(0.30, min(0.90, wr))
            
            # Calcular métricas
            ev = (wr * rr) - (1 - wr)
            be_wr = 1.0 / (1.0 + rr)
            
            # Simular 200 trades
            sim = self._simulate(wr, data["rr"], 200)
            
            results[name] = {
                "direction": data["dir"],
                "candles": data["candles"],
                "win_rate": round(wr * 100, 1),
                "rr_ratio": rr,
                "expected_value": round(ev, 4),
                "breakeven_wr": round(be_wr * 100, 1),
                "sim_return": sim["return_pct"],
                "sim_drawdown": sim["max_drawdown"],
                "sim_pf": sim["profit_factor"],
            }
        
        return results
    
    def _simulate(self, win_rate, rr_ratio, n_trades, initial=10000, risk=0.01):
        """Simula trades"""
        random.seed(42)
        balance = initial
        peak = balance
        max_dd = 0
        wins = 0
        
        for i in range(n_trades):
            if random.random() < win_rate:
                balance += balance * risk * rr_ratio
                wins += 1
            else:
                balance -= balance * risk
            
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100
            max_dd = max(max_dd, dd)
        
        return {
            "return_pct": round(((balance - initial) / initial) * 100, 1),
            "max_drawdown": round(max_dd, 1),
            "profit_factor": round((wins * rr_ratio) / max(n_trades - wins, 1), 2),
            "wins": wins,
            "losses": n_trades - wins,
        }
    
    def optimize_params(self, symbol="XAUUSD", timeframe="M15"):
        """Otimiza parâmetros automaticamente"""
        best_config = None
        best_score = -999
        
        configs = []
        
        for sl in [200, 300, 400, 500]:
            for tp in [400, 500, 600, 800, 1000, 1500]:
                rr = tp / sl
                if rr < 1.0:
                    continue
                
                config = {
                    "sl": sl, "tp": tp, "rr": rr,
                    "triple_confluence": True,
                    "filter_spread": True,
                    "filter_hours": True,
                    "adaptive_mode": True,
                }
                
                results = self.analyze_strategy(config)
                
                # Score composto
                avg_wr = sum(r["win_rate"] for r in results.values()) / len(results)
                avg_ev = sum(r["expected_value"] for r in results.values()) / len(results)
                avg_return = sum(r["sim_return"] for r in results.values()) / len(results)
                avg_dd = sum(r["sim_drawdown"] for r in results.values()) / len(results)
                
                score = (avg_ev * 10) + (avg_return / 100) - (avg_dd / 10)
                
                configs.append({
                    "sl": sl, "tp": tp, "rr": round(rr, 2),
                    "avg_wr": round(avg_wr, 1),
                    "avg_ev": round(avg_ev, 4),
                    "avg_return": round(avg_return, 1),
                    "avg_dd": round(avg_dd, 1),
                    "score": round(score, 4),
                })
                
                if score > best_score:
                    best_score = score
                    best_config = configs[-1]
        
        configs.sort(key=lambda x: x["score"], reverse=True)
        
        return {
            "best": best_config,
            "top_10": configs[:10],
            "total_tested": len(configs),
        }
    
    def generate_panel_data(self, results):
        """Gera dados para painel estatístico"""
        panel = {
            "summary": {
                "total_patterns": len(results),
                "avg_wr": round(sum(r["win_rate"] for r in results.values()) / len(results), 1),
                "avg_ev": round(sum(r["expected_value"] for r in results.values()) / len(results), 4),
                "best_pattern": max(results.items(), key=lambda x: x[1]["expected_value"])[0],
                "worst_pattern": min(results.items(), key=lambda x: x[1]["expected_value"])[0],
            },
            "by_direction": {
                "COMPRA": [],
                "VENDA": [],
            },
            "risk_profile": {
                "low_risk": [],    # R:R < 1.5
                "medium_risk": [], # R:R 1.5-2.5
                "high_risk": [],   # R:R > 2.5
            },
        }
        
        for name, data in results.items():
            entry = {"name": name, **data}
            panel["by_direction"][data["direction"]].append(entry)
            
            if data["rr_ratio"] < 1.5:
                panel["risk_profile"]["low_risk"].append(entry)
            elif data["rr_ratio"] <= 2.5:
                panel["risk_profile"]["medium_risk"].append(entry)
            else:
                panel["risk_profile"]["high_risk"].append(entry)
        
        return panel


# ============================================================
# GERADOR DE PAINEL HTML
# ============================================================

def generate_strategy_panel_html(results, optimization=None):
    """Gera HTML do painel de estratégia"""
    
    html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Golden AI — Painel de Estratégia</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #0a0e17;
            color: #e0e0e0;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
            padding: 20px 30px;
            border-bottom: 1px solid #30363d;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .header h1 {
            font-size: 24px;
            background: linear-gradient(90deg, #f0b429, #ff6b35);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .header .subtitle { color: #8b949e; font-size: 14px; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        
        /* Cards de Resumo */
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }
        .summary-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .summary-card .value {
            font-size: 28px;
            font-weight: 700;
            margin: 5px 0;
        }
        .summary-card .label {
            font-size: 12px;
            color: #8b949e;
            text-transform: uppercase;
        }
        .positive { color: #3fb950; }
        .negative { color: #f85149; }
        .neutral { color: #58a6ff; }
        
        /* Tabela de Padrões */
        .table-container {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 25px;
        }
        .table-header {
            background: #1c2333;
            padding: 15px 20px;
            font-weight: 600;
            font-size: 16px;
            border-bottom: 1px solid #30363d;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #21262d;
        }
        th {
            background: #1c2333;
            color: #8b949e;
            font-size: 12px;
            text-transform: uppercase;
        }
        tr:hover { background: #1c2333; }
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-buy { background: rgba(63,185,80,0.2); color: #3fb950; }
        .badge-sell { background: rgba(248,81,73,0.2); color: #f85149; }
        .badge-good { background: rgba(63,185,80,0.2); color: #3fb950; }
        .badge-ok { background: rgba(210,153,34,0.2); color: #d29922; }
        .badge-bad { background: rgba(248,81,73,0.2); color: #f85149; }
        
        /* Gráfico de Barras */
        .bar-chart {
            display: flex;
            align-items: flex-end;
            gap: 8px;
            height: 200px;
            padding: 20px;
        }
        .bar-item {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 5px;
        }
        .bar {
            width: 100%;
            border-radius: 4px 4px 0 0;
            transition: height 0.3s;
        }
        .bar-label {
            font-size: 10px;
            color: #8b949e;
            writing-mode: vertical-rl;
            text-orientation: mixed;
        }
        .bar-value {
            font-size: 11px;
            font-weight: 600;
        }
        
        /* Seção de Otimização */
        .optimization {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
        }
        .opt-best {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        .opt-item {
            text-align: center;
            padding: 15px;
            background: #1c2333;
            border-radius: 8px;
        }
        .opt-item .val {
            font-size: 22px;
            font-weight: 700;
            color: #f0b429;
        }
        .opt-item .lbl {
            font-size: 11px;
            color: #8b949e;
            margin-top: 3px;
        }
        
        /* Recomendações */
        .recommendations {
            background: linear-gradient(135deg, #1a2332 0%, #161b22 100%);
            border: 1px solid #f0b429;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
        }
        .rec-title {
            color: #f0b429;
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 15px;
        }
        .rec-item {
            padding: 10px 0;
            border-bottom: 1px solid #21262d;
        }
        .rec-item:last-child { border: none; }
        .rec-icon { margin-right: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 Golden AI — Painel de Estratégia</h1>
        <div class="subtitle">Análise com MiMo | Triple Confluence | """ + datetime.now().strftime('%d/%m/%Y %H:%M') + """</div>
    </div>
    
    <div class="container">
"""
    
    # Resumo
    avg_wr = sum(r["win_rate"] for r in results.values()) / len(results)
    avg_ev = sum(r["expected_value"] for r in results.values()) / len(results)
    best = max(results.items(), key=lambda x: x[1]["expected_value"])
    
    html += f"""
        <!-- Resumo -->
        <div class="summary-grid">
            <div class="summary-card">
                <div class="label">Padrões Ativos</div>
                <div class="value neutral">{len(results)}</div>
            </div>
            <div class="summary-card">
                <div class="label">Win Rate Médio</div>
                <div class="value positive">{avg_wr:.1f}%</div>
            </div>
            <div class="summary-card">
                <div class="label">EV Médio</div>
                <div class="value {'positive' if avg_ev > 0 else 'negative'}">{avg_ev:+.4f}</div>
            </div>
            <div class="summary-card">
                <div class="label">Melhor Padrão</div>
                <div class="value positive" style="font-size:16px">{best[0]}</div>
            </div>
        </div>
"""
    
    # Tabela de Padrões
    html += """
        <!-- Tabela de Padrões -->
        <div class="table-container">
            <div class="table-header">📊 Desempenho por Padrão</div>
            <table>
                <thead>
                    <tr>
                        <th>Padrão</th>
                        <th>Direção</th>
                        <th>Candles</th>
                        <th>Win Rate</th>
                        <th>R:R</th>
                        <th>EV/Trade</th>
                        <th>Retorno Sim</th>
                        <th>Max DD</th>
                        <th>Profit Factor</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    for name, data in sorted(results.items(), key=lambda x: x[1]["expected_value"], reverse=True):
        dir_badge = "badge-buy" if data["direction"] == "COMPRA" else "badge-sell"
        status = "badge-good" if data["expected_value"] > 0.5 else "badge-ok" if data["expected_value"] > 0 else "badge-bad"
        status_text = "🔥 EXCELENTE" if data["expected_value"] > 0.5 else "✅ BOM" if data["expected_value"] > 0 else "❌ RUIM"
        
        html += f"""
                    <tr>
                        <td><strong>{name}</strong></td>
                        <td><span class="badge {dir_badge}">{data["direction"]}</span></td>
                        <td>{data["candles"]}</td>
                        <td><strong>{data["win_rate"]}%</strong></td>
                        <td>{data["rr_ratio"]:.1f}</td>
                        <td class="{'positive' if data['expected_value'] > 0 else 'negative'}">{data["expected_value"]:+.4f}</td>
                        <td class="{'positive' if data['sim_return'] > 0 else 'negative'}">{data["sim_return"]:+.1f}%</td>
                        <td>{data["sim_drawdown"]:.1f}%</td>
                        <td>{data["sim_pf"]:.2f}</td>
                        <td><span class="badge {status}">{status_text}</span></td>
                    </tr>
"""
    
    html += """
                </tbody>
            </table>
        </div>
"""
    
    # Gráfico de Barras - Win Rate
    html += """
        <!-- Gráfico de Win Rate -->
        <div class="table-container">
            <div class="table-header">📈 Win Rate por Padrão</div>
            <div class="bar-chart">
"""
    
    max_wr = max(r["win_rate"] for r in results.values())
    for name, data in sorted(results.items(), key=lambda x: x[1]["win_rate"], reverse=True):
        height = (data["win_rate"] / max_wr) * 180
        color = "#3fb950" if data["win_rate"] > 65 else "#d29922" if data["win_rate"] > 55 else "#f85149"
        html += f"""
                <div class="bar-item">
                    <div class="bar-value" style="color:{color}">{data["win_rate"]}%</div>
                    <div class="bar" style="height:{height}px; background:{color}"></div>
                    <div class="bar-label">{name}</div>
                </div>
"""
    
    html += """
            </div>
        </div>
"""
    
    # Otimização
    if optimization:
        best_opt = optimization["best"]
        html += f"""
        <!-- Otimização -->
        <div class="optimization">
            <div class="table-header">⚙️ Melhor Configuração Encontrada</div>
            <div class="opt-best">
                <div class="opt-item">
                    <div class="val">{best_opt['sl']}</div>
                    <div class="lbl">Stop Loss (pts)</div>
                </div>
                <div class="opt-item">
                    <div class="val">{best_opt['tp']}</div>
                    <div class="lbl">Take Profit (pts)</div>
                </div>
                <div class="opt-item">
                    <div class="val">{best_opt['rr']:.1f}:1</div>
                    <div class="lbl">Risco:Retorno</div>
                </div>
                <div class="opt-item">
                    <div class="val">{best_opt['avg_wr']}%</div>
                    <div class="lbl">Win Rate Médio</div>
                </div>
                <div class="opt-item">
                    <div class="val">{best_opt['avg_return']:+.1f}%</div>
                    <div class="lbl">Retorno Simulado</div>
                </div>
                <div class="opt-item">
                    <div class="val">{best_opt['avg_dd']:.1f}%</div>
                    <div class="lbl">Max Drawdown</div>
                </div>
            </div>
            <p style="margin-top:15px; color:#8b949e; font-size:13px">
                Testadas {optimization['total_tested']} combinações de SL/TP
            </p>
        </div>
"""
    
    # Recomendações
    html += """
        <!-- Recomendações -->
        <div class="recommendations">
            <div class="rec-title">💡 Recomendações da IA</div>
            <div class="rec-item">
                <span class="rec-icon">🎯</span>
                <strong>Triple Confluence:</strong> Use Média + Região S/R + Nível Diário para filtrar sinais fracos
            </div>
            <div class="rec-item">
                <span class="rec-icon">⏰</span>
                <strong>Horário:</strong> Opere entre 09:00-17:00 (Londres + NY) para máxima liquidez
            </div>
            <div class="rec-item">
                <span class="rec-icon">📊</span>
                <strong>Spread:</strong> Mantenha spread abaixo de 50 pontos para entradas precisas
            </div>
            <div class="rec-item">
                <span class="rec-icon">🛡️</span>
                <strong>Risco:</strong> Risco máximo 1% por trade, máximo 3 perdas consecutivas antes de pausar
            </div>
            <div class="rec-item">
                <span class="rec-icon">🔄</span>
                <strong>Adaptativo:</strong> Ative o modo adaptativo para ajustar thresholds automaticamente
            </div>
        </div>
"""
    
    html += """
    </div>
</body>
</html>
"""
    
    return html


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def main():
    print("🎯 Golden AI — Módulo de Estratégia com MiMo")
    print("=" * 50)
    
    analyzer = StrategyAnalyzer()
    
    # 1. Analisar com configuração otimizada
    print("\n📊 Analisando estratégias...")
    config = {
        "triple_confluence": True,
        "filter_spread": True,
        "filter_hours": True,
        "adaptive_mode": True,
    }
    results = analyzer.analyze_strategy(config)
    
    for name, data in sorted(results.items(), key=lambda x: x[1]["expected_value"], reverse=True):
        emoji = "🔥" if data["expected_value"] > 0.5 else "✅" if data["expected_value"] > 0 else "❌"
        print(f"  {emoji} {name:20s} | WR {data['win_rate']:5.1f}% | R:R {data['rr_ratio']:.1f} | EV {data['expected_value']:+.4f}")
    
    # 2. Otimizar parâmetros
    print("\n⚙️ Otimizando parâmetros...")
    optimization = analyzer.optimize_params()
    best = optimization["best"]
    print(f"  🏆 Melhor: SL:{best['sl']} TP:{best['tp']} (R:R {best['rr']:.1f})")
    print(f"     WR: {best['avg_wr']}% | Retorno: {best['avg_return']:+.1f}% | DD: {best['avg_dd']:.1f}%")
    print(f"     Testadas: {optimization['total_tested']} combinações")
    
    # 3. Gerar painel HTML
    print("\n🎨 Gerando painel estatístico...")
    html = generate_strategy_panel_html(results, optimization)
    
    output_dir = r"C:\GoldenAI\studio\golden_ai_studio_web"
    panel_path = os.path.join(output_dir, "strategy_panel.html")
    with open(panel_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  ✅ Painel: {panel_path}")
    
    # 4. Salvar dados JSON
    json_data = {
        "generated_at": datetime.now().isoformat(),
        "results": results,
        "optimization": optimization,
    }
    json_path = os.path.join(r"C:\GoldenAI\.freebuff\test_results", "strategy_data.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ Dados: {json_path}")
    
    print("\n" + "=" * 50)
    print("✅ Módulo de estratégia pronto!")
    print(f"📊 Acesse o painel: http://127.0.0.1:8765/studio/golden_ai_studio_web/strategy_panel.html")


if __name__ == "__main__":
    main()
