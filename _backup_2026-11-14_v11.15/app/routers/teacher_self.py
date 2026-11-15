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
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..utils import current_uz_month_name, format_group_label, now_timestamp_ms
from ..student_links import find_duplicates
from .. import ledger

router = APIRouter(prefix="/api/teacher", tags=["teacher-self"])


def my_students(db: Session, teacher: models.Teacher):
    """[(student, source, group_label)] — source: 'own' (asosiy), 'link' (ro'yxatimga qo'shilgan), 'pay' (to'lovdan ulush)."""
    out, seen = [], set()
    for st in db.query(models.Student).filter(models.Student.type == "repetitor", models.Student.teacher_name == teacher.name,
                                              models.Student.subject_name == teacher.subject.name).all():
        seen.add(st.id); out.append((st, "own", st.group_label))
    for link, st in (db.query(models.StudentTeacher, models.Student).join(models.Student, models.Student.id == models.StudentTeacher.student_id)
                     .filter(models.StudentTeacher.teacher_id == teacher.id).all()):
        if st.id not in seen:
            seen.add(st.id); out.append((st, "link", link.group_label))
    for st in (db.query(models.Student).join(models.Payment, models.Payment.student_id == models.Student.id)
               .join(models.PaymentAllocation, models.PaymentAllocation.payment_id == models.Payment.id)
               .filter(models.PaymentAllocation.teacher_id == teacher.id).distinct().all()):
        if st.id not in seen:
            seen.add(st.id); out.append((st, "pay", None))
    return out


def teacher_payments(db: Session, teacher: models.Teacher, st: models.Student, source: str):
    """O'quvchining SHU o'qituvchiga tegishli to'lovlari: [(payment, ulush)].
    Ulush ajratilgan to'lov — shu o'qituvchiniki; asosiy o'quvchida ulushsiz (umuman bo'linmagan) to'lov ham hisobga olinadi."""
    full = f"{st.first_name} {st.last_name}"
    pays = db.query(models.Payment).filter(or_(models.Payment.student_id == st.id,
                                               and_(models.Payment.student_id.is_(None), models.Payment.student_name == full))).all()
    res = []
    for p in pays:
        allocs = db.query(models.PaymentAllocation).filter(models.PaymentAllocation.payment_id == p.id).all()
        mine = sum(int(a.amount) for a in allocs if a.teacher_id == teacher.id)
        if mine > 0 or (source == "own" and not allocs):
            res.append((p, mine))
    return res


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

    # v10.9: o'qituvchining o'quvchilari = asosiy (o'zi/rahbar biriktirgan) + o'z ro'yxatiga qo'shganlari
    #        + rahbar/admin to'lovidan unga ulush ajratilgan o'quvchilar. To'lov holati — faqat SHU
    #        o'qituvchiga tegishli to'lovlar (ulush ajratilgani) bo'yicha.
    entries = my_students(db, teacher)
    students_out = []
    paid_count = 0
    for st, source, glabel in entries:
        pays = teacher_payments(db, teacher, st, source)
        # v11.7: o'qituvchiga o'quvchining to'liq to'lov summasi BERILMAYDI — faqat rahbar unga ajratgan ulush.
        #        Oy kaliti bor = shu oy to'langan (ulush 0 bo'lsa ham — masalan hali bo'linmagan to'lov).
        months = {}
        for p, share in pays:
            months[p.month] = months.get(p.month, 0) + int(share or 0)
        paid_this_month = current_month in months
        if paid_this_month:
            paid_count += 1
        students_out.append(schemas.TeacherDashboardStudentOut(
            id=st.id, first_name=st.first_name, last_name=st.last_name, phone=st.phone,
            group_label=glabel, paid_this_month=paid_this_month,
            total_paid=sum(int(share or 0) for _, share in pays),
            paid_months=months, month_paid=months.get(current_month, 0), added_by=st.added_by,
            payments=[{"month": p.month, "share": int(share or 0),
                       "date_str": schemas.PaymentOut.from_orm(p).date_str or ""}
                      for p, share in sorted(pays, key=lambda x: x[0].timestamp or 0, reverse=True)],
            source=source,
        ))
    students = entries

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
    # v11.7: o'qituvchi faqat o'z ulushini ko'radi — o'quvchi qancha to'lagani yozilmaydi
    return ledger.teacher_ledger(db, teacher, hide_payment_amount=True)


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
    for st, src, gl in my_students(db, t):
        counts[gl] = counts.get(gl, 0) + 1
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
    n = sum(1 for _, _, gl in my_students(db, t) if gl == label)
    if n:
        raise HTTPException(status_code=400, detail=f"Bu guruhda {n} ta o'quvchi bor — avval ularni boshqa guruhga o'tkazing yoki rahbarga ayting")
    db.delete(g)
    db.commit()
    return {"ok": True}


