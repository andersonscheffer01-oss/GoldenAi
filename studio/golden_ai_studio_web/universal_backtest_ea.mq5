//+------------------------------------------------------------------+
//| GoldenAI_Backtester.mq5                                          |
//| EA Universal de Backtest - Golden AI                              |
//| Roda no Strategy Tester real do MT5                               |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"

#include <Trade/Trade.mqh>

enum ENUM_STRATEGY_TYPE
{
   STRAT_MA_CROSS = 0,
   STRAT_RSI = 1,
   STRAT_BOLLINGER = 2,
   STRAT_MACD = 3,
   STRAT_SCALPING = 4,
   STRAT_BREAKOUT = 5,
   STRAT_CHANNEL = 6,
   STRAT_SMC_FVG = 7,
   STRAT_RETRACAO_SR = 8,
};

input group "CONFIGURAÇÃO GERAL"
input string   Simbolo                    = "XAUUSD";
input ENUM_TIMEFRAMES Timeframe           = PERIOD_M15;
input long     MagicNumber                = 99999;
input ENUM_STRATEGY_TYPE TipoEstrategia   = STRAT_MA_CROSS;

input group "MÉDIAS MÓVEIS"
input int      EMA_Rapida                 = 20;
input int      EMA_Lenta                  = 50;

input group "RSI"
input int      PeriodoRSI                 = 14;
input double   RSI_Sobrecompra            = 70.0;
input double   RSI_Sobrevenda             = 30.0;

input group "BOLLINGER"
input int      PeriodoBB                  = 20;
input double   DesviosBB                  = 2.0;

input group "MACD"
input int      MACD_Fast                  = 12;
input int      MACD_Slow                  = 26;
input int      MACD_Signal                = 9;

input group "ATR"
input int      PeriodoATR                 = 14;

input group "BREAKOUT / CANAL"
input int      PeriodoLookback            = 20;
input double   BufferPontos               = 50;

input group "S/R E ZONAS"
input int      PeriodoSR                  = 50;
input double   DistanciaSR_Pontos         = 100;

input group "GERENCIAMENTO"
input double   Lote                       = 0.01;
input int      StopLoss                   = 500;
input int      TakeProfit                 = 1000;
input bool     UsarBreakeven              = true;
input int      BreakevenStart             = 300;
input bool     UsarTrailing               = false;
input int      TrailingStart              = 500;
input int      TrailingStep               = 50;

CTrade trade;
int handleEMA_Fast, handleEMA_Slow, handleRSI, handleBB, handleMACD, handleATR;
datetime lastBarTime = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);
   
   // Criar handles baseado na estratégia
   if(TipoEstrategia == STRAT_MA_CROSS || TipoEstrategia == STRAT_SCALPING || TipoEstrategia == STRAT_RETRACAO_SR)
   {
      handleEMA_Fast = iMA(Simbolo, Timeframe, EMA_Rapida, 0, MODE_EMA, PRICE_CLOSE);
      handleEMA_Slow = iMA(Simbolo, Timeframe, EMA_Lenta, 0, MODE_EMA, PRICE_CLOSE);
      handleATR = iATR(Simbolo, Timeframe, PeriodoATR);
   }
   else if(TipoEstrategia == STRAT_RSI)
   {
      handleRSI = iRSI(Simbolo, Timeframe, PeriodoRSI, PRICE_CLOSE);
   }
   else if(TipoEstrategia == STRAT_BOLLINGER)
   {
      handleBB = iBands(Simbolo, Timeframe, PeriodoBB, 0, DesviosBB, PRICE_CLOSE);
   }
   else if(TipoEstrategia == STRAT_MACD)
   {
      handleMACD = iMACD(Simbolo, Timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE);
   }
   else if(TipoEstrategia == STRAT_BREAKOUT || TipoEstrategia == STRAT_CHANNEL || TipoEstrategia == STRAT_SMC_FVG)
   {
      handleATR = iATR(Simbolo, Timeframe, PeriodoATR);
   }
   
   Print("GoldenAI Backtester OK em ", Simbolo, " - Estratégia: ", EnumToString(TipoEstrategia));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(handleEMA_Fast != INVALID_HANDLE) IndicatorRelease(handleEMA_Fast);
   if(handleEMA_Slow != INVALID_HANDLE) IndicatorRelease(handleEMA_Slow);
   if(handleRSI != INVALID_HANDLE) IndicatorRelease(handleRSI);
   if(handleBB != INVALID_HANDLE) IndicatorRelease(handleBB);
   if(handleMACD != INVALID_HANDLE) IndicatorRelease(handleMACD);
   if(handleATR != INVALID_HANDLE) IndicatorRelease(handleATR);
}

