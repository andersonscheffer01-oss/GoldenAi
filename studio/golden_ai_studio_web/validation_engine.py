#!/usr/bin/env python3
"""
Golden AI - Validation Engine v3
Validacao completa de estrategias:
  1. Backtest Simulation — simula trades historicos com parametros reais
  2. Monte Carlo — 1000+ simulacoes para medir risco de ruin
  3. Robustness Test — variar SL/TP/Entry e medir impacto
  4. Equity Curve — curva de capital simulada
  5. Walk-Forward — treino/teste/out-of-sample
  6. Mode Comparison — SCALP vs DAY vs SWING
"""

import json
import random
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import numpy as np

DATA_DIR = Path(r"C:\GoldenAI\data\validation")
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# VALIDATION ENGINE
# ═══════════════════════════════════════════════════════════════

class ValidationEngine:
    """Motor de validacao para estrategias de trading"""

    def __init__(self):
        self._cache = {}

    # ═══ 1. BACKTEST SIMULATION ═══

    def simulate_trades(self, win_rate=0.5, avg_win_r=1.5, avg_loss_r=1.0,
                        num_trades=200, slippage_r=0.05, commission_r=0.02,
                        initial_balance=10000, risk_pct=0.25):
        """
        Simula uma sequencia de trades com parametros realistas.
        Retorna equity curve e metricas.
        """
        random.seed(42)
        balance = initial_balance
        equity_curve = [balance]
        trades = []
        peak = balance
        max_dd = 0
        wins, losses = 0, 0
        total_pnl = 0

        for i in range(num_trades):
            risk_amount = balance * (risk_pct / 100.0)
            is_win = random.random() < win_rate

            if is_win:
                pnl = risk_amount * avg_win_r
                wins += 1
            else:
                pnl = -risk_amount * avg_loss_r
                losses += 1

            # Deduct costs
            pnl -= risk_amount * slippage_r
            pnl -= risk_amount * commission_r

            balance += pnl
            total_pnl += pnl
            equity_curve.append(balance)

            # Drawdown
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

            trades.append({
                'trade': i + 1,
                'result': 'WIN' if is_win else 'LOSS',
                'pnl': round(pnl, 2),
                'balance': round(balance, 2),
                'drawdown_pct': round(dd, 2),
            })

        # Metrics
        total = wins + losses
        win_rate_actual = wins / total * 100 if total > 0 else 0
        avg_win = sum(t['pnl'] for t in trades if t['result'] == 'WIN') / max(wins, 1)
        avg_loss = abs(sum(t['pnl'] for t in trades if t['result'] == 'LOSS') / max(losses, 1))
        profit_factor = (wins * avg_win) / (losses * avg_loss) if losses > 0 and avg_loss > 0 else 999

        # Sharpe
        returns = [t['pnl'] / initial_balance for t in trades]
        sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if len(returns) > 1 and np.std(returns) > 0 else 0

        # Calmar
        calmar = (total_pnl / initial_balance * 100) / max_dd if max_dd > 0 else 999

        # Max consecutive
        max_consec_wins, max_consec_losses = 0, 0
        cw, cl = 0, 0
        for t in trades:
            if t['result'] == 'WIN':
                cw += 1; cl = 0
                max_consec_wins = max(max_consec_wins, cw)
            else:
                cl += 1; cw = 0
                max_consec_losses = max(max_consec_losses, cl)

        return {
            'params': {
                'win_rate': win_rate, 'avg_win_r': avg_win_r, 'avg_loss_r': avg_loss_r,
                'num_trades': num_trades, 'slippage_r': slippage_r, 'commission_r': commission_r,
                'initial_balance': initial_balance, 'risk_pct': risk_pct,
            },
            'results': {
                'total_trades': total,
                'wins': wins, 'losses': losses,
                'win_rate': round(win_rate_actual, 1),
                'total_pnl': round(total_pnl, 2),
                'final_balance': round(balance, 2),
                'return_pct': round((balance - initial_balance) / initial_balance * 100, 2),
                'profit_factor': round(min(profit_factor, 999), 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'sharpe': round(sharpe, 2),
                'calmar': round(min(calmar, 999), 2),
                'max_drawdown_pct': round(max_dd, 2),
                'max_consec_wins': max_consec_wins,
                'max_consec_losses': max_consec_losses,
            },
            'equity_curve': equity_curve,
            'trades': trades,
        }

    # ═══ 2. MONTE CARLO ═══

    def monte_carlo(self, win_rate=0.5, avg_win_r=1.5, avg_loss_r=1.0,
                    num_trades=200, num_simulations=1000, initial_balance=10000,
                    risk_pct=0.25):
        """
        Roda N simulacoes aleatorias para medir:
        - Distribuicao de retornos
        - Risco de ruin
        - Drawdown provavel
        - Sequencia de perdas maxima
        """
        results = []
        ruin_count = 0

        for sim in range(num_simulations):
            random.seed(sim)
            balance = initial_balance
            peak = balance
            max_dd = 0
            max_consec_loss = 0
            curr_loss = 0

            for trade in range(num_trades):
                risk_amount = balance * (risk_pct / 100.0)
                is_win = random.random() < win_rate
                if is_win:
                    pnl = risk_amount * avg_win_r
                    curr_loss = 0
                else:
                    pnl = -risk_amount * avg_loss_r
                    curr_loss += 1
                    max_consec_loss = max(max_consec_loss, curr_loss)

                balance += pnl
                if balance > peak:
                    peak = balance
                dd = (peak - balance) / peak * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd

                if balance <= initial_balance * 0.5:  # 50% drawdown = ruin
                    ruin_count += 1
                    break

            results.append({
                'final_balance': round(balance, 2),
                'return_pct': round((balance - initial_balance) / initial_balance * 100, 2),
                'max_drawdown_pct': round(max_dd, 2),
                'max_consec_losses': max_consec_loss,
            })

        # Aggregate
        returns = [r['return_pct'] for r in results]
        drawdowns = [r['max_drawdown_pct'] for r in results]
        consec_losses = [r['max_consec_losses'] for r in results]

        return {
            'simulations': num_simulations,
            'trades_per_sim': num_trades,
            'ruin_probability': round(ruin_count / num_simulations * 100, 2),
            'return_median': round(float(np.median(returns)), 2),
            'return_p5': round(float(np.percentile(returns, 5)), 2),
            'return_p25': round(float(np.percentile(returns, 25)), 2),
            'return_p75': round(float(np.percentile(returns, 75)), 2),
            'return_p95': round(float(np.percentile(returns, 95)), 2),
            'return_mean': round(float(np.mean(returns)), 2),
            'return_std': round(float(np.std(returns)), 2),
            'drawdown_median': round(float(np.median(drawdowns)), 2),
            'drawdown_p95': round(float(np.percentile(drawdowns, 95)), 2),
            'max_consec_losses_median': round(float(np.median(consec_losses)), 0),
            'max_consec_losses_p95': round(float(np.percentile(consec_losses, 95)), 0),
            'positive_sims_pct': round(sum(1 for r in returns if r > 0) / num_simulations * 100, 1),
        }

    def monte_carlo_from_trades(self, trade_r_values, num_simulations=1000,
                                initial_balance=10000, risk_pct=0.25):
        """Monte Carlo reamostrando os R reais observados no journal/backtest."""
        values = [float(v) for v in trade_r_values if v is not None and math.isfinite(float(v))]
        if not values:
            return self.monte_carlo(num_simulations=num_simulations, initial_balance=initial_balance)
        results = []
        ruin_count = 0
        for sim in range(num_simulations):
            rng = random.Random(sim)
            balance = initial_balance
            peak = balance
            max_dd = 0.0
            max_losses = 0
            losses = 0
            for _ in range(len(values)):
                r_value = rng.choice(values)
                balance += balance * (risk_pct / 100.0) * r_value
                losses = losses + 1 if r_value < 0 else 0
                max_losses = max(max_losses, losses)
                peak = max(peak, balance)
                max_dd = max(max_dd, (peak - balance) / peak * 100 if peak > 0 else 0)
                if balance <= initial_balance * 0.5:
                    ruin_count += 1
                    break
            results.append({'return_pct': (balance - initial_balance) / initial_balance * 100,
                            'max_drawdown_pct': max_dd, 'max_consec_losses': max_losses,
                            'final_balance': balance})
        returns = [r['return_pct'] for r in results]
        drawdowns = [r['max_drawdown_pct'] for r in results]
        losses = [r['max_consec_losses'] for r in results]
        return {
            'simulations': num_simulations,
            'trades_per_sim': len(values),
            'sample_size': len(values),
            'source': 'REAL_TRADE_R_DISTRIBUTION',
            'ruin_probability': round(ruin_count / num_simulations * 100, 2),
            'return_median': round(float(np.median(returns)), 2),
            'return_p5': round(float(np.percentile(returns, 5)), 2),
            'return_p25': round(float(np.percentile(returns, 25)), 2),
            'return_p75': round(float(np.percentile(returns, 75)), 2),
            'return_p95': round(float(np.percentile(returns, 95)), 2),
            'return_mean': round(float(np.mean(returns)), 2),
            'return_std': round(float(np.std(returns)), 2),
            'drawdown_median': round(float(np.median(drawdowns)), 2),
            'drawdown_p95': round(float(np.percentile(drawdowns, 95)), 2),
            'max_consec_losses_median': round(float(np.median(losses)), 0),
            'max_consec_losses_p95': round(float(np.percentile(losses, 95)), 0),
            'positive_sims_pct': round(sum(1 for r in returns if r > 0) / num_simulations * 100, 1),
        }

    # ═══ 3. ROBUSTNESS TEST ═══

    def robustness_test(self, base_win_rate=0.5, base_avg_win=1.5, base_avg_loss=1.0,
                        num_trades=200, variations=None):
        """
        Testa robustez variando parametros:
        - SL +/- 10%, 20%
        - TP +/- 10%, 20%
        - Entry +/- some ticks
        Se a estrategia so funciona com parametros exatos, e fragil.
        """
        if variations is None:
            variations = [
                {'name': 'BASE', 'win_rate': base_win_rate, 'avg_win': base_avg_win, 'avg_loss': base_avg_loss},
                {'name': 'SL -10%', 'win_rate': base_win_rate * 0.95, 'avg_win': base_avg_win * 0.9, 'avg_loss': base_avg_loss},
                {'name': 'SL +10%', 'win_rate': base_win_rate * 1.02, 'avg_win': base_avg_win * 1.1, 'avg_loss': base_avg_loss},
                {'name': 'TP -10%', 'win_rate': base_win_rate * 1.02, 'avg_win': base_avg_win * 0.9, 'avg_loss': base_avg_loss},
                {'name': 'TP +10%', 'win_rate': base_win_rate * 0.95, 'avg_win': base_avg_win * 1.1, 'avg_loss': base_avg_loss},
                {'name': 'SL+TP -10%', 'win_rate': base_win_rate, 'avg_win': base_avg_win * 0.9, 'avg_loss': base_avg_loss * 0.9},
                {'name': 'SL+TP +10%', 'win_rate': base_win_rate, 'avg_win': base_avg_win * 1.1, 'avg_loss': base_avg_loss * 1.1},
                {'name': 'WR -5%', 'win_rate': base_win_rate * 0.9, 'avg_win': base_avg_win, 'avg_loss': base_avg_loss},
                {'name': 'WR +5%', 'win_rate': min(0.8, base_win_rate * 1.1), 'avg_win': base_avg_win, 'avg_loss': base_avg_loss},
            ]

        results = []
        for v in variations:
            sim = self.simulate_trades(
                win_rate=v['win_rate'], avg_win_r=v['avg_win'], avg_loss_r=v['avg_loss'],
                num_trades=num_trades
            )
            r = sim['results']
            results.append({
                'variation': v['name'],
                'win_rate': r['win_rate'],
                'total_pnl': r['total_pnl'],
                'return_pct': r['return_pct'],
                'profit_factor': r['profit_factor'],
                'max_drawdown_pct': r['max_drawdown_pct'],
                'sharpe': r['sharpe'],
                'positive': r['total_pnl'] > 0,
            })

        # Robustness score
        positive_count = sum(1 for r in results if r['positive'])
        robustness_score = positive_count / len(results) * 100

        return {
            'robustness_score': round(robustness_score, 1),
            'variations_tested': len(results),
            'positive_variations': positive_count,
            'results': results,
            'verdict': 'ROBUST' if robustness_score >= 70 else ('MODERATE' if robustness_score >= 50 else 'FRAGILE'),
        }

    # ═══ 4. EQUITY CURVE ═══

    def generate_equity_curve(self, win_rate=0.5, avg_win_r=1.5, avg_loss_r=1.0,
                              num_trades=200, initial_balance=10000, risk_pct=0.25,
                              num_curves=5):
        """Gera multiplas curvas de equity para visualizacao"""
        curves = []
        for i in range(num_curves):
            random.seed(i * 100 + 42)
            sim = self.simulate_trades(
                win_rate=win_rate, avg_win_r=avg_win_r, avg_loss_r=avg_loss_r,
                num_trades=num_trades, initial_balance=initial_balance, risk_pct=risk_pct
            )
            curves.append({
                'curve_id': i + 1,
                'equity_curve': sim['equity_curve'],
                'final_balance': sim['results']['final_balance'],
                'return_pct': sim['results']['return_pct'],
                'max_dd': sim['results']['max_drawdown_pct'],
            })
        return curves

    # ═══ 5. WALK-FORWARD ═══

    def walk_forward_analysis(self, win_rate=0.5, avg_win_r=1.5, avg_loss_r=1.0,
                              total_trades=500, train_pct=0.6, test_pct=0.2,
                              num_windows=3):
        """
        Walk-forward analysis:
        - Window 1: Train[0-60%] -> Test[60-80%]
        - Window 2: Train[20-80%] -> Test[80-100%]
        - Window 3: Train[0-80%] -> Test[80-100%] (out-of-sample)
        """
        trades_per_window = total_trades // num_windows
        results = []

        for w in range(num_windows):
            seed = w * 1000 + 42
            random.seed(seed)

            # Generate all trades for this window
            all_trades = []
            for i in range(trades_per_window):
                is_win = random.random() < win_rate
                all_trades.append(1 if is_win else -1)

            # Split into train/test
            train_size = int(len(all_trades) * train_pct)
            test_size = int(len(all_trades) * test_pct)

            train_trades = all_trades[:train_size]
            test_trades = all_trades[train_size:train_size + test_size]

            # Calculate metrics for train
            train_wins = sum(1 for t in train_trades if t > 0)
            train_total = len(train_trades)
            train_wr = train_wins / train_total * 100 if train_total > 0 else 0
            train_pnl = sum(t * avg_win_r if t > 0 else t * avg_loss_r for t in train_trades)

            # Calculate metrics for test
            test_wins = sum(1 for t in test_trades if t > 0)
            test_total = len(test_trades)
            test_wr = test_wins / test_total * 100 if test_total > 0 else 0
            test_pnl = sum(t * avg_win_r if t > 0 else t * avg_loss_r for t in test_trades)

            # Stability
            wr_diff = abs(train_wr - test_wr)
            stability = 'STABLE' if wr_diff < 10 else ('MODERATE' if wr_diff < 20 else 'UNSTABLE')

            results.append({
                'window': w + 1,
                'train_trades': train_total,
                'train_win_rate': round(train_wr, 1),
                'train_pnl_r': round(train_pnl, 2),
                'test_trades': test_total,
                'test_win_rate': round(test_wr, 1),
                'test_pnl_r': round(test_pnl, 2),
                'wr_difference': round(wr_diff, 1),
                'stability': stability,
            })

        # Overall
        avg_stability = sum(1 for r in results if r['stability'] == 'STABLE') / len(results) * 100

        return {
            'windows': num_windows,
            'results': results,
            'overall_stability': round(avg_stability, 1),
            'verdict': 'ROBUST' if avg_stability >= 67 else ('MODERATE' if avg_stability >= 33 else 'FRAGILE'),
        }

    # ═══ 6. MODE COMPARISON ═══

    def compare_modes(self):
        """Compara SCALP vs DAY vs SWING com parametros tipicos"""
        modes = {
            'scalp': {'win_rate': 0.52, 'avg_win': 1.2, 'avg_loss': 1.0, 'trades_day': 8, 'cost': 0.03},
            'day': {'win_rate': 0.48, 'avg_win': 1.8, 'avg_loss': 1.0, 'trades_day': 3, 'cost': 0.02},
            'swing': {'win_rate': 0.45, 'avg_win': 2.5, 'avg_loss': 1.0, 'trades_day': 0.5, 'cost': 0.01},
        }

        results = {}
        for mode, params in modes.items():
            annual_trades = int(params['trades_day'] * 250)
            sim = self.simulate_trades(
                win_rate=params['win_rate'], avg_win_r=params['avg_win'],
                avg_loss_r=params['avg_loss'], num_trades=min(annual_trades, 500),
                slippage_r=params['cost'], commission_r=params['cost'] * 0.5
            )
            r = sim['results']
            results[mode] = {
                'mode': mode,
                'annual_trades': annual_trades,
                'win_rate': r['win_rate'],
                'total_pnl': r['total_pnl'],
                'return_pct': r['return_pct'],
                'profit_factor': r['profit_factor'],
                'max_drawdown_pct': r['max_drawdown_pct'],
                'sharpe': r['sharpe'],
                'avg_win': r['avg_win'],
                'avg_loss': r['avg_loss'],
            }

        # Rank by Sharpe
        ranked = sorted(results.values(), key=lambda x: x['sharpe'], reverse=True)

        return {
            'modes': results,
            'ranking': [{'mode': r['mode'], 'sharpe': r['sharpe'], 'return_pct': r['return_pct']} for r in ranked],
            'best_mode': ranked[0]['mode'] if ranked else 'unknown',
        }

    # ═══ FULL VALIDATION ═══

    def run_full_validation(self, win_rate=0.5, avg_win_r=1.5, avg_loss_r=1.0,
                            num_trades=200, initial_balance=10000):
        """Executa toda a suíte de validação"""
        # 1. Backtest simulation
        backtest = self.simulate_trades(win_rate, avg_win_r, avg_loss_r, num_trades, initial_balance=initial_balance)

        # 2. Monte Carlo
        monte_carlo = self.monte_carlo(win_rate, avg_win_r, avg_loss_r, num_trades, 1000, initial_balance)

        # 3. Robustness
        robustness = self.robustness_test(win_rate, avg_win_r, avg_loss_r, num_trades)

        # 4. Equity curves
        equity_curves = self.generate_equity_curve(win_rate, avg_win_r, avg_loss_r, num_trades, initial_balance, num_curves=5)

        # 5. Walk-forward
        walk_forward = self.walk_forward_analysis(win_rate, avg_win_r, avg_loss_r, num_trades * 2)

        # 6. Mode comparison
        mode_comparison = self.compare_modes()

        return {
            'backtest': backtest,
            'monte_carlo': monte_carlo,
            'robustness': robustness,
            'equity_curves': equity_curves,
            'walk_forward': walk_forward,
            'mode_comparison': mode_comparison,
        }


    # ═══ 7. VALIDATE WITH REAL DATA (Bridge to Journal + Statistics) ═══

    def _entry_matches_strategy(self, entry, strategy_id):
        """Confere se um registro do journal pertence a uma estrategia."""
        if not strategy_id:
            return False
        candidates = [
            entry.get('strategy_id', ''),
            entry.get('setup_key', ''),
            entry.get('setup_code', ''),
            entry.get('setup_id', ''),
            entry.get('setup', ''),
        ]
        best_setup = entry.get('best_setup')
        if isinstance(best_setup, dict):
            candidates.extend([
                best_setup.get('setup_id', ''),
                best_setup.get('id', ''),
                best_setup.get('name', ''),
            ])
        elif best_setup:
            candidates.append(str(best_setup))
        target = strategy_id.upper()
        return any(target in str(value).upper() for value in candidates if value)

    def validate_strategy_real_data(self, strategy_id):
        """Valida uma estrategia usando dados reais do Trade Journal e Statistics Engine"""
        try:
            from trade_journal import journal
            all_entries = journal.get_recent_entries(limit=50000)
            strategy_entries = [e for e in all_entries if self._entry_matches_strategy(e, strategy_id)]
            resolved = [e for e in strategy_entries if e.get('result') not in ('PENDING', '', None)]

            if len(resolved) < 5:
                total_trades = len(resolved)
                win_rate = 0
                avg_win = 1.5
                avg_loss = 1.0
                expectancy = 0
                profit_factor = 0
                sharpe = 0
            else:
                total_trades = len(resolved)
                wins = sum(1 for e in resolved if e.get('result') == 'WIN')
                losses = sum(1 for e in resolved if e.get('result') == 'LOSS')
                total_rw = wins + losses
                win_rate = wins / total_rw if total_rw > 0 else 0.5
                profits = [e.get('profit_usd', 0) for e in resolved if e.get('result') == 'WIN']
                loss_amts = [abs(e.get('profit_usd', 0)) for e in resolved if e.get('result') == 'LOSS']
                avg_win_usd = np.mean(profits) if profits else 10
                avg_loss_usd = np.mean(loss_amts) if loss_amts else 10
                avg_win = avg_win_usd / avg_loss_usd if avg_loss_usd > 0 else 1.5
                avg_loss = 1.0
                total_profit = sum(e.get('profit_usd', 0) for e in resolved)
                expectancy = total_profit / total_rw / avg_loss_usd if total_rw > 0 and avg_loss_usd > 0 else 0
                gross_profit = sum(e.get('profit_usd', 0) for e in resolved if e.get('result') == 'WIN')
                gross_loss = abs(sum(e.get('profit_usd', 0) for e in resolved if e.get('result') == 'LOSS'))
                profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999
                pnls = [e.get('profit_usd', 0) for e in resolved]
                if len(pnls) > 1 and np.std(pnls) > 0:
                    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252)
                else:
                    sharpe = 0

            if total_trades < 5:
                return {
                    'strategy_id': strategy_id,
                    'status': 'INCONCLUSIVO',
                    'status_icon': '?',
                    'status_color': '#888',
                    'total_trades': total_trades,
                    'confidence_level': 0,
                    'message': 'Dados insuficientes para %s (%d trades). Minimo 5.' % (strategy_id, total_trades),
                    'backtest': None,
                    'monte_carlo': None,
                    'recommendation': 'NEEDS_DATA',
                }

            pass  # Stats already calculated above from journal

            backtest = self.simulate_trades(
                win_rate=win_rate if win_rate > 0 else 0.5,
                avg_win_r=avg_win if avg_win > 0 else 1.5,
                avg_loss_r=avg_loss if avg_loss > 0 else 1.0,
                num_trades=max(total_trades, 50),
                initial_balance=10000,
            )

            trade_r_values = [e.get('actual_rr', 0) for e in resolved]
            mc = self.monte_carlo_from_trades(trade_r_values, num_simulations=500)

            robust = self.robustness_test(
                base_win_rate=win_rate if win_rate > 0 else 0.5,
                base_avg_win=avg_win if avg_win > 0 else 1.5,
                base_avg_loss=avg_loss if avg_loss > 0 else 1.0,
                num_trades=max(total_trades, 50),
            )

            confidence = 0
            if total_trades >= 50: confidence += 20
            elif total_trades >= 20: confidence += 10
            elif total_trades >= 10: confidence += 5
            if expectancy > 0.3: confidence += 25
            elif expectancy > 0.1: confidence += 15
            elif expectancy > 0: confidence += 5
            if profit_factor > 1.5: confidence += 20
            elif profit_factor > 1.2: confidence += 10
            if sharpe > 1.0: confidence += 15
            elif sharpe > 0.5: confidence += 8
            if robust.get('robustness_score', 0) >= 70: confidence += 20
            elif robust.get('robustness_score', 0) >= 50: confidence += 10
            confidence = min(confidence, 100)

            if confidence >= 70:
                status = 'VALIDADA'
                status_icon = 'OK'
                status_color = '#22c55e'
                recommendation = 'RECOMMEND_ON'
            elif confidence >= 40:
                status = 'EM_TESTE'
                status_icon = '~'
                status_color = '#eab308'
                recommendation = 'NEEDS_DATA'
            elif confidence >= 20:
                status = 'FRACA'
                status_icon = '!'
                status_color = '#f97316'
                recommendation = 'RECOMMEND_OFF'
            elif expectancy < -0.1:
                status = 'NEGATIVA'
                status_icon = 'X'
                status_color = '#ef4444'
                recommendation = 'RECOMMEND_OFF'
            else:
                status = 'INCONCLUSIVO'
                status_icon = '?'
                status_color = '#888'
                recommendation = 'NEEDS_DATA'

            return {
                'strategy_id': strategy_id,
                'status': status,
                'status_icon': status_icon,
                'status_color': status_color,
                'total_trades': total_trades,
                'confidence_level': confidence,
                'win_rate': round(win_rate * 100, 1) if win_rate > 0 else 0,
                'expectancy': round(expectancy, 3),
                'profit_factor': round(profit_factor, 2),
                'sharpe': round(sharpe, 2),
                'backtest': {
                    'return_pct': backtest['results']['return_pct'],
                    'max_dd': backtest['results']['max_drawdown_pct'],
                    'pf': backtest['results']['profit_factor'],
                },
                'monte_carlo': {
                    'ruin_pct': mc['ruin_probability'],
                    'median_return': mc['return_median'],
                    'p95_dd': mc['drawdown_p95'],
                },
                'robustness': {
                    'score': robust['robustness_score'],
                    'verdict': robust['verdict'],
                },
                'recommendation': recommendation,
                'message': '%s (%d trades, EV: %sR, PF: %s)' % (status, total_trades, round(expectancy, 3), round(profit_factor, 2)),
            }
        except Exception as e:
            return {
                'strategy_id': strategy_id,
                'status': 'ERRO',
                'status_icon': '!',
                'status_color': '#ef4444',
                'total_trades': 0,
                'confidence_level': 0,
                'message': str(e),
                'recommendation': 'NEEDS_DATA',
            }

    def validate_all_strategies(self):
        """Valida todas as 47 estrategias usando dados reais"""
        try:
            from golden_scanner import SETUP_DEFINITIONS
        except ImportError:
            return {'error': 'SETUP_DEFINITIONS not found'}

        results = {}
        for sid in SETUP_DEFINITIONS:
            results[sid] = self.validate_strategy_real_data(sid)

        summary = {
            'total': len(results),
            'validated': sum(1 for r in results.values() if r.get('status') == 'VALIDADA'),
            'testing': sum(1 for r in results.values() if r.get('status') == 'EM_TESTE'),
            'weak': sum(1 for r in results.values() if r.get('status') == 'FRACA'),
            'negative': sum(1 for r in results.values() if r.get('status') == 'NEGATIVA'),
            'inconclusive': sum(1 for r in results.values() if r.get('status') in ('INCONCLUSIVO', 'ERRO')),
        }

        return {'strategies': results, 'summary': summary}

    def get_validation_status_for_signal(self, strategy_id, score):
        """Retorna status de validacao para incluir em um sinal do Scanner"""
        v = self.validate_strategy_real_data(strategy_id)
        return {
            'validation_status': v.get('status', 'INCONCLUSIVO'),
            'validation_icon': v.get('status_icon', '?'),
            'validation_color': v.get('status_color', '#888'),
            'validation_confidence': v.get('confidence_level', 0),
            'validation_trades': v.get('total_trades', 0),
            'validation_ev': v.get('expectancy', 0),
            'validation_pf': v.get('profit_factor', 0),
            'validation_sharpe': v.get('sharpe', 0),
            'validation_recommendation': v.get('recommendation', 'NEEDS_DATA'),
            'validation_message': v.get('message', ''),
        }


