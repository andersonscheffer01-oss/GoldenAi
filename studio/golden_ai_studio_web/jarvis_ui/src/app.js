import { THEMES, getTheme, resolveThemeId } from "./themes.js";
import { createHud } from "./hud.js";
import { createVoice, voiceSupported, ttsSupported } from "./voice.js";
import { createDesktopVoiceClient } from "./desktop-voice.js";
import { createBridge } from "./bridge.js";
import { createBrain } from "./brain.js?v=20260921-4";
import { sfx, setMuted, tone } from "./audio.js";
import { createMetrics } from "./metrics.js";
import { createGolden } from "./golden.js?v=20260928-b3-runtime-reconcile";
import { createSearch } from "./search.js?v=20260921-4";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hexToRgb = (hex) => {
  const m = String(hex).trim().replace("#", "");
  if (m.length !== 6) return [255, 255, 255];
  return [parseInt(m.slice(0, 2), 16), parseInt(m.slice(2, 4), 16), parseInt(m.slice(4, 6), 16)];
};
const storeKey = (k) => `jarvis.${k}.v1::${window.generatorName || "local"}`;

function loadJSON(key, fallback) {
  try { const v = JSON.parse(localStorage.getItem(storeKey(key))); return v == null ? fallback : v; } catch { return fallback; }
}
function saveJSON(key, val) { try { localStorage.setItem(storeKey(key), JSON.stringify(val)); } catch {} }

// ------------------------------------------------------------------ DOM ----
const app = $("#app");
const hudCanvas = $("#hudCanvas");
const orbWrap = $("#orbWrap");
const conversationEl = $("#conversation");
const thinkingBar = $("#thinkingBar");
const thinkingText = $("#thinkingText");
const cmdInput = $("#cmdInput");
const micBtn = $("#micBtn");
const isJarvisDesktop = window.__JARVIS_DESKTOP__ === true;
const sendBtn = $("#sendBtn");
const stateText = $("#stateText");
const stateHint = $("#stateHint");
const statusText = $("#statusText");
const moduleListEl = $("#moduleList");
const quickActionsEl = $("#quickActions");
const quickChipsEl = $("#quickChips");
const telemetryEl = $("#telemetry");
const activityLogEl = $("#activityLog");
const voiceCard = $("#voiceCard");
const vcBar = $("#vcBar");
const vcState = $("#vcState");
const vcWake = $("#vcWake");
const vcLast = $("#vcLast");
const toastCtn = $("#toastCtn");
const bootOverlay = $("#bootOverlay");
const bootLinesEl = $("#bootLines");
const settingsModal = $("#settingsModal");

// -------------------------------------------------------- PJS / CONFIG -----
function pjsCfg(key, fallback) {
  try {
    const v = window.JARVIS_CONFIG?.[key];
    if (v == null) return fallback;
    const s = typeof v === "string" ? v : String(v);
    return s.trim() === "" ? fallback : s;
  } catch { return fallback; }
}
function pjsList(name) {
  try {
    const all = window.JARVIS_LISTS?.[name];
    if (!all || !Array.isArray(all)) return [];
    return all.filter(Boolean);
  } catch { return []; }
}

const CFG = {
  systemName: pjsCfg("systemName", "J.A.R.V.I.S."),
  systemSub: pjsCfg("systemSub", "Sistema de Operações Pessoais"),
  userName: pjsCfg("userName", "Senhor"),
  defaultTheme: pjsCfg("defaultTheme", "golden"),
  tagline: pjsCfg("tagline", "MAIS QUE IA. UM PARCEIRO DE EVOLUÇÃO."),
  objective: pjsCfg("objective", ""),
  wakeWord: pjsCfg("wakeWord", "jarvis"),
  language: pjsCfg("language", "pt-BR"),
  voiceRate: parseFloat(pjsCfg("voiceRate", "1.02")) || 1.02,
  voicePitch: parseFloat(pjsCfg("voicePitch", "0.82")) || 0.82,
  backendUrl: pjsCfg("backendUrl", "http://localhost:8765"),
  token: pjsCfg("backendToken", ""),
  speak: pjsCfg("speakReplies", "true") !== "false",
  autoConnect: pjsCfg("autoConnect", "true") !== "false",
  boot: pjsCfg("bootSequence", "true") !== "false",
};

const MARKET_WINDOW_MODE = window.location.hash === "#market-intelligence";
const saved = loadJSON("settings", {});
const settings = {
  theme: MARKET_WINDOW_MODE ? "golden" : (saved.theme || CFG.defaultTheme),
  speak: saved.speak != null ? saved.speak : CFG.speak,
  wake: saved.wake || false,
  voiceName: saved.voiceName || "",
  rate: saved.rate ?? CFG.voiceRate,
  pitch: saved.pitch ?? CFG.voicePitch,
  wakeWord: saved.wakeWord || CFG.wakeWord,
  backendUrl: saved.backendUrl || CFG.backendUrl,
  token: saved.token ?? CFG.token,
  autoConnect: saved.autoConnect != null ? saved.autoConnect : CFG.autoConnect,
  lastCity: saved.lastCity || "",
  muted: !!saved.muted,
  objective: saved.objective || CFG.objective || "",
  agent: saved.agent || "auto",      // auto | local | backend | ia
  advanced: !!saved.advanced,        // manda o comando cru ao backend
  browserTts: saved.browserTts != null ? !!saved.browserTts : false,
  uiVersion: 1,
};

// Migração de interface: quem já tinha salvo um tema antigo passa a ver o painel
// GOLDEN JARVIS (o novo padrão). A versão fica gravada para não repetir.
if (!saved.uiVersion || saved.uiVersion < 1) {
  if (saved.theme) settings.theme = CFG.defaultTheme;
  try { localStorage.setItem(storeKey("settings"), JSON.stringify(settings)); } catch {}
}

function persist() { saveJSON("settings", settings); }

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

const notes = {
  all: loadJSON("notes", []).map((n) => ({ ...n, id: n.id || uid(), done: !!n.done })),
  add(text) {
    const item = { id: uid(), text: String(text), ts: Date.now(), done: false };
    this.all.push(item);
    saveJSON("notes", this.all);
    return item;
  },
  toggle(id) {
    const n = this.all.find((x) => String(x.id) === String(id));
    if (n) { n.done = !n.done; saveJSON("notes", this.all); }
    return n;
  },
  list() { return this.all.slice().reverse(); },
  clear() { this.all = []; saveJSON("notes", this.all); },
};

// ------------------------------------------------------- TIMERS ATIVOS -----
// O painel GOLDEN JARVIS mostra estes cronômetros como "tarefas em andamento",
// com progresso real (decorrido / total) e a contagem restante ao vivo.
const activeTimers = [];
function armTimer(ms, label) {
  const t = { id: uid(), label, start: Date.now(), end: Date.now() + ms, ms };
  activeTimers.push(t);
  golden?.refresh();
  setTimeout(() => {
    const i = activeTimers.indexOf(t);
    if (i >= 0) activeTimers.splice(i, 1);
    golden?.refresh();
  }, ms);
  return t;
}
const getTimers = () => activeTimers.map((t) => ({ id: t.id, label: t.label, start: t.start, end: t.end }));

// ------------------------------------------------- ANEXO DO COMANDO MANUAL --
// Um arquivo de texto anexado viaja junto do próximo comando escrito (não dos
// comandos de voz nem dos botões). Imagens e binários vão apenas como metadados.
let attachment = null;
function readAttachment(file) {
  return new Promise((resolve) => {
    const base = { name: file.name, size: file.size, type: file.type || "" };
    const isText = /^text\//.test(file.type) ||
      /\.(txt|md|markdown|json|csv|tsv|log|py|js|mjs|ts|tsx|jsx|html|htm|css|xml|yml|yaml|ini|cfg|conf|toml|sh|bat|ps1|c|h|cpp|cs|java|sql|env)$/i.test(file.name);
    if (!isText || file.size > 400 * 1024) { resolve(base); return; }
    const fr = new FileReader();
    fr.onload = () => resolve({ ...base, text: String(fr.result || "").slice(0, 12000) });
    fr.onerror = () => resolve(base);
    try { fr.readAsText(file.slice(0, 400 * 1024)); } catch { resolve(base); }
  });
}
function setAttachment(a) { attachment = a; golden?.refreshAttachment?.(); }
const getAttachment = () => attachment;
function takeAttachment() { const a = attachment; attachment = null; golden?.refreshAttachment?.(); return a; }

// --------------------------------------------------- PESQUISA NA INTERNET ---
const searchHist = loadJSON("searches", []);
function addSearchHistory(q) {
  const s = String(q || "").trim();
  if (!s) return;
  const i = searchHist.indexOf(s);
  if (i >= 0) searchHist.splice(i, 1);
  searchHist.unshift(s);
  if (searchHist.length > 12) searchHist.length = 12;
  saveJSON("searches", searchHist);
}
function clearSearchHistory() { searchHist.length = 0; saveJSON("searches", searchHist); }
const searchEngine = createSearch({ onLog: (m, k) => logLine(m, k) });

// -------------------------------------------------------------- ESTADO -----
let appState = "idle";
let alertTimer = 0;
const bootLines = pjsList("bootLine");
const idleQuips = pjsList("idleQuip");
let quipIdx = 0;
let pendingReply = null;
let lastTask = "";
let golden = null;   // criado mais abaixo; usado por setState/voz/backend

const hud = createHud(hudCanvas);
const metrics = createMetrics({ getFps: () => hud.getFps() });
const startedAt = Date.now();

