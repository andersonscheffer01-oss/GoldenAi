#property strict
#property version   "1.00"
#property description "Estatistica historica de ranges e rompimentos MTF"
#property indicator_chart_window
#property indicator_plots 0

enum ENUM_LINHAS_ANALISE
  {
   ANALISAR_MAXIMA_MINIMA=0,
   ANALISAR_ABERTURA_FECHAMENTO=1
  };

enum ENUM_CONFIRMACAO_ANALISE
  {
   ANALISAR_ROMPIMENTO_POR_PRECO=0,
   ANALISAR_ROMPIMENTO_POR_FECHAMENTO=1
  };

enum ENUM_MODO_SELECAO_VELAS
  {
   ANALISE_UMA_VELA=0,
   ANALISE_LISTA_DE_HORARIOS=1,
   ANALISE_INTERVALO_DE_SESSAO=2,
   ANALISE_DIA_INTEIRO=3
  };

enum ENUM_STOP_SIMULADO
  {
   SIMULAR_STOP_LINHA_OPOSTA=0,
   SIMULAR_STOP_FIXO_PONTOS=1,
   SIMULAR_STOP_PERCENTUAL_RANGE=2
  };

enum ENUM_BREAKEVEN_SIMULADO
  {
   SIMULAR_BE_PERCENTUAL_RANGE=0,
   SIMULAR_BE_FIXO_PONTOS=1
  };

// 01 - Vela que sera estudada
input group "01 - Vela que sera estudada"
input string SimboloDaAnalise="XAUUSD";
input ENUM_TIMEFRAMES TimeframeDaVelaAnalisada=PERIOD_M15;
input int HoraDaVelaAnalisada=9;
input int MinutoDaVelaAnalisada=0;
input ENUM_LINHAS_ANALISE LinhasDoRangeAnalisado=ANALISAR_MAXIMA_MINIMA;
input ENUM_MODO_SELECAO_VELAS ModoDeSelecaoDasVelas=ANALISE_LISTA_DE_HORARIOS;
input string ListaDeHorarios="01:00,01:15,01:30,01:45,02:00,02:15,02:30,02:45";
input string InicioDaSessao="01:00";
input string FimDaSessao="05:00";
input int IntervaloEntreVelasEmMinutos=15;

// 02 - Amostra e rompimento
input group "02 - Amostra e rompimento"
input int QuantidadeDeDiasParaAnalisar=120;
input ENUM_TIMEFRAMES TimeframeParaMedirORompimento=PERIOD_M1;
input int VelasAposReferenciaParaMedir=30;
input ENUM_CONFIRMACAO_ANALISE ConfirmacaoDoRompimento=ANALISAR_ROMPIMENTO_POR_FECHAMENTO;
input double DistanciaMinimaDoRompimentoEmPontos=10.0;
input bool IgnorarDiasSemRompimentoNosAvancos=true;

// 02.1 - Filtros iguais aos do robo
input group "02.1 - Filtros iguais aos do robo"
input double RangeMinimoAceitoEmPontos=200.0;
input double RangeMaximoAceitoEmPontos=1200.0;
input bool BuscarProximaVelaSeRangeForMaior=true;
input int MaximoDeProximasVelasParaAnalisar=3;
input double DistanciaMaximaDoRompimentoEmPontos=500.0;
input bool FiltrarVelaDeRompimentoGrande=true;
input double TamanhoMaximoDaVelaDeRompimentoEmPontos=600.0;

// 02.2 - Simulacao da operacao
input group "02.2 - Simulacao da operacao"
input double TakeProfitEmMultiplosDoRange=1.0;
input ENUM_STOP_SIMULADO ModoDoStopSimulado=SIMULAR_STOP_LINHA_OPOSTA;
input double StopFixoSimuladoEmPontos=300.0;
input double StopSimuladoEmPercentualDoRange=100.0;
input double MargemAlemDaLinhaOpostaEmPontos=0.0;
input bool SimularBreakeven=true;
input ENUM_BREAKEVEN_SIMULADO ModoDoBreakevenSimulado=SIMULAR_BE_PERCENTUAL_RANGE;
input double AtivarBreakevenEmPercentualDoRange=80.0;
input double AtivarBreakevenEmPontos=500.0;
input double LucroProtegidoNoBreakevenEmPontos=0.0;
input bool SimularTrailingStop=false;
input double AtivarTrailingAposPontos=600.0;
input double DistanciaDoTrailingEmPontos=500.0;
input double PassoDoTrailingEmPontos=100.0;

// 02.3 - Robustez da leitura
input group "02.3 - Robustez da leitura"
input int MinimoDeOperacoesParaConfianca=30;
input int PeriodoDoATRParaContexto=14;

// 03 - Visual e exportacao
input group "03 - Visual e exportacao"
input bool MostrarPainelEstatistico=true;
input bool DesenharUltimoRangeNoGrafico=true;
input int PosicaoHorizontalDoPainel=18;
input int PosicaoVerticalDoPainel=24;
input double EscalaDoPainel=1.0;
input bool ExportarResultadosParaCSV=false;
input string NomeDoArquivoCSV="Estatistica_Range_MTF.csv";

