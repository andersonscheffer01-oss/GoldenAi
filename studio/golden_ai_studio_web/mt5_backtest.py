"""
Golden AI - Backtest Engine
Conecta ao MetaTrader 5, baixa dados históricos e simula estratégias de trading.
Retorna equity curve, estatísticas e trades para o Dashboard.
"""
import json
import math
from pathlib import Path
from datetime import datetime, timedelta

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

ROOT = Path(r"C:\GoldenAI")
RESULTS_DIR = ROOT / "config" / "backtest_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def connect_mt5():
    """Conecta ao MetaTrader 5 via auto-connector"""
    if not MT5_AVAILABLE:
        return False, "MetaTrader5 não instalado"
    try:
        from mt5_connector import ensure_connection
        if not ensure_connection():
            return False, "MT5 não conectado. Abra o MetaTrader 5."
    except ImportError:
        if not mt5.initialize():
            return False, f"Erro ao inicializar MT5: {mt5.last_error()}"
    info = mt5.account_info()
    if not info:
        return False, "MT5 não está conectado a uma conta"
    return True, {
        "login": info.login,
        "balance": info.balance,
        "server": info.server,
        "leverage": info.leverage,
    }


def get_historical_data(symbol, timeframe, count=5000):
    """Baixa dados históricos do MT5"""
    ok, _ = connect_mt5()
    if not ok:
        return None

    tf_map = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
    }
    tf = tf_map.get(timeframe, mt5.TIMEFRAME_M15)

    # O candle na posicao 0 ainda esta aberto e nao pode contaminar o backtest.
    rates = mt5.copy_rates_from_pos(symbol, tf, 1, count)
    # mt5.shutdown() # mantido vivo pelo auto-connector

    if rates is None or len(rates) == 0:
        return None

    return [{
        "time": int(r["time"]),
        "open": r["open"],
        "high": r["high"],
        "low": r["low"],
        "close": r["close"],
        "volume": r["tick_volume"],
    } for r in rates]


