/* Desktop-only Jarvis conversation surface.
 * Existing conversation, input, voice and task nodes are moved into this
 * composition; no assistant, transport, tool registry or permission path is
 * created here. The public Web UI never imports this module. */

const PERSONAS = [
  ["equilibrado", "Equilibrado", "Direto e cordial."],
  ["brincalhao", "Brincalhão", "Humor leve e presença."],
  ["ignorante", "Ignorante", "Impaciência sem hostilidade."],
  ["malandro", "Malandro", "Descontraído e esperto."],
  ["profissional", "Profissional", "Formal e objetivo."],
  ["rigoroso", "Rigoroso", "Firme com riscos e erros."],
  ["mordomo", "Mordomo", "Elegante e cerimonioso."],
  ["amigo", "Amigo", "Caloroso e próximo."],
  ["direto", "Direto", "Só o necessário."],
  ["motivador", "Motivador", "Energético e encorajador."],
  ["narrador", "Narrador", "Ritmo e presença."],
  ["amoroso", "Amoroso", "Acolhedor sem perder o foco."],
  ["sarcastico", "Sarcástico", "Ironia fina, sem risco."],
];

const GEMINI_VOICES = [
  ["Zephyr", "Brilhante"], ["Puck", "Animada e para cima"],
  ["Charon", "Firme e informativa"], ["Kore", "Firme e segura"],
  ["Fenrir", "Empolgada e energética"], ["Leda", "Jovem e leve"],
  ["Orus", "Firme e decidida"], ["Aoede", "Leve e descontraída"],
  ["Callirrhoe", "Natural e tranquila"], ["Autonoe", "Brilhante"],
  ["Enceladus", "Suave e soprosa"], ["Iapetus", "Clara"],
  ["Umbriel", "Tranquila e de boa"], ["Algieba", "Macia e sem pressa"],
  ["Despina", "Macia e fluida"], ["Erinome", "Clara"],
  ["Algenib", "Grave e marcante"], ["Rasalgethi", "Informativa"],
  ["Laomedeia", "Animada"], ["Achernar", "Suave e delicada"],
  ["Alnilam", "Firme"], ["Schedar", "Equilibrada"], ["Gacrux", "Madura"],
  ["Pulcherrima", "Direta"], ["Achird", "Amigável"],
  ["Zubenelgenubi", "Casual"], ["Vindemiatrix", "Calma e gentil"],
  ["Sadachbia", "Viva"], ["Sadaltager", "Conhecedora"],
  ["Sulafat", "Calorosa e próxima"],
];

const MODE_ICONS = {
  chat: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5.5h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-7l-4.5 3v-3H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z"/><path d="M8 10h8M8 13h5"/></svg>`,
  images: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="9" cy="9" r="1.5"/><path d="m5.5 17 4.1-4.2 2.8 2.6 2.3-2.2 3.8 3.8"/></svg>`,
  codex: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 7-5 5 5 5M15 7l5 5-5 5M13 4l-2 16"/></svg>`,
  web: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M3.8 12h16.4M12 3.5c2.2 2.3 3.3 5.1 3.3 8.5s-1.1 6.2-3.3 8.5c-2.2-2.3-3.3-5.1-3.3-8.5S9.8 5.8 12 3.5Z"/></svg>`,
  automation: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/></svg>`,
  files: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 6.5h6l1.8 2h9.2v9a2 2 0 0 1-2 2h-15Z"/><path d="M3.5 6.5a2 2 0 0 1 2-2h4l1.8 2"/></svg>`,
};

const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>\"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;",
}[char]));

function storedSettings() {
  try {
    const raw = localStorage.getItem(`jarvis.settings.v1::${window.generatorName || "local"}`);
    return raw ? JSON.parse(raw) || {} : {};
  } catch { return {}; }
}

function saveSettings(settings) {
  try { localStorage.setItem(`jarvis.settings.v1::${window.generatorName || "local"}`, JSON.stringify(settings)); }
  catch { /* local preference persistence is best effort */ }
}

// The reference sidebar is a history, not a second copy of the active chat.
// Keep only archived summaries/transcripts here so the current conversation
// remains in the main panel, like the Codex conversation layout.
function referenceConversationStoreKey() {
  return `jarvis.conversations.v1::${window.generatorName || "local"}`;
}

function loadReferenceConversations() {
  try {
    const raw = localStorage.getItem(referenceConversationStoreKey());
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && item.id && item.archived !== false)
      .map((item) => ({
        id: String(item.id),
        title: String(item.title || "Conversa"),
        preview: String(item.preview || "Sem mensagens"),
        time: String(item.time || "—"),
        archivedAt: Number(item.archivedAt || 0),
        messages: Array.isArray(item.messages)
          ? item.messages.filter((message) => message && message.text).slice(-120).map((message) => ({
            role: String(message.role || "jarvis"),
            text: String(message.text || ""),
          }))
          : [],
      }))
      .sort((left, right) => right.archivedAt - left.archivedAt)
      .slice(0, 50);
  } catch { return []; }
}

function saveReferenceConversations(conversations) {
  try {
    localStorage.setItem(referenceConversationStoreKey(), JSON.stringify(
      (Array.isArray(conversations) ? conversations : []).slice(0, 50),
    ));
  } catch { /* local conversation history is best effort */ }
}

