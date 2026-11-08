import {
  applyTrendBatch, createTrendScan, failTrendBatch, nextTrendBatch,
  createTrendRequestGate, pauseTrendScan, retryFailedTrendBatch,
  filterTrendCatalogByClass, filterTrendItems, trendFrameMatrixValue,
  deriveTrendHorizon, trendFramePresentation, trendTechnicalExplanation,
  TREND_TIMEFRAMES, trendLeaders, trendScanProjection, trendScanSummary,
} from "./trend-ranking-state.js?v=20261007-market-score-detail-1";

let assetComboboxSequence = 0;

const app = document.querySelector("#app");
const root = document.querySelector("#golden");
const navigation = document.querySelector("#d2Navigation");
const workspace = document.querySelector("#gViews");

if (window.__JARVIS_DESKTOP__ === true && app && root && navigation && workspace) {
  const jarvis = window.jarvis;
  const analysisView = document.querySelector(".d2AnalysisView");

  // On Desktop only, promote the existing settings panels into the canonical
  // Segurança / Configuração route. The public Web UI keeps the original modal.
  const centralizeDesktopSettings = () => {
    const host = document.querySelector("#d2SecuritySettingsHost");
    const modalBody = document.querySelector("#settingsModal .modalBody");
    if (!host || !modalBody || host.dataset.mounted === "true") return;
    host.dataset.mounted = "true";
    modalBody.classList.add("d2CentralSettingsBody");
    host.appendChild(modalBody);
    const modal = document.querySelector("#settingsModal");
    if (modal) modal.hidden = true;
    window.addEventListener("DOMContentLoaded", () => {
      document.querySelector('[data-settings-tab="security"]')?.click();
    }, { once: true });
  };
  centralizeDesktopSettings();

  // The CyberBot-inspired Jarvis surface is deliberately loaded only by the
  // native Desktop shell.  The canonical Web UI keeps its existing markup and
  // behavior because this import is never evaluated outside the Desktop
  // identity injected by QWebEngine.
  // Legacy cache key retained in this comment for downstream compatibility:
  // import("./desktop-jarvis-experience.js?v=20261021-gemini-auto-settings-1")
  import("./desktop-jarvis-experience.js?v=20261107-gemini-provider-lock-1")
    .then((module) => module.mountDesktopJarvisExperience?.())
    .catch((error) => console.warn("[JARVIS-DESKTOP] experience unavailable", error));

  hydrateDemoViews();

  if (jarvis?.applyTheme && app.dataset.theme !== "golden") {
    jarvis.applyTheme("golden", true);
  }

  app.dataset.desktopShell = "1";
  root.dataset.desktopShell = "1";
  document.querySelector("#d2GatewaySlot")?.append(document.querySelector("#statusPill"));
  document.querySelector("#d2SettingsSlot")?.append(document.querySelector("#settingsBtn"));
  const statusText = document.querySelector("#statusText");
  if (statusText?.textContent.trim() === "DEMO") statusText.textContent = "VERIFICANDO";
  const coreState = document.querySelector("#d2CoreState");
  const updateCoreState = async () => {
    if (!coreState) return;
    coreState.textContent = "AGENT STATE: UNKNOWN";
    coreState.title = "Estado canônico do Core ainda não consultado.";
    if (!window.Gateway?.isAuthenticated) {
      coreState.title = "Aguardando autenticação existente do Jarvis.";
      return;
    }
    try {
      const status = await window.Gateway.httpGet("/api/desktop/status");
      const state = String(status?.state || "").toUpperCase();
      const validStates = new Set(["IDLE", "PLANNING", "WAITING_CONFIRMATION", "EXECUTING", "ERROR"]);
      if (status?.ok === true && validStates.has(state)) {
        coreState.textContent = `AGENT STATE: ${state}`;
        coreState.title = "Estado canônico lido de /api/desktop/status.";
        return;
      }
    } catch {
      // Keep the diagnostic bounded and never translate a read failure into Core state.
    }
    coreState.title = "Falha ao consultar /api/desktop/status; estado não confirmado.";
  };
  if (window.Gateway?.isAuthenticated) updateCoreState();
  else window.Gateway?.on("authenticated", updateCoreState);

  const routes = {
    jarvis: { view: "conversa", title: "Jarvis" },
    painel: { view: "d2-panel", title: "Painel" },
    analise: { view: "d2-analysis", title: "Análise GoldenAI" },
    radar: { view: "controle", title: "Análise GoldenAI", navRoute: "analise", focus: "gB3MarketSection" },
    operacoes: { view: "d2-operations", title: "Operações" },
    performance: { view: "d2-performance", title: "Performance" },
    historico: { view: "d2-history", title: "Histórico" },
    "inteligencia-mercado": { view: "d2-market-intelligence", title: "Inteligência de Mercado" },
    robos: { view: "controle", title: "Robôs", focus: "gB3RobotsSection" },
    backtests: { view: "d2-backtests", title: "Backtests" },
    tarefas: { view: "projetos", title: "Tarefas" },
    memoria: { view: "memoria", title: "Memória" },
    seguranca: { view: "d2-security", title: "Segurança" },
    "golden-arena": { view: "d2-golden-arena", title: "Golden Scalper Arena" },
    pesquisa: { view: "pesquisa", title: "Pesquisa" },
    automacao: { view: "automacao", title: "Automação" },
  };
  const viewRoutes = {
    conversa: "jarvis",
    "d2-panel": "painel",
    "d2-analysis": "analise",
    controle: "analise",
    "d2-operations": "operacoes",
    "d2-performance": "performance",
    "d2-history": "historico",
    "d2-market-intelligence": "inteligencia-mercado",
    "d2-backtests": "backtests",
    projetos: "tarefas",
    memoria: "memoria",
    "d2-security": "seguranca",
    "d2-golden-arena": "golden-arena",
    pesquisa: "pesquisa",
    automacao: "automacao",
  };
  let activeRoute = "jarvis";
  let navigationPending = false;
  let performanceSnapshotLoaded = false;
  let performanceSnapshotLoading = false;
  let operationsSnapshotLoaded = false;
  let operationsSnapshotLoading = false;
  let arenaReportLoaded = false;
  let arenaReportLoading = false;
  const panelAssetStorageKey = `jarvis.desktop.panel.selected_asset.v1::${window.generatorName || "local"}`;
  let selectedPanelAsset = loadPanelAsset();

  function loadPanelAsset() {
    try {
      const saved = JSON.parse(localStorage.getItem(panelAssetStorageKey) || "null");
      if (!saved || typeof saved !== "object" || !saved.provider_asset_id
          || !saved.provider || !saved.provider_symbol || !saved.asset_class) return null;
      if (saved.provider !== "MT5") {
        localStorage.removeItem(panelAssetStorageKey);
        return null;
      }
      return {
        provider: String(saved.provider).slice(0, 40),
        provider_asset_id: String(saved.provider_asset_id).slice(0, 96),
        provider_symbol: String(saved.provider_symbol).slice(0, 64),
        display_symbol: String(saved.display_symbol || saved.provider_symbol).slice(0, 64),
        display_name: String(saved.display_name || saved.provider_symbol).slice(0, 100),
        asset_class: String(saved.asset_class).slice(0, 24).toUpperCase(),
        price_unit: saved.price_unit ? String(saved.price_unit).slice(0, 64) : "",
        source_available: true,
        source_status: "REVALIDATION_REQUIRED",
      };
    } catch {
      return null;
    }
  }

  window.JarvisDesktopViewContext = Object.freeze({
    get active_view() { return activeRoute; },
    get selected_symbol() { return selectedPanelAsset?.provider_symbol || null; },
    get selected_asset() { return selectedPanelAsset ? { ...selectedPanelAsset } : null; },
    selected_robot_id: null,
    selected_campaign_id: null,
    selected_test_run_id: null,
    selected_time_range: null,
    operational_mode: "ANALYSIS",
  });

  function selectRoute(route) {
    const target = routes[route];
    if (!target || !jarvis?.golden?.setView) return;
    activeRoute = target.navRoute || route;
    root.dataset.d2Route = activeRoute;
    document.querySelectorAll("#d2Navigation [data-d2-route]").forEach((button) => {
      if (button.dataset.d2Route === activeRoute) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    navigationPending = true;
    jarvis.golden.setView(target.view);
    if (route === "analise") renderAnalysisProjection();
    if (route === "performance") loadCanonicalPerformance();
    if (route === "operacoes") loadCanonicalOperations();
    if (activeRoute === "golden-arena") void loadGoldenArenaReport();
    if (activeRoute === "painel") ensurePanelCatalog();
    if (activeRoute === "inteligencia-mercado" && !trendScanRecoveryChecked && !trendScan) {
      void recoverTrendScan();
    }
    if (activeRoute === "inteligencia-mercado") void refreshTrendMonitorStatus();
    syncMarketPolling();
    requestAnimationFrame(() => { navigationPending = false; });
    if (target.focus) {
      requestAnimationFrame(() => {
        if (target.focus === "gB3MarketSection") {
          document.querySelector('[data-b3-target="gB3MarketSection"]')?.click();
        } else {
          document.getElementById(target.focus)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }
  }

  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-d2-route]");
    if (button) selectRoute(button.dataset.d2Route);
  });
  document.querySelectorAll("[data-d2-period]").forEach((button) => {
    button.disabled = true;
    button.title = "A fonte canônica disponível não oferece filtro por período.";
  });

  function renderCanonicalPerformance(data) {
    const view = document.querySelector(".d2PerformanceView");
    if (!view) return;
    const hasMetric = (value) => value !== null && value !== undefined && value !== ""
      && Number.isFinite(Number(value));
    const resolvedSample = (stats) => {
      const counts = [stats?.wins, stats?.losses, stats?.breakeven];
      return counts.every(hasMetric) ? counts.reduce((sum, value) => sum + Number(value), 0) : null;
    };
    const assetPanel = view.querySelector(".d2AssetPanel");
    const assetEmpty = assetPanel?.querySelector(".d2DonorEmpty");
    const assetStatus = assetPanel?.querySelector(".d2MutedTag");
    const assetStats = data?.asset_performance;
    const resolvedAssets = assetStats && typeof assetStats === "object"
      ? Object.entries(assetStats).map(([symbol, stats]) => ({
          symbol,
          stats: stats && typeof stats === "object" ? stats : {},
          sample: resolvedSample(stats),
        })).filter((row) => row.sample !== null && row.sample > 0)
        .sort((a, b) => b.sample - a.sample || a.symbol.localeCompare(b.symbol))
      : [];
    if (assetEmpty && resolvedAssets.length) {
      const rows = document.createElement("div");
      rows.className = "d2AssetRows";
      resolvedAssets.forEach(({ symbol, stats, sample }) => {
        const row = document.createElement("div");
        const name = document.createElement("b");
        name.textContent = symbol;
        const count = document.createElement("span");
        count.textContent = `${sample} resultados resolvidos no Journal · ${hasMetric(stats.win_rate) ? `${Number(stats.win_rate).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% acerto` : "taxa indisponível"}`;
        const result = document.createElement("strong");
        result.textContent = hasMetric(stats.total_pnl_r)
          ? `${Number(stats.total_pnl_r) > 0 ? "+" : ""}${Number(stats.total_pnl_r).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} R`
          : "Resultado R indisponível";
        const detail = document.createElement("small");
        detail.textContent = hasMetric(stats.profit_factor) && hasMetric(stats.expectancy_r)
          ? `Fator de lucro ${Number(stats.profit_factor).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} · expectativa ${Number(stats.expectancy_r).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} R`
          : "Fator de lucro indisponível";
        row.append(name, count, result, detail);
        rows.append(row);
      });
      assetEmpty.replaceWith(rows);
    } else if (assetEmpty) {
      assetEmpty.querySelector("b").textContent = "Sem resultados resolvidos";
      assetEmpty.querySelector("p").textContent = "A fonte não contém amostra suficiente para métricas por ativo; ausência não significa desempenho zero.";
    }
    if (assetStatus) assetStatus.textContent = resolvedAssets.length
      ? "RESULTADOS DO JOURNAL · EXECUÇÃO NÃO COMPROVADA"
      : "TRADE JOURNAL · SEM AMOSTRA RESOLVIDA";

    const hourPanel = view.querySelector(".d2SessionPanel");
    const hourNote = hourPanel?.querySelector(".d2DonorSectionTitle p");
    const hourBadge = hourPanel?.querySelector(".d2MutedTag");
    const table = hourPanel?.querySelector(".d2PerformanceTable");
    const body = table?.querySelector("tbody");
    const hourStats = data?.hourly_performance;
    const resolvedHours = hourStats && typeof hourStats === "object"
      ? Object.entries(hourStats).map(([key, stats]) => ({
          hour: Number(stats?.hour ?? key),
          stats: stats && typeof stats === "object" ? stats : {},
          sample: resolvedSample(stats),
        })).filter((row) => Number.isInteger(row.hour) && row.hour >= 0 && row.hour <= 23
          && row.sample !== null && row.sample > 0)
        .sort((a, b) => a.hour - b.hour)
      : [];
    if (hourNote) hourNote.textContent = "Hora registrada na origem · fuso não normalizado";
    if (hourBadge) hourBadge.textContent = "JOURNAL · EXECUÇÃO NÃO COMPROVADA";
    if (table) {
      const headings = ["HORA REGISTRADA", "AMOSTRA", "WIN RATE", "EXPECTATIVA (R)", "DRAWDOWN (R)"];
      table.querySelectorAll("thead th").forEach((cell, index) => {
        if (headings[index]) cell.textContent = headings[index];
      });
    }
    if (body && resolvedHours.length) {
      body.replaceChildren(...resolvedHours.map(({ hour, stats, sample }) => {
        const row = document.createElement("tr");
        const values = [
          `${String(hour).padStart(2, "0")}:00`,
          String(sample),
          hasMetric(stats.win_rate) ? `${Number(stats.win_rate).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%` : "—",
          hasMetric(stats.expectancy_r) ? `${Number(stats.expectancy_r).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} R` : "—",
          hasMetric(stats.max_drawdown_r) ? `${Number(stats.max_drawdown_r).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} R` : "—",
        ];
        values.forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        });
        return row;
      }));
    } else if (body) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 5;
      const empty = document.createElement("div");
      empty.className = "d2TableEmpty";
      const title = document.createElement("b");
      title.textContent = "Sem resultados horários resolvidos";
      const note = document.createElement("span");
      note.textContent = "Amostra insuficiente ou indisponível; não representa resultado zero.";
      empty.append(title, note);
      cell.append(empty);
      row.append(cell);
      body.replaceChildren(row);
    }
    const summary = view.querySelector(".d2ReportHeading p");
    const sourceLimit = Number.isInteger(data?.source_limit) && data.source_limit > 0
      ? data.source_limit : 10000;
    if (summary) summary.textContent = `Trade Journal · rótulos WIN/LOSS/BREAKEVEN resolvidos; pendentes excluídos · amostra limitada a ${sourceLimit.toLocaleString("pt-BR")} registros por agregado · importações MT5 não provam execução em conta real · execução não comprovada · métricas em R, sem curva patrimonial ou resultado monetário.`;
  }

  async function loadCanonicalPerformance() {
    const view = document.querySelector(".d2PerformanceView");
    const summary = view?.querySelector(".d2ReportHeading p");
    if (performanceSnapshotLoaded || performanceSnapshotLoading || !view) return;
    if (!window.Gateway?.isAuthenticated || typeof window.Gateway.httpPost !== "function") {
      if (summary) summary.textContent = "Aguardando sessão autenticada; estatísticas não consultadas.";
      return;
    }
    performanceSnapshotLoading = true;
    if (summary) summary.textContent = "Carregando agregados canônicos do Trade Journal...";
    try {
      const response = await window.Gateway.httpPost("/api/jarvis/golden/statistics", {});
      const envelope = response?.data?.asset_performance ? response
        : response?.result?.data?.asset_performance ? response.result
        : response?.data?.data?.asset_performance ? response.data
        : null;
      if (response?.ok !== true || envelope?.read_only !== true
          || envelope?.security_state !== "READ_ONLY_NO_SIDE_EFFECT"
          || !envelope?.data || typeof envelope.data !== "object") {
        throw new Error("Estatísticas canônicas indisponíveis");
      }
      renderCanonicalPerformance(envelope.data);
      performanceSnapshotLoaded = true;
    } catch {
      if (summary) summary.textContent = "Estatísticas indisponíveis · nenhum valor foi presumido como zero.";
    } finally {
      performanceSnapshotLoading = false;
    }
  }

  async function loadCanonicalOperations() {
    const view = document.querySelector(".d2OperationsView");
    const status = view?.querySelector("[data-operations-status]");
    const message = view?.querySelector("[data-operations-message]");
    const sync = view?.querySelector("[data-operations-sync]");
    if (operationsSnapshotLoaded || operationsSnapshotLoading || !view) return;
    if (!window.Gateway?.isAuthenticated || typeof window.Gateway.httpPost !== "function") {
      if (message) message.textContent = "Aguardando sessão autenticada; MT5 não foi consultado.";
      if (sync) sync.textContent = "SINCRONIZADOR · AUTENTICAÇÃO NECESSÁRIA";
      return;
    }
    operationsSnapshotLoading = true;
    if (status) status.textContent = "CONSULTA READ-ONLY EM ANDAMENTO";
    if (message) message.textContent = "Consultando a ponte canônica MT5; nenhuma ação será enviada.";
    if (sync) sync.textContent = "SINCRONIZADOR · CONSULTANDO";

    const finiteNumber = (value) => typeof value === "number" && Number.isFinite(value) ? value : null;
    const displayNumber = (value, digits = 2) => {
      const number = finiteNumber(value);
      return number === null ? "—" : number.toLocaleString("pt-BR", {
        minimumFractionDigits: digits, maximumFractionDigits: digits,
      });
    };
    const unwrap = (value) => value?.data && typeof value.data === "object" ? value.data : value || {};
    const setMetric = (name, value, detail, note) => {
      const item = view.querySelector(`[data-operations-metric="${name}"]`);
      if (!item) return;
      const strong = item.querySelector("strong");
      const paragraph = item.querySelector("p");
      const small = item.querySelector("small");
      if (strong) strong.textContent = value;
      if (paragraph) paragraph.textContent = detail;
      if (small) small.textContent = note;
    };
    const setEmptyRows = (body, columns, title, detail) => {
      if (!body) return;
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = columns;
      const empty = document.createElement("div");
      empty.className = "d2TableEmpty";
      const heading = document.createElement("b");
      heading.textContent = title;
      const explanation = document.createElement("span");
      explanation.textContent = detail;
      empty.append(heading, explanation);
      cell.append(empty);
      row.append(cell);
      body.replaceChildren(row);
    };
    const setCells = (row, values) => {
      values.forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = String(value ?? "—");
        row.append(cell);
      });
    };
    const setUnavailable = (reason) => {
      if (status) status.textContent = "SEM OBSERVAÇÃO OPERACIONAL";
      if (message) message.textContent = reason;
      if (sync) sync.textContent = "SINCRONIZADOR · INDISPONÍVEL";
      view.querySelector("[data-operations-source]")?.replaceChildren(document.createTextNode("MT5 · INDISPONÍVEL"));
      setMetric("exposure", "—", "Sem observação canônica", "Alocação · não consultada");
      setMetric("floating", "—", "Sem observação canônica", "Resultado · não consultado");
      setMetric("orders", "—", "Posições e pendentes não observadas", "Fonte operacional indisponível");
      setMetric("protection", "—", "Estado não consultado", "Nenhuma proteção foi inferida");
      setEmptyRows(view.querySelector("[data-operations-positions]"), 12,
        "Nenhuma posição carregada", "MT5 indisponível; isso não representa conta sem posições.");
      setEmptyRows(view.querySelector("[data-operations-orders]"), 11,
        "Nenhuma ordem carregada", "MT5 indisponível; nenhuma ordem foi presumida.");
    };

    try {
      const response = await window.Gateway.httpPost("/api/jarvis/golden/overview", {
        symbol: selectedPanelAsset?.provider_symbol || "", include_live: true,
      });
      const candidates = [response, response?.data, response?.result,
        response?.result?.data, response?.data?.data];
      const envelope = candidates.find((candidate) => candidate?.mt5
        && candidate.read_only === true && candidate.execution_authority === "NONE");
      if (response?.ok !== true || !envelope) throw new Error("SNAPSHOT_OPERACIONAL_INVALIDO");

      const mt5Envelope = envelope.mt5;
      const mt5 = unwrap(mt5Envelope);
      const terminal = unwrap(mt5.terminal);
      const positionsPayload = unwrap(mt5.positions);
      const ordersPayload = unwrap(mt5.orders);
      const positions = Array.isArray(positionsPayload.positions) ? positionsPayload.positions : [];
      const orders = Array.isArray(ordersPayload.orders) ? ordersPayload.orders : [];
      const sourceAvailability = String(mt5Envelope?.availability || "").toUpperCase();
      const sourceAvailable = !["UNAVAILABLE", "SOURCE_DISABLED"].includes(sourceAvailability)
        && String(terminal?.status || "").toUpperCase() === "CONNECTED";
      if (!sourceAvailable) {
        setUnavailable("MT5 não está disponível para observação; isso não significa conta sem posições ou ordens.");
        return;
      }

      status.textContent = "OBSERVAÇÃO OPERACIONAL READ-ONLY";
      message.textContent = "Snapshot MT5 reconciliado com o Control Center; nenhuma ação foi enviada.";
      sync.textContent = "SINCRONIZADOR · SINCRONIZADO";
      view.querySelector("[data-operations-source]")?.replaceChildren(document.createTextNode("MT5 · LEITURA SOMENTE"));
      const volumes = positions.map((item) => finiteNumber(item?.volume));
      const profits = positions.map((item) => finiteNumber(item?.profit));
      const volumeKnown = volumes.every((value) => value !== null);
      const profitKnown = profits.every((value) => value !== null);
      const totalVolume = volumes.reduce((sum, value) => sum + (value || 0), 0);
      const totalProfit = profits.reduce((sum, value) => sum + (value || 0), 0);
      setMetric("exposure", volumeKnown ? `${displayNumber(totalVolume)} lotes` : "—",
        `${positions.length} posição(ões) observada(s)`, "MT5 · somente leitura");
      setMetric("floating", profitKnown ? displayNumber(totalProfit) : "—",
        "Soma de PNL das posições observadas", "Sem conversão ou inferência de moeda");
      setMetric("orders", `${positions.length + orders.length}`,
        `${positions.length} posição(ões) · ${orders.length} pendente(s)`, "Contagem observada no snapshot");
      setMetric("protection", positions.length ? "OBSERVADA" : "SEM POSIÇÕES",
        positions.length ? "SL/TP exibidos por posição quando fornecidos" : "Nenhuma posição aberta observada",
        "Nenhuma proteção foi alterada");

      const positionsBody = view.querySelector("[data-operations-positions]");
      if (positions.length) {
        positionsBody.replaceChildren();
        positions.forEach((item) => {
          const row = document.createElement("tr");
          setCells(row, [item?.ticket, "NÃO INFORMADO", item?.symbol, item?.side,
            displayNumber(item?.volume), displayNumber(item?.price_open),
            displayNumber(item?.price_current), displayNumber(item?.sl),
            displayNumber(item?.tp), displayNumber(item?.profit), "READ-ONLY", "DESABILITADO"]);
          positionsBody.append(row);
        });
      } else setEmptyRows(positionsBody, 12, "Nenhuma posição observada", "Snapshot MT5 conectado sem posições abertas.");

      const ordersBody = view.querySelector("[data-operations-orders]");
      if (orders.length) {
        ordersBody.replaceChildren();
        orders.forEach((item) => {
          const row = document.createElement("tr");
          setCells(row, [item?.ticket, "MT5", item?.symbol, item?.type,
            displayNumber(item?.volume), displayNumber(item?.price), "—",
            displayNumber(item?.sl), displayNumber(item?.tp), "OBSERVADA", "READ-ONLY"]);
          ordersBody.append(row);
        });
      } else setEmptyRows(ordersBody, 11, "Nenhuma ordem pendente observada", "Snapshot MT5 conectado sem ordens pendentes.");
      view.querySelector("[data-operations-positions-state]").textContent = "MT5 · OBSERVADO";
      view.querySelector("[data-operations-orders-state]").textContent = "MT5 · OBSERVADO";
      view.querySelector("[data-operations-position-count]").textContent = String(positions.length);
      view.querySelector("[data-operations-position-volume]").textContent = volumeKnown ? displayNumber(totalVolume) : "—";
      view.querySelector("[data-operations-position-source]").textContent = "MT5 · READ-ONLY";
      operationsSnapshotLoaded = true;
    } catch {
      setUnavailable("A consulta operacional não foi reconciliada; nenhum valor foi presumido como zero.");
    } finally {
      operationsSnapshotLoading = false;
    }
  }

  const panel = document.querySelector(".d2PanelView");
  const analysisButton = panel?.querySelector("[data-panel-analysis]");
  const analysisStatus = panel?.querySelector("[data-panel-analysis-status]");
  const assetSelect = createAssetCatalogCombobox(panel?.querySelector("[data-panel-asset-select]"), {
    ensureCatalog: () => ensurePanelCatalog(),
  });
  const assetSearchStatus = panel?.querySelector("[data-panel-search-status]");
  const analysisModeSelect = panel?.querySelector("[data-panel-analysis-mode]");
  const strategyControls = panel?.querySelector("[data-panel-strategy-controls]");
  const strategySelect = panel?.querySelector("[data-panel-strategy-select]");
  const strategyStatus = panel?.querySelector("[data-panel-strategy-status]");
  const selectedAssetHeading = panel?.querySelector("[data-panel-asset-heading]");
  let discoveredAssets = [];
