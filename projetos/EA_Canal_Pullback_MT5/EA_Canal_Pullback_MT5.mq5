#property strict
#property version   "1.11"
#property description "Rompimento de canal horario e automatico por pullback, sem repaint"

#include <Trade/Trade.mqh>

CTrade negociacao;

//--- Enumeracoes dos modos configuraveis
enum ENUM_ORIGEM_CANAL
  {
   CANAL_POR_HORARIO=0,
   CANAL_AUTOMATICO_PULLBACK=1,
   CANAL_HORARIO_E_PULLBACK=2
  };

enum ENUM_METODO_CANAL_HORARIO
  {
   CANAL_MAXIMA_MINIMA=0,
   CANAL_ABERTURA_FECHAMENTO=1,
   CANAL_CORPO_SEM_PAVIOS=2,
   CANAL_HIBRIDO=3
  };

enum ENUM_RENOVACAO_CANAL
  {
   RENOVAR_A_CADA_HORA=0,
   RENOVAR_POR_SESSAO=1,
   RENOVAR_EM_HORARIO_MANUAL=2,
   RENOVAR_UMA_VEZ_POR_DIA=3
  };

enum ENUM_TENDENCIA
  {
   TENDENCIA_POR_MEDIAS=1,
   TENDENCIA_POR_ESTRUTURA=2,
   TENDENCIA_POR_MEDIAS_E_ESTRUTURA=3
  };

enum ENUM_POSICIONAMENTO_CANAL
  {
   POSICAO_PRIMEIRA_VELA=1,
   POSICAO_EXTREMO_PULLBACK=2,
   POSICAO_FECHAMENTO_PRIMEIRA_VELA=3,
   POSICAO_CENTRALIZADA_PRIMEIRA_VELA=4
  };

enum ENUM_ENTRADA_PULLBACK
  {
   ENTRADA_NO_ROMPIMENTO=0,
   ENTRADA_NO_RETESTE=1,
   ENTRADA_CONFORME_FILTRO_GERAL=2
  };

enum ENUM_MODO_TAKE
  {
   TAKE_FIXO_PONTOS=0,
   TAKE_MEIO_CANAL=1,
   TAKE_UM_CANAL=2,
   TAKE_UM_DOIS_CANAL=3,
   TAKE_UM_MEIO_CANAL=4,
   TAKE_DOIS_CANAIS=5,
   TAKE_MULTIPLICADOR=6
  };

enum ENUM_MODO_STOP
  {
   STOP_FIXO_PONTOS=0,
   STOP_LIMITE_OPOSTO=1,
   STOP_ALEM_LIMITE_OPOSTO=2,
   STOP_UM_CANAL=3,
   STOP_UM_DOIS_CANAL=4,
   STOP_MULTIPLICADOR=5,
   STOP_ATR=6,
   STOP_ALEM_EXTREMO_PULLBACK=7
  };

enum ENUM_MODO_LOTE
  {
   LOTE_FIXO=0,
   LOTE_POR_PERCENTUAL=1,
   LOTE_POR_RISCO_MONETARIO=2
  };

enum ENUM_MODO_BREAKEVEN
  {
   BREAKEVEN_POR_PONTOS=0,
   BREAKEVEN_POR_CANAL=1,
   BREAKEVEN_APOS_ALVO_1=2
  };

enum ENUM_MODO_TRAILING
  {
   TRAILING_FIXO=0,
   TRAILING_POR_CANAL=1,
   TRAILING_POR_ATR=2,
   TRAILING_APOS_ALVO_1=3,
   TRAILING_APOS_BREAKEVEN=4
  };

enum ENUM_ESTADO_AUTOMATICO
  {
   SEM_TENDENCIA=0,
   ESTADO_TENDENCIA_ALTA=1,
   ESTADO_TENDENCIA_BAIXA=2,
   PULLBACK_IDENTIFICADO=3,
   CANAL_FORMADO=4,
   ROMPIMENTO_CONFIRMADO=5,
   OPERACAO_ABERTA=6,
   CANAL_INVALIDADO=7
  };

//--- Inputs de formacao do canal
input group "01 - Formacao do canal"
input string SimboloParaOperar="XAUUSD";
input ENUM_TIMEFRAMES PeriodoDoGrafico=PERIOD_M1;
input int VelasParaFormarCanal=10;
input bool UsarInicioDeCadaHora=true;
input int HoraInicialManual=0;
input int MinutoInicialManual=0;
input ENUM_ORIGEM_CANAL ModoDeFormacaoDoCanal=CANAL_HORARIO_E_PULLBACK;
input ENUM_METODO_CANAL_HORARIO MetodoDeCalculoDoCanalHorario=CANAL_MAXIMA_MINIMA;
input ENUM_RENOVACAO_CANAL RenovacaoDoCanal=RENOVAR_A_CADA_HORA;
input double MultiplicadorMaximoPavioHibrido=2.0;
input bool PermitirNovaEntradaNoMesmoCanal=false;

//--- Inputs de tendencia e estrutura
input group "02 - Tendencia e estrutura do pullback"
input ENUM_TENDENCIA ModoDeIdentificacaoDaTendencia=TENDENCIA_POR_MEDIAS_E_ESTRUTURA;
input int PeriodoMediaRapida=9;
input int PeriodoMediaLenta=21;
input ENUM_TIMEFRAMES TimeframeDaTendencia=PERIOD_M5;
input bool ExigirTendenciaDefinida=true;
input bool PermitirPullbackContraTendencia=false;
input int BarrasParaAnalisarEstrutura=60;
input int ForcaDoPivoEstrutural=2;

//--- Inputs do canal automatico por pullback
input group "03 - Canal automatico por pullback"
input bool AtivarCanalAutomaticoPullback=true;
input int MinimoDeVelasDoPullback=2;
input int MaximoDeVelasDoPullback=8;
input bool PermitirVelasNeutras=true;
input int MaximoDeVelasNeutras=1;
input bool ExigirFechamentosContraTendencia=true;
input bool UsarPavioNaIdentificacaoDoPullback=true;
input int PeriodoDoATR=14;
input int QuantidadeDeVelasParaMediaATR=10;
input ENUM_TIMEFRAMES TimeframeDoATR=PERIOD_M1;
input double MultiplicadorDoATR=1.0;
input bool UsarATRMedio=true;
input bool UsarATRAntesDoPullback=true;
input ENUM_POSICIONAMENTO_CANAL ModoDePosicionamentoDoCanal=POSICAO_PRIMEIRA_VELA;
input bool ExigirRetesteDoCanalPullback=false;
input int VelasMaximasParaRetestePullback=3;
input ENUM_ENTRADA_PULLBACK EntradaNoRompimentoOuReteste=ENTRADA_CONFORME_FILTRO_GERAL;
input double ToleranciaRompimentoPullbackEmPontos=1.0;
input bool PermitirNovaEntradaNoMesmoPullback=false;
input int MaximoDeVelasDeValidadeDoCanal=20;
input bool CancelarSeRomperEstrutura=true;

//--- Inputs de rompimento
input group "04 - Rompimento e confirmacao"
input bool PermitirCompras=true;
input bool PermitirVendas=true;
input bool ExigirFechamentoForaDoCanal=true;
input double ToleranciaDoRompimentoEmPontos=1.0;
input int VelasDeConfirmacao=1;
input bool ExigirReteste=false;
input int MaximoDeVelasParaReteste=3;
input bool EntradaSomenteAposFechamento=true;
input bool NaoEntrarNaVelaQueFormaORompimento=true;
input bool AtivarFiltroDeVelaGrande=true;
input double TamanhoMaximoDaVelaEmPontos=500.0;
input bool UsarATRParaFiltrarVelaGrande=true;
input double MultiplicadorMaximoDaVelaSobreATR=2.5;
input bool AtivarExpansaoDeCanalCurto=true;
input double CanalCurtoAbaixoDePontos=300.0;

//--- Inputs de take profit
input group "05 - Take profit e multiplos alvos"
input ENUM_MODO_TAKE ModoDoTakeProfit=TAKE_UM_CANAL;
input double MultiplicadorDoTakeProfit=1.0;
input double TakeProfitEmPontos=300.0;
input bool UsarMultiplosAlvos=false;
input int QuantidadeDeAlvos=4;
input double Alvo1Multiplicador=0.5;
input double Alvo2Multiplicador=1.0;
input double Alvo3Multiplicador=1.2;
input double Alvo4Multiplicador=1.5;
input double PercentualFechamentoAlvo1=25.0;
input double PercentualFechamentoAlvo2=25.0;
input double PercentualFechamentoAlvo3=25.0;
input double PercentualFechamentoAlvo4=25.0;

//--- Inputs de stop loss
input group "06 - Stop loss"
input ENUM_MODO_STOP ModoDoStopLoss=STOP_UM_CANAL;
input double MultiplicadorDoStop=1.0;
input double StopFixoEmPontos=300.0;
input double OffsetDoStopEmPontos=10.0;
input double MultiplicadorStopATR=1.5;

//--- Inputs do filtro ATR
input group "07 - Filtro ATR e tamanho do canal"
input bool AtivarFiltroATR=true;
input int PeriodoATR=14;
input ENUM_TIMEFRAMES TimeframeATR=PERIOD_M1;
input double ATRMinimoEmPontos=0.0;
input double ATRMaximoEmPontos=100000.0;
input bool UsarFiltroDeTamanhoDoCanal=true;
input double TamanhoMinimoDoCanalSobreATR=0.5;
input double TamanhoMaximoDoCanalSobreATR=5.0;

//--- Inputs de breakeven e trailing
input group "08 - Breakeven"
input bool AtivarBreakeven=true;
input ENUM_MODO_BREAKEVEN ModoDeAtivacaoDoBreakeven=BREAKEVEN_POR_CANAL;
input double BreakevenEmPontos=200.0;
input double BreakevenEmMultiploDoCanal=0.5;
input double LucroExtraNoBreakevenEmPontos=2.0;

input group "09 - Trailing stop"
input bool AtivarTrailingStop=false;
input ENUM_MODO_TRAILING ModoDoTrailing=TRAILING_FIXO;
input double TrailingInicioEmPontos=300.0;
input double TrailingInicioEmMultiploDoCanal=1.0;
input double DistanciaDoTrailingEmPontos=150.0;
input double PassoDoTrailingEmPontos=20.0;
input bool TrailingBaseadoNoATR=false;
input double MultiplicadorTrailingATR=1.0;

//--- Inputs de risco e limites
input group "10 - Gerenciamento de risco"
input ENUM_MODO_LOTE ModoDeCalculoDoLote=LOTE_FIXO;
input double LoteFixo=0.01;
input double PercentualDeRisco=1.0;
input double RiscoMonetario=50.0;
input double LoteMinimo=0.01;
input double LoteMaximo=100.0;
input double PassoDoLote=0.01;
input int MaximoDeOperacoesPorDia=3;
input int MaximoDeOperacoesPorHora=1;
input int MaximoDeOperacoesAbertas=1;
input int MaximoDePerdasConsecutivas=3;
input double PerdaMaximaDiariaPercentual=3.0;
input double LucroMaximoDiario=0.0;
input bool PausaAposStop=true;
input int MinutosDeCooldownAposOperacao=15;

//--- Inputs operacionais e sessoes
input group "11 - Filtros operacionais"
input double SpreadMaximoEmPontos=80.0;
input ulong SlippageMaximo=20;
input ulong MagicNumber=123456;
input bool PermitirApenasHorarioConfigurado=false;
input string HorarioInicialOperacao="00:00";
input string HorarioFinalOperacao="23:59";
input bool AtivarSessao1=true;
input string InicioSessao1="00:00";
input string FimSessao1="23:59";
input bool AtivarSessao2=false;
input string InicioSessao2="08:00";
input string FimSessao2="12:00";
input bool AtivarSessao3=false;
input string InicioSessao3="13:00";
input string FimSessao3="17:00";
input bool BloquearSextaFeira=false;
input bool BloquearRollover=true;
input string InicioRollover="23:55";
input string FimRollover="00:10";
input double DistanciaMinimaDoCanal=0.0;
input double DistanciaMaximaDoCanal=100000.0;
input bool AtivarFiltroDeNoticiaManual=false;
input string HorarioNoticia1="";
input string HorarioNoticia2="";
input string HorarioNoticia3="";
input int MinutosAntesDaNoticia=15;
input int MinutosDepoisDaNoticia=15;

input group "12 - Visual e diagnostico"
input bool DesenharCanalNoGrafico=true;
input bool MostrarPainel=true;
input int PosicaoHorizontalDoPainel=16;
input int PosicaoVerticalDoPainel=24;
input double EscalaDoPainel=1.0;
input bool PainelRecolhidoInicialmente=false;
input bool AtivarLogsDetalhados=true;
input bool RegistrarCadaEntradaNoDiario=true;
input bool DestacarEntradasNoGrafico=true;
input int TamanhoDaSetaDeEntrada=4;
input bool MostrarSomenteCanalAtual=true;

input group "13 - Criterio de otimizacao robusta"
input bool AtivarCriterioRobustoOnTester=true;
input int MinimoDePosicoesCompletasOnTester=100;
input double FatorLucroMinimoOnTester=1.15;
input double DrawdownMaximoPercentualOnTester=15.0;
input bool PenalizarConcentracaoMensalOnTester=true;
input double ConcentracaoMensalMaximaOnTester=35.0;
input bool RegistrarResumoOnTester=true;
input bool RegistrarResumoPorHorarioOnTester=true;
input int MinimoDeEntradasParaDestacarHorario=10;

//--- Estruturas de estado interno
struct SCanal
  {
   bool              ativo;
   bool              automatico;
   int               direcao;
   datetime          inicio;
   datetime          formadoEm;
   datetime          expiracao;
   double            superior;
   double            inferior;
   double            altura;
   double            atr;
   double            extremoPullback;
   double            estruturaProtegida;
   bool              operado;
   long              identificador;
  };

struct SPullback
  {
   bool              candidato;
   int               direcao;
   datetime          inicio;
   int               velas;
   int               neutras;
   double            primeiraAbertura;
   double            primeiraFechamento;
   double            primeiraMaxima;
   double            primeiraMinima;
   double            extremoMinimo;
   double            extremoMaximo;
   double            estruturaProtegida;
  };

struct SResultadoPosicao
  {
   ulong             identificador;
   double            resultado;
   double            volumeEntrada;
   double            volumeSaida;
   datetime          abertura;
   datetime          fechamento;
   bool              possuiEntrada;
   bool              possuiSaida;
  };

