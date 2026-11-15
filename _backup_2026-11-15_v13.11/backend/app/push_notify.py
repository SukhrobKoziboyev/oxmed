"""v8.7: Yangi versiya haqida hamma qurilmalarga bildirishnoma yuborish.

Serverda:  cd /var/www/oxmed/backend && venv/bin/python -m app.push_notify "Pro 8.7"
"""
import sys

from .database import SessionLocal, Base, engine
from . import models  # noqa: F401  (jadvallar ro'yxatga olinsin)
from .routers.push import send_to_all


def main():
    version = " ".join(sys.argv[1:]).strip()
    body = "Tizim yangilandi" + (f" ({version})" if version else "") + ". Ochish uchun bosing."
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        total = db.query(models.PushSubscription).count()
        r = send_to_all(db, "OXMED — yangi versiya 🔄", body)
    finally:
        db.close()
    print(f"Obunalar: {total} ta | yuborildi: {r['sent']} | eskirgan (o'chirildi): {r['removed']} | xato: {r['failed']}")


if __name__ == "__main__":
    main()
