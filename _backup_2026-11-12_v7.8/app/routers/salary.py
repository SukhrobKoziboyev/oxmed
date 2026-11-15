"""YANGI BO'LIM: "Hodimlar oyligi" (Staff salary)

Bu router rahbar/admin uchun quyidagilarni ta'minlaydi:
- Har bir o'qituvchining jami ajratilgan ulushi (PaymentAllocation yig'indisi)
- Har bir o'qituvchiga berilgan to'lovlar (TeacherPayout) - avans/oylik sifatida
- "Hozir olishi kerak bo'lgan summa" = jami ulush - jami berilgan to'lov
- Yangi to'lov (payout) qo'shish / o'chirish

Fan/o'qituvchi foizini o'rnatish subjects.py va teachers.py da (percent
endpointlari orqali) amalga oshiriladi.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas, auth
from ..database import get_db
from ..utils import now_uz_datestring, now_timestamp_ms, current_uz_month_name
from .. import ledger

router = APIRouter(prefix="/api/salary", tags=["salary"])


def _teacher_totals(db: Session, teacher_id: int):
    """v7.6: hisob-kitob endi yagona manbadan (app/ledger.py) olinadi."""
    return ledger.teacher_totals(db, teacher_id)


@router.get("/total-payouts")
def get_total_payouts(
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    """YANGI: bosh sahifadagi "Jami summa" dan o'qituvchilarga berilgan
    barcha oylik/avanslarni ayirib ko'rsatish uchun - markazning haqiqiy
    sof (retained) summasini hisoblash imumkin bo'lsin."""
    # v7.6: sof chiqim = berilgan oylik/avanslar - o'qituvchilar qaytargan pullar
    return {"total_payouts": ledger.net_cash_out(db)}


@router.get("/overview", response_model=List[schemas.TeacherSalaryOut])
def salary_overview(
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    teachers = (
        db.query(models.Teacher)
        .options(joinedload(models.Teacher.subject))
        .all()
    )
    current_month = current_uz_month_name()
    result = []

    for t in teachers:
        allocated_sum, payouts_sum, returned_sum, owed = _teacher_totals(db, t.id)
        percent = t.percent_override if t.percent_override is not None else t.subject.repetitor_percent

        students = db.query(models.Student).filter(
            models.Student.type == "repetitor",
            models.Student.teacher_name == t.name,
            models.Student.subject_name == t.subject.name,
        ).all()
        student_names = {f"{s.first_name} {s.last_name}" for s in students}
        paid_names = set()
        if student_names:
            paid_payments = db.query(models.Payment.student_name).filter(
                models.Payment.month == current_month,
                models.Payment.student_name.in_(student_names),
            ).distinct().all()
            paid_names = {p[0] for p in paid_payments}

        result.append(schemas.TeacherSalaryOut(
            teacher_id=t.id,
            teacher_name=t.name,
            subject_name=t.subject.name,
            percent=percent,
            total_allocated=allocated_sum,
            total_paid_out=payouts_sum,
            total_returned=returned_sum,
            owed=owed,
            students_count=len(student_names),
            paid_count=len(paid_names),
            unpaid_count=len(student_names) - len(paid_names),
        ))

    return result


@router.get("/teacher/{teacher_id}", response_model=schemas.TeacherSalaryDetailOut)
def teacher_salary_detail(
    teacher_id: int,
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")

    allocated_sum, payouts_sum, returned_sum, owed = _teacher_totals(db, teacher_id)
    percent = teacher.percent_override if teacher.percent_override is not None else teacher.subject.repetitor_percent

    allocations = (
        db.query(models.PaymentAllocation)
        .filter(models.PaymentAllocation.teacher_id == teacher_id)
        .order_by(models.PaymentAllocation.id.desc())
        .limit(200)
        .all()
    )
    payouts = (
        db.query(models.TeacherPayout)
        .filter(models.TeacherPayout.teacher_id == teacher_id)
        .order_by(models.TeacherPayout.timestamp.desc())
        .all()
    )

    return schemas.TeacherSalaryDetailOut(
        teacher_id=teacher.id,
        teacher_name=teacher.name,
        subject_name=teacher.subject.name,
        percent=percent,
        total_allocated=allocated_sum,
        total_paid_out=payouts_sum,
        total_returned=returned_sum,
        owed=owed,
        allocations=allocations,
        payouts=payouts,
    )


@router.get("/teacher/{teacher_id}/ledger", response_model=schemas.TeacherLedgerOut)
def teacher_ledger(
    teacher_id: int,
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    """v7.6: o'qituvchining to'liq hisob varag'i (har bir yozuv + balans)."""
    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")
    return ledger.teacher_ledger(db, teacher)


@router.post("/payout", response_model=schemas.PayoutOut)
def create_payout(
    payload: schemas.PayoutIn,
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Summa noto'g'ri!")
    if payload.kind not in (ledger.KIND_PAYOUT, ledger.KIND_RETURN):
        raise HTTPException(status_code=400, detail="Yozuv turi noto'g'ri!")

    teacher = db.query(models.Teacher).filter(models.Teacher.id == payload.teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")

    payout = models.TeacherPayout(
        teacher_id=teacher.id,
        teacher_name=teacher.name,
        amount=payload.amount,
        note=payload.note,
        date_str=now_uz_datestring(),
        timestamp=now_timestamp_ms(),
        paid_by=current_user.username,
        kind=payload.kind,
    )
    db.add(payout)
    db.commit()
    db.refresh(payout)
    return payout


@router.delete("/payout/{payout_id}")
def delete_payout(
    payout_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    payout = db.query(models.TeacherPayout).filter(models.TeacherPayout.id == payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Yozuv topilmadi!")
    db.delete(payout)
    db.commit()
    return {"ok": True}
