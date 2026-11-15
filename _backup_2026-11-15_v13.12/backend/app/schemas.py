from typing import Optional, List, Any
from pydantic import BaseModel, model_validator


class _UzDateMixin(BaseModel):
    """v7.9: date_str doim timestamp'dan Toshkent vaqtida hisoblanadi
    (eski yozuvlar server UTC'da 5 soat orqada yozilgan bo'lishi mumkin edi)."""

    @model_validator(mode="after")
    def _fix_uz_date(self):
        ts = getattr(self, "timestamp", None)
        if ts and ts > 10**11:
            from .utils import ts_to_uz_datestring
            try:
                self.date_str = ts_to_uz_datestring(ts)
            except Exception:  # noqa: BLE001
                pass
        return self


# ---------- AUTH ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str


class ChangeMyCredentialsRequest(BaseModel):
    current_password: str
    new_login: Optional[str] = None
    new_password: Optional[str] = None


class ChangeAdminCredentialsRequest(BaseModel):
    new_login: Optional[str] = None
    new_password: Optional[str] = None


class RecoverPasswordRequest(BaseModel):
    secret_password: str
    new_login: str
    new_password: str


class ChangeSecretPasswordRequest(BaseModel):
    current_secret: str
    new_secret: str


# ---------- SETTINGS ----------

class PhoneOut(BaseModel):
    id: int
    phone: str

    class Config:
        from_attributes = True


class SettingsOut(BaseModel):
    sms_template_parent: str
    sms_template_rahbar: str
    rahbar_phones: List[PhoneOut]
    sms_enabled: bool = False  # v8.9


class SMSTemplatesIn(BaseModel):
    sms_template_parent: str
    sms_template_rahbar: str


class PhoneIn(BaseModel):
    phone: str


# ---------- SUBJECTS ----------

class SubjectIn(BaseModel):
    name: str


class SubjectOut(BaseModel):
    id: int
    name: str
    repetitor_percent: Optional[int] = None
    school_percent: Optional[int] = None

    class Config:
        from_attributes = True


# ---------- TEACHERS / GROUPS ----------

class GroupIn(BaseModel):
    day_type: str  # toq | juft | harkuni
    start: str
    end: str


class GroupOut(BaseModel):
    id: int
    day_type: str
    start_time: str
    end_time: str
    label: str

    class Config:
        from_attributes = True


class TeacherIn(BaseModel):
    subject_id: int
    name: str
    phone: Optional[str] = None  # v11.16


class PhoneIn(BaseModel):
    phone: Optional[str] = None  # v11.16: bo'sh — o'chirish


class TeacherOut(BaseModel):
    id: int
    name: str
    subject_id: Optional[int] = None
    subject_name: str = ""
    groups: List[GroupOut] = []
    # YANGI: Hodimlar oyligi / login uchun
    percent_override: Optional[int] = None
    has_login: bool = False
    login_username: Optional[str] = None
    phone: Optional[str] = None  # v11.16

    class Config:
        from_attributes = True


class TeacherPercentIn(BaseModel):
    percent: Optional[int] = None  # None = fan standart foiziga qaytarish


class SubjectPercentIn(BaseModel):
    repetitor_percent: Optional[int] = None
    school_percent: Optional[int] = None


class TeacherLoginIn(BaseModel):
    username: str
    password: str


class TeacherLoginOut(BaseModel):
    has_login: bool
    username: Optional[str] = None


# ---------- STUDENTS ----------

class StudentIn(BaseModel):
    first_name: str
    last_name: str
    phone: str
    phone2: Optional[str] = None  # v8.6: qo'shimcha telefon (ixtiyoriy)
    type: str  # school | repetitor
    class_name: Optional[str] = None
    teacher_id: Optional[int] = None
    group_id: Optional[int] = None
    allow_duplicate: bool = False  # v10.9: bir xil ismli o'quvchi bor bo'lsa ham qo'shish


class StudentEditIn(BaseModel):
    """v7.9: o'quvchi ismi/familiyasi/telefonini (va maktab o'quvchisi sinfini) tuzatish."""
    first_name: str
    last_name: str
    phone: str
    class_name: Optional[str] = None
    phone2: Optional[str] = None  # v8.6: berilsa - yangilanadi ("" - o'chiriladi)
    allow_duplicate: bool = False  # v11.8: o'xshash o'quvchi bor, lekin baribir saqlash (aniq bir xil bo'lsa — mumkin emas)


class StudentOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone: str
    phone2: Optional[str] = None
    type: str
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None
    group_label: Optional[str] = None
    added_by: str
    added_at: str
    teachers: list = []   # v10.9: [{id, name, subject}] — qaysi o'qituvchilarda o'qiydi
    returned_at: Optional[str] = None   # v12.5: arxivdan qaytgan sana

    class Config:
        from_attributes = True


