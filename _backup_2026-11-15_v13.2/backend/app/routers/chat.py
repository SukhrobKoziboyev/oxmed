"""v13.0: CHAT — Telegram uslubida xodimlar o'rtasida yozishma.

* Kimlar: rahbar, administrator, o'qituvchilar va xodimlar (yo'qlamachi — yo'q).
* Shaxsiy suhbat (direct) — faqat ikki ishtirokchi ko'radi; rahbar ham boshqalarning yozishmasini ko'ra olmaydi.
* Umumiy guruh (g:all) — hamma a'zo.
* Profilda faqat ism, rol, fan/lavozim va "onlayn"/"oxirgi marta" — telefon, login, summalar YO'Q.
* O'qildi belgisi: chat_members.last_read_id (ikki ✓✓ — suhbatdosh o'qigan).
* Yangi xabar — qabul qiluvchilarning qurilmalariga Web Push (ilova yopiq bo'lsa ham).
Hisob-kitobga hech qanday aloqasi yo'q.
"""
import json
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, auth
from ..database import get_db, SessionLocal
from ..utils import now_timestamp_ms

router = APIRouter(prefix="/api/chat", tags=["chat"])

CHAT_ROLES = ("Markaz rahbari", "Administrator", "O'qituvchi")
GROUP_KEY = "g:all"
GROUP_TITLE = "OLMOS XATAMOV — umumiy guruh"
ONLINE_MS = 70 * 1000
MAX_LEN = 4000
_flood = defaultdict(deque)   # user_id -> oxirgi yuborish vaqtlari
_away = {}                    # v13.1: user_id -> ilovadan chiqqan vaqti (darhol "oxirgi marta ..." ko'rinsin)


def require_chat(current_user: models.User = Depends(auth.get_current_user)) -> models.User:
    if current_user.role not in CHAT_ROLES:
        raise HTTPException(status_code=403, detail="Chat siz uchun yopiq.")
    return current_user


def _touch(db: Session, u: models.User):
    now = now_timestamp_ms()
    came_back = _away.pop(u.id, None) is not None
    if came_back or not u.last_seen or now - u.last_seen > 15000:
        u.last_seen = now
        db.commit()


class _Who:
    """Foydalanuvchini ko'rsatish: Rahbar / Admin / o'qituvchi ismi (so'rov ichida keshlanadi)."""
    def __init__(self, db: Session):
        self.db, self.cache, self._teachers = db, {}, None

    def teachers(self):
        if self._teachers is None:
            self._teachers = {t.id: t for t in self.db.query(models.Teacher).all()}
        return self._teachers

    def of(self, u: Optional[models.User]) -> dict:
        if u is None:
            return {"id": None, "name": "O'chirilgan foydalanuvchi", "sub": "", "kind": "gone", "online": False, "last_seen": None}
        if u.id in self.cache:
            return self.cache[u.id]
        name, sub, kind = u.username, "", "other"
        if u.role == "Markaz rahbari":
            name, sub, kind = "Rahbar", "Markaz rahbari", "rahbar"
        elif u.role == "Administrator":
            name, sub, kind = "Admin", "Administrator", "admin"
        elif u.teacher_id:
            t = self.teachers().get(u.teacher_id)
            if t:
                name = t.name
                if getattr(t, "is_staff", False):
                    kind, sub = "staff", (t.position or "Xodim")
                else:
                    kind, sub = "teacher", ((t.subject.name + " o'qituvchisi") if t.subject else "O'qituvchi")
        ls = u.last_seen
        online = bool(ls and now_timestamp_ms() - ls < ONLINE_MS) and u.id not in _away
        d = {"id": u.id, "name": name, "sub": sub, "kind": kind, "online": online, "last_seen": ls}
        self.cache[u.id] = d
        return d


def _eligible(db: Session):
    return db.query(models.User).filter(models.User.role.in_(CHAT_ROLES)).all()


