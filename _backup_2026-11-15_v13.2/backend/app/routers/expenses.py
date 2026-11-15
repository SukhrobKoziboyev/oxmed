"""v9.8: MARKAZ XARAJATLARI.

Admin (va rahbar) markaz uchun qilingan har bir xarajatni kiritadi: "Non — 2 ta — 10 000",
"Kartrijga rang — 50 000"... Xarajatlar kassadagi sof summadan ayiriladi va rahbar
hammasini (kim kiritgani bilan) ko'rib turadi.

Qoidalar:
  * ko'rish va qo'shish — rahbar + admin;
  * tahrirlash/o'chirish — rahbar hammasini, admin faqat o'zi kiritganini;
  * o'chirilgan yozuv bazadan o'chmaydi (deleted_at) — hisobga kirmaydi, rahbar ko'ra oladi;
  * admin kelajak sanani va 62 kundan eski sanani kirita olmaydi.
"""
import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, auth
from ..database import get_db
from ..utils import UZ_MONTHS, UZ_TZ, now_timestamp_ms, ts_to_uz_datestring

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

CATEGORIES = ["Oziq-ovqat", "Kantselyariya", "Texnika", "Ta'mirlash", "Kommunal", "Tozalik", "Transport", "Boshqa"]
MAX_AMOUNT = 1_000_000_000
ADMIN_BACK_DAYS = 62


class ExpenseIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    quantity: Optional[str] = Field(None, max_length=40)
    amount: int
    category: str = "Boshqa"
    note: Optional[str] = Field(None, max_length=255)
    date: Optional[str] = None  # "YYYY-MM-DD" (bo'sh — bugun)


class ExpenseOut(BaseModel):
    id: int
    title: str
    quantity: Optional[str] = None
    amount: int
    category: str
    note: Optional[str] = None
    month: str
    timestamp: int
    date_str: str
    added_by: str
    updated_by: Optional[str] = None
    deleted: bool = False
    deleted_by: Optional[str] = None


def _out(e: models.Expense) -> ExpenseOut:
    return ExpenseOut(
        id=e.id, title=e.title, quantity=e.quantity, amount=int(e.amount), category=e.category,
        note=e.note, month=e.month, timestamp=int(e.timestamp), date_str=ts_to_uz_datestring(e.timestamp),
        added_by=e.added_by, updated_by=e.updated_by, deleted=e.deleted_at is not None, deleted_by=e.deleted_by,
    )


def _clean(data: ExpenseIn, user: models.User, keep_ts: Optional[int] = None):
    title = " ".join((data.title or "").split())
    if not title:
        raise HTTPException(status_code=400, detail="Nima uchun xarajat qilinganini yozing!")
    if not isinstance(data.amount, int) or data.amount <= 0:
        raise HTTPException(status_code=400, detail="Summa 0 dan katta bo'lishi kerak!")
    if data.amount > MAX_AMOUNT:
        raise HTTPException(status_code=400, detail="Summa juda katta!")
    category = data.category if data.category in CATEGORIES else "Boshqa"
    now = datetime.datetime.now(UZ_TZ)
    if data.date:
        try:
            d = datetime.datetime.strptime(data.date.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Sana noto'g'ri!")
        if d > now.date():
            raise HTTPException(status_code=400, detail="Kelajakdagi sanani kiritib bo'lmaydi!")
        if user.role != "Markaz rahbari" and (now.date() - d).days > ADMIN_BACK_DAYS:
            raise HTTPException(status_code=400, detail=f"{ADMIN_BACK_DAYS} kundan eski xarajatni faqat rahbar kirita oladi!")
        if d == now.date():
            dt = now
        else:
            dt = datetime.datetime(d.year, d.month, d.day, 12, 0, tzinfo=UZ_TZ)
        ts = int(dt.timestamp() * 1000)
    else:
        ts = keep_ts or now_timestamp_ms()
    month = UZ_MONTHS[datetime.datetime.fromtimestamp(ts / 1000, UZ_TZ).month - 1]
    qty = " ".join((data.quantity or "").split()) or None
    note = " ".join((data.note or "").split()) or None
    return dict(title=title, quantity=qty, amount=int(data.amount), category=category, note=note, month=month, timestamp=ts)


def total_expenses(db: Session) -> int:
    return int(db.query(func.coalesce(func.sum(models.Expense.amount), 0))
               .filter(models.Expense.deleted_at.is_(None)).scalar() or 0)


@router.get("/categories")
def categories(current_user: models.User = Depends(auth.require_staff)):
    return CATEGORIES


@router.get("", response_model=List[ExpenseOut])
def list_expenses(include_deleted: bool = False, current_user: models.User = Depends(auth.require_staff),
                  db: Session = Depends(get_db)):
    q = db.query(models.Expense)
    if not (include_deleted and current_user.role == "Markaz rahbari"):
        q = q.filter(models.Expense.deleted_at.is_(None))
    return [_out(e) for e in q.order_by(models.Expense.timestamp.desc(), models.Expense.id.desc()).all()]


@router.post("", response_model=ExpenseOut)
def create_expense(data: ExpenseIn, current_user: models.User = Depends(auth.require_staff),
                   db: Session = Depends(get_db)):
    vals = _clean(data, current_user)
    e = models.Expense(**vals, created_at=now_timestamp_ms(), added_by=current_user.username)
    db.add(e)
    db.commit()
    db.refresh(e)
    return _out(e)


def _get_editable(db: Session, eid: int, user: models.User) -> models.Expense:
    e = db.query(models.Expense).filter(models.Expense.id == eid).with_for_update().first()
    if not e or e.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Xarajat topilmadi!")
    if user.role != "Markaz rahbari" and e.added_by != user.username:
        raise HTTPException(status_code=403, detail="Faqat o'zingiz kiritgan xarajatni o'zgartira olasiz!")
    return e


@router.put("/{eid}", response_model=ExpenseOut)
def update_expense(eid: int, data: ExpenseIn, current_user: models.User = Depends(auth.require_staff),
                   db: Session = Depends(get_db)):
    e = _get_editable(db, eid, current_user)
    for k, v in _clean(data, current_user, keep_ts=e.timestamp).items():
        setattr(e, k, v)
    e.updated_by = current_user.username
    e.updated_at = now_timestamp_ms()
    db.commit()
    db.refresh(e)
    return _out(e)


@router.delete("/{eid}")
def delete_expense(eid: int, current_user: models.User = Depends(auth.require_staff),
                   db: Session = Depends(get_db)):
    e = _get_editable(db, eid, current_user)
    e.deleted_at = now_timestamp_ms()
    e.deleted_by = current_user.username
    db.commit()
    return {"ok": True}


@router.post("/{eid}/restore", response_model=ExpenseOut)
def restore_expense(eid: int, current_user: models.User = Depends(auth.require_rahbar),
                    db: Session = Depends(get_db)):
    e = db.query(models.Expense).filter(models.Expense.id == eid).first()
    if not e or e.deleted_at is None:
        raise HTTPException(status_code=404, detail="O'chirilgan xarajat topilmadi!")
    e.deleted_at = None
    e.deleted_by = None
    db.commit()
    db.refresh(e)
    return _out(e)
