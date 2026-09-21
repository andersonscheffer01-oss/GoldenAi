#!/usr/bin/env python3
"""
Golden AI - Market Regime + Specialists + Setup Ranking
Cada modo e um especialista que usa o mesmo nucleo com pesos diferentes.

Componentes:
  1. MarketRegimeDetector - Que tipo de mercado temos agora?
  2. Specialist (3 modos) - Price Action, Scalping, Swing
  3. SetupRanking - Ranking de setups por qualidade
  4. TimeFilter - Filtro de horario por setup
"""

import MetaTrader5 as mt5
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import json


# ═══════════════════════════════════════════════════════════════
# 1. MARKET REGIME DETECTOR
# ═══════════════════════════════════════════════════════════════

@dataclass
class MarketRegime:
    """Regime atual do mercado"""
    regime: str  # 'trending', 'ranging', 'volatile', 'uncertain'
    confidence: float  # 0-100
    trend_strength: float  # 0-100
    range_score: float  # 0-100
    volatility_score: float  # 0-100
    description: str
    # Recomendacoes por modo
    price_action_ok: bool
    scalping_ok: bool
    swing_ok: bool
    # Ajustes
    risk_adjustment: float  # 0.5-1.5 (multiplicador de risco)
    size_adjustment: float  # 0.5-1.0 (multiplicador de lote)