struct ESTATISTICAS
  {
   int amostras;
   int rompimentos;
   int compras;
   int vendas;
   int ambiguos;
   int atingiuLinhaOposta;
   int conflitoNaVelaDaLinhaOposta;
   int semRompimento;
   int falsos;
   int alvo05;
   int alvo08;
   int alvo10;
   int alvo14;
   int alvo20;
   int alvo10Compra;
   int alvo10Venda;
   int linhaOpostaCompra;
   int linhaOpostaVenda;
   double somaRanges;
   double menorRange;
   double maiorRange;
   double somaAvanco;
   double somaAvancoAntesLinhaOposta;
   double somaAvancoCompra;
   double somaAvancoVenda;
   double somaContra;
   double somaVelasAteRompimento;
   double somaVelasAteLinhaOposta;
   double somaMultiploAvanco;
   int rangesRejeitadosPequenos;
   int rangesRejeitadosGrandes;
   int velasRompimentoRejeitadas;
   int rompimentosEsticados;
   int operacoes;
   int vitorias;
   int derrotas;
   int breakevens;
   int perdasConsecutivasMaximas;
   int sequenciaPerdasAtual;
   int operacoesCompra;
   int operacoesVenda;
   int vitoriasCompra;
   int vitoriasVenda;
   double somaR;
   double somaRCompra;
   double somaRVenda;
   double lucroBrutoR;
   double perdaBrutaR;
   double picoAcumuladoR;
   double resultadoAcumuladoR;
   double drawdownMaximoR;
   double somaMFEPontos;
   double somaMAEPontos;
   double somaVelasAteSaida;
   double somaCorpoPercentual;
   double somaPavioSuperiorPercentual;
   double somaPavioInferiorPercentual;
   double somaRangeSobreATR;
   int amostrasATR;
   double resultadoPrimeiraMetadeR;
   double resultadoSegundaMetadeR;
   int operacoesPrimeiraMetade;
   int operacoesSegundaMetade;
   double resultadoPorDiaSemana[7];
   int operacoesPorDiaSemana[7];
  };

struct OCORRENCIA
  {
   datetime horario;
   double superior;
   double inferior;
   double rangePontos;
   int direcao;
   int velasAteRompimento;
   double avancoPontos;
   double contraPontos;
   bool falsoRompimento;
   bool atingiuLinhaOposta;
   int velasAteLinhaOposta;
   bool operacaoExecutada;
   bool venceu;
   bool perdeu;
   bool saiuNoZero;
   double entrada;
   double stopInicial;
   double take;
   double resultadoR;
   double mfePontos;
   double maePontos;
   int velasAteSaida;
  };

struct RESULTADO_HORARIO
  {
   int minutosDoDia;
   ESTATISTICAS dados;
   double nota;
  };

ESTATISTICAS estatistica;
OCORRENCIA ocorrencias[];
double rangesOrdenacao[];
datetime ultimaAtualizacao=0;
int diasSemVelaReferencia=0;
int diasSemHistoricoPosterior=0;
string statusDados="CARREGANDO HISTORICO";
int horaEmAnalise=0;
int minutoEmAnalise=0;
int horariosDaAnalise[];
RESULTADO_HORARIO resultadosPorHorario[];
int indiceSelecionado=0;
int paginaAtual=0;
const int LINHAS_POR_PAGINA=8;
string PREFIXO="IERMTF_";

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
   return SymbolInfoDouble(SimboloDaAnalise,SYMBOL_POINT);
  }

int Digitos()
  {
   return (int)SymbolInfoInteger(SimboloDaAnalise,SYMBOL_DIGITS);
  }

datetime InicioDoDia(const datetime horario)
  {
   MqlDateTime d;
   TimeToStruct(horario,d);
   d.hour=0; d.min=0; d.sec=0;
   return StructToTime(d);
  }

datetime HorarioDaVelaNoDia(const datetime dia)
  {
   return InicioDoDia(dia)+horaEmAnalise*3600+minutoEmAnalise*60;
  }

int MinutosDoHorario(const string valor)
  {
   string partes[];
   if(StringSplit(valor,':',partes)!=2) return -1;
   int hora=(int)StringToInteger(partes[0]);
   int minuto=(int)StringToInteger(partes[1]);
   if(hora<0 || hora>23 || minuto<0 || minuto>59) return -1;
   return hora*60+minuto;
  }

void AdicionarHorarioSemDuplicar(const int minutos)
  {
   if(minutos<0 || minutos>=1440) return;
   for(int i=0;i<ArraySize(horariosDaAnalise);i++)
      if(horariosDaAnalise[i]==minutos) return;
   int tamanho=ArraySize(horariosDaAnalise);
   ArrayResize(horariosDaAnalise,tamanho+1);
   horariosDaAnalise[tamanho]=minutos;
  }

void MontarListaDeHorarios()
  {
   ArrayResize(horariosDaAnalise,0);
   if(ModoDeSelecaoDasVelas==ANALISE_UMA_VELA)
      AdicionarHorarioSemDuplicar(HoraDaVelaAnalisada*60+MinutoDaVelaAnalisada);
   else if(ModoDeSelecaoDasVelas==ANALISE_LISTA_DE_HORARIOS)
     {
      string itens[];
      int total=StringSplit(ListaDeHorarios,',',itens);
      for(int i=0;i<total;i++)
        {
         string item=itens[i];
         StringTrimLeft(item); StringTrimRight(item);
         AdicionarHorarioSemDuplicar(MinutosDoHorario(item));
        }
     }
   else
     {
      int inicio=0,fim=1439;
      if(ModoDeSelecaoDasVelas==ANALISE_INTERVALO_DE_SESSAO)
        {
         inicio=MinutosDoHorario(InicioDaSessao);
         fim=MinutosDoHorario(FimDaSessao);
        }
      int passo=MathMax(1,IntervaloEntreVelasEmMinutos);
      if(inicio>=0 && fim>=inicio)
         for(int minutos=inicio;minutos<=fim;minutos+=passo) AdicionarHorarioSemDuplicar(minutos);
     }
   ArraySort(horariosDaAnalise);
  }

