#property strict
#property version   "1.00"
#property description "Rompimento de range de vela em multiplos timeframes, sem repaint"

#include <Trade/Trade.mqh>

CTrade negociacao;

enum ENUM_LINHAS_RANGE
  {
   RANGE_MAXIMA_MINIMA=0,
   RANGE_ABERTURA_FECHAMENTO=1
  };

enum ENUM_REFERENCIA_RANGE
  {
   REFERENCIA_ULTIMA_VELA_FECHADA=0,
   REFERENCIA_HORARIO_DIARIO=1,
   REFERENCIA_PRIMEIRA_VELA_DE_CADA_HORA=2,
   REFERENCIA_HORARIOS_POR_SESSAO=3
  };

enum ENUM_CONFIRMACAO_ROMPIMENTO
  {
   ROMPIMENTO_POR_PRECO=0,
   ROMPIMENTO_POR_FECHAMENTO=1
  };

enum ENUM_MODO_LOTE_RANGE
  {
   LOTE_FIXO_CONTRATOS=0,
   LOTE_POR_RISCO_FIXO=1,
   LOTE_POR_PERCENTUAL=2
  };

enum ENUM_MODO_STOP_RANGE
  {
   STOP_LINHA_OPOSTA=0,
   STOP_FIXO_PONTOS=1,
   STOP_PERCENTUAL_RANGE=2
  };

enum ENUM_MODO_BREAKEVEN_RANGE
  {
   BREAKEVEN_PERCENTUAL_RANGE=0,
   BREAKEVEN_FIXO_PONTOS=1
  };

// 01 - Vela de referencia e range
input group "01 - Vela de referencia e range"
input string SimboloParaOperar="XAUUSD";
input ENUM_TIMEFRAMES TimeframeDaVelaDeReferencia=PERIOD_M15;
input ENUM_TIMEFRAMES TimeframeDeEntrada=PERIOD_M1;
input ENUM_LINHAS_RANGE LinhasDoRange=RANGE_MAXIMA_MINIMA;
input ENUM_REFERENCIA_RANGE ModoDaVelaDeReferencia=REFERENCIA_ULTIMA_VELA_FECHADA;
input int HoraDaVelaDeReferencia=9;
input int MinutoDaVelaDeReferencia=0;
input group "01.1 - Horarios de referencia por sessao"
input bool AtivarHorariosDaSessaoAsia=true;
input string HorariosDaSessaoAsia="00:00,01:00,02:00,03:00";
input bool AtivarHorariosDaSessaoEuropa=true;
input string HorariosDaSessaoEuropa="04:00,05:00,06:00,07:00,08:00";
input bool AtivarHorariosDaSessaoEstadosUnidos=true;
input string HorariosDaSessaoEstadosUnidos="09:00,10:00,11:00,12:00,13:00";
input group "01.2 - Validacao e duracao do range"
input double RangeMinimoEmPontos=200.0;
input double RangeMaximoEmPontos=1200.0;
input bool BuscarProximaVelaSeRangeForMaior=true;
input int MaximoDeProximasVelasParaAnalisar=3;
input int ValidadeDoRangeEmVelasDeEntrada=60;
input bool PermitirUmaEntradaPorRange=true;

// 02 - Regras do rompimento
input group "02 - Regras do rompimento"
input bool PermitirCompras=true;
input bool PermitirVendas=true;
input ENUM_CONFIRMACAO_ROMPIMENTO ConfirmacaoDoRompimento=ROMPIMENTO_POR_FECHAMENTO;
input double DistanciaMinimaDoRompimentoEmPontos=10.0;
input double DistanciaMaximaDoRompimentoEmPontos=500.0;
input bool FiltrarTamanhoDaVelaDeRompimento=true;
input double TamanhoMaximoDaVelaDeRompimentoEmPontos=600.0;

// 03 - Take profit e stop loss
input group "03 - Take profit e stop loss"
input double TakeProfitEmMultiplosDoRange=1.40;
input ENUM_MODO_STOP_RANGE ModoDoStopLoss=STOP_LINHA_OPOSTA;
input double StopFixoEmPontos=300.0;
input double StopEmPercentualDoRange=100.0;
input double MargemDoStopAlemDaLinhaEmPontos=0.0;

// 04 - Lote e protecoes
input group "04 - Lote e protecoes"
input ENUM_MODO_LOTE_RANGE ModoDeCalculoDoLote=LOTE_POR_PERCENTUAL;
input double LoteFixoEmContratos=0.01;
input double RiscoFixoEmDinheiro=50.0;
input double RiscoPercentualDoCapital=0.50;
input double LoteMaximo=100.0;
input bool AtivarBreakeven=true;
input ENUM_MODO_BREAKEVEN_RANGE ModoDoBreakeven=BREAKEVEN_PERCENTUAL_RANGE;
input double AtivarBreakevenEmPercentualDoRange=80.0;
input double AtivarBreakevenEmPontos=500.0;
input double LucroProtegidoNoBreakevenEmPontos=0.0;
input bool AtivarTrailingStop=false;
input double AtivarTrailingAposPontos=600.0;
input double DistanciaDoTrailingEmPontos=500.0;
input double PassoDoTrailingEmPontos=100.0;