class MarketRegimeDetector:
    """Detecta o regime atual do mercado"""

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol

    def detect(self) -> MarketRegime:
        """Detecta o regime do mercado"""
        # Coletar dados de multiplas fontes
        candles_h4 = self._get_candles('H4', 100)
        candles_h1 = self._get_candles('H1', 200)
        candles_m15 = self._get_candles('M15', 200)

        if not candles_h4 or not candles_h1:
            return MarketRegime(
                regime='uncertain', confidence=0, trend_strength=0,
                range_score=0, volatility_score=0,
                description='Dados insuficientes',
                price_action_ok=False, scalping_ok=False, swing_ok=False,
                risk_adjustment=0.5, size_adjustment=0.5
            )

        # 1. Forca da tendencia (ADX + alinhamento de EMAs)
        trend_strength = self._calc_trend_strength(candles_h4, candles_h1)

        # 2. Score de lateralizacao
        range_score = self._calc_range_score(candles_h1, candles_m15)

        # 3. Score de volatilidade
        volatility_score = self._calc_volatility_score(candles_h1)

        # 4. Determinar regime dominante
        regime, confidence = self._determine_regime(trend_strength, range_score, volatility_score)

        # 5. Recomendacoes por modo
        pa_ok, sc_ok, sw_ok = self._recommend_modes(regime, confidence, trend_strength)

        # 6. Ajustes de risco
        risk_adj, size_adj = self._calc_adjustments(regime, volatility_score)

        description = self._describe_regime(regime, trend_strength, range_score, volatility_score)

        return MarketRegime(
            regime=regime,
            confidence=confidence,
            trend_strength=trend_strength,
            range_score=range_score,
            volatility_score=volatility_score,
            description=description,
            price_action_ok=pa_ok,
            scalping_ok=sc_ok,
            swing_ok=sw_ok,
            risk_adjustment=risk_adj,
            size_adjustment=size_adj,
        )

    def _get_candles(self, tf: str, count: int) -> List[Dict]:
        """Busca candles do MT5"""
        tf_map = {
            'M15': mt5.TIMEFRAME_M15, 'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4, 'D1': mt5.TIMEFRAME_D1,
        }
        rates = mt5.copy_rates_from_pos(self.symbol, tf_map.get(tf, mt5.TIMEFRAME_M15), 0, count)
        if rates is None:
            return []
        return [{'time': r['time'], 'open': r['open'], 'high': r['high'],
                 'low': r['low'], 'close': r['close'], 'vol': r['tick_volume']} for r in rates]

    def _calc_trend_strength(self, h4: List[Dict], h1: List[Dict]) -> float:
        """Calcula forca da tendencia (0-100)"""
        if len(h4) < 50 or len(h1) < 50:
            return 30

        # EMAs no H4
        closes_h4 = [c['close'] for c in h4]
        ema20_h4 = self._ema(closes_h4, 20)
        ema50_h4 = self._ema(closes_h4, 50)

        # EMAs no H1
        closes_h1 = [c['close'] for c in h1]
        ema20_h1 = self._ema(closes_h1, 20)
        ema50_h1 = self._ema(closes_h1, 50)

        # ADX simplificado
        adx = self._calc_adx(h1, 14)

        score = 0

        # Alinhamento H4
        if ema20_h4 > ema50_h4:
            score += 25  # Alta
        elif ema20_h4 < ema50_h4:
            score += 25  # Baixa (tendencia forte na baixa conta)

        # Alinhamento H1
        if ema20_h1 > ema50_h1:
            score += 25
        elif ema20_h1 < ema50_h1:
            score += 25

        # Consistencia entre TFs
        if (ema20_h4 > ema50_h4 and ema20_h1 > ema50_h1) or \
           (ema20_h4 < ema50_h4 and ema20_h1 < ema50_h1):
            score += 25  # Alinhados

        # ADX
        if adx > 30:
            score += 25  # Tendencia forte
        elif adx > 20:
            score += 15  # Tendencia moderada
        else:
            score += 5   # Sem tendencia

        return min(100, score)

    def _calc_range_score(self, h1: List[Dict], m15: List[Dict]) -> float:
        """Calcula score de lateralizacao (0-100)"""
        if len(h1) < 50:
            return 30

        closes = [c['close'] for c in h1[-50:]]

        # Media e desvio padrao
        mean = np.mean(closes)
        std = np.std(closes)
        cv = std / mean if mean > 0 else 0  # Coeficiente de variacao

        # Range em relacao ao ATR
        atr = self._calc_atr(h1, 14)
        price_range = max(closes) - min(closes)
        range_atr_ratio = price_range / atr if atr > 0 else 1

        score = 0

        # Baixa variacao = mais lateral
        if cv < 0.001:
            score += 40
        elif cv < 0.003:
            score += 25
        elif cv < 0.005:
            score += 10

        # Range pequeno em relacao ao ATR
        if range_atr_ratio < 2:
            score += 30
        elif range_atr_ratio < 3:
            score += 15

        # Preco voltando para media (mean reversion)
        last_price = closes[-1]
        deviations = [(c - mean) / std if std > 0 else 0 for c in closes[-10:]]
        if all(-1 < d < 1 for d in deviations):
            score += 30  # Preco oscilando proximo a media

        return min(100, score)

    def _calc_volatility_score(self, h1: List[Dict]) -> float:
        """Calcula score de volatilidade (0-100)"""
        if len(h1) < 50:
            return 50

        atr_current = self._calc_atr(h1, 14)
        atr_long = self._calc_atr(h1, 50)

        if atr_long == 0:
            return 50

        ratio = atr_current / atr_long

        # Volatilidade relativa
        if ratio > 2.0:
            return 95  # Extrema
        elif ratio > 1.5:
            return 80  # Alta
        elif ratio > 1.0:
            return 60  # Normal-alta
        elif ratio > 0.7:
            return 40  # Normal
        elif ratio > 0.5:
            return 25  # Baixa
        else:
            return 10  # Muito baixa

    def _determine_regime(self, trend: float, range_s: float, vol: float) -> Tuple[str, float]:
        """Determina o regime dominante"""
        # Tendencia forte
        if trend > 70 and range_s < 40:
            return 'trending', trend

        # Lateralizacao forte
        if range_s > 60 and trend < 50:
            return 'ranging', range_s

        # Volatilidade extrema
        if vol > 85:
            return 'volatile', vol

        # Mercado confuso (tendencia e lateralizacao medio-termo)
        if trend < 50 and range_s < 50:
            return 'uncertain', 100 - (trend + range_s) / 2

        # Default: tender para o que tem mais forca
        if trend >= range_s:
            return 'trending', trend
        else:
            return 'ranging', range_s

    def _recommend_modes(self, regime: str, confidence: float,
                         trend: float) -> Tuple[bool, bool, bool]:
        """Recomenda quais modos usar"""
        if regime == 'trending':
            return True, True, True  # Todos funcionam em tendencia
        elif regime == 'ranging':
            return True, True, False  # Swing evita lateral
        elif regime == 'volatile':
            return True, False, True  # Scalping arriscado em volatilidade alta
        else:  # uncertain
            return False, False, False  # Nao operar

    def _calc_adjustments(self, regime: str, vol: float) -> Tuple[float, float]:
        """Calcula ajustes de risco e tamanho"""
        if regime == 'trending':
            return 1.0, 1.0  # Normal
        elif regime == 'ranging':
            return 0.7, 0.8  # Reduzir risco
        elif regime == 'volatile':
            return 0.5, 0.6  # Reduzir muito
        else:
            return 0.3, 0.5  # Minimo

    def _describe_regime(self, regime: str, trend: float, rng: float, vol: float) -> str:
        """Gera descricao do regime"""
        desc = {
            'trending': 'Tendencia forte (%.0f/100) - Mercado direcional' % trend,
            'ranging': 'Lateralizacao (%.0f/100) - Mercado sideways' % rng,
            'volatile': 'Volatilidade extrema (%.0f/100) - Cuidado' % vol,
            'uncertain': 'Mercado confuso - Sem direcao clara',
        }
        return desc.get(regime, 'Desconhecido')

    def _ema(self, data: List[float], period: int) -> float:
        if len(data) < period:
            return data[-1] if data else 0
        m = 2 / (period + 1)
        e = data[0]
        for p in data[1:]:
            e = (p - e) * m + e
        return e

    def _calc_atr(self, candles: List[Dict], period: int) -> float:
        if len(candles) < period + 1:
            return 1.0
        trs = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i]['high'] - candles[i]['low'],
                abs(candles[i]['high'] - candles[i-1]['close']),
                abs(candles[i]['low'] - candles[i-1]['close'])
            )
            trs.append(tr)
        return np.mean(trs[-period:]) if trs else 1.0

    def _calc_adx(self, candles: List[Dict], period: int) -> float:
        if len(candles) < period * 2:
            return 20
        plus_dm = []
        minus_dm = []
        trs = []
        for i in range(1, len(candles)):
            hd = candles[i]['high'] - candles[i-1]['high']
            ld = candles[i-1]['low'] - candles[i]['low']
            plus_dm.append(hd if hd > ld and hd > 0 else 0)
            minus_dm.append(ld if ld > hd and ld > 0 else 0)
            tr = max(candles[i]['high'] - candles[i]['low'],
                     abs(candles[i]['high'] - candles[i-1]['close']),
                     abs(candles[i]['low'] - candles[i-1]['close']))
            trs.append(tr)
        if len(trs) < period:
            return 20
        atr = np.mean(trs[-period:])
        if atr == 0:
            return 20
        pdi = (np.mean(plus_dm[-period:]) / atr) * 100
        mdi = (np.mean(minus_dm[-period:]) / atr) * 100
        dx = abs(pdi - mdi) / (pdi + mdi + 0.001) * 100
        return dx