let trendScan = null;
let trendScanRevision = 0;
let trendScanPersisted = false;
let trendScanRecoveryChecked = false;
let trendScanRecoveryBusy = false;
let trendScanSavedAt = "";
let trendRankingPage = 0;
let trendRankingBusy = false;
let trendScanStarting = false;
let trendRankingRequestId = 0;
const trendRankingGate = createTrendRequestGate();
  let analysisHistoryUi = null;
  let selectedAnalysisMode = "INDEPENDENT";
  let selectedStrategyId = "";
  // JarvisService currently returns STRATEGY_RULESET_UNAVAILABLE for this mode.
  const strategyModeSupportedByCore = false;
  let panelAnalysisRunning = false;
  let analysisRecoveryRequestId = 0;
  let panelDiscoveryRunning = false;
  let discoveryRequestId = 0;
  let marketSnapshotRequestId = 0;
  let discoveryTimer = null;
  let marketPollTimer = null;
  let marketPollRunning = false;
  let marketPollRequested = false;
  let panelMarketSnapshot = null;
  let latestPanelAnalysis = null;
  let lastMarketDrawKey = "";
  let restoredPanelAsset = null;
  let selectedTimeframe = "M15";
  let selectedIdentityValidated = false;
  const marketPollIntervalMs = 1200;
  const marketHistoryRefreshMs = 300000;
  let marketHistoryRefreshedAt = 0;
  const chartCanvas = panel?.querySelector("[data-market-chart]");
  const chartTitle = panel?.querySelector("[data-market-chart-title]");
  const chartMeta = panel?.querySelector("[data-market-chart-meta]");
  const chartQuote = panel?.querySelector("[data-market-chart-quote]");
  const chartState = panel?.querySelector("[data-market-chart-state]");
  const chartUpdated = panel?.querySelector("[data-market-chart-updated]");
  const chartSource = panel?.querySelector("[data-market-chart-source]");

  function analysisEligibilityReason() {
    if (window.Gateway?.isAuthenticated !== true) return "AUTHENTICATION_REQUIRED";
    if (!selectedPanelAsset || !selectedIdentityValidated) return "IDENTITY_REVALIDATION_REQUIRED";
    if (selectedAnalysisMode === "STRATEGY"
        && (!selectedStrategyId || !strategyModeSupportedByCore)) return "STRATEGY_MODE_UNAVAILABLE";
    if (!panelMarketSnapshot || typeof panelMarketSnapshot !== "object") return "SNAPSHOT_UNAVAILABLE";
    const snapshotAsset = panelMarketSnapshot.asset;
    if (snapshotAsset?.provider !== selectedPanelAsset.provider
        || snapshotAsset?.asset_id !== selectedPanelAsset.provider_asset_id
        || snapshotAsset?.provider_symbol !== selectedPanelAsset.provider_symbol
        || snapshotAsset?.asset_class !== selectedPanelAsset.asset_class) {
      return "SNAPSHOT_IDENTITY_MISMATCH";
    }
    if (panelMarketSnapshot.timeframe !== selectedTimeframe) return "SNAPSHOT_TIMEFRAME_MISMATCH";
    if (panelMarketSnapshot.state?.market_data_available !== true) return "MARKET_DATA_UNAVAILABLE";
    const freshness = String(panelMarketSnapshot.state?.freshness || "UNKNOWN").toUpperCase();
    if (freshness === "STALE") return "MARKET_DATA_STALE";
    if (!["FRESH", "UNKNOWN"].includes(freshness)) return "FRESHNESS_UNAVAILABLE";
    if (selectedAnalysisMode === "INDEPENDENT") return "";
    return "ANALYSIS_MODE_UNAVAILABLE";
  }

  function analysisEligibilityMessage(reason) {
    const messages = {
      AUTHENTICATION_REQUIRED: "ANÁLISE BLOQUEADA · AUTENTICAÇÃO DO JARVIS NECESSÁRIA.",
      IDENTITY_REVALIDATION_REQUIRED: "ANÁLISE BLOQUEADA · IDENTIDADE DO ATIVO PRECISA SER VALIDADA.",
      STRATEGY_MODE_UNAVAILABLE: "ANÁLISE BLOQUEADA · MODO ESTRATÉGIA SEM ESTRATÉGIA VÁLIDA SUPORTADA.",
      SNAPSHOT_UNAVAILABLE: "ANÁLISE BLOQUEADA · AGUARDANDO SNAPSHOT DO ATIVO.",
      SNAPSHOT_IDENTITY_MISMATCH: "ANÁLISE BLOQUEADA · SNAPSHOT NÃO CORRESPONDE À IDENTIDADE SELECIONADA.",
      SNAPSHOT_TIMEFRAME_MISMATCH: "ANÁLISE BLOQUEADA · SNAPSHOT NÃO CORRESPONDE AO TIMEFRAME SELECIONADO.",
      MARKET_DATA_UNAVAILABLE: "ANÁLISE BLOQUEADA · DADOS DE MERCADO INDISPONÍVEIS.",
      MARKET_DATA_STALE: "ANÁLISE BLOQUEADA · DADOS DE MERCADO STALE.",
      FRESHNESS_UNAVAILABLE: "ANÁLISE BLOQUEADA · RECÊNCIA DOS DADOS INDISPONÍVEL.",
      ANALYSIS_MODE_UNAVAILABLE: "ANÁLISE BLOQUEADA · MODO DE ANÁLISE INDISPONÍVEL.",
    };
    return messages[reason] || "ANÁLISE BLOQUEADA · ELEGIBILIDADE NÃO CONFIRMADA.";
  }

  function analysisEligible() {
    return analysisEligibilityReason() === "";
  }

  function syncAnalysisButton() {
    const eligible = analysisEligible();
    const reason = eligible ? "" : analysisEligibilityReason();
    if (analysisButton) analysisButton.disabled = !eligible || panelAnalysisRunning;
    if (!analysisStatus || panelAnalysisRunning) return;
    if (reason) {
      analysisStatus.textContent = analysisEligibilityMessage(reason);
      analysisStatus.dataset.state = "UNAVAILABLE";
      analysisStatus.dataset.reason = reason;
      delete analysisStatus.dataset.requestId;
      delete analysisStatus.dataset.correlationId;
    } else if (analysisStatus.dataset.reason) {
      analysisStatus.textContent = "PRONTO · DADOS E IDENTIDADE ELEGÍVEIS; RECÊNCIA FINAL VALIDADA PELO CORE.";
      analysisStatus.dataset.state = "READY";
      analysisStatus.dataset.reason = "";
    }
  }

  function panelAnalysisStorageKey(asset, timeframe, mode = selectedAnalysisMode) {
    return `jarvis.desktop.golden.analysis.v2::${asset.provider_asset_id}::${timeframe}::${mode}`;
  }

  function rememberPersistedPanelAnalysis(result, asset, timeframe, mode = selectedAnalysisMode) {
    if (result?.persistence?.persisted !== true
        || typeof result.analysis_id !== "string"
        || result.analysis_mode !== mode
        || !/^panel_analysis_[A-Za-z0-9]+$/.test(result.analysis_id)) return;
    try {
      localStorage.setItem(panelAnalysisStorageKey(asset, timeframe, mode), result.analysis_id);
    } catch {}
  }

  async function recoverPersistedPanelAnalysis(asset, timeframe = selectedTimeframe,
                                               mode = selectedAnalysisMode) {
    if (!asset || !selectedIdentityValidated || panelAnalysisRunning
        || mode !== selectedAnalysisMode
        || window.Gateway?.isAuthenticated !== true
        || typeof window.Gateway.httpPost !== "function") return;
    let analysisId = "";
    try {
      analysisId = localStorage.getItem(panelAnalysisStorageKey(asset, timeframe, mode)) || "";
    } catch { return; }
    if (!/^panel_analysis_[A-Za-z0-9]+$/.test(analysisId)) return;
    const requestId = ++analysisRecoveryRequestId;
    try {
      const response = await window.Gateway.httpPost(
        "/api/jarvis/golden/panel-analysis", { action: "GET", analysis_id: analysisId });
      const envelope = [response, response?.result, response?.data, response?.data?.result]
        .find((item) => item?.analysis && typeof item.analysis === "object");
      const result = envelope?.analysis;
      if (requestId !== analysisRecoveryRequestId
          || selectedPanelAsset?.provider_asset_id !== asset.provider_asset_id
          || selectedTimeframe !== timeframe || !selectedIdentityValidated
          || envelope?.found !== true || !result
          || result.analysis_id !== analysisId
          || result.provider_asset_id !== asset.provider_asset_id
          || result.provider_symbol !== asset.provider_symbol
          || result.timeframe !== timeframe
          || result.analysis_mode !== mode) return;
      renderPanelAnalysis({ analysis: result, recovered: true }, asset);
    } catch {}
  }

  function setPanelAnalysisMode(mode) {
    const nextMode = mode === "STRATEGY" ? "STRATEGY" : "INDEPENDENT";
    if (nextMode === selectedAnalysisMode) return;
    selectedAnalysisMode = nextMode;
    selectedStrategyId = "";
    analysisRecoveryRequestId += 1;
    latestPanelAnalysis = null;
    if (strategyControls) strategyControls.hidden = nextMode !== "STRATEGY";
    if (strategySelect) strategySelect.value = "";
    invalidatePanelAnalysis("MODO DE ANÁLISE ALTERADO · RESULTADO ANTERIOR NÃO É REUTILIZADO.");
    analysisStatus.textContent = nextMode === "STRATEGY"
      ? "MODO ESTRATÉGIA · EXIGE ESTRATÉGIA VERSIONADA E SUPORTE DO CORE."
      : "MODO INDEPENDENTE · ANÁLISE SOB DEMANDA EM MÚLTIPLOS HORIZONTES.";
    analysisStatus.dataset.state = "UNAVAILABLE";
    if (nextMode === "STRATEGY") {
      if (strategySelect) strategySelect.disabled = true;
      if (strategyStatus) strategyStatus.textContent =
        "NENHUMA ESTRATÉGIA VERSIONADA E VÁLIDA DISPONÍVEL · CORE BLOQUEIA STRATEGY.";
    }
    syncAnalysisButton();
    renderAnalysisProjection();
  }

  analysisModeSelect?.addEventListener("change", () => {
    setPanelAnalysisMode(analysisModeSelect.value);
  });
  function renderAnalysisProjection() {
    if (!analysisView) return;
    const symbolChoices = analysisView.querySelector(".d2SymbolChoices");
    if (symbolChoices) {
      const identity = document.createElement("span");
      identity.className = "d2MutedTag";
      identity.textContent = selectedPanelAsset
        ? `${selectedPanelAsset.provider_symbol} · ${selectedTimeframe}` : "ATIVO NÃO SELECIONADO";
      symbolChoices.replaceChildren(identity);
    }
    analysisView.querySelector(".d2ScanButton")?.remove();

    const statusLabel = analysisView.querySelector(".d2AnalysisState span");
    const title = analysisView.querySelector(".d2AnalysisState b");
    const candidate = latestPanelAnalysis;
    const candidateSnapshotId = candidate?.result?.snapshot_id;
    const currentSnapshotId = panelMarketSnapshot?.snapshot_id;
    const snapshotMatches = !candidateSnapshotId || !currentSnapshotId
      || candidateSnapshotId === currentSnapshotId;
    const matchesSelection = candidate
      && selectedIdentityValidated
      && candidate.mode === selectedAnalysisMode
      && candidate.asset.provider === selectedPanelAsset?.provider
      && candidate.asset.provider_asset_id === selectedPanelAsset?.provider_asset_id
      && candidate.asset.provider_symbol === selectedPanelAsset?.provider_symbol
      && candidate.asset.asset_class === selectedPanelAsset?.asset_class
      && candidate.timeframe === selectedTimeframe
      && candidate.result.analysis_mode === selectedAnalysisMode
      && snapshotMatches;
    const result = matchesSelection ? candidate.result : null;
    const status = panelAnalysisRunning ? "ANALYZING" : result?.status
      || (selectedPanelAsset && !selectedIdentityValidated ? "IDENTITY_REVALIDATION_REQUIRED"
        : analysisStatus?.dataset.state === "ERROR" ? "ERROR" : "NO_ANALYSIS");
    if (title) title.textContent = "ANÁLISE GOLDENAI · RESULTADO CANÔNICO DO PAINEL";
    const freshness = result?.sources?.technical?.freshness || "UNKNOWN";
    const dataRecency = result?.context_availability?.data_recency || "UNKNOWN";
    const absoluteUtc = result?.context_availability?.absolute_utc || "UNKNOWN";
    const executionAuthority = result?.execution_authority || "UNKNOWN";
    if (statusLabel) statusLabel.textContent = selectedPanelAsset
      ? `${selectedPanelAsset.provider_symbol} · ${selectedTimeframe} · ${selectedAnalysisMode} · ${status}`
      : `ATIVO NÃO SELECIONADO · ${status}`;
    analysisView.dataset.provider = selectedPanelAsset?.provider || "";
    analysisView.dataset.providerAssetId = selectedPanelAsset?.provider_asset_id || "";
    analysisView.dataset.providerSymbol = selectedPanelAsset?.provider_symbol || "";
    analysisView.dataset.assetClass = selectedPanelAsset?.asset_class || "";
    analysisView.dataset.timeframe = selectedTimeframe;
    analysisView.dataset.snapshotId = result?.snapshot_id || "";
    analysisView.dataset.correlationId = result?.correlation_id || "";
    analysisView.dataset.dataRecency = dataRecency;
    analysisView.dataset.temporalAuthority = absoluteUtc;
    analysisView.dataset.executionAuthority = executionAuthority;

    const summaries = analysisView.querySelectorAll(".d2AnalysisSummary > div");
    const summaryLabels = ["DIREÇÃO", "CONFIANÇA DO MODELO", "CONFLUÊNCIA", "TIMEFRAME"];
    const summaryValues = [
      [result?.directional_bias || "INDISPONÍVEL", "Resultado do modelo"],
      [Number.isFinite(result?.confidence) ? `${result.confidence}%` : "INDISPONÍVEL", "Confiança informada"],
      ["INDISPONÍVEL", "Não fornecido pela análise"],
      [result ? candidate.timeframe : selectedTimeframe || "INDISPONÍVEL", "Timeframe do Painel"],
    ];
    summaries.forEach((row, index) => {
      const [value, detail] = summaryValues[index] || ["INDISPONÍVEL", "Não fornecido"];
      const strong = row.querySelector("strong");
      const small = row.querySelector("small");
      const label = row.querySelector("span");
      if (label) label.textContent = summaryLabels[index] || "DADO";
      if (strong) strong.textContent = value;
      if (small) small.textContent = detail;
    });

    const thesis = analysisView.querySelector(".d2ThesisEmpty");
    if (thesis) {
      const heading = thesis.querySelector("b");
      const body = thesis.querySelector("p");
      if (heading) heading.textContent = result ? `${result.status} · ${result.provider_symbol}` : "Sem resultado canônico para a seleção";
      if (body) body.textContent = result?.summary || "A análise só aparece aqui depois de solicitada no Painel. Trocar de aba não chama o modelo.";
    }

    const evidenceRows = analysisView.querySelectorAll(".d2ThesisPanel .d2EvidenceRows > div");
    const evidenceLabels = ["TENDÊNCIA", "ROMPIMENTO", "VOLATILIDADE", "SNAPSHOT"];
    const evidenceValues = [
      result?.trend || "INDISPONÍVEL",
      result?.breakout_context || "INDISPONÍVEL",
      result?.volatility || "INDISPONÍVEL",
      result?.snapshot_id || "INDISPONÍVEL",
    ];
    evidenceRows.forEach((row, index) => {
      const value = row.querySelector("b");
      const label = row.querySelector("span");
      if (label) label.textContent = evidenceLabels[index] || "EVIDÊNCIA";
      if (value) value.textContent = evidenceValues[index] || "INDISPONÍVEL";
    });

    const parameters = analysisView.querySelectorAll(".d2ParameterRows > div");
    const parameterValues = [result?.entry_scenario, result?.invalidation, result?.target_scenario];
    parameters.forEach((row, index) => {
      const value = row.querySelector("b");
      const note = row.querySelector("small");
      if (value) value.textContent = parameterValues[index] || "INDISPONÍVEL";
      if (note) note.textContent = result ? "Cenário analítico · não é ordem" : "Sem análise canônica";
    });

    const checklist = analysisView.querySelector(".d2ChecklistPanel .d2MutedTag");
    if (checklist) checklist.textContent = "NÃO FORNECIDO PELA ANÁLISE";
    const executionLabel = analysisView.querySelector(".d2AudioQuality");
    if (executionLabel) executionLabel.textContent = `READ-ONLY · EXECUTION_AUTHORITY ${executionAuthority}`;
    analysisView.querySelectorAll(".d2CriteriaList em").forEach((item) => {
      item.textContent = "—";
    });

    const provenanceValues = [
      result?.model?.provider
        ? `${result.model.provider}/${result.model.name || "MODELO NÃO INFORMADO"}`
        : "NÃO DISPONÍVEL",
      result?.snapshot_id || "—",
      `RECENCY ${dataRecency} · FRESHNESS ${freshness} · UTC ${absoluteUtc}`,
      result?.correlation_id || "NÃO DISPONÍVEL",
    ];
    analysisView.querySelectorAll(".d2AnalysisProvenance > span").forEach((row, index) => {
      const value = row.querySelector("b");
      if (value) value.textContent = provenanceValues[index] || "NÃO DISPONÍVEL";
    });
    const provenance = analysisView.querySelector(".d2AnalysisProvenance");
    if (provenance) provenance.dataset.temporalAuthority = absoluteUtc;
  }
  window.Gateway?.on("authenticated", () => {
    syncAnalysisButton();
    void refreshTrendMonitorStatus();
    if (activeRoute === "painel") ensurePanelCatalog();
    if (activeRoute === "inteligencia-mercado" && !trendScanRecoveryChecked && !trendScan) {
      void recoverTrendScan();
    }
  });
  window.Gateway?.on("disconnected", syncAnalysisButton);
  window.Gateway?.on("auth_error", syncAnalysisButton);

  function setMarketChartState(state, message) {
    if (!chartState) return;
    chartState.textContent = message;
    chartState.dataset.state = state;
    chartState.hidden = Array.isArray(panelMarketSnapshot?.candles)
      && panelMarketSnapshot.candles.length > 0;
  }

  function drawMarketCandles(snapshot) {
    if (!chartCanvas) return false;
    const context = chartCanvas.getContext("2d");
    const candles = Array.isArray(snapshot?.candles) ? snapshot.candles : [];
    const ordered = candles.length > 0 && candles.every((candle, index) => {
      const valid = [candle.open, candle.high, candle.low, candle.close]
        .every((value) => Number.isFinite(value) && value > 0)
        && candle.high >= Math.max(candle.open, candle.close)
        && candle.low <= Math.min(candle.open, candle.close);
      return valid && Number.isFinite(Number(candle.time_epoch))
        && (index === 0 || Number(candle.time_epoch) > Number(candles[index - 1].time_epoch));
    });
    if (!context || !ordered) {
      chartCanvas.dataset.ready = "false";
      return false;
    }
    const bounds = chartCanvas.getBoundingClientRect();
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    const width = Math.max(320, Math.floor(bounds.width));
    const height = Math.max(200, Math.floor(bounds.height));
    const lastCandle = candles[candles.length - 1];
    const first = candles[0];
    const drawKey = `${width}x${height}@${ratio}:${candles.length}:${first.time_epoch}:${lastCandle.time_epoch},${lastCandle.open},${lastCandle.high},${lastCandle.low},${lastCandle.close}`;
    if (drawKey === lastMarketDrawKey && chartCanvas.dataset.ready === "true") return true;
    lastMarketDrawKey = drawKey;
    chartCanvas.width = Math.floor(width * ratio);
    chartCanvas.height = Math.floor(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    const pad = { left: 62, right: 12, top: 12, bottom: 28 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const low = Math.min(...candles.map((item) => item.low));
    const high = Math.max(...candles.map((item) => item.high));
    const span = high - low || Math.max(Math.abs(high) * 0.001, 0.00001);
    const y = (price) => pad.top + ((high - price) / span) * plotHeight;
    context.font = "10px Consolas, monospace";
    context.textAlign = "right";
    for (let line = 0; line <= 4; line += 1) {
      const price = high - (span * line) / 4;
      const lineY = pad.top + (plotHeight * line) / 4;
      context.strokeStyle = "#2a3039";
      context.beginPath(); context.moveTo(pad.left, lineY); context.lineTo(width - pad.right, lineY); context.stroke();
      context.fillStyle = "#8893a1";
      context.fillText(price.toLocaleString(undefined, { maximumFractionDigits: 8 }), pad.left - 7, lineY + 3);
    }
    const step = plotWidth / candles.length;
    const bodyWidth = Math.max(1, Math.min(9, step * 0.68));
    candles.forEach((candle, index) => {
      const x = pad.left + step * (index + 0.5);
      const color = candle.close >= candle.open ? "#2ea043" : "#f85149";
      context.strokeStyle = color;
      context.fillStyle = color;
      context.beginPath(); context.moveTo(x, y(candle.high)); context.lineTo(x, y(candle.low)); context.stroke();
      const top = y(Math.max(candle.open, candle.close));
      const bodyHeight = Math.max(1, Math.abs(y(candle.open) - y(candle.close)));
      context.fillRect(x - bodyWidth / 2, top, bodyWidth, bodyHeight);
    });
    context.textAlign = "center";
    context.fillStyle = "#8893a1";
    for (const index of [...new Set([0, Math.floor((candles.length - 1) / 2), candles.length - 1])]) {
      const date = new Date(Number(candles[index].time_epoch) * 1000);
      const label = Number.isNaN(date.getTime()) ? "UTC ?" : date.toISOString().slice(5, 16).replace("T", " ");
      context.fillText(label, pad.left + step * (index + 0.5), height - 8);
    }
    const last = candles[candles.length - 1];
    context.strokeStyle = "rgba(227,179,65,.75)";
    context.setLineDash([4, 4]);
    context.beginPath(); context.moveTo(pad.left, y(last.close)); context.lineTo(width - pad.right, y(last.close)); context.stroke();
    context.setLineDash([]);
    chartCanvas.dataset.ready = "true";
    return true;
  }

  function clearMarketChart(message = "Selecione um ativo para carregar candles reais do MT5.") {
    panelMarketSnapshot = null;
    lastMarketDrawKey = "";
    marketHistoryRefreshedAt = 0;
    if (chartTitle) chartTitle.textContent = `GRÁFICO DO MERCADO — ${selectedPanelAsset?.provider_symbol || "SEM ATIVO"}`;
    if (chartQuote) chartQuote.textContent = "QUOTE INDISPONÍVEL";
    if (chartMeta) chartMeta.textContent = `MT5 · ${selectedTimeframe} · AGUARDANDO ATIVO`;
    if (chartUpdated) chartUpdated.textContent = "SEM ATUALIZAÇÃO";
    if (chartSource) chartSource.textContent = "MT5 · CANDLES OHLC READ-ONLY";
    if (chartCanvas) {
      const context = chartCanvas.getContext("2d");
      if (context) context.clearRect(0, 0, chartCanvas.width, chartCanvas.height);
      chartCanvas.dataset.ready = "false";
    }
    setMarketChartState("LOADING", message);
    if (analysisButton) analysisButton.disabled = true;
  }

  function renderMarketSnapshot(snapshot, asset) {
    const previousSnapshot = panelMarketSnapshot;
    const snapshotChanged = Boolean(previousSnapshot && (
      (previousSnapshot.snapshot_id && snapshot?.snapshot_id
        ? previousSnapshot.snapshot_id !== snapshot.snapshot_id
        : snapshot?.provenance?.live_change === "UPDATED"
          || previousSnapshot !== snapshot)
    ));
    panelMarketSnapshot = snapshot;
    if (snapshotChanged && latestPanelAnalysis) {
      invalidatePanelAnalysis("RESULTADO ANTERIOR INVALIDADO · NOVO SNAPSHOT MT5 RECEBIDO.");
    }
    const quote = snapshot?.quote || {};
    const state = snapshot?.state || {};
    const freshness = state.freshness || "UNKNOWN";
    const timeStatus = state.time_status !== "VERIFIED"
      || state.temporal_authority !== "VERIFIED" || freshness === "UNKNOWN" ? "TIME STATUS UNKNOWN"
      : state.market_session === "CLOSED_OR_FEED_PAUSED" ? "MARKET CLOSED / FEED PAUSED" : freshness;
    const candles = Array.isArray(snapshot?.candles) ? snapshot.candles : [];
    const currency = snapshot?.instrument?.quote_currency || "";
    const price = (value) => Number.isFinite(value)
      ? `${value.toLocaleString(undefined, { maximumFractionDigits: 8 })} ${currency}`.trim() : null;
    const quoteParts = [];
    if (price(quote.bid)) quoteParts.push(`BID ${price(quote.bid)}`);
    if (price(quote.ask)) quoteParts.push(`ASK ${price(quote.ask)}`);
    if (price(quote.last)) quoteParts.push(`LAST ${price(quote.last)}`);
    if (chartTitle) chartTitle.textContent = `GRÁFICO DO MERCADO — ${asset.provider_symbol}`;
    if (chartQuote) chartQuote.textContent = quoteParts.length ? quoteParts.join(" · ") : "QUOTE INDISPONÍVEL";
    if (chartMeta) chartMeta.textContent = `MT5 · ${selectedTimeframe} · ${timeStatus}`;
    if (chartSource) chartSource.textContent = freshness === "UNKNOWN"
      ? "EIXO · EPOCH DO PROVIDER · UTC NÃO VALIDADO" : "MT5 · CANDLES OHLC READ-ONLY · EIXO UTC";
    if (chartUpdated) {
      const fetchedAt = snapshot?.provenance?.live_received_at
        || snapshot?.provenance?.fetched_at || snapshot?.observed_at;
      const snapshotId = snapshot?.snapshot_id;
      const feedState = snapshot?.provenance?.live_change === "NO_NEW_QUOTE"
        ? "SEM NOVA COTAÇÃO" : snapshot?.provenance?.live_change === "UPDATED" ? "ATUALIZANDO" : "DADOS RECEBIDOS";
      chartUpdated.textContent = `${feedState} · ${fetchedAt || new Date().toLocaleTimeString()}${snapshotId ? ` · ${snapshotId.slice(-12)}` : ""}`;
    }
    if (selectedAssetHeading) {
      const detail = selectedAssetHeading.querySelector("small");
      if (detail) detail.textContent = `MT5 · ${asset.provider_symbol} · ${quoteParts.join(" / ") || "QUOTE INDISPONÍVEL"} · ${freshness}`;
    }
    const rendered = drawMarketCandles(snapshot);
    if (rendered) {
      setMarketChartState(timeStatus === "TIME STATUS UNKNOWN" ? "UNKNOWN_TIME" : freshness,
        timeStatus === "TIME STATUS UNKNOWN" ? "CANDLES MT5 REAIS · TIME STATUS UNKNOWN" : `CANDLES MT5 · ${timeStatus}`);
      chartState.hidden = true;
    } else {
      setMarketChartState(candles.length ? "ERROR" : snapshot?.status === "SOURCE_UNAVAILABLE" ? "SOURCE_UNAVAILABLE" : "NO_CANDLES",
        candles.length ? "Sequência OHLC inválida; os candles não foram desenhados." : snapshot?.status === "SOURCE_UNAVAILABLE" ? "Fonte MT5 indisponível." : "Nenhum candle OHLC real disponível.");
    }
    syncAnalysisButton();
    analysisStatus.textContent = freshness === "UNKNOWN"
      ? `TIME STATUS UNKNOWN · ${candles.length} CANDLES REAIS · RECÊNCIA A VALIDAR PELO CORE`
      : freshness === "STALE" ? `DADOS STALE · ${candles.length} CANDLES · GOLDENAI BLOQUEADA`
      : candles.length ? `MT5 READ-ONLY · ${selectedTimeframe} · ${candles.length} CANDLES · ${freshness}`
      : `MT5 · ${snapshot?.status || "NO_CANDLES"}`;
    analysisStatus.dataset.state = freshness === "UNKNOWN" || freshness === "STALE"
      ? "UNAVAILABLE" : snapshot?.status || "UNAVAILABLE";
  }

  function invalidatePanelAnalysis(message) {
    latestPanelAnalysis = null;
    analysisRecoveryRequestId += 1;
    analysisStatus.textContent = message;
    analysisStatus.dataset.state = "UNAVAILABLE";
    panel.querySelectorAll("[data-panel-bias]").forEach((item) => { item.textContent = "UNAVAILABLE"; });
    for (const key of ["summary", "trend", "breakout", "volatility", "confidence",
      "entry", "invalidation", "target", "strength", "provenance", "levels"]) {
      const element = panel.querySelector(`[data-panel-${key}]`);
      if (element) element.textContent = key === "summary"
        ? "A análise será gerada somente com dados reais do ativo selecionado."
        : "UNAVAILABLE";
    }
    const positionTitle = panel.querySelector(".d2PanelPosition .d2PositionEmpty b");
    const positionDetail = panel.querySelector(".d2PanelPosition .d2PositionEmpty p");
    if (positionTitle) positionTitle.textContent = "Estado da posição não consultado";
    if (positionDetail) positionDetail.textContent = "Nenhuma leitura de posição é feita para a seleção de ativo.";
    renderAnalysisProjection();
  }

  function showSelectedAsset(asset, { restored = false } = {}) {
    selectedPanelAsset = asset;
    if (selectedAssetHeading) {
      const title = selectedAssetHeading.querySelector("b");
      const detail = selectedAssetHeading.querySelector("small");
      if (title) title.textContent = asset ? `${asset.display_name} · ${asset.display_symbol}` : "Nenhum ativo selecionado";
      if (detail) detail.textContent = asset
        ? `${asset.provider} · ${asset.provider_symbol} · ${asset.asset_class} · ${restored ? "REVALIDAÇÃO NECESSÁRIA" : `${asset.source_status || "SOURCE_UNKNOWN"} · ${asset.market_data_available ? "MARKET_DATA_AVAILABLE" : asset.freshness === "STALE" ? "STALE" : "MARKET_DATA_PENDING"}`}`
        : "Busque um instrumento em uma fonte autorizada.";
    }
    syncAnalysisButton();
    if (asset && !restored) {
      try {
        localStorage.setItem(panelAssetStorageKey, JSON.stringify({
          provider: asset.provider,
          provider_asset_id: asset.provider_asset_id,
          provider_symbol: asset.provider_symbol,
          display_symbol: asset.display_symbol,
          display_name: asset.display_name,
          asset_class: asset.asset_class,
          price_unit: asset.price_unit || "",
        }));
      } catch {}
    }
  }

  async function refreshSelectedMarketSnapshot(asset) {
    const requestId = ++marketSnapshotRequestId;
    const timeframe = selectedTimeframe;
    const post = window.Gateway?.httpPost;
    if (!post || !asset) return;
    if (!panelMarketSnapshot && chartState) {
      chartState.hidden = false;
      setMarketChartState("LOADING", `LENDO MT5 · ${asset.provider_symbol} · ${timeframe}...`);
    }
    try {
      const response = await post.call(window.Gateway, "/api/jarvis/golden/market-data", {
        provider: asset.provider,
        provider_asset_id: asset.provider_asset_id,
        provider_symbol: asset.provider_symbol,
        asset_class: asset.asset_class,
        timeframe,
        count: 200,
      });
      if (requestId !== marketSnapshotRequestId
          || selectedPanelAsset?.provider_asset_id !== asset.provider_asset_id
          || selectedPanelAsset?.provider !== asset.provider
          || selectedTimeframe !== timeframe) return;
      const envelope = response?.data?.data?.asset ? response.data
        : response?.data?.asset ? response.data : response;
      const snapshot = envelope?.data?.asset ? envelope.data : envelope;
      if (!snapshot?.asset || snapshot?.ok === false
          || snapshot.asset.provider_symbol !== asset.provider_symbol
          || snapshot.timeframe !== timeframe || !Array.isArray(snapshot.candles))
        throw new Error("Identidade ou snapshot MT5 não reconciliado");
      renderMarketSnapshot(snapshot, asset);
      marketHistoryRefreshedAt = Date.now();
    } catch (error) {
      if (requestId === marketSnapshotRequestId
          && selectedPanelAsset?.provider_asset_id === asset.provider_asset_id
          && selectedTimeframe === timeframe) {
        if (panelMarketSnapshot) {
          if (chartMeta) chartMeta.textContent = `MT5 · ${timeframe} · STALE · ÚLTIMO SNAPSHOT PRESERVADO`;
          if (chartState) { chartState.hidden = true; chartState.dataset.state = "STALE"; }
          if (analysisButton) analysisButton.disabled = true;
          analysisStatus.textContent = `FALHA NA ATUALIZAÇÃO · ÚLTIMO SNAPSHOT PRESERVADO · ${error?.message || "ERRO DE REDE"}`;
          analysisStatus.dataset.state = "UNAVAILABLE";
        } else {
          setMarketChartState("ERROR", `Snapshot MT5 indisponível · ${error?.message || "ERRO DE REDE"}`);
        }
      }
    }
  }

  async function refreshLiveMarketUpdate(asset) {
    const requestId = ++marketSnapshotRequestId;
    const timeframe = selectedTimeframe;
    const post = window.Gateway?.httpPost;
    const current = panelMarketSnapshot;
    if (!post || !asset || !current || current.timeframe !== timeframe) return;
    try {
      const response = await post.call(window.Gateway, "/api/jarvis/golden/market-live", {
        provider: asset.provider, provider_asset_id: asset.provider_asset_id,
        provider_symbol: asset.provider_symbol, asset_class: asset.asset_class, timeframe,
      });
      if (requestId !== marketSnapshotRequestId
          || selectedPanelAsset?.provider_asset_id !== asset.provider_asset_id
          || selectedTimeframe !== timeframe) return;
      const envelope = response?.data?.data?.provider_symbol ? response.data
        : response?.data?.provider_symbol ? response.data : response;
      const update = envelope?.data?.provider_symbol ? envelope.data : envelope;
      if (!update?.ok || update.provider !== "MT5"
          || update.provider_symbol !== asset.provider_symbol || update.asset_class !== asset.asset_class
          || update.timeframe !== timeframe
          || !update.candle || !update.quote) throw new Error("Atualização MT5 não reconciliada");
      const candles = [...(current.candles || [])];
      const last = candles[candles.length - 1];
      const quoteChanged = ["bid", "ask", "last", "time_epoch"].some((key) =>
        Number(current.quote?.[key] ?? 0) !== Number(update.quote?.[key] ?? 0));
      let candleChanged = false;
      if (last && Number(last.time_epoch) === Number(update.candle.time_epoch)) {
        candleChanged = ["open", "high", "low", "close", "tick_volume"].some((key) =>
          Number(last[key] ?? 0) !== Number(update.candle[key] ?? 0));
        candles[candles.length - 1] = update.candle;
      } else if (!last || Number(update.candle.time_epoch) > Number(last.time_epoch)) {
        const timeframeSeconds = {M1: 60, M5: 300, M15: 900, H1: 3600, H4: 14400, D1: 86400}[timeframe];
        if (last && Number(update.candle.time_epoch) - Number(last.time_epoch) > timeframeSeconds * 1.5) {
          marketHistoryRefreshedAt = 0;
          if (chartUpdated) chartUpdated.textContent = "LACUNA TEMPORAL · RECONCILIANDO HISTÓRICO MT5";
          return;
        }
        candles.push(update.candle); candleChanged = true;
      }
      else throw new Error("Candle recebido é anterior ao último candle confirmado");
      if (candles.length > 200) candles.splice(0, candles.length - 200);
      const snapshotId = quoteChanged || candleChanged
        ? (update.snapshot_id || `market_update_${Date.now()}`)
        : current.snapshot_id;
      const next = { ...current, quote: update.quote, candles,
        snapshot_id: snapshotId,
        provenance: { ...(current.provenance || {}), live_received_at: update.received_at,
          live_change: quoteChanged || candleChanged ? "UPDATED" : "NO_NEW_QUOTE" } };
      renderMarketSnapshot(next, asset);
    } catch (error) {
      if (requestId === marketSnapshotRequestId
          && selectedPanelAsset?.provider_asset_id === asset.provider_asset_id
          && selectedTimeframe === timeframe) {
        if (chartUpdated) chartUpdated.textContent = `MT5 LIVE · FALHA DE LEITURA · ${error?.message || "ERRO"}`;
      }
    }
  }

  function stopMarketPolling() {
    if (marketPollTimer !== null) window.clearTimeout(marketPollTimer);
    marketPollTimer = null;
    marketPollRequested = false;
    marketSnapshotRequestId += 1;
  }

  function scheduleMarketPoll(delay = 0) {
    if (marketPollTimer !== null) window.clearTimeout(marketPollTimer);
    marketPollTimer = null;
    if (activeRoute !== "painel" || document.hidden || !selectedPanelAsset || !selectedIdentityValidated) return;
    if (marketPollRunning) {
      marketPollRequested = true;
      return;
    }
    marketPollTimer = window.setTimeout(async () => {
      marketPollTimer = null;
      marketPollRunning = true;
      const asset = { ...selectedPanelAsset };
      try {
        if (!panelMarketSnapshot || panelMarketSnapshot.asset?.provider_asset_id !== asset.provider_asset_id
            || panelMarketSnapshot.timeframe !== selectedTimeframe
            || Date.now() - marketHistoryRefreshedAt >= marketHistoryRefreshMs) {
          await refreshSelectedMarketSnapshot(asset);
        } else {
          await refreshLiveMarketUpdate(asset);
        }
      } finally {
        marketPollRunning = false;
      syncAnalysisButton();
      }
      const runImmediately = marketPollRequested;
      marketPollRequested = false;
      if (activeRoute === "painel" && !document.hidden && selectedPanelAsset
          && selectedIdentityValidated) scheduleMarketPoll(runImmediately ? 0 : marketPollIntervalMs);
    }, delay);
  }

  function syncMarketPolling() {
    if (activeRoute === "painel" && !document.hidden && selectedPanelAsset && selectedIdentityValidated) {
      if (marketPollTimer === null && !marketPollRunning) scheduleMarketPoll(0);
    } else stopMarketPolling();
  }

  panel?.querySelectorAll("[data-market-timeframe]").forEach((button) => {
    button.addEventListener("click", () => {
      const timeframe = button.dataset.marketTimeframe;
      if (!new Set(["M1", "M5", "M15", "H1", "H4", "D1"]).has(timeframe)
          || timeframe === selectedTimeframe) return;
      invalidatePanelAnalysis("RESULTADO ANTERIOR INVALIDADO · TIMEFRAME ALTERADO.");
      selectedTimeframe = timeframe;
      renderAnalysisProjection();
      panel.querySelectorAll("[data-market-timeframe]").forEach((item) =>
        item.setAttribute("aria-pressed", String(item === button)));
      if (panelMarketSnapshot?.timeframe !== timeframe) clearMarketChart(`CARREGANDO ${timeframe} PARA O ATIVO SELECIONADO...`);
      void recoverPersistedPanelAnalysis(selectedPanelAsset, timeframe);
      scheduleMarketPoll(0);
    });
  });
  window.addEventListener("resize", () => {
    if (panelMarketSnapshot) drawMarketCandles(panelMarketSnapshot);
  });
  document.addEventListener("visibilitychange", syncMarketPolling);
  window.addEventListener("pagehide", stopMarketPolling, { once: true });

  let catalogLoaded = false;
  let catalogLoadedAt = 0;
  let catalogObservation = { status: "UNKNOWN", observed_at: "UNKNOWN",
    enumerated_count: null, classification_counts: {} };
  const assetClassLabel = (kind) => ({FOREX: "FOREX", METALS: "METAIS", CRYPTO: "CRIPTO",
    INDICES: "ÍNDICES", STOCKS: "AÇÕES", ETF: "ETFs", COMMODITIES: "COMMODITIES",
    COMMODITIES_METALS: "COMMODITIES / METAIS", OTHER: "OUTROS",
    OTHER_UNKNOWN: "DESCONHECIDO"}[kind] || kind);
  function refreshTrendClassOptions() {
    const select = document.querySelector(".d2MarketIntelligenceView [data-trend-class-select]");
    if (!select) return;
    const present = new Set(discoveredAssets.map((asset) => String(asset.asset_class || "").toUpperCase()));
    const definitions = [
      ["FOREX", "FOREX", ["FOREX"]], ["INDICES", "ÍNDICES", ["INDICES"]],
      ["STOCKS", "AÇÕES", ["STOCKS"]], ["ETF", "ETFs", ["ETF"]],
      ["CRYPTO", "CRYPTO", ["CRYPTO"]],
      ["COMMODITIES", "COMMODITIES", ["COMMODITIES"]],
      ["METALS", "METAIS", ["METALS"]],
      ["OTHER_UNKNOWN", "OUTROS / DESCONHECIDOS", ["OTHER", "OTHER_UNKNOWN"]],
    ];
    const previous = select.value || "ALL";
    const options = [{value: "ALL", label: "TODOS"}, ...definitions
      .filter(([, , classes]) => classes.some((kind) => present.has(kind)))
      .map(([value, label]) => ({value, label}))];
    select.replaceChildren(...options.map(({value, label}) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      return option;
    }));
    select.value = options.some((option) => option.value === previous) ? previous : "ALL";
  }
  function renderAssetChoices(assets, status, sources = {}) {
    const newAssets = (Array.isArray(assets) ? assets : []).filter((asset) => asset
      && asset.provider === "MT5" && asset.provider_asset_id && asset.provider_symbol
      && asset.provider_asset_id === `mt5:${asset.provider_symbol}` && asset.asset_class
      && asset.source_available === true);
    if (status !== "CARREGANDO CATÁLOGO READ-ONLY...")
      discoveredAssets = newAssets;
    if (!assetSelect) return;
    const unavailable = ["SOURCE_UNAVAILABLE", "SOURCE_DISABLED", "SOURCE_DISABLED_BY_PROFILE"]
      .includes(sources.MT5?.status)
      || /NETWORK_ERROR|GATEWAY INDISPONÍVEL|AUTENTICAÇÃO NECESSÁRIA/.test(String(status));
    const emptyLabel = panelDiscoveryRunning && !discoveredAssets.length
      ? "Carregando catálogo MT5..."
      : discoveredAssets.length ? "Selecione um ativo disponível..."
      : unavailable ? "Catálogo MT5 indisponível"
      : catalogLoaded ? "Nenhum ativo MT5 disponível"
      : "Abrir para carregar ativos MT5";
    const selectedIndex = discoveredAssets.findIndex((asset) =>
      asset.provider === selectedPanelAsset?.provider
      && asset.provider_asset_id === selectedPanelAsset?.provider_asset_id
      && asset.provider_symbol === selectedPanelAsset?.provider_symbol
      && asset.asset_class === selectedPanelAsset?.asset_class);
    const previousValue = assetSelect.value;
    const selectedValue = selectedIndex >= 0 ? String(selectedIndex)
      : discoveredAssets.some((_asset, index) => String(index) === previousValue)
        ? previousValue : "";
    assetSelect.setCatalog(discoveredAssets, {
      selectedValue,
      emptyLabel,
      assetClassLabel,
    });
    if (assetSearchStatus) assetSearchStatus.textContent = status
      || `${discoveredAssets.length} ATIVO(S) DISPONÍVEL(IS) · MT5 READ-ONLY.`;
    analysisHistoryUi?.refreshCatalog();
    refreshTrendClassOptions();
  }

  async function searchPanelAssets(_query = "", force = false) {
    if (catalogLoaded && !force) {
      renderAssetChoices(discoveredAssets, `${discoveredAssets.length} INSTRUMENTOS DISPONÍVEIS · MT5 READ-ONLY.`);
      return;
    }
    if (panelDiscoveryRunning) return;
    const gateway = window.Gateway;
    const post = gateway?.httpPost;
    if (!gateway?.isAuthenticated || !post) {
      renderAssetChoices(discoveredAssets, !gateway?.isAuthenticated
        ? "AUTENTICAÇÃO NECESSÁRIA · CATÁLOGO NÃO CONSULTADO."
        : "GATEWAY INDISPONÍVEL · CATÁLOGO NÃO ATUALIZADO.");
      return;
    }
    const requestId = ++discoveryRequestId;
    panelDiscoveryRunning = true;
    renderAssetChoices(discoveredAssets, "CARREGANDO CATÁLOGO READ-ONLY...");
    try {
      const response = await post.call(gateway, "/api/jarvis/golden/symbol-discovery", { query: "", asset_class: "ALL" });
      if (requestId !== discoveryRequestId) return;
      const discovery = response?.data?.data?.assets ? response.data.data
        : response?.data?.assets ? response.data : response;
      const sources = discovery?.sources || {};
      const sourceStates = Object.entries(sources).map(([name, source]) => `${name}: ${source?.status || "UNKNOWN"}`);
      const refreshed = Array.isArray(discovery?.assets)
        && ["AVAILABLE", "NO_MATCH"].includes(String(discovery?.status || "").toUpperCase());
      renderAssetChoices(refreshed ? discovery.assets : discoveredAssets,
        sourceStates.join(" · ") || discovery?.status || "DISCOVERY_UNAVAILABLE", sources);
      if (refreshed) {
        catalogLoaded = true;
        catalogLoadedAt = Date.now();
        const mt5Source = sources.MT5 || {};
        const counts = mt5Source.classification_counts && typeof mt5Source.classification_counts === "object"
          ? mt5Source.classification_counts : {};
        catalogObservation = {
          status: String(mt5Source.status || "UNKNOWN").slice(0, 48),
          observed_at: String(discovery.observed_at || "UNKNOWN").slice(0, 48),
          enumerated_count: Number.isInteger(mt5Source.enumerated_count)
            ? mt5Source.enumerated_count : null,
          classification_counts: Object.fromEntries(Object.entries(counts)
            .filter(([key, value]) => ["FOREX", "METALS", "CRYPTO", "INDICES", "STOCKS", "ETF", "COMMODITIES", "OTHER_UNKNOWN"].includes(key)
              && Number.isInteger(value) && value >= 0)),
        };
        analysisHistoryUi?.refreshCatalog();
      }
      if (refreshed && restoredPanelAsset) revalidateRestoredPanelAsset();
    } catch (error) {
      if (requestId === discoveryRequestId) renderAssetChoices(discoveredAssets,
        `NETWORK_ERROR · ${error?.message || "FONTE NÃO RESPONDEU"}`);
    } finally {
      if (requestId === discoveryRequestId) {
        panelDiscoveryRunning = false;
        if (!catalogLoaded && !discoveredAssets.length && assetSelect) {
          const message = assetSearchStatus?.textContent || "CATÁLOGO MT5 INDISPONÍVEL";
          renderAssetChoices(discoveredAssets, message);
        }
      }
    }
  }

  function ensurePanelCatalog() {
    if (!catalogLoaded) searchPanelAssets("");
    else if (Date.now() - catalogLoadedAt > 60000) searchPanelAssets("", true);
  }
  analysisHistoryUi = wireGoldenAnalysisHistory(analysisView, {
    getCatalog: () => ({
      assets: discoveredAssets,
      loaded: catalogLoaded,
      loading: panelDiscoveryRunning,
      status: assetSearchStatus?.textContent || "",
    }),
    ensureCatalog: ensurePanelCatalog,
    assetClassLabel,
  });

  function selectPanelAsset(asset) {
    if (!asset) return;
    const changed = selectedPanelAsset?.provider_asset_id !== asset.provider_asset_id
      || selectedPanelAsset?.provider !== asset.provider
      || selectedPanelAsset?.provider_symbol !== asset.provider_symbol
      || selectedPanelAsset?.asset_class !== asset.asset_class;
    if (changed) invalidatePanelAnalysis("RESULTADO ANTERIOR INVALIDADO · NOVO ATIVO SELECIONADO.");
    selectedIdentityValidated = true;
    const selected = {
      provider: String(asset.provider),
      provider_asset_id: String(asset.provider_asset_id),
      provider_symbol: String(asset.provider_symbol).slice(0, 64),
      display_symbol: String(asset.display_symbol || asset.provider_symbol).slice(0, 64),
      display_name: String(asset.display_name || asset.provider_symbol),
      asset_class: String(asset.asset_class).toUpperCase(),
      price_unit: asset.price_unit || "",
      source_available: true,
      market_data_available: asset.market_data_available === true,
      freshness: String(asset.freshness || "UNKNOWN"),
      source_status: String(asset.source_status || "DISCOVERED"),
    };
    showSelectedAsset(selected);
    renderAnalysisProjection();
    analysisStatus.textContent = "IDENTIDADE RECONCILIADA · DADOS SERÃO REVALIDADOS NA ANÁLISE.";
    analysisStatus.dataset.state = "UNAVAILABLE";
    renderAssetChoices(discoveredAssets, "ATIVO SELECIONADO · IDENTIDADE MT5 PRESERVADA.");
    stopMarketPolling();
    if (changed) clearMarketChart(`CARREGANDO MT5 · ${selected.provider_symbol} · ${selectedTimeframe}...`);
    void recoverPersistedPanelAnalysis(selected, selectedTimeframe);
    scheduleMarketPoll(0);
  }
  assetSelect?.addEventListener("change", () => {
    const index = Number(assetSelect.value);
    if (Number.isInteger(index) && discoveredAssets[index])
      selectPanelAsset(discoveredAssets[index]);
  });

  const marketView = document.querySelector(".d2MarketIntelligenceView");
  const trendRanking = marketView?.querySelector("[data-trend-ranking]");
  const trendRankingBody = trendRanking?.querySelector("[data-trend-ranking-rows]");
  const trendRankingStatus = trendRanking?.querySelector("[data-trend-ranking-status]");
  const trendScanPersistence = trendRanking?.querySelector("[data-trend-scan-persistence]");
  const trendScanRecoverButton = trendRanking?.querySelector("[data-trend-scan-recover]");
  const trendRankingBatch = marketView?.querySelector("[data-trend-ranking-batch]");
  const trendRankingNext = trendRanking?.querySelector("[data-trend-ranking-next]");
  const trendRankingProgress = trendRanking?.querySelector("[data-trend-ranking-progress]");
  const trendRankingUp = marketView?.querySelector("[data-trend-ranking-up]");
  const trendRankingDown = marketView?.querySelector("[data-trend-ranking-down]");
  const trendRankingRetry = trendRanking?.querySelector("[data-trend-ranking-retry]");
  const trendRankingPause = trendRanking?.querySelector("[data-trend-ranking-pause]");
  const trendRankingExcluded = trendRanking?.querySelector("[data-trend-ranking-excluded]");
  const trendRankingExcludedDetails = trendRanking?.querySelector("[data-trend-ranking-excluded-details]");
  const trendRankingExcludedList = trendRanking?.querySelector("[data-trend-ranking-excluded-list]");
  const trendRankingPrevious = trendRanking?.querySelector("[data-trend-ranking-previous]");
  const trendRankingMore = trendRanking?.querySelector("[data-trend-ranking-more]");
  const trendRankingClassSelect = trendRanking?.querySelector("[data-trend-class-select]");
  const trendMonitorStart = trendRanking?.querySelector("[data-trend-monitor-start]");
  const trendMonitorStatus = trendRanking?.querySelector("[data-trend-monitor-status]");
  const marketFilterClass = trendRanking?.querySelector("[data-market-filter-class]");
  const marketFilterTrend = trendRanking?.querySelector("[data-market-filter-trend]");
  const marketFilterState = trendRanking?.querySelector("[data-market-filter-state]");
  const marketRankingCounts = trendRanking?.querySelector("[data-market-ranking-counts]");
  const marketAssetDetail = trendRanking?.querySelector("[data-market-asset-detail]");
  const marketAssetDetailTitle = marketAssetDetail?.querySelector("[data-market-asset-detail-title]");
  const marketAssetDetailBody = marketAssetDetail?.querySelector("[data-market-asset-detail-body]");
  const marketAssetDetailClose = marketAssetDetail?.querySelector("[data-market-asset-detail-close]");
  const panelTrendStatus = panel?.querySelector("[data-panel-trend-status]");
  const panelTrendProgress = panel?.querySelector("[data-panel-trend-progress]");
  const panelTrendUp = panel?.querySelector("[data-panel-trend-up]");
  const panelTrendDown = panel?.querySelector("[data-panel-trend-down]");
  let selectedMarketAssetId = "";

  async function refreshTrendMonitorStatus() {
    if (!trendMonitorStatus || window.Gateway?.isAuthenticated !== true) return;
    trendMonitorStatus.textContent = "MONITORAMENTO: CONSULTANDO...";
    try {
      const response = await window.Gateway.httpPost("/api/jarvis/golden/trend-scan", {
        action: "GET_MONITOR_STATUS",
      });
      const state = String(response?.monitor_state || response?.monitor?.monitor_state || "UNKNOWN").toUpperCase();
      trendMonitorStatus.textContent = `MONITORAMENTO: ${state}`;
      if (trendMonitorStart) trendMonitorStart.disabled = state === "RUNNING";
    } catch {
      trendMonitorStatus.textContent = "MONITORAMENTO: INDISPONIVEL";
    }
  }

  trendMonitorStart?.addEventListener("click", async () => {
    if (window.Gateway?.isAuthenticated !== true) {
      if (trendMonitorStatus) trendMonitorStatus.textContent = "MONITORAMENTO: AUTENTICACAO NECESSARIA";
      return;
    }
    trendMonitorStart.disabled = true;
    if (trendMonitorStatus) trendMonitorStatus.textContent = "MONITORAMENTO: INICIANDO...";
    try {
      const response = await window.Gateway.httpPost("/api/jarvis/golden/trend-scan", {
        action: "START_MONITOR",
      });
      if (response?.ok !== true) {
        if (trendMonitorStatus) trendMonitorStatus.textContent = `MONITORAMENTO: ${response?.error_code || response?.status || "BLOQUEADO"}`;
        trendMonitorStart.disabled = false;
        return;
      }
      await refreshTrendMonitorStatus();
    } catch {
      if (trendMonitorStatus) trendMonitorStatus.textContent = "MONITORAMENTO: FALHA DE TRANSPORTE";
      trendMonitorStart.disabled = false;
    }
  });

  function rankingItems() {
    return trendScan?.items || [];
  }

  function renderTrendPersistence() {
    if (trendScanPersistence) {
      trendScanPersistence.textContent = !trendScan ? "Nenhuma varredura persistida nesta sessão."
        : trendScanPersisted
          ? `PERSISTIDO · revisão ${trendScanRevision} · gravação ${trendScanSavedAt || "UNKNOWN"} · dados históricos não são dados atuais`
          : "NÃO PERSISTIDO · salve antes de avançar ou fechar o Desktop.";
    }
    if (trendScanRecoverButton) {
      trendScanRecoverButton.textContent = trendScan && !trendScanPersisted
        ? "SALVAR PENDÊNCIA" : "RECUPERAR VARREDURA";
      trendScanRecoverButton.disabled = trendRankingBusy || trendScanStarting || trendScanRecoveryBusy;
    }
  }

  async function persistTrendScan(scan = trendScan, revision = trendScanRevision,
                                  action = "SAVE", batchIndex = null,
                                  batchAssetIds = [], batchResults = []) {
    const gateway = window.Gateway;
    if (!scan || gateway?.isAuthenticated !== true || typeof gateway.httpPost !== "function") {
      trendRankingStatus.textContent = "Sessão autenticada necessária para persistir a varredura.";
      return false;
    }
    let response;
    try {
      const payload = {
        action: String(action || "SAVE").toUpperCase(), base_revision: revision,
        scan: { ...scan, contract_version: "trend-scan-v1", summary: trendScanSummary(scan) },
      };
      if (payload.action === "APPLY_BATCH") {
        payload.batch_index = Number.isInteger(batchIndex) ? batchIndex : scan.next_batch_index - 1;
        payload.batch_asset_ids = Array.isArray(batchAssetIds) ? batchAssetIds : [];
      }
      if (payload.action === "APPLY_BATCH_RESULTS") {
        payload.scan_id = scan.scan_id;
        payload.batch_index = Number.isInteger(batchIndex) ? batchIndex : scan.next_batch_index - 1;
        payload.batch_asset_ids = Array.isArray(batchAssetIds) ? batchAssetIds : [];
        payload.results = Array.isArray(batchResults) ? batchResults : [];
        payload.metadata = { asset_class_filter: scan.asset_class_filter || "ALL",
          catalog_observation: scan.catalog_observation || {} };
        delete payload.scan;
      }
      response = await gateway.httpPost("/api/jarvis/golden/trend-scan", payload);
    } catch {
      response = { ok: false, error_code: "SCAN_SAVE_TRANSPORT_FAILED" };
    }
    if (response?.ok !== true || response?.persisted !== true
      || response?.scan_id !== scan.scan_id || !Number.isInteger(response?.revision)) {
      trendScanPersisted = false;
      trendRankingStatus.textContent = `Varredura não persistida (${response?.error_code || "SCAN_SAVE_FAILED"}). Nenhum novo lote será iniciado.`;
      renderTrendPersistence();
      return false;
    }
    trendScanRevision = response.revision;
    trendScanPersisted = true;
    trendScanSavedAt = response.updated_at || "UNKNOWN";
    renderTrendPersistence();
    return true;
  }

  async function recoverTrendScan(explicit = false) {
    if (trendScanRecoveryBusy || trendRankingBusy) return;
    if (trendScan && (!explicit || !window.confirm(
      "Substituir a varredura em memória pela última versão persistida? O estado local não salvo será perdido."))) return;
    const gateway = window.Gateway;
    if (gateway?.isAuthenticated !== true || typeof gateway.httpPost !== "function") {
      trendRankingStatus.textContent = "Autenticação necessária para recuperar a varredura.";
      return;
    }
    trendScanRecoveryBusy = true;
    renderTrendPersistence();
    try {
      const response = await gateway.httpPost("/api/jarvis/golden/trend-scan", {
        action: "RECOVER",
      });
      if (response?.ok !== true) {
        trendRankingStatus.textContent = `RECUPERAÇÃO RECUSADA (${response?.error_code || "SCAN_RECOVERY_FAILED"}).`;
        return;
      }
      trendScanRecoveryChecked = true;
      if (response.found !== true) {
        trendRankingStatus.textContent = "Nenhuma varredura persistida para este dispositivo.";
        return;
      }
      const recovered = response.data;
      if (!recovered?.scan?.scan_id || !Number.isInteger(recovered.revision)
        || recovered.scan.contract_version !== "trend-scan-v1") {
        trendRankingStatus.textContent = "RECUPERAÇÃO RECUSADA (CONTRATO INVÁLIDO).";
        return;
      }
      trendScan = recovered.scan;
      trendScanRevision = recovered.revision;
      trendScanPersisted = true;
      trendScanSavedAt = recovered.updated_at || "UNKNOWN";
      trendRankingPage = 0;
      selectedMarketAssetId = "";
      trendRankingStatus.textContent = `VARREDURA RECUPERADA · ${trendScan.scan_id} · ${trendScanSummary(trendScan).evaluated}/${trendScan.universe_total} avaliados · freshness histórica não revalidada.`;
      renderTrendRanking();
    } catch {
      trendRankingStatus.textContent = "RECUPERAÇÃO RECUSADA (TRANSPORTE INDISPONÍVEL).";
    } finally {
      trendScanRecoveryBusy = false;
      renderTrendPersistence();
    }
  }

  function updateTrendRankingSummary() {
    const projection = trendScanProjection(trendScan);
    const summary = projection.summary;
    const terminal = summary.terminal;
    if (trendRankingProgress) {
      trendRankingProgress.value = summary.progress_percent;
      trendRankingProgress.max = 100;
      trendRankingProgress.setAttribute("aria-label",
        `Progresso ${summary.progress_percent}%: ${terminal} de ${summary.total} ativos em estado terminal`);
    }
    if (trendRankingBatch) {
      trendRankingBatch.textContent = trendScan
        ? `${trendScan.scan_id.slice(0, 8)} · ${summary.status} · ${terminal}/${summary.total} · ${assetClassLabel(trendScan.asset_class_filter || "ALL")}`
        : "Nenhuma varredura de mercado consultada.";
      trendRankingBatch.title = trendScan
        ? `Varredura ${trendScan.scan_id} · SHA-256 ${trendScan.universe_hash} · classe congelada: ${trendScan.asset_class_filter || "ALL"} · universo elegível congelado: ${summary.total}`
        : "";
    }
    if (marketRankingCounts) {
      marketRankingCounts.textContent = trendScan
        ? `${summary.status} · ${trendScan.scan_id.slice(0, 8)} · universo ${summary.total} · avaliados ${summary.evaluated} · classificáveis ${summary.sufficient} · insuficientes ${summary.insufficient} · indisponíveis ${summary.unavailable} · falhos ${summary.failed} · pendentes ${summary.pending} · ${summary.progress_percent}%`
        : "Nenhuma varredura de mercado consultada.";
    }
    if (trendRankingExcluded) {
      trendRankingExcluded.textContent = trendScan?.excluded?.length
        ? `${trendScan.excluded.length} excluídos: ${Object.entries(trendScan.excluded_summary || {})
          .map(([reason, count]) => `${reason}=${count}`).join(" · ")}.`
        : "";
      trendRankingExcluded.hidden = !trendScan?.excluded?.length;
    }
    if (trendRankingExcludedDetails && trendRankingExcludedList) {
      trendRankingExcludedDetails.hidden = !trendScan?.excluded?.length;
      trendRankingExcludedList.replaceChildren();
      (trendScan?.excluded || []).slice(0, 100).forEach((item) => {
        const entry = document.createElement("li");
        entry.textContent = `${item.provider_asset_id} · ${item.reason}`;
        trendRankingExcludedList.append(entry);
      });
      if ((trendScan?.excluded?.length || 0) > 100) {
        const more = document.createElement("li");
        more.textContent = `Mais ${(trendScan.excluded.length - 100)} exclusões mantidas na memória.`;
        trendRankingExcludedList.append(more);
      }
    }
    const hasPending = summary.pending > 0;
    if (trendRankingNext) {
      trendRankingNext.hidden = !trendScan || !hasPending;
      trendRankingNext.disabled = trendRankingBusy || trendScanStarting || !trendScanPersisted;
      trendRankingNext.textContent = trendScan?.paused ? "CONTINUAR VARREDURA" : "PRÓXIMO LOTE";
    }
    if (trendRankingRetry) {
      trendRankingRetry.hidden = !trendScan || !summary.failed;
      trendRankingRetry.disabled = trendRankingBusy || trendScanStarting || !trendScanPersisted;
    }
    if (trendRankingPause) {
      trendRankingPause.hidden = !hasPending || Boolean(trendScan?.paused);
      trendRankingPause.disabled = trendRankingBusy || trendScanStarting;
    }
    const run = trendRanking?.querySelector("[data-trend-ranking-run]");
    if (run) {
      run.disabled = trendRankingBusy || trendScanStarting;
      run.textContent = trendScan ? "NOVA VARREDURA" : "CONSULTAR LOTE";
    }
    renderTrendPanelSummary(projection);
    renderTrendPersistence();
  }

  function renderTrendLeaderList(container, entries, limit, emptyText) {
    if (!container) return;
    container.replaceChildren();
    entries.slice(0, limit).forEach((item) => {
      const row = document.createElement("div");
      row.className = "d2TrendLeader";
      const result = item.result;
      const score = Number(result.directional_score);
      row.textContent = `${item.asset.display_symbol || item.asset.provider_symbol} · ${item.asset.display_name || item.asset.provider_symbol} · ${assetClassLabel(item.asset.asset_class) || "DESCONHECIDO"} · ${result.trend} · ${score > 0 ? "+" : ""}${score} · ${result.alignment?.available ?? 0}/7 TF`;
      row.title = `Cobertura ${result.alignment?.available ?? 0}/7 · divergência ${result.timeframe_divergence === true ? "SIM" : result.timeframe_divergence === false ? "NÃO" : "UNKNOWN"} · extensão ${result.extended_trend_risk || "UNKNOWN"} · freshness ${result.freshness || "UNKNOWN"}`;
      container.append(row);
    });
    if (!entries.length) container.textContent = emptyText;
  }

  function renderTrendPanelSummary(projection) {
    if (!panelTrendStatus) return;
    const summary = projection.summary;
    panelTrendStatus.textContent = trendScan
      ? `${summary.status} · ${summary.evaluated}/${summary.total} ativos · ${summary.progress_percent}%`
      : "Nenhuma varredura de mercado consultada.";
    if (panelTrendProgress) {
      panelTrendProgress.value = summary.progress_percent;
      panelTrendProgress.max = 100;
    }
    renderTrendLeaderList(panelTrendUp, projection.leaders.up, 3, "Nenhuma tendência de alta avaliada.");
    renderTrendLeaderList(panelTrendDown, projection.leaders.down, 3, "Nenhuma tendência de baixa avaliada.");
  }

  function renderMarketAssetDetail(rows) {
    if (!marketAssetDetail || !marketAssetDetailBody) return;
    const item = rows.find((entry) => entry.state === "AVALIADO"
      && entry.asset?.provider_asset_id === selectedMarketAssetId);
    if (!item) {
      selectedMarketAssetId = "";
      marketAssetDetail.hidden = true;
      marketAssetDetailBody.replaceChildren();
      return;
    }
    const asset = item.asset;
    const result = item.result;
    const identity = String(asset.provider_asset_id || "");
    const score = Number.isFinite(result.directional_score)
      ? `${result.directional_score > 0 ? "+" : ""}${result.directional_score}` : "UNKNOWN";
    marketAssetDetailTitle.textContent = `${asset.display_symbol || asset.provider_symbol} · ${asset.display_name || asset.provider_symbol}`;
    marketAssetDetailBody.replaceChildren();
    const addGroup = (title, facts) => {
      if (!facts.length) return;
      const group = document.createElement("section");
      group.className = "d2MarketAssetDetailGroup";
      const heading = document.createElement("b");
      heading.textContent = title;
      const grid = document.createElement("div");
      grid.className = "d2MarketAssetDetailFacts";
      facts.forEach(([label, value, classification]) => {
        const fact = document.createElement("div");
        fact.className = "d2MarketAssetDetailFact";
        const name = document.createElement("span");
        name.textContent = label;
        const data = document.createElement("strong");
        data.textContent = String(value);
        if (classification) data.dataset.trendValue = classification;
        fact.append(name, data);
        grid.append(fact);
      });
      group.append(heading, grid);
      marketAssetDetailBody.append(group);
    };
    const frames = Array.isArray(result.evaluated_timeframes) ? result.evaluated_timeframes : [];
    const availableFrames = frames.filter((frame) => frame.status === "AVAILABLE");
    addGroup("ATIVO E VARREDURA", [
      ["CLASSE", assetClassLabel(asset.asset_class) || "UNKNOWN"],
      ["IDENTIDADE", /^mt5:[A-Za-z0-9._#-]{1,64}$/.test(identity) ? identity : "IDENTIDADE MT5 NÃO EXIBÍVEL"],
      ["SCAN ID", trendScan.scan_id],
      ["TENDÊNCIA GERAL", `${result.trend || "UNKNOWN"} ${score}`, result.trend],
      ["COBERTURA", `${availableFrames.length}/7`],
      ["ALINHAMENTO", Number.isInteger(result.alignment?.aligned)
        ? `${result.alignment.aligned}/${result.alignment.available ?? availableFrames.length}` : "UNKNOWN"],
    ]);
    addGroup("TIMEFRAMES · SCORE DIRECIONAL", TREND_TIMEFRAMES.map((timeframe) => {
      const frame = trendFramePresentation(result, timeframe);
      return [timeframe, frame.label, frame.classification];
    }));
    addGroup("HORIZONTES TÉCNICOS", [
      ["SCALP · M1 + M5", deriveTrendHorizon(result, "SCALP")],
      ["DAY · M5 + M15 + H1", deriveTrendHorizon(result, "DAY")],
      ["SWING · H1 + H4 + D1", deriveTrendHorizon(result, "SWING")],
    ]);
    const context = [];
    if (typeof result.timeframe_divergence === "boolean")
      context.push(["DIVERGÊNCIA", result.timeframe_divergence ? "SIM" : "NÃO"]);
    if (result.extended_trend_risk && result.extended_trend_risk !== "UNKNOWN")
      context.push(["EXTENSÃO", result.extended_trend_risk]);
    if (result.tick_volume_state) context.push(["TICK VOLUME", result.tick_volume_state]);
    if (result.freshness) context.push(["FRESHNESS", result.freshness]);
    if (result.temporal_authority) context.push(["AUTORIDADE TEMPORAL", result.temporal_authority]);
    if (result.absolute_utc_verified) context.push(["UTC ABSOLUTO", result.absolute_utc_verified]);
    availableFrames.forEach((frame) => {
      if (Number.isFinite(frame.volatility_percent))
        context.push([`VOLATILIDADE ${frame.timeframe}`, `${frame.volatility_percent}%`]);
      if (frame.volume_state) context.push([`VOLUME ${frame.timeframe}`, frame.volume_state]);
      if (Number.isFinite(frame.tick_volume_ratio))
        context.push([`VOLUME RELATIVO ${frame.timeframe}`, String(frame.tick_volume_ratio)]);
    });
    (Array.isArray(result.read_errors) ? result.read_errors : []).slice(0, 7).forEach((error, index) => {
      const code = String(error?.error_code || "READ_ERROR").replace(/[^A-Z0-9_.-]/gi, "_").slice(0, 80);
      context.push([`ERRO PARCIAL ${index + 1}`, code]);
    });
    addGroup("CONTEXTO DISPONÍVEL", context);
    const explanation = document.createElement("p");
    explanation.className = "d2MarketAssetDetailExplanation";
    explanation.textContent = trendTechnicalExplanation(result);
    marketAssetDetailBody.append(explanation);
    marketAssetDetail.hidden = false;
  }

  function renderTrendRanking() {
    if (!trendRankingBody) return;
    const stateValue = marketFilterState?.value || "ALL";
    const trendValue = marketFilterTrend?.value || "ALL";
    const filteredRows = filterTrendItems(trendScan, {
      assetClass: marketFilterClass?.value || "ALL", trend: trendValue, state: stateValue,
    }).sort((left, right) => {
        if (stateValue === "ALL" && left.state !== right.state)
          return left.state === "AVALIADO" ? -1 : right.state === "AVALIADO" ? 1 : 0;
        if (stateValue === "PENDING") return 0;
        if (left.state !== "AVALIADO" || right.state !== "AVALIADO") return 0;
        const leftScore = left.result?.directional_score;
        const rightScore = right.result?.directional_score;
        if (!Number.isFinite(leftScore)) return Number.isFinite(rightScore) ? 1 : 0;
        if (!Number.isFinite(rightScore)) return -1;
        if (trendValue === "BAIXA" || trendValue === "BAIXA FORTE") return leftScore - rightScore;
        if (trendValue === "ALTA" || trendValue === "ALTA FORTE") return rightScore - leftScore;
        return Math.abs(rightScore) - Math.abs(leftScore);
      });
    const pageSize = 40;
    const pageCount = Math.max(1, Math.ceil(filteredRows.length / pageSize));
    trendRankingPage = Math.max(0, Math.min(trendRankingPage, pageCount - 1));
    const rows = filteredRows.slice(trendRankingPage * pageSize, (trendRankingPage + 1) * pageSize);
    if (trendRankingPrevious) trendRankingPrevious.disabled = trendRankingPage === 0;
    if (trendRankingMore) {
      trendRankingMore.disabled = trendRankingPage + 1 >= pageCount;
      trendRankingMore.textContent = `${trendRankingPage + 1}/${pageCount} · PRÓXIMOS ATIVOS`;
    }
    trendRankingBody.replaceChildren();
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 15;
      td.textContent = !trendScan ? "Nenhuma varredura de mercado consultada."
        : stateValue === "EVALUATED" ? "Nenhum ativo avaliado neste universo."
        : stateValue === "PENDING" ? "Nenhum ativo pendente."
        : "Nenhum ativo corresponde aos filtros.";
      tr.append(td);
      trendRankingBody.append(tr);
    } else {
      rows.forEach((item, index) => {
        const row = item.result || {};
        const asset = item.asset || {};
        const score = item.state === "AVALIADO" ? row.directional_score : null;
        const availableFrames = (row.evaluated_timeframes || []).filter((frame) => frame.status === "AVAILABLE").length;
        const frameValues = TREND_TIMEFRAMES.map((timeframe) => trendFramePresentation(row, timeframe));
        const horizons = [deriveTrendHorizon(row, "SCALP"), deriveTrendHorizon(row, "DAY"), deriveTrendHorizon(row, "SWING")];
        const values = [`${asset.display_symbol || asset.provider_symbol || "—"} · ${asset.display_name || ""}`,
          ...frameValues.map((frame) => frame.label), item.state === "AVALIADO" ? row.trend : item.state,
          Number.isFinite(score) ? `${score > 0 ? "+" : ""}${score}` : "—",
          `${availableFrames}/7 · ${row.alignment?.aligned ?? 0} alinhados`,
          `${item.state === "AVALIADO" ? "AVALIADO" : item.state} · freshness ${row.freshness || "UNKNOWN"} · UTC ${row.absolute_utc_verified || "UNKNOWN"}`,
          ...horizons];
        const tr = document.createElement("tr");
        tr.title = `Cobertura ${availableFrames}/7 TF · ausentes ${((row.evaluated_timeframes || [])
          .filter((frame) => frame.status !== "AVAILABLE").map((frame) => frame.timeframe)).join(", ") || "nenhum"} · divergência ${row.timeframe_divergence === true ? "SIM" : row.timeframe_divergence === false ? "NÃO" : "UNKNOWN"} · risco de extensão ${row.extended_trend_risk || "UNKNOWN"} · autoridade temporal ${row.temporal_authority || "UNKNOWN"}`;
        values.forEach((value, valueIndex) => {
          const td = document.createElement("td");
          td.textContent = value;
          if (valueIndex >= 1 && valueIndex <= TREND_TIMEFRAMES.length)
            td.dataset.trendValue = frameValues[valueIndex - 1].classification;
          else if (["ALTA FORTE", "ALTA", "LATERAL", "BAIXA", "BAIXA FORTE", "INSUFICIENTE", "UNKNOWN"].includes(value))
            td.dataset.trendValue = value;
          if (valueIndex === 0) td.title = `${assetClassLabel(asset.asset_class) || "DESCONHECIDO"} · origem da classe ${asset.asset_class_source || "UNKNOWN"}`;
          if (valueIndex === 8 && Number.isFinite(score)) {
            const bar = document.createElement("span");
            bar.className = "d2TrendScoreBar";
            bar.style.setProperty("--trend-score-width", `${Math.min(100, Math.abs(score))}%`);
            bar.dataset.direction = score >= 0 ? "UP" : "DOWN";
            td.append(bar);
          }
          tr.append(td);
        });
        if (item.state === "AVALIADO") {
          tr.tabIndex = 0;
          tr.setAttribute("role", "button");
          tr.setAttribute("aria-label", `Destacar ${asset.display_name || asset.provider_symbol} localmente`);
          tr.dataset.trendAssetId = asset.provider_asset_id;
          tr.setAttribute("aria-selected", String(selectedMarketAssetId === asset.provider_asset_id));
        }
        trendRankingBody.append(tr);
      });
    }
    const leaders = trendLeaders(trendScan);
    const renderLeaders = (container, entries, emptyLabel) => {
      if (!container) return;
      container.replaceChildren();
      const top = entries.slice(0, 5);
      if (!top.length) {
        container.textContent = emptyLabel;
        return;
      }
      top.forEach((item) => {
        const line = document.createElement("div");
        line.className = "d2TrendLeader";
        const score = Number(item.result.directional_score);
        line.textContent = `${item.asset.display_symbol || item.asset.provider_symbol} · ${item.asset.display_name || item.asset.provider_symbol} · ${assetClassLabel(item.asset.asset_class) || "DESCONHECIDO"} · ${item.result.trend} · ${score > 0 ? "+" : ""}${score} · ${item.result.alignment?.available ?? 0}/7 TF`;
        line.title = `Cobertura ${item.result.alignment?.available ?? 0}/7 TF · divergência ${item.result.timeframe_divergence === true ? "SIM" : item.result.timeframe_divergence === false ? "NÃO" : "UNKNOWN"} · extensão ${item.result.extended_trend_risk || "UNKNOWN"} · freshness ${item.result.freshness || "UNKNOWN"} · UTC ${item.result.absolute_utc_verified || "UNKNOWN"}`;
        container.append(line);
      });
    };
    const noLeader = trendScan ? "Nenhuma tendência confirmada nos ativos avaliados."
      : "Nenhuma varredura de mercado consultada.";
    renderLeaders(trendRankingUp, leaders.up, noLeader);
    renderLeaders(trendRankingDown, leaders.down, noLeader);
    renderMarketAssetDetail(rows);
    updateTrendRankingSummary();
  }

  async function executeTrendRankingBatch(batch, retry = false) {
    if (!trendScan || !batch.length || !trendRankingStatus) return;
    if (!trendScanPersisted) {
      trendRankingStatus.textContent = "Salve a varredura antes de consultar outro lote.";
      return;
    }
    const gateway = window.Gateway;
    if (gateway?.isAuthenticated !== true || typeof gateway.httpPost !== "function") {
      trendRankingStatus.textContent = "Autenticação necessária para consultar o catálogo e o lote.";
      return;
    }
    if (trendRankingBusy || !trendRankingGate.acquire()) return;
    const batchIndex = trendScan.next_batch_index;
    const requestId = ++trendRankingRequestId;
    trendRankingBusy = true;
    updateTrendRankingSummary();
    trendRankingStatus.textContent = `Lote ${batchIndex + 1} · consultando ${batch.length} ativo(s) · até 7 TF por ativo...`;
    const correlationId = globalThis.crypto?.randomUUID?.() || `trend-${Date.now()}-${requestId}`;
    try {
      const response = await gateway.httpPost("/api/jarvis/golden/trend-ranking", {
        assets: batch.map((item) => ({
          ...item.asset,
        })),
        scan_id: trendScan.scan_id,
        universe_hash: trendScan.universe_hash,
        universe_total: trendScan.universe_total,
        asset_class_filter: trendScan.asset_class_filter || "ALL",
        batch_index: batchIndex,
        batch_total: Math.ceil(trendScan.universe_total / 4),
        batch_asset_ids: batch.map((item) => item.asset.provider_asset_id),
        excluded_count: trendScan.excluded.length,
        excluded_reason_counts: trendScan.excluded_summary,
        catalog_source: "AUTHENTICATED_MT5_SYMBOL_DISCOVERY",
        catalog_observation: catalogObservation,
        retry_of_failed_assets: retry,
        correlation_id: correlationId,
      });
      if (requestId !== trendRankingRequestId) return;
      const result = response?.data?.data?.ranked_assets ? response.data.data
        : response?.data?.ranked_assets ? response.data : response?.ranked_assets ? response : null;
      if (!result || response?.ok === false || response?.data?.ok === false) {
        const failure = new Error("RANKING_UNAVAILABLE");
        failure.code = result?.reason || response?.error_code || response?.status
          || response?.data?.error_code || response?.data?.status || "RANKING_UNAVAILABLE";
        throw failure;
      }
      applyTrendBatch(trendScan, batch, result.ranked_assets, batchIndex);
      batch.forEach((item) => {
        item.batch_correlation_id = correlationId;
        item.batch_observed_at = result.observed_at || "UNKNOWN";
      });
      trendScanPersisted = false;
      renderTrendRanking();
      if (await persistTrendScan(trendScan, trendScanRevision, "APPLY_BATCH_RESULTS",
        batchIndex, batch.map((item) => item.asset.provider_asset_id), result.ranked_assets)) {
        trendRankingStatus.textContent = `${trendScanSummary(trendScan).status} · lote persistido · freshness UNKNOWN quando não comprovada; UTC absoluto UNKNOWN.`;
      }
    } catch (error) {
      if (requestId === trendRankingRequestId) {
        const safeCode = String(error?.code || error?.error_code || "RANKING_REQUEST_FAILED")
          .replace(/[^A-Z0-9_.-]/gi, "_").slice(0, 80);
        failTrendBatch(trendScan, batch, safeCode, batchIndex);
        batch.forEach((item) => {
          item.batch_correlation_id = correlationId;
          item.batch_observed_at = "UNKNOWN";
        });
        trendScanPersisted = false;
        renderTrendRanking();
        const failedResults = batch.map((item) => ({ asset: item.asset,
          read_errors: [{ timeframe: "UNKNOWN", error_code: safeCode }],
          evaluated_timeframes: [], execution_authority: "NONE" }));
        if (await persistTrendScan(trendScan, trendScanRevision, "APPLY_BATCH_RESULTS",
          batchIndex, batch.map((item) => item.asset.provider_asset_id), failedResults)) {
          trendRankingStatus.textContent = `Lote ${batchIndex + 1} falhou (${safeCode}); resultados anteriores preservados. A retentativa é manual.`;
        }
      }
    } finally {
      trendRankingGate.release();
      if (requestId === trendRankingRequestId) {
        trendRankingBusy = false;
        updateTrendRankingSummary();
      }
    }
  }

  async function startTrendScan() {
    if (trendRankingBusy || trendScanStarting) return;
    trendScanStarting = true;
    try {
      updateTrendRankingSummary();
      trendRankingStatus.textContent = "PREPARANDO VARREDURA...";
      const selectedClass = trendRankingClassSelect?.value || "ALL";
      if (trendScan && !window.confirm(`Iniciar nova varredura para ${selectedClass} descartará o progresso atual em memória. Continuar?`)) {
        trendRankingStatus.textContent = "Nova varredura cancelada; progresso anterior preservado.";
        return;
      }
      const gateway = window.Gateway;
      if (gateway?.isAuthenticated !== true || typeof gateway.httpPost !== "function") {
        trendRankingStatus.textContent = "Autenticação necessária para consultar o catálogo e o lote.";
        return;
      }
      if (!catalogLoaded || Date.now() - catalogLoadedAt > 60000) {
        if (panelDiscoveryRunning) {
          trendRankingStatus.textContent = "Catálogo MT5 ainda está carregando.";
          return;
        }
        trendRankingStatus.textContent = "Carregando catálogo MT5 autenticado...";
        await searchPanelAssets("", true);
      }
      if (!catalogLoaded || !discoveredAssets.length || Date.now() - catalogLoadedAt > 60000) {
        trendRankingStatus.textContent = assetSearchStatus?.textContent || "Catálogo MT5 indisponível.";
        return;
      }
      const scanId = globalThis.crypto?.randomUUID?.();
      if (!scanId) throw new Error("SCAN_ID_UNAVAILABLE");
      const selectedUniverse = filterTrendCatalogByClass(discoveredAssets, selectedClass);
      if (!selectedUniverse.length) {
        trendRankingStatus.textContent = `Nenhum ativo do catálogo possui classificação comprovada para ${selectedClass}.`;
        return;
      }
      const nextScan = await createTrendScan(selectedUniverse, scanId);
      nextScan.asset_class_filter = selectedClass;
      nextScan.catalog_observation = { status: catalogObservation.status,
        observed_at: catalogObservation.observed_at,
        enumerated_count: catalogObservation.enumerated_count };
      const previousScan = trendScan;
      const previousRevision = trendScanRevision;
      const previousPersisted = trendScanPersisted;
      const previousSavedAt = trendScanSavedAt;
      trendScan = nextScan;
      trendScanRevision = 0;
      trendScanPersisted = false;
      trendRankingPage = 0;
      renderTrendRanking();
      if (!await persistTrendScan(nextScan, 0)) {
        trendScan = previousScan;
        trendScanRevision = previousRevision;
        trendScanPersisted = previousPersisted;
        trendScanSavedAt = previousSavedAt;
        renderTrendRanking();
        return;
      }
      await executeTrendRankingBatch(nextTrendBatch(trendScan));
    } catch (error) {
      const safeCode = ["SCAN_ID_UNAVAILABLE", "NO_ELIGIBLE_MT5_ASSETS", "UNIVERSE_SHA256_UNAVAILABLE"]
        .includes(error?.message) ? error.message : "SCAN_PREPARATION_FAILED";
      trendRankingStatus.textContent = `Não foi possível iniciar a varredura (${safeCode}).`;
    } finally {
      trendScanStarting = false;
      updateTrendRankingSummary();
    }
  }

  trendRanking?.querySelector("[data-trend-ranking-run]")?.addEventListener("click", () => {
    void startTrendScan();
  });
  trendRankingNext?.addEventListener("click", () => {
    if (!trendScan || trendRankingBusy || trendScanStarting || !trendScanPersisted) return;
    trendScan.paused = false;
    void executeTrendRankingBatch(nextTrendBatch(trendScan));
  });
  trendRankingRetry?.addEventListener("click", () => {
    if (!trendScan || trendRankingBusy || trendScanStarting || !trendScanPersisted) return;
    const retryBatch = retryFailedTrendBatch(trendScan);
    void executeTrendRankingBatch(retryBatch, true);
  });
  trendRankingPause?.addEventListener("click", () => {
    if (!trendScan || trendRankingBusy || trendScanStarting || !trendScanPersisted) return;
    pauseTrendScan(trendScan);
    trendScanPersisted = false;
    renderTrendRanking();
    void persistTrendScan();
  });
  trendScanRecoverButton?.addEventListener("click", () => {
    if (trendScan && !trendScanPersisted) void persistTrendScan();
    else void recoverTrendScan(true);
  });
  [marketFilterClass, marketFilterTrend, marketFilterState].forEach((select) =>
    select?.addEventListener("change", () => {
      trendRankingPage = 0;
      renderTrendRanking();
    }));
  trendRankingClassSelect?.addEventListener("change", () => {
    trendRankingPage = 0;
    renderTrendRanking();
  });
  trendRankingPrevious?.addEventListener("click", () => {
    trendRankingPage = Math.max(0, trendRankingPage - 1);
    renderTrendRanking();
  });
  trendRankingMore?.addEventListener("click", () => {
    trendRankingPage += 1;
    renderTrendRanking();
  });
  trendRankingBody?.addEventListener("click", (event) => {
    const tr = event.target.closest("[data-trend-asset-id]");
    if (tr) {
      selectedMarketAssetId = tr.dataset.trendAssetId;
      renderTrendRanking();
    }
  });
  trendRankingBody?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const tr = event.target.closest("[data-trend-asset-id]");
    if (!tr) return;
    event.preventDefault();
    selectedMarketAssetId = tr.dataset.trendAssetId;
    renderTrendRanking();
  });
  marketAssetDetailClose?.addEventListener("click", () => {
    selectedMarketAssetId = "";
    renderTrendRanking();
  });

  if (selectedPanelAsset) {
    selectedIdentityValidated = false;
    showSelectedAsset(selectedPanelAsset, { restored: true });
    invalidatePanelAnalysis("SELEÇÃO RESTAURADA · RESULTADO ANTERIOR NÃO É REUTILIZADO.");
    restoredPanelAsset = { ...selectedPanelAsset };
  } else {
    showSelectedAsset(null);
  }

  function revalidateRestoredPanelAsset() {
    if (!restoredPanelAsset) return;
    const restoredIdentity = restoredPanelAsset;
    const match = discoveredAssets.find((asset) =>
      asset.provider === restoredIdentity.provider
      && asset.provider_asset_id === restoredIdentity.provider_asset_id
      && asset.provider_symbol === restoredIdentity.provider_symbol
      && asset.asset_class === restoredIdentity.asset_class
      && asset.source_available === true);
    if (!match || selectedPanelAsset?.provider_asset_id !== restoredIdentity.provider_asset_id) {
      selectedIdentityValidated = false;
      showSelectedAsset(selectedPanelAsset, { restored: true });
      analysisStatus.textContent = "REVALIDAÇÃO FALHOU · SELECIONE NOVAMENTE UM ATIVO DISPONÍVEL.";
      return;
    }
    restoredPanelAsset = null;
    selectedIdentityValidated = true;
    showSelectedAsset({ ...restoredIdentity, asset_class: restoredIdentity.asset_class,
      source_available: true,
      freshness: match.freshness, market_data_available: match.market_data_available === true,
      source_status: match.source_status || "SOURCE_AVAILABLE" });
    analysisStatus.textContent = "IDENTIDADE REVALIDADA NO PROVIDER · ANÁLISE READ-ONLY DISPONÍVEL.";
    syncMarketPolling();
    void recoverPersistedPanelAnalysis(selectedPanelAsset, selectedTimeframe);
  }

  analysisButton?.addEventListener("click", async () => {
    if (panelAnalysisRunning) return;
    const eligibilityReason = analysisEligibilityReason();
    if (eligibilityReason) {
      analysisStatus.textContent = analysisEligibilityMessage(eligibilityReason);
      analysisStatus.dataset.state = "UNAVAILABLE";
      analysisStatus.dataset.reason = eligibilityReason;
      delete analysisStatus.dataset.requestId;
      delete analysisStatus.dataset.correlationId;
      return;
    }
    const gateway = window.Gateway;
    const submittedAsset = { ...selectedPanelAsset };
    const submittedTimeframe = selectedTimeframe;
    const submittedMode = selectedAnalysisMode;
    const submittedSnapshotId = panelMarketSnapshot?.snapshot_id || "";
    const submittedStrategyId = selectedStrategyId;
    panelAnalysisRunning = true;
    latestPanelAnalysis = null;
    syncAnalysisButton();
    analysisButton.setAttribute("aria-busy", "true");
    analysisStatus.dataset.reason = "";
    delete analysisStatus.dataset.requestId;
    delete analysisStatus.dataset.correlationId;
    analysisStatus.textContent = "COLETANDO DADOS READ-ONLY...";
    analysisStatus.dataset.state = "ANALYZING";
    const summary = panel?.querySelector("[data-panel-summary]");
    if (summary) summary.textContent = "Aguardando o resultado desta análise.";
    renderAnalysisProjection();
    try {
      const post = gateway?.httpPost;
      if (!post) throw new Error("Gateway não disponível");
      const result = await post.call(gateway, "/api/jarvis/golden/panel-analysis", {
        symbol: submittedAsset.provider_symbol,
        timeframe: submittedTimeframe,
        provider: submittedAsset.provider,
        provider_asset_id: submittedAsset.provider_asset_id,
        provider_symbol: submittedAsset.provider_symbol,
        asset_class: submittedAsset.asset_class,
        analysis_mode: submittedMode,
        request_type: "ON_DEMAND",
        analysis_style: "AUTO",
        strategy_id: submittedMode === "STRATEGY" ? submittedStrategyId : "",
        operational_mode: "ANALYSIS",
      });
      if (!result) throw new Error("Jarvis Core indisponível");
      if (result.http_failure === true) {
        const status = Number.isInteger(result.http_status) ? `HTTP ${result.http_status}` : "FALHA DE REDE";
        const errorCode = /^[A-Z0-9_]{1,80}$/.test(String(result.error_code || ""))
          ? result.error_code : "REQUEST_FAILED";
        analysisStatus.textContent = `${status} · ${errorCode}`;
        analysisStatus.dataset.state = "ERROR";
        analysisStatus.dataset.requestId = String(result.request_id || "").slice(0, 160);
        analysisStatus.dataset.correlationId = String(result.correlation_id || "").slice(0, 160);
        const summary = panel?.querySelector("[data-panel-summary]");
        if (summary) summary.textContent = "A análise não foi concluída. Nenhuma conclusão foi produzida.";
        renderAnalysisProjection();
        return;
      }
      if (selectedPanelAsset?.provider_asset_id !== submittedAsset.provider_asset_id
          || selectedTimeframe !== submittedTimeframe
          || selectedAnalysisMode !== submittedMode
          || panelMarketSnapshot?.timeframe !== submittedTimeframe
          || (submittedSnapshotId && panelMarketSnapshot?.snapshot_id !== submittedSnapshotId)) {
        analysisStatus.textContent = "RESPOSTA ANTIGA DESCARTADA · ATIVO, TIMEFRAME OU MODO ALTERADO.";
        analysisStatus.dataset.state = "UNAVAILABLE";
      } else {
        renderPanelAnalysis(result, submittedAsset, submittedMode);
      }
    } catch (error) {
      analysisStatus.textContent = "ERRO · " + (error?.message || "análise não concluída");
      analysisStatus.dataset.state = "ERROR";
      renderAnalysisProjection();
    } finally {
      panelAnalysisRunning = false;
      syncAnalysisButton();
      analysisButton.removeAttribute("aria-busy");
      renderAnalysisProjection();
    }
  });

  function renderPanelAnalysis(envelope, selectedAsset, submittedMode = selectedAnalysisMode) {
    const recovered = envelope?.recovered === true;
    const result = envelope?.analysis || envelope?.result || envelope?.data || envelope;
    if (!result || typeof result !== "object") throw new Error("Resposta estruturada ausente");
    if (result.provider_asset_id !== selectedAsset.provider_asset_id
        || result.provider_symbol !== selectedAsset.provider_symbol) {
      invalidatePanelAnalysis("IDENTIDADE DA RESPOSTA NÃO CORRESPONDE AO ATIVO SELECIONADO.");
      return;
    }
    if (result.analysis_mode !== submittedMode || submittedMode !== selectedAnalysisMode) {
      invalidatePanelAnalysis("MODO DA RESPOSTA NÃO CORRESPONDE À ANÁLISE SELECIONADA.");
      return;
    }
    if (result.snapshot_id && panelMarketSnapshot?.snapshot_id
        && result.snapshot_id !== panelMarketSnapshot.snapshot_id) {
      invalidatePanelAnalysis("SNAPSHOT DA RESPOSTA NÃO CORRESPONDE AO MT5 ATUAL.");
      return;
    }
    if (result.status === "ERROR") {
      if (!recovered) rememberPersistedPanelAnalysis(result, selectedAsset, selectedTimeframe, submittedMode);
      latestPanelAnalysis = {
        asset: { ...selectedAsset },
        timeframe: selectedTimeframe,
        mode: submittedMode,
        result,
      };
      renderAnalysisProjection();
      const rawCode = String(result.model_error_code || result.validation_error_code || "");
      const code = /^[A-Z0-9_]{1,80}$/.test(rawCode) ? rawCode : "";
      analysisStatus.textContent = `${recovered ? "RECUPERADA · " : ""}${submittedMode} · ${code
        ? `ANÁLISE NÃO CONCLUÍDA · ${code}` : "ANÁLISE NÃO CONCLUÍDA · FALHA DO CORE"}`;
      analysisStatus.dataset.state = "ERROR";
      const summary = panel.querySelector("[data-panel-summary]");
      if (summary) summary.textContent = "A análise falhou. Nenhuma conclusão foi produzida.";
      return;
    }
    if (!["COMPLETE", "PARTIAL", "INSUFFICIENT_DATA", "STALE", "UNAVAILABLE",
      "SOURCE_DISABLED", "STRATEGY_UNAVAILABLE", "MONITORING_DISABLED",
      "INVALID_REQUEST"].includes(result.status)) {
      invalidatePanelAnalysis(`DADOS DO ATIVO INDISPONÍVEIS · ${result.status || "UNKNOWN"}.`);
      return;
    }
    if (!recovered) rememberPersistedPanelAnalysis(result, selectedAsset, selectedTimeframe, submittedMode);
    latestPanelAnalysis = {
      asset: { ...selectedAsset },
      timeframe: selectedTimeframe,
      mode: submittedMode,
      result,
    };
    renderAnalysisProjection();
    const freshness = result.sources?.technical?.freshness || "UNKNOWN";
    analysisStatus.textContent = `${recovered ? "RECUPERADA · " : ""}${submittedMode} · ${result.status} · ${result.display_name || selectedAsset.display_name} · ${result.provider_symbol} · ${freshness}`;
    analysisStatus.dataset.state = result.status || "UNAVAILABLE";
    const assetDetail = selectedAssetHeading?.querySelector("small");
    const quote = result.quote || panelMarketSnapshot?.quote || {};
    const quoteLabel = Number.isFinite(quote.last)
      ? `LAST ${quote.last.toLocaleString(undefined, { maximumFractionDigits: 8 })}`
      : [Number.isFinite(quote.bid) ? `BID ${quote.bid.toLocaleString(undefined, { maximumFractionDigits: 8 })}` : "",
        Number.isFinite(quote.ask) ? `ASK ${quote.ask.toLocaleString(undefined, { maximumFractionDigits: 8 })}` : ""].filter(Boolean).join(" / ")
        || "QUOTE INDISPONÍVEL";
    if (assetDetail) assetDetail.textContent = `${result.provider} · ${result.provider_symbol} · ${quoteLabel} · ${freshness}`;
    const biases = panel.querySelectorAll("[data-panel-bias]");
    const summary = panel.querySelector("[data-panel-summary]");
    const trend = panel.querySelector("[data-panel-trend]");
    const breakout = panel.querySelector("[data-panel-breakout]");
    const volatility = panel.querySelector("[data-panel-volatility]");
    const confidence = panel.querySelector("[data-panel-confidence]");
    biases.forEach((item) => { item.textContent = result.directional_bias || "UNAVAILABLE"; });
    if (summary) summary.textContent = result.summary || "Sem resumo estruturado.";
    if (trend) trend.textContent = result.trend || "UNAVAILABLE";
    if (breakout) breakout.textContent = result.breakout_context || "UNAVAILABLE";
    if (volatility) volatility.textContent = result.volatility || "UNAVAILABLE";
    if (confidence) confidence.textContent = Number.isFinite(result.confidence)
      ? `${result.confidence}%` : "UNAVAILABLE";
    panel.querySelector("[data-panel-entry]").textContent = result.entry_scenario || "UNAVAILABLE";
    panel.querySelector("[data-panel-invalidation]").textContent = result.invalidation || "UNAVAILABLE";
    panel.querySelector("[data-panel-target]").textContent = result.target_scenario || "UNAVAILABLE";
    const strength = result.algorithmic_strength;
    panel.querySelector("[data-panel-strength]").textContent = Number.isFinite(strength?.score)
      ? `${strength.score} · score do scanner, não probabilidade` : "UNAVAILABLE";
    if (confidence?.previousElementSibling) confidence.previousElementSibling.textContent = "CONFIANÇA DO MODELO · NÃO PROBABILIDADE";
    const positionTitle = panel.querySelector(".d2PanelPosition .d2PositionEmpty b");
    const positionDetail = panel.querySelector(".d2PanelPosition .d2PositionEmpty p");
    if (positionTitle) positionTitle.textContent = result.position_state === "NOT_REQUESTED"
      ? "Estado da posição não consultado" : result.position_state === "NO_POSITION"
      ? "Nenhuma posição aberta" : result.position_state === "OPEN_POSITION_READ_ONLY"
        ? "Posição aberta observada" : "Estado da posição indisponível";
    if (positionDetail) positionDetail.textContent = result.position_state === "NOT_REQUESTED"
      ? "Esta leitura não consulta conta ou posições; nenhum estado é presumido."
      : result.position_state === "MT5_UNAVAILABLE"
      ? "MT5 não consultado ou indisponível; isso não significa conta sem posições."
      : "Estado observado por fonte canônica read-only; nenhuma ação foi executada.";
    const provenance = panel.querySelector("[data-panel-provenance]");
    const context = result.context_availability || {};
    if (provenance) provenance.textContent = result.snapshot_id
      ? `RADAR ${context.radar || "UNKNOWN"} · SCANNER ${context.scanner || "UNKNOWN"} · MACRO ${context.macro || "UNKNOWN"} · NEWS ${context.news || "UNKNOWN"} · TÉCNICO ${context.technical_freshness || "UNKNOWN"} · ${result.model?.provider || "SEM MODELO"}/${result.model?.name || ""}`
      : "PROVENIÊNCIA NÃO DISPONÍVEL";
    const notice = panel.querySelector("[data-panel-demo-notice]");
    if (notice) notice.textContent = result.status === "COMPLETE"
      ? "ANÁLISE REAL · SOMENTE LEITURA · LIVE NÃO AUTORIZADO"
      : result.status === "PARTIAL"
        ? "ANÁLISE PARCIAL · CONSULTE O ESTADO DE CADA FONTE · LIVE NÃO AUTORIZADO"
        : `ANÁLISE ${result.status || "INDISPONÍVEL"} · SEM DADOS TÉCNICOS CONFIRMADOS · LIVE NÃO AUTORIZADO`;
  }

  function arenaEscape(value) {
    return String(value ?? "—").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[char]));
  }

  function arenaMetric(metrics, key, fallback = "—") {
    const value = metrics?.[key];
    return value === null || value === undefined || value === "" ? fallback : value;
  }

  function renderGoldenArenaReport(envelope) {
    const view = document.querySelector(".d2ArenaView");
    if (!view) return;
    const status = view.querySelector("[data-arena-status]");
    const security = view.querySelector("[data-arena-security]");
    const summary = view.querySelector("[data-arena-summary]");
    const ranking = view.querySelector("[data-arena-ranking]");
    const rankingMeta = view.querySelector("[data-arena-ranking-meta]");
    const validation = view.querySelector("[data-arena-validation]");
    const validationStatus = view.querySelector("[data-arena-validation-status]");
    const provenance = view.querySelector("[data-arena-provenance]");
    const report = envelope?.report;
    if (!envelope?.ok || !report || typeof report !== "object") {
      const reason = envelope?.error_code || "ARENA_REPORT_UNAVAILABLE";
      if (status) status.textContent = `INDISPONÍVEL · ${reason}`;
      if (security) security.textContent = "READ-ONLY · SIMULATION-ONLY · EXECUTION_AUTHORITY=NONE · ORDENS REAIS: NÃO";
      if (rankingMeta) rankingMeta.textContent = "RELATÓRIO NÃO DISPONÍVEL";
      if (ranking) ranking.innerHTML = `<tr><td colspan="6">${arenaEscape(envelope?.message || "Relatório da Arena indisponível.")}</td></tr>`;
      if (validationStatus) validationStatus.textContent = "NOT_VALIDATED";
      if (validation) validation.textContent = "Nenhuma validação foi carregada nesta sessão.";
      if (provenance) provenance.textContent = `PROVENIÊNCIA · ${arenaEscape(reason)}`;
      return;
    }
    const run = report.run || {};
    const reportSecurity = report.security || envelope.security || {};
    const validationData = report.validation || {};
    const agents = Array.isArray(report.agents) ? report.agents : [];
    const winner = validationData.winner || "NENHUM";
    if (status) status.textContent = `${arenaEscape(run.status || "SIMULATION")} · ${arenaEscape(validationData.status || "NOT_VALIDATED")}`;
    if (security) security.textContent = `READ-ONLY: ${reportSecurity.read_only === true ? "SIM" : "NÃO"} · SIMULATION-ONLY: ${reportSecurity.simulation_only === true ? "SIM" : "NÃO"} · EXECUTION_AUTHORITY=${arenaEscape(reportSecurity.execution_authority || "NONE")} · ORDENS REAIS: NÃO`;
    if (summary) summary.innerHTML = [
      ["RUN", run.run_id || "—", "Identidade do replay"],
      ["SNAPSHOTS", run.snapshot_count ?? "—", "Eventos observados"],
      ["FONTE", run.source_kind || "—", run.provenance || "Proveniência não informada"],
      ["VENCEDOR APROVADO", winner, validationData.status || "Validação não concluída"],
    ].map(([label, value, detail]) => `<article><span>${arenaEscape(label)}</span><strong>${arenaEscape(value)}</strong><small>${arenaEscape(detail)}</small></article>`).join("");
    if (rankingMeta) rankingMeta.textContent = `${agents.length} AGENTES · ${arenaEscape(run.symbol || "XAUUSD")} · ${arenaEscape(run.source_kind || "REPLAY")}`;
    if (ranking) ranking.innerHTML = agents.length ? agents.map((row) => {
      const metrics = row.metrics || {};
      const pf = arenaMetric(metrics, "profit_factor");
      return `<tr><td>${arenaEscape(row.rank ?? "—")}</td><td><strong>${arenaEscape(row.agent)}</strong></td><td>${arenaEscape(arenaMetric(metrics, "net_pnl", 0))}</td><td>${arenaEscape(arenaMetric(metrics, "trades", 0))}</td><td>${arenaEscape(pf)}</td><td>${arenaEscape(arenaMetric(metrics, "max_drawdown", 0))}</td></tr>`;
    }).join("") : `<tr><td colspan="6">Nenhum agente foi carregado.</td></tr>`;
    if (validationStatus) validationStatus.textContent = validationData.status || "NOT_VALIDATED";
    if (validation) validation.innerHTML = `<b>${arenaEscape(validationData.reason || "Critérios de validação ainda não concluídos.")}</b><p>Walk-forward: ${arenaEscape(validationData.walk_forward?.status || "—")} · OOS: ${arenaEscape(validationData.out_of_sample ? "RESERVADO" : "—")} · Estresse: ${arenaEscape(validationData.stress?.status || "—")} · Paper: ${arenaEscape((validationData.paper_sessions || []).length)}</p>`;
    if (provenance) provenance.textContent = `PROVENIÊNCIA · ${arenaEscape(run.provenance || "NÃO INFORMADA")} · ATUALIZADO ${arenaEscape(run.generated_at || "—")}`;
  }

  async function loadGoldenArenaReport() {
    if (arenaReportLoading || arenaReportLoaded) return;
    const view = document.querySelector(".d2ArenaView");
    const status = view?.querySelector("[data-arena-status]");
    if (!window.Gateway?.isAuthenticated) {
      if (status) status.textContent = "AUTENTICAÇÃO NECESSÁRIA";
      return;
    }
    arenaReportLoading = true;
    if (status) status.textContent = "CONSULTANDO RELATÓRIO...";
    try {
      const envelope = await window.Gateway.httpGet("/api/jarvis/golden/arena/report");
      arenaReportLoaded = true;
      renderGoldenArenaReport(envelope);
    } catch {
      arenaReportLoaded = true;
      renderGoldenArenaReport({ok: false, error_code: "ARENA_GATEWAY_FAILURE", message: "Falha ao consultar a Arena."});
    } finally {
      arenaReportLoading = false;
    }
  }

  const observer = new MutationObserver(() => {
    if (navigationPending) return;
    const activeView = workspace.querySelector(".gView:not([hidden])");
    const route = viewRoutes[activeView?.dataset.view];
    if (route && route !== activeRoute) {
      activeRoute = route;
      root.dataset.d2Route = route;
      syncMarketPolling();
      document.querySelectorAll("#d2Navigation [data-d2-route]").forEach((button) => {
        if (button.dataset.d2Route === route) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
      });
    }
  });
  observer.observe(workspace, { subtree: true, attributes: true, attributeFilter: ["hidden", "class"] });

  renderTrendRanking();
  renderAnalysisProjection();
  selectRoute("painel");
}

