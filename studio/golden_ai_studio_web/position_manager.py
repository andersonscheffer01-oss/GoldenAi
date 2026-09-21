"""
Golden AI - Position Manager
Gerencia Breakeven e Trailing Stop para posicoes abertas.
Roda em background e monitora todas as posicoes GoldenAI.
"""
import threading
import time
from datetime import datetime

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

# CONFIGURACOES PADRAO
DEFAULT_CONFIG = {
    "breakeven_enabled": True,
    "breakeven_trigger_points": 300,
    "breakeven_profit_lock_points": 50,
    "trailing_enabled": True,
    "trailing_trigger_points": 200,
    "trailing_distance_points": 150,
    "trailing_step_points": 50,
    "partial_close_enabled": False,
    "partial_close_trigger_points": 400,
    "partial_close_percent": 50,
    "partial_closed_flag": {},
    "magic": 99999,
    "scan_interval_seconds": 2,
}

_config = dict(DEFAULT_CONFIG)
_manager_thread = None
_manager_running = False
_trade_log = []


def get_config():
    return dict(_config)


def update_config(new_config):
    global _config
    for key, value in new_config.items():
        if key in _config:
            _config[key] = value
    return get_config()


def get_trade_log(limit=50):
    return _trade_log[-limit:]


def _log_action(action, ticket, symbol, details):
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "action": action,
        "ticket": ticket,
        "symbol": symbol,
        "details": details,
    }
    _trade_log.append(entry)
    if len(_trade_log) > 200:
        _trade_log.pop(0)


def _get_positions():
    if not MT5_AVAILABLE:
        return []
    positions = mt5.positions_get()
    if not positions:
        return []
    return [p for p in positions if p.magic == _config["magic"]]


def _modify_position(ticket, sl=None, tp=None):
    if not MT5_AVAILABLE:
        return False
    position = mt5.positions_get(ticket=ticket)
    if not position:
        return False
    pos = position[0]
    info = mt5.symbol_info(pos.symbol)
    if not info:
        return False
    digits = info.digits
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": pos.symbol,
        "sl": round(sl, digits) if sl else pos.sl,
        "tp": round(tp, digits) if tp else pos.tp,
    }
    result = mt5.order_send(request)
    if result is None:
        return False
    return result.retcode == mt5.TRADE_RETCODE_DONE


def _close_partial(ticket, percent):
    if not MT5_AVAILABLE:
        return False, 0
    position = mt5.positions_get(ticket=ticket)
    if not position:
        return False, 0
    pos = position[0]
    info = mt5.symbol_info(pos.symbol)
    if not info:
        return False, 0
    lot_step = info.volume_step
    min_lot = info.volume_min
    close_volume = round(pos.volume * (percent / 100) / lot_step) * lot_step
    close_volume = max(min_lot, min(close_volume, pos.volume))
    close_volume = round(close_volume, 2)
    if close_volume <= 0:
        return False, 0
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick:
        return False, 0
    if pos.type == 0:
        price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": close_volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "magic": pos.magic,
        "comment": "GoldenAI Partial",
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return True, close_volume
    return False, 0


def _manage_position(pos):
    ticket = pos.ticket
    symbol = pos.symbol
    direction = "BUY" if pos.type == 0 else "SELL"
    entry = pos.price_open
    current_sl = pos.sl
    current_tp = pos.tp
    if not MT5_AVAILABLE:
        return
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return
    info = mt5.symbol_info(symbol)
    if not info:
        return
    point = info.point
    digits = info.digits
    if direction == "BUY":
        current_price = tick.bid
        profit_points = (current_price - entry) / point
    else:
        current_price = tick.ask
        profit_points = (entry - current_price) / point
    new_sl = current_sl

    # BREAKEVEN
    if _config["breakeven_enabled"]:
        trigger = _config["breakeven_trigger_points"]
        lock = _config["breakeven_profit_lock_points"]
        if profit_points >= trigger:
            if direction == "BUY":
                be_sl = entry + lock * point
                if current_sl < be_sl - point:
                    new_sl = be_sl
                    _log_action("BREAKEVEN", ticket, symbol,
                               "SL -> " + str(round(be_sl, digits)) + " (lucro: " + str(int(profit_points)) + "p)")
            else:
                be_sl = entry - lock * point
                if current_sl == 0 or current_sl > be_sl + point:
                    new_sl = be_sl
                    _log_action("BREAKEVEN", ticket, symbol,
                               "SL -> " + str(round(be_sl, digits)) + " (lucro: " + str(int(profit_points)) + "p)")

    # TRAILING STOP
    if _config["trailing_enabled"]:
        trigger = _config["trailing_trigger_points"]
        distance = _config["trailing_distance_points"]
        step = _config["trailing_step_points"]
        if profit_points >= trigger:
            if direction == "BUY":
                trailing_sl = current_price - distance * point
                should_move = trailing_sl > (new_sl + step * point)
                if should_move:
                    new_sl = trailing_sl
                    _log_action("TRAILING", ticket, symbol,
                               "SL trailing -> " + str(round(trailing_sl, digits)) + " (preco: " + str(round(current_price, digits)) + ")")
            else:
                trailing_sl = current_price + distance * point
                should_move = new_sl == 0 or trailing_sl < (new_sl - step * point)
                if should_move:
                    new_sl = trailing_sl
                    _log_action("TRAILING", ticket, symbol,
                               "SL trailing -> " + str(round(trailing_sl, digits)) + " (preco: " + str(round(current_price, digits)) + ")")

    # PARTIAL CLOSE
    if _config["partial_close_enabled"]:
        trigger = _config["partial_close_trigger_points"]
        pct = _config["partial_close_percent"]
        partial_key = str(ticket)
        if profit_points >= trigger and partial_key not in _config["partial_closed_flag"]:
            ok, vol = _close_partial(ticket, pct)
            if ok:
                _config["partial_closed_flag"][partial_key] = True
                _log_action("PARTIAL", ticket, symbol,
                           "Fechou " + str(vol) + " lotes (" + str(pct) + "%)")

    if new_sl != current_sl and new_sl > 0:
        _modify_position(ticket, sl=new_sl, tp=current_tp)


