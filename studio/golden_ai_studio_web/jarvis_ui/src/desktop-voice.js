// Desktop voice transport: controls and observes the existing Core VoiceService.
export function createDesktopVoiceClient(opts = {}) {
  const gateway = opts.gateway;
  const onState = opts.onState || (() => {});
  const onEvent = opts.onEvent || (() => {});
  const onError = opts.onError || (() => {});
  let active = false;
  let timer = 0;
  let lastEventId = 0;
  const seenResponseIds = new Set();

  async function status() {
    if (!gateway?.httpPost) throw new Error("Gateway indisponível para voz local.");
    const data = await gateway.httpPost("/api/jarvis/voice-service/status", {});
    if (!data || data.ok === false) {
      throw new Error(data?.error || "VoiceService indisponível.");
    }
    return data;
  }

  function acceptStatus(data, baseline = false) {
    const event = data?.last_event || {};
    const eventId = Number(event.id || 0);
    if (baseline) lastEventId = eventId;
    onState(String(data?.state || "OFF"), data);
    const responseId = String(event.response_id || "");
    if (!baseline && eventId > lastEventId &&
        (!responseId || !seenResponseIds.has(responseId))) {
      lastEventId = eventId;
      if (responseId) seenResponseIds.add(responseId);
      console.info("[JARVIS-VOICE-UI]", event.trace || {
        PROCESS_ID: event.process_id,
        SOURCE_MODULE: event.source_module,
        SESSION_ID: event.session_id,
        RESPONSE_ID: responseId,
        TTS_OWNER: event.tts_owner,
      });
      onEvent(event);
    }
  }

  async function poll(baseline = false) {
    try {
      acceptStatus(await status(), baseline);
    } catch (err) {
      onError(err?.message || String(err));
    }
  }

  function beginPolling() {
    clearInterval(timer);
    timer = setInterval(() => poll(false), 500);
  }

  async function start(options = {}) {
    const capture = options.capture !== false;
    if (!gateway?.httpPost) {
      onError("Gateway indisponível para voz local.");
      return false;
    }
    try {
      const before = await status();
      acceptStatus(before, true);
      let result = before;
      if (!before.running) {
        result = await gateway.httpPost("/api/jarvis/voice-service/start", {});
        if (!result || result.ok === false) {
          throw new Error(result?.error || "Não foi possível iniciar o VoiceService.");
        }
      }
      if (capture) {
        result = await gateway.httpPost("/api/jarvis/voice-service/listen", {
          session_id: gateway.sessionId || "",
        });
        if (!result || result.ok === false) {
          throw new Error(result?.error || "Microfone indisponível.");
        }
      }
      active = true;
      onState(capture ? "LISTENING" : String(result.state || "WAITING_WAKE"), result);
      beginPolling();
      return true;
    } catch (err) {
      active = false;
      onError(err?.message || String(err));
      return false;
    }
  }

  async function stop() {
    clearInterval(timer);
    timer = 0;
    try {
      const result = await gateway?.httpPost?.("/api/jarvis/voice-service/stop", {});
      active = false;
      onState("OFF", result || {});
      return !!result?.ok;
    } catch (err) {
      onError(err?.message || String(err));
      return false;
    }
  }

  function dispose() {
    clearInterval(timer);
    timer = 0;
    active = false;
  }

  return { start, stop, status: poll, dispose, isActive: () => active };
}