function hydrateDemoViews() {
  const panel = document.querySelector(".d2PanelView");
  const analysis = document.querySelector(".d2AnalysisView");
  const operations = document.querySelector(".d2OperationsView");
  const performance = document.querySelector(".d2PerformanceView");
  const history = document.querySelector(".d2HistoryView");
  if (!panel || !analysis || !operations || !performance || !history) return;
  queueMicrotask(() => wireTradeJournalHistory(history));

  panel.innerHTML = `
    <div class="d2DemoNotice" data-panel-demo-notice role="status">DADOS NÃO CONSULTADOS · NENHUM VALOR DEMONSTRATIVO SERÁ APRESENTADO COMO REAL</div>
    <div class="d2PanelMetrics" aria-label="Resumo sem evidência">
      <article class="d2Metric"><span>OPERAÇÕES</span><strong>—</strong><small>evidência histórica indisponível</small><i class="d2MetricIcon" aria-hidden="true">▥</i></article>
      <article class="d2Metric"><span>TAKE</span><strong>—</strong><small>amostra canônica indisponível</small><i class="d2MetricIcon d2MetricSuccess" aria-hidden="true">↑</i></article>
      <article class="d2Metric"><span>STOP</span><strong>—</strong><small>amostra canônica indisponível</small><i class="d2MetricIcon d2MetricDanger" aria-hidden="true">↓</i></article>
      <article class="d2Metric"><span>RESULTADO</span><strong>—</strong><small>resultado histórico indisponível</small><i class="d2MetricIcon" aria-hidden="true">$</i></article>
    </div>
    <div class="d2PanelColumns d2PanelDonorColumns">
      <section class="d2DonorSurface d2PanelAnalysis"><header class="d2DonorSectionTitle"><b>● &nbsp; GoldenAI — Análise do Mercado</b><span data-panel-analysis-status data-state="UNAVAILABLE">AGUARDANDO AÇÃO</span></header>
        <div class="d2PanelAssetHeading" data-panel-asset-heading><b>Nenhum ativo selecionado</b><small>Busque um instrumento em uma fonte autorizada.</small></div>
        <div class="d2SignalCard"><strong data-panel-bias>UNAVAILABLE</strong><p data-panel-summary>A análise será gerada somente após consulta read-only das fontes canônicas.</p></div>
        <div class="d2EvidenceRows"><div><span>TENDÊNCIA</span><b data-panel-trend>UNAVAILABLE</b></div><div><span>ROMPIMENTO</span><b data-panel-breakout>UNAVAILABLE</b></div><div><span>VOLATILIDADE</span><b data-panel-volatility>UNAVAILABLE</b></div><div><span>CONFIANÇA</span><b data-panel-confidence>UNAVAILABLE</b></div></div>
        <div class="d2DemoWarning">Cenários são analíticos. Não autorizam nem executam ordem.</div>
        <div class="d2AudioSummary"><span class="d2AudioGlyph">◉</span><span><b>FONTES</b><small data-panel-provenance>Snapshot, freshness e proveniência aguardando consulta.</small></span><span class="d2MutedTag">READ-ONLY</span></div>
      </section>
      <section class="d2DonorSurface d2PanelPosition"><header class="d2DonorSectionTitle"><b>▣ &nbsp; Situação da Posição</b><span class="d2OutlineTag">READ-ONLY</span></header>
        <div class="d2PositionEmpty"><strong>◇</strong><b>Estado da posição não consultado</b><p>Sem observação MT5 read-only; isso não significa conta sem posições.</p></div>
        <div class="d2UnavailableReadout"><span>FORÇA ALGORÍTMICA GOLDENAI</span><strong data-panel-strength>UNAVAILABLE</strong><small>Sem score canônico disponível.</small></div>
      <div class="d2PanelAssetPicker">
        <label>MODO DE ANÁLISE
          <select data-panel-analysis-mode aria-label="Selecionar modo da análise GoldenAI">
            <option value="INDEPENDENT" selected>Análise independente</option>
            <option value="STRATEGY">Estratégia definida</option>
          </select>
        </label>
        <div data-panel-strategy-controls hidden>
          <label>ESTRATÉGIA VERSIONADA
            <select data-panel-strategy-select aria-label="Selecionar estratégia versionada" disabled>
              <option value="">Nenhuma estratégia versionada e válida</option>
            </select>
          </label>
          <div class="d2PanelAssetStatus" data-panel-strategy-status role="status">Nenhuma estratégia versionada e válida disponível; o Core mantém o modo bloqueado.</div>
        </div>
        <label>ATIVO · MT5
          <div data-panel-asset-select></div>
        </label>
        <div class="d2PanelAssetStatus" data-panel-search-status role="status">Catálogo carregado sob demanda pela sessão autenticada.</div>
      </div>
        <button type="button" class="d2DonorButton" data-panel-analysis disabled>⚡ &nbsp; FAZER ANÁLISE COM GOLDENAI</button>
      </section>
      <section class="d2DonorSurface d2PanelPlan"><header class="d2DonorSectionTitle"><b>● &nbsp; Plano Operacional</b><span class="d2OutlineTag">ANÁLISE / CENÁRIO</span></header>
        <div class="d2PlanUnavailable"><span>DIREÇÃO</span><b data-panel-bias>UNAVAILABLE</b></div>
        <div class="d2PlanLevels"><div><span>CENÁRIO DE ENTRADA</span><strong data-panel-entry>UNAVAILABLE</strong></div><div><span>INVALIDAÇÃO</span><strong data-panel-invalidation>UNAVAILABLE</strong></div><div><span>CENÁRIO-ALVO</span><strong data-panel-target>UNAVAILABLE</strong></div></div>
        <div class="d2PlanRisk"><span>RISCO <b>UNAVAILABLE</b></span><span>RETORNO <b>UNAVAILABLE</b></span><span>RELAÇÃO RISCO/RETORNO <b>UNAVAILABLE</b></span></div>
        <div class="d2SafetyNote">Cenário analítico, não é ordem nem autorização de execução.</div>
      </section>
    </div>
    <div class="d2PanelBottom">
      <section class="d2DonorSurface d2PanelChart"><header class="d2DonorSectionTitle"><b data-market-chart-title>GRÁFICO DO MERCADO — SEM ATIVO</b><span data-market-chart-meta>MT5 · M15 · AGUARDANDO ATIVO</span></header><div class="d2MarketChartToolbar" role="group" aria-label="Período do gráfico"><span data-market-chart-quote>QUOTE INDISPONÍVEL</span><div data-market-timeframes class="d2MarketTimeframes"><button type="button" data-market-timeframe="M1" aria-pressed="false">M1</button><button type="button" data-market-timeframe="M5" aria-pressed="false">M5</button><button type="button" data-market-timeframe="M15" aria-pressed="true">M15</button><button type="button" data-market-timeframe="H1" aria-pressed="false">H1</button><button type="button" data-market-timeframe="H4" aria-pressed="false">H4</button><button type="button" data-market-timeframe="D1" aria-pressed="false">D1</button></div></div><div class="d2PanelChartFrame"><canvas data-market-chart role="img" aria-label="Candles reais do MetaTrader 5 aguardando ativo"></canvas><div class="d2MarketChartState" data-market-chart-state role="status">Selecione um ativo para carregar candles reais do MT5.</div></div><footer class="d2ChartLegend"><span data-market-chart-source>MT5 · CANDLES OHLC READ-ONLY</span><span data-market-chart-updated>SEM ATUALIZAÇÃO</span></footer>
        <div class="d2PanelTrendSummary" aria-labelledby="d2PanelTrendTitle">
          <header class="d2DonorSectionTitle"><b id="d2PanelTrendTitle">FORÇA DE TENDÊNCIA</b><span data-panel-trend-status>Nenhuma varredura de mercado consultada.</span></header>
          <progress data-panel-trend-progress max="100" value="0" aria-label="Progresso da varredura de tendências"></progress>
          <div class="d2PanelTrendLeaders"><section><b>ALTAS</b><div data-panel-trend-up>Nenhuma tendência de alta avaliada.</div></section><section><b>BAIXAS</b><div data-panel-trend-down>Nenhuma tendência de baixa avaliada.</div></section></div>
          <button type="button" class="d2TextAction" data-d2-route="inteligencia-mercado">ABRIR INTELIGÊNCIA DE MERCADO →</button>
        </div>
      </section>
      <section class="d2DonorSurface d2PanelHistory"><header class="d2DonorSectionTitle"><b>Histórico de Operações</b><button type="button" class="d2TextAction" data-d2-route="historico">Ver todas →</button></header><div class="d2MiniLedger d2PanelHistoryEmpty"><div>Nenhum registro canônico consultado</div></div><div class="d2ReadOnlyFooter">HISTÓRICO INDISPONÍVEL · NÃO É EVIDÊNCIA DE ZERO OPERAÇÕES</div></section>
    </div>`;

  return;

  analysis.innerHTML = `
    <div class="d2DemoNotice" role="note">DEMONSTRAÇÃO · CONTEÚDO ILUSTRATIVO DOS PRINTS · SEM LEITURA DE MERCADO, MT5 OU PROVEDOR</div>
    <div class="d2AnalysisToolbar"><div class="d2SymbolChoices" role="group" aria-label="Ativo ilustrativo"><button type="button" data-d2-symbol="XAU/USD" aria-pressed="true">XAU/USD</button><button type="button" data-d2-symbol="EUR/USD" aria-pressed="false">EUR/USD</button><button type="button" data-d2-symbol="GBP/USD" aria-pressed="false">GBP/USD</button><button type="button" data-d2-symbol="BTC/USD" aria-pressed="false">BTC/USD</button></div><div class="d2AnalysisState"><b>ANÁLISE GOLDENAI · SINAL ATIVO: VIÉS DE BAIXA</b><span>LIA NEURAL V2.4 · TF M15 / H1 · DADOS DEMONSTRATIVOS</span></div><button type="button" class="d2ScanButton" disabled>⚡ FORÇAR NOVA VARREDURA COMPLETA</button></div>
    <div class="d2AudioSummary"><span class="d2AudioGlyph">≋</span><span><b>Síntese de Mercado em Áudio Neural</b><small>A Lia sintetizou uma leitura ilustrativa de liquidez e fluxo para XAU/USD.</small></span><span class="d2AudioQuality">128KBPS HQ · DEMO</span><button type="button" disabled aria-label="Áudio desabilitado">▶</button><time>00:41</time></div>
    <div class="d2AnalysisColumns"><div class="d2AnalysisPrimary">
      <section class="d2DonorSurface d2ThesisPanel"><header class="d2DonorSectionTitle"><b>◉ &nbsp; Tese Operacional &amp; Recomendação</b><span class="d2MutedTag">DEMONSTRAÇÃO</span></header><div class="d2AnalysisSummary"><div><span>DIREÇÃO SUGERIDA</span><strong>VENDA</strong><small>Short Bias</small></div><div><span>FORÇA DO ALGORITMO</span><strong>8.5 / 10</strong><small>85% confiança</small></div><div><span>FILTROS VALIDADOS</span><strong>6 de 7</strong><small>Confluência alta</small></div></div><div class="d2DemoText"><b>[LIA ENGINE · TEXTO DO PRINT]</b> Absorção ilustrativa no topo asiático com reversão de fluxo em M15. Médias exponenciais alinhadas em vetor descendente. Exemplo estático, sem leitura ou validação de mercado.</div><div class="d2EvidenceRows"><div><span>RELAÇÃO RISCO/RETORNO</span><b>1 : 3,15 (exemplo)</b></div><div><span>STOP</span><b>100 pips (exemplo)</b></div><div><span>BREAK-EVEN</span><b>+190 pts (exemplo)</b></div><div><span>ALVO MÁX.</span><b>+600 pts (exemplo)</b></div></div></section>
      <section class="d2DonorSurface d2ParametersPanel"><header class="d2DonorSectionTitle"><b>▣ &nbsp; Parâmetros de Entrada MetaTrader 5</b><span class="d2MutedTag">EXEMPLOS · SEM MT5</span></header><div class="d2ParameterRows"><div><span>ENTRADA A MERCADO</span><b>4.139,14</b><small>Gatilho de venda imediata (demo)</small></div><div><span>STOP LOSS INVIOLÁVEL</span><b>4.149,14</b><small>-100 pips de contenção (demo)</small></div><div><span>ALVO 1 (BREAK-EVEN + PARCIAL)</span><b>4.137,24</b><small>+190 pontos da entrada (demo)</small></div><div><span>ALVO FINAL (TAKE PROFIT TOTAL)</span><b>4.133,14</b><small>+600 pontos estruturais (demo)</small></div></div></section>
      <section class="d2DonorSurface d2ProtectionPanel"><header class="d2DonorSectionTitle"><b>Régua de Escalonamento e Proteção de Posição</b><span class="d2MutedTag">ILUSTRATIVA</span></header><div class="d2ProtectionSteps"><div><i>NÍVEL 1</i><b>Breakeven</b><span>Move SL para 0 a 0 ao atingir +190 pts</span></div><div><i>NÍVEL 2</i><b>Parcial 30%</b><span>Liquidação parcial em 4.136,00</span></div><div><i>NÍVEL 3</i><b>Parcial 30%</b><span>Trailing stop em 4.134,50</span></div><div><i>NÍVEL 4</i><b>TP 100%</b><span>Encerramento em 4.133,14</span></div></div></section>
    </div><div class="d2AnalysisSecondary">
      <section class="d2DonorSurface d2ChecklistPanel"><header class="d2DonorSectionTitle"><b>☷ &nbsp; Checklist dos 8 Critérios Quantitativos</b><span class="d2MutedTag">STATUS: COMPLIANT · DEMO</span></header><div class="d2CriteriaList"><div><i>01</i><span><b>Operação da Lia</b><small>Aguardando toque confirmatório (exemplo)</small></span><em>ENGATILHADO</em></div><div><i>02</i><span><b>Notícias Macro (Tier 1)</b><small>Sem dado forte intraday · exemplo estático</small></span><em>LIVRE</em></div><div><i>03</i><span><b>Tendência Multitemporal</b><small>Abaixo das médias móveis de 1h e 4h</small></span><em>VENDEDOR</em></div><div><i>04</i><span><b>Rompimento Institucional</b><small>Mínima da sessão de Londres rompida (demo)</small></span><em>VALIDADO</em></div><div><i>05</i><span><b>Ritmo / Price Action</b><small>Fluxo cadenciado, sem gaps anômalos</small></span><em>NORMAL</em></div><div><i>06</i><span><b>Volume Interbancário</b><small>119% da média (amostra ilustrativa)</small></span><em>119% AVG</em></div><div><i>07</i><span><b>Volatilidade ATR (14)</b><small>1.773 pts (amostra)</small></span><em>ATENÇÃO</em></div><div><i>08</i><span><b>Médias Rápidas (M15/M30)</b><small>-1.141 pts (amostra)</small></span><em>VENDEDOR</em></div></div></section>
      <section class="d2DonorSurface d2DispersionPanel"><header class="d2DonorSectionTitle"><div><b>Medidor de Dispersão e Volatilidade Intraday</b><p>Curva ilustrativa de pressão compradora vs. vendedora</p></div><span class="d2MutedTag">DEMO</span></header><div class="d2DemoChart d2DispersionDemo"><div class="d2ChartGrid" aria-hidden="true"></div><svg viewBox="0 0 720 180" role="img" aria-label="Exemplo ilustrativo de oscilação intraday"><path class="d2DemoLine" d="M0 100 Q70 30 140 70 T280 110 T420 35 T560 125 T650 45 T720 100"/></svg></div><footer class="d2ChartLegend"><span>EXEMPLO ESTÁTICO · SEM SÉRIE DE MERCADO</span><b>-64,2% DELTA · DEMO</b></footer></section>
    </div></div>
    <footer class="d2AnalysisProvenance"><span>TELEMETRIA <b>DEMO · NÃO CONECTADA</b></span><span>VARREDURA <b>ILUSTRATIVA</b></span><span>MT5 <b>NÃO CONSULTADO</b></span><span>PROVENIÊNCIA <b>DADOS DO PRINT</b></span></footer>`;

  operations.innerHTML = `
    <div class="d2DemoNotice" role="note">DEMONSTRAÇÃO · POSIÇÕES, ORDENS, COTAÇÕES E TELEMETRIA ABAIXO SÃO FICTÍCIAS · NENHUMA CONTA FOI CONSULTADA</div>
    <div class="d2OpsIntro"><div><span class="d2Eyebrow">CENTRAL DE EXECUÇÃO &amp; CUSTÓDIA DE POSIÇÕES · DEMO</span><h1>Operações</h1></div><span class="d2SourceBadge">DEMO · SEM MT5</span></div>
    <div class="d2OpsBanner"><span>ⓘ</span><div><b>MODO DEMONSTRATIVO · TODAS AS AÇÕES DESABILITADAS</b><p>Os valores reproduzem o print e não refletem conta, broker ou posições reais.</p></div><span class="d2SyncUnavailable">SINCRONIZADOR · FICTÍCIO</span></div>
    <div class="d2OpsSummary"><section><header><b>EXPOSIÇÃO TOTAL ABERTA</b><span>DEMO</span></header><strong>0,02 lotes XAU/USD</strong><p>Margem: US$ 42,78 · 1,8% da banca</p><small>Alocação segura (&lt; 5%) · margem livre 98,2%</small></section><section><header><b>RESULTADO FLUTUANTE (PNL)</b><span>DEMO</span></header><strong>+US$ 14,20 · +142 pts</strong><p>Retorno do trade: +0,33% · Spread: 1,1 pts</p><small>Drawdown máx.: -0,04% · pico +158 pts</small></section><section><header><b>ORDENS REGISTRADAS</b><span>DEMO</span></header><strong>2 ordens ativas</strong><p>1 posição aberta (Sell) · 1 pendente (Limit)</p><small>Fila e execução são apenas exemplos estáticos</small></section><section><header><b>ALGORITMO DE PROTEÇÃO</b><span>DEMO</span></header><strong>Breakeven +190 pts</strong><p>Trailing dinâmico ativado · passo 50 pts</p><small>Próximo nível: 4.135,00 · +220 pts</small></section></div>
    <section class="d2DonorSurface d2OpsLedger"><header class="d2DonorSectionTitle"><b>♧ &nbsp; Posições Abertas em Custódia</b><span class="d2MutedTag">1 OPERAÇÃO · DEMO</span></header><div class="d2LedgerWrap"><table class="d2Ledger"><thead><tr><th>TICKET</th><th>HORÁRIO</th><th>ATIVO</th><th>TIPO</th><th>LOTE</th><th>ABERTURA</th><th>ATUAL</th><th>STOP</th><th>TAKE</th><th>PNL</th><th>PROTEÇÃO</th><th>AÇÃO</th></tr></thead><tbody><tr><td>#48921</td><td>16:14:02</td><td>XAU/USD</td><td>SELL</td><td>0,01</td><td>4.139,14</td><td>4.137,72</td><td>4.149,14</td><td>4.133,14</td><td class="d2Positive">+US$ 14,20</td><td>Breakeven +190 pts</td><td><button type="button" disabled>Fechar</button></td></tr></tbody></table></div><footer class="d2LedgerFooter"><span>TOTAL: 1 ATIVA · VOLUME 0,01 lot</span><span>GANHO ESTIMADO NO TP: +US$ 60,00 · DEMO</span></footer></section>
    <section class="d2DonorSurface d2OpsLedger"><header class="d2DonorSectionTitle"><b>▹ &nbsp; Ordens Pendentes no Book</b><span class="d2MutedTag">1 PENDENTE · DEMO</span><button type="button" disabled>Cancelar todas pendentes</button></header><div class="d2LedgerWrap"><table class="d2Ledger"><thead><tr><th>TICKET</th><th>ORIGEM</th><th>ATIVO</th><th>ORDEM / DIREÇÃO</th><th>LOTE</th><th>GATILHO</th><th>DISTÂNCIA</th><th>STOP</th><th>TAKE</th><th>CONDIÇÃO</th><th>GESTÃO</th></tr></thead><tbody><tr><td>#48929</td><td>LIA 4.2 · DEMO</td><td>XAU/USD</td><td>SELL LIMIT</td><td>0,01</td><td>4.144,50</td><td>+67,8 pts</td><td>4.152,00</td><td>4.128,00</td><td>Rejeição em resistência H1 + exaustão RSI</td><td><button type="button" disabled>Executar agora</button></td></tr></tbody></table></div></section>
    <div class="d2OpsLower"><section class="d2DonorSurface d2OrderPanel"><header class="d2DonorSectionTitle"><b>⇧ &nbsp; Módulo de Envio Direto ao MetaTrader 5</b><span class="d2ActionDenied">DESABILITADO · DEMO</span></header><div class="d2OrderInputs"><label>VOLUME DE LOTE<input type="number" value="0.01" disabled></label><label>STOP LOSS (PONTOS)<input type="number" value="100" disabled></label><label>RISCO FINANCEIRO ESTIMADO<input type="text" value="US$ 10,00 · DEMO" disabled></label></div><div class="d2OrderButtons"><button type="button" disabled>↗ &nbsp; BUY MERCADO</button><button type="button" disabled>↘ &nbsp; SELL MERCADO</button></div><div class="d2ActionLock">SEM CONEXÃO MT5 · SEM ORDENS · CONTROLES DESABILITADOS</div><div class="d2SafetyNote">Slippage máx. 3 pts · Magic 9281729 · Timeout bridge 1.500 ms (valores do print, apenas ilustrativos)</div></section><section class="d2DonorSurface d2BridgePanel"><header class="d2DonorSectionTitle"><b>▣ &nbsp; Console de Mensagens da Bridge</b><span class="d2MutedTag">LOG ESTÁTICO · DEMO</span></header><div class="d2Console"><p>[16:35:10] MT5-BRIDGE: exemplo de mensagem · não conectado</p><p>[16:34:45] LIA-AI: exemplo de proteção · não executado</p><p>[16:29:12] GATEWAY: exemplo de ordem pendente · fictício</p><p>Canal e broker não inicializados por esta interface.</p></div></section></div>`;

  performance.innerHTML = `
    <div class="d2DemoNotice" role="note">DEMONSTRAÇÃO · MÉTRICAS ESTÁTICAS COPIADAS DO PRINT · NÃO SÃO PERFORMANCE AUDITADA</div>
    <div class="d2ReportHeading d2PerformanceHeading"><div><span class="d2Eyebrow">RELATÓRIO QUANTITATIVO INSTITUCIONAL · CONFIRMAÇÃO ALGORÍTMICA 99,4% (DEMO)</span><h1>Performance</h1><p>01 Fev 2025 – Hoje · Modelo Neural Lia v4.2 · amostra ilustrativa</p></div><div class="d2ReportControls" role="group" aria-label="Período demonstrativo"><button type="button" data-d2-period="7D" aria-pressed="false">7D</button><button type="button" data-d2-period="30D" aria-pressed="false">30D</button><button type="button" data-d2-period="90D" aria-pressed="true">90D (YTD)</button><button type="button" data-d2-period="ALL" aria-pressed="false">TUDO</button><button type="button" disabled>⇩ EXPORTAR</button></div></div>
    <div class="d2PerformanceMetrics"><article><span>LUCRO LÍQUIDO</span><strong>+US$ 1.842,50</strong><small>+18,4% da banca (US$ 10.000)</small></article><article><span>DRAWDOWN MÁX.</span><strong>3,2%</strong><small>Controle de risco ótimo</small></article><article><span>TAXA DE ACERTO</span><strong>81,4%</strong><small>162 vencidas · 37 perdidas</small></article><article><span>PAYOFF RATIO</span><strong>1,68</strong><small>Ganho méd. US$ 24,80 · perda US$ 14,76</small></article><article><span>SEQUÊNCIA MÁX.</span><strong>8 vitórias</strong><small>Perdas máx. seguidas: 2 trades</small></article><article><span>SHARPE RATIO</span><strong>2,14</strong><small>Nível institucional A+</small></article></div>
    <div class="d2PerformanceMain"><section class="d2DonorSurface d2EquityPanel"><header class="d2DonorSectionTitle"><div><b>Curva Patrimonial de Longo Prazo (Equity Curve)</b><p>Progressão demonstrativa com benchmark ilustrativo</p></div><span class="d2MutedTag">DEMO · NÃO AUDITADO</span></header><div class="d2DemoChart d2EquityDemo"><div class="d2ChartGrid" aria-hidden="true"></div><svg viewBox="0 0 720 270" role="img" aria-label="Curva patrimonial demonstrativa ascendente"><path class="d2BenchmarkLine" d="M0 230 L720 145"/><path class="d2DemoArea" d="M0 238 L50 218 100 223 150 192 200 181 250 190 300 159 350 135 400 146 450 110 500 90 550 72 600 58 650 32 700 15 720 4 V270 H0Z"/><path class="d2DemoLine" d="M0 238 L50 218 100 223 150 192 200 181 250 190 300 159 350 135 400 146 450 110 500 90 550 72 600 58 650 32 700 15 720 4"/></svg><span class="d2ChartEndLabel">US$ 11.842,50 · DEMO</span></div><footer class="d2ChartLegend"><span>CURVA DEMO</span><span>BENCHMARK S&amp;P (ILUSTRATIVO)</span></footer><div class="d2EquitySummary"><span>SALDO INICIAL <b>US$ 10.000,00</b></span><span>PICO DIÁRIO <b>+US$ 312,80 · 24 Fev</b></span><span>PERDA MÁX. <b>-US$ 84,20 · 07 Fev</b></span><span>EXPECTATIVA <b>+US$ 9,25 / trade</b></span></div></section><section class="d2DonorSurface d2AssetPanel"><header class="d2DonorSectionTitle"><div><b>Desempenho por Ativo</b><p>Alocação de volume e resultado · demo</p></div><span class="d2MutedTag">199 TRADES · PRINT</span></header><div class="d2AssetRows"><div><b>XAU/USD (Ouro)</b><span>114 trades · 84,2% winrate</span><strong>+US$ 1.284,30</strong><small>Profit Factor 2,18</small></div><div><b>EUR/USD</b><span>52 trades · 76,9% winrate</span><strong>+US$ 386,40</strong><small>Profit Factor 1,54</small></div><div><b>GBP/USD</b><span>33 trades · 72,7% winrate</span><strong>+US$ 171,80</strong><small>Profit Factor 1,38</small></div></div><div class="d2SafetyNote">Alpha dominante: XAU/USD · 69,7% do ganho líquido (demonstração).</div></section></div>
    <div class="d2PerformanceLower"><section class="d2DonorSurface d2SessionPanel"><header class="d2DonorSectionTitle"><div><b>Matriz de Desempenho por Sessão &amp; Horário</b><p>GMT-3 (horário de Brasília) · exemplos</p></div><span class="d2MutedTag">DEMO</span></header><div class="d2SessionSummary"><span>Londres <b>92% acerto</b></span><span>Nova York <b>78% acerto</b></span><span>Ásia / Sydney <b>65% acerto</b></span></div><div class="d2LedgerWrap"><table class="d2Ledger d2PerformanceTable"><thead><tr><th>DIA</th><th>VOLUME</th><th>WINRATE</th><th>RESULTADO</th><th>CLASSIFICAÇÃO</th></tr></thead><tbody><tr><td>Segunda-feira</td><td>34 trades</td><td>85,3%</td><td>+US$ 342,10</td><td>ÓTIMO</td></tr><tr><td>Terça-feira</td><td>48 trades</td><td>89,6%</td><td>+US$ 528,40</td><td>PRIME</td></tr><tr><td>Quarta-feira</td><td>51 trades</td><td>82,4%</td><td>+US$ 412,00</td><td>ÓTIMO</td></tr><tr><td>Quinta-feira</td><td>42 trades</td><td>76,2%</td><td>+US$ 380,00</td><td>ESTÁVEL</td></tr><tr><td>Sexta-feira</td><td>24 trades</td><td>66,7%</td><td>+US$ 179,80</td><td>CAUTELA</td></tr></tbody></table></div></section><section class="d2DonorSurface d2FilterPanel"><header class="d2DonorSectionTitle"><div><b>Eficácia dos Filtros</b><p>Comparativo de performance empírica · demo</p></div><span class="d2MutedTag">AMOSTRA ILUSTRATIVA</span></header><div class="d2FilterComparison"><div><span>CONFLUÊNCIA ≥ 8/10</span><strong>91,2%</strong><small>125 trades · risco moderado</small></div><div><span>CONFLUÊNCIA &lt; 7/10</span><strong>64,0%</strong><small>74 trades · menos filtros</small></div></div><div class="d2DemoText">Protocolos de segurança (exemplos do print): trava de notícias de alto impacto; breakeven dinâmico em 1,2R; filtro de dispersão bayesiana.</div></section></div>`;

  history.innerHTML = `
    <div class="d2DemoNotice" role="note">DEMONSTRAÇÃO · LEDGER E TESE FICTÍCIOS COPIADOS DOS PRINTS · NÃO SÃO ORDENS NEM REGISTROS DE CONTA</div>
    <section class="d2HistoryHeaderPanel"><div class="d2ReportHeading"><div><span class="d2Eyebrow">AUDITORIA FOREX &amp; COMMODITIES · LEDGER MT5 #9281729 · DEMO</span><h1>Histórico de Ordens &amp; Registro de Confluência</h1><p>Dados ilustrativos · nenhuma conta, Trade Journal, tester ou AuditLog foi consultado.</p></div><div class="d2HistoryExports"><button type="button" disabled>▤ EXPORTAR CSV / EXCEL</button><button type="button" disabled>▧ RELATÓRIO PDF</button></div></div>
    <div class="d2HistoryFilterBar"><div class="d2PeriodChoices" role="group" aria-label="Período demonstrativo"><button type="button" data-d2-history-period="today" aria-pressed="false">HOJE</button><button type="button" data-d2-history-period="yesterday" aria-pressed="false">ONTEM</button><button type="button" data-d2-history-period="7d" aria-pressed="true">ÚLTIMOS 7D</button><button type="button" data-d2-history-period="month" aria-pressed="false">MÊS ATUAL</button><button type="button" data-d2-history-period="custom" aria-pressed="false">PERSONALIZADO</button></div><label>ATIVO<select aria-label="Filtrar por ativo"><option value="all">Todos os ativos</option><option value="xauusd">XAU/USD</option><option value="eurusd">EUR/USD</option><option value="gbpusd">GBP/USD</option></select></label><label>SAÍDA<select aria-label="Filtrar por saída"><option value="all">Todas as saídas</option><option value="take-profit">Take Profit</option><option value="stop-loss">Stop Loss</option></select></label><span id="d2HistoryFilterState" role="status">DEMO · 48 REGISTROS ILUSTRATIVOS</span></div></section>
    <div class="d2HistoryMetrics"><article><span>OPERAÇÕES</span><strong>48 execuções</strong></article><article><span>TAXA DE ACERTO</span><strong>79,2% · 38W / 10L</strong></article><article><span>LUCRO LÍQUIDO</span><strong>+US$ 342,80</strong><small>Drawdown +14,2% · mês 1,8%</small></article><article><span>FATOR DE LUCRO</span><strong>2,41 institucional</strong></article><article><span>RELAÇÃO R/R MÉDIA</span><strong>1 : 1,45</strong><small>Expectativa positiva · demo</small></article></div>
    <div class="d2HistoryLayout"><section class="d2DonorSurface d2HistoryLedger"><header class="d2DonorSectionTitle"><div><b>▤ &nbsp; Ordens Executadas &amp; Liquidadas</b><p>8 selecionadas · clique para inspecionar dados ilustrativos</p></div><span class="d2MutedTag">DEMO · NÃO É LEDGER REAL</span></header><div class="d2LedgerWrap"><table class="d2Ledger"><thead><tr><th>TICKET</th><th>EXECUÇÃO</th><th>ATIVO</th><th>LADO</th><th>LOTE</th><th>ENTRADA</th><th>SAÍDA</th><th>DUR.</th></tr></thead><tbody><tr><td>#9842104</td><td>08:14 → 08:38</td><td>XAU/USD</td><td>BUY</td><td>0,08</td><td>2734.20</td><td>2741.80</td><td>24m</td></tr><tr><td>#9841890</td><td>07:05 → 07:44</td><td>EUR/USD</td><td>SELL</td><td>0,15</td><td>1.08640</td><td>1.08412</td><td>39m</td></tr><tr><td>#9841521</td><td>05:22 → 06:01</td><td>XAU/USD</td><td>BUY</td><td>0,10</td><td>2728.50</td><td>2730.40</td><td>39m</td></tr><tr><td>#9840932</td><td>03:10 → 03:28</td><td>GBP/USD</td><td>BUY</td><td>0,12</td><td>1.29850</td><td>1.29690</td><td>17m</td></tr><tr><td>#9840310</td><td>01:15 → 01:42</td><td>XAU/USD</td><td>SELL</td><td>0,10</td><td>2745.10</td><td>2736.00</td><td>27m</td></tr><tr><td>#9839881</td><td>22:30 → 23:18</td><td>EUR/USD</td><td>BUY</td><td>0,20</td><td>1.08210</td><td>1.08248</td><td>49m</td></tr><tr><td>#9839440</td><td>20:04 → 20:45</td><td>GBP/USD</td><td>SELL</td><td>0,10</td><td>1.30120</td><td>1.29930</td><td>41m</td></tr><tr><td>#9838912</td><td>18:10 → 18:34</td><td>XAU/USD</td><td>BUY</td><td>0,12</td><td>2719.40</td><td>2730.20</td><td>24m</td></tr></tbody></table></div><footer class="d2LedgerFooter"><span>MOSTRANDO 1–8 DE 48 REGISTROS DEMONSTRATIVOS</span><div class="d2Pagination"><button type="button" disabled>‹</button><button type="button" disabled aria-current="page">1</button><button type="button" disabled>2</button><button type="button" disabled>3</button><button type="button" disabled>Próximo</button></div></footer></section>
    <aside class="d2DonorSurface d2TradeInspector"><header class="d2DonorSectionTitle"><div><b>Tese Neural da Lia</b><p>#9842104 · XAU/USD · BUY · DEMO</p></div><span class="d2MutedTag">+US$ 60,80</span></header><section class="d2InspectorEvidence"><div class="d2InspectorSubhead"><span>PREÇO DE ENTRADA / SAÍDA</span><b>2734.20 / 2741.80</b></div><div class="d2InspectorSubhead"><span>DURAÇÃO EM RISCO</span><b>23m 48s · DEMO</b></div><div class="d2InspectorSubhead"><span>CONFLUÊNCIA LIA</span><b>9 / 10 FILTROS</b></div><div class="d2InspectorSubhead"><span>TESE ALGORÍTMICA NO MOMENTO DA ORDEM</span><b>EXEMPLO</b></div><p class="d2InspectorThesis">Rompimento de liquidez na máxima de Londres com absorção institucional no Order Book. Confluência quântica confirmada pelo filtro de momentum H1 e rejeição de mínima anterior. (Texto ilustrativo do print.)</p><div class="d2InspectorSubhead"><span>CHECKLIST DOS 7 FILTROS DA LIA</span><b>DEMO</b></div><div class="d2InspectorChecks"><div><span>Fluxo Institucional &amp; Books</span><b>VALIDADO</b></div><div><span>Divergência de Delta Volume</span><b>ALTA CONVICÇÃO</b></div><div><span>Estrutura de Sessão (London Sweep)</span><b>CONFLUENTE</b></div><div><span>Assimetria Risco / Retorno ≥ 1:1,3</span><b>1,58</b></div></div></section><div class="d2InspectorFields"><div><span>FONTE</span><b>PRINT · DEMO</b></div><div><span>IDENTIDADE</span><b>FICTÍCIA</b></div><div><span>PROVENIÊNCIA</span><b>SEM AUDITLOG</b></div></div><button type="button" class="d2CopyTicket" disabled>▢ &nbsp; COPIAR TICKET · DESABILITADO</button></aside></div>`;
}