function uptime() {
  const up = Math.floor((Date.now() - startedAt) / 1000);
  return `${String(Math.floor(up / 60)).padStart(2, "0")}:${String(up % 60).padStart(2, "0")}`;
}
function clearConversation() { conversationEl.innerHTML = ""; }
function setSilent(on) { setMuted(!!on); if (on) voice.stopSpeaking(); }
function getConversation() { return { count: conversationEl.children.length }; }
function exportMemory() {
  try {
    const prefs = { ...settings };
    delete prefs.token;
    const payload = {
      geradoPor: `${CFG.systemName} · GOLDEN JARVIS`,
      gerador: window.generatorName || null,
      exportadoEm: new Date().toISOString(),
      objetivo: settings.objective,
      preferencias: prefs,
      anotacoes: notes.all,
      buscas: searchHist.slice(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `jarvis-memoria-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    logLine("memória exportada em JSON", "ok");
    return true;
  } catch (e) {
    logLine("falha ao exportar memória: " + (e?.message || e), "bad");
    return false;
  }
}

function readPalette() {
  const cs = getComputedStyle(app);
  const a = cs.getPropertyValue("--accent-rgb").split(",").map((n) => parseFloat(n) || 0);
  const b = hexToRgb(cs.getPropertyValue("--accent-2"));
  hud.setPalette(a, b);
  hud.setTitle?.(CFG.systemName);
}

function setState(s, ms) {
  clearTimeout(alertTimer);
  appState = s || "idle";
  app.dataset.state = appState;
  hud.setState(appState);
  const labels = {
    idle: ["EM ESPERA", null], listening: ["OUVINDO", "Fale agora..."],
    thinking: ["PROCESSANDO", "Analisando o comando"],
    executing: ["EXECUTANDO", "Enviando ao backend"],
    speaking: ["RESPONDENDO", ""], alert: ["⚠ ALERTA", "Vigilância máxima"],
  };
  const [label, hint] = labels[appState] || labels.idle;
  stateText.textContent = label;
  if (hint != null) stateHint.textContent = hint;
  if (appState === "alert") hud.pulse();
  golden?.setState(appState);
  if (appState === "idle") golden?.setTask(lastTask ? `✓ ${lastTask}` : "Aguardando instruções");
  readPalette();
  if (ms) alertTimer = setTimeout(() => setState("idle"), ms);
}

// -------------------------------------------------------------- SAÍDA ------
function toast(title, msg, kind = "") {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.innerHTML = `<b>${esc(title)}</b>${esc(msg)}`;
  toastCtn.appendChild(el);
  setTimeout(() => { el.style.transition = "opacity .4s, transform .4s"; el.style.opacity = "0"; el.style.transform = "translateX(20px)"; }, 4200);
  setTimeout(() => el.remove(), 4800);
}
let lastLogKey = "", lastLogEl = null, lastLogCount = 0;
function logLine(msg, kind = "") {
  const time = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const key = kind + "\u0000" + msg;
  if (key === lastLogKey && lastLogEl && lastLogEl.isConnected) {
    lastLogCount++;
    lastLogEl.querySelector("time").textContent = time;
    let rep = lastLogEl.querySelector("b.rep");
    if (!rep) { rep = document.createElement("b"); rep.className = "rep"; lastLogEl.appendChild(rep); }
    rep.textContent = "\u00d7" + lastLogCount;
    return;
  }
  lastLogKey = key; lastLogCount = 1;
  const d = document.createElement("div");
  d.innerHTML = `<time>${time}</time><span class="${kind}">${esc(msg)}</span>`;
  activityLogEl.prepend(d);
  lastLogEl = d;
  while (activityLogEl.children.length > 60) activityLogEl.lastChild.remove();
}

function formatRich(text) {
  if (window.SafeMarkdown) return window.SafeMarkdown(String(text || ""));
  return esc(text).replace(/\n/g, "<br>");
}

function addMessage(role, text, opts = {}) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + role;
  const tag = { user: "VOCÊ", jarvis: "JARVIS", sys: "SIST", err: "ERRO" }[role] || "SIST";
  const av = document.createElement("div");
  av.className = "avatar";
  av.textContent = role === "user" ? "EU" : role === "err" ? "!" : "AI";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `${tag} · ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  const body = document.createElement("div");
  body.className = "body";
  if (text) body.innerHTML = formatRich(text);
  bubble.appendChild(meta);
  bubble.appendChild(body);
  if (opts.actions?.length) {
    const ul = document.createElement("ul");
    ul.className = "actionList";
    for (const a of opts.actions) {
      const li = document.createElement("li");
      const st = a.status === "ok" ? "ok" : "no";
      li.innerHTML = `<span class="${st}">${a.status === "ok" ? "▸" : "✕"}</span> <b>${esc(a.name)}</b>${a.detail ? " — " + esc(a.detail) : ""}`;
      ul.appendChild(li);
    }
    bubble.appendChild(ul);
  }
  wrap.appendChild(av);
  wrap.appendChild(bubble);
  conversationEl.appendChild(wrap);
  conversationEl.scrollTop = conversationEl.scrollHeight;
  window.dispatchEvent(new CustomEvent("jarvis:message-added", { detail: { role, text: String(text || "") } }));
  return {
    wrap, body,
    setText(t) { body.innerHTML = formatRich(t); conversationEl.scrollTop = conversationEl.scrollHeight; },
    setPlain(t) { body.textContent = t; conversationEl.scrollTop = conversationEl.scrollHeight; },
    appendPlain(t) { body.textContent += t; conversationEl.scrollTop = conversationEl.scrollHeight; },
    finalize(t) { body.classList.remove("typing"); body.innerHTML = formatRich(t); conversationEl.scrollTop = conversationEl.scrollHeight; },
  };
}

async function typeInto(msg, text, speed = 12) {
  msg.body.classList.add("typing");
  if (text.length > 220) { msg.setText(text); msg.body.classList.remove("typing"); return; }
  let out = "";
  for (let i = 0; i < text.length; i++) {
    out += text[i];
    msg.setPlain(out);
    if (i % 2 === 0) await new Promise((r) => setTimeout(r, speed));
  }
  msg.finalize(text);
}

function renderResponse(out) {
  if (!out) return;
  const isErr = out.error || out.intent === "unknown";
  if (!out.streamed) {
    const msg = addMessage(isErr ? "err" : "jarvis", "", { actions: out.actions });
    if (out.typing === false) msg.setText(out.reply);
    else typeInto(msg, out.reply);
  }
  if (out.actions?.length) {
    for (const a of out.actions) logLine(`${a.name} ${a.status === "ok" ? "OK" : "FALHOU"}${a.detail ? " · " + a.detail : ""}`, a.status === "ok" ? "ok" : "bad");
  }
  if (out.speak !== false && settings.speak && out.speakText !== null) {
    const toSay = out.speakText || (typeof out.speak === "string" ? out.speak : out.reply);
    if (toSay) speak(toSay);
  }
}

// ------------------------------------------------------------------ VOZ ----
let speakAnim = 0;
function startSpeakAnim() {
  stopSpeakAnim();
  const t0 = performance.now();
  speakAnim = setInterval(() => {
    const t = (performance.now() - t0) / 1000;
    hud.setAmplitude(0.25 + 0.4 * Math.abs(Math.sin(t * 7.3)) + Math.random() * 0.18);
  }, 70);
}
function stopSpeakAnim() { clearInterval(speakAnim); speakAnim = 0; hud.setAmplitude(0); }

const voice = createVoice({
  onPartial: (t) => { stateHint.textContent = "«" + t + "»"; },
  onFinal: (t) => { stateHint.textContent = ""; submitCommand(t, "voz"); },
  onError: (m) => { toast("VOZ", m, "bad"); logLine(m, "bad"); setState("idle"); micBtn.classList.remove("listening"); },
  onAmplitude: (v) => {
    vcBar.style.width = Math.round(Math.min(1, v) * 100) + "%";
    golden?.setAmplitude(v);
    if (appState === "listening") hud.setAmplitude(v);
  },
  onListeningChange: (on) => {
    micBtn.classList.toggle("listening", on);
    voiceCard.dataset.on = on ? "1" : "0";
    vcState.textContent = on ? "ESCUTANDO" : "PARADO";
    if (on) setState("listening");
    else if (appState === "listening") setState("idle");
  },
  onSpeakStart: () => { setState("speaking"); startSpeakAnim(); },
  onSpeakEnd: () => { stopSpeakAnim(); if (appState === "speaking") setState("idle"); },
  onWake: () => { sfx.ping(); toast("JARVIS", "Palavra-chave detectada. Estou ouvindo.", "ok"); },
});

function applyDesktopVoiceState(state) {
  const normalized = String(state || "OFF").toUpperCase();
  const listening = ["OUVINDO", "WAITING_WAKE", "LISTENING", "WAKE_DETECTED"].includes(normalized);
  const processing = ["TRANSCRIBING", "PROCESSING", "CAPTURING_FOLLOWUP"].includes(normalized);
  micBtn.classList.toggle("listening", listening);
  voiceCard.dataset.on = listening || processing ? "1" : "0";
  vcState.textContent = processing ? "PROCESSANDO" : listening ? "ESCUTANDO" :
    normalized === "SPEAKING" ? "FALANDO" : normalized === "ERROR" ? "ERRO" : "PARADO";
  if (processing) setState("thinking");
  else if (listening) setState("listening");
  else if (normalized === "SPEAKING") setState("speaking");
  else if (appState === "listening" || appState === "thinking" || appState === "speaking") setState("idle");
}

const desktopVoice = isJarvisDesktop ? createDesktopVoiceClient({
  gateway: window.Gateway,
  onState: applyDesktopVoiceState,
  onEvent: (event) => {
    const heard = String(event?.heard || "").trim();
    const response = String(event?.response || event?.canonical_response || "").trim();
    if (heard) addMessage("user", heard, { typing: false });
    if (response) addMessage("jarvis", response, { typing: false });
    stateHint.textContent = "";
    applyDesktopVoiceState("WAITING_WAKE");
  },
  onError: (message) => {
    toast("VOZ", message, "bad");
    logLine(message, "bad");
    applyDesktopVoiceState("ERROR");
  },
}) : null;

voice.setLang(CFG.language);
voice.setRate(settings.rate);
voice.setPitch(settings.pitch);
voice.setVoice(settings.voiceName);
voice.setWakeWord(settings.wakeWord);

function speak(text) {
  if (isJarvisDesktop || !settings.browserTts || !text) return;
  voice.speak(text);
}

// -------------------------------------------------------------- BACKEND ----
let serverTelemetry = null;
let lastMarket = [];   // últimas cotações reais devolvidas pelo backend
let lastConn = "offline";
let readyAnnounced = false;
const bridge = createBridge({
  onStatus: (s, detail) => {
    app.dataset.conn = s;
    statusText.textContent = s === "online" ? "ONLINE" : s === "connecting" ? "..." : "LOCAL";
    if (s === "online" && lastConn !== "online") {
      logLine("Backend conectado" + (detail ? " · " + detail : ""), "ok");
      if (!readyAnnounced) {
        readyAnnounced = true;
        addMessage("jarvis", `Sistemas online. ${CFG.systemName} à sua disposição.`, { typing: false });
        if (settings.speak) speak(`Sistemas online. Bom trabalho, ${CFG.userName}.`);
      }
    }
    else if (s === "offline" && lastConn === "online") logLine("Backend desconectado" + (detail ? " - " + detail : ""), "bad");
    lastConn = s;
    golden?.setConnection(s, detail);
    updateModules();
  },
  onLog: (m, k) => logLine(m, k),
  onTelemetry: (data) => { serverTelemetry = data || null; metrics.setServerTelemetry(serverTelemetry); },
  onMessage: (msg) => {
    if (msg.type === "chunk") {
      if (!pendingReply) { pendingReply = addMessage("jarvis", ""); pendingReply.body.classList.add("typing"); }
      pendingReply.appendPlain(msg.text || "");
      if (settings.speak && msg.text) { /* fala só no fim */ }
      return;
    }
    if (msg.type === "reply") {
      const text = msg.text || "";
      if (pendingReply) { pendingReply.finalize(text); pendingReply = null; }
      else renderResponse({ reply: text, actions: msg.actions, streamed: false });
      if (msg.speak !== false && settings.speak) speak(msg.speak === true ? text : msg.speak || text);
      setState("idle");
      return;
    }
    if (msg.type === "action") { logLine(`${msg.name || "ação"} ${msg.status || ""}${msg.detail ? " · " + msg.detail : ""}`, msg.status === "falha" ? "bad" : "ok"); return; }
    if (msg.type === "state") { if (msg.state) setState(msg.state); return; }
    if (msg.type === "hud") { applyRemoteHud(msg); return; }
    if (msg.type === "error") { addMessage("err", msg.message || "Erro no backend"); setState("idle"); return; }
    if (msg.type === "confirmation_required") { showConfirmationDialog(msg); return; }
    if (msg.type === "command_result" || msg.type === "command_error") return;
    if (msg.text) renderResponse({ reply: msg.text });
  },
});

function applyRemoteHud(msg) {
  if (msg.theme) applyTheme(msg.theme, true);
  if (msg.clear) conversationEl.innerHTML = "";
  if (msg.say) { const m = addMessage("jarvis", ""); typeInto(m, msg.say); }
  if (msg.speak && settings.speak) speak(msg.speak === true ? msg.say : msg.speak);
  if (msg.toast) toast(msg.title || "JARVIS", msg.toast, "ok");
}

// -------------------------------------------------------- CONTEXTO BRAIN ---
const LOCAL_ONLY = new Set(["theme", "clear", "fullscreen", "alert", "help", "system", "calc", "notes-add", "notes-list", "notes-clear", "timer", "weather", "whoami"]);

async function getSystemReport() {
  const lines = [`Relatório de sistemas — ${new Date().toLocaleString("pt-BR")}`, ""];
  const cores = navigator.hardwareConcurrency || "?";
  lines.push(`• Núcleos de processamento: ${cores}`);
  const mem = navigator.deviceMemory || (performance.memory ? (performance.memory.jsHeapSizeLimit / 1073741824).toFixed(1) + " (limite JS)" : null);
  if (mem) lines.push(`• Memória do dispositivo: ${mem} GB`);
  if (performance.memory) {
    const m = performance.memory;
    lines.push(`• Heap JS em uso: ${(m.usedJSHeapSize / 1048576).toFixed(1)} MB de ${(m.totalJSHeapSize / 1048576).toFixed(1)} MB`);
  }
  const conn = navigator.connection;
  if (conn) lines.push(`• Rede: ${conn.effectiveType || "?"} · ${conn.downlink ?? "?"} Mb/s · latência ${conn.rtt ?? "?"} ms`);
  lines.push(`• Conexão: ${navigator.onLine ? "ativa" : "offline"}`);
  try {
    const b = await (navigator.getBattery ? navigator.getBattery() : Promise.reject());
    lines.push(`• Bateria: ${Math.round(b.level * 100)}%${b.charging ? " (carregando)" : ""}`);
  } catch { lines.push("• Bateria: leitura não disponível neste navegador"); }
  if (navigator.storage?.estimate) {
    const e = await navigator.storage.estimate();
    lines.push(`• Armazenamento local: ${(e.usage / 1048576).toFixed(1)} MB usados de ${(e.quota / 1073741824).toFixed(1)} GB`);
  }
  lines.push(`• Tela: ${screen.width}×${screen.height} @${window.devicePixelRatio}x · janela ${innerWidth}×${innerHeight}`);
  lines.push(`• Renderização do HUD: ${hud.getFps()} FPS · qualidade ${"100%"}`);
  const up = Math.floor((Date.now() - startedAt) / 1000);
  lines.push(`• Sessão ativa há ${Math.floor(up / 60)}min ${up % 60}s`);
  lines.push(`• Interface: ${getTheme(app.dataset.theme).name} · Estado: ${appState}`);
  lines.push(`• Backend: ${bridge.status === "online" ? "conectado (" + (bridge.kind === "ws" ? "WebSocket" : "REST") + ")" : "offline — modo local"}`);
  lines.push(`• Memória de anotações: ${notes.all.length} registro(s)`);
  if (serverTelemetry?.cpu != null) {
    lines.push("");
    lines.push("Servidor remoto:");
    lines.push(`• CPU ${serverTelemetry.cpu}% · RAM ${serverTelemetry.ram}%${serverTelemetry.disk != null ? " · Disco " + serverTelemetry.disk + "%" : ""}`);
    if (serverTelemetry.host) lines.push(`• Host: ${serverTelemetry.host}${serverTelemetry.os ? " · " + serverTelemetry.os : ""}`);
  }
  return { text: lines.join("\n"), speak: `Todos os sistemas nominais. ${hud.getFps()} quadros por segundo, ${notes.all.length} anotações na memória.` };
}

const brain = createBrain({
  systemName: CFG.systemName, userName: CFG.userName,
  get connected() { return bridge.status === "online"; },
  resolveTheme: (t) => resolveThemeId(t),
  themeName: (id) => getTheme(id).name,
  openUrl: (url, label) => {
    const a = document.createElement("a");
    a.href = url; a.target = "_blank"; a.rel = "noopener";
    document.body.appendChild(a); a.click(); a.remove();
    logLine("navegador → " + (label || url), "ok");
    sfx.ok();
  },
  toast, log: logLine,
  // "pesquisar X" roda a busca real dentro do painel GOLDEN (quando ele está aberto);
  // em outros temas devolve null e o cérebro abre a busca no navegador.
  webSearch: async (q, opts = {}) => {
    if (app.dataset.theme !== "golden" || !golden) return null;
    return await golden.runSearch(q, opts);
  },
  setTheme: (id) => applyTheme(id),
  setState,
  getLastCity: () => settings.lastCity,
  setLastCity: (c) => { settings.lastCity = c; persist(); },
  notes,
  clearConversation,
  toggleFullscreen: async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await (app.requestFullscreen?.() || app.webkitRequestFullscreen?.());
    } catch (e) { toast("TELA CHEIA", "Bloqueado pelo navegador. Use a tecla F11.", "bad"); }
  },
  setTimer: (ms, label) => {
    logLine(`timer armado: ${label}`, "ok");
    armTimer(ms, label);
    setTimeout(() => {
      sfx.alert();
      const msg = `⏰ ${label} concluído!`;
      toast("CRONÔMETRO", label + " finalizado", "ok");
      addMessage("jarvis", msg, { typing: false });
      if (settings.speak) speak(label + " concluído.");
      if ("Notification" in window && Notification.permission === "granted") {
        try { new Notification("J.A.R.V.I.S.", { body: msg }); } catch {}
      }
      if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
    }, ms);
  },
  getSystemReport,
  aiAsk: async (text) => {
    // SECURITY: AI routed through Gateway, not direct Ollama
    if (!window.Gateway || !window.Gateway.isAuthenticated) return null;
    try {
      const result = await window.Gateway.sendCommand(text);
      if (result && result.text) {
        return { text: result.text, streamed: false };
      }
    } catch(e) { console.warn('Gateway AI ask failed:', e); }
    return null;
  },
});

// -------------------------------------------------------- PIPELINE COMANDO --
// Intenções que a própria interface resolve (rápidas, sem depender do backend).
// Tudo o que é ação de sistema operacional é encaminhado ao backend conectado.
const localPatterns = [
  /\b(interface|interfaces|hud|tema|temas|layout|aparencia|visual)\b/,
  /\b(que horas|horario|que dia|data de hoje|dia da semana)\b/,
  /\b(clima|temperatura|previsao|vai chover|faz calor)\b/,
  /\b(anote|anotar|anota|minhas notas|lembretes|limpar notas|apagar notas)\b/,
  /\b(timer|cronometro|alarme|me avise em|conta \d+)\b/,
  /\b(ajuda|comandos|capacidades)\b/,
  /\b(piada|quem sou eu|quem e voce|seu nome|se apresente|o que voce faz)\b/,
  /\b(pesquisar|pesquise|procure|buscar|busque)\b/,
  /\b(tocar|toque|musica|som ambiente)\b/,
  /\b(calcule|quanto e)\b/,
  /^(oi|ola|opa|bom dia|boa tarde|boa noite)\b/,
];

function shouldForward(text) {
  if (bridge.status !== "online") return false;
  const t = text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  if (localPatterns.some((re) => re.test(t))) return false;
  if (Object.keys(brain.sites).some((k) => t.includes(k) && /\b(abrir|abre|acessar|entrar)\b/.test(t))) return false;
  return true;
}

// Fila: um comando de cada vez, para as respostas nunca saírem fora de ordem.
let commandQueue = Promise.resolve();
function submitCommand(raw, source = "texto") {
  commandQueue = commandQueue
    .then(() => runCommand(raw, source))
    .catch((e) => { logLine("falha no processamento: " + (e?.message || e), "bad"); setState("idle"); thinkingBar.hidden = true; });
  return commandQueue;
}

async function runCommand(raw, source = "texto") {
  const text = String(raw || "").trim();
  // Um anexo do COMANDO MANUAL viaja junto do próximo comando escrito à mão.
  const att = source === "texto" ? takeAttachment() : null;
  if (!text && !att) return;
  const label = text || `analisar ${att.name}`;
  if (source === "voz") vcLast.textContent = label;
  lastTask = label;
  golden?.setTask(label);
  addMessage("user", att ? `${label}  [anexo: ${att.name}]` : label);
  logLine(`comando (${source}): ${label}${att ? " · anexo " + att.name : ""}`);
  if (source === "texto") cmdInput.value = "";
  sfx.click();

  // Payload que segue para o backend/IA: o texto do comando e, quando houver,
  // o conteúdo real do anexo (arquivos grandes viajam só como metadados).
  let payload = label;
  if (att) {
    payload += `\n\n[arquivo anexado: ${att.name} · ${(att.size / 1024).toFixed(1)} KB${att.type ? " · " + att.type : ""}]`;
    if (att.text) payload += `\n--- conteúdo de ${att.name} ---\n${att.text}`;
  }

  const agent = settings.agent;

  // Local-only actions (theme, UI panels) bypass agent routing
  if (!shouldForward(label)) {
    try {
      const localRes = await brain.think(label);
      if (localRes) {
        if (localRes.setTheme) setTheme(localRes.setTheme);
        renderResponse(localRes);
        return;
      }
    } catch (e) {
      logLine("erro local: " + (e.message || e), "bad");
      setState("idle");
      return;
    }
  }

  const forceForward = agent === "backend" || settings.advanced || !!(att && att.text);

  if (agent !== "ia" && (forceForward || shouldForward(label))) {
    setState("executing");
    pendingReply = null;
    const res = await bridge.sendCommand(payload, { source, ui: { theme: app.dataset.theme, state: appState, advanced: settings.advanced, agent } });
    if (res.ok && res.data) {
      const d = res.data;
      if (d.telemetry) { serverTelemetry = d.telemetry; metrics.setServerTelemetry(d.telemetry); }
      if (Array.isArray(d.market) && d.market.length) { lastMarket = d.market; golden?.setMarket(d.market); }
      if (d.reply || d.actions) renderResponse({ reply: d.reply || "", actions: d.actions, speak: d.speak });
      setState("idle");
      return;
    }
    if (res.ok) {
      setState("thinking");
      thinkingText.textContent = "executando no backend";
      thinkingBar.hidden = false;
      clearTimeout(waitTimer);
      waitTimer = setTimeout(() => {
        thinkingBar.hidden = true;
        if (!pendingReply) { setState("idle"); logLine("backend sem resposta em 25s", "bad"); }
      }, 25000);
      return;
    }
    logLine("envio falhou: " + res.error + " · seguindo pelo núcleo local", "bad");
    setState("idle");
    const fallback = await brain.think(payload);
    renderResponse(fallback);
    return;
  }

  if (agent === "ia") {
    if (window.Gateway && window.Gateway.isAuthenticated) {
      setState("thinking");
      thinkingText.textContent = "consultando o núcleo de IA";
      thinkingBar.hidden = false;
      const out = await brain.aiAsk(payload);
      thinkingBar.hidden = true;
      setState("idle");
      if (!out?.text) logLine("o núcleo de IA não respondeu", "bad");
      if (out?.text && settings.speak) speak(out.text);
      return;
    }
    toast("NÚCLEO DE IA", "IA generativa indisponível — Gateway não conectado.", "bad");
    logLine("agente IA indisponível · usando o núcleo local", "bad");
  }

  setState("thinking");
  thinkingText.textContent = "processando";
  thinkingBar.hidden = false;
  sfx.think();
  await new Promise((r) => setTimeout(r, 260));
  let out = null;
  try { out = await brain.think(payload); }
  catch (e) { out = { reply: "Falha interna: " + (e.message || e), error: true }; }
  thinkingBar.hidden = true;
  if (out) renderResponse(out);
  setState("idle");
}
let waitTimer = 0;

// ------------------------------------------------------------------ VIDA ----
function tickClock() {
  const d = new Date();
  $("#clockEl").textContent = d.toLocaleTimeString("pt-BR");
  $("#dateEl").textContent = d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
  const up = Math.floor((Date.now() - startedAt) / 1000);
  $("#uptimeEl").textContent = `${String(Math.floor(up / 60)).padStart(2, "0")}:${String(up % 60).padStart(2, "0")}`;
}

function updateOrbTarget() {
  const a = app.getBoundingClientRect();
  // No painel GOLDEN JARVIS o orbe central é enquadrado entre o cabeçalho e a faixa
  // inferior, na coluna central — em vez da tela inteira.
  const center = $("#gCenter");
  if (app.dataset.theme === "golden" && center && center.getBoundingClientRect().height > 40) {
    const r = center.getBoundingClientRect();
    const topY = $("#gTop").getBoundingClientRect().bottom + 4 - a.top;
    const botY = Math.max(topY + 140, $("#gViews").getBoundingClientRect().top - 10 - a.top);
    const cx = r.left - a.left + r.width / 2;
    const w = Math.max(200, r.width * 0.9);
    hud.setFrame({ x: cx, y: (topY + botY) / 2, w, h: botY - topY });
    hud.setTarget(cx, (topY + botY) / 2, w * 0.36);
    return;
  }
  hud.setFrame(null);
  const r = orbWrap.getBoundingClientRect();
  const cx = r.left - a.left + r.width / 2;
  const cy = r.top - a.top + r.height * 0.44;
  const scale = app.dataset.theme === "nucleo" ? 1.55 : 1;
  const rad = Math.max(26, Math.min(r.width * 0.30, r.height * 0.38) * scale);
  hud.setTarget(cx, cy, rad);
}

// --------------------------------------------------------------- MÓDULOS ----
function moduleDefs() {
  const b = bridge.status === "online";
  return [
    { id: "nucleo", name: "NÚCLEO", desc: `${CFG.systemName} operacional`, on: true, stat: `${hud.getFps()} FPS`, cmd: "status do sistema" },
    { id: "voz", name: "VOZ", desc: voiceSupported() ? "reconhecimento ativo" : "não suportado aqui", on: voiceSupported() && settings.speak, stat: settings.speak ? "ATIVA" : "MUDO", cmd: "ajuda" },
    { id: "backend", name: "BACKEND", desc: b ? "PC conectado · execução total" : "modo local (sem execução de SO)", on: b, stat: b ? "ONLINE" : "OFFLINE", cmd: "status do sistema" },
    { id: "memoria", name: "MEMÓRIA", desc: "anotações persistentes", on: true, stat: `${notes.all.length}`, cmd: "minhas notas" },
    { id: "clima", name: "SENSOR CLIMÁTICO", desc: "Open-Meteo", on: true, stat: "PRONTO", cmd: `clima em ${settings.lastCity || "São Paulo"}` },
    { id: "midia", name: "MÍDIA", desc: "áudio por busca", on: true, stat: "PRONTO", cmd: "tocar música lofi" },
  ];
}
const ICONS = {
  nucleo: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
  voz: '<path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  backend: '<rect x="3" y="4" width="18" height="7" rx="1"/><rect x="3" y="13" width="18" height="7" rx="1"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  memoria: '<path d="M4 5h16v14H4z"/><path d="M8 9h8M8 13h5"/>',
  clima: '<path d="M6 15a4 4 0 0 1 .6-8 5.2 5.2 0 0 1 9.8 1.4A3.4 3.4 0 0 1 17 15H6Z"/>',
  midia: '<path d="M9 18V6l10-3v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="15" r="2.5"/>',
};
// Nós rotulados do tema NÚCLEO NEURAL (cada um executa um comando real).
function hostNodeList() {
  const b = bridge.status === "online";
  const hhmm = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return [
    { id: "sistema", label: "Sistema", stat: `${hud.getFps()} fps`, cmd: "status do sistema" },
    { id: "diagnostico", label: "Diagnóstico", stat: "sensores", cmd: "diagnóstico do dispositivo" },
    { id: "memoria", label: "Memória", stat: `${notes.all.length} nota(s)`, cmd: "minhas notas" },
    { id: "agenda", label: "Agenda", stat: hhmm, cmd: "que horas são" },
    { id: "clima", label: "Clima", stat: settings.lastCity || "local", cmd: `clima em ${settings.lastCity || "São Paulo"}` },
    { id: "pesquisa", label: "Pesquisa", stat: "web", cmd: "pesquisar novidades de tecnologia" },
    { id: "navegador", label: "Navegador", stat: "youtube", cmd: "abrir YouTube" },
    { id: "midia", label: "Mídia", stat: "áudio", cmd: "tocar música ambiente calma" },
    { id: "timers", label: "Timers", stat: "5 min", cmd: "timer de 5 minutos" },
    { id: "voz", label: "Voz", stat: settings.speak ? "ativa" : "muda", cmd: "ajuda" },
    { id: "humor", label: "Humor", stat: "piada", cmd: "me conte uma piada" },
    { id: "alerta", label: "Alerta", stat: "protocolo", cmd: "modo alerta" },
    { id: "backend", label: "Backend", stat: b ? "online" : "modo local", cmd: "status do sistema", on: b },
  ];
}
function updateModules() {
  moduleListEl.innerHTML = "";
  if (hud.setHostNodes) hud.setHostNodes(hostNodeList());
  for (const m of moduleDefs()) {
    const el = document.createElement("div");
    el.className = "module";
    el.dataset.on = String(m.on);
    el.innerHTML = `<span class="mIcon"><svg viewBox="0 0 24 24">${ICONS[m.id] || ICONS.nucleo}</svg></span>
      <span class="mBody"><span class="mName">${m.name}</span><span class="mDesc">${esc(m.desc)}</span></span>
      <span class="mStat">${m.stat}</span>`;
    el.onclick = () => { sfx.click(); submitCommand(m.cmd); };
    moduleListEl.appendChild(el);
  }
}

const QA = [
  { label: "Status", cmd: "status do sistema", icon: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>' },
  { label: "Clima", cmd: `clima em ${settings.lastCity || "São Paulo"}`, icon: ICONS.clima },
  { label: "Timer 5min", cmd: "timer de 5 minutos", icon: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M9 2h6"/>' },
  { label: "Notas", cmd: "minhas notas", icon: ICONS.memoria },
  { label: "Música", cmd: "tocar música instrumental épica", icon: ICONS.midia },
  { label: "Alerta", cmd: "modo alerta", icon: '<path d="M12 3l9 16H3z"/><path d="M12 9v5M12 17h.01"/>' },
];
function renderQuickActions() {
  quickActionsEl.innerHTML = "";
  for (const q of QA) {
    const b = document.createElement("button");
    b.className = "qaBtn";
    b.innerHTML = `<svg viewBox="0 0 24 24">${q.icon}</svg><span>${q.label}</span>`;
    b.onclick = () => { sfx.click(); submitCommand(q.cmd); };
    quickActionsEl.appendChild(b);
  }
}

const CHIPS = ["status do sistema", `clima em ${settings.lastCity || "São Paulo"}`, "que horas são", "abrir YouTube", "anote comprar café", "interface núcleo", "interface holograma", "calcule 128*4+12"];
function renderChips() {
  quickChipsEl.innerHTML = "";
  for (const c of CHIPS) {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = c;
    b.onclick = () => { sfx.click(); submitCommand(c); };
    quickChipsEl.appendChild(b);
  }
}

// ------------------------------------------------------------- TELEMETRIA ---
const sparkCanvas = document.createElement("canvas");
sparkCanvas.className = "spark";
const fpsHist = new Array(60).fill(0);
let lastTelemetryPaint = 0;

function buildTelemetry() {
  telemetryEl.innerHTML = "";
  const rows = [
    { id: "fps", label: "RENDER / FPS", short: "FPS" },
    { id: "heap", label: "HEAP JS", short: "MEM JS" },
    { id: "net", label: "REDE (downlink)", short: "REDE" },
    { id: "cpu", label: "CPU (PC)", short: "CPU PC" },
    { id: "ram", label: "RAM (PC)", short: "RAM PC" },
    { id: "bat", label: "BATERIA", short: "BAT" },
  ];
  for (const r of rows) {
    const d = document.createElement("div");
    d.className = "telRow";
    d.dataset.row = r.id;
    d.innerHTML = `<div class="telTop"><span class="tlLong">${r.label}</span><span class="tlShort">${r.short}</span><b>—</b></div><div class="bar"><i></i></div>`;
    telemetryEl.appendChild(d);
  }
  telemetryEl.appendChild(sparkCanvas);
  const grid = document.createElement("div");
  grid.className = "telGrid";
  grid.id = "telCells";
  telemetryEl.appendChild(grid);
}
let batteryLevel = null;

async function initBattery() {
  try {
    const b = await navigator.getBattery();
    batteryLevel = Math.round(b.level * 100);
    b.addEventListener("levelchange", () => { batteryLevel = Math.round(b.level * 100); });
  } catch { batteryLevel = null; }
}

function paintTelemetry() {
  const now = performance.now();
  if (now - lastTelemetryPaint < 900) return;
  lastTelemetryPaint = now;
  fpsHist.push(hud.getFps());
  if (fpsHist.length > 60) fpsHist.shift();

  telemetryEl.querySelectorAll(".telRow").forEach((row) => {
    const id = row.dataset.row;
    let v = null;
    if (id === "fps") v = hud.getFps();
    else if (id === "heap") v = performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null;
    else if (id === "net") v = navigator.connection ? navigator.connection.downlink : null;
    else if (id === "cpu") v = serverTelemetry?.cpu ?? null;
    else if (id === "ram") v = serverTelemetry?.ram ?? null;
    else if (id === "bat") v = batteryLevel;
    const bEl = row.querySelector(".telTop b");
    const bar = row.querySelector(".bar i");
    if (v == null) { bEl.textContent = "N/D"; bar.style.width = "0%"; return; }
    let txt, pct;
    if (id === "fps") { txt = `${Math.round(v)} fps`; pct = (v / 60) * 100; }
    else if (id === "heap") { txt = `${v.toFixed(0)} MB`; const lim = performance.memory ? performance.memory.jsHeapSizeLimit / 1048576 : 2048; pct = (v / lim) * 100; }
    else if (id === "net") { txt = `${v} Mb/s`; pct = Math.min(100, (v / 50) * 100); }
    else { txt = `${Math.round(v)}%`; pct = v; }
    bEl.textContent = txt;
    bar.style.width = Math.max(0, Math.min(100, pct)) + "%";
  });

  // sparkline
  const w = sparkCanvas.clientWidth || 240, h = 30;
  const dpr = Math.min(devicePixelRatio || 1, 2);
  sparkCanvas.width = w * dpr; sparkCanvas.height = h * dpr;
  const c = sparkCanvas.getContext("2d");
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, w, h);
  const accent = getComputedStyle(app).getPropertyValue("--accent").trim() || "#35d8ff";
  c.strokeStyle = accent + "55"; c.lineWidth = 1;
  for (let i = 1; i < 4; i++) { c.beginPath(); c.moveTo(0, (h / 4) * i); c.lineTo(w, (h / 4) * i); c.stroke(); }
  c.beginPath(); c.strokeStyle = accent; c.lineWidth = 1.6;
  fpsHist.forEach((v, i) => {
    const x = (i / (fpsHist.length - 1)) * w;
    const y = h - Math.min(1, v / 60) * (h - 4) - 2;
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  });
  c.stroke();

  const cells = $("#telCells");
  if (cells) {
    const conn = navigator.connection;
    const items = [
      ["NÚCLEOS", (navigator.hardwareConcurrency || "?") + " vCPU"],
      ["DISPOSITIVO", (navigator.deviceMemory ? navigator.deviceMemory + " GB" : (navigator.platform || "—").slice(0, 12))],
      ["TELA", `${screen.width}×${screen.height}`],
      ["REDE", conn ? (conn.effectiveType || "—") : (navigator.onLine ? "online" : "off")],
      ["BACKEND", bridge.status === "online" ? (bridge.kind === "ws" ? "WebSocket" : "REST") : "local"],
      ["MODO", appState.toUpperCase()],
    ];
    cells.innerHTML = items.map(([l, v]) => `<div class="telCell"><label>${l}</label><span>${esc(String(v))}</span></div>`).join("");
  }

  const mem = performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null;
  hud.setDataLines(app.dataset.theme === "golden" ? [] : [
    CFG.systemName + " · v1.0",
    new Date().toLocaleTimeString("pt-BR"),
    "RENDER " + hud.getFps() + " FPS",
    mem != null ? "HEAP " + mem + " MB" : "HEAP N/D",
    "NUCLEOS " + (navigator.hardwareConcurrency || "?"),
    "BACKEND " + (bridge.status === "online" ? "ONLINE" : "LOCAL"),
    "MODO " + appState.toUpperCase(),
    (CFG.userName ? "OPERADOR " + CFG.userName : "SESSAO ATIVA").toUpperCase(),
  ]);
  golden?.setTelemetry(metrics.snapshot());
}

// ------------------------------------------------- GOLDEN JARVIS (PAINEL) ---
// O painel de referência. Recebe as leituras reais do módulo metrics.js e usa
// o MESMO DOM da interface (conversa, entrada, telemetria, log, módulos), que é
// movido para dentro dos encaixes do painel enquanto o tema está ativo.
golden = createGolden({
  cfg: CFG,
  metrics,
  dom: {
    conversation: conversationEl,
    thinkingBar,
    inputRow: $("#inputRow"),
    quickActions: quickActionsEl,
    quickChips: quickChipsEl,
    telemetry: telemetryEl,
    activityLog: activityLogEl,
    moduleList: moduleListEl,
  },
  getModules: moduleDefs,
  getNotes: () => notes.list(),
  addNote: (t) => notes.add(t),
  clearNotes: () => notes.clear(),
  getTelemetry: () => metrics.snapshot(),
  submitCommand,
  toast,
  log: logLine,
  sfx: (k) => { if (typeof sfx[k] === "function") sfx[k](); },
  openSettings,
  clearConversation,
  setSilent,
  relayout: () => updateOrbTarget(),
  getObjective: () => settings.objective,
  setObjective: (t) => { settings.objective = String(t || ""); persist(); golden?.setObjective(settings.objective); },
  getVoice: () => ({ supported: voiceSupported(), listening: voice.isListening(), speak: settings.speak }),
  getSettings: () => settings,
  getBridgeStatus: () => bridge.status,
  getBridgeKind: () => bridge.kind,
  uptime,
  getTimers,
  toggleNote: (id) => { notes.toggle(id); },
  webSearch: (q, opts) => searchEngine.run(q, opts),
  getSearchHistory: () => searchHist.slice(),
  addSearchHistory: (q) => addSearchHistory(q),
  clearSearchHistory: () => clearSearchHistory(),
  readAttachment,
  setAttachment,
  getAttachment,
  setAgent: (v) => { settings.agent = v; persist(); },
  setAdvanced: (b) => { settings.advanced = !!b; persist(); },
  getConversation,
  addMessage,
  openUrl: (url, label) => {
    const value = String(url || "").trim();
    if (!/^https?:\/\//i.test(value)) return false;
    const a = document.createElement("a");
    a.href = value; a.target = "_blank"; a.rel = "noopener noreferrer";
    document.body.appendChild(a); a.click(); a.remove();
    logLine("navegador → " + (label || value), "ok");
    sfx.ok();
    return true;
  },
  exportMemory,
  getMarket: () => lastMarket,
});

// ------------------------------------------------------------- INTERFACE ----
function applyTheme(id, silent) {
  const theme = getTheme(id);
  app.dataset.theme = theme.id;
  hud.setTheme(theme.id, theme.mode);
  hud.setHoverNode?.("");
  readPalette();
  updateOrbTarget();
  if (theme.id === "golden") golden?.mount(); else golden?.unmount();
  settings.theme = theme.id;
  if (!MARKET_WINDOW_MODE) persist();
  renderThemeGrid();
  if (!silent) {
    logLine("interface → " + theme.name, "ok");
    sfx.ok();
    tone({ freq: 520, to: 980, dur: 0.22, type: "triangle", gain: 0.04 });
  }
}

function cycleTheme() {
  const ids = THEMES.map((t) => t.id);
  const i = ids.indexOf(app.dataset.theme);
  applyTheme(ids[(i + 1) % ids.length]);
  toast("INTERFACE", getTheme(app.dataset.theme).name, "ok");
}

function renderThemeGrid() {
  const grid = $("#themeGrid");
  if (!grid) return;
  grid.innerHTML = "";
  for (const t of THEMES) {
    const card = document.createElement("button");
    card.className = "themeCard";
    card.dataset.active = String(app.dataset.theme === t.id);
    card.innerHTML = `<div class="tcName">${t.name}</div><div class="tcDesc">${t.desc}</div>
      <div class="swatches">${t.swatches.map((s) => `<i style="background:${s}"></i>`).join("")}</div>`;
    card.onclick = () => { applyTheme(t.id); toast("INTERFACE", t.name, "ok"); };
    grid.appendChild(card);
  }
}

// ---------------------------------------------------------- CONFIGURAÇÕES ---
function openSettings() { settingsModal.hidden = false; renderThemeGrid(); }
function closeSettings() { settingsModal.hidden = true; }

function fillVoiceSelect() {
  const sel = $("#voiceSelect");
  if (!sel) return;
  const list = voice.getVoices();
  sel.innerHTML = "";
  const auto = document.createElement("option");
  auto.value = ""; auto.textContent = "Automática (melhor para o idioma)";
  sel.appendChild(auto);
  for (const v of list) {
    const o = document.createElement("option");
    o.value = v.name; o.textContent = `${v.name} · ${v.lang}`;
    sel.appendChild(o);
  }
  sel.value = settings.voiceName || "";
}

function renderCapabilities() {
  const el = $("#capList");
  if (!el) return;
  const caps = [
    ["Reconhecimento de voz (falar comandos)", voiceSupported()],
    ["Síntese de voz (respostas faladas)", ttsSupported()],
    ["Notificações do sistema", "Notification" in window],
    ["Tela cheia", !!document.fullscreenElement !== undefined && !!app.requestFullscreen],
    ["Vibração (celular)", "vibrate" in navigator],
    ["Leitura de bateria", !!navigator.getBattery],
    ["Info. de rede (downlink/RTT)", !!navigator.connection],
    ["Memória do dispositivo", !!navigator.deviceMemory],
    ["Armazenamento estimado", !!navigator.storage?.estimate],
    ["Geolocalização", !!navigator.geolocation],
    ["Câmera / microfone", !!navigator.mediaDevices?.getUserMedia],
    ["Compartilhamento nativo", !!navigator.share],
    ["Controle do sistema operacional", bridge.status === "online"],
  ];
  el.innerHTML = caps.map(([n, ok]) => `<div><span class="${ok ? "yes" : "no"}">${ok ? "✓" : "✗"}</span><span>${esc(n)}</span></div>`).join("");
}

function wireSettings() {
  $("#speakToggle").checked = settings.speak;
  $("#wakeToggle").checked = settings.wake;
  $("#wakeInput").value = settings.wakeWord;
  $("#rateRange").value = settings.rate;
  $("#pitchRange").value = settings.pitch;
  $("#rateVal").textContent = settings.rate;
  $("#pitchVal").textContent = settings.pitch;

  $("#speakToggle").onchange = (e) => { settings.speak = e.target.checked; persist(); updateModules(); };
  if (isJarvisDesktop) settings.browserTts = false;
  $("#browserTtsToggle").checked = settings.browserTts;
  $("#browserTtsToggle").disabled = isJarvisDesktop;
  $("#browserTtsToggle").onchange = (e) => { settings.browserTts = e.target.checked; persist(); };
  $("#wakeToggle").onchange = (e) => {
    settings.wake = e.target.checked; persist();
    if (settings.wake) {
      if (isJarvisDesktop) desktopVoice.start({ capture: false }); else voice.enableWake(settings.wakeWord);
      toast("VOZ", "Escuta contínua ativa — diga «" + settings.wakeWord + "».", "ok");
    } else if (isJarvisDesktop) desktopVoice.stop(); else voice.stop();
  };
  $("#wakeInput").onchange = (e) => { settings.wakeWord = e.target.value.trim().toLowerCase() || "jarvis"; voice.setWakeWord(settings.wakeWord); vcWake.textContent = settings.wakeWord; persist(); };
  $("#rateRange").oninput = (e) => { settings.rate = parseFloat(e.target.value); $("#rateVal").textContent = settings.rate; voice.setRate(settings.rate); persist(); };
  $("#pitchRange").oninput = (e) => { settings.pitch = parseFloat(e.target.value); $("#pitchVal").textContent = settings.pitch; voice.setPitch(settings.pitch); persist(); };
  $("#voiceSelect").onchange = (e) => { settings.voiceName = e.target.value; voice.setVoice(settings.voiceName); persist(); };
  $("#testVoiceBtn").onclick = () => {
    voice.setRate(settings.rate); voice.setPitch(settings.pitch); voice.setVoice(settings.voiceName);
    voice.speak(`Sistemas de voz calibrados. Bom dia, ${CFG.userName}.`);
  };
  // Gateway adapter: auto-connect, no manual URL config needed
  if (window.Gateway) {
    const resultEl = $("#backendResult");
    if (resultEl) {
      resultEl.textContent = "Gateway detectado — connecte-se via status pill.";
    }
  }
  $("#closeSettingsBtn").onclick = closeSettings;
  $("#settingsModal").onclick = (e) => { if (e.target === settingsModal) closeSettings(); };
}

// ------------------------------------------------- NÓS DO NÚCLEO (CLIQUE) ---
const NODE_CLICK_THEMES = { nucleo: true, golden: true };
function nodeClickableTheme() {
  return !!NODE_CLICK_THEMES[app.dataset.theme] && !!hud.getNodes;
}

function wireHudPointer() {
  let hoverId = "";
  let pressId = "";
  const r = () => hudCanvas.getBoundingClientRect();
  const pick = (e) => {
    if (!nodeClickableTheme()) return null;
    const box = r();
    const x = e.clientX - box.left, y = e.clientY - box.top;
    let best = null, bestD = Infinity;
    for (const n of hud.getNodes()) {
      const d = Math.hypot(n.x - x, n.y - y);
      if (d <= n.r && d < bestD) { best = n; bestD = d; }
    }
    return best;
  };
  hudCanvas.addEventListener("pointermove", (e) => {
    const n = pick(e);
    const id = n ? n.id : "";
    if (id !== hoverId) {
      hoverId = id;
      hud.setHoverNode(id);
      hudCanvas.style.cursor = n ? "pointer" : (nodeClickableTheme() ? "crosshair" : "default");
    }
  });
  hudCanvas.addEventListener("pointerleave", () => {
    hoverId = ""; pressId = ""; hud.setHoverNode("");
  });
  hudCanvas.addEventListener("pointerdown", (e) => {
    const n = pick(e);
    if (!n) return;
    pressId = n.id;
    sfx.click();
    hud.setHoverNode(n.id);
  });
  hudCanvas.addEventListener("pointerup", (e) => {
    const n = pick(e);
    if (!n || n.id !== pressId) { pressId = ""; return; }
    pressId = "";
    hud.setHoverNode(n.id);
    toast((n.label || n.id).toUpperCase(), n.cmd, "ok");
    submitCommand(n.cmd);
  });
}

// ------------------------------------------------------------------ BOOT ----
// --------------------------------------------------- CONFIRMATION DIALOG ---
let _confirmToken = null;
let _confirmProcessing = false;

function showConfirmationDialog(msg) {
  const dialog = $("#confirmDialog");
  const riskEl = $("#confirmRisk");
  const actionEl = $("#confirmAction");
  const messageEl = $("#confirmMessage");
  const approveBtn = $("#confirmApprove");
  const denyBtn = $("#confirmDeny");
  const statusEl = $("#confirmStatus");

  _confirmToken = msg.token || null;
  _confirmProcessing = false;

  const risk = (msg.risk || "MEDIUM").toUpperCase();
  riskEl.textContent = risk;
  riskEl.dataset.risk = risk;
  actionEl.textContent = msg.action || "Ação desconhecida";
  messageEl.textContent = msg.message || "Confirmação necessária.";
  statusEl.textContent = "";
  statusEl.className = "confirmStatus";

  approveBtn.disabled = false;
  denyBtn.disabled = false;
  dialog.hidden = false;
  setState("alert");
}

function hideConfirmationDialog() {
  const dialog = $("#confirmDialog");
  dialog.hidden = true;
  _confirmToken = null;
  _confirmProcessing = false;
  setState("idle");
}

function wireConfirmationDialog() {
  const approveBtn = $("#confirmApprove");
  const denyBtn = $("#confirmDeny");
  const statusEl = $("#confirmStatus");

  approveBtn.addEventListener("click", async () => {
    if (_confirmProcessing || !_confirmToken) return;
    _confirmProcessing = true;
    approveBtn.disabled = true;
    denyBtn.disabled = true;
    statusEl.textContent = "Enviando confirmação...";
    statusEl.className = "confirmStatus";

    try {
      if (window.Gateway && window.Gateway.isAuthenticated) {
        window.Gateway.confirmAction(_confirmToken, true);
        statusEl.textContent = "Confirmado. Aguardando execução...";
        statusEl.className = "confirmStatus ok";
        addMessage("jarvis", "Ação confirmada. Executando...");
      } else {
        statusEl.textContent = "Gateway não conectado.";
        statusEl.className = "confirmStatus error";
      }
    } catch (e) {
      statusEl.textContent = "Erro: " + e.message;
      statusEl.className = "confirmStatus error";
      _confirmProcessing = false;
      approveBtn.disabled = false;
      denyBtn.disabled = false;
      return;
    }
    setTimeout(hideConfirmationDialog, 2000);
  });

  denyBtn.addEventListener("click", () => {
    if (_confirmProcessing) return;
    if (_confirmToken && window.Gateway && window.Gateway.isAuthenticated) {
      window.Gateway.confirmAction(_confirmToken, false);
      addMessage("jarvis", "Ação cancelada pelo operador.");
    }
    hideConfirmationDialog();
  });

  // Close on Escape
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#confirmDialog").hidden) {
      if (_confirmToken && window.Gateway && window.Gateway.isAuthenticated) {
        window.Gateway.confirmAction(_confirmToken, false);
      }
      hideConfirmationDialog();
    }
  });
}

