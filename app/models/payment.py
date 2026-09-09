from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class PaymentIntent(Base):
    """A wallet-funding attempt through a payment gateway (Paystack-like flow)."""

    __tablename__ = "payment_intents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    gateway_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | successful | failed | abandoned
    settled_ledger_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
