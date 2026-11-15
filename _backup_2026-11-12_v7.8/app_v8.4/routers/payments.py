from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..utils import now_uz_datestring, now_timestamp_ms, parse_uz_datetime, UZ_MONTHS

router = APIRouter(prefix="/api/payments", tags=["payments"])


def _payment_to_out(p: models.Payment) -> schemas.PaymentOut:
    return schemas.PaymentOut.from_orm(p)


@router.get("", response_model=List[schemas.PaymentOut])
def list_payments(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    payments = db.query(models.Payment).order_by(models.Payment.id).all()
    return [_payment_to_out(p) for p in payments]


def _build_auto_allocations(db: Session, student: models.Student, amount: int):
    """YANGI: 'Hodimlar oyligi' uchun - agar to'lov kiritilayotganda frontend
    aniq ulushlarni yubormagan bo'lsa, fan/o'qituvchi foizi asosida avtomatik
    ulush(lar) hisoblanadi. Aniqlik bo'lmagan holatlarda (masalan bitta fanda
    bir nechta o'qituvchi bo'lsa) hech narsa avtomatik ajratilmaydi - rahbar
    keyinchalik to'lovni tahrirlab, qo'lda ulush kiritishi mumkin."""
    allocations = []

    if student.type == "repetitor" and student.teacher_name and student.subject_name:
        teacher = (
            db.query(models.Teacher)
            .join(models.Subject)
            .filter(
                models.Teacher.name == student.teacher_name,
                models.Subject.name == student.subject_name,
            )
            .first()
        )
        if teacher:
            percent = teacher.percent_override
            if percent is None:
                percent = teacher.subject.repetitor_percent
            if percent:
                share = round(amount * percent / 100)
                if share > 0:
                    allocations.append(models.PaymentAllocation(
                        teacher_id=teacher.id,
                        teacher_name=teacher.name,
                        subject_name=teacher.subject.name,
                        amount=share,
                    ))

    elif student.type == "school":
        subjects_with_percent = (
            db.query(models.Subject)
            .filter(models.Subject.school_percent.isnot(None), models.Subject.school_percent > 0)
            .all()
        )
        for subj in subjects_with_percent:
            if len(subj.teachers) != 1:
                # Bir nechta (yoki nolta) o'qituvchi bo'lsa, kim olishini avtomatik
                # aniqlab bo'lmaydi - rahbar buni qo'lda (allocations orqali) kiritadi.
                continue
            share = round(amount * subj.school_percent / 100)
            if share <= 0:
                continue
            teacher = subj.teachers[0]
            allocations.append(models.PaymentAllocation(
                teacher_id=teacher.id,
                teacher_name=teacher.name,
                subject_name=subj.name,
                amount=share,
            ))

    return allocations


@router.post("", response_model=schemas.PaymentOut)
def create_payment(
    payload: schemas.PaymentIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="To'lov miqdori noto'g'ri!")
    if payload.method not in ("naxt", "click"):
        raise HTTPException(status_code=400, detail="To'lov usuli noto'g'ri!")

    student = db.query(models.Student).filter(models.Student.id == payload.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")

    date_str, ts = now_uz_datestring(), now_timestamp_ms()
    if payload.date:
        if current_user.role != "Markaz rahbari":
            raise HTTPException(status_code=403, detail="Sanani faqat markaz rahbari belgilay oladi!")
        try:
            dt = parse_uz_datetime(payload.date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Sana noto'g'ri (masalan: 12.11.2026 14:30)")
        date_str, ts = dt.strftime("%d.%m.%Y %H:%M:%S"), int(dt.timestamp() * 1000)
    if payload.month not in UZ_MONTHS:
        raise HTTPException(status_code=400, detail="Oy noto'g'ri!")

    payment = models.Payment(
        student_id=student.id,
        student_name=f"{student.first_name} {student.last_name}",
        student_phone=student.phone,
        student_type=student.type,
        subject_name=student.subject_name,
        teacher_name=student.teacher_name,
        group_label=student.group_label,
        class_name=student.class_name,
        month=payload.month,
        amount=payload.amount,
        method=payload.method,
        date_str=date_str,
        timestamp=ts,
        added_by=current_user.username,
    )
    db.add(payment)
    db.flush()  # payment.id kerak bo'ladi

    # Ulushlarni (allocations) aniqlash: qo'lda berilgan bo'lsa - o'shani ishlatamiz,
    # aks holda (auto_split=True bo'lsa) fan/o'qituvchi foizi asosida avtomatik hisoblaymiz.
    if payload.allocations:
        total_alloc = sum(a.amount for a in payload.allocations)
        if total_alloc > payload.amount:
            raise HTTPException(status_code=400, detail="Ulushlar yig'indisi to'lov summasidan katta bo'lmasligi kerak!")
        for a in payload.allocations:
            if a.amount <= 0:
                continue
            teacher = db.query(models.Teacher).filter(models.Teacher.id == a.teacher_id).first() if a.teacher_id else None
            if teacher and (teacher.is_staff or not teacher.subject):
                raise HTTPException(status_code=400, detail="Xodimga o'quvchi to'lovidan ulush ajratib bo'lmaydi!")
            db.add(models.PaymentAllocation(
                payment_id=payment.id,
                teacher_id=teacher.id if teacher else None,
                teacher_name=teacher.name if teacher else (a.teacher_name or "Noma'lum"),
                subject_name=teacher.subject.name if teacher else a.subject_name,
                amount=a.amount,
            ))
    elif payload.auto_split:
        for alloc in _build_auto_allocations(db, student, payload.amount):
            alloc.payment_id = payment.id
            db.add(alloc)

    db.commit()
    db.refresh(payment)

    # SMS: Eslatma - Sukhrob Eskiz.uz'dan ro'yxatdan o'tib SMS paket sotib olgach,
    # shu yerga (yoki alohida bir sms.py xizmatiga) real SMS yuborish kodi qo'shiladi.
    # Hozircha SMS matnlari /api/settings orqali saqlanadi va faqat matn sifatida
    # tayyorlanadi (frontend konsolga chiqaradi), haqiqiy yuborish ulanmagan.

    return _payment_to_out(payment)


@router.put("/{payment_id}", response_model=schemas.PaymentOut)
def edit_payment(
    payment_id: int,
    payload: schemas.PaymentEditIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi!")

    # MUHIM TUZATISH: rahbar istalgan to'lovni, admin esa FAQAT O'ZI kiritgan
    # to'lovni tahrirlay oladi (avval admin hech qachon tahrirlay olmasdi - bug bor edi)
    if current_user.role != "Markaz rahbari" and payment.added_by != current_user.username:
        raise HTTPException(status_code=403, detail="Sizda bu amalni bajarish huquqi yo'q!")

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="To'lov miqdorini to'g'ri kiriting!")
    is_rahbar = current_user.role == "Markaz rahbari"

    if payload.allocations is not None:
        # v7.9: ulushlar qo'lda tahrirlandi - eski ulushlar to'liq almashtiriladi.
        # Balans (ledger.py) ulushlardan hisoblangani uchun o'qituvchi balansi avtomatik to'g'rilanadi.
        new_allocs = []
        for a in payload.allocations:
            if a.amount is None or a.amount < 0:
                raise HTTPException(status_code=400, detail="Ulush summasi manfiy bo'lishi mumkin emas!")
            if a.amount == 0:
                continue
            teacher = None
            if a.teacher_id:
                teacher = db.query(models.Teacher).filter(models.Teacher.id == a.teacher_id).first()
                if not teacher:
                    raise HTTPException(status_code=400, detail="Ulushdagi o'qituvchi topilmadi!")
                if teacher.is_staff or not teacher.subject:
                    raise HTTPException(status_code=400, detail="Xodimga o'quvchi to'lovidan ulush ajratib bo'lmaydi!")
            elif not (a.teacher_name or "").strip():
                raise HTTPException(status_code=400, detail="Ulush uchun o'qituvchini tanlang!")
            new_allocs.append(models.PaymentAllocation(
                teacher_id=teacher.id if teacher else None,
                teacher_name=teacher.name if teacher else a.teacher_name.strip(),
                subject_name=teacher.subject.name if teacher else a.subject_name,
                amount=int(a.amount),
            ))
        if sum(x.amount for x in new_allocs) > payload.amount:
            raise HTTPException(status_code=400, detail="O'qituvchilar ulushi yig'indisi to'lov summasidan katta bo'lmasligi kerak!")
        payment.allocations.clear()
        db.flush()
        for x in new_allocs:
            payment.allocations.append(x)
    else:
        # Ulushlarni (allocations) yangi summaga mutanosib ravishda qayta hisoblaymiz,
        # shunda "Hodimlar oyligi" bo'limidagi hisob-kitob to'g'ri qoladi.
        old_amount = payment.amount
        if old_amount > 0 and payment.allocations and old_amount != payload.amount:
            ratio = payload.amount / old_amount
            for alloc in payment.allocations:
                alloc.amount = round(alloc.amount * ratio)

    if payload.month is not None and payload.month != payment.month:
        if not is_rahbar:
            raise HTTPException(status_code=403, detail="Oyni faqat markaz rahbari o'zgartira oladi!")
        if payload.month not in UZ_MONTHS:
            raise HTTPException(status_code=400, detail="Oy noto'g'ri!")
        payment.month = payload.month

    if payload.date:
        if not is_rahbar:
            raise HTTPException(status_code=403, detail="Sanani faqat markaz rahbari o'zgartira oladi!")
        try:
            dt = parse_uz_datetime(payload.date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Sana noto'g'ri (masalan: 12.11.2026 14:30)")
        new_ts = int(dt.timestamp() * 1000)
        if new_ts != payment.timestamp:
            payment.timestamp = new_ts
            payment.date_str = dt.strftime("%d.%m.%Y %H:%M:%S")

    payment.amount = payload.amount
    if payload.method and payload.method in ("naxt", "click"):
        payment.method = payload.method
    payment.edited_by = current_user.username
    payment.edited_at = now_uz_datestring()
    db.commit()
    db.refresh(payment)
    return _payment_to_out(payment)


@router.delete("/{payment_id}")
def delete_payment(
    payment_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi!")

    snapshot = _payment_to_out(payment).dict()
    db.add(models.RecycleBinItem(
        type="payment",
        data=snapshot,
        deleted_at=now_timestamp_ms(),
        deleted_by=current_user.username,
    ))
    db.delete(payment)
    db.commit()
    return {"ok": True}