// 05 - Limites operacionais
input group "05 - Limites operacionais"
input bool RestringirHorarioDeOperacao=false;
input string HorarioInicialDeOperacao="00:00";
input string HorarioFinalDeOperacao="23:59";
input int MaximoDeOperacoesPorDia=3;
input int MaximoDeOperacoesAbertas=1;
input double PerdaMaximaDiariaPercentual=0.0;
input double LucroMaximoDiarioEmDinheiro=0.0;
input double SpreadMaximoEmPontos=80.0;
input int DesvioMaximoEmPontos=20;
input long MagicNumber=260901;

// 06 - Visual e painel
input group "06 - Visual e painel"
input bool DesenharRangeNoGrafico=true;
input bool MostrarPainel=true;
input int PosicaoHorizontalDoPainel=18;
input int PosicaoVerticalDoPainel=24;
input double EscalaDoPainel=1.0;
input bool RegistrarLogsDetalhados=true;

struct RANGE_REFERENCIA
  {
   bool ativo;
   bool valido;
   bool entradaRealizada;
   datetime horario;
   datetime expiracao;
   double superior;
   double inferior;
   double tamanhoPontos;
   string motivo;
  };

RANGE_REFERENCIA rangeAtual;
datetime ultimaVelaReferencia=0;
datetime horarioBaseDaBusca=0;
int proximaVelaDaBusca=0;
datetime ultimaVelaEntrada=0;
datetime ultimoDiaProcessado=0;
double resultadoDia=0.0;
double resultadoSemana=0.0;
double resultadoMes=0.0;
int operacoesHoje=0;
string statusEA="INICIALIZANDO";

string PREFIXO="ERRMTF_";
color COR_FUNDO=C'8,12,19';
color COR_CARTAO=C'17,24,38';
color COR_BORDA=C'43,55,72';
color COR_TEXTO=C'236,242,249';
color COR_MUTED=C'148,163,184';
color COR_CIANO=C'34,211,238';
color COR_VERDE=C'16,185,129';
color COR_VERMELHO=C'248,113,113';
color COR_OURO=C'251,191,36';

double Ponto()
  {
   return SymbolInfoDouble(SimboloParaOperar,SYMBOL_POINT);
  }

int Digitos()
  {
   return (int)SymbolInfoInteger(SimboloParaOperar,SYMBOL_DIGITS);
  }

void Log(const string mensagem)
  {
   if(RegistrarLogsDetalhados)
      Print("[EA RANGE MTF] ",mensagem);
  }

datetime InicioDoDia(const datetime horario)
  {
   MqlDateTime d;
   TimeToStruct(horario,d);
   d.hour=0; d.min=0; d.sec=0;
   return StructToTime(d);
  }

datetime InicioDoMes(const datetime horario)
  {
   MqlDateTime d;
   TimeToStruct(horario,d);
   d.day=1; d.hour=0; d.min=0; d.sec=0;
   return StructToTime(d);
  }

datetime InicioDaSemana(const datetime horario)
  {
   datetime dia=InicioDoDia(horario);
   MqlDateTime d;
   TimeToStruct(dia,d);
   int deslocamento=(d.day_of_week==0 ? 6 : d.day_of_week-1);
   return dia-deslocamento*86400;
  }

int MinutosDoHorario(const string horario)
  {
   string partes[];
   if(StringSplit(horario,':',partes)!=2) return -1;
   int hora=(int)StringToInteger(partes[0]);
   int minuto=(int)StringToInteger(partes[1]);
   if(hora<0 || hora>23 || minuto<0 || minuto>59) return -1;
   return hora*60+minuto;
  }

bool DentroDoHorario()
  {
   if(!RestringirHorarioDeOperacao) return true;
   int inicio=MinutosDoHorario(HorarioInicialDeOperacao);
   int fim=MinutosDoHorario(HorarioFinalDeOperacao);
   if(inicio<0 || fim<0) return false;
   MqlDateTime d;
   TimeToStruct(TimeCurrent(),d);
   int agora=d.hour*60+d.min;
   if(inicio<=fim) return agora>=inicio && agora<=fim;
   return agora>=inicio || agora<=fim;
  }

double ResultadoEntre(const datetime inicio,const datetime fim)
  {
   if(!HistorySelect(inicio,fim)) return 0.0;
   double total=0.0;
   int quantidade=HistoryDealsTotal();
   for(int i=0;i<quantidade;i++)
     {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0) continue;
      if(HistoryDealGetString(ticket,DEAL_SYMBOL)!=SimboloParaOperar) continue;
      if(HistoryDealGetInteger(ticket,DEAL_MAGIC)!=MagicNumber) continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY)==DEAL_ENTRY_IN) continue;
      total+=HistoryDealGetDouble(ticket,DEAL_PROFIT);
      total+=HistoryDealGetDouble(ticket,DEAL_SWAP);
      total+=HistoryDealGetDouble(ticket,DEAL_COMMISSION);
     }
   return total;
  }

int OperacoesEntre(const datetime inicio,const datetime fim)
  {
   if(!HistorySelect(inicio,fim)) return 0;
   int total=0;
   for(int i=0;i<HistoryDealsTotal();i++)
     {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0) continue;
      if(HistoryDealGetString(ticket,DEAL_SYMBOL)!=SimboloParaOperar) continue;
      if(HistoryDealGetInteger(ticket,DEAL_MAGIC)!=MagicNumber) continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY)==DEAL_ENTRY_IN) total++;
     }
   return total;
  }

