"""
Golden AI - MT5 Auto Trader
Executa trades automaticamente no MetaTrader 5 baseado na análise de IA.
"""
import re
import json
from pathlib import Path
from datetime import datetime

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


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
    }


def parse_trade_from_analysis(analysis_text, symbol="XAUUSD"):
    """
    Extrai parametros de trade da analise de IA.
    Procura por: direcao, entrada, SL, TP.
    Suporta JSON estruturado e texto livre.
    """
    result = {
        "direction": None,
        "entry": None,
        "sl": None,
        "tp": None,
        "confidence": "medium",
        "reason": "",
    }
    
    # Tentar JSON primeiro (formato da Analise Multi-Layer)
    try:
        data = json.loads(analysis_text)
        if isinstance(data, dict):
            dir_map = {'BUY': 'BUY', 'SELL': 'SELL', 'COMPRA': 'BUY', 'VENDA': 'SELL', 'NONE': None}
            result['direction'] = dir_map.get(data.get('direcao', '').upper(), data.get('direcao'))
            result['entry'] = data.get('entrada') or data.get('entry')
            result['sl'] = data.get('stop_loss') or data.get('sl')
            result['tp'] = data.get('take_profit') or data.get('tp') or data.get('take_profit_1')
            if result['direction'] and result['entry'] and result['sl'] and result['tp']:
                return result
    except (json.JSONDecodeError, TypeError):
        pass
    
    text_lower = analysis_text.lower()
    
    # Detectar direção
    if any(w in text_lower for w in ["compra", "buy", "comprar", "alta", "long"]):
        if not any(w in text_lower for w in ["venda", "sell", "vender", "baixa", "short"]):
            result["direction"] = "BUY"
    elif any(w in text_lower for w in ["venda", "sell", "vender", "baixa", "short"]):
        result["direction"] = "SELL"
    elif "aguardar" in text_lower or "neutro" in text_lower:
        result["direction"] = None
        result["reason"] = "IA recomenda aguardar"
        return result
    
    # Extrair preços (procurar por números com 4+ dígitos para XAUUSD)
    # Padrão: 1455.00, 1463.00, etc.
    price_pattern = r'(\d{3,4}\.\d{2})'
    prices = [float(p) for p in re.findall(price_pattern, analysis_text)]
    prices_sorted = sorted(set(prices)) if prices else []
    
    if prices:
        # Ordenar preços
        prices_sorted = sorted(set(prices))
        
        # Tentar mapear SL/TP baseado no contexto
        for line in analysis_text.split('\n'):
            line_lower = line.lower()
            price_match = re.search(price_pattern, line)
            if price_match:
                price_val = float(price_match.group(1))
                
                if any(w in line_lower for w in ["stop loss", "sl", "stop"]):
                    result["sl"] = price_val
                elif any(w in line_lower for w in ["take profit", "tp", "alvo", "target"]):
                    result["tp"] = price_val
                elif any(w in line_lower for w in ["entrada", "entry", "entrar"]):
                    result["entry"] = price_val
    
    # Se não encontrou SL/TP, calcular baseado nos preços
    if result["direction"] == "BUY":
        if not result["sl"] and len(prices_sorted) >= 2:
            result["sl"] = prices_sorted[0]  # Menor preço = suporte = SL
        if not result["tp"] and len(prices_sorted) >= 2:
            result["tp"] = prices_sorted[-1]  # Maior preço = resistência = TP
    elif result["direction"] == "SELL":
        if not result["sl"] and len(prices_sorted) >= 2:
            result["sl"] = prices_sorted[-1]  # Maior preço = resistência = SL
        if not result["tp"] and len(prices_sorted) >= 2:
            result["tp"] = prices_sorted[0]  # Menor preço = suporte = TP
    
    # Detectar confiança
    if any(w in text_lower for w in ["8/10", "9/10", "10/10", "forte", "alta confiança"]):
        result["confidence"] = "high"
    elif any(w in text_lower for w in ["5/10", "6/10", "7/10", "moderada"]):
        result["confidence"] = "medium"
    elif any(w in text_lower for w in ["3/10", "4/10", "fraca", "baixa"]):
        result["confidence"] = "low"
    
    return result