# ═══════════════════════════════════════════════════════════════
# 2. SPECIALIST MODES
# ═══════════════════════════════════════════════════════════════

@dataclass
class SpecialistConfig:
    """Configuracao de um especialista"""
    name: str
    mode: str  # 'price_action', 'scalping', 'swing'
    # Timeframes e pesos
    tf_context: str    # TF para contexto
    tf_trend: str      # TF para tendencia
    tf_setup: str      # TF para setup
    tf_entry: str      # TF para entrada
    tf_weights: Dict[str, float]
    # Filtros
    max_spread: int
    min_rr: float
    sl_range: Tuple[int, int]  # min, max pontos
    tp_range: Tuple[int, int]
    max_duration: str
    # Horarios
    preferred_hours: List[int]  # Horas preferidas (0-23)
    # Regime
    preferred_regimes: List[str]


# Configuracoes dos especialistas
# ═══ CONFIGURACOES BASEADAS EM PESQUISA PROFISSIONAL ═══
# Fontes: MetaGold, Ninjatrader, Journalyze, LiteFinance, ACY
# Regra: Mais TFs = mais ruído. Menos TFs = mais foco.
# Princípio: O "cabo" (entry) é o mais importante.

PRICE_ACTION_CONFIG = SpecialistConfig(
    name="Price Action / Day Trade",
    mode="price_action",
    # H1 = estrutura e tendencia (contexto)
    # M15 = setup e padroes (confirmação)
    # M5 = gatilho de entrada (trigger)
    tf_context="H1", tf_trend="H1", tf_setup="M15", tf_entry="M5",
    # Pesos: M5 (entrada) tem MAIS peso que H1 (contexto)
    tf_weights={'H1': 0.25, 'M15': 0.35, 'M5': 0.40},
    max_spread=80, min_rr=2.0,
    sl_range=(300, 800), tp_range=(500, 2000),
    max_duration="Mesmo dia",
    preferred_hours=list(range(8, 22)),  # 08:00-22:00
    preferred_regimes=['trending', 'ranging'],
)

