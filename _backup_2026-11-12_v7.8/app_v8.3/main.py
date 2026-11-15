import os
from fastapi import FastAPI
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine, SessionLocal
from . import models, auth
from .routers import auth as auth_router
from .routers import settings as settings_router
from .routers import subjects as subjects_router
from .routers import teachers as teachers_router
from .routers import students as students_router
from .routers import payments as payments_router
from .routers import recycle as recycle_router
from .routers import backup as backup_router
from .routers import salary as salary_router
from .routers import teacher_self as teacher_self_router
from .routers import webauthn_auth as webauthn_router

app = FastAPI(
    title="O'quv Markaz Boshqaruv Tizimi API",
    description="O'quv markaz uchun o'quvchi, to'lov, o'qituvchi va guruhlarni boshqarish backend API'si.",
    version="1.0.0",
)

cors_origins = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",")] if cors_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(settings_router.router)
app.include_router(subjects_router.router)
app.include_router(teachers_router.router)
app.include_router(students_router.router)
app.include_router(payments_router.router)
app.include_router(recycle_router.router)
app.include_router(backup_router.router)
app.include_router(salary_router.router)
app.include_router(teacher_self_router.router)
app.include_router(webauthn_router.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _run_light_migrations()
    _seed_initial_data()


def _run_light_migrations():
    """YANGI: v5 -> v6 yangilanishida eski (allaqachon ishlab turgan) bazaga
    yangi ustunlarni qo'shib qo'yadi. Base.metadata.create_all faqat yo'q
    JADVALLARNI yaratadi, mavjud jadvalga yangi USTUN qo'shmaydi - shuning
    uchun bu yerda xavfsiz (IF NOT EXISTS) ALTER TABLE buyruqlari ishlatiladi.
    Bularning barchasi idempotent - qayta ishga tushirilsa ham xato bermaydi."""
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS teacher_id INTEGER REFERENCES teachers(id) ON DELETE CASCADE",
        "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS repetitor_percent INTEGER",
        "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS school_percent INTEGER",
        "ALTER TABLE teachers ADD COLUMN IF NOT EXISTS percent_override INTEGER",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS method VARCHAR(16) NOT NULL DEFAULT 'naxt'",
        # v7.6: o'qituvchi pulni qaytarganini qayd etish uchun (eski yozuvlar 'payout' bo'lib qoladi)
        "ALTER TABLE teacher_payouts ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'payout'",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception as e:  # noqa: BLE001
                print(f"[migration] o'tkazib yuborildi ({e})")


def _seed_initial_data():
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            rahbar_username = os.getenv("INITIAL_RAHBAR_USERNAME", "rahbar")
            rahbar_password = os.getenv("INITIAL_RAHBAR_PASSWORD", "rahbar123")
            admin_username = os.getenv("INITIAL_ADMIN_USERNAME", "admin")
            admin_password = os.getenv("INITIAL_ADMIN_PASSWORD", "admin123")

            db.add(models.User(
                username=rahbar_username,
                password_hash=auth.hash_password(rahbar_password),
                role="Markaz rahbari",
            ))
            db.add(models.User(
                username=admin_username,
                password_hash=auth.hash_password(admin_password),
                role="Administrator",
            ))
            print(f"[seed] Boshlang'ich foydalanuvchilar yaratildi: {rahbar_username} / {admin_username}")

        if db.query(models.Settings).count() == 0:
            secret_password = os.getenv("INITIAL_SECRET_PASSWORD", "maxfiy2026")
            db.add(models.Settings(
                id=1,
                secret_password_hash=auth.hash_password(secret_password),
            ))
            print("[seed] Sozlamalar (maxfiy parol) yaratildi.")

        db.commit()
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}
