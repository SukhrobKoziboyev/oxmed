"""v13.14: OVOZLI / MATNLI YORDAMCHI (Google Gemini).

Xodim gapiradi yoki yozadi ("To'lov kiritishni och", "Aliyev Valini top",
"Valiga noyabr uchun 500 ming naqd to'lov yoz") — Gemini buni BITTA buyruqqa aylantiradi
(JSON: action, target, query, month, amount, method, ...). Buyruqni brauzerdagi dastur o'zi
bajaradi: bo'limni ochadi, o'quvchini qidiradi, formani to'ldiradi.

XAVFSIZLIK:
  * AI hech narsani saqlamaydi, o'chirmaydi, yubormaydi — faqat ekranda ochadi/to'ldiradi,
    "Saqlash"ni doim odam bosadi. Server ma'lumotlarga ruxsatni avvalgidek o'zi tekshiradi.
  * AI'ga bazadagi ma'lumot (o'quvchilar ro'yxati, telefonlar, summalar) YUBORILMAYDI —
    faqat foydalanuvchining gapi va ochish mumkin bo'lgan bo'limlar nomlari.
  * Kalit faqat serverdagi .env da: GEMINI_API_KEY (ixtiyoriy GEMINI_MODEL).
  * Har foydalanuvchiga limit: daqiqasiga 12, kuniga 300 so'rov (bepul kvota tugab qolmasin).
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import models, auth

router = APIRouter(prefix="/api/ai", tags=["ai"])

API_URL = os.getenv("GEMINI_API_URL") or "https://generativelanguage.googleapis.com/v1beta/interactions"   # sinov uchun almashtirish mumkin
API_REVISION = "2026-05-20"
DEFAULT_MODEL = "gemini-3.5-flash-lite"   # eng tez va arzon barqaror model (AI Studio, 2026-11)
MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
ACTIONS = ["open", "find_student", "fill_payment", "fill_expense", "search", "none"]
MAX_AUDIO_B64 = 950_000   # nginx standart chegarasi 1 MB — 16 kHz WAV ≈ 20 soniya

_lock = threading.Lock()
_minute = defaultdict(deque)
_day = defaultdict(deque)
PER_MIN, PER_DAY = 12, 300


def _key() -> str:
    return (os.getenv("GEMINI_API_KEY") or "").strip()


def _model() -> str:
    return (os.getenv("GEMINI_MODEL") or "").strip() or DEFAULT_MODEL


def _rate_ok(user: str) -> bool:
    now = time.time()
    with _lock:
        m, d = _minute[user], _day[user]
        while m and now - m[0] > 60:
            m.popleft()
        while d and now - d[0] > 86400:
            d.popleft()
        if len(m) >= PER_MIN or len(d) >= PER_DAY:
            return False
        m.append(now)
        d.append(now)
        return True


class Target(BaseModel):
    k: str = Field(..., max_length=40)
    t: str = Field(..., max_length=80)


class CommandIn(BaseModel):
    text: Optional[str] = Field(None, max_length=600)
    audio: Optional[str] = None           # base64 (WAV 16 kHz mono)
    mime: Optional[str] = "audio/wav"
    targets: List[Target] = []
    screen: Optional[str] = Field(None, max_length=80)


SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ACTIONS},
        "target": {"type": "string"},
        "query": {"type": "string"},
        "month": {"type": "string", "enum": [""] + MONTHS},
        "amount": {"type": "integer"},
        "method": {"type": "string", "enum": ["", "naxt", "click", "terminal"]},
        "title": {"type": "string"},
        "note": {"type": "string"},
        "heard": {"type": "string"},
        "reply": {"type": "string"},
    },
    "required": ["action", "target", "query", "month", "amount", "method", "title", "note", "heard", "reply"],
}


def _system(targets: List[Target], screen: Optional[str]) -> str:
    tl = "\n".join(f"- {t.k}: {t.t}" for t in targets[:40]) or "- (none)"
    return f"""You are the command interpreter of OXMED, a school/learning-center management app in Uzbekistan.
The user speaks or writes in Uzbek (Latin or Cyrillic), sometimes mixed with Russian. Turn the request into exactly ONE action as JSON.
The app itself performs the action on screen. You NEVER save, delete, send, pay or change passwords — a human always presses "Saqlash" (Save) himself.

Actions:
- open: open a section. "target" MUST be one of the keys below.
- find_student: find a student and show his card. "query" = the student's name/surname (as said; fix obvious speech errors), or phone digits.
- fill_payment: open the payment form and fill it (NOT save). "query" = student name; "month" = month name from the list; "amount" = integer so'm; "method" = naxt (naqd/naqt/cash), click, or terminal (karta/plastik/terminal); leave unknown fields empty/0.
- fill_expense: open the expense form and fill it (NOT save). "title" = what was bought; "amount" = integer so'm; "note" = extra detail (quantity etc.).
- search: type "query" into the search box of the current screen.
- none: nothing to do — the request is unclear, impossible, or asks to save/delete/send/pay. Explain briefly in "reply".

Sections the user may open (key: name):
{tl}
Current screen: {screen or 'unknown'}