SCALPING_CONFIG = SpecialistConfig(
    name="Scalping",
    mode="scalping",
    # M5 = contexto e estrutura (tendencia curta)
    # M1 = gatilho de entrada (trigger preciso)
    # SEM M15 — scalping não olha timeframe grande!
    tf_context="M5", tf_trend="M5", tf_setup="M5", tf_entry="M1",
    # Pesos: M1 (entrada) tem MAIS peso que M5 (contexto)
    tf_weights={'M5': 0.45, 'M1': 0.55},
    max_spread=30, min_rr=1.5,
    sl_range=(80, 150), tp_range=(80, 250),
    max_duration="5-15 minutos",
    preferred_hours=[8, 9, 10, 11, 14, 15, 16, 20, 21],
    preferred_regimes=['trending'],
)

SWING_CONFIG = SpecialistConfig(
    name="Swing Trade",
    mode="swing",
    # D1 = contexto macro (tendencia principal)
    # H4 = estrutura e zonas importantes
    # H1 = entrada e confirmação
    tf_context="D1", tf_trend="H4", tf_setup="H4", tf_entry="H1",
    # Pesos: H4 (estrutura) tem MAIS peso
    tf_weights={'D1': 0.20, 'H4': 0.40, 'H1': 0.40},
    max_spread=100, min_rr=2.5,
    sl_range=(300, 800), tp_range=(600, 2000),
    max_duration="1-7 dias",
    preferred_hours=list(range(8, 22)),
    preferred_regimes=['trending', 'ranging'],
)


