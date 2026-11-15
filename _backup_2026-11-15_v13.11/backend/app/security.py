"""v8.8: Xavfsizlik qatlami.

1) Parol terish hujumidan himoya (brute-force): ko'p xato urinishdan keyin vaqtincha bloklanadi.
2) <, > belgilarini kiritishni taqiqlash (sahifaga zararli kod joylashning oldini oladi).
3) Xavfsizlik sarlavhalari (clickjacking, MIME sniffing, keshlash).
"""
import json
import threading
import time

from fastapi import HTTPException, Request


# ---------------------------------------------------------------- 1) urinishlar cheklovi
class AttemptLimiter:
    """Kalit bo'yicha (masalan 'login:user:rahbar') xato urinishlarni sanaydi.
    `free` ta xatodan keyin blok: 1 daqiqa, keyin har safar 2 baravar, eng ko'pi 30 daqiqa."""

    def __init__(self, free: int = 5, base_lock: int = 60, max_lock: int = 1800, forget_after: int = 3600):
        self.free, self.base_lock, self.max_lock, self.forget_after = free, base_lock, max_lock, forget_after
        self._d = {}
        self._lock = threading.Lock()

    def check(self, *keys):
        now = time.time()
        with self._lock:
            for k in keys:
                if not k:
                    continue
                e = self._d.get(k)
                if e and e["until"] > now:
                    mins = max(1, int((e["until"] - now + 59) // 60))
                    raise HTTPException(
                        status_code=429,
                        detail=f"Juda ko'p noto'g'ri urinish. {mins} daqiqadan keyin qayta urinib ko'ring.",
                    )

    def fail(self, *keys):
        now = time.time()
        with self._lock:
            if len(self._d) > 20000:  # xotira to'lib ketmasin
                self._d = {k: v for k, v in self._d.items() if now - v["last"] < self.forget_after}
            for k in keys:
                if not k:
                    continue
                e = self._d.get(k)
                if not e or now - e["last"] > self.forget_after:
                    e = {"n": 0, "until": 0, "last": now}
                e["n"] += 1
                e["last"] = now
                if e["n"] >= self.free:
                    e["until"] = now + min(self.max_lock, self.base_lock * (2 ** (e["n"] - self.free)))
                self._d[k] = e

    def success(self, *keys):
        with self._lock:
            for k in keys:
                self._d.pop(k, None)


login_limiter = AttemptLimiter(free=5)
# maxfiy parol / tiklash kodi — qattiqroq
secret_limiter = AttemptLimiter(free=3, base_lock=300, max_lock=3600)


def client_ip(request: Request):
    """Haqiqiy IP (nginx orqali). Aniqlab bo'lmasa (hamma 127.0.0.1) — None,
    shunda IP bo'yicha cheklov qo'llanmaydi (hamma bloklanib qolmasin)."""
    ip = request.headers.get("x-real-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if not ip and request.client:
        ip = request.client.host
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return None
    return ip[:64]


# ---------------------------------------------------------------- 2) < > belgilari
SKIP_KEYS = ("password", "secret", "credential", "response", "token", "challenge", "chat_text")  # v13.0: chat matni ekranda doim escape qilinadi


def _bad_string(obj, key=""):
    k = (key or "").lower()
    if any(s in k for s in SKIP_KEYS):
        return False
    if isinstance(obj, str):
        return "<" in obj or ">" in obj
    if isinstance(obj, dict):
        return any(_bad_string(v, kk) for kk, v in obj.items())
    if isinstance(obj, list):
        return any(_bad_string(v, key) for v in obj)
    return False


SEC_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"same-origin"),
    (b"cache-control", b"no-store"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


class SecurityMiddleware:
    """Sof ASGI middleware: JSON so'rovlarda < > ni rad etadi va /api javoblariga
    xavfsizlik sarlavhalarini qo'shadi."""

    MAX_BODY = 25 * 1024 * 1024

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                names = {h[0].lower() for h in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [h for h in SEC_HEADERS if h[0] not in names]
            await send(message)

        method = scope.get("method", "GET")
        ctype = ""
        for k, v in scope.get("headers", []):
            if k == b"content-type":
                ctype = v.decode("latin-1").lower()
        if method in ("POST", "PUT", "PATCH") and "application/json" in ctype:
            chunks, size = [], 0
            more = True
            while more:
                msg = await receive()
                if msg["type"] == "http.disconnect":
                    return
                b = msg.get("body", b"")
                size += len(b)
                if size > self.MAX_BODY:
                    return await self._reply(send_wrapper, 413, "So'rov juda katta")
                chunks.append(b)
                more = msg.get("more_body", False)
            body = b"".join(chunks)
            try:
                data = json.loads(body) if body else None
            except Exception:
                data = None
            if data is not None and _bad_string(data):
                return await self._reply(send_wrapper, 400, "Matnda < yoki > belgilaridan foydalanib bo'lmaydi.")
            sent = False

            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            return await self.app(scope, replay, send_wrapper)
        return await self.app(scope, receive, send_wrapper)

    @staticmethod
    async def _reply(send, code, text):
        payload = json.dumps({"detail": text}).encode()
        await send({"type": "http.response.start", "status": code,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]})
        await send({"type": "http.response.body", "body": payload})
