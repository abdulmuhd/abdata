import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class LedgerDirection(str, enum.Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class LedgerCategory(str, enum.Enum):
    FUNDING = "funding"
    PURCHASE = "purchase"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"
    TRANSFER = "transfer"


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    balance_kobo: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bonus_kobo: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NGN")
    total_funded_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="wallet")
    ledger = relationship(
        "WalletTransaction",
        back_populates="wallet",
        order_by="WalletTransaction.id.desc()",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class WalletTransaction(Base):
    """Immutable double-entry-style ledger row. Balances are derivable from this table."""

    __tablename__ = "wallet_transactions"
    __table_args__ = (Index("ix_wtxn_wallet_created", "wallet_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="CASCADE"), index=True)
    direction: Mapped[LedgerDirection] = mapped_column(Enum(LedgerDirection, native_enum=False), nullable=False)
    category: Mapped[LedgerCategory] = mapped_column(Enum(LedgerCategory, native_enum=False), nullable=False)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_before_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    narration: Mapped[str] = mapped_column(String(200))
    vtu_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("vtu_transactions.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    wallet = relationship("Wallet", back_populates="ledger")
    vtu_transaction = relationship("VTUTransaction", foreign_keys=[vtu_transaction_id])
