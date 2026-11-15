import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, BigInteger, JSON, Text, UniqueConstraint
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
    # v12.8: rahbar xodimlar parolini ko'ra olishi uchun — server kaliti bilan shifrlangan nusxa (AES-GCM)
    password_enc = Column(Text, nullable=True)
    last_seen = Column(BigInteger, nullable=True)   # v13.0: chat — "onlayn" / "oxirgi marta"
    avatar_data = Column(Text, nullable=True)       # v13.3: profil rasmi (kichik JPEG, data URL)
    avatar_v = Column(BigInteger, nullable=True)    # v13.3: rasm versiyasi (kesh uchun)


class Settings(Base):
    """Yagona qator (id=1) - tizim sozlamalari."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, default=1)
    secret_password_hash = Column(String(255), nullable=False)
    att_deadline = Column(String(5), nullable=True)   # v12.6: maktab o'quvchilari kelish vaqti (HH:MM)
    sms_template_parent = Column(Text, nullable=False, default=(  # v9.7: Eskiz'da tasdiqlanadigan matn
        "{ism} {familiya}, {oy} oyi uchun {summa} so'm to'lov qabul qilindi. Sana: {sana}. Rahmat! OLMOS XATAMOV maktabi"
    ))
    sms_template_rahbar = Column(Text, nullable=False, default=(
        "Yangi to'lov: {ism} {familiya}, {summa} so'm, {oy} oyi. {sana} {vaqt}. OLMOS XATAMOV maktabi"
    ))
    # v8.9: SMS (Eskiz.uz) yoqilganmi
    sms_enabled = Column(Boolean, nullable=False, default=False)
    sms_to_parent = Column(Boolean, nullable=False, default=True)
    sms_to_rahbar = Column(Boolean, nullable=False, default=True)
    sms_to_staff = Column(Boolean, nullable=False, default=True)  # v11.16: oylik/avans SMS'i xodimga
    # v9.0: ommaviy SMS shablonlari (bo'sh bo'lsa — standart matn)
    sms_template_reminder = Column(Text, nullable=True)
    sms_template_overdue = Column(Text, nullable=True)
    sms_template_announce = Column(Text, nullable=True)


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
    # v11.16: telefon raqami — oylik/avans berilganda SMS boradi
    phone = Column(String(32), nullable=True)

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
    # v8.6: ixtiyoriy qo'shimcha telefon raqami (masalan otasi / onasi)
    phone2 = Column(String(32), nullable=True)
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
    # v12.5: ARXIV — markazdan ketgan o'quvchi o'chirilmaydi, to'lovlari va tarixi saqlanadi
    archived_at = Column(BigInteger, nullable=True)       # ms; NULL = faol o'quvchi
    archived_by = Column(String(64), nullable=True)
    archive_reason = Column(String(200), nullable=True)
    returned_at = Column(BigInteger, nullable=True)       # oxirgi marta arxivdan qaytgan vaqt (ms)


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

    # to'lov usuli - 'naxt' (naqd), 'click' (Click) yoki 'terminal' (v13.9: plastik karta terminali)
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
    # v11.16: 'avans' | 'oylik' (faqat kind='payout' uchun) va qaysi oy uchun berilgani
    ptype = Column(String(16), nullable=True)
    month = Column(String(16), nullable=True)


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


class PushSubscription(Base):
    """v8.7: Brauzer/telefon push-obunasi (Web Push). Yangi versiya chiqqanda
    ilova yopiq bo'lsa ham bildirishnoma va ilova belgisida "1" chiqishi uchun."""
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class SmsLog(Base):
    """v8.9: Yuborilgan SMS'lar jurnali (Eskiz.uz)."""
    __tablename__ = "sms_logs"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, nullable=True, index=True)
    kind = Column(String(16), nullable=False)          # parent | rahbar | test
    phone = Column(String(32), nullable=False)
    text = Column(Text, nullable=False)
    status = Column(String(16), nullable=False)        # sent | failed | skipped
    provider_id = Column(String(64), nullable=True)
    error = Column(String(500), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    created_by = Column(String(64), nullable=True)
    batch_id = Column(Integer, nullable=True, index=True)    # v9.0: ommaviy yuborish
    student_id = Column(Integer, nullable=True)


class SmsBatch(Base):
    """v9.0: Ommaviy SMS (qarzdorlarga eslatma / e'lon) — bitta tugma bilan yuborilgan to'plam."""
    __tablename__ = "sms_batches"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(16), nullable=False)          # reminder | overdue | announce
    month = Column(String(16), nullable=True)
    template = Column(Text, nullable=False)
    total = Column(Integer, nullable=False, default=0)
    sent = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    skipped = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="running")  # running | done
    created_by = Column(String(64), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    finished_at = Column(BigInteger, nullable=True)


class Expense(Base):
    """v9.8: MARKAZ XARAJATLARI (non, kartrij, ta'mir...). Admin/rahbar kiritadi.
    Kassadagi sof summa = tushum - (o'qituvchilarga berilgan - qaytarilgan) - xarajatlar.
    O'chirilgan yozuv bazada qoladi (deleted_at), hisobga kirmaydi."""

    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)          # nima uchun: "Non"
    quantity = Column(String(40), nullable=True)         # "2 ta", "5 kg" (ixtiyoriy)
    amount = Column(BigInteger, nullable=False)          # jami summa (musbat)
    category = Column(String(40), nullable=False, default="Boshqa")
    note = Column(String(255), nullable=True)
    month = Column(String(16), nullable=False, index=True)   # "Noyabr" (to'lovlar kabi)
    timestamp = Column(BigInteger, nullable=False, index=True)  # xarajat qilingan vaqt (ms)
    created_at = Column(BigInteger, nullable=False)
    added_by = Column(String(64), nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(BigInteger, nullable=True)
    deleted_at = Column(BigInteger, nullable=True, index=True)
    deleted_by = Column(String(64), nullable=True)


class BtColumn(Base):
    """v10.3: Umumiy jadvalga boshliq o'zi qo'shadigan ustun (masalan "Abet puli").
    Faqat ma'lumot uchun — kassa va o'qituvchi hisobiga ta'sir qilmaydi."""

    __tablename__ = "bt_columns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(60), nullable=False)
    kind = Column(String(10), nullable=False, default="money")   # 'money' | 'text'
    position = Column(Integer, nullable=False, default=0)
    created_by = Column(String(64), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    deleted_at = Column(BigInteger, nullable=True)


class BtCell(Base):
    """v10.3: qo'shimcha ustundagi bitta katak (bitta to'lov qatori uchun)."""

    __tablename__ = "bt_cells"
    __table_args__ = (UniqueConstraint("column_id", "payment_id", name="uq_bt_cell"),)

    id = Column(Integer, primary_key=True, index=True)
    column_id = Column(Integer, ForeignKey("bt_columns.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    value_text = Column(String(200), nullable=True)
    value_num = Column(BigInteger, nullable=True)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(BigInteger, nullable=True)


class StudentTeacher(Base):
    """v10.9: bitta o'quvchi bir nechta o'qituvchida o'qishi mumkin (matematika, kimyo, ona tili...).
    O'quvchi bazada BIR MARTA bo'ladi; boshqa o'qituvchilar uni shu jadval orqali o'z ro'yxatiga
    biriktiradi. (O'quvchining asosiy o'qituvchisi — students.teacher_name — avvalgidek.)"""

    __tablename__ = "student_teachers"
    __table_args__ = (UniqueConstraint("student_id", "teacher_id", name="uq_student_teacher"),)

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    group_label = Column(String(255), nullable=True)
    added_by = Column(String(64), nullable=False)
    added_at = Column(BigInteger, nullable=False)



class AttendanceSession(Base):
    """v12.0: YO'QLAMA — bitta guruhning bitta kundagi darsi. (Hisob-kitobga aloqasi yo'q.)"""
    __tablename__ = "attendance_sessions"
    __table_args__ = (UniqueConstraint("group_id", "date", name="uq_attendance_group_date"),)

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)
    date = Column(String(10), nullable=False, index=True)        # 'YYYY-MM-DD' (Toshkent)
    group_label = Column(String(255), nullable=True)             # nusxa (guruh o'zgarsa ham tarix qoladi)
    created_by = Column(String(64), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(BigInteger, nullable=True)


class AttendanceMark(Base):
    """v12.0: o'quvchining shu darsdagi holati: 'present' (keldi) | 'absent' (kelmadi) + ixtiyoriy sabab."""
    __tablename__ = "attendance_marks"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_mark"),)

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(16), nullable=False)
    reason = Column(String(200), nullable=True)


class StudentArchiveLog(Base):
    """v12.5: o'quvchi arxivga tushgan / qaytgan har bir voqea (tarix). teachers — o'sha paytdagi o'qituvchilari (JSON)."""
    __tablename__ = "student_archive_log"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(16), nullable=False)      # 'archive' | 'restore'
    at = Column(BigInteger, nullable=False)
    by = Column(String(64), nullable=True)
    reason = Column(String(200), nullable=True)
    teachers = Column(JSON, nullable=True)


class SchoolAttendance(Base):
    """v12.6: MAKTAB o'quvchilari yo'qlamasi — markazga kelish (eshik oldida admin belgilaydi).
    status: 'present' (vaqtida) | 'late' (rahbar belgilagan vaqtdan keyin) | 'absent' (kelmadi, sabab ixtiyoriy)."""
    __tablename__ = "school_attendance"
    __table_args__ = (UniqueConstraint("student_id", "date", name="uq_school_att_student_date"),)
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(String(10), nullable=False, index=True)      # YYYY-MM-DD (Toshkent)
    status = Column(String(16), nullable=False)
    time = Column(String(5), nullable=True)                    # HH:MM — kelgan vaqti
    deadline = Column(String(5), nullable=True)                # o'sha kungi belgilangan vaqt
    reason = Column(String(200), nullable=True)
    marked_by = Column(String(64), nullable=True)
    marked_at = Column(BigInteger, nullable=True)


# ============================================================ v13.0: CHAT (Telegram uslubida)
class ChatThread(Base):
    """Suhbat: 'direct' (ikki kishi) yoki 'group' (umumiy guruh)."""
    __tablename__ = "chat_threads"
    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(10), nullable=False)                 # 'direct' | 'group'
    key = Column(String(40), nullable=False, unique=True)     # 'd:3:7' yoki 'g:all'
    title = Column(String(100), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    last_msg_id = Column(Integer, nullable=True)
    pinned_msg_id = Column(Integer, nullable=True)            # v13.3: qadalgan xabar
    rev = Column(BigInteger, nullable=True)                   # v13.3: tahrir/o'chirish/reaksiya bo'lganda o'zgaradi


class ChatMember(Base):
    __tablename__ = "chat_members"
    __table_args__ = (UniqueConstraint("thread_id", "user_id", name="uq_chat_member"),)
    id = Column(Integer, primary_key=True)
    thread_id = Column(Integer, ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    last_read_id = Column(Integer, nullable=False, default=0)
    joined_at = Column(BigInteger, nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sender_name = Column(String(100), nullable=True)          # foydalanuvchi o'chsa ham ism qoladi
    text = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False, index=True)
    deleted = Column(Boolean, nullable=False, default=False)
    reply_to_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)  # v13.1: javob (reply)
    edited_at = Column(BigInteger, nullable=True)              # v13.3: tahrirlangan
    forwarded_from = Column(String(100), nullable=True)        # v13.3: uzatilgan (asl muallif ismi)


class ChatReaction(Base):
    """v13.3: xabarga reaksiya (har kishi bitta xabarga bitta emoji)."""
    __tablename__ = "chat_reactions"
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_chat_reaction"),)
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    emoji = Column(String(16), nullable=False)
    created_at = Column(BigInteger, nullable=False)
