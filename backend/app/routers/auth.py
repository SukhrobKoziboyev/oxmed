from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..security import login_limiter, secret_limiter, client_ip

from ..audit import note as audit_note
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
        # v13.15: oxirgi amallar — noto'g'ri parol bilan kirishga urinish (parol yozilmaydi)
        audit_note(f"⚠️ Noto'g'ri parol bilan kirishga urinish — login \"{(payload.username or '')[:40]}\"" + ("" if user else " (bunday login yo'q)"),
                   cat="login", username=(payload.username or "")[:64] if user else None, force=True)
        login_limiter.fail(k_user)
        if k_ip:
            ip_limiter.fail(k_ip)
        raise HTTPException(status_code=401, detail="Login yoki parol xato!")
    login_limiter.success(k_user)
    if not getattr(user, "password_enc", None):
        # v12.8: eski foydalanuvchilar — parol to'g'ri kiritilganda shifrlangan nusxasi saqlanadi
        user.password_enc = auth.encrypt_pw(payload.password)
        db.commit()
    token = auth.create_access_token(user.username, user.role)
    audit_note("Tizimga kirdi (login va parol bilan)", cat="login", username=user.username)
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
        auth.set_password(current_user, payload.new_password)

    audit_note("O'z login / parolini o'zgartirdi" + (f" (yangi login \"{payload.new_login}\")" if payload.new_login else ""), cat="login", username=current_user.username)
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
        auth.set_password(admin, payload.new_password)

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
    auth.set_password(rahbar, payload.new_password)
    audit_note(f"⚠️ Rahbar login/paroli maxfiy parol orqali tiklandi — yangi login \"{payload.new_login}\"", cat="login", username=payload.new_login, force=True)
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
# v12.8: LOGIN VA PAROLNI KO'RISH • YO'QLAMACHI • XODIMLAR PAROLLARI
# ("Tiklash kodi" olib tashlandi — xodim parolini unutsa, rahbardan so'raydi)
# ============================================================

ROLE_LABEL = {"Markaz rahbari": "Rahbar", "Administrator": "Administrator",
              "O'qituvchi": "O'qituvchi", auth.ROLE_ATT: "Yo'qlamachi"}


@router.get("/my-credentials")
def my_credentials(current_user: models.User = Depends(auth.get_current_user)):
    return {"username": current_user.username, "role": current_user.role,
            "password": auth.decrypt_pw(getattr(current_user, "password_enc", None))}


def _user_row(db: Session, u: models.User) -> dict:
    name, sub, kind = ROLE_LABEL.get(u.role, u.role), "", "other"
    if u.role == "Administrator":
        kind = "admin"
    elif u.role == auth.ROLE_ATT:
        kind = "att"
    elif u.teacher_id:
        t = db.query(models.Teacher).filter(models.Teacher.id == u.teacher_id).first()
        if t:
            name = t.name
            if getattr(t, "is_staff", False):
                kind, sub = "staff", (t.position or "Xodim")
            else:
                kind, sub = "teacher", ((t.subject.name + " o'qituvchisi") if t.subject else "O'qituvchi")
    return {"id": u.id, "username": u.username, "role": u.role, "kind": kind, "name": name, "sub": sub,
            "teacher_id": u.teacher_id, "password": auth.decrypt_pw(getattr(u, "password_enc", None))}


@router.get("/staff-credentials")
def staff_credentials(current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    users = db.query(models.User).filter(models.User.role != "Markaz rahbari").all()
    order = {"admin": 0, "att": 1, "teacher": 2, "staff": 3, "other": 4}
    rows = sorted((_user_row(db, u) for u in users), key=lambda r: (order.get(r["kind"], 9), r["name"].lower()))
    return {"users": rows}


class UserCredIn(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None


def _check_login(db: Session, username: str, self_id: Optional[int]):
    if len(username) < 4:
        raise HTTPException(status_code=400, detail="Login kamida 4 ta belgidan iborat bo'lishi kerak!")
    q = db.query(models.User).filter(models.User.username == username)
    if self_id:
        q = q.filter(models.User.id != self_id)
    if q.first():
        raise HTTPException(status_code=400, detail="Bu login band!")


def _check_pw(pw: str):
    if len(pw) < 6:
        raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak!")


@router.put("/users/{user_id}/credentials")
def set_user_credentials(user_id: int, payload: UserCredIn,
                         current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    """Rahbar istalgan xodimning (admin, yo'qlamachi, o'qituvchi, xodim) login/parolini o'zgartiradi."""
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u or u.role == "Markaz rahbari":
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi!")
    new_login = (payload.username or "").strip()
    if not new_login and not payload.password:
        raise HTTPException(status_code=400, detail="Kamida yangi login yoki parolni kiriting!")
    _old = u.username
    if new_login and new_login != u.username:
        _check_login(db, new_login, u.id)
        u.username = new_login
    if payload.password:
        _check_pw(payload.password)
        auth.set_password(u, payload.password)
    from ..student_links import who_label
    audit_note(f"Xodimning kirish ma'lumotini o'zgartirdi: {who_label(db, u.username)} — "
               + ", ".join(x for x in ((f"login \"{_old}\" → \"{u.username}\"" if _old != u.username else ""), ("parol yangilandi" if payload.password else "")) if x),
               cat="login", entity="user", entity_id=u.id)
    db.commit()
    return _user_row(db, u)


@router.get("/att-user")
def get_att_user(current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    u = db.query(models.User).filter(models.User.role == auth.ROLE_ATT).first()
    if not u:
        return {"exists": False}
    return {"exists": True, "id": u.id, "username": u.username, "password": auth.decrypt_pw(u.password_enc)}


@router.post("/att-user")
def set_att_user(payload: UserCredIn, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    """Yo'qlamachi login/paroli: bo'lmasa yaratiladi (ikkalasi majburiy), bo'lsa o'zgartiriladi."""
    u = db.query(models.User).filter(models.User.role == auth.ROLE_ATT).first()
    new_login = (payload.username or "").strip()
    if not u:
        if not new_login or not payload.password:
            raise HTTPException(status_code=400, detail="Login va parolni kiriting!")
        _check_login(db, new_login, None)
        _check_pw(payload.password)
        u = models.User(username=new_login, role=auth.ROLE_ATT)
        auth.set_password(u, payload.password)
        db.add(u)
    else:
        if not new_login and not payload.password:
            raise HTTPException(status_code=400, detail="Kamida yangi login yoki parolni kiriting!")
        if new_login and new_login != u.username:
            _check_login(db, new_login, u.id)
            u.username = new_login
        if payload.password:
            _check_pw(payload.password)
            auth.set_password(u, payload.password)
    db.commit()
    return {"exists": True, "id": u.id, "username": u.username, "password": auth.decrypt_pw(u.password_enc)}


@router.delete("/att-user")
def delete_att_user(current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    u = db.query(models.User).filter(models.User.role == auth.ROLE_ATT).first()
    if not u:
        raise HTTPException(status_code=404, detail="Yo'qlamachi logini yo'q!")
    try:
        db.query(models.WebAuthnCredential).filter(models.WebAuthnCredential.user_id == u.id).delete()
    except Exception:  # noqa: BLE001
        pass
    db.delete(u)
    db.commit()
    return {"ok": True}
