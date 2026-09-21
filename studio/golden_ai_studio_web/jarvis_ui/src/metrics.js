// ---------------------------------------------------------------------------
// metrics.js — leituras REAIS usadas pelo painel GOLDEN JARVIS.
//
// Nada aqui é inventado: quando o backend local (src/backend/jarvis_server.py)
// está conectado, os medidores mostram o PC de verdade (psutil/nvidia-smi:
// CPU, RAM, GPU, VRAM, temperatura, processos, rede, disco). Sem backend, os
// medidores caem para o que o navegador consegue medir de fato: carga do laço
// de render, heap JS, núcleos, nome real da GPU (WEBGL_debug_renderer_info),
// bateria, rede e long tasks do PerformanceObserver.
// ---------------------------------------------------------------------------

const clamp = (v, a = 0, b = 100) => Math.max(a, Math.min(b, v));

// Rótulo legível do sistema a partir do user agent (o navigator.platform devolve
// coisas como "Win32", que não dizem nada ao usuário).
function platformLabel() {
  const ua = navigator.userAgent || "";
  const p = navigator.userAgentData?.platform || navigator.platform || "";
  if (/android/i.test(ua)) return "Android";
  if (/iphone|ipad|ipod/i.test(ua)) return "iOS";
  if (/windows|win32|win64/i.test(ua + p)) return "Windows";
  if (/mac os|macintosh|macintel/i.test(ua + p)) return "macOS";
  if (/linux|x11/i.test(ua + p)) return "Linux";
  return p || "Dispositivo";
}

function glRenderer() {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return null;
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    if (!ext) return null;
    const raw = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) || "";
    const vendor = String(gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) || "").trim();
    let clean = String(raw)
      .replace(/^ANGLE\s*\(/i, "").replace(/\)$/, "")
      .replace(/Direct3D.*$/i, "").replace(/\s*\(0x[0-9A-F]+\)/gi, "")
      .replace(/\s{2,}/g, " ").trim();
    // "AMD, AMD Radeon RX 9060 XT" → "AMD Radeon RX 9060 XT"
    if (vendor && clean.toLowerCase().startsWith(vendor.toLowerCase())) {
      clean = clean.slice(vendor.length).replace(/^[\s,]+/, "");
    }
    // o campo vendor do WebGL costuma vir como "Google Inc. (AMD)" e não casa com o
    // começo do nome, então repetimos a checagem parte-a-parte ("AMD, AMD Radeon…")
    const parts = clean.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length > 1) {
      const head = parts[0].toLowerCase();
      if (parts.slice(1).some((p) => p.toLowerCase().includes(head))) parts.shift();
    }
    clean = parts.join(", ").replace(/\s{2,}/g, " ").trim();
    return { name: clean || raw, vendor };
  } catch { return null; }
}

