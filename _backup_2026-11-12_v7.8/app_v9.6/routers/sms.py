"""v8.9: SMS — Eskiz.uz orqali.

Login ma'lumotlari FAQAT serverdagi backend/.env faylida turadi (kodda ham, bazada ham yo'q):
    ESKIZ_EMAIL=...        Eskiz kabinetiga kiradigan email
    ESKIZ_PASSWORD=...     Eskiz API paroli (kabinet → API sozlamalari → "Ключ"/parol)
    ESKIZ_FROM=4546        Jo'natuvchi nomi (nik tasdiqlanguncha 4546)

To'lov saqlangach SMS orqada (BackgroundTasks) yuboriladi — to'lov hech qachon SMS
sababli sekinlashmaydi yoki buzilmaydi. Har bir SMS sms_logs jadvaliga yoziladi.
"""
import os
import re
import threading
import time
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db, SessionLocal
from ..utils import now_timestamp_ms

router = APIRouter(prefix="/api/sms", tags=["sms"])

ESKIZ_BASE = os.getenv("ESKIZ_BASE", "https://notify.eskiz.uz/api").rstrip("/")


def _cfg():
    return {
        "email": (os.getenv("ESKIZ_EMAIL") or "").strip(),
        "password": (os.getenv("ESKIZ_PASSWORD") or "").strip(),
        "from": (os.getenv("ESKIZ_FROM") or "4546").strip(),
    }


def configured() -> bool:
    c = _cfg()
    return bool(c["email"] and c["password"])


class EskizError(Exception):
    pass


class _Eskiz:
    """Token xotirada saqlanadi; muddati o'tsa (401) avtomatik qayta login qilinadi."""

    def __init__(self):
        self._token: Optional[str] = None
        self._lock = threading.Lock()

    def _login(self) -> str:
        import requests
        c = _cfg()
        if not (c["email"] and c["password"]):
            raise EskizError("Eskiz sozlanmagan (serverdagi .env da ESKIZ_EMAIL / ESKIZ_PASSWORD yo'q)")
        r = requests.post(f"{ESKIZ_BASE}/auth/login", data={"email": c["email"], "password": c["password"]}, timeout=15)
        try:
            j = r.json()
        except ValueError:
            j = {}
        tok = (j.get("data") or {}).get("token")
        if r.status_code != 200 or not tok:
            raise EskizError("Eskiz'ga kirib bo'lmadi: " + str(j.get("message") or r.status_code))
        self._token = tok
        return tok

    def _token_get(self) -> str:
        with self._lock:
            return self._token or self._login()

    def _request(self, method: str, path: str, **kw):
        import requests
        for attempt in (1, 2):
            tok = self._token_get()
            r = requests.request(method, f"{ESKIZ_BASE}{path}", headers={"Authorization": f"Bearer {tok}"}, timeout=20, **kw)
            if r.status_code == 401 and attempt == 1:
                with self._lock:
                    self._token = None
                continue
            return r
        return r

    def send(self, phone: str, text: str) -> str:
        r = self._request("POST", "/message/sms/send", data={"mobile_phone": phone, "message": text, "from": _cfg()["from"]})
        try:
            j = r.json()
        except ValueError:
            j = {}
        if r.status_code >= 300 or (isinstance(j, dict) and j.get("status") == "error"):
            msg = j.get("message") if isinstance(j, dict) else None
            if isinstance(msg, dict):
                msg = "; ".join(f"{k}: {v}" for k, v in msg.items())
            raise EskizError(str(msg or f"HTTP {r.status_code}")[:450])
        return str(j.get("id") or "")

    def balance(self):
        r = self._request("GET", "/user/get-limit")
        try:
            j = r.json()
        except ValueError:
            return None
        d = j.get("data") if isinstance(j, dict) else None
        if isinstance(d, dict):
            return d.get("balance")
        return None


eskiz = _Eskiz()


# ------------------------------------------------------------------ yordamchilar
def normalize_phone(raw: str) -> Optional[str]:
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 9:
        d = "998" + d
    if len(d) == 12 and d.startswith("998"):
        return d
    return None


_APOS = str.maketrans({"ʻ": "'", "ʼ": "'", "‘": "'", "’": "'", "`": "'", "´": "'"})


