import os
from fastapi import FastAPI
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

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
from .routers import staff as staff_router
from .routers import dues as dues_router
from .routers import push as push_router
from .routers import sms as sms_router
from .routers import expenses as expenses_router

app = FastAPI(
    title="O'quv Markaz Boshqaruv Tizimi API",
    description="O'quv markaz uchun o'quvchi, to'lov, o'qituvchi va guruhlarni boshqarish backend API'si.",
    version="1.0.0",
    # v8.8: API hujjatlari (/docs) tashqariga ochiq bo'lmasin
    docs_url="/api/docs" if os.getenv("ENABLE_DOCS") == "1" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if os.getenv("ENABLE_DOCS") == "1" else None,
)

# v8.8: boshqa saytlar API'ga brauzer orqali murojaat qila olmasin (o'z sayti — bir xil manba, CORS kerak emas)
cors_origins = os.getenv("CORS_ORIGINS", "https://oxmed.uz,https://www.oxmed.uz")
origins = [o.strip() for o in cors_origins.split(",")] if cors_origins != "*" else ["*"]

# v8.7: API javoblarini siqib yuborish (telefon internetida 5-8 marta tezroq)
app.add_middleware(GZipMiddleware, minimum_size=800)
# v8.8: xavfsizlik (< > taqiqi, sarlavhalar)
from .security import SecurityMiddleware  # noqa: E402
app.add_middleware(SecurityMiddleware)

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
app.include_router(staff_router.router)
app.include_router(dues_router.router)
app.include_router(push_router.router)
app.include_router(sms_router.router)
app.include_router(expenses_router.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _run_light_migrations()
    _seed_initial_data()
    # v9.1: yangi versiya yuklansa — hammaga avtomatik bildirishnoma
    from .routers.push import start_update_watcher
    start_update_watcher()


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
        # v8.4: xodimlar (o'quvchisi yo'q hodimlar) va ularning oyligi
        "ALTER TABLE teachers ALTER COLUMN subject_id DROP NOT NULL",
        "ALTER TABLE teachers ADD COLUMN IF NOT EXISTS is_staff BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE teachers ADD COLUMN IF NOT EXISTS position VARCHAR(128)",
        "ALTER TABLE teachers ADD COLUMN IF NOT EXISTS monthly_salary BIGINT",
        "ALTER TABLE teachers ADD COLUMN IF NOT EXISTS salary_start VARCHAR(7)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_salary_accrual_month ON salary_accruals (teacher_id, period) WHERE kind = 'monthly'",
        # v8.5: o'quvchi qarzi - har o'quvchi+oy uchun bitta yozuv
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_student_due_month ON student_dues (student_id, month)",
        # v8.6: o'quvchining qo'shimcha telefon raqami
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS phone2 VARCHAR(32)",
        # v8.9: SMS (Eskiz.uz) sozlamalari
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sms_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sms_to_parent BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sms_to_rahbar BOOLEAN NOT NULL DEFAULT TRUE",
        # v9.0: ommaviy SMS
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sms_template_reminder TEXT",
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sms_template_overdue TEXT",
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sms_template_announce TEXT",
        # v9.7: eski standart SMS matnlarini Eskiz'da tasdiqlanadigan yangisiga almashtirish (qo'lda o'zgartirilganlariga tegmaydi)
        "UPDATE settings SET sms_template_parent = $t${ism} {familiya}, {oy} oyi uchun {summa} so'm to'lov qabul qilindi. Sana: {sana}. Rahmat! OLMOS XATAMOV maktabi$t$ WHERE sms_template_parent = $o${ism} {familiya}, {oy} oyi uchun {summa} so'm to'lov qabul qilindi. To'lov sanasi: {sana}. Rahmat! - O'quv Markaz$o$",
        "UPDATE settings SET sms_template_rahbar = $t$Yangi to'lov: {ism} {familiya}, {summa} so'm, {oy} oyi. {sana} {vaqt}. OLMOS XATAMOV maktabi$t$ WHERE sms_template_rahbar = $o$To'lov qabul qilindi: {ism} {familiya}, {fan}/{sinf}, {summa} so'm, {oy} oyi. Sana: {sana} {vaqt}$o$",
        "ALTER TABLE sms_logs ADD COLUMN IF NOT EXISTS batch_id INTEGER",
        "ALTER TABLE sms_logs ADD COLUMN IF NOT EXISTS student_id INTEGER",
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