export function createMetrics({ getFps } = {}) {
  const gpu = glRenderer();
  const hist = { cpu: [], ram: [], gpu: [], vram: [] };
  const HIST = 72;

  let server = null;             // telemetria do backend
  let busyMs = 0;                // ms de main-thread bloqueada na janela atual
  let longTaskPct = 0;           // % de bloqueio (média móvel das janelas de 1s)
  let lastFrame = 0, frameAcc = 0, frameN = 0;
  let lastLongFlush = performance.now();
  let battery = null;
  let rafId = 0, running = false;
  let sample = null;

  try {
    const b = navigator.getBattery?.();
    if (b) b.then((x) => {
      battery = { level: Math.round(x.level * 100), charging: !!x.charging };
      x.addEventListener("levelchange", () => { battery.level = Math.round(x.level * 100); });
      x.addEventListener("chargingchange", () => { battery.charging = !!x.charging; });
    }).catch(() => {});
  } catch {}

  try {
    if (window.PerformanceObserver) {
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) busyMs += e.duration;
      }).observe({ entryTypes: ["longtask"] });
    }
  } catch {}

  function tick(now) {
    if (!running) return;
    rafId = requestAnimationFrame(tick);
    if (lastFrame) {
      const d = now - lastFrame;
      if (d > 0 && d < 400) { frameAcc += d; frameN++; }
    }
    lastFrame = now;
    // fecha a janela de 1s: % do tempo em que o laço principal ficou bloqueado
    const flush = now - lastLongFlush;
    if (flush >= 1000) {
      const pct = clamp((busyMs * 100) / flush);
      longTaskPct = longTaskPct * 0.45 + pct * 0.55;
      busyMs = 0;
      lastLongFlush = now;
    }
  }

  // Carga do laço principal deste navegador: bloqueios medidos (long tasks) mais
  // a perda de quadros em relação ao teto de desenho. É o que dá para medir sem
  // o backend — a utilização real de CPU do sistema só vem do servidor local.
  function deviceCpu() {
    const fps = typeof getFps === "function" ? getFps() : 60;
    const head = fps < 52 ? clamp((52 - fps) * 3.4) : 0;
    return clamp(longTaskPct * 0.8 + head * 0.5);
  }

  function build() {
    const net = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    const heap = performance.memory
      ? { used: performance.memory.usedJSHeapSize / 1048576, total: performance.memory.totalJSHeapSize / 1048576, limit: performance.memory.jsHeapSizeLimit / 1048576 }
      : null;
    const fps = typeof getFps === "function" ? getFps() : 60;

    if (server && (server.cpu != null || server.ram != null)) {
      return {
        source: "backend",
        cpu: { pct: server.cpu == null ? null : clamp(server.cpu), name: server.cpuName || server.host || "Servidor local", cores: server.cores || null },
        ram: { pct: server.ram == null ? null : clamp(server.ram), usedGB: server.ramUsedGB ?? null, totalGB: server.ramTotalGB ?? null },
        gpu: { pct: server.gpu == null ? null : clamp(server.gpu), name: server.gpuName || null, note: server.gpuNote || null },
        vram: { pct: server.vram == null ? null : clamp(server.vram), usedGB: server.vramUsedGB ?? null, totalGB: server.vramTotalGB ?? null, note: server.vramNote || null },
        temp: { cpu: server.tempCpu ?? null, gpu: server.tempGpu ?? null },
        procs: server.procs ?? null,
        top: Array.isArray(server.top) ? server.top : [],
        disk: server.disk == null ? null : { pct: clamp(server.disk), freeGB: server.diskFreeGB ?? null },
        net: { down: server.netDown ?? (net ? net.downlink : null), up: server.netUp ?? null, rtt: net ? net.rtt : null },
        host: server.host || null, os: server.os || null,
        uptime: server.uptime ?? null,
        apps: server.apps || null,
        models: server.models || null,
        fps, heap, battery, online: navigator.onLine,
        cores: navigator.hardwareConcurrency || null,
        gpuLocal: gpu ? gpu.name : null,
      };
    }

    const ramPct = heap ? clamp((heap.used / heap.limit) * 100) : null;
    return {
      source: "device",
      cpu: { pct: deviceCpu(), name: platformLabel() + (navigator.hardwareConcurrency ? " · " + navigator.hardwareConcurrency + " núcleos" : ""), cores: navigator.hardwareConcurrency || null },
      ram: {
        pct: ramPct,
        usedGB: null,
        totalGB: null,
        deviceGB: navigator.deviceMemory || null,
        label: "heap JS",
        name: heap ? `heap JS ${heap.used.toFixed(0)} MB` : "memória JS indisponível",
      },
      gpu: { pct: clamp(100 - Math.min(100, fps / 60 * 100) * 0.85), name: gpu ? gpu.name : "GPU indisponível", note: "carga estimada pela taxa de quadros" },
      vram: { pct: null, usedGB: null, totalGB: null, note: "a VRAM real só vem do backend" },
      temp: { cpu: null, gpu: null },
      procs: null,
      top: [],
      disk: null,
      net: { down: net ? net.downlink : null, up: null, rtt: net ? net.rtt : null },
      host: null, os: null,
      uptime: null,
      apps: null,
      models: null,
      fps, heap, battery, online: navigator.onLine,
      cores: navigator.hardwareConcurrency || null,
      gpuLocal: gpu ? gpu.name : null,
    };
  }

  function push(key, v) {
    const arr = hist[key];
    if (v == null || !isFinite(v)) return;
    arr.push(v);
    if (arr.length > HIST) arr.shift();
  }

  return {
    start() {
      if (running) return;
      running = true;
      lastFrame = 0; frameAcc = 0; frameN = 0;
      rafId = requestAnimationFrame(tick);
    },
    stop() { running = false; cancelAnimationFrame(rafId); },
    setServerTelemetry(d) { server = d || null; },
    gpuName() { return gpu ? gpu.name : null; },
    history(key) { return hist[key] || []; },
    snapshot(force) {
      if (!force && sample && performance.now() - sample.at < 700) return sample.data;
      const data = build();
      push("cpu", data.cpu.pct);
      push("ram", data.ram.pct);
      push("gpu", data.gpu.pct);
      push("vram", data.vram.pct);
      sample = { at: performance.now(), data };
      return data;
    },
  };
}
