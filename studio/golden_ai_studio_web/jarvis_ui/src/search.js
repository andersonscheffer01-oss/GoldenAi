/**
 * Search — Internet search (staging version)
 * 
 * SECURITY: ALL external searches route through Gateway → JarvisService → web_research tool.
 * NO direct fetch to Bing, Wikipedia, DuckDuckGo, HN from browser.
 * If Gateway unavailable: show "PESQUISA INDISPONÍVEL".
 * No CORS proxy. No arbitrary URL proxy.
 */

const TAGS = { noticia: "noticia", wiki: "enciclopedia", resposta: "resposta direta", relacionado: "topico relacionado", comunidade: "comunidade" };

function clean(s) {
  return String(s || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
}

function keyOf(r) {
  try { const u = new URL(r.url); return (u.hostname + u.pathname).replace(/\/$/, "").toLowerCase(); } catch { return r.url; }
}

function dedupe(list) {
  const seen = new Set();
  return list.filter((r) => {
    const k = keyOf(r);
    if (!k || seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

const RANK = { resposta: 0, noticia: 1, wiki: 2, relacionado: 3, comunidade: 4 };

/**
 * Search via Gateway web_research tool (ONLY path)
 */
async function searchViaGateway(query, { onStep, budgetMs = 22000 } = {}) {
  onStep?.("buscando via Gateway web_research", "ok");
  
  if (!window.Gateway || !window.Gateway.isAuthenticated) {
    throw new Error("Gateway nao conectado");
  }

  const result = await window.Gateway.sendCommand(`pesquise na web: ${query}`);
  
  if (!result || !result.ok) {
    throw new Error(result?.error || "Gateway web_research falhou");
  }

  const results = [];
  const sources = result.sources || [];
  
  for (const src of sources) {
    results.push({
      title: src.title || src.name || "Resultado",
      url: src.url || src.link || "",
      host: src.url ? hostOf(src.url) : (src.source || "web"),
      snippet: src.snippet || src.excerpt || src.content || "",
      kind: src.type || "web",
      at: src.date ? Date.parse(src.date) : null,
      source: src.source || "gateway",
    });
  }

  if (result.summary || result.reply) {
    results.unshift({
      title: "Resumo Gateway",
      url: "",
      host: "jarvis-gateway",
      snippet: result.summary || result.reply || "",
      kind: "resposta",
      at: null,
      source: "gateway",
    });
  }

  return {
    ok: results.length > 0,
    query,
    response: result.response || result.message || result.reply || result.text || "",
    response_id: result.response_id || result.routing_metadata?.response_id || result.routing_metadata?.request_id || "",
    session_id: result.routing_metadata?.session_id || "",
    routing_metadata: result.routing_metadata || {},
    spoken_response: result.spoken_response || "",
    results: dedupe(results).sort((a, b) => ((RANK[a.kind] ?? 5) - (RANK[b.kind] ?? 5)) || ((b.at || 0) - (a.at || 0))).slice(0, 20),
    sources: ["Gateway web_research"],
    source: "GATEWAY",
    at: Date.now(),
  };
}

export function createSearch({ onLog } = {}) {
  let running = false;

  async function run(query, { onStep, budgetMs = 22000 } = {}) {
    const q = String(query || "").trim();
    const steps = [];
    const step = (label, state = "ok") => { steps.push({ label, state }); onStep?.(label, state, steps.slice()); };
    if (!q) return { ok: false, error: "Consulta vazia.", results: [], steps };
    if (running) return { ok: false, error: "Ja existe uma busca em andamento.", results: [], steps };

    running = true;
    try {
      // ONLY path: Gateway web_research
      if (!window.Gateway || !window.Gateway.isAuthenticated) {
        step("Gateway nao conectado — pesquisa indisponivel", "warn");
        onLog?.("pesquisa indisponivel — Gateway offline", "bad");
        return { ok: false, query: q, results: [], steps, sources: [], error: "PESQUISA INDISPONIVEL — Gateway nao conectado.", source: "UNAVAILABLE" };
      }

      try {
        step("buscando via Gateway web_research");
        const gwResult = await searchViaGateway(q, { onStep, budgetMs });
        if (gwResult.ok) {
          onLog?.(`pesquisa · ${gwResult.results.length} resultados via Gateway para "${q.slice(0, 30)}"`, "ok");
          return { ...gwResult, steps };
        }
        step("Gateway nao retornou resultados", "warn");
        return { ok: false, query: q, results: [], steps, sources: [], error: "Nenhum resultado retornado pelo Gateway.", source: "GATEWAY_EMPTY" };
      } catch (e) {
        step(`Gateway falhou: ${e.message}`, "warn");
        onLog?.(`pesquisa falhou: ${e.message}`, "bad");
        return { ok: false, query: q, results: [], steps, sources: [], error: "PESQUISA INDISPONIVEL — " + e.message, source: "GATEWAY_ERROR" };
      }
    } finally {
      running = false;
    }
  }

  return { run, isRunning: () => running };
}

export const searchUrlFor = (q) => `https://duckduckgo.com/?q=${encodeURIComponent(String(q || ""))}`;
export const SOURCE_COUNT = 0;
export const KIND_TAGS = TAGS;

// Capability marker for UI-1.1 audit
export const SEARCH_BACKEND_CAPABILITY = {
  gateway: !!(window.Gateway && window.Gateway.isAuthenticated),
  directFallback: false,
  mode: (window.Gateway && window.Gateway.isAuthenticated) ? "GATEWAY_ONLY" : "UNAVAILABLE",
};