async function runBoot() {
  const lines = bootLines.length ? bootLines : [
    "Inicializando núcleo de reator... OK", "Carregando protocolos... OK", "Todos os sistemas operacionais",
  ];
  if (!CFG.boot) { bootOverlay.classList.add("done"); return; }
  sfx.boot();
  const shuf = lines.slice().sort(() => Math.random() - 0.5).slice(0, 5);
  for (const l of shuf) {
    const d = document.createElement("div");
    const m = l.match(/^(.*?)(OK|100%|operacionais)\s*$/i);
    d.innerHTML = m ? `${esc(m[1])}<b>${esc(m[2])}</b>` : esc(l);
    bootLinesEl.appendChild(d);
    tone({ freq: 600 + Math.random() * 500, dur: 0.03, gain: 0.015, type: "square" });
    await new Promise((r) => setTimeout(r, 190 + Math.random() * 120));
  }
  await new Promise((r) => setTimeout(r, 420));
  bootOverlay.classList.add("done");
  setTimeout(() => bootOverlay.remove(), 800);
}

const b3State = {
  symbol: "XAUUSD", timeframe: "M15", scanner: [], robots: [], selectedOpportunity: null,
  selectedRobot: null, marketAssets: [], marketGroup: "ALL", marketResponse: null,
  responses: {}, busy: false,
};
const B3_MARKET_INTELLIGENCE_ENDPOINT = "/api/jarvis/golden/market-intelligence";
const B3_MARKET_COMPATIBILITY_ENDPOINTS = ["/api/jarvis/golden/radar", "/api/jarvis/golden/scanner"];
const B43_ROBOT_INTELLIGENCE_ENDPOINT = "/api/jarvis/golden/robot-intelligence";

