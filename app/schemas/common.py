import re
from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")

PHONE_RE = re.compile(r"^(?:\+?234|0)([789]\d{9})$")


def normalize_phone(phone: str) -> str:
    cleaned = (phone or "").replace(" ", "").replace("-", "")
    m = PHONE_RE.match(cleaned)
    if not m:
        raise ValueError("Enter a valid Nigerian phone number, e.g.  ")
    return "0" + m.group(1)


def normalize_phone_or_none(phone: str | None) -> str | None:
    """Best-effort: returns None when the string is not a valid NG phone number."""
    if phone in (None, ""):
        return None
    try:
        return normalize_phone(phone)
    except ValueError:
        return None


def to_kobo(amount_naira: int | float | str | Decimal) -> int:
    """Convert naira supplied by a client into integer kobo (never trust floats blindly)."""
    kobo = Decimal(str(amount_naira)) * 100
    if kobo != kobo.to_integral_value():
        raise ValueError("Amount cannot have more than 2 decimal places")
    return int(kobo)


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: T | None = None


class PageMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class PagedData(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta
