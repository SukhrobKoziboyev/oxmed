"""v13.15: OXIRGI AMALLAR (harakatlar jurnali) — tizimdagi HAR BIR o'zgarish: kim, nima, kimga, qachon (soniyasigacha).

Ikki qatlam:
  1) AuditMiddleware — har bir muvaffaqiyatli o'zgartiruvchi so'rov (POST/PUT/DELETE) avtomatik yoziladi
     (hech narsa tushib qolmaydi). Matn — ROUTES jadvalidan umumiy nom.
  2) note(...) — muhim joylarda endpoint o'zi inson tilida batafsil matn beradi
     ("To'lovni tahrirladi: Aliyev Vali — 500 000 → 450 000"). Middleware shu matnni ishlatadi.
Parollar HECH QACHON yozilmaydi. Chat yozishmalari, push, AI so'rovlari yozilmaydi (maxfiylik / shovqin).
Yozuvlar 30 kun saqlanadi, keyin o'zi o'chadi. Faqat rahbar ko'radi.
"""
import contextvars
import re
import threading
import time

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

KEEP_DAYS = 30
_cv = contextvars.ContextVar("ox_audit", default=None)
_purge = {"at": 0.0}
_plock = threading.Lock()


def note(title: str, cat: str = None, entity: str = None, entity_id=None, details: dict = None,
         username: str = None, force: bool = False):
    """Endpoint ichidan: shu so'rov uchun tushunarli yozuv. Bir so'rovda bir necha marta chaqirilsa — qo'shib boriladi."""
    box = _cv.get()
    if box is None:
        return
    items = box.setdefault("items", [])
    items.append({"title": (title or "")[:500], "cat": cat, "entity": entity, "entity_id": entity_id,
                  "details": details or None})
    if username:
        box["username"] = username
    if force:
        box["force"] = True


def skip():
    """Shu so'rovni jurnalga yozmaslik (masalan hech narsa o'zgarmagan bo'lsa)."""
    box = _cv.get()
    if box is not None:
        box["skip"] = True


def money(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n)


