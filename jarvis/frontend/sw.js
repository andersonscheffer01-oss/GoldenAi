const CACHE_VERSION = 'golden-jarvis-v0.47.0';
const STATIC_ASSETS = [
  '/app',
  '/login',
  '/manifest.json',
  '/assets/css/app.css',
  '/assets/css/finance-media.css',
  '/assets/js/api.js',
  '/assets/js/auth.js',
  '/assets/js/chat.js',
  '/assets/js/dashboard.js',
  '/assets/js/upload.js',
  '/assets/js/open-finance.js',
  '/assets/js/app.js',
  '/assets/icons/icon-192.png',
  '/assets/icons/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_VERSION).then(cache => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_VERSION).map(key => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (!STATIC_ASSETS.includes(url.pathname)) return;
  event.respondWith(
    fetch(event.request).then(response => {
      const clone = response.clone();
      caches.open(CACHE_VERSION).then(cache => cache.put(event.request, clone));
      return response;
    }).catch(() => caches.match(event.request))
  );
});
