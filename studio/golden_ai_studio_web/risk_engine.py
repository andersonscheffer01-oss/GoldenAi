#!/usr/bin/env python3
"""
Golden AI - Risk Engine v3
Motor de risco completo:
  1. Position Sizing (risk % -> lot size)
  2. Daily Loss Limit + Consecutive Losses
  3. Correlation Exposure (exposicao maxima por grupo)
  4. Max Open Positions
  5. News Filter (eventos macro proximos)
  6. Slippage Estimation
  7. Risk per Trade Calculator
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════
# CORRELATION GROUPS
# ═══════════════════════════════════════════════════════════════

CORRELATION_GROUPS = {
    'USD_BULL': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD'],
    'USD_BEAR': ['USDJPY', 'USDCAD', 'USDCHF'],
    'JPY_CROSS': ['EURJPY', 'GBPJPY', 'AUDJPY'],
    'EUR_CROSS': ['EURGBP', 'EURAUD', 'EURCHF', 'EURJPY'],
    'GBP_CROSS': ['GBPJPY', 'GBPCHF'],
    'METALS': ['XAUUSD', 'XAGUSD'],
    'INDICES': ['NAS100', 'US30', 'SPX500', 'DAX40'],
    'CRYPTO': ['BTCUSD', 'ETHUSD'],
}

# Maximum exposure per correlation group (in R)
MAX_EXPOSURE_PER_GROUP = 2.0

# ═══════════════════════════════════════════════════════════════
# NEWS EVENTS (major events that affect all markets)
# ═══════════════════════════════════════════════════════════════

MAJOR_NEWS_EVENTS = [
    {'name': 'NFP', 'typical_hour_utc': 12, 'duration_min': 30, 'impact': 'HIGH'},
    {'name': 'FOMC', 'typical_hour_utc': 18, 'duration_min': 60, 'impact': 'HIGH'},
    {'name': 'CPI', 'typical_hour_utc': 12, 'duration_min': 30, 'impact': 'HIGH'},
    {'name': 'ECB', 'typical_hour_utc': 12, 'duration_min': 60, 'impact': 'HIGH'},
    {'name': 'BOE', 'typical_hour_utc': 11, 'duration_min': 30, 'impact': 'HIGH'},
    {'name': 'BOJ', 'typical_hour_utc': 3, 'duration_min': 60, 'impact': 'HIGH'},
    {'name': 'RBA', 'typical_hour_utc': 0, 'duration_min': 30, 'impact': 'MEDIUM'},
    {'name': 'SNB', 'typical_hour_utc': 7, 'duration_min': 30, 'impact': 'MEDIUM'},
]

# ═══════════════════════════════════════════════════════════════
# RISK ENGINE
# ═══════════════════════════════════════════════════════════════

class RiskEngine:
    """Motor de risco completo para o Golden AI"""

    def __init__(self):
        # Account settings
        self.account_balance = 0.0
        self.account_equity = 0.0
        self.risk_per_trade_pct = 0.25  # 0.25% of balance per trade
        self.max_daily_loss_pct = 2.0   # 2% max daily loss
        self.max_open_positions = 5
        self.max_correlation_exposure_r = MAX_EXPOSURE_PER_GROUP
        self.cooldown_seconds = 300     # 5 min between trades

        # State
        self._daily_pnl = 0.0
        self._consecutive_losses = 0
        self._last_trade_time = None
        self._open_positions = []
        self._trade_log = []
        self._active = True

    # ═══ POSITION SIZING ═══

    def calculate_lot_size(self, symbol, entry_price, stop_price, account_balance=None):
        """
        Calcula o tamanho do lote baseado no risco %.
        
        Formula:
        risk_amount = balance * risk_pct
        stop_distance = abs(entry - stop)
        pip_value = get_pip_value(symbol)
        lot_size = risk_amount / (stop_distance / pip_value)
        
        Args:
            symbol: ex: 'XAUUSD'
            entry_price: preco de entrada
            stop_price: preco do stop loss
            account_balance: saldo da conta (opcional, usa ultimo saldo)
        
        Returns:
            dict com lot_size, risk_amount, stop_distance, pip_value
        """
        balance = account_balance or self.account_balance
        if balance <= 0:
            return {'lot_size': 0.01, 'error': 'Balance not set'}

        pip_value = self._get_pip_value(symbol)
        point = self._get_point(symbol)
        stop_distance = abs(entry_price - stop_price)
        
        if stop_distance <= 0:
            return {'lot_size': 0.01, 'error': 'Invalid stop distance'}

        # Risk amount in account currency
        risk_amount = balance * (self.risk_per_trade_pct / 100.0)

        # Convert stop distance to pips
        stop_pips = stop_distance / pip_value if pip_value > 0 else 1

        # Lot size = risk_amount / (stop_pips * pip_value_per_lot)
        # pip_value_per_lot = pip_value * 100000 (for forex) or contract_size
        contract_size = self._get_contract_size(symbol)
        pip_value_per_lot = pip_value * contract_size

        if pip_value_per_lot <= 0:
            return {'lot_size': 0.01, 'error': 'Cannot calculate pip value'}

        lot_size = risk_amount / (stop_pips * pip_value_per_lot)

        # Round to lot step
        lot_step = self._get_lot_step(symbol)
        min_lot = self._get_min_lot(symbol)
        max_lot = self._get_max_lot(symbol)

        lot_size = round(lot_size / lot_step) * lot_step
        lot_size = max(min_lot, min(lot_size, max_lot))
        lot_size = round(lot_size, 2)

        return {
            'lot_size': lot_size,
            'risk_amount': round(risk_amount, 2),
            'risk_pct': self.risk_per_trade_pct,
            'stop_distance': round(stop_distance, 5),
            'stop_pips': round(stop_pips, 1),
            'pip_value': pip_value,
            'pip_value_per_lot': round(pip_value_per_lot, 4),
            'balance': balance,
        }

    def _get_pip_value(self, symbol):
        """Retorna o valor de 1 pip para o ativo"""
        pip_values = {
            'XAUUSD': 0.01, 'XAGUSD': 0.01,
            'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'USDCAD': 0.0001,
            'AUDUSD': 0.0001, 'NZDUSD': 0.0001, 'USDCHF': 0.0001,
            'EURGBP': 0.0001, 'EURJPY': 0.01, 'GBPJPY': 0.01,
            'AUDJPY': 0.01, 'EURAUD': 0.0001, 'EURCHF': 0.0001,
            'GBPCHF': 0.0001, 'USDJPY': 0.01,
            'NAS100': 0.01, 'US30': 0.01, 'SPX500': 0.01, 'DAX40': 0.01,
            'BTCUSD': 0.01, 'ETHUSD': 0.01,
        }
        return pip_values.get(symbol, 0.0001)

    def _get_point(self, symbol):
        """Retorna o valor de 1 point"""
        return self._get_pip_value(symbol)

    def _get_contract_size(self, symbol):
        """Retorna o tamanho do contrato"""
        if 'XAU' in symbol or 'XAG' in symbol:
            return 100  # 100 oz
        elif 'BTC' in symbol:
            return 1
        elif 'ETH' in symbol:
            return 1
        elif 'NAS' in symbol or 'US30' in symbol or 'SPX' in symbol or 'DAX' in symbol:
            return 1
        else:
            return 100000  # Standard lot

    def _get_lot_step(self, symbol):
        return 0.01

    def _get_min_lot(self, symbol):
        return 0.01

    def _get_max_lot(self, symbol):
        return 100.0

    # ═══ RISK CALCULATION ═══

    def calculate_risk_reward(self, entry, stop, target):
        """Calcula R:R de uma operacao"""
        stop_dist = abs(entry - stop)
        target_dist = abs(target - entry)
        if stop_dist <= 0:
            return 0, stop_dist, target_dist
        rr = target_dist / stop_dist
        return round(rr, 2), round(stop_dist, 5), round(target_dist, 5)

    def calculate_position_risk(self, lot_size, stop_distance, symbol):
        """Calcula o risco em $ de uma posicao"""
        pip_value = self._get_pip_value(symbol)
        contract_size = self._get_contract_size(symbol)
        stop_pips = stop_distance / pip_value if pip_value > 0 else 0
        risk_amount = stop_pips * pip_value * contract_size * lot_size
        return round(risk_amount, 2)

    # ═══ DAILY LOSS TRACKING ═══

    def record_trade(self, pnl_r, symbol='UNKNOWN'):
        """Registra um trade e atualiza estado de risco"""
        self._daily_pnl += pnl_r
        self._last_trade_time = datetime.now()
        self._trade_log.append({
            'time': datetime.now().isoformat(),
            'pnl_r': pnl_r,
            'symbol': symbol,
            'daily_pnl': self._daily_pnl,
        })
        if len(self._trade_log) > 200:
            self._trade_log.pop(0)

        if pnl_r < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def record_trade_open(self, symbol='UNKNOWN'):
        """Marca uma nova entrada sem falsificar PnL antes do fechamento."""
        self._last_trade_time = datetime.now()
        self._trade_log.append({
            'time': datetime.now().isoformat(),
            'pnl_r': 0.0,
            'symbol': symbol,
            'daily_pnl': self._daily_pnl,
            'event': 'OPEN',
        })

    def reset_daily(self):
        """Reset diario (chamar ao inicio de cada dia)"""
        self._daily_pnl = 0.0
        self._consecutive_losses = 0

    # ═══ TRADE VALIDATION ═══

    def can_trade(self, symbol=None, direction=None, current_positions=None):
        """
        Valida se pode operar:
        1. Kill switch ativo?
        2. Daily loss limit?
        3. Consecutive losses?
        4. Cooldown?
        5. Max positions?
        6. Correlation exposure?
        """
        if not self._active:
            return False, 'RISK ENGINE DESATIVADO', {}

        reasons = {}
        allowed = True

        # 1. Daily loss limit
        # _daily_pnl e pnl_r; converte o limite percentual da conta para R.
        daily_loss_limit = (self.max_daily_loss_pct / self.risk_per_trade_pct) if self.risk_per_trade_pct > 0 else 999
        if self._daily_pnl < 0 and abs(self._daily_pnl) >= daily_loss_limit:
            allowed = False
            reasons['daily_loss'] = 'DAILY LOSS LIMIT: %.2fR (limit: %.2fR)' % (self._daily_pnl, daily_loss_limit)

        # 2. Consecutive losses
        if self._consecutive_losses >= 3:
            allowed = False
            reasons['consecutive'] = 'CONSECUTIVE LOSSES: %d' % self._consecutive_losses

        # 3. Cooldown
        if self._last_trade_time:
            elapsed = (datetime.now() - self._last_trade_time).seconds
            if elapsed < self.cooldown_seconds:
                remaining = self.cooldown_seconds - elapsed
                allowed = False
                reasons['cooldown'] = 'COOLDOWN: %ds remaining' % remaining

        # 4. Max positions
        positions = current_positions or []
        if len(positions) >= self.max_open_positions:
            allowed = False
            reasons['max_positions'] = 'MAX POSITIONS: %d/%d' % (len(positions), self.max_open_positions)

        # 5. Correlation exposure
        if symbol and direction:
            group = self._get_correlation_group(symbol)
            if group:
                group_exposure = self._calc_group_exposure(group, positions, direction)
                if group_exposure >= self.max_correlation_exposure_r:
                    allowed = False
                    reasons['correlation'] = 'CORRELATION EXPOSURE: %.1fR in %s (limit: %.1fR)' % (
                        group_exposure, group, self.max_correlation_exposure_r)

        # 6. News filter
        news_status = self.check_news_proximity()
        if news_status['near_news']:
            allowed = False
            reasons['news'] = 'NEWS NEAR: %s in %d min' % (news_status['event_name'], news_status['minutes_until'])

        # Build response
        if allowed:
            return True, 'OK', reasons
        else:
            first_reason = list(reasons.values())[0] if reasons else 'UNKNOWN'
            return False, first_reason, reasons

    # ═══ CORRELATION ═══

    def _get_correlation_group(self, symbol):
        """Retorna o grupo de correlacao de um ativo"""
        for group, symbols in CORRELATION_GROUPS.items():
            if symbol in symbols:
                return group
        return None

    def _calc_group_exposure(self, group, positions, new_direction):
        """Calcula exposicao total de um grupo de correlacao em R"""
        group_symbols = CORRELATION_GROUPS.get(group, [])
        exposure = 0.0
        for pos in positions:
            if pos.get('symbol') in group_symbols:
                # Estimate R from entry/stop
                entry = pos.get('entry', 0)
                sl = pos.get('sl', 0)
                current = pos.get('current_price', entry)
                if entry > 0 and sl > 0:
                    stop_dist = abs(entry - sl)
                    current_pnl = abs(current - entry) / stop_dist if stop_dist > 0 else 0
                    exposure += current_pnl
        return exposure

    def get_correlation_exposure_report(self, positions):
        """Relatorio de exposicao por grupo"""
        report = {}
        for group, symbols in CORRELATION_GROUPS.items():
            group_positions = [p for p in positions if p.get('symbol') in symbols]
            if group_positions:
                total_risk = 0
                for p in group_positions:
                    entry = p.get('entry', 0)
                    sl = p.get('sl', 0)
                    if entry > 0 and sl > 0:
                        total_risk += abs(entry - sl)
                report[group] = {
                    'symbols': symbols,
                    'positions': len(group_positions),
                    'total_risk': round(total_risk, 5),
                    'exposure_r': round(total_risk / (self.account_balance * 0.0025) if self.account_balance > 0 else 0, 2),
                }
        return report

    # ═══ NEWS FILTER ═══

    def check_news_proximity(self, margin_minutes=15):
        """Verifica se ha noticias macro proximas"""
        now = datetime.now(timezone.utc)
        current_hour = now.hour
        current_minute = now.minute

        for event in MAJOR_NEWS_EVENTS:
            event_hour = event['typical_hour_utc']
            event_minute = 0
            diff_minutes = (event_hour * 60 + event_minute) - (current_hour * 60 + current_minute)
            if diff_minutes < 0:
                diff_minutes += 24 * 60
            if diff_minutes <= margin_minutes:
                return {
                    'near_news': True,
                    'event_name': event['name'],
                    'impact': event['impact'],
                    'minutes_until': diff_minutes,
                    'duration_min': event['duration_min'],
                }
        return {'near_news': False}

    # ═══ SLIPPAGE ESTIMATION ═══

    def estimate_slippage(self, symbol, spread_points, atr):
        """
        Estima slippage baseado em:
        - Spread atual
        - Volatilidade (ATR)
        - Horario (liquidez)
        - Tipo de ativo
        """
        # Base slippage by asset class
        if 'XAU' in symbol or 'XAG' in symbol:
            base_slippage = 0.5  # points
        elif 'BTC' in symbol or 'ETH' in symbol:
            base_slippage = 2.0
        elif 'NAS' in symbol or 'US30' in symbol:
            base_slippage = 1.0
        elif 'JPY' in symbol:
            base_slippage = 0.3
        else:
            base_slippage = 0.2

        # Spread impact
        spread_impact = spread_points * 0.1  # 10% of spread as slippage

        # Volatility impact
        volatility_factor = 1.0
        if atr > 0:
            # Higher ATR = more slippage
            volatility_factor = min(2.0, 1.0 + (atr / 100))

        # Session impact (lower liquidity = more slippage)
        session_factor = 1.0
        hour = datetime.now().hour
        if 0 <= hour < 7:  # Asia
            session_factor = 1.3
        elif 16 <= hour < 21:  # NY afternoon
            session_factor = 1.1
        elif 7 <= hour < 16:  # London/NY overlap
            session_factor = 0.8

        total_slippage = (base_slippage + spread_impact) * volatility_factor * session_factor

        return {
            'estimated_slippage_points': round(total_slippage, 1),
            'base': base_slippage,
            'spread_impact': round(spread_impact, 2),
            'volatility_factor': round(volatility_factor, 2),
            'session_factor': round(session_factor, 2),
            'total_cost_points': round(total_slippage + spread_points, 1),
        }

    # ═══ RISK REPORT ═══

    def get_risk_report(self, positions=None):
        """Relatorio completo de risco"""
        positions = positions or []
        allowed, reason, details = self.can_trade(current_positions=positions)

        # Calculate total exposure
        total_risk = 0
        for p in positions:
            entry = p.get('entry', 0)
            sl = p.get('sl', 0)
            if entry > 0 and sl > 0:
                total_risk += abs(entry - sl)

        # Daily stats
        today_trades = [t for t in self._trade_log if t.get('time', '').startswith(datetime.now().strftime('%Y-%m-%d'))]
        today_wins = sum(1 for t in today_trades if t['pnl_r'] > 0)
        today_losses = sum(1 for t in today_trades if t['pnl_r'] < 0)

        return {
            'allowed': allowed,
            'reason': reason,
            'details': details,
            'active': self._active,
            'daily_pnl_r': round(self._daily_pnl, 3),
            'daily_loss_limit_r': round(self.max_daily_loss_pct / self.risk_per_trade_pct, 2) if self.risk_per_trade_pct > 0 else 0,
            'consecutive_losses': self._consecutive_losses,
            'positions_count': len(positions),
            'max_positions': self.max_open_positions,
            'risk_per_trade_pct': self.risk_per_trade_pct,
            'account_balance': self.account_balance,
            'today_trades': len(today_trades),
            'today_wins': today_wins,
            'today_losses': today_losses,
            'news_status': self.check_news_proximity(),
            'correlation_report': self.get_correlation_exposure_report(positions),
        }

    # ═══ CONFIGURATION ═══

    def update_config(self, config):
        """Atualiza configuracoes de risco"""
        if 'risk_per_trade_pct' in config:
            self.risk_per_trade_pct = config['risk_per_trade_pct']
        if 'max_daily_loss_pct' in config:
            self.max_daily_loss_pct = config['max_daily_loss_pct']
        if 'max_open_positions' in config:
            self.max_open_positions = config['max_open_positions']
        if 'cooldown_seconds' in config:
            self.cooldown_seconds = config['cooldown_seconds']
        if 'max_correlation_exposure_r' in config:
            self.max_correlation_exposure_r = config['max_correlation_exposure_r']
        if 'account_balance' in config:
            self.account_balance = config['account_balance']
        if 'active' in config:
            self._active = config['active']

    def get_config(self):
        return {
            'risk_per_trade_pct': self.risk_per_trade_pct,
            'max_daily_loss_pct': self.max_daily_loss_pct,
            'max_open_positions': self.max_open_positions,
            'cooldown_seconds': self.cooldown_seconds,
            'max_correlation_exposure_r': self.max_correlation_exposure_r,
            'account_balance': self.account_balance,
            'active': self._active,
        }


# Singleton
_engine = None

def get_risk_engine():
    global _engine
    if _engine is None:
        _engine = RiskEngine()
    return _engine


if __name__ == '__main__':
    engine = get_risk_engine()
    engine.account_balance = 410.91  # From MT5

    print("=== RISK ENGINE v3 ===")
    print()

    # Test position sizing
    print("POSITION SIZING TEST:")
    result = engine.calculate_lot_size('XAUUSD', 3375.0, 3365.0)
    print(f"  XAUUSD: Entry=3375 SL=3365 -> Lot={result['lot_size']} Risk=${result['risk_amount']} ({result['risk_pct']}%)")

    result = engine.calculate_lot_size('EURUSD', 1.1650, 1.1630)
    print(f"  EURUSD: Entry=1.1650 SL=1.1630 -> Lot={result['lot_size']} Risk=${result['risk_amount']} ({result['risk_pct']}%)")

    result = engine.calculate_lot_size('NAS100', 20000, 19900)
    print(f"  NAS100: Entry=20000 SL=19900 -> Lot={result['lot_size']} Risk=${result['risk_amount']} ({result['risk_pct']}%)")

    print()
    print("NEWS FILTER:")
    news = engine.check_news_proximity()
    print(f"  Near news: {news['near_news']}")
    if news['near_news']:
        print(f"  Event: {news['event_name']} in {news['minutes_until']} min")

    print()
    print("SLIPPAGE ESTIMATION:")
    slip = engine.estimate_slippage('XAUUSD', 30, 8.0)
    print(f"  XAUUSD: {slip['estimated_slippage_points']} points (total cost: {slip['total_cost_points']} points)")

    print()
    print("RISK REPORT:")
    report = engine.get_risk_report()
    print(f"  Can trade: {report['allowed']}")
    print(f"  Balance: ${report['account_balance']}")
    print(f"  Risk per trade: {report['risk_per_trade_pct']}%")
    print(f"  Daily loss limit: {report['daily_loss_limit_r']}R")
    print(f"  Max positions: {report['max_positions']}")
