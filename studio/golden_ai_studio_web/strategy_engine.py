"""Catalogo unificado de estrategias do GoldenAI.

O Radar e o backtest usam IDs diferentes historicamente. Este modulo e o
contrato comum: cada estrategia tem identidade, origem e adaptador de execucao.
"""
from functools import lru_cache
from pathlib import Path
import re


GENERIC_STRATEGIES = {
    'ma_cross': {'name': 'Medias Moveis', 'mode': 'day', 'kind': 'generic', 'adapter': 'ma_cross'},
    'rsi_reversal': {'name': 'RSI Reversao', 'mode': 'day', 'kind': 'generic', 'adapter': 'rsi_reversal'},
    'bollinger': {'name': 'Bollinger', 'mode': 'day', 'kind': 'generic', 'adapter': 'bollinger'},
    'macd': {'name': 'MACD', 'mode': 'day', 'kind': 'generic', 'adapter': 'macd'},
    'scalping': {'name': 'Scalping EMA + ATR', 'mode': 'scalp', 'kind': 'generic', 'adapter': 'scalping'},
    'breakout': {'name': 'Breakout', 'mode': 'day', 'kind': 'generic', 'adapter': 'breakout'},
}


def _radar_adapter(strategy_id, definition):
    """Escolhe o adaptador historico mais proximo para o setup do Radar."""
    sid = strategy_id.upper()
    exact_adapters = {
        'SWING_TURTLE_BREAKOUT': 'turtle_breakout',
        'SWING_DARVAS_BOX': 'darvas_box',
        'DAY_CA_C1': 'ca_c1',
        'DAY_VOLUME_PROFILE_REJECTION': 'volume_profile_rejection',
        'DAY_VWAP_ANCHORED': 'vwap_anchored',
    }
    if sid in exact_adapters:
        return exact_adapters[sid]
    if any(k in sid for k in ('REVERSAL', 'FADE', 'REJECTION', 'FALSE_BREAK', 'MEAN_RETURN', 'GAP_FILL', 'LIQ_')):
        return 'rsi_reversal'
    if any(k in sid for k in ('BRK', 'BREAKOUT', 'ORB', 'BOS', 'CHOCH', 'COMPRESSION', 'TRIANGLE')):
        return 'breakout'
    if definition.get('mode') == 'scalp':
        return 'scalping'
    return 'ma_cross'


MT5_ROBOTS_DIR = Path(r'C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts')


def _robot_entries():
    """Transforma EAs reais em itens do mesmo catalogo consumido pelo Radar."""
    result = {}
    if not MT5_ROBOTS_DIR.exists():
        return result
    for path in MT5_ROBOTS_DIR.rglob('*.mq5'):
        try:
            code = path.read_text(encoding='utf-8', errors='replace')
            stem_key = path.stem.lower()
            is_ciclos = 'ciclos' in stem_key
            # O Master EX5 e o Bot Ciclos EA MQ5 representam a mesma familia.
            # Mantemos o MQ5 como fonte de verdade para analise e compilacao.
            robot_id = 'robot:ciclos_ea' if is_ciclos and ('bot ciclos ea' in stem_key or 'ciclosea_master' in stem_key) else 'robot:' + re.sub(r'[^a-z0-9_]+', '_', stem_key).strip('_')
            if robot_id == 'robot:ciclos_ea' and path.stem != 'Bot Ciclos EA':
                canonical = path.with_name('Bot Ciclos EA.mq5')
                if canonical.exists():
                    continue
            master_binary = path.parent / 'CiclosEA_Master.ex5'
            compiled = path.with_suffix('.ex5').exists() or (is_ciclos and master_binary.exists())
            indicators = []
            for token in ('iMA', 'iRSI', 'iBands', 'iMACD', 'iATR', 'iADX', 'iStochastic', 'iIchimoku'):
                if token in code:
                    indicators.append(token)
            mode = 'scalp' if any(x in code.lower() for x in ('scalp', 'm1', 'm5')) else 'swing' if any(x in code.lower() for x in ('swing', 'd1', 'h4')) else 'day'
            adapter = 'opening_cycle' if is_ciclos else 'robot'
            related = [str(path.with_suffix('.ex5'))] if path.with_suffix('.ex5').exists() else []
            if is_ciclos and master_binary.exists() and str(master_binary) not in related:
                related.append(str(master_binary))
            quality = 35 if compiled else 20
            quality += min(30, len(indicators) * 5)
            quality += 20 if 'OnTick' in code else 0
            result[robot_id] = {
                'name': path.stem,
                'mode': mode,
                'kind': 'robot',
                'adapter': adapter,
                'source_path': str(path),
                'compiled': compiled,
                'family': 'Bot Ciclos' if is_ciclos else path.stem,
                'related_files': related,
                'binary_note': 'CiclosEA_Master.ex5 relacionado; analise baseada no codigo MQ5.' if is_ciclos else '',
                'indicators': indicators,
                'quality_score': min(100, quality),
                'audit_recommendation': 'OBSERVAR' if not compiled else 'MANTER',
                'auto_trade_eligible': False,
                'description': 'EA real do MetaTrader 5; exige backtest e validacao proprios.',
            }
        except OSError:
            continue
    return result


