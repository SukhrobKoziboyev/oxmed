"""v12.0: YO'QLAMA (davomat).

* O'qituvchi — faqat o'z guruhlari va o'quvchilari; yo'qlamani faqat SHU KUNI kiritadi/tuzatadi.
* Admin va rahbar — hamma guruhlar; istalgan (o'tgan) kunni kiritadi/tuzatadi. Kelajak sana — yo'q.
* Guruhdagi o'quvchilar = o'qituvchining "O'quvchilarim" ro'yxatidagi (asosiy + biriktirilgan) shu guruh yorlig'idagilar.
* Holat: 'present' (keldi) | 'absent' (kelmadi) + ixtiyoriy sabab (sabab yozilgan bo'lsa — "sababli").
Hisob-kitob (to'lov, ulush, kassa, balans) bilan HECH QANDAY aloqasi yo'q — alohida jadvallar.
"""
import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models, auth
from ..database import get_db
from ..utils import format_group_label, now_timestamp_ms, now_uz, ts_to_uz_datestring
from .teacher_self import my_students

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

WEEKDAYS = {"toq": {0, 2, 4}, "juft": {1, 3, 5}, "harkuni": {0, 1, 2, 3, 4, 5}}
STATUSES = ("present", "absent")
UZ_WEEK = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]


def _today() -> str:
    return now_uz().strftime("%Y-%m-%d")


def _parse_date(s: Optional[str]) -> str:
    s = (s or "").strip()[:10] or _today()
    try:
        d = datetime.date.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=400, detail="Sana noto'g'ri!")
    if s > _today():
        raise HTTPException(status_code=400, detail="Kelajakdagi kun uchun yo'qlama qilib bo'lmaydi!")
    return d.isoformat()


def _is_staff(user: models.User) -> bool:
    return user.role in ("Markaz rahbari", "Administrator")


def _visible_groups(db: Session, user: models.User) -> List[models.Group]:
    q = db.query(models.Group).join(models.Teacher, models.Teacher.id == models.Group.teacher_id).filter(models.Teacher.is_staff.is_(False))
    if _is_staff(user):
        return q.order_by(models.Group.start_time).all()
    if user.role == "O'qituvchi" and user.teacher_id:
        return q.filter(models.Group.teacher_id == user.teacher_id).order_by(models.Group.start_time).all()
    raise HTTPException(status_code=403, detail="Ruxsat yo'q!")


def _get_group(db: Session, user: models.User, gid: int) -> models.Group:
    g = db.query(models.Group).filter(models.Group.id == gid).first()
    if not g:
        raise HTTPException(status_code=404, detail="Guruh topilmadi!")
    if not _is_staff(user) and not (user.role == "O'qituvchi" and user.teacher_id == g.teacher_id):
        raise HTTPException(status_code=403, detail="Bu guruh sizniki emas!")
    return g


def group_students(db: Session, g: models.Group) -> List[models.Student]:
    t = db.query(models.Teacher).filter(models.Teacher.id == g.teacher_id).first()
    if not t:
        return []
    label = format_group_label(g)
    out = [st for st, _src, gl in my_students(db, t) if gl == label]
    out.sort(key=lambda s: (s.last_name or "", s.first_name or ""))
    return out


def _scheduled(g: models.Group, date: str) -> bool:
    return datetime.date.fromisoformat(date).weekday() in WEEKDAYS.get(g.day_type, set())


STAFF_EDIT_DAYS = 3   # admin/rahbar: bugun + oxirgi 3 kun; undan eskisi qulflanadi (faqat ko'rish)


def _can_edit(user: models.User, date: str) -> bool:
    if _is_staff(user):
        return date >= (now_uz().date() - datetime.timedelta(days=STAFF_EDIT_DAYS)).isoformat()
    return date == _today()