void AtualizarResultados()
  {
   datetime agora=TimeCurrent();
   resultadoDia=ResultadoEntre(InicioDoDia(agora),agora);
   resultadoSemana=ResultadoEntre(InicioDaSemana(agora),agora);
   resultadoMes=ResultadoEntre(InicioDoMes(agora),agora);
   operacoesHoje=OperacoesEntre(InicioDoDia(agora),agora);
  }

int PosicoesAbertasDoEA()
  {
   int total=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL)==SimboloParaOperar && PositionGetInteger(POSITION_MAGIC)==MagicNumber) total++;
     }
   return total;
  }

double LucroFlutuanteDoEA()
  {
   double total=0.0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL)==SimboloParaOperar && PositionGetInteger(POSITION_MAGIC)==MagicNumber)
         total+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
     }
   return total;
  }

datetime HorarioDaReferenciaDiaria()
  {
   MqlDateTime d;
   TimeToStruct(TimeCurrent(),d);
   d.hour=HoraDaVelaDeReferencia;
   d.min=MinutoDaVelaDeReferencia;
   d.sec=0;
   datetime alvo=StructToTime(d);
   int segundos=PeriodSeconds(TimeframeDaVelaDeReferencia);
   if(TimeCurrent()<alvo+segundos) alvo-=86400;
   return alvo;
  }

datetime HorarioDaPrimeiraVelaFechadaDaHora()
  {
   MqlDateTime d;
   TimeToStruct(TimeCurrent(),d);
   d.min=0;
   d.sec=0;
   datetime inicioDaHora=StructToTime(d);
   int segundos=PeriodSeconds(TimeframeDaVelaDeReferencia);
   if(TimeCurrent()<inicioDaHora+segundos)
      inicioDaHora-=3600;
   return inicioDaHora;
  }

void ConsiderarHorariosDaLista(const string lista,const datetime inicioDoDia,const datetime agora,const int segundosDaReferencia,datetime &melhor)
  {
   string horarios[];
   int quantidade=StringSplit(lista,',',horarios);
   for(int i=0;i<quantidade;i++)
     {
      string horario=horarios[i];
      StringTrimLeft(horario);
      StringTrimRight(horario);
      int minutos=MinutosDoHorario(horario);
      if(minutos<0) continue;
      datetime candidato=inicioDoDia+minutos*60;
      if(agora>=candidato+segundosDaReferencia && candidato>melhor)
         melhor=candidato;
     }
  }

datetime HorarioMaisRecenteDasSessoes()
  {
   datetime agora=TimeCurrent();
   datetime hoje=InicioDoDia(agora);
   datetime melhor=0;
   int segundos=PeriodSeconds(TimeframeDaVelaDeReferencia);
   for(int deslocamento=0;deslocamento<=1;deslocamento++)
     {
      datetime dia=hoje-deslocamento*86400;
      if(AtivarHorariosDaSessaoAsia)
         ConsiderarHorariosDaLista(HorariosDaSessaoAsia,dia,agora,segundos,melhor);
      if(AtivarHorariosDaSessaoEuropa)
         ConsiderarHorariosDaLista(HorariosDaSessaoEuropa,dia,agora,segundos,melhor);
      if(AtivarHorariosDaSessaoEstadosUnidos)
         ConsiderarHorariosDaLista(HorariosDaSessaoEstadosUnidos,dia,agora,segundos,melhor);
     }
   return melhor;
  }

int ShiftDaVelaDeReferencia(datetime &horario)
  {
   if(ModoDaVelaDeReferencia==REFERENCIA_ULTIMA_VELA_FECHADA)
     {
      horario=iTime(SimboloParaOperar,TimeframeDaVelaDeReferencia,1);
      return horario>0 ? 1 : -1;
     }
   datetime alvo=HorarioDaReferenciaDiaria();
   if(ModoDaVelaDeReferencia==REFERENCIA_PRIMEIRA_VELA_DE_CADA_HORA)
      alvo=HorarioDaPrimeiraVelaFechadaDaHora();
   else if(ModoDaVelaDeReferencia==REFERENCIA_HORARIOS_POR_SESSAO)
      alvo=HorarioMaisRecenteDasSessoes();
   if(alvo<=0) return -1;
   int shift=iBarShift(SimboloParaOperar,TimeframeDaVelaDeReferencia,alvo,true);
   if(shift<0) shift=iBarShift(SimboloParaOperar,TimeframeDaVelaDeReferencia,alvo,false);
   if(shift<0) return -1;
   horario=iTime(SimboloParaOperar,TimeframeDaVelaDeReferencia,shift);
   return shift;
  }

void ApagarObjetosDoRange()
  {
   int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
     {
      string nome=ObjectName(0,i,0,-1);
      if(StringFind(nome,PREFIXO+"RANGE_")==0) ObjectDelete(0,nome);
     }
  }

void CriarLinhaDoRange(const string sufixo,const double preco,const color cor,const string texto)
  {
   string nome=PREFIXO+"RANGE_"+sufixo;
   datetime fim=rangeAtual.expiracao;
   if(!ObjectCreate(0,nome,OBJ_TREND,0,rangeAtual.horario,preco,fim,preco)) return;
   ObjectSetInteger(0,nome,OBJPROP_COLOR,cor);
   ObjectSetInteger(0,nome,OBJPROP_WIDTH,3);
   ObjectSetInteger(0,nome,OBJPROP_RAY_RIGHT,false);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,false);

   string rotulo=nome+"_ROTULO";
   if(ObjectCreate(0,rotulo,OBJ_TEXT,0,fim,preco))
     {
      ObjectSetString(0,rotulo,OBJPROP_TEXT,texto);
      ObjectSetInteger(0,rotulo,OBJPROP_COLOR,cor);
      ObjectSetInteger(0,rotulo,OBJPROP_FONTSIZE,9);
      ObjectSetInteger(0,rotulo,OBJPROP_ANCHOR,ANCHOR_RIGHT_LOWER);
      ObjectSetInteger(0,rotulo,OBJPROP_SELECTABLE,false);
     }
  }

