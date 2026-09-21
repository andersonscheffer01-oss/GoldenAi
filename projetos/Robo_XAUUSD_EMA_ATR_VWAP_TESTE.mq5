//+------------------------------------------------------------------+
//| Robo_XAUUSD_EMA_ATR_VWAP.mq5                                    |
//| EMA 200 + EMA 20 + ATR + VWAP, com gestao avancada               |
//+------------------------------------------------------------------+
#property strict
#property version   "2.20"

#include <Trade/Trade.mqh>

CTrade trade;

enum ENUM_ModoSinal
{
   SINAL_REJEICAO = 0,
   SINAL_ENGOLFO = 1,
   SINAL_FECHAMENTO_FORTE = 2,
   SINAL_QUALQUER = 3
};

enum ENUM_TipoTrailing
{
   TRAILING_DESLIGADO = 0,
   TRAILING_ATR = 1,
   TRAILING_EMA20 = 2
};

input group "Operacional"
input int      PeriodoEMA_Tendencia = 200;
input int      PeriodoEMA_Correcao  = 20;
input int      PeriodoATR           = 14;
input int      PeriodoMediaATR      = 50;
input double   ATR_MinMultiplicador = 0.60;
input double   ATR_MaxMultiplicador = 1.80;
input bool     UsarInclinacaoEMA200 = true;
input int      BarrasInclinacaoEMA200 = 10;
input double   InclinacaoMinimaATR  = 0.10;
input double   ZonaRetesteATR       = 0.30;
input double   DistanciaMaxFechamentoATR = 0.80;
input ENUM_ModoSinal ModoSinalEntrada = SINAL_REJEICAO;
input bool     ExigirEMAsAlinhadas  = true;
input bool     ExigirConfirmacaoRompimento = true;
input double   CandleMinRangeATR    = 0.35;
input double   CandleMaxRangeATR    = 1.60;
input double   FechamentoMinimoAlemEMA20ATR = 0.05;
input bool     UsarFiltroVWAP       = true;
input bool     UsarFiltroVolume     = false;
input int      PeriodoMediaVolume   = 20;
input double   VolumeMinMultiplicador = 1.00;
input int      MaxSpreadPontos      = 0;

input group "Gestao"
input double   LoteFixo             = 0.01;
input bool     UsarRiscoPercentual  = false;
input double   RiscoPercentual      = 1.0;
input bool     UsarStopTakeEmPontos = false;
input double   StopPontos           = 300.0;
input double   AlvoPontos           = 600.0;
input double   StopATR              = 1.5;
input double   AlvoATR              = 2.5;
input int      MaxPosicoes          = 1;
input long     MagicNumber          = 20260621;

input group "Gestao Avancada"
input bool     UsarParcial          = true;
input double   ParcialATR           = 1.2;
input double   PercentualParcial    = 50.0;
input bool     UsarBreakEven        = true;
input double   BreakEvenATR         = 1.2;
input double   BreakEvenOffsetPontos = 20.0;
input ENUM_TipoTrailing TipoTrailing = TRAILING_ATR;
input double   TrailingATR          = 1.2;
input double   TrailingOffsetEMA20ATR = 0.20;
input bool     UsarLimiteDiario     = true;
input double   MetaGanhoDiario      = 0.0;
input double   LimitePerdaDiaria    = 0.0;
input int      MaxTradesDia         = 3;
input int      MaxLossesSeguidosDia = 2;

input group "Execucao"
input bool     OperarCompras        = true;
input bool     OperarVendas         = true;
input bool     OperarSomenteNovoCandle = true;
input int      HoraInicio           = 4;
input int      HoraFim              = 13;
input int      DesvioPontos         = 30;

