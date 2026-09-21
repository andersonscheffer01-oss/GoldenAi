#!/usr/bin/env python3
"""
Golden Scanner v3 — Motor Real de Analise de Mercado

Arquitetura:
  SCALP (M1-M5, segundos a minutos) — 22 setups
  DAY TRADE (M5-H1, minutos a horas) — 15 setups
  SWING (H1-W1, dias a semanas) — 10 setups
  TOTAL: 47 setups com IDs unicos

Scoring 7 fatores:
  Setup Quality 30% | Regime 15% | Structure 15% | Location 15%
  Momentum 10% | Risk Quality 10% | Session 5%

Novidades v3:
  - Normalizacao por ATR em todas as distancias
  - Strategy Manager ON/OFF
  - Signal deduplication (evitar entradas duplicadas)
  - Correlation filter (nao abrir pares correlacionados)
  - Kill switch (daily loss limit, consecutive loss)
  - Regime engine expandido (7 regimes)
  - Score calibrado com expectancy
"""

import MetaTrader5 as mt5
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

# ═══════════════════════════════════════════════════════════════
# SETUP DEFINITIONS — 47 Setups com IDs unicos
# ═══════════════════════════════════════════════════════════════

SETUP_DEFINITIONS = {
    # ═══ SCALP (22) — M1/M5 — segundos a poucos minutos ═══
    'SCALP_BRK_RETEST': {
        'name': 'Breakout + Reteste', 'mode': 'scalp', 'tier': 'A',
        'description': 'Rompimento de zona com reteste e confirmacao',
        'timeframes': ['M5', 'M1'], 'conditions': ['breakout_confirmed', 'retest_zone', 'candle_reversal'],
        'tf_weights': {'M5': 0.6, 'M1': 0.4}, 'best_regime': ['trending'], 'best_hours': [8,9,10,14,15,16], 'min_rr': 1.5,
    },
    'SCALP_PULLBACK_EMA': {
        'name': 'Pullback EMA20', 'mode': 'scalp', 'tier': 'A',
        'description': 'Pullback ate EMA20 com continuacao',
        'timeframes': ['M5', 'M1'], 'conditions': ['ema_pullback', 'trend_aligned', 'rejection_candle'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5}, 'best_regime': ['trending'], 'best_hours': [8,9,10,14,15], 'min_rr': 1.5,
    },
    'SCALP_LIQ_SWEEP': {
        'name': 'Liquidity Sweep', 'mode': 'scalp', 'tier': 'A',
        'description': 'Varredura de stops com reversao rapida',
        'timeframes': ['M5', 'M1'], 'conditions': ['sweep_detected', 'reversal_candle', 'displacement'],
        'tf_weights': {'M5': 0.4, 'M1': 0.6}, 'best_regime': ['trending','ranging'], 'best_hours': [8,9,14,15,20], 'min_rr': 2.0,
    },
    'SCALP_FALSE_BREAK': {
        'name': 'Falso Rompimento', 'mode': 'scalp', 'tier': 'B',
        'description': 'Rompimento que falha com pin bar',
        'timeframes': ['M5', 'M1'], 'conditions': ['false_break_wick', 'structure_level', 'reversal_confirm'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5}, 'best_regime': ['ranging'], 'best_hours': [9,10,14,15], 'min_rr': 2.0,
    },
    'SCALP_VWAP_FADE': {
        'name': 'VWAP Fade', 'mode': 'scalp', 'tier': 'C',
        'description': 'Fade apos extensao exagerada da VWAP. So com exaustao.',
        'timeframes': ['M5', 'M1'], 'conditions': ['vwap_extended', 'rsi_extreme', 'momentum_fading'],
        'tf_weights': {'M5': 0.6, 'M1': 0.4}, 'best_regime': ['ranging'], 'best_hours': [9,10,14,15], 'min_rr': 1.5,
    },
    'SCALP_VWAP_PULLBACK': {
        'name': 'VWAP Pullback', 'mode': 'scalp', 'tier': 'A',
        'description': 'Tendencia + pullback VWAP + volume diminui + candle retomada',
        'timeframes': ['M5', 'M1'], 'conditions': ['vwap_trend_aligned', 'pullback_to_vwap', 'volume_decreasing_pullback', 'reversal_candle'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5}, 'best_regime': ['trending'], 'best_hours': [8,9,10,14,15,16], 'min_rr': 1.5,
    },
    'SCALP_VWAP_RECLAIM': {
        'name': 'VWAP Reclaim/Flip', 'mode': 'scalp', 'tier': 'B',
        'description': 'Preco perde VWAP e recupera. Cruzamento+fech+reteste+defesa.',
        'timeframes': ['M5', 'M1'], 'conditions': ['vwap_cross_decisive', 'close_beyond_vwap', 'retest_and_hold', 'structure_confirm'],
        'tf_weights': {'M5': 0.4, 'M1': 0.6}, 'best_regime': ['trending','ranging'], 'best_hours': [8,9,10,14,15], 'min_rr': 1.5,
    },
    'SCALP_ORB': {
        'name': 'Opening Range Breakout', 'mode': 'scalp', 'tier': 'A',
        'description': 'Rompimento da range dos primeiros 15-30 min',
        'timeframes': ['M5', 'M1'], 'conditions': ['opening_range_defined', 'breakout_volume', 'follow_through'],
        'tf_weights': {'M5': 0.7, 'M1': 0.3}, 'best_regime': ['trending'], 'best_hours': [8,9,14,15], 'min_rr': 1.5,
    },
    'SCALP_MICRO_PULL': {
        'name': 'Micro Pullback', 'mode': 'scalp', 'tier': 'C',
        'description': 'Pullback micro em trend forte M1',
        'timeframes': ['M1'], 'conditions': ['strong_trend_m1', 'micro_pullback_ema', 'engulfing_pattern'],
        'tf_weights': {'M1': 1.0}, 'best_regime': ['trending'], 'best_hours': [8,9,10,14,15,16], 'min_rr': 1.2,
    },
    'SCALP_SQUEEZE': {
        'name': 'Squeeze Breakout', 'mode': 'scalp', 'tier': 'A',
        'description': 'Saida de compressao de Bollinger Bands',
        'timeframes': ['M5', 'M1'], 'conditions': ['bb_squeeze', 'expansion_start', 'directional_candle'],
        'tf_weights': {'M5': 0.6, 'M1': 0.4}, 'best_regime': ['ranging'], 'best_hours': [8,9,14,15], 'min_rr': 2.0,
    },
    'SCALP_MEAN_RETURN': {
        'name': 'Retorno a Media', 'mode': 'scalp', 'tier': 'C',
        'description': 'Preco esticado retorna para EMA50',
        'timeframes': ['M5', 'M1'], 'conditions': ['extended_from_ema', 'momentum_weakening', 'rsi_divergence'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5}, 'best_regime': ['ranging'], 'best_hours': [9,10,14,15], 'min_rr': 1.5,
    },
    'SCALP_MOMENTUM_BURST': {
        'name': 'Momentum Burst', 'mode': 'scalp', 'tier': 'B',
        'description': 'Explosao de momentum com volume',
        'timeframes': ['M5', 'M1'], 'conditions': ['momentum_spike', 'volume_surge', 'price_displacement'],
        'tf_weights': {'M5': 0.3, 'M1': 0.7}, 'best_regime': ['trending'], 'best_hours': [8,9,10,14,15,16], 'min_rr': 1.5,
    },
    'SCALP_SESSION_HL': {
        'name': 'Session H/L Rejection', 'mode': 'scalp', 'tier': 'B',
        'description': 'Rejeicao no high/low da sessao',
        'timeframes': ['M5', 'M1'], 'conditions': ['session_extreme', 'rejection_wick', 'volume_at_extreme'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5}, 'best_regime': ['ranging','trending'], 'best_hours': [10,11,15,16,20], 'min_rr': 2.0,
    },
    'SCALP_OB_ENTRY': {
        'name': 'Order Block Scalp', 'mode': 'scalp', 'tier': 'B',
        'description': 'Entrada em order block M5 com confirmacao M1',
        'timeframes': ['M5', 'M1'], 'conditions': ['order_block_detected', 'displacement_before_ob', 'reaction_at_ob'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5}, 'best_regime': ['trending'], 'best_hours': [8,9,14,15], 'min_rr': 2.0,
    },
    'SCALP_MULTI_INDI': {
        'name': 'Multi-Indicador (EMA+RSI+BB)', 'mode': 'scalp', 'tier': 'A',
        'description': 'Scalping com EMA(9/20), RSI(14), BB(20,2) e VWMA',
        'timeframes': ['M5', 'M1'], 'conditions': ['ema_trend_aligned', 'rsi_momentum_zone', 'bb_midband_close', 'vwma_direction_aligned'],
        'tf_weights': {'M5': 0.4, 'M1': 0.6}, 'best_regime': ['trending'], 'best_hours': list(range(8,12))+list(range(13,18)), 'min_rr': 2.5,
    },
    'SCALP_MR_REVERSAL': {
        'name': 'Reversao de Momentum', 'mode': 'scalp', 'tier': 'B',
        'description': 'RSI extremo + BB + Estocastico. R:R 1:2',
        'timeframes': ['M5', 'M1'], 'conditions': ['rsi_extreme_reversal', 'bb_extreme_penetration', 'stoch_extreme'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5}, 'best_regime': ['ranging'], 'best_hours': [13,14,15,16,17], 'min_rr': 1.5,
    },
    'SCALP_BREAKOUT_BANDIT': {
        'name': 'Breakout Bandit', 'mode': 'scalp', 'tier': 'A',
        'description': 'Rompimento apos compressao BB + ADX>25 + volume',
        'timeframes': ['M5', 'M1'], 'conditions': ['bb_squeeze_detect', 'adx_strong_trend', 'bb_breakout_confirmed', 'volume_above_avg'],
        'tf_weights': {'M5': 0.6, 'M1': 0.4}, 'best_regime': ['trending'], 'best_hours': [8,9,10,14,15,16], 'min_rr': 2.0,
    },
    'SCALP_MA_CROSS': {
        'name': 'Cross Rapido EMA(5/10/20)', 'mode': 'scalp', 'tier': 'C',
        'description': 'Cruzamento EMA(5) x EMA(10) + alinhamento EMA(20)',
        'timeframes': ['M5', 'M1'], 'conditions': ['ema_cross_fast', 'ema_alignment', 'ema_slope_strong'],
        'tf_weights': {'M5': 0.3, 'M1': 0.7}, 'best_regime': ['trending'], 'best_hours': [8,9,10,14,15,16], 'min_rr': 1.5,
    },
    'SCALP_PA_SNIPER': {
        'name': 'Price Action Sniper', 'mode': 'scalp', 'tier': 'A',
        'description': 'Engulfing + proximidade S/R + volume + ATR elevado',
        'timeframes': ['M5', 'M1'], 'conditions': ['engulfing_pattern', 'near_sr_level', 'volume_spike', 'atr_elevated'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5}, 'best_regime': ['trending','ranging'], 'best_hours': list(range(8,22)), 'min_rr': 1.5,
    },
    'SCALP_VWAP_REAL': {
        'name': 'VWAP Real Bands 2s', 'mode': 'scalp', 'tier': 'A',
        'description': 'Entrada na VWAP real com bandas 2s',
        'timeframes': ['M5', 'M1'], 'conditions': ['vwap_real_detected', 'price_at_vwap_band', 'rsi_confirm_vwap', 'candle_reversal'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5}, 'best_regime': ['trending','ranging'], 'best_hours': [8,9,10,14,15,16], 'min_rr': 1.5,
    },
    'SCALP_MACD_DIV': {
        'name': 'MACD Divergence', 'mode': 'scalp', 'tier': 'B',
        'description': 'Divergencia preco vs MACD histogram',
        'timeframes': ['M5', 'M1'], 'conditions': ['macd_divergence_bull', 'price_near_support', 'candle_reversal'],
        'tf_weights': {'M5': 0.6, 'M1': 0.4}, 'best_regime': ['ranging','trending'], 'best_hours': [8,9,10,14,15], 'min_rr': 2.0,
    },
    'SCALP_GAP_FILL': {
        'name': 'Gap Fill', 'mode': 'scalp', 'tier': 'C',
        'description': 'Gap de abertura que tende a ser preenchido',
        'timeframes': ['M5', 'M1'], 'conditions': ['gap_detected', 'gap_filling', 'momentum_fading'],
        'tf_weights': {'M5': 0.6, 'M1': 0.4}, 'best_regime': ['ranging'], 'best_hours': [8,14,15,20], 'min_rr': 1.5,
    },
    # ═══ DAY TRADE (15) — M5/H1 — minutos a horas ═══
    'DAY_PULLBACK_DO': {
        'name': 'Pullback Demanda/Oferta', 'mode': 'day', 'tier': 'A',
        'description': 'Pullback em zona de demanda/oferta',
        'timeframes': ['M15', 'M5', 'H1'], 'conditions': ['zone_identified', 'pullback_to_zone', 'rejection_candle', 'trend_aligned'],
        'tf_weights': {'H1': 0.2, 'M15': 0.5, 'M5': 0.3}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
    },
    'DAY_FALSE_BREAK': {
        'name': 'Falso Rompimento + Reversao', 'mode': 'day', 'tier': 'A',
        'description': 'Falso rompimento de S/R com pin bar',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['sr_level_proximity', 'false_break_wick', 'reversal_pattern', 'volume_spike'],
        'tf_weights': {'H1': 0.4, 'M15': 0.35, 'M5': 0.25}, 'best_regime': ['ranging'], 'best_hours': list(range(8,22)), 'min_rr': 2.5,
    },
    'DAY_CONTINUATION': {
        'name': 'Continuacao de Tendencia', 'mode': 'day', 'tier': 'A',
        'description': 'Continuacao apos consolidacao na tendencia',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['strong_trend', 'consolidation_detected', 'breakout_directional'],
        'tf_weights': {'H1': 0.35, 'M15': 0.4, 'M5': 0.25}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 1.5,
    },
    'DAY_BOS': {
        'name': 'Break of Structure (BOS)', 'mode': 'day', 'tier': 'A',
        'description': 'Quebra de estrutura com reteste',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['bos_detected', 'retest_ob_zone', 'continuation_candle'],
        'tf_weights': {'H1': 0.35, 'M15': 0.4, 'M5': 0.25}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
    },
    'DAY_CHOCH': {
        'name': 'Change of Character (CHoCH)', 'mode': 'day', 'tier': 'A',
        'description': 'Mudanca de carater = reversao',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['choch_detected', 'structure_shift', 'entry_after_retest'],
        'tf_weights': {'H1': 0.4, 'M15': 0.35, 'M5': 0.25}, 'best_regime': ['ranging','trending'], 'best_hours': list(range(8,22)), 'min_rr': 2.5,
    },
    'DAY_FVG_FILL': {
        'name': 'Fair Value Gap Fill', 'mode': 'day', 'tier': 'A',
        'description': 'Preco retorna para FVG com reacao',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['fvg_detected', 'price_returning_to_fvg', 'reaction_at_fvg'],
        'tf_weights': {'H1': 0.3, 'M15': 0.45, 'M5': 0.25}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
    },
    'DAY_LIQ_GRAB': {
        'name': 'Liquidity Grab + Reversao', 'mode': 'day', 'tier': 'B',
        'description': 'Captura de liquidez + reversao estrutural',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['liquidity_sweep_htf', 'reversal_pattern', 'bos_after_sweep'],
        'tf_weights': {'H1': 0.4, 'M15': 0.35, 'M5': 0.25}, 'best_regime': ['trending','ranging'], 'best_hours': list(range(8,22)), 'min_rr': 2.5,
    },
    'DAY_SR_REJECTION': {
        'name': 'Rejeicao S/R Forte', 'mode': 'day', 'tier': 'A',
        'description': 'Pin bar em S/R multi-toque',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['sr_multi_touch', 'pin_bar_rejection', 'divergence'],
        'tf_weights': {'H1': 0.4, 'M15': 0.35, 'M5': 0.25}, 'best_regime': ['ranging'], 'best_hours': list(range(8,22)), 'min_rr': 2.5,
    },
    'DAY_COMPRESSION': {
        'name': 'Compressao -> Breakout', 'mode': 'day', 'tier': 'B',
        'description': 'Saida de range apertado',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['tight_range', 'volume_buildup', 'breakout_candle'],
        'tf_weights': {'H1': 0.3, 'M15': 0.4, 'M5': 0.3}, 'best_regime': ['ranging'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
    },
    'DAY_OB_ENTRY': {
        'name': 'Order Block Entry', 'mode': 'day', 'tier': 'A',
        'description': 'Entrada no OB com displacement',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['ob_identified', 'displacement_into_ob', 'rejection_at_ob', 'bos_confirmation'],
        'tf_weights': {'H1': 0.35, 'M15': 0.4, 'M5': 0.25}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 2.5,
    },
    'DAY_SMT': {
        'name': 'SMT Divergence', 'mode': 'day', 'tier': 'B',
        'description': 'Divergencia entre pares correlacionados',
        'timeframes': ['H1', 'M15'], 'conditions': ['correlated_pair_divergence', 'structure_shift', 'entry_trigger'],
        'tf_weights': {'H1': 0.5, 'M15': 0.5}, 'best_regime': ['trending','ranging'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
    },
    'DAY_KILL_ZONE': {
        'name': 'Kill Zone Entry', 'mode': 'day', 'tier': 'B',
        'description': 'Entrada em horarios de alta liquidez',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['kill_zone_active', 'liquidity_grab', 'smart_money_entry'],
        'tf_weights': {'H1': 0.3, 'M15': 0.4, 'M5': 0.3}, 'best_regime': ['trending'], 'best_hours': [8,9,13,14,15,20], 'min_rr': 2.0,
    },
    'DAY_DISCOUNT_PREM': {
        'name': 'Discount/Premium Zone', 'mode': 'day', 'tier': 'B',
        'description': 'Entrada em zona desconto/premium do range',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['swing_range_defined', 'price_in_discount', 'reversal_candle'],
        'tf_weights': {'H1': 0.4, 'M15': 0.35, 'M5': 0.25}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
    },
    'DAY_ICHIMOKU': {
        'name': 'Ichimoku Cloud Breakout', 'mode': 'day', 'tier': 'B',
        'description': 'Rompimento nuvem Ichimoku com TK cross',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['ichimoku_cloud_break', 'tk_cross_confirm', 'price_above_below_cloud'],
        'tf_weights': {'H1': 0.4, 'M15': 0.35, 'M5': 0.25}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
    },
    'DAY_TRIANGLE': {
        'name': 'Triangle Breakout', 'mode': 'day', 'tier': 'B',
        'description': 'Rompimento triangulo + volume',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['triangle_detected', 'breakout_directional', 'volume_confirm'],
        'tf_weights': {'H1': 0.3, 'M15': 0.4, 'M5': 0.3}, 'best_regime': ['ranging','trending'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
    },
    # ═══ SWING (10) — H1/W1 — dias a semanas ═══
    'SWING_FIB': {
        'name': 'Fibonacci Retracement', 'mode': 'swing', 'tier': 'A',
        'description': 'Retracao zona 38.2-61.8% com confluencia',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['fib_level_proximity', 'trend_strong', 'rejection_candle_htf'],
        'tf_weights': {'D1': 0.3, 'H4': 0.4, 'H1': 0.3}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
    },
    'SWING_STRUCT_BREAK': {
        'name': 'Breakout Estrutura Diaria', 'mode': 'swing', 'tier': 'A',
        'description': 'Rompimento estrutura D1 com follow-through',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['daily_structure_broken', 'close_above', 'volume_confirm'],
        'tf_weights': {'D1': 0.5, 'H4': 0.3, 'H1': 0.2}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
    },
    'SWING_MACRO_REV': {
        'name': 'Reversao Macro S/R', 'mode': 'swing', 'tier': 'A',
        'description': 'Reversao zona macro multi-semanal',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['macro_sr_zone', 'reversal_pattern_htf', 'volume_at_zone'],
        'tf_weights': {'D1': 0.4, 'H4': 0.4, 'H1': 0.2}, 'best_regime': ['ranging'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
    },
    'SWING_CONSOLIDATION': {
        'name': 'Saida Consolidacao Prolongada', 'mode': 'swing', 'tier': 'B',
        'description': 'Rompimento apos consolidacao de dias',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['multi_day_consolidation', 'range_narrowing', 'breakout_with_volume'],
        'tf_weights': {'D1': 0.4, 'H4': 0.35, 'H1': 0.25}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
    },
    'SWING_MA_CROSS': {
        'name': 'MA Crossover HTF', 'mode': 'swing', 'tier': 'B',
        'description': 'Cruzamento EMA50/200 em D1/H4',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['ma_cross_signal', 'trend_strength', 'pullback_entry'],
        'tf_weights': {'D1': 0.4, 'H4': 0.4, 'H1': 0.2}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 2.5,
    },
    'SWING_SR_RETEST': {
        'name': 'Reteste S/R HTF', 'mode': 'swing', 'tier': 'A',
        'description': 'Reteste zona S/R importante D1/H4',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['major_sr_level', 'retest_confirm', 'candle_reaction'],
        'tf_weights': {'D1': 0.4, 'H4': 0.35, 'H1': 0.25}, 'best_regime': ['trending','ranging'], 'best_hours': list(range(8,22)), 'min_rr': 2.5,
    },
    'SWING_VOL_EXPANSION': {
        'name': 'Expansao Volatilidade HTF', 'mode': 'swing', 'tier': 'B',
        'description': 'Squeeze BB em D1/H4 com expansao',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['bb_squeeze_htf', 'expansion_starting', 'directional_candle'],
        'tf_weights': {'D1': 0.5, 'H4': 0.3, 'H1': 0.2}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
    },
    'SWING_TREND_REV': {
        'name': 'Reversao Tendencia D1', 'mode': 'swing', 'tier': 'B',
        'description': 'Mudanca tendencia D1 com CHoCH',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['daily_choch', 'ema_cross_htf', 'volume_divergence'],
        'tf_weights': {'D1': 0.5, 'H4': 0.3, 'H1': 0.2}, 'best_regime': ['ranging'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
    },
    'SWING_OB_HTF': {
        'name': 'Order Block D1/H4', 'mode': 'swing', 'tier': 'A',
        'description': 'Entrada em OB de timeframe alto',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['ob_htf_identified', 'price_returning', 'rejection_reaction'],
        'tf_weights': {'D1': 0.35, 'H4': 0.4, 'H1': 0.25}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
    },
    'SWING_INST_FLOW': {
        'name': 'Fluxo Institucional', 'mode': 'swing', 'tier': 'B',
        'description': 'Acumulacao/distribuicao institucional',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['volume_accumulation', 'price_range_tight', 'impending_breakout'],
        'tf_weights': {'D1': 0.4, 'H4': 0.35, 'H1': 0.25}, 'best_regime': ['ranging','trending'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
    },
    # ═══ NOVAS ESTRATEGIAS — adicionadas ao Radar com filtro de ativo ═══
    'SWING_TURTLE_BREAKOUT': {
        'name': 'Turtle Breakout', 'mode': 'swing', 'tier': 'A',
        'description': 'Rompimento de maxima/minima de periodo com volume e tendencia persistente',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['turtle_breakout', 'volume_confirm', 'trend_strong'],
        'tf_weights': {'D1': 0.45, 'H4': 0.35, 'H1': 0.20}, 'best_regime': ['trending'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
        'allowed_symbols': ['XAUUSD','EURUSD','GBPUSD','USDJPY','GER40','US30','US500','BTCUSD'],
    },
    'SWING_DARVAS_BOX': {
        'name': 'Darvas Box', 'mode': 'swing', 'tier': 'A',
        'description': 'Rompimento de caixa de acumulacao confirmado por volume',
        'timeframes': ['D1', 'H4', 'H1'], 'conditions': ['darvas_box', 'volume_confirm', 'breakout_directional'],
        'tf_weights': {'D1': 0.45, 'H4': 0.35, 'H1': 0.20}, 'best_regime': ['compression','trending'], 'best_hours': list(range(8,22)), 'min_rr': 3.0,
        'allowed_symbols': ['XAUUSD','EURUSD','GBPUSD','USDJPY','GER40','US30','US500','BTCUSD'],
    },
    'DAY_CA_C1': {
        'name': 'CA + C1', 'mode': 'day', 'tier': 'A',
        'description': 'Caixa de abertura e rompimento do candle 1 com volume',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['ca_range_defined', 'c1_breakout', 'volume_confirm'],
        'tf_weights': {'H1': 0.25, 'M15': 0.45, 'M5': 0.30}, 'best_regime': ['trending','compression'], 'best_hours': [8,9,10,13,14,15], 'min_rr': 2.0,
        'allowed_symbols': ['XAUUSD','GER40','US30','US500'],
    },
    'DAY_VOLUME_PROFILE_REJECTION': {
        'name': 'Volume Profile Rejection', 'mode': 'day', 'tier': 'A',
        'description': 'Rejeicao em regiao de alto volume com candle de confirmacao',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['volume_node_rejection', 'rejection_candle', 'volume_at_zone'],
        'tf_weights': {'H1': 0.35, 'M15': 0.40, 'M5': 0.25}, 'best_regime': ['ranging','transition'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
        'allowed_symbols': ['XAUUSD','EURUSD','GBPUSD','USDJPY','GER40','US30','US500','BTCUSD'],
    },
    'DAY_VWAP_ANCHORED': {
        'name': 'VWAP Ancorada', 'mode': 'day', 'tier': 'A',
        'description': 'Preco justo ancorado no impulso ou noticia com reteste e volume',
        'timeframes': ['H1', 'M15', 'M5'], 'conditions': ['anchored_vwap_aligned', 'anchored_vwap_retest', 'volume_confirm'],
        'tf_weights': {'H1': 0.30, 'M15': 0.45, 'M5': 0.25}, 'best_regime': ['trending','ranging','transition'], 'best_hours': list(range(8,22)), 'min_rr': 2.0,
        'allowed_symbols': ['XAUUSD','EURUSD','GBPUSD','USDJPY','GER40','US30','US500','BTCUSD'],
    },
}


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class SetupState:
    setup_id: str
    name: str
    mode: str
    tier: str
    readiness: float
    level: int
    level_label: str
    conditions_met: List[str]
    conditions_missing: List[str]
    direction: str
    score: float
    details: str
    rr_ratio: float = 0.0
    confluence_score: float = 0.0
    expectancy: float = 0.0
    stop_atr: float = 0.0
    target_atr: float = 0.0
    spread_ok: bool = True
    regime_match: bool = False
    session_match: bool = False
    enabled: bool = True
    score_breakdown: Dict = field(default_factory=dict)


@dataclass
class AssetScan:
    symbol: str
    price: float
    spread: float
    regime: str
    regime_score: float
    setups: List[SetupState]
    best_setup: Optional[SetupState]
    scan_time: str
    category: str = ''
    atr_h1: float = 0.0
    atr_m15: float = 0.0
    atr_m5: float = 0.0
    daily_range_pct: float = 0.0
    daily_range_pts: float = 0.0
    trend_h4: str = ''
    trend_h1: str = ''
    trend_m15: str = ''
    trend_m5: str = ''
    rsi_h1: float = 50.0
    rsi_m15: float = 50.0
    volatility: str = ''
    session: str = ''
    pips_today: float = 0.0
    spread_usd: float = 0.0
    score_total: float = 0.0
    top_setups: List[str] = None
    alert_level: str = ''
    session_active: bool = False
    pip_value: float = 0.0
    swap_buy: float = 0.0
    swap_sell: float = 0.0
    structure_htf: str = ''
    bias: str = ''
    key_zones: int = 0
    nearest_zone_dist: float = 0.0
    bb_width: float = 0.0
    adx: float = 0.0
    volume_ratio: float = 0.0
    scalp_count: int = 0
    day_count: int = 0
    swing_count: int = 0

    def __post_init__(self):
        if self.top_setups is None:
            self.top_setups = []


# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════

ASSET_CATEGORIES = {
    'XAUUSD': 'metal', 'XAGUSD': 'metal',
    'EURUSD': 'forex', 'GBPUSD': 'forex', 'USDJPY': 'forex',
    'USDCAD': 'forex', 'AUDUSD': 'forex', 'NZDUSD': 'forex',
    'EURGBP': 'forex', 'EURJPY': 'forex', 'GBPJPY': 'forex',
    'USDCHF': 'forex', 'AUDJPY': 'forex', 'EURAUD': 'forex',
    'EURCHF': 'forex', 'GBPCHF': 'forex',
    'US100': 'index', 'US30': 'index', 'US500': 'index', 'GER40': 'index',
    'BTCUSD': 'crypto', 'ETHUSD': 'crypto',
}

BEST_SESSIONS = {
    'forex': [9, 10, 11, 14, 15, 16],
    'metal': [8, 9, 10, 14, 15, 16, 20],
    'index': [9, 10, 14, 15, 16, 21],
    'crypto': list(range(0, 24)),
}

PIP_VALUES = {
    'XAUUSD': 0.01, 'XAGUSD': 0.01,
    'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'USDCAD': 0.0001,
    'AUDUSD': 0.0001, 'NZDUSD': 0.0001, 'USDCHF': 0.0001,
    'EURGBP': 0.0001, 'EURJPY': 0.01, 'GBPJPY': 0.01,
    'AUDJPY': 0.01, 'EURAUD': 0.0001, 'EURCHF': 0.0001,
    'GBPCHF': 0.0001, 'USDJPY': 0.01,        'US100': 0.01, 'US30': 0.01, 'US500': 0.01, 'GER40': 0.01,
    'BTCUSD': 0.01, 'ETHUSD': 0.01,
}

CORRELATED_PAIRS = {
    'EURUSD': 'GBPUSD', 'GBPUSD': 'EURUSD',
    'USDJPY': 'AUDJPY', 'AUDJPY': 'USDJPY',
    'EURGBP': 'EURUSD', 'EURJPY': 'USDJPY',
    'USDCAD': 'USDCHF', 'USDCHF': 'USDCAD',
    'AUDUSD': 'NZDUSD', 'NZDUSD': 'AUDUSD',
}

# Max spread in ATR units per mode
MAX_SPREAD_ATR = {'scalp': 0.15, 'day': 0.25, 'swing': 0.40}


# ═══════════════════════════════════════════════════════════════
# STRATEGY MANAGER
# ═══════════════════════════════════════════════════════════════

class StrategyManager:
    """Gerencia ON/OFF de cada estrategia por modo e ativo"""

    def __init__(self):
        self._enabled = {}
        self._mode_enabled = {'scalp': True, 'day': True, 'swing': True}
        self._asset_enabled = {}
        for s in SETUP_DEFINITIONS:
            self._enabled[s] = True

    def is_enabled(self, setup_id, mode=None, symbol=None):
        if not self._enabled.get(setup_id, True):
            return False
        if mode and not self._mode_enabled.get(mode, True):
            return False
        if symbol:
            key = "%s_%s" % (setup_id, symbol)
            if key in self._asset_enabled and not self._asset_enabled[key]:
                return False
        return True

    def toggle(self, setup_id, enabled):
        self._enabled[setup_id] = enabled

    def toggle_mode(self, mode, enabled):
        self._mode_enabled[mode] = enabled

    def toggle_asset(self, setup_id, symbol, enabled):
        key = "%s_%s" % (setup_id, symbol)
        self._asset_enabled[key] = enabled

    def get_all_states(self):
        return dict(self._enabled)

    def get_mode_states(self):
        return dict(self._mode_enabled)

    def get_status_summary(self):
        total = len(SETUP_DEFINITIONS)
        on = sum(1 for v in self._enabled.values() if v)
        return {'total': total, 'enabled': on, 'disabled': total - on}


# ═══════════════════════════════════════════════════════════════
# KILL SWITCH
# ═══════════════════════════════════════════════════════════════

class KillSwitch:
    """Protecao: daily loss, consecutive losses, cooldown"""

    def __init__(self):
        self.daily_loss_limit = -3.0  # R
        self.consecutive_loss_limit = 5
        self.cooldown_minutes = 5
        self._daily_pnl = 0.0
        self._consecutive_losses = 0
        self._cooldown_until = None
        self._active = True

    def reset_daily(self):
        self._daily_pnl = 0.0
        self._consecutive_losses = 0

    def record_trade(self, pnl_r):
        self._daily_pnl += pnl_r
        if pnl_r < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.consecutive_loss_limit:
                self._cooldown_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
        else:
            self._consecutive_losses = 0

    def can_trade(self):
        if not self._active:
            return True, 'KILL SWITCH OFF'
        if self._daily_pnl <= self.daily_loss_limit:
            return False, 'DAILY LOSS LIMIT REACHED: %.1fR' % self._daily_pnl
        if self._cooldown_until and datetime.now() < self._cooldown_until:
            remaining = (self._cooldown_until - datetime.now()).seconds
            return False, 'COOLDOWN: %ds remaining' % remaining
        return True, 'OK'

    def get_status(self):
        allowed, reason = self.can_trade()
        return {
            'active': self._active,
            'allowed': allowed,
            'reason': reason,
            'daily_pnl_r': self._daily_pnl,
            'consecutive_losses': self._consecutive_losses,
        }


# ═══════════════════════════════════════════════════════════════
# GOLDEN SCANNER v3
# ═══════════════════════════════════════════════════════════════

class GoldenScanner:

    RADAR_SYMBOLS = [
        'XAUUSD', 'XAGUSD',
        'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD', 'NZDUSD',
        'EURGBP', 'EURJPY', 'GBPJPY', 'AUDJPY', 'EURAUD', 'EURCHF', 'GBPCHF',
        'US100', 'US30', 'US500', 'GER40',
        'BTCUSD', 'ETHUSD',
    ]

    def __init__(self):
        self.setups = SETUP_DEFINITIONS
        self._candle_cache = {}
        self.strategy_manager = StrategyManager()
        self.kill_switch = KillSwitch()
        self._open_positions_by_symbol = {}

    # ═══ MARKET DATA ═══

    def _ensure_symbol(self, symbol):
        info = mt5.symbol_info(symbol)
        if not info:
            return None
        if not info.visible:
            mt5.symbol_select(symbol, True)
        return info

    def _get_candles(self, symbol, tf, count):
        tf_map = {
            'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15, 'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4, 'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
        }
        key = "%s_%s_%d" % (symbol, tf, count)
        if key in self._candle_cache:
            return self._candle_cache[key]
        # Posicao 0 e o candle em formacao; sinais so usam candles fechados.
        rates = mt5.copy_rates_from_pos(symbol, tf_map.get(tf, mt5.TIMEFRAME_M15), 1, count)
        if rates is None:
            return []
        result = [{'time': r['time'], 'open': r['open'], 'high': r['high'],
                   'low': r['low'], 'close': r['close'], 'vol': r['tick_volume']} for r in rates]
        self._candle_cache[key] = result
        return result

    # ═══ INDICATORS ═══

    def _donchian(self, candles, period):
        """Niveis Donchian fechados, excluindo o candle mais recente."""
        if len(candles) < period + 1:
            return 0.0, 0.0
        window = candles[-period-1:-1]
        return max(c['high'] for c in window), min(c['low'] for c in window)

    def _darvas_box(self, candles):
        """Retorna o ultimo topo/fundo confirmados de uma caixa Darvas."""
        if len(candles) < 8:
            return {'top': 0.0, 'bottom': 0.0, 'confirmed': False}
        for i in range(len(candles) - 3, 3, -1):
            top = candles[i]['high']
            bottom = min(c['low'] for c in candles[i-3:i+1])
            left_high = max(c['high'] for c in candles[i-3:i])
            if top < left_high:
                continue
            confirmation = candles[i+1:i+3]
            if len(confirmation) == 2 and all(c['high'] <= top for c in confirmation):
                return {'top': top, 'bottom': bottom, 'confirmed': True}
        return {'top': 0.0, 'bottom': 0.0, 'confirmed': False}

    def _opening_range(self, candles, tf):
        """Faixa de abertura da sessao UTC; usa os tres primeiros candles."""
        if not candles or tf not in ('M5', 'M15'):
            return {'high': 0.0, 'low': 0.0, 'defined': False}
        now = datetime.utcnow()
        session_hours = (7, 13) if now.hour < 13 else (13, 20)
        start = now.replace(hour=session_hours[0], minute=0, second=0, microsecond=0)
        selected = [c for c in candles if start.timestamp() <= float(c.get('time', 0)) < (start.timestamp() + 45 * 60)]
        selected = selected[:3]
        if len(selected) < 3:
            return {'high': 0.0, 'low': 0.0, 'defined': False}
        return {'high': max(c['high'] for c in selected), 'low': min(c['low'] for c in selected), 'defined': True}

    def _volume_profile(self, candles, bins=24):
        """Perfil de volume aproximado por preco usando tick volume do MT5."""
        if len(candles) < 20:
            return {'poc': 0.0, 'vah': 0.0, 'val': 0.0, 'defined': False}
        low = min(c['low'] for c in candles)
        high = max(c['high'] for c in candles)
        width = (high - low) / bins if high > low else 0
        if width <= 0:
            return {'poc': 0.0, 'vah': 0.0, 'val': 0.0, 'defined': False}
        histogram = [0.0] * bins
        for candle in candles:
            price = (candle['high'] + candle['low'] + candle['close']) / 3
            index = min(bins - 1, max(0, int((price - low) / width)))
            histogram[index] += float(candle.get('vol', 0) or 0)
        poc_index = max(range(bins), key=lambda i: histogram[i])
        total = sum(histogram)
        target = total * 0.70
        included = histogram[poc_index]
        left = right = poc_index
        while included < target and (left > 0 or right < bins - 1):
            next_left = histogram[left - 1] if left > 0 else -1
            next_right = histogram[right + 1] if right < bins - 1 else -1
            if next_right >= next_left and right < bins - 1:
                right += 1; included += histogram[right]
            elif left > 0:
                left -= 1; included += histogram[left]
            else:
                break
        return {'poc': low + (poc_index + 0.5) * width, 'vah': low + (right + 1) * width, 'val': low + left * width, 'defined': total > 0}

    def _anchored_vwap(self, candles):
        """VWAP ancorada no inicio do dia UTC, somente com candles fechados."""
        if not candles:
            return {'value': 0.0, 'upper': 0.0, 'lower': 0.0, 'defined': False}
        last_time = float(candles[-1].get('time', 0))
        day_start = datetime.utcfromtimestamp(last_time).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        selected = [c for c in candles if float(c.get('time', 0)) >= day_start]
        total_volume = sum(float(c.get('vol', 0) or 0) for c in selected)
        if not selected or total_volume <= 0:
            return {'value': 0.0, 'upper': 0.0, 'lower': 0.0, 'defined': False}
        prices = [(c['high'] + c['low'] + c['close']) / 3 for c in selected]
        value = sum(p * float(c.get('vol', 0) or 0) for p, c in zip(prices, selected)) / total_volume
        variance = sum(((p - value) ** 2) * float(c.get('vol', 0) or 0) for p, c in zip(prices, selected)) / total_volume
        deviation = variance ** 0.5
        return {'value': value, 'upper': value + 2 * deviation, 'lower': value - 2 * deviation, 'defined': True}

    def _ema(self, data, period):
        if len(data) < period:
            return data[-1] if data else 0
        m = 2.0 / (period + 1)
        e = float(data[0])
        for p in data[1:]:
            e = (float(p) - e) * m + e
        return e

    def _ema_series(self, data, period):
        if len(data) < period:
            return data[:]
        m = 2.0 / (period + 1)
        result = [float(data[0])]
        for p in data[1:]:
            result.append((float(p) - result[-1]) * m + result[-1])
        return result

    def _atr(self, candles, period):
        if len(candles) < period + 1:
            return 1.0
        trs = []
        for i in range(1, len(candles)):
            tr = max(candles[i]['high'] - candles[i]['low'],
                     abs(candles[i]['high'] - candles[i-1]['close']),
                     abs(candles[i]['low'] - candles[i-1]['close']))
            trs.append(tr)
        if not trs:
            return 1.0
        return float(np.mean(trs[-period:]))

    def _rsi(self, data, period):
        if len(data) < period + 1:
            return 50.0
        deltas = [data[i] - data[i-1] for i in range(1, len(data))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = float(np.mean(gains[-period:]))
        avg_loss = float(np.mean(losses[-period:]))
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _stoch(self, candles, k_period=5, smooth_k=3):
        if len(candles) < k_period:
            return 50.0
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        closes = [c['close'] for c in candles]
        raw_k_values = []
        for i in range(len(candles) - 1, max(len(candles) - k_period - 1, -1), -1):
            h = max(highs[max(0, i - k_period + 1):i + 1])
            l = min(lows[max(0, i - k_period + 1):i + 1])
            if h != l:
                raw_k = ((closes[i] - l) / (h - l)) * 100
            else:
                raw_k = 50.0
            raw_k_values.append(raw_k)
        return float(np.mean(raw_k_values[:smooth_k])) if raw_k_values else 50.0

    def _adx(self, candles, period=14):
        if len(candles) < period + 1:
            return 0.0
        plus_dm, minus_dm, trs = [], [], []
        for i in range(1, len(candles)):
            hd = candles[i]['high'] - candles[i-1]['high']
            ld = candles[i-1]['low'] - candles[i]['low']
            plus_dm.append(max(hd, 0) if hd > ld else 0)
            minus_dm.append(max(ld, 0) if ld > hd else 0)
            tr = max(candles[i]['high'] - candles[i]['low'],
                     abs(candles[i]['high'] - candles[i-1]['close']),
                     abs(candles[i]['low'] - candles[i-1]['close']))
            trs.append(tr)
        if len(trs) < period:
            return 0.0
        atr_val = float(np.mean(trs[-period:]))
        if atr_val == 0:
            return 0.0
        plus_di = (float(np.mean(plus_dm[-period:])) / atr_val) * 100
        minus_di = (float(np.mean(minus_dm[-period:])) / atr_val) * 100
        di_sum = plus_di + minus_di
        if di_sum == 0:
            return 0.0
        return abs(plus_di - minus_di) / di_sum * 100

    def _bollinger(self, data, period=20, std_dev=2.0):
        if len(data) < period:
            mid = data[-1] if data else 0
            return mid, mid, mid, 0
        window = data[-period:]
        mid = float(np.mean(window))
        std = float(np.std(window))
        upper = mid + std_dev * std
        lower = mid - std_dev * std
        width = (upper - lower) / mid * 100 if mid > 0 else 0
        return upper, mid, lower, width

    def _vwap(self, candles, period=20):
        if len(candles) < 5:
            return 0, 0, 0
        recent = candles[-period:]
        cum_tp_vol = 0.0
        cum_vol = 0.0
        for c in recent:
            tp = (c['high'] + c['low'] + c['close']) / 3.0
            vol = max(c.get('vol', 1), 1)
            cum_tp_vol += tp * vol
            cum_vol += vol
        vwap = cum_tp_vol / cum_vol if cum_vol > 0 else recent[-1]['close']
        variance = sum(((c['high']+c['low']+c['close'])/3.0 - vwap)**2 for c in recent)
        std = (variance / len(recent)) ** 0.5 if recent else 0
        return vwap, vwap + 2 * std, vwap - 2 * std

    def _macd(self, data, fast=12, slow=26, signal=9):
        if len(data) < slow + signal:
            return 0, 0, 0
        ema_fast = self._ema_series(data, fast)
        ema_slow = self._ema_series(data, slow)
        macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(data))]
        signal_line = self._ema_series(macd_line[slow-1:], signal)
        if not signal_line:
            return macd_line[-1] if macd_line else 0, 0, 0
        return macd_line[-1], signal_line[-1], macd_line[-1] - signal_line[-1]

    def _ichimoku(self, candles):
        result = {'tenkan': 0, 'kijun': 0, 'senkou_a': 0, 'senkou_b': 0,
                  'price_above_cloud': False, 'price_below_cloud': False,
                  'tk_cross_bull': False, 'tk_cross_bear': False}
        if len(candles) < 52:
            return result
        tenkan = (max(c['high'] for c in candles[-9:]) + min(c['low'] for c in candles[-9:])) / 2
        kijun = (max(c['high'] for c in candles[-26:]) + min(c['low'] for c in candles[-26:])) / 2
        senkou_a = (tenkan + kijun) / 2
        senkou_b = (max(c['high'] for c in candles[-52:]) + min(c['low'] for c in candles[-52:])) / 2
        cloud_top, cloud_bot = max(senkou_a, senkou_b), min(senkou_a, senkou_b)
        price = candles[-1]['close']
        result['tenkan'] = tenkan
        result['kijun'] = kijun
        result['senkou_a'] = senkou_a
        result['senkou_b'] = senkou_b
        result['cloud_top'] = cloud_top
        result['cloud_bot'] = cloud_bot
        result['price_above_cloud'] = price > cloud_top
        result['price_below_cloud'] = price < cloud_bot
        result['tk_cross_bull'] = tenkan > kijun
        result['tk_cross_bear'] = tenkan < kijun
        return result

    def _detect_gap(self, candles):
        if len(candles) < 3:
            return {'has_gap': False}
        prev, curr = candles[-3], candles[-2]
        if curr['low'] > prev['high']:
            return {'has_gap': True, 'gap_type': 'bull', 'gap_top': curr['low'], 'gap_bot': prev['high']}
        elif curr['high'] < prev['low']:
            return {'has_gap': True, 'gap_type': 'bear', 'gap_top': prev['low'], 'gap_bot': curr['high']}
        return {'has_gap': False}

    # ═══ STRUCTURE ═══

    def _detect_structure(self, candles, lookback=50):
        if len(candles) < lookback:
            return {'type': 'RANGE', 'bos': False, 'choch': False, 'swing_highs': [], 'swing_lows': []}
        data = candles[-lookback:]
        swing_highs, swing_lows = [], []
        for i in range(2, len(data) - 2):
            if data[i]['high'] > data[i-1]['high'] and data[i]['high'] > data[i-2]['high'] and \
               data[i]['high'] > data[i+1]['high'] and data[i]['high'] > data[i+2]['high']:
                swing_highs.append({'price': data[i]['high'], 'idx': i, 'time': data[i]['time']})
            if data[i]['low'] < data[i-1]['low'] and data[i]['low'] < data[i-2]['low'] and \
               data[i]['low'] < data[i+1]['low'] and data[i]['low'] < data[i+2]['low']:
                swing_lows.append({'price': data[i]['low'], 'idx': i, 'time': data[i]['time']})
        structure_type = 'RANGE'
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            last_hh = swing_highs[-1]['price'] > swing_highs[-2]['price']
            last_hl = swing_lows[-1]['price'] > swing_lows[-2]['price']
            last_lh = swing_highs[-1]['price'] < swing_highs[-2]['price']
            last_ll = swing_lows[-1]['price'] < swing_lows[-2]['price']
            if last_hh and last_hl:
                structure_type = 'HH_HL'
            elif last_lh and last_ll:
                structure_type = 'LH_LL'
        bos, choch = False, False
        price = data[-1]['close']
        if len(swing_highs) >= 1:
            if structure_type == 'HH_HL' and price > swing_highs[-1]['price']:
                bos = True
            elif structure_type == 'LH_LL' and price < swing_lows[-1]['price']:
                bos = True
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            if structure_type == 'LH_LL' and price > swing_highs[-2]['price']:
                choch = True
            elif structure_type == 'HH_HL' and price < swing_lows[-2]['price']:
                choch = True
        return {'type': structure_type, 'bos': bos, 'choch': choch,
                'swing_highs': swing_highs[-5:], 'swing_lows': swing_lows[-5:]}

    def _detect_sr_zones(self, candles, lookback=100):
        if len(candles) < lookback:
            return []
        data = candles[-lookback:]
        all_pivots = []
        for i in range(2, len(data) - 2):
            if data[i]['high'] > data[i-1]['high'] and data[i]['high'] > data[i-2]['high'] and \
               data[i]['high'] > data[i+1]['high']:
                all_pivots.append(data[i]['high'])
            if data[i]['low'] < data[i-1]['low'] and data[i]['low'] < data[i-2]['low'] and \
               data[i]['low'] < data[i+1]['low']:
                all_pivots.append(data[i]['low'])
        if len(all_pivots) < 2:
            return []
        all_pivots.sort()
        zones, used = [], set()
        for i in range(len(all_pivots)):
            if i in used:
                continue
            cluster = [all_pivots[i]]
            for j in range(i + 1, len(all_pivots)):
                if j in used:
                    continue
                if abs(all_pivots[j] - all_pivots[i]) / max(all_pivots[i], 0.0001) < 0.003:
                    cluster.append(all_pivots[j])
                    used.add(j)
            if len(cluster) >= 2:
                avg_price = float(np.mean(cluster))
                zones.append({'price': avg_price, 'touches': len(cluster), 'strength': min(100, len(cluster) * 25)})
        zones.sort(key=lambda z: z['strength'], reverse=True)
        return zones[:10]

    def _detect_fvg(self, candles):
        if len(candles) < 5:
            return []
        fvgs = []
        for i in range(2, len(candles)):
            if candles[i]['low'] > candles[i-2]['high']:
                fvgs.append({'type': 'bull', 'top': candles[i]['low'], 'bottom': candles[i-2]['high'], 'idx': i})
            elif candles[i]['high'] < candles[i-2]['low']:
                fvgs.append({'type': 'bear', 'top': candles[i-2]['low'], 'bottom': candles[i]['high'], 'idx': i})
        current_price = candles[-1]['close']
        for fvg in fvgs:
            if fvg['type'] == 'bull':
                fvg['filled'] = current_price <= fvg['bottom']
            else:
                fvg['filled'] = current_price >= fvg['top']
        return fvgs[-5:]

    def _detect_order_blocks(self, candles):
        if len(candles) < 10:
            return []
        obs = []
        for i in range(2, len(candles)):
            if (candles[i-1]['close'] < candles[i-1]['open'] and
                i < len(candles) - 1 and
                candles[i]['close'] > candles[i]['open'] and
                (candles[i]['close'] - candles[i]['open']) > (candles[i-1]['open'] - candles[i-1]['close']) * 1.5):
                rng = candles[i]['high'] - candles[i]['low']
                strength = min(100, int((candles[i]['close'] - candles[i]['open']) / (rng + 0.0001) * 100)) if rng > 0 else 50
                obs.append({'type': 'bull_ob', 'high': candles[i-1]['high'], 'low': candles[i-1]['low'], 'idx': i-1, 'strength': strength})
            elif (candles[i-1]['close'] > candles[i-1]['open'] and
                  i < len(candles) - 1 and
                  candles[i]['close'] < candles[i]['open'] and
                  (candles[i]['open'] - candles[i]['close']) > (candles[i-1]['close'] - candles[i-1]['open']) * 1.5):
                rng = candles[i]['high'] - candles[i]['low']
                strength = min(100, int((candles[i]['open'] - candles[i]['close']) / (rng + 0.0001) * 100)) if rng > 0 else 50
                obs.append({'type': 'bear_ob', 'high': candles[i-1]['high'], 'low': candles[i-1]['low'], 'idx': i-1, 'strength': strength})
        return obs[-5:]

    def _detect_candle_patterns(self, candles):
        if len(candles) < 3:
            return {'pattern': 'none', 'direction': 0, 'strength': 0}
        c = candles[-1]
        p = candles[-2]
        body = abs(c['close'] - c['open'])
        full_range = c['high'] - c['low']
        if full_range == 0:
            return {'pattern': 'none', 'direction': 0, 'strength': 0}
        body_pct = body / full_range
        upper_wick = c['high'] - max(c['close'], c['open'])
        lower_wick = min(c['close'], c['open']) - c['low']
        if lower_wick > body * 2 and upper_wick < body * 0.5:
            return {'pattern': 'pin_bar_bull', 'direction': 1, 'strength': min(100, int(lower_wick / body * 20))}
        elif upper_wick > body * 2 and lower_wick < body * 0.5:
            return {'pattern': 'pin_bar_bear', 'direction': -1, 'strength': min(100, int(upper_wick / body * 20))}
        p_body = abs(p['close'] - p['open'])
        if body > p_body * 1.2 and body_pct > 0.6:
            if c['close'] > c['open'] and p['close'] < p['open']:
                return {'pattern': 'engulfing_bull', 'direction': 1, 'strength': min(100, int(body_pct * 100))}
            elif c['close'] < c['open'] and p['close'] > p['open']:
                return {'pattern': 'engulfing_bear', 'direction': -1, 'strength': min(100, int(body_pct * 100))}
        if body_pct > 0.7:
            d = 1 if c['close'] > c['open'] else -1
            return {'pattern': 'strong_bull' if d == 1 else 'strong_bear', 'direction': d, 'strength': int(body_pct * 80)}
        if body_pct < 0.1:
            return {'pattern': 'doji', 'direction': 0, 'strength': 30}
        return {'pattern': 'none', 'direction': 0, 'strength': 0}

    # ═══ TF ANALYSIS ═══

    def _analyze_tf(self, symbol, tf, count=100):
        candles = self._get_candles(symbol, tf, count)
        default = {'trend': 'lateral', 'ema9': 0, 'ema20': 0, 'ema50': 0, 'atr': 1, 'rsi': 50,
                    'adx': 0, 'bb_width': 0, 'price': 0, 'structure': 'RANGE',
                    'volume_ratio': 0,
                    'bos': False, 'choch': False, 'candle': {'pattern': 'none', 'direction': 0, 'strength': 0},
                    'fvg_count': 0, 'ob_count': 0, 'sr_zones': [],
                    'vwap': 0, 'vwap_upper': 0, 'vwap_lower': 0,
                    'macd': 0, 'macd_signal': 0, 'macd_hist': 0,
                    'ichimoku': {}, 'gap': {'has_gap': False},
                    'swing_highs': [], 'swing_lows': [], 'stoch_k': 50,
                    'bb_upper': 0, 'bb_lower': 0,
                    'donchian_high_20': 0, 'donchian_low_20': 0,
                    'donchian_high_55': 0, 'donchian_low_55': 0,
                    'darvas_box': {}, 'opening_range': {}, 'volume_profile': {}, 'anchored_vwap': {}}
        if not candles or len(candles) < 20:
            return default
        closes = [c['close'] for c in candles]
        volumes = [float(c.get('vol', c.get('tick_volume', 0)) or 0) for c in candles]
        volume_avg = sum(volumes[:-1]) / max(len(volumes) - 1, 1)
        volume_ratio = volumes[-1] / volume_avg if volume_avg > 0 else 0
        price = closes[-1]
        ema9 = self._ema(closes, 9)
        ema20 = self._ema(closes, 20)
        ema50 = self._ema(closes, 50)
        atr = self._atr(candles, 14)
        rsi = self._rsi(closes, 14)
        adx = self._adx(candles, 14)
        bb_upper, _, bb_lower, bb_width = self._bollinger(closes, 20)
        stoch_k = self._stoch(candles)
        vwap, vwap_upper, vwap_lower = self._vwap(candles)
        donchian_high_20, donchian_low_20 = self._donchian(candles, 20)
        donchian_high_55, donchian_low_55 = self._donchian(candles, 55)
        darvas_box = self._darvas_box(candles)
        opening_range = self._opening_range(candles, tf)
        volume_profile = self._volume_profile(candles)
        anchored_vwap = self._anchored_vwap(candles)
        macd_val, macd_signal, macd_hist = self._macd(closes)
        ichimoku = self._ichimoku(candles)
        gap = self._detect_gap(candles)
        trend = 'alta' if (ema20 > ema50 and price > ema20) else ('baixa' if (ema20 < ema50 and price < ema20) else 'lateral')
        structure = self._detect_structure(candles)
        candle_pat = self._detect_candle_patterns(candles)
        fvgs = self._detect_fvg(candles)
        obs = self._detect_order_blocks(candles)
        sr_zones = self._detect_sr_zones(candles)
        return {
            'trend': trend, 'ema9': ema9, 'ema20': ema20, 'ema50': ema50,
            'atr': atr, 'rsi': rsi, 'adx': adx, 'bb_width': bb_width, 'volume_ratio': round(volume_ratio, 2),
            'price': price, 'structure': structure['type'],
            'bos': structure['bos'], 'choch': structure['choch'],
            'candle': candle_pat,
            'fvg_count': len([f for f in fvgs if not f.get('filled', False)]),
            'ob_count': len(obs), 'sr_zones': sr_zones,
            'swing_highs': structure.get('swing_highs', []),
            'swing_lows': structure.get('swing_lows', []),
            'stoch_k': stoch_k, 'bb_upper': bb_upper, 'bb_lower': bb_lower,
            'vwap': vwap, 'vwap_upper': vwap_upper, 'vwap_lower': vwap_lower,
            'macd': macd_val, 'macd_signal': macd_signal, 'macd_hist': macd_hist,
            'ichimoku': ichimoku, 'gap': gap,
            'donchian_high_20': donchian_high_20, 'donchian_low_20': donchian_low_20,
            'donchian_high_55': donchian_high_55, 'donchian_low_55': donchian_low_55,
            'darvas_box': darvas_box, 'opening_range': opening_range,
            'volume_profile': volume_profile, 'anchored_vwap': anchored_vwap,
        }

    # ═══ SCORING — 7 FATORES INDEPENDENTES ═══

    def _calc_confluence(self, tf_data, direction, tf_weights):
        """FATOR 1: Setup Quality — 30%"""
        if direction == 0 or not tf_data:
            return 0
        score, total_weight = 0, 0
        for tf, weight in tf_weights.items():
            if tf not in tf_data:
                continue
            data = tf_data[tf]
            total_weight += weight
            tf_score = 0
            if data['trend'] == 'alta' and direction == 1:
                tf_score += 30
            elif data['trend'] == 'baixa' and direction == -1:
                tf_score += 30
            elif data['trend'] != 'lateral':
                tf_score += 5
            if data['structure'] == 'HH_HL' and direction == 1:
                tf_score += 25
            elif data['structure'] == 'LH_LL' and direction == -1:
                tf_score += 25
            rsi = data['rsi']
            if direction == 1 and 30 < rsi < 70:
                tf_score += 15
            elif direction == -1 and 30 < rsi < 70:
                tf_score += 15
            if data['candle']['direction'] == direction:
                tf_score += min(15, data['candle']['strength'] * 15 // 100)
            if data['bos']:
                tf_score += 10
            score += tf_score * weight
        return min(100, score / total_weight) if total_weight > 0 else 0

    def _calc_rr(self, tf_data, direction, mode, atr):
        if not tf_data or direction == 0 or atr <= 0:
            return 0, 0, 0, 0, 0
        primary_tf = 'M5' if mode == 'scalp' else ('M15' if mode == 'day' else 'H4')
        data = tf_data.get(primary_tf, {})
        price = data.get('price', 0)
        if price <= 0:
            return 0, 0, 0, 0, 0
        swing_highs = data.get('swing_highs', [])
        swing_lows = data.get('swing_lows', [])
        stop_distance, target_distance = 0, 0
        if direction == 1:
            if swing_lows:
                nearest_low = max([s['price'] for s in swing_lows if s['price'] < price], default=0)
                if nearest_low > 0:
                    stop_distance = price - nearest_low
            if stop_distance <= 0:
                stop_distance = atr * 1.5
            if swing_highs:
                nearest_high = min([s['price'] for s in swing_highs if s['price'] > price], default=0)
                if nearest_high > 0:
                    target_distance = nearest_high - price
            if target_distance <= 0:
                target_distance = atr * 2.5
        else:
            if swing_highs:
                nearest_high = min([s['price'] for s in swing_highs if s['price'] > price], default=999999)
                if nearest_high < 999999:
                    stop_distance = nearest_high - price
            if stop_distance <= 0:
                stop_distance = atr * 1.5
            if swing_lows:
                nearest_low = max([s['price'] for s in swing_lows if s['price'] < price], default=0)
                if nearest_low > 0:
                    target_distance = price - nearest_low
            if target_distance <= 0:
                target_distance = atr * 2.5
        rr = target_distance / stop_distance if stop_distance > 0 else 0
        stop_atr = stop_distance / atr if atr > 0 else 0
        target_atr = target_distance / atr if atr > 0 else 0
        return round(stop_distance, 5), round(target_distance, 5), round(rr, 2), round(stop_atr, 2), round(target_atr, 2)

    def _detect_regime(self, symbol):
        """Regime engine expandido: TREND_UP/DOWN, RANGE, COMPRESSION, TRANSITION, HIGH_VOL, LOW_VOL"""
        candles = self._get_candles(symbol, 'H1', 200)
        if len(candles) < 50:
            return {'type': 'unknown', 'score': 0}
        closes = [c['close'] for c in candles]
        ema20 = self._ema(closes, 20)
        ema50 = self._ema(closes, 50)
        ema200 = self._ema(closes, 200) if len(closes) >= 200 else ema50
        adx = self._adx(candles, 14)
        atr = self._atr(candles, 14)
        atr_long = self._atr(candles, 50)
        vol_ratio = atr / atr_long if atr_long > 0 else 1
        bb_upper, _, bb_lower, bb_width = self._bollinger(closes)
        trending_up = ema20 > ema50 and ema50 > ema200 and closes[-1] > ema20
        trending_down = ema20 < ema50 and ema50 < ema200 and closes[-1] < ema20
        if trending_up and adx > 25:
            return {'type': 'trending', 'score': min(100, 60 + adx), 'direction': 'up'}
        elif trending_down and adx > 25:
            return {'type': 'trending', 'score': min(100, 60 + adx), 'direction': 'down'}
        elif adx < 15 and bb_width < 0.8:
            return {'type': 'compression', 'score': min(100, 100 - adx * 2)}
        elif vol_ratio > 1.5:
            return {'type': 'volatile', 'score': min(100, vol_ratio * 50)}
        elif vol_ratio < 0.6:
            return {'type': 'low_vol', 'score': 40}
        elif 40 <= (ema20/ema50*100 if ema50 > 0 else 50) <= 60:
            return {'type': 'transition', 'score': 50}
        elif adx > 20:
            trend_score_calc = 50 if ema20 > ema50 else 50
            return {'type': 'trending', 'score': min(100, trend_score_calc + adx), 'direction': 'up' if ema20 > ema50 else 'down'}
        else:
            return {'type': 'ranging', 'score': min(100, 100 - adx)}

    def _get_session(self):
        h = datetime.now().hour
        if 0 <= h < 7:
            return 'ASIA'
        elif 7 <= h < 12:
            return 'LONDON'
        elif 12 <= h < 16:
            return 'OVERLAP'
        elif 16 <= h < 21:
            return 'NY'
        return 'OFF'

    def _get_trend(self, symbol, tf):
        candles = self._get_candles(symbol, tf, 60)
        if len(candles) < 20:
            return 'lateral'
        closes = [c['close'] for c in candles]
        ema20 = self._ema(closes, 20)
        ema50 = self._ema(closes, 50)
        if ema20 > ema50 and closes[-1] > ema20:
            return 'alta'
        elif ema20 < ema50 and closes[-1] < ema20:
            return 'baixa'
        return 'lateral'

    def _get_rsi(self, symbol, tf):
        candles = self._get_candles(symbol, tf, 30)
        if len(candles) < 15:
            return 50.0
        closes = [c['close'] for c in candles]
        return self._rsi(closes, 14)

    # ═══ SETUP EVALUATION ═══

    def _evaluate_setup(self, symbol, setup_id, setup_def, regime, tf_data_cache):
        mode = setup_def['mode']
        tfs = setup_def['timeframes']
        conditions = setup_def['conditions']
        tf_weights = setup_def.get('tf_weights', {})
        best_regimes = setup_def.get('best_regime', [])
        best_hours = setup_def.get('best_hours', [])
        min_rr = setup_def.get('min_rr', 1.5)
        tier = setup_def.get('tier', 'C')

        # Check if strategy manager allows
        if not self.strategy_manager.is_enabled(setup_id, mode, symbol):
            return SetupState(setup_id=setup_id, name=setup_def['name'], mode=mode, tier=tier,
                              readiness=0, level=0, level_label='OFF',
                              conditions_met=[], conditions_missing=conditions,
                              direction='-', score=0, details='DESATIVADO PELO MANAGER', enabled=False)
        allowed_symbols = setup_def.get('allowed_symbols', [])
        if allowed_symbols and symbol not in allowed_symbols:
            return SetupState(setup_id=setup_id, name=setup_def['name'], mode=mode, tier=tier,
                              readiness=0, level=0, level_label='OFF',
                              conditions_met=[], conditions_missing=conditions,
                              direction='-', score=0, details='ATIVO NAO PERMITIDO PARA ESTA ESTRATEGIA', enabled=False)

        regime_ok = regime['type'] in best_regimes
        current_hour = datetime.now().hour
        hour_ok = current_hour in best_hours

        # Cache TF data
        tf_data = {}
        for tf in tfs:
            cache_key = "%s_%s" % (symbol, tf)
            if cache_key in tf_data_cache:
                tf_data[tf] = tf_data_cache[cache_key]
            else:
                data = self._analyze_tf(symbol, tf)
                tf_data_cache[cache_key] = data
                tf_data[tf] = data

        # Direction
        buy_conf = self._calc_confluence(tf_data, 1, tf_weights)
        sell_conf = self._calc_confluence(tf_data, -1, tf_weights)
        if buy_conf > sell_conf:
            direction, direction_str, base_conf = 1, 'BUY', buy_conf
        elif sell_conf > buy_conf:
            direction, direction_str, base_conf = -1, 'SELL', sell_conf
        else:
            direction, direction_str, base_conf = 0, 'NEUTRO', 0

        # Conditions
        met, missing = [], []
        for cond in conditions:
            if self._check_real_condition(cond, tf_data, regime, direction):
                met.append(cond)
            else:
                missing.append(cond)
        conditions_score = (len(met) / len(conditions)) * 100 if conditions else 0

        # R:R
        primary_tf = tfs[0] if tfs else 'H1'
        atr = tf_data.get(primary_tf, {}).get('atr', 1)
        stop_dist, target_dist, rr, stop_atr, target_atr = self._calc_rr(tf_data, direction, mode, atr)

        # Spread filter (ATR-normalized)
        spread_ok = True
        try:
            info = mt5.symbol_info(symbol)
            if info and atr > 0:
                spread_in_atr = (info.spread * PIP_VALUES.get(symbol, 0.0001)) / atr
                if spread_in_atr > MAX_SPREAD_ATR.get(mode, 0.25):
                    spread_ok = False
        except:
            pass

        # ═══ 7-FACTOR SCORING ═══
        score_breakdown = {}

        # 1. Setup Quality — 30%
        score_breakdown['setup_quality'] = conditions_score

        # 2. Regime Match — 15%
        score_breakdown['regime'] = 100 if regime_ok else 30

        # 3. Structure — 15%
        structure_score = 0
        for tf_key, data in tf_data.items():
            if isinstance(data, dict):
                s = data.get('structure', 'RANGE')
                if (direction == 1 and s == 'HH_HL') or (direction == -1 and s == 'LH_LL'):
                    structure_score += 80
                elif s != 'RANGE':
                    structure_score += 30
        score_breakdown['structure'] = min(100, structure_score / max(len(tf_data), 1))

        # 4. Location (S/R proximity, VWAP, OB, FVG) — 15%
        location_score = 0
        for tf_key, data in tf_data.items():
            if isinstance(data, dict):
                price = data.get('price', 0)
                for zone in data.get('sr_zones', []):
                    if price > 0 and abs(price - zone['price']) / atr < 0.3:
                        location_score += 60
                if data.get('ob_count', 0) > 0:
                    location_score += 30
                if data.get('fvg_count', 0) > 0:
                    location_score += 20
        score_breakdown['location'] = min(100, location_score / max(len(tf_data), 1))

        # 5. Momentum/Volume — 10%
        momentum_score = 0
        for tf_key, data in tf_data.items():
            if isinstance(data, dict):
                adx = data.get('adx', 0)
                rsi = data.get('rsi', 50)
                if adx > 25:
                    momentum_score += 50
                elif adx > 15:
                    momentum_score += 25
                if direction == 1 and 45 < rsi < 75:
                    momentum_score += 30
                elif direction == -1 and 25 < rsi < 55:
                    momentum_score += 30
        score_breakdown['momentum'] = min(100, momentum_score / max(len(tf_data), 1))

        # 6. Risk Quality (R:R + spread) — 10%
        risk_score = 0
        if rr >= min_rr * 2:
            risk_score = 100
        elif rr >= min_rr:
            risk_score = 70
        elif rr >= min_rr * 0.7:
            risk_score = 40
        if not spread_ok:
            risk_score *= 0.3
        score_breakdown['risk'] = risk_score

        # 7. Session — 5%
        score_breakdown['session'] = 100 if hour_ok else 40

        # Weighted total
        weights = {'setup_quality': 0.30, 'regime': 0.15, 'structure': 0.15,
                   'location': 0.15, 'momentum': 0.10, 'risk': 0.10, 'session': 0.05}
        total_score = sum(score_breakdown[k] * weights[k] for k in weights)

        # R:R penalty
        if rr > 0 and rr < min_rr:
            total_score *= 0.6

        # Spread penalty
        if not spread_ok:
            total_score *= 0.3

        # Tier bonus
        tier_bonus = {'A': 1.0, 'B': 0.95, 'C': 0.90}
        total_score *= tier_bonus.get(tier, 1.0)

        total_score = min(100, total_score)

        # Expectancy estimate
        if rr > 0 and total_score > 0:
            wr_estimate = min(0.70, 0.35 + (total_score / 200))
            expectancy = (wr_estimate * rr) - (1 - wr_estimate)
        else:
            expectancy = 0

        # Level
        if total_score >= 75 and rr >= min_rr and spread_ok:
            level, level_label = 3, 'OPORTUNIDADE'
        elif total_score >= 50:
            level, level_label = 2, 'PRE_ENTRADA'
        else:
            level, level_label = 1, 'MONITORANDO'

        details = self._generate_details(setup_def, met, missing, regime, hour_ok, rr, base_conf, spread_ok)

        return SetupState(setup_id=setup_id, name=setup_def['name'], mode=mode, tier=tier,
                          readiness=round(total_score), level=level, level_label=level_label,
                          conditions_met=met, conditions_missing=missing,
                          direction=direction_str, score=round(total_score),
                          details=details, rr_ratio=rr, confluence_score=round(base_conf),
                          expectancy=round(expectancy, 3), stop_atr=stop_atr, target_atr=target_atr,
                          spread_ok=spread_ok, regime_match=regime_ok, session_match=hour_ok,
                          score_breakdown=score_breakdown)

    def _generate_details(self, setup_def, met, missing, regime, hour_ok, rr, confluence, spread_ok):
        parts = []
        parts.append("Setup: %s [%s]" % (setup_def['name'], setup_def.get('tier', '?')))
        parts.append("Condicoes: %d/%d" % (len(met), len(met) + len(missing)))
        parts.append("Regime: %s (%s)" % (regime.get('type', '?'), 'OK' if regime['type'] in setup_def.get('best_regime', []) else 'NAO'))
        parts.append("Horario: %s" % ('OK' if hour_ok else 'NAO'))
        parts.append("R:R: %.1f" % rr)
        parts.append("Spread: %s" % ('OK' if spread_ok else 'ALTO'))
        parts.append("Confluencia: %.0f%%" % confluence)
        if met:
            parts.append("Atendido: %s" % ', '.join(met[:3]))
        if missing:
            parts.append("Falta: %s" % ', '.join(missing[:3]))
        return ' | '.join(parts)

    # ═══ CONDITION CHECKER (mantido do v2 com correcoes) ═══

    def _check_real_condition(self, condition, tf_data, regime, direction):
        def _iter():
            for tf_key, data in tf_data.items():
                if isinstance(data, dict) and 'price' in data:
                    yield data

        if condition == 'breakout_confirmed':
            for data in _iter():
                sh = data.get('swing_highs', [])
                if sh and data['price'] > sh[-1]['price']:
                    return True
            return False
        if condition == 'breakout_volume':
            return any(data.get('adx', 0) > 25 for data in _iter())
        if condition == 'retest_zone':
            for data in _iter():
                price, atr = data['price'], data.get('atr', 1)
                for zone in data.get('sr_zones', []):
                    if abs(price - zone['price']) < atr * 0.3:
                        return True
            return False
        if condition in ('trend_aligned', 'strong_trend', 'trend_strong'):
            aligned = sum(1 for data in _iter() if
                (direction == 1 and data.get('trend') == 'alta') or
                (direction == -1 and data.get('trend') == 'baixa'))
            return aligned >= 2
        if condition == 'strong_trend_m1':
            d = tf_data.get('M1', {})
            return isinstance(d, dict) and d.get('adx', 0) > 20 and d.get('trend') != 'lateral'
        if condition == 'ema_pullback':
            for data in _iter():
                ema20 = data.get('ema20', 0)
                if ema20 > 0 and abs(data['price'] - ema20) / ema20 < 0.003:
                    return True
            return False
        if condition in ('candle_reversal', 'rejection_candle', 'reversal_candle', 'reversal_pattern', 'pin_bar_rejection'):
            for data in _iter():
                c = data.get('candle', {})
                if c.get('direction', 0) == direction and c.get('strength', 0) > 30:
                    return True
            return False
        if condition in ('engulfing_bull', 'bull_bear_engulfing', 'engulfing_pattern'):
            for data in _iter():
                if 'engulfing' in data.get('candle', {}).get('pattern', ''):
                    return True
            return False
        if condition == 'reversal_confirm':
            for data in _iter():
                c = data.get('candle', {})
                if c.get('direction', 0) == direction:
                    return True
                rsi = data.get('rsi', 50)
                if (direction == 1 and rsi < 40) or (direction == -1 and rsi > 60):
                    return True
            return False
        if condition in ('sweep_detected', 'liquidity_sweep_htf', 'liquidity_grab'):
            for data in _iter():
                price = data['price']
                sh = data.get('swing_highs', [])
                sl = data.get('swing_lows', [])
                c = data.get('candle', {})
                if sh and price < sh[-1]['price'] and c.get('pattern', '').startswith('pin_bar'):
                    return True
                if sl and price > sl[-1]['price'] and c.get('pattern', '').startswith('pin_bar'):
                    return True
            return False
        if condition in ('false_break_wick', 'false_break_reversal'):
            for data in _iter():
                c = data.get('candle', {})
                if c.get('pattern', '').startswith('pin_bar') and c.get('strength', 0) > 40:
                    return True
            return False
        if condition == 'structure_level':
            return any(len(data.get('sr_zones', [])) > 0 for data in _iter())
        if condition in ('volume_spike', 'volume_surge', 'volume_confirm', 'volume_at_extreme', 'volume_above_avg'):
            threshold = 1.50 if condition in ('volume_spike', 'volume_surge') else 1.10
            return any(data.get('volume_ratio', 0) >= threshold for data in _iter())
        if condition in ('momentum_spike', 'strong_momentum', 'displacement', 'price_displacement'):
            for data in _iter():
                rsi = data.get('rsi', 50)
                if (direction == 1 and rsi > 55) or (direction == -1 and rsi < 45):
                    return True
            return False
        if condition in ('momentum_fading', 'momentum_weakening'):
            return any(35 < data.get('rsi', 50) < 65 for data in _iter())
        if condition == 'rsi_divergence':
            for data in _iter():
                rsi = data.get('rsi', 50)
                if (direction == 1 and rsi < 45) or (direction == -1 and rsi > 55):
                    return True
            return False
        if condition == 'rsi_extreme':
            return any(data.get('rsi', 50) > 70 or data.get('rsi', 50) < 30 for data in _iter())
        if condition in ('range', 'consolidation', 'tight_range', 'consolidation_detected'):
            return regime.get('type') in ('ranging', 'compression')
        if condition == 'opening_range_defined':
            for data in _iter():
                sh = data.get('swing_highs', [])
                sl = data.get('swing_lows', [])
                if sh and sl:
                    rng = abs(sh[-1]['price'] - sl[-1]['price'])
                    if data['price'] > 0 and rng / data['price'] < 0.015:
                        return True
            return False
        if condition == 'session_extreme':
            for data in _iter():
                price = data['price']
                sh = data.get('swing_highs', [])
                sl = data.get('swing_lows', [])
                if sh and sl:
                    highest = max(s['price'] for s in sh[-3:])
                    lowest = min(s['price'] for s in sl[-3:])
                    if price >= highest * 0.998 or price <= lowest * 1.002:
                        return True
            return False
        if condition in ('bb_squeeze', 'bb_squeeze_htf', 'squeeze'):
            return any(data.get('bb_width', 100) < 1.0 for data in _iter())
        if condition in ('expansion_start', 'expansion_starting', 'expansion'):
            return any(data.get('adx', 0) > 25 for data in _iter())
        if condition == 'directional_candle':
            return any(data.get('candle', {}).get('strength', 0) > 50 for data in _iter())
        if condition == 'vwap_extended':
            return any(data.get('rsi', 50) > 72 or data.get('rsi', 50) < 28 for data in _iter())
        if condition == 'ema_trend_aligned':
            for data in _iter():
                ema20 = data.get('ema20', 0)
                if ema20 > 0:
                    if (direction == 1 and data['price'] > ema20) or (direction == -1 and data['price'] < ema20):
                        return True
            return False
        if condition == 'rsi_momentum_zone':
            for data in _iter():
                rsi = data.get('rsi', 50)
                if (direction == 1 and 55 < rsi < 75) or (direction == -1 and 25 < rsi < 45):
                    return True
            return False
        if condition == 'bb_midband_close':
            for data in _iter():
                bb_u, bb_l = data.get('bb_upper', 0), data.get('bb_lower', 0)
                if bb_u > 0 and bb_l > 0:
                    mid = (bb_u + bb_l) / 2
                    band = bb_u - bb_l
                    if band > 0:
                        pos = (data['price'] - bb_l) / band
                        if 0.3 < pos < 0.7:
                            return True
            return False
        if condition == 'vwma_direction_aligned':
            for data in _iter():
                ema9 = data.get('ema9', data.get('ema20', 0))
                ema20 = data.get('ema20', 0)
                rsi, adx = data.get('rsi', 50), data.get('adx', 0)
                if direction == 1 and ema9 > ema20 and rsi > 50 and adx > 15:
                    return True
                elif direction == -1 and ema9 < ema20 and rsi < 50 and adx > 15:
                    return True
            return False
        if condition == 'vwap_trend_aligned':
            for data in _iter():
                ema20 = data.get('ema20', 0)
                rsi = data.get('rsi', 50)
                if (direction == 1 and data['price'] > ema20 and rsi > 50) or \
                   (direction == -1 and data['price'] < ema20 and rsi < 50):
                    return True
            return False
        if condition == 'pullback_to_vwap':
            for data in _iter():
                ema20 = data.get('ema20', 0)
                atr = data.get('atr', 1)
                if ema20 > 0 and abs(data['price'] - ema20) < atr * 0.3:
                    return True
            return False
        if condition == 'volume_decreasing_pullback':
            return any(15 < data.get('adx', 0) < 30 for data in _iter())
        if condition == 'vwap_cross_decisive':
            for data in _iter():
                ema20 = data.get('ema20', 0)
                c = data.get('candle', {})
                if (direction == 1 and data['price'] > ema20 and c.get('direction', 0) == 1 and c.get('strength', 0) > 30) or \
                   (direction == -1 and data['price'] < ema20 and c.get('direction', 0) == -1 and c.get('strength', 0) > 30):
                    return True
            return False
        if condition == 'close_beyond_vwap':
            for data in _iter():
                ema20 = data.get('ema20', 0)
                if ema20 > 0:
                    if (direction == 1 and data['price'] > ema20) or (direction == -1 and data['price'] < ema20):
                        return True
            return False
        if condition == 'retest_and_hold':
            for data in _iter():
                ema20, atr, rsi = data.get('ema20', 0), data.get('atr', 1), data.get('rsi', 50)
                if ema20 > 0 and abs(data['price'] - ema20) < atr * 0.2:
                    if (direction == 1 and rsi > 45) or (direction == -1 and rsi < 55):
                        return True
            return False
        if condition == 'structure_confirm':
            for data in _iter():
                s = data.get('structure', 'RANGE')
                if (direction == 1 and s in ('HH_HL', 'RANGE')) or (direction == -1 and s in ('LH_LL', 'RANGE')):
                    return True
            return False
        if condition == 'rsi_extreme_reversal':
            for data in _iter():
                rsi = data.get('rsi', 50)
                if (direction == 1 and rsi <= 25) or (direction == -1 and rsi >= 75):
                    return True
            return False
        if condition == 'bb_extreme_penetration':
            for data in _iter():
                bb_u, bb_l = data.get('bb_upper', 0), data.get('bb_lower', 0)
                if bb_u > 0 and bb_l > 0:
                    if (direction == 1 and data['price'] <= bb_l) or (direction == -1 and data['price'] >= bb_u):
                        return True
            return False
        if condition == 'stoch_extreme':
            for data in _iter():
                stoch = data.get('stoch_k', 50)
                if (direction == 1 and stoch <= 20) or (direction == -1 and stoch >= 80):
                    return True
            return False
        if condition == 'bb_squeeze_detect':
            return any(data.get('bb_width', 100) < 1.5 for data in _iter())
        if condition == 'adx_strong_trend':
            return any(data.get('adx', 0) > 25 for data in _iter())
        if condition == 'bb_breakout_confirmed':
            for data in _iter():
                bb_u, bb_l = data.get('bb_upper', 0), data.get('bb_lower', 0)
                if bb_u > 0 and bb_l > 0:
                    if (direction == 1 and data['price'] > bb_u) or (direction == -1 and data['price'] < bb_l):
                        return True
            return False
        if condition == 'ema_cross_fast':
            for data in _iter():
                ema9 = data.get('ema9', data.get('ema20', 0))
                ema20 = data.get('ema20', 0)
                if ema20 > 0 and ema9 > 0:
                    if (direction == 1 and ema9 > ema20) or (direction == -1 and ema9 < ema20):
                        return True
            return False
        if condition == 'ema_alignment':
            for data in _iter():
                ema9 = data.get('ema9', data.get('ema20', 0))
                ema20, rsi = data.get('ema20', 0), data.get('rsi', 50)
                if ema20 > 0 and ema9 > 0:
                    if (direction == 1 and ema9 > ema20 and rsi > 50) or (direction == -1 and ema9 < ema20 and rsi < 50):
                        return True
            return False
        if condition == 'ema_slope_strong':
            return any(data.get('adx', 0) > 15 for data in _iter())
        if condition == 'near_sr_level':
            for data in _iter():
                price, atr = data['price'], data.get('atr', 1)
                for zone in data.get('sr_zones', []):
                    if abs(price - zone['price']) < atr * 0.3:
                        return True
            return False
        if condition == 'atr_elevated':
            return any(data.get('adx', 0) > 20 for data in _iter())
        if condition == 'follow_through':
            return any(data.get('candle', {}).get('direction', 0) == direction for data in _iter())
        if condition in ('order_block_detected', 'ob_identified', 'ob_htf_identified'):
            return any(data.get('ob_count', 0) > 0 for data in _iter())
        if condition in ('displacement_before_ob', 'displacement_into_ob'):
            return any(data.get('candle', {}).get('strength', 0) > 60 for data in _iter())
        if condition in ('reaction_at_ob', 'rejection_at_ob', 'reaction_at_fvg'):
            for data in _iter():
                c = data.get('candle', {})
                if c.get('direction', 0) == direction and c.get('strength', 0) > 30:
                    return True
            return False
        if condition in ('fvg_detected', 'fvg_fill', 'price_returning_to_fvg'):
            return any(data.get('fvg_count', 0) > 0 for data in _iter())
        if condition in ('sr_zone', 'sr_zone_proximity', 'sr_multi_touch', 'major_sr_level', 'macro_sr_zone'):
            for data in _iter():
                zones = data.get('sr_zones', [])
                if condition == 'sr_multi_touch' and any(z['touches'] >= 3 for z in zones):
                    return True
                elif condition == 'major_sr_level' and any(z['strength'] >= 50 for z in zones):
                    return True
                elif len(zones) > 0:
                    return True
            return False
        if condition == 'sr_level_proximity':
            for data in _iter():
                price, atr = data['price'], data.get('atr', 1)
                for zone in data.get('sr_zones', []):
                    if abs(price - zone['price']) < atr * 0.5:
                        return True
            return False
        if condition in ('zone_identified', 'pullback_to_zone'):
            return any(len(data.get('sr_zones', [])) > 0 for data in _iter())
        if condition in ('pullback', 'pullback_htf'):
            return any(data.get('trend') != 'lateral' for data in _iter())
        if condition == 'micro_pullback_ema':
            for data in _iter():
                ema20 = data.get('ema20', 0)
                if ema20 > 0 and abs(data['price'] - ema20) / ema20 < 0.001:
                    return True
            return False
        if condition in ('bos_detected', 'bos_confirmation'):
            return any(data.get('bos') for data in _iter())
        if condition in ('choch_detected', 'daily_choch'):
            return any(data.get('choch') for data in _iter())
        if condition == 'structure_shift':
            return any(data.get('bos') or data.get('choch') for data in _iter())
        if condition == 'retest_ob_zone':
            return any(data.get('ob_count', 0) > 0 and data.get('sr_zones') for data in _iter())
        if condition == 'continuation_candle':
            return any(data.get('candle', {}).get('direction', 0) == direction for data in _iter())
        if condition == 'correlated_pair_divergence':
            for data in _iter():
                rsi, structure = data.get('rsi', 50), data.get('structure', 'RANGE')
                if (direction == 1 and structure == 'HH_HL' and rsi < 45) or \
                   (direction == -1 and structure == 'LH_LL' and rsi > 55):
                    return True
            return False
        if condition == 'entry_trigger':
            return True
        if condition in ('fib_level', 'fib_level_proximity'):
            return any(data.get('trend') != 'lateral' for data in _iter())
        if condition in ('ma_cross', 'ma_cross_signal', 'trend_confirm'):
            return regime.get('type') == 'trending'
        if condition == 'daily_structure':
            return True
        if condition == 'daily_structure_broken':
            return any(data.get('bos') for data in _iter())
        if condition == 'close_above':
            return any(data.get('trend') == 'alta' for data in _iter())
        if condition == 'multi_day_consolidation':
            return regime.get('type') in ('ranging', 'compression')
        if condition == 'range_narrowing':
            return any(data.get('bb_width', 100) < 1.5 for data in _iter())
        if condition == 'breakout_with_volume':
            return any(data.get('adx', 0) > 20 for data in _iter())
        if condition == 'turtle_breakout':
            for data in _iter():
                if direction == 1 and data.get('donchian_high_20', 0) and data['price'] > data['donchian_high_20']:
                    return True
                if direction == -1 and data.get('donchian_low_20', 0) and data['price'] < data['donchian_low_20']:
                    return True
            return False
        if condition == 'darvas_box':
            for data in _iter():
                box = data.get('darvas_box', {})
                if box.get('confirmed') and box.get('top', 0) > box.get('bottom', 0):
                    return True
            return False
        if condition == 'ca_range_defined':
            for data in _iter():
                if data.get('opening_range', {}).get('defined'):
                    return True
            return False
        if condition == 'c1_breakout':
            for data in _iter():
                opening = data.get('opening_range', {})
                price = data.get('price', 0)
                if opening.get('defined') and ((direction == 1 and price > opening.get('high', 0)) or (direction == -1 and price < opening.get('low', 0))):
                    if data.get('candle', {}).get('direction', 0) == direction and data.get('candle', {}).get('strength', 0) > 50:
                        return True
            return False
        if condition == 'breakout_directional':
            return any(data.get('candle', {}).get('direction', 0) == direction and data.get('candle', {}).get('strength', 0) > 40 for data in _iter())
        if condition == 'volume_at_zone':
            for data in _iter():
                price, atr = data.get('price', 0), data.get('atr', 1)
                if any(abs(price - zone.get('price', 0)) < atr * 0.6 for zone in data.get('sr_zones', [])):
                    return True
            return False
        if condition == 'volume_node_rejection':
            for data in _iter():
                price, profile = data.get('price', 0), data.get('volume_profile', {})
                if profile.get('defined') and profile.get('val', 0) <= price <= profile.get('vah', 0):
                    if data.get('candle', {}).get('direction', 0) == direction and data.get('volume_ratio', 0) >= 1.10:
                        return True
            return False
        if condition == 'anchored_vwap_aligned':
            for data in _iter():
                vwap = data.get('anchored_vwap', {}).get('value', 0)
                if vwap > 0 and ((direction == 1 and data['price'] > vwap) or (direction == -1 and data['price'] < vwap)):
                    return True
            return False
        if condition == 'anchored_vwap_retest':
            for data in _iter():
                vwap, atr = data.get('anchored_vwap', {}).get('value', 0), data.get('atr', 1)
                if vwap > 0 and abs(data.get('price', 0) - vwap) < atr * 0.35:
                    return True
            return False
        if condition == 'pullback_entry':
            for data in _iter():
                ema50 = data.get('ema50', 0)
                if ema50 > 0 and abs(data['price'] - ema50) / ema50 < 0.005:
                    return True
            return False
        if condition == 'candle_reaction':
            return any(data.get('candle', {}).get('strength', 0) > 40 for data in _iter())
        if condition == 'ema_cross_htf':
            for data in _iter():
                ema20, ema50 = data.get('ema20', 0), data.get('ema50', 0)
                if ema20 > 0 and ema50 > 0 and abs(ema20 - ema50) / ema50 < 0.005:
                    return True
            return False
        if condition == 'volume_divergence':
            return any(40 < data.get('rsi', 50) < 60 for data in _iter())
        if condition in ('entry_after_retest', 'retest_confirm'):
            return any(data.get('bos') or data.get('choch') for data in _iter())
        if condition == 'kill_zone_active':
            return datetime.now().hour in [8, 9, 13, 14, 15, 20]
        if condition == 'smart_money_entry':
            return any(data.get('ob_count', 0) > 0 or data.get('fvg_count', 0) > 0 for data in _iter())
        if condition == 'swing_range_defined':
            return any(len(data.get('swing_highs', [])) >= 2 and len(data.get('swing_lows', [])) >= 2 for data in _iter())
        if condition == 'price_in_discount':
            for data in _iter():
                sh, sl = data.get('swing_highs', []), data.get('swing_lows', [])
                price = data.get('price', 0)
                if sh and sl and price > 0:
                    high = max(s['price'] for s in sh)
                    low = min(s['price'] for s in sl)
                    mid = (high + low) / 2
                    if (direction == 1 and price < mid) or (direction == -1 and price > mid):
                        return True
            return False
        if condition == 'rejection_candle_htf':
            return any(data.get('candle', {}).get('strength', 0) > 40 for data in _iter())
        if condition == 'bos_after_sweep':
            return any(data.get('bos') for data in _iter())
        if condition == 'volume_accumulation':
            return any(data.get('adx', 0) < 20 for data in _iter())
        if condition == 'price_range_tight':
            return any(data.get('bb_width', 100) < 1.0 for data in _iter())
        if condition == 'impending_breakout':
            return any(15 < data.get('adx', 0) < 30 for data in _iter())
        if condition == 'vwap_real_detected':
            return any(data.get('vwap', 0) > 0 for data in _iter())
        if condition == 'price_at_vwap_band':
            for data in _iter():
                vwap_u = data.get('vwap_upper', 0)
                vwap_l = data.get('vwap_lower', 0)
                if vwap_u > 0 and vwap_l > 0:
                    if (direction == 1 and data['price'] <= vwap_l * 1.002) or \
                       (direction == -1 and data['price'] >= vwap_u * 0.998):
                        return True
            return False
        if condition == 'rsi_confirm_vwap':
            for data in _iter():
                rsi = data.get('rsi', 50)
                if (direction == 1 and rsi < 45) or (direction == -1 and rsi > 55):
                    return True
            return False
        if condition in ('macd_divergence_bull', 'macd_divergence'):
            for data in _iter():
                hist = data.get('macd_hist', 0)
                macd = data.get('macd', 0)
                sig = data.get('macd_signal', 0)
                if (direction == 1 and hist < 0 and macd > sig) or \
                   (direction == -1 and hist > 0 and macd < sig):
                    return True
            return False
        if condition == 'price_near_support':
            for data in _iter():
                price, atr = data['price'], data.get('atr', 1)
                for zone in data.get('sr_zones', []):
                    if abs(price - zone['price']) < atr * 0.5:
                        return True
            return False
        if condition == 'ichimoku_cloud_break':
            for data in _iter():
                ich = data.get('ichimoku', {})
                if (direction == 1 and ich.get('price_above_cloud')) or \
                   (direction == -1 and ich.get('price_below_cloud')):
                    return True
            return False
        if condition == 'tk_cross_confirm':
            for data in _iter():
                ich = data.get('ichimoku', {})
                if (direction == 1 and ich.get('tk_cross_bull')) or \
                   (direction == -1 and ich.get('tk_cross_bear')):
                    return True
            return False
        if condition == 'price_above_below_cloud':
            for data in _iter():
                ich = data.get('ichimoku', {})
                if (direction == 1 and ich.get('price_above_cloud')) or \
                   (direction == -1 and ich.get('price_below_cloud')):
                    return True
            return False
        if condition == 'gap_detected':
            return any(data.get('gap', {}).get('has_gap', False) for data in _iter())
        if condition == 'gap_filling':
            for data in _iter():
                gap = data.get('gap', {})
                if gap.get('has_gap', False):
                    price = data['price']
                    top, bot = gap.get('gap_top', 0), gap.get('gap_bot', 0)
                    if top > 0 and bot > 0 and min(top, bot) <= price <= max(top, bot):
                        return True
            return False
        if condition == 'london_session_active':
            return datetime.now().hour in [8, 9, 10, 11]
        if condition == 'asian_range_defined':
            for data in _iter():
                sh, sl = data.get('swing_highs', []), data.get('swing_lows', [])
                if sh and sl:
                    rng = abs(max(s['price'] for s in sh[-3:]) - min(s['price'] for s in sl[-3:]))
                    price = data.get('price', 0)
                    if price > 0 and 0.002 < rng / price < 0.015:
                        return True
            return False
        if condition == 'triangle_detected':
            for data in _iter():
                sh, sl = data.get('swing_highs', []), data.get('swing_lows', [])
                if len(sh) >= 2 and len(sl) >= 2:
                    if sh[-1]['price'] < sh[-2]['price'] and sl[-1]['price'] > sl[-2]['price']:
                        return True
                    if abs(sh[-1]['price'] - sh[-2]['price']) / max(sh[-1]['price'], 0.0001) < 0.003 and sl[-1]['price'] > sl[-2]['price']:
                        return True
            return False
        if condition == 'extended_from_ema':
            for data in _iter():
                ema50 = data.get('ema50', 0)
                atr = data.get('atr', 1)
                if ema50 > 0 and abs(data['price'] - ema50) > atr * 2:
                    return True
            return False
        if condition == 'divergence':
            return any(data.get('rsi', 50) > 65 or data.get('rsi', 50) < 35 for data in _iter())
        if condition == 'rejection_wick':
            for data in _iter():
                c = data.get('candle', {})
                if c.get('pattern', '').startswith('pin_bar') and c.get('strength', 0) > 30:
                    return True
            return False
        if condition == 'rejection_reaction':
            for data in _iter():
                c = data.get('candle', {})
                if c.get('direction', 0) == direction and c.get('strength', 0) > 30:
                    return True
            return False
        if condition == 'tight_range':
            return any(data.get('bb_width', 100) < 1.0 for data in _iter())
        if condition == 'volume_buildup':
            return any(data.get('adx', 0) < 25 for data in _iter())
        if condition == 'breakout_candle':
            for data in _iter():
                c = data.get('candle', {})
                if c.get('direction', 0) == direction and c.get('strength', 0) > 40:
                    return True
            return False
        if condition == 'pin_bar_rejection':
            for data in _iter():
                c = data.get('candle', {})
                if c.get('pattern', '').startswith('pin_bar') and c.get('strength', 0) > 30:
                    return True
            return False
        return False

    # ═══ SIGNAL DEDUPLICATION ═══

    def _deduplicate_signals(self, setups):
        """Remove sinais duplicados — keep highest score per direction+region"""
        seen = {}
        result = []
        for s in setups:
            if s.readiness < 30:
                result.append(s)
                continue
            key = "%s_%s" % (s.direction, s.mode)
            if key not in seen or s.readiness > seen[key].readiness:
                if key in seen:
                    result.remove(seen[key])
                seen[key] = s
                result.append(s)
            else:
                result.append(s)
        return result

    # ═══ CORRELATION FILTER ═══

    def _check_correlation_exposure(self, symbol, direction, open_positions):
        """Check if we already have a correlated position in the same direction"""
        corr = CORRELATED_PAIRS.get(symbol, '')
        if not corr:
            return True
        for pos in open_positions:
            if pos.get('symbol') == corr and pos.get('direction') == direction:
                return False
        return True

    # ═══ MAIN SCAN ═══

    def scan_symbol(self, symbol):
        self._candle_cache = {}
        info = self._ensure_symbol(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if not info or not tick:
            return AssetScan(symbol=symbol, price=0, spread=0, regime='unknown', regime_score=0,
                             setups=[], best_setup=None, scan_time=datetime.now().isoformat(),
                             category=ASSET_CATEGORIES.get(symbol, 'unknown'))
        price = (tick.bid + tick.ask) / 2
        spread = info.spread
        category = ASSET_CATEGORIES.get(symbol, 'unknown')
        pip = PIP_VALUES.get(symbol, 0.0001)
        spread_usd = spread * pip
        candles_h1 = self._get_candles(symbol, 'H1', 60)
        candles_m15 = self._get_candles(symbol, 'M15', 60)
        candles_m5 = self._get_candles(symbol, 'M5', 60)
        atr_h1 = self._atr(candles_h1, 14) if len(candles_h1) > 14 else 0.0
        atr_m15 = self._atr(candles_m15, 14) if len(candles_m15) > 14 else 0.0
        atr_m5 = self._atr(candles_m5, 14) if len(candles_m5) > 14 else 0.0
        trend_h4 = self._get_trend(symbol, 'H4')
        trend_h1 = self._get_trend(symbol, 'H1')
        trend_m15 = self._get_trend(symbol, 'M15')
        trend_m5 = self._get_trend(symbol, 'M5')
        rsi_h1 = self._get_rsi(symbol, 'H1')
        rsi_m15 = self._get_rsi(symbol, 'M15')
        adx = self._adx(candles_h1, 14) if len(candles_h1) > 14 else 0.0
        h1_volumes = [float(c.get('vol', 0) or 0) for c in candles_h1]
        h1_volume_avg = sum(h1_volumes[:-1]) / max(len(h1_volumes) - 1, 1)
        volume_ratio = h1_volumes[-1] / h1_volume_avg if h1_volumes and h1_volume_avg > 0 else 0.0
        closes_h1 = [c['close'] for c in candles_h1] if candles_h1 else []
        _, _, _, bb_width = self._bollinger(closes_h1) if closes_h1 else (0, 0, 0, 0)
        structure = self._detect_structure(candles_h1) if len(candles_h1) >= 50 else {'type': 'RANGE'}
        structure_htf = structure.get('type', 'RANGE')
        bias = 'BULLISH' if structure_htf == 'HH_HL' else ('BEARISH' if structure_htf == 'LH_LL' else 'NEUTRAL')
        sr_zones = self._detect_sr_zones(candles_h1) if candles_h1 else []
        key_zones = len(sr_zones)
        nearest_zone_dist = 0
        if sr_zones and atr_h1 > 0:
            nearest = min(abs(price - z['price']) for z in sr_zones)
            nearest_zone_dist = nearest / atr_h1
        candles_d1 = self._get_candles(symbol, 'D1', 2)
        daily_range_pct = 0.0
        daily_range_pts = 0.0
        if candles_d1 and len(candles_d1) >= 2:
            daily_range_pts = candles_d1[-1]['high'] - candles_d1[-1]['low']
            if price > 0:
                daily_range_pct = (daily_range_pts / price) * 100
        volatility = 'NORMAL'
        if atr_h1 > 0 and len(candles_h1) >= 50:
            atr_long = self._atr(candles_h1, 50)
            if atr_long > 0:
                vol_ratio = atr_h1 / atr_long
                if vol_ratio > 1.5: volatility = 'EXTREME'
                elif vol_ratio > 1.2: volatility = 'HIGH'
                elif vol_ratio < 0.7: volatility = 'LOW'
        session = self._get_session()
        best_sessions = BEST_SESSIONS.get(category, BEST_SESSIONS['forex'])
        session_active = datetime.now().hour in best_sessions
        pips_today = 0.0
        if candles_d1 and len(candles_d1) >= 2:
            open_price = candles_d1[-1]['open']
            if open_price > 0 and price > 0:
                pips_today = (price - open_price) / pip
        swap_buy = info.swap_long if hasattr(info, 'swap_long') else 0
        swap_sell = info.swap_short if hasattr(info, 'swap_short') else 0
        regime = self._detect_regime(symbol)

        # Pre-cache TF data
        tf_data_cache = {}
        for tf in ['M1', 'M5', 'M15', 'H1', 'H4', 'D1']:
            tf_data_cache["%s_%s" % (symbol, tf)] = self._analyze_tf(symbol, tf)

        # Evaluate all setups
        setups = []
        for setup_id, setup_def in self.setups.items():
            if category == 'crypto' and setup_def.get('mode') == 'swing':
                continue
            state = self._evaluate_setup(symbol, setup_id, setup_def, regime, tf_data_cache)
            setups.append(state)

        # Sort by readiness
        setups.sort(key=lambda s: s.readiness, reverse=True)

        # Count by mode
        scalp_count = sum(1 for s in setups if s.mode == 'scalp' and s.readiness > 0)
        day_count = sum(1 for s in setups if s.mode == 'day' and s.readiness > 0)
        swing_count = sum(1 for s in setups if s.mode == 'swing' and s.readiness > 0)

        # Best setup
        best = None
        for s in setups:
            if s.readiness > 40 and s.rr_ratio >= s.score * 0.015:
                best = s
                break
        if best is None and setups and setups[0].readiness > 30:
            best = setups[0]

        top_setups = [s.name for s in setups[:3] if s.readiness > 40]
        alert_level = best.level_label if best else 'NENHUM'

        # Score total (7-factor weighted)
        score_total = 0.0
        if best:
            score_total += best.readiness * 0.50
            score_total += best.confluence_score * 0.15
        if bias in ('BULLISH', 'BEARISH'):
            score_total += 10
        if regime['type'] == 'trending':
            score_total += 10
        elif regime['type'] == 'ranging':
            score_total += 5
        if volatility in ('NORMAL', 'HIGH'):
            score_total += 10
        if session_active:
            score_total += 5
        score_total = min(100, score_total)

        return AssetScan(
            symbol=symbol, price=price, spread=spread, regime=regime.get('type', 'unknown'),
            regime_score=regime.get('score', 0), setups=setups, best_setup=best,
            scan_time=datetime.now().isoformat(), category=category,
            atr_h1=round(atr_h1, 5), atr_m15=round(atr_m15, 5), atr_m5=round(atr_m5, 5),
            daily_range_pct=round(daily_range_pct, 3), daily_range_pts=round(daily_range_pts, 5),
            trend_h4=trend_h4, trend_h1=trend_h1, trend_m15=trend_m15, trend_m5=trend_m5,
            rsi_h1=round(rsi_h1, 1), rsi_m15=round(rsi_m15, 1),
            volatility=volatility, session=session, pips_today=round(pips_today, 1),
            spread_usd=round(spread_usd, 4), score_total=round(score_total, 1),
            top_setups=top_setups, alert_level=alert_level, session_active=session_active,
            pip_value=pip, swap_buy=round(swap_buy, 2), swap_sell=round(swap_sell, 2),
            structure_htf=structure_htf, bias=bias, key_zones=key_zones,
            nearest_zone_dist=round(nearest_zone_dist, 2), bb_width=round(bb_width, 3),
            adx=round(adx, 1),
            volume_ratio=round(volume_ratio, 2),
            scalp_count=scalp_count, day_count=day_count, swing_count=swing_count,
        )

    def scan_all(self):
        results = []
        for symbol in self.RADAR_SYMBOLS:
            try:
                scan = self.scan_symbol(symbol)
                results.append(scan)
            except Exception as e:
                print("[SCANNER] Erro ao scannear %s: %s" % (symbol, str(e)[:80]))
        return results
