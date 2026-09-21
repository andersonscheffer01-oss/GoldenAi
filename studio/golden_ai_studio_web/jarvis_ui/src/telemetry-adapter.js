/**
 * Telemetry Adapter — Separates client metrics from host metrics
 * 
 * CLIENT METRICS (browser-side, no Gateway):
 *   - FPS, canvas performance
 *   - Browser memory (performance.memory, Chrome only)
 *   - WebGL renderer info
 *   - navigator.connection (needs HTTPS)
 *   - Battery API (needs HTTPS)
 * 
 * HOST METRICS (via Gateway → JarvisService):
 *   - Real CPU, RAM, disk, GPU, processes
 *   - Ollama model status
 *   - MT5 status
 *   - Network I/O
 * 
 * NEVER present browser metrics as PC metrics.
 */
(function() {
  'use strict';

  const TelemetryAdapter = {
    _clientMetrics: {
      fps: 0,
      browserMemory: null,
      gpu: null,
      network: null,
      battery: null,
    },
    _hostMetrics: null,
    _listeners: [],

    // ─── Client Metrics (browser-side) ───

    collectClientMetrics() {
      const m = {};

      // FPS (from HUD)
      if (window.hud) {
        m.fps = window.hud.getFps ? window.hud.getFps() : 0;
      }

      // Browser memory (Chrome only)
      if (performance.memory) {
        m.browserMemory = {
          used: performance.memory.usedJSHeapSize,
          total: performance.memory.jsHeapSizeLimit,
          limit: performance.memory.jsHeapSizeLimit,
        };
      }

      // WebGL renderer
      try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {
          const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
          if (debugInfo) {
            m.gpu = {
              vendor: gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL),
              renderer: gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL),
            };
          }
        }
      } catch(e) {}

      // Network info (needs HTTPS)
      if (navigator.connection) {
        m.network = {
          downlink: navigator.connection.downlink,
          rtt: navigator.connection.rtt,
          effectiveType: navigator.connection.effectiveType,
          type: navigator.connection.type,
        };
      }

      this._clientMetrics = m;
      return m;
    },

    async collectBattery() {
      try {
        if (navigator.getBattery) {
          const battery = await navigator.getBattery();
          this._clientMetrics.battery = {
            level: battery.level,
            charging: battery.charging,
            chargingTime: battery.chargingTime,
            dischargingTime: battery.dischargingTime,
          };
          return this._clientMetrics.battery;
        }
      } catch(e) {}
      return null;
    },

    getClientMetrics() {
      return { ...this._clientMetrics };
    },

    // ─── Host Metrics (via Gateway HTTP API) ───

    async fetchHostMetrics() {
      if (!window.Gateway) return null;
      try {
        const data = await window.Gateway.httpGet('/api/status');
        if (data && data.ok !== false) {
          this._hostMetrics = {
            cpu: data.cpu || 0,
            ram: data.ram || data.memory || 0,
            disk: data.disk || 0,
            gpu: data.gpu || null,
            uptime: data.uptime || 0,
            processes: data.processes || 0,
            network: data.network || null,
          };
          return this._hostMetrics;
        }
      } catch(e) {
        console.warn('Host metrics fetch failed:', e);
      }
      return null;
    },

    async fetchOllamaModels() {
      if (!window.Gateway) return null;
      try {
        const data = await window.Gateway.httpGet('/api/jarvis/providers/status');
        if (data && data.ok !== false) {
          return data;
        }
      } catch(e) {}
      // SECURITY: No direct Ollama access from frontend — must route through Gateway
      return null;
    },

    async fetchMT5Status() {
      if (!window.Gateway) return null;
      try {
        const data = await window.Gateway.httpGet('/api/mt5/status');
        if (data) return data;
      } catch(e) {}
      return null;
    },

    getHostMetrics() {
      return this._hostMetrics ? { ...this._hostMetrics } : null;
    },

    // ─── Combined Telemetry (for display) ───

    getDisplayMetrics() {
      const client = this.getClientMetrics();
      const host = this.getHostMetrics();
      return {
        client: client,
        host: host,
        isHostAvailable: host !== null,
      };
    },

    // ─── Periodic Collection ───

    start(intervalMs) {
      const interval = intervalMs || 5000;
      this._collectLoop = setInterval(() => {
        this.collectClientMetrics();
        this.fetchHostMetrics();
      }, interval);
      this.collectBattery();
    },

    stop() {
      if (this._collectLoop) {
        clearInterval(this._collectLoop);
        this._collectLoop = null;
      }
    },
  };

  window.TelemetryAdapter = TelemetryAdapter;
})();