# ---------- PAYMENTS / ULUSHLAR (allocations) ----------

class AllocationIn(BaseModel):
    teacher_id: Optional[int] = None
    # teacher_id berilmasa, faqat ma'lumot uchun (masalan qo'lda kiritilgan,
    # tizimda ro'yxatdan o'tmagan holat) - odatda teacher_id doim beriladi
    teacher_name: Optional[str] = None
    subject_name: Optional[str] = None
    amount: int


class AllocationOut(BaseModel):
    id: int
    teacher_id: Optional[int] = None
    teacher_name: str
    subject_name: Optional[str] = None
    amount: int

    class Config:
        from_attributes = True


class PaymentIn(BaseModel):
    student_id: int
    month: str
    year: Optional[int] = None   # v13.11: berilmasa — dastur o'zi aniqlaydi (utils.auto_year)
    amount: int
    method: str = "naxt"  # naxt | click | terminal
    # Qo'lda kiritilgan ulushlar (agar berilsa, avtomatik foiz hisoblanmaydi)
    allocations: Optional[List[AllocationIn]] = None
    # allocations berilmasa va bu True bo'lsa, fan/o'qituvchi foizi asosida
    # avtomatik ulush hisoblanadi (mumkin bo'lsa)
    auto_split: bool = True
    # v7.9: ixtiyoriy sana 'dd.mm.YYYY HH:MM' (faqat rahbar; berilmasa - hozirgi vaqt)
    date: Optional[str] = None
    # v8.5: shu to'lovdan keyin shu oy uchun QOLGAN qarz (berilmasa - avvalgi qarz yozuvi saqlanadi
    # va bu to'lov uni avtomatik kamaytiradi; 0 berilsa - qarz yopiladi)
    debt: Optional[int] = None
    # v8.8: shu oy uchun oldin to'lov bo'lsa server 409 qaytaradi; foydalanuvchi
    # "Ha, yana kiritaman" desa shu True bilan qayta yuboriladi
    allow_duplicate: bool = False


class PaymentEditIn(BaseModel):
    amount: int
    method: Optional[str] = None
    # v7.9: qo'shimcha tahrirlar (berilmasa - o'zgarmaydi)
    month: Optional[str] = None
    year: Optional[int] = None          # v13.11: oy o'zgarsa — berilmasa dastur o'zi aniqlaydi
    date: Optional[str] = None          # 'dd.mm.YYYY HH:MM' (faqat rahbar)
    # Berilsa - to'lovning o'qituvchilar ulushlari TO'LIQ shu ro'yxat bilan almashtiriladi.
    # Berilmasa - eski xatti-harakat: ulushlar yangi summaga mutanosib qayta hisoblanadi.
    allocations: Optional[List[AllocationIn]] = None
    # v8.5: shu o'quvchining shu oy uchun qolgan qarzi (berilmasa o'zgarmaydi)
    debt: Optional[int] = None


class DueSetIn(BaseModel):
    """v8.5: o'quvchining oy uchun qolgan qarzini belgilash (0 - qarz yo'q)."""
    student_id: int
    month: str
    year: Optional[int] = None   # v13.11
    debt: int
    note: Optional[str] = None


class DueOut(BaseModel):
    student_id: int
    student_name: str
    student_type: str
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None
    phone: str = ""
    month: str
    year: Optional[int] = None
    due_amount: int
    paid: int
    debt: int
    note: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: Optional[str] = None


class PaymentOut(_UzDateMixin):
    id: int
    student_id: Optional[int]
    student_name: str
    student_phone: str
    student_type: str
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None
    group_label: Optional[str] = None
    class_name: Optional[str] = None
    month: str
    year: Optional[int] = None
    amount: int
    method: str = "naxt"
    date_str: str
    timestamp: int
    added_by: str
    edited_by: Optional[str] = None
    edited_at: Optional[str] = None
    allocations: List[AllocationOut] = []

    class Config:
        from_attributes = True


# ---------- RECYCLE BIN ----------

class RecycleBinOut(BaseModel):
    id: int
    type: str
    data: Any
    deleted_at: int
    deleted_by: str

    class Config:
        from_attributes = True


# ---------- HODIMLAR OYLIGI (Staff salary) ----------

class TeacherSalaryOut(BaseModel):
    teacher_id: int
    teacher_name: str
    subject_name: str
    percent: Optional[int] = None  # amaldagi foiz (override yoki fan standarti)
    total_allocated: int  # jami ajratilgan ulush (barcha vaqt)
    total_paid_out: int  # jami berilgan to'lovlar (oylik/avanslar)
    total_returned: int = 0  # v7.6: o'qituvchi markazga qaytargan summa
    # hozir olishi kerak bo'lgan summa = total_allocated - total_paid_out + total_returned
    # (manfiy bo'lsa - o'qituvchi markazga shuncha qarzdor)
    owed: int
    phone: Optional[str] = None  # v11.16
    students_count: int
    paid_count: int  # shu oy to'lov qilgan o'quvchilar soni
    unpaid_count: int


