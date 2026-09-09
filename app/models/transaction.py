from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from .enums import ServiceTypeEnum, TxnStatus


class VTUTransaction(Base):
    """A purchase/order placed through the platform (airtime, data, bills)."""

    __tablename__ = "vtu_transactions"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_user_idempotency"),
        Index("ix_vtu_user_created", "user_id", "created_at"),
        Index("ix_vtu_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    service_type: Mapped[ServiceTypeEnum] = mapped_column(Enum(ServiceTypeEnum, native_enum=False), index=True)
    provider_code: Mapped[str] = mapped_column(String(40))
    customer_ref: Mapped[str] = mapped_column(String(80))  # phone / meter no / smartcard no
    details: Mapped[dict] = mapped_column(JSON, default=dict)  # plan info, customer name, meter type...
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    profit_kobo: Mapped[int] = mapped_column(BigInteger, default=0)

    status: Mapped[TxnStatus] = mapped_column(Enum(TxnStatus, native_enum=False), default=TxnStatus.PENDING, index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="transactions")