def get_symbol_info(symbol):
    """Obtém informações do símbolo"""
    if not MT5_AVAILABLE:
        return None
    
    info = mt5.symbol_info(symbol)
    if info is None:
        # Tentar selecionar
        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
    
    return info


def calculate_lots(symbol, risk_percent=1.0, sl_points=500):
    """Calcula tamanho do lote baseado no risco"""
    ok, account = connect_mt5()
    if not ok:
        return 0.01
    
    info = get_symbol_info(symbol)
    if not info:
        return 0.01
    
    balance = account.get("balance", 10000)
    risk_amount = balance * (risk_percent / 100)
    
    # Calcular valor do ponto
    tick_value = info.trade_tick_value
    tick_size = info.trade_tick_size
    point = info.point
    
    if tick_value <= 0 or tick_size <= 0:
        return 0.01
    
    # Valor por ponto
    point_value = (tick_value / tick_size) * point
    
    if point_value <= 0:
        return 0.01
    
    # Lote = risco / (SL em pontos * valor por ponto)
    lots = risk_amount / (sl_points * point_value)
    
    # Limitar
    lot_step = info.volume_step
    min_lot = info.volume_min
    max_lot = info.volume_max
    
    lots = max(min_lot, min(max_lot, lots))
    lots = round(lots / lot_step) * lot_step
    
    return round(lots, 2)


