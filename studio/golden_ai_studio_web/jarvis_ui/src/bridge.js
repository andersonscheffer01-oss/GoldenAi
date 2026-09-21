/**
 * Bridge — Communication layer (staging version)
 * 
 * REPLACES: original bridge.js with X-Ja-Token header
 * NOW: Uses Gateway adapter for WS communication with device auth protocol
 * 
 * Protocol: Gateway WS V1 (hello → auth → command → result)
 * Auth: Device token via WS messages (NOT HTTP header)
 * No standalone HTTP fallback (Gateway is authoritative)
 */

export function createBridge(handlers = {}) {
  const {
    onStatus = () => {}, onMessage = () => {}, onTelemetry = () => {}, onLog = () => {},
  } = handlers;

  let status = "offline";
  let serverInfo = null;
  let informedOffline = false;

  function setStatus(s, detail) {
    status = s;
    onStatus(s, detail, serverInfo);
  }

  function reportOffline(msg) {
    if (informedOffline) return;
    informedOffline = true;
    onLog(msg, "bad");
    onLog("Modo local ativo. Para controlar o PC, conecte-se ao Gateway.", "");
  }

  // ─── Gateway Integration ───

  function initGateway() {
    if (!window.Gateway) {
      setStatus("offline", "Gateway adapter não encontrado");
      return;
    }

    window.Gateway.on('status', (s) => {
      if (s === 'online') {
        serverInfo = { name: 'jarvis-gateway', version: '1.0' };
        informedOffline = false;
        setStatus("online", "Gateway conectado");
        onLog("Gateway WebSocket conectado", "ok");
      } else if (s === 'connecting') {
        setStatus("connecting");
      } else if (s === 'disconnected') {
        setStatus("offline", "desconectado");
      } else if (s === 'auth_error') {
        setStatus("offline", "autenticação falhou");
      }
    });

    window.Gateway.on('authenticated', () => {
      onLog("Autenticado com Gateway", "ok");
    });

    window.Gateway.on('auth_error', (payload) => {
      onLog("Erro de autenticação: " + (payload.error || "token inválido"), "bad");
    });

    window.Gateway.on('command_result', (payload) => {
      onMessage({ type: "command_result", ...payload });
    });

    window.Gateway.on('command_error', (payload) => {
      onMessage({ type: "command_error", ...payload });
    });

    window.Gateway.on('confirmation_required', (payload) => {
      onMessage({ type: "confirmation_required", ...payload });
    });

    window.Gateway.on('event', (payload) => {
      onMessage({ type: "event", ...payload });
    });

    window.Gateway.on('disconnected', () => {
      setStatus("offline", "Gateway desconectado");
    });

    window.Gateway.on('error', () => {
      reportOffline("Gateway WebSocket não encontrado — modo local ativo.");
    });
  }

  // ─── Public API (compatible with app.js) ───

  function connect() {
    if (!window.Gateway) {
      setStatus("offline", "Gateway adapter não carregado");
      reportOffline("Gateway adapter não encontrado.");
      return;
    }
    initGateway();
    window.Gateway.start(true);
  }

  function disconnect() {
    if (window.Gateway) window.Gateway.disconnect();
    setStatus("offline", "desconectado");
  }

  function configure(next = {}) {
    // Gateway adapter handles configuration internally
    // Token management via Gateway.setToken()
    if (next.token && window.Gateway) {
      window.Gateway.setToken(next.token);
    }
    return {};
  }

  async function sendCommand(text, extra = {}) {
    if (!window.Gateway || !window.Gateway.isAuthenticated) {
      return { ok: false, error: "offline" };
    }
    try {
      const result = await window.Gateway.sendCommand(text, extra);
      return { ok: true, data: result };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  }

  function sendRaw(obj) {
    // Legacy compatibility — not used in staging
    console.warn('sendRaw called — deprecated in staging. Use Gateway.sendCommand()');
    return false;
  }

  async function test() {
    if (!window.Gateway) return { ok: false, error: "Gateway adapter não encontrado" };
    const t0 = performance.now();
    try {
      window.Gateway.connect();
      const ms = Math.round(performance.now() - t0);
      return { ok: true, ms, info: { name: 'jarvis-gateway' } };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  }

  return {
    configure, connect, disconnect, test, sendCommand, sendRaw,
    get status() { return status; },
    get kind() { return "ws"; },
    get info() { return serverInfo; },
    get config() { return {}; },
  };
}
