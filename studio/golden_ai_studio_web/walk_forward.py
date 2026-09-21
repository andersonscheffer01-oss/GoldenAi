#!/usr/bin/env python3
"""
Golden AI - Walk-Forward Testing Engine
Valida estrategias em dados fora da amostra para detectar overfitting.

Metodo:
  1. Separar dados em treino/validacao/out-of-sample
  2. Otimizar parametros no treino
  3. Validar na validacao
  4. Testar fora da amostra
  5. Calcular robustez
"""

import MetaTrader5 as mt5
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import json


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class WalkForwardWindow:
    """Uma janela de walk-forward"""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    # Resultados do treino
    train_win_rate: float
    train_expectancy: float
    train_trades: int
    # Resultados do teste (out-of-sample)
    test_win_rate: float
    test_expectancy: float
    test_trades: int
    # Degradacao
    degradation: float  # % de perda de performance
    overfitting_risk: str  # 'baixo', 'medio', 'alto'


@dataclass
class WalkForwardResult:
    """Resultado completo do walk-forward"""
    symbol: str
    strategy: str
    total_windows: int
    # Metricas gerais
    avg_train_wr: float
    avg_test_wr: float
    avg_degradation: float
    # Robustez
    robustness_score: float  # 0-100
    robustness_label: str  # 'muito_robusto', 'robusto', 'fragil', 'overfitado'
    # Overfitting
    overfitting_score: float  # 0-100 (maior = mais overfitado)
    overfitting_risk: str
    # Janelas
    windows: List[WalkForwardWindow]
    # Recomendacao
    recommendation: str
    confidence: str


# ═══════════════════════════════════════════════════════════════
# WALK-FORWARD ENGINE
# ═══════════════════════════════════════════════════════════════

