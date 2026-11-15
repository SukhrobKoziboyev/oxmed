import datetime
from . import models

DAY_LABELS = {
    "toq": "🔴 Toq kunlar (Dush, Chor, Juma)",
    "juft": "🔵 Juft kunlar (Sesh, Pay, Shan)",
    "harkuni": "🟢 Har kuni",
}


def format_group_label(group: models.Group) -> str:
    label = DAY_LABELS.get(group.day_type, group.day_type)
    return f"{label} • {group.start_time} - {group.end_time}"


# v7.9: O'zbekiston vaqti (UTC+5, yozgi vaqt yo'q). Server UTC'da ishlagani uchun
# avval datetime.now() Toshkentdan 5 soat orqada yozilardi — endi doim UTC+5.
UZ_TZ = datetime.timezone(datetime.timedelta(hours=5), "Asia/Tashkent")
DATE_FMT = "%d.%m.%Y %H:%M:%S"


def now_uz() -> datetime.datetime:
    return datetime.datetime.now(UZ_TZ)


def now_uz_datestring() -> str:
    return now_uz().strftime(DATE_FMT)


def now_timestamp_ms() -> int:
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)


def ts_to_uz_datestring(ts_ms) -> str:
    """Epoch millisekunddan Toshkent vaqtidagi 'dd.mm.YYYY HH:MM:SS' matni."""
    return datetime.datetime.fromtimestamp(int(ts_ms) / 1000, UZ_TZ).strftime(DATE_FMT)


def parse_uz_datetime(text: str) -> datetime.datetime:
    """'dd.mm.YYYY HH:MM[:SS]' yoki 'YYYY-MM-DDTHH:MM' -> Toshkent vaqtidagi datetime."""
    text = (text or "").strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.datetime.strptime(text, fmt).replace(tzinfo=UZ_TZ)
        except ValueError:
            continue
    raise ValueError("Sana noto'g'ri")


def utc_naive_to_uz_string(dt) -> str:
    """Bazada utcnow() bilan saqlangan (naive UTC) vaqtni Toshkent vaqtida ko'rsatish."""
    if not dt:
        return ""
    return dt.replace(tzinfo=datetime.timezone.utc).astimezone(UZ_TZ).strftime(DATE_FMT)


UZ_MONTHS = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]


def current_uz_month_name() -> str:
    """Hozirgi oyning o'zbekcha nomi (frontend/backend bir xil oy ro'yxatidan
    foydalanadi - to'lovlar 'month' maydonida shu nomlar bilan saqlanadi)."""
    return UZ_MONTHS[now_uz().month - 1]
