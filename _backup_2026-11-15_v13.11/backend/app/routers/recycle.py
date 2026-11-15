import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..student_links import canon, phone9

router = APIRouter(prefix="/api/recycle-bin", tags=["recycle-bin"])

SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000


def _clean_expired(db: Session):
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    db.query(models.RecycleBinItem).filter(
        (now_ms - models.RecycleBinItem.deleted_at) > SEVEN_DAYS_MS
    ).delete(synchronize_session=False)
    db.commit()


def _resolve_student_id(db: Session, data: dict):
    """v11.8: to'lov tiklanayotganda o'quvchisi bazada bo'lmasa (o'chirilgan) — xato bermaymiz:
    ism + telefon bo'yicha qidiramiz (masalan o'quvchi oldin tiklangan bo'lsa), topilmasa — o'quvchisiz."""
    sid = data.get("student_id")
    if sid and db.query(models.Student.id).filter(models.Student.id == sid).first():
        return sid
    name, ph = canon(data.get("student_name") or ""), phone9(data.get("student_phone") or "")
    found = [st.id for st in db.query(models.Student).all()
             if canon(f"{st.first_name} {st.last_name}") == name and (not ph or phone9(st.phone) == ph)]
    return found[0] if len(found) == 1 else None


def _snap_year(data: dict):
    from ..utils import auto_year
    try:
        return auto_year(data["month"], data.get("timestamp") or None)
    except ValueError:
        return None


def _payment_from_snapshot(db: Session, data: dict, current_user, student_id=None) -> models.Payment:
    payment = models.Payment(
        student_id=student_id if student_id is not None else _resolve_student_id(db, data),
        student_name=data["student_name"],
        student_phone=data["student_phone"],
        student_type=data["student_type"],
        subject_name=data.get("subject_name"),
        teacher_name=data.get("teacher_name"),
        group_label=data.get("group_label"),
        class_name=data.get("class_name"),
        month=data["month"],
        year=data.get("year") or _snap_year(data),   # v13.11
        amount=data["amount"],
        method=data.get("method") or "naxt",
        date_str=data.get("date_str", ""),
        timestamp=data.get("timestamp", 0),
        added_by=data.get("added_by", current_user.username),
        edited_by=data.get("edited_by"),
        edited_at=data.get("edited_at"),
    )
    # v8.9: o'qituvchilar ulushi ham qaytariladi
    alloc_total = 0
    for a in data.get("allocations") or []:
        amt = int(a.get("amount") or 0)
        if amt <= 0 or alloc_total + amt > int(data["amount"]):
            continue
        tid = a.get("teacher_id")
        if tid is not None and not db.query(models.Teacher.id).filter(models.Teacher.id == tid).first():
            tid = None
        payment.allocations.append(models.PaymentAllocation(
            teacher_id=tid,
            teacher_name=a.get("teacher_name") or "",
            subject_name=a.get("subject_name"),
            amount=amt,
        ))
        alloc_total += amt
    return payment


@router.get("", response_model=List[schemas.RecycleBinOut])
def list_recycle_bin(
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    _clean_expired(db)
    q = db.query(models.RecycleBinItem)
    if current_user.role != "Markaz rahbari":
        # v8.9: admin faqat o'quvchi va to'lovlarni ko'radi (to'liq tizim zaxirasi — faqat rahbarga)
        q = q.filter(models.RecycleBinItem.type.in_(["student", "payment"]))
    return q.order_by(models.RecycleBinItem.deleted_at.desc()).all()


@router.post("/{item_id}/restore")
def restore_item(
    item_id: int,
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    item = db.query(models.RecycleBinItem).filter(models.RecycleBinItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Element topilmadi!")

    data = item.data
    if current_user.role != "Markaz rahbari" and item.type not in ("student", "payment"):
        raise HTTPException(status_code=403, detail="Buni faqat markaz rahbari tiklay oladi!")

    if item.type == "student":
        student = models.Student(
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone=data["phone"],
            phone2=data.get("phone2"),
            type=data["type"],
            class_name=data.get("class_name"),
            subject_name=data.get("subject_name"),
            teacher_name=data.get("teacher_name"),
            group_label=data.get("group_label"),
            added_by=data.get("added_by", current_user.username),
        )
        db.add(student)
        db.flush()
        # v11.8: o'quvchi bilan birga o'chirilgan to'lovlari ham qaytadi (yangi o'quvchiga bog'lanadi)
        old_id, full = data.get("id"), f"{data['first_name']} {data['last_name']}"
        for it in db.query(models.RecycleBinItem).filter(models.RecycleBinItem.type == "payment").all():
            d = it.data or {}
            if (old_id and d.get("student_id") == old_id) or (not d.get("student_id") and d.get("student_name") == full):
                db.add(_payment_from_snapshot(db, d, current_user, student_id=student.id))
                db.delete(it)
        # avval o'quvchisiz tiklangan to'lovlari ham shu o'quvchiga qaytadan bog'lanadi
        for p in db.query(models.Payment).filter(models.Payment.student_id.is_(None), models.Payment.student_name == full).all():
            if phone9(p.student_phone) == phone9(data["phone"]):
                p.student_id = student.id
    elif item.type == "payment":
        db.add(_payment_from_snapshot(db, data, current_user))
    elif item.type == "allData":
        raise HTTPException(
            status_code=400,
            detail="To'liq tizim zaxirasini shu yerdan emas, /api/backup/restore orqali tiklang.",
        )

    db.delete(item)
    db.commit()
    return {"ok": True}


@router.delete("/{item_id}")
def delete_permanently(
    item_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    item = db.query(models.RecycleBinItem).filter(models.RecycleBinItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Element topilmadi!")
    db.delete(item)
    db.commit()
    return {"ok": True}
