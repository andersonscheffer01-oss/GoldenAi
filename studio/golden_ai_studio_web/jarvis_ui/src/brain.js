/**
 * Brain — Command intent matching (staging version)
 * 
 * SECURITY CHANGES from reference:
 * 1. safeCalc() replaced by MathParser (no Function()/eval())
 * 2. systemActionFallback() routes through Gateway (no "backend offline" message)
 * 3. openSite() routes system-level opens through Gateway
 * 4. Unknown commands route through Gateway (not "backend offline")
 * 5. All browser-side intents preserved (time, date, notes, theme, etc.)
 */

const SITES = {
  youtube: "https://www.youtube.com", gmail: "https://mail.google.com", google: "https://www.google.com",
  github: "https://github.com", whatsapp: "https://web.whatsapp.com", instagram: "https://www.instagram.com",
  facebook: "https://www.facebook.com", x: "https://x.com", twitter: "https://x.com",
  netflix: "https://www.netflix.com", spotify: "https://open.spotify.com", maps: "https://maps.google.com",
  wikipedia: "https://pt.wikipedia.org", chatgpt: "https://chat.openai.com", drive: "https://drive.google.com",
  discord: "https://discord.com/app", telegram: "https://web.telegram.org", reddit: "https://www.reddit.com",
  twitch: "https://www.twitch.tv", mercado: "https://www.mercadolivre.com.br", amazon: "https://www.amazon.com.br",
  globo: "https://g1.globo.com", noticias: "https://g1.globo.com", linkedin: "https://www.linkedin.com",
  tradutor: "https://translate.google.com", calendario: "https://calendar.google.com", agenda: "https://calendar.google.com",
  canva: "https://www.canva.com", figma: "https://www.figma.com",
};

const AJUDA = [
  "Capacidades da interface (modo local):",
  "",
  "• «que horas são» / «que dia é hoje» — relógio e calendário",
  "• «clima em São Paulo» — previsão real (Open-Meteo)",
  "• «abrir YouTube» / «abre o GitHub» — abre site numa nova aba",
  "• «pesquisar receita de pão» — busca na web",
  "• «tocar música lofi» — ambiente sonoro/vídeo por busca",
  "• «anote comprar café» / «minhas notas» — memória local persistente",
  "• «timer de 10 minutos» / «alarme às 7:30» — cronômetro e alarme",
  "• «status do sistema» — CPU, memória e disco (via Gateway)",
  "• «interface dourada» — muda o HUD (7 modelos)",
  "• «tela cheia», «limpar conversa», «calcule 12*7», «piada»",
  "",
  "Para ações de sistema (abrir programas, volume, MT5, etc.),",
  "conecte-se ao Gateway — todos os comandos são roteados com segurança.",
].join("\n");

const PIADAS = [
  "Meu criador diz que eu sou a IA mais bem vestida do mundo. É só uma armadura, mas obrigado.",
  "Um programador foi ao médico: Doutor, dói quando eu faço assim. O médico respondeu: então não faça assim.",
  "Existem 10 tipos de pessoas no mundo: as que entendem binário e as que não.",
  "Eu tentaria contar uma piada sobre UDP, mas talvez você não a recebesse.",
  "Processando humor... pronto. Se você não riu, o problema está no seu módulo de emoções.",
];

const WEATHER_CODES = {
  0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
  45: "névoa", 48: "névoa congelante", 51: "garoa leve", 53: "garoa", 55: "garoa forte",
  61: "chuva leve", 63: "chuva", 65: "chuva forte", 71: "neve leve", 73: "neve", 75: "neve forte",
  80: "pancadas de chuva", 81: "pancadas fortes", 82: "pancadas violentas",
  95: "trovoada", 96: "trovoada com granizo", 99: "trovoada severa",
};

const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ").trim();
const hasAny = (t, arr) => arr.some((w) => t.includes(w));

