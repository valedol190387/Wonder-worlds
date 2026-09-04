/* Service worker: кешируем оболочку и тяжёлую статику (фоны, декодер HEIC),
   чтобы повторные открытия были мгновенными. HTML и API — всегда из сети:
   миры живут на сервере, устаревшую страницу показывать нельзя. */
const VERSION = 'wonderworlds-v4';
const SHELL = [
  '/', '/index.html', '/app.html', '/manifest.webmanifest',
  '/vendor/qrcode.js', '/vendor/libheif.js', '/vendor/libheif.wasm',
  '/bg/night.jpg', '/bg/farm.jpg', '/bg/track.jpg', '/bg/sky.jpg',
  '/icons/icon-192.png', '/icons/icon-512.png',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL).catch(()=>{})).then(()=> self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(()=> self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  if (u.pathname.startsWith('/api/') || u.pathname === '/health') return;   // живые данные — только сеть

  // страницы и списки (index.json наборов, манифест): сеть, при обрыве — кеш.
  // Картинки наборов версионируются хвостом ?v=, поэтому им кеш не страшен,
  // а вот сам список должен приходить свежим — иначе после обновления
  // наборов пользователь неделю видит старые картинки.
  if (e.request.mode === 'navigate' || u.pathname.endsWith('.html') ||
      u.pathname.endsWith('.json') || u.pathname.endsWith('.webmanifest')){
    e.respondWith(fetch(e.request).then(r => {
      const copy = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); return r;
    }).catch(()=> caches.match(e.request).then(r => r || caches.match('/index.html'))));
    return;
  }
  // статика: кеш, при промахе — сеть с докладыванием в кеш
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
    if (resp.ok){ const copy = resp.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); }
    return resp;
  })));
});
