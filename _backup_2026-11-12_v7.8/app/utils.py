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


def now_uz_datestring() -> str:
    now = datetime.datetime.now()
    return now.strftime("%d.%m.%Y %H:%M:%S")


def now_timestamp_ms() -> int:
    return int(datetime.datetime.now().timestamp() * 1000)


UZ_MONTHS = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]


def current_uz_month_name() -> str:
    """Hozirgi oyning o'zbekcha nomi (frontend/backend bir xil oy ro'yxatidan
    foydalanadi - to'lovlar 'month' maydonida shu nomlar bilan saqlanadi)."""
    return UZ_MONTHS[datetime.datetime.now().month - 1]
