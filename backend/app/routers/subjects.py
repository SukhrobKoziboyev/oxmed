from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


@router.get("", response_model=list[schemas.SubjectOut])
def list_subjects(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == auth.ROLE_ATT:  # v12.8: yo'qlamachi faqat yo'qlamani ko'radi
        raise HTTPException(status_code=403, detail="Sizda ruxsat yo'q!")
    return db.query(models.Subject).order_by(models.Subject.id).all()


@router.post("", response_model=schemas.SubjectOut)
def create_subject(
    payload: schemas.SubjectIn,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Fan nomini kiriting!")
    if db.query(models.Subject).filter(models.Subject.name == name).first():
        raise HTTPException(status_code=400, detail="Bu fan allaqachon mavjud!")
    subject = models.Subject(name=name)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


@router.put("/{subject_id}", response_model=schemas.SubjectOut)
def update_subject(
    subject_id: int,
    payload: schemas.SubjectIn,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Fan topilmadi!")
    new_name = payload.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Fan nomini kiriting!")
    if new_name != subject.name and db.query(models.Subject).filter(models.Subject.name == new_name).first():
        raise HTTPException(status_code=400, detail="Bu fan allaqachon mavjud!")

    old_name = subject.name
    subject.name = new_name
    db.commit()
    db.refresh(subject)

    # O'quvchi/to'lov yozuvlaridagi snapshot nomini ham yangilaymiz
    db.query(models.Student).filter(models.Student.subject_name == old_name).update(
        {models.Student.subject_name: new_name}
    )
    db.query(models.Payment).filter(models.Payment.subject_name == old_name).update(
        {models.Payment.subject_name: new_name}
    )
    db.commit()

    return subject


@router.delete("/{subject_id}")
def delete_subject(
    subject_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Fan topilmadi!")

    students_count = db.query(models.Student).filter(models.Student.subject_name == subject.name).count()
    if students_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Bu fanda {students_count} ta o'quvchi bor! Avval ularni boshqa fanga ko'chiring.",
        )

    db.delete(subject)  # teachers/groups cascade orqali o'chadi
    db.commit()
    return {"ok": True}


@router.put("/{subject_id}/percent", response_model=schemas.SubjectOut)
def set_subject_percent(
    subject_id: int,
    payload: schemas.SubjectPercentIn,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    """YANGI: 'Hodimlar oyligi' bo'limi uchun - rahbar shu fan bo'yicha
    repetitor va maktab to'lovlaridan avtomatik ajratiladigan foizlarni
    belgilaydi (0-100 oralig'ida, bo'sh qoldirilsa o'chadi)."""
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Fan topilmadi!")

    for value in (payload.repetitor_percent, payload.school_percent):
        if value is not None and not (0 <= value <= 100):
            raise HTTPException(status_code=400, detail="Foiz 0 dan 100 gacha bo'lishi kerak!")

    subject.repetitor_percent = payload.repetitor_percent
    subject.school_percent = payload.school_percent
    db.commit()
    db.refresh(subject)
    return subject