struct SMetricasRobustas
  {
   int               posicoes;
   int               vencedoras;
   int               perdedoras;
   double            lucroLiquido;
   double            lucroBruto;
   double            perdaBruta;
   double            fatorLucro;
   double            expectativa;
   double            concentracaoMensal;
  };

SCanal canal;
SPullback pullback;
ENUM_ESTADO_AUTOMATICO estadoAutomatico=SEM_TENDENCIA;

string simbolo="";
double ponto=0.0;
int digitos=0;
int handleATR=INVALID_HANDLE;
int handleATRPullback=INVALID_HANDLE;
int handleMediaRapida=INVALID_HANDLE;
int handleMediaLenta=INVALID_HANDLE;
datetime ultimaBarra=0;
datetime ultimaBarraEntrada=0;
datetime ultimaSaida=0;
datetime ultimaSaidaComPerda=0;
datetime ultimoInicioCanalHorario=0;
int confirmacoesRompimento=0;
int direcaoRompimento=0;
bool aguardandoReteste=false;
int velasAguardandoReteste=0;
bool expansaoCanalCurtoRealizada=false;
string motivoBloqueio="Inicializando";
string sinalAtual="Sem sinal";
int tendenciaAtual=0;
double atrAtual=0.0;
int operacoesHoje=0;
int operacoesNaHora=0;
int perdasConsecutivas=0;
double resultadoDiario=0.0;
bool alvoAtingido[4];
bool breakevenExecutado=false;
double volumeInicialPosicao=0.0;
double canalPosicaoSuperior=0.0;
double canalPosicaoInferior=0.0;
double canalPosicaoAltura=0.0;
double canalPosicaoATR=0.0;
string prefixoPainel="";
bool painelRecolhido=false;
ulong ultimaAtualizacaoPainelMs=0;
bool painelPrecisaRedesenhar=true;

//--- Utilitarios gerais
void Log(const string texto)
  {
   if(AtivarLogsDetalhados)
      Print("[EA Canal Pullback] ",texto);
  }

double NormalizarPreco(const double preco)
  {
   return NormalizeDouble(preco,digitos);
  }

int DigitosVolume(const double passo)
  {
   if(passo>=1.0) return 0;
   if(passo>=0.1) return 1;
   if(passo>=0.01) return 2;
   if(passo>=0.001) return 3;
   return 4;
  }

double NormalizarVolume(const double volumeDesejado)
  {
   double minimoCorretora=SymbolInfoDouble(simbolo,SYMBOL_VOLUME_MIN);
   double maximoCorretora=SymbolInfoDouble(simbolo,SYMBOL_VOLUME_MAX);
   double passoCorretora=SymbolInfoDouble(simbolo,SYMBOL_VOLUME_STEP);
   double minimo=MathMax(minimoCorretora,LoteMinimo);
   double maximo=MathMin(maximoCorretora,LoteMaximo);
   double passo=MathMax(passoCorretora,PassoDoLote);
   if(passo<=0.0) passo=passoCorretora;
   double volume=MathFloor((volumeDesejado+1e-12)/passo)*passo;
   volume=MathMax(minimo,MathMin(maximo,volume));
   return NormalizeDouble(volume,DigitosVolume(passo));
  }

datetime InicioDoDia(const datetime horario)
  {
   MqlDateTime partes;
   TimeToStruct(horario,partes);
   partes.hour=0;
   partes.min=0;
   partes.sec=0;
   return StructToTime(partes);
  }

int MinutosDoHorario(const string horario)
  {
   string partes[];
   if(StringSplit(horario,':',partes)!=2)
      return -1;
   int hora=(int)StringToInteger(partes[0]);
   int minuto=(int)StringToInteger(partes[1]);
   if(hora<0 || hora>23 || minuto<0 || minuto>59)
      return -1;
   return hora*60+minuto;
  }

bool EstaNoIntervalo(const int agora,const int inicio,const int fim)
  {
   if(inicio<0 || fim<0) return false;
   if(inicio<=fim) return agora>=inicio && agora<=fim;
   return agora>=inicio || agora<=fim;
  }

bool EstaNaSessao(const datetime horario,const bool ativa,const string inicio,const string fim)
  {
   if(!ativa) return false;
   MqlDateTime partes;
   TimeToStruct(horario,partes);
   return EstaNoIntervalo(partes.hour*60+partes.min,MinutosDoHorario(inicio),MinutosDoHorario(fim));
  }

string ChaveGlobal(const string sufixo)
  {
   return StringFormat("EACP_%I64u_%s_%s",MagicNumber,simbolo,sufixo);
  }

bool EstaNoStrategyTester()
  {
   return MQLInfoInteger(MQL_TESTER)>0 || MQLInfoInteger(MQL_OPTIMIZATION)>0;
  }

void SalvarEstado()
  {
   if(EstaNoStrategyTester()) return;
   GlobalVariableSet(ChaveGlobal("ATV"),canal.ativo ? 1.0 : 0.0);
   GlobalVariableSet(ChaveGlobal("AUT"),canal.automatico ? 1.0 : 0.0);
   GlobalVariableSet(ChaveGlobal("DIR"),(double)canal.direcao);
   GlobalVariableSet(ChaveGlobal("INI"),(double)canal.inicio);
   GlobalVariableSet(ChaveGlobal("FRM"),(double)canal.formadoEm);
   GlobalVariableSet(ChaveGlobal("EXP"),(double)canal.expiracao);
   GlobalVariableSet(ChaveGlobal("SUP"),canal.superior);
   GlobalVariableSet(ChaveGlobal("INF"),canal.inferior);
   GlobalVariableSet(ChaveGlobal("ALT"),canal.altura);
   GlobalVariableSet(ChaveGlobal("ATR"),canal.atr);
   GlobalVariableSet(ChaveGlobal("EXT"),canal.extremoPullback);
   GlobalVariableSet(ChaveGlobal("EST"),canal.estruturaProtegida);
   GlobalVariableSet(ChaveGlobal("OPE"),canal.operado ? 1.0 : 0.0);
   GlobalVariableSet(ChaveGlobal("ID"),(double)canal.identificador);
   GlobalVariableSet(ChaveGlobal("PALT"),canalPosicaoAltura);
   GlobalVariableSet(ChaveGlobal("PSUP"),canalPosicaoSuperior);
   GlobalVariableSet(ChaveGlobal("PINF"),canalPosicaoInferior);
   GlobalVariableSet(ChaveGlobal("PATR"),canalPosicaoATR);
   GlobalVariableSet(ChaveGlobal("PVOL"),volumeInicialPosicao);
   GlobalVariableSet(ChaveGlobal("BE"),breakevenExecutado ? 1.0 : 0.0);
   GlobalVariableSet(ChaveGlobal("PBC"),pullback.candidato ? 1.0 : 0.0);
   GlobalVariableSet(ChaveGlobal("PBD"),(double)pullback.direcao);
   GlobalVariableSet(ChaveGlobal("PBI"),(double)pullback.inicio);
   GlobalVariableSet(ChaveGlobal("PBV"),(double)pullback.velas);
   GlobalVariableSet(ChaveGlobal("PBN"),(double)pullback.neutras);
   GlobalVariableSet(ChaveGlobal("PBO"),pullback.primeiraAbertura);
   GlobalVariableSet(ChaveGlobal("PBF"),pullback.primeiraFechamento);
   GlobalVariableSet(ChaveGlobal("PBH"),pullback.primeiraMaxima);
   GlobalVariableSet(ChaveGlobal("PBL"),pullback.primeiraMinima);
   GlobalVariableSet(ChaveGlobal("PBX"),pullback.extremoMaximo);
   GlobalVariableSet(ChaveGlobal("PBM"),pullback.extremoMinimo);
   GlobalVariableSet(ChaveGlobal("PBE"),pullback.estruturaProtegida);
   GlobalVariableSet(ChaveGlobal("CNF"),(double)confirmacoesRompimento);
   GlobalVariableSet(ChaveGlobal("DRP"),(double)direcaoRompimento);
   GlobalVariableSet(ChaveGlobal("RET"),aguardandoReteste ? 1.0 : 0.0);
   GlobalVariableSet(ChaveGlobal("VRR"),(double)velasAguardandoReteste);
   GlobalVariableSet(ChaveGlobal("EXC"),expansaoCanalCurtoRealizada ? 1.0 : 0.0);
   for(int i=0;i<4;i++)
      GlobalVariableSet(ChaveGlobal(StringFormat("A%d",i+1)),alvoAtingido[i] ? 1.0 : 0.0);
  }

void CarregarEstado()
  {
   if(EstaNoStrategyTester()) return;
   if(!GlobalVariableCheck(ChaveGlobal("ID")))
      return;
   canal.ativo=GlobalVariableGet(ChaveGlobal("ATV"))>0.5;
   canal.automatico=GlobalVariableGet(ChaveGlobal("AUT"))>0.5;
   canal.direcao=(int)GlobalVariableGet(ChaveGlobal("DIR"));
   canal.inicio=(datetime)GlobalVariableGet(ChaveGlobal("INI"));
   canal.formadoEm=(datetime)GlobalVariableGet(ChaveGlobal("FRM"));
   canal.expiracao=(datetime)GlobalVariableGet(ChaveGlobal("EXP"));
   canal.superior=GlobalVariableGet(ChaveGlobal("SUP"));
   canal.inferior=GlobalVariableGet(ChaveGlobal("INF"));
   canal.altura=GlobalVariableGet(ChaveGlobal("ALT"));
   canal.atr=GlobalVariableGet(ChaveGlobal("ATR"));
   canal.extremoPullback=GlobalVariableGet(ChaveGlobal("EXT"));
   canal.estruturaProtegida=GlobalVariableGet(ChaveGlobal("EST"));
   canal.operado=GlobalVariableGet(ChaveGlobal("OPE"))>0.5;
   canal.identificador=(long)GlobalVariableGet(ChaveGlobal("ID"));
   canalPosicaoAltura=GlobalVariableGet(ChaveGlobal("PALT"));
   canalPosicaoSuperior=GlobalVariableGet(ChaveGlobal("PSUP"));
   canalPosicaoInferior=GlobalVariableGet(ChaveGlobal("PINF"));
   canalPosicaoATR=GlobalVariableGet(ChaveGlobal("PATR"));
   volumeInicialPosicao=GlobalVariableGet(ChaveGlobal("PVOL"));
   breakevenExecutado=GlobalVariableGet(ChaveGlobal("BE"))>0.5;
   pullback.candidato=GlobalVariableGet(ChaveGlobal("PBC"))>0.5;
   pullback.direcao=(int)GlobalVariableGet(ChaveGlobal("PBD"));
   pullback.inicio=(datetime)GlobalVariableGet(ChaveGlobal("PBI"));
   pullback.velas=(int)GlobalVariableGet(ChaveGlobal("PBV"));
   pullback.neutras=(int)GlobalVariableGet(ChaveGlobal("PBN"));
   pullback.primeiraAbertura=GlobalVariableGet(ChaveGlobal("PBO"));
   pullback.primeiraFechamento=GlobalVariableGet(ChaveGlobal("PBF"));
   pullback.primeiraMaxima=GlobalVariableGet(ChaveGlobal("PBH"));
   pullback.primeiraMinima=GlobalVariableGet(ChaveGlobal("PBL"));
   pullback.extremoMaximo=GlobalVariableGet(ChaveGlobal("PBX"));
   pullback.extremoMinimo=GlobalVariableGet(ChaveGlobal("PBM"));
   pullback.estruturaProtegida=GlobalVariableGet(ChaveGlobal("PBE"));
   confirmacoesRompimento=(int)GlobalVariableGet(ChaveGlobal("CNF"));
   direcaoRompimento=(int)GlobalVariableGet(ChaveGlobal("DRP"));
   aguardandoReteste=GlobalVariableGet(ChaveGlobal("RET"))>0.5;
   velasAguardandoReteste=(int)GlobalVariableGet(ChaveGlobal("VRR"));
   expansaoCanalCurtoRealizada=GlobalVariableCheck(ChaveGlobal("EXC")) && GlobalVariableGet(ChaveGlobal("EXC"))>0.5;
   for(int i=0;i<4;i++)
      alvoAtingido[i]=GlobalVariableGet(ChaveGlobal(StringFormat("A%d",i+1)))>0.5;
  }

//--- Leitura de indicadores somente em candles fechados
bool LerBufferFechado(const int handle,const int deslocamento,double &valor)
  {
   double dados[1];
   if(handle==INVALID_HANDLE || CopyBuffer(handle,0,deslocamento,1,dados)!=1)
      return false;
   valor=dados[0];
   return valor>0.0 && valor!=EMPTY_VALUE;
  }

double CalcularATRMedio(const datetime antesDe)
  {
   int deslocamento=1;
   if(UsarATRAntesDoPullback && antesDe>0)
     {
      int barra=iBarShift(simbolo,TimeframeDoATR,antesDe,false);
      if(barra>=0) deslocamento=barra+1;
     }
   int quantidade=MathMax(1,QuantidadeDeVelasParaMediaATR);
   double valores[];
   ArrayResize(valores,quantidade);
   if(CopyBuffer(handleATRPullback,0,deslocamento,quantidade,valores)!=quantidade)
      return 0.0;
   double soma=0.0;
   int validos=0;
   for(int i=0;i<quantidade;i++)
     {
      if(valores[i]>0.0 && valores[i]!=EMPTY_VALUE)
        {
         soma+=valores[i];
         validos++;
        }
     }
   if(validos==0) return 0.0;
   if(!UsarATRMedio) return valores[quantidade-1];
   return soma/validos;
  }

//--- Deteccao de estrutura por dois pivôs confirmados
bool EhPivoAlto(const MqlRates &taxas[],const int indice,const int forca)
  {
   for(int j=1;j<=forca;j++)
      if(taxas[indice].high<=taxas[indice-j].high || taxas[indice].high<=taxas[indice+j].high)
         return false;
   return true;
  }

bool EhPivoBaixo(const MqlRates &taxas[],const int indice,const int forca)
  {
   for(int j=1;j<=forca;j++)
      if(taxas[indice].low>=taxas[indice-j].low || taxas[indice].low>=taxas[indice+j].low)
         return false;
   return true;
  }

