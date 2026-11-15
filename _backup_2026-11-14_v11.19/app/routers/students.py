from typing import List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..utils import format_group_label, now_timestamp_ms, utc_naive_to_uz_string
from ..student_links import find_duplicates, canon, phone9, duplicate_pairs

router = APIRouter(prefix="/api/students", tags=["students"])


def _student_to_out(s: models.Student) -> schemas.StudentOut:
    return schemas.StudentOut(
        id=s.id,
        first_name=s.first_name,
        last_name=s.last_name,
        phone=s.phone,
        phone2=s.phone2,
        type=s.type,
        class_name=s.class_name,
        subject_name=s.subject_name,
        teacher_name=s.teacher_name,
        group_label=s.group_label,
        added_by=s.added_by,
        added_at=utc_naive_to_uz_string(s.added_at),
    )


@router.get("", response_model=List[schemas.StudentOut])
def list_students(
    current_user: models.User = Depends(auth.require_staff),  # v10.9: o'qituvchi hammani ko'rmasin
    db: Session = Depends(get_db),
):
    students = db.query(models.Student).order_by(models.Student.id).all()
    # v10.9: har bir o'quvchi qaysi o'qituvchilarda o'qiydi (asosiy + biriktirilgan + to'lovdan ulush) — bitta o'tishda
    teachers = {t.id: t for t in db.query(models.Teacher).all() if not t.is_staff}
    by_name = {}
    for t in teachers.values():
        if t.subject:
            by_name[(t.name, t.subject.name)] = t.id
    tmap = {}   # student_id -> [(teacher_id, group_label, source)]
    for st in students:
        if st.teacher_name and st.subject_name and (st.teacher_name, st.subject_name) in by_name:
            tmap.setdefault(st.id, []).append((by_name[(st.teacher_name, st.subject_name)], st.group_label, "own"))
    for sid, tid, gl in db.query(models.StudentTeacher.student_id, models.StudentTeacher.teacher_id, models.StudentTeacher.group_label).all():
        tmap.setdefault(sid, []).append((tid, gl, "link"))
    for sid, tid in (db.query(models.Payment.student_id, models.PaymentAllocation.teacher_id)
                     .join(models.PaymentAllocation, models.PaymentAllocation.payment_id == models.Payment.id)
                     .filter(models.Payment.student_id.isnot(None), models.PaymentAllocation.teacher_id.isnot(None)).distinct().all()):
        tmap.setdefault(sid, []).append((tid, None, "pay"))
    out = []
    for s in students:
        o = _student_to_out(s)
        res, seen = [], set()
        for tid, gl, src in tmap.get(s.id, []):
            if tid in teachers and tid not in seen:
                seen.add(tid)
                t = teachers[tid]
                res.append({"id": tid, "name": t.name, "subject": t.subject.name if t.subject else "", "group": gl, "source": src})
        o.teachers = res
        out.append(o)
    return out


@router.post("", response_model=schemas.StudentOut)
def create_student(
    payload: schemas.StudentIn,
    current_user: models.User = Depends(auth.require_staff),  # v10.4: o'qituvchi /api/teacher/students orqali qo'shadi
    db: Session = Depends(get_db),
):
    if payload.type not in ("school", "repetitor"):
        raise HTTPException(status_code=400, detail="O'quvchi turi noto'g'ri!")
    if not payload.first_name.strip() or not payload.last_name.strip() or not payload.phone.strip():
        raise HTTPException(status_code=400, detail="Ism, familiya va telefon raqamini kiriting!")
    # v10.9: bitta o'quvchi bazada bir marta — bir xil ism-familiyali o'quvchi bo'lsa, avval so'raymiz
    # v11.8: aqlli o'xshashlik (Ahmad = Axmad). Ism VA telefon bir xil bo'lsa — baribir qo'shib bo'lmaydi.
    dups = find_duplicates(db, payload.first_name, payload.last_name, payload.phone)
    blocked = any(d["exact_same"] for d in dups)
    if dups and (blocked or not payload.allow_duplicate):
        raise HTTPException(status_code=409, detail={"code": "duplicate_student", "matches": dups, "blocked": blocked})

    student = models.Student(
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        phone=payload.phone.strip(),
        phone2=(payload.phone2 or "").strip() or None,
        type=payload.type,
        added_by=current_user.username,
    )

    if payload.type == "school":
        if not payload.class_name:
            raise HTTPException(status_code=400, detail="Sinfni tanlang!")
        student.class_name = payload.class_name
    else:
        # v8.6: o'qituvchi ham, guruh ham ixtiyoriy. O'qituvchisiz repetitor o'quvchida
        # fan/o'qituvchi/guruh bo'sh (NULL) qoladi - to'lovida avtomatik ulush ajratilmaydi.
        if not payload.teacher_id:
            if payload.group_id:
                raise HTTPException(status_code=400, detail="Guruh tanlash uchun avval o'qituvchini tanlang!")
            db.add(student)
            db.commit()
            db.refresh(student)
            return _student_to_out(student)
        teacher = db.query(models.Teacher).filter(models.Teacher.id == payload.teacher_id).first()
        if not teacher:
            raise HTTPException(status_code=400, detail="O'qituvchi topilmadi!")
        if teacher.is_staff or not teacher.subject:
            raise HTTPException(status_code=400, detail="Xodimga o'quvchi biriktirib bo'lmaydi!")
        group = None
        if payload.group_id:
            group = db.query(models.Group).filter(models.Group.id == payload.group_id).first()
            if not group or group.teacher_id != teacher.id:
                raise HTTPException(status_code=400, detail="Guruh topilmadi yoki bu o'qituvchiga tegishli emas!")
        student.subject_name = teacher.subject.name
        student.teacher_name = teacher.name
        student.group_label = format_group_label(group) if group else None

    db.add(student)
    db.commit()
    db.refresh(student)
    return _student_to_out(student)