int handleEmaTendencia = INVALID_HANDLE;
int handleEmaCorrecao  = INVALID_HANDLE;
int handleAtr          = INVALID_HANDLE;
datetime ultimoCandle  = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(DesvioPontos);

   handleEmaTendencia = iMA(_Symbol, _Period, PeriodoEMA_Tendencia, 0, MODE_EMA, PRICE_CLOSE);
   handleEmaCorrecao  = iMA(_Symbol, _Period, PeriodoEMA_Correcao, 0, MODE_EMA, PRICE_CLOSE);
   handleAtr          = iATR(_Symbol, _Period, PeriodoATR);

   if(handleEmaTendencia == INVALID_HANDLE || handleEmaCorrecao == INVALID_HANDLE || handleAtr == INVALID_HANDLE)
   {
      Print("Erro ao criar handles dos indicadores.");
      return INIT_FAILED;
   }

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(handleEmaTendencia != INVALID_HANDLE) IndicatorRelease(handleEmaTendencia);
   if(handleEmaCorrecao  != INVALID_HANDLE) IndicatorRelease(handleEmaCorrecao);
   if(handleAtr          != INVALID_HANDLE) IndicatorRelease(handleAtr);
}

//+------------------------------------------------------------------+
void OnTick()
{
   double ema200[], ema20[], atr[];
   MqlRates rates[];

   if(!CarregarDados(ema200, ema20, atr, rates))
      return;

   GerenciarPosicoes(atr[1], ema20[1]);

   if(!PodeProcurarEntrada())
      return;

   if(ContarPosicoesDoRobo() >= MaxPosicoes)
      return;

   if(!ATRNormal(atr))
      return;

   if(MaxSpreadPontos > 0 && SpreadAtualPontos() > MaxSpreadPontos)
      return;

   double vwap = CalcularVWAPDiario();
   bool filtroVWAPCompra = (!UsarFiltroVWAP || rates[1].close > vwap);
   bool filtroVWAPVenda  = (!UsarFiltroVWAP || rates[1].close < vwap);
   bool filtroVolume     = (!UsarFiltroVolume || VolumeNormal(rates));

   bool emasCompra = (!ExigirEMAsAlinhadas || ema20[1] > ema200[1]);
   bool emasVenda  = (!ExigirEMAsAlinhadas || ema20[1] < ema200[1]);

   bool tendenciaCompra = rates[1].close > ema200[1] && emasCompra && InclinacaoCompra(ema200, atr[1]);
   bool tendenciaVenda  = rates[1].close < ema200[1] && emasVenda && InclinacaoVenda(ema200, atr[1]);

   bool compra = OperarCompras
                 && tendenciaCompra
                 && SinalCompra(rates, ema20[1], atr[1])
                 && filtroVWAPCompra
                 && filtroVolume;

   bool venda = OperarVendas
                && tendenciaVenda
                && SinalVenda(rates, ema20[1], atr[1])
                && filtroVWAPVenda
                && filtroVolume;

   if(compra)
      AbrirCompra(atr[1]);
   else if(venda)
      AbrirVenda(atr[1]);
}

//+------------------------------------------------------------------+
bool CarregarDados(double &ema200[], double &ema20[], double &atr[], MqlRates &rates[])
{
   int emaBarras = MathMax(BarrasInclinacaoEMA200 + 5, 20);
   int atrBarras = PeriodoMediaATR + 5;
   int ratesBarras = MathMax(PeriodoMediaVolume + PeriodoMediaATR + 10, 80);

   ArrayResize(ema200, emaBarras);
   ArrayResize(ema20, emaBarras);
   ArrayResize(atr, atrBarras);
   ArrayResize(rates, ratesBarras);
   ArraySetAsSeries(ema200, true);
   ArraySetAsSeries(ema20, true);
   ArraySetAsSeries(atr, true);
   ArraySetAsSeries(rates, true);

   if(CopyBuffer(handleEmaTendencia, 0, 0, emaBarras, ema200) < emaBarras)
      return false;
   if(CopyBuffer(handleEmaCorrecao, 0, 0, emaBarras, ema20) < emaBarras)
      return false;
   if(CopyBuffer(handleAtr, 0, 0, atrBarras, atr) < atrBarras)
      return false;
   if(CopyRates(_Symbol, _Period, 0, ratesBarras, rates) < ratesBarras)
      return false;

   for(int i = 0; i < emaBarras; i++)
   {
      if(ema200[i] == EMPTY_VALUE || !MathIsValidNumber(ema200[i]))
         return false;
      if(ema20[i] == EMPTY_VALUE || !MathIsValidNumber(ema20[i]))
         return false;
   }

   for(int i = 0; i < atrBarras; i++)
   {
      if(atr[i] == EMPTY_VALUE || !MathIsValidNumber(atr[i]))
         return false;
   }

   for(int i = 0; i < ratesBarras; i++)
   {
      if(rates[i].time == 0 || !MathIsValidNumber(rates[i].close) ||
         !MathIsValidNumber(rates[i].high) || !MathIsValidNumber(rates[i].low))
         return false;
   }

   return true;
}