def _edit_denied(user: models.User) -> str:
    if _is_staff(user):
        return f"{STAFF_EDIT_DAYS} kundan eski yo'qlamani kiritib yoki o'zgartirib bo'lmaydi!"
    return "O'tgan kunlar yo'qlamasini faqat admin yoki rahbar o'zgartira oladi!"


def _who(db: Session, username: Optional[str]) -> str:
    if not username:
        return ""
    from ..student_links import who_label
    return who_label(db, username)


# ------------------------------------------------------------------ guruhlar (kun bo'yicha)
@router.get("/groups")
def list_groups(date: Optional[str] = None, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    date = _parse_date(date)
    groups = _visible_groups(db, current_user)
    sessions = {s.group_id: s for s in db.query(models.AttendanceSession).filter(models.AttendanceSession.date == date).all()}
    out = []
    for g in groups:
        t = g.teacher
        studs = group_students(db, g)
        s = sessions.get(g.id)
        info = None
        if s:
            marks = db.query(models.AttendanceMark).filter(models.AttendanceMark.session_id == s.id).all()
            info = {"present": sum(1 for m in marks if m.status == "present"), "absent": sum(1 for m in marks if m.status == "absent"),
                    "by": _who(db, s.updated_by or s.created_by), "at": ts_to_uz_datestring(s.updated_at or s.created_at)}
        out.append({
            "id": g.id, "label": format_group_label(g), "day_type": g.day_type, "start": g.start_time, "end": g.end_time,
            "teacher_id": t.id if t else None, "teacher_name": t.name if t else "", "subject": t.subject.name if t and t.subject else "",
            "students": len(studs), "scheduled": _scheduled(g, date), "session": info,
        })
    d = datetime.date.fromisoformat(date)
    return {"date": date, "today": _today(), "weekday": UZ_WEEK[d.weekday()], "groups": out, "can_edit": _can_edit(current_user, date),
            "edit_days": STAFF_EDIT_DAYS if _is_staff(current_user) else 0}


# ------------------------------------------------------------------ bitta dars: ko'rish / saqlash
@router.get("/session")
def get_session(group_id: int, date: Optional[str] = None, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    date = _parse_date(date)
    g = _get_group(db, current_user, group_id)
    s = db.query(models.AttendanceSession).filter(models.AttendanceSession.group_id == g.id, models.AttendanceSession.date == date).first()
    marks = {}
    if s:
        marks = {m.student_id: m for m in db.query(models.AttendanceMark).filter(models.AttendanceMark.session_id == s.id).all()}
    studs = group_students(db, g)
    ids = {st.id for st in studs}
    # avval belgilangan, lekin endi guruhda bo'lmagan o'quvchilar ham ko'rinsin (tarix buzilmasin)
    for sid in marks:
        if sid not in ids:
            st = db.query(models.Student).filter(models.Student.id == sid).first()
            if st:
                studs.append(st)
    t = g.teacher
    return {
        "group": {"id": g.id, "label": format_group_label(g), "teacher_name": t.name if t else "", "subject": t.subject.name if t and t.subject else ""},
        "date": date, "today": _today(), "can_edit": _can_edit(current_user, date), "scheduled": _scheduled(g, date),
        "session": {"by": _who(db, s.created_by), "at": ts_to_uz_datestring(s.created_at),
                    "updated_by": _who(db, s.updated_by) if s.updated_by else None,
                    "updated_at": ts_to_uz_datestring(s.updated_at) if s.updated_at else None} if s else None,
        "students": [{"id": st.id, "first_name": st.first_name, "last_name": st.last_name, "phone": st.phone,
                      "status": marks[st.id].status if st.id in marks else None,
                      "reason": marks[st.id].reason if st.id in marks else None} for st in studs],
    }


class MarkIn(BaseModel):
    student_id: int
    status: str
    reason: Optional[str] = Field(None, max_length=200)


class SessionIn(BaseModel):
    group_id: int
    date: Optional[str] = None
    marks: List[MarkIn]


@router.post("/session")
def save_session(data: SessionIn, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    date = _parse_date(data.date)
    g = _get_group(db, current_user, data.group_id)
    if not _can_edit(current_user, date):
        raise HTTPException(status_code=403, detail=_edit_denied(current_user))
    allowed = {st.id for st in group_students(db, g)}
    s = db.query(models.AttendanceSession).filter(models.AttendanceSession.group_id == g.id, models.AttendanceSession.date == date).with_for_update().first()
    if s:
        allowed |= {m.student_id for m in db.query(models.AttendanceMark).filter(models.AttendanceMark.session_id == s.id).all()}
    if not data.marks:
        raise HTTPException(status_code=400, detail="Guruhda o'quvchi yo'q!")
    seen = set()
    for m in data.marks:
        if m.status not in STATUSES:
            raise HTTPException(status_code=400, detail="Holat noto'g'ri!")
        if m.student_id not in allowed:
            raise HTTPException(status_code=400, detail="Bu o'quvchi shu guruhda emas!")
        if m.student_id in seen:
            raise HTTPException(status_code=400, detail="Bitta o'quvchi ikki marta belgilangan!")
        seen.add(m.student_id)
    missing = allowed - seen
    if missing and not s:
        raise HTTPException(status_code=400, detail=f"Hamma o'quvchini belgilang ({len(missing)} ta qoldi)")
    now = now_timestamp_ms()
    if not s:
        s = models.AttendanceSession(group_id=g.id, teacher_id=g.teacher_id, date=date, group_label=format_group_label(g),
                                     created_by=current_user.username, created_at=now)
        db.add(s)
        db.flush()
    else:
        s.updated_by, s.updated_at = current_user.username, now
    existing = {m.student_id: m for m in db.query(models.AttendanceMark).filter(models.AttendanceMark.session_id == s.id).all()}
    for m in data.marks:
        reason = " ".join((m.reason or "").split()) or None
        if m.status == "present":
            reason = None
        row = existing.get(m.student_id)
        if row:
            row.status, row.reason = m.status, reason
        else:
            db.add(models.AttendanceMark(session_id=s.id, student_id=m.student_id, status=m.status, reason=reason))
    db.commit()
    present = sum(1 for m in data.marks if m.status == "present")
    return {"ok": True, "present": present, "absent": len(data.marks) - present}


# ------------------------------------------------------------------ hisobot: guruh x oy
@router.get("/report")
def group_report(group_id: int, month: Optional[str] = None, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    g = _get_group(db, current_user, group_id)
    month = (month or _today()[:7])[:7]
    sessions = (db.query(models.AttendanceSession).filter(models.AttendanceSession.group_id == g.id,
                models.AttendanceSession.date.like(month + "-%")).order_by(models.AttendanceSession.date).all())
    marks = {}
    if sessions:
        for m in db.query(models.AttendanceMark).filter(models.AttendanceMark.session_id.in_([s.id for s in sessions])).all():
            marks[(m.session_id, m.student_id)] = m
    studs = group_students(db, g)
    ids = {st.id for st in studs}
    for (_sid, stid) in marks:
        if stid not in ids:
            st = db.query(models.Student).filter(models.Student.id == stid).first()
            if st:
                studs.append(st); ids.add(stid)
    rows, tot_p, tot_all = [], 0, 0
    for st in studs:
        cells, p, a, ex = [], 0, 0, 0
        for s in sessions:
            m = marks.get((s.id, st.id))
            if not m:
                cells.append(None); continue
            cells.append({"s": m.status, "r": m.reason})
            if m.status == "present":
                p += 1
            else:
                a += 1
                if m.reason:
                    ex += 1
        n = p + a
        tot_p += p; tot_all += n
        rows.append({"id": st.id, "name": f"{st.last_name} {st.first_name}", "phone": st.phone, "cells": cells,
                     "present": p, "absent": a, "excused": ex, "percent": round(p * 100 / n) if n else None})
    return {"group": {"id": g.id, "label": format_group_label(g), "teacher_name": g.teacher.name if g.teacher else ""},
            "month": month, "dates": [s.date for s in sessions], "students": rows,
            "percent": round(tot_p * 100 / tot_all) if tot_all else None}


# ------------------------------------------------------------------ xavfli: ketma-ket 3 dars qoldirganlar
@router.get("/risk")
def risk_list(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    out = []
    for g in _visible_groups(db, current_user):
        sessions = (db.query(models.AttendanceSession).filter(models.AttendanceSession.group_id == g.id)
                    .order_by(models.AttendanceSession.date.desc()).limit(10).all())
        if len(sessions) < 3:
            continue
        sids = [s.id for s in sessions]
        marks = {}
        for m in db.query(models.AttendanceMark).filter(models.AttendanceMark.session_id.in_(sids)).all():
            marks[(m.session_id, m.student_id)] = m.status
        for st in group_students(db, g):
            streak = 0
            for s in sessions:   # eng yangisidan orqaga
                stt = marks.get((s.id, st.id))
                if stt is None:
                    continue
                if stt == "absent":
                    streak += 1
                else:
                    break
            if streak >= 3:
                out.append({"student_id": st.id, "name": f"{st.last_name} {st.first_name}", "phone": st.phone,
                            "group_id": g.id, "group": format_group_label(g), "teacher_name": g.teacher.name if g.teacher else "",
                            "streak": streak})
    out.sort(key=lambda r: -r["streak"])
    return out


# ------------------------------------------------------------------ o'quvchi kartasi uchun (rahbar/admin)
@router.get("/student/{student_id}")
def student_summary(student_id: int, current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    rows = (db.query(models.AttendanceMark, models.AttendanceSession)
            .join(models.AttendanceSession, models.AttendanceSession.id == models.AttendanceMark.session_id)
            .filter(models.AttendanceMark.student_id == student_id).order_by(models.AttendanceSession.date.desc()).all())
    p = sum(1 for m, _ in rows if m.status == "present")
    a = len(rows) - p
    return {"present": p, "absent": a, "percent": round(p * 100 / len(rows)) if rows else None,
            "last": [{"date": s.date, "status": m.status, "reason": m.reason, "group": s.group_label} for m, s in rows[:8]]}


# ------------------------------------------------------------------ v12.2: STATISTIKA (o'qituvchi — o'ziniki, admin/rahbar — hammasi)
def _scoped_marks(db: Session, user: models.User, month: Optional[str], teacher_id: Optional[int] = None,
                  group_id: Optional[int] = None, student_id: Optional[int] = None):
    q = (db.query(models.AttendanceMark, models.AttendanceSession, models.Group)
         .join(models.AttendanceSession, models.AttendanceSession.id == models.AttendanceMark.session_id)
         .join(models.Group, models.Group.id == models.AttendanceSession.group_id))
    if not _is_staff(user):
        if user.role != "O'qituvchi" or not user.teacher_id:
            raise HTTPException(status_code=403, detail="Ruxsat yo'q!")
        q = q.filter(models.Group.teacher_id == user.teacher_id)
    elif teacher_id:
        q = q.filter(models.Group.teacher_id == teacher_id)
    if group_id:
        q = q.filter(models.Group.id == group_id)
    if student_id:
        q = q.filter(models.AttendanceMark.student_id == student_id)
    if month and month != "all":
        q = q.filter(models.AttendanceSession.date.like(month[:7] + "-%"))
    return q.order_by(models.AttendanceSession.date.desc()).all()


def _teacher_info(db: Session, ids):
    out = {}
    for t in db.query(models.Teacher).filter(models.Teacher.id.in_(list(ids) or [0])).all():
        out[t.id] = {"name": t.name, "subject": t.subject.name if t.subject else ""}
    return out


@router.get("/stats")
def stats(month: Optional[str] = None, teacher_id: Optional[int] = None, group_id: Optional[int] = None,
          current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    month = month or _today()[:7]
    rows = _scoped_marks(db, current_user, month, teacher_id, group_id)
    tinfo = _teacher_info(db, {g.teacher_id for _, _, g in rows})
    per, sessions = {}, set()
    for m, s, g in rows:
        sessions.add(s.id)
        r = per.setdefault(m.student_id, {"student_id": m.student_id, "present": 0, "absent": 0, "excused": 0, "last_absent": None, "groups": {}})
        if m.status == "present":
            r["present"] += 1
        else:
            r["absent"] += 1
            if m.reason:
                r["excused"] += 1
            if not r["last_absent"] or s.date > r["last_absent"]:
                r["last_absent"] = s.date
        ti = tinfo.get(g.teacher_id, {})
        r["groups"][g.id] = {"teacher": ti.get("name", ""), "subject": ti.get("subject", ""), "group": format_group_label(g)}
    studs = {st.id: st for st in db.query(models.Student).filter(models.Student.id.in_(list(per) or [0])).all()}
    out = []
    for sid, r in per.items():
        st = studs.get(sid)
        if not st:
            continue
        n = r["present"] + r["absent"]
        r.update({"name": f"{st.last_name} {st.first_name}", "phone": st.phone, "percent": round(r["present"] * 100 / n) if n else None,
                  "total": n, "groups": list(r["groups"].values())})
        out.append(r)
    out.sort(key=lambda r: (-r["absent"], r["name"]))
    tp = sum(r["present"] for r in out); tn = sum(r["total"] for r in out)
    teachers = []
    if _is_staff(current_user):
        for t in (db.query(models.Teacher).join(models.Group, models.Group.teacher_id == models.Teacher.id)
                  .filter(models.Teacher.is_staff.is_(False)).distinct().order_by(models.Teacher.name).all()):
            teachers.append({"id": t.id, "name": t.name, "subject": t.subject.name if t.subject else ""})
    return {"month": month, "today": _today(), "lessons": len(sessions), "students": out, "teachers": teachers,
            "present": tp, "absent": tn - tp, "percent": round(tp * 100 / tn) if tn else None}


@router.get("/student-detail/{student_id}")
def student_detail(student_id: int, month: Optional[str] = None, current_user: models.User = Depends(auth.get_current_user),
                   db: Session = Depends(get_db)):
    st = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")
    rows = _scoped_marks(db, current_user, month or "all", student_id=student_id)
    if not _is_staff(current_user) and not rows:
        t = db.query(models.Teacher).filter(models.Teacher.id == current_user.teacher_id).first()
        if not t or student_id not in {x.id for x, _s, _g in my_students(db, t)}:
            raise HTTPException(status_code=403, detail="Bu o'quvchi sizda o'qimaydi!")
    tinfo = _teacher_info(db, {g.teacher_id for _, _, g in rows})
    items = []
    for m, s, g in rows:
        d = datetime.date.fromisoformat(s.date)
        ti = tinfo.get(g.teacher_id, {})
        items.append({"date": s.date, "weekday": UZ_WEEK[d.weekday()], "status": m.status, "reason": m.reason,
                      "teacher": ti.get("name", ""), "subject": ti.get("subject", ""), "group": format_group_label(g),
                      "by": _who(db, s.updated_by or s.created_by)})
    p = sum(1 for i in items if i["status"] == "present"); a = len(items) - p
    return {"student": {"id": st.id, "name": f"{st.last_name} {st.first_name}", "phone": st.phone, "phone2": getattr(st, "phone2", None)},
            "month": month or "all", "items": items, "present": p, "absent": a,
            "excused": sum(1 for i in items if i["status"] == "absent" and i["reason"]),
            "percent": round(p * 100 / len(items)) if items else None}