void DesenharRange()
  {
   ApagarObjetosDoRange();
   if(!DesenharRangeNoGrafico || !rangeAtual.ativo) return;
   string tamanho=DoubleToString(rangeAtual.tamanhoPontos,1)+" pts";
   CriarLinhaDoRange("SUPERIOR",rangeAtual.superior,COR_VERDE,"COMPRA acima | range "+tamanho);
   CriarLinhaDoRange("INFERIOR",rangeAtual.inferior,COR_VERMELHO,"VENDA abaixo | range "+tamanho);
   ChartRedraw();
  }

void FormarRangeSeNecessario()
  {
   datetime horarioBase=0;
   int shiftBase=ShiftDaVelaDeReferencia(horarioBase);
   if(shiftBase<0 || horarioBase<=0) return;

   if(horarioBaseDaBusca==0 || horarioBase>horarioBaseDaBusca)
     {
      horarioBaseDaBusca=horarioBase;
      proximaVelaDaBusca=0;
     }

   int segundosReferencia=PeriodSeconds(TimeframeDaVelaDeReferencia);
   datetime horarioDesejado=horarioBaseDaBusca+(datetime)(proximaVelaDaBusca*segundosReferencia);
   if(TimeCurrent()<horarioDesejado+segundosReferencia) return;

   int shift=iBarShift(SimboloParaOperar,TimeframeDaVelaDeReferencia,horarioDesejado,true);
   if(shift<0) shift=iBarShift(SimboloParaOperar,TimeframeDaVelaDeReferencia,horarioDesejado,false);
   if(shift<0) return;
   datetime horario=iTime(SimboloParaOperar,TimeframeDaVelaDeReferencia,shift);
   if(horario<=0 || horario==ultimaVelaReferencia) return;

   double abertura=iOpen(SimboloParaOperar,TimeframeDaVelaDeReferencia,shift);
   double fechamento=iClose(SimboloParaOperar,TimeframeDaVelaDeReferencia,shift);
   double maxima=iHigh(SimboloParaOperar,TimeframeDaVelaDeReferencia,shift);
   double minima=iLow(SimboloParaOperar,TimeframeDaVelaDeReferencia,shift);
   if(abertura<=0 || fechamento<=0 || maxima<=0 || minima<=0) return;

   rangeAtual.superior=(LinhasDoRange==RANGE_MAXIMA_MINIMA ? maxima : MathMax(abertura,fechamento));
   rangeAtual.inferior=(LinhasDoRange==RANGE_MAXIMA_MINIMA ? minima : MathMin(abertura,fechamento));
   rangeAtual.tamanhoPontos=(rangeAtual.superior-rangeAtual.inferior)/Ponto();
   rangeAtual.horario=horario;
   rangeAtual.expiracao=horario+PeriodSeconds(TimeframeDaVelaDeReferencia)+(datetime)(ValidadeDoRangeEmVelasDeEntrada*PeriodSeconds(TimeframeDeEntrada));
   rangeAtual.ativo=true;
   rangeAtual.entradaRealizada=false;
   rangeAtual.valido=rangeAtual.tamanhoPontos>=RangeMinimoEmPontos && rangeAtual.tamanhoPontos<=RangeMaximoEmPontos;
   if(rangeAtual.tamanhoPontos<RangeMinimoEmPontos) rangeAtual.motivo="RANGE MENOR QUE O MINIMO";
   else if(rangeAtual.tamanhoPontos>RangeMaximoEmPontos)
     {
      if(BuscarProximaVelaSeRangeForMaior && proximaVelaDaBusca<MaximoDeProximasVelasParaAnalisar)
        {
         proximaVelaDaBusca++;
         rangeAtual.motivo="RANGE GRANDE - AGUARDANDO VELA "+IntegerToString(proximaVelaDaBusca)+"/"+IntegerToString(MaximoDeProximasVelasParaAnalisar);
        }
      else
         rangeAtual.motivo="RANGE MAIOR - LIMITE DE BUSCA";
     }
   else rangeAtual.motivo="AGUARDANDO ROMPIMENTO";
   ultimaVelaReferencia=horario;
   DesenharRange();
   Log("Novo range: "+DoubleToString(rangeAtual.tamanhoPontos,1)+" pontos | "+rangeAtual.motivo);
  }