def ema(data, period):
    """Calcula Exponential Moving Average"""
    if len(data) < period:
        return [None] * len(data)
    result = [None] * (period - 1)
    k = 2 / (period + 1)
    result.append(sum(data[:period]) / period)
    for i in range(period, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result


def sma(data, period):
    """Calcula Simple Moving Average"""
    if len(data) < period:
        return [None] * len(data)
    result = [None] * (period - 1)
    for i in range(period - 1, len(data)):
        result.append(sum(data[i - period + 1:i + 1]) / period)
    return result


def rsi(data, period=14):
    """Calcula RSI"""
    if len(data) < period + 1:
        return [None] * len(data)
    result = [None] * period
    gains = []
    losses = []
    for i in range(1, len(data)):
        change = data[i] - data[i - 1]
        gains.append(max(0, change))
        losses.append(max(0, -change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(data)):
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - 100 / (1 + rs))
        if i < len(gains):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    return result


def bollinger(data, period=20, std_dev=2.0):
    """Calcula Bollinger Bands"""
    mid = sma(data, period)
    upper = [None] * len(data)
    lower = [None] * len(data)

    for i in range(period - 1, len(data)):
        if mid[i] is None:
            continue
        window = data[i - period + 1:i + 1]
        variance = sum((x - mid[i]) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper[i] = mid[i] + std_dev * std
        lower[i] = mid[i] - std_dev * std

    return mid, upper, lower


def macd(data, fast=12, slow=26, signal_period=9):
    """Calcula MACD"""
    ema_fast = ema(data, fast)
    ema_slow = ema(data, slow)
    macd_line = [None] * len(data)

    for i in range(len(data)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # Signal line
    macd_values = [v for v in macd_line if v is not None]
    signal = ema(macd_values, signal_period) if len(macd_values) >= signal_period else [None] * len(macd_values)

    return macd_line, signal


def simulate_strategy(strategy, data, params):
    """Simula uma estratégia e retorna trades e equity curve"""
    initial_balance = params.get("balance", 10000)
    sl_points = params.get("sl", 500)
    tp_points = params.get("tp", 1000)
    lot = params.get("lot", 0.01)
    point_value = params.get("point_value", 0.01)  # XAUUSD = 0.01

    balance = initial_balance
    equity_curve = [{"time": data[0]["time"], "equity": balance}]
    trades = []
    position = None  # {"type": "BUY"/"SELL", "entry": price, "sl": price, "tp": price, "time": timestamp}

    closes = [d["close"] for d in data]
    highs = [d["high"] for d in data]
    lows = [d["low"] for d in data]
    volumes = [float(d.get("volume", 0) or 0) for d in data]

    for i in range(50, len(data)):
        price = closes[i]
        high = highs[i]
        low = lows[i]
        time_val = data[i]["time"]

        # Check existing position
        if position:
            hit_sl = False
            hit_tp = False

            if position["type"] == "BUY":
                if low <= position["sl"]:
                    hit_sl = True
                    exit_price = position["sl"]
                elif high >= position["tp"]:
                    hit_tp = True
                    exit_price = position["tp"]
            else:  # SELL
                if high >= position["sl"]:
                    hit_sl = True
                    exit_price = position["sl"]
                elif low <= position["tp"]:
                    hit_tp = True
                    exit_price = position["tp"]

            if hit_sl or hit_tp:
                pnl_points = (exit_price - position["entry"]) / point_value if position["type"] == "BUY" else (position["entry"] - exit_price) / point_value
                # PnL em dólares: pontos * point_value * lot * 100 (para XAUUSD)
                pnl_dollars = pnl_points * point_value * lot * 100
                balance += pnl_dollars
                trades.append({
                    "time": time_val,
                    "entry_time": position["time"],
                    "exit_time": time_val,
                    "type": position["type"],
                    "entry": position["entry"],
                    "exit": exit_price,
                    "sl": position["sl"],
                    "tp": position["tp"],
                    "strategy_levels": position.get("strategy_levels", []),
                    "pnl_points": round(pnl_points, 1),
                    "pnl": round(pnl_dollars, 2),
                    "result": "WIN" if pnl_dollars > 0 else "LOSS"
                })
                position = None

        # Check for new signals
        if position is None and i >= 60:
            signal = None
            signal_levels = []

            if strategy == "ma_cross":
                # Usar períodos dos indicadores do robô se disponíveis
                ema_periods = params.get("ema_periods", [20, 50])
                fast_period = ema_periods[0] if len(ema_periods) > 0 else params.get("fast_period", 20)
                slow_period = ema_periods[1] if len(ema_periods) > 1 else params.get("slow_period", 50)
                ema_fast = ema(closes[:i + 1], fast_period)
                ema_slow = ema(closes[:i + 1], slow_period)
                if ema_fast[-1] and ema_slow[-1] and ema_fast[-2] and ema_slow[-2]:
                    if ema_fast[-1] > ema_slow[-1] and ema_fast[-2] <= ema_slow[-2]:
                        signal = "BUY"
                    elif ema_fast[-1] < ema_slow[-1] and ema_fast[-2] >= ema_slow[-2]:
                        signal = "SELL"

            elif strategy == "rsi_reversal":
                rsi_period = params.get("rsi_period", 14)
                oversold = params.get("rsi_oversold", params.get("oversold", 30))
                overbought = params.get("rsi_overbought", params.get("overbought", 70))
                rsi_vals = rsi(closes[:i + 1], rsi_period)
                if rsi_vals[-1] is not None and rsi_vals[-2] is not None:
                    if rsi_vals[-2] < oversold and rsi_vals[-1] >= oversold:
                        signal = "BUY"
                    elif rsi_vals[-2] > overbought and rsi_vals[-1] <= overbought:
                        signal = "SELL"

            elif strategy == "bollinger":
                period = params.get("bb_period", 20)
                std = params.get("bb_std", params.get("desvios", 2.0))
                mid, upper, lower = bollinger(closes[:i + 1], period, std)
                if lower[-1] and upper[-1] and lower[-2] and upper[-2]:
                    if closes[i - 1] <= lower[-2] and closes[i] > lower[-1]:
                        signal = "BUY"
                    elif closes[i - 1] >= upper[-2] and closes[i] < upper[-1]:
                        signal = "SELL"

            elif strategy == "macd":
                macd_fast = params.get("macd_fast", 12)
                macd_slow = params.get("macd_slow", 26)
                macd_sig = params.get("macd_signal", 9)
                macd_line, signal_line = macd(closes[:i + 1], macd_fast, macd_slow, macd_sig)
                macd_vals = [v for v in macd_line if v is not None]
                sig_vals = signal_line if signal_line else []
                if len(macd_vals) >= 2 and len(sig_vals) >= 2:
                    if macd_vals[-1] > sig_vals[-1] and macd_vals[-2] <= sig_vals[-2]:
                        signal = "BUY"
                    elif macd_vals[-1] < sig_vals[-1] and macd_vals[-2] >= sig_vals[-2]:
                        signal = "SELL"

            elif strategy == "scalping":
                ema_periods = params.get("ema_periods", [9])
                ema_period = ema_periods[0] if len(ema_periods) > 0 else params.get("ema_period", 9)
                ema_vals = ema(closes[:i + 1], ema_period)
                if ema_vals[-1] and ema_vals[-2]:
                    if closes[i - 1] <= ema_vals[-2] and closes[i] > ema_vals[-1]:
                        signal = "BUY"
                    elif closes[i - 1] >= ema_vals[-2] and closes[i] < ema_vals[-1]:
                        signal = "SELL"

            elif strategy == "breakout":
                lookback = params.get("lookback", 20)
                if i >= lookback:
                    highest = max(highs[i - lookback:i])
                    lowest = min(lows[i - lookback:i])
                    if price > highest:
                        signal = "BUY"
                    elif price < lowest:
                        signal = "SELL"

            elif strategy == "turtle_breakout":
                if i >= 20:
                    high20, low20 = max(highs[i - 20:i]), min(lows[i - 20:i])
                    avg_volume = sum(volumes[i - 20:i]) / 20 if sum(volumes[i - 20:i]) > 0 else 0
                    volume_ok = volumes[i] >= avg_volume * 1.10 if avg_volume else False
                    if volume_ok and price > high20:
                        signal = "BUY"
                        signal_levels = [{"label": "Donchian 20 H", "price": high20}, {"label": "Donchian 20 L", "price": low20}]
                    elif volume_ok and price < low20:
                        signal = "SELL"
                        signal_levels = [{"label": "Donchian 20 H", "price": high20}, {"label": "Donchian 20 L", "price": low20}]

            elif strategy == "darvas_box":
                if i >= 8:
                    box_high, box_low = max(highs[i - 6:i - 2]), min(lows[i - 6:i - 2])
                    box_width = box_high - box_low
                    avg_volume = sum(volumes[i - 20:i]) / 20 if i >= 20 else 0
                    volume_ok = volumes[i] >= avg_volume * 1.10 if avg_volume else False
                    if box_width > 0 and volume_ok and price > box_high:
                        signal = "BUY"
                        signal_levels = [{"label": "Darvas topo", "price": box_high}, {"label": "Darvas fundo", "price": box_low}]
                    elif box_width > 0 and volume_ok and price < box_low:
                        signal = "SELL"
                        signal_levels = [{"label": "Darvas topo", "price": box_high}, {"label": "Darvas fundo", "price": box_low}]

            elif strategy == "ca_c1":
                from datetime import datetime, timezone
                candle_time = datetime.fromtimestamp(data[i]["time"], timezone.utc)
                session_start = params.get("session_start_utc", 13)
                same_session = [j for j in range(max(0, i - 20), i) if datetime.fromtimestamp(data[j]["time"], timezone.utc).date() == candle_time.date() and datetime.fromtimestamp(data[j]["time"], timezone.utc).hour == session_start]
                if len(same_session) >= 3:
                    opening_high = max(highs[j] for j in same_session[:3])
                    opening_low = min(lows[j] for j in same_session[:3])
                    avg_volume = sum(volumes[max(0, i - 20):i]) / max(min(20, i), 1)
                    if volumes[i] >= avg_volume * 1.10 and price > opening_high:
                        signal = "BUY"
                        signal_levels = [{"label": "CA+C1 topo", "price": opening_high}, {"label": "CA+C1 fundo", "price": opening_low}]
                    elif volumes[i] >= avg_volume * 1.10 and price < opening_low:
                        signal = "SELL"
                        signal_levels = [{"label": "CA+C1 topo", "price": opening_high}, {"label": "CA+C1 fundo", "price": opening_low}]

            elif strategy == "volume_profile_rejection":
                if i >= 50:
                    window = data[i - 50:i]
                    profile_low = min(d["low"] for d in window)
                    profile_high = max(d["high"] for d in window)
                    bin_width = (profile_high - profile_low) / 24 if profile_high > profile_low else 0
                    histogram = [0.0] * 24
                    if bin_width > 0:
                        for candle in window:
                            typical = (candle["high"] + candle["low"] + candle["close"]) / 3
                            histogram[min(23, max(0, int((typical - profile_low) / bin_width)))] += float(candle.get("volume", 0) or 0)
                        poc = profile_low + (max(range(24), key=lambda x: histogram[x]) + 0.5) * bin_width
                        avg_volume = sum(volumes[i - 20:i]) / 20 if sum(volumes[i - 20:i]) > 0 else 0
                        if abs(price - poc) <= bin_width and volumes[i] >= avg_volume * 1.10:
                            if closes[i] > data[i]["open"]:
                                signal = "BUY"
                                signal_levels = [{"label": "POC", "price": poc}]
                            elif closes[i] < data[i]["open"]:
                                signal = "SELL"
                                signal_levels = [{"label": "POC", "price": poc}]

            elif strategy == "vwap_anchored":
                from datetime import datetime, timezone
                candle_time = datetime.fromtimestamp(data[i]["time"], timezone.utc)
                day_data = [d for d in data[:i + 1] if datetime.fromtimestamp(d["time"], timezone.utc).date() == candle_time.date()]
                total_volume = sum(float(d.get("volume", 0) or 0) for d in day_data)
                if total_volume > 0 and len(day_data) >= 3:
                    anchored = sum(((d["high"] + d["low"] + d["close"]) / 3) * float(d.get("volume", 0) or 0) for d in day_data) / total_volume
                    previous = closes[i - 1]
                    if previous <= anchored < price:
                        signal = "BUY"
                        signal_levels = [{"label": "VWAP anc", "price": anchored}]
                    elif previous >= anchored > price:
                        signal = "SELL"
                        signal_levels = [{"label": "VWAP anc", "price": anchored}]

            if signal:
                entry = price
                if signal == "BUY":
                    sl = entry - sl_points * point_value
                    tp = entry + tp_points * point_value
                else:
                    sl = entry + sl_points * point_value
                    tp = entry - tp_points * point_value

                position = {
                    "type": signal,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "time": time_val,
                    "strategy_levels": signal_levels,
                }

        equity_curve.append({"time": time_val, "equity": round(balance, 2)})

    # Close any remaining position at last price
    if position:
        exit_price = closes[-1]
        pnl_points = (exit_price - position["entry"]) / point_value if position["type"] == "BUY" else (position["entry"] - exit_price) / point_value
        pnl_dollars = pnl_points * point_value * lot * 100
        balance += pnl_dollars
        trades.append({
            "time": position["time"],
            "entry_time": position["time"],
            "exit_time": data[-1]["time"],
            "type": position["type"],
            "entry": position["entry"],
            "exit": exit_price,
            "sl": position["sl"],
            "tp": position["tp"],
            "strategy_levels": position.get("strategy_levels", []),
            "pnl_points": round(pnl_points, 1),
            "pnl": round(pnl_dollars, 2),
            "result": "WIN" if pnl_dollars > 0 else "LOSS"
        })

    return trades, equity_curve, balance


def calculate_stats(trades, initial_balance, final_balance):
    """Calcula estatísticas do backtest"""
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
            "total_pnl": 0, "profit_factor": 0, "max_drawdown": 0,
            "max_win": 0, "max_loss": 0, "avg_win": 0, "avg_loss": 0,
            "return_pct": 0, "sharpe_ratio": 0,
        }

    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    total_pnl = sum(t["pnl"] for t in trades)
    gross_profit = sum(t["pnl"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0

    # Max drawdown
    equity = initial_balance
    peak = initial_balance
    max_dd = 0
    for t in trades:
        equity += t["pnl"]
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)

    # Win/Loss streaks
    max_win_streak = 0
    max_loss_streak = 0
    current_streak = 0
    streak_type = None
    for t in trades:
        if t["result"] == "WIN":
            if streak_type == "WIN":
                current_streak += 1
            else:
                current_streak = 1
                streak_type = "WIN"
            max_win_streak = max(max_win_streak, current_streak)
        else:
            if streak_type == "LOSS":
                current_streak += 1
            else:
                current_streak = 1
                streak_type = "LOSS"
            max_loss_streak = max(max_loss_streak, current_streak)

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "total_pnl": round(total_pnl, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999 if gross_profit > 0 else 0),
        "max_drawdown": round(max_dd, 1),
        "max_win": round(max(t["pnl"] for t in wins), 2) if wins else 0,
        "max_loss": round(min(t["pnl"] for t in losses), 2) if losses else 0,
        "avg_win": round(gross_profit / len(wins), 2) if wins else 0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0,
        "return_pct": round(total_pnl / initial_balance * 100, 1),
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(-gross_loss, 2),
    }


def run_backtest(strategy, symbol, timeframe, params=None):
    """Executa um backtest completo"""
    if params is None:
        params = {}

    from strategy_engine import resolve_strategy
    requested_strategy = strategy
    strategy, strategy_meta = resolve_strategy(strategy)
    balance = params.get("balance", 10000)
    sl = params.get("sl", 500)
    tp = params.get("tp", 1000)
    lot = params.get("lot", 0.01)
    count = params.get("count", 3000)

    # Get point value for symbol
    ok, _ = connect_mt5()
    point_value = 0.01
    if ok:
        sym_info = mt5.symbol_info(symbol)
        if sym_info:
            point_value = sym_info.point
            # mt5.shutdown() # mantido vivo pelo auto-connector

    # Download data
    data = get_historical_data(symbol, timeframe, count)
    if not data:
        return {"ok": False, "error": f"Não foi possível obter dados de {symbol} no timeframe {timeframe}"}

    # Add strategy-specific params
    full_params = {
        "balance": balance,
        "sl": sl,
        "tp": tp,
        "lot": lot,
        "point_value": point_value,
    }
    full_params.update(params)

    # Simulate
    trades, equity_curve, final_balance = simulate_strategy(strategy_meta['adapter'], data, full_params)

    # Calculate stats
    stats = calculate_stats(trades, balance, final_balance)
    stats["initial_balance"] = balance
    stats["final_balance"] = round(final_balance, 2)
    stats["symbol"] = symbol
    stats["timeframe"] = timeframe
    stats["strategy"] = requested_strategy
    stats["strategy_name"] = strategy_meta.get('name', requested_strategy)
    stats["strategy_kind"] = strategy_meta.get('kind', 'generic')
    stats["engine_adapter"] = strategy_meta.get('adapter', strategy)
    if strategy_meta.get('kind') == 'radar':
        specialized = {
            'turtle_breakout', 'darvas_box', 'ca_c1',
            'volume_profile_rejection', 'vwap_anchored',
        }
        if strategy_meta.get('adapter') in specialized:
            stats["strategy_note"] = 'Backtest especializado com candle fechado e regra dedicada da estratégia.'
        else:
            stats["strategy_note"] = 'Adaptador historico do Radar; validar regras exatas no EA antes de operar.'
    stats["period_start"] = data[0]["time"]
    stats["period_end"] = data[-1]["time"]
    stats["period_days"] = round((data[-1]["time"] - data[0]["time"]) / 86400)
    stats["candles"] = len(data)

    # Save results
    result = {
        "ok": True,
        "stats": stats,
        "trades": trades if params.get("include_all_trades") else trades[-50:],
        "equity_curve": equity_curve,
        "timestamp": datetime.now().isoformat(),
    }

    # Save to file
    result_id = f"{strategy}_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    result_path = RESULTS_DIR / f"{result_id}.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")

    return result


def get_backtest_history(limit=20):
    """Retorna histórico de backtests executados"""
    results = []
    for f in sorted(RESULTS_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["id"] = f.stem
            results.append(data)
        except:
            pass
    return results


def compare_strategies(symbol, timeframe, strategies=None, params=None):
    """Compara múltiplas estratégias no mesmo período"""
    if strategies is None:
        from strategy_engine import list_strategies
        strategies = [s['id'] for s in list_strategies()[:5]]

    if params is None:
        params = {}

    results = []
    for strategy in strategies:
        result = run_backtest(strategy, symbol, timeframe, params)
        if result.get("ok"):
            results.append(result)

    return {
        "ok": True,
        "comparison": results,
        "symbol": symbol,
        "timeframe": timeframe,
    }


# Quick test
if __name__ == "__main__":
    result = run_backtest("ma_cross", "XAUUSD", "M15", {"sl": 500, "tp": 1000, "lot": 0.01})
    if result.get("ok"):
        s = result["stats"]
        print(f"Strategy: {s['strategy']}")
        print(f"Trades: {s['total_trades']}")
        print(f"Win Rate: {s['win_rate']}%")
        print(f"PnL: ${s['total_pnl']}")
        print(f"Profit Factor: {s['profit_factor']}")
        print(f"Max Drawdown: {s['max_drawdown']}%")
        print(f"Return: {s['return_pct']}%")
    else:
        print(f"Error: {result.get('error')}")