//+------------------------------------------------------------------+
bool PodeProcurarEntrada()
{
   if(!DentroDoHorario())
      return false;

   if(OperarSomenteNovoCandle && !NovoCandle())
      return false;

   if(!ControleDiarioPermiteOperar())
      return false;

   return true;
}

//+------------------------------------------------------------------+
bool NovoCandle()
{
   datetime candleAtual = iTime(_Symbol, _Period, 0);
   if(candleAtual == ultimoCandle)
      return false;

   ultimoCandle = candleAtual;
   return true;
}

//+------------------------------------------------------------------+
bool DentroDoHorario()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   if(HoraInicio <= HoraFim)
      return (dt.hour >= HoraInicio && dt.hour <= HoraFim);

   return (dt.hour >= HoraInicio || dt.hour <= HoraFim);
}

//+------------------------------------------------------------------+
bool ControleDiarioPermiteOperar()
{
   if(!UsarLimiteDiario)
      return true;

   int tradesHoje = 0;
   int perdasSeguidas = 0;
   double lucroFechado = LucroFechadoHoje(tradesHoje, perdasSeguidas);
   if(lucroFechado == -1.0)
      return false;
   double pnlDia = lucroFechado + LucroAbertoDoRobo();

   if(MaxTradesDia > 0 && tradesHoje >= MaxTradesDia)
      return false;
   if(MaxLossesSeguidosDia > 0 && perdasSeguidas >= MaxLossesSeguidosDia)
      return false;
   if(MetaGanhoDiario > 0.0 && pnlDia >= MetaGanhoDiario)
      return false;
   if(LimitePerdaDiaria > 0.0 && pnlDia <= -LimitePerdaDiaria)
      return false;

   return true;
}

//+------------------------------------------------------------------+
datetime InicioDiaServidor()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dt.hour = 0;
   dt.min = 0;
   dt.sec = 0;
   return StructToTime(dt);
}

//+------------------------------------------------------------------+
double LucroFechadoHoje(int &tradesHoje, int &perdasSeguidas)
{
   tradesHoje = 0;
   perdasSeguidas = 0;
   double lucro = 0.0;

   if(!HistorySelect(InicioDiaServidor(), TimeCurrent()))
      return -1.0;

   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;

      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != MagicNumber)
         continue;

      ENUM_DEAL_ENTRY entrada = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entrada == DEAL_ENTRY_IN)
      {
         tradesHoje++;
         continue;
      }

      if(entrada != DEAL_ENTRY_OUT && entrada != DEAL_ENTRY_INOUT && entrada != DEAL_ENTRY_OUT_BY)
         continue;

      double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      double swap = HistoryDealGetDouble(ticket, DEAL_SWAP);
      double commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION);

      if(profit == DBL_MAX || swap == DBL_MAX || commission == DBL_MAX)
         continue;

      double resultado = profit + swap + commission;

      lucro += resultado;

      if(resultado < 0.0)
         perdasSeguidas++;
      else if(resultado > 0.0)
         perdasSeguidas = 0;
   }

   return lucro;
}

//+------------------------------------------------------------------+
double LucroAbertoDoRobo()
{
   double lucro = 0.0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == MagicNumber)
      {
         lucro += PositionGetDouble(POSITION_PROFIT);
      }
   }

   return lucro;
}

//+------------------------------------------------------------------+
bool ATRNormal(const double &atr[])
{
   double soma = 0.0;
   for(int i = 2; i < PeriodoMediaATR + 2; i++)
      soma += atr[i];

   double media = soma / PeriodoMediaATR;
   if(media <= 0.0)
      return false;

   return (atr[1] >= media * ATR_MinMultiplicador && atr[1] <= media * ATR_MaxMultiplicador);
}

//+------------------------------------------------------------------+
bool InclinacaoCompra(const double &ema200[], double atrAtual)
{
   if(!UsarInclinacaoEMA200)
      return true;

   double inclinacao = ema200[1] - ema200[BarrasInclinacaoEMA200 + 1];
   return (inclinacao >= atrAtual * InclinacaoMinimaATR);
}