function b3Payload(response) {
  return response?.data && typeof response.data === "object" ? response.data : (response || {});
}
function b3Status(response) {
  if (!response) return "UNAVAILABLE";
  if (response.error || response.ok === false && response.status === "ERROR") return "ERROR";
  return String(response.availability || response.status || (response.ok === false ? "UNAVAILABLE" : "AVAILABLE")).toUpperCase();
}
function b3Value(value) {
  if (value == null || value === "") return "UNKNOWN";
  if (Array.isArray(value)) return value.length ? value.map((v) => b3Value(v)).join(", ") : "EMPTY";
  if (typeof value === "object") {
    try { return JSON.stringify(value); } catch { return "UNKNOWN"; }
  }
  return String(value);
}
function b3Short(value, max = 180) {
  const text = b3Value(value);
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
function b3StateTag(value) {
  const state = String(value || "UNKNOWN").toUpperCase();
  return `<span class="gB3State" data-state="${esc(state)}">${esc(state)}</span>`;
}
function b3Empty(text = "Nenhum dado verificável disponível.") {
  return `<p class="gB3Empty">${esc(text)}</p>`;
}
function b3Detail(items) {
  return `<div class="gB3DetailGrid">${items.map(([label, value]) => `<div class="gB3DetailItem"><label>${esc(label)}</label><span title="${esc(b3Value(value))}">${esc(b3Short(value))}</span></div>`).join("")}</div>`;
}
function b3Num(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
function b3Fmt(value, digits = 2) {
  const number = b3Num(value);
  return number == null ? "UNKNOWN" : number.toLocaleString("pt-BR", { maximumFractionDigits: digits });
}
function b3AssetKey(value) {
  return String(value || "").replace(/[^A-Z0-9]/gi, "").toUpperCase();
}
function b3MarketAssetRows() {
  return b3State.marketGroup === "ALL"
    ? b3State.marketAssets
    : b3State.marketAssets.filter((item) => String(item.group || item.asset_class || "UNKNOWN") === b3State.marketGroup);
}
function b3RenderMarketChart(chart) {
  const canvas = $("#gB3MarketChart");
  const status = $("#gB3MarketChartState");
  const candles = Array.isArray(chart?.candles) ? chart.candles.filter((item) =>
    [item.open, item.high, item.low, item.close].every((value) => b3Num(value) != null)) : [];
  if (status) status.textContent = candles.length ? `${chart.source || "OBSERVED"} · ${candles.length} CANDLES` : "DATA UNAVAILABLE";
  if (!canvas || !candles.length) return;
  const draw = () => {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 640;
    const height = canvas.clientHeight || 250;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const pad = { left: 12, right: 58, top: 12, bottom: 22 };
    const lows = candles.map((item) => Number(item.low));
    const highs = candles.map((item) => Number(item.high));
    const low = Math.min(...lows), high = Math.max(...highs), span = high - low || 1;
    const plotWidth = Math.max(1, width - pad.left - pad.right);
    const plotHeight = Math.max(1, height - pad.top - pad.bottom);
    const y = (value) => pad.top + ((high - value) / span) * plotHeight;
    const step = plotWidth / candles.length;
    const body = Math.max(2, Math.min(9, step * 0.64));
    ctx.clearRect(0, 0, width, height);
    ctx.font = "9px Segoe UI";
    ctx.fillStyle = "rgba(150, 200, 240, .58)";
    ctx.strokeStyle = "rgba(120, 190, 230, .14)";
    for (let index = 0; index < 5; index += 1) {
      const lineY = pad.top + (plotHeight * index) / 4;
      ctx.beginPath(); ctx.moveTo(pad.left, lineY); ctx.lineTo(width - pad.right, lineY); ctx.stroke();
      ctx.fillText(b3Fmt(high - (span * index) / 4, 3), width - pad.right + 7, lineY + 3);
    }
    candles.forEach((item, index) => {
      const x = pad.left + (index + 0.5) * step;
      const up = Number(item.close) >= Number(item.open);
      const color = up ? "#44e0a1" : "#ff6d86";
      ctx.strokeStyle = color; ctx.fillStyle = color;
      ctx.beginPath(); ctx.moveTo(x, y(Number(item.high))); ctx.lineTo(x, y(Number(item.low))); ctx.stroke();
      const top = y(Math.max(Number(item.open), Number(item.close)));
      const bottom = y(Math.min(Number(item.open), Number(item.close)));
      ctx.fillRect(x - body / 2, top, body, Math.max(1, bottom - top));
    });
    const last = Number(candles.at(-1).close), lastY = y(last);
    ctx.setLineDash([4, 4]); ctx.strokeStyle = "#e1ad45";
    ctx.beginPath(); ctx.moveTo(pad.left, lastY); ctx.lineTo(width - pad.right, lastY); ctx.stroke();
    ctx.setLineDash([]);
  };
  draw();
  window.addEventListener("resize", draw, { once: true });
}
function b3RenderMarketMiniRows(items) {
  return items.length ? items.map((item) => {
    const change = b3Num(item.change ?? item.variation);
    const cls = change == null ? "" : change >= 0 ? "gB3MarketUp" : "gB3MarketDown";
    return `<div class="gB3MarketMiniRow"><b>${esc(item.symbol || item.label || "UNKNOWN")}</b><span>${esc(b3Value(item.price))}</span><strong class="${cls}">${change == null ? "UNKNOWN" : `${change >= 0 ? "+" : ""}${b3Fmt(change)}%`}</strong></div>`;
  }).join("") : b3Empty("Nenhum ativo verificável para este filtro.");
}
function b3RenderStatus(id, response) {
  const el = $(`#${id}`);
  if (!el) return;
  const status = b3Status(response);
  el.textContent = status;
  el.dataset.status = status;
}
function b3Overview(overview, radar, scanner, robots, evidence, memory) {
  const robotData = b3Payload(robots);
  const report = robotData.report || {};
  const counts = report.association_counts || {};
  const radarData = b3Payload(radar);
  const scannerData = b3Payload(scanner);
  const evidenceData = evidence || {};
  const validationData = b3Payload(evidenceData.validation);
  const testerData = b3Payload(evidenceData.tester);
  const memoryData = memory?.contract || {};
  const metrics = [
    ["CAPABILITIES", overview?.capabilities?.count ?? "UNKNOWN"],
    ["OPORTUNIDADES", scannerData.normalized_results?.length ?? "UNKNOWN"],
    ["ATIVOS MONITORADOS", radarData.market_map?.length ?? "UNKNOWN"],
    ["ROBÔS NO CATÁLOGO", robotData.robots?.length ?? "UNKNOWN"],
    ["EVIDÊNCIAS HISTÓRICAS", validationData.history?.length ?? "UNKNOWN"],
    ["TESTER RUNS", testerData.test_runs?.length ?? "UNKNOWN"],
    ["MEMÓRIA", memoryData.status || "UNKNOWN"],
    ["BACKTESTS NÃO RESOLVIDOS", counts.UNRESOLVED ?? "UNKNOWN"],
  ];
  $("#gB3Overview").innerHTML = metrics.map(([label, value]) => `<div class="gB3Metric"><label>${esc(label)}</label><b title="${esc(b3Value(value))}">${esc(b3Short(value, 32))}</b></div>`).join("");
  const matching = overview?.strategy?.data?.matching_coverage?.EXISTING_ROBOT_MARKET_MATCHING_COVERAGE || [];
  $("#gGoldenBridgeSummary").innerHTML = b3Detail([
    ["AUTORIDADE", overview?.authority || "JarvisService"],
    ["MODO", overview?.read_only ? "READ_ONLY" : "UNKNOWN"],
    ["SEGURANÇA", "READ_ONLY_NO_SIDE_EFFECT"],
    ["MATCHING", matching.join(", ") || "UNKNOWN"],
    ["FRESHNESS RADAR", radar?.freshness || "UNKNOWN"],
    ["SOURCE INTEGRITY", radarData.source_integrity ? "AVAILABLE" : "UNKNOWN"],
  ]);
}
function b3RenderMarket(response) {
  const data = b3Payload(response);
  const assets = Array.isArray(data.market_map) ? data.market_map : [];
  b3State.marketAssets = assets;
  b3State.marketResponse = response;
  const groups = [...new Set(assets.map((item) => String(item.group || item.asset_class || "UNKNOWN")))].sort();
  const groupSelect = $("#gB3MarketGroup");
  if (groupSelect) {
    const active = b3State.marketGroup;
    groupSelect.innerHTML = `<option value="ALL">TODOS OS ATIVOS</option>${groups.map((group) => `<option value="${esc(group)}">${esc(group)}</option>`).join("")}`;
    groupSelect.value = groups.includes(active) || active === "ALL" ? active : "ALL";
    b3State.marketGroup = groupSelect.value;
  }
  const visibleAssets = b3MarketAssetRows();
  const selected = assets.find((item) => b3AssetKey(item.symbol || item.label) === b3AssetKey(b3State.symbol)) || assets[0] || null;
  const changes = assets.map((item) => b3Num(item.change ?? item.variation)).filter((value) => value != null);
  const up = changes.filter((value) => value >= 0).length;
  const down = changes.filter((value) => value < 0).length;
  $("#gB3MarketSummary").innerHTML = b3Detail([
    ["ATIVO", b3State.symbol], ["TIMEFRAME", b3State.timeframe],
    ["NEWS", data.news?.length ?? "UNKNOWN"], ["MACRO", data.macro_indicators?.length ?? "UNKNOWN"],
    ["FRESHNESS", response?.freshness || "UNKNOWN"], ["SOURCE", data.source || response?.provenance?.source_module || "UNKNOWN"],
  ]);
  $("#gB3MarketKpis").innerHTML = [
    [selected?.symbol || b3State.symbol, selected?.price ?? "UNKNOWN", selected?.change, "ATIVO SELECIONADO"],
    ["ATIVOS", assets.length, null, "MONITORADOS"], ["EM ALTA", up, null, "OBSERVED"], ["EM BAIXA", down, null, "OBSERVED"],
  ].map(([label, value, change, caption]) => `<div class="gB3MarketKpi"><label>${esc(label)}</label><b>${esc(b3Value(value))}${change != null ? ` <em class="${change >= 0 ? "gB3MarketUp" : "gB3MarketDown"}">${change >= 0 ? "+" : ""}${esc(b3Fmt(change))}%</em>` : ""}</b><span>${esc(caption)}</span></div>`).join("");
  $("#gB3MarketAssets").innerHTML = visibleAssets.length ? `<table class="gB3Table"><thead><tr><th>ATIVO</th><th>GRUPO</th><th>PREÇO</th><th>VARIAÇÃO</th><th>FONTE</th></tr></thead><tbody>${visibleAssets.slice(0, 40).map((item) => `<tr><td>${esc(item.symbol || item.label || "UNKNOWN")}</td><td>${esc(item.group || item.asset_class || "UNKNOWN")}</td><td>${esc(b3Value(item.price))}</td><td>${esc(b3Value(item.change ?? item.variation))}</td><td class="gB3Muted">${esc(item.source || data.source || "UNKNOWN")}</td></tr>`).join("")}</tbody></table>` : b3Empty("Radar sem ativos disponíveis; o estado não foi convertido em zero.");
  const heatmap = $("#gB3MarketHeatmap");
  if (heatmap) heatmap.innerHTML = visibleAssets.length ? visibleAssets.slice(0, 24).map((item) => {
    const change = b3Num(item.change ?? item.variation);
    const tone = change == null ? "unknown" : change >= 0 ? "up" : "down";
    return `<div class="gB3HeatCell ${tone}" title="${esc(`${item.symbol || item.label || "UNKNOWN"} · ${b3Value(item.change ?? item.variation)}`)}"><b>${esc(item.symbol || item.label || "UNKNOWN")}</b><span>${change == null ? "UNKNOWN" : `${change >= 0 ? "+" : ""}${b3Fmt(change)}%`}</span></div>`;
  }).join("") : b3Empty("Mapa indisponível: nenhum ativo observado.");
  b3RenderMarketChart(data.technical_state || {});
  $("#gB3MarketFlow").innerHTML = data.capital_flow ? b3RenderMarketMiniRows(Array.isArray(data.capital_flow) ? data.capital_flow : []) : b3Empty("Fluxo de capitais não fornecido pelo read model.");
  const topAssets = assets.slice().sort((a, b) => Math.abs(bNum(b.change ?? b.variation) ?? 0) - Math.abs(bNum(a.change ?? a.variation) ?? 0)).slice(0, 6);
  $("#gB3MarketTop").innerHTML = b3RenderMarketMiniRows(topAssets);
  const news = Array.isArray(data.news) ? data.news.slice(0, 5) : [];
  $("#gB3MarketNews").innerHTML = news.length ? news.map((item) => `<div class="gB3MarketNewsRow"><b>${esc(item.title || "UNKNOWN")}</b><span>${esc(item.source || "SOURCE UNKNOWN")} · ${esc(item.published_at || "TIME UNKNOWN")}</span></div>`).join("") : b3Empty("Nenhuma notícia verificável disponível.");
  $("#gB3MarketDetail").innerHTML = b3Detail([
    ["SUPORTE/RESISTÊNCIA", data.support_resistance], ["FORÇA DE MOEDAS", data.currency_strength],
    ["SESSÕES", data.market_sessions], ["CALENDÁRIO", data.economic_calendar?.length ?? "UNKNOWN"],
    ["INTEGRIDADE", data.source_integrity], ["REPLAY", data.replay_metadata],
  ]);
  const risk = data.risk || {};
  const validation = data.validation || {};
  const performance = data.performance || {};
  const sources = data.source_availability || {};
  $("#gB3MarketRisk").innerHTML = b3Detail([
    ["STATUS", sources.risk?.status || risk.status || "UNKNOWN"],
    ["MERCADO", risk.market_risk || risk.risk_state || "UNKNOWN"],
    ["SETUP", risk.setup_risk || "UNKNOWN"],
    ["PORTFÓLIO", risk.portfolio_risk || risk.exposure || "UNKNOWN"],
    ["EVENTO", risk.event_risk || "UNKNOWN"],
    ["EXECUÇÃO", "NÃO AUTORIZA TRADE"],
  ]);
  $("#gB3MarketValidation").innerHTML = b3Detail([
    ["STATUS", sources.validation?.status || validation.status || "UNKNOWN"],
    ["ESTÁGIOS", validation.stages?.length ?? "UNKNOWN"],
    ["EVIDÊNCIAS", validation.history?.length ?? "UNKNOWN"],
    ["UNKNOWN", "NÃO É FAIL"],
    ["FONTE", sources.validation?.source || "UNKNOWN"],
  ]);
  $("#gB3MarketPerformance").innerHTML = b3Detail([
    ["STATUS", performance.status || "UNKNOWN"],
    ["AMOSTRA", performance.sample_count ?? "UNKNOWN"],
    ["TIPOS", performance.evidence_type_counts || "UNKNOWN"],
    ["MÉTRICAS", Object.keys(performance.metrics || {}).length || "UNKNOWN"],
    ["LIMITAÇÕES", performance.limitations || "UNKNOWN"],
  ]);
}
function b3RenderScanner(response) {
  const data = b3Payload(response);
  b3State.scanner = Array.isArray(data.normalized_results) ? data.normalized_results : [];
  $("#gB3Scanner").innerHTML = b3State.scanner.length ? `<table class="gB3Table"><thead><tr><th>ATIVO</th><th>DIREÇÃO</th><th>SCORE</th><th>READINESS</th><th>SETUP</th><th>ESTADO</th></tr></thead><tbody>${b3State.scanner.map((item, index) => `<tr data-selectable="1" data-opportunity="${index}"><td>${esc(item.symbol)}</td><td>${esc(item.direction)}</td><td>${esc(b3Value(item.score))}</td><td>${esc(b3Value(item.readiness))}</td><td>${esc(b3Short(item.selected_setup, 42))}</td><td>${b3StateTag(item.status || item.alert_state)}</td></tr>`).join("")}</tbody></table>` : b3Empty("Scanner sem oportunidades verificáveis neste momento.");
  $("#gB3OpportunityDetail").innerHTML = b3State.selectedOpportunity ? b3Detail([
    ["ATIVO", b3State.selectedOpportunity.symbol], ["REGIME", b3State.selectedOpportunity.market_regime],
    ["VOLATILIDADE", b3State.selectedOpportunity.volatility], ["SESSÃO", b3State.selectedOpportunity.session],
    ["HTF BIAS", b3State.selectedOpportunity.HTF_bias], ["H4/H1/M15/M5", b3State.selectedOpportunity.trend],
    ["R:R", b3State.selectedOpportunity.risk_reward], ["CONFLUÊNCIA", b3State.selectedOpportunity.confluence],
    ["INDICADORES", b3State.selectedOpportunity.indicators], ["PROVENANCE", b3State.selectedOpportunity.provenance],
  ]) : b3Empty("Selecione uma oportunidade para abrir o detalhe.");
  document.querySelectorAll("#gB3Scanner tr[data-opportunity]").forEach((row) => {
    row.onclick = () => { b3State.selectedOpportunity = b3State.scanner[Number(row.dataset.opportunity)] || null; b3RenderScanner(response); };
  });
}
function b3RenderRobots(response) {
  const data = b3Payload(response);
  b3State.robots = Array.isArray(data.robots) ? data.robots : [];
  const report = data.report || {};
  const unresolved = report.association_counts?.UNRESOLVED ?? "UNKNOWN";
  $("#gB3Robots").innerHTML = b3State.robots.length ? `<table class="gB3Table"><thead><tr><th>IDENTIDADE</th><th>STATUS FONTE</th><th>COMPILADO</th><th>BACKTESTS</th><th>LIFECYCLE</th></tr></thead><tbody>${b3State.robots.slice(0, 50).map((item, index) => `<tr data-selectable="1" data-robot="${index}"><td>${esc(item.display_name || item.robot_id || "UNKNOWN")}</td><td>${esc(item.source_artifacts?.length ? "AVAILABLE" : "UNKNOWN")}</td><td>${esc(item.compiled_artifacts?.length ? "AVAILABLE" : "UNKNOWN")}</td><td>${esc(b3Value(item.backtest_artifacts?.length ?? item.test_runs?.length))}</td><td>${b3StateTag(item.status || "UNKNOWN")}</td></tr>`).join("")}</tbody></table>` : b3Empty("Catálogo sem robôs observados. Discovery não é executado pelo painel.");
  $("#gB3Unresolved").textContent = `Evidência histórica não resolvida: ${b3Value(unresolved)} · ACTIVE = active in repertoire · autorização de trading: NONE`;
  $("#gB3RobotDetail").innerHTML = b3State.selectedRobot ? b3Detail([
    ["ROBOT ID", b3State.selectedRobot.robot_id], ["NOME", b3State.selectedRobot.display_name],
    ["SOURCE HASH", b3State.selectedRobot.source_hash], ["COMPILED HASH", b3State.selectedRobot.compiled_hash],
    ["PRESETS", b3State.selectedRobot.parameter_sets?.length], ["EVIDÊNCIAS", b3State.selectedRobot.provenance],
    ["TEST RUNS", b3State.selectedRobot.test_runs?.length], ["LIMITAÇÕES", b3State.selectedRobot.known_limitations],
  ]) : b3Empty("Selecione um robô para abrir identidade e evidências.");
  document.querySelectorAll("#gB3Robots tr[data-robot]").forEach((row) => {
    row.onclick = () => { b3State.selectedRobot = b3State.robots[Number(row.dataset.robot)] || null; b3RenderRobots(response); };
  });
}
function b43RenderRobotIntelligence(response) {
  const data = response || {};
  const dataset = data.evidence_dataset || {};
  const suitability = data.suitability || {};
  const identity = data.artifact_identity || {};
  const historicalArtifact = identity.compiled_artifacts?.historical_tested || {};
  const currentArtifact = identity.compiled_artifacts?.current_observed || {};
  const state = $("#gB43State");
  if (state) state.textContent = data.status || suitability.status || "UNKNOWN";
  const summary = b3Detail([
    ["ANÁLISE", suitability.status || "UNKNOWN"],
    ["ROBÔS", data.robot_count ?? "UNKNOWN"],
    ["AMOSTRAS", dataset.unique_samples ?? "UNKNOWN"],
    ["RÓTULOS", dataset.labeled_samples ?? "UNKNOWN"],
    ["MATCHING EMPÍRICO", suitability.empirical_matching || "NOT_IMPLEMENTED"],
    ["AUTORIZAÇÃO", "NOT_GRANTED"],
    ["TESTED COMPILED", b3Short(historicalArtifact.sha256 || "UNKNOWN", 18)],
    ["CURRENT COMPILED", b3Short(currentArtifact.sha256 || "UNKNOWN", 18)],
    ["IDENTITY STATUS", identity.source_compiled_relationship?.compiled_identity_status || "UNKNOWN"],
  ]);
  const rows = Array.isArray(suitability.results) ? suitability.results : [];
  const table = rows.length ? `<table class="gB3Table"><thead><tr><th>ROBÔ</th><th>REPERTOIRE</th><th>SUITABILITY</th><th>EVIDÊNCIA</th><th>POR QUÊ</th></tr></thead><tbody>${rows.slice(0, 50).map((item) => `<tr><td>${esc(item.name || item.robot_id || "UNKNOWN")}</td><td>${b3StateTag(item.repertoire_status || "UNKNOWN")}</td><td>${b3StateTag(item.match_status || "UNKNOWN")}</td><td>${esc(item.evidence_strength || "UNKNOWN")}</td><td class="gB3Muted">${esc((item.explanation?.why || []).concat(item.explanation?.why_not || []).join("; ") || "UNKNOWN")}</td></tr>`).join("")}</tbody></table>` : b3Empty("Nenhuma suitability verificável disponível.");
  const identityNote = `<p class="gB3Note">TESTED ARTIFACT: ${esc(b3Short(historicalArtifact.sha256 || "UNKNOWN", 24))} · CURRENT ARTIFACT: ${esc(b3Short(currentArtifact.sha256 || "UNKNOWN", 24))} · HISTORICAL BYTES: ${esc(identity.historical_artifact_availability || "UNKNOWN")} · CURRENT ROBOT TESTED: NO</p>`;
  $("#gB43RobotIntelligence").innerHTML = summary + table + identityNote + `<p class="gB3Note">ANALYSIS ONLY · ACTIVE NO REPERTOIRE NÃO AUTORIZA TRADING · OPAQUE_AI_SCORE=FALSE</p>`;
}
function b3RenderEvidence(response) {
  const validation = b3Payload(response?.validation);
  const tester = b3Payload(response?.tester);
  const rows = [...(validation.history || []).map((item) => ({ ...item, kind: "VALIDATION" })), ...(tester.test_runs || []).map((item) => ({ ...item, kind: "TESTER" }))];
  $("#gB3Evidence").innerHTML = rows.length ? `<table class="gB3Table"><thead><tr><th>TIPO</th><th>IDENTIDADE</th><th>CLASSIFICAÇÃO</th><th>STATUS</th><th>FONTE</th></tr></thead><tbody>${rows.slice(0, 80).map((item) => `<tr><td>${esc(item.kind)}</td><td>${esc(item.run_id || item.test_run_id || item.id || "UNKNOWN")}</td><td>${esc(item.evidence_class || item.evidence_type || "UNKNOWN")}</td><td>${esc(item.status || "UNKNOWN")}</td><td class="gB3Muted">${esc(item.source || item.artifact || "UNKNOWN")}</td></tr>`).join("")}</tbody></table>` : b3Empty("Nenhuma evidência verificável disponível.");
}
function b46RenderTemporalContext(response, marketResponse) {
  const el = $("#gB46TemporalContext");
  if (!el) return;
  const current = b3Payload(marketResponse).temporal_context || {};
  const contexts = Array.isArray(response?.temporal_contexts) ? response.temporal_contexts : [];
  const rows = contexts.map((item) => {
    const labels = item.labels || {};
    const label = (name) => labels[name]?.label || "UNKNOWN";
    const artifact = item.historical_artifact || {};
    return `<tr><td>${esc(item.test_run_id || "UNKNOWN")}</td><td>${esc(`${item.window?.from || "UNKNOWN"} → ${item.window?.to || "UNKNOWN"}`)}</td><td>${esc(label("TREND_STATE"))}</td><td>${esc(label("VOLATILITY_STATE"))}</td><td>${esc(label("SESSION_STATE"))}</td><td title="${esc(artifact.normalized_fingerprint || "UNKNOWN")}">${esc(b3Short(artifact.normalized_fingerprint || "UNKNOWN", 18))}</td><td>${esc(item.context_status || "UNKNOWN")}</td></tr>`;
  }).join("");
  const currentLabels = current.label_status || {};
  const summary = b3Detail([
    ["CURRENT CONTEXT", current.context_status || "UNKNOWN"],
    ["POINT-IN-TIME", current.point_in_time_supported ? "STRUCTURAL" : "UNKNOWN"],
    ["CONTEXT FINGERPRINT", current.context_fingerprint || "UNKNOWN"],
    ["AVAILABLE_AT", current.available_at || "UNKNOWN"],
    ["OUTCOME IN LABELING", "EXCLUDED"],
    ["R1/R2/R3", contexts.length || "UNKNOWN"],
  ]);
  const table = rows ? `<div class="gB3TableWrap"><table class="gB3Table"><thead><tr><th>RUN</th><th>WINDOW</th><th>TREND</th><th>VOLATILITY</th><th>SESSION</th><th>ARTIFACT</th><th>STATUS</th></tr></thead><tbody>${rows}</tbody></table></div>` : b3Empty("Nenhum contexto histórico congelado disponível.");
  const outcomes = Array.isArray(response?.temporal_evidence?.rows) ? response.temporal_evidence.rows : [];
  const outcomeTable = outcomes.length ? `<div class="gB3TableWrap"><table class="gB3Table"><thead><tr><th>POST_WINDOW_OUTCOME</th><th>ROBÔ</th><th>BALANCE CHANGE</th><th>CONTEXT FINGERPRINT</th></tr></thead><tbody>${outcomes.map((item) => `<tr><td>${esc(item.test_run_id || "UNKNOWN")}</td><td>${esc(item.robot_id || "UNKNOWN")}</td><td>${esc(item.post_window_outcome?.balance_change ?? "UNKNOWN")}</td><td class="gB3Muted">${esc(b3Short(item.context_fingerprint || "UNKNOWN", 24))}</td></tr>`).join("")}</tbody></table></div>` : "";
  el.innerHTML = summary + table + outcomeTable + `<p class="gB3Note">Rótulos ausentes permanecem UNKNOWN. Contexto congelado antes do POST_WINDOW_OUTCOME. ${esc(Object.keys(currentLabels).length ? "READ MODEL" : "HISTORICAL ARTIFACT PENDENTE")}</p>`;
}
function b3RenderMemory(response) {
  const contract = response?.contract || {};
  const status = contract.status || "UNKNOWN";
  $("#gScientificMemorySummary").innerHTML = b3Detail([
    ["STATUS", status], ["AUTORIDADE", contract.authority || "CanonicalMemoryBoundary"],
    ["SCHEMA CHANGE", response?.schema_change_required ? "YES" : "NO"],
    ["IMPORT EXECUTADO", response?.import_executed ? "YES" : "NO"],
    ["REGISTROS", contract.engine?.memory_count ?? contract.engine?.records ?? "UNKNOWN"],
    ["ENTIDADES", contract.graph?.entities ?? "UNKNOWN"],
  ]);
  const matrix = Array.isArray(response?.matrix) ? response.matrix : [];
  $("#gB3MemoryRelations").innerHTML = matrix.length ? `<table class="gB3Table"><thead><tr><th>CONCEITO</th><th>EQUIVALENTE JARVIS</th><th>RELAÇÃO/GAP</th><th>DECISÃO</th></tr></thead><tbody>${matrix.map((item) => `<tr><td>${esc(item.legacy_concept)}</td><td>${esc(item.current_jarvis_equivalent)}</td><td>${esc(item.gap)}</td><td>${esc(item.decision)}</td></tr>`).join("")}</tbody></table>` : b3Empty("Nenhuma relação científica disponível.");
}
function b3RenderProvenance(responses) {
  const rows = Object.entries(responses).map(([name, response]) => [name, b3Status(response), response?.freshness || response?.provenance?.freshness_state || "UNKNOWN", response?.provenance?.source_module || response?.provenance?.provider || "JarvisService", response?.content_fingerprint || response?.provenance?.content_fingerprint || "UNKNOWN"]);
  $("#gB3Provenance").innerHTML = `<table class="gB3Table"><thead><tr><th>READ MODEL</th><th>STATUS</th><th>FRESHNESS</th><th>SOURCE</th><th>FINGERPRINT</th></tr></thead><tbody>${rows.map((item) => `<tr><td>${esc(item[0])}</td><td>${b3StateTag(item[1])}</td><td>${esc(item[2])}</td><td>${esc(item[3])}</td><td class="gB3Muted" title="${esc(item[4])}">${esc(b3Short(item[4], 24))}</td></tr>`).join("")}</tbody></table>`;
}
async function refreshGoldenBridge() {
  const state = $("#gGoldenBridgeState");
  if (!state || b3State.busy) return;
  b3State.busy = true;
  b3State.symbol = ($(("#gB3Symbol"))?.value || "XAUUSD").trim().toUpperCase() || "XAUUSD";
  b3State.timeframe = $("#gB3Timeframe")?.value || "M15";
  state.textContent = "CONSULTANDO";
  $("#gB3Safety").textContent = "READ-ONLY · NO TRADING";
  $("#gB3MarketSummary").innerHTML = b3Empty("Atualizando o read model do Radar...");
  $("#gB3MarketKpis").innerHTML = "";
  $("#gB3MarketHeatmap").innerHTML = b3Empty("Atualizando ativos observados...");
  $("#gB3MarketFlow").innerHTML = "";
  $("#gB3MarketTop").innerHTML = "";
  $("#gB3MarketNews").innerHTML = "";
  try {
    const post = window.Gateway?.httpPost;
    if (!post) throw new Error("Gateway indisponível");
    const [overview, market, robots, robotIntelligence, evidence, memory] = await Promise.all([
      post.call(window.Gateway, "/api/jarvis/golden/overview", { include_live: false }),
      post.call(window.Gateway, B3_MARKET_INTELLIGENCE_ENDPOINT, { symbol: b3State.symbol, timeframe: b3State.timeframe }),
      post.call(window.Gateway, "/api/jarvis/golden/robots", {}),
      post.call(window.Gateway, B43_ROBOT_INTELLIGENCE_ENDPOINT, { symbol: b3State.symbol, timeframe: b3State.timeframe }),
      post.call(window.Gateway, "/api/jarvis/golden/evidence", { limit: 30 }),
      post.call(window.Gateway, "/api/jarvis/memory/scientific", {}),
    ]);
    // The scanner projection is part of the same correlated snapshot.
    const scanner = market?.scanner ? {
      ...market.scanner,
      ok: market.ok,
      status: market.scanner.status || market.status,
      snapshot_id: market.snapshot_id,
      correlation_id: market.correlation_id,
      provenance: market.provenance,
    } : { ok: false, status: "UNAVAILABLE", normalized_results: [] };
    b3State.responses = { overview, market, scanner, robots, robotIntelligence, evidence, memory };
    const failures = Object.values(b3State.responses).filter((item) => !item || item.ok === false).length;
    const responseCount = Object.keys(b3State.responses).length;
    state.textContent = failures ? (failures === responseCount ? "UNAVAILABLE" : "PARTIAL") : "READ-ONLY";
    ["gB3MarketState", "gB3ScannerState", "gB3RobotState", "gB3EvidenceState", "gB3MemoryState"].forEach((id, index) => b3RenderStatus(id, [market, scanner, robots, evidence, memory][index]));
    b3Overview(overview || {}, market, scanner, robots, evidence || {}, memory || {});
    b3RenderMarket(market || {});
    b3RenderScanner(scanner || {});
    b3RenderRobots(robots || {});
    b43RenderRobotIntelligence(robotIntelligence || {});
    b46RenderTemporalContext(robotIntelligence || {}, market || {});
    b3RenderEvidence(evidence || {});
    b3RenderMemory(memory || {});
    b3RenderProvenance(b3State.responses);
    $("#gB3ProvenanceState").textContent = failures ? "PARTIAL" : "AVAILABLE";
  } catch (error) {
    state.textContent = "UNAVAILABLE";
    $("#gGoldenBridgeSummary").innerHTML = b3Empty(error?.message || "Read models indisponíveis.");
    ["gB3MarketSummary", "gB3MarketAssets", "gB3MarketHeatmap", "gB3MarketFlow", "gB3MarketTop", "gB3MarketNews", "gB3MarketDetail", "gB3MarketRisk", "gB3MarketValidation", "gB3MarketPerformance", "gB46TemporalContext", "gB43RobotIntelligence"].forEach((id) => {
      const el = $(`#${id}`); if (el) el.innerHTML = b3Empty("Read model indisponível; nenhum valor foi substituído.");
    });
    ["gB3MarketState", "gB3ScannerState", "gB3RobotState", "gB43State", "gB3EvidenceState", "gB3MemoryState", "gB3ProvenanceState"].forEach((id) => { const el = $(`#${id}`); if (el) el.textContent = "UNAVAILABLE"; });
  } finally {
    b3State.busy = false;
  }
}
window.JarvisB3Refresh = refreshGoldenBridge;

// ------------------------------------------------------------------ INIT ----
function wireUI() {
  $("#sysName").textContent = CFG.systemName;
  $("#sysSub").textContent = CFG.systemSub;
  $("#inputRow").onsubmit = (e) => { e.preventDefault(); submitCommand(cmdInput.value); };
  micBtn.onclick = async () => {
    if (isJarvisDesktop) {
      logLine("Microfone Desktop acionado", "ok");
      const ok = await desktopVoice.start();
      if (ok) sfx.listenOn();
      return;
    }
    if (voice.isListening()) { voice.stop(); return; }
    if (settings.speak === false) { /* ainda dá para ouvir */ }
    const ok = voice.start(false);
    if (ok) sfx.listenOn();
  };
  $("#voiceToggleBtn").onclick = () => {
    settings.speak = !settings.speak; persist();
    $("#speakToggle").checked = settings.speak;
    $("#voiceToggleBtn").classList.toggle("active", settings.speak);
    updateModules();
    toast("VOZ", settings.speak ? "Respostas faladas ativadas." : "Respostas faladas desativadas.", "ok");
    if (!settings.speak) voice.stopSpeaking();
  };
  $("#voiceToggleBtn").classList.toggle("active", settings.speak);
  $("#themeBtn").onclick = cycleTheme;
  $("#settingsBtn").onclick = openSettings;
  $("#fullscreenBtn").onclick = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await app.requestFullscreen();
    } catch { toast("TELA CHEIA", "Bloqueado pelo navegador. Use F11.", "bad"); }
  };
  $("#statusPill").onclick = () => {
    const s = bridge.status;
    if (s === "online") { bridge.disconnect(); toast("GATEWAY", "Conexão encerrada — modo local.", ""); }
    else { bridge.connect(); toast("GATEWAY", "Conectando ao Gateway...", ""); }
  };
  $("#bootSkipBtn").onclick = () => { bootOverlay.classList.add("done"); };
  $("#gGoldenBridgeRefresh")?.addEventListener("click", refreshGoldenBridge);
  $("#gB3MarketGroup")?.addEventListener("change", (event) => {
    b3State.marketGroup = event.target.value || "ALL";
    if (b3State.marketResponse) b3RenderMarket(b3State.marketResponse);
  });

  document.addEventListener("keydown", (e) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (e.key === "Escape") {
      if (!settingsModal.hidden) return closeSettings();
      voice.stopSpeaking(); voice.stop(); setState("idle"); return;
    }
    if (typing) return;
    if (e.key === " ") { e.preventDefault(); micBtn.click(); }
    else if (e.key.toLowerCase() === "t") { cycleTheme(); }
    else if (e.key.toLowerCase() === "m") { $("#voiceToggleBtn").click(); }
    else if (e.key.toLowerCase() === "s" && app.dataset.theme === "golden") { golden.setShadow(!golden.isShadow()); }
    else if (e.key === "/") { e.preventDefault(); cmdInput.focus(); }
  });

  window.addEventListener("resize", () => { hud.resize(); updateOrbTarget(); golden?.refresh(); });
  wireHudPointer();
  if (window.ResizeObserver) new ResizeObserver(updateOrbTarget).observe(orbWrap);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) hud.stop(); else hud.start();
  });
  window.addEventListener("online", () => logLine("Rede restaurada", "ok"));
  window.addEventListener("offline", () => logLine("Rede perdida", "bad"));
  if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = () => fillVoiceSelect();
}

