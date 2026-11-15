"""v7.6: O'QITUVCHI HISOB-KITOBI - YAGONA MANBA

Barcha o'qituvchi balansi hisob-kitoblari FAQAT shu fayldagi funksiyalar orqali
bajariladi (Hodimlar oyligi, O'qituvchi kabineti, bosh sahifa - hammasi shu yerdan
oladi). Shuning uchun turli joylarda turli raqam chiqishi mumkin emas.

Formula:
    balans = ulushlar (+)  +  hisoblangan oylik (+, v8.4 xodimlar)
             -  berilgan oylik/avanslar (-)  +  qaytarilgan pullar (+)

    "ulushlar" (total_allocated) ichiga xodimlarning hisoblangan oyligi ham kiradi
    (o'qituvchilarda u 0 - ularning hisobi avvalgidek o'zgarmaydi).

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
KIND_ACCRUAL = "accrual"  # v8.4: ledger qatori turi (xodimga oylik hisoblandi)

UZ_MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
             "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]


def accrued_total(db: Session, teacher_id: int) -> int:
    """v8.4: xodimga hisoblangan jami oylik (monthly + extra)."""
    return int(db.query(func.coalesce(func.sum(models.SalaryAccrual.amount), 0)).filter(
        models.SalaryAccrual.teacher_id == teacher_id
    ).scalar() or 0)


def _periods(start: str, end: str):
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (ey, em) and len(out) < 240:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def period_label(period: str) -> str:
    try:
        return f"{UZ_MONTHS[int(period[5:7]) - 1]} {period[:4]}"
    except Exception:  # noqa: BLE001
        return period or ""


def ensure_staff_accruals(db: Session, teacher) -> int:
    """v8.4: xodim uchun salary_start oyidan joriy oygacha har oyga bitta oylik
    yozuvi borligini ta'minlaydi (yo'qlarini yaratadi). Idempotent: qayta
    chaqirilsa hech narsa ikki marta yozilmaydi (bazada unique index ham bor).
    Joriy oy ham hisoblanadi (oy boshida o'sha oy oyligi yoziladi)."""
    if not teacher or not teacher.is_staff or not teacher.monthly_salary or not teacher.salary_start:
        return 0
    import datetime
    from .utils import now_uz, UZ_TZ, now_uz_datestring
    now = now_uz()
    current = f"{now.year:04d}-{now.month:02d}"
    if teacher.salary_start > current:
        return 0
    existing = {p for (p,) in db.query(models.SalaryAccrual.period).filter(
        models.SalaryAccrual.teacher_id == teacher.id,
        models.SalaryAccrual.kind == "monthly",
    ).all()}
    created = 0
    for per in _periods(teacher.salary_start, current):
        if per in existing:
            continue
        ts = int(datetime.datetime(int(per[:4]), int(per[5:7]), 1, tzinfo=UZ_TZ).timestamp() * 1000)
        db.add(models.SalaryAccrual(
            teacher_id=teacher.id, teacher_name=teacher.name, kind="monthly", period=per,
            amount=int(teacher.monthly_salary), note=None,
            date_str=datetime.datetime(int(per[:4]), int(per[5:7]), 1, tzinfo=UZ_TZ).strftime("%d.%m.%Y %H:%M:%S"),
            timestamp=ts, created_by="avto",
        ))
        created += 1
    if created:
        try:
            db.commit()
        except Exception:  # noqa: BLE001 - parallel so'rov allaqachon yaratgan bo'lsa
            db.rollback()
    return created


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

    allocated = int(allocated) + accrued_total(db, teacher_id)  # v8.4: xodim oyligi (o'qituvchida 0)
    paid_out, returned = int(paid_out), int(returned)
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

    # v8.4: xodimga hisoblangan oyliklar (0 so'mlik - bekor qilinganlar ko'rsatilmaydi)
    accruals = db.query(models.SalaryAccrual).filter(
        models.SalaryAccrual.teacher_id == teacher.id, models.SalaryAccrual.amount != 0
    ).all()
    for ac in accruals:
        rows.append({
            "kind": KIND_ACCRUAL,
            "amount": int(ac.amount),
            "timestamp": int(ac.timestamp or 0),
            "date_str": ac.date_str,
            "title": (f"{period_label(ac.period)} oyligi hisoblandi" if ac.kind == "monthly" else "Qo'shimcha hisoblandi"),
            "detail": " • ".join(x for x in [ac.note, f"kiritdi: {ac.created_by}" if ac.created_by and ac.created_by != "avto" else None] if x),
            "ref_id": ac.id,
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
