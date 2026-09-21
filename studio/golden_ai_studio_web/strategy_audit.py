"""Auditoria de qualidade das estrategias do Radar.

Esta camada nao afirma que uma estrategia e lucrativa. Ela verifica se o
Radar possui dados e uma implementacao adequada para testar cada regra.
"""
from functools import lru_cache


# Condicoes que o scanner mede diretamente com os campos calculados por TF.
DIRECT_CONDITIONS = {
    'adx_strong_trend', 'atr_elevated', 'bb_squeeze', 'bb_squeeze_detect',
    'bb_squeeze_htf', 'candle_reaction', 'candle_reversal', 'close_above',
    'close_beyond_vwap', 'consolidation_detected', 'continuation_candle',
    'directional_candle', 'ema_alignment', 'ema_cross_fast', 'ema_pullback',
    'ema_slope_strong', 'ema_trend_aligned', 'engulfing_pattern',
    'false_break_wick', 'fib_level_proximity', 'follow_through', 'fvg_detected',
    'kill_zone_active', 'liquidity_sweep_htf', 'micro_pullback_ema',
    'momentum_fading', 'momentum_weakening', 'near_sr_level', 'ob_identified',
    'ob_htf_identified', 'opening_range_defined', 'order_block_detected',
    'pin_bar_rejection', 'price_at_vwap_band', 'price_in_discount',
    'price_returning_to_fvg', 'pullback_to_vwap', 'pullback_to_zone',
    'range_narrowing', 'reaction_at_fvg', 'reaction_at_ob', 'rejection_at_ob',
    'rejection_candle', 'rejection_candle_htf', 'rejection_reaction',
    'retest_and_hold', 'retest_confirm', 'retest_ob_zone', 'retest_zone',
    'reversal_candle', 'reversal_confirm', 'reversal_pattern',
    'reversal_pattern_htf', 'rsi_extreme', 'rsi_extreme_reversal',
    'rsi_momentum_zone', 'session_extreme', 'smart_money_entry',
    'sr_level_proximity', 'sr_multi_touch', 'stoch_extreme', 'strong_trend',
    'strong_trend_m1', 'structure_confirm', 'structure_level', 'structure_shift',
    'sweep_detected', 'swing_range_defined', 'tight_range', 'trend_aligned',
    'trend_strong', 'vwap_extended', 'vwap_real_detected', 'vwap_cross_decisive',
    'vwap_trend_aligned', 'volume_decreasing_pullback', 'volume_accumulation',
    'volume_at_extreme', 'volume_buildup', 'volume_confirm', 'volume_surge',
    'volume_spike', 'volume_above_avg', 'vwma_direction_aligned', 'zone_identified',
}

# A implementacao atual usa outro indicador como aproximacao desta regra.
PROXY_CONDITIONS = {
    'breakout_confirmed', 'breakout_directional', 'breakout_volume',
    'breakout_with_volume', 'bos_after_sweep', 'bos_confirmation', 'bos_detected',
    'choch_detected', 'daily_choch', 'daily_structure_broken', 'displacement',
    'displacement_before_ob', 'displacement_into_ob', 'divergence',
    'entry_after_retest', 'entry_trigger', 'expansion_start', 'expansion_starting',
    'ma_cross_signal', 'macd_divergence_bull', 'momentum_spike', 'price_displacement',
    'price_near_support', 'retest_confirm', 'reversal_confirm', 'volume_at_zone',
    'volume_divergence',
}

# Sem medicao fiel no OHLCV atualmente; deve ficar fora do auto-trade.
UNSUPPORTED_CONDITIONS = {
    'correlated_pair_divergence', 'extended_from_ema', 'gap_detected', 'gap_filling',
    'ichimoku_cloud_break', 'price_above_below_cloud', 'price_returning',
    'trend_strength', 'tk_cross_confirm', 'triangle_detected',
}


def audit_condition(condition):
    if condition in UNSUPPORTED_CONDITIONS:
        return 'UNSUPPORTED'
    if condition in PROXY_CONDITIONS:
        return 'PROXY'
    if condition in DIRECT_CONDITIONS:
        return 'DIRECT'
    return 'UNSUPPORTED'


@lru_cache(maxsize=1)
def audit_all_strategies():
    from golden_scanner import SETUP_DEFINITIONS
    result = {}
    for strategy_id, definition in SETUP_DEFINITIONS.items():
        conditions = list(definition.get('conditions', []))
        condition_status = [{'condition': c, 'status': audit_condition(c)} for c in conditions]
        direct = sum(1 for c in condition_status if c['status'] == 'DIRECT')
        proxy = sum(1 for c in condition_status if c['status'] == 'PROXY')
        unsupported = sum(1 for c in condition_status if c['status'] == 'UNSUPPORTED')
        coverage = (direct + proxy * 0.5) / len(conditions) if conditions else 0
        if unsupported:
            recommendation = 'REFAZER'
        elif coverage >= 0.8:
            recommendation = 'MANTER'
        else:
            recommendation = 'OBSERVAR'
        result[strategy_id] = {
            'strategy_id': strategy_id,
            'name': definition.get('name', strategy_id),
            'mode': definition.get('mode', 'day'),
            'tier': definition.get('tier', 'C'),
            'conditions': condition_status,
            'direct_conditions': direct,
            'proxy_conditions': proxy,
            'unsupported_conditions': unsupported,
            'coverage_score': round(coverage * 100, 1),
            'recommendation': recommendation,
            'auto_trade_eligible': recommendation == 'MANTER',
        }
    return result


def get_audit_summary():
    audits = audit_all_strategies()
    return {
        'total': len(audits),
        'keep': sum(1 for a in audits.values() if a['recommendation'] == 'MANTER'),
        'observe': sum(1 for a in audits.values() if a['recommendation'] == 'OBSERVAR'),
        'refactor': sum(1 for a in audits.values() if a['recommendation'] == 'REFAZER'),
        'direct_conditions': sum(a['direct_conditions'] for a in audits.values()),
        'proxy_conditions': sum(a['proxy_conditions'] for a in audits.values()),
        'unsupported_conditions': sum(a['unsupported_conditions'] for a in audits.values()),
    }