# ---------- umumiy nomlar (note bo'lmasa) ----------
ROUTES = [
    # (metod, regex, kategoriya, matn)
    ("POST", r"^/api/payments$", "pay", "To'lov kiritdi"),
    ("PUT", r"^/api/payments/\d+$", "pay", "To'lovni tahrirladi"),
    ("DELETE", r"^/api/payments/\d+$", "pay", "To'lovni o'chirdi"),
    ("PUT", r"^/api/dues$", "pay", "O'quvchi qarzini belgiladi"),
    ("POST", r"^/api/students$", "stu", "O'quvchi qo'shdi"),
    ("POST", r"^/api/students/bulk$", "stu", "O'quvchilarni ro'yxat bilan yukladi"),
    ("PUT", r"^/api/students/\d+$", "stu", "O'quvchi ma'lumotini tahrirladi"),
    ("DELETE", r"^/api/students/\d+$", "stu", "O'quvchini o'chirdi"),
    ("POST", r"^/api/students/\d+/archive$", "stu", "O'quvchini arxivga o'tkazdi"),
    ("POST", r"^/api/students/\d+/restore$", "stu", "O'quvchini arxivdan qaytardi"),
    ("POST", r"^/api/students/\d+/merge$", "stu", "Ikki o'quvchini birlashtirdi"),
    ("POST", r"^/api/teacher/students$", "stu", "O'qituvchi o'quvchi qo'shdi"),
    ("DELETE", r"^/api/teacher/students/\d+/link$", "stu", "O'qituvchi o'quvchini ro'yxatidan chiqardi"),
    ("POST", r"^/api/teacher/groups$", "stu", "O'qituvchi guruh qo'shdi"),
    ("DELETE", r"^/api/teacher/groups/\d+$", "stu", "O'qituvchi guruhni o'chirdi"),
    ("PUT", r"^/api/teacher/phone$", "staff", "Telefon raqamini o'zgartirdi"),
    ("POST", r"^/api/expenses$", "exp", "Xarajat kiritdi"),
    ("PUT", r"^/api/expenses/\d+$", "exp", "Xarajatni tahrirladi"),
    ("DELETE", r"^/api/expenses/\d+$", "exp", "Xarajatni o'chirdi"),
    ("POST", r"^/api/expenses/\d+/restore$", "exp", "O'chirilgan xarajatni tikladi"),
    ("POST", r"^/api/salary/payout$", "sal", "Oylik / avans berdi"),
    ("DELETE", r"^/api/salary/payout/\d+$", "sal", "Oylik / avans yozuvini o'chirdi"),
    ("POST", r"^/api/staff$", "staff", "Xodim qo'shdi"),
    ("PUT", r"^/api/staff/\d+$", "staff", "Xodim ma'lumotini tahrirladi"),
    ("DELETE", r"^/api/staff/\d+$", "staff", "Xodimni o'chirdi"),
    ("POST", r"^/api/staff/\d+/merge$", "staff", "Xodimni o'qituvchiga birlashtirdi"),
    ("POST", r"^/api/staff/\d+/accrual$", "sal", "Xodimga bonus / qo'shimcha hisobladi"),
    ("PUT", r"^/api/staff/accrual/\d+$", "sal", "Hisoblangan oylikni tahrirladi"),
    ("DELETE", r"^/api/staff/accrual/\d+$", "sal", "Hisoblangan oylikni bekor qildi"),
    ("POST", r"^/api/teachers$", "staff", "O'qituvchi qo'shdi"),
    ("DELETE", r"^/api/teachers/\d+$", "staff", "O'qituvchini o'chirdi"),
    ("PUT", r"^/api/teachers/\d+/phone$", "staff", "O'qituvchi/xodim telefonini o'zgartirdi"),
    ("PUT", r"^/api/teachers/\d+/percent$", "staff", "O'qituvchi ulush foizini o'zgartirdi"),
    ("PUT", r"^/api/teachers/\d+/access$", "login", "Ruxsatlar / qo'shimcha oylikni o'zgartirdi"),
    ("POST", r"^/api/teachers/\d+/groups$", "staff", "Guruh qo'shdi"),
    ("DELETE", r"^/api/groups/\d+$", "staff", "Guruhni o'chirdi"),
    ("POST", r"^/api/teachers/\d+/login$", "login", "O'qituvchiga login berdi / o'zgartirdi"),
    ("DELETE", r"^/api/teachers/\d+/login$", "login", "O'qituvchi loginini o'chirdi"),
    ("POST", r"^/api/subjects$", "set", "Fan qo'shdi"),
    ("PUT", r"^/api/subjects/\d+$", "set", "Fanni tahrirladi"),
    ("DELETE", r"^/api/subjects/\d+$", "set", "Fanni o'chirdi"),
    ("PUT", r"^/api/subjects/\d+/percent$", "set", "Fan ulush foizini o'zgartirdi"),
    ("POST", r"^/api/auth/login$", "login", "Tizimga kirdi"),
    ("POST", r"^/api/webauthn/login/verify$", "login", "Barmoq izi / Face ID bilan kirdi"),
    ("POST", r"^/api/webauthn/register/verify$", "login", "Barmoq izi / Face ID qo'shdi"),
    ("DELETE", r"^/api/webauthn/credentials/\d+$", "login", "Barmoq izi qurilmasini o'chirdi"),
    ("POST", r"^/api/auth/change-my-credentials$", "login", "O'z login / parolini o'zgartirdi"),
    ("POST", r"^/api/auth/change-admin-credentials$", "login", "Admin login / parolini o'zgartirdi"),
    ("POST", r"^/api/auth/recover-password$", "login", "Maxfiy parol bilan rahbar parolini tikladi"),
    ("POST", r"^/api/auth/change-secret-password$", "login", "Maxfiy parolni o'zgartirdi"),
    ("PUT", r"^/api/auth/users/\d+/credentials$", "login", "Xodimning login / parolini o'zgartirdi"),
    ("POST", r"^/api/auth/att-user$", "login", "Yo'qlamachi loginini o'zgartirdi"),
    ("DELETE", r"^/api/auth/att-user$", "login", "Yo'qlamachi loginini o'chirdi"),
    ("GET", r"^/api/auth/staff-credentials$", "login", "Xodimlarning login-parollarini ko'rdi"),
    ("GET", r"^/api/backup$", "set", "To'liq zaxira (backup) yuklab oldi"),
    ("POST", r"^/api/backup/restore$", "set", "Zaxiradan (backup) tikladi"),
    ("POST", r"^/api/backup/clear-all$", "set", "Tizimni tozaladi"),
    ("POST", r"^/api/recycle-bin/\d+/restore$", "set", "Qayta tiklash bo'limidan tikladi"),
    ("DELETE", r"^/api/recycle-bin/\d+$", "set", "Qayta tiklash bo'limidan butunlay o'chirdi"),
    ("PUT", r"^/api/settings/sms-templates$", "set", "SMS shablonini o'zgartirdi"),
    ("POST", r"^/api/settings/phones$", "set", "Rahbar telefon raqamini qo'shdi"),
    ("DELETE", r"^/api/settings/phones/\d+$", "set", "Rahbar telefon raqamini o'chirdi"),
    ("PUT", r"^/api/sms/settings$", "set", "SMS sozlamalarini o'zgartirdi"),
    ("PUT", r"^/api/sms/templates$", "sms", "SMS matnlarini o'zgartirdi"),
    ("POST", r"^/api/sms/bulk$", "sms", "Ommaviy SMS yubordi"),
    ("POST", r"^/api/sms/test$", "sms", "Sinov SMS yubordi"),
    ("POST", r"^/api/school-att/mark$", "att", "Yo'qlama belgiladi"),
    ("POST", r"^/api/school-att/absent-rest$", "att", "Qolganlarni \"kelmadi\" deb belgiladi"),
    ("PUT", r"^/api/school-att/settings$", "att", "Darsga kelish vaqtini o'zgartirdi"),
    ("POST", r"^/api/attendance/session$", "att", "Guruh yo'qlamasini saqladi"),
    ("POST", r"^/api/bt-columns$", "pay", "Umumiy jadvalga ustun qo'shdi"),
    ("PUT", r"^/api/bt-columns/\d+$", "pay", "Umumiy jadval ustunini qayta nomladi"),
    ("DELETE", r"^/api/bt-columns/\d+$", "pay", "Umumiy jadval ustunini o'chirdi"),
    ("PUT", r"^/api/bt-columns/\d+/cells/\d+$", "pay", "Umumiy jadval katagini o'zgartirdi"),
]
_ROUTES = [(m, re.compile(rx), c, t) for m, rx, c, t in ROUTES]
SKIP = re.compile(r"^/api/(chat|push|ai|dev|health|audit|webauthn/(register|login)/options|teacher/dashboard|teacher/ledger)")
SENSITIVE_GET = re.compile(r"^/api/(auth/staff-credentials|backup)$")


