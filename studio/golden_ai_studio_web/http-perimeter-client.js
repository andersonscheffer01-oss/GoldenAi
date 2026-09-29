/* Attach the already-paired device identity to same-origin HTTP API calls. */
(function installJarvisHttpPerimeterClient() {
  if (window.__JARVIS_HTTP_PERIMETER__) return;
  const nativeFetch = window.fetch.bind(window);
  const tokenKeys = ["jarvis_device_token", "jarvis-device-token"];

  function token() {
    for (const key of tokenKeys) {
      try {
        const value = localStorage.getItem(key);
        if (value) return value;
      } catch (_) {}
    }
    return "";
  }

  window.fetch = function jarvisPerimeterFetch(input, init) {
    const requestInit = { ...(init || {}) };
    const rawUrl = typeof input === "string" ? input : input?.url || "";
    let parsed;
    try { parsed = new URL(rawUrl, window.location.href); } catch (_) { return nativeFetch(input, requestInit); }
    if (parsed.origin !== window.location.origin ||
        (!parsed.pathname.startsWith("/api/") && !parsed.pathname.startsWith("/stream/"))) {
      return nativeFetch(input, requestInit);
    }
    const headers = new Headers(requestInit.headers || (input instanceof Request ? input.headers : undefined));
    const deviceToken = token();
    if (deviceToken && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${deviceToken}`);
    if (!headers.has("X-Request-ID")) headers.set("X-Request-ID", `web-${Date.now().toString(36)}`);
    requestInit.headers = headers;
    return nativeFetch(input, requestInit);
  };

  window.__JARVIS_HTTP_PERIMETER__ = { enabled: true };
})();
