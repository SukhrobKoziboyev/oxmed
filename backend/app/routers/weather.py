"""v13.21: KUNGA MOSLASH — markaz joylashgan shahar ob-havosi (Open-Meteo, bepul, kalitsiz).

Brauzerdagi effektlar (yomg'ir, momaqaldiroq, quyosh, shamol, qor) shu javobga qarab tanlanadi.
Tashqi xizmatga faqat SHAHAR koordinatalari yuboriladi (foydalanuvchi haqida hech narsa yo'q).
Natija hamma uchun 10 daqiqa xotirada saqlanadi — ko'p foydalanuvchi bo'lsa ham so'rov kam.
Joylashuv: .env → WEATHER_LAT, WEATHER_LON, WEATHER_CITY (standart: Qarshi).
"""
import json
import os
import threading
import time
import urllib.request

from fastapi import APIRouter, Depends

from .. import models, auth

router = APIRouter(prefix="/api/weather", tags=["weather"])

LAT = os.getenv("WEATHER_LAT") or "38.8606"
LON = os.getenv("WEATHER_LON") or "65.7891"
CITY = os.getenv("WEATHER_CITY") or "Qarshi"
TTL = 600
_lock = threading.Lock()
_cache = {"at": 0.0, "data": None}


def kind_of(code: int, wind: float, is_day: bool) -> str:
    """WMO ob-havo kodi → effekt turi."""
    if code in (95, 96, 99):
        return "storm"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if wind >= 28:
        return "wind"
    if code in (2, 3, 45, 48):
        return "cloudy"
    return "sun" if is_day else "night"


TEXT = {"storm": "Momaqaldiroq", "snow": "Qor", "rain": "Yomg'ir", "wind": "Shamolli", "cloudy": "Bulutli", "sun": "Quyoshli", "night": "Ochiq osmon (tun)"}


def _fetch() -> dict:
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&current=temperature_2m,weather_code,wind_speed_10m,is_day&timezone=Asia%%2FTashkent" % (LAT, LON))
    req = urllib.request.Request(url, headers={"User-Agent": "oxmed-weather/1.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        cur = (json.loads(r.read().decode() or "{}").get("current") or {})
    code, wind = int(cur.get("weather_code") or 0), float(cur.get("wind_speed_10m") or 0)
    day = bool(cur.get("is_day", 1))
    k = kind_of(code, wind, day)
    return {"ok": True, "kind": k, "text": TEXT[k], "code": code, "temp": cur.get("temperature_2m"), "wind": round(wind),
            "is_day": day, "city": CITY, "at": int(time.time() * 1000)}


@router.get("")
def weather(current_user: models.User = Depends(auth.get_current_user)):
    now = time.time()
    with _lock:
        if _cache["data"] and now - _cache["at"] < TTL:
            return _cache["data"]
    try:
        data = _fetch()
    except Exception:  # noqa: BLE001 — internet bo'lmasa effekt "kunga moslash"siz qoladi
        with _lock:
            if _cache["data"]:
                return _cache["data"]
        return {"ok": False, "kind": None, "city": CITY}
    with _lock:
        _cache.update(at=now, data=data)
    return data
