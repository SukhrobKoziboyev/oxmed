from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..security import login_limiter, secret_limiter, client_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Bitta IP'dan ko'p loginlarga urinish (20 xatodan keyin blok)
from ..security import AttemptLimiter  # noqa: E402
ip_limiter = AttemptLimiter(free=20)
_DUMMY_HASH = auth.hash_password("oxmed-dummy-password")


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    # v8.8: parol terib ko'rish hujumidan himoya (5 xatodan keyin vaqtincha blok)
    ip = client_ip(request)
    k_user = "login:u:" + (payload.username or "").strip().lower()[:64]
    k_ip = ("login:ip:" + ip) if ip else None
    login_limiter.check(k_user)
    if k_ip:
        ip_limiter.check(k_ip)
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user:
        auth.verify_password(payload.password or "x", _DUMMY_HASH)  # vaqt bo'yicha farq bilinmasin
    if not user or not auth.verify_password(payload.password, user.password_hash):
        login_limiter.fail(k_user)
        if k_ip:
            ip_limiter.fail(k_ip)
        raise HTTPException(status_code=401, detail="Login yoki parol xato!")
    login_limiter.success(k_user)
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
def recover_password(payload: schemas.RecoverPasswordRequest, request: Request, db: Session = Depends(get_db)):
    # v8.8: maxfiy parolni terib topishdan himoya — 3 xatodan keyin 5 daqiqa+ blok (hamma uchun)
    secret_limiter.check("recover:all")
    settings = db.query(models.Settings).first()
    if not settings or not auth.verify_password(payload.secret_password, settings.secret_password_hash):
        secret_limiter.fail("recover:all")
        raise HTTPException(status_code=400, detail="Maxfiy parol noto'g'ri!")
    secret_limiter.success("recover:all")

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
    secret_limiter.check("change-secret")
    settings = db.query(models.Settings).first()
    if not settings or not auth.verify_password(payload.current_secret, settings.secret_password_hash):
        secret_limiter.fail("change-secret")
        raise HTTPException(status_code=400, detail="Hozirgi maxfiy parol noto'g'ri!")
    secret_limiter.success("change-secret")
    if len(payload.new_secret) < 8:
        raise HTTPException(status_code=400, detail="Maxfiy parol kamida 8 ta belgidan iborat bo'lishi kerak!")

    settings.secret_password_hash = auth.hash_password(payload.new_secret)
    db.commit()
    return {"ok": True}



# ============================================================
# v7.7: O'qituvchi rahbar bergan kod bilan yangi parol o'rnatadi
# ============================================================

class ResetWithCodeIn(BaseModel):
    username: str
    code: str
    new_password: str


@router.post("/reset-with-code")
def reset_with_code(payload: ResetWithCodeIn, request: Request, db: Session = Depends(get_db)):
    import time
    ip = client_ip(request)
    k_ip = ("reset:ip:" + ip) if ip else None
    if k_ip:
        login_limiter.check(k_ip)
    generic = HTTPException(status_code=400, detail="Login yoki kod noto'g'ri, yoki kod muddati o'tgan. Rahbardan yangi kod so'rang.")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak!")
    code = (payload.code or "").strip().replace(" ", "")
    user = db.query(models.User).filter(models.User.username == payload.username.strip()).first()
    if not user or user.role != "O'qituvchi" or not code.isdigit() or len(code) != 6:
        raise generic
    now = int(time.time() * 1000)
    rc = db.query(models.PasswordResetCode).filter(
        models.PasswordResetCode.user_id == user.id,
        models.PasswordResetCode.used == False,  # noqa: E712
        models.PasswordResetCode.expires_at > now,
    ).order_by(models.PasswordResetCode.id.desc()).first()
    if not rc:
        raise generic
    if not auth.verify_password(code, rc.code_hash):
        if k_ip:
            login_limiter.fail(k_ip)
        rc.attempts += 1
        if rc.attempts >= 5:  # 5 marta xato -> kod butunlay bekor
            rc.used = True
        db.commit()
        raise generic
    rc.used = True
    user.password_hash = auth.hash_password(payload.new_password)
    db.commit()
    return {"ok": True, "username": user.username}
