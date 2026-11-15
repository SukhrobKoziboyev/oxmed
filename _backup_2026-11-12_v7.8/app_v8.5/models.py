import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, BigInteger, JSON, Text
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    # 'Markaz rahbari' yoki 'Administrator' yoki 'O'qituvchi'
    role = Column(String(32), nullable=False)
    # YANGI: agar role == "O'qituvchi" bo'lsa, shu foydalanuvchi qaysi
    # Teacher yozuviga tegishli ekanini bildiradi (o'qituvchi shaxsiy kabinetiga
    # kirishi uchun). O'qituvchi o'chirilsa, uning login'i ham o'chadi (CASCADE).
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=True)


class Settings(Base):
    """Yagona qator (id=1) - tizim sozlamalari."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, default=1)
    secret_password_hash = Column(String(255), nullable=False)
    sms_template_parent = Column(Text, nullable=False, default=(
        "{ism} {familiya}, {oy} oyi uchun {summa} so'm to'lov qabul qilindi. "
        "To'lov sanasi: {sana}. Rahmat! - O'quv Markaz"
    ))
    sms_template_rahbar = Column(Text, nullable=False, default=(
        "To'lov qabul qilindi: {ism} {familiya}, {fan}/{sinf}, {summa} so'm, {oy} oyi. "
        "Sana: {sana} {vaqt}"
    ))


class RahbarPhone(Base):
    __tablename__ = "rahbar_phones"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(32), nullable=False)


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)

    # YANGI: "Hodimlar oyligi" bo'limi uchun - ulush foizlari.
    # repetitor_percent: shu fandagi repetitor to'lovlaridan o'qituvchiga
    #   avtomatik ajratiladigan standart foiz (masalan 60 -> 60% o'qituvchiga,
    #   40% markazga). Har bir o'qituvchi uchun Teacher.percent_override bilan
    #   bekor qilinishi (o'zgartirilishi) mumkin.
    # school_percent: maktab o'quvchisi to'lovi kelganda, shu fan
    #   o'qituvchisiga to'lov summasidan avtomatik ajratiladigan foiz
    #   (masalan 2,200,000 so'mdan matematikaga 18% -> 396,000 so'm taklif qilinadi).
    repetitor_percent = Column(Integer, nullable=True)
    school_percent = Column(Integer, nullable=True)

    teachers = relationship("Teacher", back_populates="subject", cascade="all, delete-orphan")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    # v8.4: xodimlarda (farrosh, oshpaz, ...) fan bo'lmaydi -> NULL
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(128), nullable=False)

    # v8.4: o'quvchisi yo'q xodimlar (farrosh, oshpaz, direktor o'rinbosari, ...).
    # Ular ham shu jadvalda turadi - login, kabinet, oylik berish, hisob varag'i
    # o'qituvchilarniki bilan bir xil ishlaydi. Faqat ulush o'rniga har oy
    # belgilangan oylik avtomatik "hisoblanadi" (SalaryAccrual).
    is_staff = Column(Boolean, nullable=False, default=False)
    position = Column(String(128), nullable=True)          # lavozim
    monthly_salary = Column(BigInteger, nullable=True)     # oylik maosh (so'm)
    salary_start = Column(String(7), nullable=True)        # 'YYYY-MM' - qaysi oydan hisoblanadi

    # YANGI: shu o'qituvchiga xos maxsus foiz (agar rahbar bilan kelishuv fan
    # bo'yicha standart foizdan farq qilsa). Bo'sh bo'lsa, Subject.repetitor_percent
    # ishlatiladi.
    percent_override = Column(Integer, nullable=True)

    subject = relationship("Subject", back_populates="teachers")
    groups = relationship("Group", back_populates="teacher", cascade="all, delete-orphan")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    # 'toq' | 'juft' | 'harkuni'
    day_type = Column(String(16), nullable=False)
    start_time = Column(String(8), nullable=False)  # "08:00"
    end_time = Column(String(8), nullable=False)    # "10:00"

    teacher = relationship("Teacher", back_populates="groups")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(128), nullable=False)
    last_name = Column(String(128), nullable=False)
    phone = Column(String(32), nullable=False)
    # 'school' | 'repetitor'
    type = Column(String(16), nullable=False)

    # Maktab o'quvchisi uchun
    class_name = Column(String(16), nullable=True)

    # Repetitor o'quvchisi uchun - snapshot matn ko'rinishida saqlanadi
    # (o'qituvchi/guruh keyinchalik o'zgartirilsa ham eski yozuv o'zgarmay qoladi,
    #  bu frontend'dagi filtrlash mantiqi bilan bir xil ishlaydi)
    subject_name = Column(String(128), nullable=True)
    teacher_name = Column(String(128), nullable=True)
    group_label = Column(String(255), nullable=True)

    added_by = Column(String(64), nullable=False)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True)

    # Snapshotlar - o'quvchi keyinchalik o'zgartirilsa/o'chirilsa ham to'lov tarixi buzilmasin
    student_name = Column(String(255), nullable=False)
    student_phone = Column(String(32), nullable=False)
    student_type = Column(String(16), nullable=False)
    subject_name = Column(String(128), nullable=True)
    teacher_name = Column(String(128), nullable=True)
    group_label = Column(String(255), nullable=True)
    class_name = Column(String(16), nullable=True)

    month = Column(String(16), nullable=False)
    amount = Column(BigInteger, nullable=False)

    # YANGI: to'lov usuli - 'naxt' (naqd) yoki 'click' (Click/plastik)
    method = Column(String(16), nullable=False, default="naxt")

    date_str = Column(String(64), nullable=False)
    timestamp = Column(BigInteger, nullable=False)

    added_by = Column(String(64), nullable=False)
    edited_by = Column(String(64), nullable=True)
    edited_at = Column(String(64), nullable=True)

    allocations = relationship(
        "PaymentAllocation", back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentAllocation(Base):
    """YANGI: 'Hodimlar oyligi' bo'limi uchun - bitta to'lovning qaysi qismi
    qaysi o'qituvchiga (qaysi fan bo'yicha) ajratilganini saqlaydi.
    Masalan repetitordan 500,000 so'm tushsa va foiz 60% bo'lsa, shu yerga
    {teacher: Vali, subject: Matematika, amount: 300000} yozuvi qo'shiladi.
    Maktab to'lovi bir nechta fanga bo'linsa, bir nechta qator yoziladi.
    Qolgan qism (to'lov - barcha ajratmalar yig'indisi) avtomatik markaz
    sof foydasi hisoblanadi (alohida saqlanmaydi, hisoblab chiqiladi)."""

    __tablename__ = "payment_allocations"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)
    # O'qituvchi o'chirilsa ham tarix buzilmasin uchun SET NULL (ism snapshot saqlanadi)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    teacher_name = Column(String(128), nullable=False)
    subject_name = Column(String(128), nullable=True)
    amount = Column(BigInteger, nullable=False)

    payment = relationship("Payment", back_populates="allocations")


class TeacherPayout(Base):
    """YANGI: rahbar/admin tomonidan o'qituvchiga berilgan oylik/avans
    to'lovlarini qayd etadi. Bu summalar o'qituvchining "hozir olishi kerak
    bo'lgan summa"sidan (jami ajratilgan ulush - jami berilgan to'lovlar)
    ayiriladi."""

    __tablename__ = "teacher_payouts"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    teacher_name = Column(String(128), nullable=False)
    amount = Column(BigInteger, nullable=False)  # doim musbat son
    note = Column(String(255), nullable=True)
    date_str = Column(String(64), nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    paid_by = Column(String(64), nullable=False)
    # v7.6: yozuv turi
    #   'payout' - markaz o'qituvchiga pul berdi (oylik/avans)  -> balansdan AYIRILADI
    #   'return' - o'qituvchi olgan pulini markazga qaytardi     -> balansga QO'SHILADI
    # Balans (o'qituvchi hozir olishi kerak) = ulushlar - berilganlar + qaytarilganlar
    kind = Column(String(16), nullable=False, default="payout")


class StudentDue(Base):
    """v8.5: o'quvchining oy uchun to'lashi KERAK bo'lgan summasi (qarzni hisoblash uchun).
    Qarz = due_amount - shu oy uchun haqiqatda to'langan summa (manfiy bo'lmaydi).
    Shuning uchun o'quvchi qolganini to'lasa, qarz O'ZI kamayadi.
    Har o'quvchi+oy uchun bitta qator (unique index). Qarz 0 bo'lsa qator o'chiriladi."""
    __tablename__ = "student_dues"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    month = Column(String(16), nullable=False)
    due_amount = Column(BigInteger, nullable=False)
    note = Column(String(255), nullable=True)
    updated_by = Column(String(64), nullable=False)
    updated_at = Column(String(64), nullable=False)


