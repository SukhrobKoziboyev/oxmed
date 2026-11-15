import os
import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from . import models

_DEFAULT_SECRET = "insecure-dev-secret-change-me"


def _load_jwt_secret() -> str:
    """v8.8: .env da JWT_SECRET bo'lmasa (yoki standart qiymat bo'lsa) — hamma biladigan
    kalit bilan soxta token yasash mumkin edi. Endi serverda tasodifiy kalit bir marta
    yaratilib, backend/jwt_secret.key faylida saqlanadi."""
    env = os.getenv("JWT_SECRET")
    if env and env != _DEFAULT_SECRET and len(env) >= 16:
        return env
    import secrets
    from pathlib import Path
    path = Path(os.getenv("JWT_SECRET_FILE", str(Path(__file__).resolve().parents[1] / "jwt_secret.key")))
    try:
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_text(secrets.token_urlsafe(48))
            os.chmod(tmp, 0o600)
            try:
                os.link(tmp, path)
            except FileExistsError:
                pass
            finally:
                tmp.unlink(missing_ok=True)
        val = path.read_text().strip()
        if len(val) >= 32:
            return val
    except OSError:
        pass
    return secrets.token_urlsafe(48)  # fayl yozib bo'lmasa ham standart kalit ishlatilmaydi


JWT_SECRET = _load_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "12"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


# ---------- v12.8: parolning shifrlangan nusxasi (rahbar ko'rishi uchun) ----------
def _load_pw_key() -> bytes:
    import base64, secrets
    from pathlib import Path
    path = Path(os.getenv("PW_SECRET_FILE", str(Path(__file__).resolve().parents[1] / "pw_secret.key")))
    try:
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_text(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
            os.chmod(tmp, 0o600)
            try:
                os.link(tmp, path)
            except FileExistsError:
                pass
            finally:
                tmp.unlink(missing_ok=True)
        key = base64.urlsafe_b64decode(path.read_text().strip())
        if len(key) == 32:
            return key
    except (OSError, ValueError):
        pass
    return b""


_PW_KEY = _load_pw_key()


def encrypt_pw(password: str) -> Optional[str]:
    if not _PW_KEY or not password:
        return None
    import base64, secrets
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_PW_KEY).encrypt(nonce, password.encode("utf-8"), b"oxmed-pw")
    return "v1:" + base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt_pw(token: Optional[str]) -> Optional[str]:
    if not token or not _PW_KEY or not token.startswith("v1:"):
        return None
    try:
        import base64
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = base64.urlsafe_b64decode(token[3:])
        return AESGCM(_PW_KEY).decrypt(raw[:12], raw[12:], b"oxmed-pw").decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def set_password(user, password: str) -> None:
    """Parolni o'rnatish — xesh (kirish uchun) + shifrlangan nusxa (rahbar ko'rishi uchun)."""
    user.password_hash = hash_password(password)
    user.password_enc = encrypt_pw(password)


def create_access_token(username: str, role: str) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token yaroqsiz yoki muddati tugagan. Qaytadan tizimga kiring.",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    payload = decode_access_token(credentials.credentials)
    username: Optional[str] = payload.get("sub")
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Foydalanuvchi topilmadi.")
    return user


def require_rahbar(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != "Markaz rahbari":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faqat Markaz rahbari bu amalni bajara oladi!",
        )
    return current_user


def require_staff(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Rahbar YOKI Administrator - 'Hodimlar oyligi' kabi ikkalasi ham
    ko'ra oladigan (lekin faqat rahbar o'zgartira oladigan) joylarda ishlatiladi."""
    if current_user.role not in ("Markaz rahbari", "Administrator"):
        raise HTTPException(status_code=403, detail="Sizda ruxsat yo'q!")
    return current_user


ROLE_ATT = "Yo'qlamachi"


def require_attendance(current_user: models.User = Depends(get_current_user)) -> models.User:
    """v12.8: maktab yo'qlamasi — rahbar, admin yoki faqat yo'qlama bilan shug'ullanuvchi xodim."""
    if current_user.role not in ("Markaz rahbari", "Administrator", ROLE_ATT):
        raise HTTPException(status_code=403, detail="Sizda ruxsat yo'q!")
    return current_user


def require_expense_user(current_user: models.User = Depends(get_current_user),
                         db: Session = Depends(get_db)) -> models.User:
    """v13.12: xarajatlar — rahbar, admin YOKI rahbar ruxsat bergan xodim (masalan bozorchi)."""
    if current_user.role in ("Markaz rahbari", "Administrator"):
        return current_user
    if current_user.role == "O'qituvchi" and current_user.teacher_id:
        t = db.query(models.Teacher).filter(models.Teacher.id == current_user.teacher_id).first()
        if t and t.is_staff and t.can_expenses:
            return current_user
    raise HTTPException(status_code=403, detail="Sizda ruxsat yo'q!")


def require_teacher(current_user: models.User = Depends(get_current_user)) -> models.User:
    """YANGI: O'qituvchining shaxsiy kabineti uchun - faqat 'O'qituvchi'
    roli bilan kirgan va teacher_id biriktirilgan foydalanuvchilarga ruxsat."""
    if current_user.role != "O'qituvchi" or not current_user.teacher_id:
        raise HTTPException(status_code=403, detail="Faqat o'qituvchilar uchun!")
    return current_user