string TextoHorario(const int minutos)
  {
   return StringFormat("%02d:%02d",minutos/60,minutos%60);
  }

void ZerarEstatisticas()
  {
   ZeroMemory(estatistica);
   estatistica.menorRange=DBL_MAX;
   ArrayResize(ocorrencias,0);
   ArrayResize(rangesOrdenacao,0);
   diasSemVelaReferencia=0;
   diasSemHistoricoPosterior=0;
   statusDados="ANALISANDO";
  }

bool ObterVelaDeReferencia(const datetime horarioDesejado,MqlRates &vela)
  {
   int shift=iBarShift(SimboloDaAnalise,TimeframeDaVelaAnalisada,horarioDesejado,false);
   if(shift<0) return false;
   MqlRates dados[1];
   if(CopyRates(SimboloDaAnalise,TimeframeDaVelaAnalisada,shift,1,dados)!=1) return false;
   vela=dados[0];
   int tolerancia=PeriodSeconds(TimeframeDaVelaAnalisada);
   return MathAbs((long)(vela.time-horarioDesejado))<tolerancia;
  }

void LimitesDaVela(const MqlRates &vela,double &superior,double &inferior)
  {
   if(LinhasDoRangeAnalisado==ANALISAR_MAXIMA_MINIMA)
     {
      superior=vela.high;
      inferior=vela.low;
     }
   else
     {
      superior=MathMax(vela.open,vela.close);
      inferior=MathMin(vela.open,vela.close);
     }
  }

bool ObterVelasPosteriores(const datetime inicio,MqlRates &velas[])
  {
   ArrayResize(velas,VelasAposReferenciaParaMedir);
   datetime fim=inicio+(datetime)(VelasAposReferenciaParaMedir*PeriodSeconds(TimeframeParaMedirORompimento))-1;
   int copiadas=CopyRates(SimboloDaAnalise,TimeframeParaMedirORompimento,inicio,fim,velas);
   if(copiadas<VelasAposReferenciaParaMedir)
     {
      ArrayResize(velas,0);
      return false;
     }
   ArraySetAsSeries(velas,false);
   return true;
  }

void AdicionarOcorrencia(const OCORRENCIA &item)
  {
   int indice=ArraySize(ocorrencias);
   ArrayResize(ocorrencias,indice+1);
   ocorrencias[indice]=item;
   ArrayResize(rangesOrdenacao,indice+1);
   rangesOrdenacao[indice]=item.rangePontos;
  }

void AnalisarDia(const datetime dia)
  {
   datetime horario=HorarioDaVelaNoDia(dia);
   int segundosReferencia=PeriodSeconds(TimeframeDaVelaAnalisada);
   if(horario+segundosReferencia>=TimeCurrent()) return;

   MqlRates referencia;
   if(!ObterVelaDeReferencia(horario,referencia)) { diasSemVelaReferencia++; return; }
   double superior=0.0,inferior=0.0;
   LimitesDaVela(referencia,superior,inferior);
   double rangePontos=(superior-inferior)/Ponto();
   if(rangePontos<=0) return;

   MqlRates velas[];
   if(!ObterVelasPosteriores(referencia.time+segundosReferencia,velas)) { diasSemHistoricoPosterior++; return; }

   OCORRENCIA item;
   ZeroMemory(item);
   item.horario=horario;
   item.superior=superior;
   item.inferior=inferior;
   item.rangePontos=rangePontos;
   double distancia=DistanciaMinimaDoRompimentoEmPontos*Ponto();
   int indiceRompimento=-1;

   for(int i=0;i<ArraySize(velas);i++)
     {
      bool rompeuCima=(ConfirmacaoDoRompimento==ANALISAR_ROMPIMENTO_POR_PRECO ? velas[i].high>=superior+distancia : velas[i].close>=superior+distancia);
      bool rompeuBaixo=(ConfirmacaoDoRompimento==ANALISAR_ROMPIMENTO_POR_PRECO ? velas[i].low<=inferior-distancia : velas[i].close<=inferior-distancia);
      if(rompeuCima && rompeuBaixo)
        {
         item.direcao=2;
         indiceRompimento=i;
         break;
        }
      if(rompeuCima) { item.direcao=1; indiceRompimento=i; break; }
      if(rompeuBaixo) { item.direcao=-1; indiceRompimento=i; break; }
     }

   estatistica.amostras++;
   estatistica.somaRanges+=rangePontos;
   estatistica.menorRange=MathMin(estatistica.menorRange,rangePontos);
   estatistica.maiorRange=MathMax(estatistica.maiorRange,rangePontos);

   if(indiceRompimento<0)
     {
      estatistica.semRompimento++;
      AdicionarOcorrencia(item);
      return;
     }
   if(item.direcao==2)
     {
      estatistica.ambiguos++;
      AdicionarOcorrencia(item);
      return;
     }

   item.velasAteRompimento=indiceRompimento+1;
   double avanco=0.0;
   double contra=0.0;
   bool voltouParaDentro=false;
   for(int i=indiceRompimento+1;i<ArraySize(velas);i++)
     {
      bool tocouLinhaOposta=(item.direcao>0 ? velas[i].low<=inferior : velas[i].high>=superior);
      if(tocouLinhaOposta)
        {
         item.atingiuLinhaOposta=true;
         item.velasAteLinhaOposta=i-indiceRompimento;
         bool tambemAvancou=(item.direcao>0 ? velas[i].high>=superior+rangePontos*0.5*Ponto() : velas[i].low<=inferior-rangePontos*0.5*Ponto());
         if(tambemAvancou) estatistica.conflitoNaVelaDaLinhaOposta++;
         break;
        }
      if(item.direcao>0)
        {
         avanco=MathMax(avanco,(velas[i].high-superior)/Ponto());
         contra=MathMax(contra,(superior-velas[i].low)/Ponto());
         if(i>indiceRompimento && velas[i].close<superior) voltouParaDentro=true;
        }
      else
        {
         avanco=MathMax(avanco,(inferior-velas[i].low)/Ponto());
         contra=MathMax(contra,(velas[i].high-inferior)/Ponto());
         if(i>indiceRompimento && velas[i].close>inferior) voltouParaDentro=true;
        }
     }

   item.avancoPontos=avanco;
   item.contraPontos=contra;
   item.falsoRompimento=voltouParaDentro;
   estatistica.rompimentos++;
   if(item.direcao>0) { estatistica.compras++; estatistica.somaAvancoCompra+=avanco; }
   else { estatistica.vendas++; estatistica.somaAvancoVenda+=avanco; }
   if(voltouParaDentro) estatistica.falsos++;
   if(item.atingiuLinhaOposta)
     {
      estatistica.atingiuLinhaOposta++;
      estatistica.somaAvancoAntesLinhaOposta+=avanco;
      estatistica.somaVelasAteLinhaOposta+=item.velasAteLinhaOposta;
      if(item.direcao>0) estatistica.linhaOpostaCompra++;
      else estatistica.linhaOpostaVenda++;
     }
   if(avanco>=rangePontos*0.5) estatistica.alvo05++;
   if(avanco>=rangePontos*0.8) estatistica.alvo08++;
   if(avanco>=rangePontos*1.0)
     {
      estatistica.alvo10++;
      if(item.direcao>0) estatistica.alvo10Compra++;
      else estatistica.alvo10Venda++;
     }
   if(avanco>=rangePontos*1.4) estatistica.alvo14++;
   if(avanco>=rangePontos*2.0) estatistica.alvo20++;
   estatistica.somaAvanco+=avanco;
   estatistica.somaMultiploAvanco+=avanco/rangePontos;
   estatistica.somaContra+=contra;
   estatistica.somaVelasAteRompimento+=item.velasAteRompimento;
   AdicionarOcorrencia(item);
  }

