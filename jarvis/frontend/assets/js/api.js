(function () {
  const API_TIMEOUT = 20000;

  function token() {
    return sessionStorage.getItem('jarvis_token') || '';
  }

  function setToken(value) {
    if (value) sessionStorage.setItem('jarvis_token', value);
    else sessionStorage.removeItem('jarvis_token');
  }

  function user() {
    try { return JSON.parse(sessionStorage.getItem('jarvis_user') || 'null'); }
    catch (_) { return null; }
  }

  function setUser(value) {
    if (value) sessionStorage.setItem('jarvis_user', JSON.stringify(value));
    else sessionStorage.removeItem('jarvis_user');
  }

  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeout || API_TIMEOUT);
    const headers = new Headers(options.headers || {});
    const currentToken = token();
    if (currentToken) headers.set('Authorization', 'Bearer ' + currentToken);
    if (options.json) {
      headers.set('Content-Type', 'application/json');
      options.body = JSON.stringify(options.json);
    }
    try {
      const response = await fetch(path, { ...options, headers, signal: controller.signal });
      if (response.status === 401) {
        setToken('');
        setUser(null);
        if (!location.pathname.startsWith('/login')) location.href = '/login';
        throw new Error('Sessao expirada. Entre novamente.');
      }
      const contentType = response.headers.get('content-type') || '';
      const data = contentType.includes('application/json') ? await response.json() : await response.text();
      if (!response.ok) {
        const detail = data && data.detail;
        const message = detail && typeof detail === 'object' ? detail.message : detail;
        const error = new Error(message || 'Falha na comunicacao com a API.');
        if (detail && typeof detail === 'object') Object.assign(error, detail);
        error.status = response.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('A API demorou demais para responder.');
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  window.JarvisAPI = { request, token, setToken, user, setUser };
})();