bool LerEstrutura(int &direcao,double &nivelProtegido)
  {
   direcao=0;
   nivelProtegido=0.0;
   int forca=MathMax(1,ForcaDoPivoEstrutural);
   int quantidade=MathMax(BarrasParaAnalisarEstrutura,forca*2+10);
   MqlRates taxas[];
   ArraySetAsSeries(taxas,true);
   if(CopyRates(simbolo,TimeframeDaTendencia,0,quantidade,taxas)<quantidade)
      return false;
   double altos[2]={0.0,0.0};
   double baixos[2]={0.0,0.0};
   int contaAltos=0,contaBaixos=0;
   for(int i=forca+1;i<quantidade-forca && (contaAltos<2 || contaBaixos<2);i++)
     {
      if(contaAltos<2 && EhPivoAlto(taxas,i,forca)) altos[contaAltos++]=taxas[i].high;
      if(contaBaixos<2 && EhPivoBaixo(taxas,i,forca)) baixos[contaBaixos++]=taxas[i].low;
     }
   if(contaAltos<2 || contaBaixos<2)
      return false;
   bool alta=altos[0]>altos[1] && baixos[0]>baixos[1];
   bool baixa=altos[0]<altos[1] && baixos[0]<baixos[1];
   if(alta)
     {
      direcao=1;
      nivelProtegido=baixos[0];
      return true;
     }
   if(baixa)
     {
      direcao=-1;
      nivelProtegido=altos[0];
      return true;
     }
   return true;
  }

int IdentificarTendencia(double &estruturaProtegida)
  {
   double rapida=0.0,lenta=0.0;
   bool mediasValidas=LerBufferFechado(handleMediaRapida,1,rapida) && LerBufferFechado(handleMediaLenta,1,lenta);
   int tendenciaMedias=0;
   if(mediasValidas)
     {
      if(rapida>lenta) tendenciaMedias=1;
      else if(rapida<lenta) tendenciaMedias=-1;
     }
   int tendenciaEstrutura=0;
   double protegida=0.0;
   bool estruturaValida=LerEstrutura(tendenciaEstrutura,protegida);
   estruturaProtegida=protegida;
   if(ModoDeIdentificacaoDaTendencia==TENDENCIA_POR_MEDIAS)
      return tendenciaMedias;
   if(ModoDeIdentificacaoDaTendencia==TENDENCIA_POR_ESTRUTURA)
      return estruturaValida ? tendenciaEstrutura : 0;
   if(!mediasValidas || !estruturaValida || tendenciaMedias==0 || tendenciaEstrutura==0)
      return 0;
   return tendenciaMedias==tendenciaEstrutura ? tendenciaMedias : 0;
  }

//--- Estatisticas da conta e limites diarios
void AtualizarEstatisticas()
  {
   datetime agora=TimeCurrent();
   datetime inicioDia=InicioDoDia(agora);
   MqlDateTime partes;
   TimeToStruct(agora,partes);
   partes.min=0;
   partes.sec=0;
   datetime inicioHora=StructToTime(partes);
   operacoesHoje=0;
   operacoesNaHora=0;
   perdasConsecutivas=0;
   resultadoDiario=0.0;
   ultimaSaida=0;
   ultimaSaidaComPerda=0;
   if(!HistorySelect(inicioDia,agora)) return;
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
     {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0) continue;
      if(HistoryDealGetString(ticket,DEAL_SYMBOL)!=simbolo) continue;
      if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=MagicNumber) continue;
      ENUM_DEAL_ENTRY entrada=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      datetime horario=(datetime)HistoryDealGetInteger(ticket,DEAL_TIME);
      if(entrada==DEAL_ENTRY_IN || entrada==DEAL_ENTRY_INOUT)
        {
         operacoesHoje++;
         if(horario>=inicioHora) operacoesNaHora++;
        }
      if(entrada==DEAL_ENTRY_OUT || entrada==DEAL_ENTRY_OUT_BY || entrada==DEAL_ENTRY_INOUT)
        {
         double resultado=HistoryDealGetDouble(ticket,DEAL_PROFIT)+HistoryDealGetDouble(ticket,DEAL_SWAP)+HistoryDealGetDouble(ticket,DEAL_COMMISSION);
         resultadoDiario+=resultado;
         if(horario>ultimaSaida) ultimaSaida=horario;
         if(resultado<0.0 && horario>ultimaSaidaComPerda) ultimaSaidaComPerda=horario;
        }
     }
   for(int i=total-1;i>=0;i--)
     {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0 || HistoryDealGetString(ticket,DEAL_SYMBOL)!=simbolo || (ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=MagicNumber)
         continue;
      ENUM_DEAL_ENTRY entrada=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(entrada!=DEAL_ENTRY_OUT && entrada!=DEAL_ENTRY_OUT_BY && entrada!=DEAL_ENTRY_INOUT)
         continue;
      double resultado=HistoryDealGetDouble(ticket,DEAL_PROFIT)+HistoryDealGetDouble(ticket,DEAL_SWAP)+HistoryDealGetDouble(ticket,DEAL_COMMISSION);
      if(resultado<0.0) perdasConsecutivas++;
      else if(resultado>0.0) break;
     }
  }

int ContarPosicoesDoRobo()
  {
   int total=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)==simbolo && (ulong)PositionGetInteger(POSITION_MAGIC)==MagicNumber)
         total++;
     }
   return total;
  }

bool HaPosicaoDoRobo()
  {
   return ContarPosicoesDoRobo()>0;
  }

//--- Filtros de horario, noticia, spread e risco
bool BloqueadoPorNoticia(const datetime agora)
  {
   if(!AtivarFiltroDeNoticiaManual) return false;
   string horarios[3]={HorarioNoticia1,HorarioNoticia2,HorarioNoticia3};
   for(int i=0;i<3;i++)
     {
      if(StringLen(horarios[i])<5) continue;
      datetime noticia=StringToTime(horarios[i]);
      if(noticia<=0) continue;
      if(agora>=noticia-MinutosAntesDaNoticia*60 && agora<=noticia+MinutosDepoisDaNoticia*60)
         return true;
     }
   return false;
  }

bool FiltrosOperacionais(string &motivo)
  {
   datetime agora=TimeCurrent();
   MqlDateTime partes;
   TimeToStruct(agora,partes);
   int minutoAtual=partes.hour*60+partes.min;
   if(BloquearSextaFeira && partes.day_of_week==5)
     { motivo="Sexta-feira bloqueada"; return false; }
   if(BloquearRollover && EstaNoIntervalo(minutoAtual,MinutosDoHorario(InicioRollover),MinutosDoHorario(FimRollover)))
     { motivo="Horario de rollover"; return false; }
   if(PermitirApenasHorarioConfigurado && !EstaNoIntervalo(minutoAtual,MinutosDoHorario(HorarioInicialOperacao),MinutosDoHorario(HorarioFinalOperacao)))
     { motivo="Fora do horario operacional"; return false; }
   if((AtivarSessao1 || AtivarSessao2 || AtivarSessao3) &&
      !EstaNaSessao(agora,AtivarSessao1,InicioSessao1,FimSessao1) &&
      !EstaNaSessao(agora,AtivarSessao2,InicioSessao2,FimSessao2) &&
      !EstaNaSessao(agora,AtivarSessao3,InicioSessao3,FimSessao3))
     { motivo="Fora das sessoes configuradas"; return false; }
   if(BloqueadoPorNoticia(agora))
     { motivo="Janela de noticia manual"; return false; }
   MqlTick tick;
   if(!SymbolInfoTick(simbolo,tick))
     { motivo="Sem cotacao atual"; return false; }
   double spread=(tick.ask-tick.bid)/ponto;
   if(SpreadMaximoEmPontos>0.0 && spread>SpreadMaximoEmPontos)
     { motivo=StringFormat("Spread alto: %.1f",spread); return false; }
   AtualizarEstatisticas();
   if(MaximoDeOperacoesPorDia>0 && operacoesHoje>=MaximoDeOperacoesPorDia)
     { motivo="Limite diario de operacoes"; return false; }
   if(MaximoDeOperacoesPorHora>0 && operacoesNaHora>=MaximoDeOperacoesPorHora)
     { motivo="Limite horario de operacoes"; return false; }
   if(MaximoDeOperacoesAbertas>0 && ContarPosicoesDoRobo()>=MaximoDeOperacoesAbertas)
     { motivo="Limite de posicoes abertas"; return false; }
   if(MaximoDePerdasConsecutivas>0 && perdasConsecutivas>=MaximoDePerdasConsecutivas)
     { motivo="Limite de perdas consecutivas"; return false; }
   double saldoInicio=AccountInfoDouble(ACCOUNT_BALANCE)-resultadoDiario;
   if(PerdaMaximaDiariaPercentual>0.0 && saldoInicio>0.0 && resultadoDiario<=-saldoInicio*PerdaMaximaDiariaPercentual/100.0)
     { motivo="Perda maxima diaria atingida"; return false; }
   if(LucroMaximoDiario>0.0 && resultadoDiario>=LucroMaximoDiario)
     { motivo="Lucro maximo diario atingido"; return false; }
   if(MinutosDeCooldownAposOperacao>0 && ultimaSaida>0 && agora<ultimaSaida+MinutosDeCooldownAposOperacao*60)
     { motivo="Cooldown apos operacao"; return false; }
   if(PausaAposStop && MinutosDeCooldownAposOperacao>0 && ultimaSaidaComPerda>0 && agora<ultimaSaidaComPerda+MinutosDeCooldownAposOperacao*60)
     { motivo="Pausa apos stop"; return false; }
   return true;
  }

bool FiltroATRDoCanal(const double altura,string &motivo)
  {
   if(!LerBufferFechado(handleATR,1,atrAtual))
     { motivo="ATR indisponivel"; return false; }
   if(!AtivarFiltroATR) return true;
   double atrPontos=atrAtual/ponto;
   if(atrPontos<ATRMinimoEmPontos || atrPontos>ATRMaximoEmPontos)
     { motivo=StringFormat("ATR fora da faixa: %.1f pontos",atrPontos); return false; }
   if(UsarFiltroDeTamanhoDoCanal)
     {
      if(altura<atrAtual*TamanhoMinimoDoCanalSobreATR || altura>atrAtual*TamanhoMaximoDoCanalSobreATR)
        { motivo="Altura do canal fora da faixa sobre ATR"; return false; }
     }
   return true;
  }

//--- Desenho do canal sem alterar objetos historicos
void CriarLinhaCanal(const string nome,const datetime inicio,const datetime fim,const double preco,const color cor,const ENUM_LINE_STYLE estilo)
  {
   if(ObjectFind(0,nome)<0)
      ObjectCreate(0,nome,OBJ_TREND,0,inicio,preco,fim,preco);
   ObjectSetInteger(0,nome,OBJPROP_TIME,0,inicio);
   ObjectSetDouble(0,nome,OBJPROP_PRICE,0,preco);
   ObjectSetInteger(0,nome,OBJPROP_TIME,1,fim);
   ObjectSetDouble(0,nome,OBJPROP_PRICE,1,preco);
   ObjectSetInteger(0,nome,OBJPROP_COLOR,cor);
   ObjectSetInteger(0,nome,OBJPROP_STYLE,estilo);
   ObjectSetInteger(0,nome,OBJPROP_RAY_RIGHT,false);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,false);
  }

void AtualizarLinhaPosicao(const string nome,const double preco,const color cor)
  {
   if(preco<=0.0)
     {
      ObjectDelete(0,nome);
      return;
     }
   if(ObjectFind(0,nome)<0) ObjectCreate(0,nome,OBJ_HLINE,0,0,preco);
   ObjectSetDouble(0,nome,OBJPROP_PRICE,preco);
   ObjectSetInteger(0,nome,OBJPROP_COLOR,cor);
   ObjectSetInteger(0,nome,OBJPROP_STYLE,STYLE_DASHDOT);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,false);
  }