def _scan_loop():
    global _manager_running
    while _manager_running:
        try:
            if MT5_AVAILABLE:
                try:
                    from mt5_connector import ensure_connection
                    ensure_connection()
                except ImportError:
                    pass
                positions = _get_positions()
                for pos in positions:
                    _manage_position(pos)
        except Exception as e:
            _log_action("ERROR", 0, "SYSTEM", str(e))
        time.sleep(_config["scan_interval_seconds"])


def start_manager():
    global _manager_thread, _manager_running
    if _manager_running:
        return {"ok": True, "message": "Manager ja esta rodando"}
    if not MT5_AVAILABLE:
        return {"ok": False, "error": "MetaTrader5 nao instalado"}
    _manager_running = True
    _manager_thread = threading.Thread(target=_scan_loop, daemon=True)
    _manager_thread.start()
    _log_action("START", 0, "SYSTEM", "Position Manager iniciado")
    return {"ok": True, "message": "Position Manager iniciado"}


def stop_manager():
    global _manager_running
    _manager_running = False
    _log_action("STOP", 0, "SYSTEM", "Position Manager parado")
    return {"ok": True, "message": "Position Manager parado"}


def get_status():
    return {
        "running": _manager_running,
        "config": get_config(),
        "positions_managed": len(_get_positions()) if MT5_AVAILABLE else 0,
        "last_actions": get_trade_log(10),
    }


