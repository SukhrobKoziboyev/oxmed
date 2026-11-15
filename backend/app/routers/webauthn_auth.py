"""v7.7: BARMOQ IZI / FACE ID BILAN KIRISH (WebAuthn / Passkey)

Qanday ishlaydi:
  1) Foydalanuvchi bir marta parol bilan kiradi va "Barmoq izini yoqish" ni bosadi.
  2) Telefon barmoq izi / yuzni so'raydi va o'zida maxfiy kalit yaratadi.
     Serverga faqat OCHIQ kalit yuboriladi (webauthn_credentials jadvali).
  3) Keyingi safar "Barmoq izi bilan kirish" bosilsa, telefon yana barmoq izini
     so'raydi va server bergan tasodifiy "savol"ni maxfiy kalit bilan imzolaydi.
     Server imzoni ochiq kalit bilan tekshiradi va to'g'ri bo'lsa token beradi.

Xavfsizlik: barmoq izi/yuz hech qachon telefondan chiqmaydi va serverga
yuborilmaydi. Kalit faqat shu sayt (oxmed.uz) uchun ishlaydi - boshqa sayt uni
ishlata olmaydi.

Eslatma: agar serverda `webauthn` kutubxonasi o'rnatilmagan bo'lsa, bu bo'lim
o'chiq turadi (status: available=false), qolgan tizim esa odatdagidek ishlaydi.
"""
import os
import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/api/webauthn", tags=["webauthn"])

RP_ID = os.getenv("WEBAUTHN_RP_ID", "oxmed.uz")
RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "OXMED")
ORIGINS = [o.strip() for o in os.getenv(
    "WEBAUTHN_ORIGINS", "https://oxmed.uz,https://www.oxmed.uz"
).split(",") if o.strip()]
CHALLENGE_TTL_MS = 5 * 60 * 1000

try:  # kutubxona bo'lmasa ham butun tizim ishlashda davom etadi
    import webauthn
    from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        AuthenticatorAttachment,
        ResidentKeyRequirement,
        UserVerificationRequirement,
        PublicKeyCredentialDescriptor,
    )
    WEBAUTHN_OK = True
except Exception:  # noqa: BLE001
    WEBAUTHN_OK = False


def _now_ms() -> int:
    return int(time.time() * 1000)


def _require_lib():
    if not WEBAUTHN_OK:
        raise HTTPException(status_code=503, detail="Barmoq izi bilan kirish serverda hali yoqilmagan.")


def _save_challenge(db: Session, challenge: bytes, kind: str, user_id: Optional[int]) -> int:
    # eskirgan savollarni tozalab turamiz
    db.query(models.AuthChallenge).filter(models.AuthChallenge.expires_at < _now_ms()).delete()
    ch = models.AuthChallenge(
        challenge=bytes_to_base64url(challenge), kind=kind, user_id=user_id,
        expires_at=_now_ms() + CHALLENGE_TTL_MS, used=False,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch.id


def _take_challenge(db: Session, challenge_id: int, kind: str, user_id: Optional[int]) -> bytes:
    ch = db.query(models.AuthChallenge).filter(models.AuthChallenge.id == challenge_id).first()
    if (not ch or ch.used or ch.kind != kind or ch.expires_at < _now_ms()
            or (user_id is not None and ch.user_id != user_id)):
        raise HTTPException(status_code=400, detail="So'rov muddati o'tgan. Qaytadan urinib ko'ring.")
    ch.used = True  # bir marta ishlatiladi
    db.commit()
    return base64url_to_bytes(ch.challenge)


class VerifyIn(BaseModel):
    challenge_id: int
    credential: dict
    device_name: Optional[str] = None


@router.get("/status")
def status():
    return {"available": WEBAUTHN_OK}


# ---------------- Ro'yxatdan o'tkazish (kirgan foydalanuvchi uchun) ----------------

@router.post("/register/options")
def register_options(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _require_lib()
    existing = db.query(models.WebAuthnCredential).filter(models.WebAuthnCredential.user_id == current_user.id).all()
    options = webauthn.generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(current_user.id).encode(),
        user_name=current_user.username,
        user_display_name=f"{current_user.username} ({current_user.role})",
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in existing],
    )
    cid = _save_challenge(db, options.challenge, "reg", current_user.id)
    return {"challenge_id": cid, "options": json.loads(webauthn.options_to_json(options))}


