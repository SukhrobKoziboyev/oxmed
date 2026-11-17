"""v13.25: BUGUNGI TUSHUM va "BUGUNGI TO'LOVNI OLDIM" (rahbar).

Bugungi tushum = bugun (Toshkent) sanasidagi to'lovlar, oxirgi "oldim" tasdig'idan keyin kiritilganlari
(id bo'yicha). Rahbar "Bugungi to'lovni oldim" ni tasdiqlasa — shu paytgacha bo'lgan to'lovlar "topshirilgan"
deb belgilanadi va rahbarda ham, adminda ham bugungi tushum 0 dan boshlanadi.

MUHIM: bu faqat belgi. To'lovlar, ulushlar, kassa, o'qituvchi balansi — HECH NARSA o'zgarmaydi.
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, auth
from ..database import get_db
from ..student_links import who_label
from ..utils import now_uz, now_timestamp_ms, UZ_TZ

router = APIRouter(prefix="/api/cash", tags=["cash"])
METHODS = ("naxt", "click", "terminal")


def _day_range(now: Optional[datetime.datetime] = None):
    now = now or now_uz()
    start = datetime.datetime(now.year, now.month, now.day, tzinfo=UZ_TZ)
    return int(start.timestamp() * 1000), int((start + datetime.timedelta(days=1)).timestamp() * 1000)


def _last_upto(db: Session) -> int:
    return int(db.query(func.max(models.CashHandover.upto_id)).scalar() or 0)


def _today_payments(db: Session, upto: Optional[int] = None):
    a, b = _day_range()
    q = (db.query(models.Payment).filter(models.Payment.timestamp >= a, models.Payment.timestamp < b,
                                         models.Payment.id > _last_upto(db)))
    if upto is not None:
        q = q.filter(models.Payment.id <= upto)
    return q.order_by(models.Payment.id.desc()).all()


def _totals(rows) -> dict:
    t = {"all": 0, "count": len(rows)}
    for m in METHODS:
        t[m] = 0
        t[m + "_count"] = 0
    for p in rows:
        m = p.method if p.method in METHODS else "naxt"
        t[m] += int(p.amount)
        t[m + "_count"] += 1
        t["all"] += int(p.amount)
    return t


@router.get("/today")
def today(current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    rows = _today_payments(db)
    who = {}

    def wl(u):
        if u not in who:
            who[u] = who_label(db, u) if u else ""
        return who[u]

    a, b = _day_range()
    hand = (db.query(models.CashHandover).filter(models.CashHandover.at >= a, models.CashHandover.at < b)
            .order_by(models.CashHandover.id.desc()).all())
    return {
        "date": now_uz().strftime("%Y-%m-%d"),
        "items": [{"id": p.id, "student": p.student_name, "type": p.student_type, "class_name": p.class_name or "",
                   "subject": p.subject_name or "", "teacher": p.teacher_name or "", "month": p.month, "year": p.year,
                   "amount": int(p.amount), "method": p.method if p.method in METHODS else "naxt",
                   "time": datetime.datetime.fromtimestamp(p.timestamp / 1000, UZ_TZ).strftime("%H:%M"),
                   "by": wl(p.added_by)} for p in rows],
        "totals": _totals(rows),
        "upto_id": max([p.id for p in rows] or [0]),
        "handovers": [{"at": int(h.at), "time": datetime.datetime.fromtimestamp(h.at / 1000, UZ_TZ).strftime("%H:%M"),
                       "by": wl(h.by_user), "total": int(h.total), "naxt": int(h.naxt), "click": int(h.click),
                       "terminal": int(h.terminal), "count": int(h.count)} for h in hand],
        "can_confirm": current_user.role == "Markaz rahbari",
    }


class HandoverIn(BaseModel):
    upto_id: int


@router.post("/handover")
def handover(data: HandoverIn, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    """Rahbar: "Bugungi to'lovni oldim" — ekranda ko'rgan to'lovlarigacha (upto_id) topshirilgan deb belgilanadi."""
    rows = _today_payments(db, upto=int(data.upto_id))
    if not rows:
        raise HTTPException(status_code=400, detail="Bugun hali olinmagan to'lov yo'q")
    t = _totals(rows)
    h = models.CashHandover(at=now_timestamp_ms(), by_user=current_user.username, upto_id=max(p.id for p in rows),
                            total=t["all"], naxt=t["naxt"], click=t["click"], terminal=t["terminal"], count=t["count"])
    db.add(h)
    from ..audit import note as _an

    def fm(v):
        return f"{v:,}".replace(",", " ")
    _an(f"Bugungi to'lovni oldi: {fm(t['all'])} so'm ({t['count']} ta) — naqd {fm(t['naxt'])}, click {fm(t['click'])}, terminal {fm(t['terminal'])}",
        cat="pay")
    db.commit()
    return {"ok": True, "totals": t}