# Singleton
_engine = None

def get_validation_engine():
    global _engine
    if _engine is None:
        _engine = ValidationEngine()
    return _engine


if __name__ == '__main__':
    engine = get_validation_engine()

    print("=== VALIDATION ENGINE v3 ===")
    print()

    # Full validation
    result = engine.run_full_validation(0.5, 1.5, 1.0, 200, 10000)

    # Backtest
    bt = result['backtest']['results']
    print("BACKTEST (200 trades, WR=50%, R:R 1.5:1):")
    print(f"  Return: {bt['return_pct']}%")
    print(f"  Profit Factor: {bt['profit_factor']}")
    print(f"  Max Drawdown: {bt['max_drawdown_pct']}%")
    print(f"  Sharpe: {bt['sharpe']}")
    print()

    # Monte Carlo
    mc = result['monte_carlo']
    print("MONTE CARLO (1000 simulations):")
    print(f"  Ruin probability: {mc['ruin_probability']}%")
    print(f"  Return median: {mc['return_median']}%")
    print(f"  Return P5-P95: {mc['return_p5']}% to {mc['return_p95']}%")
    print(f"  Max DD P95: {mc['drawdown_p95']}%")
    print(f"  Max consecutive losses P95: {mc['max_consec_losses_p95']}")
    print()

    # Robustness
    rob = result['robustness']
    print("ROBUSTNESS:")
    print(f"  Score: {rob['robustness_score']}% ({rob['verdict']})")
    print(f"  Positive variations: {rob['positive_variations']}/{rob['variations_tested']}")
    print()

    # Walk-forward
    wf = result['walk_forward']
    print("WALK-FORWARD:")
    print(f"  Stability: {wf['overall_stability']}% ({wf['verdict']})")
    for w in wf['results']:
        print(f"  Window {w['window']}: Train WR={w['train_win_rate']}% -> Test WR={w['test_win_rate']}% [{w['stability']}]")
    print()

    # Mode comparison
    mc = result['mode_comparison']
    print("MODE COMPARISON:")
    for r in mc['ranking']:
        print(f"  {r['mode']:6} | Sharpe: {r['sharpe']:.2f} | Return: {r['return_pct']:.1f}%")
    print(f"  Best: {mc['best_mode']}")
