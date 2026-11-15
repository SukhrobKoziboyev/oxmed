"""YANGI BO'LIM: O'qituvchining shaxsiy kabineti (mobil "profil" ko'rinishi).

O'qituvchi rahbar bergan login/parol bilan kirganda shu endpointlar orqali
o'zining: hozir olishi kerak bo'lgan summasini, nechta o'quvchisi borligini,
nechtasi shu oy to'lov qilgan/qilmaganini ko'radi. Login/parolni o'zgartirish
uchun umumiy /api/auth/change-my-credentials ishlatiladi (u current_user'ga
bog'liq, rol qanday bo'lishidan qat'iy nazar ishlaydi)."""
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..utils import current_uz_month_name, format_group_label
from .. import ledger

router = APIRouter(prefix="/api/teacher", tags=["teacher-self"])


@router.get("/dashboard", response_model=schemas.TeacherDashboardOut)
def teacher_dashboard(
    current_user: models.User = Depends(auth.require_teacher),
    db: Session = Depends(get_db),
):
    teacher = db.query(models.Teacher).filter(models.Teacher.id == current_user.teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")

    if teacher.is_staff or not teacher.subject:
        # v8.4: xodim kabineti - o'quvchilar yo'q, faqat oylik hisobi
        ledger.ensure_staff_accruals(db, teacher)
        accrued, paid_out, returned, owed = ledger.teacher_totals(db, teacher.id)
        return schemas.TeacherDashboardOut(
            teacher_name=teacher.name, subject_name=teacher.position or "Xodim", percent=None,
            students_count=0, paid_count=0, unpaid_count=0,
            total_allocated=accrued, total_paid_out=paid_out, total_returned=returned, owed=owed,
            current_month=current_uz_month_name(), students=[],
            is_staff=True, position=teacher.position, monthly_salary=int(teacher.monthly_salary or 0),
        )

    percent = teacher.percent_override if teacher.percent_override is not None else teacher.subject.repetitor_percent
    current_month = current_uz_month_name()

    # v7.6: hisob-kitob yagona manbadan (app/ledger.py)
    allocated_sum, payouts_sum, returned_sum, owed = ledger.teacher_totals(db, teacher.id)

    students = db.query(models.Student).filter(
        models.Student.type == "repetitor",
        models.Student.teacher_name == teacher.name,
        models.Student.subject_name == teacher.subject.name,
    ).all()

    students_out = []
    paid_count = 0
    for s in students:
        full_name = f"{s.first_name} {s.last_name}"
        student_payments = db.query(models.Payment).filter(models.Payment.student_name == full_name).all()
        paid_this_month = any(p.month == current_month for p in student_payments)
        if paid_this_month:
            paid_count += 1
        students_out.append(schemas.TeacherDashboardStudentOut(
            id=s.id,
            first_name=s.first_name,
            last_name=s.last_name,
            phone=s.phone,
            group_label=s.group_label,
            paid_this_month=paid_this_month,
            total_paid=sum(p.amount for p in student_payments),
        ))

    return schemas.TeacherDashboardOut(
        teacher_name=teacher.name,
        subject_name=teacher.subject.name,
        percent=percent,
        students_count=len(students),
        paid_count=paid_count,
        unpaid_count=len(students) - paid_count,
        total_allocated=allocated_sum,
        total_paid_out=payouts_sum,
        total_returned=returned_sum,
        owed=owed,
        current_month=current_month,
        students=students_out,
    )


@router.get("/ledger", response_model=schemas.TeacherLedgerOut)
def my_ledger(
    current_user: models.User = Depends(auth.require_teacher),
    db: Session = Depends(get_db),
):
    """v7.6: o'qituvchi o'z hisob varag'ini ko'radi (faqat o'zinikini)."""
    teacher = db.query(models.Teacher).filter(models.Teacher.id == current_user.teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")
    ledger.ensure_staff_accruals(db, teacher)
    return ledger.teacher_ledger(db, teacher)


# =====================================================================
# v10.4: O'QITUVCHI O'ZI — guruhlarini va o'quvchilarini qo'shadi
#   * faqat fan o'qituvchisi (xodim — farrosh, zam direktor... — emas);
#   * qo'shilgan o'quvchi oddiy repetitor o'quvchi: Jami o'quvchilar, to'lov kiritish,
#     ulush hisobi — hammasi avvalgidek ishlaydi; added_by = o'qituvchi logini;
#   * o'qituvchi faqat o'z o'quvchilari va guruhlarini ko'radi.
# =====================================================================
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _my_teacher(db: Session, user: models.User) -> models.Teacher:
    t = db.query(models.Teacher).filter(models.Teacher.id == user.teacher_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")
    if t.is_staff or not t.subject:
        raise HTTPException(status_code=403, detail="Bu bo'lim faqat fan o'qituvchilari uchun")
    return t


def _group_out(g: models.Group) -> dict:
    return {"id": g.id, "day_type": g.day_type, "start_time": g.start_time, "end_time": g.end_time, "label": format_group_label(g)}


class MyGroupIn(BaseModel):
    day_type: str
    start: str
    end: str


@router.get("/groups")
def my_groups(current_user: models.User = Depends(auth.require_teacher), db: Session = Depends(get_db)):
    t = _my_teacher(db, current_user)
    groups = db.query(models.Group).filter(models.Group.teacher_id == t.id).order_by(models.Group.start_time).all()
    counts = {}
    for st in db.query(models.Student).filter(models.Student.type == "repetitor", models.Student.teacher_name == t.name,
                                              models.Student.subject_name == t.subject.name).all():
        counts[st.group_label] = counts.get(st.group_label, 0) + 1
    return [{**_group_out(g), "students": counts.get(format_group_label(g), 0)} for g in groups]


@router.post("/groups")
def add_my_group(data: MyGroupIn, current_user: models.User = Depends(auth.require_teacher), db: Session = Depends(get_db)):
    t = _my_teacher(db, current_user)
    if data.day_type not in ("toq", "juft", "harkuni"):
        raise HTTPException(status_code=400, detail="Kunlarni tanlang!")
    a, b = (data.start or "").strip(), (data.end or "").strip()
    if not _TIME.match(a) or not _TIME.match(b):
        raise HTTPException(status_code=400, detail="Vaqtni to'g'ri kiriting (masalan 14:00)")
    a, b = a.zfill(5), b.zfill(5)
    if a >= b:
        raise HTTPException(status_code=400, detail="Tugash vaqti boshlanishidan keyin bo'lishi kerak!")
    if db.query(models.Group).filter(models.Group.teacher_id == t.id, models.Group.day_type == data.day_type,
                                     models.Group.start_time == a, models.Group.end_time == b).first():
        raise HTTPException(status_code=400, detail="Bunday guruh allaqachon bor!")
    g = models.Group(teacher_id=t.id, day_type=data.day_type, start_time=a, end_time=b)
    db.add(g)
    db.commit()
    db.refresh(g)
    return {**_group_out(g), "students": 0}


@router.delete("/groups/{gid}")
def delete_my_group(gid: int, current_user: models.User = Depends(auth.require_teacher), db: Session = Depends(get_db)):
    t = _my_teacher(db, current_user)
    g = db.query(models.Group).filter(models.Group.id == gid, models.Group.teacher_id == t.id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Guruh topilmadi!")
    label = format_group_label(g)
    n = db.query(models.Student).filter(models.Student.type == "repetitor", models.Student.teacher_name == t.name,
                                        models.Student.subject_name == t.subject.name, models.Student.group_label == label).count()
    if n:
        raise HTTPException(status_code=400, detail=f"Bu guruhda {n} ta o'quvchi bor — avval ularni boshqa guruhga o'tkazing yoki rahbarga ayting")
    db.delete(g)
    db.commit()
    return {"ok": True}


class MyStudentIn(BaseModel):
    first_name: str = Field(..., max_length=128)
    last_name: str = Field(..., max_length=128)
    phone: str = Field(..., max_length=32)
    phone2: Optional[str] = Field(None, max_length=32)
    group_id: Optional[int] = None


def _digits(x: str) -> str:
    return re.sub(r"\D", "", x or "")[-9:]


@router.post("/students")
def add_my_student(data: MyStudentIn, current_user: models.User = Depends(auth.require_teacher), db: Session = Depends(get_db)):
    t = _my_teacher(db, current_user)
    fn, ln, ph = " ".join(data.first_name.split()), " ".join(data.last_name.split()), data.phone.strip()
    if not fn or not ln:
        raise HTTPException(status_code=400, detail="Ism va familiyani kiriting!")
    if len(_digits(ph)) < 9:
        raise HTTPException(status_code=400, detail="Telefon raqamini to'liq kiriting (9 ta raqam)")
    group = None
    if data.group_id:
        group = db.query(models.Group).filter(models.Group.id == data.group_id, models.Group.teacher_id == t.id).first()
        if not group:
            raise HTTPException(status_code=400, detail="Guruh topilmadi!")
    # takror: shu o'qituvchida shu ism-familiya va telefon bilan o'quvchi bormi
    for st in db.query(models.Student).filter(models.Student.type == "repetitor", models.Student.teacher_name == t.name,
                                              models.Student.subject_name == t.subject.name).all():
        if st.first_name.lower() == fn.lower() and st.last_name.lower() == ln.lower() and _digits(st.phone) == _digits(ph):
            raise HTTPException(status_code=409, detail="Bu o'quvchi sizning ro'yxatingizda allaqachon bor!")
    st = models.Student(first_name=fn, last_name=ln, phone=ph, phone2=(data.phone2 or "").strip() or None, type="repetitor",
                        subject_name=t.subject.name, teacher_name=t.name,
                        group_label=format_group_label(group) if group else None, added_by=current_user.username)
    db.add(st)
    db.commit()
    db.refresh(st)
    return {"id": st.id, "first_name": st.first_name, "last_name": st.last_name, "phone": st.phone, "group_label": st.group_label}

