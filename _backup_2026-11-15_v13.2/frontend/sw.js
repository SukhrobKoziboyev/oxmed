// OXMED service worker (v8.7)
// 1) Ilova sahifasi (index.html) keshdan DARHOL ochiladi, shu payt orqada serverdan
//    yangisi tekshiriladi. Yangi versiya bo'lsa — sahifaga "yangilash" xabari yuboriladi
//    (yangilash majburiy oynasi chiqadi).
// 2) Ma'lumotlar (/api/...) HECH QACHON keshlanmaydi — har doim serverdan.
// 3) Push: yangi versiya chiqqanda (ilova yopiq bo'lsa ham) bildirishnoma + belgida "1".
const SHELL = 'oxmed-shell-v1';
const FLAG = '/__oxmed_update';
const STATIC = ['/logo.png', '/icon-ox-192.png', '/icon-ox-512.png', '/apple-touch-icon-ox.png', '/favicon-ox.png', '/manifest.json'];

self.addEventListener('install', (e) => {
    self.skipWaiting();
    e.waitUntil((async () => {
        try {
            const c = await caches.open(SHELL);
            const r = await fetch('/index.html', { cache: 'no-cache' });
            if (r.ok) await c.put('/index.html', r);
        } catch (err) {}
    })());
});
self.addEventListener('activate', (e) => e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k.startsWith('oxmed-') && k !== SHELL).map(k => caches.delete(k)));
    await self.clients.claim();
})()));

async function sameVersion(a, b) {
    const ea = a.headers.get('etag'), eb = b.headers.get('etag');
    if (ea && eb) return ea === eb;
    const la = a.headers.get('last-modified'), lb = b.headers.get('last-modified');
    if (la && lb) return la === lb;
    try { return (await a.clone().text()) === (await b.clone().text()); } catch (e) { return false; }
}

async function tellClients(msg) {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    all.forEach(c => { try { c.postMessage(msg); } catch (e) {} });
}

// Serverdan yangi index.html ni olib, keshdagisi bilan solishtiradi.
// O'zgargan bo'lsa keshni yangilaydi va true qaytaradi.
async function refreshShell() {
    const c = await caches.open(SHELL);
    const net = await fetch('/index.html', { cache: 'no-cache' });
    if (!net.ok) return { changed: false, net };
    const old = await c.match('/index.html');
    const changed = !!old && !(await sameVersion(old, net));
    await c.put('/index.html', net.clone());
    if (changed) {
        await c.put(FLAG, new Response(String(Date.now())));
        await tellClients({ type: 'oxmed-update' });
    }
    return { changed, net };
}

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);
    if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

    if (req.mode === 'navigate' && (url.pathname === '/' || url.pathname === '/index.html')) {
        event.respondWith((async () => {
            const c = await caches.open(SHELL);
            const cached = await c.match('/index.html');
            const fresh = refreshShell();
            if (cached) {
                event.waitUntil(fresh.catch(() => {}));
                return cached;
            }
            try { return (await fresh).net.clone(); } catch (e) { return fetch(req); }
        })());
        return;
    }

    if (STATIC.includes(url.pathname)) {
        event.respondWith((async () => {
            const c = await caches.open(SHELL);
            const cached = await c.match(url.pathname);
            const net = fetch(req).then(r => { if (r.ok) c.put(url.pathname, r.clone()); return r; });
            if (cached) { event.waitUntil(net.catch(() => {})); return cached; }
            return net;
        })());
    }
});

// Sahifadan buyruq: "yangi versiyani hozir yukla" (Yangilash tugmasi)
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'oxmed-check') {
        event.waitUntil(refreshShell().catch(() => {}));
    }
});

// v8.7: PUSH — yangi versiya chiqdi
self.addEventListener('push', (event) => {
    let d = {};
    try { d = event.data ? event.data.json() : {}; } catch (e) { d = { body: event.data ? event.data.text() : '' }; }
    if (d.kind === 'chat') { // v13.0: chatdagi yangi xabar
        event.waitUntil((async () => {
            try { if (self.navigator.setAppBadge) await self.navigator.setAppBadge(1); } catch (e) {}
            await self.registration.showNotification(d.title || 'OXMED — yangi xabar', {
                body: d.body || '', icon: '/icon-ox-192.png', badge: '/icon-ox-192.png',
                tag: d.tag || 'chat', renotify: true, data: { url: d.url || '/', chat: d.tid || null },
            });
        })());
        return;
    }
    event.waitUntil((async () => {
        try { if (self.navigator.setAppBadge) await self.navigator.setAppBadge(d.badge || 1); } catch (e) {}
        // Yangi versiyani oldindan yuklab qo'yamiz — ilova ochilganda darhol yangisi chiqadi
        try { await refreshShell(); } catch (e) {}
        await self.registration.showNotification(d.title || 'OXMED — yangi versiya 🔄', {
            body: d.body || 'Tizim yangilandi. Ochish uchun bosing.',
            icon: '/icon-ox-192.png',
            badge: '/icon-ox-192.png',
            tag: d.tag || 'oxmed-update',
            renotify: true,
            data: { url: d.url || '/' },
        });
    })());
});

// Bildirishnoma bosilganda ilovani ochish
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const chat = event.notification.data && event.notification.data.chat;
    if (chat) { // v13.0: chat xabari — ochiq ilovada suhbatni ochamiz
        event.waitUntil((async () => {
            const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
            for (const c of all) { if ('focus' in c) { c.postMessage({ type: 'open-chat', tid: chat }); return c.focus(); } }
            if (self.clients.openWindow) return self.clients.openWindow('/?chat=' + chat);
        })());
        return;
    }
    event.waitUntil((async () => {
        const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const c of all) {
            if ('focus' in c) { try { await c.navigate(c.url.split('?')[0] + '?v=' + Date.now().toString(36)); } catch (e) {} return c.focus(); }
        }
        if (self.clients.openWindow) return self.clients.openWindow('/?v=' + Date.now().toString(36));
    })());
});
