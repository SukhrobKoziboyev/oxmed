"""v10.3: UMUMIY JADVAL — boshliqning o'z ustunlari ("Abet puli", "Kitob puli", izoh...).

  * ustun qo'shish / nomini o'zgartirish / o'chirish — faqat Markaz rahbari;
  * kataklarni to'ldirish — rahbar va administrator (ikkalasi ham jadvalni ko'radi);
  * bu ustunlar FAQAT MA'LUMOT uchun: kassa, o'qituvchi ulushi va qarzlarga ta'sir qilmaydi;
  * o'chirilgan ustun bazada qoladi (deleted_at), kataklari ham saqlanadi.
"""
from typing import Optional, Union
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models, auth
from ..database import get_db
from ..utils import now_timestamp_ms

router = APIRouter(prefix="/api/bt-columns", tags=["bt-columns"])
MAX_COLUMNS = 12
MAX_NUM = 1_000_000_000


class ColumnIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    kind: str = "money"


class ColumnRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)


class CellIn(BaseModel):
    value: Optional[Union[int, str]] = None


def _clean_name(name: str) -> str:
    n = " ".join((name or "").split())
    if not n:
        raise HTTPException(status_code=400, detail="Ustun nomini yozing!")
    return n[:60]


def _col_out(c: models.BtColumn) -> dict:
    return {"id": c.id, "name": c.name, "kind": c.kind, "position": c.position}


@router.get("")
def list_columns(current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    cols = db.query(models.BtColumn).filter(models.BtColumn.deleted_at.is_(None)).order_by(models.BtColumn.position, models.BtColumn.id).all()
    ids = [c.id for c in cols]
    cells = []
    if ids:
        for x in db.query(models.BtCell).filter(models.BtCell.column_id.in_(ids)).all():
            cells.append({"c": x.column_id, "p": x.payment_id, "v": x.value_num if x.value_num is not None else x.value_text})
    return {"columns": [_col_out(c) for c in cols], "cells": cells}


@router.post("")
def create_column(data: ColumnIn, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    name = _clean_name(data.name)
    kind = data.kind if data.kind in ("money", "text") else "money"
    live = db.query(models.BtColumn).filter(models.BtColumn.deleted_at.is_(None)).all()
    if len(live) >= MAX_COLUMNS:
        raise HTTPException(status_code=400, detail=f"Ko'pi bilan {MAX_COLUMNS} ta qo'shimcha ustun qo'shish mumkin")
    if any(c.name.lower() == name.lower() for c in live):
        raise HTTPException(status_code=400, detail="Bunday nomli ustun allaqachon bor!")
    c = models.BtColumn(name=name, kind=kind, position=max([x.position for x in live] or [0]) + 1,
                        created_by=current_user.username, created_at=now_timestamp_ms())
    db.add(c)
    db.commit()
    db.refresh(c)
    return _col_out(c)


def _get_col(db: Session, cid: int) -> models.BtColumn:
    c = db.query(models.BtColumn).filter(models.BtColumn.id == cid, models.BtColumn.deleted_at.is_(None)).first()
    if not c:
        raise HTTPException(status_code=404, detail="Ustun topilmadi!")
    return c


@router.put("/{cid}")
def rename_column(cid: int, data: ColumnRename, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    c = _get_col(db, cid)
    name = _clean_name(data.name)
    if db.query(models.BtColumn).filter(models.BtColumn.deleted_at.is_(None), models.BtColumn.id != cid).filter(
            models.BtColumn.name.ilike(name)).first():
        raise HTTPException(status_code=400, detail="Bunday nomli ustun allaqachon bor!")
    c.name = name
    db.commit()
    return _col_out(c)


@router.delete("/{cid}")
def delete_column(cid: int, current_user: models.User = Depends(auth.require_rahbar), db: Session = Depends(get_db)):
    c = _get_col(db, cid)
    c.deleted_at = now_timestamp_ms()
    db.commit()
    return {"ok": True}


@router.put("/{cid}/cells/{pid}")
def set_cell(cid: int, pid: int, data: CellIn, current_user: models.User = Depends(auth.require_staff), db: Session = Depends(get_db)):
    c = _get_col(db, cid)
    if not db.query(models.Payment.id).filter(models.Payment.id == pid).first():
        raise HTTPException(status_code=404, detail="To'lov topilmadi!")
    cell = db.query(models.BtCell).filter(models.BtCell.column_id == cid, models.BtCell.payment_id == pid).first()
    v = data.value
    if isinstance(v, str):
        v = " ".join(v.split())
    empty = v is None or v == ""
    num, txt = None, None
    if not empty:
        if c.kind == "money":
            if isinstance(v, str):
                digits = v.replace(" ", "").replace(",", "")
                if not digits.lstrip("-").isdigit():
                    raise HTTPException(status_code=400, detail="Bu ustunga faqat summa yoziladi!")
                v = int(digits)
            if not isinstance(v, int) or v < 0 or v > MAX_NUM:
                raise HTTPException(status_code=400, detail="Summa noto'g'ri!")
            num = v
        else:
            txt = str(v)[:200]
    if empty:
        if cell:
            db.delete(cell)
            db.commit()
        return {"c": cid, "p": pid, "v": None}
    if not cell:
        cell = models.BtCell(column_id=cid, payment_id=pid)
        db.add(cell)
    cell.value_num, cell.value_text = num, txt
    cell.updated_by, cell.updated_at = current_user.username, now_timestamp_ms()
    db.commit()
    return {"c": cid, "p": pid, "v": num if num is not None else txt}