bool LimitesOperacionaisLiberados()
  {
   AtualizarResultados();
   if(!DentroDoHorario()) { statusEA="FORA DO HORARIO"; return false; }
   if(MaximoDeOperacoesPorDia>0 && operacoesHoje>=MaximoDeOperacoesPorDia) { statusEA="LIMITE DIARIO DE OPERACOES"; return false; }
   if(MaximoDeOperacoesAbertas>0 && PosicoesAbertasDoEA()>=MaximoDeOperacoesAbertas) { statusEA="OPERACAO EM ANDAMENTO"; return false; }
   double saldoInicio=AccountInfoDouble(ACCOUNT_BALANCE)-resultadoDia;
   if(PerdaMaximaDiariaPercentual>0 && saldoInicio>0 && resultadoDia<=-saldoInicio*PerdaMaximaDiariaPercentual/100.0)
     { statusEA="PERDA MAXIMA DIARIA"; return false; }
   if(LucroMaximoDiarioEmDinheiro>0 && resultadoDia>=LucroMaximoDiarioEmDinheiro)
     { statusEA="META DIARIA ATINGIDA"; return false; }
   MqlTick tick;
   if(!SymbolInfoTick(SimboloParaOperar,tick)) { statusEA="SEM COTACAO"; return false; }
   if(SpreadMaximoEmPontos>0 && (tick.ask-tick.bid)/Ponto()>SpreadMaximoEmPontos)
     { statusEA="SPREAD ACIMA DO LIMITE"; return false; }
   return true;
  }

double NormalizarLote(double lote)
  {
   double minimo=SymbolInfoDouble(SimboloParaOperar,SYMBOL_VOLUME_MIN);
   double maximo=MathMin(SymbolInfoDouble(SimboloParaOperar,SYMBOL_VOLUME_MAX),LoteMaximo);
   double passo=SymbolInfoDouble(SimboloParaOperar,SYMBOL_VOLUME_STEP);
   if(passo<=0) passo=0.01;
   lote=MathFloor(lote/passo)*passo;
   lote=MathMax(minimo,MathMin(maximo,lote));
   return NormalizeDouble(lote,2);
  }