@router.post("/register/verify")
def register_verify(
    payload: VerifyIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _require_lib()
    challenge = _take_challenge(db, payload.challenge_id, "reg", current_user.id)
    try:
        v = webauthn.verify_registration_response(
            credential=payload.credential,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGINS,
            require_user_verification=True,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Barmoq izini tasdiqlab bo'lmadi: {e}")

    cred_id = bytes_to_base64url(v.credential_id)
    if db.query(models.WebAuthnCredential).filter(models.WebAuthnCredential.credential_id == cred_id).first():
        raise HTTPException(status_code=400, detail="Bu qurilma allaqachon qo'shilgan.")
    db.add(models.WebAuthnCredential(
        user_id=current_user.id,
        credential_id=cred_id,
        public_key=bytes_to_base64url(v.credential_public_key),
        sign_count=v.sign_count,
        device_name=(payload.device_name or "Qurilma")[:128],
        created_at=_now_ms(),
    ))
    db.commit()
    return {"ok": True}


# ---------------- Kirish (parolsiz) ----------------

@router.post("/login/options")
def login_options(db: Session = Depends(get_db)):
    _require_lib()
    options = webauthn.generate_authentication_options(
        rp_id=RP_ID,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    cid = _save_challenge(db, options.challenge, "auth", None)
    return {"challenge_id": cid, "options": json.loads(webauthn.options_to_json(options))}


@router.post("/login/verify", response_model=schemas.LoginResponse)
def login_verify(payload: VerifyIn, db: Session = Depends(get_db)):
    _require_lib()
    challenge = _take_challenge(db, payload.challenge_id, "auth", None)
    cred_id = str(payload.credential.get("id") or payload.credential.get("rawId") or "")
    cred = db.query(models.WebAuthnCredential).filter(models.WebAuthnCredential.credential_id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=401, detail="Bu qurilma tizimda topilmadi. Parol bilan kiring va barmoq izini qaytadan yoqing.")
    try:
        v = webauthn.verify_authentication_response(
            credential=payload.credential,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGINS,
            credential_public_key=base64url_to_bytes(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Barmoq izi tasdiqlanmadi.")

    user = db.query(models.User).filter(models.User.id == cred.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Foydalanuvchi topilmadi.")
    cred.sign_count = v.new_sign_count
    cred.last_used_at = _now_ms()
    db.commit()
    token = auth.create_access_token(user.username, user.role)
    from ..audit import note as _an
    _an("Tizimga kirdi (barmoq izi / Face ID bilan)", cat="login", username=user.username)
    return schemas.LoginResponse(token=token, username=user.username, role=user.role)


# ---------------- O'z qurilmalarini boshqarish ----------------

@router.get("/credentials")
def my_credentials(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(models.WebAuthnCredential).filter(
        models.WebAuthnCredential.user_id == current_user.id
    ).order_by(models.WebAuthnCredential.id).all()
    return [{"id": r.id, "credential_id": r.credential_id, "device_name": r.device_name,
             "created_at": r.created_at, "last_used_at": r.last_used_at} for r in rows]


@router.delete("/credentials/{cred_db_id}")
def delete_credential(
    cred_db_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    cred = db.query(models.WebAuthnCredential).filter(
        models.WebAuthnCredential.id == cred_db_id,
        models.WebAuthnCredential.user_id == current_user.id,  # faqat o'zinikini
    ).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Topilmadi.")
    db.delete(cred)
    db.commit()
    return {"ok": True}
