"""v8.4: XODIMLAR - o'quvchisi bo'lmagan hodimlar (farrosh, oshpaz, direktor
o'rinbosari, qorovul, ...).

Xodim `teachers` jadvalida is_staff=True va subject_id=NULL bilan saqlanadi.
Shuning uchun login berish, parol tiklash kodi, barmoq izi, oylik/avans berish
(/api/salary/payout), pul qaytarish va hisob varag'i o'qituvchilarniki bilan
AYNAN bir xil mexanizmda ishlaydi.

Farqi: ulush o'rniga har oy belgilangan oylik avtomatik hisoblanadi
(SalaryAccrual, ledger.ensure_staff_accruals). Balans (ledger.py):
    hisoblangan oylik - berilgan + qaytarilgan
"""
import re
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth, ledger
from ..database import get_db
from ..utils import now_uz, now_uz_datestring, now_timestamp_ms, clean_staff_phone

router = APIRouter(prefix="/api/staff", tags=["staff"])

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _current_period() -> str:
    n = now_uz()
    return f"{n.year:04d}-{n.month:02d}"


def _get_staff(db: Session, staff_id: int) -> models.Teacher:
    t = db.query(models.Teacher).filter(models.Teacher.id == staff_id, models.Teacher.is_staff.is_(True)).first()
    if not t:
        raise HTTPException(status_code=404, detail="Xodim topilmadi!")
    return t


def _to_out(db: Session, t: models.Teacher) -> schemas.StaffOut:
    login_user = db.query(models.User).filter(models.User.teacher_id == t.id).first()
    allocated, paid_out, returned, owed = ledger.teacher_totals(db, t.id)
    return schemas.StaffOut(
        id=t.id, name=t.name, position=t.position, monthly_salary=int(t.monthly_salary or 0),
        salary_start=t.salary_start, phone=t.phone, can_expenses=bool(t.can_expenses), has_login=login_user is not None,
        login_username=login_user.username if login_user else None,
        total_accrued=allocated, total_paid_out=paid_out, total_returned=returned, owed=owed,
    )