double Percentual(const int parte,const int total)
  {
   return total>0 ? 100.0*parte/total : 0.0;
  }

double Media(const double soma,const int quantidade)
  {
   return quantidade>0 ? soma/quantidade : 0.0;
  }

int BaseDosAvancos()
  {
   return IgnorarDiasSemRompimentoNosAvancos ? estatistica.rompimentos : estatistica.amostras;
  }

double MedianaDosRanges()
  {
   int total=ArraySize(rangesOrdenacao);
   if(total==0) return 0.0;
   double copia[];
   ArrayCopy(copia,rangesOrdenacao);
   ArraySort(copia);
   if(total%2==1) return copia[total/2];
   return (copia[total/2-1]+copia[total/2])/2.0;
  }

double PercentilDosRanges(const double percentil)
  {
   int total=ArraySize(rangesOrdenacao);
   if(total==0) return 0.0;
   double copia[];
   ArrayCopy(copia,rangesOrdenacao);
   ArraySort(copia);
   double posicao=(total-1)*MathMax(0.0,MathMin(1.0,percentil));
   int inferior=(int)MathFloor(posicao);
   int superior=(int)MathCeil(posicao);
   if(inferior==superior) return copia[inferior];
   double peso=posicao-inferior;
   return copia[inferior]*(1.0-peso)+copia[superior]*peso;
  }

void CalcularHorarioAtual()
  {
   ZerarEstatisticas();
   datetime hoje=InicioDoDia(TimeCurrent());
   for(int i=QuantidadeDeDiasParaAnalisar;i>=0;i--)
      AnalisarDia(hoje-i*86400);
  }

double CalcularNota(const ESTATISTICAS &dados)
  {
   if(dados.amostras<5 || dados.rompimentos<3) return 0.0;
   double taxaRompimento=Percentual(dados.rompimentos,dados.amostras);
   double taxaAlvo10=Percentual(dados.alvo10,dados.rompimentos);
   double taxaAlvo14=Percentual(dados.alvo14,dados.rompimentos);
   double taxaFalso=Percentual(dados.falsos,dados.rompimentos);
   double taxaLinhaOposta=Percentual(dados.atingiuLinhaOposta,dados.rompimentos);
   double confianca=MathMin(1.0,dados.amostras/30.0);
   double nota=(taxaRompimento*0.20+taxaAlvo10*0.30+taxaAlvo14*0.20+(100.0-taxaFalso)*0.15+(100.0-taxaLinhaOposta)*0.15)*confianca;
   return MathMax(0.0,MathMin(100.0,nota));
  }

