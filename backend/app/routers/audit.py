"""v13.15: OXIRGI AMALLAR — faqat rahbar uchun: ro'yxat, yangilar soni (qizil belgi), ko'rildi, o'chirish."""
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models, auth
from ..audit import KEEP_DAYS, skip
from ..database import get_db
from ..utils import ts_to_uz_datestring

router = APIRouter(prefix="/api/audit", tags=["audit"])
CATS = {"pay", "stu", "exp", "sal", "staff", "login", "set", "sms", "att", "other"}


def _out(r: models.ActivityLog) -> dict:
    return {"id": r.id, "at": int(r.at), "date": ts_to_uz_datestring(r.at), "username": r.username, "who": r.who, "role": r.role,
            "cat": r.cat, "title": r.title, "details": r.details, "entity": r.entity, "entity_id": r.entity_id,
            "ip": r.ip, "ua": r.ua, "status": r.status}


def _base(db: Session):
    cut = int((time.time() - KEEP_DAYS * 86400) * 1000)
    return db.query(models.ActivityLog).filter(models.ActivityLog.at >= cut)


@router.get("")
def list_audit(cat: Optional[str] = None, who: Optional[str] = None, q: Optional[str] = None, before_id: Optional[int] = None,
               limit: int = 100, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    qr = _base(db)
    if cat and cat in CATS:
        qr = qr.filter(models.ActivityLog.cat == cat)
    if who:
        qr = qr.filter(models.ActivityLog.username == who)
    if q:
        like = f"%{q.strip()[:80]}%"
        qr = qr.filter(or_(models.ActivityLog.title.ilike(like), models.ActivityLog.who.ilike(like)))
    if before_id:
        qr = qr.filter(models.ActivityLog.id < before_id)
    limit = max(10, min(int(limit or 100), 300))
    rows = qr.order_by(models.ActivityLog.id.desc()).limit(limit + 1).all()
    return {"items": [_out(r) for r in rows[:limit]], "has_more": len(rows) > limit,
            "seen_id": int(current_user.audit_seen_id or 0), "keep_days": KEEP_DAYS}


@router.get("/who")
def list_who(current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    rows = (_base(db).with_entities(models.ActivityLog.username, func.max(models.ActivityLog.who), func.count(models.ActivityLog.id))
            .filter(models.ActivityLog.username.isnot(None), models.ActivityLog.username != "")
            .group_by(models.ActivityLog.username).all())
    return [{"username": u, "who": w or u, "count": int(c)} for u, w, c in sorted(rows, key=lambda x: -x[2])]


@router.get("/unread")
def unread(current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    """Yangi amallar soni (rahbarning o'z amallari hisobga olinmaydi)."""
    n = (_base(db).filter(models.ActivityLog.id > int(current_user.audit_seen_id or 0),
                          or_(models.ActivityLog.username.is_(None), models.ActivityLog.username != current_user.username)).count())
    return {"count": int(n)}


class SeenIn(BaseModel):
    last_id: int


@router.post("/seen")
def mark_seen(data: SeenIn, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    mx = db.query(func.max(models.ActivityLog.id)).scalar() or 0
    v = max(int(current_user.audit_seen_id or 0), min(int(data.last_id), int(mx)))
    current_user.audit_seen_id = v
    db.commit()
    return {"ok": True, "seen_id": v}


class DelIn(BaseModel):
    ids: List[int]


@router.delete("")
def delete_items(data: DelIn, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    ids = list({int(i) for i in data.ids})[:500]
    if not ids:
        raise HTTPException(status_code=400, detail="Hech narsa tanlanmagan")
    n = db.query(models.ActivityLog).filter(models.ActivityLog.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    skip()   # v13.16: o'chirish jurnalga yozilmaydi — o'chirilgan narsa butunlay yo'qoladi
    return {"ok": True, "deleted": int(n)}