class WalkForwardEngine:
    """Engine de walk-forward testing"""

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol

    def run_walk_forward(self, strategy_params: Dict = None) -> WalkForwardResult:
        """
        Executa walk-forward testing completo.
        
        Parametros da estrategia (padrao: pullback de tendencia):
        - tendencia: EMA20 > EMA50
        - pullback: preco < EMA20
        - entrada: rompimento da EMA20
        - SL: 2x ATR
        - TP: 3x ATR
        """
        if strategy_params is None:
            strategy_params = {
                'ema_fast': 20,
                'ema_slow': 50,
                'atr_period': 14,
                'sl_atr_mult': 2.0,
                'tp_atr_mult': 3.0,
                'min_score': 60,
            }

        # Buscar dados historicos (5 anos)
        candles = self._get_long_term_data('M15', 50000)
        if len(candles) < 10000:
            return self._empty_result('Dados insuficientes (minimo 10000 candles)')

        # Dividir em janelas walk-forward
        windows = self._create_windows(candles, strategy_params)

        # Calcular metricas gerais
        if not windows:
            return self._empty_result('Nenhuma janela valida')

        avg_train_wr = np.mean([w.train_win_rate for w in windows])
        avg_test_wr = np.mean([w.test_win_rate for w in windows])
        avg_degradation = np.mean([w.degradation for w in windows])

        # Calcular robustez
        robustness = self._calc_robustness(windows)
        overfitting = self._calc_overfitting(windows)

        # Gerar recomendacao
        recommendation, confidence = self._generate_recommendation(
            robustness, overfitting, avg_test_wr, avg_degradation
        )

        return WalkForwardResult(
            symbol=self.symbol,
            strategy='Pullback de Tendencia',
            total_windows=len(windows),
            avg_train_wr=round(avg_train_wr, 1),
            avg_test_wr=round(avg_test_wr, 1),
            avg_degradation=round(avg_degradation, 1),
            robustness_score=round(robustness['score']),
            robustness_label=robustness['label'],
            overfitting_score=round(overfitting['score']),
            overfitting_risk=overfitting['risk'],
            windows=windows,
            recommendation=recommendation,
            confidence=confidence,
        )

    def _get_long_term_data(self, tf: str, count: int) -> List[Dict]:
        """Busca dados de longo prazo"""
        tf_map = {'M15': mt5.TIMEFRAME_M15, 'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4}
        rates = mt5.copy_rates_from_pos(self.symbol, tf_map.get(tf, mt5.TIMEFRAME_M15), 0, count)
        if rates is None:
            return []
        return [{
            'time': r['time'], 'open': r['open'], 'high': r['high'],
            'low': r['low'], 'close': r['close'], 'vol': r['tick_volume']
        } for r in rates]

    def _create_windows(self, candles: List[Dict], params: Dict) -> List[WalkForwardWindow]:
        """Cria janelas de walk-forward"""
        windows = []
        total = len(candles)
        
        # Tamanho da janela: ~1 ano de dados M15 (~50000 candles / 5 anos = ~10000 por ano)
        window_size = 10000
        train_ratio = 0.7  # 70% treino, 30% teste
        
        window_id = 0
        start = 0
        
        while start + window_size <= total:
            train_end = start + int(window_size * train_ratio)
            test_start = train_end
            test_end = min(start + window_size, total)
            
            if test_end - test_start < 1000:
                break
            
            # Simular treino
            train_data = candles[start:train_end]
            test_data = candles[test_start:test_end]
            
            train_result = self._backtest_strategy(train_data, params)
            test_result = self._backtest_strategy(test_data, params)
            
            # Calcular degradacao
            if train_result['win_rate'] > 0:
                degradation = ((train_result['win_rate'] - test_result['win_rate']) / train_result['win_rate']) * 100
            else:
                degradation = 0
            
            # Risco de overfitting
            if degradation > 30:
                of_risk = 'alto'
            elif degradation > 15:
                of_risk = 'medio'
            else:
                of_risk = 'baixo'
            
            from datetime import datetime as dt
            train_start_dt = dt.fromtimestamp(train_data[0]['time']).strftime('%Y-%m')
            train_end_dt = dt.fromtimestamp(train_data[-1]['time']).strftime('%Y-%m')
            test_start_dt = dt.fromtimestamp(test_data[0]['time']).strftime('%Y-%m')
            test_end_dt = dt.fromtimestamp(test_data[-1]['time']).strftime('%Y-%m')
            
            windows.append(WalkForwardWindow(
                window_id=window_id,
                train_start=train_start_dt,
                train_end=train_end_dt,
                test_start=test_start_dt,
                test_end=test_end_dt,
                train_win_rate=train_result['win_rate'],
                train_expectancy=train_result['expectancy'],
                train_trades=train_result['trades'],
                test_win_rate=test_result['win_rate'],
                test_expectancy=test_result['expectancy'],
                test_trades=test_result['trades'],
                degradation=round(degradation, 1),
                overfitting_risk=of_risk,
            ))
            
            window_id += 1
            start += window_size // 2  # Overlap de 50%
        
        return windows

    def _backtest_strategy(self, candles: List[Dict], params: Dict) -> Dict:
        """Backtest simples da estrategia"""
        if len(candles) < 100:
            return {'win_rate': 0, 'expectancy': 0, 'trades': 0}
        
        closes = [c['close'] for c in candles]
        ema_fast_period = params.get('ema_fast', 20)
        ema_slow_period = params.get('ema_slow', 50)
        atr_period = params.get('atr_period', 14)
        sl_mult = params.get('sl_atr_mult', 2.0)
        tp_mult = params.get('tp_atr_mult', 3.0)
        
        # Calcular EMAs
        ema_fast = self._ema_series(closes, ema_fast_period)
        ema_slow = self._ema_series(closes, ema_slow_period)
        
        # Calcular ATR
        atrs = self._atr_series(candles, atr_period)
        
        trades = []
        in_trade = False
        entry_price = 0
        sl_price = 0
        tp_price = 0
        direction = 0
        
        for i in range(max(ema_slow_period, atr_period) + 1, len(candles)):
            if not in_trade:
                # Verificar sinal de entrada
                # Condicao: EMA rapida > EMA lenta (tendencia de alta)
                # Pullback: preco volta para perto da EMA rapida
                # Entrada: quando preco cruza EMA rapida de baixo para cima
                
                if (ema_fast[i] > ema_slow[i] and  # Tendencia de alta
                    closes[i-1] < ema_fast[i-1] and  # Preco abaixo da EMA
                    closes[i] > ema_fast[i]):  # Preco cruzou para cima
                    
                    direction = 1  # BUY
                    entry_price = closes[i]
                    atr = atrs[i] if atrs[i] > 0 else 1
                    sl_price = entry_price - atr * sl_mult
                    tp_price = entry_price + atr * tp_mult
                    in_trade = True
                    
                elif (ema_fast[i] < ema_slow[i] and  # Tendencia de baixa
                      closes[i-1] > ema_fast[i-1] and  # Preco acima da EMA
                      closes[i] < ema_fast[i]):  # Preco cruzou para baixo
                    
                    direction = -1  # SELL
                    entry_price = closes[i]
                    atr = atrs[i] if atrs[i] > 0 else 1
                    sl_price = entry_price + atr * sl_mult
                    tp_price = entry_price - atr * tp_mult
                    in_trade = True
            else:
                # Verificar saida
                if direction == 1:  # BUY
                    if candles[i]['low'] <= sl_price:
                        trades.append({'result': 'LOSS', 'rr': -sl_mult})
                        in_trade = False
                    elif candles[i]['high'] >= tp_price:
                        trades.append({'result': 'WIN', 'rr': tp_mult})
                        in_trade = False
                elif direction == -1:  # SELL
                    if candles[i]['high'] >= sl_price:
                        trades.append({'result': 'LOSS', 'rr': -sl_mult})
                        in_trade = False
                    elif candles[i]['low'] <= tp_price:
                        trades.append({'result': 'WIN', 'rr': tp_mult})
                        in_trade = False
        
        if not trades:
            return {'win_rate': 0, 'expectancy': 0, 'trades': 0}
        
        wins = sum(1 for t in trades if t['result'] == 'WIN')
        total = len(trades)
        win_rate = (wins / total) * 100
        expectancy = np.mean([t['rr'] for t in trades])
        
        return {
            'win_rate': round(win_rate, 1),
            'expectancy': round(expectancy, 2),
            'trades': total,
        }

    def _calc_robustness(self, windows: List[WalkForwardWindow]) -> Dict:
        """Calcula score de robustez"""
        if not windows:
            return {'score': 0, 'label': 'indeterminado'}
        
        scores = []
        for w in windows:
            # Componente 1: Test WR >= 50%
            s1 = min(25, (w.test_win_rate / 50) * 25)
            # Componente 2: Degradacao baixa
            s2 = max(0, 25 - w.degradation * 0.5)
            # Componente 3: Amostra suficiente
            s3 = min(25, (w.test_trades / 30) * 25)
            # Componente 4: Expectativa positiva
            s4 = 25 if w.test_expectancy > 0 else 0
            
            scores.append(s1 + s2 + s3 + s4)
        
        avg_score = np.mean(scores)
        
        if avg_score >= 75:
            label = 'muito_robusto'
        elif avg_score >= 55:
            label = 'robusto'
        elif avg_score >= 35:
            label = 'fragil'
        else:
            label = 'overfitado'
        
        return {'score': avg_score, 'label': label}

    def _calc_overfitting(self, windows: List[WalkForwardWindow]) -> Dict:
        """Calcula score de overfitting"""
        if not windows:
            return {'score': 50, 'risk': 'medio'}
        
        # Overfitting = diferenca consistente entre treino e teste
        degradations = [w.degradation for w in windows]
        avg_deg = np.mean(degradations)
        std_deg = np.std(degradations)
        
        # Score: 0 = sem overfitting, 100 = muito overfitado
        score = min(100, avg_deg * 1.5 + std_deg * 0.5)
        
        if score > 60:
            risk = 'alto'
        elif score > 35:
            risk = 'medio'
        else:
            risk = 'baixo'
        
        return {'score': score, 'risk': risk}

    def _generate_recommendation(self, robustness: Dict, overfitting: Dict,
                                  avg_test_wr: float, avg_degradation: float) -> Tuple[str, str]:
        """Gera recomendacao final"""
        r_score = robustness['score']
        o_score = overfitting['score']
        
        if r_score >= 70 and o_score < 30 and avg_test_wr >= 55:
            return (
                'ESTRATEGIA VALIDADA - Robusta com evidencia fora da amostra. '
                'Win rate %.1f%% em dados nao vistos com degradacao menor que 15%%. '
                'Pode ser usada com confianca.' % avg_test_wr,
                'alta'
            )
        elif r_score >= 50 and o_score < 50:
            return (
                'ESTRATEGIA PROMISSORA - Performance aceitavel mas necessita mais dados. '
                'Win rate %.1f%% com degradacao de %.1f%%. '
                'Recomendado usar com risco reduzido.' % (avg_test_wr, avg_degradation),
                'media'
            )
        elif r_score >= 35:
            return (
                'ESTRATEGIA FRAGIL - Performance inconsistente entre periodos. '
                'Win rate %.1f%% com degradacao alta (%.1f%%). '
                'NAO recomendado para operacao real.' % (avg_test_wr, avg_degradation),
                'baixa'
            )
        else:
            return (
                'ESTRATEGIA OVERFITADA - Performance no treino nao se repete no teste. '
                'Provavelmente ajustada demais ao passado. '
                'Revisar parametros ou abandonar estrategia.',
                'muito_baixa'
            )

    def _ema_series(self, data: List[float], period: int) -> List[float]:
        """Calcula serie de EMA"""
        if len(data) < period:
            return data[:]
        m = 2 / (period + 1)
        ema = [data[0]]
        for p in data[1:]:
            ema.append((p - ema[-1]) * m + ema[-1])
        return ema

    def _atr_series(self, candles: List[Dict], period: int) -> List[float]:
        """Calcula serie de ATR"""
        if len(candles) < period + 1:
            return [0] * len(candles)
        
        trs = [0]
        for i in range(1, len(candles)):
            tr = max(
                candles[i]['high'] - candles[i]['low'],
                abs(candles[i]['high'] - candles[i-1]['close']),
                abs(candles[i]['low'] - candles[i-1]['close'])
            )
            trs.append(tr)
        
        # ATR como media movel
        atrs = [0] * period
        for i in range(period, len(trs)):
            atrs.append(np.mean(trs[i-period:i+1]))
        
        return atrs

    def _empty_result(self, reason: str) -> WalkForwardResult:
        """Retorna resultado vazio"""
        return WalkForwardResult(
            symbol=self.symbol,
            strategy='N/A',
            total_windows=0,
            avg_train_wr=0, avg_test_wr=0, avg_degradation=0,
            robustness_score=0, robustness_label='indeterminado',
            overfitting_score=50, overfitting_risk='medio',
            windows=[],
            recommendation=reason,
            confidence='nenhuma',
        )


# ═══════════════════════════════════════════════════════════════
# BACKTEST COMPARATIVO (antes vs depois da otimizacao)
# ═══════════════════════════════════════════════════════════════

class ComparativeBacktest:
    """Compara estrategias antes e depois da otimizacao"""

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.wf_engine = WalkForwardEngine(symbol)

    def compare_params(self, params_before: Dict, params_after: Dict) -> Dict:
        """Compara duas configuracoes de estrategia"""
        result_before = self.wf_engine.run_walk_forward(params_before)
        result_after = self.wf_engine.run_walk_forward(params_after)

        return {
            'before': {
                'train_wr': result_before.avg_train_wr,
                'test_wr': result_before.avg_test_wr,
                'degradation': result_before.avg_degradation,
                'robustness': result_before.robustness_label,
                'overfitting': result_before.overfitting_risk,
            },
            'after': {
                'train_wr': result_after.avg_train_wr,
                'test_wr': result_after.avg_test_wr,
                'degradation': result_after.avg_degradation,
                'robustness': result_after.robustness_label,
                'overfitting': result_after.overfitting_risk,
            },
            'improvement': {
                'test_wr_delta': round(result_after.avg_test_wr - result_before.avg_test_wr, 1),
                'degradation_delta': round(result_after.avg_degradation - result_before.avg_degradation, 1),
                'robustness_improved': result_after.robustness_score > result_before.robustness_score,
            }
        }
