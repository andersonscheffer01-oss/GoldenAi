const TAU = Math.PI * 2;
const DEG = Math.PI / 180;

const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;

function mulberry(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createHud(canvas) {
  const ctx = canvas.getContext("2d", { alpha: true });
  const rnd = mulberry(1337);

  let W = 0, H = 0, dpr = 1;
  let mode = "arc";
  let state = "idle";
  let amp = 0, ampNow = 0;
  let accent = [53, 216, 255];
  let accent2 = [255, 176, 46];
  let cx = 0, cy = 0, R = 150;
  // quadro opcional (em pixels) que o app pode definir para encaixar o busto
  // holográfico dentro de uma área específica do layout (painel GOLDEN JARVIS)
  let bustFrame = null;
  let running = false, rafId = 0, prev = 0, elapsed = 0, drawAcc = 0;
  let quality = 1, qualityLock = false, fpsAcc = 0, fpsFrames = 0, fps = 60, drawErrorLogged = false;
  const pulses = [];

  // --------------------------------------------------------- PEÇAS COMUNS --
  // sprites de brilho pré-renderizados (muito mais rápido que milhares de gradientes)
  const spriteCache = new Map();
  function sprite(col) {
    const key = col.join(",");
    let s = spriteCache.get(key);
    if (s) return s;
    const size = 32;
    s = document.createElement("canvas");
    s.width = s.height = size;
    const c = s.getContext("2d");
    const g = c.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, rgba(col, 1));
    g.addColorStop(0.28, rgba(col, 0.55));
    g.addColorStop(0.62, rgba(col, 0.12));
    g.addColorStop(1, rgba(col, 0));
    c.fillStyle = g;
    c.fillRect(0, 0, size, size);
    spriteCache.set(key, s);
    return s;
  }
  function dot(x, y, size, col, alpha) {
    ctx.globalAlpha = Math.max(0, Math.min(1, alpha));
    const sp = sprite(col);
    ctx.drawImage(sp, x - size, y - size, size * 2, size * 2);
    ctx.globalAlpha = 1;
  }

  // rotação 3D compartilhada (yaw/pitch) + projeção em perspectiva
  const rotBuf = { cl: 1, sl: 0, ct: 1, st: 0 };
  function setRot(yaw, pitch) {
    rotBuf.cl = Math.cos(yaw); rotBuf.sl = Math.sin(yaw);
    rotBuf.ct = Math.cos(pitch); rotBuf.st = Math.sin(pitch);
  }
  function rot3(x, y, z) {
    const x1 = x * rotBuf.cl + z * rotBuf.sl;
    const z1 = -x * rotBuf.sl + z * rotBuf.cl;
    const y1 = y * rotBuf.ct - z1 * rotBuf.st;
    const z2 = y * rotBuf.st + z1 * rotBuf.ct;
    return [x1, y1, z2];
  }
  function persp(z, depth) { return 1 / (1.65 - z / depth); }
  function project(x, y, z, depth) {
    const p = persp(z, depth);
    return [x * p, y * p, z, p];
  }

  let dataLines = [];
  function drawDataLines(x, y) {
    if (!dataLines.length) return;
    ctx.save();
    try { ctx.letterSpacing = "1px"; } catch {}
    ctx.font = "11px 'Share Tech Mono', monospace";
    ctx.textAlign = "right";
    ctx.textBaseline = "top";
    for (let i = 0; i < dataLines.length; i++) {
      const s = String(dataLines[i]);
      ctx.fillStyle = rgba(accent, 0.30 - i * 0.03);
      ctx.fillText(s, x, y + i * 15);
    }
    ctx.restore();
  }

  const arcDots = Array.from({ length: 84 }, (_, i) => ({
    ang: rnd() * TAU, rad: 1.04 + rnd() * 0.55, spd: (0.12 + rnd() * 0.5) * (rnd() < 0.5 ? -1 : 1),
    size: 0.8 + rnd() * 2, ph: rnd() * TAU,
  }));
  const motes = Array.from({ length: 110 }, () => ({
    x: (rnd() - 0.5) * 2.6, y: (rnd() - 1.4) * 1.6, z: 0.25 + rnd() * 0.95, spd: 0.05 + rnd() * 0.16, ph: rnd() * TAU,
  }));
  const nodes = Array.from({ length: 96 }, () => {
    const u = rnd() * 2 - 1, th = rnd() * TAU, s = Math.sqrt(1 - u * u);
    return { x: s * Math.cos(th), y: u, z: s * Math.sin(th), spd: 0.15 + rnd() * 0.7, ph: rnd() * TAU, size: 0.7 + rnd() * 1.5 };
  });
  const blips = Array.from({ length: 11 }, (_, i) => ({
    ang: rnd() * TAU, rad: 0.25 + rnd() * 0.72, id: String.fromCharCode(65 + i), hot: rnd() < 0.35,
  }));
  const sweepWedge = 26;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    W = w; H = h;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // redesenha na hora: trocar o tamanho do canvas zera o bitmap, e se o
    // requestAnimationFrame estiver suspenso a tela ficaria em branco
    if (running) {
      ctx.save();
      ctx.globalCompositeOperation = "source-over";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const d = modeDraw[mode] || drawArc;
      try { d(elapsed); } catch { /* o próximo frame tenta de novo */ }
      ctx.restore();
    }
  }

  function stateSpeed() {
    if (state === "listening") return 2.1;
    if (state === "thinking") return 3.1;
    if (state === "speaking") return 1.5;
    if (state === "executing") return 2.6;
    if (state === "alert") return 4;
    return 1;
  }

  function speedMul() { return stateSpeed(); }

  function glow(x, y, rad, col, alpha) {
    const g = ctx.createRadialGradient(x, y, 0, x, y, rad);
    g.addColorStop(0, rgba(col, alpha));
    g.addColorStop(0.45, rgba(col, alpha * 0.35));
    g.addColorStop(1, rgba(col, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, rad, 0, TAU);
    ctx.fill();
  }

  function ring(radius, from, to, width, alpha, col) {
    ctx.beginPath();
    ctx.strokeStyle = rgba(col || accent, alpha);
    ctx.lineWidth = width;
    ctx.arc(0, 0, radius, from, to);
    ctx.stroke();
  }

  // ------------------------------------------------------------------ ARC --
  function drawArc(t) {
    const sm = speedMul();
    const a = ampNow;
    ctx.save();
    ctx.translate(cx, cy);

    ctx.globalCompositeOperation = "lighter";

    const pulse = 1 + Math.sin(t * 1.5) * 0.012;
    const r0 = R * pulse;

    glow(0, 0, r0 * 0.95 * (1 + a * 0.3), accent, 0.16 + a * 0.22);

    // tick ring
    for (let i = 0; i < 96; i++) {
      const ang = (i / 96) * TAU + t * 0.05;
      const long = i % 8 === 0;
      const len = long ? r0 * 0.075 : r0 * 0.032;
      const rr = r0 * 1.62;
      ctx.beginPath();
      ctx.strokeStyle = rgba(accent, long ? 0.5 : 0.22);
      ctx.lineWidth = long ? 1.6 : 1;
      ctx.moveTo(Math.cos(ang) * rr, Math.sin(ang) * rr);
      ctx.lineTo(Math.cos(ang) * (rr + len), Math.sin(ang) * (rr + len));
      ctx.stroke();
    }

    // rotating arc segments
    const arcs = [
      { r: 1.52, w: 2.4, spd: 0.34, a: 0.75, spans: [[0, 0.7], [1.6, 2.05], [3.4, 3.9]] },
      { r: 1.22, w: 1.6, spd: -0.55, a: 0.6, spans: [[0.4, 1.5], [2.6, 3.5]] },
      { r: 0.98, w: 3.2, spd: 0.9, a: 0.45, spans: [[0.1, 0.55], [1.2, 1.9], [2.4, 3.05]] },
    ];
    for (const seg of arcs) {
      for (const [s, e] of seg.spans) {
        ring(r0 * seg.r, s + t * seg.spd * sm, e + t * seg.spd * sm, seg.w, seg.a * (1 - a * 0.15), accent);
      }
    }

    // dashed inner ring
    ctx.save();
    ctx.rotate(t * 0.7 * sm);
    ctx.setLineDash([r0 * 0.04, r0 * 0.035]);
    ring(r0 * 0.82, 0, TAU, 1.4, 0.35 * (1 + a), accent2);
    ctx.restore();

    // expanding pulse rings
    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i];
      p.t += 0.016 * sm;
      const rr = r0 * (0.4 + p.t * 1.5);
      const alpha = Math.max(0, 0.5 - p.t * 0.42);
      if (alpha <= 0) { pulses.splice(i, 1); continue; }
      ring(rr, 0, TAU, 2 - p.t, alpha, accent);
    }

    // core
    const coreR = r0 * 0.33 * (1 + a * 0.22 + Math.sin(t * 5) * 0.012);
    glow(0, 0, coreR * 3.1, accent, 0.3 + a * 0.3);
    ctx.beginPath();
    ctx.strokeStyle = rgba(accent2, 0.9);
    ctx.lineWidth = 2.2;
    ctx.arc(0, 0, coreR * 1.34, 0, TAU);
    ctx.stroke();

    ctx.save();
    ctx.rotate(t * 0.42 * sm);
    ctx.beginPath();
    ctx.moveTo(0, -coreR);
    ctx.lineTo(coreR * 0.92, coreR * 0.66);
    ctx.lineTo(-coreR * 0.92, coreR * 0.66);
    ctx.closePath();
    const cg = ctx.createLinearGradient(0, -coreR, 0, coreR);
    cg.addColorStop(0, rgba(accent, 0.95));
    cg.addColorStop(1, rgba(accent2, 0.7));
    ctx.fillStyle = cg;
    ctx.shadowColor = rgba(accent, 0.9);
    ctx.shadowBlur = 26;
    ctx.fill();
    ctx.restore();

    // orbiting particles
    const n = Math.round(arcDots.length * quality);
    for (let i = 0; i < n; i++) {
      const d = arcDots[i];
      const ang = d.ang + t * d.spd * sm * 0.6;
      const rr = r0 * (d.rad + Math.sin(t * 1.1 + d.ph) * 0.03);
      const x = Math.cos(ang) * rr;
      const y = Math.sin(ang) * rr * 0.98;
      const al = 0.25 + 0.5 * Math.abs(Math.sin(t * 1.4 + d.ph));
      ctx.beginPath();
      ctx.fillStyle = rgba(i % 5 === 0 ? accent2 : accent, al);
      ctx.arc(x, y, d.size * (1 + a * 0.6), 0, TAU);
      ctx.fill();
    }

    // energy filaments
    for (let i = 0; i < 6; i++) {
      const ang = t * 0.5 + (i / 6) * TAU;
      const len = r0 * (1.1 + Math.sin(t * 2.2 + i) * 0.16);
      ctx.beginPath();
      const fg = ctx.createLinearGradient(0, 0, Math.cos(ang) * len, Math.sin(ang) * len);
      fg.addColorStop(0, rgba(accent, 0));
      fg.addColorStop(0.6, rgba(accent, 0.28 + a * 0.3));
      fg.addColorStop(1, rgba(accent2, 0));
      ctx.strokeStyle = fg;
      ctx.lineWidth = 1.4;
      ctx.moveTo(Math.cos(ang) * coreR, Math.sin(ang) * coreR);
      ctx.lineTo(Math.cos(ang) * len, Math.sin(ang) * len);
      ctx.stroke();
    }

    ctx.restore();
  }

  // ----------------------------------------------------------------- HOLO --
  function drawHolo(t) {
    const sm = speedMul();
    const a = ampNow;
    const rotY = t * 0.22 * Math.min(sm, 2.4);
    const tiltX = -0.34 + Math.sin(t * 0.13) * 0.07;
    const rG = R * 1.0 * (1 + a * 0.06);

    ctx.save();
    ctx.translate(cx, cy);
    ctx.globalCompositeOperation = "lighter";

    const proj = (latDeg, lonDeg) => {
      const la = latDeg * DEG, lo = lonDeg * DEG + rotY;
      const x = Math.cos(la) * Math.sin(lo);
      const y0 = Math.sin(la);
      const z0 = Math.cos(la) * Math.cos(lo);
      const y = y0 * Math.cos(tiltX) - z0 * Math.sin(tiltX);
      const z = y0 * Math.sin(tiltX) + z0 * Math.cos(tiltX);
      return { x: x * rG, y: y * rG, z };
    };

    glow(0, 0, rG * 1.15, accent, 0.1 + a * 0.12);

    // meridians
    for (let m = 0; m < 12; m++) {
      const lon = m * 30;
      const pts = [];
      for (let s = -90; s <= 90; s += 10) pts.push(proj(s, lon));
      for (let i = 0; i < pts.length - 1; i++) {
        const zAvg = (pts[i].z + pts[i + 1].z) / 2;
        const front = (zAvg + 1) / 2;
        ctx.beginPath();
        ctx.strokeStyle = rgba(accent, 0.06 + front * 0.34);
        ctx.lineWidth = 0.8 + front * 0.9;
        ctx.moveTo(pts[i].x, pts[i].y);
        ctx.lineTo(pts[i + 1].x, pts[i + 1].y);
        ctx.stroke();
      }
    }
    // parallels
    for (let p = -60; p <= 60; p += 30) {
      const pts = [];
      for (let lon = 0; lon <= 360; lon += 10) pts.push(proj(p, lon));
      for (let i = 0; i < pts.length - 1; i++) {
        const zAvg = (pts[i].z + pts[i + 1].z) / 2;
        const front = (zAvg + 1) / 2;
        ctx.beginPath();
        ctx.strokeStyle = rgba(accent, 0.05 + front * 0.26);
        ctx.lineWidth = 0.7 + front * 0.8;
        ctx.moveTo(pts[i].x, pts[i].y);
        ctx.lineTo(pts[i + 1].x, pts[i + 1].y);
        ctx.stroke();
      }
    }
    // nodes on the grid
    for (let m = 0; m < 12; m++) {
      for (let p = -60; p <= 60; p += 30) {
        const pt = proj(p, m * 30);
        const front = (pt.z + 1) / 2;
        ctx.beginPath();
        ctx.fillStyle = rgba(accent2, 0.1 + front * 0.55);
        ctx.arc(pt.x, pt.y, 1.1 + front * 1.5, 0, TAU);
        ctx.fill();
      }
    }

    // equator scan ring travelling up and down
    const scanY = Math.sin(t * 0.55) * rG * 0.82;
    const latAt = Math.asin(Math.max(-1, Math.min(1, scanY / rG))) / DEG;
    const scanPts = [];
    for (let lon = 0; lon <= 360; lon += 8) scanPts.push(proj(latAt, lon));
    ctx.beginPath();
    ctx.strokeStyle = rgba(accent2, 0.5);
    ctx.lineWidth = 1.6;
    scanPts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    ctx.stroke();

    // rising data motes
    const n = Math.round(motes.length * quality);
    for (let i = 0; i < n; i++) {
      const mo = motes[i];
      const py = ((mo.y + t * mo.spd * -1) % 1.9 + 1.9) % 1.9 - 0.95;
      const px = mo.x * R * 0.55 + Math.sin(t * 0.8 + mo.ph) * 6;
      const sy = cy + py * R * 1.5;
      const alpha = (1 - Math.abs(py)) * 0.55 * mo.z;
      if (sy < 0 || sy > H) continue;
      ctx.beginPath();
      ctx.fillStyle = rgba(i % 4 === 0 ? accent2 : accent, Math.max(0, alpha));
      ctx.fillRect(cx + px, sy, 1.6, 1.6 + mo.z * 4);
    }

    // sweep ring
    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i];
      p.t += 0.008;
      const rr = rG * (0.2 + p.t * 1.4);
      const alpha = Math.max(0, 0.4 - p.t * 0.35);
      if (alpha <= 0) { pulses.splice(i, 1); continue; }
      ctx.save();
      ctx.scale(1, 0.36);
      ring(rr, 0, TAU, 1.8 - p.t, alpha, accent);
      ctx.restore();
    }

    ctx.restore();
  }

  // --------------------------------------------------------------- NEURAL --
  function drawNeural(t) {
    const sm = Math.min(speedMul(), 2.2);
    const a = ampNow;
    const rotY = t * 0.16 * sm;
    const tiltX = -0.22;
    const base = R * 0.95;

    ctx.save();
    ctx.translate(cx, cy);
    ctx.globalCompositeOperation = "lighter";
    glow(0, 0, R * 1.1, accent, 0.12 + a * 0.2);

    const n = Math.max(20, Math.round(nodes.length * quality));
    const pos = [];
    for (let i = 0; i < n; i++) {
      const nd = nodes[i];
      const wob = 1 + Math.sin(t * nd.spd + nd.ph) * 0.14 + a * 0.07;
      const x0 = nd.x * base * wob, y0 = nd.y * base * wob, z0 = nd.z * base * wob;
      const lo = rotY, cl = Math.cos(lo), sl = Math.sin(lo);
      const x1 = x0 * cl + z0 * sl;
      const z1 = -x0 * sl + z0 * cl;
      const y1 = y0 * Math.cos(tiltX) - z1 * Math.sin(tiltX);
      const z2 = y0 * Math.sin(tiltX) + z1 * Math.cos(tiltX);
      const persp = 1 / (1.7 - z2 / (base * 2.2));
      pos.push({ x: x1 * persp, y: y1 * persp, z: z2, s: nd.size * persp * 1.1 });
    }

    // connections
    const step = 13;
    for (let i = 0; i < n; i++) {
      const A = pos[i];
      const lim = Math.min(n, i + step);
      for (let j = i + 1; j < lim; j++) {
        const B = pos[j];
        const dx = A.x - B.x, dy = A.y - B.y;
        const d2 = dx * dx + dy * dy;
        const maxD = base * 0.62;
        if (d2 > maxD * maxD) continue;
        const closeness = 1 - Math.sqrt(d2) / maxD;
        const front = ((A.z + B.z) / 2 / base + 1) / 2;
        ctx.beginPath();
        ctx.strokeStyle = rgba(accent, closeness * 0.28 * (0.35 + front * 0.65) * (1 + a * 0.7));
        ctx.lineWidth = 0.55 + closeness * 0.9;
        ctx.moveTo(A.x, A.y);
        ctx.lineTo(B.x, B.y);
        ctx.stroke();
      }
    }

    // nodes
    for (let i = 0; i < n; i++) {
      const p = pos[i];
      const front = (p.z / base + 1) / 2;
      const alpha = 0.18 + front * 0.7;
      ctx.beginPath();
      ctx.fillStyle = rgba(i % 7 === 0 ? accent2 : accent, alpha);
      ctx.arc(p.x, p.y, p.s * (1 + a * 0.8), 0, TAU);
      ctx.fill();
    }

    // spark pulses travelling outward
    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i];
      p.t += 0.02 * sm;
      const rr = base * (0.15 + p.t * 1.15);
      const alpha = Math.max(0, 0.35 - p.t * 0.3);
      if (alpha <= 0) { pulses.splice(i, 1); continue; }
      const k = Math.floor(p.t * 40);
      const A = pos[(k * 7) % n], B = pos[(k * 13 + 5) % n];
      if (!A || !B) continue;
      ctx.beginPath();
      ctx.strokeStyle = rgba(accent2, alpha);
      ctx.lineWidth = 1.8;
      ctx.moveTo(A.x, A.y);
      ctx.lineTo(B.x, B.y);
      ctx.stroke();
      glow(B.x, B.y, 10, accent2, alpha);
      void rr;
    }

    ctx.restore();
  }

  // ------------------------------------------------------------- SENTINEL --
  function drawSentinel(t) {
    const sm = speedMul();
    const a = ampNow;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.globalCompositeOperation = "lighter";
    const rMax = R * 1.12;

    // radar range rings
    for (const f of [0.42, 0.72, 1.0]) {
      ring(rMax * f, 0, TAU, 1, 0.22, accent);
    }
    // crosshair
    ctx.beginPath();
    ctx.strokeStyle = rgba(accent, 0.28);
    ctx.lineWidth = 1;
    ctx.moveTo(-rMax, 0); ctx.lineTo(-rMax * 0.18, 0);
    ctx.moveTo(rMax * 0.18, 0); ctx.lineTo(rMax, 0);
    ctx.moveTo(0, -rMax); ctx.lineTo(0, -rMax * 0.18);
    ctx.moveTo(0, rMax * 0.18); ctx.lineTo(0, rMax);
    ctx.stroke();

    // sweeping wedge
    const sweep = (t * 1.1 * Math.min(sm, 2)) % TAU;
    for (let i = 0; i < sweepWedge; i++) {
      const f = i / sweepWedge;
      const from = sweep - f * 0.85;
      ctx.beginPath();
      ctx.fillStyle = rgba(accent, 0.16 * (1 - f) * (1 - f));
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, rMax, from, from + 0.06);
      ctx.closePath();
      ctx.fill();
    }

    // blips with fade relative to sweep
    for (const b of blips) {
      let d = ((sweep - b.ang) % TAU + TAU) % TAU;
      const fade = Math.max(0, 1 - d / 2.4);
      if (fade <= 0.02) continue;
      const x = Math.cos(b.ang) * rMax * b.rad;
      const y = Math.sin(b.ang) * rMax * b.rad;
      const col = b.hot ? accent2 : accent;
      glow(x, y, 12 * fade * (1 + a), col, 0.5 * fade);
      ctx.beginPath();
      ctx.fillStyle = rgba(col, 0.9 * fade);
      ctx.arc(x, y, (b.hot ? 2.6 : 1.8) * (1 + a * 0.5), 0, TAU);
      ctx.fill();
      if (b.hot && fade > 0.5) {
        ctx.font = "9px 'Share Tech Mono', monospace";
        ctx.fillStyle = rgba(col, 0.75 * fade);
        ctx.fillText(b.id, x + 7, y - 5);
      }
    }

    // reticle brackets around the core
    const br = rMax * 1.22;
    ctx.strokeStyle = rgba(accent2, 0.55 + a * 0.3);
    ctx.lineWidth = 2;
    const arm = br * 0.22;
    const corners = [[-1, -1], [1, -1], [-1, 1], [1, 1]];
    for (const [sx, sy] of corners) {
      const x = sx * br, y = sy * br;
      ctx.beginPath();
      ctx.moveTo(x, y - sy * arm);
      ctx.lineTo(x, y);
      ctx.lineTo(x - sx * arm, y);
      ctx.stroke();
    }

    // core glow pulse
    glow(0, 0, R * 0.55 * (1 + a * 0.4), accent, 0.2 + a * 0.25);

    // waveform across the core
    const wN = 64;
    ctx.beginPath();
    ctx.strokeStyle = rgba(accent, 0.75);
    ctx.lineWidth = 1.5;
    for (let i = 0; i <= wN; i++) {
      const p = i / wN;
      const x = (p - 0.5) * R * 1.3;
      const env = Math.sin(p * Math.PI);
      const y = Math.sin(p * 18 + t * 4 * sm) * env * R * (0.06 + a * 0.22);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.stroke();

    // vertical sweep line
    const scanX = ((t * 90 * Math.min(sm, 1.6)) % (W + 200)) - 100;
    const lg = ctx.createLinearGradient(scanX - 60, 0, scanX + 60, 0);
    lg.addColorStop(0, rgba(accent, 0));
    lg.addColorStop(0.5, rgba(accent, 0.16));
    lg.addColorStop(1, rgba(accent, 0));
    ctx.fillStyle = lg;
    ctx.fillRect(scanX - 60 - cx, 0 - cy, 120, H);

    ctx.restore();
  }

  // ------------------------------------------------- NÚCLEO / HOLOGRAMA ----
  function hashStr(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }

  // filamentos da rede neural interna do núcleo
  const filaments = Array.from({ length: 200 }, () => {
    const dir = () => {
      const u = rnd() * 2 - 1, th = rnd() * TAU, s = Math.sqrt(1 - u * u);
      return [s * Math.cos(th), u, s * Math.sin(th)];
    };
    return { p: dir(), q: dir(), bow: 0.08 + rnd() * 0.5, ph: rnd() * TAU, sp: 0.25 + rnd() * 0.95, w: 0.5 + rnd() * 0.85, hot: rnd() < 0.08 };
  });

  const hostNodes = [];
  let nodeHoverId = "";
  function setHostNodes(list) {
    hostNodes.length = 0;
    const arr = (list || []).slice(0, 15);
    for (let i = 0; i < arr.length; i++) {
      const n = arr[i];
      const h = hashStr(String(n.id ?? n.label ?? i));
      const step = TAU / Math.max(1, arr.length);
      const ang = -Math.PI * 0.5 + i * step + (((h % 500) / 500) - 0.5) * step * 0.7;
      const rf = 1 + ((((h >> 7) % 500) / 500) - 0.5) * 0.26;
      hostNodes.push({ ...n, ang, rf, ph: (((h >> 3) % 500) / 500) * TAU });
    }
  }
  const nodeHits = [];

  // -------------------------------------------------------- NÚCLEO NEURAL --
  function drawNucleo(t) {
    const sm = Math.min(speedMul(), 2.2);
    const a = ampNow;
    const base = R * 0.9;
    const ringR = base * 1.34;
    setRot(t * 0.20 * sm, -0.16);

    ctx.save();
    ctx.translate(cx, cy);
    ctx.globalCompositeOperation = "lighter";

    glow(0, 0, base * 2.1, accent, 0.09 + a * 0.14);
    glow(0, 0, ringR * 1.25, accent2, 0.07 + a * 0.10);

    // ---- filamentos internos (rede neural) ----
    const stride = Math.max(1, Math.round(1 / (0.35 + quality * 0.65)));
    const depth = base * 2.2;
    for (let i = 0; i < filaments.length; i += stride) {
      const f = filaments[i];
      const A = rot3(f.p[0], f.p[1], f.p[2]);
      const B = rot3(f.q[0], f.q[1], f.q[2]);
      const mx = (f.p[0] + f.q[0]) * 0.5, my = (f.p[1] + f.q[1]) * 0.5, mz = (f.p[2] + f.q[2]) * 0.5;
      const ml = Math.hypot(mx, my, mz) || 1;
      const kk = 0.42 + f.bow;
      const C = rot3((mx / ml) * kk, (my / ml) * kk, (mz / ml) * kk);
      const a1 = project(A[0] * base, A[1] * base, A[2] * base, depth);
      const a2 = project(B[0] * base, B[1] * base, B[2] * base, depth);
      const a3 = project(C[0] * base, C[1] * base, C[2] * base, depth);
      const front = ((A[2] + B[2]) * 0.5 + 1) * 0.5;
      const puls = 0.45 + 0.55 * Math.abs(Math.sin(t * f.sp + f.ph));
      const alpha = (0.06 + front * 0.30) * puls * (1 + a * 0.9);
      if (alpha < 0.012) continue;
      ctx.beginPath();
      ctx.strokeStyle = rgba(f.hot ? accent2 : [180, 226, 255], alpha);
      ctx.lineWidth = (0.45 + front * 1.0) * f.w;
      ctx.moveTo(a1[0], a1[1]);
      ctx.quadraticCurveTo(a3[0], a3[1], a2[0], a2[1]);
      ctx.stroke();
      if (f.hot) dot(a2[0], a2[1], 2.6 * a2[3], accent2, alpha * 2.2);
    }

    // ---- ponto brilhante nos nós da malha ----
    for (let i = 0; i < filaments.length; i += stride * 3) {
      const p = filaments[i].p;
      const A = rot3(p[0], p[1], p[2]);
      const s = project(A[0] * base, A[1] * base, A[2] * base, depth);
      const front = (A[2] + 1) * 0.5;
      dot(s[0], s[1], (1.6 + front * 2.2) * s[3], i % 5 === 0 ? accent2 : [200, 240, 255], 0.10 + front * 0.34);
    }

    // ---- núcleo de energia ----
    const coreR = base * (0.30 + a * 0.07);
    glow(0, 0, coreR * 2.6, [255, 232, 180], 0.16 + a * 0.22);
    glow(0, 0, coreR * 1.15, [255, 255, 255], 0.34 + a * 0.3);
    for (let i = 0; i < 5; i++) {
      const rr = coreR * (0.55 + i * 0.30);
      const sp = (i % 2 ? -1 : 1) * (0.5 + i * 0.22) * sm;
      ctx.beginPath();
      ctx.strokeStyle = rgba(i % 2 ? accent : accent2, 0.30 - i * 0.04);
      ctx.lineWidth = 1.5 - i * 0.15;
      ctx.ellipse(0, 0, rr, rr * 0.34, t * sp * 0.25, t * sp, t * sp + 2.2 + i * 0.5);
      ctx.stroke();
    }

    // ---- anel dourado externo ----
    ctx.lineWidth = 7;
    ctx.strokeStyle = rgba(accent2, 0.16 + a * 0.10);
    ctx.beginPath(); ctx.arc(0, 0, ringR, 0, TAU); ctx.stroke();
    ctx.lineWidth = 2.4;
    ctx.strokeStyle = rgba(accent2, 0.72);
    ctx.beginPath(); ctx.arc(0, 0, ringR, 0, TAU); ctx.stroke();
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba([255, 240, 205], 0.85);
    ctx.beginPath(); ctx.arc(0, 0, ringR * 1.012, 0, TAU); ctx.stroke();
    // segmentos girando por cima do anel
    const segs = [[0.15, 0.75], [1.35, 1.95], [2.7, 3.35], [4.4, 5.1]];
    ctx.lineWidth = 5;
    for (let i = 0; i < segs.length; i++) {
      const s0 = segs[i][0] + t * (0.05 + i * 0.012) * sm;
      ctx.beginPath();
      ctx.strokeStyle = rgba([255, 236, 190], 0.55);
      ctx.arc(0, 0, ringR, s0, s0 + (segs[i][1] - segs[i][0]));
      ctx.stroke();
    }
    // ticks
    for (let i = 0; i < 72; i++) {
      const ang = (i / 72) * TAU - t * 0.04 * sm;
      const lng = i % 6 === 0;
      const r0 = ringR * 1.035, r1 = ringR * (lng ? 1.10 : 1.065);
      ctx.beginPath();
      ctx.strokeStyle = rgba(accent2, lng ? 0.7 : 0.28);
      ctx.lineWidth = lng ? 1.7 : 1;
      ctx.moveTo(Math.cos(ang) * r0, Math.sin(ang) * r0);
      ctx.lineTo(Math.cos(ang) * r1, Math.sin(ang) * r1);
      ctx.stroke();
    }
    // anel interno fino
    ctx.lineWidth = 1.1;
    ctx.strokeStyle = rgba(accent, 0.42);
    ctx.beginPath(); ctx.arc(0, 0, ringR * 0.87, 0, TAU); ctx.stroke();

    // ---- nós rotulados ligados ao núcleo ----
    const labels = W >= 620 && H >= 520;
    const ex = Math.min(W * 0.41, base * 2.5, W * 0.5 - (labels ? 88 : 30));
    const ey = Math.min(H * 0.37, base * 2.15, H * 0.5 - 148);
    const fs = W < 900 ? 10 : 11;
    nodeHits.length = 0;
    try { ctx.letterSpacing = W < 900 ? "0.5px" : "1px"; } catch {}
    for (let i = 0; i < hostNodes.length; i++) {
      const nd = hostNodes[i];
      const wob = 1 + Math.sin(t * 0.5 + nd.ph) * 0.025;
      const nx = Math.cos(nd.ang) * ex * nd.rf * wob;
      const ny = Math.max(86 - cy, Math.min(H - 118 - cy, Math.sin(nd.ang) * ey * nd.rf * wob));
      const ang = Math.atan2(ny, nx);
      const sx = Math.cos(ang) * ringR, sy = Math.sin(ang) * ringR;
      const side = nx >= 0 ? 1 : -1;
      const kx = nx - side * (labels ? 30 : 16);
      const hover = nd.id === nodeHoverId;
      const live = nd.on !== false;

      // conector em cotovelo
      ctx.beginPath();
      ctx.strokeStyle = rgba(hover ? accent2 : accent, hover ? 0.6 : live ? 0.26 : 0.12);
      ctx.lineWidth = hover ? 1.5 : 1;
      ctx.moveTo(nx, ny);
      ctx.lineTo(kx, ny);
      ctx.lineTo(sx, sy);
      ctx.stroke();
      // arco de encaixe no anel
      ctx.beginPath();
      ctx.strokeStyle = rgba(accent, hover ? 0.7 : 0.3);
      ctx.lineWidth = hover ? 2 : 1.4;
      ctx.arc(0, 0, ringR, ang - 0.055, ang + 0.055);
      ctx.stroke();

      // pulso viajando do núcleo até o nó
      const seg1 = Math.abs(kx - nx) || 1;
      const seg2 = Math.hypot(sx - kx, sy - ny);
      const d = ((t * 0.32 * sm + nd.ph) % 1) * (seg1 + seg2);
      let px1, py1;
      if (d <= seg1) { px1 = sx + (kx - sx) * 0 + (kx - nx) * 0; px1 = nx + (kx - nx) * (1 - d / seg1); py1 = ny; }
      else { const k2 = (d - seg1) / (seg2 || 1); px1 = kx + (sx - kx) * k2; py1 = ny + (sy - ny) * k2; }
      dot(px1, py1, hover ? 4.4 : 3.2, accent2, hover ? 0.85 : 0.5);

      // marcador
      const ms = hover ? 6.5 : 5;
      ctx.save();
      ctx.translate(nx, ny);
      ctx.rotate(Math.PI / 4);
      ctx.beginPath();
      ctx.fillStyle = rgba(live ? accent : [120, 130, 140], hover ? 0.95 : 0.55);
      ctx.fillRect(-ms / 2, -ms / 2, ms, ms);
      ctx.strokeStyle = rgba(accent2, hover ? 0.9 : 0.45);
      ctx.lineWidth = 1;
      ctx.strokeRect(-ms / 2 - 2.5, -ms / 2 - 2.5, ms + 5, ms + 5);
      ctx.restore();
      if (hover) glow(nx, ny, 22, accent2, 0.35);

      // rótulo
      if (labels) {
        ctx.font = (hover ? "600 " : "") + fs + "px 'Share Tech Mono', monospace";
        ctx.textAlign = side >= 0 ? "left" : "right";
        ctx.textBaseline = "middle";
        ctx.fillStyle = rgba(hover ? [255, 236, 190] : [206, 236, 255], hover ? 0.98 : 0.72);
        ctx.fillText(String(nd.label || nd.id || "").toUpperCase(), nx + side * 13, ny - 5);
        if (nd.stat) {
          ctx.font = (fs - 1.5) + "px 'Share Tech Mono', monospace";
          ctx.fillStyle = rgba(live ? accent : [130, 140, 150], 0.6);
          ctx.fillText(String(nd.stat).toUpperCase(), nx + side * 13, ny + 8);
        }
      }

      nodeHits.push({ id: nd.id, label: nd.label, cmd: nd.cmd, on: live, x: cx + nx, y: cy + ny, r: labels ? 34 : 22 });
    }

    drawDataLines(W - 22, 84);
    ctx.restore();
  }

  // ------------------------------------------------------------- HOLOGRAMA --
  // Busto humano gerado por VARREDURA DE PERFIL: uma tabela [y → meia-largura,
  // meia-profundidade, deslocamento frontal] define a silhueta (crânio, maxilar,
  // pescoço estreito, trapézio inclinado, deltoides, peito e tronco). As
  // isolinhas horizontais do SDF desenham a anatomia; os detalhes (visopr,
  // nariz, clavículas, mandíbula) são peças extras somadas ao corpo.
  const bust = (() => {
    // Proporções humanas reais (1 unidade ≈ 73 cm): cabeça 0,33 de altura × 0,21
    // de largura; pescoço curto (0,30 da cabeça); ombros 2,9× a largura da
    // cabeça, com o ponto mais largo logo abaixo da linha do trapézio; o busto
    // é cortado no peito (base reta, sem fechamento arredondado).
    const PROF = [
      [-0.932, 0.026, 0.028, 0.000],
      [-0.910, 0.058, 0.062, 0.002],
      [-0.885, 0.082, 0.088, 0.004],
      [-0.855, 0.096, 0.108, 0.006],
      [-0.820, 0.103, 0.124, 0.008],
      [-0.780, 0.105, 0.132, 0.012],
      [-0.740, 0.104, 0.136, 0.016],
      [-0.700, 0.100, 0.140, 0.020],
      [-0.668, 0.095, 0.142, 0.022],
      [-0.640, 0.088, 0.134, 0.020],
      [-0.618, 0.070, 0.120, 0.016],
      [-0.600, 0.058, 0.108, 0.012],
      [-0.575, 0.054, 0.088, 0.008],
      [-0.548, 0.052, 0.078, 0.006],
      [-0.522, 0.057, 0.076, 0.006],
      [-0.500, 0.071, 0.082, 0.008],
      [-0.480, 0.098, 0.092, 0.010],
      [-0.460, 0.140, 0.104, 0.012],
      [-0.440, 0.190, 0.116, 0.012],
      [-0.420, 0.235, 0.126, 0.012],
      [-0.400, 0.272, 0.134, 0.012],
      [-0.380, 0.295, 0.140, 0.010],
      [-0.355, 0.305, 0.142, 0.008],
      [-0.300, 0.298, 0.146, 0.006],
      [-0.230, 0.276, 0.144, 0.004],
      [-0.150, 0.256, 0.138, 0.002],
      [-0.070, 0.238, 0.130, 0.000],
      [0.000, 0.222, 0.122, 0.000],
    ];
    const Y0 = PROF[0][0], Y1 = PROF[PROF.length - 1][0];
    // interpolação linear da tabela
    const at = (y) => {
      const yy = Math.max(Y0, Math.min(Y1, y));
      let i = 0;
      while (i < PROF.length - 2 && PROF[i + 1][0] < yy) i++;
      const a = PROF[i], b = PROF[i + 1];
      const u = (yy - a[0]) / (b[0] - a[0] || 1);
      return [
        a[1] + (b[1] - a[1]) * u,
        a[2] + (b[2] - a[2]) * u,
        a[3] + (b[3] - a[3]) * u,
      ];
    };
    // corpo = sólido de revolução elíptica em torno da tabela
    const body = (x, y, z) => {
      if (y < Y0 - 0.012 || y > Y1) return 1e3;
      const p = at(y);
      // arredonda apenas o topo da cabeça; a base é um CORTE RETO no peito
      let cap = 1;
      if (y < Y0) cap = Math.sqrt(Math.max(0, 1 - ((Y0 - y) / 0.046) ** 2));
      const ex = p[0] * cap, ez = p[1] * cap, cz = p[2];
      const r = Math.hypot(x / (ex || 1e-4), (z - cz) / (ez || 1e-4));
      return (r - 1) * Math.min(ex, ez);
    };
    const ell = (x, y, z, ox, oy, oz, rx, ry, rz) => {
      const qx = (x - ox) / rx, qy = (y - oy) / ry, qz = (z - oz) / rz;
      const k0 = Math.hypot(qx, qy, qz);
      const k1 = Math.hypot(qx / rx, qy / ry, qz / rz);
      return k1 === 0 ? -Math.min(rx, ry, rz) : (k0 * (k0 - 1)) / k1;
    };
    const cap = (x, y, z, ax, ay, az, bx, by, bz, r) => {
      const pax = x - ax, pay = y - ay, paz = z - az;
      const bax = bx - ax, bay = by - ay, baz = bz - az;
      const h = Math.max(0, Math.min(1, (pax * bax + pay * bay + paz * baz) / (bax * bax + bay * bay + baz * baz)));
      return Math.hypot(pax - bax * h, pay - bay * h, paz - baz * h) - r;
    };
    // y cresce para baixo, z positivo = frente do rosto
    const sd = (x, y, z) => {
      let d = body(x, y, z);
      d = Math.min(d, ell(x, y, z, 0, -0.620, 0.116, 0.046, 0.030, 0.050));      // queixo/maxilar
      d = Math.min(d, ell(x, y, z, 0, -0.742, 0.146, 0.014, 0.030, 0.030));      // nariz
      d = Math.min(d, ell(x, y, z, -0.104, -0.760, 0.000, 0.020, 0.040, 0.026));  // orelha esq.
      d = Math.min(d, ell(x, y, z, 0.104, -0.760, 0.000, 0.020, 0.040, 0.026));   // orelha dir.
      d = Math.min(d, ell(x, y, z, -0.046, -0.812, 0.140, 0.044, 0.014, 0.014));  // sobrancelha esq.
      d = Math.min(d, ell(x, y, z, 0.046, -0.812, 0.140, 0.044, 0.014, 0.014));   // sobrancelha dir.
      d = Math.min(d, cap(x, y, z, -0.026, -0.470, 0.076, -0.196, -0.386, 0.050, 0.016)); // clavícula esq.
      d = Math.min(d, cap(x, y, z, 0.026, -0.470, 0.076, 0.196, -0.386, 0.050, 0.016));  // clavícula dir.
      return d;
    };
    // energia dourada: rosto e centro do peito
    const inFace = (x, y, z) => z > 0.088 && Math.abs(x) < 0.080 && y > -0.850 && y < -0.650;
    const inChest = (x, y, z) => z > 0.072 && Math.abs(x) < 0.100 && y > -0.312 && y < -0.108;
    const gold = (x, y, z) => inFace(x, y, z) || inChest(x, y, z);

    // ---- casca de partículas sobre a superfície ----
    const shell = [], inner = [];
    let tries = 0;
    while (shell.length < 5200 && tries < 3200000) {
      tries++;
      const x = (rnd() * 2 - 1) * 0.34;
      const y = -0.960 + rnd() * 1.020;
      const z = (rnd() * 2 - 1) * 0.180;
      const d = sd(x, y, z);
      if (d < -0.014 || d > 0.006) continue;
      const g = gold(x, y, z);
      const fade = 0.55 + 0.45 * Math.min(1, Math.max(0, (0.000 - y) / 0.170));
      const band = z > 0.02 && Math.abs(y + 0.782) < 0.017 && Math.abs(x) < 0.098;   // não sujar o visor
      shell.push({
        x, y, z, gold: g, fade, band,
        rim: g ? 0 : 1 - Math.min(1, Math.abs(z) / 0.120),
        size: 0.55 + rnd() * 1.05,
        ph: rnd() * TAU, sp: 0.5 + rnd() * 2.2,
        bright: rnd() < 0.05 ? 1.9 : 1,
      });
    }
    while (inner.length < 460 && tries < 5200000) {
      tries++;
      const x = (rnd() * 2 - 1) * 0.100;
      const y = -0.780 + rnd() * 0.800;
      const z = -0.020 + rnd() * 0.170;
      if (sd(x, y, z) > -0.018) continue;
      inner.push({ x, y, z, size: 0.5 + rnd() * 0.9, ph: rnd() * TAU, sp: 0.8 + rnd() * 2.6 });
    }

    // ---- contorno: isolinhas horizontais do SDF ----
    const rows = [];
    const NX = 15;
    for (let y = -0.950; y <= 0.004; y += 0.0115) {
      if (sd(0, y, 0) > -0.004) continue;
      let lo = 0, hi = 0.40;
      if (sd(hi, y, 0) < 0) hi = 0.40;
      for (let k = 0; k < 15; k++) { const m = (lo + hi) / 2; if (sd(m, y, 0) < 0) lo = m; else hi = m; }
      const rx = lo;
      if (rx < 0.010) continue;
      const pts = [];
      for (let i = 0; i < NX; i++) {
        const u = (i / (NX - 1)) * 2 - 1;
        const x = u * rx * 0.996;
        let zl = 0, zh = 0.40;
        for (let k = 0; k < 12; k++) { const m = (zl + zh) / 2; if (sd(x, y, m) < 0) zl = m; else zh = m; }
        pts.push([x, y, zl]);
      }
      rows.push({ y, rx, pts });
    }
    // ênfase onde a superfície "vira" (queixo, ombro, trapézio): dá leitura anatômica
    const dy = 0.0115;
    for (let i = 0; i < rows.length; i++) {
      const a2 = rows[Math.max(0, i - 2)], b2 = rows[Math.min(rows.length - 1, i + 2)];
      const slope = Math.abs(b2.rx - a2.rx) / (2 * dy);
      rows[i].emph = 1 + Math.min(2.4, slope * 0.50);
    }
    return { shell, inner, rows };
  })();

  const visor = { y: -0.782, z: 0.140, half: 0.082 };
  const cores = [
    { p: [0, -0.784, 0.062], r: 0.046 },
    { p: [0, -0.210, 0.088], r: 0.056 },
  ];
  const coreDots = (() => {
    const out = [];
    for (const c of cores) {
      for (let i = 0; i < 90; i++) {
        const u = rnd() * 2 - 1, th = rnd() * TAU, s = Math.sqrt(1 - u * u), rr = c.r * Math.cbrt(rnd());
        out.push({
          x: c.p[0] + s * Math.cos(th) * rr, y: c.p[1] + u * rr * 0.85, z: c.p[2] + s * Math.sin(th) * rr * 0.5,
          ph: rnd() * TAU, sp: 1.2 + rnd() * 2.6, size: 0.6 + rnd() * 1.1,
        });
      }
    }
    return out;
  })();

  // detalhes de contorno desenhados como fios (dão leitura anatômica)
  const wires = [
    { alpha: 0.20, pts: [[-0.026, -0.470, 0.076], [-0.110, -0.434, 0.076], [-0.196, -0.386, 0.050]] },
    { alpha: 0.20, pts: [[0.026, -0.470, 0.076], [0.110, -0.434, 0.076], [0.196, -0.386, 0.050]] },
    { alpha: 0.13, pts: [[0, -0.470, 0.082], [0, -0.300, 0.124], [0, -0.140, 0.132]] },
    { alpha: 0.16, pts: [[0.008, -0.560, 0.074], [0.052, -0.598, 0.082], [0.090, -0.672, 0.058], [0.104, -0.742, 0.016]] },
    { alpha: 0.16, pts: [[-0.008, -0.560, 0.074], [-0.052, -0.598, 0.082], [-0.090, -0.672, 0.058], [-0.104, -0.742, 0.016]] },
    { alpha: 0.12, pts: [[-0.046, -0.812, 0.142], [0.046, -0.812, 0.142]] },
  ];

  const drifters = Array.from({ length: 190 }, () => ({
    x: (rnd() * 2 - 1) * 0.40, y: -0.99 + rnd() * 1.020, z: (rnd() * 2 - 1) * 0.190,
    vy: 0.011 + rnd() * 0.035, vx: (rnd() - 0.5) * 0.02, life: rnd(), sp: 0.4 + rnd() * 1.4,
    size: 0.5 + rnd() * 1.2, gold: rnd() < 0.28,
  }));

  const streams = [];
  for (const side of [-1, 1]) {
    for (let w = 0; w < 5; w++) {
      streams.push({
        side, w, speed: 0.055 + rnd() * 0.055,
        amp: 0.038 + w * 0.024, k: 2.7 + w * 0.62, ph: rnd() * TAU,
        y0: -0.300 + w * 0.052 + rnd() * 0.02,
        gold: rnd() < 0.35,
      });
    }
  }

  function drawAvatar(t) {
    const sm = Math.min(speedMul(), 1.8);
    const a = ampNow;
    const top = 56;
    const bottom = Math.max(top + 300, H - 120);
    const avail = bottom - top;
    // quadro (quando definido) ou tela inteira
    const FW = bustFrame ? bustFrame.w : W;
    const FH = bustFrame ? bustFrame.h : avail;
    const FX = bustFrame ? bustFrame.x : W * 0.5;
    const FY = bustFrame ? bustFrame.y : top + avail * 0.5;
    // o busto ocupa y ∈ [-0.944, -0.007] (0,94 unidades de altura)
    // S = pixels por unidade em z=0; persp(0) = 1/1.65, então k = S / persp(0)
    const S = Math.min(FH / 1.14, FW / 0.86);
    const U = S * 0.0030;
    const ox = FX;
    const oy = FY + 0.476 * S;
    const depth = 1.7;
    const q = Math.max(0.34, Math.min(1, quality));
    const thin = (i) => q >= 0.999 || ((i * 2654435761) % 1000) * 0.001 <= q;
    setRot(Math.sin(t * 0.17) * 0.26, -0.02 + Math.sin(t * 0.11) * 0.02);

    ctx.save();
    ctx.translate(ox, oy);
    ctx.globalCompositeOperation = "lighter";
    const k = S * 1.65;
    const P3 = (x, y, z) => { const p = rot3(x, y, z); const pe = persp(p[2], depth); return [p[0] * k * pe, p[1] * k * pe, p[2]]; };
    const path = (pts, close) => {
      ctx.beginPath();
      for (let i = 0; i < pts.length; i++) {
        const P = P3(pts[i][0], pts[i][1], pts[i][2]);
        if (i === 0) ctx.moveTo(P[0], P[1]); else ctx.lineTo(P[0], P[1]);
      }
      if (close) ctx.closePath();
    };

    // ---- anéis de contenção (atrás do busto) ----
    for (let i = 0; i < 3; i++) {
      const rr = S * (0.52 + i * 0.165);
      const rot = Math.sin(t * (0.16 + i * 0.05) * sm + i * 1.7) * 0.09 + (i % 2 ? 1 : -1) * 0.14;
      ctx.beginPath();
      ctx.strokeStyle = rgba(i % 2 ? accent2 : accent, 0.075 - i * 0.019);
      ctx.lineWidth = i === 0 ? 1.2 : 0.8;
      ctx.ellipse(0, -0.36 * S, rr, rr * 0.34, rot, 0, TAU);
      ctx.stroke();
    }

    // ---- varredura vertical ----
    const sweepY = -0.99 + ((t * 0.20 * sm) % 1) * 1.03;

    // ---- fluxos de dados laterais ----
    const wOut = Math.max(0.50, Math.min(0.66, (FW * 0.5 - 10) / S));
    const NP = 26;
    for (const st of streams) {
      const pts = [];
      for (let i = 0; i <= NP; i++) {
        const u = i / NP;
        const x = st.side * (0.40 + u * (wOut - 0.40));
        const y = st.y0 + Math.sin(st.k * u * 2.3 - t * 1.15 * sm + st.ph) * st.amp * (0.32 + u * 0.92);
        pts.push(P3(x, y, 0.03 + Math.sin(u * 12) * 0.04));
      }
      ctx.beginPath();
      ctx.strokeStyle = rgba([72, 138, 235], 0.030);
      ctx.lineWidth = 1;
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i <= NP; i++) ctx.lineTo(pts[i][0], pts[i][1]);
      ctx.stroke();
      for (let i = 0; i < 22; i++) {
        if (!thin(i * 5 + st.w * 23 + (st.side > 0 ? 7 : 0))) continue;
        const u = ((i / 22 + t * st.speed * sm * 1.5) % 1);
        const x = st.side * (0.40 + u * (wOut - 0.40));
        const wave = Math.sin(st.k * u * 2.3 - t * 1.15 * sm + st.ph);
        const y = st.y0 + wave * st.amp * (0.32 + u * 0.92);
        const P = P3(x, y, 0.03 + Math.sin(u * 12) * 0.04);
        const alpha = (0.28 - u * 0.08) * (0.45 + u * 0.9) * (0.6 + a * 0.9);
        if (alpha <= 0.02) continue;
        dot(P[0], P[1], U * (0.45 + (1 - u) * 0.30) * (0.85 + wave * 0.15), st.gold && wave > 0.5 ? [255, 186, 92] : [138, 196, 255], alpha);
      }
    }

    // ---- corpo: varredura sólida + isolinhas ----
    const cont = Math.min(1, S / 900);
    const rowProj = [];
    const rowStep = 0.0132 * k;
    for (let r = 0; r < bust.rows.length; r++) {
      const row = bust.rows[r];
      const near = Math.abs(row.y - sweepY) < 0.030;
      const dim = row.y > -0.06 ? Math.max(0.30, 1 - (row.y + 0.06) * 4.4) : 1;
      const edgeA = (0.086 + 0.058 * Math.min(1, row.rx / 0.34)) * dim * (row.emph || 1) * (0.7 + a * 0.6);
      const alphaRow = edgeA * (near ? 1.9 : 1);
      if (alphaRow < 0.008) continue;
      rowProj.length = 0;
      for (let i = 0; i < row.pts.length; i++) rowProj.push(P3(row.pts[i][0], row.pts[i][1], row.pts[i][2]));
      ctx.beginPath();
      ctx.moveTo(rowProj[0][0], rowProj[0][1]);
      for (let i = 1; i < rowProj.length; i++) ctx.lineTo(rowProj[i][0], rowProj[i][1]);
      ctx.strokeStyle = rgba([52, 116, 220], 0.014 + (near ? 0.026 : 0));
      ctx.lineWidth = rowStep * 1.4;
      ctx.stroke();
      ctx.strokeStyle = rgba(near ? [214, 244, 255] : [96, 172, 252], alphaRow);
      ctx.lineWidth = (near ? 1.4 : 0.85) * (0.8 + cont * 0.4);
      ctx.stroke();
      const A = rowProj[0], B = rowProj[rowProj.length - 1];
      const rimA = Math.min(1, alphaRow * (near ? 2.6 : 4.6));
      dot(A[0], A[1], U * (near ? 2.6 : 2.0), near ? [230, 250, 255] : [186, 226, 255], rimA);
      dot(B[0], B[1], U * (near ? 2.6 : 2.0), near ? [230, 250, 255] : [186, 226, 255], rimA);
    }
    // meridianos verticais (volume)
    for (const mu of [0.34, 0.72]) {
      for (const sgn of [-1, 1]) {
        ctx.beginPath();
        ctx.strokeStyle = rgba(accent, 0.075);
        ctx.lineWidth = 1;
        let st3 = false;
        for (let r = 0; r < bust.rows.length; r++) {
          const row = bust.rows[r];
          const i = Math.max(0, Math.min(row.pts.length - 1, Math.round(((sgn * mu + 1) / 2) * (row.pts.length - 1))));
          const p = row.pts[i];
          const P = P3(p[0], p[1], p[2] * 0.80);
          if (!st3) { ctx.moveTo(P[0], P[1]); st3 = true; } else ctx.lineTo(P[0], P[1]);
        }
        ctx.stroke();
      }
    }

    // ---- fios anatômicos (clavícula, esterno, mandíbula, sobrancelha) ----
    for (const w of wires) {
      path(w.pts, false);
      ctx.strokeStyle = rgba([150, 206, 255], w.alpha * (0.7 + a * 0.5));
      ctx.lineWidth = 1.1;
      ctx.stroke();
    }

    // ---- casca de partículas ----
    for (let pass = 0; pass < 2; pass++) {
      for (let i = 0; i < bust.shell.length; i++) {
        if (pass === 0 && i % 3) continue;
        if (!thin(i)) continue;
        const p = bust.shell[i];
        if (p.band) continue;
        const shim = 1 + Math.sin(t * p.sp + p.ph) * 0.005;
        const P = P3(p.x * shim, p.y * shim, p.z * shim);
        const front = (P[2] + 0.22) / 0.44;
        const near = Math.abs(p.y - sweepY) < 0.030;
        let alpha = (0.030 + front * 0.140) * p.fade * (1 + p.rim * 1.0);
        if (p.gold) alpha *= 1.7;
        alpha *= 0.8 + a * 0.7;
        if (near) alpha *= 2.2;
        alpha *= pass === 0 ? 0.22 : 1;
        if (alpha <= 0.008) continue;
        const col = near ? [206, 244, 255] : p.gold ? [255, 176, 72] : (p.bright > 1.5 || p.rim > 0.6) ? [200, 232, 255] : [110, 172, 255];
        dot(P[0], P[1], U * p.size * p.bright * (pass === 0 ? 2.4 : 1) * (0.9 + front * 0.5), col, alpha);
      }
    }

    // ---- brilho interno ----
    for (let i = 0; i < bust.inner.length; i++) {
      if (!thin(i + 7)) continue;
      const p = bust.inner[i];
      const P = P3(p.x, p.y + Math.sin(t * p.sp + p.ph) * 0.005, p.z);
      const front = (P[2] + 0.22) / 0.44;
      dot(P[0], P[1], U * p.size * 0.7, [255, 198, 116], (0.040 + front * 0.115) * (0.9 + a * 1.1));
    }

    // ---- visor ----
    {
      const v = [];
      for (let i = 0; i <= 10; i++) {
        const u = (i / 10) * 2 - 1;
        v.push(P3(u * visor.half, visor.y, visor.z - u * u * 0.028));
      }
      const pulse = 0.78 + 0.22 * Math.sin(t * 1.9 * sm);
      const hot = state === "speaking" || state === "listening" || state === "thinking" ? 1.45 : 1;
      ctx.beginPath();
      ctx.moveTo(v[0][0], v[0][1]);
      for (let i = 1; i < v.length; i++) ctx.lineTo(v[i][0], v[i][1]);
      ctx.strokeStyle = rgba([255, 214, 140], (0.34 + a * 0.25) * pulse * hot);
      ctx.lineWidth = 2.2 + a * 0.9;
      ctx.stroke();
      ctx.strokeStyle = rgba([255, 255, 255], (0.18 + a * 0.2) * pulse * hot);
      ctx.lineWidth = 0.9;
      ctx.stroke();
      const mid = P3(0, visor.y, visor.z);
      glow(mid[0], mid[1], S * 0.062 * (0.85 + a * 0.35), [255, 168, 60], 0.11 + a * 0.09);
      for (let i = 0; i <= 6; i++) {
        const u = (i / 6) * 2 - 1;
        const P = P3(u * visor.half * 1.02, visor.y + u * u * 0.010, visor.z - u * u * 0.028);
        dot(P[0], P[1], U * 0.8, [255, 236, 190], (0.26 + a * 0.3) * pulse);
      }
      // nariz e boca (leitura de face)
      const nose = P3(0, -0.742, 0.166);
      dot(nose[0], nose[1], U * 1.1, [255, 226, 176], 0.22 + a * 0.2);
      const mouth = P3(0, -0.672, 0.146);
      dot(mouth[0], mouth[1], U * 0.9, [255, 200, 150], 0.14 + a * 0.16);
    }

    // ---- aglomerado do pescoço ----
    for (let i = 0; i < 60; i++) {
      const ang = (i / 60) * TAU;
      const rr = 0.050 + (i % 5) * 0.003;
      const P = P3(Math.cos(ang) * rr, -0.556 + (i % 7) * 0.008, Math.sin(ang) * rr * 0.74 + 0.008);
      dot(P[0], P[1], U * 0.5, i % 4 === 0 ? [255, 214, 150] : [168, 216, 255], 0.12 + a * 0.16);
    }

    // ---- núcleos de energia ----
    const pulse = 0.5 + Math.sin(t * 1.7 * sm) * 0.5;
    for (const c of cores) {
      const P = P3(c.p[0], c.p[1], c.p[2]);
      const chest = c.p[1] > -0.20;
      glow(P[0], P[1], S * c.r * (2.0 + a * 0.7 + pulse * 0.2), [255, 146, 40], (chest ? 0.034 : 0.070) + a * 0.05);
      glow(P[0], P[1], S * c.r * (0.95 + pulse * 0.1), [255, 224, 168], (chest ? 0.038 : 0.078) + a * 0.06);
    }
    for (const d of coreDots) {
      const P = P3(d.x, d.y, d.z);
      const tw = 0.55 + 0.45 * Math.abs(Math.sin(t * d.sp + d.ph));
      dot(P[0], P[1], U * d.size * (1 + a * 0.5), [255, 198, 118], (0.11 + a * 0.18) * tw * (d.y > -0.20 ? 0.62 : 1));
    }

    // ---- partículas que se desprendem ----
    for (let i = 0; i < drifters.length; i++) {
      if (!thin(i + 3)) continue;
      const d = drifters[i];
      const lt = (d.life + t * d.vy * 3) % 1;
      const P = P3(d.x + d.vx * lt, d.y - lt * 0.30, d.z);
      const alpha = (1 - lt) * 0.17 * (0.6 + a * 0.5);
      if (alpha <= 0.01) continue;
      dot(P[0], P[1], U * d.size * 0.5, d.gold ? [255, 186, 92] : [120, 180, 255], alpha);
    }

    drawDataLines(W - 22, 84);
    ctx.restore();
  }

  // -------------------------------------------------------- NÚCLEO GOLDEN -----
  // O centro do painel GOLDEN JARVIS, como na referência do usuário: um globo de
  // partículas (casca digital brilhante, mais intensa na silhueta) com um núcleo
  // de energia dourado dentro, anéis de contenção girando, grade de meridianos e
  // paralelos, e os módulos REAIS do sistema em órbita — cada nó tem rótulo,
  // leitura ao vivo e executa um comando de verdade quando clicado.
  const coreSphere = (() => {
    const pts = [];
    const N = 3600;
    const ga = Math.PI * (3 - Math.sqrt(5));      // espiral de Fibonacci (uniforme)
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const th = ga * i;
      pts.push({
        x: Math.cos(th) * r, y, z: Math.sin(th) * r,
        ph: rnd() * TAU, sp: 0.35 + rnd() * 1.7,
        size: 0.70 + rnd() * 1.25,
        gold: rnd() < 0.10, big: rnd() < 0.06,
      });
    }
    return pts;
  })();
  // faíscas que vivem dentro da esfera (energia do núcleo)
  const coreMotes = Array.from({ length: 170 }, () => {
    const u = rnd() * 2 - 1, th = rnd() * TAU, s = Math.sqrt(1 - u * u), rr = 0.26 + Math.cbrt(rnd()) * 0.70;
    return {
      x: s * Math.cos(th) * rr, y: u * rr, z: s * Math.sin(th) * rr,
      ph: rnd() * TAU, sp: 0.9 + rnd() * 2.4, size: 0.6 + rnd() * 1.1, gold: rnd() < 0.55,
    };
  });
  // partículas que escapam da casca
  const coreDrift = Array.from({ length: 90 }, () => {
    const u = rnd() * 2 - 1, th = rnd() * TAU, s = Math.sqrt(1 - u * u);
    return {
      x: s * Math.cos(th), y: u, z: s * Math.sin(th),
      sp: 0.05 + rnd() * 0.14, ph: rnd() * TAU, size: 0.5 + rnd() * 1.1, gold: rnd() < 0.3,
    };
  });
  let coreTitle = "";

  function drawCore(t) {
    const sm = Math.min(speedMul(), 1.8);
    const a = ampNow;
    const q = Math.max(0.4, Math.min(1, quality));
    const thin = (i) => q >= 0.999 || ((i * 2654435761) % 1000) * 0.001 <= q;

    // área útil: a coluna central do painel GOLDEN JARVIS (definida pelo app)
    const FW = bustFrame ? bustFrame.w : Math.min(W * 0.9, H * 1.1);
    const FH = bustFrame ? bustFrame.h : H * 0.72;
    const FX = bustFrame ? bustFrame.x : W * 0.5;
    const FY = bustFrame ? bustFrame.y : H * 0.44;

    const coreR = Math.max(40, Math.min(FH * 0.165, FW * 0.115));  // raio do núcleo
    const k = coreR * 2.70;                                        // raio do globo (mundo)
    const vR = k / 1.65;                                           // raio aparente (após a perspectiva)
    // órbita dos módulos: elipse larga (a coluna central é muito mais larga que alta)
    const ex = Math.max(vR * 2.30, Math.min(FW * 0.40, FH * 0.76));
    const ey = Math.max(vR * 1.26, FH * 0.335);
    const depth = 2.2;
    const rotY = t * 0.13 * sm;
    const tilt = -0.24 + Math.sin(t * 0.10 * sm) * 0.05;

    ctx.save();
    ctx.translate(FX, FY);
    ctx.globalCompositeOperation = "lighter";

    // brilho geral do globo (volumetria)
    glow(0, 0, vR * 1.55, accent, 0.15 + a * 0.12);
    glow(0, 0, vR * 1.02, [110, 186, 255], 0.11 + a * 0.08);

    setRot(rotY, tilt);
    const P3 = (x, y, z) => {
      const p = rot3(x, y, z);
      const pe = persp(p[2], depth);
      return [p[0] * k * pe, p[1] * k * pe, p[2]];
    };

    // ---- anéis de contenção em volta do globo (metade de trás) ----
    const orbRings = [
      { rx: vR * 1.30, sq: 0.62, rot: -0.06, sp: 0.00, col: accent2, al: 0.30, w: 1.2 },
      { rx: vR * 1.08, sq: 0.74, rot: 0.10, sp: -0.50, col: accent, al: 0.24, w: 1.1 },
      { rx: vR * 0.90, sq: 0.48, rot: 0.22, sp: 0.32, col: accent, al: 0.20, w: 0.9 },
    ];
    const drawOrbRings = (front) => {
      for (const rg of orbRings) {
        const rr = rg.rot + rg.sp * t * 0.11 * sm;
        // halo largo + traço fino = leitura de anel 3D, não de elipse 2D
        ctx.beginPath();
        ctx.strokeStyle = rgba(rg.col, rg.al * 0.36 * (0.75 + a * 0.4));
        ctx.lineWidth = rg.w * 4.0;
        if (front) ctx.ellipse(0, 0, rg.rx, rg.rx * rg.sq, rr, 0, Math.PI);
        else ctx.ellipse(0, 0, rg.rx, rg.rx * rg.sq, rr, Math.PI, TAU);
        ctx.stroke();
        ctx.beginPath();
        ctx.strokeStyle = rgba([200, 234, 255], (front ? 0.32 : 0.17) * (0.72 + a * 0.4));
        ctx.lineWidth = rg.w * 0.9;
        if (front) ctx.ellipse(0, 0, rg.rx, rg.rx * rg.sq, rr, 0, Math.PI);
        else ctx.ellipse(0, 0, rg.rx, rg.rx * rg.sq, rr, Math.PI, TAU);
        ctx.stroke();
        // faísca correndo pelo anel (dá vida e profundidade)
        const u = (((t * 0.17 + rg.sp * 0.42) % 1) + 1) % 1;
        const s0 = front ? u * Math.PI : Math.PI + u * Math.PI;
        ctx.beginPath();
        ctx.strokeStyle = rgba([255, 244, 214], front ? 0.60 : 0.26);
        ctx.lineWidth = rg.w + 1.4;
        ctx.ellipse(0, 0, rg.rx, rg.rx * rg.sq, rr, s0, s0 + 0.42);
        ctx.stroke();
      }
    };
    drawOrbRings(false);

    // ---- casca de partículas (a "pele" digital, forte na silhueta) ----
    // Desenhada em DUAS passadas (atrás / à frente do núcleo): é isso que dá
    // leitura de volume — a poeira da frente flutua sobre o plasma dourado.
    const stride = q >= 0.999 ? 1 : Math.round(1 / q);
    const drawShell = (front) => {
      for (let i = 0; i < coreSphere.length; i += stride) {
        const p = coreSphere[i];
        const R3 = rot3(p.x, p.y, p.z);
        const isFront = R3[2] > 0.08;
        if (isFront !== front) continue;
        const pe = persp(R3[2], depth);
        const s = [R3[0] * k * pe, R3[1] * k * pe, R3[2], pe];
        const fr = (R3[2] + 1) * 0.5;
        const rim = 1 - Math.abs(R3[2]);
        const rimW = rim * rim * Math.sqrt(rim);
        const tw = 0.72 + 0.28 * Math.sin(t * p.sp + p.ph);
        // aglomerados: quebra a uniformidade "pincel de pontos" da casca
        const clump = 0.30 + 0.70 * Math.abs(Math.sin(p.x * 7.1 + p.y * 5.3 + p.z * 6.7) * Math.sin(p.x * 3.3 - p.z * 4.1));
        let al = (0.09 + fr * 0.19 + rimW * 0.74) * tw * (0.85 + a * 0.55) * (0.45 + 0.55 * clump);
        al *= front ? 0.52 : 0.66;
        if (p.gold) al *= 1.4;
        if (p.big) al *= 1.4;
        if (al <= 0.012) continue;
        // abre espaço para o plasma dourado: a casca some no miolo do globo
        const inner = coreR * 1.22;
        const sr = Math.hypot(s[0], s[1]);
        if (sr < inner) al *= 0.05 + 0.95 * Math.pow(sr / inner, 1.9);
        const col = p.gold ? [255, 186, 96] : rim > 0.62 ? [176, 224, 255] : fr > 0.55 ? [150, 212, 255] : [88, 152, 246];
        dot(s[0], s[1], Math.min(4.6, Math.max(1.1, p.size * 2.6 * s[3] * (1 + rimW * 0.9) * (0.75 + clump * 0.5))), col, Math.min(1, al));
      }
    };
    drawShell(false);

    // ---- membrana volumétrica + brilho especular (dá corpo de esfera) ----
    {
      const mg = ctx.createRadialGradient(0, 0, vR * 0.08, 0, 0, vR * 1.02);
      mg.addColorStop(0, rgba([34, 84, 162], 0.045));
      mg.addColorStop(0.40, rgba([52, 118, 204], 0.075));
      mg.addColorStop(0.72, rgba([104, 178, 255], 0.135));
      mg.addColorStop(0.90, rgba([152, 212, 255], 0.125));
      mg.addColorStop(1, rgba([152, 212, 255], 0));
      ctx.fillStyle = mg;
      ctx.beginPath();
      ctx.ellipse(0, 0, vR * 1.02, vR * 1.02, 0, 0, TAU);
      ctx.fill();
      glow(-vR * 0.34, -vR * 0.40, vR * 0.62, [214, 240, 255], 0.13 + a * 0.05);
      glow(-vR * 0.26, -vR * 0.31, vR * 0.30, [240, 250, 255], 0.10);
    }

    // ---- contorno do globo (silhueta luminosa) ----
    {
      const limb = ctx.createRadialGradient(0, 0, vR * 0.52, 0, 0, vR * 1.03);
      limb.addColorStop(0, rgba(accent, 0));
      limb.addColorStop(0.58, rgba([96, 168, 250], 0.05));
      limb.addColorStop(0.86, rgba([152, 216, 255], 0.26));
      limb.addColorStop(0.97, rgba([226, 248, 255], 0.16));
      limb.addColorStop(1, rgba([226, 248, 255], 0));
      ctx.fillStyle = limb;
      ctx.beginPath();
      ctx.ellipse(0, 0, vR * 1.03, vR * 1.03, 0, 0, TAU);
      ctx.fill();
      ctx.beginPath();
      ctx.ellipse(0, 0, vR * 1.005, vR * 1.005, 0, 0, TAU);
      ctx.strokeStyle = rgba([198, 234, 255], 0.24 + a * 0.14);
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // ---- grade do globo (meridianos e paralelos) ----
    // Também em duas passadas: a metade de trás fica esmaecida atrás do plasma
    // e a da frente é redesenhada por cima — é isso que faz a grade "abraçar"
    // a esfera em vez de parecer um arame plano.
    const gridPass = (front) => {
      const gridA = 0.7 + a * 0.5;
      const seg = (x0, y0, z0, x1, y1, z1, base, w) => {
        const A = P3(x0, y0, z0), B = P3(x1, y1, z1);
        const mz = (A[2] + B[2]) * 0.5;
        if ((mz > 0.05) !== front) return;
        const fr = (mz + 1) * 0.5;
        // perto dos polos todos os meridianos convergem: sem esse fade a
        // sobreposição vira uma linha reta brilhante no topo do globo
        const my = Math.abs((y0 + y1) * 0.5);
        const poleFade = 1 - 0.82 * Math.pow(my, 7);
        let al = (base[0] + fr * base[1]) * gridA * poleFade;
        // a grade também desbota no miolo (onde fica o plasma do núcleo)
        const gmx = (A[0] + B[0]) * 0.5, gmy = (A[1] + B[1]) * 0.5;
        const gsr = Math.hypot(gmx, gmy);
        const coreIn = coreR * 1.05;
        if (gsr < coreIn) al *= 0.22 + 0.78 * Math.pow(gsr / coreIn, 1.5);
        if (!front) al *= 0.46;
        if (al < 0.02) return;
        ctx.beginPath();
        ctx.strokeStyle = rgba(front ? [168, 224, 255] : [74, 132, 228], al);
        ctx.lineWidth = w * (0.7 + fr * 0.7);
        ctx.moveTo(A[0], A[1]);
        ctx.lineTo(B[0], B[1]);
        ctx.stroke();
      };
      const MER = [0.12, 0.50];
      const PAR = [0.10, 0.42];
      const STEP = 12;
      for (let mi = 0; mi < 12; mi++) {
        if (!thin(mi * 13 + 5)) continue;
        const lon = mi * 30 * DEG;
        const sl = Math.sin(lon), cl = Math.cos(lon);
        for (let la = -84; la < 84; la += STEP) {
          const a0 = la * DEG, a1 = (la + STEP) * DEG;
          seg(Math.cos(a0) * sl, Math.sin(a0), Math.cos(a0) * cl,
              Math.cos(a1) * sl, Math.sin(a1), Math.cos(a1) * cl,
              MER, 1.0);
        }
      }
      for (let pi = -60; pi <= 60; pi += 30) {
        if (pi === 0) continue;                 // o equador é o feixe de varredura
        if (!thin(pi + 71)) continue;
        const la = pi * DEG, cy0 = Math.cos(la), sy0 = Math.sin(la);
        for (let lon = 0; lon < 360; lon += STEP * 1.5) {
          const b0 = lon * DEG, b1 = (lon + STEP * 1.5) * DEG;
          seg(Math.cos(b0) * cy0, sy0, Math.sin(b0) * cy0,
              Math.cos(b1) * cy0, sy0, Math.sin(b1) * cy0,
              PAR, 0.9);
        }
      }
      // feixe de varredura girando (um feixe, não um arame cortando a esfera)
      {
        const la = Math.asin(Math.sin(t * 0.5 * sm) * 0.92) / DEG;
        const laR = la * DEG, cy0 = Math.cos(laR), sy0 = Math.sin(laR);
        const beam = (t * 0.85 * sm) % TAU;
        for (let lon = 0; lon < 360; lon += 6) {
          const b0 = lon * DEG, b1 = (lon + 6) * DEG;
          const A2 = P3(Math.cos(b0) * cy0, sy0, Math.sin(b0) * cy0);
          const B2 = P3(Math.cos(b1) * cy0, sy0, Math.sin(b1) * cy0);
          if (((A2[2] + B2[2]) * 0.5 > 0.05) !== front) continue;
          const d = (((b0 - beam) % TAU) + TAU) % TAU;
          const kb = Math.pow(Math.max(0, 1 - d / 2.6), 2.2);
          let al = (0.05 + 0.55 * kb) * (0.8 + a * 0.4);
          const gsr = Math.hypot((A2[0] + B2[0]) * 0.5, (A2[1] + B2[1]) * 0.5);
          const coreIn = coreR * 1.05;
          if (gsr < coreIn) al *= 0.22 + 0.78 * Math.pow(gsr / coreIn, 1.5);
          if (!front) al *= 0.5;
          if (al < 0.02) continue;
          ctx.beginPath();
          ctx.strokeStyle = rgba([214, 244, 255], al);
          ctx.lineWidth = 1.2 + kb * 1.5;
          ctx.moveTo(A2[0], A2[1]);
          ctx.lineTo(B2[0], B2[1]);
          ctx.stroke();
        }
      }
    };
    gridPass(false);

    // ---- faíscas internas ----
    for (let i = 0; i < coreMotes.length; i++) {
      if (!thin(i + 29)) continue;
      const p = coreMotes[i];
      const R3 = rot3(p.x, p.y, p.z);
      const pe = persp(R3[2], depth);
      const s = [R3[0] * k * pe, R3[1] * k * pe, R3[2], pe];
      const front = (R3[2] + 1) * 0.5;
      const tw = 0.5 + 0.5 * Math.abs(Math.sin(t * p.sp + p.ph));
      dot(s[0], s[1], Math.max(0.9, p.size * 1.8 * s[3]), p.gold ? [255, 200, 128] : [162, 222, 255],
        (0.16 + front * 0.22) * tw * (0.85 + a * 0.8));
    }

    // ---- plasma do núcleo: preenche o miolo do globo com calor dourado ----
    // (a casca de partículas é atenuada no centro para abrir espaço pra ele,
    // então o ouro não é lavado pelo azul e o núcleo realmente domina)
    const pulse = 0.5 + 0.5 * Math.sin(t * 1.6 * sm);
    const cr = coreR * (0.34 + pulse * 0.035 + a * 0.05);
    glow(0, 0, coreR * 2.60, [255, 90, 6], 0.24 + a * 0.12);
    glow(0, 0, coreR * 1.74, [255, 116, 14], 0.36 + a * 0.18);
    glow(0, 0, coreR * 1.12, [255, 150, 30], 0.50 + a * 0.22);
    glow(0, 0, cr * 2.05, [255, 174, 58], 0.56 + a * 0.22);
    glow(0, 0, cr * 1.18, [255, 214, 130], 0.58 + a * 0.20);
    glow(0, 0, cr * 0.58, [255, 236, 196], 0.28 + a * 0.08);
    // turbulência interna: células quentes girando = núcleo "fervendo"
    for (let i = 0; i < 7; i++) {
      const an = t * (0.42 + i * 0.13) * sm + i * 1.7;
      const rr2 = cr * (0.20 + ((i * 37) % 100) * 0.0058);
      const px2 = Math.cos(an) * rr2;
      const py2 = Math.sin(an * 1.3 + i) * rr2 * 0.72;
      const sz = cr * (0.40 + ((i * 53) % 100) * 0.0042);
      glow(px2, py2, sz, i % 3 === 0 ? [255, 238, 184] : i % 3 === 1 ? [255, 168, 44] : [255, 118, 18], 0.18 + a * 0.10);
    }
    // anéis de energia em volta do núcleo (fina faixa dourada girando)
    for (let i = 0; i < 3; i++) {
      const rr = cr * (1.22 + i * 0.46);
      const sp = (i % 2 ? -1 : 1) * (0.45 + i * 0.22) * sm;
      ctx.beginPath();
      ctx.strokeStyle = rgba(i === 0 ? [255, 232, 186] : [255, 160, 62], i === 0 ? 0.62 : 0.34 - i * 0.06);
      ctx.lineWidth = 1.8 - i * 0.3;
      ctx.ellipse(0, 0, rr, rr * 0.28, t * sp * 0.25, t * sp, t * sp + 2.1 + i * 0.55);
      ctx.stroke();
    }

    // ---- aro do núcleo: limite visível do "sol" (mantém o ouro contido) ----
    {
      const rg2 = ctx.createRadialGradient(0, 0, coreR * 0.80, 0, 0, coreR * 0.94);
      rg2.addColorStop(0, rgba([255, 176, 60], 0));
      rg2.addColorStop(0.55, rgba([255, 196, 92], 0.16 + a * 0.08));
      rg2.addColorStop(1, rgba([255, 232, 176], 0));
      ctx.fillStyle = rg2;
      ctx.beginPath();
      ctx.arc(0, 0, coreR * 0.94, 0, TAU);
      ctx.fill();
    }

    // ---- nome do sistema sobre o núcleo ----
    {
      const name = (coreTitle || "J.A.R.V.I.S.").toUpperCase();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      let fs = Math.max(11, Math.min(coreR * 0.35, 46));
      try { ctx.letterSpacing = (fs * 0.16) + "px"; } catch {}
      ctx.font = `700 ${fs}px Orbitron, 'Rajdhani', sans-serif`;
      let mw = ctx.measureText(name).width;
      const maxW = coreR * 1.80;
      if (mw > maxW) {
        fs *= maxW / mw;
        try { ctx.letterSpacing = (fs * 0.16) + "px"; } catch {}
        ctx.font = `700 ${fs}px Orbitron, 'Rajdhani', sans-serif`;
        mw = ctx.measureText(name).width;
      }
      // sangramento quente: o nome participa da luz do plasma (não é adesivo)
      ctx.shadowColor = "rgba(255,188,92,0.80)";
      ctx.shadowBlur = fs * 1.05;
      ctx.fillStyle = "rgba(255,198,112,0.34)";
      ctx.fillText(name, 0, 0);
      ctx.fillText(name, 0, 0);
      ctx.shadowBlur = 0;
      // contorno escuro por glifo em vez de faixa: mantém o plasma esférico
      // intacto e o nome legível em cima do ouro
      ctx.globalCompositeOperation = "source-over";
      ctx.lineJoin = "round";
      ctx.miterLimit = 2;
      ctx.shadowColor = "rgba(24,10,0,0.85)";
      ctx.shadowBlur = fs * 0.55;
      ctx.strokeStyle = "rgba(26,12,0,0.55)";
      ctx.lineWidth = fs * 0.34;
      ctx.strokeText(name, 0, 0);
      ctx.shadowBlur = 0;
      ctx.strokeStyle = "rgba(12,6,0,0.88)";
      ctx.lineWidth = fs * 0.17;
      ctx.strokeText(name, 0, 0);
      const tg = ctx.createLinearGradient(0, -fs * 0.62, 0, fs * 0.58);
      tg.addColorStop(0, "rgba(255,255,255,1)");
      tg.addColorStop(0.55, "rgba(255,246,228,0.99)");
      tg.addColorStop(1, "rgba(255,224,168,0.96)");
      ctx.fillStyle = tg;
      ctx.fillText(name, 0, 0);
      try { ctx.letterSpacing = "0px"; } catch {}
      ctx.textAlign = "left";
      ctx.globalCompositeOperation = "lighter";
    }

    // ---- grade da frente: por cima do plasma, com a oclusão correta ----
    gridPass(true);

    // ---- poeira da frente: flutua SOBRE o núcleo e o nome (profundidade) ----
    drawShell(true);

    // ---- módulos reais do sistema: geometria + fibras ----
    // A órbita é desenhada em duas fases: as fibras passam POR BAIXO dos anéis
    // da frente (oclusão correta) em vez de cruzá-los por cima — era isso que
    // fazia o entorno parecer "linhas atravessando tudo".
    nodeHits.length = 0;
    const labels = FW > 560 && FH > 360;
    const fsN = FW < 900 ? 11 : 13;
    const nNodes = hostNodes.length;
    const blocked = 20 * DEG;              // cunha do fundo (pílula e legenda)
    const freeArc = TAU - 2 * blocked;     // módulos distribuídos no arco livre
    const startArc = Math.PI * 0.5 + blocked;
    const nodeGeo = [];
    for (let i = 0; i < nNodes; i++) {
      const nd = hostNodes[i];
      const ang = startArc + (i / nNodes) * freeArc;
      const rf = 1 + (nd.rf - 1) * 0.18;
      const nx = Math.cos(ang) * ex * rf;
      const ny = Math.sin(ang) * ey * rf;
      const nl = Math.max(1e-3, Math.hypot(nx, ny));
      const sf = Math.min(1, (vR * 1.02) / nl) * 0.94;
      nodeGeo.push({
        nd, nx, ny, sx: nx * sf, sy: ny * sf,
        side: nx >= 0 ? 1 : -1, hover: nd.id === nodeHoverId, live: nd.on !== false,
      });
    }
    for (const g of nodeGeo) {
      const { nd, nx, ny, sx, sy, hover, live } = g;
      // fibra óptica curva: nasce na borda do globo e apaga até o módulo
      const cxp = (sx + nx) * 0.5, cyp = (sy + ny) * 0.5;
      const bow = 0.13;
      const qx = cxp - (ny - sy) * bow, qy = cyp + (nx - sx) * bow;
      const lg2 = ctx.createLinearGradient(sx, sy, nx, ny);
      lg2.addColorStop(0, rgba(hover ? accent2 : accent, hover ? 0.92 : live ? 0.50 : 0.18));
      lg2.addColorStop(0.55, rgba(hover ? accent2 : accent, hover ? 0.7 : live ? 0.30 : 0.10));
      lg2.addColorStop(1, rgba(hover ? accent2 : accent, hover ? 0.55 : live ? 0.14 : 0.05));
      ctx.beginPath();
      ctx.strokeStyle = lg2;
      ctx.lineWidth = hover ? 2.0 : 1.15;
      ctx.moveTo(sx, sy);
      ctx.quadraticCurveTo(qx, qy, nx, ny);
      ctx.stroke();
      const sAng = Math.atan2(sy, sx);
      ctx.beginPath();
      ctx.strokeStyle = rgba(accent, hover ? 0.9 : 0.5);
      ctx.lineWidth = hover ? 2.2 : 1.5;
      ctx.arc(0, 0, Math.hypot(sx, sy), sAng - 0.07, sAng + 0.07);
      ctx.stroke();
      // pulso viajando do núcleo até o módulo
      const u = (t * 0.30 * sm + (nd.ph || 0) / TAU) % 1;
      dot(sx + (nx - sx) * u, sy + (ny - sy) * u, hover ? 4.5 : 3.4, [186, 236, 255], (hover ? 0.9 : 0.6) * (0.45 + u * 0.55));
    }

    // ---- anéis de contenção (metade da frente, por cima do núcleo) ----
    drawOrbRings(true);

    // ---- órbita dos módulos: anel externo, ticks e segmentos girando ----
    ctx.beginPath();
    ctx.ellipse(0, 0, ex, ey, 0, 0, TAU);
    ctx.strokeStyle = rgba(accent, 0.16 + a * 0.08);
    ctx.lineWidth = 6;
    ctx.stroke();
    ctx.beginPath();
    ctx.ellipse(0, 0, ex, ey, 0, 0, TAU);
    ctx.strokeStyle = rgba(accent2, 0.45);
    ctx.lineWidth = 1.4;
    ctx.stroke();
    const NSEG = 6;
    for (let i = 0; i < NSEG; i++) {
      const s0 = t * (0.055 + i * 0.012) * sm + i * (TAU / NSEG);
      ctx.beginPath();
      ctx.ellipse(0, 0, ex, ey, 0, s0, s0 + 0.28 + (i % 3) * 0.05);
      ctx.strokeStyle = rgba([255, 232, 182], 0.55 + a * 0.2);
      ctx.lineWidth = 2.4;
      ctx.stroke();
    }
    for (let i = 0; i < 84; i++) {
      const ang = (i / 84) * TAU - t * 0.03 * sm;
      const lng = i % 7 === 0;
      const c0 = Math.cos(ang), s0 = Math.sin(ang);
      ctx.beginPath();
      ctx.strokeStyle = rgba(accent2, lng ? 0.62 : 0.26);
      ctx.lineWidth = lng ? 1.6 : 0.9;
      ctx.moveTo(ex * 1.012 * c0, ey * 1.012 * s0);
      ctx.lineTo(ex * (lng ? 1.055 : 1.032) * c0, ey * (lng ? 1.055 : 1.032) * s0);
      ctx.stroke();
    }

    // ---- fase B: chips e rótulos dos módulos (por cima da órbita) ----
    try { ctx.letterSpacing = "1px"; } catch {}
    for (const g of nodeGeo) {
      const { nd, nx, ny, side, hover, live } = g;
      // chip do módulo
      const ms = hover ? 8 : 6;
      if (hover) glow(nx, ny, 30, accent2, 0.45);
      glow(nx, ny, ms * 2.2, live ? accent : [130, 140, 150], 0.28);
      ctx.beginPath();
      ctx.strokeStyle = rgba(live ? accent : [130, 140, 150], hover ? 1 : 0.88);
      ctx.lineWidth = hover ? 2.2 : 1.5;
      ctx.arc(nx, ny, ms, 0, TAU);
      ctx.stroke();
      ctx.beginPath();
      ctx.strokeStyle = rgba(live ? accent2 : [130, 140, 150], hover ? 0.95 : 0.7);
      ctx.lineWidth = 1;
      ctx.moveTo(nx - ms - 3.5, ny);
      ctx.lineTo(nx - ms + 1, ny);
      ctx.moveTo(nx + ms - 1, ny);
      ctx.lineTo(nx + ms + 3.5, ny);
      ctx.stroke();
      dot(nx, ny, ms * 0.85, live ? accent2 : [150, 150, 150], hover ? 1 : 0.8);
      // rótulo e leitura ao vivo
      if (labels) {
        ctx.font = (hover ? "600 " : "") + fsN + "px 'Share Tech Mono', monospace";
        ctx.textAlign = side >= 0 ? "left" : "right";
        ctx.textBaseline = "middle";
        ctx.fillStyle = rgba(hover ? [255, 240, 200] : [216, 240, 255], hover ? 1 : 0.92);
        ctx.fillText(String(nd.label || nd.id || "").toUpperCase(), nx + side * 14, ny - (nd.stat ? 5.5 : 0));
        if (nd.stat) {
          ctx.font = (fsN - 2) + "px 'Share Tech Mono', monospace";
          ctx.fillStyle = rgba(live ? accent2 : [140, 150, 160], 0.92);
          ctx.fillText(String(nd.stat).toUpperCase(), nx + side * 14, ny + 9);
        }
      }
      const hitR = labels ? Math.max(26, ctx.measureText(String(nd.label || "")).width + 16) : 22;
      nodeHits.push({ id: nd.id, label: nd.label, cmd: nd.cmd, on: live, x: FX + nx, y: FY + ny, r: hover ? hitR + 6 : hitR });
    }
    try { ctx.letterSpacing = "0px"; } catch {}

    // ---- partículas que escapam ----
    for (let i = 0; i < coreDrift.length; i++) {
      if (!thin(i + 41)) continue;
      const d = coreDrift[i];
      const esc = (t * d.sp + d.ph / TAU) % 1;
      const rr = (1 + esc * 0.85) * 1.65;
      const R3 = rot3(d.x * rr, d.y * rr, d.z * rr);
      const pe = persp(R3[2], depth);
      const s = [R3[0] * k * pe, R3[1] * k * pe, R3[2], pe];
      const al = (1 - esc) * 0.38 * (0.6 + a * 0.5);
      if (al <= 0.012) continue;
      dot(s[0], s[1], 2.3 * s[3] * (1 + d.size * 0.4), d.gold ? [255, 194, 108] : [132, 198, 255], al);
    }

    drawDataLines(W - 22, 84);
    ctx.restore();
  }

  const modeDraw = { arc: drawArc, holo: drawHolo, neural: drawNeural, sentinel: drawSentinel, nucleo: drawNucleo, avatar: drawAvatar, core: drawCore };

  function frame(now) {
    if (!running) return;
    rafId = requestAnimationFrame(frame);
    const realDt = (now - prev) / 1000 || 0.016;
    const dt = Math.min(0.05, realDt);
    prev = now;
    elapsed += dt;

    // limita o desenho a ~60 fps (economiza bateria em telas de alta taxa)
    drawAcc += realDt;
    if (drawAcc < 0.0155) return;
    const measuredDt = drawAcc;
    drawAcc = 0;

    fpsAcc += measuredDt; fpsFrames++;
    if (fpsAcc > 0.5) {
      fps = fpsFrames / fpsAcc;
      fpsAcc = 0; fpsFrames = 0;
      if (!qualityLock) {
        if (fps < 34 && quality > 0.4) quality = Math.max(0.4, quality - 0.18);
        else if (fps > 56 && quality < 1) quality = Math.min(1, quality + 0.08);
      }
    }

    ampNow += (amp - ampNow) * Math.min(1, dt * 9);

    // limpa sempre com o estado "neutro" — se algum modo lançar erro com
    // globalCompositeOperation="lighter" ativo, o clearRect deixaria de apagar
    // e a tela acumularia rastros brilhantes.
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.restore();
    const draw = modeDraw[mode] || drawArc;
    try { draw(elapsed); } catch (err) { if (!drawErrorLogged) { drawErrorLogged = true; console.error("hud draw error:", err); } }
  }

  return {
    setTheme(id, themeMode) {
      mode = themeMode || id || "arc";
      pulses.length = 0;
      nodeHits.length = 0;
      nodeHoverId = "";
    },
    setState(s) { state = s || "idle"; },
    setTitle(v) { coreTitle = String(v || "").toUpperCase(); },
    setAmplitude(v) { amp = Math.max(0, Math.min(1, v || 0)); },
    setPalette(a, b) {
      if (a) accent = a;
      if (b) accent2 = b;
    },
    setTarget(x, y, r) { cx = x; cy = y; R = Math.max(24, r); },
    setFrame(f) { bustFrame = f && f.w > 60 && f.h > 60 ? { x: f.x, y: f.y, w: f.w, h: f.h } : null; },
    pulse() { if (pulses.length < 6) pulses.push({ t: 0 }); },
    setHostNodes,
    getNodes() { return nodeHits.map((n) => ({ ...n })); },
    setHoverNode(id) { nodeHoverId = id || ""; },
    setDataLines(lines) { dataLines = (lines || []).slice(0, 8); },
    getFps() { return Math.round(fps); },
    // trava a qualidade (0.4–1) para inspeção/medição; `null` volta ao automático
    setQuality(v) {
      if (v == null) { qualityLock = false; return; }
      qualityLock = true;
      quality = Math.max(0.4, Math.min(1, v));
    },
    start() {
      if (running) return;
      running = true;
      prev = performance.now();
      resize();
      rafId = requestAnimationFrame(frame);
    },
    stop() {
      running = false;
      cancelAnimationFrame(rafId);
    },
    resize,
  };
}