class Specialist:
    """Especialista que analisa com pesos especificos"""

    def __init__(self, config: SpecialistConfig, symbol: str = "XAUUSD"):
        self.config = config
        self.symbol = symbol
        self.regime_detector = MarketRegimeDetector(symbol)

    def analyze(self, full_analysis: Dict) -> Dict:
        """Analise especializada"""
        # 1. Detectar regime
        regime = self.regime_detector.detect()

        # 2. Verificar se o modo e adequado
        if self.config.mode == 'scalping' and not regime.scalping_ok:
            return self._no_trade('Mercado nao favoravel para scalping')
        if self.config.mode == 'swing' and not regime.swing_ok:
            return self._no_trade('Mercado nao favoravel para swing')
        if self.config.mode == 'price_action' and not regime.price_action_ok:
            return self._no_trade('Mercado nao favoravel para price action')

        # 3. Verificar horario
        current_hour = datetime.now().hour
        if current_hour not in self.config.preferred_hours:
            return self._no_trade('Horario nao favoravel (hora atual: %d:00)' % current_hour)

        # 4. Verificar spread
        info = mt5.symbol_info(self.symbol)
        if info and info.spread > self.config.max_spread:
            return self._no_trade('Spread alto (%d > %d)' % (info.spread, self.config.max_spread))

        # 5. Aplicar pesos do especialista na analise
        adapted = self._adapt_analysis(full_analysis, regime)

        # 6. Recalcular score com pesos do especialista
        adapted['score'] = self._calculate_specialist_score(adapted, regime)
        adapted['regime'] = {
            'type': regime.regime,
            'confidence': round(regime.confidence, 1),
            'description': regime.description,
            'risk_adjustment': regime.risk_adjustment,
            'size_adjustment': regime.size_adjustment,
        }

        # 7. Ajustar SL/TP
        adapted = self._adjust_sl_tp(adapted, info)

        return adapted

    def _adapt_analysis(self, analysis: Dict, regime: MarketRegime) -> Dict:
        """Adapta a analise completa para o especialista"""
        adapted = dict(analysis)
        adapted['mode'] = self.config.mode
        adapted['specialist'] = self.config.name
        adapted['preferred_regimes'] = self.config.preferred_regimes
        adapted['max_duration'] = self.config.max_duration
        return adapted

    def _calculate_specialist_score(self, analysis: Dict, regime: MarketRegime) -> float:
        """Calcula score com pesos do especialista"""
        tfs = analysis.get('timeframes', {})
        score = 0

        # Contexto (TF principal)
        ctx_tf = self.config.tf_context
        if ctx_tf in tfs:
            ctx = tfs[ctx_tf]
            w = self.config.tf_weights.get(ctx_tf, 0.25)
            if ctx.get('trend') == 'alta' and analysis.get('direction') == 'BUY':
                score += w * 100
            elif ctx.get('trend') == 'baixa' and analysis.get('direction') == 'SELL':
                score += w * 100

        # Tendencia
        trend_tf = self.config.tf_trend
        if trend_tf in tfs:
            trend = tfs[trend_tf]
            w = self.config.tf_weights.get(trend_tf, 0.25)
            if trend.get('trend') == 'alta' and analysis.get('direction') == 'BUY':
                score += w * 100
            elif trend.get('trend') == 'baixa' and analysis.get('direction') == 'SELL':
                score += w * 100

        # Setup
        setup_tf = self.config.tf_setup
        if setup_tf in tfs:
            setup = tfs[setup_tf]
            w = self.config.tf_weights.get(setup_tf, 0.25)
            if setup.get('pullback') or setup.get('breakout'):
                score += w * 80

        # Entrada
        entry_tf = self.config.tf_entry
        if entry_tf in tfs:
            entry = tfs[entry_tf]
            w = self.config.tf_weights.get(entry_tf, 0.25)
            if entry.get('breakout') and entry.get('breakout_confirmed'):
                score += w * 100
            elif entry.get('pullback'):
                score += w * 60

        # Bonus de regime
        if regime.regime in self.config.preferred_regimes:
            score += 10

        # Penalidade de volatilidade extrema
        if regime.volatility_score > 85:
            score -= 15

        return min(100, max(0, round(score)))

    def _adjust_sl_tp(self, analysis: Dict, info) -> Dict:
        """Ajusta SL/TP para o especialista"""
        if not info:
            return analysis

        direction = analysis.get('direction', 'NONE')
        entry = analysis.get('entry', 0)
        if direction == 'NONE' or entry == 0:
            return analysis

        point = info.point
        digits = info.digits

        # SL/TP baseado no modo
        sl_min, sl_max = self.config.sl_range
        tp_min, tp_max = self.config.tp_range

        # Usar ATR como referencia
        atr = analysis.get('timeframes', {}).get(self.config.tf_setup, {}).get('atr', 0)

        if direction == 'BUY':
            sl = round(entry - max(sl_min * point, atr * 1.5), digits)
            tp = round(entry + max(tp_min * point, atr * 2.5), digits)
        else:
            sl = round(entry + max(sl_min * point, atr * 1.5), digits)
            tp = round(entry - max(tp_min * point, atr * 2.5), digits)

        analysis['stop_loss'] = sl
        analysis['take_profit_1'] = tp
        analysis['risk_reward'] = round(abs(tp - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0

        return analysis

    def _no_trade(self, reason: str) -> Dict:
        """Retorna decisao de nao operar"""
        return {
            'ok': True,
            'direction': 'NONE',
            'mode': self.config.mode,
            'specialist': self.config.name,
            'score': 0,
            'confidence': 'nao_operar',
            'reason': reason,
            'entry': 0,
            'stop_loss': 0,
            'take_profit_1': 0,
            'risk_reward': 0,
            'timeframes': {},
            'statistics': {},
            'market_structure': {},
            'regime': {},
            'symbol': self.symbol,
            'current_price': 0,
            'timestamp': datetime.now().isoformat(),
        }


# ═══════════════════════════════════════════════════════════════
# 3. SETUP RANKING
# ═══════════════════════════════════════════════════════════════

@dataclass
class RankedSetup:
    """Setup rankeado"""
    rank: int
    setup_id: str
    name: str
    direction: str
    score: float
    expectancy: float
    sample_size: int
    win_rate: float
    confidence: str
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    status: str  # 'favoravel', 'aguardar', 'descartado'


class SetupRanker:
    """ rankeia os setups encontrados """

    # Configuracoes de setups pre-definidos
    SETUP_PATTERNS = {
        'pullback_continuacao': {
            'name': 'Pullback + Continuacao',
            'conditions': {'pullback': True, 'breakout': False, 'trend_aligned': True},
        },
        'rompimento_reteste': {
            'name': 'Rompimento + Reteste',
            'conditions': {'pullback': False, 'breakout': True, 'breakout_confirmed': True},
        },
        'rejeicao_regiao': {
            'name': 'Rejeicao de Regiao',
            'conditions': {'pullback': False, 'breakout': False, 'near_sr': True},
        },
        'continuacao_tendencia': {
            'name': 'Continuacao de Tendencia',
            'conditions': {'pullback': False, 'breakout': False, 'trend_aligned': True},
        },
        'reversao_regiao': {
            'name': 'Reversao em Regiao',
            'conditions': {'pullback': False, 'breakout': False, 'near_sr': True, 'trend_aligned': False},
        },
    }

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol

    def rank_setups(self, analysis: Dict, mode: str) -> List[RankedSetup]:
        """Encontra e rankeia todos os setups possiveis"""
        tfs = analysis.get('timeframes', {})
        direction = analysis.get('direction', 'NONE')
        stats = analysis.get('statistics', {})

        ranked = []

        for pattern_id, pattern in self.SETUP_PATTERNS.items():
            # Verificar se as condicoes do setup estao presentes
            match_score = self._match_conditions(pattern, tfs, direction, analysis)

            if match_score > 0:
                # Calcular expectativa historica
                exp = stats.get('expectancy', 0) if stats.get('sufficient_data') else 0
                wr = stats.get('win_rate', 0) if stats.get('sufficient_data') else 0
                samples = stats.get('sample_size', 0)

                # Ajustar score pelo match
                final_score = match_score * analysis.get('score', 50) / 100

                # Determinar status
                if final_score >= 75 and exp > 0.2:
                    status = 'favoravel'
                elif final_score >= 50:
                    status = 'aguardar'
                else:
                    status = 'descartado'

                ranked.append(RankedSetup(
                    rank=0,
                    setup_id=pattern_id,
                    name=pattern['name'],
                    direction=direction,
                    score=round(final_score),
                    expectancy=round(exp, 2),
                    sample_size=samples,
                    win_rate=round(wr, 1),
                    confidence=analysis.get('confidence', 'fraco'),
                    entry=analysis.get('entry', 0),
                    stop_loss=analysis.get('stop_loss', 0),
                    take_profit=analysis.get('take_profit_1', 0),
                    risk_reward=analysis.get('risk_reward', 0),
                    status=status,
                ))

        # Ordenar por score
        ranked.sort(key=lambda x: x.score, reverse=True)

        # Atribuir rank
        for i, s in enumerate(ranked):
            s.rank = i + 1

        return ranked[:5]  # Top 5

    def _match_conditions(self, pattern: Dict, tfs: Dict, direction: str, analysis: Dict) -> float:
        """Verifica quanto um setup corresponde as condicoes"""
        conditions = pattern['conditions']
        score = 0
        total = len(conditions)

        for cond, expected in conditions.items():
            if cond == 'pullback':
                m15 = tfs.get('M15', {})
                if m15.get('pullback') == expected:
                    score += 1
            elif cond == 'breakout':
                m5 = tfs.get('M5', {})
                if m5.get('breakout') == expected:
                    score += 1
            elif cond == 'breakout_confirmed':
                m5 = tfs.get('M5', {})
                if m5.get('breakout_confirmed') == expected:
                    score += 1
            elif cond == 'trend_aligned':
                # Verificar se direction esta alinhada com tendencia
                h1 = tfs.get('H1', {})
                aligned = (direction == 'BUY' and h1.get('trend') == 'alta') or \
                          (direction == 'SELL' and h1.get('trend') == 'baixa')
                if aligned == expected:
                    score += 1
            elif cond == 'near_sr':
                ms = analysis.get('market_structure', {})
                if ms.get('in_demand_zone') or ms.get('in_supply_zone'):
                    score += 1

        return (score / total * 100) if total > 0 else 0


# ═══════════════════════════════════════════════════════════════
# 4. TIME FILTER (Aprende melhores horarios)
# ═══════════════════════════════════════════════════════════════

class TimeFilter:
    """Aprende quais horarios funcionam melhor para cada setup"""

    def __init__(self):
        self.data_file = None  # Será integrado ao Setup Database

    def get_best_hours(self, symbol: str, mode: str, setup_type: str) -> List[int]:
        """Retorna os melhores horarios para um setup"""
        # Por padrao, usar horarios de alta liquidez
        default_hours = {
            'price_action': [8, 9, 10, 11, 14, 15, 16, 20, 21],
            'scalping': [8, 9, 10, 11, 14, 15, 16],
            'swing': list(range(8, 22)),
        }
        return default_hours.get(mode, list(range(8, 22)))

    def should_trade_now(self, symbol: str, mode: str, setup_type: str) -> bool:
        """Verifica se e um bom horario para operar"""
        current_hour = datetime.now().hour
        best = self.get_best_hours(symbol, mode, setup_type)
        return current_hour in best


# ═══════════════════════════════════════════════════════════════
# 5. MASTER ANALYZER (JUNTA TUDO)
# ═══════════════════════════════════════════════════════════════

class MasterAnalyzer:
    """Analise completa com regime + especialistas + ranking"""

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.regime_detector = MarketRegimeDetector(symbol)
        self.ranker = SetupRanker(symbol)
        self.specialists = {
            'price_action': Specialist(PRICE_ACTION_CONFIG, symbol),
            'scalping': Specialist(SCALPING_CONFIG, symbol),
            'swing': Specialist(SWING_CONFIG, symbol),
        }

    def full_analysis(self, base_analysis: Dict, mode: str = 'price_action') -> Dict:
        """Analise completa com especialista"""
        # 1. Detectar regime
        regime = self.regime_detector.detect()

        # 2. Rodar especialista
        specialist = self.specialists.get(mode, self.specialists['price_action'])
        result = specialist.analyze(base_analysis)

        # 3. Rankear setups
        ranked = self.ranker.rank_setups(result, mode)

        # 4. Montar resposta completa
        result['regime'] = {
            'type': regime.regime,
            'confidence': round(regime.confidence, 1),
            'description': regime.description,
            'trend_strength': round(regime.trend_strength, 1),
            'range_score': round(regime.range_score, 1),
            'volatility_score': round(regime.volatility_score, 1),
            'risk_adjustment': regime.risk_adjustment,
            'size_adjustment': regime.size_adjustment,
            'modes': {
                'price_action': 'OK' if regime.price_action_ok else 'EVITAR',
                'scalping': 'OK' if regime.scalping_ok else 'EVITAR',
                'swing': 'OK' if regime.swing_ok else 'EVITAR',
            }
        }

        result['ranked_setups'] = [
            {
                'rank': s.rank,
                'setup_id': s.setup_id,
                'name': s.name,
                'direction': s.direction,
                'score': s.score,
                'expectancy': s.expectancy,
                'sample_size': s.sample_size,
                'win_rate': s.win_rate,
                'status': s.status,
                'entry': s.entry,
                'stop_loss': s.stop_loss,
                'take_profit': s.take_profit,
                'risk_reward': s.risk_reward,
            }
            for s in ranked
        ]

        return result