def execute_trade(symbol, direction, entry=None, sl=None, tp=None, lots=None, magic=99999, comment="GoldenAI Auto"):
    """
    Executa uma ordem no MetaTrader 5.
    """
    ok, account = connect_mt5()
    if not ok:
        return {"ok": False, "error": account}
    
    info = get_symbol_info(symbol)
    if not info:
        return {"ok": False, "error": f"Símbolo {symbol} não encontrado"}
    
    # Obter preço atual
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return {"ok": False, "error": f"Não foi possível obter cotação de {symbol}"}
    
    point = info.point
    digits = info.digits
    
    # Definir preco de entrada
    use_market_order = entry is None  # Lembrete: entrada nula = ordem a mercado
    if entry is None:
        if direction == "BUY":
            entry = tick.ask
        else:
            entry = tick.bid
    
    # Normalizar precos
    entry = round(entry, digits)
    
    if sl:
        sl = round(sl, digits)
    if tp:
        tp = round(tp, digits)
    
    # Calcular lote se nao fornecido
    if lots is None or lots <= 0:
        sl_points = abs(entry - sl) / point if sl else 500
        try:
            from risk_engine import get_risk_engine
            risk_percent = get_risk_engine().risk_per_trade_pct
        except Exception:
            risk_percent = 0.25
        lots = calculate_lots(symbol, risk_percent, sl_points)

    # Toda ordem automatica passa pelo mesmo bloqueio de risco.
    try:
        from risk_engine import get_risk_engine
        risk = get_risk_engine()
        risk.update_config({'account_balance': account.get('balance', 0)})
        current_positions = get_open_positions()
        normalized_positions = [
            {
                'symbol': p.get('symbol'),
                'entry': p.get('price_open', p.get('entry', 0)),
                'sl': p.get('sl', 0),
                'current_price': p.get('price_current', p.get('price_open', 0)),
            }
            for p in current_positions
        ]
        allowed, reason, details = risk.can_trade(symbol, direction, normalized_positions)
        if not allowed:
            return {'ok': False, 'blocked_by_risk': True, 'error': reason, 'risk_details': details}
    except Exception as e:
        return {'ok': False, 'blocked_by_risk': True, 'error': 'Risk Engine indisponivel: %s' % e}
    
    # Criar request
    request = {
        "action": mt5.TRADE_ACTION_DEAL if use_market_order else mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": lots,
        "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": entry if direction == "BUY" else entry,
        "sl": sl if sl else 0,
        "tp": tp if tp else 0,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    # Logica de ordem: mercado vs pendente
    current_price = tick.ask if direction == "BUY" else tick.bid
    distance = abs(entry - current_price) / point
    
    # Obter stop level do broker (distancia minima para ordens pendentes)
    stop_level = 0
    try:
        stop_level = info.trade_stops_level
    except AttributeError:
        stop_level = 10
    
    # Decidir tipo de ordem
    if use_market_order:
        # Entrada a mercado (entry=None)
        request["action"] = mt5.TRADE_ACTION_DEAL
        if direction == "BUY":
            request["type"] = mt5.ORDER_TYPE_BUY
            request["price"] = tick.ask
        else:
            request["type"] = mt5.ORDER_TYPE_SELL
            request["price"] = tick.bid
    elif distance <= 20:
        # Preco muito proximo = ordem a mercado
        request["action"] = mt5.TRADE_ACTION_DEAL
        if direction == "BUY":
            request["type"] = mt5.ORDER_TYPE_BUY
            request["price"] = tick.ask
        else:
            request["type"] = mt5.ORDER_TYPE_SELL
            request["price"] = tick.bid
    else:
        # Preco distante = ordem pendente
        request["action"] = mt5.TRADE_ACTION_PENDING
        request["price"] = entry
        if direction == "BUY":
            # BUY_LIMIT: entrada abaixo do mercado (pullback)
            # BUY_STOP: entrada acima do mercado (rompimento)
            if entry < current_price:
                request["type"] = mt5.ORDER_TYPE_BUY_LIMIT
            else:
                request["type"] = mt5.ORDER_TYPE_BUY_STOP
        else:
            # SELL_LIMIT: entrada acima do mercado (pullback)
            # SELL_STOP: entrada abaixo do mercado (rompimento)
            if entry > current_price:
                request["type"] = mt5.ORDER_TYPE_SELL_LIMIT
            else:
                request["type"] = mt5.ORDER_TYPE_SELL_STOP
        
        # Validar distancias minimas do broker
        min_distance = max(stop_level, 10)
        if sl and direction == "BUY" and (entry - sl) / point < min_distance:
            sl = round(entry - min_distance * point, digits)
            request["sl"] = sl
        elif sl and direction == "SELL" and (sl - entry) / point < min_distance:
            sl = round(entry + min_distance * point, digits)
            request["sl"] = sl
        
        if tp and direction == "BUY" and (tp - entry) / point < min_distance:
            tp = round(entry + min_distance * point, digits)
            request["tp"] = tp
        elif tp and direction == "SELL" and (entry - tp) / point < min_distance:
            tp = round(entry - min_distance * point, digits)
            request["tp"] = tp
    
    # Enviar ordem
    result = mt5.order_send(request)
    
    if result is None:
        return {"ok": False, "error": "Erro ao enviar ordem: %s" % str(mt5.last_error())}
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"ok": False, "error": "Ordem rejeitada: %s (codigo: %d)" % (result.comment, result.retcode)}
    
    # Tipo de ordem para mensagem
    order_type = 'Mercado' if request['action'] == mt5.TRADE_ACTION_DEAL else 'Pendente'
    
    try:
        risk.record_trade_open(symbol)
    except Exception:
        pass

    return {
        "ok": True,
        "order": result.order,
        "deal": result.deal,
        "price": result.price,
        "volume": result.volume,
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "lots": lots,
        "order_type": order_type,
        "message": "%s %s %s @ %s | SL: %s | TP: %s | Lote: %.2f" % (
            'Ordem Pendente' if order_type == 'Pendente' else 'Executada',
            direction, symbol, entry, sl, tp, lots),
    }


def get_current_price_from_mt5(symbol="XAUUSD"):
    """Obtém preço atual via MT5 (mantido vivo)"""
    try:
        if not MT5_AVAILABLE:
            return None
        try:
            from mt5_connector import ensure_connection
            ensure_connection()
        except ImportError:
            if not mt5.initialize():
                return None
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return (tick.bid + tick.ask) / 2.0
    except Exception:
        pass
    return None