def _group(db: Session, users=None) -> models.ChatThread:
    g = db.query(models.ChatThread).filter(models.ChatThread.key == GROUP_KEY).first()
    now = now_timestamp_ms()
    if not g:
        g = models.ChatThread(kind="group", key=GROUP_KEY, title=GROUP_TITLE, created_at=now)
        db.add(g)
        db.flush()
    have = {m.user_id for m in db.query(models.ChatMember).filter(models.ChatMember.thread_id == g.id).all()}
    added = False
    for u in (users if users is not None else _eligible(db)):
        if u.id not in have:
            # yangi a'zo eski xabarlarni "o'qilmagan" deb ko'rmasin
            db.add(models.ChatMember(thread_id=g.id, user_id=u.id, last_read_id=g.last_msg_id or 0, joined_at=now))
            added = True
    if added:
        db.commit()
    return g


def _member(db: Session, tid: int, user: models.User) -> models.ChatMember:
    m = db.query(models.ChatMember).filter(models.ChatMember.thread_id == tid, models.ChatMember.user_id == user.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Suhbat topilmadi.")
    return m


def _others_read(db: Session, tid: int, me_id: int) -> int:
    v = db.query(func.max(models.ChatMember.last_read_id)).filter(
        models.ChatMember.thread_id == tid, models.ChatMember.user_id != me_id).scalar()
    return int(v or 0)


def _unread(db: Session, tid: int, me: models.User, last_read: int) -> int:
    return db.query(func.count(models.ChatMessage.id)).filter(
        models.ChatMessage.thread_id == tid, models.ChatMessage.id > last_read,
        models.ChatMessage.deleted.is_(False),
        (models.ChatMessage.sender_id.is_(None)) | (models.ChatMessage.sender_id != me.id)).scalar() or 0


def _sname(m: models.ChatMessage, who: _Who, users: dict) -> str:
    s = who.of(users.get(m.sender_id)) if m.sender_id and users.get(m.sender_id) else None
    return s["name"] if s else (m.sender_name or "O'chirilgan foydalanuvchi")


def _msg(m: models.ChatMessage, me: models.User, who: _Who, users: dict, replies: Optional[dict] = None) -> dict:
    s = who.of(users.get(m.sender_id)) if m.sender_id else None
    d = {"id": m.id, "mine": m.sender_id == me.id, "sender_id": m.sender_id,
         "sender_name": (s["name"] if s and s["id"] else (m.sender_name or "O'chirilgan foydalanuvchi")),
         "sender_kind": (s["kind"] if s else "gone"),
         "text": "" if m.deleted else m.text, "deleted": bool(m.deleted), "at": m.created_at, "reply": None}
    rid = getattr(m, "reply_to_id", None)
    if rid and replies is not None:
        r = replies.get(rid)
        d["reply"] = {"id": rid, "sender_id": r.sender_id if r else None,
                      "sender_name": _sname(r, who, users) if r else "", "deleted": (not r) or bool(r.deleted),
                      "text": "" if (not r or r.deleted) else r.text[:160]}
    return d


def _with_replies(db: Session, rows, users: dict) -> dict:
    """Javob berilgan xabarlarni va ularning yozuvchilarini bir so'rovda yuklaydi."""
    ids = {m.reply_to_id for m in rows if getattr(m, "reply_to_id", None)}
    if not ids:
        return {}
    reps = {r.id: r for r in db.query(models.ChatMessage).filter(models.ChatMessage.id.in_(ids)).all()}
    need = {r.sender_id for r in reps.values() if r.sender_id and r.sender_id not in users}
    if need:
        for u in db.query(models.User).filter(models.User.id.in_(need)).all():
            users[u.id] = u
    return reps


def _peer(db: Session, t: models.ChatThread, me: models.User):
    if t.kind != "direct":
        return None
    m = db.query(models.ChatMember).filter(models.ChatMember.thread_id == t.id, models.ChatMember.user_id != me.id).first()
    return db.query(models.User).filter(models.User.id == m.user_id).first() if m else None


# ------------------------------------------------------------------ ro'yxat
@router.get("/state")
def state(me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    _touch(db, me)
    users = _eligible(db)
    umap = {u.id: u for u in users}
    who = _Who(db)
    g = _group(db, users)
    mems = db.query(models.ChatMember).filter(models.ChatMember.user_id == me.id).all()
    threads = {t.id: t for t in db.query(models.ChatThread).filter(models.ChatThread.id.in_([m.thread_id for m in mems] or [0])).all()}
    last_ids = [t.last_msg_id for t in threads.values() if t.last_msg_id]
    lasts = {m.id: m for m in db.query(models.ChatMessage).filter(models.ChatMessage.id.in_(last_ids or [0])).all()}
    peers = {}
    for m in db.query(models.ChatMember).filter(models.ChatMember.thread_id.in_(list(threads) or [0]), models.ChatMember.user_id != me.id).all():
        if threads[m.thread_id].kind == "direct":
            peers[m.thread_id] = m.user_id
    chats, total = [], 0
    for mm in mems:
        t = threads.get(mm.thread_id)
        if not t:
            continue
        un = _unread(db, t.id, me, mm.last_read_id)
        total += un
        lm = lasts.get(t.last_msg_id)
        item = {"id": t.id, "kind": t.kind, "title": t.title, "unread": un,
                "last": _msg(lm, me, who, umap) if lm else None,
                "last_read_by_others": _others_read(db, t.id, me.id) if lm and lm.sender_id == me.id else 0}
        if t.kind == "direct":
            pu = umap.get(peers.get(t.id))
            if pu is None:
                continue  # suhbatdosh o'chirilgan / chat huquqi yo'q
            item["peer"] = who.of(pu)
        else:
            item["members"] = len(users)
        chats.append(item)
    contacts = [who.of(u) for u in users if u.id != me.id]
    return {"me": who.of(me), "chats": chats, "contacts": contacts, "unread_total": total,
            "group_id": g.id, "now": now_timestamp_ms()}


@router.get("/unread")
def unread(me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    """Pastki menyudagi belgi uchun — yengil so'rov."""
    _touch(db, me)
    total = 0
    for mm in db.query(models.ChatMember).filter(models.ChatMember.user_id == me.id).all():
        total += _unread(db, mm.thread_id, me, mm.last_read_id)
    return {"total": total}


class OpenIn(BaseModel):
    user_id: int


@router.post("/open")
def open_direct(data: OpenIn, me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    if data.user_id == me.id:
        raise HTTPException(status_code=400, detail="O'zingizga yozib bo'lmaydi.")
    peer = db.query(models.User).filter(models.User.id == data.user_id).first()
    if not peer or peer.role not in CHAT_ROLES:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi.")
    a, b = sorted((me.id, peer.id))
    key = f"d:{a}:{b}"
    t = db.query(models.ChatThread).filter(models.ChatThread.key == key).first()
    if not t:
        now = now_timestamp_ms()
        t = models.ChatThread(kind="direct", key=key, created_at=now)
        db.add(t)
        db.flush()
        db.add(models.ChatMember(thread_id=t.id, user_id=me.id, last_read_id=0, joined_at=now))
        db.add(models.ChatMember(thread_id=t.id, user_id=peer.id, last_read_id=0, joined_at=now))
        db.commit()
    return {"thread_id": t.id}


# ------------------------------------------------------------------ suhbat
@router.get("/thread/{tid}")
def thread(tid: int, after: int = 0, before: int = 0, limit: int = 60,
           me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    _touch(db, me)
    mm = _member(db, tid, me)
    t = db.query(models.ChatThread).filter(models.ChatThread.id == tid).first()
    limit = max(1, min(limit, 200))
    q = db.query(models.ChatMessage).filter(models.ChatMessage.thread_id == tid)
    if after:
        rows = q.filter(models.ChatMessage.id > after).order_by(models.ChatMessage.id.asc()).limit(limit).all()
    else:
        if before:
            q = q.filter(models.ChatMessage.id < before)
        rows = list(reversed(q.order_by(models.ChatMessage.id.desc()).limit(limit).all()))
    ids = {m.sender_id for m in rows if m.sender_id}
    peer = _peer(db, t, me)
    if peer:
        ids.add(peer.id)
    umap = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(ids or [0])).all()}
    who = _Who(db)
    reps = _with_replies(db, rows, umap)
    out = {"thread": {"id": t.id, "kind": t.kind, "title": t.title, "last_msg_id": t.last_msg_id or 0},
           "messages": [_msg(m, me, who, umap, reps) for m in rows],
           "others_read_id": _others_read(db, tid, me.id), "my_last_read": mm.last_read_id,
           "has_more": bool(rows) and not after and len(rows) == limit}
    if peer:
        out["thread"]["peer"] = who.of(peer)
    else:
        out["thread"]["members"] = db.query(func.count(models.ChatMember.id)).filter(models.ChatMember.thread_id == tid).scalar()
    return out


class SendIn(BaseModel):
    chat_text: str = Field(..., max_length=MAX_LEN + 100)
    reply_to: Optional[int] = None


def _push(tid: int, sender_id: int, title: str, body: str):
    """Qabul qiluvchilarning qurilmalariga Web Push (orqada)."""
    db = SessionLocal()
    try:
        from .push import get_vapid, VAPID_SUBJECT
        from py_vapid import Vapid02
        from pywebpush import webpush, WebPushException
        uids = [m.user_id for m in db.query(models.ChatMember).filter(models.ChatMember.thread_id == tid, models.ChatMember.user_id != sender_id).all()]
        if not uids:
            return
        subs = db.query(models.PushSubscription).filter(models.PushSubscription.user_id.in_(uids)).all()
        if not subs:
            return
        vapid = Vapid02.from_pem(get_vapid()["private_pem"].encode())
        claims = {"sub": VAPID_SUBJECT if VAPID_SUBJECT.startswith(("mailto:", "https://")) else "https://oxmed.uz"}
        for s in subs:
            payload = json.dumps({"kind": "chat", "tid": tid, "title": title, "body": body[:140],
                                  "tag": f"chat-{tid}", "url": f"/?chat={tid}"})
            try:
                webpush(subscription_info={"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                        data=payload, vapid_private_key=vapid, vapid_claims=dict(claims),
                        ttl=3 * 24 * 3600, headers={"Urgency": "high"}, timeout=10)
            except WebPushException as e:
                if getattr(e.response, "status_code", None) in (404, 410):
                    db.delete(s)
            except Exception:  # noqa: BLE001
                pass
        db.commit()
    except Exception:  # noqa: BLE001
        pass
    finally:
        db.close()


@router.post("/thread/{tid}/send")
def send(tid: int, data: SendIn, bg: BackgroundTasks, me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    mm = _member(db, tid, me)
    text = (data.chat_text or "").replace("\r\n", "\n").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Xabar bo'sh.")
    if len(text) > MAX_LEN:
        raise HTTPException(status_code=400, detail=f"Xabar juda uzun (ko'pi bilan {MAX_LEN} belgi).")
    q, now_s = _flood[me.id], time.time()
    while q and now_s - q[0] > 60:
        q.popleft()
    if len(q) >= 40:
        raise HTTPException(status_code=429, detail="Juda tez yozyapsiz — biroz kuting.")
    q.append(now_s)
    who = _Who(db)
    mine = who.of(me)
    t = db.query(models.ChatThread).filter(models.ChatThread.id == tid).first()
    reply_to = None
    if data.reply_to:
        r = db.query(models.ChatMessage).filter(models.ChatMessage.id == data.reply_to, models.ChatMessage.thread_id == tid).first()
        reply_to = r.id if r else None
    m = models.ChatMessage(thread_id=tid, sender_id=me.id, sender_name=mine["name"], text=text, created_at=now_timestamp_ms(),
                           deleted=False, reply_to_id=reply_to)
    db.add(m)
    db.flush()
    t.last_msg_id = m.id
    mm.last_read_id = m.id
    me.last_seen = m.created_at
    db.commit()
    title = mine["name"] if t.kind == "direct" else f"{mine['name']} • Umumiy guruh"
    bg.add_task(_push, tid, me.id, title, text)
    umap = {me.id: me}
    return _msg(m, me, who, umap, _with_replies(db, [m], umap))


class ReadIn(BaseModel):
    last_id: int


@router.post("/thread/{tid}/read")
def mark_read(tid: int, data: ReadIn, me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    mm = _member(db, tid, me)
    t = db.query(models.ChatThread).filter(models.ChatThread.id == tid).first()
    v = min(int(data.last_id or 0), t.last_msg_id or 0)
    if v > mm.last_read_id:
        mm.last_read_id = v
        db.commit()
    return {"last_read_id": mm.last_read_id}


@router.delete("/message/{mid}")
def delete_message(mid: int, me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    m = db.query(models.ChatMessage).filter(models.ChatMessage.id == mid).first()
    if not m or m.sender_id != me.id:
        raise HTTPException(status_code=404, detail="Xabar topilmadi.")
    _member(db, m.thread_id, me)
    m.deleted, m.text = True, ""
    db.commit()
    return {"ok": True}


@router.get("/user/{uid}")
def profile(uid: int, me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    """Profil: ism, fan/lavozim, onlayn holati va (bo'lsa) ish telefoni. Login/parol/summalar berilmaydi.
    v13.2: Sukhrob — xodim profilida telefon raqami va qaysi fan o'qituvchisi ekani ko'rinsin."""
    u = db.query(models.User).filter(models.User.id == uid).first()
    if not u or u.role not in CHAT_ROLES:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi.")
    d = dict(_Who(db).of(u))
    phone = None
    if u.teacher_id:
        t = db.query(models.Teacher).filter(models.Teacher.id == u.teacher_id).first()
        phone = t.phone if t else None
    d["phone"] = phone
    return d


# ------------------------------------------------------------------ v13.1
@router.get("/message/{mid}/reads")
def message_reads(mid: int, me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    """Kimlar o'qidi (faqat o'z xabari uchun) — Telegram'dagi kabi."""
    m = db.query(models.ChatMessage).filter(models.ChatMessage.id == mid).first()
    if not m or m.sender_id != me.id:
        raise HTTPException(status_code=404, detail="Xabar topilmadi.")
    _member(db, m.thread_id, me)
    mems = db.query(models.ChatMember).filter(models.ChatMember.thread_id == m.thread_id, models.ChatMember.user_id != me.id).all()
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([x.user_id for x in mems] or [0])).all()}
    who = _Who(db)
    read, unread = [], []
    for x in mems:
        u = users.get(x.user_id)
        if not u or u.role not in CHAT_ROLES:
            continue
        (read if x.last_read_id >= mid else unread).append(who.of(u))
    key = lambda p: p["name"].lower()
    return {"read": sorted(read, key=key), "unread": sorted(unread, key=key)}


@router.post("/away")
def away(me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    """Ilova yopildi / fonga o'tdi — darhol "oxirgi marta HH:MM da" ko'rinadi."""
    me.last_seen = now_timestamp_ms()
    _away[me.id] = me.last_seen
    db.commit()
    return {"ok": True}


@router.get("/me")
def my_profile(me: models.User = Depends(require_chat), db: Session = Depends(get_db)):
    """O'z profilim: ism, lavozim va (bo'lsa) telefonim — faqat o'zimga."""
    d = dict(_Who(db).of(me))
    d["online"] = True
    phone = None
    if me.teacher_id:
        t = db.query(models.Teacher).filter(models.Teacher.id == me.teacher_id).first()
        phone = t.phone if t else None
    d["phone"] = phone
    return d