void DesenharMarcacaoEntrada(const ulong identificador,const int direcao,const datetime horario,const double entrada,const double stop,const double take,const double lote,const string origem)
  {
   if(!DestacarEntradasNoGrafico) return;
   string base=StringFormat("EACP_ENTRADA_%I64u_",identificador);
   color corEntrada=direcao>0 ? clrLimeGreen : clrOrangeRed;
   string seta=base+"SETA";
   ENUM_OBJECT tipoSeta=direcao>0 ? OBJ_ARROW_BUY : OBJ_ARROW_SELL;
   if(ObjectCreate(0,seta,tipoSeta,0,horario,entrada))
     {
      ObjectSetInteger(0,seta,OBJPROP_COLOR,corEntrada);
      ObjectSetInteger(0,seta,OBJPROP_WIDTH,MathMax(1,TamanhoDaSetaDeEntrada));
      ObjectSetInteger(0,seta,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(0,seta,OBJPROP_BACK,false);
      ObjectSetString(0,seta,OBJPROP_TOOLTIP,StringFormat("%s %s | lote %.2f | entrada %.*f | SL %.*f | TP %.*f",
                      origem,direcao>0 ? "COMPRA" : "VENDA",lote,digitos,entrada,digitos,stop,digitos,take));
     }
   string rotulo=base+"ROTULO";
   double deslocamento=MathMax(canal.altura*0.12,20.0*ponto);
   double precoRotulo=entrada+(direcao>0 ? -deslocamento : deslocamento);
   if(ObjectCreate(0,rotulo,OBJ_TEXT,0,horario,precoRotulo))
     {
      ObjectSetString(0,rotulo,OBJPROP_TEXT,StringFormat("%s %s %.2f @ %.*f",direcao>0 ? "▲ COMPRA" : "▼ VENDA",origem,lote,digitos,entrada));
      ObjectSetInteger(0,rotulo,OBJPROP_COLOR,corEntrada);
      ObjectSetInteger(0,rotulo,OBJPROP_FONTSIZE,10);
      ObjectSetInteger(0,rotulo,OBJPROP_ANCHOR,direcao>0 ? ANCHOR_UPPER : ANCHOR_LOWER);
      ObjectSetInteger(0,rotulo,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(0,rotulo,OBJPROP_BACK,false);
     }
   ChartRedraw(0);
  }

void LimparLinhasDeCanaisAnteriores()
  {
   if(!MostrarSomenteCanalAtual) return;
   for(int i=ObjectsTotal(0)-1;i>=0;i--)
     {
      string nome=ObjectName(0,i);
      if(StringFind(nome,"EACP_")!=0) continue;
      if(StringFind(nome,"EACP_ENTRADA_")==0 || StringFind(nome,"EACP_UI_")==0) continue;
      if(nome=="EACP_Stop_Atual" || nome=="EACP_Take_Atual") continue;
      ObjectDelete(0,nome);
     }
  }

void CriarRotuloCanal(const string nome,const datetime horario,const double preco,const string texto,const color cor,const ENUM_ANCHOR_POINT ancora)
  {
   if(ObjectFind(0,nome)<0) ObjectCreate(0,nome,OBJ_TEXT,0,horario,preco);
   ObjectMove(0,nome,0,horario,preco);
   ObjectSetString(0,nome,OBJPROP_TEXT,texto);
   ObjectSetInteger(0,nome,OBJPROP_COLOR,cor);
   ObjectSetInteger(0,nome,OBJPROP_FONTSIZE,10);
   ObjectSetInteger(0,nome,OBJPROP_ANCHOR,ancora);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,nome,OBJPROP_BACK,false);
  }

void DesenharCanal()
  {
   if(!DesenharCanalNoGrafico || !canal.ativo) return;
   LimparLinhasDeCanaisAnteriores();
   datetime fim=canal.expiracao>canal.inicio ? canal.expiracao : canal.inicio+PeriodSeconds(PeriodoDoGrafico)*MaximoDeVelasDeValidadeDoCanal;
   string base=StringFormat("EACP_%I64d_",canal.identificador);
   CriarLinhaCanal(base+"Superior",canal.inicio,fim,canal.superior,clrLime,STYLE_SOLID);
   CriarLinhaCanal(base+"Inferior",canal.inicio,fim,canal.inferior,clrTomato,STYLE_SOLID);
   ObjectSetInteger(0,base+"Superior",OBJPROP_WIDTH,3);
   ObjectSetInteger(0,base+"Inferior",OBJPROP_WIDTH,3);
   double tamanhoParte=(expansaoCanalCurtoRealizada ? canal.altura/2.0 : canal.altura)/ponto;
   string tamanho=expansaoCanalCurtoRealizada
                  ? StringFormat("cada canal %.1f pts | total %.1f pts",tamanhoParte,canal.altura/ponto)
                  : StringFormat("canal %.1f pts",canal.altura/ponto);
   CriarRotuloCanal(base+"RotuloSuperior",fim,canal.superior,"MAXIMA | COMPRA acima | "+tamanho,clrLime,ANCHOR_LEFT_LOWER);
   CriarRotuloCanal(base+"RotuloInferior",fim,canal.inferior,"MINIMA | VENDA abaixo | "+tamanho,clrTomato,ANCHOR_LEFT_UPPER);
   ChartRedraw(0);
  }

//--- Formacao do canal por horario usando apenas candles fechados
datetime AncoraCanalHorario(const datetime agora)
  {
   MqlDateTime partes;
   TimeToStruct(agora,partes);
   partes.sec=0;
   if(RenovacaoDoCanal==RENOVAR_A_CADA_HORA && UsarInicioDeCadaHora)
     {
      partes.min=0;
      return StructToTime(partes);
     }
   if(RenovacaoDoCanal==RENOVAR_POR_SESSAO)
     {
      string inicios[3]={InicioSessao1,InicioSessao2,InicioSessao3};
      bool ativas[3]={AtivarSessao1,AtivarSessao2,AtivarSessao3};
      datetime melhor=0;
      datetime dia=InicioDoDia(agora);
      for(int i=0;i<3;i++)
        {
         if(!ativas[i]) continue;
         int minutos=MinutosDoHorario(inicios[i]);
         if(minutos<0) continue;
         datetime candidato=dia+minutos*60;
         if(candidato>agora) candidato-=86400;
         if(candidato>melhor) melhor=candidato;
        }
      return melhor;
     }
   partes.hour=MathMax(0,MathMin(23,HoraInicialManual));
   partes.min=MathMax(0,MathMin(59,MinutoInicialManual));
   datetime ancora=StructToTime(partes);
   if(ancora>agora) ancora-=86400;
   return ancora;
  }

bool FormarCanalHorario()
  {
   if(ModoDeFormacaoDoCanal==CANAL_AUTOMATICO_PULLBACK) return false;
   if(ModoDeFormacaoDoCanal==CANAL_HORARIO_E_PULLBACK && canal.ativo && canal.automatico) return false;
   datetime agora=TimeCurrent();
   datetime ancora=AncoraCanalHorario(agora);
   if(ancora<=0 || ancora==ultimoInicioCanalHorario) return false;
   int segundos=PeriodSeconds(PeriodoDoGrafico);
   if(segundos<=0 || agora<ancora+VelasParaFormarCanal*segundos) return false;
   MqlRates taxas[];
   ArraySetAsSeries(taxas,false);
   int copiados=CopyRates(simbolo,PeriodoDoGrafico,ancora,ancora+VelasParaFormarCanal*segundos-1,taxas);
   if(copiados<VelasParaFormarCanal) return false;
   double superior=-DBL_MAX,inferior=DBL_MAX;
   for(int i=0;i<VelasParaFormarCanal;i++)
     {
      double alto=taxas[i].high;
      double baixo=taxas[i].low;
      double corpoAlto=MathMax(taxas[i].open,taxas[i].close);
      double corpoBaixo=MathMin(taxas[i].open,taxas[i].close);
      if(MetodoDeCalculoDoCanalHorario==CANAL_ABERTURA_FECHAMENTO || MetodoDeCalculoDoCanalHorario==CANAL_CORPO_SEM_PAVIOS)
        { alto=corpoAlto; baixo=corpoBaixo; }
      else if(MetodoDeCalculoDoCanalHorario==CANAL_HIBRIDO)
        {
         double corpo=MathMax(ponto,corpoAlto-corpoBaixo);
         if(taxas[i].high-corpoAlto>corpo*MultiplicadorMaximoPavioHibrido) alto=corpoAlto;
         if(corpoBaixo-taxas[i].low>corpo*MultiplicadorMaximoPavioHibrido) baixo=corpoBaixo;
        }
      superior=MathMax(superior,alto);
      inferior=MathMin(inferior,baixo);
     }
   double altura=superior-inferior;
   string motivo="";
   if(altura<=0.0 || altura/ponto<DistanciaMinimaDoCanal || altura/ponto>DistanciaMaximaDoCanal)
     { motivoBloqueio="Canal horario fora do tamanho permitido"; return false; }
   if(!FiltroATRDoCanal(altura,motivo))
     { motivoBloqueio=motivo; return false; }
   canal.ativo=true;
   canal.automatico=false;
   canal.direcao=0;
   canal.inicio=ancora;
   canal.formadoEm=taxas[VelasParaFormarCanal-1].time+segundos;
   canal.expiracao=(RenovacaoDoCanal==RENOVAR_A_CADA_HORA ? ancora+3600 : ancora+86400);
   canal.superior=NormalizarPreco(superior);
   canal.inferior=NormalizarPreco(inferior);
   canal.altura=canal.superior-canal.inferior;
   canal.atr=atrAtual;
   canal.extremoPullback=0.0;
   canal.estruturaProtegida=0.0;
   canal.operado=false;
   canal.identificador=(long)ancora;
   expansaoCanalCurtoRealizada=false;
   ultimoInicioCanalHorario=ancora;
   confirmacoesRompimento=0;
   aguardandoReteste=false;
   estadoAutomatico=CANAL_FORMADO;
   Log(StringFormat("Canal horario formado: superior=%.5f inferior=%.5f altura=%.1f pontos ATR=%.1f",canal.superior,canal.inferior,canal.altura/ponto,canal.atr/ponto));
   DesenharCanal();
   SalvarEstado();
   return true;
  }

//--- Pullback: velas contrarias geram somente candidato, nunca um canal isoladamente
bool VelaNeutra(const MqlRates &vela)
  {
   return MathAbs(vela.close-vela.open)<=ponto;
  }

bool VelaCorretiva(const int direcao,const MqlRates &atual,const MqlRates &anterior)
  {
   bool corpoContra=(direcao>0 ? atual.close<atual.open : atual.close>atual.open);
   bool estruturaCurta=(direcao>0 ? (atual.high<anterior.high || atual.low<anterior.low) : (atual.high>anterior.high || atual.low>anterior.low));
   if(ExigirFechamentosContraTendencia) return corpoContra;
   if(UsarPavioNaIdentificacaoDoPullback) return corpoContra || estruturaCurta;
   return corpoContra || (direcao>0 ? atual.close<anterior.close : atual.close>anterior.close);
  }

void CancelarPullback(const string motivo)
  {
   Log("Pullback/canal automatico invalidado: "+motivo);
   motivoBloqueio=motivo;
   pullback.candidato=false;
   if(canal.automatico) canal.ativo=false;
   estadoAutomatico=CANAL_INVALIDADO;
   confirmacoesRompimento=0;
   aguardandoReteste=false;
   SalvarEstado();
  }

void IniciarCandidatoPullback(const int direcao,const double estruturaProtegida,const MqlRates &vela)
  {
   pullback.candidato=true;
   pullback.direcao=direcao;
   pullback.inicio=vela.time;
   pullback.velas=1;
   pullback.neutras=0;
   pullback.primeiraAbertura=vela.open;
   pullback.primeiraFechamento=vela.close;
   pullback.primeiraMaxima=vela.high;
   pullback.primeiraMinima=vela.low;
   pullback.extremoMinimo=vela.low;
   pullback.extremoMaximo=vela.high;
   pullback.estruturaProtegida=estruturaProtegida;
   estadoAutomatico=PULLBACK_IDENTIFICADO;
   Log(StringFormat("Candidato a pullback iniciado. Direcao=%s, ancora=%s, estrutura protegida=%.5f",direcao>0 ? "alta" : "baixa",TimeToString(vela.time),estruturaProtegida));
   SalvarEstado();
  }

bool FormarCanalDoPullback(const MqlRates &ultimaVela)
  {
   double atrMedio=CalcularATRMedio(pullback.inicio);
   double tamanho=atrMedio*MultiplicadorDoATR;
   if(atrMedio<=0.0 || tamanho<=0.0)
     { CancelarPullback("ATR medio indisponivel"); return false; }
   string motivo="";
   if(!FiltroATRDoCanal(tamanho,motivo))
     { CancelarPullback(motivo); return false; }
   double superior=0.0,inferior=0.0;
   if(ModoDePosicionamentoDoCanal==POSICAO_CENTRALIZADA_PRIMEIRA_VELA)
     {
      double centro=(pullback.primeiraAbertura+pullback.primeiraFechamento)/2.0;
      inferior=centro-tamanho/2.0;
      superior=centro+tamanho/2.0;
     }
   else if(pullback.direcao>0)
     {
      if(ModoDePosicionamentoDoCanal==POSICAO_EXTREMO_PULLBACK) inferior=pullback.extremoMinimo;
      else if(ModoDePosicionamentoDoCanal==POSICAO_FECHAMENTO_PRIMEIRA_VELA) inferior=pullback.primeiraFechamento;
      else inferior=pullback.primeiraMinima;
      superior=inferior+tamanho;
     }
   else
     {
      if(ModoDePosicionamentoDoCanal==POSICAO_EXTREMO_PULLBACK) superior=pullback.extremoMaximo;
      else if(ModoDePosicionamentoDoCanal==POSICAO_FECHAMENTO_PRIMEIRA_VELA) superior=pullback.primeiraFechamento;
      else superior=pullback.primeiraMaxima;
      inferior=superior-tamanho;
     }
   canal.ativo=true;
   canal.automatico=true;
   canal.direcao=pullback.direcao;
   canal.inicio=pullback.inicio;
   canal.formadoEm=ultimaVela.time+PeriodSeconds(PeriodoDoGrafico);
   canal.expiracao=canal.formadoEm+MaximoDeVelasDeValidadeDoCanal*PeriodSeconds(PeriodoDoGrafico);
   canal.superior=NormalizarPreco(superior);
   canal.inferior=NormalizarPreco(inferior);
   canal.altura=canal.superior-canal.inferior;
   canal.atr=atrMedio;
   canal.extremoPullback=pullback.direcao>0 ? pullback.extremoMinimo : pullback.extremoMaximo;
   canal.estruturaProtegida=pullback.estruturaProtegida;
   canal.operado=false;
   canal.identificador=(long)pullback.inicio;
   expansaoCanalCurtoRealizada=false;
   pullback.candidato=false;
   estadoAutomatico=CANAL_FORMADO;
   Log(StringFormat("Canal de pullback formado sem repaint. Inicio=%s, velas=%d, ATR medio=%.1f pontos, tamanho=%.1f pontos, direcao=%s",TimeToString(canal.inicio),pullback.velas,atrMedio/ponto,canal.altura/ponto,canal.direcao>0 ? "alta" : "baixa"));
   DesenharCanal();
   SalvarEstado();
   return true;
  }

void ProcessarPullback(const MqlRates &taxas[])
  {
   if(!AtivarCanalAutomaticoPullback || ModoDeFormacaoDoCanal==CANAL_POR_HORARIO) return;
   if(HaPosicaoDoRobo()) return;
   if(canal.ativo && (canal.automatico || ModoDeFormacaoDoCanal!=CANAL_HORARIO_E_PULLBACK)) return;
   double protegida=0.0;
   int tendencia=IdentificarTendencia(protegida);
   tendenciaAtual=tendencia;
   if(!pullback.candidato)
     {
      if(tendencia==0 && ExigirTendenciaDefinida)
        { estadoAutomatico=SEM_TENDENCIA; motivoBloqueio="Sem tendencia definida"; return; }
      int direcao=tendencia;
      if(direcao==0 || (!PermitirPullbackContraTendencia && direcao!=tendencia)) return;
      if(VelaCorretiva(direcao,taxas[1],taxas[2]))
         IniciarCandidatoPullback(direcao,protegida,taxas[1]);
      return;
     }
   if(CancelarSeRomperEstrutura && pullback.estruturaProtegida>0.0)
     {
      bool rompeu=(pullback.direcao>0 ? taxas[1].low<pullback.estruturaProtegida : taxas[1].high>pullback.estruturaProtegida);
      if(rompeu)
        { CancelarPullback("Correcao rompeu a estrutura principal protegida"); return; }
     }
   if(ExigirTendenciaDefinida && tendencia!=pullback.direcao)
     { CancelarPullback("Tendencia deixou de estar definida durante a correcao"); return; }
   bool corretiva=VelaCorretiva(pullback.direcao,taxas[1],taxas[2]);
   bool neutra=PermitirVelasNeutras && VelaNeutra(taxas[1]);
   if(corretiva || neutra)
     {
      pullback.velas++;
      if(neutra) pullback.neutras++;
      pullback.extremoMinimo=MathMin(pullback.extremoMinimo,taxas[1].low);
      pullback.extremoMaximo=MathMax(pullback.extremoMaximo,taxas[1].high);
      if(pullback.neutras>MaximoDeVelasNeutras)
        { CancelarPullback("Excesso de velas neutras"); return; }
      if(pullback.velas>MaximoDeVelasDoPullback)
        { CancelarPullback("Pullback excedeu o numero maximo de velas"); return; }
      if(pullback.velas>=MinimoDeVelasDoPullback)
         FormarCanalDoPullback(taxas[1]);
      else
         SalvarEstado();
      return;
     }
   CancelarPullback("Sequencia corretiva terminou antes da formacao valida");
  }

//--- Invalida canal automatico sem jamais reposiciona-lo retroativamente
bool ValidarCanalAutomatico(const MqlRates &vela)
  {
   if(!canal.ativo || !canal.automatico) return true;
   if(TimeCurrent()>canal.expiracao)
     { CancelarPullback("Validade maxima do canal encerrada"); return false; }
   if(expansaoCanalCurtoRealizada) return true;
   if(CancelarSeRomperEstrutura && canal.estruturaProtegida>0.0)
     {
      bool rompeu=(canal.direcao>0 ? vela.low<canal.estruturaProtegida : vela.high>canal.estruturaProtegida);
      if(rompeu)
        { CancelarPullback("Preco rompeu a estrutura principal"); return false; }
     }
   if(vela.time>canal.formadoEm)
     {
      bool atingiuOposto=(canal.direcao>0 ? vela.close<canal.inferior : vela.close>canal.superior);
      if(atingiuOposto)
        { CancelarPullback("Preco atingiu o limite oposto antes do rompimento"); return false; }
     }
   double protegida=0.0;
   int tendencia=IdentificarTendencia(protegida);
   tendenciaAtual=tendencia;
   if(ExigirTendenciaDefinida && tendencia!=canal.direcao)
     { CancelarPullback("Tendencia invalida antes do rompimento"); return false; }
   return true;
  }

//--- Calculo de stop, take e lote
double MultiplicadorTakeSelecionado()
  {
   if(ModoDoTakeProfit==TAKE_MEIO_CANAL) return 0.5;
   if(ModoDoTakeProfit==TAKE_UM_CANAL) return 1.0;
   if(ModoDoTakeProfit==TAKE_UM_DOIS_CANAL) return 1.2;
   if(ModoDoTakeProfit==TAKE_UM_MEIO_CANAL) return 1.5;
   if(ModoDoTakeProfit==TAKE_DOIS_CANAIS) return 2.0;
   return MultiplicadorDoTakeProfit;
  }

double CalcularTake(const int direcao,const double entrada)
  {
   if(ModoDoTakeProfit==TAKE_FIXO_PONTOS)
      return NormalizarPreco(entrada+direcao*TakeProfitEmPontos*ponto);
   double multiplicador=MultiplicadorTakeSelecionado();
   return NormalizarPreco(direcao>0 ? canal.superior+canal.altura*multiplicador : canal.inferior-canal.altura*multiplicador);
  }

double CalcularStop(const int direcao,const double entrada)
  {
   double stop=0.0;
   if(ModoDoStopLoss==STOP_FIXO_PONTOS)
      stop=entrada-direcao*StopFixoEmPontos*ponto;
   else if(ModoDoStopLoss==STOP_LIMITE_OPOSTO)
      stop=direcao>0 ? canal.inferior : canal.superior;
   else if(ModoDoStopLoss==STOP_ALEM_LIMITE_OPOSTO)
      stop=direcao>0 ? canal.inferior-OffsetDoStopEmPontos*ponto : canal.superior+OffsetDoStopEmPontos*ponto;
   else if(ModoDoStopLoss==STOP_UM_CANAL)
      stop=entrada-direcao*canal.altura;
   else if(ModoDoStopLoss==STOP_UM_DOIS_CANAL)
      stop=entrada-direcao*canal.altura*1.2;
   else if(ModoDoStopLoss==STOP_MULTIPLICADOR)
      stop=entrada-direcao*canal.altura*MultiplicadorDoStop;
   else if(ModoDoStopLoss==STOP_ATR)
      stop=entrada-direcao*atrAtual*MultiplicadorStopATR;
   else
      stop=direcao>0 ? canal.extremoPullback-OffsetDoStopEmPontos*ponto : canal.extremoPullback+OffsetDoStopEmPontos*ponto;
   return NormalizarPreco(stop);
  }

bool AjustarStopsDaCorretora(const int direcao,const double entrada,double &stop,double &take)
  {
   double distanciaMinima=(double)MathMax((long)SymbolInfoInteger(simbolo,SYMBOL_TRADE_STOPS_LEVEL),(long)SymbolInfoInteger(simbolo,SYMBOL_TRADE_FREEZE_LEVEL))*ponto;
   if(direcao>0)
     {
      if(stop>=entrada-distanciaMinima) stop=entrada-distanciaMinima;
      if(take<=entrada+distanciaMinima) return false;
     }
   else
     {
      if(stop<=entrada+distanciaMinima) stop=entrada+distanciaMinima;
      if(take>=entrada-distanciaMinima) return false;
     }
   stop=NormalizarPreco(stop);
   take=NormalizarPreco(take);
   return stop>0.0 && take>0.0;
  }

double CalcularLote(const int direcao,const double entrada,const double stop)
  {
   if(ModoDeCalculoDoLote==LOTE_FIXO)
      return NormalizarVolume(LoteFixo);
   double risco=RiscoMonetario;
   if(ModoDeCalculoDoLote==LOTE_POR_PERCENTUAL)
      risco=AccountInfoDouble(ACCOUNT_EQUITY)*PercentualDeRisco/100.0;
   double perdaUmLote=0.0;
   ENUM_ORDER_TYPE tipo=direcao>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(risco<=0.0 || !OrderCalcProfit(tipo,simbolo,1.0,entrada,stop,perdaUmLote) || perdaUmLote==0.0)
      return 0.0;
   double volume=NormalizarVolume(risco/MathAbs(perdaUmLote));
   Log(StringFormat("Calculo de lote: risco=%.2f, perda por 1 lote=%.2f, volume=%.4f",risco,MathAbs(perdaUmLote),volume));
   return volume;
  }

//--- Envio seguro da ordem
bool AbrirOperacao(const int direcao)
  {
   string motivo="";
   if(!FiltrosOperacionais(motivo))
     { motivoBloqueio=motivo; Log("Entrada bloqueada: "+motivo); return false; }
   if(canal.operado && !(canal.automatico ? PermitirNovaEntradaNoMesmoPullback : PermitirNovaEntradaNoMesmoCanal))
     { motivoBloqueio="Canal ja operado"; return false; }
   if(ultimaBarraEntrada==ultimaBarra)
     { motivoBloqueio="Ja houve entrada neste candle"; return false; }
   if((direcao>0 && !PermitirCompras) || (direcao<0 && !PermitirVendas))
     { motivoBloqueio="Direcao desabilitada"; return false; }
   MqlTick tick;
   if(!SymbolInfoTick(simbolo,tick)) return false;
   double entrada=direcao>0 ? tick.ask : tick.bid;
   double stop=CalcularStop(direcao,entrada);
   double take=CalcularTake(direcao,entrada);
   if(!AjustarStopsDaCorretora(direcao,entrada,stop,take))
     { motivoBloqueio="Stop ou take invalido para o preco atual"; return false; }
   double lote=CalcularLote(direcao,entrada,stop);
   if(lote<=0.0)
     { motivoBloqueio="Lote calculado invalido"; return false; }
   negociacao.SetExpertMagicNumber(MagicNumber);
   negociacao.SetDeviationInPoints(SlippageMaximo);
   negociacao.SetTypeFillingBySymbol(simbolo);
   double takeCorretora=UsarMultiplosAlvos ? 0.0 : take;
   string origem=canal.automatico ? "AUTO" : "HORA";
   string comentario=StringFormat("EACP %s %s",origem,direcao>0 ? "BUY" : "SELL");
   bool enviado=direcao>0
                ? negociacao.Buy(lote,simbolo,0.0,stop,takeCorretora,comentario)
                : negociacao.Sell(lote,simbolo,0.0,stop,takeCorretora,comentario);
   if(!enviado)
     {
      motivoBloqueio=StringFormat("Erro da corretora %u: %s",negociacao.ResultRetcode(),negociacao.ResultRetcodeDescription());
      Log(motivoBloqueio);
      return false;
     }
   datetime horarioMarcacao=TimeCurrent();
   ulong identificadorMarcacao=negociacao.ResultDeal();
   double precoExecutado=negociacao.ResultPrice();
   if(precoExecutado<=0.0) precoExecutado=entrada;
   if(identificadorMarcacao>0 && HistoryDealSelect(identificadorMarcacao))
      horarioMarcacao=(datetime)HistoryDealGetInteger(identificadorMarcacao,DEAL_TIME);
   if(identificadorMarcacao==0) identificadorMarcacao=(ulong)horarioMarcacao;
   DesenharMarcacaoEntrada(identificadorMarcacao,direcao,horarioMarcacao,precoExecutado,stop,take,lote,origem);
   if(RegistrarCadaEntradaNoDiario)
     {
      datetime horarioEntrada=TimeCurrent();
      ulong negocioEntrada=negociacao.ResultDeal();
      if(negocioEntrada>0 && HistoryDealSelect(negocioEntrada))
         horarioEntrada=(datetime)HistoryDealGetInteger(negocioEntrada,DEAL_TIME);
      MqlDateTime partesHorario;
      TimeToStruct(horarioEntrada,partesHorario);
      PrintFormat("ENTRADA | servidor=%s | faixa=%02d:00-%02d:59 | origem=%s | lado=%s | lote=%.4f | preco=%.5f | stop=%.5f | take=%.5f",
                  TimeToString(horarioEntrada,TIME_DATE|TIME_SECONDS),partesHorario.hour,partesHorario.hour,
                  origem,direcao>0 ? "COMPRA" : "VENDA",lote,entrada,stop,take);
     }
   canal.operado=true;
   pullback.candidato=false;
   ultimaBarraEntrada=ultimaBarra;
   canalPosicaoSuperior=canal.superior;
   canalPosicaoInferior=canal.inferior;
   canalPosicaoAltura=canal.altura;
   canalPosicaoATR=canal.atr;
   volumeInicialPosicao=lote;
   breakevenExecutado=false;
   for(int i=0;i<4;i++) alvoAtingido[i]=false;
   estadoAutomatico=OPERACAO_ABERTA;
   sinalAtual=direcao>0 ? "Compra aberta" : "Venda aberta";
   Log(StringFormat("Operacao aberta: %s lote=%.4f entrada=%.5f stop=%.5f take=%.5f canal=%.1f pontos",direcao>0 ? "COMPRA" : "VENDA",lote,entrada,stop,take,canal.altura/ponto));
   SalvarEstado();
   return true;
  }

//--- Confirmacao de rompimento e reteste em candles fechados
bool VelaDeRompimentoGrande(const MqlRates &vela)
  {
   if(!AtivarFiltroDeVelaGrande) return false;
   double tamanho=vela.high-vela.low;
   if(TamanhoMaximoDaVelaEmPontos>0.0 && tamanho/ponto>TamanhoMaximoDaVelaEmPontos) return true;
   if(UsarATRParaFiltrarVelaGrande && atrAtual>0.0 && tamanho>atrAtual*MultiplicadorMaximoDaVelaSobreATR) return true;
   return false;
  }

bool DeveExigirReteste()
  {
   if(!canal.automatico) return ExigirReteste;
   if(EntradaNoRompimentoOuReteste==ENTRADA_NO_ROMPIMENTO) return false;
   if(EntradaNoRompimentoOuReteste==ENTRADA_NO_RETESTE) return true;
   return ExigirRetesteDoCanalPullback;
  }

int MaximoVelasRetesteAtual()
  {
   return canal.automatico ? VelasMaximasParaRetestePullback : MaximoDeVelasParaReteste;
  }

bool ExpandirCanalCurtoConfirmado(const int direcao,const MqlRates &vela)
  {
   if(!AtivarExpansaoDeCanalCurto || CanalCurtoAbaixoDePontos<=0.0) return false;
   if(expansaoCanalCurtoRealizada) return false;
   double alturaAnterior=canal.altura/ponto;
   if(alturaAnterior>CanalCurtoAbaixoDePontos) return false;
   double tamanhoCanal=canal.altura;
   if(direcao>0)
      canal.superior=NormalizarPreco(canal.superior+tamanhoCanal);
   else
      canal.inferior=NormalizarPreco(canal.inferior-tamanhoCanal);
   canal.altura=canal.superior-canal.inferior;
   if(canal.altura<=0.0) return false;
   expansaoCanalCurtoRealizada=true;
   canal.direcao=0;
   confirmacoesRompimento=0;
   direcaoRompimento=0;
   aguardandoReteste=false;
   velasAguardandoReteste=0;
   sinalAtual=StringFormat("Segundo canal formado: %.1f + %.1f pts",alturaAnterior,alturaAnterior);
   motivoBloqueio="Aguardando rompimento fechado de uma extremidade externa";
   Log(StringFormat("SEGUNDO CANAL | expansao=%s | cada_canal=%.1f pts | total=%.1f pts | topo_externo=%.5f | fundo_externo=%.5f | fechamento_confirmador=%.5f",
                    direcao>0 ? "ACIMA" : "ABAIXO",alturaAnterior,canal.altura/ponto,canal.superior,canal.inferior,vela.close));
   DesenharCanal();
   SalvarEstado();
   return true;
  }

void ProcessarRompimento(const MqlRates &taxas[])
  {
   if(!canal.ativo || HaPosicaoDoRobo()) return;
   if(!ValidarCanalAutomatico(taxas[1])) return;
   if(canal.operado && !(canal.automatico ? PermitirNovaEntradaNoMesmoPullback : PermitirNovaEntradaNoMesmoCanal)) return;
   string motivo="";
   if(!FiltroATRDoCanal(canal.altura,motivo))
     { motivoBloqueio=motivo; return; }
   double tolerancia=(canal.automatico ? ToleranciaRompimentoPullbackEmPontos : ToleranciaDoRompimentoEmPontos)*ponto;
   if(aguardandoReteste)
     {
      velasAguardandoReteste++;
      SalvarEstado();
      bool voltou=(direcaoRompimento>0 ? taxas[1].low<=canal.superior+tolerancia && taxas[1].close>=canal.superior
                                      : taxas[1].high>=canal.inferior-tolerancia && taxas[1].close<=canal.inferior);
      bool fechouDentro=(direcaoRompimento>0 ? taxas[1].close<canal.superior : taxas[1].close>canal.inferior);
      if(fechouDentro)
        { aguardandoReteste=false; confirmacoesRompimento=0; motivoBloqueio="Reteste fechou dentro do canal"; return; }
      if(voltou)
        {
         aguardandoReteste=false;
         sinalAtual=direcaoRompimento>0 ? "Reteste comprador confirmado" : "Reteste vendedor confirmado";
         AbrirOperacao(direcaoRompimento);
         return;
        }
      if(velasAguardandoReteste>MaximoVelasRetesteAtual())
        { aguardandoReteste=false; confirmacoesRompimento=0; motivoBloqueio="Prazo do reteste expirou"; }
      return;
     }
   bool canalCurtoParaExpansao=AtivarExpansaoDeCanalCurto && !expansaoCanalCurtoRealizada && CanalCurtoAbaixoDePontos>0.0 && canal.altura/ponto<=CanalCurtoAbaixoDePontos;
   bool exigirFechamentoAtual=ExigirFechamentoForaDoCanal || canalCurtoParaExpansao || expansaoCanalCurtoRealizada;
   bool rompeuAlta=exigirFechamentoAtual ? taxas[1].close>canal.superior+tolerancia : taxas[1].high>canal.superior+tolerancia;
   bool rompeuBaixa=exigirFechamentoAtual ? taxas[1].close<canal.inferior-tolerancia : taxas[1].low<canal.inferior-tolerancia;
   if(canal.automatico)
     {
      if(canal.direcao>0) rompeuBaixa=false;
      if(canal.direcao<0) rompeuAlta=false;
     }
   int direcao=rompeuAlta ? 1 : (rompeuBaixa ? -1 : 0);
   if(direcao==0)
     { confirmacoesRompimento=0; direcaoRompimento=0; sinalAtual="Aguardando rompimento"; return; }
   if(VelaDeRompimentoGrande(taxas[1]))
     { confirmacoesRompimento=0; motivoBloqueio="Vela de rompimento excessivamente grande"; Log(motivoBloqueio); return; }
   if(canalCurtoParaExpansao && ExpandirCanalCurtoConfirmado(direcao,taxas[1])) return;
   if(direcaoRompimento!=direcao)
     { direcaoRompimento=direcao; confirmacoesRompimento=1; }
   else confirmacoesRompimento++;
   sinalAtual=StringFormat("Rompimento %s (%d/%d)",direcao>0 ? "alta" : "baixa",confirmacoesRompimento,MathMax(1,VelasDeConfirmacao));
   SalvarEstado();
   if(confirmacoesRompimento<MathMax(1,VelasDeConfirmacao)) return;
   estadoAutomatico=ROMPIMENTO_CONFIRMADO;
   if(DeveExigirReteste())
     {
      aguardandoReteste=true;
      velasAguardandoReteste=0;
      Log("Rompimento confirmado; aguardando reteste");
      return;
     }
   AbrirOperacao(direcao);
  }

//--- Gerenciamento de alvos, breakeven e trailing em cada tick
double MultiplicadorAlvo(const int indice)
  {
   if(indice==0) return Alvo1Multiplicador;
   if(indice==1) return Alvo2Multiplicador;
   if(indice==2) return Alvo3Multiplicador;
   return Alvo4Multiplicador;
  }

double PercentualAlvo(const int indice)
  {
   if(indice==0) return PercentualFechamentoAlvo1;
   if(indice==1) return PercentualFechamentoAlvo2;
   if(indice==2) return PercentualFechamentoAlvo3;
   return PercentualFechamentoAlvo4;
  }

bool FecharVolumeDaPosicao(const ulong ticket,const double volume,const bool fecharTudo)
  {
   if(fecharTudo) return negociacao.PositionClose(ticket,SlippageMaximo);
   double minimo=SymbolInfoDouble(simbolo,SYMBOL_VOLUME_MIN);
   double passo=SymbolInfoDouble(simbolo,SYMBOL_VOLUME_STEP);
   double atual=PositionGetDouble(POSITION_VOLUME);
   double fechar=MathFloor((MathMin(volume,atual)+1e-12)/passo)*passo;
   fechar=NormalizeDouble(fechar,DigitosVolume(passo));
   if(fechar<minimo || atual-fechar<minimo) return negociacao.PositionClose(ticket,SlippageMaximo);
   MqlTick tick;
   if(!SymbolInfoTick(simbolo,tick)) return false;
   MqlTradeRequest pedido={};
   MqlTradeResult resultado={};
   ENUM_POSITION_TYPE tipo=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   long modosPreenchimento=SymbolInfoInteger(simbolo,SYMBOL_FILLING_MODE);
   pedido.action=TRADE_ACTION_DEAL;
   pedido.position=ticket;
   pedido.symbol=simbolo;
   pedido.magic=MagicNumber;
   pedido.volume=fechar;
   pedido.deviation=SlippageMaximo;
   pedido.type=(tipo==POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY);
   pedido.price=(tipo==POSITION_TYPE_BUY ? tick.bid : tick.ask);
   if((modosPreenchimento & SYMBOL_FILLING_FOK)==SYMBOL_FILLING_FOK)
      pedido.type_filling=ORDER_FILLING_FOK;
   else if((modosPreenchimento & SYMBOL_FILLING_IOC)==SYMBOL_FILLING_IOC)
      pedido.type_filling=ORDER_FILLING_IOC;
   else
      pedido.type_filling=ORDER_FILLING_RETURN;
   if(!OrderSend(pedido,resultado))
     {
      Log(StringFormat("OrderSend da parcial falhou. Erro=%d",GetLastError()));
      return false;
     }
   bool sucesso=resultado.retcode==TRADE_RETCODE_DONE || resultado.retcode==TRADE_RETCODE_DONE_PARTIAL;
   if(!sucesso) Log(StringFormat("Fechamento parcial recusado. Retcode=%u comentario=%s",resultado.retcode,resultado.comment));
   return sucesso;
  }

void GerenciarMultiplosAlvos(const ulong ticket,const ENUM_POSITION_TYPE tipo,const double precoAtual)
  {
   if(!UsarMultiplosAlvos || canalPosicaoAltura<=0.0) return;
   int quantidade=MathMax(1,MathMin(4,QuantidadeDeAlvos));
   for(int i=0;i<quantidade;i++)
     {
      if(alvoAtingido[i]) continue;
      double nivel=(tipo==POSITION_TYPE_BUY ? canalPosicaoSuperior+canalPosicaoAltura*MultiplicadorAlvo(i)
                                           : canalPosicaoInferior-canalPosicaoAltura*MultiplicadorAlvo(i));
      bool atingiu=(tipo==POSITION_TYPE_BUY ? precoAtual>=nivel : precoAtual<=nivel);
      if(!atingiu) continue;
      bool ultimo=(i==quantidade-1);
      double volume=volumeInicialPosicao*PercentualAlvo(i)/100.0;
      if(FecharVolumeDaPosicao(ticket,volume,ultimo))
        {
         alvoAtingido[i]=true;
         Log(StringFormat("Alvo %d (%.2f canal) atingido",i+1,MultiplicadorAlvo(i)));
         SalvarEstado();
        }
      else Log(StringFormat("Falha ao fechar alvo %d: %s",i+1,negociacao.ResultRetcodeDescription()));
      break;
     }
  }

bool StopMelhora(const ENUM_POSITION_TYPE tipo,const double atual,const double candidato)
  {
   if(tipo==POSITION_TYPE_BUY) return candidato>atual+ponto/2.0;
   return atual==0.0 || candidato<atual-ponto/2.0;
  }

bool StopRespeitaCorretora(const ENUM_POSITION_TYPE tipo,const double stop,const MqlTick &tick)
  {
   double distancia=(double)MathMax((long)SymbolInfoInteger(simbolo,SYMBOL_TRADE_STOPS_LEVEL),(long)SymbolInfoInteger(simbolo,SYMBOL_TRADE_FREEZE_LEVEL))*ponto;
   if(tipo==POSITION_TYPE_BUY) return stop<=tick.bid-distancia;
   return stop>=tick.ask+distancia;
  }

void GerenciarProtecao(const ulong ticket,const ENUM_POSITION_TYPE tipo,const double entrada,const double stopAtual,const double takeAtual,const MqlTick &tick)
  {
   double precoAtual=tipo==POSITION_TYPE_BUY ? tick.bid : tick.ask;
   double lucroDistancia=tipo==POSITION_TYPE_BUY ? precoAtual-entrada : entrada-precoAtual;
   double novoStop=stopAtual;
   if(AtivarBreakeven && !breakevenExecutado)
     {
      bool ativar=false;
      if(ModoDeAtivacaoDoBreakeven==BREAKEVEN_POR_PONTOS) ativar=lucroDistancia>=BreakevenEmPontos*ponto;
      else if(ModoDeAtivacaoDoBreakeven==BREAKEVEN_POR_CANAL) ativar=canalPosicaoAltura>0.0 && lucroDistancia>=canalPosicaoAltura*BreakevenEmMultiploDoCanal;
      else ativar=alvoAtingido[0];
      if(ativar)
        {
         double candidato=entrada+(tipo==POSITION_TYPE_BUY ? 1.0 : -1.0)*LucroExtraNoBreakevenEmPontos*ponto;
         candidato=NormalizarPreco(candidato);
         if(StopMelhora(tipo,stopAtual,candidato) && StopRespeitaCorretora(tipo,candidato,tick))
           {
            novoStop=candidato;
            if(negociacao.PositionModify(ticket,novoStop,takeAtual))
              { breakevenExecutado=true; Log(StringFormat("Breakeven ativado em %.5f",novoStop)); SalvarEstado(); }
           }
        }
     }
   if(!AtivarTrailingStop) return;
   bool iniciar=false;
   if(ModoDoTrailing==TRAILING_FIXO) iniciar=lucroDistancia>=TrailingInicioEmPontos*ponto;
   else if(ModoDoTrailing==TRAILING_POR_CANAL) iniciar=canalPosicaoAltura>0.0 && lucroDistancia>=canalPosicaoAltura*TrailingInicioEmMultiploDoCanal;
   else if(ModoDoTrailing==TRAILING_POR_ATR) iniciar=canalPosicaoATR>0.0 && lucroDistancia>=canalPosicaoATR*MultiplicadorTrailingATR;
   else if(ModoDoTrailing==TRAILING_APOS_ALVO_1) iniciar=alvoAtingido[0];
   else if(ModoDoTrailing==TRAILING_APOS_BREAKEVEN) iniciar=breakevenExecutado;
   if(!iniciar) return;
   double distancia=DistanciaDoTrailingEmPontos*ponto;
   if(TrailingBaseadoNoATR || ModoDoTrailing==TRAILING_POR_ATR)
      distancia=MathMax(ponto,atrAtual*MultiplicadorTrailingATR);
   double candidato=NormalizarPreco(precoAtual+(tipo==POSITION_TYPE_BUY ? -distancia : distancia));
   double referencia=stopAtual;
   if(novoStop!=stopAtual) referencia=novoStop;
   if(!StopMelhora(tipo,referencia,candidato)) return;
   if(referencia>0.0 && MathAbs(candidato-referencia)<PassoDoTrailingEmPontos*ponto) return;
   if(!StopRespeitaCorretora(tipo,candidato,tick)) return;
   if(negociacao.PositionModify(ticket,candidato,takeAtual))
      Log(StringFormat("Trailing moveu stop para %.5f",candidato));
   else Log("Erro no trailing: "+negociacao.ResultRetcodeDescription());
  }

void GerenciarPosicoes()
  {
   MqlTick tick;
   if(!SymbolInfoTick(simbolo,tick)) return;
   bool encontrou=false;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=simbolo || (ulong)PositionGetInteger(POSITION_MAGIC)!=MagicNumber) continue;
      encontrou=true;
      ENUM_POSITION_TYPE tipo=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double entrada=PositionGetDouble(POSITION_PRICE_OPEN);
      double stop=PositionGetDouble(POSITION_SL);
      double take=PositionGetDouble(POSITION_TP);
      AtualizarLinhaPosicao("EACP_Stop_Atual",stop,clrOrangeRed);
      AtualizarLinhaPosicao("EACP_Take_Atual",take,clrDodgerBlue);
      double precoAtual=tipo==POSITION_TYPE_BUY ? tick.bid : tick.ask;
      GerenciarMultiplosAlvos(ticket,tipo,precoAtual);
      if(PositionSelectByTicket(ticket))
         GerenciarProtecao(ticket,tipo,entrada,PositionGetDouble(POSITION_SL),PositionGetDouble(POSITION_TP),tick);
     }
   if(!encontrou)
     {
      AtualizarLinhaPosicao("EACP_Stop_Atual",0.0,clrOrangeRed);
      AtualizarLinhaPosicao("EACP_Take_Atual",0.0,clrDodgerBlue);
     }
  }

