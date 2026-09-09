import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class NotificationType(str, enum.Enum):
    TRANSACTION = "transaction"
    WALLET = "wallet"
    SECURITY = "security"
    SYSTEM = "system"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20), default=NotificationType.SYSTEM.value)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(64), nullable=True)  # link to txn ref
    is_read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="notifications")