function wireTradeJournalHistory(history) {
  const header = history.querySelector(".d2HistoryHeaderPanel");
  if (!header) return;
  const controls = header.querySelector(".d2HistoryExports");
  if (!controls) return;
  const filterState = history.querySelector("#d2HistoryFilterState");
  const periodButtons = history.querySelectorAll("[data-d2-history-period]");
  const customDates = history.querySelector("[data-history-custom-dates]");
  const dateFrom = history.querySelector("[data-history-date-from]");
  const dateTo = history.querySelector("[data-history-date-to]");
  const symbolInput = history.querySelector("[data-history-symbol]");
  const exitSelect = history.querySelector("[data-history-exit]");
  if (!filterState || !symbolInput || !exitSelect) return;

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "CONSULTAR HISTÓRICO";
  button.dataset.historyConsult = "";
  controls.prepend(button);

  const resultPanel = document.createElement("section");
  resultPanel.className = "d2DonorSurface d2HistoryRead";
  resultPanel.setAttribute("aria-labelledby", "d2HistoryReadTitle");
  resultPanel.innerHTML = '<header class="d2DonorSectionTitle"><div><b id="d2HistoryReadTitle">Trade Journal · leitura canônica</b><p>Até 10 registros por página · somente leitura · datas do registro sem conversão de fuso</p></div><span class="d2MutedTag" data-history-read-state>AINDA NÃO CONSULTADO</span></header><p data-history-read-status role="status">Aguardando solicitação autenticada. A aba não consulta o Journal automaticamente.</p><div class="d2LedgerWrap"><table class="d2Ledger"><thead><tr><th>DATA ORIGINAL</th><th>ATIVO</th><th>DIREÇÃO</th><th>CLASSIFICAÇÃO</th><th>EXECUÇÃO</th><th>SAÍDA REGISTRADA</th></tr></thead><tbody data-history-read-records></tbody></table></div>';
  header.insertAdjacentElement("afterend", resultPanel);

  const status = resultPanel.querySelector("[data-history-read-status]");
  const state = resultPanel.querySelector("[data-history-read-state]");
  const body = resultPanel.querySelector("[data-history-read-records]");
  const pageInfo = document.createElement("span");
  pageInfo.textContent = "Nenhuma página consultada";
  const previous = document.createElement("button");
  previous.type = "button";
  previous.textContent = "‹";
  previous.setAttribute("aria-label", "Página anterior");
  previous.disabled = true;
  const pageLabel = document.createElement("span");
  pageLabel.textContent = "—";
  const next = document.createElement("button");
  next.type = "button";
  next.textContent = "›";
  next.setAttribute("aria-label", "Próxima página");
  next.disabled = true;
  const pagination = document.createElement("footer");
  pagination.className = "d2LedgerFooter d2HistoryPagination";
  const paginationControls = document.createElement("div");
  paginationControls.className = "d2Pagination";
  paginationControls.append(previous, pageLabel, next);
  pagination.append(pageInfo, paginationControls);
  resultPanel.append(pagination);

  let pending = false;
  let appliedFilters = null;
  let pageOffsets = [0];
  let appliedCount = 0;
  let hasMore = false;

  const setStatus = (message, label) => {
    status.textContent = message;
    state.textContent = label;
  };
  const setFiltersDisabled = (disabled) => {
    periodButtons.forEach((item) => { item.disabled = disabled; });
    [dateFrom, dateTo, symbolInput, exitSelect].filter(Boolean)
      .forEach((item) => { item.disabled = disabled; });
  };
  const localDateString = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  const filtersFromControls = () => {
    const selected = Array.from(periodButtons).find((item) => item.getAttribute("aria-pressed") === "true");
    const period = selected?.dataset.d2HistoryPeriod || "7d";
    const today = new Date();
    let from = "";
    let to = "";
    if (period === "today") from = to = localDateString(today);
    else if (period === "yesterday") {
      const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1, 12);
      from = to = localDateString(yesterday);
    } else if (period === "7d") {
      from = localDateString(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6, 12));
      to = localDateString(today);
    } else if (period === "month") {
      from = localDateString(new Date(today.getFullYear(), today.getMonth(), 1, 12));
      to = localDateString(today);
    } else if (period === "custom") {
      from = dateFrom?.value || "";
      to = dateTo?.value || "";
      const validDate = (value) => {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
        const [year, month, day] = value.split("-").map(Number);
        return localDateString(new Date(year, month - 1, day, 12)) === value;
      };
      if (!validDate(from) || !validDate(to) || from > to) return { error: "Informe um intervalo de datas válido." };
    }
    const symbol = String(symbolInput.value || "").trim().toUpperCase();
    if (symbol && !/^[A-Z0-9._#-]{1,32}$/.test(symbol)) return { error: "Ativo inválido. Use somente um símbolo válido." };
    return { period, date_from: from, date_to: to, symbol,
      exit_type: String(exitSelect.value || "ALL").toUpperCase() };
  };
  const clearRows = () => {
    body.replaceChildren();
    pageInfo.textContent = "Filtros ainda não consultados";
    pageLabel.textContent = "—";
    previous.disabled = true;
    next.disabled = true;
  };
  const clearFailedResults = () => {
    body.replaceChildren();
    appliedFilters = null;
    pageOffsets = [0];
    appliedCount = 0;
    hasMore = false;
    clearRows();
  };
  const filtersChanged = () => {
    pageOffsets = [0];
    appliedFilters = null;
    appliedCount = 0;
    hasMore = false;
    clearRows();
    filterState.textContent = "FILTROS ALTERADOS · CONSULTA NECESSÁRIA · DATA ORIGINAL SEM CONVERSÃO DE FUSO";
  };
  periodButtons.forEach((periodButton) => periodButton.addEventListener("click", () => {
    periodButtons.forEach((item) => item.setAttribute("aria-pressed", String(item === periodButton)));
    if (customDates) customDates.hidden = periodButton.dataset.d2HistoryPeriod !== "custom";
    filtersChanged();
  }));
  [dateFrom, dateTo, symbolInput, exitSelect].filter(Boolean).forEach((input) => {
    input.addEventListener("change", filtersChanged);
    if (input === symbolInput) input.addEventListener("input", filtersChanged);
  });

  const showRecords = (response, targetOffset, filters) => {
    const page = response?.data?.data || response?.data || response?.result?.data?.data
      || response?.result?.data || response?.result || response;
    const errorCode = String(page?.error_code || "").match(/^[A-Z0-9_]{1,64}$/)?.[0] || "";
    const unavailableCode = String(page?.reason || "").match(/^[A-Z0-9_]{1,64}$/)?.[0] || "";
    if (response?.ok === true && page?.status === "UNAVAILABLE") {
      clearFailedResults();
      pageInfo.textContent = "Journal indisponível · nenhum total inferido";
      setStatus(unavailableCode
        ? `Trade Journal indisponível. Código: ${unavailableCode}. Nenhum registro foi apresentado.`
        : "Trade Journal indisponível. Nenhum registro foi apresentado.", "INDISPONÍVEL");
      return false;
    }
    if (response?.ok !== true || page?.read_only !== true
        || !Array.isArray(page?.records) || typeof page?.has_more !== "boolean"
        || typeof page?.scan_truncated !== "boolean"
        || page?.date_basis !== "RAW_TIMESTAMP_CALENDAR_DATE_NO_TZ_CONVERSION"
        || page?.date_from !== (filters.date_from || null)
        || page?.date_to !== (filters.date_to || null)
        || page?.symbol !== filters.symbol
        || page?.exit_type_filter !== filters.exit_type) {
      clearFailedResults();
      setStatus(errorCode
        ? `A consulta não foi concluída. Código: ${errorCode}. Nenhum registro foi apresentado.`
        : "A consulta não foi concluída ou os filtros não foram reconciliados. Nenhum registro foi apresentado.",
      "INDISPONÍVEL");
      return false;
    }
    body.replaceChildren();
    const fields = ["timestamp", "symbol", "direction", "record_type", "execution_status", "exit_type"];
    page.records.slice(0, 10).forEach((record) => {
      const row = document.createElement("tr");
      fields.forEach((field) => {
        const cell = document.createElement("td");
        cell.textContent = String(record?.[field] ?? (field === "exit_type" ? "NÃO INFORMADO" : "—")).slice(0, 120);
        row.append(cell);
      });
      body.append(row);
    });
    const count = Math.min(page.records.length, 10);
    appliedFilters = { ...filters };
    appliedCount = count;
    hasMore = page.has_more;
    const index = pageOffsets.indexOf(targetOffset);
    if (index >= 0) pageOffsets = pageOffsets.slice(0, index + 1);
    else pageOffsets.push(targetOffset);
    pageLabel.textContent = String(pageOffsets.length);
    previous.disabled = pageOffsets.length <= 1;
    next.disabled = !hasMore || count === 0;
    pageInfo.textContent = count
      ? `${count} registro(s) nesta página${page.scan_truncated ? " · varredura limitada a 10.000; continuidade desconhecida" : hasMore ? " · há próxima página" : " · não há próxima página informada"}`
      : "Nenhum registro nesta página; isso não representa desempenho zero.";
    const range = filters.date_from ? `${filters.date_from} a ${filters.date_to} · data original` : "sem filtro de data";
    filterState.textContent = `${range} · ${filters.symbol || "todos os ativos"} · ${count} registro(s) · saída: ${filters.exit_type === "ALL" ? "todas" : "não registrada"}`;
    setStatus(count ? `${count} registro(s) do Trade Journal · somente leitura · sem conversão de fuso.`
      : "Nenhum registro corresponde aos filtros nesta página. Isso não representa desempenho zero.", "CONSULTA CONCLUÍDA");
    return true;
  };

  const requestPage = async (targetOffset = 0) => {
    if (pending) return;
    setFiltersDisabled(true);
    const filters = filtersFromControls();
    if (filters.error) {
      setFiltersDisabled(false);
      setStatus(filters.error, "FILTROS INVÁLIDOS");
      return;
    }
    const gateway = window.Gateway;
    if (gateway?.isAuthenticated !== true || typeof gateway.httpPost !== "function") {
      setFiltersDisabled(false);
      setStatus("Conecte-se ao Jarvis com a sessão autenticada para solicitar a leitura.", "AUTENTICAÇÃO NECESSÁRIA");
      return;
    }
    pending = true;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    setStatus("Solicitando confirmação ao SecurityManager...", "AGUARDANDO CONFIRMAÇÃO");
    let awaitingConfirmation = false;
    const finishPending = () => {
      pending = false;
      button.disabled = false;
      button.removeAttribute("aria-busy");
      setFiltersDisabled(false);
      previous.disabled = pageOffsets.length <= 1;
      next.disabled = !hasMore || appliedCount === 0;
    };
    try {
      const request = await gateway.httpPost("/api/jarvis/golden/trade-history", {
        symbol: filters.symbol, record_type: "ALL", limit: 10, offset: targetOffset,
        date_from: filters.date_from, date_to: filters.date_to,
        exit_type: filters.exit_type,
      });
      const envelope = request?.result || request?.data || request;
      if (request?.ok !== true || envelope?.confirmation_required !== true
          || typeof envelope.token !== "string" || !envelope.token) {
        throw new Error("Consulta não disponível.");
      }
      const requestConfirmation = window.requestJarvisHttpConfirmation;
      if (typeof requestConfirmation !== "function") {
        throw new Error("Confirmação segura do Jarvis indisponível.");
      }
      const opened = requestConfirmation({
        token: envelope.token,
        action: "Consultar Trade Journal",
        message: `Autorizar uma leitura somente leitura, limitada a 10 registros? Período: ${filters.date_from || "sem data"} a ${filters.date_to || "sem data"}; ativo: ${filters.symbol || "todos"}.`,
        onApprove: async (token) => gateway.httpPost("/api/desktop/confirm", { token }),
        onComplete: (response) => {
          showRecords(response, targetOffset, filters);
          finishPending();
        },
        onCancel: () => {
          void gateway.httpPost("/api/security/deny", {
            request_id: `jarvis:${envelope.token}`,
          });
          setStatus("Consulta cancelada. Nenhum registro foi lido.", "CANCELADA");
          finishPending();
        },
        onFailure: () => {
          setStatus("Confirmação inválida ou expirada. Nenhum registro foi lido.", "INDISPONÍVEL");
          finishPending();
        },
      });
      if (!opened) throw new Error("Confirmação segura do Jarvis indisponível.");
      awaitingConfirmation = true;
    } catch (error) {
      const message = error?.message === "Confirmação segura do Jarvis indisponível."
        ? error.message : "Não foi possível iniciar a consulta do Histórico.";
      setStatus(message, "INDISPONÍVEL");
    } finally {
      if (!awaitingConfirmation) finishPending();
    }
  };

  button.addEventListener("click", () => requestPage(0));
  previous.addEventListener("click", () => {
    if (!pending && pageOffsets.length > 1) return requestPage(pageOffsets[pageOffsets.length - 2]);
  });
  next.addEventListener("click", () => {
    if (!pending && hasMore && appliedFilters && appliedCount > 0) {
      return requestPage(pageOffsets[pageOffsets.length - 1] + appliedCount);
    }
  });
}

