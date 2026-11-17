"""v12.6: MAKTAB O'QUVCHILARI YO'QLAMASI (markazga kelish).

Admin (yoki rahbar) eshik oldida telefon/kompyuterda har bir maktab o'quvchisini belgilaydi:
  * "Keldi" — shu zahoti Toshkent vaqti yoziladi; rahbar belgilagan vaqtgacha bo'lsa — VAQTIDA, keyin — KECHIKDI.
  * "Kelmadi" — sabab ixtiyoriy.
Faqat maktab o'quvchilari (type='school', arxivda emas). Fan/o'qituvchi/guruh yo'q.
Hisob-kitobga (to'lov, ulush, kassa) hech qanday aloqasi yo'q.
"""
import datetime
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models, auth
from ..database import get_db
from ..utils import now_uz, now_timestamp_ms
from ..student_links import who_label

router = APIRouter(prefix="/api/school-att", tags=["school-attendance"])

DEFAULT_DEADLINE = "08:30"
EDIT_DAYS = 3
UZ_WEEK = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _today() -> str:
    return now_uz().strftime("%Y-%m-%d")


def _date(s: Optional[str]) -> str:
    s = (s or "").strip()[:10] or _today()
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=400, detail="Sana noto'g'ri!")
    if s > _today():
        raise HTTPException(status_code=400, detail="Kelajakdagi kun uchun yo'qlama qilib bo'lmaydi!")
    return s


def _deadline(db: Session) -> str:
    st = db.query(models.Settings).first()
    d = getattr(st, "att_deadline", None) if st else None
    return d if d and _TIME.match(d) else DEFAULT_DEADLINE


def _can_edit(date: str) -> bool:
    return date >= (now_uz().date() - datetime.timedelta(days=EDIT_DAYS)).isoformat()