def validate_trade_price(trade_params, symbol="XAUUSD"):
    """
    Valida se os preços do trade estão próximos ao preço real.
    Rejeita se entry/SL/TP estiverem muito distantes (>50% do preço atual).
    """
    current = get_current_price_from_mt5(symbol)
    if current is None or current <= 0:
        return True, "Sem preço de referência, aceitando trade"
    
    entry = trade_params.get("entry")
    sl = trade_params.get("sl")
    tp = trade_params.get("tp")
    
    tolerance = 0.5  # 50% de tolerância (preço pode mudar)
    
    for name, price in [("entry", entry), ("sl", sl), ("tp", tp)]:
        if price and price > 0:
            distance_pct = abs(price - current) / current
            if distance_pct > tolerance:
                return False, (
                    f"❌ PREÇO INVÁLIDO: {name}={price} está a {distance_pct*100:.0f}% "
                    f"do preço atual ({current:.2f}). "
                    f"O modelo de IA errou o preço. Use o preço real: ~{current:.2f}"
                )
    
    return True, f"✅ Preços validados (preço atual: {current:.2f})"


def parse_scalping_json(analysis_text, symbol="XAUUSD"):
    """
    Tenta parsear resposta JSON de scalping.
    Retorna dict com: direcao, entrada, stop_loss, take_profit, etc.
    Valida preços contra o preço real do MT5.
    """
    import json as _json
    result = {
        "direction": None,
        "entry": None,
        "sl": None,
        "tp": None,
        "confidence": "medium",
        "reason": "",
        "risk_points": None,
        "reward_points": None,
        "rr_ratio": None,
        "time_estimated": None,
    }
    
    # Tentar extrair JSON da resposta
    try:
        # Procurar bloco JSON na resposta
        json_start = analysis_text.find('{')
        json_end = analysis_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_str = analysis_text[json_start:json_end]
            data = _json.loads(json_str)
            
            # Mapear campos
            d = data.get("direcao", "").upper()
            if d in ("BUY", "COMPRA", "SELL", "VENDA"):
                result["direction"] = "BUY" if d in ("BUY", "COMPRA") else "SELL"
            elif d == "AGUARDAR":
                result["direction"] = None
                result["reason"] = data.get("motivo", "Aguardar")
                return result
            
            result["entry"] = data.get("entrada")
            result["sl"] = data.get("stop_loss")
            result["tp"] = data.get("take_profit")
            result["risk_points"] = data.get("pontos_risco")
            result["reward_points"] = data.get("pontos_lucro")
            result["rr_ratio"] = data.get("rr_ratio")
            result["reason"] = data.get("motivo", "")
            result["time_estimated"] = data.get("tempo_estimado", "")
            
            # Confidence
            conf = data.get("confianca", 5)
            if isinstance(conf, int):
                if conf >= 8:
                    result["confidence"] = "high"
                elif conf >= 6:
                    result["confidence"] = "medium"
                else:
                    result["confidence"] = "low"
            
            # VALIDAR PREÇOS - rejeitar se muito distantes
            is_valid, msg = validate_trade_price(result, symbol)
            if not is_valid:
                result["direction"] = None
                result["reason"] = msg
                result["price_error"] = True
            
            return result
    except (_json.JSONDecodeError, KeyError, TypeError):
        pass
    
    # Fallback: usar parse antigo
    return parse_trade_from_analysis(analysis_text)


