import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas, auth
from ..database import get_db
from ..utils import format_group_label, now_timestamp_ms, now_uz_datestring

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("", response_model=schemas.BackupOut)
def get_backup(
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    subjects = [s.name for s in db.query(models.Subject).all()]

    teachers_by_subject: dict = {}
    for subject in db.query(models.Subject).options(joinedload(models.Subject.teachers).joinedload(models.Teacher.groups)):
        teachers_by_subject[subject.name] = [
            {
                "name": t.name,
                "groups": [
                    {"id": g.id, "dayType": g.day_type, "start": g.start_time, "end": g.end_time}
                    for g in t.groups
                ],
            }
            for t in subject.teachers
        ]

    students = []
    for s in db.query(models.Student).all():
        students.append({
            "firstName": s.first_name, "lastName": s.last_name, "phone": s.phone,
            "type": s.type, "class": s.class_name, "subject": s.subject_name,
            "teacher": s.teacher_name, "group": s.group_label,
            "addedBy": s.added_by,
            "addedDate": s.added_at.strftime("%d.%m.%Y %H:%M:%S") if s.added_at else "",
        })

    payments = []
    for p in db.query(models.Payment).all():
        payments.append({
            "studentName": p.student_name, "studentPhone": p.student_phone,
            "studentType": p.student_type, "subject": p.subject_name,
            "teacher": p.teacher_name, "group": p.group_label, "class": p.class_name,
            "month": p.month, "amount": p.amount, "method": p.method, "date": p.date_str,
            "timestamp": p.timestamp, "addedBy": p.added_by,
        })

    settings = db.query(models.Settings).first()
    phones = [p.phone for p in db.query(models.RahbarPhone).all()]

    return schemas.BackupOut(
        subjects=subjects,
        teachers=teachers_by_subject,
        students=students,
        payments=payments,
        sms_template_parent=settings.sms_template_parent,
        sms_template_rahbar=settings.sms_template_rahbar,
        rahbar_phones=phones,
        backup_date=now_uz_datestring(),
    )


@router.post("/restore")
def restore_backup(
    payload: dict,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    """To'liq zaxira faylidan (frontend'da yuklab olingan JSON) qayta tiklaydi.
    Diqqat: bu amal hozirgi barcha o'quvchi/to'lov/o'qituvchi ma'lumotlarini
    o'chirib, zaxiradagilar bilan almashtiradi."""

    students = payload.get("students", [])
    payments = payload.get("payments", [])
    teachers = payload.get("teachers", {})
    subjects = payload.get("subjects", [])

    db.query(models.Payment).delete()
    db.query(models.Student).delete()
    db.query(models.Group).delete()
    # v8.4: xodimlar (is_staff) zaxiradan tiklashda o'chirilmaydi - ular fanlarga bog'liq emas
    db.query(models.Teacher).filter(models.Teacher.is_staff.is_(False)).delete(synchronize_session=False)
    db.query(models.Subject).delete()
    db.commit()

    subject_objs = {}
    for name in subjects:
        subj = models.Subject(name=name)
        db.add(subj)
        db.flush()
        subject_objs[name] = subj

    for subject_name, teacher_list in teachers.items():
        subj = subject_objs.get(subject_name)
        if not subj:
            subj = models.Subject(name=subject_name)
            db.add(subj)
            db.flush()
            subject_objs[subject_name] = subj
        for t in teacher_list:
            teacher = models.Teacher(subject_id=subj.id, name=t.get("name", ""))
            db.add(teacher)
            db.flush()
            for g in t.get("groups", []):
                db.add(models.Group(
                    teacher_id=teacher.id,
                    day_type=g.get("dayType", "toq"),
                    start_time=g.get("start", "08:00"),
                    end_time=g.get("end", "10:00"),
                ))

    for s in students:
        db.add(models.Student(
            first_name=s.get("firstName", ""), last_name=s.get("lastName", ""),
            phone=s.get("phone", ""), type=s.get("type", "school"),
            class_name=s.get("class"), subject_name=s.get("subject"),
            teacher_name=s.get("teacher"), group_label=s.get("group"),
            added_by=s.get("addedBy", current_user.username),
        ))

    for p in payments:
        db.add(models.Payment(
            student_name=p.get("studentName", ""), student_phone=p.get("studentPhone", ""),
            student_type=p.get("studentType", "school"), subject_name=p.get("subject"),
            teacher_name=p.get("teacher"), group_label=p.get("group"), class_name=p.get("class"),
            month=p.get("month", ""), amount=p.get("amount", 0),
            method=p.get("method", "naxt"),
            date_str=p.get("date", ""), timestamp=p.get("timestamp", 0),
            added_by=p.get("addedBy", current_user.username),
        ))

    if payload.get("smsTemplateParent") or payload.get("smsTemplateRahbar"):
        settings = db.query(models.Settings).first()
        if payload.get("smsTemplateParent"):
            settings.sms_template_parent = payload["smsTemplateParent"]
        if payload.get("smsTemplateRahbar"):
            settings.sms_template_rahbar = payload["smsTemplateRahbar"]

    if payload.get("rahbarPhones"):
        db.query(models.RahbarPhone).delete()
        for phone in payload["rahbarPhones"]:
            db.add(models.RahbarPhone(phone=phone))

    db.commit()
    return {"ok": True, "studentsRestored": len(students), "paymentsRestored": len(payments)}


@router.post("/clear-all")
def clear_all_data(
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    students_count = db.query(models.Student).count()
    payments_count = db.query(models.Payment).count()
    teachers_count = db.query(models.Teacher).filter(models.Teacher.is_staff.is_(False)).count()

    # Tozalashdan oldingi holatni recycle bin'ga saqlaymiz (7 kun ichida tiklash uchun)
    snapshot = {
        "students": [
            {"firstName": s.first_name, "lastName": s.last_name, "phone": s.phone, "type": s.type,
             "class": s.class_name, "subject": s.subject_name, "teacher": s.teacher_name,
             "group": s.group_label, "addedBy": s.added_by}
            for s in db.query(models.Student).all()
        ],
        "payments": [
            {"studentName": p.student_name, "studentPhone": p.student_phone, "studentType": p.student_type,
             "subject": p.subject_name, "teacher": p.teacher_name, "group": p.group_label,
             "class": p.class_name, "month": p.month, "amount": p.amount, "date": p.date_str,
             "timestamp": p.timestamp, "addedBy": p.added_by}
            for p in db.query(models.Payment).all()
        ],
        "studentsCount": students_count,
        "paymentsCount": payments_count,
        "teachersCount": teachers_count,
    }

    db.add(models.RecycleBinItem(
        type="allData",
        data=snapshot,
        deleted_at=now_timestamp_ms(),
        deleted_by=current_user.username,
    ))

    db.query(models.Payment).delete()
    db.query(models.Student).delete()
    db.query(models.Group).delete()
    # subjects saqlanib qoladi, faqat o'qituvchi+guruhlar tozalanadi; v8.4: xodimlar (is_staff) ham saqlanadi
    db.query(models.Teacher).filter(models.Teacher.is_staff.is_(False)).delete(synchronize_session=False)
    db.commit()

    return {
        "ok": True,
        "studentsCount": students_count,
        "paymentsCount": payments_count,
        "teachersCount": teachers_count,
    }
