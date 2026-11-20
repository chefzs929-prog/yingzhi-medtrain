/* RadioCheck · Service Worker（快捷入口 / 离线外壳）
 *
 * 策略：
 *   - 导航请求：网络优先，失败回落缓存（断网也能打开看过的页面）
 *   - 静态资源：缓存优先 + 后台更新（stale-while-revalidate）
 *   - 不缓存 /api/ 与影像/3D 大文件，避免占满存储、也避免把接口结果当成证据
 *
 * 升级方式：改 VERSION 即可，activate 时清掉旧缓存。
 */
const VERSION = 'v5.0.0';
const CACHE = `yingzhi-${VERSION}`;
const OFFLINE_PAGE = './index.html';

const SKIP_PATH = [/\/api\//, /\/images\//, /\/models\//, /\/_work\//];
const CACHEABLE_TYPE = /(javascript|css|html|json|manifest|png|svg)/;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll([OFFLINE_PAGE, './app.html', './manifest.webmanifest']))
      .catch(() => undefined)
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys.filter((k) => k.startsWith('yingzhi-') && k !== CACHE).map((k) => caches.delete(k))
    );
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (SKIP_PATH.some((re) => re.test(url.pathname))) return;
  if (req.headers.has('range')) return;

  if (req.mode === 'navigate') {
    event.respondWith(networkFirst(req));
    return;
  }
  if (CACHEABLE_TYPE.test(req.destination) || /\.(js|css|json|webmanifest)$/.test(url.pathname)) {
    event.respondWith(staleWhileRevalidate(req));
  }
});

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req, { ignoreSearch: true });
    if (hit) return hit;
    const shell = await cache.match(OFFLINE_PAGE, { ignoreSearch: true });
    if (shell) return shell;
    return new Response(
      '<!doctype html><meta charset="utf-8"><title>离线</title>' +
      '<body style="font:15px/1.7 -apple-system,PingFang SC,sans-serif;padding:40px;color:#0b4f55">' +
      '<h1 style="font-size:18px">当前处于离线状态</h1>' +
      '<p>RadioCheck 外壳已缓存，但这张页面还没被打开过。联网后刷新即可。</p></body>',
      { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  const network = fetch(req)
    .then((res) => {
      if (res && res.ok) cache.put(req, res.clone());
      return res;
    })
    .catch(() => undefined);
  if (hit) {
    network.catch(() => undefined);
    return hit;
  }
  const res = await network;
  if (res) return res;
  return new Response('', { status: 504, statusText: 'offline' });
}
