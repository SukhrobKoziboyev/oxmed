"""v10.9: o'quvchi takrorlanishini aniqlash va o'quvchi <-> o'qituvchi bog'lanishlari (yagona joy)."""
import re
from sqlalchemy.orm import Session
from . import models

_APOS = str.maketrans({"ʻ": "'", "ʼ": "'", "‘": "'", "’": "'", "`": "'", "´": "'"})


def norm_name(x: str) -> str:
    return " ".join((x or "").translate(_APOS).lower().split())


def phone9(x: str) -> str:
    return re.sub(r"\D", "", x or "")[-9:]


def who_label(db: Session, username: str) -> str:
    """'admin' -> 'Admin', 'rahbar' -> 'Rahbar', o'qituvchi logini -> uning ismi."""
    if not username:
        return ""
    u = db.query(models.User).filter(models.User.username == username).first()
    if u and u.role == "Markaz rahbari":
        return "Rahbar"
    if u and u.role == "Administrator":
        return "Admin"
    if u and u.teacher_id:
        t = db.query(models.Teacher).filter(models.Teacher.id == u.teacher_id).first()
        if t:
            return f"{t.name} ({t.subject.name if t.subject else (t.position or 'xodim')} o'qituvchisi)" if t.subject else t.name
    return username


def student_teachers(db: Session, st: models.Student) -> list:
    """O'quvchi qaysi o'qituvchilarda o'qiydi: asosiy + biriktirilganlar + to'lovdan ulush olganlar."""
    out, seen = [], set()

    def add(t: models.Teacher):
        if t and t.id not in seen and not t.is_staff:
            seen.add(t.id)
            out.append({"id": t.id, "name": t.name, "subject": t.subject.name if t.subject else ""})
    if st.teacher_name and st.subject_name:
        for t in db.query(models.Teacher).filter(models.Teacher.name == st.teacher_name).all():
            if t.subject and t.subject.name == st.subject_name:
                add(t)
    for link in db.query(models.StudentTeacher).filter(models.StudentTeacher.student_id == st.id).all():
        add(db.query(models.Teacher).filter(models.Teacher.id == link.teacher_id).first())
    tids = [r[0] for r in db.query(models.PaymentAllocation.teacher_id).join(models.Payment, models.Payment.id == models.PaymentAllocation.payment_id)
            .filter(models.Payment.student_id == st.id, models.PaymentAllocation.teacher_id.isnot(None)).distinct().all()]
    for tid in tids:
        add(db.query(models.Teacher).filter(models.Teacher.id == tid).first())
    return out


def find_duplicates(db: Session, first: str, last: str, phone: str, exclude_id=None) -> list:
    """Bir xil ism-familiya (telefon farq qilsa ham) — ehtimol o'sha o'quvchi."""
    fn, ln, ph = norm_name(first), norm_name(last), phone9(phone)
    res = []
    for st in db.query(models.Student).all():
        if exclude_id and st.id == exclude_id:
            continue
        same_name = norm_name(st.first_name) == fn and norm_name(st.last_name) == ln
        swapped = norm_name(st.first_name) == ln and norm_name(st.last_name) == fn
        if not (same_name or swapped):
            continue
        res.append({
            "id": st.id, "name": f"{st.first_name} {st.last_name}", "phone": st.phone,
            "same_phone": bool(ph) and phone9(st.phone) == ph,
            "type": st.type, "class_name": st.class_name,
            "added_by": who_label(db, st.added_by),
            "teachers": student_teachers(db, st),
        })
    res.sort(key=lambda r: not r["same_phone"])
    return res
