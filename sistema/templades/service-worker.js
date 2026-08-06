{% load static %}
const CACHE_VERSION = 'conexion-pwa-v2';
const DB_NAME = 'conexion-offline';
const STORE = 'outbox';
const OFFLINE_URL = '{% url "pwa_offline" %}';
const PRECACHE = [
  OFFLINE_URL,
  '{% static "style.css" %}',
  '{% static "assets/css/bootstrap.min.css" %}',
  '{% static "assets/js/bootstrap.bundle.min.js" %}',
  '{% static "assets/images/favicon.svg" %}',
  '{% static "pwa/icon-192.png" %}',
  '{% static "pwa/icon-512.png" %}',
];

function abrirDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, {keyPath: 'id'});
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function guardarPendiente(request, id, headers) {
  const body = await request.arrayBuffer();
  const item = {
    id, url: request.url, method: request.method,
    headers: Array.from(headers.entries()), body,
    creadoEn: Date.now(), intentos: 0,
  };
  const db = await abrirDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(item);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  await avisarClientes({type: 'OFFLINE_QUEUED', id});
}

async function pendientes() {
  const db = await abrirDb();
  return new Promise((resolve, reject) => {
    const req = db.transaction(STORE).objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function eliminarPendiente(id) {
  const db = await abrirDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

async function avisarClientes(mensaje) {
  const clientes = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
  clientes.forEach(cliente => cliente.postMessage(mensaje));
}

async function sincronizar() {
  const items = await pendientes();
  if (!items.length) {
    await avisarClientes({type: 'OFFLINE_COUNT', count: 0});
    return;
  }

  for (const item of items) {
    try {
      const response = await fetch(item.url, {
        method: item.method,
        headers: new Headers(item.headers),
        body: item.body,
        credentials: 'include',
        redirect: 'manual',
      });
      const aceptada = (
        response.type === 'opaqueredirect'
        || response.headers.get('X-PWA-Accepted') === '1'
        || response.headers.get('X-PWA-Replayed') === '1'
      );
      if (aceptada) {
        await eliminarPendiente(item.id);
        await avisarClientes({type: 'OFFLINE_SYNCED', id: item.id});
      } else if (response.status === 401 || response.status === 403) {
        await avisarClientes({type: 'OFFLINE_AUTH_REQUIRED'});
        break;
      } else {
        await avisarClientes({type: 'OFFLINE_REVIEW_REQUIRED', id: item.id, url: item.url});
      }
    } catch (_) {
      break;
    }
  }
  await avisarClientes({type: 'OFFLINE_COUNT', count: (await pendientes()).length});
}

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_VERSION).then(cache => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key !== CACHE_VERSION).map(key => caches.delete(key))
  )));
  self.clients.claim();
});

self.addEventListener('sync', event => {
  if (event.tag === 'sincronizar-formularios') event.waitUntil(sincronizar());
});

self.addEventListener('message', event => {
  if (event.data?.type === 'SYNC_OUTBOX') event.waitUntil(sincronizar());
  if (event.data?.type === 'GET_OUTBOX_COUNT') {
    event.waitUntil(pendientes().then(items => avisarClientes({type:'OFFLINE_COUNT', count:items.length})));
  }
});

self.addEventListener('fetch', event => {
  const original = event.request;
  const url = new URL(original.url);
  const noEncolar = (
    ['/login/', '/logout/', '/registro/'].includes(url.pathname)
    || url.pathname.startsWith('/admin/')
    || url.pathname.includes('/eliminar/')
    || url.pathname.includes('/toggle-activo/')
    || url.pathname.includes('/enviar-correo/')
  );

  if (original.method !== 'GET' && url.origin === self.location.origin && !noEncolar) {
    event.respondWith((async () => {
      const copiaCola = original.clone();
      const headers = new Headers(original.headers);
      const id = headers.get('X-PWA-Request-ID') || crypto.randomUUID();
      headers.set('X-PWA-Request-ID', id);
      try {
        return await fetch(new Request(original, {headers}));
      } catch (_) {
        await guardarPendiente(copiaCola, id, headers);
        if ('sync' in self.registration) {
          await self.registration.sync.register('sincronizar-formularios');
        }
        if (original.mode === 'navigate') {
          return new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Guardado pendiente</title><style>body{font-family:system-ui;background:#f3f6fb;display:grid;place-items:center;min-height:100vh;margin:0;padding:24px}main{background:white;padding:36px;border-radius:16px;text-align:center;max-width:460px;box-shadow:0 10px 35px #0002}h1{color:#155bd5}button{background:#155bd5;color:white;border:0;border-radius:8px;padding:11px 20px}</style><main><h1>Guardado pendiente</h1><p>Conservamos tus datos en este dispositivo. Se sincronizarán automáticamente cuando vuelva internet.</p><button onclick="history.back()">Volver</button></main>`, {status: 202, headers:{'Content-Type':'text/html; charset=utf-8'}});
        }
        return new Response(JSON.stringify({ok:true, queued:true, request_id:id}), {
          status: 202, headers:{'Content-Type':'application/json'}
        });
      }
    })());
    return;
  }

  if (original.method !== 'GET') return;
  if (original.mode === 'navigate') {
    event.respondWith(fetch(original).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(original).then(cached => cached || fetch(original).then(response => {
      if (response.ok) {
        const copia = response.clone();
        caches.open(CACHE_VERSION).then(cache => cache.put(original, copia));
      }
      return response;
    })));
  }
});