//--- Dashboard grafico moderno em portugues
#define COR_PAINEL_FUNDO       C'12,18,30'
#define COR_PAINEL_CARTAO      C'20,29,46'
#define COR_PAINEL_CARTAO_2    C'24,35,54'
#define COR_PAINEL_BORDA       C'43,57,78'
#define COR_PAINEL_TEXTO       C'230,237,247'
#define COR_PAINEL_MUTED       C'132,148,170'
#define COR_PAINEL_DESTAQUE    C'46,211,183'
#define COR_PAINEL_AZUL        C'72,149,239'
#define COR_PAINEL_OURO        C'245,183,66'
#define COR_PAINEL_VERDE       C'54,211,153'
#define COR_PAINEL_VERMELHO    C'248,113,113'
#define COR_PAINEL_LARANJA     C'251,146,60'

int PainelPX(const int valor)
  {
   return (int)MathRound(valor*MathMax(0.70,MathMin(1.60,EscalaDoPainel)));
  }

string NomePainel(const string sufixo)
  {
   return prefixoPainel+sufixo;
  }

void ApagarPainel()
  {
   if(StringLen(prefixoPainel)>0) ObjectsDeleteAll(0,prefixoPainel);
  }

void CriarRetanguloPainel(const string sufixo,const int x,const int y,const int largura,const int altura,const color fundo,const color borda)
  {
   string nome=NomePainel(sufixo);
   if(ObjectFind(0,nome)<0) ObjectCreate(0,nome,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,nome,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,nome,OBJPROP_XDISTANCE,PosicaoHorizontalDoPainel+PainelPX(x));
   ObjectSetInteger(0,nome,OBJPROP_YDISTANCE,PosicaoVerticalDoPainel+PainelPX(y));
   ObjectSetInteger(0,nome,OBJPROP_XSIZE,PainelPX(MathMax(1,largura)));
   ObjectSetInteger(0,nome,OBJPROP_YSIZE,PainelPX(MathMax(1,altura)));
   ObjectSetInteger(0,nome,OBJPROP_BGCOLOR,fundo);
   ObjectSetInteger(0,nome,OBJPROP_BORDER_COLOR,borda);
   ObjectSetInteger(0,nome,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(0,nome,OBJPROP_WIDTH,1);
   ObjectSetInteger(0,nome,OBJPROP_BACK,false);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,nome,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,nome,OBJPROP_ZORDER,80);
  }