class PayoutIn(BaseModel):
    teacher_id: int
    amount: int
    note: Optional[str] = None
    kind: str = "payout"  # v7.6: 'payout' (berildi) | 'return' (qaytarildi)
    ptype: Optional[str] = None  # v11.16: 'avans' | 'oylik' (berilganda)
    month: Optional[str] = None  # v11.16: qaysi oy uchun (bo'sh — joriy oy)


class PayoutOut(_UzDateMixin):
    id: int
    teacher_id: Optional[int] = None
    teacher_name: str
    amount: int
    note: Optional[str] = None
    date_str: str
    timestamp: int
    paid_by: str
    kind: str = "payout"
    ptype: Optional[str] = None
    month: Optional[str] = None
    sms: Optional[str] = None  # v11.16: 'queued' | 'no_phone' | 'off'

    class Config:
        from_attributes = True


class LedgerEntryOut(_UzDateMixin):
    """v7.6: o'qituvchi hisob varag'idagi bitta qator."""
    kind: str            # 'share' (ulush) | 'payout' (berildi) | 'return' (qaytarildi)
    amount: int          # balansga ta'siri: + yoki -
    balance: int         # shu yozuvdan keyingi balans
    timestamp: int
    date_str: str
    title: str
    detail: Optional[str] = None
    ref_id: Optional[int] = None


class TeacherLedgerOut(BaseModel):
    teacher_id: int
    teacher_name: str
    total_allocated: int
    total_paid_out: int
    total_returned: int
    owed: int
    entries: List[LedgerEntryOut]  # eng yangisi birinchi


class TeacherSalaryDetailOut(BaseModel):
    teacher_id: int
    teacher_name: str
    subject_name: str
    percent: Optional[int] = None
    total_allocated: int
    total_paid_out: int
    total_returned: int = 0
    owed: int
    allocations: List[AllocationOut]
    payouts: List[PayoutOut]


class TeacherDashboardStudentOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone: str
    group_label: Optional[str] = None
    paid_this_month: bool
    total_paid: int
    # v10.6: qaysi oylar uchun to'lagan (oy -> summa) va shu oy to'lagan summa
    paid_months: dict = {}
    month_paid: int = 0
    payments: list = []   # v10.8: [{month, amount, date_str}] — eng yangisi birinchi
    source: str = "own"  # v10.9: own | link | pay
    added_by: Optional[str] = None


class TeacherDashboardOut(BaseModel):
    teacher_name: str
    subject_name: str
    percent: Optional[int] = None
    students_count: int
    paid_count: int
    unpaid_count: int
    total_allocated: int
    total_paid_out: int
    total_returned: int = 0
    owed: int
    current_month: str
    students: List[TeacherDashboardStudentOut]
    # v8.4: xodim (o'quvchisi yo'q hodim) kabineti uchun
    is_staff: bool = False
    can_expenses: bool = False   # v13.12: kabinetda "Xarajatlar" bo'limi
    position: Optional[str] = None
    monthly_salary: Optional[int] = None
    phone: Optional[str] = None  # v11.17: o'qituvchi/xodimning o'z telefoni (SMS shu raqamga)


# ---------- v8.4: XODIMLAR (farrosh, oshpaz, direktor o'rinbosari, ...) ----------

class StaffIn(BaseModel):
    name: str
    position: str
    monthly_salary: int = 0
    salary_start: Optional[str] = None  # 'YYYY-MM'; bo'sh bo'lsa - joriy oy
    phone: Optional[str] = None  # v11.16
    can_expenses: Optional[bool] = None  # v13.12: berilmasa — o'zgarmaydi (yangi xodimda — yo'q)


class StaffOut(BaseModel):
    id: int
    name: str
    position: Optional[str] = None
    monthly_salary: int = 0
    salary_start: Optional[str] = None
    phone: Optional[str] = None  # v11.16
    can_expenses: bool = False   # v13.12
    has_login: bool = False
    login_username: Optional[str] = None
    total_accrued: int = 0
    total_paid_out: int = 0
    total_returned: int = 0
    owed: int = 0


class AccrualIn(BaseModel):
    amount: int
    note: Optional[str] = None


class AccrualEditIn(BaseModel):
    amount: int
    note: Optional[str] = None


# ---------- BACKUP / RESTORE ----------

class BackupOut(BaseModel):
    subjects: List[str]
    teachers: dict
    students: List[dict]
    payments: List[dict]
    sms_template_parent: str
    sms_template_rahbar: str
    rahbar_phones: List[str]
    backup_date: str
