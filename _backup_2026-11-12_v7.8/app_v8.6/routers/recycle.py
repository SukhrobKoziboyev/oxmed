import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/api/recycle-bin", tags=["recycle-bin"])

SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000


def _clean_expired(db: Session):
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    db.query(models.RecycleBinItem).filter(
        (now_ms - models.RecycleBinItem.deleted_at) > SEVEN_DAYS_MS
    ).delete(synchronize_session=False)
    db.commit()


@router.get("", response_model=List[schemas.RecycleBinOut])
def list_recycle_bin(
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    _clean_expired(db)
    return db.query(models.RecycleBinItem).order_by(models.RecycleBinItem.deleted_at.desc()).all()


@router.post("/{item_id}/restore")
def restore_item(
    item_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    item = db.query(models.RecycleBinItem).filter(models.RecycleBinItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Element topilmadi!")

    data = item.data

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
    elif item.type == "payment":
        payment = models.Payment(
            student_id=data.get("student_id"),
            student_name=data["student_name"],
            student_phone=data["student_phone"],
            student_type=data["student_type"],
            subject_name=data.get("subject_name"),
            teacher_name=data.get("teacher_name"),
            group_label=data.get("group_label"),
            class_name=data.get("class_name"),
            month=data["month"],
            amount=data["amount"],
            date_str=data.get("date_str", ""),
            timestamp=data.get("timestamp", 0),
            added_by=data.get("added_by", current_user.username),
            edited_by=data.get("edited_by"),
            edited_at=data.get("edited_at"),
        )
        db.add(payment)
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
