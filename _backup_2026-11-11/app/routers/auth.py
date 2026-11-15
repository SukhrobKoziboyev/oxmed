from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Login yoki parol xato!")
    token = auth.create_access_token(user.username, user.role)
    return schemas.LoginResponse(token=token, username=user.username, role=user.role)


@router.post("/change-my-credentials")
def change_my_credentials(
    payload: schemas.ChangeMyCredentialsRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if not auth.verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Hozirgi parol noto'g'ri!")

    if not payload.new_login and not payload.new_password:
        raise HTTPException(status_code=400, detail="Kamida yangi login yoki parolni kiriting!")

    if payload.new_login:
        if len(payload.new_login) < 4:
            raise HTTPException(status_code=400, detail="Login kamida 4 ta belgidan iborat bo'lishi kerak!")
        existing = db.query(models.User).filter(
            models.User.username == payload.new_login,
            models.User.id != current_user.id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Bu login band!")
        current_user.username = payload.new_login

    if payload.new_password:
        if len(payload.new_password) < 6:
            raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak!")
        current_user.password_hash = auth.hash_password(payload.new_password)

    db.commit()
    # Login (username) o'zgargan bo'lsa, eski token endi yaroqsiz bo'ladi (JWT
    # ichida eski username qotib qolgan) - shuning uchun yangi token qaytaramiz.
    new_token = auth.create_access_token(current_user.username, current_user.role)
    return {"ok": True, "username": current_user.username, "token": new_token}


@router.post("/change-admin-credentials")
def change_admin_credentials(
    payload: schemas.ChangeAdminCredentialsRequest,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    admin = db.query(models.User).filter(models.User.role == "Administrator").first()
    if not admin:
        raise HTTPException(status_code=404, detail="Administrator topilmadi!")

    if not payload.new_login and not payload.new_password:
        raise HTTPException(status_code=400, detail="Kamida yangi login yoki parolni kiriting!")

    if payload.new_login:
        if len(payload.new_login) < 4:
            raise HTTPException(status_code=400, detail="Login kamida 4 ta belgidan iborat bo'lishi kerak!")
        if payload.new_login == "rahbar":
            raise HTTPException(status_code=400, detail="Bu loginni ishlatib bo'lmaydi!")
        existing = db.query(models.User).filter(
            models.User.username == payload.new_login,
            models.User.id != admin.id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Bu login band!")
        admin.username = payload.new_login

    if payload.new_password:
        if len(payload.new_password) < 6:
            raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak!")
        admin.password_hash = auth.hash_password(payload.new_password)

    db.commit()
    return {"ok": True}


@router.post("/recover-password")
def recover_password(payload: schemas.RecoverPasswordRequest, db: Session = Depends(get_db)):
    settings = db.query(models.Settings).first()
    if not settings or not auth.verify_password(payload.secret_password, settings.secret_password_hash):
        raise HTTPException(status_code=400, detail="Maxfiy parol noto'g'ri!")

    if len(payload.new_login) < 4:
        raise HTTPException(status_code=400, detail="Login kamida 4 ta belgidan iborat bo'lishi kerak!")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak!")

    rahbar = db.query(models.User).filter(models.User.role == "Markaz rahbari").first()
    if not rahbar:
        raise HTTPException(status_code=404, detail="Rahbar hisobi topilmadi!")

    existing = db.query(models.User).filter(
        models.User.username == payload.new_login,
        models.User.id != rahbar.id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu login band!")

    rahbar.username = payload.new_login
    rahbar.password_hash = auth.hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


@router.post("/change-secret-password")
def change_secret_password(
    payload: schemas.ChangeSecretPasswordRequest,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    settings = db.query(models.Settings).first()
    if not settings or not auth.verify_password(payload.current_secret, settings.secret_password_hash):
        raise HTTPException(status_code=400, detail="Hozirgi maxfiy parol noto'g'ri!")
    if len(payload.new_secret) < 8:
        raise HTTPException(status_code=400, detail="Maxfiy parol kamida 8 ta belgidan iborat bo'lishi kerak!")

    settings.secret_password_hash = auth.hash_password(payload.new_secret)
    db.commit()
    return {"ok": True}
