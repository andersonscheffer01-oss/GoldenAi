#property strict
#property version   "1.00"
#property description "Tendencia MA 9/21/50 com pullback, rompimento e confirmacao por volume"

#include <Trade/Trade.mqh>

CTrade trade;

input group "Sinal"
input ENUM_TIMEFRAMES PeriodoGrafico = PERIOD_M15;
input int PeriodoMediaRapida = 9;
input int PeriodoMediaIntermedia = 21;
input int PeriodoMediaLenta = 50;
input ENUM_MA_METHOD MetodoDasMedias = MODE_EMA;
input ENUM_APPLIED_PRICE PrecoAplicado = PRICE_CLOSE;
input bool UsarPullback = true;
input bool UsarRompimento = true;
input int PeriodoVolume = 20;
input double MultiplicadorVolume = 1.10;
input int BarrasConsolidacao = 10;
input double MaximoCaixaATR = 2.00;
input bool ExigirPullbackComVolumeBaixo = false;

input group "Risco e ordem"
input double LoteFixo = 0.01;
input bool UsarRiscoPercentual = false;
input double RiscoPercentual = 1.00;
input int PeriodoATR = 14;
input double BufferATR = 0.20;
input double RelacaoRiscoRetorno = 2.00;
input int SpreadMaximoPontos = 80;
input int MaximoPosicoes = 1;
input ulong NumeroMagico = 92150;

input group "Gerenciamento"
input bool UsarBreakEven = true;
input double AtivarBreakEvenEmR = 1.00;
input int DistanciaBreakEvenPontos = 2;
input bool UsarTrailingMedia21 = true;
input double BufferTrailingATR = 0.30;

input group "Visualizacao no grafico"
input bool MostrarMedia9 = true;
input bool MostrarMedia21 = true;
input bool MostrarMedia50 = true;
input bool MostrarVolume = true;

// Alias internos para preservar a logica do robo.
#define InpTimeframe PeriodoGrafico
#define InpFastMAPeriod PeriodoMediaRapida
#define InpMediumMAPeriod PeriodoMediaIntermedia
#define InpSlowMAPeriod PeriodoMediaLenta
#define InpMAMethod MetodoDasMedias
#define InpAppliedPrice PrecoAplicado
#define InpUsePullback UsarPullback
#define InpUseBreakout UsarRompimento
#define InpVolumePeriod PeriodoVolume
#define InpVolumeMultiplier MultiplicadorVolume
#define InpBreakoutBars BarrasConsolidacao
#define InpMaxBoxATR MaximoCaixaATR
#define InpRequireQuietPullback ExigirPullbackComVolumeBaixo
#define InpLots LoteFixo
#define InpUseRiskPercent UsarRiscoPercentual
#define InpRiskPercent RiscoPercentual
#define InpATRPeriod PeriodoATR
#define InpATRBuffer BufferATR
#define InpRewardRisk RelacaoRiscoRetorno
#define InpMaxSpreadPoints SpreadMaximoPontos
#define InpMaxPositions MaximoPosicoes
#define InpMagic NumeroMagico
#define InpUseBreakEven UsarBreakEven
#define InpBreakEvenAtR AtivarBreakEvenEmR
#define InpBreakEvenOffsetPoints DistanciaBreakEvenPontos
#define InpUseTrailingMA21 UsarTrailingMedia21
#define InpTrailingATRBuffer BufferTrailingATR

int hFast = INVALID_HANDLE;
int hMedium = INVALID_HANDLE;
int hSlow = INVALID_HANDLE;
int hATR = INVALID_HANDLE;
int hVolume = INVALID_HANDLE;
datetime lastBarTime = 0;

