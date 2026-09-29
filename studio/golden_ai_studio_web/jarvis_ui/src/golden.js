// ---------------------------------------------------------------------------
// golden.js — painel GOLDEN JARVIS (o modelo padrão da interface).
//
// Os painéis em volta do orbe central seguem a interface de referência:
//   • coluna esquerda  → menu de seções, medidores SISTEMA e relógio/globo;
//   • coluna direita   → SISTEMA ONLINE, AGENTES ATIVOS, MEMÓRIA DO SISTEMA,
//                        PESQUISA E INTERNET, PROJETOS RECENTES e MISSÃO ATUAL;
//   • faixa inferior   → TAREFAS EM ANDAMENTO, CONVERSA + COMANDO MANUAL e
//                        AÇÕES RÁPIDAS.
// O centro (orbe de partículas, palavra, pílula, onda) permanece como antes.
//
// Tudo é interativo de verdade: os medidores leem hardware real (metrics.js),
// a lista de agentes deriva do estado real (voz, rede, backend, apps, notas),
// as tarefas são timers ativos + comando em execução + projetos pendentes, a
// pesquisa consulta a internet (search.js) e o comando manual roteia para o
// núcleo local, para o backend ou para a IA. O DOM compartilhado (conversa,
// entrada, telemetria, log, módulos) é MOVIDO para dentro dos encaixes do
// painel e devolvido ao sair do tema.
// ---------------------------------------------------------------------------

const TAU = Math.PI * 2;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const hhmm = (ts) => new Date(ts).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

const WORDS_L = ["OUVIR", "COMPREENDER", "ANALISAR", "CONECTAR", "PLANEJAR", "EXECUTAR"];
const WORDS_R = ["PESSOAS", "IDEIAS", "DADOS", "ESTRATÉGIA", "AUTOMAÇÃO", "RESULTADOS"];

const STATE_LABEL = {
  idle: "EM ESPERA", listening: "OUVINDO", thinking: "PROCESSANDO",
  executing: "EXECUTANDO", speaking: "RESPONDENDO", alert: "ALERTA",
};

const AGENT_LABEL = { auto: "Automático", local: "Núcleo local", backend: "Backend (PC)", ia: "IA generativa" };
const KIND_LABEL = { noticia: "notícia", wiki: "enciclopédia", resposta: "resposta direta", relacionado: "tópico relacionado", comunidade: "comunidade" };

const NAV = [
  { id: "conversa", label: "Conversa", sub: "diálogo e comandos", icon: "chat" },
  { id: "controle", label: "Controle", sub: "sistema e módulos", icon: "sliders" },
  { id: "projetos", label: "Projetos", sub: "do plano à realização", icon: "folder" },
  { id: "pesquisa", label: "Pesquisa", sub: "informação em ação", icon: "search" },
  { id: "analise", label: "Análise", sub: "dados em insights", icon: "chart" },
  { id: "automacao", label: "Automação", sub: "processos inteligentes", icon: "bolt" },
  { id: "memoria", label: "Memória", sub: "contexto sempre ativo", icon: "brain" },
  { id: "config", label: "Configurações", sub: "ajustes do sistema", icon: "gear", action: "settings" },
];