double CalcularLote(const int direcao,const double entrada,const double stop)
  {
   if(ModoDeCalculoDoLote==LOTE_FIXO_CONTRATOS) return NormalizarLote(LoteFixoEmContratos);
   double risco=(ModoDeCalculoDoLote==LOTE_POR_RISCO_FIXO ? RiscoFixoEmDinheiro : AccountInfoDouble(ACCOUNT_EQUITY)*RiscoPercentualDoCapital/100.0);
   if(risco<=0 || MathAbs(entrada-stop)<Ponto()) return 0.0;
   double perdaPorLote=0.0;
   ENUM_ORDER_TYPE tipo=(direcao>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   if(!OrderCalcProfit(tipo,SimboloParaOperar,1.0,entrada,stop,perdaPorLote)) return 0.0;
   perdaPorLote=MathAbs(perdaPorLote);
   if(perdaPorLote<=0) return 0.0;
   return NormalizarLote(risco/perdaPorLote);
  }

double CalcularStop(const int direcao,const double entrada)
  {
   double distancia=0.0;
   if(ModoDoStopLoss==STOP_LINHA_OPOSTA)
      return NormalizeDouble((direcao>0 ? rangeAtual.inferior-MargemDoStopAlemDaLinhaEmPontos*Ponto() : rangeAtual.superior+MargemDoStopAlemDaLinhaEmPontos*Ponto()),Digitos());
   if(ModoDoStopLoss==STOP_FIXO_PONTOS) distancia=StopFixoEmPontos*Ponto();
   else distancia=rangeAtual.tamanhoPontos*(StopEmPercentualDoRange/100.0)*Ponto();
   return NormalizeDouble(entrada-direcao*distancia,Digitos());
  }

void MarcarEntrada(const int direcao,const datetime horario,const double entrada)
  {
   string base=PREFIXO+"ENTRADA_"+IntegerToString((int)horario);
   ENUM_OBJECT tipo=(direcao>0 ? OBJ_ARROW_BUY : OBJ_ARROW_SELL);
   color cor=(direcao>0 ? COR_VERDE : COR_VERMELHO);
   if(ObjectCreate(0,base,tipo,0,horario,entrada))
     {
      ObjectSetInteger(0,base,OBJPROP_COLOR,cor);
      ObjectSetInteger(0,base,OBJPROP_WIDTH,4);
      ObjectSetInteger(0,base,OBJPROP_SELECTABLE,false);
     }
   string texto=base+"_TEXTO";
   if(ObjectCreate(0,texto,OBJ_TEXT,0,horario,entrada-direcao*rangeAtual.tamanhoPontos*Ponto()*0.15))
     {
      ObjectSetString(0,texto,OBJPROP_TEXT,(direcao>0 ? "COMPRA" : "VENDA"));
      ObjectSetInteger(0,texto,OBJPROP_COLOR,cor);
      ObjectSetInteger(0,texto,OBJPROP_FONTSIZE,10);
      ObjectSetInteger(0,texto,OBJPROP_SELECTABLE,false);
     }
  }

bool AbrirOperacao(const int direcao,const double precoSinal)
  {
   if(!LimitesOperacionaisLiberados()) return false;
   MqlTick tick;
   if(!SymbolInfoTick(SimboloParaOperar,tick)) return false;
   double entrada=(direcao>0 ? tick.ask : tick.bid);
   double stop=CalcularStop(direcao,entrada);
   double take=NormalizeDouble(entrada+direcao*rangeAtual.tamanhoPontos*TakeProfitEmMultiplosDoRange*Ponto(),Digitos());
   double distanciaMinima=(double)SymbolInfoInteger(SimboloParaOperar,SYMBOL_TRADE_STOPS_LEVEL)*Ponto();
   if((direcao>0 && (entrada-stop<distanciaMinima || take-entrada<distanciaMinima)) ||
      (direcao<0 && (stop-entrada<distanciaMinima || entrada-take<distanciaMinima)))
     {
      statusEA="STOP OU TAKE MUITO PROXIMO";
      Log("Protecoes recusadas antes do envio: distancia minima do ativo "+DoubleToString(distanciaMinima/Ponto(),1)+" pontos.");
      return false;
     }
   double lote=CalcularLote(direcao,entrada,stop);
   if(lote<=0) { statusEA="LOTE INVALIDO"; return false; }

   negociacao.SetExpertMagicNumber(MagicNumber);
   negociacao.SetDeviationInPoints(DesvioMaximoEmPontos);
   bool sucesso=(direcao>0 ? negociacao.Buy(lote,SimboloParaOperar,0,stop,take,"Range MTF compra") : negociacao.Sell(lote,SimboloParaOperar,0,stop,take,"Range MTF venda"));
   if(!sucesso)
     {
      statusEA="ORDEM RECUSADA";
      Log("Ordem recusada: "+negociacao.ResultRetcodeDescription());
      return false;
     }
   rangeAtual.entradaRealizada=true;
   statusEA=(direcao>0 ? "COMPRADO" : "VENDIDO");
   MarcarEntrada(direcao,TimeCurrent(),entrada);
   Log(statusEA+" | lote "+DoubleToString(lote,2)+" | entrada "+DoubleToString(entrada,Digitos())+" | sinal "+DoubleToString(precoSinal,Digitos()));
   return true;
  }

bool NovaVelaDeEntrada()
  {
   datetime atual=iTime(SimboloParaOperar,TimeframeDeEntrada,0);
   if(atual<=0 || atual==ultimaVelaEntrada) return false;
   ultimaVelaEntrada=atual;
   return true;
  }

bool VelaDeRompimentoValida(const int shift)
  {
   if(!FiltrarTamanhoDaVelaDeRompimento) return true;
   double tamanho=(iHigh(SimboloParaOperar,TimeframeDeEntrada,shift)-iLow(SimboloParaOperar,TimeframeDeEntrada,shift))/Ponto();
   if(tamanho>TamanhoMaximoDaVelaDeRompimentoEmPontos)
     {
      statusEA="VELA DE ROMPIMENTO MUITO GRANDE";
      return false;
     }
   return true;
  }

void VerificarRompimento()
  {
   if(!rangeAtual.ativo) { statusEA="AGUARDANDO RANGE"; return; }
   if(TimeCurrent()>rangeAtual.expiracao) { statusEA="RANGE EXPIRADO"; return; }
   if(!rangeAtual.valido) { statusEA=rangeAtual.motivo; return; }
   if(PermitirUmaEntradaPorRange && rangeAtual.entradaRealizada) { statusEA="RANGE JA OPERADO"; return; }
   if(PosicoesAbertasDoEA()>0) { statusEA="OPERACAO EM ANDAMENTO"; return; }

   double minimo=DistanciaMinimaDoRompimentoEmPontos*Ponto();
   double maximo=DistanciaMaximaDoRompimentoEmPontos*Ponto();
   if(ConfirmacaoDoRompimento==ROMPIMENTO_POR_PRECO)
     {
      MqlTick tick;
      if(!SymbolInfoTick(SimboloParaOperar,tick)) return;
      double excessoCompra=tick.ask-rangeAtual.superior;
      double excessoVenda=rangeAtual.inferior-tick.bid;
      bool compraValida=PermitirCompras && excessoCompra>=minimo && (DistanciaMaximaDoRompimentoEmPontos<=0 || excessoCompra<=maximo);
      bool vendaValida=PermitirVendas && excessoVenda>=minimo && (DistanciaMaximaDoRompimentoEmPontos<=0 || excessoVenda<=maximo);
      if((compraValida || vendaValida) && !VelaDeRompimentoValida(0)) return;
      if(compraValida) AbrirOperacao(1,tick.ask);
      else if(vendaValida) AbrirOperacao(-1,tick.bid);
      return;
     }

   if(!NovaVelaDeEntrada()) return;
   int shift=1;
   if(!VelaDeRompimentoValida(shift)) return;
   double fechamento=iClose(SimboloParaOperar,TimeframeDeEntrada,shift);
   double excessoCompra=fechamento-rangeAtual.superior;
   double excessoVenda=rangeAtual.inferior-fechamento;
   if(PermitirCompras && excessoCompra>=minimo && (DistanciaMaximaDoRompimentoEmPontos<=0 || excessoCompra<=maximo)) AbrirOperacao(1,fechamento);
   else if(PermitirVendas && excessoVenda>=minimo && (DistanciaMaximaDoRompimentoEmPontos<=0 || excessoVenda<=maximo)) AbrirOperacao(-1,fechamento);
  }

void GerenciarPosicoes()
  {
   MqlTick tick;
   if(!SymbolInfoTick(SimboloParaOperar,tick)) return;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=SimboloParaOperar || PositionGetInteger(POSITION_MAGIC)!=MagicNumber) continue;
      ENUM_POSITION_TYPE tipo=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      int direcao=(tipo==POSITION_TYPE_BUY ? 1 : -1);
      double entrada=PositionGetDouble(POSITION_PRICE_OPEN);
      double stopAtual=PositionGetDouble(POSITION_SL);
      double take=PositionGetDouble(POSITION_TP);
      double preco=(direcao>0 ? tick.bid : tick.ask);
      double ganhoPontos=direcao*(preco-entrada)/Ponto();
      double novoStop=stopAtual;

      if(AtivarBreakeven)
        {
         double gatilho=(ModoDoBreakeven==BREAKEVEN_PERCENTUAL_RANGE ? rangeAtual.tamanhoPontos*AtivarBreakevenEmPercentualDoRange/100.0 : AtivarBreakevenEmPontos);
         double stopBE=entrada+direcao*LucroProtegidoNoBreakevenEmPontos*Ponto();
         bool aindaNaoProtegido=(direcao>0 ? stopAtual<stopBE : stopAtual==0 || stopAtual>stopBE);
         if(ganhoPontos>=gatilho && aindaNaoProtegido) novoStop=stopBE;
        }

      if(AtivarTrailingStop && ganhoPontos>=AtivarTrailingAposPontos)
        {
         double candidato=preco-direcao*DistanciaDoTrailingEmPontos*Ponto();
         bool melhora=(direcao>0 ? candidato>novoStop+PassoDoTrailingEmPontos*Ponto() : novoStop==0 || candidato<novoStop-PassoDoTrailingEmPontos*Ponto());
         if(melhora) novoStop=candidato;
        }

      novoStop=NormalizeDouble(novoStop,Digitos());
      if(novoStop>0 && MathAbs(novoStop-stopAtual)>=Ponto())
         negociacao.PositionModify(ticket,novoStop,take);
     }
  }

