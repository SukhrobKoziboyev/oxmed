"""YANGI BO'LIM: O'qituvchining shaxsiy kabineti (mobil "profil" ko'rinishi).

O'qituvchi rahbar bergan login/parol bilan kirganda shu endpointlar orqali
o'zining: hozir olishi kerak bo'lgan summasini, nechta o'quvchisi borligini,
nechtasi shu oy to'lov qilgan/qilmaganini ko'radi. Login/parolni o'zgartirish
uchun umumiy /api/auth/change-my-credentials ishlatiladi (u current_user'ga
bog'liq, rol qanday bo'lishidan qat'iy nazar ishlaydi)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..utils import current_uz_month_name

router = APIRouter(prefix="/api/teacher", tags=["teacher-self"])


@router.get("/dashboard", response_model=schemas.TeacherDashboardOut)
def teacher_dashboard(
    current_user: models.User = Depends(auth.require_teacher),
    db: Session = Depends(get_db),
):
    teacher = db.query(models.Teacher).filter(models.Teacher.id == current_user.teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")

    percent = teacher.percent_override if teacher.percent_override is not None else teacher.subject.repetitor_percent
    current_month = current_uz_month_name()

    allocated_sum = sum(
        a[0] for a in db.query(models.PaymentAllocation.amount)
        .filter(models.PaymentAllocation.teacher_id == teacher.id).all()
    )
    payouts_sum = sum(
        p[0] for p in db.query(models.TeacherPayout.amount)
        .filter(models.TeacherPayout.teacher_id == teacher.id).all()
    )

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
        owed=allocated_sum - payouts_sum,
        current_month=current_month,
        students=students_out,
    )
