from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas, auth
from ..database import get_db
from ..utils import format_group_label

router = APIRouter(prefix="/api", tags=["teachers"])


def _teacher_to_out(teacher: models.Teacher, db: Session) -> schemas.TeacherOut:
    login_user = db.query(models.User).filter(models.User.teacher_id == teacher.id).first()
    return schemas.TeacherOut(
        id=teacher.id,
        name=teacher.name,
        subject_id=teacher.subject_id,
        subject_name=teacher.subject.name,
        groups=[
            schemas.GroupOut(
                id=g.id,
                day_type=g.day_type,
                start_time=g.start_time,
                end_time=g.end_time,
                label=format_group_label(g),
            )
            for g in teacher.groups
        ],
        percent_override=teacher.percent_override,
        has_login=login_user is not None,
        login_username=login_user.username if login_user else None,
    )


@router.get("/teachers", response_model=list[schemas.TeacherOut])
def list_teachers(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    teachers = (
        db.query(models.Teacher)
        .options(joinedload(models.Teacher.subject), joinedload(models.Teacher.groups))
        .all()
    )
    return [_teacher_to_out(t, db) for t in teachers]


@router.post("/teachers", response_model=schemas.TeacherOut)
def create_teacher(
    payload: schemas.TeacherIn,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    subject = db.query(models.Subject).filter(models.Subject.id == payload.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Fan topilmadi!")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="O'qituvchi ismini kiriting!")

    existing = db.query(models.Teacher).filter(
        models.Teacher.subject_id == subject.id, models.Teacher.name == name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu o'qituvchi allaqachon mavjud!")

    teacher = models.Teacher(subject_id=subject.id, name=name)
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return _teacher_to_out(teacher, db)


@router.delete("/teachers/{teacher_id}")
def delete_teacher(
    teacher_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")

    students_count = db.query(models.Student).filter(
        models.Student.teacher_name == teacher.name,
        models.Student.subject_name == teacher.subject.name,
    ).count()
    if students_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Bu o'qituvchida {students_count} ta o'quvchi bor! Avval ularni boshqa o'qituvchiga ko'chiring.",
        )

    db.delete(teacher)  # groups cascade orqali o'chadi
    db.commit()
    return {"ok": True}


@router.post("/teachers/{teacher_id}/groups", response_model=schemas.GroupOut)
def add_group(
    teacher_id: int,
    payload: schemas.GroupIn,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")

    if payload.day_type not in ("toq", "juft", "harkuni"):
        raise HTTPException(status_code=400, detail="Kun turi noto'g'ri!")
    if not payload.start or not payload.end:
        raise HTTPException(status_code=400, detail="Boshlanish va tugash vaqtini kiriting!")

    group = models.Group(
        teacher_id=teacher.id,
        day_type=payload.day_type,
        start_time=payload.start,
        end_time=payload.end,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return schemas.GroupOut(
        id=group.id,
        day_type=group.day_type,
        start_time=group.start_time,
        end_time=group.end_time,
        label=format_group_label(group),
    )


@router.delete("/groups/{group_id}")
def delete_group(
    group_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Guruh topilmadi!")

    label = format_group_label(group)
    teacher = group.teacher
    students_count = db.query(models.Student).filter(
        models.Student.subject_name == teacher.subject.name,
        models.Student.teacher_name == teacher.name,
        models.Student.group_label == label,
    ).count()
    if students_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Bu guruhda {students_count} ta o'quvchi bor! Avval ularni boshqa guruhga ko'chiring.",
        )

    db.delete(group)
    db.commit()
    return {"ok": True}


# ============================================================
# YANGI: HODIMLAR OYLIGI UCHUN - O'QITUVCHI FOIZI
# ============================================================

@router.put("/teachers/{teacher_id}/percent", response_model=schemas.TeacherOut)
def set_teacher_percent(
    teacher_id: int,
    payload: schemas.TeacherPercentIn,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")
    if payload.percent is not None and not (0 <= payload.percent <= 100):
        raise HTTPException(status_code=400, detail="Foiz 0 dan 100 gacha bo'lishi kerak!")
    teacher.percent_override = payload.percent
    db.commit()
    db.refresh(teacher)
    return _teacher_to_out(teacher, db)


# ============================================================
# YANGI: O'QITUVCHI SHAXSIY KABINETI UCHUN LOGIN BOSHQARUVI
# (faqat rahbar o'qituvchiga login/parol bera oladi)
# ============================================================

@router.get("/teachers/{teacher_id}/login", response_model=schemas.TeacherLoginOut)
def get_teacher_login(
    teacher_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")
    user = db.query(models.User).filter(models.User.teacher_id == teacher_id).first()
    if not user:
        return schemas.TeacherLoginOut(has_login=False)
    return schemas.TeacherLoginOut(has_login=True, username=user.username)


@router.post("/teachers/{teacher_id}/login", response_model=schemas.TeacherLoginOut)
def set_teacher_login(
    teacher_id: int,
    payload: schemas.TeacherLoginIn,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="O'qituvchi topilmadi!")

    username = payload.username.strip()
    if len(username) < 4:
        raise HTTPException(status_code=400, detail="Login kamida 4 ta belgidan iborat bo'lishi kerak!")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak!")

    existing = db.query(models.User).filter(
        models.User.username == username, models.User.teacher_id != teacher_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu login band!")

    user = db.query(models.User).filter(models.User.teacher_id == teacher_id).first()
    if user:
        user.username = username
        user.password_hash = auth.hash_password(payload.password)
    else:
        user = models.User(
            username=username,
            password_hash=auth.hash_password(payload.password),
            role="O'qituvchi",
            teacher_id=teacher_id,
        )
        db.add(user)

    db.commit()
    return schemas.TeacherLoginOut(has_login=True, username=username)


@router.delete("/teachers/{teacher_id}/login")
def remove_teacher_login(
    teacher_id: int,
    current_user: models.User = Depends(auth.require_rahbar),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.teacher_id == teacher_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Bu o'qituvchida login mavjud emas!")
    db.delete(user)
    db.commit()
    return {"ok": True}
