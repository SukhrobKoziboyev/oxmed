"""v7.6: O'QITUVCHI HISOB-KITOBI - YAGONA MANBA

Barcha o'qituvchi balansi hisob-kitoblari FAQAT shu fayldagi funksiyalar orqali
bajariladi (Hodimlar oyligi, O'qituvchi kabineti, bosh sahifa - hammasi shu yerdan
oladi). Shuning uchun turli joylarda turli raqam chiqishi mumkin emas.

Formula:
    balans = ulushlar (+)  -  berilgan oylik/avanslar (-)  +  qaytarilgan pullar (+)

    balans > 0  -> o'qituvchi markazdan shuncha OLISHI kerak
    balans < 0  -> o'qituvchi markazga shuncha QARZDOR
    balans = 0  -> hisob teng

Qarz qanday yopiladi?
  1) O'qituvchi naqd qaytarsa -> "Qaytarildi" (kind='return') yozuvi qo'shiladi.
  2) Markaz o'quvchilar to'lovidan ushlab qolsa -> hech narsa qilish shart emas:
     har bir yangi o'quvchi to'lovida o'qituvchiga yoziladigan ulush balansga
     avtomatik qo'shiladi va qarz o'z-o'zidan kamayadi. Faqat qarz yopilguncha
     o'qituvchiga oylik bermaslik kifoya.
  Eski yozuvlar HECH QACHON o'chirilmaydi - tarix doim to'liq qoladi.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models

KIND_PAYOUT = "payout"
KIND_RETURN = "return"


def teacher_totals(db: Session, teacher_id: int):
    """(jami_ulush, jami_berilgan, jami_qaytarilgan, balans) - SQL yig'indisi bilan."""
    allocated = db.query(func.coalesce(func.sum(models.PaymentAllocation.amount), 0)).filter(
        models.PaymentAllocation.teacher_id == teacher_id
    ).scalar() or 0

    paid_out = db.query(func.coalesce(func.sum(models.TeacherPayout.amount), 0)).filter(
        models.TeacherPayout.teacher_id == teacher_id,
        func.coalesce(models.TeacherPayout.kind, KIND_PAYOUT) != KIND_RETURN,
    ).scalar() or 0

    returned = db.query(func.coalesce(func.sum(models.TeacherPayout.amount), 0)).filter(
        models.TeacherPayout.teacher_id == teacher_id,
        models.TeacherPayout.kind == KIND_RETURN,
    ).scalar() or 0

    allocated, paid_out, returned = int(allocated), int(paid_out), int(returned)
    return allocated, paid_out, returned, allocated - paid_out + returned


def net_cash_out(db: Session) -> int:
    """Markaz kassasidan o'qituvchilarga sof chiqqan pul (berilgan - qaytarilgan)."""
    paid_out = db.query(func.coalesce(func.sum(models.TeacherPayout.amount), 0)).filter(
        func.coalesce(models.TeacherPayout.kind, KIND_PAYOUT) != KIND_RETURN
    ).scalar() or 0
    returned = db.query(func.coalesce(func.sum(models.TeacherPayout.amount), 0)).filter(
        models.TeacherPayout.kind == KIND_RETURN
    ).scalar() or 0
    return int(paid_out) - int(returned)


def teacher_ledger(db: Session, teacher: models.Teacher):
    """O'qituvchining to'liq hisob varag'i: har bir yozuv va undan keyingi balans."""
    rows = []

    allocs = (
        db.query(models.PaymentAllocation, models.Payment)
        .join(models.Payment, models.PaymentAllocation.payment_id == models.Payment.id)
        .filter(models.PaymentAllocation.teacher_id == teacher.id)
        .all()
    )
    for a, p in allocs:
        rows.append({
            "kind": "share",
            "amount": int(a.amount),
            "timestamp": int(p.timestamp or 0),
            "date_str": p.date_str,
            "title": f"{p.student_name} to'lovidan ulush",
            "detail": f"{p.month} oyi • to'lov {int(p.amount):,} so'm".replace(",", " ")
                      + (f" • {a.subject_name}" if a.subject_name else ""),
            "ref_id": a.id,
            "_order": 0,
        })

    payouts = db.query(models.TeacherPayout).filter(models.TeacherPayout.teacher_id == teacher.id).all()
    for po in payouts:
        is_return = (po.kind == KIND_RETURN)
        rows.append({
            "kind": KIND_RETURN if is_return else KIND_PAYOUT,
            "amount": int(po.amount) if is_return else -int(po.amount),
            "timestamp": int(po.timestamp or 0),
            "date_str": po.date_str,
            "title": "Markazga qaytarildi" if is_return else "Oylik / avans berildi",
            "detail": " • ".join(x for x in [po.note, f"kiritdi: {po.paid_by}" if po.paid_by else None] if x),
            "ref_id": po.id,
            "_order": 1,
        })

    # Vaqt bo'yicha tartib (bir xil vaqtda: avval ulush, keyin to'lov)
    rows.sort(key=lambda r: (r["timestamp"], r["_order"], r["ref_id"] or 0))

    balance = 0
    for r in rows:
        balance += r["amount"]
        r["balance"] = balance
        r.pop("_order", None)

    allocated, paid_out, returned, owed = teacher_totals(db, teacher.id)
    # Ishonch uchun: ketma-ket hisoblangan balans yig'indi formulasiga teng bo'lishi shart
    assert balance == owed, f"Hisob-kitob mos emas: {balance} != {owed}"

    rows.reverse()  # eng yangisi tepada
    return {
        "teacher_id": teacher.id,
        "teacher_name": teacher.name,
        "total_allocated": allocated,
        "total_paid_out": paid_out,
        "total_returned": returned,
        "owed": owed,
        "entries": rows,
    }