double NormalizePrice(const double price)
{
   return NormalizeDouble(price, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
}

bool IsNewBar(MqlRates &rates[])
{
   if(ArraySize(rates) < 3)
      return false;
   if(rates[0].time == lastBarTime)
      return false;
   lastBarTime = rates[0].time;
   return true;
}

bool LoadData(MqlRates &rates[], double &fast[], double &medium[], double &slow[], double &atr[])
{
   int needed = MathMax(80, InpBreakoutBars + InpVolumePeriod + 10);
   ArraySetAsSeries(rates, true);
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(medium, true);
   ArraySetAsSeries(slow, true);
   ArraySetAsSeries(atr, true);

   if(CopyRates(_Symbol, InpTimeframe, 0, needed, rates) < needed)
      return false;
   if(CopyBuffer(hFast, 0, 0, needed, fast) < needed)
      return false;
   if(CopyBuffer(hMedium, 0, 0, needed, medium) < needed)
      return false;
   if(CopyBuffer(hSlow, 0, 0, needed, slow) < needed)
      return false;
   if(CopyBuffer(hATR, 0, 0, needed, atr) < needed)
      return false;
   return true;
}

double AverageVolume(const MqlRates &rates[], const int start, const int count)
{
   if(count <= 0)
      return 0.0;
   double total = 0.0;
   for(int i = start; i < start + count; i++)
      total += (double)rates[i].tick_volume;
   return total / count;
}

bool VolumeConfirms(const MqlRates &rates[], const int index)
{
   double average = AverageVolume(rates, index + 1, InpVolumePeriod);
   if(average <= 0.0)
      return false;
   return (double)rates[index].tick_volume >= average * InpVolumeMultiplier;
}

bool QuietPullback(const MqlRates &rates[])
{
   if(!InpRequireQuietPullback)
      return true;
   double average = AverageVolume(rates, 3, InpVolumePeriod);
   double pullbackAverage = AverageVolume(rates, 2, 2);
   return average > 0.0 && pullbackAverage <= average;
}

bool TrendUp(const MqlRates &rates[], const double &fast[], const double &medium[], const double &slow[])
{
   return fast[1] > medium[1] && medium[1] > slow[1] &&
          slow[1] > slow[1 + 3] && rates[1].close > fast[1];
}

bool TrendDown(const MqlRates &rates[], const double &fast[], const double &medium[], const double &slow[])
{
   return fast[1] < medium[1] && medium[1] < slow[1] &&
          slow[1] < slow[1 + 3] && rates[1].close < fast[1];
}

bool PullbackBuy(const MqlRates &rates[], const double &fast[], const double &medium[], const double &slow[])
{
   if(!TrendUp(rates, fast, medium, slow) || !QuietPullback(rates) || !VolumeConfirms(rates, 1))
      return false;
   bool touchedMA = rates[1].low <= fast[1] || rates[1].low <= medium[1] || rates[1].low <= slow[1];
   bool bullishTrigger = rates[1].close > rates[1].open && rates[1].close > rates[2].high;
   return touchedMA && bullishTrigger;
}

bool PullbackSell(const MqlRates &rates[], const double &fast[], const double &medium[], const double &slow[])
{
   if(!TrendDown(rates, fast, medium, slow) || !QuietPullback(rates) || !VolumeConfirms(rates, 1))
      return false;
   bool touchedMA = rates[1].high >= fast[1] || rates[1].high >= medium[1] || rates[1].high >= slow[1];
   bool bearishTrigger = rates[1].close < rates[1].open && rates[1].close < rates[2].low;
   return touchedMA && bearishTrigger;
}

double BoxHigh(const MqlRates &rates[])
{
   double value = rates[2].high;
   for(int i = 3; i < 2 + InpBreakoutBars; i++)
      value = MathMax(value, rates[i].high);
   return value;
}

double BoxLow(const MqlRates &rates[])
{
   double value = rates[2].low;
   for(int i = 3; i < 2 + InpBreakoutBars; i++)
      value = MathMin(value, rates[i].low);
   return value;
}

bool BreakoutBuy(const MqlRates &rates[], const double &fast[], const double &medium[], const double &slow[], const double &atr[])
{
   if(!TrendUp(rates, fast, medium, slow) || !VolumeConfirms(rates, 1))
      return false;
   double top = BoxHigh(rates);
   double bottom = BoxLow(rates);
   return top > bottom && top - bottom <= atr[1] * InpMaxBoxATR && rates[1].close > top;
}

bool BreakoutSell(const MqlRates &rates[], const double &fast[], const double &medium[], const double &slow[], const double &atr[])
{
   if(!TrendDown(rates, fast, medium, slow) || !VolumeConfirms(rates, 1))
      return false;
   double top = BoxHigh(rates);
   double bottom = BoxLow(rates);
   return top > bottom && top - bottom <= atr[1] * InpMaxBoxATR && rates[1].close < bottom;
}

int CountPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic)
         count++;
   }
   return count;
}