void CriarTextoPainel(const string sufixo,const string texto,const int x,const int y,const int tamanho,const color cor)
  {
   string nome=NomePainel(sufixo);
   if(ObjectFind(0,nome)<0) ObjectCreate(0,nome,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,nome,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,nome,OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0,nome,OBJPROP_XDISTANCE,PosicaoHorizontalDoPainel+PainelPX(x));
   ObjectSetInteger(0,nome,OBJPROP_YDISTANCE,PosicaoVerticalDoPainel+PainelPX(y));
   ObjectSetInteger(0,nome,OBJPROP_FONTSIZE,MathMax(7,PainelPX(tamanho)));
   ObjectSetInteger(0,nome,OBJPROP_COLOR,cor);
   ObjectSetString(0,nome,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,nome,OBJPROP_TEXT,texto);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,nome,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,nome,OBJPROP_ZORDER,100);
  }

void CriarBotaoPainel(const string sufixo,const string texto,const int x,const int y,const int largura,const int altura)
  {
   string nome=NomePainel(sufixo);
   if(ObjectFind(0,nome)<0) ObjectCreate(0,nome,OBJ_BUTTON,0,0,0);
   ObjectSetInteger(0,nome,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,nome,OBJPROP_XDISTANCE,PosicaoHorizontalDoPainel+PainelPX(x));
   ObjectSetInteger(0,nome,OBJPROP_YDISTANCE,PosicaoVerticalDoPainel+PainelPX(y));
   ObjectSetInteger(0,nome,OBJPROP_XSIZE,PainelPX(largura));
   ObjectSetInteger(0,nome,OBJPROP_YSIZE,PainelPX(altura));
   ObjectSetInteger(0,nome,OBJPROP_BGCOLOR,COR_PAINEL_CARTAO_2);
   ObjectSetInteger(0,nome,OBJPROP_BORDER_COLOR,COR_PAINEL_BORDA);
   ObjectSetInteger(0,nome,OBJPROP_COLOR,COR_PAINEL_TEXTO);
   ObjectSetInteger(0,nome,OBJPROP_FONTSIZE,MathMax(8,PainelPX(9)));
   ObjectSetString(0,nome,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,nome,OBJPROP_TEXT,texto);
   ObjectSetInteger(0,nome,OBJPROP_SELECTABLE,true);
   ObjectSetInteger(0,nome,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,nome,OBJPROP_ZORDER,120);
  }

