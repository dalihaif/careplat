/* 照护管理平台 · Service Worker
   策略：静态资源 cache-first；页面 network-first（失败回退缓存） */
   打卡等 POST 请求不缓存，离线时直接失败并提示 */
const CACHE = 'careplat-v1';
const ASSETS = [
  '/static/vendor/bootstrap.min.css',
  '/static/vendor/bootstrap.bundle.min.js',
  '/static/vendor/chart.umd.min.js',
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/manifest.webmanifest'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  // 静态资源：cache-first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((resp) => {
        const cp = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, cp));
        return resp;
      }))
    );
    return;
  }

  // 页面：network-first，离线回退缓存
  e.respondWith(
    fetch(req).then((resp) => {
      if (resp.ok) {
        const cp = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, cp));
      }
      return resp;
    }).catch(() =>
      caches.match(req).then((hit) => hit || caches.match('/'))
    )
  );
});

/* 页面发来的消息：跳过等待立即生效 */
self.addEventListener('message', (e) => {
  if (e.data === 'skipWaiting') self.skipWaiting();
});