function setPlaceholder() {
  cmdInput.placeholder = innerWidth < 520 ? "Digite um comando…" : "Fale ou digite um comando, senhor...";
}

function rotateQuips() {
  if (!idleQuips.length) return;
  setInterval(() => {
    if (appState !== "idle") return;
    quipIdx = (quipIdx + 1) % idleQuips.length;
    stateHint.textContent = idleQuips[quipIdx];
  }, 9000);
}

async function init() {
  wireUI();
  wireSettings();
  wireConfirmationDialog();
  renderThemeGrid();
  renderQuickActions();
  renderChips();
  buildTelemetry();
  updateModules();
  setPlaceholder();
  window.addEventListener("resize", setPlaceholder);
  fillVoiceSelect();
  renderCapabilities();
  metrics.start();
  applyTheme(settings.theme, true);
  hud.start();
  updateOrbTarget();
  setState("idle");
  initBattery();
  setInterval(paintTelemetry, 1000);
  setInterval(tickClock, 1000);
  tickClock();
  updateModules();
  setInterval(updateModules, 5000);
  rotateQuips();

  vcWake.textContent = settings.wakeWord;
  voiceCard.dataset.on = "0";
  vcState.textContent = voiceSupported() ? "PARADO" : "SEM SUPORTE";

  if (settings.speak) $("#voiceToggleBtn").classList.add("active");

  const shouldConnectGateway = settings.autoConnect || isJarvisDesktop;
  const welcomeLine = shouldConnectGateway
    ? `Interface pronta. Conectando ao Gateway, ${CFG.userName}.`
    : `Interface pronta, ${CFG.userName}. Abra as CONFIGURAÇÕES para conectar o Gateway.`;
  addMessage("jarvis", welcomeLine, { typing: false });
  logLine("sessão iniciada", "ok");

  await runBoot();

  if (shouldConnectGateway) {
    bridge.connect();
  }
  if (settings.wake) {
    if (isJarvisDesktop) desktopVoice.start({ capture: false }); else voice.enableWake(settings.wakeWord);
  }
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();

window.jarvis = { submitCommand, applyTheme, bridge, voice, hud, brain, metrics, golden, settings, notes, addMessage, toast, clearConversation };
