"""v8.5: O'QUVCHI QARZI.

Model: StudentDue(student_id, month, due_amount) - o'quvchi shu oy uchun jami
qancha to'lashi kerak. Qarz har doim HISOBLANADI:

    qarz = max(0, due_amount - shu oy uchun to'langan summa)

Shuning uchun:
  * to'lov kiritishda "qarz qoldi: X" yozilsa -> due = (shu oy to'langan) + X;
  * keyin o'quvchi qolganini to'lasa, qarz o'z-o'zidan kamayadi (hech narsa qilish shart emas);
  * qarz 0 qilib belgilansa - yozuv o'chiriladi.
O'qituvchilar ulushi faqat HAQIQIY to'lovlardan hisoblanadi - qarz unga ta'sir qilmaydi.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..utils import now_uz_datestring, UZ_MONTHS, auto_year

router = APIRouter(prefix="/api/dues", tags=["dues"])


def paid_for_month(db: Session, student_id: int, month: str, year: Optional[int] = None) -> int:
    """v13.11: shu o'quvchi shu OY+YIL uchun to'lagan summa (yil berilmasa — dastur o'zi aniqlaydi)."""
    if year is None:
        year = auto_year(month)
    return int(db.query(func.coalesce(func.sum(models.Payment.amount), 0)).filter(
        models.Payment.student_id == student_id, models.Payment.month == month, models.Payment.year == year
    ).scalar() or 0)


def set_student_debt(db: Session, student: models.Student, month: str, debt: int, user: str,
                     note: Optional[str] = None, year: Optional[int] = None) -> int:
    """Qolgan qarzni belgilaydi (commit QILMAYDI). Qaytaradi: yangi qarz."""
    if month not in UZ_MONTHS:
        raise HTTPException(status_code=400, detail="Oy noto'g'ri!")
    if year is None:
        year = auto_year(month)
    if debt is None or debt < 0:
        raise HTTPException(status_code=400, detail="Qarz summasi manfiy bo'lishi mumkin emas!")
    db.flush()
    paid = paid_for_month(db, student.id, month, year)
    row = db.query(models.StudentDue).filter(
        models.StudentDue.student_id == student.id, models.StudentDue.month == month,
        models.StudentDue.year == year
    ).first()
    if debt == 0:
        if row:
            db.delete(row)
        return 0
    if not row:
        row = models.StudentDue(student_id=student.id, month=month, year=year, due_amount=0,
                                updated_by=user, updated_at=now_uz_datestring())
        db.add(row)
    row.due_amount = paid + int(debt)
    row.updated_by = user
    row.updated_at = now_uz_datestring()
    if note is not None:
        row.note = note.strip() or None
    return int(debt)


def _rows(db: Session, only_debtors: bool = True) -> List[schemas.DueOut]:
    out = []
    q = (db.query(models.StudentDue, models.Student).join(models.Student, models.StudentDue.student_id == models.Student.id)
         .filter(models.Student.archived_at.is_(None)))   # v12.5: arxivdagilar chiqmaydi
    for d, s in q.all():
        paid = paid_for_month(db, s.id, d.month, d.year)
        debt = max(0, int(d.due_amount) - paid)
        if only_debtors and debt <= 0:
            continue
        out.append(schemas.DueOut(
            student_id=s.id, student_name=f"{s.first_name} {s.last_name}", student_type=s.type,
            class_name=s.class_name, subject_name=s.subject_name, teacher_name=s.teacher_name,
            phone=s.phone or "", month=d.month, year=d.year, due_amount=int(d.due_amount), paid=paid, debt=debt,
            note=d.note, updated_by=d.updated_by, updated_at=d.updated_at,
        ))
    return out


@router.get("", response_model=List[schemas.DueOut])
def list_debts(current_user: models.User = Depends(auth.require_perm('pay', 'bt', 'students', 'hist', 'sms')), db: Session = Depends(get_db)):
    """Hozir qarzi bor o'quvchilar (har o'quvchi+oy bitta qator)."""
    return _rows(db, only_debtors=True)


@router.put("", response_model=schemas.DueOut)
def set_debt(payload: schemas.DueSetIn, current_user: models.User = Depends(auth.require_perm('pay', 'bt', 'students')),
             db: Session = Depends(get_db)):
    """O'quvchining oy uchun qolgan qarzini belgilash yoki o'zgartirish (0 - qarzni yopish)."""
    student = db.query(models.Student).filter(models.Student.id == payload.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")
    if payload.month not in UZ_MONTHS:
        raise HTTPException(status_code=400, detail="Oy noto'g'ri!")
    year = payload.year or auto_year(payload.month)
    debt = set_student_debt(db, student, payload.month, payload.debt, current_user.username, payload.note, year)
    db.commit()
    paid = paid_for_month(db, student.id, payload.month, year)
    return schemas.DueOut(
        student_id=student.id, student_name=f"{student.first_name} {student.last_name}",
        student_type=student.type, class_name=student.class_name, subject_name=student.subject_name,
        teacher_name=student.teacher_name, phone=student.phone or "", month=payload.month, year=year,
        due_amount=paid + debt, paid=paid, debt=debt, note=payload.note,
        updated_by=current_user.username, updated_at=now_uz_datestring(),
    )