def _mins(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _calc(t: Optional[str], deadline: str) -> str:
    """Kelgan vaqti kelish vaqtigacha (shu daqiqa ham) — vaqtida, keyin — kechikdi."""
    return "present" if t and t <= deadline else "late"


def _day_deadline(db: Session, date: str) -> str:
    """v13.17: BIR KUN — BITTA KELISH VAQTI. Bugun — rahbarning hozirgi sozlamasi;
    o'tgan kun — o'sha kun yozuvlarida eng ko'p uchragan vaqt (yozuv bo'lmasa — hozirgi sozlama)."""
    if date == _today():
        return _deadline(db)
    cnt = {}
    for (d,) in db.query(models.SchoolAttendance.deadline).filter(models.SchoolAttendance.date == date).all():
        if d and _TIME.match(d):
            cnt[d] = cnt.get(d, 0) + 1
    return max(cnt, key=lambda k: (cnt[k], k)) if cnt else _deadline(db)


def _normalize_day(db: Session, date: str, dl: str) -> int:
    """Shu kunning hamma yozuvlarini bitta kelish vaqtiga keltiradi va vaqtida/kechikdi ni qayta hisoblaydi.
    (Avval har yozuv belgilangan paytdagi vaqtni saqlab qolardi — rahbar vaqtni o'zgartirsa, eski yozuvlar
    eski vaqt bo'yicha qolib, 08:52 "vaqtida", 08:51 "kechikdi" bo'lib ko'rinardi.)"""
    n = 0
    for a in db.query(models.SchoolAttendance).filter(models.SchoolAttendance.date == date).all():
        st = _calc(a.time, dl) if a.status in ("present", "late") else a.status
        if a.deadline != dl or a.status != st:
            a.deadline, a.status = dl, st
            n += 1
    return n


def _fix_dates(db: Session, dates) -> None:
    """Statistika/o'quvchi kunlari uchun: ko'rsatilayotgan kunlarni yagona kelish vaqtiga keltiradi."""
    if sum(_normalize_day(db, d, _day_deadline(db, d)) for d in set(dates)):
        db.commit()


def _students(db: Session):
    return (db.query(models.Student).filter(models.Student.type == "school", models.Student.archived_at.is_(None))
            .order_by(models.Student.last_name, models.Student.first_name).all())


def _row(st: models.Student, a: Optional[models.SchoolAttendance], who: dict, db: Session) -> dict:
    d = {"id": st.id, "first_name": st.first_name, "last_name": st.last_name, "class_name": st.class_name or "",
         "phone": st.phone, "status": None, "time": None, "reason": None, "late_min": 0, "by": None,
         "edited": False, "edited_by": None, "edited_at": None, "orig_status": None, "orig_time": None}
    if a:
        if a.marked_by not in who:
            who[a.marked_by] = who_label(db, a.marked_by)
        d.update({"status": a.status, "time": a.time, "reason": a.reason, "by": who[a.marked_by],
                  "late_min": max(0, _mins(a.time) - _mins(a.deadline)) if a.status == "late" and a.time and a.deadline else 0})
        if a.edited_at:
            if a.edited_by not in who:
                who[a.edited_by] = who_label(db, a.edited_by)
            d.update({"edited": True, "edited_by": who[a.edited_by], "edited_at": int(a.edited_at),
                      "orig_status": a.orig_status, "orig_time": a.orig_time})
    return d


@router.get("/settings")
def get_settings(current_user: models.User = Depends(auth.require_attendance), db: Session = Depends(get_db)):
    return {"deadline": _deadline(db)}


class SettingsIn(BaseModel):
    deadline: str


@router.put("/settings")
def set_settings(data: SettingsIn, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    if not _TIME.match(data.deadline or ""):
        raise HTTPException(status_code=400, detail="Vaqt noto'g'ri (masalan 08:30)")
    st = db.query(models.Settings).first()
    if not st:
        raise HTTPException(status_code=500, detail="Sozlamalar topilmadi")
    old = _deadline(db)
    st.att_deadline = data.deadline
    n = _normalize_day(db, _today(), data.deadline)   # v13.17: bugungi yozuvlar ham yangi vaqt bo'yicha qayta hisoblanadi
    from ..audit import note as _an
    _an(f"Darsga kelish vaqtini o'zgartirdi: {old} → {data.deadline}" + (f" (bugungi {n} ta yozuv qayta hisoblandi)" if n else ""), cat="att")
    db.commit()
    return {"deadline": data.deadline, "recalculated": n}


@router.get("/day")
def day(date: Optional[str] = None, current_user: models.User = Depends(auth.require_attendance), db: Session = Depends(get_db)):
    date = _date(date)
    dl = _day_deadline(db, date)
    if _normalize_day(db, date, dl):   # eski (v13.16 gacha) aralash yozuvlar bo'lsa — o'zi tuzaladi
        db.commit()
    marks = {a.student_id: a for a in db.query(models.SchoolAttendance).filter(models.SchoolAttendance.date == date).all()}
    who = {}
    rows = [_row(st, marks.get(st.id), who, db) for st in _students(db)]
    counts = {"total": len(rows), "present": 0, "late": 0, "absent": 0, "none": 0}
    for r in rows:
        counts[r["status"] or "none"] += 1
    return {"date": date, "today": _today(), "weekday": UZ_WEEK[datetime.date.fromisoformat(date).weekday()],
            "deadline": dl, "now": now_uz().strftime("%H:%M"),
            "can_edit": _can_edit(date), "edit_days": EDIT_DAYS, "students": rows, "counts": counts}


class MarkIn(BaseModel):
    student_id: int
    status: str                       # 'came' | 'absent' | 'clear'
    date: Optional[str] = None
    time: Optional[str] = None        # o'tgan kun yoki tuzatish uchun HH:MM
    reason: Optional[str] = Field(None, max_length=200)


@router.post("/mark")
def mark(data: MarkIn, current_user: models.User = Depends(auth.require_attendance), db: Session = Depends(get_db)):
    date = _date(data.date)
    if not _can_edit(date):
        raise HTTPException(status_code=403, detail=f"{EDIT_DAYS} kundan eski yo'qlamani o'zgartirib bo'lmaydi!")
    st = db.query(models.Student).filter(models.Student.id == data.student_id).first()
    if not st or st.type != "school":
        raise HTTPException(status_code=404, detail="Maktab o'quvchisi topilmadi!")
    if st.archived_at is not None:
        raise HTTPException(status_code=400, detail="Bu o'quvchi arxivda (markazdan ketgan)!")
    a = (db.query(models.SchoolAttendance).filter(models.SchoolAttendance.student_id == st.id, models.SchoolAttendance.date == date)
         .with_for_update().first())
    if data.status == "clear":
        if a:
            from ..audit import note as _an
            _an(f"Yo'qlama belgisini olib tashladi: {st.last_name} {st.first_name} ({st.class_name or ''}) — avval "
                + ({"present": f"vaqtida {a.time}", "late": f"kechikdi {a.time}", "absent": "kelmadi"}.get(a.status, a.status)) + f" ({date})",
                cat="att", entity="student", entity_id=st.id)
            db.delete(a)
            db.commit()
        return {"ok": True, "row": _row(st, None, {}, db)}
    if data.status not in ("came", "absent"):
        raise HTTPException(status_code=400, detail="Holat noto'g'ri!")
    deadline = _day_deadline(db, date)   # v13.17: doim shu kunning yagona kelish vaqti
    if data.status == "came":
        t = (data.time or "").strip()
        if t:
            if not _TIME.match(t):
                raise HTTPException(status_code=400, detail="Vaqt noto'g'ri (masalan 08:15)")
        elif date == _today():
            t = now_uz().strftime("%H:%M")
        else:
            raise HTTPException(status_code=400, detail="O'tgan kun uchun kelgan vaqtini kiriting!")
        if date == _today() and t > now_uz().strftime("%H:%M"):
            raise HTTPException(status_code=400, detail="Kelgan vaqti hozirgi vaqtdan keyin bo'lishi mumkin emas!")
        status, reason = _calc(t, deadline), (" ".join((data.reason or "").split()) or None)
    else:
        t, status, reason = None, "absent", (" ".join((data.reason or "").split()) or None)
    now = now_timestamp_ms()
    if not a:
        a = models.SchoolAttendance(student_id=st.id, date=date)
        db.add(a)
        a.marked_by, a.marked_at = current_user.username, now
        if data.status == "came" and (data.time or "").strip() and date == _today():
            a.edited_at, a.edited_by = now, current_user.username   # bugun vaqt qo'lda yozildi — "tahrirlangan"
    elif (a.status, a.time) != (status, t) or (a.reason or None) != reason:
        # v13.17: TAHRIRLANDI — birinchi (asl) holat saqlanadi, kim/qachon yoziladi
        if not a.orig_status:   # birinchi (asl) belgi faqat bir marta saqlanadi
            a.orig_status, a.orig_time = a.status, a.time
        a.edited_at, a.edited_by = now, current_user.username
    a.status, a.time, a.reason, a.deadline = status, t, reason, deadline
    from ..audit import note as _an
    _an(f"Yo'qlama: {st.last_name} {st.first_name} ({st.class_name or ''}) — "
        + ({"present": f"keldi {t}", "late": f"kechikib keldi {t}", "absent": "kelmadi"}[status]) + (f", sabab: {reason}" if reason else "") + f" ({date})",
        cat="att", entity="student", entity_id=st.id)
    db.commit()
    db.refresh(a)
    return {"ok": True, "row": _row(st, a, {}, db)}


class BulkAbsentIn(BaseModel):
    date: Optional[str] = None


@router.post("/absent-rest")
def absent_rest(data: BulkAbsentIn, current_user: models.User = Depends(auth.require_attendance), db: Session = Depends(get_db)):
    """Belgilanmay qolgan hamma maktab o'quvchilarini "kelmadi" deb belgilash (kun oxirida)."""
    date = _date(data.date)
    if not _can_edit(date):
        raise HTTPException(status_code=403, detail=f"{EDIT_DAYS} kundan eski yo'qlamani o'zgartirib bo'lmaydi!")
    have = {r[0] for r in db.query(models.SchoolAttendance.student_id).filter(models.SchoolAttendance.date == date).all()}
    dl, now, n = _deadline(db), now_timestamp_ms(), 0
    for st in _students(db):
        if st.id not in have:
            db.add(models.SchoolAttendance(student_id=st.id, date=date, status="absent", deadline=dl,
                                           marked_by=current_user.username, marked_at=now))
            n += 1
    db.commit()
    return {"ok": True, "count": n}


@router.get("/stats")
def stats(month: Optional[str] = None, current_user: models.User = Depends(auth.require_attendance), db: Session = Depends(get_db)):
    month = (month or _today())[:7]
    _fix_dates(db, [r[0] for r in db.query(models.SchoolAttendance.date).filter(models.SchoolAttendance.date.like(month + "-%")).distinct().all()])
    rows = db.query(models.SchoolAttendance).filter(models.SchoolAttendance.date.like(month + "-%")).all()
    per, days = {}, set()
    for a in rows:
        days.add(a.date)
        r = per.setdefault(a.student_id, {"present": 0, "late": 0, "absent": 0, "excused": 0, "late_min": 0})
        r[a.status] += 1
        if a.status == "absent" and a.reason:
            r["excused"] += 1
        if a.status == "late" and a.time and a.deadline:
            r["late_min"] += max(0, _mins(a.time) - _mins(a.deadline))
    studs = {s.id: s for s in db.query(models.Student).filter(models.Student.id.in_(list(per) or [0])).all()}
    out = []
    for sid, r in per.items():
        s = studs.get(sid)
        if not s:
            continue
        n = r["present"] + r["late"] + r["absent"]
        r.update({"id": sid, "name": f"{s.last_name} {s.first_name}", "class_name": s.class_name or "", "phone": s.phone,
                  "archived": s.archived_at is not None, "total": n,
                  "percent": round((r["present"] + r["late"]) * 100 / n) if n else None})
        out.append(r)
    out.sort(key=lambda r: (-(r["absent"] * 2 + r["late"]), r["name"]))
    tot = {k: sum(r[k] for r in out) for k in ("present", "late", "absent")}
    return {"month": month, "today": _today(), "days": len(days), "students": out, **tot}


@router.get("/student/{student_id}")
def student_days(student_id: int, month: Optional[str] = None, current_user: models.User = Depends(auth.require_attendance),
                 db: Session = Depends(get_db)):
    st = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="O'quvchi topilmadi!")
    q = db.query(models.SchoolAttendance).filter(models.SchoolAttendance.student_id == st.id)
    _fix_dates(db, [r[0] for r in q.with_entities(models.SchoolAttendance.date).distinct().all()])
    if month and month != "all":
        q = q.filter(models.SchoolAttendance.date.like(month[:7] + "-%"))
    who, items = {}, []
    for a in q.order_by(models.SchoolAttendance.date.desc()).all():
        if a.marked_by not in who:
            who[a.marked_by] = who_label(db, a.marked_by)
        items.append({"date": a.date, "weekday": UZ_WEEK[datetime.date.fromisoformat(a.date).weekday()], "status": a.status,
                      "edited": bool(a.edited_at),
                      "time": a.time, "deadline": a.deadline, "reason": a.reason, "by": who[a.marked_by],
                      "late_min": max(0, _mins(a.time) - _mins(a.deadline)) if a.status == "late" and a.time and a.deadline else 0})
    c = {k: sum(1 for i in items if i["status"] == k) for k in ("present", "late", "absent")}
    n = len(items)
    return {"student": {"id": st.id, "name": f"{st.last_name} {st.first_name}", "class_name": st.class_name or "", "phone": st.phone},
            "items": items, **c, "excused": sum(1 for i in items if i["status"] == "absent" and i["reason"]),
            "percent": round((c["present"] + c["late"]) * 100 / n) if n else None}
