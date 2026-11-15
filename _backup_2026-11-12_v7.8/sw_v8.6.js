// OXMED - oddiy service worker (ilovani telefonga o'rnatish uchun kerak).
// Hech narsani keshlamaydi: sahifa va ma'lumotlar har doim serverdan yangi olinadi,
// shuning uchun yangilanishlar darhol ko'rinadi.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => { /* tarmoqdan odatdagidek olinadi */ });

// v8.4: "yangi versiya" bildirishnomasi bosilganda ilovani ochish
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil((async () => {
        const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const c of all) {
            if ('focus' in c) { try { await c.navigate(c.url.split('?')[0] + '?v=' + Date.now().toString(36)); } catch (e) {} return c.focus(); }
        }
        if (self.clients.openWindow) return self.clients.openWindow('/?v=' + Date.now().toString(36));
    })());
});
