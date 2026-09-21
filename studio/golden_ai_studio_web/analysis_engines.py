#!/usr/bin/env python3
"""
Golden AI - Multi-Layer Analysis Engines
Sistema de analise em camadas para decisoes de trading estatisticamente validas.

Camadas:
  1. Motor de Estrutura (OHLCV -> HH/HL/LH/LL, S/R, Liquidez)
  2. Motor Multi-Timeframe (H4->H1->M15->M5)
  3. Motor Estatistico (backtest de setups identicos)
  4. Motor de Scoring (0-100)
  5. IA Raciocinadora (LLM com dados estruturados)
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
class OHLCV:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class StructurePoint:
    """Ponto de estrutura (HH, HL, LH, LL)"""
    time: datetime
    price: float
    point_type: str  # 'HH', 'HL', 'LH', 'LL', 'SWING_HIGH', 'SWING_LOW'
    strength: int  # numero de toques

@dataclass
class SupportResistance:
    """Zona de suporte ou resistencia"""
    price: float
    upper: float
    lower: float
    type: str  # 'support' ou 'resistance'
    touches: int
    strength: float  # 0-100
    last_test: datetime

@dataclass
class LiquidityZone:
    """Zona de liquidez (stops acumulados)"""
    price: float
    type: str  # 'buy_stops' ou 'sell_stops'
    strength: float
    swept: bool

@dataclass
class TimeframeAnalysis:
    """Analise de um timeframe"""
    tf: str
    trend: str  # 'alta', 'baixa', 'lateral'
    trend_strength: float  # 0-100
    structure: str  # 'HH_HL', 'LH_LL', 'lateral'
    pullback: bool
    breakout: bool
    breakout_confirmed: bool
    atr: float
    atr_percentile: float  # percentil do ATR vs historico
    spread_points: float
    ema_fast: float
    ema_slow: float
    ema_trend: float
    rsi: float
    adx: float
    distance_to_support: float
    distance_to_resistance: float
    near_liquidity: bool
    candle_pattern: str

@dataclass
class MarketStructure:
    """Estrutura completa do mercado"""
    symbol: str
    current_price: float
    bid: float
    ask: float
    spread: float
    # Tendencias por timeframe
    h4_trend: str
    h1_trend: str
    m15_trend: str
    m5_trend: str
    # Alinhamento
    trend_alignment: float  # 0-100 (todos TFs concordam?)
    # Estrutura
    structure_type: str  # 'trending_up', 'trending_down', 'ranging', 'volatile'
    # Suporte/Resistencia
    nearest_support: float
    nearest_resistance: float
    distance_to_support_pct: float
    distance_to_resistance_pct: float
    # Liquidez
    liquidity_above: List[LiquidityZone]
    liquidity_below: List[LiquidityZone]
    # Volatilidade
    atr_h1: float
    atr_m15: float
    atr_percentile: float  # 0-100
    volatility_regime: str  # 'low', 'normal', 'high', 'extreme'
    # Zonas
    in_demand_zone: bool
    in_supply_zone: bool
    demand_zone_price: float
    supply_zone_price: float
    # Score bruto
    raw_score: float  # 0-100

@dataclass
class TradeSetup:
    """Setup de trade identificado"""
    direction: str  # 'BUY', 'SELL', 'NONE'
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward: float
    score: float  # 0-100
    confidence: str  # 'fraco', 'moderado', 'forte', 'excepcional'
    reasons: List[str]
    timeframes: Dict[str, TimeframeAnalysis]
    structure: MarketStructure
    # Estatisticas
    historical_win_rate: float
    historical_expectancy: float
    sample_size: int


# ═══════════════════════════════════════════════════════════════
# MOTOR 1: ESTRUTURA DO MERCADO
# ═══════════════════════════════════════════════════════════════

class StructureEngine:
    """Analise de estrutura: HH/HL/LH/LL, Suporte/Resistencia, Liquidez"""

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.point = mt5.symbol_info(symbol).point if mt5.symbol_info(symbol) else 0.01

    def get_ohlcv(self, tf: str, count: int = 200) -> List[OHLCV]:
        """Busca dados OHLCV do MT5"""
        tf_map = {
            'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15, 'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
        }
        rates = mt5.copy_rates_from_pos(self.symbol, tf_map.get(tf, mt5.TIMEFRAME_M15), 0, count)
        if rates is None or len(rates) == 0:
            return []

        candles = []
        for r in rates:
            candles.append(OHLCV(
                time=datetime.fromtimestamp(r['time']),
                open=r['open'], high=r['high'], low=r['low'],
                close=r['close'], volume=r['tick_volume']
            ))
        return candles

    def find_swing_points(self, candles: List[OHLCV], left: int = 5, right: int = 5) -> List[StructurePoint]:
        """Identifica pontos de inflexao (swing highs/lows)"""
        points = []
        if len(candles) < left + right + 1:
            return points

        for i in range(left, len(candles) - right):
            # Swing High
            is_high = True
            for j in range(i - left, i + right + 1):
                if j != i and candles[j].high >= candles[i].high:
                    is_high = False
                    break
            if is_high:
                points.append(StructurePoint(
                    time=candles[i].time, price=candles[i].high,
                    point_type='SWING_HIGH', strength=1
                ))

            # Swing Low
            is_low = True
            for j in range(i - left, i + right + 1):
                if j != i and candles[j].low <= candles[i].low:
                    is_low = False
                    break
            if is_low:
                points.append(StructurePoint(
                    time=candles[i].time, price=candles[i].low,
                    point_type='SWING_LOW', strength=1
                ))

        return points

    def classify_structure(self, points: List[StructurePoint]) -> str:
        """Classifica estrutura: HH_HL, LH_LL, ou lateral"""
        if len(points) < 4:
            return 'lateral'

        # Pegar ultimos 4 pontos
        recent = points[-4:]
        highs = [p for p in recent if 'HIGH' in p.point_type]
        lows = [p for p in recent if 'LOW' in p.point_type]

        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1].price > highs[-2].price
            hl = lows[-1].price > lows[-2].price
            lh = highs[-1].price < highs[-2].price
            ll = lows[-1].price < lows[-2].price

            if hh and hl:
                return 'HH_HL'  # Tendencia de alta
            elif lh and ll:
                return 'LH_LL'  # Tendencia de baixa

        return 'lateral'

    def find_support_resistance(self, candles: List[OHLCV], sensitivity: int = 10) -> List[SupportResistance]:
        """Identifica niveis de suporte e resistencia"""
        zones = []
        if len(candles) < sensitivity * 2:
            return zones

        # Usar metade dos dados para encontrar niveis
        half = len(candles) // 2
        lookback = candles[:half]
        validation = candles[half:]

        # Encontrar niveis no lookback
        price_counts = {}
        for c in lookback:
            # Arredondar para nivel mais proximo (10 pontos)
            level = round(c.high / (self.point * 100)) * (self.point * 100)
            price_counts[level] = price_counts.get(level, 0) + 1
            level = round(c.low / (self.point * 100)) * (self.point * 100)
            price_counts[level] = price_counts.get(level, 0) + 1

        # Filtrar niveis com mais toques
        for price, touches in sorted(price_counts.items(), key=lambda x: -x[1]):
            if touches >= 3:
                # Validar no periodo de validacao
                valid_touches = 0
                for c in validation:
                    if abs(c.high - price) < self.point * 50 or abs(c.low - price) < self.point * 50:
                        valid_touches += 1

                if valid_touches >= 1:
                    is_support = price < candles[-1].close
                    zones.append(SupportResistance(
                        price=price,
                        upper=price + self.point * 30,
                        lower=price - self.point * 30,
                        type='support' if is_support else 'resistance',
                        touches=touches + valid_touches,
                        strength=min(100, (touches + valid_touches) * 15),
                        last_test=candles[-1].time
                    ))

            if len(zones) >= 10:
                break

        return zones

    def find_liquidity_zones(self, candles: List[OHLCV]) -> List[LiquidityZone]:
        """Identifica zonas de liquidez (stops acumulados)"""
        zones = []
        if len(candles) < 20:
            return zones

        # Procurar por swing highs/lows onde stops se acumulam
        points = self.find_swing_points(candles, left=3, right=3)

        for p in points:
            if p.point_type == 'SWING_HIGH':
                # Buy stops acima deste high
                zones.append(LiquidityZone(
                    price=p.price + self.point * 10,
                    type='buy_stops',
                    strength=min(100, p.strength * 25),
                    swept=False
                ))
            elif p.point_type == 'SWING_LOW':
                # Sell stops abaixo deste low
                zones.append(LiquidityZone(
                    price=p.price - self.point * 10,
                    type='sell_stops',
                    strength=min(100, p.strength * 25),
                    swept=False
                ))

        # Verificar se alguma zona ja foi varrida
        current_price = candles[-1].close
        for z in zones:
            if z.type == 'buy_stops' and current_price > z.price:
                z.swept = True
            elif z.type == 'sell_stops' and current_price < z.price:
                z.swept = True

        return zones

    def calculate_atr(self, candles: List[OHLCV], period: int = 14) -> float:
        """Calcula ATR"""
        if len(candles) < period + 1:
            return 0.0

        trs = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i-1].close),
                abs(candles[i].low - candles[i-1].close)
            )
            trs.append(tr)

        return np.mean(trs[-period:])

    def atr_percentile(self, candles: List[OHLCV], period: int = 14) -> float:
        """Percentil do ATR atual vs historico"""
        if len(candles) < period * 3:
            return 50.0

        current_atr = self.calculate_atr(candles, period)
        historical_atrs = []

        for i in range(period * 2, len(candles)):
            atr = self.calculate_atr(candles[i-period:i+1], period)
            historical_atrs.append(atr)

        if not historical_atrs:
            return 50.0

        below = sum(1 for a in historical_atrs if a < current_atr)
        return (below / len(historical_atrs)) * 100

    def detect_candle_pattern(self, candles: List[OHLCV]) -> str:
        """Detecta padroes de candle"""
        if len(candles) < 3:
            return 'none'

        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        body1 = abs(c1.close - c1.open)
        body2 = abs(c2.close - c2.open)
        body3 = abs(c3.close - c3.open)
        range1 = c1.high - c1.low
        range2 = c2.high - c2.low
        range3 = c3.high - c3.low

        if range3 == 0:
            return 'none'

        # Engolfo de alta
        if c2.close < c2.open and c3.close > c3.open:
            if c3.close > c2.open and c3.open < c2.close:
                return 'engolfo_compra'

        # Engolfo de baixa
        if c2.close > c2.open and c3.close < c3.open:
            if c3.close < c2.open and c3.open > c2.close:
                return 'engolfo_venda'

        # Martelo
        lower_wick = min(c3.open, c3.close) - c3.low
        upper_wick = c3.high - max(c3.open, c3.close)
        if lower_wick > body3 * 2 and upper_wick < body3 * 0.5:
            return 'martelo'

        # Estrela cadente
        if upper_wick > body3 * 2 and lower_wick < body3 * 0.5:
            return 'estrela_cadente'

        # Doji
        if body3 < range3 * 0.1:
            return 'doji'

        return 'none'


# ═══════════════════════════════════════════════════════════════
# MOTOR 2: MULTI-TIMEFRAME
# ═══════════════════════════════════════════════════════════════

class MultiTimeframeEngine:
    """Analise multi-timeframe adaptativa por modo"""

    # Timeframes padrao (Price Action)
    TIMEFRAMES = ['H1', 'M15', 'M5']
    TF_WEIGHTS = {'H1': 0.25, 'M15': 0.35, 'M5': 0.40}

    # Configuracoes por modo
    MODE_CONFIG = {
        'price_action': {
            'timeframes': ['H1', 'M15', 'M5'],
            'weights': {'H1': 0.25, 'M15': 0.35, 'M5': 0.40},
        },
        'scalping': {
            'timeframes': ['M5', 'M1'],
            'weights': {'M5': 0.45, 'M1': 0.55},
        },
        'swing': {
            'timeframes': ['D1', 'H4', 'H1'],
            'weights': {'D1': 0.20, 'H4': 0.40, 'H1': 0.40},
        },
    }

    def __init__(self, symbol: str = "XAUUSD", mode: str = "price_action"):
        self.symbol = symbol
        self.mode = mode
        self.structure_engine = StructureEngine(symbol)
        # Aplicar configuracao do modo
        config = self.MODE_CONFIG.get(mode, self.MODE_CONFIG['price_action'])
        self.TIMEFRAMES = config['timeframes']
        self.TF_WEIGHTS = config['weights']

    def calculate_ema(self, closes: List[float], period: int) -> float:
        """Calcula EMA"""
        if len(closes) < period:
            return closes[-1] if closes else 0.0
        multiplier = 2 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        """Calcula RSI"""
        if len(closes) < period + 1:
            return 50.0

        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def calculate_adx(self, candles: List[OHLCV], period: int = 14) -> float:
        """Calcula ADX simplificado"""
        if len(candles) < period * 2:
            return 20.0

        plus_dm = []
        minus_dm = []
        trs = []

        for i in range(1, len(candles)):
            high_diff = candles[i].high - candles[i-1].high
            low_diff = candles[i-1].low - candles[i].low

            plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
            minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)

            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i-1].close),
                abs(candles[i].low - candles[i-1].close)
            )
            trs.append(tr)

        if len(trs) < period:
            return 20.0

        atr = np.mean(trs[-period:])
        if atr == 0:
            return 20.0

        plus_di = (np.mean(plus_dm[-period:]) / atr) * 100
        minus_di = (np.mean(minus_dm[-period:]) / atr) * 100

        dx = abs(plus_di - minus_di) / (plus_di + minus_di + 0.001) * 100
        return dx

    def analyze_timeframe(self, tf: str) -> TimeframeAnalysis:
        """Analisa um timeframe especifico"""
        candles = self.structure_engine.get_ohlcv(tf, 200)
        if not candles:
            return TimeframeAnalysis(
                tf=tf, trend='lateral', trend_strength=0, structure='lateral',
                pullback=False, breakout=False, breakout_confirmed=False,
                atr=0, atr_percentile=50, spread_points=0,
                ema_fast=0, ema_slow=0, ema_trend=0, rsi=50, adx=20,
                distance_to_support=0, distance_to_resistance=0,
                near_liquidity=False, candle_pattern='none'
            )

        closes = [c.close for c in candles]
        current = closes[-1]

        # EMAs
        ema_fast = self.calculate_ema(closes, 20)
        ema_slow = self.calculate_ema(closes, 50)
        ema_trend = self.calculate_ema(closes, 200) if len(closes) >= 200 else ema_slow

        # Tendencia
        if ema_fast > ema_slow > ema_trend:
            trend = 'alta'
            trend_strength = min(100, ((ema_fast - ema_slow) / ema_slow * 10000) * 10)
        elif ema_fast < ema_slow < ema_trend:
            trend = 'baixa'
            trend_strength = min(100, ((ema_slow - ema_fast) / ema_slow * 10000) * 10)
        else:
            trend = 'lateral'
            trend_strength = 30

        # Estrutura
        points = self.structure_engine.find_swing_points(candles)
        structure = self.structure_engine.classify_structure(points)

        # Pullback
        pullback = False
        if trend == 'alta' and current < ema_fast:
            pullback = True
        elif trend == 'baixa' and current > ema_fast:
            pullback = True

        # Breakout
        breakout = False
        breakout_confirmed = False
        if len(candles) >= 5:
            recent_high = max(c.high for c in candles[-20:])
            recent_low = min(c.low for c in candles[-20:])
            if current > recent_high * 0.999:
                breakout = True
                breakout_confirmed = candles[-1].close > candles[-1].open  # vela de confirmação
            elif current < recent_low * 1.001:
                breakout = True
                breakout_confirmed = candles[-1].close < candles[-1].open

        # ATR
        atr = self.structure_engine.calculate_atr(candles)
        atr_pct = self.structure_engine.atr_percentile(candles)

        # RSI e ADX
        rsi = self.calculate_rsi(closes)
        adx = self.calculate_adx(candles)

        # Suporte/Resistencia
        sr = self.structure_engine.find_support_resistance(candles)
        nearest_sup = max([s.price for s in sr if s.type == 'support'], default=current - 1000)
        nearest_res = min([s.price for s in sr if s.type == 'resistance'], default=current + 1000)

        # Liquidez
        liq = self.structure_engine.find_liquidity_zones(candles)
        near_liquidity = any(
            abs(z.price - current) < atr * 0.5
            for z in liq if not z.swept
        )

        # Padrao de candle
        pattern = self.structure_engine.detect_candle_pattern(candles)

        # Spread
        info = mt5.symbol_info(self.symbol)
        spread = info.spread if info else 0

        return TimeframeAnalysis(
            tf=tf,
            trend=trend,
            trend_strength=trend_strength,
            structure=structure,
            pullback=pullback,
            breakout=breakout,
            breakout_confirmed=breakout_confirmed,
            atr=atr,
            atr_percentile=atr_pct,
            spread_points=spread,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            ema_trend=ema_trend,
            rsi=rsi,
            adx=adx,
            distance_to_support=current - nearest_sup,
            distance_to_resistance=nearest_res - current,
            near_liquidity=near_liquidity,
            candle_pattern=pattern
        )

    def analyze_all(self) -> Dict[str, TimeframeAnalysis]:
        """Analisa todos os timeframes"""
        results = {}
        for tf in self.TIMEFRAMES:
            results[tf] = self.analyze_timeframe(tf)
        return results

    def calculate_alignment(self, analyses: Dict[str, TimeframeAnalysis]) -> float:
        """Calcula alinhamento entre timeframes (0-100)"""
        if not analyses:
            return 0

        trend_scores = []
        for tf, weight in self.TF_WEIGHTS.items():
            if tf in analyses:
                a = analyses[tf]
                if a.trend == 'alta':
                    trend_scores.append(weight * 100)
                elif a.trend == 'baixa':
                    trend_scores.append(weight * 0)
                else:
                    trend_scores.append(weight * 50)

        return sum(trend_scores) / sum(self.TF_WEIGHTS.values()) if trend_scores else 50


# ═══════════════════════════════════════════════════════════════
# MOTOR 3: ESTATISTICO (BACKTEST DE SETUPS)
# ═══════════════════════════════════════════════════════════════

class StatisticalEngine:
    """Busca setups identicos no historico e calcula expectancia"""

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.structure_engine = StructureEngine(symbol)

    def search_historical_setups(self, direction: str, trend_h4: str, trend_h1: str,
                                  has_pullback: bool, has_breakout: bool,
                                  atr_percentile: float, min_sample: int = 30) -> Dict:
        """Busca setups identicos no historico"""
        # Buscar 1000 candles de M15 para encontrar padroes
        candles = self.structure_engine.get_ohlcv('M15', 1000)
        if len(candles) < 200:
            return {
                'win_rate': 0, 'sample_size': 0, 'expectancy': 0,
                'tp1_rate': 0, 'tp2_rate': 0, 'stop_rate': 0,
                'sufficient_data': False
            }

        # Simular encontrar setups similares
        matching_setups = []
        closes = [c.close for c in candles]
        ema20 = self._calc_ema_series(closes, 20)
        ema50 = self._calc_ema_series(closes, 50)

        for i in range(200, len(candles) - 50):
            # Verificar se as condicoes sao similares
            setup_match = True

            # Tendencia similar
            if trend_h4 == 'alta' and ema20[i] < ema50[i]:
                setup_match = False
            elif trend_h4 == 'baixa' and ema20[i] > ema50[i]:
                setup_match = False

            # Pullback similar
            if has_pullback and closes[i] > ema20[i]:
                setup_match = False
            elif not has_pullback and closes[i] < ema20[i] * 0.999:
                setup_match = False

            if setup_match:
                # Simular resultado: quanto moveu nos proximos 50 candles
                entry = closes[i]
                max_move_up = max(closes[i+1:i+51]) - entry
                max_move_down = entry - min(closes[i+1:i+51])

                # SL = 2x ATR, TP = 3x ATR (simulacao)
                atr = self.structure_engine.calculate_atr(candles[i-14:i+1])
                sl_distance = atr * 2
                tp_distance = atr * 3

                if direction == 'BUY':
                    hit_tp = max_move_up >= tp_distance
                    hit_sl = max_move_down >= sl_distance
                else:
                    hit_tp = max_move_down >= tp_distance
                    hit_sl = max_move_up >= sl_distance

                matching_setups.append({
                    'hit_tp': hit_tp,
                    'hit_sl': hit_sl,
                    'max_favorable': max_move_up if direction == 'BUY' else max_move_down,
                    'max_adverse': max_move_down if direction == 'BUY' else max_move_up,
                })

        # Calcular estatisticas
        total = len(matching_setups)
        if total < min_sample:
            return {
                'win_rate': 0, 'sample_size': total, 'expectancy': 0,
                'tp1_rate': 0, 'tp2_rate': 0, 'stop_rate': 0,
                'sufficient_data': False
            }

        wins = sum(1 for s in matching_setups if s['hit_tp'])
        losses = sum(1 for s in matching_setups if s['hit_sl'])
        breakeven = total - wins - losses

        win_rate = (wins / total) * 100
        loss_rate = (losses / total) * 100

        # Expectancia em R
        avg_win = np.mean([s['max_favorable'] for s in matching_setups if s['hit_tp']]) if wins else 0
        avg_loss = np.mean([s['max_adverse'] for s in matching_setups if s['hit_sl']]) if losses else 1
        expectancy = (win_rate/100 * avg_win/avg_loss) - (loss_rate/100) if avg_loss > 0 else 0

        return {
            'win_rate': round(win_rate, 1),
            'sample_size': total,
            'expectancy': round(expectancy, 2),
            'tp1_rate': round(win_rate * 0.85, 1),  # Estimativa
            'tp2_rate': round(win_rate * 0.65, 1),
            'stop_rate': round(loss_rate, 1),
            'sufficient_data': True,
            'avg_win_points': round(avg_win / 0.01, 0) if avg_win else 0,
            'avg_loss_points': round(avg_loss / 0.01, 0) if avg_loss else 0,
        }

    def _calc_ema_series(self, data: List[float], period: int) -> List[float]:
        """Calcula serie de EMA"""
        if len(data) < period:
            return data[:]
        multiplier = 2 / (period + 1)
        ema = [data[0]]
        for price in data[1:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        return ema


# ═══════════════════════════════════════════════════════════════
# MOTOR 4: SCORING (0-100)
# ═══════════════════════════════════════════════════════════════

class ScoringEngine:
    """Calcula score de confianca 0-100"""

    WEIGHTS = {
        'trend_h4': 15,
        'trend_h1': 15,
        'trend_m15': 15,
        'structure_m5': 15,
        'liquidity': 10,
        'volatility': 10,
        'risk_reward': 10,
        'backtest': 10,
    }

    def calculate_score(self, mtf_analyses: Dict[str, TimeframeAnalysis],
                        structure: MarketStructure,
                        stats: Dict,
                        direction: str) -> Tuple[float, str, List[str]]:
        """Calcula score e retorna (score, confidence_label, reasons)"""

        score = 0
        reasons = []

        # 1. Tendencia H4 (15 pts)
        h4 = mtf_analyses.get('H4')
        if h4:
            if (direction == 'BUY' and h4.trend == 'alta') or \
               (direction == 'SELL' and h4.trend == 'baixa'):
                pts = min(15, h4.trend_strength * 0.15)
                score += pts
                reasons.append(f"H4 tendencia {h4.trend}: +{pts:.0f}/15")
            else:
                reasons.append(f"H4 tendencia {h4.trend} CONTRA: +0/15")

        # 2. Tendencia H1 (15 pts)
        h1 = mtf_analyses.get('H1')
        if h1:
            if (direction == 'BUY' and h1.trend == 'alta') or \
               (direction == 'SELL' and h1.trend == 'baixa'):
                pts = min(15, h1.trend_strength * 0.15)
                score += pts
                reasons.append(f"H1 tendencia {h1.trend}: +{pts:.0f}/15")
            else:
                reasons.append(f"H1 tendencia {h1.trend} CONTRA: +0/15")

        # 3. Tendencia M15 (15 pts)
        m15 = mtf_analyses.get('M15')
        if m15:
            if (direction == 'BUY' and m15.trend == 'alta') or \
               (direction == 'SELL' and m15.trend == 'baixa'):
                pts = min(15, m15.trend_strength * 0.15)
                score += pts
                reasons.append(f"M15 tendencia {m15.trend}: +{pts:.0f}/15")

        # 4. Estrutura M5 (15 pts)
        m5 = mtf_analyses.get('M5')
        if m5:
            if m5.breakout and m5.breakout_confirmed:
                score += 15
                reasons.append("M5 breakout confirmado: +15/15")
            elif m5.pullback:
                score += 10
                reasons.append("M5 pullback detectado: +10/15")
            else:
                reasons.append("M5 sem sinal claro: +0/15")

        # 5. Liquidez (10 pts)
        has_liquidity = (len(structure.liquidity_above) > 0 or len(structure.liquidity_below) > 0)
        if has_liquidity:
            score += 5
            reasons.append("Zonas de liquidez proximas: +5/10")

        # 6. Volatilidade (10 pts)
        if 30 <= structure.atr_percentile <= 70:
            score += 10
            reasons.append(f"Volatilidade adequada (ATR {structure.atr_percentile:.0f}%): +10/10")
        elif structure.atr_percentile > 85:
            score += 3
            reasons.append(f"Volatilidade alta demais (ATR {structure.atr_percentile:.0f}%): +3/10")
        else:
            score += 5
            reasons.append(f"Volatilidade baixa (ATR {structure.atr_percentile:.0f}%): +5/10")

        # 7. Risco/Retorno (10 pts)
        if structure.current_price:
            if direction == 'BUY':
                risk = structure.distance_to_support_pct if structure.distance_to_support_pct > 0 else 0.5
                reward = structure.distance_to_resistance_pct if structure.distance_to_resistance_pct > 0 else 0.5
            else:
                risk = structure.distance_to_resistance_pct if structure.distance_to_resistance_pct > 0 else 0.5
                reward = structure.distance_to_support_pct if structure.distance_to_support_pct > 0 else 0.5

            rr = reward / risk if risk > 0 else 0
            if rr >= 2:
                score += 10
                reasons.append(f"R/R excelente ({rr:.1f}): +10/10")
            elif rr >= 1.5:
                score += 7
                reasons.append(f"R/R bom ({rr:.1f}): +7/10")
            elif rr >= 1:
                score += 4
                reasons.append(f"R/R adequado ({rr:.1f}): +4/10")
            else:
                reasons.append(f"R/R ruim ({rr:.1f}): +0/10")

        # 8. Backtest (10 pts)
        if stats.get('sufficient_data'):
            wr = stats['win_rate']
            exp = stats['expectancy']
            if wr >= 60 and exp > 0.3:
                score += 10
                reasons.append(f"Backtest forte (WR {wr}%, EV {exp}R): +10/10")
            elif wr >= 55 and exp > 0:
                score += 7
                reasons.append(f"Backtest bom (WR {wr}%, EV {exp}R): +7/10")
            elif wr >= 50:
                score += 4
                reasons.append(f"Backtest medio (WR {wr}%, EV {exp}R): +4/10")
            else:
                reasons.append(f"Backtest fraco (WR {wr}%, EV {exp}R): +0/10")
        else:
            reasons.append("Backtest sem dados suficientes: +0/10")

        # Classificar confianca
        if score >= 85:
            confidence = 'excepcional'
        elif score >= 75:
            confidence = 'forte'
        elif score >= 65:
            confidence = 'moderado'
        elif score >= 50:
            confidence = 'fraco'
        else:
            confidence = 'nao_operar'

        return score, confidence, reasons


# ═══════════════════════════════════════════════════════════════
# MOTOR 5: ANALISADOR COMPLETO (JUNTA TUDO)
# ═══════════════════════════════════════════════════════════════

class FullAnalyzer:
    """Analise completa em camadas"""

    def __init__(self, symbol: str = "XAUUSD", mode: str = "price_action"):
        self.symbol = symbol
        self.mode = mode
        self.structure_engine = StructureEngine(symbol)
        self.mtf_engine = MultiTimeframeEngine(symbol, mode)
        self.stat_engine = StatisticalEngine(symbol)
        self.scoring_engine = ScoringEngine()

    def analyze(self, mode: str = None) -> Dict:
        """Analise completa do mercado"""
        # 1. Coletar dados
        info = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        if not info or not tick:
            return {'ok': False, 'error': 'MT5 nao disponivel'}

        current_price = (tick.bid + tick.ask) / 2

        # 2. Analise multi-timeframe
        mtf = self.mtf_engine.analyze_all()
        alignment = self.mtf_engine.calculate_alignment(mtf)

        # 3. Identificar direcao
        buy_score = 0
        sell_score = 0

        for tf_name, weight in MultiTimeframeEngine.TF_WEIGHTS.items():
            if tf_name in mtf:
                a = mtf[tf_name]
                if a.trend == 'alta':
                    buy_score += weight * 100
                elif a.trend == 'baixa':
                    sell_score += weight * 100

        # 4. Montar estrutura de mercado
        sr = self.structure_engine.find_support_resistance(
            self.structure_engine.get_ohlcv('H1', 200)
        )
        nearest_sup = max([s.price for s in sr if s.type == 'support'], default=current_price - 100)
        nearest_res = min([s.price for s in sr if s.type == 'resistance'], default=current_price + 100)

        liq = self.structure_engine.find_liquidity_zones(
            self.structure_engine.get_ohlcv('M15', 100)
        )

        atr_h1 = self.structure_engine.calculate_atr(
            self.structure_engine.get_ohlcv('H1', 100)
        )
        atr_m15 = self.structure_engine.calculate_atr(
            self.structure_engine.get_ohlcv('M15', 100)
        )
        atr_pct = self.structure_engine.atr_percentile(
            self.structure_engine.get_ohlcv('H1', 200)
        )

        # Volatilidade
        if atr_pct > 85:
            vol_regime = 'extreme'
        elif atr_pct > 70:
            vol_regime = 'high'
        elif atr_pct > 30:
            vol_regime = 'normal'
        else:
            vol_regime = 'low'

        structure = MarketStructure(
            symbol=self.symbol,
            current_price=current_price,
            bid=tick.bid,
            ask=tick.ask,
            spread=info.spread,
            h4_trend=mtf.get('H4', TimeframeAnalysis(tf='H4', trend='lateral', trend_strength=0, structure='lateral', pullback=False, breakout=False, breakout_confirmed=False, atr=0, atr_percentile=50, spread_points=0, ema_fast=0, ema_slow=0, ema_trend=0, rsi=50, adx=20, distance_to_support=0, distance_to_resistance=0, near_liquidity=False, candle_pattern='none')).trend,
            h1_trend=mtf.get('H1', TimeframeAnalysis(tf='H1', trend='lateral', trend_strength=0, structure='lateral', pullback=False, breakout=False, breakout_confirmed=False, atr=0, atr_percentile=50, spread_points=0, ema_fast=0, ema_slow=0, ema_trend=0, rsi=50, adx=20, distance_to_support=0, distance_to_resistance=0, near_liquidity=False, candle_pattern='none')).trend,
            m15_trend=mtf.get('M15', TimeframeAnalysis(tf='M15', trend='lateral', trend_strength=0, structure='lateral', pullback=False, breakout=False, breakout_confirmed=False, atr=0, atr_percentile=50, spread_points=0, ema_fast=0, ema_slow=0, ema_trend=0, rsi=50, adx=20, distance_to_support=0, distance_to_resistance=0, near_liquidity=False, candle_pattern='none')).trend,
            m5_trend=mtf.get('M5', TimeframeAnalysis(tf='M5', trend='lateral', trend_strength=0, structure='lateral', pullback=False, breakout=False, breakout_confirmed=False, atr=0, atr_percentile=50, spread_points=0, ema_fast=0, ema_slow=0, ema_trend=0, rsi=50, adx=20, distance_to_support=0, distance_to_resistance=0, near_liquidity=False, candle_pattern='none')).trend,
            trend_alignment=alignment,
            structure_type='trending_up' if buy_score > sell_score * 1.3 else 'trending_down' if sell_score > buy_score * 1.3 else 'ranging',
            nearest_support=nearest_sup,
            nearest_resistance=nearest_res,
            distance_to_support_pct=((current_price - nearest_sup) / current_price * 100) if current_price > 0 else 0,
            distance_to_resistance_pct=((nearest_res - current_price) / current_price * 100) if current_price > 0 else 0,
            liquidity_above=[z for z in liq if z.price > current_price and not z.swept],
            liquidity_below=[z for z in liq if z.price < current_price and not z.swept],
            atr_h1=atr_h1,
            atr_m15=atr_m15,
            atr_percentile=atr_pct,
            volatility_regime=vol_regime,
            in_demand_zone=current_price <= nearest_sup * 1.002,
            in_supply_zone=current_price >= nearest_res * 0.998,
            demand_zone_price=nearest_sup if current_price <= nearest_sup * 1.002 else 0,
            supply_zone_price=nearest_res if current_price >= nearest_res * 0.998 else 0,
            raw_score=0
        )

        # 5. Determinar direcao
        direction = 'BUY' if buy_score > sell_score * 1.2 else 'SELL' if sell_score > buy_score * 1.2 else 'NONE'

        # 6. Estatisticas
        stats = {'win_rate': 0, 'sample_size': 0, 'expectancy': 0, 'sufficient_data': False}
        if direction != 'NONE':
            stats = self.stat_engine.search_historical_setups(
                direction=direction,
                trend_h4=structure.h4_trend,
                trend_h1=structure.h1_trend,
                has_pullback=mtf.get('M15', TimeframeAnalysis(tf='M15', trend='lateral', trend_strength=0, structure='lateral', pullback=False, breakout=False, breakout_confirmed=False, atr=0, atr_percentile=50, spread_points=0, ema_fast=0, ema_slow=0, ema_trend=0, rsi=50, adx=20, distance_to_support=0, distance_to_resistance=0, near_liquidity=False, candle_pattern='none')).pullback,
                has_breakout=mtf.get('M5', TimeframeAnalysis(tf='M5', trend='lateral', trend_strength=0, structure='lateral', pullback=False, breakout=False, breakout_confirmed=False, atr=0, atr_percentile=50, spread_points=0, ema_fast=0, ema_slow=0, ema_trend=0, rsi=50, adx=20, distance_to_support=0, distance_to_resistance=0, near_liquidity=False, candle_pattern='none')).breakout,
                atr_percentile=atr_pct
            )

        # 7. Score
        score, confidence, reasons = self.scoring_engine.calculate_score(
            mtf, structure, stats, direction
        )
        structure.raw_score = score

        # 8. Calcular entrada/SL/TP
        entry = current_price
        if direction == 'BUY':
            sl = nearest_sup - atr_m15 * 0.5
            tp1 = entry + atr_m15 * 1.5
            tp2 = entry + atr_m15 * 2.5
            tp3 = entry + atr_m15 * 3.5
        elif direction == 'SELL':
            sl = nearest_res + atr_m15 * 0.5
            tp1 = entry - atr_m15 * 1.5
            tp2 = entry - atr_m15 * 2.5
            tp3 = entry - atr_m15 * 3.5
        else:
            sl = 0
            tp1 = tp2 = tp3 = 0

        risk = abs(entry - sl) if sl else 1
        reward = abs(tp1 - entry) if tp1 else 0
        rr = reward / risk if risk > 0 else 0

        return {
            'ok': True,
            'direction': direction,
            'entry': round(entry, info.digits),
            'stop_loss': round(sl, info.digits),
            'take_profit_1': round(tp1, info.digits),
            'take_profit_2': round(tp2, info.digits),
            'take_profit_3': round(tp3, info.digits),
            'risk_reward': round(rr, 2),
            'score': score,
            'confidence': confidence,
            'reasons': reasons,
            'timeframes': {tf: {
                'trend': a.trend,
                'strength': round(a.trend_strength, 1),
                'structure': a.structure,
                'pullback': a.pullback,
                'breakout': a.breakout,
                'rsi': round(a.rsi, 1),
                'adx': round(a.adx, 1),
                'atr': round(a.atr, 2),
                'candle_pattern': a.candle_pattern,
            } for tf, a in mtf.items()},
            'statistics': stats,
            'market_structure': {
                'alignment': round(alignment, 1),
                'type': structure.structure_type,
                'volatility': structure.volatility_regime,
                'atr_percentile': round(atr_pct, 1),
                'nearest_support': structure.nearest_support,
                'nearest_resistance': structure.nearest_resistance,
                'liquidity_above': len(structure.liquidity_above),
                'liquidity_below': len(structure.liquidity_below),
                'in_demand_zone': structure.in_demand_zone,
                'in_supply_zone': structure.in_supply_zone,
            },
            'symbol': self.symbol,
            'current_price': current_price,
            'timestamp': datetime.now().isoformat(),
        }

    def _log_to_journal(self, result: Dict, ai_response: str = '', ai_model: str = ''):
        """Registra analise no Trade Journal"""
        try:
            from trade_journal import journal, setup_db
            setup_id = journal.log_analysis(result, ai_response, ai_model)
            setup_db.save_setup(result)
            result['setup_id'] = setup_id
            print("[JOURNAL] Setup registrado: %s" % setup_id)
        except Exception as e:
            print("[JOURNAL] Erro ao registrar: %s" % e)

# ═══════════════════════════════════════════════════════════════
# CONSTRUIR PROMPT PARA IA RACIOCINADORA
# ═══════════════════════════════════════════════════════════════

def build_structured_prompt(analysis: Dict) -> str:
    """Construi prompt com dados estruturados para a IA raciocinar"""

    direction = analysis.get('direction', 'NONE')
    score = analysis.get('score', 0)
    confidence = analysis.get('confidence', 'nao_operar')

    tf_text = ""
    for tf, data in analysis.get('timeframes', {}).items():
        tf_text += f"""
{tf}:
  Tendencia: {data['trend'].upper()} (forca {data['strength']})
  Estrutura: {data['structure']}
  Pullback: {'SIM' if data['pullback'] else 'NAO'}
  Breakout: {'SIM' if data['breakout'] else 'NAO'}
  RSI: {data['rsi']}
  ADX: {data['adx']}
  ATR: {data['atr']}
  Padrao candle: {data['candle_pattern']}"""

    stats = analysis.get('statistics', {})
    stats_text = ""
    if stats.get('sufficient_data'):
        stats_text = f"""