//+------------------------------------------------------------------+
bool InclinacaoVenda(const double &ema200[], double atrAtual)
{
   if(!UsarInclinacaoEMA200)
      return true;

   double inclinacao = ema200[BarrasInclinacaoEMA200 + 1] - ema200[1];
   return (inclinacao >= atrAtual * InclinacaoMinimaATR);
}

//+------------------------------------------------------------------+
bool SinalCompra(const MqlRates &rates[], double ema20, double atrAtual)
{
   if(!CandleSaudavel(rates[1], atrAtual))
      return false;
   if(ExigirConfirmacaoRompimento && rates[1].high <= rates[2].high)
      return false;
   if(rates[1].close < ema20 + atrAtual * FechamentoMinimoAlemEMA20ATR)
      return false;

   bool rejeicao = CandleRejeicaoCompra(rates[1], ema20, atrAtual);
   bool engolfo = CandleEngolfoCompra(rates[1], rates[2], ema20, atrAtual);
   bool fechamento = CandleFechamentoForteCompra(rates[1], ema20, atrAtual);

   if(ModoSinalEntrada == SINAL_REJEICAO)
      return rejeicao;
   if(ModoSinalEntrada == SINAL_ENGOLFO)
      return engolfo;
   if(ModoSinalEntrada == SINAL_FECHAMENTO_FORTE)
      return fechamento;

   return (rejeicao || engolfo || fechamento);
}

//+------------------------------------------------------------------+
bool SinalVenda(const MqlRates &rates[], double ema20, double atrAtual)
{
   if(ArraySize(rates) < 3)
      return false;
   if(!CandleSaudavel(rates[1], atrAtual))
      return false;
   if(ExigirConfirmacaoRompimento && rates[1].close >= rates[2].low)
      return false;
   if(rates[1].close > ema20 - atrAtual * FechamentoMinimoAlemEMA20ATR)
      return false;

   bool rejeicao = CandleRejeicaoVenda(rates[1], ema20, atrAtual);
   bool engolfo = CandleEngolfoVenda(rates[1], rates[2], ema20, atrAtual);
   bool fechamento = CandleFechamentoForteVenda(rates[1], ema20, atrAtual);

   if(ModoSinalEntrada == SINAL_REJEICAO)
      return rejeicao;
   if(ModoSinalEntrada == SINAL_ENGOLFO)
      return engolfo;
   if(ModoSinalEntrada == SINAL_FECHAMENTO_FORTE)
      return fechamento;

   return (rejeicao || engolfo || fechamento);
}

//+------------------------------------------------------------------+
bool CandleSaudavel(const MqlRates &candle, double atrAtual)
{
   if(atrAtual <= 0.0)
      return false;

   double range = candle.high - candle.low;
   if(range <= 0.0)
      return false;

   return (range >= atrAtual * CandleMinRangeATR && range <= atrAtual * CandleMaxRangeATR);
}

//+------------------------------------------------------------------+
bool ZonaCompra(const MqlRates &candle, double ema20, double atrAtual)
{
   double tolerancia = atrAtual * ZonaRetesteATR;
   double distanciaFechamento = MathAbs(candle.close - ema20);
   return (candle.low <= ema20 + tolerancia && candle.close >= ema20 - tolerancia &&
           distanciaFechamento <= atrAtual * DistanciaMaxFechamentoATR);
}

//+------------------------------------------------------------------+
bool ZonaVenda(const MqlRates &candle, double ema20, double atrAtual)
{
   double tolerancia = atrAtual * ZonaRetesteATR;
   double distanciaFechamento = MathAbs(candle.close - ema20);
   return (candle.high >= ema20 - tolerancia && candle.close <= ema20 + tolerancia &&
           distanciaFechamento <= atrAtual * DistanciaMaxFechamentoATR);
}

