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
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas, auth
from ..database import get_db
from ..utils import now_uz_datestring, now_timestamp_ms, current_uz_month_name, ts_to_uz_datestring, UZ_MONTHS, now_uz
from .. import ledger
from .teacher_self import my_students, teacher_payments

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


@router.get("/payouts-list")
def payouts_list(
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    """v10.0: "Kimga qancha berildi" hisoboti uchun — barcha berilgan oylik/avans va
    qaytarilgan pullar (o'qituvchi va xodimlar). Faqat o'qish; summalar o'zgarmaydi."""
    tmap = {t.id: t for t in db.query(models.Teacher).options(joinedload(models.Teacher.subject)).all()}
    out = []
    for p in db.query(models.TeacherPayout).order_by(models.TeacherPayout.timestamp.desc()).all():
        t = tmap.get(p.teacher_id)
        role = ""
        if t is not None:
            role = (t.position or "Xodim") if t.is_staff else ((t.subject.name if t.subject else "") or "O'qituvchi")
        out.append({
            "id": p.id, "teacher_id": p.teacher_id, "name": p.teacher_name, "role": role,
            "is_staff": bool(t.is_staff) if t is not None else False,
            "amount": int(p.amount), "kind": p.kind or "payout", "note": p.note or "", "ptype": p.ptype, "month": p.month,
            "timestamp": int(p.timestamp), "paid_by": p.paid_by,
            "date_str": ts_to_uz_datestring(p.timestamp),
            "orphan": t is None,  # o'qituvchi/xodim tizimdan o'chirilgan, pul yozuvi qolgan
        })
    return out


@router.get("/overview", response_model=List[schemas.TeacherSalaryOut])
def salary_overview(
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    teachers = (
        db.query(models.Teacher)
        .options(joinedload(models.Teacher.subject))
        .filter(models.Teacher.is_staff.is_(False))  # v8.4: xodimlar alohida bo'limda
        .all()
    )
    current_month = current_uz_month_name()
    result = []

    for t in teachers:
        allocated_sum, payouts_sum, returned_sum, owed = _teacher_totals(db, t.id)
        percent = t.percent_override if t.percent_override is not None else t.subject.repetitor_percent

        # v11.19: o'qituvchi kabinetidagi bilan AYNAN bir xil — asosiy + biriktirilgan + to'lovdan ulush olgan
        # o'quvchilar; "to'lagan" = shu oy uchun SHU o'qituvchiga tegishli to'lovi bor (teacher_self.teacher_payments)
        entries = my_students(db, t)
        paid_n = 0
        for st, source, _g in entries:
            if any(p.month == current_month and (p.year is None or p.year == now_uz().year) for p, _share in teacher_payments(db, t, st, source)):
                paid_n += 1

        result.append(schemas.TeacherSalaryOut(
            teacher_id=t.id,
            teacher_name=t.name,
            subject_name=t.subject.name,
            percent=percent,
            total_allocated=allocated_sum,
            total_paid_out=payouts_sum,
            total_returned=returned_sum,
            owed=owed,
            phone=t.phone,
            students_count=len(entries),
            paid_count=paid_n,
            unpaid_count=len(entries) - paid_n,
        ))

    return result


# v12.3: "O'quvchilar / To'lagan / To'lamagan" ustiga bosilganda — ro'yxat (faqat o'qish, hisob-kitobga tegmaydi)
@router.get("/teacher/{teacher_id}/students")
def teacher_students_list(
    teacher_id: int,
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    from ..student_links import who_label
    from ..utils import utc_naive_to_uz_string
    t = db.query(models.Teacher).filter(models.Teacher.id == teacher_id, models.Teacher.is_staff.is_(False)).first()
    if not t:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")
    current_month = current_uz_month_name()
    who_cache, out = {}, []
    for st, source, group in my_students(db, t):
        pays = teacher_payments(db, t, st, source)
        cur = [(p, sh) for p, sh in pays if p.month == current_month and (p.year is None or p.year == now_uz().year)]
        if st.added_by not in who_cache:
            who_cache[st.added_by] = who_label(db, st.added_by)
        out.append({
            "id": st.id, "first_name": st.first_name, "last_name": st.last_name,
            "phone": st.phone, "phone2": getattr(st, "phone2", None),
            "added_by": who_cache[st.added_by] or "—",
            "added_at": utc_naive_to_uz_string(st.added_at) if st.added_at else "",
            "source": source, "group": group,
            "paid": bool(cur), "month_share": sum(int(sh) for _p, sh in cur),
        })
    out.sort(key=lambda r: ((r["last_name"] or "").lower(), (r["first_name"] or "").lower()))
    return {"teacher": {"id": t.id, "name": t.name, "subject": t.subject.name if t.subject else ""},
            "month": current_month, "students": out}


@router.get("/teacher/{teacher_id}", response_model=schemas.TeacherSalaryDetailOut)
def teacher_salary_detail(
    teacher_id: int,
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")

    ledger.ensure_staff_accruals(db, teacher)
    allocated_sum, payouts_sum, returned_sum, owed = _teacher_totals(db, teacher_id)
    percent = teacher.percent_override if teacher.percent_override is not None else (teacher.subject.repetitor_percent if teacher.subject else None)

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
        subject_name=teacher.subject.name if teacher.subject else (teacher.position or "Xodim"),
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
    ledger.ensure_staff_accruals(db, teacher)
    return ledger.teacher_ledger(db, teacher)


@router.post("/payout", response_model=schemas.PayoutOut)
def create_payout(
    payload: schemas.PayoutIn,
    background: BackgroundTasks,
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

    # v11.16: avans yoki oylik + qaysi oy uchun (faqat pul berilganda)
    ptype, month = None, None
    if payload.kind == ledger.KIND_PAYOUT:
        ptype = (payload.ptype or "avans").strip().lower()
        if ptype not in ("avans", "oylik"):
            raise HTTPException(status_code=400, detail="Turi noto'g'ri (avans yoki oylik)!")
        month = (payload.month or "").strip() or current_uz_month_name()
        if month not in UZ_MONTHS:
            raise HTTPException(status_code=400, detail="Oy noto'g'ri!")

    payout = models.TeacherPayout(
        teacher_id=teacher.id,
        teacher_name=teacher.name,
        amount=payload.amount,
        note=payload.note,
        date_str=now_uz_datestring(),
        timestamp=now_timestamp_ms(),
        paid_by=current_user.username,
        kind=payload.kind,
        ptype=ptype,
        month=month,
    )
    db.add(payout)
    db.commit()
    db.refresh(payout)
    out = schemas.PayoutOut.from_orm(payout)
    # v11.16: xodimga SMS — "... siz Noyabr oyi uchun 500 000 so'm avans oldingiz"
    if ptype:
        st = db.query(models.Settings).first()
        from .sms import send_payout_sms, configured
        if not (st and st.sms_enabled and getattr(st, "sms_to_staff", True) and configured()):
            out.sms = "off"
        elif not teacher.phone:
            out.sms = "no_phone"
        else:
            out.sms = "queued"
            background.add_task(send_payout_sms, payout.id)
    return out


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
