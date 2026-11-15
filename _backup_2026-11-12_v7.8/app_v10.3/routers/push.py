"""v8.7: Web Push — yangi versiya chiqqanda hamma qurilmalarga bildirishnoma.

- Kalitlar (VAPID) birinchi marta avtomatik yaratiladi va backend/vapid_keys.json
  faylida saqlanadi (maxfiy kalit tashqariga hech qachon chiqmaydi).
- Brauzer obunani /api/push/subscribe ga yuboradi.
- Yuborish faqat serverning o'zida: `venv/bin/python -m app.push_notify "matn"`
  (HTTP orqali hech kim yubora olmaydi).
"""
import base64
import json
import os
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, auth
from ..database import get_db
from ..utils import now_timestamp_ms

router = APIRouter(prefix="/api/push", tags=["push"])

VAPID_FILE = Path(os.getenv("VAPID_FILE", str(Path(__file__).resolve().parents[2] / "vapid_keys.json")))
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "https://oxmed.uz")
_lock = threading.Lock()
_cache = {}


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def get_vapid() -> dict:
    """{'private_pem': str, 'public_key': base64url} — bo'lmasa yaratadi."""
    if _cache:
        return _cache
    with _lock:
        if _cache:
            return _cache
        if not VAPID_FILE.exists():
            from py_vapid import Vapid02
            from cryptography.hazmat.primitives import serialization
            v = Vapid02()
            v.generate_keys()
            data = {
                "private_pem": v.private_pem().decode(),
                "public_key": _b64u(v.public_key.public_bytes(
                    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
            }
            tmp = VAPID_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            os.chmod(tmp, 0o600)
            try:
                os.link(tmp, VAPID_FILE)  # boshqa jarayon bilan poyga bo'lsa, birinchisi yutadi
            except FileExistsError:
                pass
            finally:
                tmp.unlink(missing_ok=True)
        _cache.update(json.loads(VAPID_FILE.read_text()))
        return _cache


class SubKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeIn(BaseModel):
    endpoint: str
    keys: SubKeys
    expirationTime: Optional[float] = None


class UnsubscribeIn(BaseModel):
    endpoint: str


@router.get("/key")
def public_key():
    return {"public_key": get_vapid()["public_key"]}


@router.post("/subscribe")
def subscribe(
    data: SubscribeIn,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if not data.endpoint.startswith("https://") or len(data.endpoint) > 2000:
        raise HTTPException(status_code=400, detail="Noto'g'ri obuna manzili")
    now = now_timestamp_ms()
    ua = (request.headers.get("user-agent") or "")[:255]
    sub = db.query(models.PushSubscription).filter(models.PushSubscription.endpoint == data.endpoint).first()
    if sub:
        sub.p256dh, sub.auth = data.keys.p256dh[:255], data.keys.auth[:255]
        sub.user_id, sub.user_agent, sub.updated_at = current_user.id, ua, now
    else:
        db.add(models.PushSubscription(
            endpoint=data.endpoint, p256dh=data.keys.p256dh[:255], auth=data.keys.auth[:255],
            user_id=current_user.id, user_agent=ua, created_at=now, updated_at=now,
        ))
    db.commit()
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(
    data: UnsubscribeIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    db.query(models.PushSubscription).filter(models.PushSubscription.endpoint == data.endpoint).delete()
    db.commit()
    return {"ok": True}


def send_to_all(db: Session, title: str, body: str, tag: str = "oxmed-update") -> dict:
    """Hamma obunalarga yuboradi. Eskirgan (404/410) obunalar o'chiriladi."""
    from py_vapid import Vapid02
    from pywebpush import webpush, WebPushException

    vapid = Vapid02.from_pem(get_vapid()["private_pem"].encode())
    payload = json.dumps({"title": title, "body": body, "tag": tag, "badge": 1, "url": "/"})
    sent = removed = failed = 0
    for sub in db.query(models.PushSubscription).all():
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload,
                vapid_private_key=vapid,
                vapid_claims={"sub": VAPID_SUBJECT if VAPID_SUBJECT.startswith(("mailto:", "https://")) else "https://oxmed.uz"},
                ttl=7 * 24 * 3600,
                headers={"Urgency": "high"},  # v9.1: darhol yetkazilsin
                timeout=10,
            )
            sent += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):
                db.delete(sub)
                removed += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    db.commit()
    return {"sent": sent, "removed": removed, "failed": failed}


# ====================================================================== v9.1: AVTOMATIK BILDIRISHNOMA
# Serverga yangi index.html yuklanishi bilan (15 soniya ichida) hamma obuna bo'lgan
# qurilmalarga push yuboriladi. Telefon o'chiq/oflayn bo'lsa — push xizmati (Google/Apple)
# xabarni 7 kungacha saqlab turadi va qurilma internetga ulanishi bilan yetkazadi.
import hashlib
import re as _re

_BASE = Path(__file__).resolve()
INDEX_CANDIDATES = [p for p in [
    os.getenv("INDEX_FILE"),
    str(_BASE.parents[3] / "index.html"),               # serverda: /var/www/oxmed/index.html
    str(_BASE.parents[3] / "frontend" / "index.html"),  # Mac'da: oxmed/frontend/index.html
] if p]
STATE_FILE = _BASE.parents[2] / ".last_index_hash"


def _index_path():
    for p in INDEX_CANDIDATES:
        if os.path.isfile(p):
            return Path(p)
    return None


def _file_hash(p: Path):
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def _version_of(p: Path) -> str:
    try:
        m = _re.search(r"Pro (\d+\.\d+)", p.read_text(encoding="utf-8", errors="ignore"))
        return f"Pro {m.group(1)}" if m else ""
    except OSError:
        return ""


def _watch_loop(interval: float):
    import time as _t
    from ..database import SessionLocal
    while True:
        try:
            p = _index_path()
            h = _file_hash(p) if p else None
            if h:
                last = STATE_FILE.read_text().strip() if STATE_FILE.exists() else ""
                if h != last:
                    _t.sleep(5)  # fayl to'liq yozilib bo'lishini kutamiz
                    if _file_hash(p) == h:
                        STATE_FILE.write_text(h)
                        ver = _version_of(p)
                        db = SessionLocal()
                        try:
                            r = send_to_all(db, "OXMED — yangi versiya 🔄",
                                            "Tizim yangilandi" + (f" ({ver})" if ver else "") + ". Ochish uchun bosing.")
                            print(f"[push] yangi versiya {ver}: {r}", flush=True)
                        finally:
                            db.close()
        except Exception as e:  # noqa: BLE001
            print(f"[push] kuzatuvchi xatosi: {e}", flush=True)
        _t.sleep(interval)


_watch_lock_fh = None


def start_update_watcher(interval: float = 15.0):
    """Faqat bitta jarayon kuzatadi (bir nechta uvicorn worker bo'lsa ham)."""
    global _watch_lock_fh
    if os.getenv("PUSH_WATCH", "1") == "0":
        return
    try:
        import fcntl
        _watch_lock_fh = open(_BASE.parents[2] / ".push_watch.lock", "w")
        fcntl.flock(_watch_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:  # noqa: BLE001 — boshqa jarayon allaqachon kuzatyapti
        return
    threading.Thread(target=_watch_loop, args=(interval,), daemon=True, name="oxmed-update-watcher").start()