HISTORICO ({stats['sample_size']} ocorrencias similares):
  Win Rate: {stats['win_rate']}%
  Expectancia: {stats['expectancy']}R
  Stop Rate: {stats['stop_rate']}%"""

    reasons_text = "\n".join(f"  - {r}" for r in analysis.get('reasons', []))

    prompt = f"""Voce e um analista profissional. Analise estes dados OBJETIVOS e decida.

=== DADOS DO MERCADO ===
Ativo: {analysis.get('symbol', 'XAUUSD')}
Preco atual: {analysis.get('current_price', 0)}
Direcao identificada: {direction}
Score: {score}/100 ({confidence})

=== TIMEFRAMES ===
{tf_text}

=== ESTRUTURA ===
Alinhamento: {analysis.get('market_structure', {}).get('alignment', 0)}%
Tipo: {analysis.get('market_structure', {}).get('type', 'N/A')}
Volatilidade: {analysis.get('market_structure', {}).get('volatility', 'N/A')} (percentil {analysis.get('market_structure', {}).get('atr_percentile', 0)})
Suporte: {analysis.get('market_structure', {}).get('nearest_support', 0)}
Resistencia: {analysis.get('market_structure', {}).get('nearest_resistance', 0)}
Zona de demanda: {'SIM' if analysis.get('market_structure', {}).get('in_demand_zone') else 'NAO'}
Zona de oferta: {'SIM' if analysis.get('market_structure', {}).get('in_supply_zone') else 'NAO'}
Liquidez acima: {analysis.get('market_structure', {}).get('liquidity_above', 0)} zonas
Liquidez abaixo: {analysis.get('market_structure', {}).get('liquidity_below', 0)} zonas
{stats_text}

=== PONTUACAO ===
{reasons_text}

=== INSTRUCAO ===
Com base em TODOS os dados acima, responda em JSON:
{{
  "direcao": "BUY" ou "SELL" ou "NONE",
  "entrada": preco,
  "stop_loss": preco,
  "take_profit_1": preco,
  "take_profit_2": preco,
  "take_profit_3": preco,
  "rr_ratio": numero,
  "confianca": 1-10,
  "motivo": "explicacao",
  "tempo_estimado": "XX min",
  "alertas": ["risco1", "risco2"]
}}

REGRAS:
- Se score < 50, responda NONE
- Se sinais conflitantes, responda NONE
- Se volatilidade extrema, responda NONE
- Seja CONSERVADOR: melhor perder oportunidade que dinheiro
- NAO invente precos - use os dados fornecidos"""

    return prompt