class SalaryAccrual(Base):
    """v8.4: xodimga hisoblangan oylik (balansga QO'SHILADI).
    kind='monthly' - har oy avtomatik (period='YYYY-MM', har oyga bittadan);
    kind='extra'   - rahbar qo'lda qo'shgan (bonus / qo'shimcha ish).
    Oylik bekor qilinsa qator o'chirilmaydi, amount=0 qilinadi (qayta yaratilmasligi uchun)."""
    __tablename__ = "salary_accruals"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)
    teacher_name = Column(String(128), nullable=False)
    kind = Column(String(16), nullable=False, default="monthly")
    period = Column(String(7), nullable=True)
    amount = Column(BigInteger, nullable=False)
    note = Column(String(255), nullable=True)
    date_str = Column(String(64), nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    created_by = Column(String(64), nullable=False)


class RecycleBinItem(Base):
    __tablename__ = "recycle_bin"

    id = Column(Integer, primary_key=True, index=True)
    # 'student' | 'payment' | 'allData'
    type = Column(String(16), nullable=False)
    data = Column(JSON, nullable=False)
    deleted_at = Column(BigInteger, nullable=False)  # ms since epoch, frontend bilan mos
    deleted_by = Column(String(64), nullable=False)


class WebAuthnCredential(Base):
    """v7.7: Barmoq izi / Face ID bilan kirish (WebAuthn "passkey").
    Telefonning o'zida maxfiy kalit saqlanadi, serverda faqat OCHIQ kalit turadi -
    shuning uchun bu yozuv o'g'irlansa ham, u bilan tizimga kirib bo'lmaydi."""
    __tablename__ = "webauthn_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id = Column(String(512), unique=True, nullable=False, index=True)  # base64url
    public_key = Column(Text, nullable=False)  # base64url
    sign_count = Column(BigInteger, nullable=False, default=0)
    device_name = Column(String(128), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    last_used_at = Column(BigInteger, nullable=True)


class AuthChallenge(Base):
    """v7.7: WebAuthn uchun bir martalik tasodifiy "savol" (5 daqiqa amal qiladi)."""
    __tablename__ = "auth_challenges"

    id = Column(Integer, primary_key=True, index=True)
    challenge = Column(String(256), nullable=False)  # base64url
    kind = Column(String(16), nullable=False)  # 'reg' | 'auth'
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    expires_at = Column(BigInteger, nullable=False)
    used = Column(Boolean, nullable=False, default=False)


class PasswordResetCode(Base):
    """v7.7: O'qituvchi parolini tiklash kodi. Kodni FAQAT rahbar yaratadi va
    o'qituvchiga o'zi aytadi. 6 xonali, 30 daqiqa, bir marta ishlaydi,
    5 marta noto'g'ri kiritilsa bekor bo'ladi. Bazada kodning o'zi emas, xeshi saqlanadi."""
    __tablename__ = "password_reset_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(BigInteger, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    used = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(64), nullable=False)
    created_at = Column(BigInteger, nullable=False)