function createAssetCatalogCombobox(host, options = {}) {
  if (!host) return null;
  const allowAll = options.allowAll === true;
  const id = `d2AssetComboboxList${++assetComboboxSequence}`;
  const root = document.createElement("div");
  root.className = "d2AssetCombobox";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "d2AssetComboboxInput";
  input.autocomplete = "off";
  input.maxLength = 64;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-haspopup", "listbox");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", id);
  input.setAttribute("aria-label", options.ariaLabel || "Selecionar ativo por símbolo ou nome");
  const listbox = document.createElement("div");
  listbox.id = id;
  listbox.className = "d2AssetComboboxList";
  listbox.dataset.assetComboboxList = "";
  listbox.setAttribute("role", "listbox");
  listbox.hidden = true;
  root.append(input, listbox);
  host.replaceChildren(root);

  let assets = [];
  let selectedValue = allowAll ? "" : "";
  let selectedLabel = "";
  let emptyLabel = "Catálogo MT5 indisponível";
  let queryActive = false;
  let opened = false;
  let highlightedValue = null;
  let changeListeners = [];

  const optionRows = () => Array.from(listbox.querySelectorAll('[role="option"]'))
    .filter((row) => !row.hidden && !row.disabled);
  const updateActiveOption = () => {
    const rows = optionRows();
    rows.forEach((row) => {
      const active = row.dataset.assetValue === highlightedValue;
      row.dataset.highlighted = String(active);
    });
    const activeRow = rows.find((row) => row.dataset.assetValue === highlightedValue);
    if (activeRow) input.setAttribute("aria-activedescendant", activeRow.id);
    else input.removeAttribute("aria-activedescendant");
  };
  const filterOptions = () => {
    const query = queryActive ? String(input.value || "").trim().toLocaleLowerCase() : "";
    let visibleAssets = 0;
    optionRowsAll().forEach((row) => {
      const match = !query || String(row.textContent || "").toLocaleLowerCase().includes(query)
        || (allowAll && row.dataset.assetValue === "");
      row.hidden = !match;
      if (match && !(allowAll && row.dataset.assetValue === "")) visibleAssets += 1;
    });
    Array.from(listbox.querySelectorAll('[role="group"]')).forEach((group) => {
      const rows = Array.from(group.querySelectorAll('[role="option"]'));
      group.hidden = rows.length > 0 && rows.every((row) => row.hidden);
    });
    let noResults = listbox.querySelector("[data-asset-no-results]");
    if (query && assets.length > 0 && !visibleAssets) {
      if (!noResults) {
        noResults = document.createElement("div");
        noResults.dataset.assetNoResults = "";
        noResults.className = "d2AssetComboboxMessage";
        noResults.setAttribute("role", "status");
        listbox.append(noResults);
      }
      noResults.textContent = "Nenhum ativo corresponde à pesquisa.";
      noResults.hidden = false;
    } else if (noResults) noResults.hidden = true;
    updateActiveOption();
  };
  const optionRowsAll = () => Array.from(listbox.querySelectorAll('[role="option"]'));
  const close = (restoreSelection = true) => {
    opened = false;
    queryActive = false;
    highlightedValue = null;
    listbox.hidden = true;
    input.setAttribute("aria-expanded", "false");
    if (restoreSelection) input.value = selectedLabel;
    input.placeholder = selectedLabel ? "" : emptyLabel;
    filterOptions();
  };
  const open = (loadCatalog = true) => {
    if (!opened) {
      opened = true;
      queryActive = false;
      highlightedValue = null;
      input.setAttribute("aria-expanded", "true");
      listbox.hidden = false;
      filterOptions();
      if (loadCatalog) options.ensureCatalog?.();
    }
  };
  const setSelection = (value, notify = false) => {
    const next = String(value ?? "");
    const validAll = allowAll && next === "";
    const assetIndex = next === "" ? -1 : Number(next);
    if (!validAll && (!Number.isInteger(assetIndex) || !assets[assetIndex])) return false;
    const changed = next !== selectedValue;
    selectedValue = next;
    selectedLabel = validAll ? "Todos os ativos"
      : assetIndex >= 0 ? `${assets[assetIndex].provider_symbol} · ${assets[assetIndex].display_name || assets[assetIndex].provider_symbol}`
      : "";
    input.value = selectedLabel;
    input.placeholder = selectedLabel ? "" : emptyLabel;
    if (changed) {
      optionRowsAll().forEach((row) => row.setAttribute("aria-selected", String(row.dataset.assetValue === selectedValue)));
      if (notify) changeListeners.forEach((listener) => listener({target: {value: selectedValue}}));
    }
    close(false);
    return true;
  };
  const commit = (value) => setSelection(value, true);
  const moveHighlight = (direction) => {
    const rows = optionRows();
    if (!rows.length) return;
    const index = rows.findIndex((row) => row.dataset.assetValue === highlightedValue);
    const nextIndex = index < 0 ? (direction > 0 ? 0 : rows.length - 1)
      : (index + direction + rows.length) % rows.length;
    highlightedValue = rows[nextIndex].dataset.assetValue;
    updateActiveOption();
  };
  const setCatalog = (nextAssets, config = {}) => {
    const activeQuery = opened && queryActive ? input.value : "";
    assets = Array.isArray(nextAssets) ? nextAssets : [];
    emptyLabel = String(config.emptyLabel || "Catálogo MT5 indisponível");
    listbox.replaceChildren();
    if (allowAll) appendComboboxOption(listbox, "", config.allLabel || "Todos os ativos");
    appendGroupedAssetOptions(listbox, assets, config.assetClassLabel || ((value) => value));
    if (!assets.length) {
      const message = document.createElement("div");
      message.className = "d2AssetComboboxMessage";
      message.setAttribute("role", "status");
      message.textContent = emptyLabel;
      listbox.append(message);
    }
    const wanted = String(config.selectedValue ?? selectedValue);
    const validAll = allowAll && wanted === "";
    const index = wanted === "" ? -1 : Number(wanted);
    selectedValue = validAll || (Number.isInteger(index) && assets[index]) ? wanted : "";
    selectedLabel = selectedValue === "" ? (allowAll ? (config.allLabel || "Todos os ativos") : "")
      : `${assets[Number(selectedValue)].provider_symbol} · ${assets[Number(selectedValue)].display_name || assets[Number(selectedValue)].provider_symbol}`;
    optionRowsAll().forEach((row) => row.setAttribute("aria-selected", String(row.dataset.assetValue === selectedValue)));
    if (opened && queryActive) input.value = activeQuery;
    else input.value = selectedLabel;
    input.placeholder = selectedLabel ? "" : emptyLabel;
    filterOptions();
  };

  input.addEventListener("focus", () => {
    open();
    input.select?.();
  });
  input.addEventListener("click", () => {
    const wasOpen = opened;
    open();
    if (!wasOpen && !queryActive) input.select?.();
  });
  input.addEventListener("input", () => {
    open(false);
    queryActive = true;
    highlightedValue = null;
    filterOptions();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      open();
      moveHighlight(event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Enter") {
      if (highlightedValue !== null) {
        event.preventDefault();
        commit(highlightedValue);
      }
    } else if (event.key === "Escape" && opened) {
      event.preventDefault();
      close(true);
    }
  });
  input.addEventListener("blur", () => {
    if (opened) close(true);
  });

  const api = {
    get value() { return selectedValue; },
    set value(value) { setSelection(value); },
    input,
    listbox,
    setCatalog,
    addEventListener(name, listener) {
      if (name === "change" && typeof listener === "function") changeListeners.push(listener);
    },
    focus() { input.focus(); },
    commit,
  };
  listbox.assetComboboxApi = api;
  return api;
}

