//+------------------------------------------------------------------+
//| Golden Midas VWAP                                                |
//| VWAP ancorada para leitura de pullbacks no MetaTrader 5          |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 9
#property indicator_plots   9

#property indicator_label1  "Midas VWAP"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrOrange
#property indicator_width1  2
#property indicator_label2  "Banda superior"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrDarkOrange
#property indicator_style2  STYLE_DOT
#property indicator_label3  "Banda inferior"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrDarkOrange
#property indicator_style3  STYLE_DOT
#property indicator_label4  "EMA 9"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrGold
#property indicator_width4  1
#property indicator_label5  "EMA 21"
#property indicator_type5   DRAW_LINE
#property indicator_color5  clrDodgerBlue
#property indicator_width5  1
#property indicator_label6  "EMA 50"
#property indicator_type6   DRAW_LINE
#property indicator_color6  clrMediumPurple
#property indicator_width6  1
#property indicator_label7  "Compra pullback"
#property indicator_type7   DRAW_ARROW
#property indicator_color7  clrLimeGreen
#property indicator_width7  2
#property indicator_label8  "Venda pullback"
#property indicator_type8   DRAW_ARROW
#property indicator_color8  clrRed
#property indicator_width8  2
#property indicator_label9  "Âncora"
#property indicator_type9   DRAW_ARROW
#property indicator_color9  clrWhite
#property indicator_width9  1

enum ENUM_TIPO_ANCORA
  {
   ANCORA_SESSAO = 0,       // Início do dia do candle
   ANCORA_PIVOT = 1,        // Último pivô confirmado
   ANCORA_BARRAS = 2,       // Quantidade fixa de barras
   ANCORA_MANUAL = 3        // Vela informada manualmente
  };

input group "CONFIGURAÇÃO DA VWAP"
input ENUM_TIPO_ANCORA TipoDeAncora = ANCORA_SESSAO;
input int             BarrasDaAncora = 100;
input int             PeriodoPivo = 5;
input datetime        DataHoraDaAncora = D'2026.01.01 00:00';
input ENUM_APPLIED_PRICE PrecoDoCalculo = PRICE_TYPICAL;
input ENUM_APPLIED_PRICE PrecoDoMarcador = PRICE_CLOSE;
input double          MultiplicadorDesvio = 1.0;

input group "FILTRO DO PULLBACK"
input bool            UsarFiltroDeTendencia = true;
input int             PeriodoEMARapida = 9;
input int             PeriodoEMAMedia = 21;
input int             PeriodoEMALenta = 50;
input int             ToleranciaPullbackPontos = 30;
input bool            UsarFiltroDeVolume = true;
input int             PeriodoVolume = 20;
input double          VolumeMinimoRelativo = 1.10;

input group "VISUALIZAÇÃO"
input bool            PlotarBandas = true;
input bool            UsarSomenteVWAP = false;
input bool            PlotarMedias = true;
input bool            PlotarSetas = true;
input bool            PlotarMarcadorDaAncora = true;
input int             MaximoDeBarrasCalculadas = 1500;

double VwapBuffer[];
double BandaSuperiorBuffer[];
double BandaInferiorBuffer[];
double Ema9Buffer[];
double Ema21Buffer[];
double Ema50Buffer[];
double CompraBuffer[];
double VendaBuffer[];
double AncoraBuffer[];

int handleEma9 = INVALID_HANDLE;
int handleEma21 = INVALID_HANDLE;
int handleEma50 = INVALID_HANDLE;
int indiceAncoraManual = -1;

double PrecoAplicado(const int index,
                     const double &open[],
                     const double &high[],
                     const double &low[],
                     const double &close[])
  {
   if(PrecoDoCalculo == PRICE_OPEN) return open[index];
   if(PrecoDoCalculo == PRICE_HIGH) return high[index];
   if(PrecoDoCalculo == PRICE_LOW) return low[index];
   if(PrecoDoCalculo == PRICE_MEDIAN) return (high[index] + low[index]) / 2.0;
   if(PrecoDoCalculo == PRICE_WEIGHTED) return (high[index] + low[index] + close[index] + close[index]) / 4.0;
   return (high[index] + low[index] + close[index]) / 3.0;
  }

bool MesmoDia(const datetime a,const datetime b)
  {
   MqlDateTime da,db;
   TimeToStruct(a,da);
   TimeToStruct(b,db);
   return da.year == db.year && da.day_of_year == db.day_of_year;
  }