def auto_trade_from_analysis(analysis_text, symbol="XAUUSD", auto_execute=False, magic=99999, mode="price_action"):
    """
    Fluxo completo: analisa texto → extrai trade → executa (se auto_execute=True)
    Modos: price_action, scalping, swing
    """
    mode_aliases = {"scalp": "scalping", "day": "price_action"}
    mode = mode_aliases.get(mode, mode)

    # 1. Extrair trade da análise (usar JSON parse para scalping)
    if mode == "scalping":
        trade_params = parse_scalping_json(analysis_text, symbol)
    else:
        trade_params = parse_trade_from_analysis(analysis_text, symbol)
    
    if not trade_params["direction"]:
        return {
            "ok": False,
            "trade_params": trade_params,
            "message": "❌ IA não recomenda entrada neste momento (AGUARDAR)",
        }
    
    # Ajustar SL/TP baseado no modo
    if mode == "scalping":
        # Scalping: SL/TP apertado, timeout curto
        comment = f"GoldenAI Scalp {trade_params['direction']}"
    elif mode == "swing":
        # Swing: SL/TP mais amplo
        comment = f"GoldenAI Swing {trade_params['direction']}"
    else:
        comment = f"GoldenAI {trade_params['direction']}"
    
    # 2. Se auto_execute está desligado, apenas retornar os parâmetros
    if not auto_execute:
        mode_emoji = {"scalping": "⚡", "swing": "📈", "price_action": "📊"}.get(mode, "📊")
        msg = (f"{mode_emoji} Trade detectado: {trade_params['direction']} @ ~{trade_params.get('entry', 'mercado')} | "
               f"SL: {trade_params.get('sl', '-')} | TP: {trade_params.get('tp', '-')}")
        if trade_params.get("rr_ratio"):
            msg += f" | R:R 1:{trade_params['rr_ratio']}"
        if trade_params.get("time_estimated"):
            msg += f" | Tempo: {trade_params['time_estimated']}"
        
        return {
            "ok": True,
            "trade_params": trade_params,
            "message": msg,
            "needs_confirmation": True,
            "mode": mode,
        }
    
    # 3. Executar trade
    result = execute_trade(
        symbol=symbol,
        direction=trade_params["direction"],
        entry=trade_params["entry"],
        sl=trade_params["sl"],
        tp=trade_params["tp"],
        magic=magic,
        comment=comment,
    )
    
    return {
        "ok": result.get("ok", False),
        "trade_params": trade_params,
        "execution": result,
        "message": result.get("message", ""),
        "mode": mode,
    }


def get_open_positions(symbol=None, magic=None):
    """Lista posições abertas"""
    ok, _ = connect_mt5()
    if not ok:
        return []
    
    positions = mt5.positions_get()
    if not positions:
        return []
    
    result = []
    for pos in positions:
        if symbol and pos.symbol != symbol:
            continue
        if magic and pos.magic != magic:
            continue
        
        result.append({
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": "BUY" if pos.type == 0 else "SELL",
            "volume": pos.volume,
            "price_open": pos.price_open,
            "sl": pos.sl,
            "tp": pos.tp,
            "profit": pos.profit,
            "swap": pos.swap,
            "magic": pos.magic,
            "comment": pos.comment,
            "time": datetime.fromtimestamp(pos.time).isoformat(),
        })
    
    return result


def close_position(ticket):
    """Fecha uma posição"""
    ok, _ = connect_mt5()
    if not ok:
        return {"ok": False, "error": "MT5 não conectado"}
    
    position = mt5.positions_get(ticket=ticket)
    if not position:
        return {"ok": False, "error": f"Posição {ticket} não encontrada"}
    
    pos = position[0]
    tick = mt5.symbol_info_tick(pos.symbol)
    
    if pos.type == 0:  # BUY
        price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
    else:  # SELL
        price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "magic": pos.magic,
        "comment": "GoldenAI Close",
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    
    if result is None:
        return {"ok": False, "error": f"Erro ao fechar: {mt5.last_error()}"}
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"ok": False, "error": f"Falha ao fechar: {result.comment}"}
    
    return {
        "ok": True,
        "message": f"✅ Posição {ticket} fechada @ {price}",
        "profit": pos.profit,
    }


# Quick test
if __name__ == "__main__":
    # Testar parse
    test_analysis = """
    ### 6. SUGESTÃO DE OPERAÇÃO
    - **Direção recomendada**: COMPRA
    - **Zona de entrada sugerida**: 1458.00
    - **Stop Loss sugerido**: 1455.00
    - **Take Profit sugerido**: 1465.00
    - **Relação Risco/Retorno**: 1:2.3
    """
    
    result = parse_trade_from_analysis(test_analysis, "XAUUSD")
    print(json.dumps(result, indent=2))
