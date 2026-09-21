const IS_DESKTOP = typeof window !== "undefined" && window.__JARVIS_DESKTOP__ === true;
const SR = typeof window !== "undefined" && !IS_DESKTOP
  ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;

export function voiceSupported() { return IS_DESKTOP || !!SR; }
export function ttsSupported() { return typeof window !== "undefined" && "speechSynthesis" in window; }

export function createVoice(opts = {}) {
  const {
    onPartial = () => {}, onFinal = () => {}, onError = () => {},
    onAmplitude = () => {}, onListeningChange = () => {},
    onSpeakStart = () => {}, onSpeakEnd = () => {},
    onWake = () => {},
  } = opts;

  let lang = "pt-BR";
  let rate = 1.02;
  let pitch = 0.82;
  let voiceName = "";
  let listening = false;
  let rec = null;
  let killNext = false;
  let wakeMode = false;
  let wakeWord = "jarvis";
  let wakeRestartTimer = 0;

  // --- microphone amplitude (visual reaction) ---
  let audioCtx = null, analyser = null, ampBuf = null, ampRaf = 0, ampStream = null;

  async function startAmp() {
    stopAmp();
    try {
      if (!navigator.mediaDevices?.getUserMedia) return;
      ampStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      audioCtx = audioCtx || new Ctx();
      const src = audioCtx.createMediaStreamSource(ampStream);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.75;
      src.connect(analyser);
      ampBuf = new Uint8Array(analyser.frequencyBinCount);
      const loop = () => {
        ampRaf = requestAnimationFrame(loop);
        if (!analyser) return;
        analyser.getByteTimeDomainData(ampBuf);
        let sum = 0;
        for (let i = 0; i < ampBuf.length; i++) {
          const v = (ampBuf[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / ampBuf.length);
        onAmplitude(Math.min(1, rms * 4.2));
      };
      ampRaf = requestAnimationFrame(loop);
    } catch {
      // microphone blocked or unavailable — the orb falls back to a synthetic pulse
    }
  }

  function stopAmp() {
    cancelAnimationFrame(ampRaf);
    ampRaf = 0;
    analyser = null;
    if (ampStream) { ampStream.getTracks().forEach((t) => t.stop()); ampStream = null; }
    onAmplitude(0);
  }

  // --- speech recognition ---
  function buildRecognition(continuous) {
    const r = new SR();
    r.lang = lang;
    r.continuous = !!continuous;
    r.interimResults = true;
    r.maxAlternatives = 1;
    return r;
  }

  function attach(r, { continuous }) {
    r.onstart = () => {
      listening = true;
      onListeningChange(true);
      startAmp();
    };
    r.onresult = (e) => {
      let interim = "", final = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) final += res[0].transcript;
        else interim += res[0].transcript;
      }
      const said = (final || interim).toLowerCase().trim();
      if (continuous && wakeMode) {
        if (said.includes(wakeWord)) {
          const rest = said.split(wakeWord).slice(1).join(" ").trim();
          if (final) {
            if (rest.length > 1) onFinal(rest);
            else onWake();
          }
        }
        return;
      }
      if (final.trim()) onFinal(final.trim());
      else onPartial(interim.trim());
    };
    r.onerror = (e) => {
      const map = {
        "not-allowed": "Microfone bloqueado pelo navegador. Permita o acesso ou abra o gerador em uma aba própria.",
        "service-not-allowed": "Serviço de voz indisponível neste contexto (iframe). Abra o gerador em uma aba própria.",
        "audio-capture": "Nenhum microfone encontrado.",
        "no-speech": "Não ouvi nada. Tente novamente.",
        network: "Falha de rede no reconhecimento de voz.",
      };
      const msg = map[e.error] || `Erro de voz: ${e.error}`;
      if (e.error !== "no-speech" && e.error !== "aborted") onError(msg);
      if (e.error === "not-allowed" || e.error === "service-not-allowed") wakeMode = false;
    };
    r.onend = () => {
      listening = false;
      onListeningChange(false);
      stopAmp();
      if (killNext) { killNext = false; return; }
      if (wakeMode && SR) {
        clearTimeout(wakeRestartTimer);
        wakeRestartTimer = setTimeout(() => { if (wakeMode) start(true); }, 420);
      }
    };
  }

  function start(continuous = false) {
    if (!SR) { onError("Seu navegador não suporta reconhecimento de voz. Use o campo de texto."); return false; }
    if (listening) return true;
    try {
      rec = buildRecognition(continuous || wakeMode);
      attach(rec, { continuous: continuous || wakeMode });
      rec.start();
      return true;
    } catch (err) {
      onError("Não foi possível iniciar o microfone: " + (err?.message || err));
      return false;
    }
  }

  function stop() {
    wakeMode = false;
    clearTimeout(wakeRestartTimer);
    killNext = true;
    try { rec?.stop(); } catch {}
    listening = false;
    onListeningChange(false);
    stopAmp();
  }

  function enableWake(word) {
    if (word) wakeWord = String(word).toLowerCase();
    wakeMode = true;
    start(true);
  }

  function setWakeWord(w) { wakeWord = String(w || "jarvis").toLowerCase(); }
  function setLang(l) { lang = l || "pt-BR"; }
  function setRate(v) { rate = Number(v) || 1; }
  function setPitch(v) { pitch = Number(v) || 1; }
  function setVoice(name) { voiceName = name || ""; }

  function getVoices() {
    if (!ttsSupported()) return [];
    return window.speechSynthesis.getVoices().map((v) => ({ name: v.name, lang: v.lang, local: v.localService }));
  }

  function pickVoice() {
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return null;
    if (voiceName) {
      const exact = voices.find((v) => v.name === voiceName);
      if (exact) return exact;
    }
    const base = lang.split("-")[0];
    const langMatch = voices.filter((v) => v.lang?.toLowerCase().startsWith(base));
    const pool = langMatch.length ? langMatch : voices;
    const prefer = [
      /google.*portugu/i, /luciana/i, /microsoft.*(daniel|ricardo|antonio)/i,
      /en-GB.*(male|daniel|george)/i, /google uk english male/i, /male/i,
    ];
    for (const re of prefer) {
      const found = pool.find((v) => re.test(v.name));
      if (found) return found;
    }
    return pool.find((v) => v.default) || pool[0];
  }

  function cleanForSpeech(text) {
    return String(text)
      .replace(/```[\s\S]*?```/g, " bloco de código ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/https?:\/\/\S+/g, "link")
      .replace(/[*_#>|]/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim()
      .slice(0, 900);
  }

  function speak(text) {
    if (!ttsSupported() || !text) { return false; }
    const t = cleanForSpeech(text);
    if (!t) return false;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(t);
      u.lang = lang;
      u.rate = rate;
      u.pitch = pitch;
      const v = pickVoice();
      if (v) u.voice = v;
      u.onstart = () => onSpeakStart();
      u.onend = () => onSpeakEnd();
      u.onerror = () => onSpeakEnd();
      window.speechSynthesis.speak(u);
      return true;
    } catch { return false; }
  }

  function stopSpeaking() {
    try { window.speechSynthesis.cancel(); } catch {}
    onSpeakEnd();
  }

  function isSpeaking() {
    try { return window.speechSynthesis.speaking; } catch { return false; }
  }

  return {
    start, stop, enableWake, setWakeWord, setLang, setRate, setPitch, setVoice,
    getVoices, speak, stopSpeaking, isSpeaking,
    isListening: () => listening,
    isWakeMode: () => wakeMode,
  };
}