function durableConversationPreview(item) {
  const updated = Number(item?.updated_at || 0);
  return {
    id: String(item?.conversation_id || ""),
    title: String(item?.title || item?.first_user_preview || "Conversa"),
    preview: String(item?.last_preview || item?.first_user_preview || "Sem mensagens"),
    time: updated ? new Date(updated * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—",
    archivedAt: updated * 1000,
    archived: true,
    durable: true,
    messages: [],
  };
}

async function hydrateDurableConversations(surface, state) {
  const post = endpoint();
  if (!post) return;
  const result = await post("/api/jarvis/conversations", { limit: 50 }).catch(() => null);
  if (!result?.ok || !Array.isArray(result.conversations)) return;
  const durable = result.conversations
    .map(durableConversationPreview)
    .filter((item) => item.id);
  const local = (Array.isArray(state.referenceConversations) ? state.referenceConversations : [])
    .filter((item) => !durable.some((entry) => entry.id === item.id));
  state.referenceConversations = [...durable, ...local]
    .sort((left, right) => Number(right.archivedAt || 0) - Number(left.archivedAt || 0))
    .slice(0, 50);
  saveReferenceConversations(state.referenceConversations);
  renderReferenceConversations(surface, state);
}

function newReferenceConversation() {
  return {
    id: `conversation-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title: "Conversa atual",
    preview: "",
    time: "agora",
    messages: [],
  };
}

function canonicalConversationSnapshot() {
  const root = document.querySelector("#conversation");
  if (!root) return [];
  return [...root.querySelectorAll(":scope > .msg")]
    .map((node) => {
      const role = ["user", "jarvis", "sys", "err"].find((candidate) => node.classList.contains(candidate)) || "jarvis";
      return { role, text: String(node.querySelector(".body")?.textContent || "").trim() };
    })
    .filter((message) => message.text)
    .slice(-120);
}

function archiveReferenceConversation(state) {
  const current = state?.referenceCurrent;
  if (!current) return false;
  const visibleMessages = canonicalConversationSnapshot();
  const messages = visibleMessages.length
    ? visibleMessages
    : (Array.isArray(current.messages) ? current.messages : []);
  // A welcome/system response alone is not an old conversation. Archive only
  // sessions in which the operator actually sent a message.
  if (!messages.some((message) => message.role === "user")) return false;
  const firstUser = messages.find((message) => message.role === "user");
  const item = {
    id: current.id,
    title: firstUser?.text?.slice(0, 52) || current.title || "Conversa",
    preview: (messages[messages.length - 1]?.text || current.preview || "Sem mensagens").slice(0, 90),
    time: current.time || new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    archivedAt: Date.now(),
    archived: true,
    messages,
  };
  state.referenceConversations = [
    item,
    ...(Array.isArray(state.referenceConversations) ? state.referenceConversations : []).filter((entry) => entry.id !== item.id),
  ].slice(0, 50);
  saveReferenceConversations(state.referenceConversations);
  return true;
}

function endpoint() {
  return window.Gateway?.isAuthenticated && typeof window.Gateway.httpPost === "function"
    ? window.Gateway.httpPost.bind(window.Gateway) : null;
}

function voiceAuthorizationPayload(state, payload = {}) {
  const token = state?.geminiAuthorizationToken || "";
  return token ? { ...payload, authorization_token: token } : payload;
}

function setSettingsGeminiStatus(value) {
  const node = document.querySelector("#settingsGeminiStatus");
  if (node) node.textContent = String(value || "Gemini Live aguardando estado.");
}

function syncSettingsMirror(state) {
  const mode = document.querySelector("#voiceMode");
  const voice = document.querySelector("#geminiVoice");
  if (mode) mode.value = state.settings.voiceMode;
  if (voice) voice.value = state.settings.geminiVoice;
  document.querySelectorAll("#personaGrid [data-persona]").forEach((node) => {
    node.setAttribute("aria-pressed", String(node.dataset.persona === state.settings.persona));
  });
}

function clearGeminiGrantRenewal(state) {
  if (state?._geminiGrantRenewTimer) {
    window.clearTimeout(state._geminiGrantRenewTimer);
    state._geminiGrantRenewTimer = 0;
  }
}

function scheduleGeminiGrantRenewal(surface, state, expiresIn = 120) {
  if (!state?.geminiAuthorizationToken) return;
  if (state._geminiGrantRenewTimer) return;
  const delay = Math.max(30, Math.min(Number(expiresIn || 120) - 30, 90)) * 1000;
  state._geminiGrantRenewTimer = window.setTimeout(async () => {
    state._geminiGrantRenewTimer = 0;
    const post = endpoint();
    if (!post || !state.geminiAuthorizationToken) return;
    const renewed = await post(
      "/api/jarvis/voice-service/gemini/renew",
      voiceAuthorizationPayload(state),
    ).catch((error) => ({ ok: false, error: error?.message || String(error) }));
    if (renewed?.ok && renewed.authorization_token) {
      state.geminiAuthorizationToken = renewed.authorization_token;
      window.__JARVIS_GEMINI_AUTH_TOKEN__ = state.geminiAuthorizationToken;
      scheduleGeminiGrantRenewal(surface, state, renewed.expires_in);
      return;
    }
    if (renewed?.authorization_required || renewed?.error === "VOICE_AUTHORIZATION_REQUIRED") {
      state.geminiAuthorizationToken = "";
      clearGeminiGrantRenewal(state);
      window.__JARVIS_GEMINI_AUTH_TOKEN__ = "";
      const status = $("[data-dj-gemini-preview-status]", surface);
      if (status) status.textContent = "Autorização Gemini expirada; clique em INICIAR GEMINI LIVE.";
      await refreshStatus(surface, state);
    }
  }, delay);
}

function addStatus(parent, label, id, value = "—") {
  const card = document.createElement("article");
  card.className = "djStatusCard";
  card.innerHTML = `<span>${esc(label)}</span><b data-dj-value="${esc(id)}">${esc(value)}</b>`;
  parent.append(card);
}

function setValue(surface, id, value, state = "") {
  const node = [...surface.querySelectorAll("[data-dj-value]")]
    .find((candidate) => candidate.dataset.djValue === id);
  if (!node) return;
  node.textContent = String(value ?? "—");
  if (state) node.dataset.state = state;
}

function statusCode(data) {
  return [data?.error_code, data?.code, data?.reason, data?.status_reason, data?.error]
    .filter(Boolean).join(" ").toUpperCase();
}

function setupDiagnosticSummary(result) {
  const candidates = [
    result?.diagnostics,
    result?.status?.diagnostics?.provider?.transport,
  ];
  const diagnostics = candidates.find((item) => item && typeof item === "object"
    && Object.keys(item).length > 0) || {};
  const runtime = diagnostics?.runtime || {};
  const credential = diagnostics?.credential || {};
  const fields = [
    ["fase", diagnostics?.phase],
    ["exceção", diagnostics?.last_error_class || diagnostics?.error_class],
    ["categoria", diagnostics?.last_error_category || diagnostics?.category],
    ["fechamento", diagnostics?.remote_close_code ?? diagnostics?.close_code],
    ["motivo", diagnostics?.remote_close_reason || diagnostics?.close_reason],
    ["duração_ms", diagnostics?.connect_duration_ms ?? diagnostics?.duration_ms],
    ["modelo", runtime?.model || diagnostics?.model],
    ["voz", diagnostics?.voice || runtime?.voice],
    ["API", runtime?.api_version],
    ["Python", runtime?.python_version],
    ["SDK", runtime?.google_genai_version],
    ["credencial", credential?.resolution],
    ["runtime", runtime?.runtime_instance_id],
    ["correlação", runtime?.correlation_id || diagnostics?.correlation_id],
    ["backend", diagnostics?.connection?.backend],
    ["loop", diagnostics?.connection?.event_loop_class],
    ["ws_host", diagnostics?.connection?.websocket_base_host],
    ["proxy", diagnostics?.connection?.proxy_env_present
      ? Object.entries(diagnostics.connection.proxy_env_present).filter(([, present]) => present).map(([name]) => name).join(",") || "nenhum"
      : undefined],
  ].filter(([, value]) => value !== undefined && value !== null && String(value) !== "");
  return fields.map(([label, value]) => `${label}=${String(value).slice(0, 160)}`).join(" · ");
}

function voiceState(data, state) {
  const profile = data?.conversation_profile || data?.profile || {};
  const reason = [statusCode(data), profile?.reason, profile?.status].filter(Boolean).join(" ").toUpperCase();
  const liveConnected = profile?.gemini_live_connected === true;
  const requested = profile?.requested_mode || state.settings.voiceMode || "gemini_live";
  const features = data?.voice_features || {};
  const liveAvailable = features.gemini_live === true || data?.gemini_live_ready === true;
  if (liveConnected && profile?.voice_change_requires_reconnect === true) {
    return { label: "GEMINI LIVE · VOZ PENDENTE", state: "warn", detail: "Sessão conectada; a nova voz será aplicada ao encerrar e iniciar novamente." };
  }
  if (liveConnected) {
    return { label: "GEMINI LIVE · CONECTADO", state: "ok", detail: "Sessão Gemini Live conectada; permissões locais adicionais permanecem separadas." };
  }
  const disabledByProfile = reason.includes("VOICE_DISABLED_BY_PROFILE")
    || reason.includes("PROFILE_BLOCKED")
    || (reason.includes("PROFILE") && data?.enabled === false);
  if (disabledByProfile) return { label: "VOICE_DISABLED_BY_PROFILE", state: "error", detail: "A voz está bloqueada pelo perfil atual; nenhuma permissão foi contornada." };
  if (data?.ok === false) return { label: "VOICE SERVICE · ERROR", state: "error", detail: `VoiceService indisponível${statusCode(data) ? ` (${statusCode(data)})` : ""}.` };
  if (data?.enabled === false) return { label: "VOICE SERVICE · DISABLED", state: "error", detail: "VoiceService desativado; ative-o pelo mecanismo autorizado." };
  const rememberedFailure = state?.geminiFailure;
  const liveDiagnostics = data?.gemini_live?.diagnostics || {};
  const providerDiagnostics = liveDiagnostics?.provider || {};
  const transportDiagnostics = providerDiagnostics?.transport || {};
  const providerError = transportDiagnostics?.last_error || providerDiagnostics?.metrics?.last_error || "";
  if (requested === "gemini_live" && (rememberedFailure?.code || providerError)) {
    const code = rememberedFailure?.code || "GEMINI_LIVE_CONNECT_FAILED";
    const detail = rememberedFailure?.detail || providerError;
    return { label: "GEMINI LIVE · ERRO", state: "error", detail: `${code}${detail ? ` · ${detail}` : ""}` };
  }
  if (requested === "gemini_live" && !liveAvailable) {
    return { label: "GEMINI LIVE · INDISPONÍVEL", state: "warn", detail: "Gemini Live não está disponível no Core; a captura não será desviada para a pipeline local." };
  }
  if (requested === "gemini_live" && (data?.gemini_authorization === "NOT_AUTHORIZED" || data?.authorization_required === true)) {
    return { label: "GEMINI LIVE · AUTORIZAÇÃO NECESSÁRIA", state: "warn", detail: "Provider disponível, mas a sessão ainda não foi autorizada; clique em INICIAR GEMINI LIVE." };
  }
  if (requested === "gemini_live" && liveAvailable && !liveConnected) {
    return { label: "GEMINI LIVE · NOT CONNECTED", state: "warn", detail: "Provider disponível, mas a sessão remota não está conectada." };
  }
  return { label: liveConnected ? "GEMINI LIVE · ENABLED" : "GEMINI LIVE · AGUARDANDO", state: liveConnected ? "ok" : "warn", detail: liveConnected ? "Sessão Gemini Live conectada." : "Gemini Live ainda não está conectado; nenhum TTS local será usado." };
}

function microphoneState(data, state, voice) {
  if (!data || data.ok === false) {
    const code = statusCode(data);
    if (code.includes("VOICE_DISABLED_BY_PROFILE") || data?.disabled_by_profile === true) {
      return { label: "AUTHORIZATION REQUIRED", state: "warn", detail: "O microfone só é liberado durante uma sessão Gemini Live autorizada; não é uma falha de hardware." };
    }
    if (code.includes("PERMISSION") || code.includes("ACCESS")) return { label: "PERMISSION DENIED", state: "error", detail: "O sistema bloqueou o acesso ao microfone." };
    return { label: "UNAVAILABLE", state: "error", detail: code ? `Enumeração indisponível (${code}).` : "Não foi possível enumerar os microfones." };
  }
  const endpoints = Array.isArray(data.microphones) ? data.microphones : [];
  if (!endpoints.length) return { label: "NO ENDPOINT", state: "warn", detail: "Nenhum endpoint de entrada foi enumerado." };
  const selectedId = voice?.microphone?.selected_id || state.settings.microphoneId || "";
  if (selectedId && !endpoints.some((item) => item.stable_id === selectedId)) {
    return { label: "SELECTED · MISSING", state: "warn", detail: "O endpoint salvo não está conectado; escolha outro dispositivo." };
  }
  if (selectedId) {
    const selected = endpoints.find((item) => item.stable_id === selectedId);
    return { label: "SELECTED · READY", state: "ok", detail: `${selected?.name || "Endpoint selecionado"} · ${selected?.host_api || "API desconhecida"}.` };
  }
  return { label: `AVAILABLE · ${endpoints.length} ENDPOINT(S)`, state: "ok", detail: "Dispositivos enumerados; selecione um endpoint para capturar áudio." };
}

function buildSurface() {
  // There is also a navigation button with data-view="conversa". Target the
  // actual view container first; the fallback preserves compatibility with
  // older shells that did not add the .gView class.
  const view = document.querySelector('.gView[data-view="conversa"]')
    || document.querySelector('[data-view="conversa"]');
  const band = view?.querySelector(":scope > .gBand");
  if (!view || !band || view.querySelector(".desktopJarvisExperience")) return null;

  // These are already-wired canonical widgets. They are moved, never cloned.
  const taskPanel = band.querySelector(".gTaskPanel");
  const chatCard = band.querySelector(".gChatCard");
  const commandCard = band.querySelector(".gCmdCard");
  const quickPanel = band.querySelector(".gQuickPanel");
  const chatSlot = chatCard?.querySelector("#gChatSlot");
  const inputSlot = commandCard?.querySelector("#gInputSlot");
  const quick = quickPanel?.querySelector("#gQuick");
  if (!taskPanel || !chatCard || !commandCard || !quickPanel || !chatSlot || !inputSlot) return null;

  const surface = document.createElement("section");
  surface.className = "desktopJarvisExperience djReferenceSurface";
  surface.setAttribute("aria-label", "Central de conversa Jarvis Desktop");
  surface.innerHTML = `
    <header class="djRefHero djHero">
      <div class="djHeroBackdrop" aria-hidden="true"><span class="djHeroRobot"></span><span class="djHeroScreens"></span></div>
      <div class="djCoreSlot" data-dj-core aria-label="Núcleo visual do Jarvis"></div>
      <div class="djHeroCopy"><span class="djEyebrow">GOLDEN JARVIS · DESKTOP</span><h1>Jarvis</h1><h2>Seu assistente pessoal de IA</h2><p>Análise de mercado, estratégias, programação, automações e muito mais.</p><small data-dj-connection>Verificando conexão com o Gateway…</small><small data-dj-voice-detail>Estado de voz não consultado.</small></div>
      <div class="djHeroActions"><span class="djHeroState djHeroPill djGeminiPill" data-dj-state>● GEMINI LIVE</span><span class="djHeroPill" data-dj-connection-short>● ONLINE</span><button type="button" class="djButton djProfileButton" data-dj-settings-toggle aria-label="Abrir perfil e configurações" aria-expanded="false">Jarvis⌄</button><button type="button" class="djIconButton" data-dj-settings-toggle aria-label="Abrir configurações" aria-expanded="false">⚙</button><button type="button" class="djButton djPrimary" data-dj-listen>OUVIR</button><button type="button" class="djButton" data-dj-stop>PARAR</button></div>
    </header>
    <div class="djModeCards" role="tablist" aria-label="Modos do Jarvis">
      <button type="button" class="djModeCard is-active" data-dj-mode-card data-mode="chat" role="tab" aria-selected="true"><span class="djModeIcon djModeIconChat">${MODE_ICONS.chat}</span><span><b>Chat</b><small>Converse comigo</small></span></button>
      <button type="button" class="djModeCard" data-dj-mode-card data-mode="images" role="tab" aria-selected="false"><span class="djModeIcon">${MODE_ICONS.images}</span><span><b>Imagens</b><small>Criar e editar</small></span></button>
      <button type="button" class="djModeCard" data-dj-mode-card data-mode="codex" role="tab" aria-selected="false"><span class="djModeIcon djModeIconCode">${MODE_ICONS.codex}</span><span><b>Codex</b><small>Análise de código</small></span></button>
      <button type="button" class="djModeCard" data-dj-mode-card data-mode="web" role="tab" aria-selected="false"><span class="djModeIcon djModeIconWeb">${MODE_ICONS.web}</span><span><b>Web</b><small>Pesquisar na internet</small></span></button>
      <button type="button" class="djModeCard" data-dj-mode-card data-mode="automation" role="tab" aria-selected="false"><span class="djModeIcon">${MODE_ICONS.automation}</span><span><b>Automação</b><small>Executar tarefas</small></span></button>
      <button type="button" class="djModeCard" data-dj-mode-card data-mode="files" role="tab" aria-selected="false"><span class="djModeIcon">${MODE_ICONS.files}</span><span><b>Arquivos</b><small>Analisar documentos</small></span></button>
    </div>
    <div class="djStatusGrid" data-dj-status-grid></div>
    <div class="djReferenceWorkspace djExperienceGrid">
      <aside class="djConversations djPanel" aria-label="Conversas"><div class="djConversationHead"><div><span class="djEyebrow">WORKSPACE</span><h2>Conversas</h2></div><button type="button" class="djButton djPrimary" data-dj-new-conversation>＋ Nova conversa</button></div><div class="djConversationList" data-dj-conversation-list></div></aside>
      <main class="djPanel djChatPanel">
        <div class="djPanelHead"><div><span class="djEyebrow">CONVERSA ATUAL</span><h2>Fale naturalmente com o Jarvis</h2><p class="djPanelSubhead" data-dj-chat-state>ONLINE</p></div><div class="djChatTools"><span class="djLiveTag" data-dj-voice-state>UNKNOWN</span><button type="button" class="djMini" data-dj-clear>LIMPAR</button></div></div>
        <div class="djReferenceQuickActions" aria-label="Ações rápidas"><button type="button" data-dj-quick-prompt="Crie uma imagem de ">▧ Criar imagem</button><button type="button" data-dj-quick-prompt="Use o Codex para analisar ">&lt;/&gt; Analisar código</button><button type="button" data-dj-quick-prompt="Pesquise na internet sobre ">◎ Pesquisar na web</button><button type="button" data-dj-quick-prompt="Execute uma tarefa: ">▶ Executar tarefa</button></div>
        <div class="djArtifactActions" data-dj-artifact-actions aria-label="Ações de imagem"><button type="button" data-dj-quick-prompt="Crie uma variação da última imagem gerada">⤨ Criar variações</button><button type="button" data-dj-quick-prompt="Edite a última imagem gerada: ">✎ Editar imagem</button><button type="button" data-dj-quick-prompt="Analise a última imagem gerada">⌕ Analisar esta imagem</button><button type="button" data-dj-quick-prompt="Use a última imagem gerada no projeto atual">▣ Usar no projeto</button></div>
        <div class="djConversationSlot" data-dj-slot="chat"></div>
        <div class="djThinkingSlot" data-dj-slot="thinking"></div>
        <div class="djQuickSlot" data-dj-slot="quick"></div>
      </main>
    </div>
    <div class="djControlBar" aria-label="Preferências da conversa"><div class="djControlGroup"><span>Modelos de IA</span><div class="djChipRow"><button type="button" class="djChip is-active" data-dj-model="gemini_live">Gemini Live</button><button type="button" class="djChip" data-dj-model="chatgpt">ChatGPT</button><button type="button" class="djChip" data-dj-model="codex">Codex</button><button type="button" class="djChip" data-dj-model="flux">FLUX (Cloudflare)</button><button type="button" class="djChip" data-dj-model="stable_diffusion">Stable Diffusion</button></div></div><div class="djControlGroup"><span>Estilo de resposta</span><div class="djChipRow"><button type="button" class="djChip is-active" data-dj-style="direto">Direto</button><button type="button" class="djChip" data-dj-style="analitico">Analítico</button><button type="button" class="djChip" data-dj-style="criativo">Criativo</button><button type="button" class="djChip" data-dj-style="tecnico">Técnico</button></div></div><div class="djControlGroup"><span>Modo de trabalho</span><div class="djChipRow"><button type="button" class="djChip djGold is-active" data-dj-workmode="conversa">Conversa</button><button type="button" class="djChip" data-dj-workmode="projeto">Projeto</button><button type="button" class="djChip" data-dj-workmode="automacao">Automação</button><button type="button" class="djChip" data-dj-workmode="analise">Análise</button></div></div><button type="button" class="djControlSettings" data-dj-settings-toggle aria-label="Abrir configurações" aria-expanded="false">☷</button></div>
    <div class="djFooterComposer"><div class="djComposerTools" data-dj-slot="command-tools"></div><div class="djInputSlot" data-dj-slot="command"></div></div>
    <aside class="djSettingsDrawer" data-dj-settings-drawer hidden aria-label="Configurações do Jarvis">
      <div class="djSettingsHead"><div><span class="djEyebrow">CONFIGURAÇÕES</span><h2>Voz, personalidade e permissões</h2></div><button type="button" class="djIconButton" data-dj-settings-toggle aria-label="Fechar configurações">×</button></div>
      <section class="djSettingsSection"><div class="djPanelHead"><div><span class="djEyebrow">VOZ E JEITO</span><h3>Presença do Jarvis</h3></div><span class="djLiveTag" data-dj-voice-state>UNKNOWN</span></div><label class="djField"><span>MODO</span><select data-dj-mode><option value="gemini_live">Gemini Live · indisponível</option></select></label><label class="djField"><span>VOZ INDEPENDENTE</span><select data-dj-voice></select></label><div class="djActions"><button type="button" class="djButton" data-dj-gemini-test>TESTAR VOZ GEMINI</button><button type="button" class="djButton" data-dj-gemini-preview-stop disabled>PARAR TESTE</button><button type="button" class="djButton" data-dj-gemini-setup>DIAGNÓSTICO SETUP</button><button type="button" class="djButton djPrimary" data-dj-gemini-start>INICIAR GEMINI LIVE</button><button type="button" class="djButton" data-dj-gemini-stop>ENCERRAR GEMINI LIVE</button></div><p class="djHint" data-dj-gemini-preview-status>Prévia Gemini requer sessão autorizada.</p><div class="djPersonaGrid" data-dj-personas role="radiogroup" aria-label="Personalidades do Jarvis"></div></section>
      <section class="djSettingsSection"><div class="djPanelHead"><div><span class="djEyebrow">MICROFONE</span><h3>Escuta e calibração</h3></div><span class="djLiveTag" data-dj-mic-state>UNKNOWN</span></div><label class="djField"><span>ENDPOINT ESTÁVEL</span><select data-dj-mic><option value="">Consultar dispositivos…</option></select></label><div class="djActions"><button type="button" class="djButton" data-dj-mic-refresh>ATUALIZAR</button><button type="button" class="djButton" data-dj-mic-probe>TESTAR</button><button type="button" class="djButton" data-dj-mic-calibrate>CALIBRAR</button></div><p class="djHint" data-dj-mic-detail>Sem diagnóstico realizado.</p></section>
      <details class="djSettingsSection djDisclosure"><summary><span><span class="djEyebrow">COMPUTER USE</span><b>Missão sob controle</b></span><span class="djLiveTag" data-dj-esc>ESC UNKNOWN</span></summary><div class="djDisclosureBody"><label class="djField"><span>ID DA TAREFA</span><input data-dj-task maxlength="120" placeholder="Opcional"></label><div class="djActions"><button type="button" class="djButton" data-dj-task-refresh>ATUALIZAR</button><button type="button" class="djButton" data-dj-task-pause>PAUSAR</button><button type="button" class="djButton" data-dj-task-resume>RETOMAR</button><button type="button" class="djButton djDanger" data-dj-task-cancel>CANCELAR</button></div><pre class="djReadout" data-dj-task-detail>Estado não consultado.</pre></div></details>
      <details class="djSettingsSection djDisclosure"><summary><span><span class="djEyebrow">SEGURANÇA E BRIDGES</span><b>Estados reais dos serviços</b></span><span class="djLiveTag">LOCAL</span></summary><div class="djDisclosureBody"><div class="djStatusList"><div><span>COFRE DPAPI</span><b data-dj-value="vault">UNKNOWN</b></div><div><span>WHATSAPP</span><b data-dj-value="whatsapp">PENDING_CONFIGURATION</b></div><div><span>CONFIRMAÇÕES</span><b data-dj-value="approvals">NÃO CONSULTADO</b></div><div><span>IMAGENS / ARQUIVOS</span><b data-dj-value="images">NÃO CONSULTADO</b></div></div><div class="djLatency"><div><span>CAPTURA / VAD</span><b data-dj-value="capture">—</b></div><div><span>STT / MODELO / TTS</span><b data-dj-value="pipeline">—</b></div><div><span>PRIMEIRO ÁUDIO</span><b data-dj-value="first-audio">—</b></div></div><p class="djHint" data-dj-image-detail>Análise visual local e anexos usam os serviços canônicos. Geração/edição de imagens não configurada.</p></div></details>
    </aside>
    <aside class="djRail" hidden aria-hidden="true"></aside>`;

  // The full voice/microphone rail is now available from the centralized
  // Segurança / Configuração route. Keep this canonical rail mounted as a
  // hidden command surface so existing handlers and VoiceService ownership are
  // reused without duplicating controls or creating another voice service.
  const rail = $(".djRail", surface);
  if (rail) {
    rail.hidden = true;
    surface.classList.add("djSettingsCentralized");
  }

  const statusGrid = $("[data-dj-status-grid]", surface);
  addStatus(statusGrid, "VOZ", "voice", "LOCAL · UNKNOWN");
  addStatus(statusGrid, "PERSONALIDADE", "persona", "EQUILIBRADO");
  addStatus(statusGrid, "MICROFONE", "mic", "UNKNOWN");
  addStatus(statusGrid, "COMPUTER USE", "computer", "ESC UNKNOWN");
  addStatus(statusGrid, "WHATSAPP", "whatsapp", "PENDING_CONFIGURATION");

  const core = document.querySelector("#orbWrap");
  if (core) $("[data-dj-core]", surface).append(core);
  // Keep the canonical slot containers attached: golden.js relayout() uses
  // these exact nodes whenever tabs/state change, so no shared widget is lost.
  $("[data-dj-slot=chat]", surface).append(chatSlot);
  if (quick) $("[data-dj-slot=quick]", surface).append(quick);
  $("[data-dj-slot=command]", surface).append(inputSlot);
  const commandTools = commandCard.querySelector(".gCmdBar");
  if (commandTools) $("[data-dj-slot=command-tools]", surface).append(commandTools);
  band.hidden = true;
  view.querySelector(".jarvisExperienceStrip")?.setAttribute("hidden", "true");
  view.querySelector("#gPills")?.setAttribute("hidden", "true");
  view.prepend(surface);
  return surface;
}

function fillMicrophones(surface, data, state, voice = {}) {
  const select = $("[data-dj-mic]", surface);
  if (!select) return;
  if (!data?.ok) {
    select.innerHTML = `<option value="">Microfone indisponível</option>`;
    select.value = "";
    return;
  }
  const selected = voice?.microphone?.selected_id || state.settings.microphoneId || "";
  select.innerHTML = `<option value="">Selecione um microfone</option>` + (data.microphones || []).map((mic) => `<option value="${esc(mic.stable_id)}">${esc(mic.name)} · ${esc(mic.host_api)}</option>`).join("");
  select.value = selected;
  if (selected && select.value === selected) state.settings.microphoneId = selected;
  $("[data-dj-mic-state]", surface).textContent = `${data.microphones?.length || 0} ENDPOINT(S)`;
}

function fillVoices(surface, state) {
  const select = $("[data-dj-voice]", surface);
  if (!select) return;
  select.innerHTML = GEMINI_VOICES.map(([id, desc]) => `<option value="${id}">${id} · ${desc}</option>`).join("");
  select.value = state.settings.geminiVoice || "Charon";
}

function renderPersonas(surface, state) {
  const grid = $("[data-dj-personas]", surface);
  if (!grid) return;
  grid.innerHTML = PERSONAS.map(([id, name, desc]) => `<button type="button" data-dj-persona="${id}" aria-pressed="${state.settings.persona === id}"><b>${name}</b><span>${desc}</span></button>`).join("");
}

const REFERENCE_MODE_PROMPTS = {
  chat: "",
  images: "Crie uma imagem de ",
  codex: "Use o Codex para ",
  web: "Pesquise na internet sobre ",
  automation: "Execute uma tarefa: ",
  files: "Analise o arquivo ",
};

function referenceInput(surface, value = null) {
  const input = document.querySelector("#cmdInput");
  if (!input) return null;
  if (value !== null) {
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  input.focus();
  return input;
}

function referenceSubmit(prompt) {
  const text = String(prompt || "").trim();
  if (!text) return false;
  if (typeof window.jarvis?.submitCommand === "function") {
    window.jarvis.submitCommand(text, "texto");
    return true;
  }
  const input = referenceInput(document.querySelector(".desktopJarvisExperience"));
  if (!input) return false;
  input.value = text;
  input.form?.requestSubmit?.();
  return true;
}

function renderReferenceConversations(surface, state) {
  const list = $("[data-dj-conversation-list]", surface);
  if (!list) return;
  const conversations = (Array.isArray(state.referenceConversations) ? state.referenceConversations : [])
    .filter((item) => item && item.archived !== false);
  if (!conversations.length) {
    list.innerHTML = `<div class="djConversationEmpty"><span class="djConversationEmptyIcon">◌</span><b>Nenhuma conversa anterior</b><small>As conversas concluídas aparecerão aqui.</small></div>`;
    return;
  }
  list.innerHTML = conversations.map((item) => `<button type="button" class="djConversationItem" data-dj-conversation="${esc(item.id)}" title="Abrir conversa antiga"><span class="djConversationIcon">▧</span><span><b>${esc(item.title || "Conversa")}</b><small>${esc(item.preview || "Sem mensagens")}</small></span><time class="djConversationTime">${esc(item.time || "—")}</time></button>`).join("");
}

function setReferenceSelection(surface, selector, attribute, value) {
  surface.querySelectorAll(selector).forEach((node) => {
    const active = node.dataset[attribute] === value;
    node.classList.toggle("is-active", active);
    if (node.hasAttribute("aria-selected")) node.setAttribute("aria-selected", String(active));
  });
}

function setupReferenceControls(surface, state) {
  const savedModel = state.settings.model || "gemini_live";
  const savedStyle = state.settings.responseStyle || "direto";
  const savedWorkMode = state.settings.workMode || "conversa";
  setReferenceSelection(surface, "[data-dj-model]", "djModel", savedModel);
  setReferenceSelection(surface, "[data-dj-style]", "djStyle", savedStyle);
  setReferenceSelection(surface, "[data-dj-workmode]", "djWorkmode", savedWorkMode);
  renderReferenceConversations(surface, state);

  // Keep image-only actions hidden until the canonical conversation receives
  // an actual generated image artifact.
  const conversation = document.querySelector("#conversation");
  const artifactActions = $("[data-dj-artifact-actions]", surface);
  const syncArtifactActions = () => artifactActions?.classList.toggle("is-visible", Boolean(conversation?.querySelector("img")));
  if (conversation && artifactActions && window.MutationObserver) {
    new MutationObserver(syncArtifactActions).observe(conversation, { childList: true, subtree: true });
    syncArtifactActions();
  }

  surface.querySelectorAll("[data-dj-mode-card]").forEach((button) => button.addEventListener("click", () => {
    const mode = button.dataset.mode || "chat";
    setReferenceSelection(surface, "[data-dj-mode-card]", "mode", mode);
    const template = REFERENCE_MODE_PROMPTS[mode] || "";
    referenceInput(surface, template);
    const agent = document.querySelector("#gAgentSel");
    if (agent && mode === "codex") { agent.value = "backend"; agent.dispatchEvent(new Event("change", { bubbles: true })); }
    if (agent && mode === "web") { agent.value = "auto"; agent.dispatchEvent(new Event("change", { bubbles: true })); }
  }));
  surface.querySelectorAll("[data-dj-quick-prompt]").forEach((button) => button.addEventListener("click", () => {
    referenceInput(surface, button.dataset.djQuickPrompt || "");
  }));
  surface.querySelectorAll("[data-dj-model]").forEach((button) => button.addEventListener("click", () => {
    const model = button.dataset.djModel || "gemini_live";
    state.settings.model = model;
    saveSettings(state.settings);
    setReferenceSelection(surface, "[data-dj-model]", "djModel", model);
    const agent = document.querySelector("#gAgentSel");
    if (agent) {
      const route = model === "codex" ? "backend" : model === "chatgpt" || model === "gemini_live" ? "ia" : "auto";
      agent.value = route;
      agent.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (model === "gemini_live") {
      const mode = $("[data-dj-mode]", surface);
      if (mode && mode.value !== "gemini_live") { mode.value = "gemini_live"; mode.dispatchEvent(new Event("change", { bubbles: true })); }
    }
    const modeMap = { flux: "images", stable_diffusion: "images", codex: "codex", gemini_live: "chat", chatgpt: "chat" };
    const card = $(
      `[data-dj-mode-card][data-mode="${modeMap[model] || "chat"}"]`, surface,
    );
    card?.click();
  }));
  surface.querySelectorAll("[data-dj-style]").forEach((button) => button.addEventListener("click", () => {
    state.settings.responseStyle = button.dataset.djStyle || "direto";
    saveSettings(state.settings);
    setReferenceSelection(surface, "[data-dj-style]", "djStyle", state.settings.responseStyle);
  }));
  surface.querySelectorAll("[data-dj-workmode]").forEach((button) => button.addEventListener("click", () => {
    state.settings.workMode = button.dataset.djWorkmode || "conversa";
    saveSettings(state.settings);
    setReferenceSelection(surface, "[data-dj-workmode]", "djWorkmode", state.settings.workMode);
  }));
  surface.querySelectorAll("[data-dj-settings-toggle]").forEach((button) => button.addEventListener("click", () => {
    const drawer = $("[data-dj-settings-drawer]", surface);
    if (!drawer) return;
    const open = drawer.hidden;
    drawer.hidden = !open;
    surface.querySelectorAll("[data-dj-settings-toggle]").forEach((toggle) => toggle.setAttribute("aria-expanded", String(open)));
  }));
  $("[data-dj-conversation-list]", surface)?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-dj-conversation]");
    if (!button) return;
    const item = (state.referenceConversations || []).find((entry) => entry.id === button.dataset.djConversation);
    if (!item) return;
    let messages = Array.isArray(item.messages) ? item.messages : [];
    if (!messages.length && item.durable) {
      const post = endpoint();
      const result = post
        ? await post("/api/jarvis/conversations/get", { conversation_id: item.id, limit: 120 }).catch(() => null)
        : null;
      const turns = Array.isArray(result?.turns) ? result.turns : [];
      messages = turns.map((turn) => ({
        role: String(turn.role || "assistant") === "user" ? "user" : "jarvis",
        text: String(turn.content || "").trim(),
      })).filter((turn) => turn.text);
      item.messages = messages;
    }
    if (!messages.length || typeof window.jarvis?.addMessage !== "function") return;
    document.querySelector("#gClearBtn")?.click();
    state._restoringConversation = true;
    state.referenceCurrent = { ...item, messages: [] };
    for (const message of messages) window.jarvis.addMessage(message.role, message.text);
    state.referenceCurrent.messages = messages;
    state._restoringConversation = false;
  });
  $("[data-dj-new-conversation]", surface)?.addEventListener("click", () => {
    archiveReferenceConversation(state);
    document.querySelector("#gClearBtn")?.click();
    state.referenceCurrent = newReferenceConversation();
    renderReferenceConversations(surface, state);
    referenceInput(surface, "");
  });
  window.addEventListener("jarvis:message-added", (event) => {
    if (state._restoringConversation) return;
    const text = String(event.detail?.text || "").trim();
    if (!text) return;
    const current = state.referenceCurrent || (state.referenceCurrent = newReferenceConversation());
    const role = String(event.detail?.role || "jarvis");
    current.messages = Array.isArray(current.messages) ? current.messages : [];
    current.messages.push({ role, text });
    if (role === "user" && current.title === "Conversa atual") current.title = text.slice(0, 52);
    current.preview = text.slice(0, 75);
    current.time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  });
  window.addEventListener("beforeunload", () => archiveReferenceConversation(state));
}

function syncCoreState(surface) {
  const app = document.querySelector("#app");
  const value = String(app?.dataset.state || "idle").toLowerCase();
  surface.dataset.voiceState = value;
  const core = $("[data-dj-core]", surface);
  if (core) core.dataset.state = value;
  const labels = { idle: "LOCAL · OCIOSO", listening: "LOCAL · ESCUTANDO", thinking: "LOCAL · PROCESSANDO", executing: "LOCAL · PROCESSANDO", speaking: "LOCAL · RESPONDENDO", interrupted: "LOCAL · INTERROMPIDO", alert: "LOCAL · ERRO", error: "LOCAL · ERRO" };
  const stateNode = $("[data-dj-state]", surface);
  if (stateNode && !stateNode.dataset.providerState) stateNode.textContent = labels[value] || "LOCAL · AGUARDANDO";
}

async function configureProfile(surface, state, payload, options = {}) {
  const post = endpoint();
  if (!post) return { ok: false, error: "Gateway aguardando autenticação." };
  // Profile changes are session-scoped while Gemini Live is active. Send the
  // existing grant on the first attempt; otherwise the route perimeter rejects
  // the request and the old implementation only retried when the token was
  // empty, making voice/personality changes appear to do nothing.
  let requestPayload = options.authorize
    ? voiceAuthorizationPayload(state, payload)
    : payload;
  let result = await post("/api/jarvis/voice-service/profile", requestPayload).catch((error) => ({ ok: false, error: error?.message || String(error) }));
  const code = String(result?.error || result?.error_code || "");
  const requiresGrant = !result?.ok && (result?.authorization_required === true
    || code === "VOICE_AUTHORIZATION_REQUIRED");
  if (requiresGrant && options.authorize && !state.geminiAuthorizationToken) {
    const authorization = await post("/api/jarvis/voice-service/gemini/authorize", { confirm: true })
      .catch((error) => ({ ok: false, error: error?.message || String(error) }));
    if (authorization?.authorization_token) {
      state.geminiAuthorizationToken = authorization.authorization_token;
      window.__JARVIS_GEMINI_AUTH_TOKEN__ = state.geminiAuthorizationToken;
      requestPayload = voiceAuthorizationPayload(state, payload);
      result = await post(
        "/api/jarvis/voice-service/profile",
        requestPayload,
      ).catch((error) => ({ ok: false, error: error?.message || String(error) }));
    }
  }
  if (result?.ok === false) {
    const detail = $("[data-dj-voice-detail]", surface);
    if (detail) detail.textContent = `Preferência não aplicada: ${String(result.error || result.error_code || "erro").slice(0, 120)}`;
  }
  return result || { ok: false, error: "Resposta vazia do VoiceService." };
}

async function reconnectGeminiLive(surface, state) {
  const post = endpoint();
  const detail = $("[data-dj-voice-detail]", surface);
  const preview = $("[data-dj-gemini-preview-status]", surface);
  if (!post) {
    return { ok: false, error: "GATEWAY_UNAVAILABLE" };
  }
  // Grants are intentionally short-lived. A user-initiated profile change
  // may obtain a fresh, equally scoped grant before reconnecting the same
  // canonical VoiceService session.
  if (!state.geminiAuthorizationToken) {
    const authorization = await post("/api/jarvis/voice-service/gemini/authorize", { confirm: true })
      .catch((error) => ({ ok: false, error: error?.message || String(error) }));
    if (!authorization?.authorization_token) {
      return { ok: false, error: String(authorization?.error || "VOICE_AUTHORIZATION_REQUIRED") };
    }
    state.geminiAuthorizationToken = authorization.authorization_token;
    window.__JARVIS_GEMINI_AUTH_TOKEN__ = state.geminiAuthorizationToken;
  }
  if (detail) detail.textContent = "Aplicando voz e personalidade na sessão Gemini Live…";
  if (preview) preview.textContent = "Reconectando sessão Gemini Live…";
  const result = await post(
    "/api/jarvis/voice-service/gemini/reconnect",
    voiceAuthorizationPayload(state),
  ).catch((error) => ({ ok: false, error: error?.message || String(error) }));
  if (!result?.ok) {
    const code = String(result?.error || result?.error_code || result?.detail || "GEMINI_LIVE_RECONNECT_FAILED");
    state.geminiFailure = { code, detail: "" };
    if (detail) detail.textContent = `Perfil não aplicado: ${code}`;
    if (preview) preview.textContent = `Falha ao aplicar perfil: ${code}`;
  } else {
    state.geminiFailure = null;
    if (detail) detail.textContent = "Voz e personalidade aplicadas à sessão Gemini Live.";
    if (preview) preview.textContent = "Gemini Live conectado. Microfone mudo — clique no botão para falar.";
  }
  await refreshStatus(surface, state);
  return result || { ok: false, error: "Resposta vazia do VoiceService." };
}

async function refreshStatus(surface, state) {
  const post = endpoint();
  if (!post) { $("[data-dj-connection]", surface).textContent = "Gateway aguardando autenticação."; setValue(surface, "connection", "DISCONNECTED", "error"); return; }
  try {
    const [voice, mics, whatsapp, vault, approvals, vision, audio] = await Promise.all([
      post("/api/jarvis/voice-service/status", {}), post("/api/jarvis/voice-service/microphones", voiceAuthorizationPayload(state)),
      post("/api/jarvis/whatsapp/status", {}), post("/api/jarvis/vault/status", {}), post("/api/jarvis/approvals/list", {}),
      post("/api/jarvis/vision/status", {}),
      state.geminiAuthorizationToken
        ? post("/api/jarvis/voice-service/gemini/audio/status", voiceAuthorizationPayload(state))
        : Promise.resolve(null),
    ]);
    state.voice = voice || {};
    state.geminiAudio = audio?.audio || null;
    publishGeminiAudioState(state);
    syncGeminiAudioPolling(surface, state);
    window.__JARVIS_VOICE_PROFILE_BLOCKED__ = String(voice?.voice_disabled_reason || voice?.error || "").toUpperCase() === "VOICE_DISABLED_BY_PROFILE";
    const features = voice?.voice_features || {};
    const liveReady = features.gemini_live === true || voice?.gemini_live_ready === true;
    const liveConnected = voice?.conversation_profile?.gemini_live_connected === true;
    const mode = liveConnected ? "GEMINI LIVE" : "GEMINI LIVE · AGUARDANDO";
    if (liveConnected && state.geminiAuthorizationToken) {
      scheduleGeminiGrantRenewal(surface, state, 120);
    } else if (!state.geminiAuthorizationToken) {
      clearGeminiGrantRenewal(state);
    }
    const resolved = voiceState(voice, state);
    setValue(surface, "voice", resolved.label, resolved.state);
    setValue(surface, "persona", String(voice?.conversation_profile?.personality_label || state.settings.persona || "equilibrado").toUpperCase());
    const mic = microphoneState(mics, state, voice);
    setValue(surface, "mic", mic.label, mic.state);
    setValue(surface, "computer", voice?.computer_use_esc === true ? "ESC ENABLED" : "ESC DISABLED");
    setValue(surface, "connection", "AUTHENTICATED", "ok");
    setValue(surface, "whatsapp", whatsapp?.state || "PENDING_CONFIGURATION");
    const count = Array.isArray(approvals?.approvals) ? approvals.approvals.length : 0;
    setValue(surface, "vault", vault?.state || "ERROR");
    setValue(surface, "approvals", count ? `${count} PENDENTE(S)` : "NENHUMA PENDENTE");
    const imageReady = vision?.ok === true && vision?.vision_available === true;
    setValue(surface, "images", imageReady ? "ANÁLISE LOCAL · READY" : "GERAÇÃO INDISPONÍVEL", imageReady ? "ok" : "warn");
    $("[data-dj-connection]", surface).textContent = `Serviços locais conectados · ${resolved.detail}`;
    const connectionShort = $("[data-dj-connection-short]", surface);
    if (connectionShort) connectionShort.textContent = resolved.label.includes("CONECTADO") ? "● ONLINE" : resolved.label.includes("ERRO") ? "● ATENÇÃO" : "● ONLINE";
    $("[data-dj-voice-detail]", surface).textContent = resolved.detail;
    setSettingsGeminiStatus(resolved.detail);
    const settingsVoiceStatus = document.querySelector("#geminiVoiceStatus");
    if (settingsVoiceStatus) settingsVoiceStatus.textContent = resolved.detail;
    $("[data-dj-mic-state]", surface).textContent = mic.label;
    const audioMetrics = audio?.audio?.metrics;
    const outputDiagnostics = audio?.audio?.output || {};
    const previewButton = $("[data-dj-gemini-test]", surface);
    const previewStop = $("[data-dj-gemini-preview-stop]", surface);
    const previewStatus = $("[data-dj-gemini-preview-status]", surface);
    const previewActive = state.geminiAudio?.preview_active === true;
    if (previewButton) {
      previewButton.disabled = previewActive;
      previewButton.title = previewActive ? "Prévia em andamento; use PARAR TESTE para interromper." : "";
    }
    if (previewStop) previewStop.disabled = !previewActive;
    if (previewActive && previewStatus?.textContent.includes("GEMINI_PREVIEW_IN_PROGRESS")) {
      previewStatus.textContent = "Prévia Gemini já está em andamento; use PARAR TESTE para interromper.";
    }
    const audioError = String(audio?.audio?.last_error?.error || "").trim();
    $("[data-dj-mic-detail]", surface).textContent = audio?.ok && audio?.audio?.active
      ? `${mic.detail} · frames enviados: ${audioMetrics?.frames_sent ?? 0} · áudio recebido: ${audioMetrics?.audio_chunks_received ?? 0}`
      : audioError
        ? `${mic.detail} · ${audioError.slice(0, 180)}`
        : mic.detail;
    const outputError = String(outputDiagnostics?.last_error || "").trim();
    if (previewStatus && state.geminiAudio?.preview_active === true) {
      if (outputError) previewStatus.textContent = `Saída Gemini falhou: ${outputError.slice(0, 180)}`;
      else if (Number(audioMetrics?.audio_chunks_received || 0) > 0 && outputDiagnostics?.active === true)
        previewStatus.textContent = "Áudio Gemini recebido e em reprodução…";
      else previewStatus.textContent = "Aguardando áudio Gemini…";
    }
    $("[data-dj-image-detail]", surface).textContent = imageReady
      ? `Análise visual local disponível (${vision.model || "modelo configurado"}). Geração/edição de imagens não está exposta por um provider Golden autorizado.`
      : "Análise visual local indisponível. Geração/edição de imagens não está configurada; nenhum sucesso é simulado.";
    $("[data-dj-voice-state]", surface).textContent = resolved.label;
    const heroState = $("[data-dj-state]", surface);
    if (heroState) { heroState.textContent = resolved.label; heroState.dataset.providerState = "true"; }
    $("[data-dj-chat-state]", surface).textContent = mode;
    $("[data-dj-esc]", surface).textContent = voice?.computer_use_esc === true ? "ESC ENABLED" : "ESC DISABLED";
    const modeSelect = $("[data-dj-mode]", surface);
    if (modeSelect) {
      // Keep the operator's explicit mode selection. The old code silently
      // changed it back to Local whenever the feature probe was temporarily
      // false, so the PTT button called the local VoiceService path even
      // during a connected Gemini session.
      state.settings.voiceMode = "gemini_live";
      modeSelect.value = "gemini_live";
      modeSelect.options[0].textContent = liveReady || liveConnected
        ? "Gemini Live · pronto para conectar" : "Gemini Live · indisponível no Core";
      modeSelect.options[0].disabled = false;
      window.__JARVIS_DESKTOP_VOICE_MODE__ = "gemini_live";
    }
    const timing = voice?.metrics || voice?.latency || {};
    setValue(surface, "capture", timing.capture_ms ?? timing.vad_ms ?? "não reportado");
    setValue(surface, "pipeline", [timing.stt_ms, timing.llm_ms, timing.tts_ms].filter((v) => v != null).join(" / ") || "não reportado");
    setValue(surface, "first-audio", timing.first_audio_ms ?? timing.ttfb_ms ?? "não reportado");
    fillMicrophones(surface, mics, state, voice); fillVoices(surface, state);
    await restoreSelectedMicrophone(surface, state, voice, mics);
  } catch (error) { setValue(surface, "connection", "ERROR", "error"); $("[data-dj-connection]", surface).textContent = `Falha ao consultar o Gateway: ${String(error?.message || error).slice(0, 100)}`; }
}

function publishGeminiAudioState(state) {
  // ``active`` also means that the output bridge is alive while the
  // push-to-talk microphone is muted. The button must reflect capture only.
  const active = state?.geminiAudio?.capture_active === true;
  window.__JARVIS_GEMINI_AUDIO_ACTIVE__ = active;
  window.dispatchEvent(new CustomEvent("jarvis:gemini-audio-state", {
    detail: { active, generation: state?.geminiAudio?.generation || 0 },
  }));
  const transcription = state?.geminiAudio?.transcription || {};
  const sequence = Number(transcription.sequence || 0);
  if (sequence > 0 && sequence !== Number(state._lastGeminiTranscriptSequence || 0)) {
    state._lastGeminiTranscriptSequence = sequence;
    window.dispatchEvent(new CustomEvent("jarvis:gemini-transcript", {
      detail: {
        input: String(transcription.input || "").trim(),
        output: String(transcription.output || "").trim(),
        sequence,
      },
    }));
  }
}

async function refreshGeminiAudioOnly(surface, state) {
  const post = endpoint();
  if (!post || !state.geminiAuthorizationToken) return;
  const result = await post(
    "/api/jarvis/voice-service/gemini/audio/status",
    voiceAuthorizationPayload(state),
  ).catch(() => null);
  if (result?.ok) {
    state.geminiAudio = result.audio || null;
    publishGeminiAudioState(state);
    syncGeminiAudioPolling(surface, state);
  }
}

function syncGeminiAudioPolling(surface, state) {
  const active = state?.geminiAudio?.capture_active === true || state?.geminiAudio?.active === true;
  const bridgeActive = state?.geminiAudio?.bridge_active === true;
  if ((active || bridgeActive || state?.geminiAudio?.preview_active === true) && !state._geminiAudioPollTimer) {
    state._geminiAudioPollTimer = window.setInterval(
      () => void refreshGeminiAudioOnly(surface, state), 700,
    );
  } else if (!active && !bridgeActive && state?.geminiAudio?.preview_active !== true
             && state._geminiAudioPollTimer) {
    window.clearInterval(state._geminiAudioPollTimer);
    state._geminiAudioPollTimer = 0;
  }
}

async function toggleGeminiAudio(surface, state) {
  if (state._geminiAudioToggleBusy) return { ok: false, error: "GEMINI_AUDIO_TOGGLE_IN_PROGRESS" };
  const post = endpoint();
  if (!post) return { ok: false, error: "GATEWAY_UNAVAILABLE" };
  if (!state.geminiAuthorizationToken) return { ok: false, error: "VOICE_AUTHORIZATION_REQUIRED" };
  state._geminiAudioToggleBusy = true;
  const currentlyActive = state.geminiAudio?.capture_active === true;
  const path = currentlyActive
    ? "/api/jarvis/voice-service/gemini/audio/capture/stop"
    : "/api/jarvis/voice-service/gemini/audio/capture/start";
  try {
    const result = await post(path, voiceAuthorizationPayload(state, currentlyActive
      ? {}
      : { endpoint_id: state.settings.microphoneId || "" }))
      .catch((error) => ({ ok: false, error: error?.message || String(error) }));
    if (!result?.ok) return result || { ok: false, error: "GEMINI_LIVE_AUDIO_TOGGLE_FAILED" };
    state.geminiAudio = result.audio || state.geminiAudio || null;
    // A web-research narration briefly suppresses the synthetic Live
    // transcription.  A real push-to-talk turn must always be visible in the
    // chat, so a fresh microphone press clears that narration-only window.
    if (state.geminiAudio?.capture_active === true) {
      window.__JARVIS_SUPPRESS_GEMINI_TRANSCRIPT_UNTIL__ = 0;
    }
    const status = $("[data-dj-gemini-preview-status]", surface);
    if (status) status.textContent = state.geminiAudio?.capture_active === true
      ? "Microfone Gemini ativo — fale agora."
      : "Turno encerrado — aguardando resposta Gemini…";
    publishGeminiAudioState(state);
    // Do not issue a second full status request here.  It can race the
    // capture stop/start response and overwrite the button with a stale
    // capture_active value.  The bounded audio poll refreshes diagnostics.
    return { ...result, audio: state.geminiAudio };
  } finally {
    state._geminiAudioToggleBusy = false;
  }
}

async function interruptGeminiAudio(surface, state) {
  const post = endpoint();
  if (!post) return { ok: false, error: "GATEWAY_UNAVAILABLE" };
  if (!state.geminiAuthorizationToken) {
    return { ok: false, error: "VOICE_AUTHORIZATION_REQUIRED" };
  }
  const payload = voiceAuthorizationPayload(state);
  // Stop capture first so an ESC press cannot leave a microphone turn open;
  // then cancel the output sink and the current Live generation.  Both calls
  // are cooperative and use the same scoped authorization grant.
  if (state.geminiAudio?.capture_active === true) {
    await post(
      "/api/jarvis/voice-service/gemini/audio/capture/stop",
      payload,
    ).catch(() => {});
  }
  const result = await post(
    "/api/jarvis/voice-service/gemini/audio/interrupt",
    payload,
  ).catch((error) => ({ ok: false, error: error?.message || String(error) }));
  if (result?.audio) state.geminiAudio = result.audio;
  const status = $("[data-dj-gemini-preview-status]", surface);
  if (status) status.textContent = result?.ok
    ? "Áudio Gemini interrompido; microfone mudo."
    : "Falha ao interromper áudio Gemini: " + String(result?.error || "GEMINI_LIVE_AUDIO_INTERRUPT_FAILED").slice(0, 160);
  publishGeminiAudioState(state);
  await refreshStatus(surface, state);
  return result || { ok: false, error: "GEMINI_LIVE_AUDIO_INTERRUPT_FAILED" };
}

async function sendGeminiText(surface, state, text) {
  const post = endpoint();
  const prompt = String(text || "").trim();
  if (!post) return { ok: false, error: "GATEWAY_UNAVAILABLE" };
  if (!state.geminiAuthorizationToken) return { ok: false, error: "VOICE_AUTHORIZATION_REQUIRED" };
  if (!prompt) return { ok: false, error: "GEMINI_LIVE_TEXT_REQUIRED" };
  const result = await post(
    "/api/jarvis/voice-service/gemini/text",
    voiceAuthorizationPayload(state, { text: prompt.slice(0, 2000) }),
  ).catch((error) => ({ ok: false, error: error?.message || String(error) }));
  const status = $("[data-dj-gemini-preview-status]", surface);
  if (status) status.textContent = result?.ok
    ? "Texto enviado ao Gemini Live — resposta em áudio."
    : "Falha ao enviar texto Gemini: " + String(result?.error || "GEMINI_LIVE_TEXT_FAILED").slice(0, 160);
  return result || { ok: false, error: "GEMINI_LIVE_TEXT_FAILED" };
}

async function taskStatus(surface) {
  const post = endpoint(); const id = $("[data-dj-task]", surface)?.value.trim(); const detail = $("[data-dj-task-detail]", surface);
  if (!post || !id) { if (detail) detail.textContent = "Informe um task_id para consultar a missão."; return; }
  try { const data = await post("/api/jarvis/tasks/get", { task_id: id }); detail.textContent = JSON.stringify(data?.task || data?.error || data, null, 2); } catch (error) { detail.textContent = String(error?.message || error); }
}

async function taskAction(surface, path) { const post = endpoint(); const id = $("[data-dj-task]", surface)?.value.trim(); if (!post || !id) return; await post(path, { task_id: id }).catch(() => {}); await taskStatus(surface); }

async function microphoneAction(surface, state, action) {
  const post = endpoint(); const id = $("[data-dj-mic]", surface)?.value || state.settings.microphoneId; const detail = $("[data-dj-mic-detail]", surface);
  if (!post || !id) { if (detail) detail.textContent = "Selecione um endpoint real."; return; }
  try {
    if (action === "select") {
      const result = await post("/api/jarvis/voice-service/microphone/select", voiceAuthorizationPayload(state, { endpoint_id: id }));
      if (result?.ok === false) throw new Error(result.error || result.error_code || "MICROPHONE_SELECT_FAILED");
      state.settings.microphoneId = id; saveSettings(state.settings);
      if (detail) detail.textContent = "Endpoint selecionado; captura ainda não foi testada.";
    }
    if (action === "probe" || action === "calibrate") {
      const sample = await post("/api/jarvis/voice-service/microphone/probe", voiceAuthorizationPayload(state, { endpoint_id: id }));
      if (!sample?.ok) throw new Error(sample?.error || sample?.error_code || "CAPTURE_UNAVAILABLE");
      if (action === "calibrate") {
        const level = Number(sample.rms || 0);
        if (!(level > 0)) throw new Error("NO_AUDIO_LEVEL");
        const calibration = await post("/api/jarvis/voice-service/microphone/calibrate", voiceAuthorizationPayload(state, { endpoint_id: id, kind: "noise", level }));
        if (calibration?.ok === false) throw new Error(calibration.error || calibration.error_code || "CALIBRATION_FAILED");
        detail.textContent = `calibrado · RMS: ${level} · confiança: ${calibration?.thresholds?.confidence ?? "—"}`;
      } else detail.textContent = `captura OK · blocos: ${sample.blocks || 0} · RMS: ${sample.rms || 0} · clipping: ${sample.clipping || 0}`;
    }
  } catch (error) { if (detail) detail.textContent = String(error?.message || error).slice(0, 120); }
}

async function restoreSelectedMicrophone(surface, state, voice, microphones) {
  const post = endpoint();
  const id = state.settings.microphoneId || "";
  if (!post || !id || !microphones?.ok || voice?.microphone?.selected_id === id) return;
  if (!(microphones.microphones || []).some((item) => item.stable_id === id)) return;
  const result = await post("/api/jarvis/voice-service/microphone/select", voiceAuthorizationPayload(state, { endpoint_id: id })).catch(() => null);
  if (result?.ok === false) {
    const detail = $("[data-dj-mic-detail]", surface);
    if (detail) detail.textContent = "Endpoint salvo não pôde ser reativado; selecione-o novamente.";
  }
}

async function autoConnectGeminiLive(surface, state) {
  if (state._autoConnectAttempted || state.settings.voiceMode !== "gemini_live") return;
  state._autoConnectAttempted = true;
  const voice = state.voice || {};
  const profile = voice.conversation_profile || {};
  if (profile.gemini_live_connected === true) {
    setSettingsGeminiStatus("Gemini Live já está conectado.");
    return;
  }
  const features = voice.voice_features || {};
  if (voice.gemini_live_ready !== true && features.gemini_live !== true) {
    setSettingsGeminiStatus("Gemini Live indisponível ou credencial não configurada.");
    return;
  }
  const start = $("[data-dj-gemini-start]", surface);
  if (!start) return;
  setSettingsGeminiStatus("Conectando Gemini Live automaticamente…");
  start.click();
}

export function mountDesktopJarvisExperience() {
  if (window.__JARVIS_DESKTOP__ !== true) return;
  if (!document.querySelector('link[data-desktop-jarvis-experience]')) { const stylesheet = document.createElement("link"); stylesheet.rel = "stylesheet"; stylesheet.href = "src/desktop-jarvis-experience.css?v=20261021-reference-interface-8"; stylesheet.dataset.desktopJarvisExperience = ""; document.head.append(stylesheet); }
  const surface = buildSurface(); if (!surface) return;
  const saved = storedSettings();
  const settings = { persona: "equilibrado", geminiVoice: "Charon", model: "gemini_live", responseStyle: "direto", workMode: "conversa", ...saved, voiceMode: "gemini_live" };
  if (!GEMINI_VOICES.some(([id]) => id === settings.geminiVoice)) settings.geminiVoice = "Charon";
  const state = { settings, voice: {}, referenceConversations: loadReferenceConversations(), referenceCurrent: newReferenceConversation(), geminiAudio: null, geminiAuthorizationToken: "", _geminiAudioToggleBusy: false, _geminiAudioPollTimer: 0, _lastGeminiTranscriptSequence: 0, _autoConnectAttempted: false, _restoringConversation: false }; window.__JARVIS_DESKTOP_VOICE_MODE__ = state.settings.voiceMode; renderPersonas(surface, state); syncSettingsMirror(state); setupReferenceControls(surface, state); void hydrateDurableConversations(surface, state); const post = endpoint();
  window.__JARVIS_GEMINI_AUDIO_TOGGLE__ = () => toggleGeminiAudio(surface, state);
  window.__JARVIS_GEMINI_AUDIO_INTERRUPT__ = () => interruptGeminiAudio(surface, state);
  window.__JARVIS_GEMINI_AUDIO_STATUS__ = () => state.geminiAudio || {};
  window.__JARVIS_GEMINI_SEND_TEXT__ = (text) => sendGeminiText(surface, state, text);
  window.__JARVIS_DESKTOP_CONTROL__ = {
    setMode(value) {
      const node = $("[data-dj-mode]", surface);
      if (!node) return false;
      node.value = "gemini_live";
      node.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    },
    setVoice(value) {
      const node = $("[data-dj-voice]", surface);
      if (!node) return false;
      node.value = String(value || "Charon");
      node.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    },
    setPersona(value) {
      const node = $(`[data-dj-persona="${String(value || "equilibrado").replace(/"/g, "")}"]`, surface);
      if (!node) return false;
      node.click();
      return true;
    },
    setup() { $("[data-dj-gemini-setup]", surface)?.click(); },
    start() { $("[data-dj-gemini-start]", surface)?.click(); },
    stop() { $("[data-dj-gemini-stop]", surface)?.click(); },
  };
  syncCoreState(surface);
  const app = document.querySelector("#app");
  if (app && window.MutationObserver) new MutationObserver(() => syncCoreState(surface)).observe(app, { attributes: true, attributeFilter: ["data-state"] });
  $("[data-dj-mode]", surface)?.addEventListener("change", async (event) => { state.settings.voiceMode = "gemini_live"; event.target.value = "gemini_live"; window.__JARVIS_DESKTOP_VOICE_MODE__ = "gemini_live"; saveSettings(state.settings); await configureProfile(surface, state, { mode: "gemini_live" }, { authorize: true }); await refreshStatus(surface, state); });
  $("[data-dj-voice]", surface)?.addEventListener("change", async (event) => {
    const previousVoice = state.settings.geminiVoice;
    const requestedVoice = event.target.value;
    const configured = await configureProfile(surface, state, { voice: requestedVoice }, { authorize: true });
    if (!configured?.ok) {
      event.target.value = previousVoice;
      const detail = $("[data-dj-voice-detail]", surface);
      if (detail) detail.textContent = `Voz não aplicada: ${String(configured?.error || "GEMINI_VOICE_UNSUPPORTED").slice(0, 120)}`;
    } else {
      state.settings.geminiVoice = requestedVoice;
      saveSettings(state.settings);
      state.geminiFailure = null;
      if (configured.profile_change_requires_reconnect) await reconnectGeminiLive(surface, state);
    }
    await refreshStatus(surface, state);
  });
  $("[data-dj-personas]", surface)?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-dj-persona]");
    if (!button) return;
    const previousPersona = state.settings.persona;
    const requestedPersona = button.dataset.djPersona;
    const configured = await configureProfile(surface, state, { personality: requestedPersona }, { authorize: true });
    if (configured?.ok) {
      state.settings.persona = requestedPersona;
      saveSettings(state.settings);
      renderPersonas(surface, state);
      if (configured.profile_change_requires_reconnect) await reconnectGeminiLive(surface, state);
    } else {
      state.settings.persona = previousPersona;
      renderPersonas(surface, state);
    }
    await refreshStatus(surface, state);
  });
  $("[data-dj-mic]", surface)?.addEventListener("change", async (event) => { state.settings.microphoneId = event.target.value; saveSettings(state.settings); await microphoneAction(surface, state, "select"); await refreshStatus(surface, state); });
  $("[data-dj-voice-test]", surface)?.addEventListener("click", () => document.querySelector("#testVoiceBtn")?.click());
  $("[data-dj-gemini-test]", surface)?.addEventListener("click", async () => {
    const post = endpoint(); const status = $("[data-dj-gemini-preview-status]", surface); const stop = $("[data-dj-gemini-preview-stop]", surface);
    if (!post || !state.geminiAuthorizationToken) { if (status) status.textContent = "Conecte o Gemini Live por INICIAR GEMINI LIVE; nenhuma conexão foi aberta."; return; }
    if (state.geminiAudio?.preview_active === true) {
      if (status) status.textContent = "Prévia Gemini já está em andamento; use PARAR TESTE para interromper.";
      return;
    }
    if (status) status.textContent = "Carregando áudio Gemini…"; if (stop) stop.disabled = false;
    const result = await post("/api/jarvis/voice-service/gemini/preview/start", voiceAuthorizationPayload(state, { text: "Olá! Sou o Jarvis, seu assistente pessoal. Esta é uma demonstração da minha voz." })).catch((error) => ({ ok: false, error: error?.message || String(error) }));
    if (result?.ok) {
      if (status) status.textContent = "Reproduzindo áudio Gemini Live…";
    } else {
      const code = String(result?.error || result?.error_code || result?.detail || "GEMINI_PREVIEW_FAILED");
      const authorizationRequired = result?.authorization_required
        || code === "VOICE_AUTHORIZATION_REQUIRED"
        || code === "VOICE_DISABLED_BY_PROFILE";
      if (authorizationRequired) {
        state.geminiAuthorizationToken = "";
        clearGeminiGrantRenewal(state);
        window.__JARVIS_GEMINI_AUTH_TOKEN__ = "";
      }
      if (status) status.textContent = authorizationRequired
        ? "Autorização Gemini Live ausente ou expirada; clique em INICIAR GEMINI LIVE."
        : code === "GEMINI_PREVIEW_IN_PROGRESS"
          ? "Prévia Gemini já está em andamento; use PARAR TESTE para interromper."
          : `Falha na prévia Gemini: ${code}`;
      if (stop) stop.disabled = true;
      await refreshStatus(surface, state);
    }
    if (result?.ok) {
      await refreshStatus(surface, state);
      window.setTimeout(() => {
        if (state.geminiAudio?.preview_active === true) void refreshStatus(surface, state);
      }, 800);
    }
  });
  $("[data-dj-gemini-preview-stop]", surface)?.addEventListener("click", async () => {
    const post = endpoint(); if (!post || !state.geminiAuthorizationToken) return;
    await post("/api/jarvis/voice-service/gemini/preview/stop", voiceAuthorizationPayload(state)).catch(() => {});
    state.geminiAudio = null;
    const status = $("[data-dj-gemini-preview-status]", surface); const stop = $("[data-dj-gemini-preview-stop]", surface); if (status) status.textContent = "Prévia interrompida."; if (stop) stop.disabled = true;
    await refreshStatus(surface, state);
  });
  $("[data-dj-gemini-setup]", surface)?.addEventListener("click", async () => {
    const post = endpoint();
    const detail = $("[data-dj-voice-detail]", surface);
    const previewStatus = $("[data-dj-gemini-preview-status]", surface);
    if (!post) {
      if (previewStatus) previewStatus.textContent = "Gateway aguardando autenticação.";
      return;
    }
    if (detail) detail.textContent = "Solicitando autorização temporária para diagnóstico…";
    if (previewStatus) previewStatus.textContent = "Setup-only: sem microfone, áudio ou ferramentas.";
    const authorization = await post("/api/jarvis/voice-service/gemini/authorize", { confirm: true })
      .catch((error) => ({ ok: false, error: error?.message || String(error) }));
    if (!authorization?.authorization_token) {
      if (previewStatus) previewStatus.textContent = "Diagnóstico não autorizado: " + String(authorization?.error || "VOICE_AUTHORIZATION_FAILED");
      await refreshStatus(surface, state);
      return;
    }
    state.geminiAuthorizationToken = authorization.authorization_token;
    const result = await post(
      "/api/jarvis/voice-service/gemini/setup-diagnostic",
      voiceAuthorizationPayload(state),
    ).catch((error) => ({ ok: false, error: error?.message || String(error) }));
    const events = result?.diagnostics?.lifecycle_events
      || result?.status?.diagnostics?.provider?.transport?.lifecycle_events
      || [];
    const diagnosticSummary = setupDiagnosticSummary(result);
    state.geminiAuthorizationToken = "";
    clearGeminiGrantRenewal(state);
    window.__JARVIS_GEMINI_AUTH_TOKEN__ = "";
    if (result?.ok) {
      if (detail) detail.textContent = "Handshake setup_complete confirmado; sessão encerrada sem áudio."
        + (diagnosticSummary ? ` ${diagnosticSummary}` : "");
      if (previewStatus) previewStatus.textContent = "Diagnóstico concluído: " + events.map((item) => item.event).join(" → ");
    } else {
      const code = String(result?.error || "GEMINI_LIVE_SETUP_FAILED");
      if (detail) detail.textContent = "Diagnóstico Gemini falhou: " + code
        + (diagnosticSummary ? ` · ${diagnosticSummary}` : "");
      if (previewStatus) previewStatus.textContent = code + (events.length ? " · " + events.map((item) => item.event).join(" → ") : "");
    }
    await refreshStatus(surface, state);
  });
  $("[data-dj-gemini-start]", surface)?.addEventListener("click", async () => {
    state.geminiFailure = null;
    const post = endpoint();
    const detail = $("[data-dj-voice-detail]", surface);
    const previewStatus = $("[data-dj-gemini-preview-status]", surface);
    if (!post) {
      if (detail) detail.textContent = "Gateway aguardando autenticação; Gemini Live não foi iniciado.";
      return;
    }
    if (detail) detail.textContent = "Solicitando autorização temporária Gemini Live…";
    if (previewStatus) previewStatus.textContent = "Autorizando sessão Gemini Live…";
    state.settings.voiceMode = "gemini_live";
    window.__JARVIS_DESKTOP_VOICE_MODE__ = "gemini_live";
    saveSettings(state.settings);
    const authorization = await post("/api/jarvis/voice-service/gemini/authorize", { confirm: true })
      .catch((error) => ({ ok: false, error: error?.message || String(error) }));
    if (!authorization?.authorization_token) {
      const code = String(authorization?.error || authorization?.error_code || authorization?.detail || "VOICE_AUTHORIZATION_FAILED");
      if (detail) detail.textContent = `Gemini Live não iniciado: ${code}`;
      if (previewStatus) previewStatus.textContent = code === "VOICE_AUTHORIZATION_REQUIRED" || code === "VOICE_DISABLED_BY_PROFILE"
        ? "Autorização não concedida; nenhuma conexão foi aberta."
        : `Falha de autorização: ${code}`;
      await refreshStatus(surface, state);
      return;
    }
    state.geminiAuthorizationToken = authorization.authorization_token;
    window.__JARVIS_GEMINI_AUTH_TOKEN__ = state.geminiAuthorizationToken;
    const configured = await configureProfile(surface, state, {
      mode: "gemini_live",
      personality: state.settings.persona,
      voice: state.settings.geminiVoice,
    }, { authorize: true });
    if (!configured?.ok) {
      const code = String(configured?.error || configured?.error_code || "VOICE_PROFILE_FAILED");
      if (detail) detail.textContent = `Gemini Live não iniciado: ${code}`;
      if (previewStatus) previewStatus.textContent = `Falha ao aplicar o perfil: ${code}`;
      await post("/api/jarvis/voice-service/gemini/disconnect", { authorization_token: state.geminiAuthorizationToken }).catch(() => {});
      state.geminiAuthorizationToken = "";
      clearGeminiGrantRenewal(state);
      window.__JARVIS_GEMINI_AUTH_TOKEN__ = "";
      await refreshStatus(surface, state);
      return;
    }
    if (detail) detail.textContent = "Conectando ao Gemini Live…";
    if (previewStatus) previewStatus.textContent = "Conectando sessão Gemini Live…";
    const connected = await post("/api/jarvis/voice-service/gemini/connect", { authorization_token: state.geminiAuthorizationToken })
      .catch((error) => ({ ok: false, error: error?.message || String(error) }));
    if (!connected?.ok) {
      const code = String(connected?.error || connected?.error_code || connected?.detail || "GEMINI_LIVE_CONNECT_FAILED");
      const detailCode = connected?.detail && String(connected.detail) !== code ? ` · ${String(connected.detail).slice(0, 180)}` : "";
      const diagnosticClass = connected?.diagnostic?.error_class ? ` [${String(connected.diagnostic.error_class).slice(0, 80)}]` : "";
      const diagnosticSummary = setupDiagnosticSummary({ diagnostics: connected?.diagnostic || {} });
      const diagnosticSuffix = diagnosticSummary ? ` · ${diagnosticSummary.slice(0, 420)}` : "";
      state.geminiFailure = { code, detail: detailCode + diagnosticClass + diagnosticSuffix };
      if (detail) detail.textContent = `Gemini Live não conectado: ${code}`;
      if (previewStatus) previewStatus.textContent = code === "VOICE_AUTHORIZATION_REQUIRED" || code === "VOICE_DISABLED_BY_PROFILE"
        ? "Autorização Gemini Live ausente ou expirada."
        : `Falha de conexão: ${code}${detailCode}${diagnosticClass}${diagnosticSuffix}`;
      state.geminiAuthorizationToken = "";
      clearGeminiGrantRenewal(state);
      window.__JARVIS_GEMINI_AUTH_TOKEN__ = "";
      await refreshStatus(surface, state);
      return;
    }
    const audio = await post("/api/jarvis/voice-service/gemini/audio/start", voiceAuthorizationPayload(state, {
      endpoint_id: state.settings.microphoneId || "", capture: false,
    }))
      .catch((error) => ({ ok: false, error: error?.message || String(error) }));
    if (!audio?.ok) {
      const code = String(audio?.error || audio?.error_code || audio?.detail || "GEMINI_LIVE_AUDIO_START_FAILED");
      state.geminiFailure = { code, detail: "" };
      if (detail) detail.textContent = `Gemini conectado, mas captura não iniciou: ${code}`;
      if (previewStatus) previewStatus.textContent = `Áudio não iniciado: ${code}`;
      await post("/api/jarvis/voice-service/gemini/disconnect", { authorization_token: state.geminiAuthorizationToken }).catch(() => {});
      state.geminiAuthorizationToken = "";
      clearGeminiGrantRenewal(state);
      window.__JARVIS_GEMINI_AUTH_TOKEN__ = "";
      await refreshStatus(surface, state);
      return;
    }
    state.geminiFailure = null;
    if (detail) detail.textContent = "Gemini Live conectado; captura de áudio autorizada.";
    if (previewStatus) previewStatus.textContent = "Gemini Live conectado. Microfone mudo — clique no botão para falar.";
    await refreshStatus(surface, state);
  });
  $("[data-dj-gemini-stop]", surface)?.addEventListener("click", async () => { const post = endpoint(); if (!post) return; await post("/api/jarvis/voice-service/gemini/audio/stop", voiceAuthorizationPayload(state)).catch(() => {}); await post("/api/jarvis/voice-service/gemini/disconnect", { authorization_token: state.geminiAuthorizationToken || "" }).catch(() => {}); state.geminiAuthorizationToken = ""; clearGeminiGrantRenewal(state); state.geminiAudio = null; state.geminiFailure = null; window.__JARVIS_GEMINI_AUTH_TOKEN__ = ""; await refreshStatus(surface, state); });
  $("[data-dj-mic-refresh]", surface)?.addEventListener("click", () => refreshStatus(surface, state)); $("[data-dj-mic-probe]", surface)?.addEventListener("click", () => microphoneAction(surface, state, "probe")); $("[data-dj-mic-calibrate]", surface)?.addEventListener("click", () => microphoneAction(surface, state, "calibrate"));
  $("[data-dj-task-refresh]", surface)?.addEventListener("click", () => taskStatus(surface)); $("[data-dj-task-pause]", surface)?.addEventListener("click", () => taskAction(surface, "/api/jarvis/tasks/pause")); $("[data-dj-task-resume]", surface)?.addEventListener("click", () => taskAction(surface, "/api/jarvis/tasks/resume")); $("[data-dj-task-cancel]", surface)?.addEventListener("click", () => taskAction(surface, "/api/jarvis/tasks/cancel"));
  $("[data-dj-clear]", surface)?.addEventListener("click", () => document.querySelector("#gClearBtn")?.click()); $("[data-dj-listen]", surface)?.addEventListener("click", () => { const toggle = document.querySelector("#wakeToggle"); if (state.settings.voiceMode !== "gemini_live" && toggle && !toggle.checked) toggle.click(); }); $("[data-dj-stop]", surface)?.addEventListener("click", async () => { const post = endpoint(); if (state.settings.voiceMode === "gemini_live" && post) { await post("/api/jarvis/voice-service/gemini/audio/stop", voiceAuthorizationPayload(state)).catch(() => {}); await post("/api/jarvis/voice-service/gemini/disconnect", { authorization_token: state.geminiAuthorizationToken || "" }).catch(() => {}); state.geminiAuthorizationToken = ""; clearGeminiGrantRenewal(state); state.geminiAudio = null; await refreshStatus(surface, state); return; } const toggle = document.querySelector("#wakeToggle"); if (toggle?.checked) toggle.click(); });
  const initializeDesktopVoice = async () => {
    if (!endpoint()) {
      await refreshStatus(surface, state);
      return;
    }
    await configureProfile(surface, state, { personality: state.settings.persona, voice: state.settings.geminiVoice, mode: state.settings.voiceMode });
    await refreshStatus(surface, state);
    await autoConnectGeminiLive(surface, state);
  };
  void initializeDesktopVoice();
  if (window.Gateway?.on) window.Gateway.on("authenticated", () => {
    state._autoConnectAttempted = false;
    void initializeDesktopVoice();
  });
}
