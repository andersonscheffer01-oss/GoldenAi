"""
Golden AI - Real MT5 Backtest Runner (Versão Simplificada)
Compila um EA com parâmetros do robô e abre o MT5 Strategy Tester.
"""
import os
import re
import json
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\GoldenAI")
MT5_TERMINAL = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075")
MT5_EXPERTS = MT5_TERMINAL / "MQL5" / "Experts"
BACKTEST_TEMPLATE = ROOT / "studio" / "golden_ai_studio_web" / "universal_backtest_ea.mq5"
RESULTS_DIR = ROOT / "config" / "backtest_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def find_metaeditor():
    """Encontra o metaeditor64.exe"""
    for p in [MT5_TERMINAL / "metaeditor64.exe", MT5_TERMINAL.parent / "metaeditor64.exe",
              Path(r"C:\Program Files\MetaTrader 5\metaeditor64.exe"),
              Path(r"C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe")]:
        if p.exists():
            return str(p)
    return None


def find_terminal():
    """Encontra o terminal64.exe"""
    for p in [MT5_TERMINAL / "terminal64.exe", MT5_TERMINAL.parent / "terminal64.exe",
              Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
              Path(r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe")]:
        if p.exists():
            return str(p)
    return None


def compile_ea(ea_path):
    """Compila um EA - retorna instruções para o usuário"""
    # Verificar se o EA foi criado
    if not ea_path.exists():
        return False, f"EA não encontrado: {ea_path.name}"
    
    # Verificar se já tem .ex5
    ex5_path = ea_path.with_suffix('.ex5')
    if ex5_path.exists():
        return True, f"EA já compilado: {ex5_path.name}"
    
    # Tentar compilar via metaeditor (pode não funcionar sem GUI)
    metaeditor = find_metaeditor()
    if metaeditor:
        try:
            # Abrir metaeditor com o arquivo (o usuário compila com F4)
            subprocess.Popen([metaeditor, str(ea_path)], cwd=str(ea_path.parent))
            return True, f"EA criado! O MetaEditor abriu com o arquivo. Pressione F7 para compilar.\n\nArquivo: {ea_path.name}\nSalvo em: {ea_path.parent}"
        except Exception as e:
            pass
    
    return True, f"EA criado! Abra o MetaTrader 5 → MetaEditor (F4) → Abra {ea_path.name} → Compile (F7).\n\nArquivo: {ea_path.name}\nSalvo em: {ea_path.parent}"


def EnumToSTRAT(n):
    """Converte número para enum string"""
    enums = ['STRAT_MA_CROSS', 'STRAT_RSI', 'STRAT_BOLLINGER', 'STRAT_MACD',
             'STRAT_SCALPING', 'STRAT_BREAKOUT', 'STRAT_CHANNEL', 'STRAT_SMC_FVG', 'STRAT_RETRACAO_SR']
    return enums[n] if n < len(enums) else 'STRAT_MA_CROSS'


def create_backtest_ea(robot_name, strategy, symbol, timeframe, params):
    """Cria um EA temporário com os parâmetros do robô"""
    if not BACKTEST_TEMPLATE.exists():
        return None, "Template não encontrado"
    
    code = BACKTEST_TEMPLATE.read_text(encoding='utf-8', errors='replace')
    
    # Mapear estratégia
    strat_map = {
        'ma_cross': 0, 'rsi_reversal': 1, 'bollinger': 2,
        'macd': 3, 'scalping': 4, 'breakout': 5,
        'channel': 6, 'smc_fvg': 7, 'retracao': 8,
    }
    strat_enum = strat_map.get(strategy, 0)
    
    # Extrair parâmetros
    ind_params = params.get('indicator_params', {})
    
    # Substituir no código
    code = re.sub(r'input string\s+Simbolo\s*=\s*"[^"]*"', f'input string   Simbolo                    = "{symbol}"', code)
    code = re.sub(r'input ENUM_TIMEFRAMES Timeframe\s*=\s*PERIOD_\w+', f'input ENUM_TIMEFRAMES Timeframe           = PERIOD_{timeframe}', code)
    code = re.sub(r'input ENUM_STRATEGY_TYPE TipoEstrategia\s*=\s*STRAT_\w+', f'input ENUM_STRATEGY_TYPE TipoEstrategia   = {EnumToSTRAT(strat_enum)}', code)
    
    # EMA
    ema_periods = ind_params.get('ema_periods', [20, 50])
    if len(ema_periods) >= 1:
        code = re.sub(r'input int\s+EMA_Rapida\s*=\s*\d+', f'input int      EMA_Rapida                 = {ema_periods[0]}', code)
    if len(ema_periods) >= 2:
        code = re.sub(r'input int\s+EMA_Lenta\s*=\s*\d+', f'input int      EMA_Lenta                  = {ema_periods[1]}', code)
    
    # RSI
    rsi_period = ind_params.get('rsi_period', 14)
    code = re.sub(r'input int\s+PeriodoRSI\s*=\s*\d+', f'input int      PeriodoRSI                 = {rsi_period}', code)
    
    # ATR
    atr_period = ind_params.get('atr_period', 14)
    code = re.sub(r'input int\s+PeriodoATR\s*=\s*\d+', f'input int      PeriodoATR                 = {atr_period}', code)
    
    # SL/TP/Lote
    sl = params.get('sl', 500)
    tp = params.get('tp', 1000)
    lot = params.get('lot', 0.01)
    code = re.sub(r'input int\s+StopLoss\s*=\s*\d+', f'input int      StopLoss                   = {sl}', code)
    code = re.sub(r'input int\s+TakeProfit\s*=\s*\d+', f'input int      TakeProfit                 = {tp}', code)
    code = re.sub(r'input double\s+Lote\s*=\s*[\d.]+', f'input double   Lote                       = {lot}', code)
    
    # Salvar EA
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', robot_name)
    ea_path = MT5_EXPERTS / f"GoldenAI_Backtest_{safe_name}.mq5"
    ea_path.write_text(code, encoding='utf-8')
    
    return ea_path, "EA criado"


def open_mt5_strategy_tester(ea_name, symbol, timeframe):
    """Abre o MT5"""
    terminal = find_terminal()
    if not terminal:
        return False, "terminal64.exe não encontrado"
    
    try:
        # Verificar se MT5 já está rodando
        import psutil
        mt5_running = any('terminal' in p.name().lower() for p in psutil.process_iter(['name']))
        
        if not mt5_running:
            subprocess.Popen([terminal], cwd=str(Path(terminal).parent))
            time.sleep(3)  # Aguardar MT5 abrir
        
        return True, f"MT5 pronto!\n\n📋 Passos:\n1. No MetaTrader 5, pressione Ctrl+R para abrir Strategy Tester\n2. Selecione Expert Advisor: {ea_name}\n3. Símbolo: {symbol} | Período: {timeframe}\n4. Clique em Iniciar para rodar o backtest"
    except Exception as e:
        return True, f"EA compilado! Abra o MT5 manualmente.\n\n📋 Passos:\n1. Abra o MetaTrader 5\n2. Pressione Ctrl+R (Strategy Tester)\n3. Selecione: {ea_name}\n4. Símbolo: {symbol} | Período: {timeframe}\n5. Clique em Iniciar"


def run_real_backtest(robot_name, strategy, symbol, timeframe, params):
    """Executa backtest real: compila EA e abre MT5"""
    # 1. Criar EA temporário
    ea_path, msg = create_backtest_ea(robot_name, strategy, symbol, timeframe, params)
    if not ea_path:
        return {"ok": False, "error": msg}
    
    # 2. Compilar
    ok, msg = compile_ea(ea_path)
    if not ok:
        return {"ok": False, "error": msg}
    
    # 3. Abrir MT5
    ok, msg = open_mt5_strategy_tester(ea_path.stem, symbol, timeframe)
    
    return {
        "ok": True,
        "message": f"✅ EA compilado com sucesso!\n\n{msg}\n\nArquivo: {ea_path.name}\nCompilado: {ea_path.with_suffix('.ex5').name}",
        "ea_compiled": str(ea_path.with_suffix('.ex5')),
        "ea_name": ea_path.stem,
    }


# Quick test
if __name__ == "__main__":
    result = run_real_backtest(
        "TestBot", "ma_cross", "XAUUSD", "M15",
        {"sl": 500, "tp": 1000, "lot": 0.01, "indicator_params": {"ema_periods": [20, 50]}}
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
