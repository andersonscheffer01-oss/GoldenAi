/* ---------------------------------------------------------------------------
   jarvis-config.js — configuração da interface (staging)
   ---------------------------------------------------------------------------
   Staging version: NO hardcoded backend URL, NO standalone server references.
   Gateway origin derived from location.origin at runtime.

   • namespace ....... prefixo das preferências no localStorage
   • defaultTheme .... golden | arc | holo | neural | sentinel | nucleo | avatar
   • aiForce ......... true se o endpoint de IA só aceitar POST
--------------------------------------------------------------------------- */
window.JARVIS_CONFIG = {
  systemName: "J.A.R.V.I.S.",
  systemSub: "Sistema de Operações Pessoais",
  userName: "Senhor",
  defaultTheme: "golden",
  tagline: "MAIS QUE IA. UM PARCEIRO DE EVOLUÇÃO.",
  objective: "Evoluir o Golden Jarvis até o controle total do meu ecossistema.",
  wakeWord: "jarvis",
  language: "pt-BR",
  voiceRate: "1.02",
  voicePitch: "0.82",
  speakReplies: "true",
  autoConnect: "true",
  bootSequence: "true",
  namespace: "jarvis-local",
  aiForce: false,
  // SECURITY: backendUrl removed — derived from location.origin via Gateway adapter
  // SECURITY: backendToken removed — device auth via Gateway WS protocol
  // SECURITY: aiUrl removed — AI routed through Gateway → JarvisService
  // SECURITY: fetchProxyUrl removed — search via Gateway Browser/Research tool
};

/* Falas de inicialização e frases de espera (as listas do main.pjs). */
window.JARVIS_LISTS = {
  bootLine: [
    "Inicializando núcleo de reator... OK",
    "Carregando protocolos de segurança... OK",
    "Sincronizando módulos de telemetria... OK",
    "Calibrando sensores de voz... OK",
    "Estabelecendo canal seguro com o backend... OK",
    "Compilando camada de interface... OK",
    "Verificando integridade estrutural... 100%",
    "Todos os sistemas operacionais",
  ],
  idleQuip: [
    "Pronto quando você estiver, senhor.",
    "Aguardando instruções.",
    "Posso ajudar em algo mais?",
    "Sensores em standby.",
    "Todos os sistemas nominais.",
    "À sua disposição.",
    "Estou monitorando, senhor.",
  ],
};