def simulate_impact(sl_points, tp_points, breakeven_trigger, breakeven_lock,
                    trailing_trigger, trailing_distance, trailing_step,
                    sample_trades=100):
    """
    Simula o impacto de BE + Trailing Stop com caminho de preco realista.
    Cada trade: random walk com volatilidade adequada ao timeframe.
    """
    import random as _rnd
    _rnd.seed(42)

    no_management = {"wins": 0, "losses": 0, "total_pnl": 0.0}
    with_be = {"wins": 0, "losses": 0, "total_pnl": 0.0}
    with_be_trailing = {"wins": 0, "losses": 0, "total_pnl": 0.0}

    for i in range(sample_trades):
        step_vol = _rnd.uniform(4.0, 15.0)
        drift = _rnd.gauss(0, 0.5)

        path = [0.0]
        for _ in range(99):
            move = _rnd.gauss(drift, step_vol)
            path.append(path[-1] + move)

        # SEM GERENCIAMENTO
        nm_pnl = 0
        nm_exited = False
        for p in path:
            if p >= tp_points:
                nm_pnl = tp_points
                nm_exited = True
                break
            if p <= -sl_points:
                nm_pnl = -sl_points
                nm_exited = True
                break
        if not nm_exited:
            nm_pnl = path[-1]
        if nm_pnl > 0:
            no_management["wins"] += 1
        else:
            no_management["losses"] += 1
        no_management["total_pnl"] += nm_pnl

        # COM BREAKEVEN
        be_active = False
        be_pnl = 0
        be_exited = False
        for p in path:
            if p >= breakeven_trigger:
                be_active = True
            if be_active:
                effective_sl = -breakeven_lock
                if p <= effective_sl:
                    be_pnl = breakeven_lock
                    be_exited = True
                    break
            else:
                if p <= -sl_points:
                    be_pnl = -sl_points
                    be_exited = True
                    break
            if p >= tp_points:
                be_pnl = tp_points
                be_exited = True
                break
        if not be_exited:
            be_pnl = path[-1] if not be_active else max(path[-1], breakeven_lock)
        if be_pnl > 0:
            with_be["wins"] += 1
        else:
            with_be["losses"] += 1
        with_be["total_pnl"] += be_pnl

        # COM BREAKEVEN + TRAILING
        be_active2 = False
        trailing_active = False
        trail_sl = None
        bt_pnl = 0
        bt_exited = False
        peak_price = 0.0

        for p in path:
            if p > peak_price:
                peak_price = p

            if p >= breakeven_trigger:
                be_active2 = True

            if p >= trailing_trigger:
                trailing_active = True
                new_trail_sl = peak_price - trailing_distance
                if trail_sl is None or new_trail_sl >= trail_sl + trailing_step:
                    trail_sl = new_trail_sl

            if trailing_active and trail_sl is not None:
                effective_sl = max(trail_sl, -breakeven_lock if be_active2 else -sl_points)
            elif be_active2:
                effective_sl = -breakeven_lock
            else:
                effective_sl = -sl_points

            if p <= effective_sl:
                bt_pnl = effective_sl
                bt_exited = True
                break

            if p >= tp_points:
                bt_pnl = tp_points
                bt_exited = True
                break

        if not bt_exited:
            bt_pnl = path[-1] if path[-1] > 0 else 0
            if trail_sl is not None and path[-1] <= trail_sl:
                bt_pnl = trail_sl

        if bt_pnl > 0:
            with_be_trailing["wins"] += 1
        else:
            with_be_trailing["losses"] += 1
        with_be_trailing["total_pnl"] += bt_pnl

    def calc_metrics(data):
        total = data["wins"] + data["losses"]
        if total == 0:
            return {"win_rate": 0, "avg_pnl": 0, "profit_factor": 0,
                    "trades": 0, "wins": 0, "losses": 0, "total_pnl": 0}
        wr = (data["wins"] / total) * 100
        avg = data["total_pnl"] / total
        if data["losses"] > 0 and data["wins"] > 0:
            avg_win = tp_points
            avg_loss = sl_points
            pf = (data["wins"] * avg_win) / (data["losses"] * avg_loss)
        elif data["losses"] == 0:
            pf = 999.0
        else:
            pf = 0.0
        return {
            "win_rate": round(wr, 1),
            "avg_pnl": round(avg, 2),
            "profit_factor": round(min(pf, 999.0), 2),
            "trades": total,
            "wins": data["wins"],
            "losses": data["losses"],
            "total_pnl": round(data["total_pnl"], 2),
        }

    return {
        "sample_size": sample_trades,
        "parameters": {
            "sl": sl_points, "tp": tp_points,
            "be_trigger": breakeven_trigger, "be_lock": breakeven_lock,
            "trailing_trigger": trailing_trigger,
            "trailing_distance": trailing_distance,
            "trailing_step": trailing_step,
        },
        "no_management": calc_metrics(no_management),
        "with_breakeven": calc_metrics(with_be),
        "with_be_trailing": calc_metrics(with_be_trailing),
    }


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    configs = [
        ('SCALPING  SL:200 TP:400', 200, 400, 150, 30, 180, 100, 30),
        ('SCALPING  SL:300 TP:600', 300, 600, 200, 50, 250, 150, 50),
        ('PA        SL:500 TP:1000', 500, 1000, 300, 80, 400, 250, 80),
        ('SWING     SL:800 TP:2000', 800, 2000, 500, 100, 600, 400, 100),
    ]

    for name, sl, tp, be_t, be_l, t_t, t_d, t_s in configs:
        r = simulate_impact(sl, tp, be_t, be_l, t_t, t_d, t_s, 3000)
        nm = r['no_management']
        be = r['with_breakeven']
        bt = r['with_be_trailing']
        print('')
        print('=== ' + name + ' ===')
        print('  Without Mgmt : WR=' + str(nm['win_rate']) + '%  PnL=' + str(nm['total_pnl']) + '  PF=' + str(nm['profit_factor']) + '  Avg=' + str(nm['avg_pnl']))
        print('  With BE      : WR=' + str(be['win_rate']) + '%  PnL=' + str(be['total_pnl']) + '  PF=' + str(be['profit_factor']) + '  Avg=' + str(be['avg_pnl']))
        print('  With BE+Trail: WR=' + str(bt['win_rate']) + '%  PnL=' + str(bt['total_pnl']) + '  PF=' + str(bt['profit_factor']) + '  Avg=' + str(bt['avg_pnl']))
        wr_diff = bt['win_rate'] - nm['win_rate']
        pnl_diff = bt['total_pnl'] - nm['total_pnl']
        print('  IMPROVEMENT  : WR ' + str(round(wr_diff, 1)) + '%  PnL ' + str(round(pnl_diff, 0)))