string TextoCurto(const string texto,const int limite)
  {
   if(StringLen(texto)<=limite) return texto;
   return StringSubstr(texto,0,MathMax(1,limite-3))+"...";
  }

string TextoTendencia()
  {
   if(tendenciaAtual>0) return "Alta";
   if(tendenciaAtual<0) return "Baixa";
   return "Indefinida";
  }

string TextoEstado()
  {
   if(HaPosicaoDoRobo()) return "OPERACAO ABERTA";
   if(canal.ativo) return canal.automatico ? "CANAL PULLBACK ATIVO" : "CANAL HORARIO ATIVO";
   if(pullback.candidato) return "PULLBACK CANDIDATO";
   return "AGUARDANDO";
  }

color CorDaTendencia()
  {
   if(tendenciaAtual>0) return COR_PAINEL_VERDE;
   if(tendenciaAtual<0) return COR_PAINEL_VERMELHO;
   return COR_PAINEL_OURO;
  }

color CorDoStatus()
  {
   if(HaPosicaoDoRobo()) return COR_PAINEL_VERDE;
   if(canal.ativo) return COR_PAINEL_DESTAQUE;
   if(pullback.candidato) return COR_PAINEL_OURO;
   return COR_PAINEL_MUTED;
  }

void AtualizarPainel()
  {
   if(!MostrarPainel)
     { ApagarPainel(); Comment(""); return; }
   ulong agoraMs=GetTickCount64();
   if(!painelPrecisaRedesenhar && agoraMs-ultimaAtualizacaoPainelMs<250) return;
   ultimaAtualizacaoPainelMs=agoraMs;
   painelPrecisaRedesenhar=false;
   MqlTick tick;
   SymbolInfoTick(simbolo,tick);
   double spread=(tick.ask-tick.bid)/ponto;
   Comment("");

   // Sombra, fundo e cabecalho do dashboard.
   int alturaPainel=painelRecolhido ? 54 : 354;
   CriarRetanguloPainel("Sombra",4,4,448,alturaPainel,C'5,9,16',C'5,9,16');
   CriarRetanguloPainel("Fundo",0,0,448,alturaPainel,COR_PAINEL_FUNDO,COR_PAINEL_BORDA);
   CriarRetanguloPainel("Acento",0,0,5,alturaPainel,COR_PAINEL_DESTAQUE,COR_PAINEL_DESTAQUE);
   CriarTextoPainel("Titulo","GOLDEN CHANNEL",18,10,12,COR_PAINEL_TEXTO);
   CriarTextoPainel("Subtitulo",simbolo+"  |  "+EnumToString(PeriodoDoGrafico)+"  |  SEM REPAINT",18,30,7,COR_PAINEL_MUTED);
   CriarTextoPainel("StatusPonto","●",322,15,13,CorDoStatus());
   CriarTextoPainel("StatusTopo",TextoCurto(TextoEstado(),17),341,17,8,COR_PAINEL_TEXTO);
   CriarBotaoPainel("Toggle",painelRecolhido ? "+" : "-",412,12,24,24);
   if(painelRecolhido)
     {
      ChartRedraw();
      return;
     }

   // Cartoes de metricas em tempo real.
   CriarRetanguloPainel("CardATR",12,64,132,52,COR_PAINEL_CARTAO,COR_PAINEL_BORDA);
   CriarRetanguloPainel("CardSpread",158,64,132,52,COR_PAINEL_CARTAO,COR_PAINEL_BORDA);
   CriarRetanguloPainel("CardResultado",304,64,132,52,COR_PAINEL_CARTAO,COR_PAINEL_BORDA);
   CriarTextoPainel("ATRLabel","ATR / VOLATILIDADE",22,73,7,COR_PAINEL_MUTED);
   CriarTextoPainel("ATRValor",DoubleToString(atrAtual/ponto,1)+" pts",22,90,13,COR_PAINEL_AZUL);
   CriarTextoPainel("SpreadLabel","SPREAD ATUAL",168,73,7,COR_PAINEL_MUTED);
   color corSpread=(SpreadMaximoEmPontos<=0.0 || spread<=SpreadMaximoEmPontos) ? COR_PAINEL_VERDE : COR_PAINEL_VERMELHO;
   CriarTextoPainel("SpreadValor",DoubleToString(spread,1)+" pts",168,90,13,corSpread);
   CriarTextoPainel("ResultadoLabel","RESULTADO DO DIA",314,73,7,COR_PAINEL_MUTED);
   color corResultado=resultadoDiario>0.0 ? COR_PAINEL_VERDE : (resultadoDiario<0.0 ? COR_PAINEL_VERMELHO : COR_PAINEL_MUTED);
   CriarTextoPainel("ResultadoValor",DoubleToString(resultadoDiario,2)+" "+AccountInfoString(ACCOUNT_CURRENCY),314,90,12,corResultado);

   // Cartao do canal e progresso de formacao do pullback.
   CriarRetanguloPainel("CardCanal",12,128,207,126,COR_PAINEL_CARTAO,COR_PAINEL_BORDA);
   CriarTextoPainel("CanalTitulo","CANAL ATUAL",22,138,8,COR_PAINEL_DESTAQUE);
   string tipoCanal=canal.ativo ? (canal.automatico ? "Pullback automatico" : "Canal por horario") : "Aguardando formacao";
   CriarTextoPainel("CanalTipo",tipoCanal,22,158,10,COR_PAINEL_TEXTO);
   CriarTextoPainel("SuperiorLabel","Superior",22,181,7,COR_PAINEL_MUTED);
   CriarTextoPainel("SuperiorValor",canal.ativo ? DoubleToString(canal.superior,digitos) : "--",88,179,9,COR_PAINEL_VERDE);
   CriarTextoPainel("InferiorLabel","Inferior",22,200,7,COR_PAINEL_MUTED);
   CriarTextoPainel("InferiorValor",canal.ativo ? DoubleToString(canal.inferior,digitos) : "--",88,198,9,COR_PAINEL_VERMELHO);
   CriarTextoPainel("AlturaLabel","Altura",22,219,7,COR_PAINEL_MUTED);
   CriarTextoPainel("AlturaValor",DoubleToString(canal.ativo ? canal.altura/ponto : 0.0,1)+" pts",88,217,9,COR_PAINEL_OURO);
   double progresso=canal.ativo ? 1.0 : (pullback.candidato ? MathMin(1.0,(double)pullback.velas/MathMax(1,MinimoDeVelasDoPullback)) : 0.0);
   CriarRetanguloPainel("ProgressoFundo",22,239,179,5,COR_PAINEL_CARTAO_2,COR_PAINEL_CARTAO_2);
   CriarRetanguloPainel("ProgressoValor",22,239,(int)MathRound(179.0*progresso),5,canal.ativo ? COR_PAINEL_VERDE : COR_PAINEL_OURO,canal.ativo ? COR_PAINEL_VERDE : COR_PAINEL_OURO);

   // Cartao de leitura do mercado e do sinal.
   CriarRetanguloPainel("CardSinal",229,128,207,126,COR_PAINEL_CARTAO,COR_PAINEL_BORDA);
   CriarTextoPainel("SinalTitulo","LEITURA DO MERCADO",239,138,8,COR_PAINEL_AZUL);
   CriarTextoPainel("TendenciaLabel","Tendencia",239,160,7,COR_PAINEL_MUTED);
   CriarTextoPainel("TendenciaValor",TextoTendencia(),320,157,11,CorDaTendencia());
   CriarTextoPainel("SinalLabel","Sinal",239,184,7,COR_PAINEL_MUTED);
   CriarTextoPainel("SinalValor",TextoCurto(sinalAtual,23),239,201,9,COR_PAINEL_TEXTO);
   string fase=pullback.candidato ? StringFormat("Pullback %d/%d",pullback.velas,MinimoDeVelasDoPullback) : TextoEstado();
   CriarTextoPainel("FaseLabel","Fase",239,224,7,COR_PAINEL_MUTED);
   CriarTextoPainel("FaseValor",TextoCurto(fase,24),278,222,8,CorDoStatus());

   // Faixa de desempenho e seguranca operacional.
   CriarRetanguloPainel("CardRodape",12,266,424,76,COR_PAINEL_CARTAO_2,COR_PAINEL_BORDA);
   CriarTextoPainel("OperacoesLabel","OPERACOES",22,276,7,COR_PAINEL_MUTED);
   CriarTextoPainel("OperacoesValor",IntegerToString(operacoesHoje)+" / "+IntegerToString(MaximoDeOperacoesPorDia),22,293,11,COR_PAINEL_TEXTO);
   CriarTextoPainel("PerdasLabel","PERDAS SEGUIDAS",125,276,7,COR_PAINEL_MUTED);
   color corPerdas=perdasConsecutivas>0 ? COR_PAINEL_LARANJA : COR_PAINEL_VERDE;
   CriarTextoPainel("PerdasValor",IntegerToString(perdasConsecutivas)+" / "+IntegerToString(MaximoDePerdasConsecutivas),125,293,11,corPerdas);
   CriarTextoPainel("RiscoLabel","RISCO / LOTE",253,276,7,COR_PAINEL_MUTED);
   string textoRisco=(ModoDeCalculoDoLote==LOTE_FIXO ? "Fixo  "+DoubleToString(LoteFixo,2) : (ModoDeCalculoDoLote==LOTE_POR_PERCENTUAL ? DoubleToString(PercentualDeRisco,1)+"% equity" : DoubleToString(RiscoMonetario,2)+" "+AccountInfoString(ACCOUNT_CURRENCY)));
   CriarTextoPainel("RiscoValor",textoRisco,253,293,10,COR_PAINEL_OURO);
   CriarTextoPainel("BloqueioIcone","●",22,320,9,motivoBloqueio=="" ? COR_PAINEL_VERDE : COR_PAINEL_LARANJA);
   CriarTextoPainel("BloqueioTexto",TextoCurto(motivoBloqueio=="" ? "Todos os filtros liberados" : motivoBloqueio,54),38,319,8,COR_PAINEL_MUTED);
   ChartRedraw();
  }

//--- Ciclo principal processado uma vez por nova barra fechada
bool NovaBarra(MqlRates &taxas[])
  {
   int necessario=MathMax(20,MaximoDeVelasDoPullback+5);
   ArraySetAsSeries(taxas,true);
   if(CopyRates(simbolo,PeriodoDoGrafico,0,necessario,taxas)<necessario) return false;
   if(taxas[0].time==ultimaBarra) return false;
   ultimaBarra=taxas[0].time;
   return true;
  }

void ProcessarNovaBarra()
  {
   MqlRates taxas[];
   if(!NovaBarra(taxas)) return;
   LerBufferFechado(handleATR,1,atrAtual);
   AtualizarEstatisticas();
   double protegida=0.0;
   tendenciaAtual=IdentificarTendencia(protegida);
   if(canal.ativo && !canal.automatico && TimeCurrent()>canal.expiracao)
     {
      canal.ativo=false;
      SalvarEstado();
     }
   FormarCanalHorario();
   ProcessarPullback(taxas);
   ProcessarRompimento(taxas);
   AtualizarPainel();
  }

int LocalizarResultadoPosicao(SResultadoPosicao &resultados[],const ulong identificador)
  {
   int total=ArraySize(resultados);
   for(int indice=0;indice<total;indice++)
      if(resultados[indice].identificador==identificador) return indice;
   int novoTotal=total+1;
   if(ArrayResize(resultados,novoTotal)!=novoTotal) return -1;
   resultados[total].identificador=identificador;
   resultados[total].resultado=0.0;
   resultados[total].volumeEntrada=0.0;
   resultados[total].volumeSaida=0.0;
   resultados[total].abertura=0;
   resultados[total].fechamento=0;
   resultados[total].possuiEntrada=false;
   resultados[total].possuiSaida=false;
   return total;
  }

int LocalizarMes(int &meses[],const int chave)
  {
   int total=ArraySize(meses);
   for(int indice=0;indice<total;indice++)
      if(meses[indice]==chave) return indice;
   int novoTotal=total+1;
   if(ArrayResize(meses,novoTotal)!=novoTotal) return -1;
   meses[total]=chave;
   return total;
  }

bool PosicaoEstaCompleta(const SResultadoPosicao &resultado)
  {
   return resultado.possuiEntrada
          && resultado.possuiSaida
          && resultado.volumeSaida+0.0000001>=resultado.volumeEntrada;
  }