class MyStudentIn(BaseModel):
    first_name: str = Field("", max_length=128)
    last_name: str = Field("", max_length=128)
    phone: str = Field("", max_length=32)
    phone2: Optional[str] = Field(None, max_length=32)
    group_id: Optional[int] = None
    link_student_id: Optional[int] = None   # v10.9: bazadagi o'quvchini ro'yxatimga biriktirish
    force_new: bool = False                 # v10.9: bir xil ismli bor, lekin bu boshqa bola


def _digits(x: str) -> str:
    return re.sub(r"\D", "", x or "")[-9:]


@router.post("/students")
def add_my_student(data: MyStudentIn, current_user: models.User = Depends(auth.require_teacher), db: Session = Depends(get_db)):
    t = _my_teacher(db, current_user)
    group = None
    if data.group_id:
        group = db.query(models.Group).filter(models.Group.id == data.group_id, models.Group.teacher_id == t.id).first()
        if not group:
            raise HTTPException(status_code=400, detail="Guruh topilmadi!")
    glabel = format_group_label(group) if group else None
    mine = {st.id for st, _, _ in my_students(db, t)}

    # 1) bazadagi o'quvchini o'z ro'yxatimga qo'shish (yangi o'quvchi YARATILMAYDI)
    if data.link_student_id:
        st = db.query(models.Student).filter(models.Student.id == data.link_student_id).first()
        if not st:
            raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")
        if st.id in mine:
            raise HTTPException(status_code=400, detail="Bu o'quvchi allaqachon sizning ro'yxatingizda!")
        db.add(models.StudentTeacher(student_id=st.id, teacher_id=t.id, group_label=glabel,
                                     added_by=current_user.username, added_at=now_timestamp_ms()))
        db.commit()
        return {"id": st.id, "first_name": st.first_name, "last_name": st.last_name, "phone": st.phone, "group_label": glabel, "linked": True}

    fn, ln, ph = " ".join(data.first_name.split()), " ".join(data.last_name.split()), data.phone.strip()
    if not fn or not ln:
        raise HTTPException(status_code=400, detail="Ism va familiyani kiriting!")
    if len(_digits(ph)) < 9:
        raise HTTPException(status_code=400, detail="Telefon raqamini to'liq kiriting (9 ta raqam)")
    # 2) bir xil ism-familiyali o'quvchi bazada bormi — avval so'raymiz
    dups = find_duplicates(db, fn, ln, ph)
    for d in dups:
        d["in_my_list"] = d["id"] in mine
    if any(d["in_my_list"] and d["exact_same"] for d in dups):
        raise HTTPException(status_code=400, detail="Bu o'quvchi allaqachon sizning ro'yxatingizda!")
    blocked = any(d["exact_same"] for d in dups)  # v11.8: ism va telefon bir xil — faqat biriktirish mumkin
    if dups and (blocked or not data.force_new):
        raise HTTPException(status_code=409, detail={"code": "duplicate_student", "matches": dups, "blocked": blocked})
    st = models.Student(first_name=fn, last_name=ln, phone=ph, phone2=(data.phone2 or "").strip() or None, type="repetitor",
                        subject_name=t.subject.name, teacher_name=t.name, group_label=glabel, added_by=current_user.username)
    db.add(st)
    db.commit()
    db.refresh(st)
    return {"id": st.id, "first_name": st.first_name, "last_name": st.last_name, "phone": st.phone, "group_label": st.group_label}


@router.delete("/students/{sid}/link")
def remove_my_link(sid: int, current_user: models.User = Depends(auth.require_teacher), db: Session = Depends(get_db)):
    """v10.9: o'z ro'yxatimga qo'shgan o'quvchini ro'yxatimdan chiqarish (bazadan O'CHMAYDI)."""
    t = _my_teacher(db, current_user)
    link = db.query(models.StudentTeacher).filter(models.StudentTeacher.student_id == sid, models.StudentTeacher.teacher_id == t.id).first()
    if not link:
        raise HTTPException(status_code=400, detail="Bu o'quvchini faqat rahbar yoki admin o'zgartira oladi")
    db.delete(link)
    db.commit()
    return {"ok": True}