function appendComboboxOption(listbox, value, label) {
  const option = document.createElement("button");
  option.type = "button";
  option.className = "d2AssetComboboxOption d2AssetComboboxAll";
  option.dataset.assetValue = String(value);
  option.id = `d2AssetOption${++assetComboboxSequence}`;
  option.textContent = label;
  option.setAttribute("role", "option");
  option.setAttribute("aria-selected", "false");
  option.addEventListener("mousedown", (event) => event.preventDefault());
  option.addEventListener("click", () => listbox.assetComboboxApi?.commit(String(value)));
  listbox.append(option);
}

function appendGroupedAssetOptions(select, assets, assetClassLabel) {
  const comboboxList = select?.dataset?.assetComboboxList !== undefined;
  const classes = [...new Set(assets.map((asset) => asset.asset_class))].sort();
  for (const kind of classes) {
    const group = document.createElement(comboboxList ? "div" : "optgroup");
    if (comboboxList) {
      group.className = "d2AssetComboboxGroup";
      group.setAttribute("role", "group");
      group.setAttribute("aria-label", assetClassLabel(kind));
      const heading = document.createElement("div");
      heading.className = "d2AssetComboboxGroupLabel";
      heading.setAttribute("role", "presentation");
      heading.textContent = assetClassLabel(kind);
      group.append(heading);
    } else group.label = assetClassLabel(kind);
    assets.forEach((asset, index) => {
      if (asset.asset_class !== kind) return;
      const option = document.createElement(comboboxList ? "button" : "option");
      if (comboboxList) {
        option.type = "button";
        option.className = "d2AssetComboboxOption";
        option.dataset.assetValue = String(index);
        option.id = `d2AssetOption${++assetComboboxSequence}`;
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", "false");
        option.addEventListener("mousedown", (event) => event.preventDefault());
        option.addEventListener("click", () => select.assetComboboxApi?.commit(String(index)));
      } else option.value = String(index);
      option.textContent = `${asset.provider_symbol} · ${asset.display_name || asset.provider_symbol}`;
      group.append(option);
    });
    select.append(group);
  }
}

