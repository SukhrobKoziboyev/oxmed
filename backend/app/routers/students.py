from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..utils import format_group_label, now_timestamp_ms, utc_naive_to_uz_string
from ..student_links import find_duplicates, canon, phone9, duplicate_pairs, student_teachers, who_label
from ..utils import ts_to_uz_datestring
from ..audit import note as audit_note, money as _m

router = APIRouter(prefix="/api/students", tags=["students"])


def _stu_where(s: models.Student) -> str:
    if s.type == "school":
        return f"maktab, {s.class_name or ''}".strip(", ")
    return ", ".join(x for x in ("repetitor", s.subject_name, s.teacher_name, s.group_label) if x)


def _stu_snap(s: models.Student) -> dict:
    return {"Ism": s.first_name, "Familiya": s.last_name, "Telefon": s.phone, "Qo'shimcha telefon": s.phone2 or "",
            "Turi": "Maktab" if s.type == "school" else "Repetitor", "Sinf / fan": _stu_where(s)}


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
        returned_at=ts_to_uz_datestring(s.returned_at) if getattr(s, "returned_at", None) else None,
    )


@router.get("", response_model=List[schemas.StudentOut])
def list_students(
    current_user: models.User = Depends(auth.require_perm('pay', 'hist', 'bt', 'students', 'sms')),  # v10.9: o'qituvchi hammani ko'rmasin
    db: Session = Depends(get_db),
):
    # v12.5: arxivdagi (markazdan ketgan) o'quvchilar umumiy ro'yxatda chiqmaydi — /api/students/archived da
    students = db.query(models.Student).filter(models.Student.archived_at.is_(None)).order_by(models.Student.id).all()
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
    current_user: models.User = Depends(auth.require_perm('students')),  # v10.4: o'qituvchi /api/teacher/students orqali qo'shadi
    db: Session = Depends(get_db),
):
    if payload.type not in ("school", "repetitor"):
        raise HTTPException(status_code=400, detail="O'quvchi turi noto'g'ri!")
    if not payload.first_name.strip() or not payload.last_name.strip() or not payload.phone.strip():
        raise HTTPException(status_code=400, detail="Ism, familiya va telefon raqamini kiriting!")
    # v10.9: bitta o'quvchi bazada bir marta — bir xil ism-familiyali o'quvchi bo'lsa, avval so'raymiz
    # v11.8: aqlli o'xshashlik (Ahmad = Axmad). Ism VA telefon bir xil bo'lsa — baribir qo'shib bo'lmaydi.
    dups = find_duplicates(db, payload.first_name, payload.last_name, payload.phone)
    arch = [d for d in dups if d.get("archived") and d["exact_same"]]
    if arch:  # v12.5: shu o'quvchi arxivda — yangisini emas, arxivdan qaytarishni taklif qilamiz
        _a = db.query(models.Student).filter(models.Student.id == arch[0]["id"]).first()
        _w = "bitirganlar ro'yxatida" if (_a and _a.archive_kind == "graduated") else "markazdan ketgan"   # v13.11
        raise HTTPException(status_code=409, detail={"code": "archived_student", "student_id": arch[0]["id"], "name": arch[0]["name"],
                                                     "message": f"{arch[0]['name']} arxivda ({_w}). Arxivdan qaytarasizmi?"})
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
            audit_note(f"O'quvchi qo'shdi: {student.last_name} {student.first_name} ({_stu_where(student)}), tel {student.phone}",
                       cat="stu", entity="student", entity_id=student.id, details=_stu_snap(student))
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
    audit_note(f"O'quvchi qo'shdi: {student.last_name} {student.first_name} ({_stu_where(student)}), tel {student.phone}",
               cat="stu", entity="student", entity_id=student.id, details=_stu_snap(student))
    return _student_to_out(student)


