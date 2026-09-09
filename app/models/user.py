import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    pin_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)  # email verified
    verification_code_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)

    pin_failed_attempts: Mapped[int] = mapped_column(default=0)
    pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reset_token_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)

    referral_code: Mapped[str | None] = mapped_column(String(10), unique=True, index=True, nullable=True)
    referred_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    transactions = relationship("VTUTransaction", back_populates="user", order_by="VTUTransaction.id.desc()")
    notifications = relationship(
        "Notification", back_populates="user", order_by="Notification.id.desc()", cascade="all, delete-orphan"
    )
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    referrer = relationship("User", remote_side="User.id", foreign_keys="User.referred_by")


class RefreshToken(Base):
    """Server-side record of issued refresh sessions so they can be revoked (logout)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="refresh_tokens")