//+------------------------------------------------------------------+
bool CandleRejeicaoCompra(const MqlRates &candle, double ema20, double atrAtual)
{
   double corpo = MathAbs(candle.close - candle.open);
   double range = candle.high - candle.low;
   if(range <= 0.0)
      return false;

   double pavioInferior = MathMin(candle.open, candle.close) - candle.low;
   bool fechouAlta = (candle.close > candle.open);
   bool rejeitou = (pavioInferior >= MathMax(corpo * 1.20, range * 0.25) &&
                    candle.close > candle.low + range * 0.55);

   return (ZonaCompra(candle, ema20, atrAtual) && fechouAlta && rejeitou);
}

//+------------------------------------------------------------------+
bool CandleRejeicaoVenda(const MqlRates &candle, double ema20, double atrAtual)
{
   double corpo = MathAbs(candle.close - candle.open);
   double range = candle.high - candle.low;
   if(range <= 0.0)
      return false;

   double pavioSuperior = candle.high - MathMax(candle.open, candle.close);
   bool fechouBaixa = (candle.close < candle.open);
   bool rejeitou = (pavioSuperior >= MathMax(corpo * 1.20, range * 0.25) &&
                    candle.close < candle.low + range * 0.45);

   return (ZonaVenda(candle, ema20, atrAtual) && fechouBaixa && rejeitou);
}

//+------------------------------------------------------------------+
bool CandleEngolfoCompra(const MqlRates &atual, const MqlRates &anterior, double ema20, double atrAtual)
{
   bool anteriorBaixa = anterior.close < anterior.open;
   bool atualAlta = atual.close > atual.open;
   bool engolfo = atual.open <= anterior.close && atual.close >= anterior.open;

   return (ZonaCompra(atual, ema20, atrAtual) && anteriorBaixa && atualAlta && engolfo);
}

//+------------------------------------------------------------------+
bool CandleEngolfoVenda(const MqlRates &atual, const MqlRates &anterior, double ema20, double atrAtual)
{
   bool anteriorAlta = anterior.close > anterior.open;
   bool atualBaixa = atual.close < atual.open;
   bool engolfo = atual.open >= anterior.close && atual.close <= anterior.open;

   return (ZonaVenda(atual, ema20, atrAtual) && anteriorAlta && atualBaixa && engolfo);
}

//+------------------------------------------------------------------+
bool CandleFechamentoForteCompra(const MqlRates &candle, double ema20, double atrAtual)
{
   double range = candle.high - candle.low;
   if(range <= 0.0)
      return false;

   return (ZonaCompra(candle, ema20, atrAtual) &&
           candle.close > candle.open &&
           candle.close >= candle.low + range * 0.70);
}

//+------------------------------------------------------------------+
bool CandleFechamentoForteVenda(const MqlRates &candle, double ema20, double atrAtual)
{
   double range = candle.high - candle.low;
   if(range <= 0.0)
      return false;

   return (ZonaVenda(candle, ema20, atrAtual) &&
           candle.close < candle.open &&
           candle.close <= candle.low + range * 0.30);
}

//+------------------------------------------------------------------+
bool VolumeNormal(const MqlRates &rates[])
{
   double soma = 0.0;
   for(int i = 2; i < PeriodoMediaVolume + 2; i++)
      soma += (double)rates[i].tick_volume;

   double media = soma / PeriodoMediaVolume;
   if(media <= 0.0)
      return false;

   return ((double)rates[1].tick_volume >= media * VolumeMinMultiplicador);
}

//+------------------------------------------------------------------+
double CalcularVWAPDiario()
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);

   datetime inicioDia = iTime(_Symbol, PERIOD_D1, 0);
   if(inicioDia <= 0)
      return iClose(_Symbol, _Period, 1);

   int copiados = CopyRates(_Symbol, _Period, inicioDia, TimeCurrent(), rates);
   if(copiados <= 0)
      return iClose(_Symbol, _Period, 1);

   double pv = 0.0;
   double vol = 0.0;

   for(int i = 0; i < copiados; i++)
   {
      double precoTipico = (rates[i].high + rates[i].low + rates[i].close) / 3.0;
      double volume = (double)rates[i].tick_volume;
      pv += precoTipico * volume;
      vol += volume;
   }

   if(vol <= 0.0 || pv <= 0.0 || !MathIsValidNumber(pv))
      return iClose(_Symbol, _Period, 1);

   return pv / vol;
}