int EncontrarAncora(const int index,const int total,const datetime &time[])
  {
   if(TipoDeAncora == ANCORA_MANUAL)
      return indiceAncoraManual >= 0 ? indiceAncoraManual : MathMin(total - 1,index + MathMax(1,BarrasDaAncora) - 1);
   if(TipoDeAncora == ANCORA_BARRAS)
      return MathMin(total - 1,index + MathMax(1,BarrasDaAncora) - 1);

   if(TipoDeAncora == ANCORA_SESSAO)
     {
      int j = index;
      while(j + 1 < total && MesmoDia(time[j],time[j + 1])) j++;
      return j;
     }

   // O pivô só é usado depois de confirmado por barras dos dois lados.
   int esquerda = MathMax(2,PeriodoPivo);
   int direita = MathMax(2,PeriodoPivo);
   int limite = MathMin(total - esquerda - 1,index + 400);
   for(int j = index + direita;j <= limite;j++)
     {
      bool topo = true;
      bool fundo = true;
      double h = iHigh(_Symbol,_Period,j);
      double l = iLow(_Symbol,_Period,j);
      for(int k = 1;k <= esquerda && (topo || fundo);k++)
        {
         if(h <= iHigh(_Symbol,_Period,j - k) || h <= iHigh(_Symbol,_Period,j + k)) topo = false;
         if(l >= iLow(_Symbol,_Period,j - k) || l >= iLow(_Symbol,_Period,j + k)) fundo = false;
        }
      if(topo || fundo) return j;
     }
   return MathMin(total - 1,index + MathMax(1,BarrasDaAncora) - 1);
  }

int LocalizarAncoraManual(const int total,const datetime &time[])
  {
   if(DataHoraDaAncora <= 0) return -1;
   int melhor = -1;
   long menorDiferenca = LONG_MAX;
   for(int i = 0;i < total;i++)
     {
      long diferenca = (long)MathAbs((double)(time[i] - DataHoraDaAncora));
      if(diferenca < menorDiferenca)
        {
         menorDiferenca = diferenca;
         melhor = i;
        }
     }
   return melhor;
  }

double VolumeRelativo(const int index,const int total,const long &tick_volume[])
  {
   int periodo = MathMax(2,PeriodoVolume);
   if(index + periodo >= total) return 0.0;
   double media = 0.0;
   for(int j = index + 1;j <= index + periodo;j++) media += (double)tick_volume[j];
   media /= periodo;
   return media > 0.0 ? (double)tick_volume[index] / media : 0.0;
  }

