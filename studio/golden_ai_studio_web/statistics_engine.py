#!/usr/bin/env python3
"""
Golden AI - Statistics Engine v3
Analytics completos para o Scanner:
  - Performance por estrategia (47 setups)
  - Performance por ativo (22 pares)
  - Performance por horario
  - Performance por regime de mercado
  - Expectancy calibrada por score
  - Walk-forward basico
  - Confidence status por estrategia
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import numpy as np

class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

# ═══════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path(r"C:\GoldenAI\data\statistics")

JOURNAL_DIR = Path(r"C:\GoldenAI\data\trade_journal")


# ═══════════════════════════════════════════════════════════════
# STATISTICS ENGINE
# ═══════════════════════════════════════════════════════════════

class StatisticsEngine:
    """Engine de analytics para o Golden Scanner v3"""

    def __init__(self):
        self._cache = {}
        self._cache_time = None
        self._cache_ttl = 60  # seconds

    # ═══ DATA LOADING ═══

    def _load_journal_entries(self, limit=10000):
        """Carrega todas as entradas do journal"""
        entries = []
        for f in sorted(JOURNAL_DIR.glob("journal_*.jsonl"), reverse=True):
            if not f.exists():
                continue
            with open(f, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                        if len(entries) >= limit:
                            return entries
                    except json.JSONDecodeError:
                        continue
        return entries

    def _load_cached_stats(self):
        """Carrega estatisticas cacheadas"""
        cache_file = DATA_DIR / "cached_stats.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_cached_stats(self, stats):
        """Salva estatisticas em cache"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = DATA_DIR / "cached_stats.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2, cls=_NumpyEncoder)

    # ═══ CORE STATISTICS ═══

    def _normalized_rr_values(self, trades):
        """Retorna R-multiples robustos, corrigindo imports antigos do MT5."""
        resolved = [t for t in trades if t.get('result') in ('WIN', 'LOSS', 'BREAKEVEN')]
        loss_usd = [
            abs(float(t.get('profit_usd', 0) or 0))
            for t in resolved
            if t.get('result') == 'LOSS' and abs(float(t.get('profit_usd', 0) or 0)) > 0
        ]
        usd_risk_unit = float(np.median(loss_usd)) if loss_usd else 0.0

        values = []
        for t in resolved:
            profit_usd = t.get('profit_usd', None)
            rr = t.get('actual_rr', 0)
            try:
                rr = float(rr or 0)
            except (TypeError, ValueError):
                rr = 0.0

            # Imports legados tinham actual_rr calculado como pips/100, criando
            # valores irreais em BTC/ETH/indices. Quando ha PnL em USD, ele e
            # uma base mais confiavel para normalizar.
            imported = str(t.get('confidence', '')).startswith('IMPORTED') or t.get('ai_model') == 'MT5_IMPORT'
            if profit_usd is not None and (imported or abs(rr) > 20):
                try:
                    profit = float(profit_usd or 0)
                except (TypeError, ValueError):
                    profit = 0.0
                if usd_risk_unit > 0:
                    rr = profit / usd_risk_unit
                elif profit > 0:
                    rr = 1.0
                elif profit < 0:
                    rr = -1.0
                else:
                    rr = 0.0

            values.append(max(-20.0, min(20.0, rr)))
        return values

    def _calc_group_stats(self, trades):
        """Calcula metricas basicas para um grupo de trades"""
        if not trades:
            return {
                'total': 0, 'wins': 0, 'losses': 0, 'breakeven': 0,
                'win_rate': 0, 'profit_factor': 0, 'expectancy_r': 0,
                'avg_win_r': 0, 'avg_loss_r': 0, 'avg_rr': 0,
                'max_win': 0, 'max_loss': 0, 'max_consec_wins': 0,
                'max_consec_losses': 0, 'sharpe': 0, 'max_drawdown_r': 0,
                'total_pnl_r': 0, 'avg_mfe': 0, 'avg_mae': 0,
            }

        resolved = [t for t in trades if t.get('result') in ('WIN', 'LOSS', 'BREAKEVEN')]
        if not resolved:
            return {'total': len(trades), 'wins': 0, 'losses': 0, 'breakeven': 0,
                    'win_rate': 0, 'profit_factor': 0, 'expectancy_r': 0}

        wins = [t for t in resolved if t['result'] == 'WIN']
        losses = [t for t in resolved if t['result'] == 'LOSS']
        breakeven = [t for t in resolved if t['result'] == 'BREAKEVEN']

        total = len(resolved)
        win_rate = len(wins) / total * 100 if total > 0 else 0

        rr_by_trade = dict(zip([id(t) for t in resolved], self._normalized_rr_values(resolved)))

        # PnL in R multiples
        win_rrs = [rr_by_trade.get(id(t), 1.0) for t in wins]
        loss_rrs = [abs(rr_by_trade.get(id(t), -1.0)) for t in losses]

        avg_win_r = np.mean(win_rrs) if win_rrs else 0
        avg_loss_r = np.mean(loss_rrs) if loss_rrs else 0

        # Profit Factor
        gross_profit = sum(win_rrs)
        gross_loss = sum(loss_rrs) if loss_rrs else 0.001
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0

        # Expectancy
        expectancy_r = (len(wins)/total * avg_win_r) - (len(losses)/total * avg_loss_r) if total > 0 else 0

        # Consecutive
        max_consec_wins, max_consec_losses = 0, 0
        curr_wins, curr_losses = 0, 0
        for t in resolved:
            if t['result'] == 'WIN':
                curr_wins += 1
                curr_losses = 0
                max_consec_wins = max(max_consec_wins, curr_wins)
            elif t['result'] == 'LOSS':
                curr_losses += 1
                curr_wins = 0
                max_consec_losses = max(max_consec_losses, curr_losses)
            else:
                curr_wins = 0
                curr_losses = 0

        # Max Drawdown in R
        equity = [0]
        for t in resolved:
            rr = rr_by_trade.get(id(t), 0)
            equity.append(equity[-1] + rr)
        peak = equity[0]
        max_dd = 0
        for e in equity:
            if e > peak:
                peak = e
            dd = peak - e
            if dd > max_dd:
                max_dd = dd

        # MFE/MAE
        mfe_values = [t.get('mfe', 0) for t in resolved if t.get('mfe', 0) > 0]
        mae_values = [t.get('mae', 0) for t in resolved if t.get('mae', 0) > 0]

        # Sharpe (simplified)
        rr_values = [rr_by_trade.get(id(t), 0) for t in resolved]
        sharpe = (np.mean(rr_values) / np.std(rr_values)) if len(rr_values) > 1 and np.std(rr_values) > 0 else 0

        # Score distribution
        scores = [t.get('score', 0) for t in resolved]
        avg_score = np.mean(scores) if scores else 0

        return {
            'total': total,
            'wins': len(wins),
            'losses': len(losses),
            'breakeven': len(breakeven),
            'win_rate': round(win_rate, 1),
            'profit_factor': round(min(profit_factor, 999), 2),
            'expectancy_r': round(expectancy_r, 3),
            'avg_win_r': round(avg_win_r, 2),
            'avg_loss_r': round(avg_loss_r, 2),
            'avg_rr': round(np.mean(rr_values), 2) if rr_values else 0,
            'max_win': round(max(win_rrs), 2) if win_rrs else 0,
            'max_loss': round(max(loss_rrs), 2) if loss_rrs else 0,
            'max_consec_wins': max_consec_wins,
            'max_consec_losses': max_consec_losses,
            'sharpe': round(sharpe, 2),
            'max_drawdown_r': round(max_dd, 2),
            'total_pnl_r': round(sum(rr_values), 2),
            'avg_mfe': round(np.mean(mfe_values), 2) if mfe_values else 0,
            'avg_mae': round(np.mean(mae_values), 2) if mae_values else 0,
            'avg_score': round(avg_score, 1),
        }

    # ═══ PERFORMANCE POR ESTRATEGIA ═══

    def get_strategy_performance(self):
        """Performance detalhada de cada uma das 47 estrategias"""
        entries = self._load_journal_entries()
        strategy_stats = {}

        for entry in entries:
            sid = entry.get('setup_id', '')
            # Extract strategy name from setup_id (e.g., "EURUSD_20260826_SCALP_BRK_RETEST" -> "SCALP_BRK_RETEST")
            parts = sid.split('_')
            if len(parts) >= 3:
                # Try to find the strategy part
                for i, p in enumerate(parts):
                    if p in ('SCALP', 'DAY', 'SWING') and i + 1 < len(parts):
                        strategy_key = '_'.join(parts[i:])
                        break
                else:
                    strategy_key = entry.get('symbol', 'UNKNOWN')
            else:
                strategy_key = entry.get('symbol', 'UNKNOWN')

            if strategy_key not in strategy_stats:
                strategy_stats[strategy_key] = []
            strategy_stats[strategy_key].append(entry)

        results = {}
        for strat, trades in strategy_stats.items():
            stats = self._calc_group_stats(trades)
            # Determine confidence status
            if stats['total'] < 10:
                status = 'INCONCLUSIVO'
                status_icon = '[?]'
            elif stats['expectancy_r'] > 0.15 and stats['total'] >= 30:
                status = 'VALIDADA'
                status_icon = '[OK]'
            elif stats['expectancy_r'] > 0:
                status = 'EM_TESTE'
                status_icon = '[~]'
            elif stats['expectancy_r'] > -0.1:
                status = 'FRACA'
                status_icon = '[!]'
            else:
                status = 'NEGATIVA'
                status_icon = '[X]'

            stats['status'] = status
            stats['status_icon'] = status_icon
            stats['strategy_id'] = strat
            results[strat] = stats

        return results

    # ═══ PERFORMANCE POR ATIVO ═══

    def get_asset_performance(self):
        """Performance por ativo (22 pares)"""
        entries = self._load_journal_entries()
        asset_trades = defaultdict(list)

        for entry in entries:
            symbol = entry.get('symbol', 'UNKNOWN')
            asset_trades[symbol].append(entry)

        results = {}
        for symbol, trades in asset_trades.items():
            stats = self._calc_group_stats(trades)

            # Best strategy per asset
            strat_trades = defaultdict(list)
            for t in trades:
                sid = t.get('setup_id', '')
                parts = sid.split('_')
                strat = '_'.join(parts[2:]) if len(parts) > 2 else 'UNKNOWN'
                strat_trades[strat].append(t)

            best_strat = None
            best_exp = -999
            for strat, strades in strat_trades.items():
                s = self._calc_group_stats(strades)
                if s['expectancy_r'] > best_exp and s['total'] >= 5:
                    best_exp = s['expectancy_r']
                    best_strat = strat

            stats['best_strategy'] = best_strat
            stats['best_strategy_expectancy'] = round(best_exp, 3)
            stats['symbol'] = symbol
            results[symbol] = stats

        return results

    # ═══ PERFORMANCE POR HORARIO ═══

    def get_hourly_performance(self):
        """Performance por hora do dia"""
        entries = self._load_journal_entries()
        hourly = defaultdict(list)

        for entry in entries:
            ts = entry.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(ts)
                hour = dt.hour
            except:
                hour = -1
            hourly[hour].append(entry)

        results = {}
        for hour, trades in sorted(hourly.items()):
            if hour < 0:
                continue
            stats = self._calc_group_stats(trades)
            stats['hour'] = hour
            stats['session'] = self._get_session_name(hour)
            results[hour] = stats

        return results

    def _get_session_name(self, hour):
        if 0 <= hour < 7:
            return 'ASIA'
        elif 7 <= hour < 12:
            return 'LONDON'
        elif 12 <= hour < 16:
            return 'OVERLAP'
        elif 16 <= hour < 21:
            return 'NY'
        return 'OFF'

    # ═══ PERFORMANCE POR REGIME ═══

    def get_regime_performance(self):
        """Performance por regime de mercado"""
        entries = self._load_journal_entries()
        regime_trades = defaultdict(list)

        for entry in entries:
            regime = entry.get('tf_h1_trend', 'unknown')
            if regime == 'alta':
                regime = 'trending'
            elif regime == 'baixa':
                regime = 'trending'
            else:
                regime = 'ranging'
            regime_trades[regime].append(entry)

        results = {}
        for regime, trades in regime_trades.items():
            stats = self._calc_group_stats(trades)
            stats['regime'] = regime
            results[regime] = stats

        return results

    # ═══ PERFORMANCE POR MODALIDADE ═══

    def get_mode_performance(self):
        """Performance por modalidade (SCALP/DAY/SWING)"""
        entries = self._load_journal_entries()
        mode_trades = defaultdict(list)

        for entry in entries:
            sid = entry.get('setup_id', '')
            if 'SCALP' in sid:
                mode = 'scalp'
            elif 'DAY' in sid:
                mode = 'day'
            elif 'SWING' in sid:
                mode = 'swing'
            else:
                mode = 'unknown'
            mode_trades[mode].append(entry)

        results = {}
        for mode, trades in mode_trades.items():
            stats = self._calc_group_stats(trades)
            stats['mode'] = mode
            results[mode] = stats

        return results

    # ═══ SCORE CALIBRATION ═══

    def get_score_calibration(self):
        """Mapeia score 0-100 para expectancy real"""
        entries = self._load_journal_entries()
        resolved = [e for e in entries if e.get('result') in ('WIN', 'LOSS', 'BREAKEVEN')]

        if len(resolved) < 20:
            return {'calibrated': False, 'message': 'Need 20+ resolved trades'}

        # Group by score buckets
        buckets = {}
        for e in resolved:
            score = e.get('score', 0)
            bucket = (score // 10) * 10  # 0-9, 10-19, 20-29, etc.
            if bucket not in buckets:
                buckets[bucket] = []
            buckets[bucket].append(e)

        calibration = {}
        for bucket, trades in sorted(buckets.items()):
            stats = self._calc_group_stats(trades)
            if stats['total'] >= 3:
                calibration['%d-%d' % (bucket, bucket + 9)] = {
                    'trades': stats['total'],
                    'win_rate': stats['win_rate'],
                    'expectancy_r': stats['expectancy_r'],
                    'profit_factor': stats['profit_factor'],
                }

        return {'calibrated': True, 'buckets': calibration}

    # ═══ WALK-FORWARD ═══

    def get_walk_forward(self, train_months=6, test_months=1):
        """Walk-forward analysis basico"""
        entries = self._load_journal_entries()
        resolved = [e for e in entries if e.get('result') in ('WIN', 'LOSS', 'BREAKEVEN')]

        if len(resolved) < 50:
            return {'sufficient_data': False, 'message': 'Need 50+ resolved trades'}

        # Sort by timestamp
        resolved.sort(key=lambda e: e.get('timestamp', ''))

        # Split into periods
        results = []
        period_size = len(resolved) // 4  # 4 periods
        if period_size < 10:
            return {'sufficient_data': False, 'message': 'Not enough data for walk-forward'}

        for i in range(3):
            train_start = i * period_size
            train_end = train_start + period_size
            test_start = train_end
            test_end = min(test_start + period_size // 2, len(resolved))

            if test_end <= test_start:
                break

            train_data = resolved[train_start:train_end]
            test_data = resolved[test_start:test_end]

            train_stats = self._calc_group_stats(train_data)
            test_stats = self._calc_group_stats(test_data)

            results.append({
                'period': i + 1,
                'train_trades': train_stats['total'],
                'train_win_rate': train_stats['win_rate'],
                'train_expectancy': train_stats['expectancy_r'],
                'test_trades': test_stats['total'],
                'test_win_rate': test_stats['win_rate'],
                'test_expectancy': test_stats['expectancy_r'],
                'stability': bool(abs(train_stats['expectancy_r'] - test_stats['expectancy_r']) < 0.2),
            })

        return {'sufficient_data': True, 'periods': results}

    # ═══ CONFIDENCE STATUS ═══

    def get_confidence_status(self):
        """Status de confianca para cada estrategia"""
        strat_perf = self.get_strategy_performance()
        status_counts = defaultdict(int)
        for strat, stats in strat_perf.items():
            status_counts[stats['status']] += 1

        return {
            'total_strategies': len(strat_perf),
            'status_distribution': dict(status_counts),
            'strategies': {k: {'status': v['status'], 'status_icon': v['status_icon'],
                               'expectancy_r': v['expectancy_r'], 'total': v['total']}
                           for k, v in strat_perf.items()},
        }

    # ═══ FULL DASHBOARD DATA ═══

    def get_full_dashboard(self):
        """Dados completos para o dashboard"""
        cache = self._load_cached_stats()
        now = datetime.now()

        # Cache for 60 seconds
        if cache.get('_cached_at'):
            try:
                cached_at = datetime.fromisoformat(cache['_cached_at'])
                if (now - cached_at).seconds < self._cache_ttl:
                    return cache
            except:
                pass

        dashboard = {
            '_cached_at': now.isoformat(),
            'strategy_performance': self.get_strategy_performance(),
            'asset_performance': self.get_asset_performance(),
            'hourly_performance': self.get_hourly_performance(),
            'regime_performance': self.get_regime_performance(),
            'mode_performance': self.get_mode_performance(),
            'score_calibration': self.get_score_calibration(),
            'walk_forward': self.get_walk_forward(),
            'confidence_status': self.get_confidence_status(),
        }

        self._save_cached_stats(dashboard)
        return dashboard


# Singleton
_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = StatisticsEngine()
    return _engine


if __name__ == '__main__':
    engine = get_engine()
    print("=== STATISTICS ENGINE v3 ===")
    print()

    # Strategy performance
    sp = engine.get_strategy_performance()
    print(f"Estrategias com dados: {len(sp)}")
    for strat, stats in sorted(sp.items(), key=lambda x: x[1]['expectancy_r'], reverse=True):
        if stats['total'] > 0:
            print(f"  {stats['status_icon']} {strat:30} | Trades:{stats['total']:4} | WR:{stats['win_rate']:5.1f}% | EV:{stats['expectancy_r']:+.3f}R | PF:{stats['profit_factor']:.2f}")

    print()
    # Score calibration
    cal = engine.get_score_calibration()
    if cal.get('calibrated'):
        print("Score Calibration:")
        for bucket, data in cal['buckets'].items():
            print(f"  Score {bucket}: WR={data['win_rate']:.1f}% | EV={data['expectancy_r']:+.3f}R | Trades={data['trades']}")
    else:
        print(f"Score Calibration: {cal.get('message', 'N/A')}")
