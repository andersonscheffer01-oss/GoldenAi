export const THEMES = [
  {
    id: "golden",
    name: "GOLDEN JARVIS",
    short: "Golden",
    desc: "O painel de referência: medidores de hardware reais, navegação por visões (Projetos, Análise, Automação, Controle), núcleo de IA, modo sombra e o globo de partículas com os módulos reais em órbita ao centro.",
    swatches: ["#01040b", "#4fd0ff", "#ffc23c"],
    mode: "core",
    demoCommand: "interface golden",
  },
  {
    id: "arc",
    name: "REATOR ARC",
    short: "Reator",
    desc: "Núcleo de energia centralizado, anéis giratórios e foco total na conversa. O visual clássico do Homem de Ferro.",
    swatches: ["#04121b", "#35d8ff", "#ffb02e"],
    mode: "arc",
    demoCommand: "interface reator",
  },
  {
    id: "holo",
    name: "CENTRO DE COMANDO",
    short: "Comando",
    desc: "Três colunas, globo holográfico, grade em perspectiva e telemetria sempre visível.",
    swatches: ["#02060d", "#4de1ff", "#7cf0c8"],
    mode: "holo",
    demoCommand: "interface comando",
  },
  {
    id: "neural",
    name: "NEURAL",
    short: "Neural",
    desc: "Enxame de partículas conectadas, minimalismo violeta e histórico de conversa em destaque.",
    swatches: ["#04030a", "#b98cff", "#ff7ad9"],
    mode: "neural",
    demoCommand: "interface neural",
  },
  {
    id: "sentinel",
    name: "SENTINELA",
    short: "Sentinela",
    desc: "HUD tático âmbar com radar, retículo de mira e leitura de dados densa.",
    swatches: ["#070502", "#ffb02e", "#7dffa8"],
    mode: "sentinel",
    demoCommand: "interface sentinela",
  },
  {
    id: "nucleo",
    name: "NÚCLEO NEURAL",
    short: "Núcleo",
    desc: "Anel dourado com rede de filamentos vivos e nós rotulados ligados ao núcleo — clique num nó para executar.",
    swatches: ["#05070d", "#58c8ff", "#ffc23c"],
    mode: "nucleo",
    demoCommand: "interface núcleo",
  },
  {
    id: "avatar",
    name: "HOLOGRAMA",
    short: "Holograma",
    desc: "Busto de partículas com núcleo de energia dourado, ondas laterais e anéis de contenção.",
    swatches: ["#04060e", "#59b6ff", "#ffa32e"],
    mode: "avatar",
    demoCommand: "interface holograma",
  },
];

export const THEME_ALIASES = {
  golden: "golden", "golden jarvis": "golden", dourada: "golden", dourado: "golden", ouro: "golden",
  padrao: "golden", "padrão": "golden", principal: "golden", painel: "golden", referencia: "golden", "referência": "golden",
  reator: "arc", arc: "arc", jarvis: "arc", classico: "arc", clássico: "arc",
  comando: "holo", holo: "holo", holografico: "holo", holográfico: "holo", centro: "holo", stark: "holo",
  neural: "neural", partículas: "neural", particulas: "neural", violeta: "neural",
  sentinela: "sentinel", sentinel: "sentinel", tatico: "sentinel", tático: "sentinel", radar: "sentinel", militar: "sentinel",
  nucleo: "nucleo", "núcleo": "nucleo", core: "nucleo",
  avatar: "avatar", holograma: "avatar", humanoide: "avatar", busto: "avatar",
};

export function resolveThemeId(text) {
  const t = String(text || "").toLowerCase();
  for (const key of Object.keys(THEME_ALIASES)) {
    if (t.includes(key)) return THEME_ALIASES[key];
  }
  return null;
}

export function getTheme(id) {
  return THEMES.find((t) => t.id === id) || THEMES[0];
}