const SVG = {
  chat: '<path d="M4 5h16v11H8l-4 4z"/>',
  sliders: '<path d="M4 7h16M4 12h16M4 17h16"/><circle cx="9" cy="7" r="1.9"/><circle cx="15" cy="12" r="1.9"/><circle cx="7" cy="17" r="1.9"/>',
  folder: '<path d="M3 6h6l2 2h10v11H3z"/>',
  search: '<circle cx="11" cy="11" r="6.4"/><path d="M15.8 15.8 20.5 20.5"/>',
  chart: '<path d="M4 19V5M4 19h16M8 16v-5M12 16V8M16 16v-7"/>',
  bolt: '<path d="M13 2 4 14h6l-1 8 9-12h-6z"/>',
  brain: '<path d="M9 4a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3M15 4a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3M12 4v16"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4"/>',
  doc: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4M9 13h6M9 17h4"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.6 2.6 2.6 14.4 0 17M12 3.5c-2.6 2.6-2.6 14.4 0 17"/>',
  chart2: '<path d="M4 19V5M4 19h16M8 16v-4M12 16V8M16 16v-6"/>',
  radar: '<circle cx="12" cy="12" r="8"/><path d="M12 12l6-4"/><circle cx="12" cy="12" r="2"/>',
  media: '<path d="M9 18V6l10-3v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="15" r="2.5"/>',
  vol: '<path d="M4 9h3l4-4v14l-4-4H4zM15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12"/>',
  shot: '<rect x="3" y="6" width="18" height="13" rx="2"/><circle cx="12" cy="12" r="3.4"/>',
  lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M10 2v4M14 2v4M10 18v4M14 18v4M2 10h4M2 14h4M18 10h4M18 14h4"/>',
  links: '<path d="M10 6H7a4 4 0 0 0 0 8h3M14 10h3a4 4 0 0 1 0 8h-3M9 12h6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};

const QUICK = [
  { label: "Nova Pesquisa", icon: "search", act: "search" },
  { label: "Analisar Arquivo", icon: "file", act: "file" },
  { label: "Criar Projeto", icon: "folder", act: "project" },
  { label: "Automatizar", icon: "bolt", act: "cmd", cmd: "abrir gerenciador de tarefas" },
  { label: "Gerar Relatório", icon: "doc", act: "cmd", cmd: "diagnóstico do dispositivo" },
  { label: "Acesso à Web", icon: "globe", act: "cmd", cmd: "abrir navegador" },
];

const CONTROLS = [
  { label: "Abrir MetaTrader 5", cmd: "abrir mt5", icon: "chart2" },
  { label: "Analisar mercado", action: "open_market_intelligence", icon: "radar" },
  { label: "Tocar / pausar mídia", cmd: "pausar música", icon: "media" },
  { label: "Volume +10%", cmd: "aumentar volume", icon: "vol" },
  { label: "Capturar tela", cmd: "tirar print da tela", icon: "shot" },
  { label: "Bloquear o PC", cmd: "bloquear o computador", icon: "lock" },
  { label: "Abrir navegador", cmd: "abrir navegador", icon: "globe" },
  { label: "Painel de tarefas", cmd: "abrir gerenciador de tarefas", icon: "chip" },
];

const PILLS = [
  { label: "Status do sistema", cmd: "status do sistema" },
  { label: "Analisar mercado", action: "open_market_intelligence" },
  { label: "Projetos", view: "projetos" },
  { label: "Pesquisar na web", view: "pesquisa" },
  { label: "Modo foco", role: "focus" },
  { label: "", role: "settings", icon: "plus" },
];

function fmtMoney(v, dec = 2) {
  if (v == null || isNaN(v)) return "—";
  try { return Number(v).toLocaleString("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec }); }
  catch { return String(v); }
}
function fmtSize(b) {
  if (b == null) return "—";
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}
function fmtLeft(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s >= 3600) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min restantes`;
  if (s >= 60) return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s restantes`;
  return `${s} s restantes`;
}

export function createGolden(api) {
  const root = $("#golden");
  if (!root) return null;

  const el = {
    name: $("#gName"), sub: $("#gSub"), nav: $("#gNav"), tagline: $("#gTagline"), side: $("#gSide"),
    src: $("#gSrc"), gauges: $("#gGauges"), time: $("#gTime"), day: $("#gDay"), globe: $("#gGlobe"), verL: $("#gVerL"),
    wordsL: $("#gWordsL"), wordsR: $("#gWordsR"),
    pill: $("#gPill"), pillText: $("#gPillText"), caption: $("#gCaption"), wave: $("#gWave"),
    shadow: $("#gShadow"), sysDot: $("#gSysDot"), conn: $("#gConn"), connSub: $("#gConnSub"),
    agentCount: $("#gAgentCount"), agents: $("#gAgents"),
    memVal: $("#gMemVal"), memFill: $("#gMemFill"), memNote: $("#gMemNote"),
    netStat: $("#gNetStat"), netWave: $("#gNetWave"), netGlobe: $("#gNetGlobe"), netRows: $("#gNetRows"),
    netForm: $("#gNetForm"), netInput: $("#gNetInput"),
    recent: $("#gRecent"), recentAll: $("#gRecentAll"),
    task: $("#gTask"), objective: $("#gObjective"),
    views: $("#gViews"), tasks: $("#gTasks"), taskCount: $("#gTaskCount"),
    chatSlot: $("#gChatSlot"), clearBtn: $("#gClearBtn"),
    inputSlot: $("#gInputSlot"), cmdMode: $("#gCmdMode"), attachBtn: $("#gAttachBtn"),
    attachChip: $("#gAttachChip"), agentSel: $("#gAgentSel"), advBtn: $("#gAdvBtn"), file: $("#gFile"),
    quick: $("#gQuick"), pills: $("#gPills"),
    searchSrc: $("#gSearchSrc"), searchForm: $("#gSearchForm"), searchInput: $("#gSearchInput"),
    searchSteps: $("#gSearchSteps"), searchResults: $("#gSearchResults"),
    sumSrc: $("#gSumSrc"), summary: $("#gSearchSummary"), sumBtn: $("#gSumBtn"),
    histClear: $("#gHistClear"), hist: $("#gSearchHist"),
    projects: $("#gProjects"), projCount: $("#gProjCount"),
    projectForm: $("#gProjectForm"), projectInput: $("#gProjectInput"), projectsClear: $("#gProjectsClear"),
    telemetrySlot: $("#gTelemetrySlot"), diag: $("#gDiag"), reportBtn: $("#gReportBtn"),
    mktAt: $("#gMktAt"), market: $("#gMarket"),
    quickSlot: $("#gQuickSlot"), logSlot: $("#gLogSlot"), modulesSlot: $("#gModulesSlot"),
    controls: $("#gControls"), ctrlConn: $("#gCtrlConn"),
    expandChatBtn: $("#gExpandChatBtn"), expanded: $("#chatExpanded"),
    expandedHistory: $("#chatExpandedHistory"), expandedThinking: $("#chatExpandedThinking"),
    expandedInput: $("#chatExpandedInput"), expandedClose: $("#chatExpandedClose"),
    expandedLatest: $("#chatExpandedLatest"), expandedStatus: $("#chatExpandedStatus"),
    expandedTime: $("#chatExpandedTime"),
    flowState: $("#gFlowState"), models: $("#gModels"), flow: $("#gFlow"),
    aiCoreSummary: $("#gAiCoreSummary"), aiCoreProviders: $("#gAiCoreProviders"),
    aiCoreLast: $("#gAiCoreLast"),
    memCount: $("#gMemCount"), memStats: $("#gMemStats"), memExport: $("#gMemExport"),
    memClear: $("#gMemClear"), memNotes: $("#gMemNotes"),
    foot: $("#gFoot"), ver: $("#gVer"),
  };

  const st = {
    mounted: false, view: "conversa", shadow: false, focus: false,
    raf: 0, timers: [], moved: [], lastT: 0, lastDraw: 0, amp: 0, ampTarget: 0,
    state: "idle", flowPulse: 0, ollama: null, ollamaAt: 0, aiCore: null, aiCoreAt: 0, diagData: null,
    expanded: false, expandedAtBottom: true, expandedWired: false,
    taskText: "", market: null, marketAt: 0, agents: [],
    search: { last: null, busy: false, summary: "" },
  };

  // avisa o app que o layout mudou (a área do orbe central é recalculada)
  let relayoutRaf = 0;
  function relayout() {
    if (!st.mounted) return;
    cancelAnimationFrame(relayoutRaf);
    relayoutRaf = requestAnimationFrame(() => api.relayout?.());
  }

  // ---------------------------------------------------------------- encaixes --
  function moveInto(node, slot) {
    if (!node || !slot) return;
    st.moved.push({ node, parent: node.parentNode, next: node.nextSibling });
    slot.appendChild(node);
  }
  function restore() {
    for (const m of st.moved.reverse()) {
      try {
        if (m.next && m.next.parentNode === m.parent) m.parent.insertBefore(m.node, m.next);
        else m.parent.appendChild(m.node);
      } catch {}
    }
    st.moved = [];
  }

  // ----------------------------------------------------------------- abas ----
  function setView(v, silent) {
    st.view = v;
    $$(".gTab", el.nav).forEach((b) => b.classList.toggle("on", b.dataset.view === v));
    $$(".gSideItem", el.side).forEach((b) => b.classList.toggle("on", b.dataset.view === v));
    $$(".gView", el.views).forEach((s) => {
      const on = s.dataset.view === v;
      s.hidden = !on;
      s.classList.toggle("on", on);
    });
    if (v === "analise") { renderDiag(); renderMarket(); }
    if (v === "projetos") renderProjects();
    if (v === "memoria") renderMemoria();
    if (v === "pesquisa") renderHist();
    if (v === "controle") window.JarvisB3Refresh?.();
    relayout();
    if (!silent) api.log?.(`painel → ${v}`, "ok");
  }

  function openB3(target) {
    setView("controle");
    if (window.location.hash === "#market-intelligence") {
      setMarketSurface(target);
      return;
    }
    if (!target) return;
    const focus = () => document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(focus);
    else window.setTimeout(focus, 0);
  }

  const B3_SURFACE_IDS = [
    "gB3OverviewSection", "gB3MarketSection", "gB3ScannerSection",
    "gB3RobotsSection", "gB3EvidenceSection", "gB3MemorySection",
    "gB3ProvenanceSection",
  ];
  function setMarketSurface(target) {
    if (window.location.hash !== "#market-intelligence") return;
    const selected = B3_SURFACE_IDS.includes(target) ? target : "gB3MarketSection";
    root.dataset.marketSurface = selected;
    root.dataset.marketSurfaceVersion = "b3-market-v2";
    B3_SURFACE_IDS.forEach((id) => {
      const node = document.getElementById(id);
      if (!node) return;
      const active = id === "gB3OverviewSection" || id === selected;
      node.hidden = !active;
      node.dataset.b3SurfaceActive = active && id === selected ? "1" : "0";
      node.setAttribute("data-b3-surface-active", active && id === selected ? "1" : "0");
    });
    $$(".gB3Jump", root).forEach((button) => {
      button.classList.toggle("on", button.dataset.b3Target === selected);
      button.setAttribute("aria-current", button.dataset.b3Target === selected ? "page" : "false");
    });
  }

  function openMarketIntelligence() {
    const desktopOpen = window.__JARVIS_DESKTOP_OPEN_MARKET__;
    if (typeof desktopOpen === "function") {
      desktopOpen();
      return;
    }
    const target = new URL(window.location.href);
    target.hash = "market-intelligence";
    const child = window.open(
      target.href,
      "jarvis-market-intelligence",
      "popup=yes,width=1500,height=900,resizable=yes,scrollbars=yes"
    );
    if (child) {
      child.focus?.();
      return;
    }
    window.location.assign(target.href);
  }

  function expandedAtBottom() {
    if (!el.expandedHistory) return true;
    return el.expandedHistory.scrollHeight - el.expandedHistory.scrollTop - el.expandedHistory.clientHeight < 32;
  }

  function scrollExpandedToLatest() {
    if (!el.expandedHistory) return;
    el.expandedHistory.scrollTop = el.expandedHistory.scrollHeight;
    st.expandedAtBottom = true;
    if (el.expandedLatest) el.expandedLatest.hidden = true;
  }

  function openExpandedChat() {
    if (st.expanded || !el.expanded) return;
    st.expanded = true;
    el.expanded.hidden = false;
    document.body.classList.add("chat-expanded-open");
    el.expandedStatus.textContent = api.getBridgeStatus?.() === "online" ? "ONLINE" : "LOCAL";
    el.expandedTime.textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    el.expandedHistory.appendChild(el.chatSlot.querySelector("#conversation"));
    const thinking = el.chatSlot.querySelector("#thinkingBar");
    if (thinking) el.expandedThinking.appendChild(thinking);
    const input = el.inputSlot.querySelector("#inputRow");
    if (input) el.expandedInput.appendChild(input);
    requestAnimationFrame(scrollExpandedToLatest);
  }

  function closeExpandedChat() {
    if (!st.expanded) return;
    const conversation = el.expandedHistory.querySelector("#conversation");
    if (conversation) el.chatSlot.appendChild(conversation);
    const thinking = el.expandedThinking.querySelector("#thinkingBar");
    if (thinking) el.chatSlot.appendChild(thinking);
    const input = el.expandedInput.querySelector("#inputRow");
    if (input) el.inputSlot.appendChild(input);
    el.expanded.hidden = true;
    document.body.classList.remove("chat-expanded-open");
    st.expanded = false;
  }

  function handleNewMessage() {
    if (!st.expanded || !el.expandedHistory) return;
    const shouldFollow = st.expandedAtBottom || expandedAtBottom();
    requestAnimationFrame(() => {
      if (shouldFollow) scrollExpandedToLatest();
      else if (el.expandedLatest) el.expandedLatest.hidden = false;
    });
  }

  // ----------------------------------------------------------- menu lateral --
  function renderSideNav() {
    el.side.innerHTML = NAV.map((n) => `
      <button class="gSideItem" type="button" data-view="${n.id}" data-icon="${n.icon}" title="${esc(n.sub)}">
        <svg viewBox="0 0 24 24" aria-hidden="true">${SVG[n.icon] || SVG.chip}</svg>
        <span>${esc(n.label)}</span>
        <i class="gSideSub">${esc(n.sub)}</i>
      </button>`).join("");
    $$(".gSideItem", el.side).forEach((b) => {
      b.onclick = () => {
        const n = NAV.find((x) => x.id === b.dataset.view);
        api.sfx?.("click");
        if (!n) return;
        if (n.action === "settings") { api.openSettings?.(); return; }
        setView(n.id);
      };
    });
  }

  // ------------------------------------------------------------- medidores ---
  const GAUGES = [
    { id: "cpu", label: "CPU" },
    { id: "ram", label: "RAM" },
    { id: "gpu", label: "GPU" },
    { id: "vram", label: "VRAM" },
  ];
  function buildGauges() {
    el.gauges.innerHTML = GAUGES.map((g) => `
      <div class="gGauge" data-g="${g.id}" data-ix="1" title="Clique para detalhes de ${g.label}">
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <circle class="gg-bg" cx="50" cy="50" r="42"/>
          <circle class="gg-fg" cx="50" cy="50" r="42" stroke-dasharray="0 264"/>
        </svg>
        <b class="gg-val">--</b>
        <span class="gg-lab">${g.label}</span>
        <i class="gg-name">—</i>
      </div>`).join("");
    $$(".gGauge", el.gauges).forEach((n) => {
      n.onclick = () => {
        const id = n.dataset.g;
        const m = (st.diagData || {})[id] || {};
        const nome = m.name || m.note || "—";
        api.toast?.("SISTEMA", `${id.toUpperCase()}: ${nome}${m.pct != null ? " · " + Math.round(m.pct) + "%" : ""}`);
        api.log?.(`medidor ${id} · ${nome}`, "ok");
      };
    });
  }
  function paintGauges(d) {
    st.diagData = d;
    for (const g of GAUGES) {
      const node = $(`.gGauge[data-g="${g.id}"]`, el.gauges);
      if (!node) continue;
      const m = d[g.id] || {};
      const pct = m.pct;
      const circ = 2 * Math.PI * 42;
      const v = pct == null ? 0 : clamp(pct, 0, 100);
      $(".gg-fg", node).setAttribute("stroke-dasharray", `${(v / 100) * circ} ${circ}`);
      node.dataset.empty = pct == null ? "1" : "0";
      node.dataset.hot = v > 82 ? "1" : "0";
      $(".gg-val", node).textContent = pct == null ? "—" : (v < 10 && v > 0 ? v.toFixed(1) : Math.round(pct)) + "%";
      // sem backend, alguns sensores simplesmente não existem no navegador:
      // nesse caso mostramos o motivo informado pela telemetria (ex.: "sem sensor")
      let name = pct == null ? (m.note || "requer o backend") : (m.name || m.note || "—");
      if (g.id === "ram" && m.usedGB != null && m.totalGB != null) name = `${m.usedGB.toFixed(1)} / ${m.totalGB.toFixed(1)} GB`;
      if (g.id === "vram" && m.usedGB != null && m.totalGB != null) name = `${m.usedGB.toFixed(1)} / ${m.totalGB.toFixed(1)} GB`;
      if (g.id === "cpu" && m.cores) name = `${m.name || ""} · ${m.cores}n`;
      node.title = `${g.label}: ${name}${m.note && m.name ? " · " + m.note : ""} — clique para detalhes`;
      const nm = $(".gg-name", node);
      nm.textContent = name.length > 30 ? name.slice(0, 29) + "…" : name;
    }
    const backend = d.source === "backend";
    el.src.textContent = backend ? "SERVIDOR" : "DISPOSITIVO";
    el.src.dataset.src = backend ? "backend" : "device";
  }

  // --------------------------------------------------------- agentes ativos --
  function agentList() {
    const d = st.diagData || {};
    const set = api.getSettings?.() || {};
    const v = api.getVoice?.() || {};
    const bridgeOn = api.getBridgeStatus?.() === "online";
    const net = navigator.onLine !== false;
    const apps = d.apps || null;
    const hasAI = false;
    const nNotes = (api.getNotes?.() || []).length;
    const backend = d.source === "backend";
    const list = [
      { name: "Núcleo", on: true, stat: "Online", why: "a própria interface" },
      { name: "Voz", on: !!v.supported && !!set.speak, stat: !v.supported ? "Ausente" : v.listening ? "Ouvindo" : set.speak ? "Online" : "Mudo", why: "síntese e reconhecimento do navegador" },
      { name: "Pesquisador", on: net, stat: net ? "Online" : "Offline", why: "leitura da web sem CORS (super-fetch)" },
      { name: "Navegador Web", on: net, stat: net ? "Online" : "Offline", why: "abre sites e buscas" },
      { name: "Automação", on: bridgeOn, stat: bridgeOn ? "Online" : "Offline", why: "executa ações no sistema pelo backend" },
      { name: "Trading (MT5)", on: !!(apps && apps.mt5), stat: apps ? (apps.mt5 ? "Ativo" : "Fechado") : bridgeOn ? "Offline" : "Sem socket", why: "MetaTrader 5 detectado no PC" },
      { name: "Especialista Financeiro", on: bridgeOn || net, stat: bridgeOn ? "Online" : net ? "Janela" : "Offline", why: "cotações reais pelo servidor local" },
      { name: "Analista de Dados", on: true, stat: backend ? "Online" : "Parcial", why: "telemetria real do dispositivo/PC" },
      { name: "Memória", on: true, stat: `${nNotes} item${nNotes === 1 ? "" : "s"}`, why: "anotações persistentes no navegador" },
      { name: "IA generativa", on: hasAI, stat: hasAI ? "Online" : "Não carregada", why: "plugin ai-text-plugin (opcional)" },
    ];
    return list;
  }
  function paintAgents() {
    st.agents = agentList();
    const on = st.agents.filter((a) => a.on).length;
    el.agentCount.textContent = `${on}/${st.agents.length}`;
    el.agentCount.dataset.all = on === st.agents.length ? "1" : "0";
    el.agents.innerHTML = st.agents.map((a) => `
      <div class="gAgent" data-on="${a.on ? 1 : 0}" title="${esc(a.why)}">
        <i></i><span>${esc(a.name)}</span><b>${esc(a.stat)}</b>
      </div>`).join("");
  }

  // ------------------------------------------------------ memória do sistema --
  function paintMemory() {
    const d = st.diagData || {};
    const ram = d.ram || {};
    const pct = ram.pct;
    const backend = d.source === "backend";
    el.memVal.textContent = pct == null ? "—" : `${Math.round(pct)}% em uso`;
    el.memVal.dataset.hot = pct > 85 ? "1" : "0";
    el.memFill.style.width = (pct == null ? 0 : clamp(pct, 0, 100)) + "%";
    el.memFill.dataset.hot = pct > 85 ? "1" : "0";
    if (pct == null) el.memNote.textContent = "Este navegador não expõe leitura de memória.";
    else if (backend) el.memNote.textContent = `RAM do PC · ${ram.usedGB != null ? ram.usedGB.toFixed(1) : "?"} / ${ram.totalGB != null ? ram.totalGB.toFixed(1) : "?"} GB · sincronizada`;
    else el.memNote.textContent = `Heap JS deste navegador${ram.name ? " · " + ram.name : ""} · o backend libera a RAM real do PC`;
    el.memNote.dataset.sync = pct == null ? "0" : "1";
  }

  // ---------------------------------------------------- pesquisa e internet --
  function paintNet() {
    const on = navigator.onLine !== false;
    const bridgeOn = api.getBridgeStatus?.() === "online";
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection || {};
    const hasAI = false;
    const last = st.search.last;
    el.netStat.textContent = !on ? "OFFLINE" : bridgeOn ? "CONECTADO · PC" : "CONECTADO";
    el.netStat.dataset.src = on ? "backend" : "device";
    const rows = [
      ["REDE", !on ? "sem conexão" : [conn.effectiveType ? String(conn.effectiveType).toUpperCase() : "ATIVA", conn.downlink ? conn.downlink + " Mb/s" : null].filter(Boolean).join(" · ")],
      ["PESQUISADOR", st.search.busy ? "consultando a web…" : last ? `${last.results.length} fontes · ${hhmm(last.at)}` : "pronto — nenhuma busca ainda"],
      ["IA LEITORA", hasAI ? "pronta para resumir as fontes" : "não carregada (opcional)"],
    ];
    el.netRows.innerHTML = rows.map(([l, v]) => `<div class="gNetRow"><label>${l}</label><span>${esc(v)}</span></div>`).join("");
  }

  // --------------------------------------------------------- projetos/notas --
  function statusOf(n) { return n.done ? "Concluído" : "Em andamento"; }
  function renderProjects() {
    const list = api.getNotes?.() || [];
    el.projCount.textContent = String(list.length);
    if (!list.length) {
      el.projects.innerHTML = `<p class="gEmpty">Nenhum projeto registrado ainda. Adicione uma tarefa ao lado e ela fica salva neste navegador.</p>`;
      return;
    }
    el.projects.innerHTML = list.map((n, i) => {
      const d = new Date(n.ts);
      return `<div class="gProj${n.done ? " done" : ""}" data-id="${esc(n.id || i)}" role="button" tabindex="0" title="Clique para marcar como ${n.done ? "em andamento" : "concluído"}">
        <i>${String(list.length - i).padStart(2, "0")}</i>
        <div><p>${esc(n.text)}</p><span>${statusOf(n)} · ${d.toLocaleDateString("pt-BR")} ${hhmm(n.ts)}</span></div>
      </div>`;
    }).join("");
    $$(".gProj", el.projects).forEach((node) => {
      node.onclick = () => {
        const n = list.find((x, i) => String(x.id || i) === node.dataset.id);
        if (!n) return;
        api.toggleNote?.(n.id);
        api.toast?.("PROJETO", n.done ? "Reaberto na lista." : "Marcado como concluído.");
        api.sfx?.("ok");
        renderProjects(); renderRecent(); renderTasks();
      };
    });
  }

  function renderRecent() {
    const list = (api.getNotes?.() || []).slice(0, 4);
    if (!list.length) {
      el.recent.innerHTML = `<p class="gEmpty">Nada por aqui ainda. Use «Criar Projeto» nas ações rápidas.</p>`;
      return;
    }
    el.recent.innerHTML = list.map((n) => `
      <div class="gRecentRow${n.done ? " done" : ""}" data-id="${esc(n.id || "")}" title="${esc(n.text)}">
        <span class="gRName">${esc(n.text)}</span>
        <i class="gRStat">${statusOf(n)}</i>
      </div>`).join("");
    $$(".gRecentRow", el.recent).forEach((node) => {
      node.onclick = () => {
        const n = list.find((x) => String(x.id) === node.dataset.id);
        if (!n) return;
        api.toast?.("PROJETO", n.text.slice(0, 140));
        api.log?.(`projeto · ${n.text.slice(0, 48)}`, "ok");
      };
    });
  }

  // ----------------------------------------------------------- tarefas ativas --
  function taskRows() {
    const rows = [];
    const now = Date.now();
    for (const t of api.getTimers?.() || []) {
      const total = Math.max(1, t.end - t.start);
      const left = Math.max(0, t.end - now);
      rows.push({ kind: "timer", key: "t" + t.id, title: t.label, agent: "Cronômetro", pct: clamp(100 * (1 - left / total), 0, 100), note: fmtLeft(left) });
    }
    const running = st.state && st.state !== "idle" && st.state !== "speaking";
    if (running) {
      rows.push({
        kind: "job", key: "job", title: st.taskText || "processando",
        agent: AGENT_LABEL[(api.getSettings?.() || {}).agent] || "Núcleo",
        pct: null, note: STATE_LABEL[st.state] || "ativo", live: true,
      });
    }
    const all = api.getNotes?.() || [];
    const done = all.filter((n) => n.done).length;
    let shown = 0;
    for (const n of all) {
      if (n.done || shown >= 4) continue;
      shown++;
      rows.push({ kind: "note", key: "n" + (n.id || n.ts), id: n.id, title: n.text, agent: "Projeto", pct: 0, note: "aguardando início" });
    }
    return { rows, done, total: all.length };
  }
  function renderTasks() {
    const { rows, done } = taskRows();
    el.taskCount.textContent = String(rows.length);
    if (!rows.length) {
      el.tasks.innerHTML = `<p class="gEmpty">Nenhuma tarefa ativa agora.<br><span class="gDim">Peça algo no comando manual, arme um «timer de 10 minutos» ou crie um projeto.</span>${done ? `<br><span class="gDim">${done} já concluída${done > 1 ? "s" : ""} na memória.</span>` : ""}</p>`;
      return;
    }
    el.tasks.innerHTML = rows.map((r) => `
      <div class="gTaskRow${r.live ? " live" : ""}" data-k="${esc(r.key)}"${r.id ? ` data-id="${esc(r.id)}" role="button" tabindex="0"` : ""}${r.kind === "note" ? ' title="Clique para concluir"' : ""}>
        <div class="gT2top"><span class="gT2t">${esc(r.title)}</span><b>${r.pct == null ? "•••" : Math.round(r.pct) + "%"}</b></div>
        <div class="gT2sub">${esc(r.agent)} · ${esc(r.note)}</div>
        <div class="gBar${r.live ? " live" : ""}"><i style="width:${r.pct == null ? 42 : clamp(r.pct, 1, 100)}%"></i></div>
      </div>`).join("") + (done ? `<p class="gDim gDoneLine">${done} concluída${done > 1 ? "s" : ""} na memória</p>` : "");
  }

  // ------------------------------------------------------------ diagnóstico --
  function renderDiag() {
    const d = st.diagData || {};
    const rows = [];
    rows.push(["FONTE", d.source === "backend" ? "backend local (PC)" : "este dispositivo"]);
    if (d.source !== "backend") rows.push(["LEITURAS", "sensores do navegador — o backend libera CPU/GPU/temperatura reais"]);
    if (d.ram?.deviceGB) rows.push(["MEMÓRIA DO DISPOSITIVO", d.ram.deviceGB + " GB"]);
    if (d.gpuLocal && d.source !== "backend") rows.push(["GPU (navegador)", d.gpuLocal]);
    if (d.host) rows.push(["HOST", (d.host || "") + (d.os ? " · " + d.os : "")]);
    if (d.cpu?.name) rows.push(["PROCESSADOR", d.cpu.name]);
    if (d.gpu?.name) rows.push(["GPU", d.gpu.name + (d.gpu.note ? " · " + d.gpu.note : "")]);
    if (d.temp?.cpu != null) rows.push(["TEMP CPU", d.temp.cpu + " °C"]);
    if (d.temp?.gpu != null) rows.push(["TEMP GPU", d.temp.gpu + " °C"]);
    if (d.disk?.pct != null) rows.push(["DISCO", Math.round(d.disk.pct) + "%" + (d.disk.freeGB != null ? ` · ${d.disk.freeGB} GB livres` : "")]);
    if (d.procs != null) rows.push(["PROCESSOS", String(d.procs)]);
    if (d.net?.down != null) rows.push(["REDE ↓", d.net.down + " Mb/s" + (d.net.rtt != null ? ` · ${d.net.rtt} ms` : "")]);
    if (d.heap) rows.push(["HEAP JS", `${d.heap.used.toFixed(1)} / ${d.heap.limit.toFixed(0)} MB`]);
    if (d.battery) rows.push(["BATERIA", `${d.battery.level}%${d.battery.charging ? " ⚡" : ""}`]);
    rows.push(["RENDER", `${Math.round(d.fps || 0)} FPS`]);
    rows.push(["CONEXÃO", api.getBridgeStatus?.() === "online" ? (api.getBridgeKind?.() === "ws" ? "WebSocket" : "REST") : "modo local"]);
    rows.push(["SESSÃO", api.uptime ? api.uptime() : "—"]);
    el.diag.innerHTML = rows.map(([l, v]) => `<div class="gDiagRow"><label>${esc(l)}</label><span>${esc(v)}</span></div>`).join("");
    if (Array.isArray(d.top) && d.top.length) {
      el.diag.insertAdjacentHTML("beforeend",
        `<div class="gTopProcs"><h5>MAIS PESADOS</h5>${d.top.slice(0, 5).map((p) =>
          `<div class="gProc"><span>${esc(p.name)}</span><b>${p.cpu != null ? Math.round(p.cpu) + "%" : "—"}</b></div>`).join("")}</div>`);
    }
  }

  function renderMarket() {
    const rows = st.market;
    if (!rows || !rows.length) {
      el.mktAt.textContent = "SEM DADOS";
      el.market.innerHTML = `<p class="gEmpty">Sem cotações ainda. Ligue o backend local (é ele que busca as cotações reais) e diga «analisar mercado».</p>`;
      return;
    }
    el.mktAt.textContent = `ATUALIZADO ${hhmm(st.marketAt)}`;
    el.mktAt.dataset.src = "backend";
    el.market.innerHTML = rows.map((r) => {
      const chg = r.chg;
      const cls = chg == null ? "" : chg >= 0 ? "up" : "down";
      const varTxt = chg == null ? "—" : `${chg >= 0 ? "+" : ""}${Number(chg).toFixed(2)}%`;
      return `<div class="gMktRow">
        <span class="gMktLab">${esc(r.label || r.key || "")}</span>
        <b class="gMktPx">${fmtMoney(r.price, r.dec == null ? 2 : r.dec)}${r.unit ? " " + esc(r.unit) : ""}</b>
        <i class="gMktVar ${cls}">${varTxt}</i>
        <span class="gMktSrc">${esc(r.src || "")}</span>
      </div>`;
    }).join("");
  }

  // ----------------------------------------------------------------- núcleo IA
  async function probeOllama() {
    if (Date.now() - st.ollamaAt < 20000) return st.ollama;
    st.ollamaAt = Date.now();
    // SECURITY: No direct Ollama calls. Use Gateway adapter or telemetry.
    // If Gateway is connected, models come from backend telemetry.
    if (window.Gateway && window.Gateway.isAuthenticated) {
      try {
        const data = await window.Gateway.httpGet('/api/jarvis/providers/status');
        if (data && data.ai_core) {
          st.aiCore = data.ai_core;
          const local = data.ai_core.local_ai || {};
          st.ollama = { on: local.status === "ONLINE", list: local.model ? [local.model] : [] };
          return st.ollama;
        }
      } catch(e) {}
    }
    st.ollama = { on: false, list: [] };
    return st.ollama;
  }
  function paintModels() {
    const s = st.diagData || {};
    const models = s.models;
    const oll = st.ollama;
    const rows = [];
    const canonical = Array.isArray(st.aiCore?.providers) ? st.aiCore.providers : [];
    if (canonical.length) {
      for (const p of canonical) {
        if (p.name === "tavily" || p.name === "brave") continue;
        rows.push({ name: String(p.name || "").toUpperCase(), on: p.status === "ONLINE", detail: p.status + (p.model ? ` · ${p.model}` : "") });
      }
    } else if (Array.isArray(models) && models.length) {
      for (const m of models) rows.push({ name: m.name || m.id, on: !!m.on, detail: m.detail || (m.model || "") });
    } else {
      rows.push({ name: "PROVIDERS", on: false, detail: "STATUS INDISPONÍVEL" });
    }
    el.models.innerHTML = rows.map((m) => `
      <div class="gModel" data-on="${m.on ? 1 : 0}">
        <i></i><span>${esc(m.name)}</span><b>${esc(m.detail || (m.on ? "ATIVO" : "OFF"))}</b>
      </div>`).join("");
    paintAiCore();
  }

  function paintAiCore() {
    const core = st.aiCore;
    if (!core) {
      if (el.aiCoreSummary) el.aiCoreSummary.textContent = "STATUS GERAL · N/D";
      if (el.aiCoreProviders) el.aiCoreProviders.innerHTML = "";
      if (el.aiCoreLast) el.aiCoreLast.textContent = "ÚLTIMA EXECUÇÃO · N/D";
      return;
    }
    const llm = core.llm || {};
    const research = core.research || {};
    const last = core.last_request;
    const status = String(core.overall_status || "N/D");
    if (el.aiCoreSummary) el.aiCoreSummary.innerHTML = `<b>STATUS GERAL</b><span data-status="${esc(status)}">${esc(status)}</span><em>ATIVO: ${esc(llm.active_provider || "N/D")} / ${esc(llm.active_model || "N/D")}</em>`;
    if (el.aiCoreProviders) {
      const items = (core.providers || []).map((p) => `<span class="gAiProvider" data-status="${esc(p.status || "N/D")}"><b>${esc(String(p.name || "").toUpperCase())}</b><i>${esc(p.status || "N/D")}</i></span>`);
      const researchProviders = Object.entries(research.providers || {});
      if (researchProviders.length) {
        researchProviders.forEach(([name, item]) => items.push(`<span class="gAiProvider" data-status="${esc(item.status || "N/D")}"><b>PESQUISA · ${esc(name.toUpperCase())}</b><i>${esc(item.status || "N/D")}</i></span>`));
      } else {
        items.push(`<span class="gAiProvider" data-status="${esc(research.status || "N/D")}"><b>PESQUISA</b><i>${esc(research.status || "N/D")}</i></span>`);
      }
      el.aiCoreProviders.innerHTML = items.join("");
    }
    if (el.aiCoreLast) {
      if (!last) { el.aiCoreLast.textContent = "ÚLTIMA EXECUÇÃO · N/D"; return; }
      const tools = Array.isArray(last.tools_used) && last.tools_used.length ? last.tools_used.join(", ") : "nenhuma";
      const researchText = last.research_used ? `${last.research_provider || "web"} · ${last.source_count ?? 0} fontes` : "não";
      const latency = last.total_latency_ms == null ? "N/D" : `${last.total_latency_ms} ms`;
      el.aiCoreLast.innerHTML = `<b>ÚLTIMA EXECUÇÃO</b><span>ROTA: ${esc(last.route || last.answer_route || "N/D")}</span><span>TOOLS: ${esc(tools)}</span><span>LLM: ${esc(last.llm_provider || "nenhum")} / ${esc(last.llm_model || "N/D")}</span><span>PESQUISA: ${esc(researchText)} · FALLBACK: ${last.fallback_used ? "SIM" : "NÃO"} · ${esc(latency)}</span>`;
    }
  }

  async function refreshAiCore() {
    if (!window.Gateway || !window.Gateway.isAuthenticated) return;
    if (Date.now() - st.aiCoreAt < 2500) return;
    st.aiCoreAt = Date.now();
    try {
      const data = await window.Gateway.httpGet('/api/jarvis/providers/status');
      if (data?.ai_core) { st.aiCore = data.ai_core; paintModels(); }
    } catch (e) { /* connection state is rendered by the existing Gateway UI */ }
  }

  // --------------------------------------------------------------- relógio ---
  const DOW = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];
  const MON = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  function tickClock() {
    const d = new Date();
    el.time.textContent = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    el.day.textContent = `${DOW[d.getDay()]}, ${d.getDate()} de ${MON[d.getMonth()]}`;
  }

  // ------------------------------------------------------ canvas auxiliares --
  const ctxCache = new WeakMap();
  function fit(canvas, h) {
    const w = Math.max(60, canvas.clientWidth || 220);
    const dpr = Math.min(devicePixelRatio || 1, 2);
    let c = ctxCache.get(canvas);
    if (!c) { c = canvas.getContext("2d"); ctxCache.set(canvas, c); }
    const bw = Math.round(w * dpr), bh = Math.round(h * dpr);
    if (canvas.width !== bw || canvas.height !== bh) { canvas.width = bw; canvas.height = bh; }
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, w, h);
    return { c, w, h };
  }

  function drawGlobeInto(canvas, t, height, dots) {
    const { c, w, h } = fit(canvas, height);
    const cx = w / 2, cy = h / 2 + 4, R = Math.min(w, h) * 0.42;
    const cyan = "rgba(90,200,255,";
    const gold = "rgba(255,190,70,";
    c.lineWidth = 1;
    for (let i = 0; i < 7; i++) {
      const ph = (i / 7) * TAU + t * 0.18;
      const rx = Math.abs(Math.cos(ph)) * R;
      c.beginPath();
      c.strokeStyle = cyan + (0.10 + 0.16 * Math.abs(Math.sin(ph))).toFixed(3) + ")";
      c.ellipse(cx, cy, Math.max(0.6, rx), R, 0, 0, TAU);
      c.stroke();
    }
    for (let i = 1; i < 6; i++) {
      const yy = cy - R + (R * 2 * i) / 6;
      const rr = Math.sqrt(Math.max(0, R * R - (yy - cy) * (yy - cy)));
      c.beginPath();
      c.strokeStyle = cyan + "0.11)";
      c.ellipse(cx, yy, rr, rr * 0.16, 0, 0, TAU);
      c.stroke();
    }
    c.beginPath();
    c.strokeStyle = gold + "0.42)";
    c.lineWidth = 1.2;
    c.ellipse(cx, cy, R, R, 0, 0, TAU);
    c.stroke();
    for (let i = 0; i < dots; i++) {
      const a = (i / dots) * TAU + t * 0.30;
      const lat = Math.sin(i * 2.7) * 0.85;
      const rr = Math.cos(Math.asin(lat)) * R;
      const x = cx + Math.cos(a) * rr;
      const y = cy - lat * R;
      const near = Math.cos(a) > 0;
      c.fillStyle = (i % 5 === 0 ? gold : cyan) + (near ? 0.65 : 0.18).toFixed(2) + ")";
      c.beginPath(); c.arc(x, y, near ? 1.4 : 0.9, 0, TAU); c.fill();
    }
  }

  function drawNetWave(t) {
    const { c, w, h } = fit(el.netWave, 38);
    const mid = h / 2;
    const conn = navigator.connection || {};
    const rate = st.search.busy ? 1 : clamp((conn.downlink || 0) / 40, 0, 1);
    c.lineWidth = 1.3;
    for (let layer = 0; layer < 2; layer++) {
      c.beginPath();
      c.strokeStyle = (layer === 0 ? "rgba(255,192,80," : "rgba(90,200,255,") + (0.75 - layer * 0.34).toFixed(2) + ")";
      for (let x = 0; x <= w; x += 2) {
        const u = x / w;
        const env = Math.sin(u * Math.PI) ** 0.8;
        const a = 0.12 + rate * 0.55 + (st.search.busy ? 0.3 * Math.abs(Math.sin(t * 3)) : 0);
        const y = mid + env * Math.sin(u * 24 - t * (2.4 + rate * 3.6)) * h * 0.34 * a;
        x ? c.lineTo(x, y) : c.moveTo(x, y);
      }
      c.stroke();
    }
  }

  function drawWave(t) {
    const { c, w, h } = fit(el.wave, 64);
    const mid = h / 2;
    const amp = st.amp;
    const active = st.state !== "idle";
    c.lineWidth = 1.6;
    for (let layer = 0; layer < 3; layer++) {
      c.beginPath();
      const col = layer === 0 ? "rgba(255,192,80," : layer === 1 ? "rgba(120,215,255," : "rgba(60,130,220,";
      c.strokeStyle = col + (0.85 - layer * 0.26).toFixed(2) + ")";
      for (let x = 0; x <= w; x += 2) {
        const u = x / w;
        const env = Math.sin(u * Math.PI) ** 0.7;
        const idle = active ? 0 : 0.07 * (0.6 + 0.4 * Math.sin(t * 1.15 + layer * 1.7));
        const a = (0.17 + idle + amp * 0.95) * (layer === 0 ? 1 : 0.72);
        const y = mid + env * Math.sin(u * 26 - t * (3.2 + layer * 0.9) * (active ? 1.9 : 1)) * h * 0.36 * a
          + env * Math.sin(u * 61 + t * 5.1) * h * 0.10 * a;
        x ? c.lineTo(x, y) : c.moveTo(x, y);
      }
      c.stroke();
    }
    if (active) {
      c.fillStyle = "rgba(255,214,120,0.85)";
      const bx = ((t * 0.55) % 1) * w;
      c.beginPath(); c.arc(bx, mid, 2.1, 0, TAU); c.fill();
    }
  }

  function drawFlow(t) {
    const { c, w, h } = fit(el.flow, 46);
    const y = h / 2;
    const nodes = [0.12, 0.5, 0.88].map((u) => ({ x: u * w, y }));
    c.strokeStyle = "rgba(90,190,255,0.22)";
    c.lineWidth = 1;
    c.beginPath(); c.moveTo(nodes[0].x, y); c.lineTo(nodes[2].x, y); c.stroke();
    const live = st.state !== "idle";
    const speed = st.state === "thinking" ? 0.55 : st.state === "speaking" || st.state === "listening" ? 0.40 : 0.16;
    st.flowPulse = (st.flowPulse + speed * 0.016) % 1;
    for (let k = 0; k < 3; k++) {
      const u = (st.flowPulse + k / 3) % 1;
      const x = nodes[0].x + (nodes[2].x - nodes[0].x) * u;
      const a = live ? 0.85 : 0.32;
      c.fillStyle = `rgba(255,200,90,${a})`;
      c.beginPath(); c.arc(x, y, 2.1, 0, TAU); c.fill();
      c.fillStyle = `rgba(255,200,90,${a * 0.22})`;
      c.beginPath(); c.arc(x, y, 6, 0, TAU); c.fill();
    }
    nodes.forEach((n, i) => {
      const on = live ? (st.state === "listening" ? i === 0 : st.state === "thinking" ? i === 1 : i === 2) : false;
      c.beginPath();
      c.arc(n.x, n.y, on ? 6.2 : 4.6, 0, TAU);
      c.fillStyle = on ? "rgba(255,196,80,0.92)" : "rgba(40,90,140,0.85)";
      c.fill();
      c.lineWidth = 1.2;
      c.strokeStyle = on ? "rgba(255,232,170,0.95)" : "rgba(120,200,255,0.55)";
      c.stroke();
    });
  }

  function loop(t) {
    if (!st.mounted) return;
    st.raf = requestAnimationFrame(loop);
    const dt = Math.min(0.05, (t - st.lastT) / 1000 || 0.016);
    st.lastT = t;
    st.amp += (st.ampTarget - st.amp) * Math.min(1, dt * 7);
    // as decorações rodam a ~35fps — o centro fica fluido sem que a soma com o
    // orbe central do HUD derrube a taxa de quadros
    if (t - st.lastDraw < 28) return;
    st.lastDraw = t;
    const s = t / 1000;
    drawWave(s);
    drawFlow(s);
    drawGlobeInto(el.globe, s, 84, 26);
    drawNetWave(s);
    drawGlobeInto(el.netGlobe, s * 0.8, 64, 14);
  }

  // ---------------------------------------------------------------- pílulas --
  function renderPills() {
    el.pills.innerHTML = PILLS.map((p, i) =>
      `<button class="gPillBtn${p.icon ? " ico" : ""}" type="button" data-i="${i}" data-role="${p.role || ""}">${p.icon ? `<svg viewBox="0 0 24 24">${SVG[p.icon]}</svg>` : esc(p.label)}</button>`
    ).join("");
    $$(".gPillBtn", el.pills).forEach((b) => {
      b.onclick = () => {
        const p = PILLS[+b.dataset.i];
        api.sfx?.("click");
        if (p.role === "settings") return api.openSettings?.();
        if (p.role === "focus") return toggleFocus();
        if (p.action === "open_market_intelligence") return openMarketIntelligence();
        if (p.view === "controle") return openB3(p.target);
        if (p.view) return setView(p.view);
        api.submitCommand(p.cmd);
      };
    });
  }

  function toggleFocus(force) {
    st.focus = force === true ? true : !st.focus;
    root.dataset.focus = st.focus ? "1" : "0";
    el.pills.querySelector('[data-role="focus"]')?.classList.toggle("on", st.focus);
    api.toast?.("MODO FOCO", st.focus ? "Interface minimizada. Só o essencial permanece." : "Modo foco encerrado.");
    api.log?.(`modo foco ${st.focus ? "ativado" : "encerrado"}`, "ok");
  }

  // ------------------------------------------------------------ modo sombra --
  function setShadow(v, announce) {
    st.shadow = !!v;
    root.dataset.shadow = st.shadow ? "1" : "0";
    el.shadow.dataset.on = st.shadow ? "1" : "0";
    el.shadow.setAttribute("aria-pressed", st.shadow ? "true" : "false");
    api.setSilent?.(st.shadow);
    relayout();
    if (announce !== false) {
      api.toast?.("MODO SOMBRA", st.shadow ? "Interface oculta e voz silenciada." : "Sistema visível novamente.");
      api.log?.(`modo sombra ${st.shadow ? "ativado" : "desativado"}`, "ok");
    }
  }

  // --------------------------------------------------------------- controles-
  function renderControls() {
    el.controls.innerHTML = CONTROLS.map((c, i) =>
      `<button class="gCtrlBtn" type="button" data-i="${i}"><svg viewBox="0 0 24 24">${SVG[c.icon] || SVG.chip}</svg><span>${esc(c.label)}</span></button>`
    ).join("");
    $$(".gCtrlBtn", el.controls).forEach((b) => {
      b.onclick = () => {
        const control = CONTROLS[+b.dataset.i];
        api.sfx?.("click");
        if (control.action === "open_market_intelligence") return openMarketIntelligence();
        if (control.view === "controle") return openB3(control.target);
        api.submitCommand(control.cmd);
      };
    });
  }

  function wireB3Navigation() {
    $$(".gB3Jump", root).forEach((button) => {
      button.onclick = () => { api.sfx?.("click"); openB3(button.dataset.b3Target); };
    });
  }

  // --------------------------------------------------------- ações rápidas ---
  function pickFile() {
    return new Promise((resolve) => {
      if (!el.file) return resolve(null);
      el.file.value = "";
      el.file.onchange = () => resolve(el.file.files?.[0] || null);
      el.file.click();
    });
  }

  async function quickAct(q) {
    if (q.act === "search") {
      setView("pesquisa");
      setTimeout(() => el.searchInput?.focus(), 60);
      return;
    }
    if (q.act === "file") {
      const f = await pickFile();
      if (!f) return;
      const att = await api.readAttachment?.(f);
      if (!att) return;
      if (!att.text) api.toast?.("ARQUIVO", `${att.name} não é texto legível — vou anexar só os dados do arquivo.`);
      api.setAttachment?.(att);
      api.submitCommand(`Analise o arquivo ${att.name} e diga o que ele contém.`);
      return;
    }
    if (q.act === "project") {
      const t = window.prompt("Nome do projeto ou da tarefa:", "");
      if (t && t.trim()) {
        api.addNote?.(t.trim());
        api.toast?.("PROJETO", "Novo projeto registrado.");
        api.sfx?.("ok");
        renderProjects(); renderRecent(); renderTasks(); renderMemoria();
      }
      return;
    }
    if (q.cmd) api.submitCommand(q.cmd);
  }
  function renderQuick() {
    el.quick.innerHTML = QUICK.map((q, i) =>
      `<button class="gQBtn" type="button" data-i="${i}"><svg viewBox="0 0 24 24">${SVG[q.icon] || SVG.chip}</svg><span>${esc(q.label)}</span></button>`
    ).join("");
    $$(".gQBtn", el.quick).forEach((b) => {
      b.onclick = () => { api.sfx?.("click"); quickAct(QUICK[+b.dataset.i]); };
    });
  }

  // ------------------------------------------------------------ comandos -----
  function paintCmdBar() {
    const set = api.getSettings?.() || {};
    const mode = set.agent || "auto";
    el.cmdMode.textContent = (AGENT_LABEL[mode] || "AUTO").toUpperCase() + (set.advanced ? " · AVANÇADO" : "");
    el.cmdMode.dataset.src = mode === "backend" ? "backend" : mode === "ia" ? "ia" : mode === "local" ? "local" : "device";
    if (el.agentSel) el.agentSel.value = mode;
    el.advBtn.dataset.on = set.advanced ? "1" : "0";
  }
  function refreshAttachment() {
    const a = api.getAttachment?.();
    if (!el.attachChip) return;
    el.attachChip.hidden = !a;
    el.attachChip.textContent = a ? `📎 ${a.name} · ${fmtSize(a.size)}${a.text ? "" : " (sem texto)"}` : "";
    el.attachChip.title = a ? `${a.name} — vai junto no próximo comando` : "";
  }

  // ---------------------------------------------------------------- pesquisa --
  function renderSteps(steps) {
    if (!el.searchSteps) return;
    el.searchSteps.innerHTML = (steps || []).map((s) =>
      `<div class="gStep" data-st="${esc(s.state || "ok")}"><i></i>${esc(s.label)}</div>`).join("");
  }
  function renderResults(res) {
    if (!el.searchResults) return;
    if (!res || !res.results || !res.results.length) {
      el.searchResults.innerHTML = `<p class="gEmpty">${esc(res?.error || "Sem resultados.")}<br><span class="gDim">${res?.query ? `Você pode abrir a busca direto no navegador: <a class="gLink" href="https://duckduckgo.com/?q=${encodeURIComponent(res.query)}" target="_blank" rel="noopener">DuckDuckGo · ${esc(res.query)}</a>` : ""}</span></p>`;
      return;
    }
    el.searchResults.innerHTML = res.results.map((r, i) => {
      const url = String(r.url || "").trim();
      const safe = /^https?:\/\//i.test(url);
      const tag = safe ? "a" : "div";
      return `
      <${tag} class="gRes" data-kind="${esc(r.kind || "")}"${safe ? ` href="${esc(url)}" target="_blank" rel="noopener noreferrer"` : ""}>
        <div class="gResTop"><i>${String(i + 1).padStart(2, "0")}</i><b>${esc(r.title)}</b></div>
        <span class="gResHost">${r.kind ? `<em class="gResKind">${esc(KIND_LABEL[r.kind] || r.kind)}</em>` : ""}${esc(r.host || "")}</span>
        ${r.snippet ? `<p>${esc(r.snippet)}</p>` : ""}
      </${tag}>`;
    }).join("");
    if (el.searchResults && api.openUrl) {
      el.searchResults.querySelectorAll("a.gRes").forEach((card) => {
        card.addEventListener("click", (event) => {
          const url = String(card.getAttribute("href") || "").trim();
          if (!/^https?:\/\//i.test(url)) {
            event.preventDefault();
            return;
          }
          event.preventDefault();
          api.openUrl(url, card.querySelector(".gResTop b")?.textContent || url);
        });
      });
    }
  }
  function renderHist() {
    const hist = api.getSearchHistory?.() || [];
    el.hist.innerHTML = hist.length
      ? hist.map((h) => `<button class="gHistRow" type="button" data-q="${esc(h)}"><i></i>${esc(h)}</button>`).join("")
      : `<p class="gEmpty">Suas buscas ficam guardadas aqui neste navegador.</p>`;
    $$(".gHistRow", el.hist).forEach((b) => {
      b.onclick = () => { el.searchInput.value = b.dataset.q; el.searchForm.requestSubmit(); };
    });
  }
  async function runSearch(q, options = {}) {
    if (st.search.busy) return;
    const query = String(q || "").trim();
    if (!query) return;
    if (!options.background) setView("pesquisa");
    st.search.busy = true;
    el.searchSrc.textContent = "CONSULTANDO";
    el.searchResults.innerHTML = `<p class="gEmpty">Lendo a web agora…</p>`;
    if (el.summary) el.summary.textContent = "Lendo a resposta sintetizada…";
    renderSteps([{ label: `iniciando busca por "${query}"`, state: "run" }]);
    paintNet();
    const res = await api.webSearch?.(query, {
      onStep: (label, state, steps) => { renderSteps(steps); paintNet(); },
    });
    st.search.busy = false;
    st.search.last = res && res.ok ? res : null;
    el.searchSrc.textContent = res?.source ? String(res.source).toUpperCase() : res?.ok ? "WEB" : "FALHA";
    renderResults(res);
    if (el.summary) {
      const answer = res?.response || res?.final_response || res?.answer || res?.summary || "";
      el.summary.textContent = answer || (res?.ok ? "A pesquisa retornou fontes, mas não trouxe uma síntese final." : "");
      if (el.sumSrc) el.sumSrc.textContent = answer ? "GEMINI" : "N/D";
    }
    if (res?.ok) {
      // Chat-originated research is rendered by brain.js -> renderResponse.
      // Direct research-panel searches still need their own conversation entry.
      if (!options.background && res.response && api.addMessage) {
        api.addMessage("jarvis", res.response, { typing: false });
      }
      api.addSearchHistory?.(query);
      renderHist();
      api.toast?.("PESQUISA", `${res.results.length} fontes encontradas.`);
    } else {
      api.toast?.("PESQUISA", res?.error || "Não consegui pesquisar agora.", "bad");
    }
    paintNet();
    renderTasks();
    return res;
  }
  async function summarize() {
    // AI summarizer not available — gen is not connected
    // Button is disabled in wireSearch()
    return;
    const last = st.search.last;
    if (!gen || !last) return;
    el.sumSrc.textContent = "GERANDO";
    el.summary.textContent = "O núcleo está lendo as fontes…";
    const list = last.results.slice(0, 8).map((r, i) => `${i + 1}. ${r.title} — ${r.host}\n${r.snippet}`).join("\n\n");
    let full = "";
    try {
      await gen({
        instruction: `Você é o núcleo de pesquisa do GOLDEN JARVIS. Resuma em português do Brasil, em no máximo 5 frases curtas, o que as fontes abaixo respondem sobre "${last.query}". Diga o que é consenso e o que é incerto. Não invente dados que não estejam nas fontes.\n\nFONTES:\n${list}`,
        onChunk: (d) => { full += d.textChunk; el.summary.textContent = full; },
      });
      st.search.summary = full.trim();
      el.summary.textContent = st.search.summary || "—";
      el.sumSrc.textContent = "IA";
      api.log?.(`resumo da pesquisa · ${last.query.slice(0, 40)}`, "ok");
    } catch (e) {
      el.summary.textContent = "Não consegui resumir agora.";
      el.sumSrc.textContent = "FALHA";
    }
  }

  // ----------------------------------------------------------------- memória --
  function renderMemoria() {
    const list = api.getNotes?.() || [];
    const done = list.filter((n) => n.done).length;
    const set = api.getSettings?.() || {};
    const conv = api.getConversation?.() || { count: 0 };
    el.memCount.textContent = String(list.length);
    const rows = [
      ["ANOTAÇÕES", `${list.length} (${done} concluída${done === 1 ? "" : "s"})`],
      ["BUSCAS SALVAS", String((api.getSearchHistory?.() || []).length)],
      ["MENSAGENS NA SESSÃO", String(conv.count || 0)],
      ["TEMPO DE SESSÃO", api.uptime?.() || "—"],
      ["ÚLTIMA CIDADE", set.lastCity || "—"],
      ["ROTA DO COMANDO", AGENT_LABEL[set.agent || "auto"] || "Automático"],
      ["ARMAZENAMENTO", "localStorage deste navegador"],
    ];
    el.memStats.innerHTML = rows.map(([l, v]) => `<div class="gDiagRow"><label>${esc(l)}</label><span>${esc(v)}</span></div>`).join("");
    el.memNotes.innerHTML = list.length
      ? list.slice(0, 40).map((n) => `<div class="gProj${n.done ? " done" : ""}" data-id="${esc(n.id || "")}" role="button" tabindex="0">
          <i>${n.done ? "✓" : "•"}</i>
          <div><p>${esc(n.text)}</p><span>${statusOf(n)} · ${new Date(n.ts).toLocaleDateString("pt-BR")} ${hhmm(n.ts)}</span></div>
        </div>`).join("")
      : `<p class="gEmpty">Nenhuma anotação salva ainda.</p>`;
    $$(".gProj", el.memNotes).forEach((node) => {
      node.onclick = () => {
        api.toggleNote?.(node.dataset.id);
        renderMemoria(); renderProjects(); renderRecent(); renderTasks();
      };
    });
  }

  // ------------------------------------------------------------------ mount --
  function mount() {
    if (st.mounted) return;
    st.mounted = true;
    const marketWindow = window.location.hash === "#market-intelligence";
    if (marketWindow) {
      root.dataset.marketWindow = "1";
      root.dataset.marketSurfaceVersion = "b3-market-v2";
      st.view = "controle";
      document.title = "JARVIS — Market Intelligence";
    }
    root.classList.add("on");
    root.setAttribute("aria-hidden", "false");
    const sysName = (api.cfg?.systemName || "GOLDEN JARVIS").toUpperCase();
    el.name.textContent = sysName;
    el.sub.textContent = api.cfg?.systemSub ? String(api.cfg.systemSub).toUpperCase() : "INTELIGÊNCIA PARA UM MUNDO MAIOR";
    el.ver.textContent = `${sysName} v1.0.0`;
    el.verL.textContent = `${sysName} v1.0.0`;
    el.objective.textContent = api.getObjective?.() || "—";
    if (el.tagline && api.cfg?.tagline) el.tagline.textContent = String(api.cfg.tagline).toUpperCase();

    el.wordsL.innerHTML = WORDS_L.map((w) => `<span>${w}</span>`).join("");
    el.wordsR.innerHTML = WORDS_R.map((w) => `<span>${w}</span>`).join("");

    renderSideNav();
    buildGauges();
    if (el.src) {
      el.src.title = "Clique para abrir a análise completa do sistema";
      el.src.onclick = () => setView("analise");
    }
    renderPills();
    renderControls();
    wireB3Navigation();
    renderQuick();
    setView(st.view, true);
    if (marketWindow) {
      setMarketSurface("gB3MarketSection");
      const focusMarket = () => setMarketSurface("gB3MarketSection");
      if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(focusMarket);
      else window.setTimeout(focusMarket, 0);
    }
    paintGauges(api.getTelemetry?.() || st.diagData || {});
    paintAgents();
    paintMemory();
    paintNet();
    paintCmdBar();
    refreshAttachment();
    renderProjects();
    renderRecent();
    renderTasks();
    renderDiag();
    renderMarket();
    renderMemoria();
    renderHist();
    renderSteps([]);

    // move o DOM compartilhado para dentro do painel
    const d = api.dom || {};
    moveInto(d.conversation, el.chatSlot);
    moveInto(d.thinkingBar, el.chatSlot);
    moveInto(d.inputRow, el.inputSlot);
    moveInto(d.quickActions, el.quickSlot);
    moveInto(d.telemetry, el.telemetrySlot);
    moveInto(d.activityLog, el.logSlot);
    moveInto(d.moduleList, el.modulesSlot);
    if (d.quickChips) d.quickChips.hidden = true;

    $$(".gTab", el.nav).forEach((b) => { b.onclick = () => { api.sfx?.("click"); setView(b.dataset.view); }; });
    el.shadow.onclick = () => { api.sfx?.("click"); setShadow(!st.shadow); };
    // com o modo sombra ativo, um clique em qualquer lugar traz a interface de volta
    root.addEventListener("click", (e) => {
      if (!st.shadow) return;
      if (e.target.closest("button, a, input, form, select, label")) return;
      setShadow(false);
    });
    el.objective.onclick = () => {
      const t = window.prompt("Defina o objetivo atual:", api.getObjective?.() || "");
      if (t != null) api.setObjective?.(t.trim());
    };
    el.clearBtn.onclick = () => { api.clearConversation?.(); api.toast?.("CONVERSA", "Histórico limpo."); renderMemoria(); };
    if (!st.expandedWired) {
      el.expandChatBtn.onclick = openExpandedChat;
      el.expandedClose.onclick = closeExpandedChat;
      el.expandedLatest.onclick = scrollExpandedToLatest;
      el.expandedHistory.addEventListener("scroll", () => {
        st.expandedAtBottom = expandedAtBottom();
        if (st.expandedAtBottom && el.expandedLatest) el.expandedLatest.hidden = true;
      }, { passive: true });
      window.addEventListener("jarvis:message-added", handleNewMessage);
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && st.expanded) closeExpandedChat();
        if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "f") {
          event.preventDefault();
          st.expanded ? closeExpandedChat() : openExpandedChat();
        }
      });
      st.expandedWired = true;
    }
    el.recentAll.onclick = () => setView("projetos");

    // tarefas: clique conclui/reabre um projeto
    el.tasks.addEventListener("click", (e) => {
      const row = e.target.closest(".gTaskRow[data-id]");
      if (!row) return;
      api.toggleNote?.(row.dataset.id);
      api.sfx?.("ok");
      renderTasks(); renderProjects(); renderRecent(); renderMemoria();
    });
    el.tasks.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const row = e.target.closest(".gTaskRow[data-id]");
      if (!row) return;
      e.preventDefault();
      api.toggleNote?.(row.dataset.id);
      renderTasks(); renderProjects(); renderRecent();
    });

    // comando manual: anexo, agente e modo avançado
    el.attachBtn.onclick = async () => {
      const f = await pickFile();
      if (!f) return;
      const att = await api.readAttachment?.(f);
      if (!att) return;
      api.setAttachment?.(att);
      api.toast?.("ANEXO", `${att.name} (${fmtSize(att.size)}) vai junto no próximo comando.`);
      refreshAttachment();
    };
    el.agentSel.onchange = () => {
      api.setAgent?.(el.agentSel.value);
      paintCmdBar();
      api.toast?.("AGENTE", `Os comandos agora vão para: ${AGENT_LABEL[el.agentSel.value] || el.agentSel.value}.`);
      api.log?.(`rota de comando → ${el.agentSel.value}`, "ok");
    };
    el.advBtn.onclick = () => {
      const on = !(api.getSettings?.().advanced);
      api.setAdvanced?.(on);
      paintCmdBar();
      api.toast?.("MODO AVANÇADO", on ? "Comandos vão crus ao backend, sem atalhos locais." : "Atalhos locais reativados.", on ? "" : "ok");
    };

    // ações rápidas do painel + pílulas de pesquisa
    el.netForm.onsubmit = (e) => { e.preventDefault(); const q = el.netInput.value.trim(); el.netInput.value = ""; runSearch(q); };
    el.searchForm.onsubmit = (e) => { e.preventDefault(); runSearch(el.searchInput.value.trim()); };
    el.sumBtn.onclick = () => summarize();
    // Disable AI summarizer — gen not connected in staging
    el.sumBtn.disabled = true;
    el.sumBtn.title = "Indisponível — resumo por IA em desenvolvimento";
    el.sumBtn.textContent = "RESUMIR (em desenvolvimento)";
    el.histClear.onclick = () => { api.clearSearchHistory?.(); renderHist(); api.toast?.("PESQUISA", "Histórico de buscas limpo."); };

    el.projectForm.onsubmit = (e) => {
      e.preventDefault();
      const v = el.projectInput.value.trim();
      if (!v) return;
      api.addNote?.(v);
      el.projectInput.value = "";
      renderProjects(); renderRecent(); renderTasks(); renderMemoria();
      api.log?.(`projeto registrado · ${v.slice(0, 40)}`, "ok");
      api.toast?.("PROJETO", "Anotação salva.");
      api.sfx?.("ok");
    };
    el.projectsClear.onclick = () => {
      api.clearNotes?.();
      renderProjects(); renderRecent(); renderTasks(); renderMemoria();
      api.toast?.("PROJETOS", "Todas as anotações foram removidas.");
    };
    el.reportBtn.onclick = () => api.submitCommand("diagnóstico do dispositivo");
    el.memExport.onclick = () => {
      const ok = api.exportMemory?.();
      api.toast?.("MEMÓRIA", ok ? "Arquivo JSON gerado com o seu histórico." : "Não consegui exportar agora.", ok ? "ok" : "bad");
    };
    el.memClear.onclick = () => {
      if (!window.confirm("Apagar todas as anotações e o histórico de buscas deste navegador?")) return;
      api.clearNotes?.();
      api.clearSearchHistory?.();
      renderProjects(); renderRecent(); renderTasks(); renderMemoria(); renderHist();
      api.toast?.("MEMÓRIA", "Anotações e buscas removidas.");
    };

    el.pill.dataset.on = "0";
    el.sumBtn.hidden = true;
    el.sumSrc.textContent = "GATEWAY";

    st.lastT = performance.now();
    relayout();

    st.raf = requestAnimationFrame(loop);
    st.timers.push(setInterval(tickClock, 1000));
    st.timers.push(setInterval(() => { renderTasks(); }, 1000));
    st.timers.push(setInterval(() => { paintAgents(); paintMemory(); renderDiag(); renderMemoria(); }, 3000));
    st.timers.push(setInterval(paintModels, 4000));
    st.timers.push(setInterval(refreshAiCore, 3000));
    st.timers.push(setInterval(() => { paintNet(); }, 6000));
    st.timers.push(setInterval(() => { probeOllama().then(paintModels); }, 15000));
    tickClock();
    paintModels();
    refreshAiCore();
    probeOllama().then(paintModels);
    setShadow(st.shadow, false);
    api.log?.("painel golden online", "ok");
  }

  function unmount() {
    if (!st.mounted) return;
    if (st.shadow) setShadow(false, false);
    st.mounted = false;
    root.classList.remove("on");
    delete root.dataset.marketWindow;
    delete root.dataset.marketSurface;
    delete root.dataset.marketSurfaceVersion;
    root.setAttribute("aria-hidden", "true");
    cancelAnimationFrame(st.raf);
    st.timers.forEach(clearInterval);
    st.timers = [];
    if (api.dom?.quickChips) api.dom.quickChips.hidden = false;
    restore();
  }

  return {
    root,
    mount,
    unmount,
    setView,
    isMounted: () => st.mounted,
    isShadow: () => st.shadow,
    isFocus: () => st.focus,
    setShadow,
    runSearch,
    setTask(text) { st.taskText = text || ""; el.task.textContent = text || "—"; renderTasks(); },
    setObjective(text) { el.objective.textContent = text || "—"; },
    setAmplitude(v) { st.ampTarget = clamp(v, 0, 1); },
    setMarket(rows) {
      if (!Array.isArray(rows) || !rows.length) return;
      st.market = rows;
      st.marketAt = Date.now();
      renderMarket();
    },
    setConnection(status, detail) {
      const on = status === "online";
      el.conn.textContent = on ? "ONLINE" : status === "connecting" ? "CONECTANDO" : "LOCAL";
      el.conn.dataset.on = on ? "1" : "0";
      el.sysDot.dataset.on = on ? "1" : "0";
      el.ctrlConn.textContent = el.conn.textContent;
      el.ctrlConn.dataset.src = on ? "backend" : "device";
      el.connSub.textContent = on
        ? (detail ? String(detail) : "Todos os sistemas operacionais")
        : "Modo local — rode o backend para controle total";
      paintAgents();
      paintNet();
    },
    setState(s) {
      st.state = s || "idle";
      st.ampTarget = s === "listening" || s === "speaking" ? Math.max(0.42, st.ampTarget) : st.state === "idle" ? 0 : st.ampTarget;
      el.pillText.textContent = STATE_LABEL[st.state] || "EM ESPERA";
      el.pill.dataset.on = st.state === "idle" ? "0" : "1";
      el.flowState.textContent = STATE_LABEL[st.state] || "EM ESPERA";
      el.caption.textContent = {
        idle: "Transformando ideias em realidade.",
        listening: "Ouvindo você...",
        thinking: "Analisando a solicitação...",
        executing: "Executando no sistema...",
        speaking: "Respondendo agora.",
        alert: "Protocolo de alerta ativo.",
      }[st.state] || "Transformando ideias em realidade.";
      renderTasks();
    },
    refreshAttachment,
    setTelemetry(d) { paintGauges(d); paintAgents(); paintMemory(); },
    refresh: () => {
      renderProjects(); renderRecent(); renderTasks(); renderDiag(); renderMemoria();
      paintAgents(); paintModels(); paintNet(); paintCmdBar();
      setView(st.view, true);
    },
  };
}