//+------------------------------------------------------------------+
void OnTick()
{
   datetime currentBar = iTime(Simbolo, Timeframe, 0);
   if(currentBar == lastBarTime) return;
   lastBarTime = currentBar;
   
   // Gerenciar posição existente
   GerenciarPosicao();
   
   // Verificar sinais
   int signal = GetSignal();
   
   if(signal == 1 && PositionsTotal() == 0)
      AbrirCompra();
   else if(signal == -1 && PositionsTotal() == 0)
      AbrirVenda();
}

//+------------------------------------------------------------------+
int GetSignal()
{
   double close1 = iClose(Simbolo, Timeframe, 1);
   double close2 = iClose(Simbolo, Timeframe, 2);
   
   switch(TipoEstrategia)
   {
      case STRAT_MA_CROSS:
         return SignalMA();
      case STRAT_RSI:
         return SignalRSI();
      case STRAT_BOLLINGER:
         return SignalBollinger();
      case STRAT_MACD:
         return SignalMACD();
      case STRAT_SCALPING:
         return SignalScalping();
      case STRAT_BREAKOUT:
         return SignalBreakout();
      case STRAT_CHANNEL:
         return SignalChannel();
      case STRAT_SMC_FVG:
         return SignalSMC();
      case STRAT_RETRACAO_SR:
         return SignalRetracao();
   }
   return 0;
}

//+------------------------------------------------------------------+
int SignalMA()
{
   double fast[2], slow[2];
   CopyBuffer(handleEMA_Fast, 0, 1, 2, fast);
   CopyBuffer(handleEMA_Slow, 0, 1, 2, slow);
   if(ArraySize(fast) < 2) return 0;
   
   if(fast[0] > slow[0] && fast[1] <= slow[1]) return 1;
   if(fast[0] < slow[0] && fast[1] >= slow[1]) return -1;
   return 0;
}

//+------------------------------------------------------------------+
int SignalRSI()
{
   double rsi[2];
   CopyBuffer(handleRSI, 0, 1, 2, rsi);
   if(ArraySize(rsi) < 2) return 0;
   
   if(rsi[1] < RSI_Sobrevenda && rsi[0] >= RSI_Sobrevenda) return 1;
   if(rsi[1] > RSI_Sobrecompra && rsi[0] <= RSI_Sobrecompra) return -1;
   return 0;
}

//+------------------------------------------------------------------+
int SignalBollinger()
{
   double upper[2], mid[2], lower[2];
   CopyBuffer(handleBB, 1, 1, 2, upper);
   CopyBuffer(handleBB, 0, 1, 2, mid);
   CopyBuffer(handleBB, 2, 1, 2, lower);
   if(ArraySize(upper) < 2) return 0;
   
   double close1 = iClose(Simbolo, Timeframe, 1);
   double close2 = iClose(Simbolo, Timeframe, 2);
   
   if(close2 <= lower[1] && close1 > lower[0]) return 1;
   if(close2 >= upper[1] && close1 < upper[0]) return -1;
   return 0;
}

//+------------------------------------------------------------------+
int SignalMACD()
{
   double main[2], signal[2];
   CopyBuffer(handleMACD, 0, 1, 2, main);
   CopyBuffer(handleMACD, 1, 1, 2, signal);
   if(ArraySize(main) < 2) return 0;
   
   if(main[0] > signal[0] && main[1] <= signal[1]) return 1;
   if(main[0] < signal[0] && main[1] >= signal[1]) return -1;
   return 0;
}

//+------------------------------------------------------------------+
int SignalScalping()
{
   double fast[1];
   CopyBuffer(handleEMA_Fast, 0, 1, 1, fast);
   if(ArraySize(fast) < 1) return 0;
   
   double close1 = iClose(Simbolo, Timeframe, 1);
   double close2 = iClose(Simbolo, Timeframe, 2);
   
   if(close2 <= fast[0] && close1 > fast[0]) return 1;
   if(close2 >= fast[0] && close1 < fast[0]) return -1;
   return 0;
}

//+------------------------------------------------------------------+
int SignalBreakout()
{
   double highest = iHigh(Simbolo, Timeframe, 1);
   double lowest = iLow(Simbolo, Timeframe, 1);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   
   for(int i = 2; i <= PeriodoLookback; i++)
   {
      highest = MathMax(highest, iHigh(Simbolo, Timeframe, i));
      lowest = MathMin(lowest, iLow(Simbolo, Timeframe, i));
   }
   
   double close = iClose(Simbolo, Timeframe, 1);
   if(close > highest + BufferPontos * pt) return 1;
   if(close < lowest - BufferPontos * pt) return -1;
   return 0;
}

