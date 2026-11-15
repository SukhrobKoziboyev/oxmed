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


def require_teacher(current_user: models.User = Depends(get_current_user)) -> models.User:
    """YANGI: O'qituvchining shaxsiy kabineti uchun - faqat 'O'qituvchi'
    roli bilan kirgan va teacher_id biriktirilgan foydalanuvchilarga ruxsat."""
    if current_user.role != "O'qituvchi" or not current_user.teacher_id:
        raise HTTPException(status_code=403, detail="Faqat o'qituvchilar uchun!")
    return current_user