int OnInit()
  {
   SetIndexBuffer(0,VwapBuffer,INDICATOR_DATA);
   SetIndexBuffer(1,BandaSuperiorBuffer,INDICATOR_DATA);
   SetIndexBuffer(2,BandaInferiorBuffer,INDICATOR_DATA);
   SetIndexBuffer(3,Ema9Buffer,INDICATOR_DATA);
   SetIndexBuffer(4,Ema21Buffer,INDICATOR_DATA);
   SetIndexBuffer(5,Ema50Buffer,INDICATOR_DATA);
   SetIndexBuffer(6,CompraBuffer,INDICATOR_DATA);
   SetIndexBuffer(7,VendaBuffer,INDICATOR_DATA);
   SetIndexBuffer(8,AncoraBuffer,INDICATOR_DATA);

   PlotIndexSetInteger(6,PLOT_ARROW,233);
   PlotIndexSetInteger(7,PLOT_ARROW,234);
   PlotIndexSetInteger(8,PLOT_ARROW,159);
   PlotIndexSetDouble(6,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   PlotIndexSetDouble(7,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   PlotIndexSetDouble(8,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   if(!PlotarBandas || UsarSomenteVWAP)
     {
      PlotIndexSetInteger(1,PLOT_DRAW_TYPE,DRAW_NONE);
      PlotIndexSetInteger(2,PLOT_DRAW_TYPE,DRAW_NONE);
     }
   if(!PlotarMedias)
     {
      PlotIndexSetInteger(3,PLOT_DRAW_TYPE,DRAW_NONE);
      PlotIndexSetInteger(4,PLOT_DRAW_TYPE,DRAW_NONE);
      PlotIndexSetInteger(5,PLOT_DRAW_TYPE,DRAW_NONE);
     }
   if(!PlotarSetas)
     {
      PlotIndexSetInteger(6,PLOT_DRAW_TYPE,DRAW_NONE);
      PlotIndexSetInteger(7,PLOT_DRAW_TYPE,DRAW_NONE);
     }
   if(!PlotarMarcadorDaAncora) PlotIndexSetInteger(8,PLOT_DRAW_TYPE,DRAW_NONE);

   handleEma9 = iMA(_Symbol,_Period,MathMax(1,PeriodoEMARapida),0,MODE_EMA,PRICE_CLOSE);
   handleEma21 = iMA(_Symbol,_Period,MathMax(1,PeriodoEMAMedia),0,MODE_EMA,PRICE_CLOSE);
   handleEma50 = iMA(_Symbol,_Period,MathMax(1,PeriodoEMALenta),0,MODE_EMA,PRICE_CLOSE);
   if(handleEma9 == INVALID_HANDLE || handleEma21 == INVALID_HANDLE || handleEma50 == INVALID_HANDLE)
      return INIT_FAILED;
   if(TipoDeAncora == ANCORA_MANUAL)
     {
      indiceAncoraManual = iBarShift(_Symbol,_Period,DataHoraDaAncora,false);
      if(indiceAncoraManual < 0) Print("Golden Midas VWAP: horário da âncora não encontrado no histórico carregado.");
     }
   IndicatorSetString(INDICATOR_SHORTNAME,"Golden Midas VWAP");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(handleEma9 != INVALID_HANDLE) IndicatorRelease(handleEma9);
   if(handleEma21 != INVALID_HANDLE) IndicatorRelease(handleEma21);
   if(handleEma50 != INVALID_HANDLE) IndicatorRelease(handleEma50);
  }

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   int minimo = MathMax(PeriodoVolume + 10,MathMax(PeriodoEMALenta,PeriodoPivo * 2 + 10));
   if(rates_total < minimo) return 0;
   // Reaplica a visibilidade em cada atualização para refletir imediatamente os inputs.
   PlotIndexSetInteger(0,PLOT_DRAW_TYPE,DRAW_LINE);
   PlotIndexSetInteger(1,PLOT_DRAW_TYPE,(PlotarBandas && !UsarSomenteVWAP) ? DRAW_LINE : DRAW_NONE);
   PlotIndexSetInteger(2,PLOT_DRAW_TYPE,(PlotarBandas && !UsarSomenteVWAP) ? DRAW_LINE : DRAW_NONE);
   PlotIndexSetInteger(3,PLOT_DRAW_TYPE,PlotarMedias ? DRAW_LINE : DRAW_NONE);
   PlotIndexSetInteger(4,PLOT_DRAW_TYPE,PlotarMedias ? DRAW_LINE : DRAW_NONE);
   PlotIndexSetInteger(5,PLOT_DRAW_TYPE,PlotarMedias ? DRAW_LINE : DRAW_NONE);
   PlotIndexSetInteger(6,PLOT_DRAW_TYPE,PlotarSetas ? DRAW_ARROW : DRAW_NONE);
   PlotIndexSetInteger(7,PLOT_DRAW_TYPE,PlotarSetas ? DRAW_ARROW : DRAW_NONE);
   PlotIndexSetInteger(8,PLOT_DRAW_TYPE,PlotarMarcadorDaAncora ? DRAW_ARROW : DRAW_NONE);
   ArraySetAsSeries(VwapBuffer,true);
   ArraySetAsSeries(BandaSuperiorBuffer,true);
   ArraySetAsSeries(BandaInferiorBuffer,true);
   ArraySetAsSeries(Ema9Buffer,true);
   ArraySetAsSeries(Ema21Buffer,true);
   ArraySetAsSeries(Ema50Buffer,true);
   ArraySetAsSeries(CompraBuffer,true);
   ArraySetAsSeries(VendaBuffer,true);
   ArraySetAsSeries(AncoraBuffer,true);

   int copiados9 = CopyBuffer(handleEma9,0,0,rates_total,Ema9Buffer);
   int copiados21 = CopyBuffer(handleEma21,0,0,rates_total,Ema21Buffer);
   int copiados50 = CopyBuffer(handleEma50,0,0,rates_total,Ema50Buffer);
   if(copiados9 <= 0 || copiados21 <= 0 || copiados50 <= 0)
     {
      for(int i = 0;i < rates_total;i++)
        {
         Ema9Buffer[i] = close[i];
         Ema21Buffer[i] = close[i];
         Ema50Buffer[i] = close[i];
        }
     }

   if(TipoDeAncora == ANCORA_MANUAL)
      indiceAncoraManual = LocalizarAncoraManual(rates_total,time);

   int limite = MathMin(rates_total - minimo,MathMax(100,MaximoDeBarrasCalculadas));
   for(int i = rates_total - 1;i >= 0;i--)
     {
      VwapBuffer[i] = EMPTY_VALUE;
      BandaSuperiorBuffer[i] = EMPTY_VALUE;
      BandaInferiorBuffer[i] = EMPTY_VALUE;
      CompraBuffer[i] = EMPTY_VALUE;
      VendaBuffer[i] = EMPTY_VALUE;
      AncoraBuffer[i] = EMPTY_VALUE;
     }

   for(int i = limite;i >= 0;i--)
     {
      int ancora = EncontrarAncora(i,rates_total,time);
      if(TipoDeAncora == ANCORA_MANUAL && ancora < i) continue;
      double somaPV = 0.0,somaV = 0.0,somaQuadrado = 0.0;
      for(int j = i;j <= ancora;j++)
        {
         double p = PrecoAplicado(j,open,high,low,close);
         double v = (double)tick_volume[j];
         if(v <= 0.0) v = 1.0;
         somaPV += p * v;
         somaV += v;
        }
      if(somaV <= 0.0) continue;
      double vwap = somaPV / somaV;
      for(int j = i;j <= ancora;j++)
        {
         double p = PrecoAplicado(j,open,high,low,close);
         double v = (double)tick_volume[j];
         if(v <= 0.0) v = 1.0;
         somaQuadrado += (p - vwap) * (p - vwap) * v;
        }
      double desvio = MathSqrt(somaQuadrado / somaV) * MathMax(0.0,MultiplicadorDesvio);
      VwapBuffer[i] = vwap;
      BandaSuperiorBuffer[i] = vwap + desvio;
      BandaInferiorBuffer[i] = vwap - desvio;
      if(i == ancora)
        {
         if(PrecoDoMarcador == PRICE_OPEN) AncoraBuffer[i] = open[i];
         else if(PrecoDoMarcador == PRICE_HIGH) AncoraBuffer[i] = high[i];
         else if(PrecoDoMarcador == PRICE_LOW) AncoraBuffer[i] = low[i];
         else if(PrecoDoMarcador == PRICE_MEDIAN) AncoraBuffer[i] = (high[i] + low[i]) / 2.0;
         else if(PrecoDoMarcador == PRICE_WEIGHTED) AncoraBuffer[i] = (high[i] + low[i] + close[i] + close[i]) / 4.0;
         else AncoraBuffer[i] = close[i];
        }

      // Candle 0 nunca gera seta: a confirmação ocorre no candle fechado.
      if(i < 1 || !PlotarSetas) continue;
      double tolerancia = ToleranciaPullbackPontos * _Point;
      bool tendenciaCompra = !UsarFiltroDeTendencia || (Ema9Buffer[i] > Ema21Buffer[i] && Ema21Buffer[i] > Ema50Buffer[i]);
      bool tendenciaVenda = !UsarFiltroDeTendencia || (Ema9Buffer[i] < Ema21Buffer[i] && Ema21Buffer[i] < Ema50Buffer[i]);
      bool volumeOk = !UsarFiltroDeVolume || VolumeRelativo(i,rates_total,tick_volume) >= VolumeMinimoRelativo;
      bool rejeitouCompra = low[i] <= vwap + tolerancia && close[i] > vwap && close[i] > open[i];
      bool rejeitouVenda = high[i] >= vwap - tolerancia && close[i] < vwap && close[i] < open[i];
      bool cruzouCompra = close[i + 1] <= VwapBuffer[i + 1] && close[i] > vwap;
      bool cruzouVenda = close[i + 1] >= VwapBuffer[i + 1] && close[i] < vwap;
      if(volumeOk && tendenciaCompra && rejeitouCompra && cruzouCompra) CompraBuffer[i] = low[i] - 8.0 * _Point;
      if(volumeOk && tendenciaVenda && rejeitouVenda && cruzouVenda) VendaBuffer[i] = high[i] + 8.0 * _Point;
     }
   return rates_total;
  }