def _validate(payload: schemas.StaffIn):
    name = (payload.name or "").strip()
    position = (payload.position or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Xodim ism-familiyasini kiriting!")
    if not position:
        raise HTTPException(status_code=400, detail="Lavozimni kiriting (masalan: Farrosh)!")
    if payload.monthly_salary is None or payload.monthly_salary < 0:
        raise HTTPException(status_code=400, detail="Oylik summasi noto'g'ri!")
    start = (payload.salary_start or "").strip() or _current_period()
    if not _PERIOD_RE.match(start):
        raise HTTPException(status_code=400, detail="Boshlanish oyi noto'g'ri!")
    return name, position, int(payload.monthly_salary), start


def _phone(payload) -> str:
    try:
        return clean_staff_phone(payload.phone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[schemas.StaffOut])
def list_staff(current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    staff = db.query(models.Teacher).filter(models.Teacher.is_staff.is_(True)).order_by(models.Teacher.id).all()
    for t in staff:
        ledger.ensure_staff_accruals(db, t)
    return [_to_out(db, t) for t in staff]


@router.post("", response_model=schemas.StaffOut)
def create_staff(payload: schemas.StaffIn, current_user: models.User = Depends(auth.require_rahbar),
                 db: Session = Depends(get_db)):
    name, position, salary, start = _validate(payload)
    t = models.Teacher(subject_id=None, name=name, is_staff=True, position=position,
                       monthly_salary=salary, salary_start=start, phone=_phone(payload),
                       can_expenses=bool(payload.can_expenses))
    db.add(t)
    db.commit()
    db.refresh(t)
    ledger.ensure_staff_accruals(db, t)
    return _to_out(db, t)


@router.put("/{staff_id}", response_model=schemas.StaffOut)
def edit_staff(staff_id: int, payload: schemas.StaffIn, current_user: models.User = Depends(auth.require_rahbar),
               db: Session = Depends(get_db)):
    """Ism, lavozim, oylik summasi, boshlanish oyini o'zgartirish.
    Oylik summasi o'zgarsa - KEYINGI hisoblanadigan oylardan amal qiladi;
    allaqachon hisoblangan oylar o'zgarmaydi (kerak bo'lsa ularni alohida tahrirlang)."""
    t = _get_staff(db, staff_id)
    name, position, salary, start = _validate(payload)
    t.name, t.position, t.monthly_salary, t.salary_start = name, position, salary, start
    if payload.phone is not None:
        t.phone = _phone(payload)
    if payload.can_expenses is not None:
        t.can_expenses = bool(payload.can_expenses)
    db.commit()
    ledger.ensure_staff_accruals(db, t)
    return _to_out(db, t)


@router.delete("/{staff_id}")
def delete_staff(staff_id: int, current_user: models.User = Depends(auth.require_rahbar),
                 db: Session = Depends(get_db)):
    """Xodimni o'chirish. Hisob yozuvlari (berilgan oyliklar va hisoblangan oyliklar)
    tarix uchun saqlanadi (teacher_id=NULL), login esa o'chadi."""
    t = _get_staff(db, staff_id)
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.get("/{staff_id}/ledger", response_model=schemas.TeacherLedgerOut)
def staff_ledger(staff_id: int, current_user: models.User = Depends(auth.require_staff),
                 db: Session = Depends(get_db)):
    t = _get_staff(db, staff_id)
    ledger.ensure_staff_accruals(db, t)
    return ledger.teacher_ledger(db, t)


@router.post("/{staff_id}/accrual", response_model=schemas.StaffOut)
def add_accrual(staff_id: int, payload: schemas.AccrualIn, current_user: models.User = Depends(auth.require_rahbar),
                db: Session = Depends(get_db)):
    """Qo'shimcha hisoblash (bonus, qo'shimcha ish) - balansga qo'shiladi."""
    t = _get_staff(db, staff_id)
    if payload.amount is None or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Summa noto'g'ri!")
    db.add(models.SalaryAccrual(
        teacher_id=t.id, teacher_name=t.name, kind="extra", period=None, amount=int(payload.amount),
        note=(payload.note or "").strip() or None, date_str=now_uz_datestring(), timestamp=now_timestamp_ms(),
        created_by=current_user.username,
    ))
    db.commit()
    return _to_out(db, t)


@router.put("/accrual/{accrual_id}", response_model=schemas.StaffOut)
def edit_accrual(accrual_id: int, payload: schemas.AccrualEditIn, current_user: models.User = Depends(auth.require_rahbar),
                 db: Session = Depends(get_db)):
    """Hisoblangan oylik summasini o'zgartirish (masalan, yarim oy ishlagan bo'lsa)."""
    ac = db.query(models.SalaryAccrual).filter(models.SalaryAccrual.id == accrual_id).first()
    if not ac or not ac.teacher_id:
        raise HTTPException(status_code=404, detail="Yozuv topilmadi!")
    if payload.amount is None or payload.amount < 0:
        raise HTTPException(status_code=400, detail="Summa noto'g'ri!")
    ac.amount = int(payload.amount)
    if payload.note is not None:
        ac.note = payload.note.strip() or None
    db.commit()
    return _to_out(db, _get_staff(db, ac.teacher_id))


@router.delete("/accrual/{accrual_id}", response_model=schemas.StaffOut)
def delete_accrual(accrual_id: int, current_user: models.User = Depends(auth.require_rahbar),
                   db: Session = Depends(get_db)):
    """Qo'shimcha hisob - butunlay o'chiriladi. Oylik (monthly) esa 0 ga tushiriladi,
    aks holda avtomatik qayta yaratilib qolardi."""
    ac = db.query(models.SalaryAccrual).filter(models.SalaryAccrual.id == accrual_id).first()
    if not ac or not ac.teacher_id:
        raise HTTPException(status_code=404, detail="Yozuv topilmadi!")
    tid = ac.teacher_id
    if ac.kind == "monthly":
        ac.amount = 0
        ac.note = f"bekor qilindi ({current_user.username})"
    else:
        db.delete(ac)
    db.commit()
    return _to_out(db, _get_staff(db, tid))