//+------------------------------------------------------------------+
int SignalChannel()
{
   double highest = iHigh(Simbolo, Timeframe, 1);
   double lowest = iLow(Simbolo, Timeframe, 1);
   
   for(int i = 2; i <= PeriodoLookback; i++)
   {
      highest = MathMax(highest, iHigh(Simbolo, Timeframe, i));
      lowest = MathMin(lowest, iLow(Simbolo, Timeframe, i));
   }
   
   double mid = (highest + lowest) / 2;
   double close = iClose(Simbolo, Timeframe, 1);
   
   if(close <= lowest) return 1;    // Compra no fundo do canal
   if(close >= highest) return -1;  // Venda no topo do canal
   return 0;
}

//+------------------------------------------------------------------+
int SignalSMC()
{
   double atr[1];
   CopyBuffer(handleATR, 0, 1, 1, atr);
   if(ArraySize(atr) < 1) return 0;
   
   double highest = iHigh(Simbolo, Timeframe, 1);
   double lowest = iLow(Simbolo, Timeframe, 1);
   double close = iClose(Simbolo, Timeframe, 1);
   double open1 = iOpen(Simbolo, Timeframe, 1);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   
   // Encontrar Zonas de Suporte/Resistência
   double resistance = 0, support = 999999;
   for(int i = 2; i <= PeriodoSR; i++)
   {
      resistance = MathMax(resistance, iHigh(Simbolo, Timeframe, i));
      support = MathMin(support, iLow(Simbolo, Timeframe, i));
   }
   
   // Order Block: preço toca zona e volta com força
   if(low <= support + DistanciaSR_Pontos * pt && close > support)
      return 1;   // COMPRA no Order Block de suporte
   if(high >= resistance - DistanciaSR_Pontos * pt && close < resistance)
      return -1;  // VENDA no Order Block de resistência
   
   return 0;
}

//+------------------------------------------------------------------+
int SignalRetracao()
{
   double fast[1];
   CopyBuffer(handleEMA_Fast, 0, 1, 1, fast);
   if(ArraySize(fast) < 1) return 0;
   
   double atr[1];
   CopyBuffer(handleATR, 0, 1, 1, atr);
   if(ArraySize(atr) < 1) return 0;
   
   double close = iClose(Simbolo, Timeframe, 1);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   
   // Retração: preço volta para a média
   if(close < fast[0] && close > fast[0] - atr[0] * 0.5) return 1;
   if(close > fast[0] && close < fast[0] + atr[0] * 0.5) return -1;
   return 0;
}

//+------------------------------------------------------------------+
void AbrirCompra()
{
   double ask = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? ask - StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? ask + TakeProfit * pt : 0;
   trade.Buy(Lote, Simbolo, ask, sl, tp, "GoldenAI Backtest BUY");
}

//+------------------------------------------------------------------+
void AbrirVenda()
{
   double bid = SymbolInfoDouble(Simbolo, SYMBOL_BID);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? bid + StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? bid - TakeProfit * pt : 0;
   trade.Sell(Lote, Simbolo, bid, sl, tp, "GoldenAI Backtest SELL");
}

//+------------------------------------------------------------------+
void GerenciarPosicao()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double cSL = PositionGetDouble(POSITION_SL);
      double cTP = PositionGetDouble(POSITION_TP);
      long tipo = PositionGetInteger(POSITION_TYPE);
      double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
      
      // Breakeven
      if(UsarBreakeven)
      {
         if(tipo == POSITION_TYPE_BUY)
         {
            double p = SymbolInfoDouble(Simbolo, SYMBOL_BID);
            if(p >= open + BreakevenStart * pt && cSL < open)
               trade.PositionModify(ticket, open, cTP);
         }
         else
         {
            double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
            if(p <= open - BreakevenStart * pt && (cSL > open || cSL == 0))
               trade.PositionModify(ticket, open, cTP);
         }
      }
      
      // Trailing Stop
      if(UsarTrailing)
      {
         if(tipo == POSITION_TYPE_BUY)
         {
            double p = SymbolInfoDouble(Simbolo, SYMBOL_BID);
            double nsl = p - TrailingStep * pt;
            if(p >= open + TrailingStart * pt && nsl > cSL)
               trade.PositionModify(ticket, nsl, cTP);
         }
         else
         {
            double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
            double nsl = p + TrailingStep * pt;
            if(p <= open - TrailingStart * pt && (nsl < cSL || cSL == 0))
               trade.PositionModify(ticket, nsl, cTP);
         }
      }
   }
}
//+------------------------------------------------------------------+