void CalcularEstatisticas()
  {
   MontarListaDeHorarios();
   int total=ArraySize(horariosDaAnalise);
   ArrayResize(resultadosPorHorario,total);
   for(int i=0;i<total;i++)
     {
      horaEmAnalise=horariosDaAnalise[i]/60;
      minutoEmAnalise=horariosDaAnalise[i]%60;
      CalcularHorarioAtual();
      resultadosPorHorario[i].minutosDoDia=horariosDaAnalise[i];
      resultadosPorHorario[i].dados=estatistica;
      resultadosPorHorario[i].nota=CalcularNota(estatistica);
     }

   if(total==0)
     {
      ZerarEstatisticas();
      statusDados="LISTA DE HORARIOS VAZIA";
      ultimaAtualizacao=TimeCurrent();
      return;
     }
   if(indiceSelecionado<0 || indiceSelecionado>=total) indiceSelecionado=0;
   int paginas=(total+LINHAS_POR_PAGINA-1)/LINHAS_POR_PAGINA;
   if(paginaAtual>=paginas) paginaAtual=MathMax(0,paginas-1);
   horaEmAnalise=resultadosPorHorario[indiceSelecionado].minutosDoDia/60;
   minutoEmAnalise=resultadosPorHorario[indiceSelecionado].minutosDoDia%60;
   CalcularHorarioAtual();
   if(estatistica.amostras>0)
      statusDados="DADOS CARREGADOS";
   else if(diasSemHistoricoPosterior>0)
      statusDados="AGUARDANDO HISTORICO "+EnumToString(TimeframeParaMedirORompimento);
   else
      statusDados="SEM VELAS NO HORARIO ESCOLHIDO";
   ultimaAtualizacao=TimeCurrent();
   Print("[INDICADOR RANGE MTF] ",TextoHorario(horaEmAnalise*60+minutoEmAnalise)," | ",statusDados," | amostras=",estatistica.amostras," | sem referencia=",diasSemVelaReferencia," | sem posterior=",diasSemHistoricoPosterior);
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

void CriarBotao(const string sufixo,const string texto,const int x,const int y,const int largura,const int altura,const color fundo,const color corTexto,const color borda)
  {
   string nome=PREFIXO+"UI_"+sufixo;
   if(ObjectFind(0,nome)<0) ObjectCreate(0,nome,OBJ_BUTTON,0,0,0);
   ObjectSetInteger(0,nome,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,nome,OBJPROP_XDISTANCE,PosicaoHorizontalDoPainel+(int)(x*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_YDISTANCE,PosicaoVerticalDoPainel+(int)(y*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_XSIZE,(int)(largura*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_YSIZE,(int)(altura*EscalaDoPainel));
   ObjectSetInteger(0,nome,OBJPROP_BGCOLOR,fundo);
   ObjectSetInteger(0,nome,OBJPROP_COLOR,corTexto);
   ObjectSetInteger(0,nome,OBJPROP_BORDER_COLOR,borda);
   ObjectSetInteger(0,nome,OBJPROP_FONTSIZE,(int)(9*EscalaDoPainel));
   ObjectSetString(0,nome,OBJPROP_FONT,"Consolas");
   ObjectSetString(0,nome,OBJPROP_TEXT,texto);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,false);
  }

string Pct(const int parte,const int total)
  {
   return DoubleToString(Percentual(parte,total),1)+"%";
  }

void AtualizarPainel()
  {
   if(!MostrarPainelEstatistico) return;
   int rompimentosValidos=estatistica.rompimentos;
   CriarRetangulo("FUNDO",0,0,1220,520,COR_FUNDO,COR_BORDA);
   CriarRetangulo("ACENTO",0,0,5,520,COR_CIANO,COR_CIANO);
   CriarTexto("TITULO","ESTATISTICA DE RANGE MTF",18,14,15,COR_TEXTO);
   CriarTexto("SUB",SimboloDaAnalise+" | "+EnumToString(TimeframeDaVelaAnalisada)+" das "+TextoHorario(horaEmAnalise*60+minutoEmAnalise)+" | janela "+IntegerToString(VelasAposReferenciaParaMedir)+" "+EnumToString(TimeframeParaMedirORompimento),18,39,9,COR_MUTED);
   CriarTexto("STATUS",statusDados,350,16,9,estatistica.amostras>0 ? COR_VERDE : COR_OURO);

   CriarRetangulo("AMOSTRA",14,68,256,104,COR_CARTAO,COR_BORDA);
   CriarTexto("AMOSTRA_T","AMOSTRA",26,80,9,COR_MUTED);
   CriarTexto("AMOSTRA_V",IntegerToString(estatistica.amostras)+" dias validos",26,102,16,COR_CIANO);
   CriarTexto("ROMP","Rompimentos  "+IntegerToString(rompimentosValidos)+" ("+Pct(rompimentosValidos,estatistica.amostras)+")",26,134,9,COR_TEXTO);
   CriarTexto("SEM","Sem rompimento  "+IntegerToString(estatistica.semRompimento),26,152,9,COR_MUTED);

   CriarRetangulo("RANGE",284,68,262,104,COR_CARTAO,COR_BORDA);
   CriarTexto("RANGE_T","TAMANHO DAS VELAS",296,80,9,COR_MUTED);
   CriarTexto("RANGE_V",DoubleToString(Media(estatistica.somaRanges,estatistica.amostras),1)+" pts media",296,102,16,COR_OURO);
   CriarTexto("MEDIANA","Mediana  "+DoubleToString(MedianaDosRanges(),1)+" pts",296,134,9,COR_TEXTO);
   CriarTexto("EXTREMOS","P25 "+DoubleToString(PercentilDosRanges(0.25),0)+" | P75 "+DoubleToString(PercentilDosRanges(0.75),0)+" pts",296,152,9,COR_MUTED);

   CriarRetangulo("DIRECAO",14,186,256,104,COR_CARTAO,COR_BORDA);
   CriarTexto("DIR_T","PRIMEIRO ROMPIMENTO",26,198,9,COR_MUTED);
   CriarTexto("COMPRA","Compra  "+IntegerToString(estatistica.compras)+" ("+Pct(estatistica.compras,rompimentosValidos)+")",26,224,11,COR_VERDE);
   CriarTexto("VENDA","Venda    "+IntegerToString(estatistica.vendas)+" ("+Pct(estatistica.vendas,rompimentosValidos)+")",26,248,11,COR_VERMELHO);
   CriarTexto("TEMPO","Tempo medio  "+DoubleToString(Media(estatistica.somaVelasAteRompimento,rompimentosValidos),1)+" velas",26,270,9,COR_MUTED);

   CriarRetangulo("MOV",284,186,262,104,COR_CARTAO,COR_BORDA);
   CriarTexto("MOV_T","DEPOIS DO ROMPIMENTO",296,198,9,COR_MUTED);
   CriarTexto("AVANCO","Avanco medio  "+DoubleToString(Media(estatistica.somaAvanco,BaseDosAvancos()),1)+" pts",296,224,11,COR_CIANO);
   CriarTexto("CONTRA","Compra "+DoubleToString(Media(estatistica.somaAvancoCompra,estatistica.compras),0)+" | Venda "+DoubleToString(Media(estatistica.somaAvancoVenda,estatistica.vendas),0)+" pts",296,248,9,COR_TEXTO);
   CriarTexto("FALSO","Antes oposta "+DoubleToString(Media(estatistica.somaAvancoAntesLinhaOposta,estatistica.atingiuLinhaOposta),0)+" pts | Tocou "+Pct(estatistica.atingiuLinhaOposta,rompimentosValidos),296,270,9,COR_VERMELHO);

   CriarRetangulo("ALVOS",14,304,532,98,COR_CARTAO,COR_BORDA);
   CriarTexto("ALVOS_T","ALVOS ALCANCADOS ANTES DA LINHA OPOSTA",26,316,9,COR_MUTED);
   CriarTexto("A05","0,5x  "+Pct(estatistica.alvo05,rompimentosValidos),26,348,11,COR_VERDE);
   CriarTexto("A08","0,8x  "+Pct(estatistica.alvo08,rompimentosValidos),126,348,11,COR_VERDE);
   CriarTexto("A10","1,0x  "+Pct(estatistica.alvo10,rompimentosValidos),226,348,11,COR_CIANO);
   CriarTexto("A14","1,4x  "+Pct(estatistica.alvo14,rompimentosValidos),326,348,11,COR_OURO);
   CriarTexto("A20","2,0x  "+Pct(estatistica.alvo20,rompimentosValidos),426,348,11,COR_VERMELHO);
   CriarTexto("OBS","Rompimentos ambiguos: "+IntegerToString(estatistica.ambiguos)+" | Ordem ambigua no stop: "+IntegerToString(estatistica.conflitoNaVelaDaLinhaOposta),26,378,8,COR_MUTED);

   CriarRetangulo("QUALIDADE",14,416,532,88,COR_CARTAO,COR_BORDA);
   CriarTexto("QUAL_T","QUALIDADE DO MOVIMENTO SELECIONADO",26,428,9,COR_MUTED);
   CriarTexto("EFICIENCIA","Avanco medio  "+DoubleToString(Media(estatistica.somaMultiploAvanco,rompimentosValidos),2)+"x do range",26,452,11,COR_CIANO);
   CriarTexto("COMPRA_1X","Compra 1x  "+Pct(estatistica.alvo10Compra,estatistica.compras),220,452,10,COR_VERDE);
   CriarTexto("VENDA_1X","Venda 1x  "+Pct(estatistica.alvo10Venda,estatistica.vendas),350,452,10,COR_VERMELHO);
   CriarTexto("CONFIANCA","Amostra "+IntegerToString(estatistica.amostras)+" | Min "+DoubleToString(estatistica.menorRange==DBL_MAX ? 0 : estatistica.menorRange,0)+" | P90 "+DoubleToString(PercentilDosRanges(0.90),0)+" | Max "+DoubleToString(estatistica.maiorRange,0)+" pts",26,480,8,COR_MUTED);

   CriarRetangulo("TABELA",574,68,632,436,COR_CARTAO,COR_BORDA);
   CriarTexto("TAB_T","COMPARACAO DE HORARIOS",588,80,10,COR_TEXTO);
   int melhor=-1;
   for(int i=0;i<ArraySize(resultadosPorHorario);i++)
      if(melhor<0 || resultadosPorHorario[i].nota>resultadosPorHorario[melhor].nota) melhor=i;
   string melhorTexto=(melhor>=0 ? "Melhor: "+TextoHorario(resultadosPorHorario[melhor].minutosDoDia)+"  nota "+DoubleToString(resultadosPorHorario[melhor].nota,0) : "Sem horarios validos");
   CriarTexto("MELHOR",melhorTexto,974,80,9,COR_VERDE);
   CriarTexto("H_HORA","HORA",592,108,8,COR_MUTED);
   CriarTexto("H_NOTA","NOTA",650,108,8,COR_MUTED);
   CriarTexto("H_N","N",702,108,8,COR_MUTED);
   CriarTexto("H_RANGE","RANGE",742,108,8,COR_MUTED);
   CriarTexto("H_ROMPE","ROMPE",810,108,8,COR_MUTED);
   CriarTexto("H_OPOS","OPOSTA",875,108,8,COR_MUTED);
   CriarTexto("H_05","0,5x",950,108,8,COR_MUTED);
   CriarTexto("H_10","1,0x",1018,108,8,COR_MUTED);
   CriarTexto("H_14","1,4x",1086,108,8,COR_MUTED);
   CriarTexto("H_EF","EFIC.",1150,108,8,COR_MUTED);

   for(int linha=0;linha<LINHAS_POR_PAGINA;linha++)
     {
      ObjectDelete(0,PREFIXO+"UI_ROW_"+IntegerToString(linha));
      for(int coluna=0;coluna<10;coluna++) ObjectDelete(0,PREFIXO+"UI_CELL_"+IntegerToString(linha)+"_"+IntegerToString(coluna));
      int indice=paginaAtual*LINHAS_POR_PAGINA+linha;
      if(indice>=ArraySize(resultadosPorHorario)) continue;
      ESTATISTICAS dados=resultadosPorHorario[indice].dados;
      double mediaRange=Media(dados.somaRanges,dados.amostras);
      color corNota=(resultadosPorHorario[indice].nota>=70 ? COR_VERDE : resultadosPorHorario[indice].nota>=50 ? COR_OURO : COR_VERMELHO);
      color fundo=(indice==indiceSelecionado ? C'23,48,65' : C'12,18,28');
      color borda=(indice==indiceSelecionado ? COR_CIANO : COR_BORDA);
      int y=126+linha*32;
      string valores[10];
      valores[0]=TextoHorario(resultadosPorHorario[indice].minutosDoDia);
      valores[1]=DoubleToString(resultadosPorHorario[indice].nota,0);
      valores[2]=IntegerToString(dados.amostras);
      valores[3]=DoubleToString(mediaRange,0);
      valores[4]=DoubleToString(Percentual(dados.rompimentos,dados.amostras),1)+"%";
      valores[5]=DoubleToString(Percentual(dados.atingiuLinhaOposta,dados.rompimentos),1)+"%";
      valores[6]=DoubleToString(Percentual(dados.alvo05,dados.rompimentos),1)+"%";
      valores[7]=DoubleToString(Percentual(dados.alvo10,dados.rompimentos),1)+"%";
      valores[8]=DoubleToString(Percentual(dados.alvo14,dados.rompimentos),1)+"%";
      valores[9]=DoubleToString(Media(dados.somaMultiploAvanco,dados.rompimentos),2)+"x";
      int xs[10]={588,646,694,730,793,858,935,1002,1069,1136};
      int larguras[10]={56,46,34,61,63,75,65,65,65,56};
      for(int coluna=0;coluna<10;coluna++)
         CriarBotao("CELL_"+IntegerToString(linha)+"_"+IntegerToString(coluna),valores[coluna],xs[coluna],y,larguras[coluna],27,fundo,(coluna==1 ? corNota : COR_TEXTO),borda);
     }
   int totalPaginas=MathMax(1,(ArraySize(resultadosPorHorario)+LINHAS_POR_PAGINA-1)/LINHAS_POR_PAGINA);
   CriarTexto("LEGENDA","N=amostras | EFIC.=avanco medio / range | alvos antes da oposta",588,394,8,COR_MUTED);
   CriarTexto("RESUMO_TABELA","Selecionado: "+TextoHorario(horaEmAnalise*60+minutoEmAnalise)+" | 1x antes oposta "+Pct(estatistica.alvo10,rompimentosValidos)+" | oposta em "+DoubleToString(Media(estatistica.somaVelasAteLinhaOposta,estatistica.atingiuLinhaOposta),1)+" velas",588,424,9,COR_CIANO);
   CriarTexto("FALSO_TAB","Falso rompimento "+Pct(estatistica.falsos,rompimentosValidos)+" | Compra 1x "+Pct(estatistica.alvo10Compra,estatistica.compras)+" | Venda 1x "+Pct(estatistica.alvo10Venda,estatistica.vendas),588,448,9,COR_MUTED);
   CriarBotao("ANTERIOR","<",588,474,36,24,COR_FUNDO,COR_TEXTO,COR_BORDA);
   CriarTexto("PAGINA","Pagina "+IntegerToString(paginaAtual+1)+" de "+IntegerToString(totalPaginas),638,478,9,COR_MUTED);
   CriarBotao("PROXIMA",">",1156,474,36,24,COR_FUNDO,COR_TEXTO,COR_BORDA);
   ChartRedraw();
  }

void DesenharUltimoRange()
  {
   string sup=PREFIXO+"RANGE_SUP";
   string inf=PREFIXO+"RANGE_INF";
   ObjectDelete(0,sup);
   ObjectDelete(0,inf);
   if(!DesenharUltimoRangeNoGrafico || ArraySize(ocorrencias)==0) return;
   OCORRENCIA item=ocorrencias[ArraySize(ocorrencias)-1];
   datetime fim=item.horario+PeriodSeconds(TimeframeDaVelaAnalisada)+VelasAposReferenciaParaMedir*PeriodSeconds(TimeframeParaMedirORompimento);
   if(ObjectCreate(0,sup,OBJ_TREND,0,item.horario,item.superior,fim,item.superior))
     {
      ObjectSetInteger(0,sup,OBJPROP_COLOR,COR_VERDE); ObjectSetInteger(0,sup,OBJPROP_WIDTH,3); ObjectSetInteger(0,sup,OBJPROP_RAY_RIGHT,false);
     }
   if(ObjectCreate(0,inf,OBJ_TREND,0,item.horario,item.inferior,fim,item.inferior))
     {
      ObjectSetInteger(0,inf,OBJPROP_COLOR,COR_VERMELHO); ObjectSetInteger(0,inf,OBJPROP_WIDTH,3); ObjectSetInteger(0,inf,OBJPROP_RAY_RIGHT,false);
     }
  }

void ExportarCSV()
  {
   if(!ExportarResultadosParaCSV) return;
   int arquivo=FileOpen(NomeDoArquivoCSV,FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,';');
   if(arquivo==INVALID_HANDLE) { Print("Nao foi possivel criar CSV: ",GetLastError()); return; }
   FileWrite(arquivo,"Data","Superior","Inferior","Range pontos","Direcao","Velas ate romper","Avanco antes da linha oposta","Contra pontos","Falso rompimento","Atingiu linha oposta","Velas ate linha oposta");
   for(int i=0;i<ArraySize(ocorrencias);i++)
     {
      string direcao=(ocorrencias[i].direcao==1 ? "Compra" : ocorrencias[i].direcao==-1 ? "Venda" : ocorrencias[i].direcao==2 ? "Ambiguo" : "Sem rompimento");
      FileWrite(arquivo,TimeToString(ocorrencias[i].horario,TIME_DATE|TIME_MINUTES),DoubleToString(ocorrencias[i].superior,Digitos()),DoubleToString(ocorrencias[i].inferior,Digitos()),DoubleToString(ocorrencias[i].rangePontos,1),direcao,ocorrencias[i].velasAteRompimento,DoubleToString(ocorrencias[i].avancoPontos,1),DoubleToString(ocorrencias[i].contraPontos,1),ocorrencias[i].falsoRompimento ? "Sim" : "Nao",ocorrencias[i].atingiuLinhaOposta ? "Sim" : "Nao",ocorrencias[i].velasAteLinhaOposta);
     }
   FileClose(arquivo);
   Print("CSV exportado em Arquivos Comuns: ",NomeDoArquivoCSV);
  }

void ApagarObjetos()
  {
   for(int i=ObjectsTotal(0,0,-1)-1;i>=0;i--)
     {
      string nome=ObjectName(0,i,0,-1);
      if(StringFind(nome,PREFIXO)==0) ObjectDelete(0,nome);
     }
  }

void ExecutarAnalise()
  {
   CalcularEstatisticas();
   AtualizarPainel();
   DesenharUltimoRange();
   ExportarCSV();
  }

int OnInit()
  {
   if(!SymbolSelect(SimboloDaAnalise,true)) return INIT_FAILED;
   if(HoraDaVelaAnalisada<0 || HoraDaVelaAnalisada>23 || MinutoDaVelaAnalisada<0 || MinutoDaVelaAnalisada>59 || QuantidadeDeDiasParaAnalisar<1 || VelasAposReferenciaParaMedir<1)
      return INIT_PARAMETERS_INCORRECT;
   if(PeriodSeconds(TimeframeDaVelaAnalisada)<=PeriodSeconds(TimeframeParaMedirORompimento))
     {
      Print("O timeframe da vela analisada deve ser maior que o timeframe de medicao.");
      return INIT_PARAMETERS_INCORRECT;
     }
   EventSetTimer(5);
   ExecutarAnalise();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int motivo)
  {
   EventKillTimer();
   ApagarObjetos();
  }

void OnTimer()
  {
   if(estatistica.amostras==0 || TimeCurrent()-ultimaAtualizacao>=300) ExecutarAnalise();
  }

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
  {
   if(id!=CHARTEVENT_OBJECT_CLICK) return;
   string base=PREFIXO+"UI_";
   if(sparam==base+"ANTERIOR")
     {
      if(paginaAtual>0) paginaAtual--;
      AtualizarPainel();
      return;
     }
   if(sparam==base+"PROXIMA")
     {
      int totalPaginas=MathMax(1,(ArraySize(resultadosPorHorario)+LINHAS_POR_PAGINA-1)/LINHAS_POR_PAGINA);
      if(paginaAtual+1<totalPaginas) paginaAtual++;
      AtualizarPainel();
      return;
     }
   string prefixoLinha=base+"CELL_";
   if(StringFind(sparam,prefixoLinha)!=0) return;
   string identificador=StringSubstr(sparam,StringLen(prefixoLinha));
   int separador=StringFind(identificador,"_");
   if(separador<0) return;
   int linha=(int)StringToInteger(StringSubstr(identificador,0,separador));
   int indice=paginaAtual*LINHAS_POR_PAGINA+linha;
   if(indice<0 || indice>=ArraySize(resultadosPorHorario)) return;
   indiceSelecionado=indice;
   horaEmAnalise=resultadosPorHorario[indice].minutosDoDia/60;
   minutoEmAnalise=resultadosPorHorario[indice].minutosDoDia%60;
   CalcularHorarioAtual();
   statusDados=(estatistica.amostras>0 ? "DADOS CARREGADOS" : "SEM DADOS PARA ESTE HORARIO");
   AtualizarPainel();
   DesenharUltimoRange();
   ExportarCSV();
  }

int OnCalculate(const int rates_total,const int prev_calculated,const datetime &time[],const double &open[],const double &high[],const double &low[],const double &close[],const long &tick_volume[],const long &volume[],const int &spread[])
  {
   return rates_total;
  }