function fmtTime(d) {
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function fmtDate(d) {
  return d.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
}

// SECURITY: Uses MathParser instead of Function()/eval()
function safeCalc(expr) {
  let s = norm(expr)
    .replace(/\b(quanto|quanto e|quanto é|calcule|calcular|resultado de|resultado|e|de)\b/g, " ")
    .replace(/x|×/g, "*").replace(/,/g, ".").replace(/÷/g, "/")
    .replace(/[^0-9+\-*/().%\s^]/g, "")
    .trim();
  if (!s || !/[0-9]/.test(s)) return null;
  try {
    if (!window.MathParser) return null;
    const val = window.MathParser.evaluate(s);
    return { expr: s, val };
  } catch { return null; }
}

// Route through Gateway for system actions
async function routeToGateway(command, ctx) {
  if (!ctx.connected || !window.Gateway || !window.Gateway.isAuthenticated) {
    return {
      reply: `Esse comando requer o Gateway conectado.\n\n1. Verifique se o Gateway está rodando\n2. Conecte-se via CONFIGURAÇÕES\n\nComando: «${command}»`,
      speak: "Esse comando requer o Gateway conectado.",
      actions: [{ name: "gateway", status: "offline", detail: "não conectado" }],
    };
  }
  try {
    const result = await window.Gateway.sendCommand(command);
    return {
      reply: result.text || result.output || JSON.stringify(result),
      speak: true,
      actions: [{ name: "gateway", status: "ok", detail: command }],
    };
  } catch (err) {
    return {
      reply: `Erro ao executar via Gateway: ${err.message}`,
      speak: false,
      error: true,
      actions: [{ name: "gateway", status: "error", detail: err.message }],
    };
  }
}

export function createBrain(ctx) {
  async function clima(local) {
    const q = local || ctx.getLastCity() || "São Paulo";
    const geoR = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}&count=1&language=pt&format=json`);
    const geo = await geoR.json();
    const place = geo?.results?.[0];
    if (!place) return { reply: `Não encontrei a localidade «${q}». Tente o nome de uma cidade maior.`, speak: true };
    ctx.setLastCity(place.name + (place.admin1 ? ", " + place.admin1 : ""));
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${place.latitude}&longitude=${place.longitude}`
      + `&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m`
      + `&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&timezone=auto&forecast_days=3`;
    const r = await fetch(url);
    const d = await r.json();
    const c = d.current, dl = d.daily;
    const desc = WEATHER_CODES[c.weather_code] || "condição indefinida";
    const lines = [
      `Clima em ${place.name}${place.country ? " (" + place.country + ")" : ""}:`,
      `Agora: ${Math.round(c.temperature_2m)}°C (sensação ${Math.round(c.apparent_temperature)}°C), ${desc}.`,
      `Umidade ${c.relative_humidity_2m}% · vento ${Math.round(c.wind_speed_10m)} km/h · chuva ${c.precipitation} mm.`,
      "",
      "Próximos dias:",
      ...dl.time.slice(0, 3).map((day, i) => {
        const dd = new Date(day + "T12:00:00");
        const nome = dd.toLocaleDateString("pt-BR", { weekday: "short" });
        return `  ${nome}: ${Math.round(dl.temperature_2m_min[i])}° a ${Math.round(dl.temperature_2m_max[i])}° · ${WEATHER_CODES[dl.weather_code[i]] || "—"} · chuva ${dl.precipitation_probability_max[i] ?? 0}%`;
      }),
    ];
    return { reply: lines.join("\n"), speak: `Em ${place.name} está ${Math.round(c.temperature_2m)} graus, ${desc}.` };
  }

  const INTENTS = [
    {
      id: "greeting",
      test: (t) => /^(oi|ola|opa|eae|e ai|bom dia|boa tarde|boa noite|hey|jarvis)\b/.test(t) || t === "jarvis",
      run: (t) => {
        const h = new Date().getHours();
        const saud = h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
        const extra = hasAny(t, ["bom dia"]) ? "Sistemas em ordem." : "";
        return { reply: `${saud}, ${ctx.userName}. ${extra} ${ctx.connected ? "Gateway conectado e aguardando ordens." : "Em modo local — diga «ajuda» para ver o que já posso fazer."}`.replace(/\s+/g, " ").trim(), speak: true };
      },
    },
    {
      id: "identity",
      test: (t) => hasAny(t, ["quem e voce", "quem e vc", "seu nome", "o que voce e", "se apresente", "qual seu nome"]),
      run: () => ({
        reply: `Sou ${ctx.systemName} — sua interface de comando pessoal. Converso por voz ou texto, controlo as interfaces, monitoro sensores e executo rotinas.\nOs comandos de sistema são roteados com segurança através do Gateway.`,
        speak: `Sou ${ctx.systemName}, sua interface de comando pessoal.`,
      }),
    },
    {
      id: "help",
      test: (t) => /^(ajuda|help|comandos|o que voce faz|o que vc faz|funcoes|capacidades)\b/.test(t) || t === "?",
      run: () => ({ reply: AJUDA, speak: "Vou listar minhas capacidades na tela, senhor." }),
    },
    {
      id: "time",
      test: (t) => hasAny(t, ["que horas", "horas sao", "horario", "me diga a hora", "hora agora"]),
      run: () => {
        const d = new Date();
        return { reply: `Agora são ${fmtTime(d)}${d.getHours() < 12 ? " da manhã" : d.getHours() < 18 ? " da tarde" : " da noite"}.`, speak: true };
      },
    },
    {
      id: "date",
      test: (t) => hasAny(t, ["que dia", "data de hoje", "hoje e que dia", "qual a data", "dia da semana"]),
      run: () => ({ reply: `Hoje é ${fmtDate(new Date())}.`, speak: true }),
    },
    {
      id: "timer",
      test: (t) => /\b(timer|cronometro|conta|alarme|me avise|me lembre|daqui a)\b/.test(t),
      run: (t) => {
        let ms = 0, label = "";
        const mMin = t.match(/(\d+(?:[.,]\d+)?)\s*(min|minuto|minutos)\b/);
        const mSec = t.match(/(\d+)\s*(seg|segundo|segundos)\b/);
        const mHour = t.match(/(\d+(?:[.,]\d+)?)\s*(h|hora|horas)\b/);
        const mClock = t.match(/(?:as|às|as)\s*(\d{1,2})[:h](\d{2})?/);
        if (mClock) {
          const now = new Date();
          const target = new Date();
          target.setHours(+mClock[1], +(mClock[2] || 0), 0, 0);
          if (target <= now) target.setDate(target.getDate() + 1);
          ms = target - now;
          label = `alarme das ${mClock[1]}:${(mClock[2] || "00")}`;
        } else if (mHour) { ms = parseFloat(mHour[1].replace(",", ".")) * 3600000; label = `${mHour[1]} hora(s)`; }
        else if (mMin) { ms = parseFloat(mMin[1].replace(",", ".")) * 60000; label = `${mMin[1]} minuto(s)`; }
        else if (mSec) { ms = +mSec[1] * 1000; label = `${mSec[1]} segundo(s)`; }
        if (!ms || ms < 1000) return { reply: "Diga o tempo, por exemplo: «timer de 10 minutos» ou «alarme às 7:30».", speak: true };
        ctx.setTimer(ms, label);
        const totalSec = Math.round(ms / 1000);
        const mins = Math.floor(totalSec / 60), secs = totalSec % 60;
        return {
          reply: `Cronômetro armado para ${label} (${mins > 0 ? mins + "min " : ""}${secs}s). Vou avisar com som e notificação.`,
          speak: `Cronômetro armado para ${label}.`,
        };
      },
    },
    {
      id: "notes-add",
      test: (t) => /\b(anote|anotar|anota|lembre de|guardar|memorize|salve)\b/.test(t),
      run: (t, raw) => {
        const body = String(raw || t).replace(/^.*?\b(anote|anotar|anota|lembre de|memorize|guardar|salve)\b/i, "").replace(/^[:\s-]+/, "").trim();
        if (!body) return { reply: "O que devo anotar?", speak: true };
        ctx.notes.add(body);
        return { reply: `Anotado: «${body}». Já está na memória local (sobrevive a recarregamentos).`, speak: "Anotado." };
      },
    },
    {
      id: "notes-list",
      test: (t) => /\b(minhas notas|listar notas|mostrar notas|o que anotei|lembretes)\b/.test(t),
      run: () => {
        const list = ctx.notes.list();
        if (!list.length) return { reply: "Sua memória está vazia. Diga «anote ...» para gravar algo." };
        return { reply: "Anotações:\n" + list.map((n, i) => `${i + 1}. ${n.text}  ·  ${new Date(n.ts).toLocaleString("pt-BR")}`).join("\n"), speak: `Você tem ${list.length} anotações.` };
      },
    },
    {
      id: "notes-clear",
      test: (t) => /\b(limpar notas|limpar memoria|apagar notas|esquecer tudo)\b/.test(t),
      run: () => { ctx.notes.clear(); return { reply: "Memória de anotações apagada.", speak: true }; },
    },
    {
      id: "theme",
      test: (t) => /\b(interface|interfaces|hud|tema|temas|layout|aparencia|visual)\b/.test(t),
      run: (t) => {
        const id = ctx.resolveTheme(t);
        if (!id) return { reply: "Tenho sete modelos, senhor. O padrão é o GOLDEN JARVIS. Além dele: REATOR ARC, CENTRO DE COMANDO, NEURAL, SENTINELA, NÚCLEO NEURAL e HOLOGRAMA. Qual deles?", speak: true };
        ctx.setTheme(id);
        return { reply: `Interface alternada para ${ctx.themeName(id)}.`, speak: true };
      },
    },
    {
      id: "alert",
      test: (t) => /\b(modo alerta|alerta|emergencia|perigo|protocolo vermelho)\b/.test(t),
      run: (t) => {
        if (hasAny(t, ["cancelar", "desligar", "sair do", "parar"])) {
          ctx.setState("idle");
          return { reply: "Modo alerta encerrado. Todos os sistemas retornando ao normal.", speak: true };
        }
        ctx.setState("alert", 9000);
        return { reply: "MODO ALERTA ATIVADO. Sensores em vigilância máxima por 9 segundos.", speak: "Modo alerta ativado." };
      },
    },
    {
      id: "calc",
      test: (t) => /^[0-9\s(]/.test(t) && /[+\-*/^x×]/.test(t) || /\b(calcule|quanto e|quanto é)\b/.test(t),
      run: (t) => {
        const r = safeCalc(t);
        if (!r) return null;
        return { reply: `${r.expr.replace(/\*\*/g, "^")} = ${r.val}`, speak: `${r.val}` };
      },
    },
    {
      id: "weather",
      test: (t) => hasAny(t, ["clima", "tempo", "temperatura", "vai chover", "previsao", "faz calor"]),
      run: async (t) => {
        const m = t.match(/(?:em|no|na|de|para)\s+([a-záéíóúâêôãõç\s'-]{3,40})$/);
        let local = m ? m[1].trim() : null;
        if (!local) {
          const m2 = String(t).match(/\b(?:clima|tempo|temperatura|previsao)\s+([a-záéíóúâêôãõç\s'-]{3,40})/);
          if (m2) local = m2[1].trim();
        }
        return await clima(local);
      },
    },
    {
      id: "music",
      test: (t) => /\b(tocar|toque|play|musica|som ambiente|colocar uma musica)\b/.test(t),
      run: (t, raw) => {
        const q = String(raw || t).replace(/^.*?\b(tocar|toque|play|musica|colocar)\b/i, "").replace(/^[:\s-]+/, "").trim() || "lofi hip hop";
        const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`;
        ctx.openUrl(url, "YouTube · " + q);
        return { reply: `Abrindo áudio: «${q}». O navegador exige um toque/clique para liberar o som — o player já está na aba nova.`, speak: `Reproduzindo ${q}.` };
      },
    },
    {
      id: "openSite",
      test: (t) => /\b(abrir|abre|abrir o|acessar|entrar no|entra no|vai para|ir para)\b/.test(t),
      run: (t, raw) => {
        const after = String(raw || t).replace(/^.*?\b(abrir|abre|abrir o|acessar|entrar no|entra no|vai para|ir para)\b/i, "").replace(/^[:\s-]+/, "").trim();
        const n = norm(after).replace(/[^a-z0-9 ]/g, "");
        const hit = Object.keys(SITES).find((k) => n.includes(k));
        if (hit) {
          ctx.openUrl(SITES[hit], hit);
          return { reply: `Abrindo ${hit.toUpperCase()} numa nova aba.`, speak: `Abrindo ${hit}.` };
        }
        if (/^(https?:\/\/|\w+\.\w{2,})/.test(after)) {
          const url = /^https?:/.test(after) ? after : "https://" + after;
          ctx.openUrl(url, after);
          return { reply: `Abrindo ${after}.`, speak: true };
        }
        // System-level open → route through Gateway
        return routeToGateway(`abrir ${after}`, ctx);
      },
    },
    {
      id: "search",
      test: (t) => /\b(pesquisar|pesquise|procure|buscar|busque|google)\b/.test(t),
      run: async (t, raw) => {
        const q = String(raw || t).replace(/^.*?\b(pesquisar|pesquise|procure|buscar|busque|google)\b/i, "").replace(/^[:\s-]+/, "").replace(/\b(no|na|por|sobre)\b\s*/gi, "").trim();
        if (!q) return { reply: "O que devo pesquisar?", speak: true };
        if (ctx.webSearch) {
          const r = await ctx.webSearch(q);
          if (r?.ok) {
            const n = r.results.length;
            const src = (r.sources || []).join(", ");
            const top = r.results[0];
            return {
              reply: `Pesquisei «${q}» na internet agora: ${n} fonte${n === 1 ? "" : "s"} ${n === 1 ? "real" : "reais"}${src ? " (" + src + ")" : ""}.\n${top ? "Mais relevante: " + top.title + " — " + (top.host || "") : ""}`,
              speak: `Encontrei ${n} fontes sobre ${q}.`,
            };
          }
          if (r) return { reply: `Não consegui pesquisar «${q}» na internet agora — ${r.error || "nenhuma fonte respondeu"}`, speak: "A pesquisa não respondeu.", error: true };
        }
        ctx.openUrl(`https://duckduckgo.com/?q=${encodeURIComponent(q)}`, q);
        return { reply: `Pesquisando «${q}» na web.`, speak: `Pesquisando ${q}.` };
      },
    },
    {
      id: "fullscreen",
      test: (t) => hasAny(t, ["tela cheia", "fullscreen", "tela completa", "maximizar janela"]),
      run: () => { ctx.toggleFullscreen(); return { reply: "Alternando modo de tela cheia.", speak: true }; },
    },
    {
      id: "clear",
      test: (t) => hasAny(t, ["limpar conversa", "limpar historico", "apagar conversa", "limpar tela", "nova sessao"]),
      run: () => { ctx.clearConversation(); return { reply: "Histórico de conversa limpo.", speak: true }; },
    },
    {
      id: "whoami",
      test: (t) => hasAny(t, ["quem sou eu", "meu nome", "meus dados"]),
      run: () => ({ reply: `Você é ${ctx.userName} — o operador desta instalação do ${ctx.systemName}.\nEste dispositivo: ${navigator.platform || "desconhecido"} · ${screen.width}×${screen.height} · ${navigator.hardwareConcurrency || "?"} núcleos.`, speak: true }),
    },
    {
      id: "joke",
      test: (t) => /\b(piada|conte algo engracado|me faca rir|humor)\b/.test(t),
      run: () => { const p = PIADAS[Math.floor(Math.random() * PIADAS.length)]; return { reply: p, speak: p }; },
    },
    // System actions → ALL route through Gateway
    {
      id: "system-action",
      test: (t) => /\b(volume|mudo|mutar|silenciar|travar|bloquear|lock|desligar|desliga|reiniciar|reinicia|suspender|print|captura de tela|screenshot|fechar|processos|cpu|ram|disco|wifi|bluetooth|abrir programa)\b/.test(t)
        || /\b(abrir|abre|fechar|fecha|executar|rode|iniciar|inicia)\s+[a-z0-9]/i.test(t),
      run: async (t) => routeToGateway(t, ctx),
    },
  ];

  return {
    async think(rawText) {
      const text = String(rawText || "").trim();
      if (!text) return null;
      const t = norm(text);

      for (const intent of INTENTS) {
        let match = false;
        try { match = intent.test(t); } catch { match = false; }
        if (!match) continue;
        try {
          const out = await intent.run(t, text);
          if (out) return { ...out, intent: intent.id };
        } catch (e) {
          return { reply: `Falha ao processar «${text}»: ${e.message || e}`, speak: false, error: true };
        }
      }

      // Unknown → route through Gateway
      return routeToGateway(text, ctx);
    },
    clima,
    aiAsk: ctx.aiAsk,
    helpText: AJUDA,
    sites: SITES,
  };
}