@router.put("/{student_id}", response_model=schemas.StudentOut)
def edit_student(
    student_id: int,
    payload: schemas.StudentEditIn,
    current_user: models.User = Depends(auth.require_perm('students', 'pay', 'bt', 'hist')),
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
    _before = _stu_snap(student)

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
    _after = _stu_snap(student)
    _chg = [f"{k}: {_before[k] or '—'} → {_after[k] or '—'}" for k in _before if _before[k] != _after[k]]
    audit_note(f"O'quvchi ma'lumotini tahrirladi: {student.last_name} {student.first_name} — " + ("; ".join(_chg) if _chg else "o'zgarishsiz"),
               cat="stu", entity="student", entity_id=student.id, details={"Oldin": _before, "Keyin": _after})
    return _student_to_out(student)


# =====================================================================
# v12.5: ARXIV — markazdan ketgan o'quvchilar. O'quvchi O'CHIRILMAYDI: to'lovlari, ulushlar, qarz, yo'qlama
# tarixi joyida qoladi (kassa va o'qituvchi balansi o'zgarmaydi). Faqat ro'yxatlardan yashiriladi.
# =====================================================================
class ArchiveIn(BaseModel):
    reason: str = ""
    kind: str = "left"   # v13.11: 'left' (markazdan ketdi) | 'graduated' (bitirdi)


def _ym_label(p) -> str:
    """v13.11: 'Noyabr 2026' (yil bo'lmasa — faqat oy)."""
    return f"{p.month} {p.year}" if getattr(p, "year", None) else p.month


def _ym_key(p):
    from ..utils import UZ_MONTHS
    mi = UZ_MONTHS.index(p.month) if p.month in UZ_MONTHS else 0
    return ((p.year or 0), mi)


def _payments_of(db: Session, st: models.Student):
    full = f"{st.first_name} {st.last_name}"
    from sqlalchemy import or_, and_
    return (db.query(models.Payment).filter(or_(models.Payment.student_id == st.id,
            and_(models.Payment.student_id.is_(None), models.Payment.student_name == full)))
            .order_by(models.Payment.timestamp.desc()).all())


@router.post("/{student_id}/archive")
def archive_student(student_id: int, payload: ArchiveIn, current_user: models.User = Depends(auth.require_perm('students')),
                    db: Session = Depends(get_db)):
    st = db.query(models.Student).filter(models.Student.id == student_id).with_for_update().first()
    if not st:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")
    if st.archived_at is not None:
        raise HTTPException(status_code=400, detail="Bu o'quvchi allaqachon arxivda!")
    kind = payload.kind if payload.kind in ("left", "graduated") else "left"
    reason = " ".join((payload.reason or "").split())[:200] or None
    now = now_timestamp_ms()
    snap = student_teachers(db, st)
    for t in snap:  # guruhini ham eslab qolamiz
        if st.teacher_name == t["name"] and st.subject_name == t["subject"]:
            t["group"] = st.group_label
        link = db.query(models.StudentTeacher).filter(models.StudentTeacher.student_id == st.id, models.StudentTeacher.teacher_id == t["id"]).first()
        if link and link.group_label:
            t["group"] = link.group_label
    st.archived_at, st.archived_by, st.archive_reason, st.archive_kind = now, current_user.username, reason, kind
    db.add(models.StudentArchiveLog(student_id=st.id, action=("graduate" if kind == "graduated" else "archive"), at=now,
                                    by=current_user.username, reason=reason, teachers=snap))
    audit_note((f"O'quvchini \"Bitirganlar\"ga o'tkazdi: " if kind == "graduated" else "O'quvchini arxivga o'tkazdi (markazdan ketdi): ")
               + f"{st.last_name} {st.first_name}" + (f" — sabab: {reason}" if reason else ""), cat="stu", entity="student", entity_id=st.id)
    db.commit()
    return {"ok": True, "archived_at": ts_to_uz_datestring(now)}


@router.post("/{student_id}/restore")
def restore_student(student_id: int, current_user: models.User = Depends(auth.require_perm('students')), db: Session = Depends(get_db)):
    """Arxivdan qaytarish: o'quvchi yana "Jami o'quvchilar"da, to'lov qabul qilinadi. Avvalgi o'qituvchilariga
    avtomatik QO'SHILMAYDI (boshqa fan tanlashi mumkin) — yangi to'lov ulushi kimga bo'linsa o'shanda chiqadi,
    yoki o'qituvchi o'zi ro'yxatiga qo'shib oladi. Eski to'lovlar va tarix joyida qoladi."""
    st = db.query(models.Student).filter(models.Student.id == student_id).with_for_update().first()
    if not st:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")
    if st.archived_at is None:
        raise HTTPException(status_code=400, detail="Bu o'quvchi arxivda emas!")
    now = now_timestamp_ms()
    st.archived_at = st.archived_by = st.archive_reason = st.archive_kind = None
    st.returned_at = now
    if st.type == "repetitor":
        st.teacher_name = st.subject_name = st.group_label = None
    db.query(models.StudentTeacher).filter(models.StudentTeacher.student_id == st.id).delete(synchronize_session=False)
    db.add(models.StudentArchiveLog(student_id=st.id, action="restore", at=now, by=current_user.username))
    audit_note(f"O'quvchini arxivdan qaytardi: {st.last_name} {st.first_name}", cat="stu", entity="student", entity_id=st.id)
    db.commit()
    return {"ok": True, "returned_at": ts_to_uz_datestring(now)}


@router.get("/archived")
def list_archived(kind: Optional[str] = None, current_user: models.User = Depends(auth.require_perm('students')), db: Session = Depends(get_db)):
    """v13.11: kind = 'left' (markazdan ketganlar) | 'graduated' (bitirganlar) | bo'sh — hammasi."""
    q = db.query(models.Student).filter(models.Student.archived_at.isnot(None))
    if kind == "graduated":
        q = q.filter(models.Student.archive_kind == "graduated")
    elif kind == "left":
        from sqlalchemy import or_
        q = q.filter(or_(models.Student.archive_kind.is_(None), models.Student.archive_kind != "graduated"))
    rows = q.order_by(models.Student.archived_at.desc()).all()
    who, out = {}, []
    for st in rows:
        pays = _payments_of(db, st)
        if st.archived_by not in who:
            who[st.archived_by] = who_label(db, st.archived_by)
        months = sorted({(_ym_key(p), _ym_label(p)) for p in pays})
        first_ts = min((int(p.timestamp) for p in pays if p.timestamp), default=None)
        out.append({"id": st.id, "first_name": st.first_name, "last_name": st.last_name, "phone": st.phone, "phone2": st.phone2,
                    "type": st.type, "class_name": st.class_name,
                    "archived_at": ts_to_uz_datestring(st.archived_at), "archived_ts": int(st.archived_at),
                    "archived_by": who[st.archived_by], "reason": st.archive_reason,
                    "total_paid": sum(int(p.amount) for p in pays), "payments": len(pays),
                    "last_month": _ym_label(pays[0]) if pays else None,
                    # v13.11: bitirganlar uchun — qachon kelgan, necha oy o'qigan, qaysi oylarda
                    "kind": st.archive_kind or "left",
                    "added_at": utc_naive_to_uz_string(st.added_at), "first_payment": ts_to_uz_datestring(first_ts) if first_ts else None,
                    "months": [m[1] for m in months], "months_count": len(months),
                    "teachers": sorted({a.teacher_name for p in pays for a in p.allocations if a.teacher_name})})
    return out


@router.get("/{student_id}/profile")
def student_profile(student_id: int, current_user: models.User = Depends(auth.require_perm('students', 'hist', 'bt', 'pay')), db: Session = Depends(get_db)):
    """O'quvchining to'liq tarixi (arxivdagi ham): to'lovlar (oy, sana, usul, kim kiritdi, kimga ulush), qarzlar,
    kimlarda o'qigan, arxivga tushgan/qaytgan voqealar."""
    st = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")
    pays = _payments_of(db, st)
    who = {}
    def w(u):
        if u not in who:
            who[u] = who_label(db, u) if u else ""
        return who[u]
    plist, teachers = [], {}
    for p in pays:
        allocs = [{"teacher": a.teacher_name, "subject": a.subject_name, "amount": int(a.amount)} for a in p.allocations]
        for a in p.allocations:
            teachers.setdefault((a.teacher_name, a.subject_name or ""), {"name": a.teacher_name, "subject": a.subject_name or "", "group": None, "via": "to'lov"})
        plist.append({"id": p.id, "month": p.month, "year": p.year, "label": _ym_label(p), "amount": int(p.amount), "method": p.method, "date_str": ts_to_uz_datestring(p.timestamp),
                      "added_by": w(p.added_by), "allocations": allocs})
    logs = db.query(models.StudentArchiveLog).filter(models.StudentArchiveLog.student_id == st.id).order_by(models.StudentArchiveLog.at).all()
    for lg in logs:
        for t in (lg.teachers or []):
            k = (t.get("name"), t.get("subject") or "")
            if k not in teachers or not teachers[k].get("group"):
                teachers[k] = {"name": t.get("name"), "subject": t.get("subject") or "", "group": t.get("group"), "via": "avval"}
    for t in student_teachers(db, st):
        k = (t["name"], t["subject"])
        teachers.setdefault(k, {"name": t["name"], "subject": t["subject"], "group": None, "via": "hozir"})
    if st.teacher_name and st.subject_name:
        k = (st.teacher_name, st.subject_name)
        teachers.setdefault(k, {"name": st.teacher_name, "subject": st.subject_name, "group": st.group_label, "via": "hozir"})
        if not teachers[k].get("group"):
            teachers[k]["group"] = st.group_label
    months = [m[1] for m in sorted({(_ym_key(p), _ym_label(p)) for p in pays})]   # v13.11: 'Sentabr 2026', ... (tartib bilan)
    dues = [{"month": d.month, "year": d.year, "due": int(d.due_amount)} for d in db.query(models.StudentDue).filter(models.StudentDue.student_id == st.id).all()]
    return {
        "student": {"id": st.id, "first_name": st.first_name, "last_name": st.last_name, "phone": st.phone, "phone2": st.phone2,
                    "type": st.type, "class_name": st.class_name, "added_by": w(st.added_by), "added_at": utc_naive_to_uz_string(st.added_at),
                    "archived": st.archived_at is not None, "archive_kind": (st.archive_kind or "left") if st.archived_at else None,
                    "archived_at": ts_to_uz_datestring(st.archived_at) if st.archived_at else None,
                    "archived_by": w(st.archived_by) if st.archived_by else None, "reason": st.archive_reason,
                    "returned_at": ts_to_uz_datestring(st.returned_at) if st.returned_at else None},
        "payments": plist, "total_paid": sum(p["amount"] for p in plist), "months": months,
        "teachers": list(teachers.values()), "dues": dues,
        "history": [{"action": lg.action, "at": ts_to_uz_datestring(lg.at), "by": w(lg.by), "reason": lg.reason} for lg in logs],
    }


@router.get("/duplicates")
def list_duplicates(current_user: models.User = Depends(auth.require_perm('students')), db: Session = Depends(get_db)):
    """v11.8: ikki marta yozilganga o'xshagan o'quvchilar (Jami o'quvchilar tepasida ogohlantirish)."""
    return duplicate_pairs(db)


class MergeIn(BaseModel):
    into_id: int


@router.post("/{student_id}/merge")
def merge_student(
    student_id: int,
    payload: MergeIn,
    current_user: models.User = Depends(auth.require_perm('students')),
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
        same = db.query(models.StudentDue).filter(models.StudentDue.student_id == dst.id, models.StudentDue.month == due.month,
                                                  models.StudentDue.year == due.year).first()
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
    audit_note(f"Ikki o'quvchini birlashtirdi: {src.last_name} {src.first_name} → {dst.last_name} {dst.first_name} ({moved_pay} ta to'lov o'tdi)",
               cat="stu", entity="student", entity_id=dst.id)
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
    audit_note(f"O'quvchini o'chirdi: {student.last_name} {student.first_name} ({_stu_where(student)})"
               + (f" va uning {len(related_payments)} ta to'lovi ({_m(sum(int(p.amount) for p in related_payments))} so'm)" if related_payments else "")
               + " — Qayta tiklash bo'limiga tushdi", cat="stu", entity="student", entity_id=student.id, details=_stu_snap(student))

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