@lru_cache(maxsize=1)
def get_strategy_catalog():
    catalog = dict(GENERIC_STRATEGIES)
    try:
        from golden_scanner import SETUP_DEFINITIONS
        from strategy_audit import audit_all_strategies
        audits = audit_all_strategies()
        for strategy_id, definition in SETUP_DEFINITIONS.items():
            audit = audits.get(strategy_id, {})
            catalog[strategy_id] = {
                'name': definition.get('name', strategy_id),
                'mode': definition.get('mode', 'day'),
                'tier': definition.get('tier', 'C'),
                'description': definition.get('description', ''),
                'min_rr': definition.get('min_rr', 1.5),
                'kind': 'radar',
                'adapter': _radar_adapter(strategy_id, definition),
                'conditions': definition.get('conditions', []),
                'audit_recommendation': audit.get('recommendation', 'OBSERVAR'),
                'coverage_score': audit.get('coverage_score', 0),
                'quality_score': audit.get('coverage_score', 0),
                'auto_trade_eligible': audit.get('auto_trade_eligible', False),
            }
    except Exception:
        pass
    catalog.update(_robot_entries())
    return catalog


def list_strategies(kind=None, mode=None):
    result = []
    for strategy_id, item in get_strategy_catalog().items():
        if kind and item.get('kind') != kind:
            continue
        if mode and item.get('mode') != mode:
            continue
        result.append({'id': strategy_id, **item})
    return sorted(result, key=lambda x: (x.get('kind') != 'radar', x.get('mode', ''), x['id']))


def resolve_strategy(strategy_id):
    item = get_strategy_catalog().get(strategy_id)
    if item:
        return strategy_id, item
    return 'ma_cross', GENERIC_STRATEGIES['ma_cross']


def strategy_score(item, backtest=None, validation=None):
    """Score explicavel, sem transformar retorno isolado em autorizacao de trade."""
    score = float(item.get('quality_score', item.get('coverage_score', 50)))
    if item.get('audit_recommendation') == 'REFAZER':
        score -= 25
    if item.get('compiled') is False and item.get('kind') == 'robot':
        score -= 20
    if backtest:
        stats = backtest.get('stats', backtest)
        score += min(15, max(-15, float(stats.get('profit_factor', 1)) - 1) * 8)
        score += min(10, max(-10, float(stats.get('win_rate', 50)) - 50) / 2)
        score -= min(20, float(stats.get('max_drawdown', stats.get('max_drawdown_pct', 0))) / 3)
    if validation:
        score += min(15, float(validation.get('confidence', validation.get('robustness_score', 0))) / 10)
    return round(max(0, min(100, score)), 1)