def render(template: str, data: dict) -> str:
    text = template or ""
    for k, v in data.items():
        text = text.replace("{" + k + "}", str(v if v is not None else ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text.translate(_APOS)[:600]


def fmt_money(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def payment_data(p: models.Payment) -> dict:
    first, _, last = (p.student_name or "").partition(" ")
    date_str = schemas.PaymentOut.from_orm(p).date_str or ""
    sana, _, vaqt = date_str.partition(" ")
    return {
        "ism": first, "familiya": last, "fan": p.subject_name or "", "sinf": p.class_name or "",
        "oy": p.month, "summa": fmt_money(p.amount), "sana": sana, "vaqt": vaqt[:5],
    }


def _log(db: Session, **kw) -> models.SmsLog:
    row = models.SmsLog(created_at=now_timestamp_ms(), **kw)
    db.add(row)
    db.commit()
    return row


def send_one(db: Session, phone_raw: str, text: str, kind: str, payment_id=None, by=None,
             batch_id=None, student_id=None) -> models.SmsLog:
    extra = {"batch_id": batch_id, "student_id": student_id}
    phone = normalize_phone(phone_raw)
    if not phone:
        return _log(db, payment_id=payment_id, kind=kind, phone=(phone_raw or "-")[:32], text=text,
                    status="skipped", error="Telefon raqami noto'g'ri yoki yo'q", created_by=by, **extra)
    try:
        pid = eskiz.send(phone, text)
        return _log(db, payment_id=payment_id, kind=kind, phone=phone, text=text, status="sent",
                    provider_id=pid[:64] or None, created_by=by, **extra)
    except Exception as e:  # noqa: BLE001 — SMS xatosi hech narsani buzmasin
        return _log(db, payment_id=payment_id, kind=kind, phone=phone, text=text, status="failed",
                    error=str(e)[:450], created_by=by, **extra)


def send_payment_sms(payment_id: int):
    """To'lovdan keyin orqada ishlaydi (o'z DB sessiyasi bilan)."""
    db = SessionLocal()
    try:
        st = db.query(models.Settings).first()
        if not st or not st.sms_enabled or not configured():
            return
        p = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
        if not p:
            return
        data = payment_data(p)
        if st.sms_to_parent and p.student_phone:
            send_one(db, p.student_phone, render(st.sms_template_parent, data), "parent", p.id, p.added_by)
        if st.sms_to_rahbar:
            text = render(st.sms_template_rahbar, data)
            seen = set()
            for rp in db.query(models.RahbarPhone).all():
                n = normalize_phone(rp.phone)
                if n in seen:
                    continue
                seen.add(n)
                send_one(db, rp.phone, text, "rahbar", p.id, p.added_by)
    except Exception:  # noqa: BLE001
        pass
    finally:
        db.close()


# ------------------------------------------------------------------ API
class SmsSettingsIn(BaseModel):
    enabled: bool
    to_parent: bool = True
    to_rahbar: bool = True


class SmsTestIn(BaseModel):
    phone: str
    text: Optional[str] = None


def _log_out(r: models.SmsLog) -> dict:
    return {"id": r.id, "payment_id": r.payment_id, "kind": r.kind, "phone": r.phone, "text": r.text,
            "status": r.status, "error": r.error, "created_at": r.created_at, "created_by": r.created_by}


_bal_cache = {"t": 0, "v": None}


@router.get("/status")
def sms_status(current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    st = db.query(models.Settings).first()
    bal, err = None, None
    if configured():
        if time.time() - _bal_cache["t"] < 60:
            bal = _bal_cache["v"]
        else:
            try:
                bal = eskiz.balance()
                _bal_cache.update(t=time.time(), v=bal)
            except Exception as e:  # noqa: BLE001
                err = str(e)[:200]
    logs = db.query(models.SmsLog).order_by(models.SmsLog.id.desc()).limit(30).all()
    from sqlalchemy import func
    counts = dict(db.query(models.SmsLog.status, func.count(models.SmsLog.id)).group_by(models.SmsLog.status).all())
    H5, DAY = 5 * 3600 * 1000, 86400 * 1000
    day0 = (now_timestamp_ms() + H5) // DAY * DAY - H5  # Toshkent vaqti bilan bugun 00:00
    today = dict(db.query(models.SmsLog.status, func.count(models.SmsLog.id))
                 .filter(models.SmsLog.created_at >= day0).group_by(models.SmsLog.status).all())
    return {
        "counts": {k: counts.get(k, 0) for k in ("sent", "failed", "skipped")},
        "today": {k: today.get(k, 0) for k in ("sent", "failed", "skipped")},
        "can_manage": current_user.role == "Markaz rahbari",
        "configured": configured(), "from": _cfg()["from"], "balance": bal, "error": err,
        "enabled": bool(st and st.sms_enabled), "to_parent": bool(st and st.sms_to_parent),
        "to_rahbar": bool(st and st.sms_to_rahbar), "logs": [_log_out(r) for r in logs],
    }


@router.put("/settings")
def sms_settings(data: SmsSettingsIn, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    st = db.query(models.Settings).first()
    if data.enabled and not configured():
        raise HTTPException(status_code=400, detail="Avval serverda Eskiz login ma'lumotlarini kiriting (.env)")
    st.sms_enabled, st.sms_to_parent, st.sms_to_rahbar = data.enabled, data.to_parent, data.to_rahbar
    db.commit()
    return {"ok": True}


@router.post("/test")
def sms_test(data: SmsTestIn, current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    if not configured():
        raise HTTPException(status_code=400, detail="Eskiz sozlanmagan (serverdagi .env da ESKIZ_EMAIL / ESKIZ_PASSWORD yo'q)")
    text = (data.text or "").strip() or "Bu Eskiz dan test"
    row = send_one(db, data.phone, text[:600], "test", None, current_user.username)
    return _log_out(row)



# ====================================================================== v9.0: OMMAVIY SMS
DEFAULT_TEMPLATES = {
    "reminder": "Hurmatli ota-ona! {ism} {familiya}ning {oy} oyi uchun to'lovi hali qilinmagan. "
                "Iltimos, to'lovni o'z vaqtida amalga oshiring. OLMOS XATAMOV maktabi",
    "overdue": "Hurmatli ota-ona! {ism} {familiya}ning {oy} oyi uchun to'lov muddati o'tib ketdi. "
               "Iltimos, to'lovni tezroq amalga oshiring. OLMOS XATAMOV maktabi",
    "announce": "Hurmatli ota-onalar! ... OLMOS XATAMOV maktabi",
}
KINDS = ("reminder", "overdue", "announce")


def _templates(st) -> dict:
    return {
        "reminder": (st.sms_template_reminder if st and st.sms_template_reminder else DEFAULT_TEMPLATES["reminder"]),
        "overdue": (st.sms_template_overdue if st and st.sms_template_overdue else DEFAULT_TEMPLATES["overdue"]),
        "announce": (st.sms_template_announce if st and st.sms_template_announce else DEFAULT_TEMPLATES["announce"]),
    }


class TemplatesIn(BaseModel):
    reminder: Optional[str] = None
    overdue: Optional[str] = None
    announce: Optional[str] = None


@router.get("/templates")
def get_templates(current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    return _templates(db.query(models.Settings).first())


@router.put("/templates")
def put_templates(data: TemplatesIn, current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    st = db.query(models.Settings).first()
    for k in KINDS:
        v = getattr(data, k)
        if v is not None:
            v = v.strip()
            if len(v) > 600:
                raise HTTPException(status_code=400, detail="Shablon juda uzun (600 belgidan oshmasin)")
            setattr(st, f"sms_template_{k}", v or None)
    db.commit()
    return _templates(st)


class BulkIn(BaseModel):
    kind: str
    month: Optional[str] = None
    text: str
    student_ids: List[int]


def _batch_out(b: models.SmsBatch) -> dict:
    return {"id": b.id, "kind": b.kind, "month": b.month, "template": b.template, "total": b.total,
            "sent": b.sent, "failed": b.failed, "skipped": b.skipped, "status": b.status,
            "created_by": b.created_by, "created_at": b.created_at, "finished_at": b.finished_at}


def student_vars(db: Session, stu: models.Student, month: Optional[str]) -> dict:
    qarz = ""
    if month:
        due = db.query(models.StudentDue).filter(models.StudentDue.student_id == stu.id,
                                                  models.StudentDue.month == month).first()
        if due:
            from .dues import paid_for_month
            d = max(0, int(due.due_amount) - paid_for_month(db, stu.id, month))
            qarz = fmt_money(d) if d else ""
    return {"ism": stu.first_name, "familiya": stu.last_name, "oy": month or "", "qarz": qarz,
            "sinf": stu.class_name or "", "fan": stu.subject_name or ""}


def run_batch(batch_id: int, student_ids: List[int]):
    db = SessionLocal()
    try:
        b = db.query(models.SmsBatch).filter(models.SmsBatch.id == batch_id).first()
        if not b:
            return
        for sid in student_ids:
            stu = db.query(models.Student).filter(models.Student.id == sid).first()
            if not stu:
                _log(db, kind=b.kind, phone="-", text="", status="skipped", error="O'quvchi topilmadi (o'chirilgan)",
                     created_by=b.created_by, batch_id=b.id, student_id=sid)
                b.skipped += 1
                db.commit()
                continue
            text = render(b.template, student_vars(db, stu, b.month))
            row = send_one(db, stu.phone, text, b.kind, None, b.created_by, batch_id=b.id, student_id=stu.id)
            setattr(b, row.status, getattr(b, row.status) + 1)
            db.commit()
            time.sleep(0.05)
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            b = db.query(models.SmsBatch).filter(models.SmsBatch.id == batch_id).first()
            if b:
                b.status, b.finished_at = "done", now_timestamp_ms()
                db.commit()
        finally:
            db.close()


@router.post("/bulk")
def bulk_send(data: BulkIn, background: BackgroundTasks,
              current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    from ..utils import UZ_MONTHS
    if data.kind not in KINDS:
        raise HTTPException(status_code=400, detail="Noto'g'ri tur")
    if not configured():
        raise HTTPException(status_code=400, detail="Eskiz hali ulanmagan — SMS yuborib bo'lmaydi (serverga Eskiz login/paroli kiritilishi kerak)")
    text = (data.text or "").strip()
    if len(text) < 5:
        raise HTTPException(status_code=400, detail="SMS matnini yozing")
    if len(text) > 600:
        raise HTTPException(status_code=400, detail="SMS matni juda uzun (600 belgidan oshmasin)")
    if data.kind != "announce" and data.month not in UZ_MONTHS:
        raise HTTPException(status_code=400, detail="Oyni tanlang")
    ids = list(dict.fromkeys(int(i) for i in data.student_ids))
    if not ids:
        raise HTTPException(status_code=400, detail="Hech qaysi o'quvchi tanlanmagan")
    if len(ids) > 3000:
        raise HTTPException(status_code=400, detail="Bir martada 3000 tadan ko'p bo'lmasin")
    recent = (db.query(models.SmsBatch)
              .filter(models.SmsBatch.status == "running", models.SmsBatch.created_at > now_timestamp_ms() - 30 * 60 * 1000)
              .first())
    if recent:
        raise HTTPException(status_code=409, detail="Oldingi SMS yuborish hali tugamadi — biroz kuting")
    b = models.SmsBatch(kind=data.kind, month=(data.month if data.kind != "announce" else None), template=text,
                        total=len(ids), status="running", created_by=current_user.username, created_at=now_timestamp_ms())
    db.add(b)
    db.commit()
    db.refresh(b)
    background.add_task(run_batch, b.id, ids)
    return _batch_out(b)


@router.get("/batches")
def list_batches(current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    rows = db.query(models.SmsBatch).order_by(models.SmsBatch.id.desc()).limit(30).all()
    return [_batch_out(b) for b in rows]


@router.get("/logs")
def list_logs(batch_id: Optional[int] = None, status: Optional[str] = None, limit: int = 300,
              current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    q = db.query(models.SmsLog)
    if batch_id:
        q = q.filter(models.SmsLog.batch_id == batch_id)
    if status in ("sent", "failed", "skipped"):
        q = q.filter(models.SmsLog.status == status)
    rows = q.order_by(models.SmsLog.id.desc()).limit(max(1, min(limit, 1000))).all()
    out = []
    for r in rows:
        d = _log_out(r)
        d["batch_id"], d["student_id"] = r.batch_id, r.student_id
        out.append(d)
    return out