function wireGoldenAnalysisHistory(analysisView, options = {}) {
  if (!analysisView || analysisView.querySelector("[data-golden-analysis-history]")) return;

  const section = document.createElement("section");
  section.className = "d2DonorSurface d2GoldenAnalysisHistory";
  section.dataset.goldenAnalysisHistory = "";
  section.setAttribute("aria-labelledby", "d2GoldenAnalysisHistoryTitle");
  const heading = document.createElement("header");
  heading.className = "d2DonorSectionTitle";
  const title = document.createElement("b");
  title.id = "d2GoldenAnalysisHistoryTitle";
  title.textContent = "Histórico de Análises";
  const badge = document.createElement("span");
  badge.className = "d2MutedTag";
  badge.dataset.historyState = "";
  badge.textContent = "NÃO CONSULTADO";
  heading.append(title, badge);

  const intro = document.createElement("p");
  intro.className = "d2GoldenAnalysisHistoryIntro";
  intro.textContent = "Registros canônicos de análise · não representam operações executadas.";
  const controls = document.createElement("div");
  controls.className = "d2GoldenAnalysisHistoryFilters";
  const symbolHost = document.createElement("div");
  symbolHost.dataset.historySymbol = "";
  const mode = document.createElement("select");
  mode.setAttribute("aria-label", "Filtrar análises por modo");
  mode.dataset.historyMode = "";
  const statusFilter = document.createElement("select");
  statusFilter.setAttribute("aria-label", "Filtrar análises por status");
  statusFilter.dataset.historyStatus = "";
  const addOption = (select, value, label) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.append(option);
  };
  addOption(mode, "", "Todos os modos");
  addOption(mode, "INDEPENDENT", "Análise independente");
  addOption(mode, "STRATEGY", "Estratégia definida");
  addOption(statusFilter, "", "Todos os status");
  [
    ["COMPLETE", "Concluída"],
    ["PARTIAL", "Parcial"],
    ["ERROR", "Erro"],
    ["INSUFFICIENT_DATA", "Dados insuficientes"],
    ["UNAVAILABLE", "Indisponível"],
  ].forEach(([value, label]) => {
    addOption(statusFilter, value, label);
  });
  const addFilter = (label, control) => {
    const wrapper = document.createElement("label");
    wrapper.append(document.createTextNode(label), control);
    controls.append(wrapper);
  };
  addFilter("ATIVO", symbolHost);
  addFilter("MODO", mode);
  addFilter("STATUS", statusFilter);
  const consult = document.createElement("button");
  consult.type = "button";
  consult.className = "d2TextAction";
  consult.textContent = "CONSULTAR HISTÓRICO";
  consult.dataset.historyConsult = "";
  controls.append(consult);

  const message = document.createElement("p");
  message.className = "d2GoldenAnalysisHistoryMessage";
  message.setAttribute("role", "status");
  message.dataset.historyMessage = "";
  message.textContent = "Aguardando consulta autenticada. Nenhum histórico é carregado automaticamente.";
  const list = document.createElement("div");
  list.className = "d2GoldenAnalysisHistoryList";
  list.dataset.historyList = "";
  const detail = document.createElement("section");
  detail.className = "d2GoldenAnalysisHistoryDetail";
  detail.dataset.historyDetail = "";
  detail.hidden = true;
  section.append(heading, intro, controls, message, list, detail);
  const provenance = analysisView.querySelector(".d2AnalysisProvenance");
  if (provenance) provenance.insertAdjacentElement("afterend", section);
  else analysisView.append(section);

  const pageSize = 25;
  let offset = 0;
  let hasMore = false;
  let pending = false;
  let pageRows = [];
  let filterRevision = 0;
  let displayedAssets = [];
  const symbol = createAssetCatalogCombobox(symbolHost, {
    allowAll: true,
    ariaLabel: "Filtrar análises por ativo",
    ensureCatalog: () => options.ensureCatalog?.(),
  });
  const setState = (label, text) => {
    badge.textContent = label;
    message.textContent = text;
  };
  const safeCode = (value) => String(value || "").match(/^[A-Z0-9_]{1,80}$/)?.[0] || "";
  const unwrap = (response, predicate) => {
    const queue = [response];
    const seen = new Set();
    for (let depth = 0; queue.length && depth < 12; depth += 1) {
      const item = queue.shift();
      if (!item || typeof item !== "object" || seen.has(item)) continue;
      seen.add(item);
      if (predicate(item)) return item;
      if (item.http_failure === true) return item;
      if (item.result && typeof item.result === "object") queue.push(item.result);
      if (item.data && typeof item.data === "object") queue.push(item.data);
    }
    return response;
  };
  const clearDetail = () => {
    detail.replaceChildren();
    detail.hidden = true;
  };
  const invalidateResults = () => {
    filterRevision += 1;
    offset = 0;
    hasMore = false;
    pageRows = [];
    list.replaceChildren();
    clearDetail();
    setState("CONSULTA NECESSÁRIA", "Filtros alterados. Consulte novamente para carregar a lista atualizada.");
  };
  const refreshCatalog = () => {
    const previousValue = symbol.value;
    const previousAsset = previousValue ? displayedAssets[Number(previousValue)] : null;
    const catalog = typeof options.getCatalog === "function" ? options.getCatalog() : {};
    const assets = Array.isArray(catalog.assets) ? catalog.assets : [];
    const selectedIndex = previousAsset ? assets.findIndex((asset) =>
      asset.provider_asset_id === previousAsset.provider_asset_id
      && asset.provider_symbol === previousAsset.provider_symbol
      && asset.asset_class === previousAsset.asset_class) : -1;
    displayedAssets = assets;
    const unavailable = /UNAVAILABLE|DISABLED|NETWORK_ERROR|GATEWAY INDISPONÍVEL|AUTENTICAÇÃO NECESSÁRIA/i
      .test(String(catalog.status || ""));
    const emptyLabel = catalog.loading ? "Carregando catálogo MT5..."
      : catalog.loaded ? "Nenhum ativo MT5 disponível"
        : unavailable ? "Catálogo MT5 indisponível"
        : "Catálogo MT5 ainda não carregado";
    symbol.setCatalog(assets, {
      selectedValue: selectedIndex >= 0 ? String(selectedIndex) : "",
      emptyLabel,
      allLabel: "Todos os ativos",
      assetClassLabel: options.assetClassLabel || ((value) => value),
    });
    if (previousAsset && selectedIndex < 0) invalidateResults();
  };
  const displayValue = (value) => {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  };
  const addDetailField = (parent, label, value) => {
    const row = document.createElement("div");
    const name = document.createElement("span");
    const content = document.createElement("b");
    name.textContent = label;
    content.textContent = displayValue(value);
    row.append(name, content);
    parent.append(row);
  };
  const renderDetail = (record, analysis) => {
    clearDetail();
    const status = String(analysis.analysis_status || analysis.status || record.status || "").toUpperCase();
    const title = document.createElement("h3");
    title.textContent = `${record.symbol || analysis.symbol || "Ativo não informado"} · ${record.timeframe || analysis.timeframe || "TF desconhecido"} · ${record.analysis_mode || analysis.analysis_mode || "MODO DESCONHECIDO"}`;
    const state = document.createElement("p");
    state.dataset.analysisResultState = status;
    const metadata = document.createElement("div");
    metadata.className = "d2GoldenAnalysisHistoryMetadata";
    addDetailField(metadata, "STATUS", status || "INCOMPLETA");
    addDetailField(metadata, "ANALYSIS ID", record.analysis_id);
    addDetailField(metadata, "PROVIDER / MODELO", analysis.model);
    addDetailField(metadata, "SNAPSHOT", record.snapshot_id || analysis.snapshot_id);
    addDetailField(metadata, "CORRELAÇÃO", record.correlation_id || analysis.audit_correlation_id || analysis.correlation_id);
    addDetailField(metadata, "CRIADA (ORIGINAL)", record.created_at || analysis.started_at);
    if (status === "ERROR") {
      state.textContent = "A análise foi persistida com falha; nenhuma conclusão analítica está disponível.";
      const code = safeCode(analysis.model_error_code || analysis.validation_error_code || analysis.reason_code);
      if (code) addDetailField(metadata, "MOTIVO SANITIZADO", code);
    } else {
      const complete = status === "COMPLETE";
      state.textContent = complete
        ? "Resultado concluído recuperado do registro canônico."
        : "Registro incompleto ou parcial; campos ausentes permanecem não informados.";
      [
        ["RESUMO", analysis.summary],
        ["ESTILO", analysis.analysis_style],
        ["HORIZONTES AVALIADOS", analysis.horizon_assessments],
        ["TIMEFRAMES AVALIADOS", analysis.timeframes_evaluated],
        ["ESTADO DE MERCADO", analysis.market_state],
        ["ESTRUTURA", analysis.market_structure],
        ["TENDÊNCIA", analysis.trend || analysis.directional_bias],
        ["MOMENTUM", analysis.momentum],
        ["CONTEXTO DE ROMPIMENTO", analysis.breakout_context],
        ["VOLATILIDADE", analysis.volatility],
        ["NÍVEIS IMPORTANTES", analysis.important_levels],
        ["RESUMO MULTITEMPORAL", analysis.multi_timeframe_summary],
        ["CONTEXTO MACRO", analysis.macro_context],
        ["RISCO DE EVENTOS/NOTÍCIAS", analysis.news_event_risk],
        ["SUPORTES", analysis.support_levels],
        ["RESISTÊNCIAS", analysis.resistance_levels],
        ["CONFIANÇA E SEMÂNTICA", analysis.confidence_semantics
          ? { value: analysis.confidence, semantics: analysis.confidence_semantics }
          : analysis.confidence],
        ["CENÁRIO PRINCIPAL", analysis.primary_scenario],
        ["CENÁRIO ALTERNATIVO", analysis.alternative_scenario],
        ["ENTRADA CONDICIONAL", analysis.entry_scenario],
        ["INVALIDAÇÃO", analysis.invalidation],
        ["ALVO ANALÍTICO", analysis.target_scenario],
        ["EVIDÊNCIAS", analysis.evidence_references],
        ["FONTES", analysis.sources],
        ["DISPONIBILIDADE DO CONTEXTO", analysis.context_availability],
        ["AUTORIDADE TEMPORAL", analysis.temporal_authority],
        ["PROVENIÊNCIA", analysis.provenance],
        ["LIMITAÇÕES", analysis.limitations || analysis.risk_warnings],
        ["AUTORIDADE DE EXECUÇÃO", analysis.execution_authority],
      ].forEach(([label, value]) => {
        if (value !== undefined && value !== null && value !== "") addDetailField(metadata, label, value);
      });
    }
    detail.append(title, state, metadata);
    detail.hidden = false;
  };
  const renderRows = (rows) => {
    list.replaceChildren();
    pageRows = rows;
    rows.forEach((record) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "d2GoldenAnalysisHistoryRow";
      button.dataset.analysisId = String(record.analysis_id || "");
      const primary = document.createElement("span");
      primary.textContent = `${record.symbol || "?"} · ${record.timeframe || "?"} · ${record.analysis_mode || "?"}`;
      const secondary = document.createElement("small");
      secondary.textContent = `${record.status || "UNKNOWN"} · ${record.created_at || "data original indisponível"}`;
      button.append(primary, secondary);
      list.append(button);
    });
    const pagination = document.createElement("footer");
    pagination.className = "d2LedgerFooter d2GoldenAnalysisHistoryPagination";
    const pageText = document.createElement("span");
    pageText.textContent = rows.length ? `${offset + 1}–${offset + rows.length}` : "0 registros nesta página";
    const previous = document.createElement("button");
    previous.type = "button";
    previous.textContent = "‹";
    previous.setAttribute("aria-label", "Página anterior de análises");
    previous.disabled = offset <= 0;
    previous.addEventListener("click", () => { if (!pending && offset > 0) void requestList(Math.max(0, offset - pageSize)); });
    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "›";
    next.setAttribute("aria-label", "Próxima página de análises");
    next.disabled = !hasMore || rows.length === 0;
    next.addEventListener("click", () => { if (!pending && hasMore && rows.length) void requestList(offset + rows.length); });
    const controls = document.createElement("div");
    controls.className = "d2Pagination";
    controls.append(previous, next);
    pagination.append(pageText, controls);
    list.append(pagination);
  };
  const requestList = async (requestedOffset = 0) => {
    if (pending) return;
    const gateway = window.Gateway;
    if (gateway?.isAuthenticated !== true || typeof gateway.httpPost !== "function") {
      renderRows([]);
      hasMore = false;
      clearDetail();
      setState("AUTENTICAÇÃO NECESSÁRIA", "Conecte o Desktop à sessão autenticada do Jarvis para consultar análises.");
      return;
    }
    const requestRevision = filterRevision;
    const selectedAsset = symbol.value === "" ? null : displayedAssets[Number(symbol.value)];
    if (symbol.value && (!selectedAsset || selectedAsset.provider !== "MT5"
        || selectedAsset.provider_asset_id !== `mt5:${selectedAsset.provider_symbol}`)) {
      setState("FILTRO INVÁLIDO", "O ativo selecionado não corresponde à identidade validada do catálogo MT5.");
      return;
    }
    const symbolValue = String(selectedAsset?.provider_symbol || "").trim().toUpperCase();
    pending = true;
    consult.disabled = true;
    consult.setAttribute("aria-busy", "true");
    clearDetail();
    setState("CONSULTANDO", "Solicitando lista autenticada de análises...");
    try {
      const response = await gateway.httpPost("/api/jarvis/golden/panel-analysis", {
        action: "LIST", symbol: symbolValue, analysis_mode: mode.value,
        status: statusFilter.value, limit: pageSize, offset: requestedOffset,
      });
      if (requestRevision !== filterRevision) return;
      const pageEnvelope = unwrap(response, (item) => Array.isArray(item?.data?.items));
      if (response?.http_failure === true || pageEnvelope?.http_failure === true) {
        renderRows([]);
        hasMore = false;
        const code = safeCode(response?.error_code || pageEnvelope?.error_code);
        const httpStatus = Number(response?.http_status || pageEnvelope?.http_status);
        setState("FALHA DE RECUPERAÇÃO", `Não foi possível consultar o histórico${Number.isFinite(httpStatus) && httpStatus > 0 ? ` · HTTP ${httpStatus}` : ""}${code ? ` · ${code}` : ""}.`);
        return;
      }
      const payload = unwrap(response, (item) => Array.isArray(item?.data?.items));
      const page = payload?.data;
      if (payload?.ok !== true || !page || !Array.isArray(page.items)
          || page.limit !== pageSize || page.offset !== requestedOffset
          || typeof page.has_more !== "boolean") {
        renderRows([]);
        hasMore = false;
        const code = safeCode(payload?.error_code);
        setState("FALHA DE RECUPERAÇÃO", code
          ? `A resposta do histórico não pôde ser reconciliada · ${code}.`
          : "A resposta do histórico não pôde ser reconciliada. Nenhum registro foi exibido.");
        return;
      }
      const rows = page.items.slice(0, pageSize).filter((record) => record
        && typeof record.analysis_id === "string"
        && /^panel_analysis_[A-Za-z0-9]+$/.test(record.analysis_id));
      offset = requestedOffset;
      hasMore = page.has_more && rows.length > 0;
      renderRows(rows);
      if (rows.length) setState("LISTA DISPONÍVEL", `${rows.length} análise(s) recuperável(is) nesta página. Selecione um registro para carregar o resultado completo.`);
      else setState("NENHUM REGISTRO", "Nenhuma análise corresponde aos filtros. Isso não é uma consulta ao Trade Journal.");
    } catch {
      if (requestRevision !== filterRevision) return;
      renderRows([]);
      hasMore = false;
      setState("FALHA DE RECUPERAÇÃO", "A consulta do histórico falhou. Nenhum resultado anterior foi reutilizado.");
    } finally {
      pending = false;
      consult.disabled = false;
      consult.removeAttribute("aria-busy");
    }
  };
  const requestRecord = async (record) => {
    const gateway = window.Gateway;
    if (!record || pending) return;
    clearDetail();
    if (gateway?.isAuthenticated !== true || typeof gateway.httpPost !== "function") {
      setState("AUTENTICAÇÃO NECESSÁRIA", "A sessão autenticada não está disponível para recuperar o registro.");
      return;
    }
    pending = true;
    const requestRevision = filterRevision;
    detail.hidden = false;
    detail.textContent = "Recuperando resultado completo...";
    try {
      const response = await gateway.httpPost("/api/jarvis/golden/panel-analysis", {
        action: "GET", analysis_id: record.analysis_id,
      });
      if (requestRevision !== filterRevision) return;
      const payload = unwrap(response, (item) => item?.analysis && typeof item.analysis === "object");
      if (response?.http_failure === true || payload?.http_failure === true) {
        clearDetail();
        setState("FALHA DE RECUPERAÇÃO", "A recuperação autenticada do resultado falhou. Nenhum dado de análise foi apresentado.");
        return;
      }
      if (payload?.ok !== true || payload?.found !== true || !payload.analysis) {
        clearDetail();
        if (payload?.status === "NOT_FOUND" || payload?.found === false) {
          setState("REGISTRO NÃO ENCONTRADO", "O registro selecionado não está disponível no histórico canônico.");
        } else {
          const code = safeCode(payload?.error_code);
          setState("FALHA DE RECUPERAÇÃO", code
            ? `O resultado não pôde ser recuperado · ${code}.`
            : "O resultado não pôde ser recuperado. Nenhum resultado anterior foi reutilizado.");
        }
        return;
      }
      const analysis = payload.analysis;
      const analysisStatus = String(analysis.analysis_status || analysis.status || "").toUpperCase();
      const reconciled = analysis.analysis_id === record.analysis_id
        && analysis.symbol === record.symbol
        && analysis.timeframe === record.timeframe
        && analysis.analysis_mode === record.analysis_mode
        && String(analysis.snapshot_id || "") === String(record.snapshot_id || "")
        && analysisStatus === String(record.status || "").toUpperCase();
      if (!reconciled) {
        clearDetail();
        setState("IDENTIDADE DIVERGENTE", "Os metadados do registro e do resultado completo não correspondem. O resultado foi ocultado.");
        return;
      }
      renderDetail(record, analysis);
      setState(analysisStatus === "ERROR" ? "ANÁLISE COM ERRO"
        : analysisStatus === "COMPLETE" ? "ANÁLISE CONCLUÍDA" : "ANÁLISE INCOMPLETA",
      "Resultado recuperado pelo GET canônico. Esta consulta não iniciou análise nem acessou MT5/provider.");
    } catch {
      if (requestRevision !== filterRevision) return;
      clearDetail();
      setState("FALHA DE RECUPERAÇÃO", "A recuperação do registro falhou. Nenhum resultado anterior foi reutilizado.");
    } finally {
      pending = false;
    }
  };

  consult.addEventListener("click", () => { void requestList(0); });
  [symbol, mode, statusFilter].forEach((filter) => {
    filter.addEventListener("change", invalidateResults);
  });
  const ensureCatalog = () => {
    if (typeof options.ensureCatalog === "function") options.ensureCatalog();
  };
  list.addEventListener("click", (event) => {
    const target = event.target?.closest?.("[data-analysis-id]");
    if (!target) return;
    const record = pageRows.find((item) => item.analysis_id === target.dataset.analysisId);
    if (record) void requestRecord(record);
  });
  refreshCatalog();
  return {refreshCatalog, symbol};
}

