from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..utils import format_group_label, now_timestamp_ms

router = APIRouter(prefix="/api/students", tags=["students"])


def _student_to_out(s: models.Student) -> schemas.StudentOut:
    return schemas.StudentOut(
        id=s.id,
        first_name=s.first_name,
        last_name=s.last_name,
        phone=s.phone,
        type=s.type,
        class_name=s.class_name,
        subject_name=s.subject_name,
        teacher_name=s.teacher_name,
        group_label=s.group_label,
        added_by=s.added_by,
        added_at=s.added_at.strftime("%d.%m.%Y %H:%M:%S") if s.added_at else "",
    )


@router.get("", response_model=List[schemas.StudentOut])
def list_students(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    students = db.query(models.Student).order_by(models.Student.id).all()
    return [_student_to_out(s) for s in students]


@router.post("", response_model=schemas.StudentOut)
def create_student(
    payload: schemas.StudentIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if payload.type not in ("school", "repetitor"):
        raise HTTPException(status_code=400, detail="O'quvchi turi noto'g'ri!")

    student = models.Student(
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        phone=payload.phone.strip(),
        type=payload.type,
        added_by=current_user.username,
    )

    if payload.type == "school":
        if not payload.class_name:
            raise HTTPException(status_code=400, detail="Sinfni tanlang!")
        student.class_name = payload.class_name
    else:
        if not payload.teacher_id or not payload.group_id:
            raise HTTPException(status_code=400, detail="O'qituvchi va guruhni tanlang!")
        teacher = db.query(models.Teacher).filter(models.Teacher.id == payload.teacher_id).first()
        group = db.query(models.Group).filter(models.Group.id == payload.group_id).first()
        if not teacher or not group or group.teacher_id != teacher.id:
            raise HTTPException(status_code=400, detail="O'qituvchi yoki guruh topilmadi!")
        student.subject_name = teacher.subject.name
        student.teacher_name = teacher.name
        student.group_label = format_group_label(group)

    db.add(student)
    db.commit()
    db.refresh(student)
    return _student_to_out(student)


@router.delete("/{student_id}")
def delete_student(
    student_id: int,
    current_user: models.User = Depends(auth.get_current_user),
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
    current_user: models.User = Depends(auth.get_current_user),
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
                student.subject_name = teacher.subject.name
                student.teacher_name = teacher.name
                student.group_label = format_group_label(group)

            db.add(student)
            created += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"Qator {i + 1}: {e}")

    db.commit()
    return {"created": created, "errors": errors}