//+------------------------------------------------------------------+
void AbrirCompra(double atrAtual)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double distanciaStop = DistanciaStop(atrAtual);
   double distanciaAlvo = DistanciaAlvo(atrAtual);
   double sl = NormalizarPreco(ask - distanciaStop);
   double tp = NormalizarPreco(ask + distanciaAlvo);
   double lote = CalcularLote(ask - sl);

   if(lote <= 0.0)
      return;

   if(sl >= NormalizarPreco(ask))
      return;

   trade.Buy(lote, _Symbol, ask, sl, tp, "Compra EMA20/EMA200 ATR v2");
}

//+------------------------------------------------------------------+
void AbrirVenda(double atrAtual)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double distanciaStop = DistanciaStop(atrAtual);
   double distanciaAlvo = DistanciaAlvo(atrAtual);
   double sl = NormalizarPreco(bid + distanciaStop);
   double tp = NormalizarPreco(bid - distanciaAlvo);
   double lote = CalcularLote(sl - bid);

   if(lote <= 0.0)
      return;

   trade.Sell(lote, _Symbol, bid, sl, tp, "Venda EMA20/EMA200 ATR v2");
}

//+------------------------------------------------------------------+
double DistanciaStop(double atrAtual)
{
   if(UsarStopTakeEmPontos)
      return StopPontos * _Point;

   return atrAtual * StopATR;
}

//+------------------------------------------------------------------+
double DistanciaAlvo(double atrAtual)
{
   if(UsarStopTakeEmPontos)
      return AlvoPontos * _Point;

   return atrAtual * AlvoATR;
}

//+------------------------------------------------------------------+
void GerenciarPosicoes(double atrAtual, double ema20)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol ||
         PositionGetInteger(POSITION_MAGIC) != MagicNumber)
      {
         continue;
      }

      ENUM_POSITION_TYPE tipo = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double precoEntrada = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double precoAtual = (tipo == POSITION_TYPE_BUY)
                          ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                          : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      GerenciarParcial(ticket, tipo, precoEntrada, precoAtual, sl, tp, volume, atrAtual);
      GerenciarBreakEven(ticket, tipo, precoEntrada, precoAtual, sl, tp, atrAtual);
      GerenciarTrailing(ticket, tipo, precoEntrada, precoAtual, sl, tp, atrAtual, ema20);
   }
}

//+------------------------------------------------------------------+
void GerenciarParcial(ulong ticket, ENUM_POSITION_TYPE tipo, double entrada, double atual,
                      double sl, double tp, double volume, double atrAtual)
{
   if(!UsarParcial || PercentualParcial <= 0.0 || PercentualParcial >= 100.0)
      return;

   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double gatilho = atrAtual * ParcialATR;
   bool parcialJaFeita = false;
   
   // Verificação correta usando ticket para evitar parcial duplicada
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong posTicket = PositionGetTicket(i);
      if(posTicket == 0)
         continue;
      
      if(posTicket == ticket)
      {
         // Verificar se já existe uma parcial para esta posição
         double posSl = PositionGetDouble(POSITION_SL);
         if((tipo == POSITION_TYPE_BUY && posSl >= entrada) ||
            (tipo == POSITION_TYPE_SELL && posSl <= entrada && posSl > 0.0))
         {
            parcialJaFeita = true;
            break;
         }
      }
   }

   if(parcialJaFeita)
      return;

   bool atingiu = (tipo == POSITION_TYPE_BUY && atual >= entrada + gatilho) ||
                  (tipo == POSITION_TYPE_SELL && atual <= entrada - gatilho);

   if(!atingiu || volume <= minLot)
      return;

   double volumeFechar = NormalizarLote(volume * PercentualParcial / 100.0);
   if(volumeFechar < minLot || volumeFechar >= volume)
      return;

   if(trade.PositionClosePartial(ticket, volumeFechar))
   {
      double novoSL = BreakEvenPreco(tipo, entrada);
      trade.PositionModify(ticket, novoSL, tp);
   }
}

