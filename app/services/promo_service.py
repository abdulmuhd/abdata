from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.promo import PromoCode


def validate_promo(db: Session, code: str, amount_kobo: int) -> dict | None:
    promo = db.execute(select(PromoCode).where(PromoCode.code == code.upper())).scalar_one_or_none()
    if not promo:
        return None
    if not promo.is_active:
        return None
    if promo.expires_at and promo.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    if promo.max_uses and promo.used_count >= promo.max_uses:
        return None
    if amount_kobo < promo.min_amount_kobo:
        return None

    discount_kobo = promo.discount_kobo
    if promo.discount_percent:
        pct_discount = amount_kobo * promo.discount_percent // 100
        discount_kobo = max(discount_kobo, pct_discount)

    return {
        "code": promo.code,
        "discount_kobo": min(discount_kobo, amount_kobo),
    }


def apply_promo(db: Session, code: str) -> None:
    promo = db.execute(select(PromoCode).where(PromoCode.code == code.upper())).scalar_one_or_none()
    if promo:
        promo.used_count += 1
        db.commit()