void ImprimirResumoPorHorario(SResultadoPosicao &resultados[])
  {
   int entradas[24];
   int vitorias[24];
   double lucroLiquido[24];
   double lucroBruto[24];
   double perdaBruta[24];
   ArrayInitialize(entradas,0);
   ArrayInitialize(vitorias,0);
   ArrayInitialize(lucroLiquido,0.0);
   ArrayInitialize(lucroBruto,0.0);
   ArrayInitialize(perdaBruta,0.0);

   int total=ArraySize(resultados);
   for(int indice=0;indice<total;indice++)
     {
      if(!PosicaoEstaCompleta(resultados[indice]) || resultados[indice].abertura<=0) continue;
      MqlDateTime data;
      TimeToStruct(resultados[indice].abertura,data);
      int hora=data.hour;
      double resultado=resultados[indice].resultado;
      entradas[hora]++;
      lucroLiquido[hora]+=resultado;
      if(resultado>0.0)
        {
         vitorias[hora]++;
         lucroBruto[hora]+=resultado;
        }
      else if(resultado<0.0)
         perdaBruta[hora]+=MathAbs(resultado);
     }

   int melhorHora=-1;
   double melhorScore=-DBL_MAX;
   Print("HORARIOS | resultados agrupados pela hora do servidor da corretora");
   for(int hora=0;hora<24;hora++)
     {
      if(entradas[hora]==0) continue;
      double taxaAcerto=100.0*vitorias[hora]/entradas[hora];
      double expectativa=lucroLiquido[hora]/entradas[hora];
      double fatorLucro=perdaBruta[hora]>0.0 ? lucroBruto[hora]/perdaBruta[hora] : (lucroBruto[hora]>0.0 ? 99.0 : 0.0);
      PrintFormat("HORARIO | %02d:00-%02d:59 | entradas=%d | acerto=%.2f%% | lucro=%.2f | PF=%.2f | expectativa=%.2f",
                  hora,hora,entradas[hora],taxaAcerto,lucroLiquido[hora],fatorLucro,expectativa);
      if(entradas[hora]>=MinimoDeEntradasParaDestacarHorario && lucroLiquido[hora]>0.0 && fatorLucro>1.0)
        {
         double score=expectativa*MathSqrt((double)entradas[hora])*MathMin(fatorLucro,3.0);
         if(score>melhorScore)
           {
            melhorScore=score;
            melhorHora=hora;
           }
        }
     }
   if(melhorHora>=0)
      PrintFormat("MELHOR HORARIO | %02d:00-%02d:59 | entradas=%d | lucro=%.2f | criterio=expectativa x raiz(amostra) x PF",
                  melhorHora,melhorHora,entradas[melhorHora],lucroLiquido[melhorHora]);
   else
      PrintFormat("MELHOR HORARIO | nenhum periodo atingiu o minimo de %d entradas",MinimoDeEntradasParaDestacarHorario);
  }

bool CalcularMetricasRobustas(SMetricasRobustas &metricas)
  {
   ZeroMemory(metricas);
   metricas.concentracaoMensal=100.0;
   if(!HistorySelect(0,TimeCurrent())) return false;

   SResultadoPosicao resultados[];
   int totalNegocios=HistoryDealsTotal();
   for(int indiceNegocio=0;indiceNegocio<totalNegocios;indiceNegocio++)
     {
      ulong ticket=HistoryDealGetTicket(indiceNegocio);
      if(ticket==0) continue;
      if(HistoryDealGetString(ticket,DEAL_SYMBOL)!=simbolo) continue;
      if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=MagicNumber) continue;
      ulong identificador=(ulong)HistoryDealGetInteger(ticket,DEAL_POSITION_ID);
      if(identificador==0) continue;
      int indicePosicao=LocalizarResultadoPosicao(resultados,identificador);
      if(indicePosicao<0) return false;
      ENUM_DEAL_ENTRY entrada=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      double volume=HistoryDealGetDouble(ticket,DEAL_VOLUME);
      datetime horario=(datetime)HistoryDealGetInteger(ticket,DEAL_TIME);
      if(entrada==DEAL_ENTRY_IN || entrada==DEAL_ENTRY_INOUT)
        {
         resultados[indicePosicao].possuiEntrada=true;
         resultados[indicePosicao].volumeEntrada+=volume;
         if(resultados[indicePosicao].abertura==0 || horario<resultados[indicePosicao].abertura)
            resultados[indicePosicao].abertura=horario;
        }
      if(entrada==DEAL_ENTRY_OUT || entrada==DEAL_ENTRY_OUT_BY || entrada==DEAL_ENTRY_INOUT)
        {
         resultados[indicePosicao].possuiSaida=true;
         resultados[indicePosicao].volumeSaida+=volume;
         if(horario>resultados[indicePosicao].fechamento) resultados[indicePosicao].fechamento=horario;
        }
      resultados[indicePosicao].resultado+=HistoryDealGetDouble(ticket,DEAL_PROFIT)
                                                +HistoryDealGetDouble(ticket,DEAL_SWAP)
                                                +HistoryDealGetDouble(ticket,DEAL_COMMISSION)
                                                +HistoryDealGetDouble(ticket,DEAL_FEE);
     }

   int meses[];
   double resultadosMensais[];
   int totalPosicoes=ArraySize(resultados);
   for(int indicePosicao=0;indicePosicao<totalPosicoes;indicePosicao++)
     {
      if(!PosicaoEstaCompleta(resultados[indicePosicao])) continue;
      double resultado=resultados[indicePosicao].resultado;
      metricas.posicoes++;
      metricas.lucroLiquido+=resultado;
      if(resultado>0.0)
        {
         metricas.vencedoras++;
         metricas.lucroBruto+=resultado;
        }
      else if(resultado<0.0)
        {
         metricas.perdedoras++;
         metricas.perdaBruta+=MathAbs(resultado);
        }
      MqlDateTime data;
      TimeToStruct(resultados[indicePosicao].fechamento,data);
      int chave=data.year*100+data.mon;
      int indiceMes=LocalizarMes(meses,chave);
      if(indiceMes<0) return false;
      if(ArraySize(resultadosMensais)<ArraySize(meses))
        {
         int tamanhoAnterior=ArraySize(resultadosMensais);
         if(ArrayResize(resultadosMensais,ArraySize(meses))!=ArraySize(meses)) return false;
         resultadosMensais[tamanhoAnterior]=0.0;
        }
      resultadosMensais[indiceMes]+=resultado;
     }

   if(metricas.posicoes>0) metricas.expectativa=metricas.lucroLiquido/metricas.posicoes;
   if(metricas.perdaBruta>0.0) metricas.fatorLucro=metricas.lucroBruto/metricas.perdaBruta;
   else if(metricas.lucroBruto>0.0) metricas.fatorLucro=99.0;

   if(metricas.lucroLiquido>0.0)
     {
      double melhorMes=0.0;
      int totalMeses=ArraySize(resultadosMensais);
      for(int indiceMes=0;indiceMes<totalMeses;indiceMes++)
         if(resultadosMensais[indiceMes]>melhorMes) melhorMes=resultadosMensais[indiceMes];
      metricas.concentracaoMensal=100.0*melhorMes/metricas.lucroLiquido;
     }
   if(RegistrarResumoPorHorarioOnTester) ImprimirResumoPorHorario(resultados);
   return metricas.posicoes>0;
  }

double OnTester()
  {
   double lucroTestador=TesterStatistics(STAT_PROFIT);
   if(!AtivarCriterioRobustoOnTester && !RegistrarResumoPorHorarioOnTester) return lucroTestador;

   SMetricasRobustas metricas;
   if(!CalcularMetricasRobustas(metricas)) return AtivarCriterioRobustoOnTester ? -1000000.0 : lucroTestador;
   if(!AtivarCriterioRobustoOnTester) return lucroTestador;
   double drawdownPercentual=TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
   double drawdownDinheiro=TesterStatistics(STAT_EQUITY_DD);
   bool aprovado=metricas.posicoes>=MinimoDePosicoesCompletasOnTester
                 && metricas.lucroLiquido>0.0
                 && metricas.fatorLucro>=FatorLucroMinimoOnTester
                 && drawdownPercentual<=DrawdownMaximoPercentualOnTester
                 && (!PenalizarConcentracaoMensalOnTester || metricas.concentracaoMensal<=ConcentracaoMensalMaximaOnTester);
   double penalidadeConcentracao=MathMax(0.10,1.0-MathMin(metricas.concentracaoMensal,90.0)/100.0);
   double recuperacao=metricas.lucroLiquido/MathMax(drawdownDinheiro,1.0);
   double pontuacao=recuperacao*MathMin(metricas.fatorLucro,3.0)*MathSqrt((double)metricas.posicoes)*penalidadeConcentracao;
   if(!aprovado) pontuacao=-1000000.0+MathMin(pontuacao,999999.0);
   if(RegistrarResumoOnTester)
      PrintFormat("ROBUSTO | score=%.4f aprovado=%s posicoes=%d vitorias=%d derrotas=%d lucro=%.2f PF=%.2f DD=%.2f%% expectativa=%.2f concentracao=%.2f%%",
                  pontuacao,aprovado ? "SIM" : "NAO",metricas.posicoes,metricas.vencedoras,metricas.perdedoras,
                  metricas.lucroLiquido,metricas.fatorLucro,drawdownPercentual,metricas.expectativa,metricas.concentracaoMensal);
   return pontuacao;
  }

//--- Inicializacao e encerramento
int OnInit()
  {
   simbolo=StringLen(SimboloParaOperar)>0 ? SimboloParaOperar : _Symbol;
   prefixoPainel=StringFormat("EACP_UI_%I64u_",MagicNumber);
   painelRecolhido=PainelRecolhidoInicialmente;
   if(!SymbolSelect(simbolo,true))
     {
      Print("Nao foi possivel selecionar o simbolo ",simbolo);
      return INIT_FAILED;
     }
   ponto=SymbolInfoDouble(simbolo,SYMBOL_POINT);
   digitos=(int)SymbolInfoInteger(simbolo,SYMBOL_DIGITS);
   if(ponto<=0.0 || VelasParaFormarCanal<1 || MinimoDeVelasDoPullback<2 || MaximoDeVelasDoPullback<MinimoDeVelasDoPullback)
     {
      Print("Parametros invalidos de simbolo, canal ou pullback");
      return INIT_PARAMETERS_INCORRECT;
     }
   handleATR=iATR(simbolo,TimeframeATR,PeriodoATR);
   handleATRPullback=iATR(simbolo,TimeframeDoATR,PeriodoDoATR);
   handleMediaRapida=iMA(simbolo,TimeframeDaTendencia,PeriodoMediaRapida,0,MODE_EMA,PRICE_CLOSE);
   handleMediaLenta=iMA(simbolo,TimeframeDaTendencia,PeriodoMediaLenta,0,MODE_EMA,PRICE_CLOSE);
   if(handleATR==INVALID_HANDLE || handleATRPullback==INVALID_HANDLE || handleMediaRapida==INVALID_HANDLE || handleMediaLenta==INVALID_HANDLE)
     {
      Print("Falha ao criar handles dos indicadores. Erro ",GetLastError());
      return INIT_FAILED;
     }
   negociacao.SetExpertMagicNumber(MagicNumber);
   negociacao.SetDeviationInPoints(SlippageMaximo);
   negociacao.SetTypeFillingBySymbol(simbolo);
   ultimaBarra=iTime(simbolo,PeriodoDoGrafico,0);
   CarregarEstado();
   if(canal.ativo && !canal.automatico) ultimoInicioCanalHorario=canal.inicio;
   if(canal.ativo && canal.expiracao>0 && TimeCurrent()>canal.expiracao && !HaPosicaoDoRobo()) canal.ativo=false;
   AtualizarEstatisticas();
   LerBufferFechado(handleATR,1,atrAtual);
   motivoBloqueio="Aguardando o proximo candle fechado";
   Log("EA inicializado. Sinais anteriores foram ignorados; processamento comeca na proxima barra.");
   DesenharCanal();
   AtualizarPainel();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int motivo)
  {
   SalvarEstado();
   ApagarPainel();
   if(handleATR!=INVALID_HANDLE) IndicatorRelease(handleATR);
   if(handleATRPullback!=INVALID_HANDLE) IndicatorRelease(handleATRPullback);
   if(handleMediaRapida!=INVALID_HANDLE) IndicatorRelease(handleMediaRapida);
   if(handleMediaLenta!=INVALID_HANDLE) IndicatorRelease(handleMediaLenta);
   Comment("");
  }

void OnTick()
  {
   GerenciarPosicoes();
   ProcessarNovaBarra();
   AtualizarPainel();
  }

void OnChartEvent(const int id,const long &parametroLongo,const double &parametroDouble,const string &parametroString)
  {
   if(id!=CHARTEVENT_OBJECT_CLICK || parametroString!=NomePainel("Toggle")) return;
   painelRecolhido=!painelRecolhido;
   painelPrecisaRedesenhar=true;
   ApagarPainel();
   AtualizarPainel();
  }

void OnTradeTransaction(const MqlTradeTransaction &transacao,const MqlTradeRequest &requisicao,const MqlTradeResult &resultado)
  {
   if(transacao.type!=TRADE_TRANSACTION_DEAL_ADD || transacao.deal==0) return;
   if(!HistoryDealSelect(transacao.deal)) return;
   if(HistoryDealGetString(transacao.deal,DEAL_SYMBOL)!=simbolo || (ulong)HistoryDealGetInteger(transacao.deal,DEAL_MAGIC)!=MagicNumber) return;
   ENUM_DEAL_ENTRY entrada=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(transacao.deal,DEAL_ENTRY);
   if(entrada==DEAL_ENTRY_OUT || entrada==DEAL_ENTRY_OUT_BY || entrada==DEAL_ENTRY_INOUT)
     {
      double lucro=HistoryDealGetDouble(transacao.deal,DEAL_PROFIT)+HistoryDealGetDouble(transacao.deal,DEAL_SWAP)+HistoryDealGetDouble(transacao.deal,DEAL_COMMISSION);
      Log(StringFormat("Saida registrada. Resultado=%.2f",lucro));
      AtualizarEstatisticas();
      if(!HaPosicaoDoRobo())
        {
         if(canal.automatico && canal.operado && !PermitirNovaEntradaNoMesmoPullback)
           {
            canal.ativo=false;
            pullback.candidato=false;
            estadoAutomatico=CANAL_INVALIDADO;
            motivoBloqueio="Pullback concluido apos a operacao";
            Log("Canal automatico liberado apos o encerramento da operacao");
           }
         else
            estadoAutomatico=canal.ativo ? CANAL_FORMADO : SEM_TENDENCIA;
         ultimaSaida=TimeCurrent();
        }
      SalvarEstado();
     }
  }