//+------------------------------------------------------------------+
void GerenciarBreakEven(ulong ticket, ENUM_POSITION_TYPE tipo, double entrada, double atual,
                        double sl, double tp, double atrAtual)
{
   if(!UsarBreakEven)
      return;

   double gatilho = atrAtual * BreakEvenATR;
   double novoSL = BreakEvenPreco(tipo, entrada);

   if(tipo == POSITION_TYPE_BUY)
   {
      if(atual < entrada + gatilho)
         return;
      if(sl >= novoSL)
         return;
   }
   else
   {
      if(atual > entrada - gatilho)
         return;
      if(sl > 0.0 && sl <= novoSL)
         return;
   }

   trade.PositionModify(ticket, novoSL, tp);
}

//+------------------------------------------------------------------+
void GerenciarTrailing(ulong ticket, ENUM_POSITION_TYPE tipo, double entrada, double atual,
                       double sl, double tp, double atrAtual, double ema20)
{
   if(TipoTrailing == TRAILING_DESLIGADO)
      return;

   double novoSL = sl;

   if(TipoTrailing == TRAILING_ATR)
   {
      if(tipo == POSITION_TYPE_BUY)
         novoSL = NormalizarPreco(atual - atrAtual * TrailingATR);
      else
         novoSL = NormalizarPreco(atual + atrAtual * TrailingATR);
   }
   else if(TipoTrailing == TRAILING_EMA20)
   {
      if(tipo == POSITION_TYPE_BUY)
         novoSL = NormalizarPreco(ema20 - atrAtual * TrailingOffsetEMA20ATR);
      else
         novoSL = NormalizarPreco(ema20 + atrAtual * TrailingOffsetEMA20ATR);
   }

   // Trava de proteção: o trailing nunca move o stop para além do preço de entrada
   if(tipo == POSITION_TYPE_BUY && novoSL <= entrada)
      return;
   if(tipo == POSITION_TYPE_SELL && novoSL >= entrada)
      return;

   if(tipo == POSITION_TYPE_BUY)
   {
      if(novoSL <= sl)
         return;
   }
   else
   {
      if(sl > 0.0 && novoSL >= sl)
         return;
   }

   trade.PositionModify(ticket, novoSL, tp);
}

//+------------------------------------------------------------------+
double BreakEvenPreco(ENUM_POSITION_TYPE tipo, double entrada)
{
   if(BreakEvenOffsetPontos <= 0.0)
      return entrada;

   double offset = BreakEvenOffsetPontos * _Point;

   if(tipo == POSITION_TYPE_BUY)
      return NormalizarPreco(entrada + offset);

   return NormalizarPreco(entrada - offset);
}

//+------------------------------------------------------------------+
double CalcularLote(double distanciaStop)
{
   if(!UsarRiscoPercentual)
      return NormalizarLote(LoteFixo);

   double saldo = AccountInfoDouble(ACCOUNT_BALANCE);
   double riscoDinheiro = saldo * (RiscoPercentual / 100.0);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);

   if(distanciaStop <= 0.0 || !(tickSize > 0.0) || !(tickValue > 0.0) ||
      !MathIsValidNumber(tickSize) || !MathIsValidNumber(tickValue))
      return NormalizarLote(LoteFixo);

   double perdaPorLote = (distanciaStop / tickSize) * tickValue;

   if(perdaPorLote <= 0.0 || !MathIsValidNumber(perdaPorLote))
      return NormalizarLote(LoteFixo);

   double loteCalculado = riscoDinheiro / perdaPorLote;

   if(!MathIsValidNumber(loteCalculado) || loteCalculado <= 0.0)
      return NormalizarLote(LoteFixo);

   return NormalizarLote(loteCalculado);
}

//+------------------------------------------------------------------+
double NormalizarLote(double lote)
{
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   lote = MathMax(minLot, MathMin(maxLot, lote));
   if(step > 0.0)
      lote = MathFloor(lote / step) * step;

   int digitos = 2;
   if(step > 0.0)
      digitos = (int)MathMax(0, MathRound(-MathLog10(step)));

   return NormalizeDouble(lote, digitos);
}

//+------------------------------------------------------------------+
double NormalizarPreco(double preco)
{
   return NormalizeDouble(preco, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
}

//+------------------------------------------------------------------+
int SpreadAtualPontos()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   return (int)MathRound((ask - bid) / _Point);
}

//+------------------------------------------------------------------+
int ContarPosicoesDoRobo()
{
   int total = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == MagicNumber)
      {
         total++;
      }
   }

   return total;
}
//+------------------------------------------------------------------+
