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


# ---------------------------------------------------------------------------
# v11.8: AQLLI O'XSHASHLIK — "To'yliyev Ahmad" = "Toyliyev Axmad" = "Тўйлиев Аҳмад"
#   1) kirill -> lotin; apostroflar va belgilar olib tashlanadi;
#   2) o'zbekcha yozuv farqlari tenglashtiriladi: x/h/kh, q/k, ye/e, iy/i, dj/j, w/v, ikki harf;
#   3) 1-2 harf xato (Levenshtein) — ism va familiya alohida, joyi almashgani ham;
#   4) telefon bir xil + familiya bir xil — ehtimol aka-uka (yumshoq ogohlantirish).
# ---------------------------------------------------------------------------
_CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z",
        "и": "i", "й": "y", "к": "k", "қ": "q", "л": "l", "м": "m", "н": "n", "о": "o", "ў": "o", "п": "p",
        "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ҳ": "h", "ц": "s", "ч": "ch", "ш": "sh",
        "щ": "sh", "ъ": "", "ь": "", "ы": "i", "э": "e", "ю": "yu", "я": "ya"}


def canon(x: str) -> str:
    s = "".join(_CYR.get(ch, ch) for ch in (x or "").lower())
    s = re.sub(r"[^a-z]", "", s)
    for a, b in (("kh", "h"), ("x", "h"), ("q", "k"), ("w", "v"), ("dj", "j"), ("ye", "e"), ("iy", "i"), ("ts", "s")):
        s = s.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", s)


def _lev(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _close(a: str, b: str) -> bool:
    if not a or not b:
        return False
    d, n = _lev(a, b), max(len(a), len(b))
    return d == 0 or (d == 1 and n >= 4) or (d <= 2 and n >= 8)


def compare_names(f1, l1, f2, l2):
    """-> ('exact'|'similar'|None, almashganmi)"""
    a, b, c, d = canon(f1), canon(l1), canon(f2), canon(l2)
    if (a, b) == (c, d):
        return "exact", False
    if (a, b) == (d, c):
        return "exact", True
    if _close(a, c) and _close(b, d):
        return "similar", False
    if _close(a, d) and _close(b, c):
        return "similar", True
    return None, False


def find_duplicates(db: Session, first: str, last: str, phone: str, exclude_id=None) -> list:
    """Bazada shu o'quvchiga o'xshaganlar (eng ishonchlisi birinchi).
    match: 'exact' — ism-familiya bir xil (yozilishi farq qilsa ham: Ahmad = Axmad);
           'similar' — 1-2 harf farq; 'sibling' — telefon va familiya bir xil, ism boshqa.
    exact_same: ism bir xil VA telefon bir xil — aniq shu bola (ikkinchi marta yozib bo'lmaydi)."""
    ph = phone9(phone)
    res = []
    for st in db.query(models.Student).all():
        if exclude_id and st.id == exclude_id:
            continue
        kind, swapped = compare_names(first, last, st.first_name, st.last_name)
        same_phone = bool(ph) and len(ph) == 9 and ph in (phone9(st.phone), phone9(st.phone2 or ""))
        if not kind and same_phone and _close(canon(last), canon(st.last_name)):
            kind = "sibling"
        if not kind:
            continue
        reasons = []
        if kind == "exact":
            same_txt = norm_name(first) == norm_name(st.first_name) and norm_name(last) == norm_name(st.last_name)
            reasons.append("Ism-familiya bir xil" if same_txt else "Ism-familiya bir xil (faqat yozilishi farq qiladi)")
        elif kind == "similar":
            reasons.append("Ism-familiya juda o'xshash (1-2 harf farq)")
        else:
            reasons.append("Familiya va telefon bir xil — aka-uka yoki opa-singil bo'lishi mumkin")
        if swapped:
            reasons.append("ism va familiya joyi almashgan")
        if same_phone and kind != "sibling":
            reasons.append("telefon ham bir xil")
        res.append({
            "id": st.id, "name": f"{st.first_name} {st.last_name}", "phone": st.phone,
            "same_phone": same_phone, "match": kind, "exact_same": kind == "exact" and same_phone,
            "reason": ", ".join(reasons),
            "type": st.type, "class_name": st.class_name,
            "added_by": who_label(db, st.added_by),
            "teachers": student_teachers(db, st),
        })
    order = {"exact": 0, "similar": 1, "sibling": 2}
    res.sort(key=lambda r: (not r["exact_same"], not r["same_phone"], order[r["match"]]))
    return res


def duplicate_pairs(db: Session) -> list:
    """v11.8: bazada HOZIR ikki marta yozilganga o'xshagan o'quvchilar juftlari (aka-ukalar emas)."""
    rows = db.query(models.Student).order_by(models.Student.id).all()
    keyed = [(st, canon(st.first_name), canon(st.last_name), phone9(st.phone)) for st in rows]
    out = []
    for i, (a, af, al, ap) in enumerate(keyed):
        for b, bf, bl, bp in keyed[i + 1:]:
            if not ({af, al} & {bf, bl}) and abs(len(af + al) - len(bf + bl)) > 2:
                continue
            kind, swapped = compare_names(a.first_name, a.last_name, b.first_name, b.last_name)
            if not kind:
                continue
            same_phone = bool(ap) and ap == bp
            if kind == "similar" and not same_phone:
                continue  # 1-2 harf farq + boshqa telefon — ko'pincha boshqa bola, bezovta qilmaymiz
            out.append({"a": {"id": a.id, "name": f"{a.first_name} {a.last_name}", "phone": a.phone, "added_by": who_label(db, a.added_by)},
                        "b": {"id": b.id, "name": f"{b.first_name} {b.last_name}", "phone": b.phone, "added_by": who_label(db, b.added_by)},
                        "match": kind, "same_phone": same_phone})
    out.sort(key=lambda r: (not r["same_phone"], r["match"] != "exact"))
    return out