def _route(method: str, path: str):
    for m, rx, c, t in _ROUTES:
        if m == method and rx.match(path):
            return c, t
    return None, None


def _ua(s: str) -> str:
    s = s or ""
    dev = "iPhone" if "iPhone" in s else "iPad" if "iPad" in s else "Android" if "Android" in s else \
        "Mac" if "Macintosh" in s else "Windows" if "Windows" in s else "Linux" if "Linux" in s else ""
    br = "Edge" if "Edg/" in s else "Opera" if "OPR/" in s else "Chrome" if ("Chrome/" in s or "CriOS" in s) else \
        "Firefox" if "Firefox" in s else "Safari" if "Safari" in s else ""
    return " • ".join(x for x in (dev, br) if x)[:80]


def _write(rec: dict):
    from .database import SessionLocal
    from . import models
    from .student_links import who_label
    db = SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.username == rec["username"]).first() if rec.get("username") else None
        who = who_label(db, rec["username"]) if u else (rec.get("username") or "Noma'lum")
        role = (u.role if u else "") or ""
        if u and u.teacher_id:
            t = db.query(models.Teacher).filter(models.Teacher.id == u.teacher_id).first()
            if t and t.is_staff:
                role = t.position or "Xodim"
        for it in rec["items"]:
            db.add(models.ActivityLog(
                at=rec["at"], username=(rec.get("username") or "")[:64], who=who[:200], role=role[:60],
                cat=(it.get("cat") or rec.get("cat") or "other")[:20], action=rec["action"][:80],
                title=(it.get("title") or rec.get("title") or rec["action"])[:500],
                details=it.get("details"), entity=(it.get("entity") or None), entity_id=it.get("entity_id"),
                ip=(rec.get("ip") or None), ua=(rec.get("ua") or None), status=rec.get("status")))
        now = time.time()
        with _plock:
            due = now - _purge["at"] > 3600
            if due:
                _purge["at"] = now
        if due:   # 30 kundan eskilari o'zi o'chadi
            db.query(models.ActivityLog).filter(models.ActivityLog.at < int((now - KEEP_DAYS * 86400) * 1000)).delete(synchronize_session=False)
        db.commit()
    except Exception as e:  # noqa: BLE001 — jurnal xatosi asosiy ishni buzmasin
        db.rollback()
        print(f"[audit] yozib bo'lmadi: {e}")
    finally:
        db.close()


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path, method = request.url.path.rstrip("/") or "/", request.method.upper()
        if not path.startswith("/api/") or SKIP.match(path):
            return await call_next(request)
        if method not in ("POST", "PUT", "DELETE", "PATCH") and not (method == "GET" and SENSITIVE_GET.match(path)):
            return await call_next(request)
        box = {}
        tok = _cv.set(box)
        try:
            resp = await call_next(request)
        finally:
            _cv.reset(tok)
        st = resp.status_code
        if box.get("skip") or not (st < 400 or box.get("force")):
            return resp
        username = box.get("username")
        if not username:
            h = request.headers.get("authorization") or ""
            if h.lower().startswith("bearer "):
                try:
                    from .auth import decode_access_token
                    username = decode_access_token(h[7:].strip()).get("sub")
                except Exception:  # noqa: BLE001
                    username = None
        cat, title = _route(method, path)
        if not box.get("items"):
            box["items"] = [{"title": title or f"{method} {path}", "cat": cat or "other"}]
        ip = request.headers.get("x-real-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() \
            or (request.client.host if request.client else "")
        rec = {"at": int(time.time() * 1000), "username": username, "action": f"{method} {re.sub(r'/[0-9]+', '/#', path)}",
               "cat": cat, "title": title, "items": box["items"], "ip": ip[:64], "ua": _ua(request.headers.get("user-agent")), "status": st}
        await run_in_threadpool(_write, rec)
        return resp