void CriarRetangulo(const string sufixo,const int x,const int y,const int largura,const int altura,const color fundo,const color borda)
  {
   string nome=PREFIXO+"UI_"+sufixo;
   if(ObjectFind(0,nome)<0) ObjectCreate(0,nome,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,nome,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,nome,OBJPROP_XDISTANCE,PosicaoHorizontalDoPainel+(int)(x*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_YDISTANCE,PosicaoVerticalDoPainel+(int)(y*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_XSIZE,(int)(largura*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_YSIZE,(int)(altura*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_BGCOLOR,fundo);
   ObjectSetInteger(0,nome,OBJPROP_BORDER_COLOR,borda);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,false);
  }

void CriarTexto(const string sufixo,const string texto,const int x,const int y,const int tamanho,const color cor)
  {
   string nome=PREFIXO+"UI_"+sufixo;
   if(ObjectFind(0,nome)<0) ObjectCreate(0,nome,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,nome,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,nome,OBJPROP_XDISTANCE,PosicaoHorizontalDoPainel+(int)(x*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_YDISTANCE,PosicaoVerticalDoPainel+(int)(y*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_FONTSIZE,(int)(tamanho*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_COLOR,cor);
   ObjectSetString(0,nome,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,nome,OBJPROP_TEXT,texto);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,false);
  }

string Moeda(const double valor)
  {
   return (valor>=0 ? "+" : "")+DoubleToString(valor,2)+" "+AccountInfoString(ACCOUNT_CURRENCY);
  }

void AtualizarPainel()
  {
   if(!MostrarPainel) return;
   AtualizarResultados();
   color corStatus=COR_CIANO;
   if(StringFind(statusEA,"COMPRADO")>=0) corStatus=COR_VERDE;
   else if(StringFind(statusEA,"VENDIDO")>=0 || StringFind(statusEA,"PERDA")>=0 || StringFind(statusEA,"MAIOR")>=0) corStatus=COR_VERMELHO;
   else if(StringFind(statusEA,"FORA")>=0 || StringFind(statusEA,"AGUARDANDO")>=0 || StringFind(statusEA,"MENOR")>=0) corStatus=COR_OURO;

   CriarRetangulo("FUNDO",0,0,476,348,COR_FUNDO,COR_BORDA);
   CriarRetangulo("ACENTO",0,0,5,348,COR_CIANO,COR_CIANO);
   CriarTexto("TITULO","RANGE MTF PRO",18,14,15,COR_TEXTO);
   CriarTexto("SUBTITULO",SimboloParaOperar+" | referencia "+EnumToString(TimeframeDaVelaDeReferencia)+" | entrada "+EnumToString(TimeframeDeEntrada),18,38,9,COR_MUTED);
   CriarTexto("STATUS_T","STATUS OPERACIONAL",18,68,8,COR_MUTED);
   CriarTexto("STATUS",statusEA,18,86,13,corStatus);

   CriarRetangulo("RANGE",14,120,214,100,COR_CARTAO,COR_BORDA);
   CriarTexto("RANGE_T","RANGE ATUAL",26,132,9,COR_MUTED);
   CriarTexto("RANGE_V",rangeAtual.ativo ? DoubleToString(rangeAtual.tamanhoPontos,1)+" pts" : "--",26,154,16,rangeAtual.valido ? COR_CIANO : COR_VERMELHO);
   CriarTexto("MAX",rangeAtual.ativo ? "Superior  "+DoubleToString(rangeAtual.superior,Digitos()) : "Superior  --",26,184,9,COR_VERDE);
   CriarTexto("MIN",rangeAtual.ativo ? "Inferior  "+DoubleToString(rangeAtual.inferior,Digitos()) : "Inferior  --",26,202,9,COR_VERMELHO);

   CriarRetangulo("TRADE",242,120,220,100,COR_CARTAO,COR_BORDA);
   CriarTexto("TRADE_T","OPERACAO ATUAL",254,132,9,COR_MUTED);
   int abertas=PosicoesAbertasDoEA();
   double flutuante=LucroFlutuanteDoEA();
   CriarTexto("TRADE_V",abertas>0 ? Moeda(flutuante) : "SEM POSICAO",254,154,16,flutuante>=0 ? COR_VERDE : COR_VERMELHO);
   CriarTexto("TRADES_DIA","Operacoes hoje  "+IntegerToString(operacoesHoje)+" / "+IntegerToString(MaximoDeOperacoesPorDia),254,186,9,COR_TEXTO);
   CriarTexto("RISCO","Risco  "+DoubleToString(RiscoPercentualDoCapital,2)+"% | TP  "+DoubleToString(TakeProfitEmMultiplosDoRange,2)+"x",254,204,9,COR_MUTED);

   CriarRetangulo("RESULTADOS",14,234,448,96,COR_CARTAO,COR_BORDA);
   CriarTexto("RES_T","RESULTADOS REALIZADOS",26,246,9,COR_MUTED);
   CriarTexto("DIA_T","DIA",26,270,8,COR_MUTED);
   CriarTexto("DIA",Moeda(resultadoDia),26,288,11,resultadoDia>=0 ? COR_VERDE : COR_VERMELHO);
   CriarTexto("SEM_T","SEMANA",172,270,8,COR_MUTED);
   CriarTexto("SEM",Moeda(resultadoSemana),172,288,11,resultadoSemana>=0 ? COR_VERDE : COR_VERMELHO);
   CriarTexto("MES_T","MES",326,270,8,COR_MUTED);
   CriarTexto("MES",Moeda(resultadoMes),326,288,11,resultadoMes>=0 ? COR_VERDE : COR_VERMELHO);
   ChartRedraw();
  }

void AtualizarStatusSemSinal()
  {
   AtualizarResultados();
   if(PosicoesAbertasDoEA()>0)
     {
      for(int i=PositionsTotal()-1;i>=0;i--)
        {
         ulong ticket=PositionGetTicket(i);
         if(ticket==0) continue;
         if(PositionGetString(POSITION_SYMBOL)==SimboloParaOperar && PositionGetInteger(POSITION_MAGIC)==MagicNumber)
           {
            statusEA=((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? "COMPRADO" : "VENDIDO");
            return;
           }
        }
     }
   if(!DentroDoHorario()) { statusEA="FORA DO HORARIO"; return; }
   if(MaximoDeOperacoesPorDia>0 && operacoesHoje>=MaximoDeOperacoesPorDia) { statusEA="LIMITE DIARIO DE OPERACOES"; return; }
   double saldoInicio=AccountInfoDouble(ACCOUNT_BALANCE)-resultadoDia;
   if(PerdaMaximaDiariaPercentual>0 && saldoInicio>0 && resultadoDia<=-saldoInicio*PerdaMaximaDiariaPercentual/100.0) { statusEA="PERDA MAXIMA DIARIA"; return; }
   if(LucroMaximoDiarioEmDinheiro>0 && resultadoDia>=LucroMaximoDiarioEmDinheiro) { statusEA="META DIARIA ATINGIDA"; return; }
   if(!rangeAtual.ativo) { statusEA="AGUARDANDO RANGE"; return; }
   if(!rangeAtual.valido) { statusEA=rangeAtual.motivo; return; }
   if(TimeCurrent()>rangeAtual.expiracao) { statusEA="RANGE EXPIRADO"; return; }
   if(rangeAtual.entradaRealizada && PermitirUmaEntradaPorRange) { statusEA="RANGE JA OPERADO"; return; }
   statusEA="AGUARDANDO ROMPIMENTO";
  }

void ApagarTodosObjetosDoEA()
  {
   for(int i=ObjectsTotal(0,0,-1)-1;i>=0;i--)
     {
      string nome=ObjectName(0,i,0,-1);
      if(StringFind(nome,PREFIXO)==0) ObjectDelete(0,nome);
     }
  }

int OnInit()
  {
   if(!SymbolSelect(SimboloParaOperar,true)) return INIT_FAILED;
   if(PeriodSeconds(TimeframeDaVelaDeReferencia)<=PeriodSeconds(TimeframeDeEntrada))
     {
      Print("O timeframe da referencia deve ser maior que o timeframe de entrada.");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(RangeMinimoEmPontos<=0 || RangeMaximoEmPontos<=RangeMinimoEmPontos || TakeProfitEmMultiplosDoRange<=0 || MaximoDeProximasVelasParaAnalisar<0)
      return INIT_PARAMETERS_INCORRECT;
   negociacao.SetExpertMagicNumber(MagicNumber);
   negociacao.SetDeviationInPoints(DesvioMaximoEmPontos);
   EventSetTimer(1);
   FormarRangeSeNecessario();
   AtualizarPainel();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int motivo)
  {
   EventKillTimer();
   ApagarTodosObjetosDoEA();
  }

void OnTick()
  {
   FormarRangeSeNecessario();
   GerenciarPosicoes();
   VerificarRompimento();
  }

void OnTimer()
  {
   AtualizarStatusSemSinal();
   AtualizarPainel();
  }

void OnTradeTransaction(const MqlTradeTransaction &transacao,const MqlTradeRequest &requisicao,const MqlTradeResult &resultado)
  {
   AtualizarResultados();
  }