Rules:
- Months (Uzbek): {", ".join(MONTHS)}. "shu oy"/"bu oy" = the current month is not known to you — leave month empty.
- Amounts: convert spoken numbers to integer so'm: "500 ming" = 500000, "bir million ikki yuz ming" = 1200000, "1,5 mln" = 1500000, "yarim million" = 500000.
- If the user wants something not in the list, use none and say it is not available for him.
- "heard": what the user said, written in Uzbek Latin.
- "reply": one short, polite Uzbek (Latin) sentence describing what will happen, e.g. "To'lov kiritish ochildi — tekshirib, Saqlashni bosing."
- Unused string fields = "", unused amount = 0."""


def _call(body: dict) -> dict:
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "x-goog-api-key": _key(), "Api-Revision": API_REVISION})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="ignore")[:600]
        msg = raw
        try:
            msg = (json.loads(raw).get("error") or {}).get("message") or raw
        except Exception:  # noqa: BLE001
            pass
        if e.code == 429:
            raise HTTPException(status_code=429, detail="AI limiti vaqtincha tugadi — birozdan keyin qayta urinib ko'ring.")
        if e.code in (401, 403):
            raise HTTPException(status_code=503, detail="AI kaliti noto'g'ri yoki ruxsat yo'q (serverdagi GEMINI_API_KEY ni tekshiring).")
        raise HTTPException(status_code=502, detail=f"AI xatosi: {msg}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise HTTPException(status_code=504, detail=f"AI bilan aloqa yo'q: {e}")


def _text_of(resp: dict) -> str:
    """Interactions API javobidan model matnini topadi (steps[].type == model_output → content[].text)."""
    if isinstance(resp.get("output_text"), str):
        return resp["output_text"]
    parts = []
    for st in resp.get("steps") or []:
        if st.get("type") == "model_output":
            for c in st.get("content") or []:
                if isinstance(c, dict) and c.get("type", "text") == "text" and c.get("text"):
                    parts.append(c["text"])
    if not parts:   # zaxira: boshqa shakllar
        for o in resp.get("outputs") or []:
            if isinstance(o, dict) and o.get("text"):
                parts.append(o["text"])
    return "".join(parts).strip()


def _clean(d: dict, keys: set) -> dict:
    out = {
        "action": d.get("action") if d.get("action") in ACTIONS else "none",
        "target": str(d.get("target") or "")[:40],
        "query": str(d.get("query") or "")[:120],
        "month": d.get("month") if d.get("month") in MONTHS else "",
        "amount": 0,
        "method": d.get("method") if d.get("method") in ("naxt", "click", "terminal") else "",
        "title": str(d.get("title") or "")[:200],
        "note": str(d.get("note") or "")[:255],
        "heard": str(d.get("heard") or "")[:600],
        "reply": str(d.get("reply") or "")[:300],
    }
    try:
        out["amount"] = max(0, min(int(d.get("amount") or 0), 1_000_000_000))
    except (TypeError, ValueError):
        out["amount"] = 0
    if out["action"] == "open" and out["target"] not in keys:
        out["action"] = "none"
        out["reply"] = "Bu bo'lim siz uchun ochiq emas."   # AI "ochildi" desa ham — ochilmaydi
    return out


@router.get("/status")
def ai_status(current_user: models.User = Depends(auth.get_current_user)):
    ok = bool(_key())
    out = {"available": ok}
    if current_user.role == "Markaz rahbari":
        out["model"] = _model()
    return out


@router.post("/command")
def ai_command(data: CommandIn, current_user: models.User = Depends(auth.get_current_user)):
    if not _key():
        raise HTTPException(status_code=503, detail="AI hali ulanmagan (serverga GEMINI_API_KEY kiritilmagan).")
    text = (data.text or "").strip()
    audio = (data.audio or "").strip()
    if not text and not audio:
        raise HTTPException(status_code=400, detail="Gapiring yoki yozing.")
    if audio:
        if len(audio) > MAX_AUDIO_B64:
            raise HTTPException(status_code=400, detail="Ovoz juda uzun — qisqaroq gapiring.")
        try:
            base64.b64decode(audio[:4000] + "=" * (-len(audio[:4000]) % 4), validate=False)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Ovoz fayli noto'g'ri.")
    if not _rate_ok(current_user.username):
        raise HTTPException(status_code=429, detail="Juda ko'p so'rov — bir daqiqadan keyin qayta urinib ko'ring.")
    inp = []
    if audio:
        mime = data.mime if (data.mime or "").startswith("audio/") else "audio/wav"
        inp.append({"type": "audio", "data": audio, "mime_type": mime})
        inp.append({"type": "text", "text": text or "Foydalanuvchining ovozli buyrug'i (yuqoridagi audio)."})
    else:
        inp.append({"type": "text", "text": text})
    body = {
        "model": _model(),
        "system_instruction": _system(data.targets, data.screen),
        "input": inp,
        "response_format": {"type": "text", "mime_type": "application/json", "schema": SCHEMA},
        "generation_config": {"thinking_level": "minimal", "max_output_tokens": 600},
        "store": False,
    }
    resp = _call(body)
    raw = _text_of(resp)
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        s, e = raw.find("{"), raw.rfind("}")
        try:
            d = json.loads(raw[s:e + 1]) if s != -1 and e > s else {}
        except ValueError:
            d = {}
    if not isinstance(d, dict) or not d:
        return {"action": "none", "target": "", "query": "", "month": "", "amount": 0, "method": "", "title": "",
                "note": "", "heard": "", "reply": "Tushunmadim — qaytadan, aniqroq ayting."}
    return _clean(d, {t.k for t in data.targets})
