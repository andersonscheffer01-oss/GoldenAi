(function () {
  async function login(email, senha) {
    const data = await JarvisAPI.request('/api/auth/login', { method: 'POST', json: { email, senha } });
    JarvisAPI.setToken(data.access_token);
    JarvisAPI.setUser(data.usuario);
    return data.usuario;
  }

  async function me() {
    const data = await JarvisAPI.request('/api/auth/me');
    JarvisAPI.setUser(data);
    return data;
  }

  async function logout() {
    try { await JarvisAPI.request('/api/auth/logout', { method: 'POST' }); }
    catch (_) {}
    JarvisAPI.setToken('');
    JarvisAPI.setUser(null);
    location.href = '/login';
  }

  function requireLogin() {
    if (!JarvisAPI.token()) {
      location.href = '/login';
      return false;
    }
    return true;
  }

  function redirectIfLogged() {
    if (JarvisAPI.token()) location.href = '/app';
  }

  window.JarvisAuth = { login, me, logout, requireLogin, redirectIfLogged };
})();

