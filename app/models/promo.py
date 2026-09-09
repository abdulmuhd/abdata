from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    discount_kobo: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    min_amount_kobo: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