@router.put("/{student_id}", response_model=schemas.StudentOut)
def edit_student(
    student_id: int,
    payload: schemas.StudentEditIn,
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    """v7.9: o'quvchining ismi, familiyasi, telefoni (va maktab o'quvchisi sinfi)ni tuzatish.
    Shu o'quvchining to'lovlaridagi ism/telefon nusxasi ham yangilanadi - summalar va
    o'qituvchilar ulushiga TEGILMAYDI."""
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")

    first = (payload.first_name or "").strip()
    last = (payload.last_name or "").strip()
    phone = (payload.phone or "").strip()
    if not first or not last:
        raise HTTPException(status_code=400, detail="Ism va familiyani kiriting!")
    if len("".join(ch for ch in phone if ch.isdigit())) < 9:
        raise HTTPException(status_code=400, detail="Telefon raqamini to'g'ri kiriting!")

    # v11.8: tahrirlab boshqa o'quvchi bilan bir xil qilib qo'yib bo'lmaydi (o'xshash bo'lsa — avval so'raymiz)
    changed = (canon(first), canon(last), phone9(phone)) != (canon(student.first_name), canon(student.last_name), phone9(student.phone))
    if changed:
        dups = [d for d in find_duplicates(db, first, last, phone, exclude_id=student.id) if d["match"] != "sibling"]
        blocked = any(d["exact_same"] for d in dups)
        if dups and (blocked or not payload.allow_duplicate):
            raise HTTPException(status_code=409, detail={"code": "duplicate_student", "matches": dups, "blocked": blocked, "editing_id": student.id})
    student.first_name, student.last_name, student.phone = first, last, phone
    if payload.phone2 is not None:
        p2 = payload.phone2.strip()
        if p2 and len("".join(ch for ch in p2 if ch.isdigit())) < 9:
            raise HTTPException(status_code=400, detail="Qo'shimcha telefon raqamini to'g'ri kiriting!")
        student.phone2 = p2 or None
    if student.type == "school" and payload.class_name and payload.class_name.strip():
        student.class_name = payload.class_name.strip()
    new_full = f"{first} {last}"

    payments = db.query(models.Payment).filter(models.Payment.student_id == student.id).all()
    for p in payments:
        p.student_name = new_full
        p.student_phone = phone

    db.commit()
    db.refresh(student)
    return _student_to_out(student)


@router.get("/duplicates")
def list_duplicates(current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    """v11.8: ikki marta yozilganga o'xshagan o'quvchilar (Jami o'quvchilar tepasida ogohlantirish)."""
    return duplicate_pairs(db)


class MergeIn(BaseModel):
    into_id: int


@router.post("/{student_id}/merge")
def merge_student(
    student_id: int,
    payload: MergeIn,
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    """v11.8: ikki marta yozilgan o'quvchini BIRLASHTIRISH. student_id (ortiqchasi) -> into_id (qoladigani).
    To'lovlar, qarzlar, o'qituvchilarga biriktirishlar qoladigan o'quvchiga o'tadi, ortiqchasi o'chadi.
    Summalar va o'qituvchi ulushlari (payment_allocations) O'ZGARMAYDI — kassa va hisob-kitob o'sha-o'sha."""
    if student_id == payload.into_id:
        raise HTTPException(status_code=400, detail="O'quvchini o'zi bilan birlashtirib bo'lmaydi!")
    src = db.query(models.Student).filter(models.Student.id == student_id).with_for_update().first()
    dst = db.query(models.Student).filter(models.Student.id == payload.into_id).with_for_update().first()
    if not src or not dst:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")
    dst_full = f"{dst.first_name} {dst.last_name}"
    moved_pay = 0
    for p in db.query(models.Payment).filter(models.Payment.student_id == src.id).all():
        p.student_id, p.student_name, p.student_phone = dst.id, dst_full, dst.phone
        moved_pay += 1
    for due in db.query(models.StudentDue).filter(models.StudentDue.student_id == src.id).all():
        same = db.query(models.StudentDue).filter(models.StudentDue.student_id == dst.id, models.StudentDue.month == due.month).first()
        if same:  # ikkalasi bitta qarzni yozgan — kattasini qoldiramiz (ikki marta qo'shilmaydi)
            same.due_amount = max(int(same.due_amount), int(due.due_amount))
            db.delete(due)
        else:
            due.student_id = dst.id
    have = {l.teacher_id for l in db.query(models.StudentTeacher).filter(models.StudentTeacher.student_id == dst.id).all()}
    for link in db.query(models.StudentTeacher).filter(models.StudentTeacher.student_id == src.id).all():
        if link.teacher_id in have:
            db.delete(link)
        else:
            link.student_id = dst.id
            have.add(link.teacher_id)
    # ortiqchasining asosiy o'qituvchisi qoladiganida yo'q bo'lsa — saqlab qolamiz
    if src.teacher_name and src.subject_name:
        if not dst.teacher_name:
            dst.subject_name, dst.teacher_name, dst.group_label = src.subject_name, src.teacher_name, src.group_label
            if dst.type == "school" and not dst.class_name:
                dst.type = "repetitor"
        elif (dst.teacher_name, dst.subject_name) != (src.teacher_name, src.subject_name):
            t = (db.query(models.Teacher).join(models.Subject).filter(models.Teacher.name == src.teacher_name,
                 models.Subject.name == src.subject_name).first())
            if t and t.id not in have:
                db.add(models.StudentTeacher(student_id=dst.id, teacher_id=t.id, group_label=src.group_label,
                                             added_by=src.added_by or current_user.username, added_at=now_timestamp_ms()))
    if not dst.phone2 and phone9(src.phone) and phone9(src.phone) != phone9(dst.phone):
        dst.phone2 = src.phone
    db.query(models.SmsLog).filter(models.SmsLog.student_id == src.id).update({"student_id": dst.id}, synchronize_session=False)
    db.flush()
    db.delete(src)
    db.commit()
    return {"ok": True, "into_id": dst.id, "moved_payments": moved_pay}


@router.delete("/{student_id}")
def delete_student(
    student_id: int,
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")

    full_name = f"{student.first_name} {student.last_name}"
    related_payments = db.query(models.Payment).filter(models.Payment.student_name == full_name).all()

    # Recycle bin'ga saqlash
    student_snapshot = _student_to_out(student).dict()
    db.add(models.RecycleBinItem(
        type="student",
        data=student_snapshot,
        deleted_at=now_timestamp_ms(),
        deleted_by=current_user.username,
    ))
    for p in related_payments:
        payment_snapshot = schemas.PaymentOut.from_orm(p).dict()
        db.add(models.RecycleBinItem(
            type="payment",
            data=payment_snapshot,
            deleted_at=now_timestamp_ms(),
            deleted_by=current_user.username,
        ))
        db.delete(p)

    db.delete(student)
    db.commit()
    return {"ok": True, "removed_payments": len(related_payments)}


@router.post("/bulk")
def bulk_create_students(
    rows: List[dict],
    current_user: models.User = Depends(auth.require_staff),
    db: Session = Depends(get_db),
):
    """Excel'dan ommaviy yuklash uchun. Har bir qatorda:
    firstName, lastName, phone, type ('school'|'repetitor'),
    school bo'lsa: className
    repetitor bo'lsa: teacherId, groupId (frontend avval /api/teachers dan
    o'qituvchi/guruhni topib shu ID larni yuborishi kerak)
    """
    created = 0
    errors = []

    for i, row in enumerate(rows):
        try:
            first_name = row.get("firstName", "").strip()
            last_name = row.get("lastName", "").strip()
            phone = row.get("phone", "").strip()
            s_type = row.get("type", "").strip().lower()

            if not (first_name and last_name and phone and s_type in ("school", "repetitor")):
                errors.append(f"Qator {i + 1}: majburiy maydonlar to'ldirilmagan")
                continue

            student = models.Student(
                first_name=first_name, last_name=last_name, phone=phone,
                type=s_type, added_by=current_user.username,
            )

            if s_type == "school":
                class_name = row.get("className")
                if not class_name:
                    errors.append(f"Qator {i + 1}: sinf ko'rsatilmagan")
                    continue
                student.class_name = class_name
            else:
                teacher_id = row.get("teacherId")
                group_id = row.get("groupId")
                teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
                group = db.query(models.Group).filter(models.Group.id == group_id).first()
                if not teacher or not group:
                    errors.append(f"Qator {i + 1}: o'qituvchi yoki guruh topilmadi")
                    continue
                if teacher.is_staff or not teacher.subject:
                    errors.append(f"Qator {i + 1}: xodimga o'quvchi biriktirib bo'lmaydi")
                    continue
                student.subject_name = teacher.subject.name
                student.teacher_name = teacher.name
                student.group_label = format_group_label(group)

            db.add(student)
            created += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"Qator {i + 1}: {e}")

    db.commit()
    return {"created": created, "errors": errors}