double LotSize(const double stopDistance)
{
   if(!InpUseRiskPercent || stopDistance <= 0.0)
      return InpLots;
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = balance * InpRiskPercent / 100.0;
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0)
      return InpLots;
   double lots = riskMoney / (stopDistance / tickSize * tickValue);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lots = MathMax(minLot, MathMin(maxLot, lots));
   if(step > 0.0)
      lots = MathFloor(lots / step) * step;
   return NormalizeDouble(lots, 2);
}

bool ValidStops(const ENUM_ORDER_TYPE type, const double sl, const double tp)
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int stopsLevel = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minimum = stopsLevel * point;
   double price = type == ORDER_TYPE_BUY ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(type == ORDER_TYPE_BUY)
      return price - sl >= minimum && tp - price >= minimum;
   return sl - price >= minimum && price - tp >= minimum;
}

void OpenTrade(const ENUM_ORDER_TYPE type, const double stopReference, const double atrValue)
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price = type == ORDER_TYPE_BUY ? ask : bid;
   double sl = type == ORDER_TYPE_BUY ? stopReference - atrValue * InpATRBuffer : stopReference + atrValue * InpATRBuffer;
   double distance = MathAbs(price - sl);
   if(distance <= point)
      return;
   double tp = type == ORDER_TYPE_BUY ? price + distance * InpRewardRisk : price - distance * InpRewardRisk;
   sl = NormalizePrice(sl);
   tp = NormalizePrice(tp);
   if(!ValidStops(type, sl, tp))
   {
      Print("Stops muito proximos para o broker. Ordem ignorada.");
      return;
   }
   double lots = LotSize(distance);
   bool sent = type == ORDER_TYPE_BUY
               ? trade.Buy(lots, _Symbol, 0.0, sl, tp, "MA9-21-50 Volume BUY")
               : trade.Sell(lots, _Symbol, 0.0, sl, tp, "MA9-21-50 Volume SELL");
   if(!sent)
      PrintFormat("Falha ao enviar ordem: %d - %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

void ManagePosition(const double &medium[], const double &atr[])
{
   if(!PositionSelect(_Symbol) || (ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic)
      return;
   ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double entry = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   double current = type == POSITION_TYPE_BUY ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double risk = MathAbs(entry - sl);
   if(risk <= 0.0)
      return;
   double rMultiple = type == POSITION_TYPE_BUY ? (current - entry) / risk : (entry - current) / risk;
   double newSL = sl;
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(InpUseBreakEven && rMultiple >= InpBreakEvenAtR)
   {
      double be = type == POSITION_TYPE_BUY ? entry + InpBreakEvenOffsetPoints * point : entry - InpBreakEvenOffsetPoints * point;
      if(type == POSITION_TYPE_BUY)
         newSL = MathMax(newSL, be);
      else
         newSL = (newSL == 0.0 ? be : MathMin(newSL, be));
   }
   if(InpUseTrailingMA21 && rMultiple >= 1.0)
   {
      double trail = type == POSITION_TYPE_BUY ? medium[1] - atr[1] * InpTrailingATRBuffer : medium[1] + atr[1] * InpTrailingATRBuffer;
      if(type == POSITION_TYPE_BUY)
         newSL = MathMax(newSL, trail);
      else
         newSL = (newSL == 0.0 ? trail : MathMin(newSL, trail));
   }
   newSL = NormalizePrice(newSL);
   if(newSL <= 0.0 || MathAbs(newSL - sl) < point)
      return;
   if(type == POSITION_TYPE_BUY && newSL >= current)
      return;
   if(type == POSITION_TYPE_SELL && newSL <= current)
      return;
   if(!trade.PositionModify(_Symbol, newSL, tp))
      PrintFormat("Falha ao ajustar stop: %d - %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

int OnInit()
{
   if(InpFastMAPeriod <= 0 || InpMediumMAPeriod <= InpFastMAPeriod || InpSlowMAPeriod <= InpMediumMAPeriod || InpVolumePeriod < 2)
      return INIT_PARAMETERS_INCORRECT;
   hFast = iMA(_Symbol, InpTimeframe, InpFastMAPeriod, 0, InpMAMethod, InpAppliedPrice);
   hMedium = iMA(_Symbol, InpTimeframe, InpMediumMAPeriod, 0, InpMAMethod, InpAppliedPrice);
   hSlow = iMA(_Symbol, InpTimeframe, InpSlowMAPeriod, 0, InpMAMethod, InpAppliedPrice);
   hATR = iATR(_Symbol, InpTimeframe, InpATRPeriod);
   if(hFast == INVALID_HANDLE || hMedium == INVALID_HANDLE || hSlow == INVALID_HANDLE || hATR == INVALID_HANDLE)
      return INIT_FAILED;
   if(MostrarVolume)
      hVolume = iVolumes(_Symbol, InpTimeframe, VOLUME_TICK);
   if(MostrarMedia9 && !ChartIndicatorAdd(0, 0, hFast))
      Print("Nao foi possivel plotar a Media 9 no grafico.");
   if(MostrarMedia21 && !ChartIndicatorAdd(0, 0, hMedium))
      Print("Nao foi possivel plotar a Media 21 no grafico.");
   if(MostrarMedia50 && !ChartIndicatorAdd(0, 0, hSlow))
      Print("Nao foi possivel plotar a Media 50 no grafico.");
   if(MostrarVolume && hVolume != INVALID_HANDLE && !ChartIndicatorAdd(0, 1, hVolume))
      Print("Nao foi possivel plotar o Volume no grafico.");
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(_Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hFast != INVALID_HANDLE) IndicatorRelease(hFast);
   if(hMedium != INVALID_HANDLE) IndicatorRelease(hMedium);
   if(hSlow != INVALID_HANDLE) IndicatorRelease(hSlow);
   if(hATR != INVALID_HANDLE) IndicatorRelease(hATR);
   if(hVolume != INVALID_HANDLE) IndicatorRelease(hVolume);
}

void OnTick()
{
   MqlRates rates[];
   double fast[], medium[], slow[], atr[];
   if(!LoadData(rates, fast, medium, slow, atr))
      return;

   ManagePosition(medium, atr);
   if(!IsNewBar(rates))
      return;
   if(CountPositions() >= InpMaxPositions)
      return;
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double spread = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / point;
   if(spread > InpMaxSpreadPoints)
      return;

   bool buy = false;
   bool sell = false;
   double buyStop = rates[1].low;
   double sellStop = rates[1].high;
   if(InpUsePullback)
   {
      buy = PullbackBuy(rates, fast, medium, slow);
      sell = PullbackSell(rates, fast, medium, slow);
   }
   if(InpUseBreakout && !buy && !sell)
   {
      buy = BreakoutBuy(rates, fast, medium, slow, atr);
      sell = BreakoutSell(rates, fast, medium, slow, atr);
      if(buy) buyStop = BoxLow(rates);
      if(sell) sellStop = BoxHigh(rates);
   }
   if(buy)
      OpenTrade(ORDER_TYPE_BUY, buyStop, atr[1]);
   else if(sell)
      OpenTrade(ORDER_TYPE_SELL, sellStop, atr[1]);
}
