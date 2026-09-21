let audioCtx = null;
let muted = false;

function ac() {
  if (muted) return null;
  try {
    if (!audioCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      audioCtx = new Ctx();
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  } catch {
    return null;
  }
}

export function setMuted(v) { muted = !!v; }
export function isMuted() { return muted; }

export function tone({ freq = 880, to = null, dur = 0.09, type = "sine", gain = 0.05, delay = 0 } = {}) {
  const ctx = ac();
  if (!ctx) return;
  const t0 = ctx.currentTime + delay;
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (to) osc.frequency.exponentialRampToValueAtTime(Math.max(40, to), t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.012);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g).connect(ctx.destination);
  osc.start(t0);
  osc.stop(t0 + dur + 0.03);
}

export const sfx = {
  ping() { tone({ freq: 1180, to: 1560, dur: 0.07, type: "sine", gain: 0.045 }); },
  listenOn() { tone({ freq: 620, to: 1240, dur: 0.16, type: "triangle", gain: 0.05 }); tone({ freq: 1560, dur: 0.09, gain: 0.03, delay: 0.14 }); },
  listenOff() { tone({ freq: 1240, to: 520, dur: 0.15, type: "triangle", gain: 0.045 }); },
  think() { tone({ freq: 240, to: 300, dur: 0.12, type: "sawtooth", gain: 0.02 }); },
  ok() { tone({ freq: 880, dur: 0.08, gain: 0.04 }); tone({ freq: 1320, dur: 0.12, gain: 0.035, delay: 0.08 }); },
  err() { tone({ freq: 190, to: 90, dur: 0.28, type: "square", gain: 0.045 }); },
  boot() {
    tone({ freq: 130, to: 900, dur: 1.1, type: "sine", gain: 0.035 });
    tone({ freq: 1400, dur: 0.1, gain: 0.025, delay: 1.0 });
  },
  alert() {
    tone({ freq: 720, dur: 0.18, type: "square", gain: 0.035 });
    tone({ freq: 720, dur: 0.18, type: "square", gain: 0.035, delay: 0.26 });
  },
  click() { tone({ freq: 1600, dur: 0.03, gain: 0.02, type: "square" }); },
};
