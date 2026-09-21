/**
 * Gateway Adapter — Replaces bridge.js (X-Ja-Token) + jarvis-standalone.js (direct Ollama)
 * 
 * Real protocol: Gateway WS on port 8766
 * Auth: Device token via WS hello/auth messages (not HTTP header)
 * Commands: All routed through Gateway → JarvisService → ToolRegistry → SecurityManager
 * 
 * CRITICAL INVARIANTS:
 * - No direct Ollama calls
 * - No direct shell/OS commands
 * - No direct MT5 access
 * - No X-Ja-Token header
 * - All commands go through Gateway
 */
(function() {
  'use strict';

  const PROTOCOL_VERSION = 1;
  const MAX_RECONNECT_DELAY = 30000;
  const INITIAL_RECONNECT_DELAY = 1000;

  class GatewayAdapter {
    constructor() {
      this._ws = null;
      this._authenticated = false;
      this._sessionId = null;
      this._reconnectDelay = INITIAL_RECONNECT_DELAY;
      this._reconnectTimer = null;
      this._pendingCommands = new Map();
      this._idempotencyCounter = 0;
      this._status = 'disconnected';
      this._listeners = {};
      this._autoConnect = false;
      this._tokenSource = 'none';
      console.info('[JARVIS-GATEWAY] ui_origin=' + location.origin);
      console.info('[JARVIS-GATEWAY] ws_url=' + this.wsUrl);
    }

    // ─── Origin Derivation (no hardcoded backendUrl) ───

    get wsUrl() {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      return proto + '//' + location.hostname + ':8766/ws';
    }

    get httpUrl() {
      return location.origin;
    }

    get status() { return this._status; }
    get isAuthenticated() { return this._authenticated; }
    get sessionId() { return this._sessionId; }

    // ─── Event System ───

    on(event, fn) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(fn);
    }

    _emit(event, data) {
      const fns = this._listeners[event];
      if (fns) fns.forEach(fn => { try { fn(data); } catch(e) { console.error('Listener error:', e); } });
    }

    // ─── Token Management (device auth, NOT X-Ja-Token) ───
    // KEY: 'jarvis_device_token' — must match mobile.html exactly.

    static TOKEN_KEY = 'jarvis_device_token';
    static TOKEN_KEY_LEGACY = 'jarvis-device-token';

    getToken() {
      // Primary: official key (matches mobile.html)
      let token = localStorage.getItem(GatewayAdapter.TOKEN_KEY) || '';
      this._tokenSource = token ? 'primary' : 'none';
      // One-time migration: if primary empty, check legacy key
      if (!token) {
        const legacy = localStorage.getItem(GatewayAdapter.TOKEN_KEY_LEGACY) || '';
        if (legacy) {
          token = legacy;
          localStorage.setItem(GatewayAdapter.TOKEN_KEY, token);
          localStorage.removeItem(GatewayAdapter.TOKEN_KEY_LEGACY);
          this._tokenSource = 'legacy_migrated';
        }
      }
      return token;
    }

    setToken(token) {
      localStorage.setItem(GatewayAdapter.TOKEN_KEY, token);
    }

    // ─── Connection ───

    connect() {
      if (this._ws && (this._ws.readyState === WebSocket.OPEN || this._ws.readyState === WebSocket.CONNECTING)) {
        return;
      }
      this._setStatus('connecting');
      console.info('[JARVIS-GATEWAY] websocket=constructing');
      try {
        this._ws = new WebSocket(this.wsUrl);
        this._ws.onopen = () => this._onOpen();
        this._ws.onmessage = (e) => this._onMessage(e);
        this._ws.onclose = (e) => this._onClose(e);
        this._ws.onerror = (e) => this._onError(e);
      } catch (err) {
        console.error('WebSocket connect failed:', err);
        this._setStatus('error');
        this._scheduleReconnect();
      }
    }

    disconnect() {
      this._autoConnect = false;
      clearTimeout(this._reconnectTimer);
      if (this._ws) {
        try { this._ws.close(); } catch(e) {}
      }
      this._authenticated = false;
      this._sessionId = null;
      this._setStatus('disconnected');
    }

    _onOpen() {
      console.info('[JARVIS-GATEWAY] websocket=open; hello=sent');
      this._reconnectDelay = INITIAL_RECONNECT_DELAY;
      this._sendHello();
    }

    _onClose(event) {
      console.info('[JARVIS-GATEWAY] websocket=closed; code=' + event.code);
      this._authenticated = false;
      this._sessionId = null;
      this._ws = null;
      this._setStatus('disconnected');
      this._emit('disconnected', { code: event.code, reason: event.reason });
      if (this._autoConnect) this._scheduleReconnect();
    }

    _onError(error) {
      console.error('[JARVIS-GATEWAY] websocket=error');
      this._emit('error', error);
    }

    _onMessage(event) {
      try {
        const msg = JSON.parse(event.data);
        this._handleMessage(msg);
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    }

    // ─── Protocol Messages ───

    _send(type, payload, sessionId, messageId) {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return false;
      const msg = {
        version: PROTOCOL_VERSION,
        id: messageId || this._nextId(),
        type: type,
        timestamp: new Date().toISOString(),
        payload: payload || {},
      };
      if (sessionId || this._sessionId) msg.session_id = sessionId || this._sessionId;
      this._ws.send(JSON.stringify(msg));
      return true;
    }

    _sendHello() {
      this._send('hello', { client: 'jarvis-ui', version: '1.0.0' });
    }

    _sendAuth(token) {
      this._send('auth', { token: token });
    }

    _nextId() {
      return 'ui_' + Date.now().toString(36) + '_' + (++this._idempotencyCounter);
    }

    // ─── Message Handler ───

    _handleMessage(msg) {
      const type = msg.type;
      const payload = msg.payload || {};

      switch (type) {
        case 'status':
          // Hello response — auth required
          if (payload.auth_required) {
            const token = this.getToken();
            console.info('[JARVIS-GATEWAY] auth_required=true; token_present=' +
              Boolean(token) + '; token_source=' + this._tokenSource);
            if (token) {
              console.info('[JARVIS-GATEWAY] auth=sent');
              this._sendAuth(token);
            } else {
              this._setStatus('awaiting_auth');
              this._emit('awaiting_auth', payload);
            }
          }
          break;

        case 'auth_ok':
          console.info('[JARVIS-GATEWAY] auth=ok; session_open=sent');
          this._authenticated = true;
          this._setStatus('online');
          this._emit('authenticated', payload);
          // Open session
          this._send('session_open', { client_info: { ui: 'jarvis-ui', platform: navigator.platform } });
          break;

        case 'auth_error':
          console.error('[JARVIS-GATEWAY] auth=failed');
          this._authenticated = false;
          this._setStatus('auth_error');
          this._emit('auth_error', payload);
          break;

        case 'session_info':
          if (payload.action === 'opened' && payload.session_id) {
            this._sessionId = payload.session_id;
            console.info('[JARVIS-GATEWAY] session=opened; ready=true');
            this._emit('session_opened', payload);
          }
          break;

        case 'command_ack':
          this._emit('command_ack', payload);
          break;

        case 'command_result': {
          const normalized = this._normalizeCommandResult(payload);
          this._resolveCommand(msg.id, normalized);
          this._emit('command_result', normalized);
          break;
        }

        case 'command_error':
          this._rejectCommand(msg.id, payload);
          this._emit('command_error', payload);
          break;

        case 'confirmation_required':
          this._emit('confirmation_required', payload);
          break;

        case 'event':
          this._emit('event', payload);
          break;

        case 'pong':
          break;

        case 'error':
          console.error('Gateway error:', payload);
          this._emit('gateway_error', payload);
          break;

        default:
          console.warn('Unknown message type:', type);
      }
    }

    // ─── Command Execution (ALL through Gateway) ───

    // O backend responde envelope de tool ({ok, message|error, tool, risk, state}).
    // A UI procura campos conversacionais (reply/text/output). Adicionamos aliases
    // sem remover nenhum campo original — preserva todo o payload do backend.
    _normalizeCommandResult(payload) {
      if (!payload || typeof payload !== 'object') return payload;
      const conversationalText =
        payload.reply ??
        payload.text ??
        payload.message ??
        payload.output ??
        (payload.ok === false ? payload.error : undefined);
      if (!conversationalText) return payload;
      return {
        ...payload,
        reply: payload.reply ?? conversationalText,
        text: payload.text ?? conversationalText,
        output: payload.output ?? conversationalText,
      };
    }

    sendCommand(command, options) {
      return new Promise((resolve, reject) => {
        if (!this._authenticated) {
          reject(new Error('Not authenticated'));
          return;
        }
        const id = this._nextId();
        this._pendingCommands.set(id, { resolve, reject, timestamp: Date.now() });
        this._send('command', { command: command, ...(options || {}) }, undefined, id);
        // Allow Brain routing plus the research tool's 45s execution budget
        // to complete without expiring the client-side command first.
        setTimeout(() => {
          if (this._pendingCommands.has(id)) {
            this._pendingCommands.delete(id);
            reject(new Error('Command timeout'));
          }
        }, 90000);
      });
    }

    _resolveCommand(id, result) {
      const pending = this._pendingCommands.get(id);
      if (pending) {
        this._pendingCommands.delete(id);
        pending.resolve(result);
      }
    }

    _rejectCommand(id, error) {
      const pending = this._pendingCommands.get(id);
      if (pending) {
        this._pendingCommands.delete(id);
        pending.reject(new Error(error.error || 'Command failed'));
      }
    }

    // ─── Confirmation Response ───

    confirmAction(token, approved) {
      this._send('confirmation_response', { token: token, approved: approved });
    }

    // ─── Ping (keepalive) ───

    ping() {
      this._send('ping', {});
    }

    // ─── HTTP API (for endpoints that exist on server_agent.py port 8765) ───

    async httpGet(path) {
      try {
        const res = await fetch(this.httpUrl + path);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return await res.json();
      } catch (err) {
        console.error('HTTP GET failed:', path, err);
        return null;
      }
    }

    async httpPost(path, data) {
      try {
        const res = await fetch(this.httpUrl + path, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data || {}),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return await res.json();
      } catch (err) {
        console.error('HTTP POST failed:', path, err);
        return null;
      }
    }

    // ─── Reconnection ───

    _scheduleReconnect() {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = setTimeout(() => {
        this.connect();
      }, this._reconnectDelay);
      this._reconnectDelay = Math.min(this._reconnectDelay * 2, MAX_RECONNECT_DELAY);
    }

    _setStatus(status) {
      this._status = status;
      this._emit('status', status);
    }

    // ─── Auto-connect ───

    start(autoConnect) {
      this._autoConnect = autoConnect !== false;
      if (this._autoConnect) this.connect();
    }
  }

  // Singleton
  window.Gateway = new GatewayAdapter();
})();
