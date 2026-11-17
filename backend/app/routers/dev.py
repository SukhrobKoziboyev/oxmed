"""v13.26: DASTURCHI (yashirin) — SMS hisobini to'ldirish.

Rahbar dasturchining kartasiga to'laydi (eng kam {min} = 182 000). Shundan
{fee} (82 000) — dasturchining xizmat haqi, qolgani ({to_eskiz} = 100 000) —
Eskiz SMS hisobiga tushadigan pul. Dasturchi sahifasida "kutilmoqda" bo'lib
turadi; dasturchi pulni olib, Eskiz'ni to'ldiradi va "bajarildi" qiladi.

MUHIM: bu OXMED kassasi/hisob-kitobiga MUTLAQO ta'sir qilmaydi — butunlay alohida.
Barcha /api/dev/* so'rovlari audit (Oxirgi amallar)'ga YOZILMAYDI (audit.SKIP).
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, auth
from ..database import get_db
from ..utils import now_timestamp_ms
from ..auth import require_dev, require_perm

router = APIRouter(prefix="/api/dev", tags=["dev"])

DEF_MIN = 182000
DEF_FEE = 82000
DEF_TELEGRAM = os.getenv("DEV_TELEGRAM") or "Sukhrob_Koziboyev"
DEF_CARD = os.getenv("DEV_CARD") or ""
DEF_CARD_NAME = os.getenv("DEV_CARD_NAME") or "Sukhrob Koziboyev"


def _settings(db: Session) -> models.Settings:
    s = db.query(models.Settings).first()
    if not s:
        raise HTTPException(status_code=500, detail="Sozlamalar topilmadi")
    return s


def _cfg(db: Session) -> dict:
    s = _settings(db)
    return {
        "min": int(s.topup_min or DEF_MIN),
        "fee": int(s.topup_fee or DEF_FEE),
        "card": (s.topup_card or DEF_CARD or ""),
        "card_name": (s.topup_card_name or DEF_CARD_NAME or ""),
        "telegram": (s.topup_telegram or DEF_TELEGRAM or "").lstrip("@"),
    }


def _row(t: models.SmsTopup) -> dict:
    from ..utils import ts_to_uz_datestring
    import datetime
    from ..utils import UZ_TZ
    tm = datetime.datetime.fromtimestamp(t.at / 1000, UZ_TZ).strftime("%H:%M")
    return {
        "id": t.id, "at": int(t.at), "date_str": ts_to_uz_datestring(t.at), "time": tm,
        "amount": int(t.amount), "to_eskiz": int(t.to_eskiz), "fee": int(t.fee),
        "status": t.status, "by_user": t.by_user, "by_who": t.by_who, "note": t.note,
        "done_at": int(t.done_at) if t.done_at else None, "done_by": t.done_by,
    }


# ---------------- RAHBAR/SMS tomoni: to'ldirish ----------------
@router.get("/topup/info")
def topup_info(current_user: models.User = Depends(require_perm("sms")), db: Session = Depends(get_db)):
    """Rahbar uchun: karta, telegram, eng kam summa, xizmat haqi + shu oyda kutilayotganlar."""
    c = _cfg(db)
    mine = (db.query(models.SmsTopup).order_by(models.SmsTopup.id.desc()).limit(20).all())
    pending = db.query(models.SmsTopup).filter(models.SmsTopup.status == "pending").count()
    return {**c, "pending": pending, "items": [_row(t) for t in mine]}


class PayIn(BaseModel):
    amount: int
    note: Optional[str] = None


@router.post("/topup/pay")
def topup_pay(data: PayIn, current_user: models.User = Depends(require_perm("sms")), db: Session = Depends(get_db)):
    """Rahbar "To'ladim" bosganda — kutilayotgan yozuv yaratiladi."""
    c = _cfg(db)
    amount = int(data.amount or 0)
    if amount < c["min"]:
        raise HTTPException(status_code=400, detail=f"Yetarli emas. Eng kam summa {c['min']:,} so'm".replace(",", " "))
    fee = c["fee"]
    to_eskiz = amount - fee
    if to_eskiz <= 0:
        raise HTTPException(status_code=400, detail="Summa xizmat haqidan ko'p bo'lishi kerak")
    who = "Rahbar" if current_user.role == "Markaz rahbari" else (
        "Administrator" if current_user.role == "Administrator" else current_user.username)
    t = models.SmsTopup(at=now_timestamp_ms(), amount=amount, to_eskiz=to_eskiz, fee=fee,
                        status="pending", by_user=current_user.username, by_who=who,
                        note=(data.note or None))
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"ok": True, "topup": _row(t), **c}


# ---------------- DASTURCHI tomoni ----------------
@router.get("/topups")
def dev_topups(current_user: models.User = Depends(require_dev), db: Session = Depends(get_db)):
    # kutilayotganlar birinchi, keyin yangi -> eski
    rows = db.query(models.SmsTopup).order_by(models.SmsTopup.id.desc()).limit(200).all()
    rows.sort(key=lambda t: (t.status != "pending", -t.id))
    tot_pending = sum(int(t.to_eskiz) for t in rows if t.status == "pending")
    tot_fee = sum(int(t.fee) for t in rows if t.status != "canceled")
    return {"items": [_row(t) for t in rows], "pending_eskiz": tot_pending, "fee_total": tot_fee}


@router.post("/topup/{tid}/done")
def dev_done(tid: int, current_user: models.User = Depends(require_dev), db: Session = Depends(get_db)):
    t = db.query(models.SmsTopup).filter(models.SmsTopup.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Topilmadi")
    t.status = "done"
    t.done_at = now_timestamp_ms()
    t.done_by = current_user.username
    db.commit()
    return {"ok": True, "topup": _row(t)}


@router.post("/topup/{tid}/cancel")
def dev_cancel(tid: int, current_user: models.User = Depends(require_dev), db: Session = Depends(get_db)):
    t = db.query(models.SmsTopup).filter(models.SmsTopup.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Topilmadi")
    t.status = "canceled"
    t.done_at = now_timestamp_ms()
    t.done_by = current_user.username
    db.commit()
    return {"ok": True, "topup": _row(t)}


@router.get("/eskiz-balance")
def dev_balance(current_user: models.User = Depends(require_dev)):
    try:
        from .sms import eskiz, configured
        if not configured():
            return {"ok": False, "balance": None, "error": "Eskiz sozlanmagan"}
        return {"ok": True, "balance": eskiz.balance()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "balance": None, "error": str(e)[:120]}


class DevSettingsIn(BaseModel):
    min: Optional[int] = None
    fee: Optional[int] = None
    card: Optional[str] = None
    card_name: Optional[str] = None
    telegram: Optional[str] = None


@router.get("/settings")
def dev_get_settings(current_user: models.User = Depends(require_dev), db: Session = Depends(get_db)):
    return _cfg(db)


@router.put("/settings")
def dev_put_settings(data: DevSettingsIn, current_user: models.User = Depends(require_dev), db: Session = Depends(get_db)):
    s = _settings(db)
    if data.min is not None:
        s.topup_min = max(1000, int(data.min))
    if data.fee is not None:
        s.topup_fee = max(0, int(data.fee))
    if data.card is not None:
        s.topup_card = (data.card or "").strip()[:40] or None
    if data.card_name is not None:
        s.topup_card_name = (data.card_name or "").strip()[:80] or None
    if data.telegram is not None:
        s.topup_telegram = (data.telegram or "").strip().lstrip("@")[:64] or None
    db.commit()
    return _cfg(db)


class DevCredIn(BaseModel):
    new_login: Optional[str] = None
    new_password: Optional[str] = None


@router.get("/whoami")
def dev_whoami(current_user: models.User = Depends(require_dev)):
    return {"login": auth.DEV_LOGIN, "role": auth.ROLE_DEV}
