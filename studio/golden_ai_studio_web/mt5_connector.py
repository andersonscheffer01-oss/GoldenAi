#!/usr/bin/env python3
"""
Golden AI - MT5 Connector
Gerencia conexao MT5 centralizada. Conecta automaticamente e mantem conectado.
"""
import MetaTrader5 as mt5
import sys
from datetime import datetime
from threading import Lock

_lock = Lock()
_connected = False
_initialized = False


def _try_launch_mt5():
    """Tenta abrir o MetaTrader 5 automaticamente."""
    import subprocess
    import time
    import os
    terminals = [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\..\..\..\..\..\terminal64.exe",
    ]
    for t in terminals:
        if os.path.exists(t):
            print("[MT5] Abrindo MetaTrader 5: %s" % t)
            try:
                subprocess.Popen([t], creationflags=0x00000008)  # DETACHED_PROCESS
                time.sleep(15)  # Aguardar MT5 iniciar
                return True
            except Exception as e:
                print("[MT5] Erro ao abrir: %s" % e)
                return False
    print("[MT5] terminal64.exe nao encontrado")
    return False


def ensure_connection():
    """Garante que MT5 esta conectado. Reconecta automaticamente se necessario."""
    global _connected, _initialized
    with _lock:
        if _connected:
            # Verificar se ainda esta vivo
            info = mt5.terminal_info()
            if info and info.connected:
                return True
            _connected = False

        # Tentar conectar
        if not _initialized:
            mt5_path = None
            # Tentar encontrar o terminal automaticamente
            terminals = [
                r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075",
                r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal",
            ]
            for path in terminals:
                try:
                    if mt5.initialize(path=path):
                        _connected = True
                        _initialized = True
                        account = mt5.account_info()
                        print("[MT5] ✅ Conectado: %s | %s | Saldo: %.2f" % (
                            account.login if account else "?",
                            account.server if account else "?",
                            account.balance if account else 0
                        ))
                        return True
                except Exception:
                    continue

        # Ultima tentativa sem path
        try:
            if mt5.initialize():
                _connected = True
                _initialized = True
                account = mt5.account_info()
                print("[MT5] ✅ Conectado: %s" % (account.login if account else "?"))
                return True
        except Exception as e:
            print("[MT5] ❌ Nao foi possivel conectar: %s" % str(e)[:100])

        # Se nao conseguiu, tentar abrir MT5 automaticamente
        if not _initialized:
            try:
                _try_launch_mt5()
                # Tentar novamente apos abrir
                for path in terminals:
                    try:
                        if mt5.initialize(path=path):
                            _connected = True
                            _initialized = True
                            account = mt5.account_info()
                            print("[MT5] ✅ Conectado apos auto-launch: %s" % (account.login if account else "?"))
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

        return False


def get_status():
    """Retorna status da conexao MT5."""
    info = mt5.terminal_info()
    account = mt5.account_info()
    return {
        'connected': _connected and info is not None and info.connected,
        'terminal': info.name if info else None,
        'account': account.login if account else None,
        'server': account.server if account else None,
        'balance': account.balance if account else 0,
        'equity': account.equity if account else 0,
        'leverge': account.leverage if account else 0,
    }


def safe_initialize():
    """Wrapper para garantir MT5 conectado antes de qualquer operacao."""
    if not ensure_connection():
        raise ConnectionError("MT5 nao conectado. Verifique se o MetaTrader 5 esta aberto.")


def safe_shutdown():
    """Nao desligar MT5 - manter sempre conectado."""
    pass


def get_candles(symbol, timeframe, count=200):
    """Busca candles com auto-reconexao."""
    safe_initialize()
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        # Tentar reconectar
        ensure_connection()
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    return rates


def get_symbol_info(symbol):
    """Obtem info do simbolo com auto-reconexao."""
    safe_initialize()
    info = mt5.symbol_info(symbol)
    if info is None:
        ensure_connection()
        info = mt5.symbol_info(symbol)
    return info


def get_tick(symbol):
    """Obtem tick atual com auto-reconexao."""
    safe_initialize()
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        ensure_connection()
        tick = mt5.symbol_info_tick(symbol)
    return tick


def send_order(request):
    """Envia ordem com auto-reconexao."""
    safe_initialize()
    result = mt5.order_send(request)
    if result is None or result.retcode != 10009:
        ensure_connection()
        result = mt5.order_send(request)
    return result


def get_positions():
    """Lista posicoes abertas."""
    safe_initialize()
    return mt5.positions_get()


def get_orders():
    """Lista ordens pendentes."""
    safe_initialize()
    return mt5.orders_get()


# Auto-conectar ao importar
try:
    ensure_connection()
except Exception:
    pass