/**
 * DATA_SOURCE audit for UI-1.1 — marks each panel's data source
 * REAL = data comes from backend/Gateway
 * CLIENT = data comes from browser APIs
 * MISSING = no real data source (would need to be implemented)
 */
window.GOLDEN_PANEL_DATA_SOURCES = {
  // Diagnostic panel — CPU/GPU/RAM/disk from backend telemetry
  DIAG: { source: "REAL", via: "Gateway → /api/status → TelemetryAdapter", note: "Real CPU, RAM, disk, GPU, processes from PC" },
  // Agent list — constructed from real telemetry + browser APIs
  AGENTS: { source: "REAL", via: "TelemetryAdapter + browser APIs", note: "Real status: online/offline based on actual connectivity" },
  // Gauges (CPU/RAM/GPU/VRAM) — real from backend
  GAUGES: { source: "REAL", via: "Gateway → /api/status → paintGauges()", note: "Real percentages from PC sensors" },
  // Memory bar — real from backend
  MEMORY: { source: "REAL", via: "Gateway → /api/status → paintMemory()", note: "Real RAM usage from PC" },
  // Market ticker — real from backend
  MARKET: { source: "REAL", via: "Backend response d.market → golden.setMarket()", note: "Real cotações from backend" },
  // Network status — browser API
  NETWORK: { source: "CLIENT", via: "navigator.onLine + navigator.connection", note: "Browser network status" },
  // Ollama models — via Gateway
  OLLAMA_MODELS: { source: "REAL", via: "Gateway → /api/jarvis/providers/status", note: "Real model list from backend" },
  // MT5 status — via Gateway
  MT5_STATUS: { source: "REAL", via: "Gateway → /api/mt5/status", note: "Real MT5 connection status" },
  // Projects/Notes — browser localStorage
  PROJECTS: { source: "CLIENT", via: "localStorage (api.getNotes())", note: "Browser-local notes" },
  // Robot list — via Gateway (trading-panels.js)
  ROBOT_LIST: { source: "REAL", via: "Gateway → web_research/list_robots tool", note: "Real MT5 robot list from backend" },
  // Scanner — via Gateway (trading-panels.js)
  SCANNER: { source: "REAL", via: "Gateway → scanner tool", note: "Real market scan from backend" },
  // Backtest — via Gateway (trading-panels.js)
  BACKTEST: { source: "REAL", via: "Gateway → backtest tool", note: "Real backtest from backend" },
  // Comparison — via Gateway (trading-panels.js)
  COMPARISON: { source: "REAL", via: "Gateway → compare tool", note: "Real strategy comparison from backend" },
  // Validation — via Gateway (trading-panels.js)
  VALIDATION: { source: "REAL", via: "Gateway → validation tool", note: "Real validation from backend" },
  // Risk status — via Gateway (trading-panels.js)
  RISK_STATUS: { source: "REAL", via: "Gateway → risk tool", note: "Real risk engine from backend" },
  // Positions — via Gateway (trading-panels.js)
  POSITIONS: { source: "REAL", via: "Gateway → positions tool", note: "Real open positions from MT5" },
  // Security panel — MISSING (not in jarvis-ui)
  SECURITY_PANEL: { source: "MISSING", note: "Security mode selector and approval queue not implemented in jarvis-ui" },
  // Strategy manager — MISSING (not in jarvis-ui)
  STRATEGY_MANAGER: { source: "MISSING", note: "47-setup management not implemented in jarvis-ui" },
  // Control classifications (UNCLASSIFIED → resolved)
  ESCAPE_KEY: { source: "LOCAL_UI_ONLY", note: "Closes settings modal, stops voice, resets idle state. No backend call." },
  PROJECT_ROW_CLICK: { source: "LOCAL_UI_ONLY", note: "Toggles done status in localStorage. Browser-local persistence only, no backend." },
  AI_SUMMARIZER: { source: "DISABLED", note: "gen is hardcoded to null (golden.js:859). Button will be disabled in UI." },
};
