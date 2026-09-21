#!/usr/bin/env python3
"""
🎯 Golden AI — MQL5 EA Builder Engine
Gera robôs Expert Advisors profissionais e completos para MetaTrader 5
com tratamento de ordens via CTrade, trailing stop, breakeven e múltiplos indicadores.
"""

from typing import Dict, Any
from datetime import datetime


def generate_mql5_ea(config: Dict[str, Any]) -> str:
    """
    Gera o código fonte MQL5 completo baseado na configuração fornecida.
    """
    name = config.get("name", "Golden_AutoEA")
    version = config.get("version", "1.00")
    symbol = config.get("symbol", "_Symbol")
    magic_number = int(config.get("magic_number", 777888))
    
    # Risco
    lot = float(config.get("lot", 0.01))
    sl_points = int(config.get("stop_loss", 200))
    tp_points = int(config.get("take_profit", 400))
    trailing_points = int(config.get("trailing_stop", 150))
    breakeven_points = int(config.get("breakeven", 100))
    
    # Horários
    use_time = bool(config.get("use_time_filter", True))
    start_hour = int(config.get("start_hour", 9))
    end_hour = int(config.get("end_hour", 17))
    
    # Estratégia
    strategy_type = config.get("strategy_type", "MA_CROSS")  # MA_CROSS, RSI_REVERSAL, BB_BREAKOUT, COMBINED
    ma_fast = int(config.get("ma_fast_period", 9))
    ma_slow = int(config.get("ma_slow_period", 21))
    rsi_period = int(config.get("rsi_period", 14))
    rsi_ob = float(config.get("rsi_overbought", 70.0))
    rsi_os = float(config.get("rsi_oversold", 30.0))

    code = f"""//+------------------------------------------------------------------+
//|                                                {name}.mq5 |
//|                                     Gerado por Golden AI Studio  |
//|                                       https://goldenai.studio    |
//+------------------------------------------------------------------+
#property copyright "Golden AI Studio Pro"
#property link      "https://goldenai.studio"
#property version   "{version}"
#property description "Expert Advisor automatizado gerado por Golden AI"

#include <Trade\\Trade.mqh>
#include <Trade\\PositionInfo.mqh>

//--- INPUTS GERAIS
input group "=== CONFIGURAÇÃO DO ROBÔ ==="
input ulong   InpMagicNumber = {magic_number};      // Magic Number
input string  InpComment     = "{name}"; // Comentário da Ordem
input double  InpLotSize     = {lot};            // Lote Fixo

input group "=== GESTÃO DE RISCO (PONTOS) ==="
input int     InpStopLoss    = {sl_points};           // Stop Loss (0 = desativado)
input int     InpTakeProfit  = {tp_points};           // Take Profit (0 = desativado)
input int     InpTrailingStop= {trailing_points};           // Trailing Stop (0 = desativado)
input int     InpBreakeven   = {breakeven_points};           // Breakeven (0 = desativado)

input group "=== FILTRO DE HORÁRIO ==="
input bool    InpUseTimeFilter = {str(use_time).lower()};     // Ativar Filtro de Horário
input int     InpStartHour     = {start_hour};             // Hora de Início
input int     InpEndHour       = {end_hour};            // Hora de Término

input group "=== PARÂMETROS TÉCNICOS ==="
input int     InpMAFastPeriod  = {ma_fast};             // Período Média Rápida
input int     InpMASlowPeriod  = {ma_slow};            // Período Média Lenta
input int     InpRsiPeriod     = {rsi_period};            // Período RSI
input double  InpRsiOverbought = {rsi_ob};          // RSI Sobrecompra
input double  InpRsiOversold   = {rsi_os};          // RSI Sobrevenda

//--- OBJETOS GLOBAIS
CTrade         m_trade;
CPositionInfo  m_position;

int            m_handle_ma_fast = INVALID_HANDLE;
int            m_handle_ma_slow = INVALID_HANDLE;
int            m_handle_rsi     = INVALID_HANDLE;
datetime       m_last_bar_time  = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{{
    m_trade.SetExpertMagicNumber(InpMagicNumber);
    m_trade.SetDeviationInPoints(20);
    m_trade.SetTypeFillingBySymbol(_Symbol);

    // Inicializar Indicadores
    m_handle_ma_fast = iMA(_Symbol, _Period, InpMAFastPeriod, 0, MODE_EMA, PRICE_CLOSE);
    m_handle_ma_slow = iMA(_Symbol, _Period, InpMASlowPeriod, 0, MODE_EMA, PRICE_CLOSE);
    m_handle_rsi     = iRSI(_Symbol, _Period, InpRsiPeriod, PRICE_CLOSE);

    if(m_handle_ma_fast == INVALID_HANDLE || m_handle_ma_slow == INVALID_HANDLE || m_handle_rsi == INVALID_HANDLE)
    {{
        Print("Erro ao criar handles dos indicadores!");
        return(INIT_FAILED);
    }}

    Print(">>> {name} v{version} inicializado com sucesso no ativo ", _Symbol);
    return(INIT_SUCCEEDED);
}}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{{
    if(m_handle_ma_fast != INVALID_HANDLE) IndicatorRelease(m_handle_ma_fast);
    if(m_handle_ma_slow != INVALID_HANDLE) IndicatorRelease(m_handle_ma_slow);
    if(m_handle_rsi != INVALID_HANDLE)     IndicatorRelease(m_handle_rsi);
    Print(">>> {name} finalizado. Motivo: ", reason);
}}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{{
    // Gerenciamento de posições abertas em cada Tick
    GerenciarTrailingStop();
    GerenciarBreakeven();

    // Executar lógica de entrada apenas na abertura de cada nova barra
    if(!IsNewBar()) return;

    // Verificar filtro de horário
    if(InpUseTimeFilter && !IsTradingTime()) return;

    // Verificar se já temos posição aberta por este EA
    if(TemPosicaoAberta()) return;

    // Obter buffers dos indicadores
    double ma_fast[2], ma_slow[2], rsi[2];
    if(CopyBuffer(m_handle_ma_fast, 0, 1, 2, ma_fast) < 2) return;
    if(CopyBuffer(m_handle_ma_slow, 0, 1, 2, ma_slow) < 2) return;
    if(CopyBuffer(m_handle_rsi, 0, 1, 2, rsi) < 2) return;

    // Sinais
    bool sinal_compra = false;
    bool sinal_venda  = false;

    // Lógica de Cruzamento com filtro RSI
    bool cruzou_cima  = (ma_fast[0] <= ma_slow[0] && ma_fast[1] > ma_slow[1]);
    bool cruzou_baixo = (ma_fast[0] >= ma_slow[0] && ma_fast[1] < ma_slow[1]);

    if(cruzou_cima && rsi[1] > InpRsiOversold)
    {{
        sinal_compra = true;
    }}
    else if(cruzou_baixo && rsi[1] < InpRsiOverbought)
    {{
        sinal_venda = true;
    }}

    // Execução de Ordens
    if(sinal_compra)
    {{
        AbrirCompra();
    }}
    else if(sinal_venda)
    {{
        AbrirVenda();
    }}
}}

//+------------------------------------------------------------------+
//| Funções de Execução de Ordens                                    |
//+------------------------------------------------------------------+
void AbrirCompra()
{{
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double sl  = (InpStopLoss > 0)   ? (ask - InpStopLoss * _Point)   : 0.0;
    double tp  = (InpTakeProfit > 0) ? (ask + InpTakeProfit * _Point) : 0.0;

    m_trade.Buy(InpLotSize, _Symbol, ask, sl, tp, InpComment);
    Print("[COMPRA] Ordem enviada em ", ask, " SL=", sl, " TP=", tp);
}}

void AbrirVenda()
{{
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double sl  = (InpStopLoss > 0)   ? (bid + InpStopLoss * _Point)   : 0.0;
    double tp  = (InpTakeProfit > 0) ? (bid - InpTakeProfit * _Point) : 0.0;

    m_trade.Sell(InpLotSize, _Symbol, bid, sl, tp, InpComment);
    Print("[VENDA] Ordem enviada em ", bid, " SL=", sl, " TP=", tp);
}}

//+------------------------------------------------------------------+
//| Trailing Stop e Breakeven                                        |
//+------------------------------------------------------------------+
void GerenciarTrailingStop()
{{
    if(InpTrailingStop <= 0) return;

    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {{
        if(m_position.SelectByIndex(i))
        {{
            if(m_position.Magic() == InpMagicNumber && m_position.Symbol() == _Symbol)
            {{
                if(m_position.PositionType() == POSITION_TYPE_BUY)
                {{
                    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                    double novo_sl = bid - InpTrailingStop * _Point;
                    if(novo_sl > m_position.PriceOpen() && novo_sl > m_position.StopLoss())
                    {{
                        m_trade.PositionModify(m_position.Ticket(), novo_sl, m_position.TakeProfit());
                    }}
                }}
                else if(m_position.PositionType() == POSITION_TYPE_SELL)
                {{
                    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                    double novo_sl = ask + InpTrailingStop * _Point;
                    if(novo_sl < m_position.PriceOpen() && (m_position.StopLoss() == 0 || novo_sl < m_position.StopLoss()))
                    {{
                        m_trade.PositionModify(m_position.Ticket(), novo_sl, m_position.TakeProfit());
                    }}
                }}
            }}
        }}
    }}
}}

void GerenciarBreakeven()
{{
    if(InpBreakeven <= 0) return;

    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {{
        if(m_position.SelectByIndex(i))
        {{
            if(m_position.Magic() == InpMagicNumber && m_position.Symbol() == _Symbol)
            {{
                if(m_position.PositionType() == POSITION_TYPE_BUY)
                {{
                    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                    if((bid - m_position.PriceOpen()) >= InpBreakeven * _Point)
                    {{
                        if(m_position.StopLoss() < m_position.PriceOpen())
                        {{
                            m_trade.PositionModify(m_position.Ticket(), m_position.PriceOpen(), m_position.TakeProfit());
                            Print("[BREAKEVEN] Posição de Compra protegida no zero a zero.");
                        }}
                    }}
                }}
                else if(m_position.PositionType() == POSITION_TYPE_SELL)
                {{
                    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                    if((m_position.PriceOpen() - ask) >= InpBreakeven * _Point)
                    {{
                        if(m_position.StopLoss() == 0 || m_position.StopLoss() > m_position.PriceOpen())
                        {{
                            m_trade.PositionModify(m_position.Ticket(), m_position.PriceOpen(), m_position.TakeProfit());
                            Print("[BREAKEVEN] Posição de Venda protegida no zero a zero.");
                        }}
                    }}
                }}
            }}
        }}
    }}
}}

//+------------------------------------------------------------------+
//| Funções Auxiliares                                               |
//+------------------------------------------------------------------+
bool IsNewBar()
{{
    datetime current_time = iTime(_Symbol, _Period, 0);
    if(current_time != m_last_bar_time)
    {{
        m_last_bar_time = current_time;
        return true;
    }}
    return false;
}}

bool IsTradingTime()
{{
    MqlDateTime dt;
    TimeCurrent(dt);
    if(dt.hour >= InpStartHour && dt.hour < InpEndHour)
        return true;
    return false;
}}

bool TemPosicaoAberta()
{{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {{
        if(m_position.SelectByIndex(i))
        {{
            if(m_position.Magic() == InpMagicNumber && m_position.Symbol() == _Symbol)
                return true;
        }}
    }}
    return false;
}}
//+------------------------------------------------------------------+
"""
    return code
