from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=schemas.SettingsOut)
def get_settings(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    settings = db.query(models.Settings).first()
    phones = db.query(models.RahbarPhone).all()
    return schemas.SettingsOut(
        sms_template_parent=settings.sms_template_parent,
        sms_template_rahbar=settings.sms_template_rahbar,
        rahbar_phones=[schemas.PhoneOut.from_orm(p) for p in phones],
        sms_enabled=bool(getattr(settings, "sms_enabled", False)),
    )


@router.put("/sms-templates")
def update_sms_templates(
    payload: schemas.SMSTemplatesIn,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    settings = db.query(models.Settings).first()
    settings.sms_template_parent = payload.sms_template_parent
    settings.sms_template_rahbar = payload.sms_template_rahbar
    db.commit()
    return {"ok": True}


@router.post("/phones")
def add_phone(
    payload: schemas.PhoneIn,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    existing = db.query(models.RahbarPhone).filter(models.RahbarPhone.phone == payload.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu telefon raqam allaqachon qo'shilgan!")
    phone = models.RahbarPhone(phone=payload.phone)
    db.add(phone)
    db.commit()
    return {"ok": True, "id": phone.id}


@router.delete("/phones/{phone_id}")
def delete_phone(
    phone_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    phone = db.query(models.RahbarPhone).filter(models.RahbarPhone.id == phone_id).first()
    if not phone:
        raise HTTPException(status_code=404, detail="Telefon raqam topilmadi!")
    db.delete(phone)
    db.commit()
    return {"ok": True}
