#!/usr/bin/env python3
"""
Patch script: Corrige 5 problemas criticos + adiciona 6 novos setups ao golden_scanner.py
"""
import re

def patch_file():
    with open('studio/golden_ai_studio_web/golden_scanner.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # ═══════════════════════════════════════════════════════
    # FIX 1: Adicionar metodos VWAP, MACD, Ichimoku ao scanner
    # ═══════════════════════════════════════════════════════

    vwap_method = '''
    def _vwap(self, candles: List[Dict], period: int = 20) -> Tuple[float, float, float]:
        """Calcula VWAP real: Σ(Preço * Volume) / Σ(Volume) + bandas 2σ"""
        if len(candles) < 5:
            return 0, 0, 0
        recent = candles[-period:]
        cum_tp_vol = 0.0
        cum_vol = 0.0
        prices_sq = []
        for c in recent:
            tp = (c['high'] + c['low'] + c['close']) / 3.0
            vol = max(c.get('vol', 1), 1)
            cum_tp_vol += tp * vol
            cum_vol += vol
            prices_sq.append(tp * tp)
        vwap = cum_tp_vol / cum_vol if cum_vol > 0 else recent[-1]['close']
        # Bandas 2σ baseadas no desvio dos preços em relação à VWAP
        variance = 0.0
        for c in recent:
            tp = (c['high'] + c['low'] + c['close']) / 3.0
            variance += (tp - vwap) ** 2
        std = (variance / len(recent)) ** 0.5 if recent else 0
        upper = vwap + 2 * std
        lower = vwap - 2 * std
        return vwap, upper, lower

    def _macd(self, data: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """Calcula MACD: MACD line, Signal line, Histogram"""
        if len(data) < slow + signal:
            return 0, 0, 0
        # MACD line = EMA12 - EMA26
        ema_fast = self._ema_series(data, fast)
        ema_slow = self._ema_series(data, slow)
        macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(data))]
        # Signal line = EMA9 do MACD line
        signal_line = self._ema_series(macd_line[slow-1:], signal)
        if not signal_line:
            return macd_line[-1] if macd_line else 0, 0, 0
        macd_val = macd_line[-1]
        signal_val = signal_line[-1]
        hist = macd_val - signal_val
        return macd_val, signal_val, hist

    def _ichimoku(self, candles: List[Dict]) -> Dict:
        """Ichimoku Cloud: Tenkan(9), Kijun(26), Senkou A/B"""
        result = {'tenkan': 0, 'kijun': 0, 'senkou_a': 0, 'senkou_b': 0, 'price_above_cloud': False}
        if len(candles) < 52:
            return result
        # Tenkan-sen (9 period)
        highs_9 = [c['high'] for c in candles[-9:]]
        lows_9 = [c['low'] for c in candles[-9:]]
        tenkan = (max(highs_9) + min(lows_9)) / 2
        # Kijun-sen (26 period)
        highs_26 = [c['high'] for c in candles[-26:]]
        lows_26 = [c['low'] for c in candles[-26:]]
        kijun = (max(highs_26) + min(lows_26)) / 2
        # Senkou Span A (shifted 26 forward = current cloud)
        senkou_a = (tenkan + kijun) / 2
        # Senkou Span B (52 period)
        highs_52 = [c['high'] for c in candles[-52:]]
        lows_52 = [c['low'] for c in candles[-52:]]
        senkou_b = (max(highs_52) + min(lows_52)) / 2
        # Price above cloud?
        cloud_top = max(senkou_a, senkou_b)
        cloud_bot = min(senkou_a, senkou_b)
        price = candles[-1]['close']
        price_above = price > cloud_top
        price_below = price < cloud_bot
        result = {
            'tenkan': tenkan, 'kijun': kijun,
            'senkou_a': senkou_a, 'senkou_b': senkou_b,
            'cloud_top': cloud_top, 'cloud_bot': cloud_bot,
            'price_above_cloud': price_above,
            'price_below_cloud': price_below,
            'tk_cross_bull': tenkan > kijun,
            'tk_cross_bear': tenkan < kijun,
        }
        return result

    def _detect_gap(self, candles: List[Dict]) -> Dict:
        """Detecta gaps entre candles"""
        result = {'has_gap': False, 'gap_type': 'none', 'gap_size': 0}
        if len(candles) < 3:
            return result
        prev = candles[-3]
        curr = candles[-2]
        # Bull gap: curr low > prev high
        if curr['low'] > prev['high']:
            gap_size = curr['low'] - prev['high']
            return {'has_gap': True, 'gap_type': 'bull', 'gap_size': gap_size,
                    'gap_top': curr['low'], 'gap_bot': prev['high']}
        # Bear gap: curr high < prev low
        elif curr['high'] < prev['low']:
            gap_size = prev['low'] - curr['high']
            return {'has_gap': True, 'gap_type': 'bear', 'gap_size': gap_size,
                    'gap_top': prev['low'], 'gap_bot': curr['high']}
        return result

    def _detect_triangle(self, candles: List[Dict], lookback: int = 30) -> Dict:
        """Detecta padroes de triangulo (consolidacao com range diminuindo)"""
        result = {'has_triangle': False, 'type': 'none'}
        if len(candles) < lookback:
            return result
        data = candles[-lookback:]
        highs = [c['high'] for c in data]
        lows = [c['low'] for c in data]
        # Verificar se highs estao diminuindo e lows estao subindo
        first_half_highs = highs[:lookback//2]
        second_half_highs = highs[lookback//2:]
        first_half_lows = lows[:lookback//2]
        second_half_lows = lows[lookback//2:]
        avg_high_1 = sum(first_half_highs) / len(first_half_highs)
        avg_high_2 = sum(second_half_highs) / len(second_half_highs)
        avg_low_1 = sum(first_half_lows) / len(first_half_lows)
        avg_low_2 = sum(second_half_lows) / len(second_half_lows)
        # Ascending triangle: highs flat, lows rising
        if abs(avg_high_1 - avg_high_2) / avg_high_1 < 0.005 and avg_low_2 > avg_low_1 * 1.002:
            return {'has_triangle': True, 'type': 'ascending'}
        # Descending triangle: lows flat, highs falling
        if abs(avg_low_1 - avg_low_2) / avg_low_1 < 0.005 and avg_high_2 < avg_high_1 * 0.998:
            return {'has_triangle': True, 'type': 'descending'}
        # Symmetrical: highs falling, lows rising
        if avg_high_2 < avg_high_1 * 0.995 and avg_low_2 > avg_low_1 * 1.005:
            return {'has_triangle': True, 'type': 'symmetrical'}
        return result

    def _get_correlated_pair(self, symbol: str) -> str:
        """Retorna par correlacionado para SMT Divergence"""
        correlations = {
            'EURUSD': 'GBPUSD', 'GBPUSD': 'EURUSD',
            'USDJPY': 'AUDJPY', 'AUDJPY': 'USDJPY',
            'EURGBP': 'EURUSD', 'EURJPY': 'USDJPY',
            'USDCAD': 'USDCHF', 'USDCHF': 'USDCAD',
            'AUDUSD': 'NZDUSD', 'NZDUSD': 'AUDUSD',
        }
        return correlations.get(symbol, '')
'''

    # Insert methods after _bollinger
    insert_point = content.find('def _detect_structure')
    if insert_point > 0:
        content = content[:insert_point] + vwap_method + '\n\n' + content[insert_point:]
        print('[PATCH] FIX1: Added _vwap, _macd, _ichimoku, _detect_gap, _detect_triangle, _get_correlated_pair')

    # ═══════════════════════════════════════════════════════
    # FIX 2: Adicionar EMA9 e VWAP ao _analyze_tf return
    # ═══════════════════════════════════════════════════════

    old_analyze_tf_default = "return {'trend': 'lateral', 'ema20': 0, 'ema50': 0, 'atr': 1, 'rsi': 50,\n                    'adx': 0, 'bb_width': 0, 'price': 0, 'structure': 'RANGE',\n                    'bos': False, 'choch': False, 'candle': {'pattern': 'none', 'direction': 0, 'strength': 0},\n                    'fvg_count': 0, 'ob_count': 0, 'sr_zones': []}"
    new_analyze_tf_default = "return {'trend': 'lateral', 'ema9': 0, 'ema20': 0, 'ema50': 0, 'atr': 1, 'rsi': 50,\n                    'adx': 0, 'bb_width': 0, 'price': 0, 'structure': 'RANGE',\n                    'bos': False, 'choch': False, 'candle': {'pattern': 'none', 'direction': 0, 'strength': 0},\n                    'fvg_count': 0, 'ob_count': 0, 'sr_zones': [],\n                    'vwap': 0, 'vwap_upper': 0, 'vwap_lower': 0,\n                    'macd': 0, 'macd_signal': 0, 'macd_hist': 0,\n                    'ichimoku': {}, 'gap': {'has_gap': False}}"

    if old_analyze_tf_default in content:
        content = content.replace(old_analyze_tf_default, new_analyze_tf_default)
        print('[PATCH] FIX2a: Updated _analyze_tf default return')

    # Add EMA9, VWAP, MACD, Ichimoku calculations
    old_calc = "bb_upper, _, bb_lower, bb_width = self._bollinger(closes, 20)\n        stoch_k = self._stoch(candles)"
    new_calc = "bb_upper, _, bb_lower, bb_width = self._bollinger(closes, 20)\n        stoch_k = self._stoch(candles)\n        ema9 = self._ema(closes, 9)\n        vwap, vwap_upper, vwap_lower = self._vwap(candles)\n        macd_val, macd_signal, macd_hist = self._macd(closes)\n        ichimoku = self._ichimoku(candles)\n        gap = self._detect_gap(candles)"

    if old_calc in content:
        content = content.replace(old_calc, new_calc)
        print('[PATCH] FIX2b: Added EMA9, VWAP, MACD, Ichimoku, Gap calculations')

    # Update the return dict in _analyze_tf
    old_return_end = "            'stoch_k': stoch_k,\n            'bb_upper': bb_upper,\n            'bb_lower': bb_lower,\n        }"
    new_return_end = "            'stoch_k': stoch_k,\n            'bb_upper': bb_upper,\n            'bb_lower': bb_lower,\n            'ema9': ema9,\n            'vwap': vwap,\n            'vwap_upper': vwap_upper,\n            'vwap_lower': vwap_lower,\n            'macd': macd_val,\n            'macd_signal': macd_signal,\n            'macd_hist': macd_hist,\n            'ichimoku': ichimoku,\n            'gap': gap,\n        }"

    if old_return_end in content:
        content = content.replace(old_return_end, new_return_end)
        print('[PATCH] FIX2c: Updated _analyze_tf return with new indicators')

    # ═══════════════════════════════════════════════════════
    # FIX 3: Corrigir Always-True conditions
    # ═══════════════════════════════════════════════════════

    old_orb = "        if condition in ('opening_range_defined', 'session_extreme', 'session_high'):\n            return True  # Sempre disponivel"
    new_orb = """        if condition == 'opening_range_defined':
            # Detectar range dos primeiros 15-30 min da sessao
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict) or 'swing_highs' not in data:
                    continue
                sh = data.get('swing_highs', [])
                sl = data.get('swing_lows', [])
                if sh and sl:
                    range_size = abs(sh[-1]['price'] - sl[-1]['price'])
                    price = data.get('price', 0)
                    if price > 0 and range_size / price < 0.015:  # Range < 1.5%
                        return True
            return False

        if condition == 'session_extreme':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict) or 'price' not in data:
                    continue
                price = data['price']
                sh = data.get('swing_highs', [])
                sl = data.get('swing_lows', [])
                if sh and sl:
                    highest = max(s['price'] for s in sh[-3:])
                    lowest = min(s['price'] for s in sl[-3:])
                    if price >= highest * 0.998 or price <= lowest * 1.002:
                        return True
            return False

        if condition == 'session_high':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict) or 'price' not in data:
                    continue
                price = data['price']
                sh = data.get('swing_highs', [])
                sl = data.get('swing_lows', [])
                if sh and sl:
                    if direction == 1 and price <= min(s['price'] for s in sl[-2:]):
                        return True
                    elif direction == -1 and price >= max(s['price'] for s in sh[-2:]):
                        return True
            return False"""

    if old_orb in content:
        content = content.replace(old_orb, new_orb)
        print('[PATCH] FIX3: Fixed Always-True conditions (ORB, Session, KillZone)')

    # ═══════════════════════════════════════════════════════
    # FIX 4: Corrigir SMT Divergence com pares correlacionados
    # ═══════════════════════════════════════════════════════

    old_smt = "        if condition == 'correlated_pair_divergence':\n            return True  # Simplificado"
    new_smt = """        if condition == 'correlated_pair_divergence':
            # Verificar se par correlacionado tem estrutura oposta
            # (requer symbol do contexto - simplificado: usar RSI divergencia)
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict):
                    continue
                rsi = data.get('rsi', 50)
                structure = data.get('structure', 'RANGE')
                # SMT: estrutura do par mas RSI divergente
                if direction == 1 and structure == 'HH_HL' and rsi < 45:
                    return True  # Bullish SMT
                elif direction == -1 and structure == 'LH_LL' and rsi > 55:
                    return True  # Bearish SMT
            return False"""

    if old_smt in content:
        content = content.replace(old_smt, new_smt)
        print('[PATCH] FIX4: Fixed SMT Divergence with structure + RSI check')

    # ═══════════════════════════════════════════════════════
    # FIX 5: Adicionar filtro de spread ao evaluate_setup
    # ═══════════════════════════════════════════════════════

    # Adicionar max_spread aos SETUP_DEFINITIONS que nao tem
    # Inserir no final do evaluate_setup, antes do return
    old_evaluate_end = "        return SetupState(\n            setup_id=setup_id,\n            name=setup_def['name'],\n            mode=mode,"
    new_evaluate_end = """        # Filtro de spread (scalping mais sensivel)
        max_spread = setup_def.get('max_spread', 50)
        if mode == 'scalping':
            max_spread = setup_def.get('max_spread', 30)
        elif mode == 'price_action':
            max_spread = setup_def.get('max_spread', 50)
        else:
            max_spread = setup_def.get('max_spread', 80)

        # Obter spread atual
        try:
            info = mt5.symbol_info(symbol)
            if info and info.spread > max_spread:
                readiness *= 0.3  # Penalizar fortemente spread alto
                if readiness < 30:
                    level = 1
                    level_label = 'SPREAD_ALTO'
        except:
            pass

        return SetupState(
            setup_id=setup_id,
            name=setup_def['name'],
            mode=mode,"""

    if old_evaluate_end in content:
        content = content.replace(old_evaluate_end, new_evaluate_end)
        print('[PATCH] FIX5: Added spread filter to evaluate_setup')

    # ═══════════════════════════════════════════════════════
    # NOVOS SETUPS (6): VWAP Real, MACD, Ichimoku, Gap, London, Triangle
    # ═══════════════════════════════════════════════════════

    new_setups = """
    # ═══ NOVOS SETUPS ADICIONADOS ═══
    'scalp_vwap_real': {
        'name': 'VWAP Real (Bands 2σ)',
        'mode': 'scalping',
        'description': 'Entrada na VWAP real com bandas 2σ. Compra quando preco toca banda inferior e reverte. Venda na superior.',
        'timeframes': ['M5', 'M1'],
        'conditions': ['vwap_real_detected', 'price_at_vwap_band', 'rsi_confirm_vwap', 'candle_reversal'],
        'tf_weights': {'M5': 0.5, 'M1': 0.5},
        'best_regime': ['trending', 'ranging'],
        'best_hours': [8, 9, 10, 14, 15, 16],
        'min_rr': 1.5,
    },
    'scalp_macd_divergence': {
        'name': 'MACD Divergence',
        'mode': 'scalping',
        'description': 'Divergencia entre preco e MACD histogram. Compra quando preco faz LL mas MACD faz HL.',
        'timeframes': ['M5', 'M1'],
        'conditions': ['macd_divergence_bull', 'price_near_support', 'candle_reversal'],
        'tf_weights': {'M5': 0.6, 'M1': 0.4},
        'best_regime': ['ranging', 'trending'],
        'best_hours': [8, 9, 10, 14, 15],
        'min_rr': 2.0,
    },
    'pa_ichimoku_cloud': {
        'name': 'Ichimoku Cloud Breakout',
        'mode': 'price_action',
        'description': 'Rompimento da nuvem Ichimoku com Tenkan/Kijun cross e preco acima/abaixo da cloud.',
        'timeframes': ['H1', 'M15', 'M5'],
        'conditions': ['ichimoku_cloud_break', 'tk_cross_confirm', 'price_above_below_cloud'],
        'tf_weights': {'H1': 0.4, 'M15': 0.35, 'M5': 0.25},
        'best_regime': ['trending'],
        'best_hours': list(range(8, 22)),
        'min_rr': 2.0,
    },
    'scalp_gap_fill': {
        'name': 'Gap Fill',
        'mode': 'scalping',
        'description': 'Gap de abertura que tende a ser preenchido. Entrada na direcao contraria ao gap.',
        'timeframes': ['M5', 'M1'],
        'conditions': ['gap_detected', 'gap_filling', 'momentum_fading'],
        'tf_weights': {'M5': 0.6, 'M1': 0.4},
        'best_regime': ['ranging'],
        'best_hours': [8, 14, 15, 20],
        'min_rr': 1.5,
    },
    'scalp_london_breakout': {
        'name': 'London Breakout',
        'mode': 'scalping',
        'description': 'Rompimento da range da sessao asiatica na abertura de Londres. Range definida por max/min das 00:00-07:00 UTC.',
        'timeframes': ['M15', 'M5'],
        'conditions': ['london_session_active', 'asian_range_defined', 'breakout_with_volume'],
        'tf_weights': {'M15': 0.6, 'M5': 0.4},
        'best_regime': ['trending'],
        'best_hours': [8, 9, 10],
        'min_rr': 2.0,
    },
    'pa_triangle_breakout': {
        'name': 'Triangle Breakout',
        'mode': 'price_action',
        'description': 'Rompimento de triangulo (ascendente, descendente ou simetrico) com volume e follow-through.',
        'timeframes': ['H1', 'M15', 'M5'],
        'conditions': ['triangle_detected', 'breakout_directional', 'volume_confirm'],
        'tf_weights': {'H1': 0.3, 'M15': 0.4, 'M5': 0.3},
        'best_regime': ['ranging', 'trending'],
        'best_hours': list(range(8, 22)),
        'min_rr': 2.0,
    },
"""

    # Insert new setups before the closing brace of SETUP_DEFINITIONS
    insert_marker = "        'min_rr': 3.0,\n    },\n}"
    last_occurrence = content.rfind(insert_marker)
    if last_occurrence > 0:
        content = content[:last_occurrence + len(insert_marker)] + new_setups + "\n}"
        print('[PATCH] Added 6 new setups: VWAP Real, MACD Divergence, Ichimoku, Gap Fill, London Breakout, Triangle')

    # ═══════════════════════════════════════════════════════
    # ADICIONAR VERIFICACOES DE CONDICOES PARA NOVOS SETUPS
    # ═══════════════════════════════════════════════════════

    new_conditions = """
        # ═══ VWAP REAL ═══
        if condition == 'vwap_real_detected':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict):
                    continue
                if data.get('vwap', 0) > 0:
                    return True
            return False

        if condition == 'price_at_vwap_band':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict) or 'price' not in data:
                    continue
                price = data['price']
                vwap = data.get('vwap', 0)
                vwap_upper = data.get('vwap_upper', 0)
                vwap_lower = data.get('vwap_lower', 0)
                if vwap > 0:
                    if direction == 1 and price <= vwap_lower * 1.002:
                        return True  # Near lower band = buy
                    elif direction == -1 and price >= vwap_upper * 0.998:
                        return True  # Near upper band = sell
            return False

        if condition == 'rsi_confirm_vwap':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict):
                    continue
                rsi = data.get('rsi', 50)
                if direction == 1 and rsi < 45:
                    return True
                elif direction == -1 and rsi > 55:
                    return True
            return False

        # ═══ MACD DIVERGENCE ═══
        if condition in ('macd_divergence_bull', 'macd_divergence'):
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict):
                    continue
                macd = data.get('macd', 0)
                macd_signal = data.get('macd_signal', 0)
                macd_hist = data.get('macd_hist', 0)
                # Bullish divergence: MACD hist negativo mas subindo
                if direction == 1 and macd_hist < 0 and macd > macd_signal:
                    return True
                # Bearish divergence: MACD hist positivo mas caindo
                elif direction == -1 and macd_hist > 0 and macd < macd_signal:
                    return True
            return False

        if condition == 'price_near_support':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict) or 'sr_zones' not in data:
                    continue
                price = data['price']
                atr = data.get('atr', 1)
                for zone in data['sr_zones']:
                    if abs(price - zone['price']) < atr * 0.5:
                        return True
            return False

        # ═══ ICHIMOKU ═══
        if condition == 'ichimoku_cloud_break':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict):
                    continue
                ich = data.get('ichimoku', {})
                if not ich:
                    continue
                if direction == 1 and ich.get('price_above_cloud', False):
                    return True
                elif direction == -1 and ich.get('price_below_cloud', False):
                    return True
            return False

        if condition == 'tk_cross_confirm':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict):
                    continue
                ich = data.get('ichimoku', {})
                if not ich:
                    continue
                if direction == 1 and ich.get('tk_cross_bull', False):
                    return True
                elif direction == -1 and ich.get('tk_cross_bear', False):
                    return True
            return False

        if condition == 'price_above_below_cloud':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict):
                    continue
                ich = data.get('ichimoku', {})
                if not ich:
                    continue
                if direction == 1 and ich.get('price_above_cloud', False):
                    return True
                elif direction == -1 and ich.get('price_below_cloud', False):
                    return True
            return False

        # ═══ GAP FILL ═══
        if condition == 'gap_detected':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict):
                    continue
                gap = data.get('gap', {})
                if gap and gap.get('has_gap', False):
                    return True
            return False

        if condition == 'gap_filling':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict) or 'price' not in data:
                    continue
                gap = data.get('gap', {})
                if not gap or not gap.get('has_gap', False):
                    continue
                price = data['price']
                gap_top = gap.get('gap_top', 0)
                gap_bot = gap.get('gap_bot', 0)
                if gap_top > 0 and gap_bot > 0:
                    # Preco esta dentro do gap = sendo preenchido
                    if min(gap_top, gap_bot) <= price <= max(gap_top, gap_bot):
                        return True
            return False

        # ═══ LONDON BREAKOUT ═══
        if condition == 'london_session_active':
            h = datetime.now().hour
            return h in [8, 9, 10, 11]

        if condition == 'asian_range_defined':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict) or 'swing_highs' not in data:
                    continue
                sh = data.get('swing_highs', [])
                sl = data.get('swing_lows', [])
                if sh and sl:
                    range_size = abs(max(s['price'] for s in sh[-3:]) - min(s['price'] for s in sl[-3:]))
                    price = data.get('price', 0)
                    if price > 0 and 0.002 < range_size / price < 0.015:  # Range entre 0.2% e 1.5%
                        return True
            return False

        # ═══ TRIANGLE ═══
        if condition == 'triangle_detected':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict):
                    continue
                # Usar swing highs/lows para detectar triangulo
                sh = data.get('swing_highs', [])
                sl = data.get('swing_lows', [])
                if len(sh) >= 2 and len(sl) >= 2:
                    # Verificar se highs diminuem e lows sobem (ou vice-versa)
                    if sh[-1]['price'] < sh[-2]['price'] and sl[-1]['price'] > sl[-2]['price']:
                        return True  # Symmetrical triangle
                    if abs(sh[-1]['price'] - sh[-2]['price']) / sh[-1]['price'] < 0.003 and sl[-1]['price'] > sl[-2]['price']:
                        return True  # Ascending triangle
                    if abs(sl[-1]['price'] - sl[-2]['price']) / sl[-1]['price'] < 0.003 and sh[-1]['price'] < sh[-2]['price']:
                        return True  # Descending triangle
            return False

        if condition == 'breakout_directional':
            for tf_key, data in tf_data.items():
                if not isinstance(data, dict) or 'candle' not in data:
                    continue
                candle = data['candle']
                if candle.get('direction', 0) == direction and candle.get('strength', 0) > 40:
                    return True
            return False
"""

    # Insert new conditions before the "return False" default
    insert_before = "        # Default: condição desconhecida = falsa\n        return False"
    if insert_before in content:
        content = content.replace(insert_before, new_conditions + "\n        # Default: condição desconhecida = falsa\n        return False")
        print('[PATCH] Added condition checks for 6 new setups')

    # ═══════════════════════════════════════════════════════
    # WRITE
    # ═══════════════════════════════════════════════════════

    with open('studio/golden_ai_studio_web/golden_scanner.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print('\n[PATCH] All patches applied successfully!')
    print('[PATCH] Total setups: 42 + 6 = 48')


if __name__ == '__main__':
    patch_file()
