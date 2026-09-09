from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ApiLog(Base):
    """Server-side audit trail of outbound VTU-provider / payment-gateway calls."""

    __tablename__ = "api_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)   # mock / vtpass / paystack...
    endpoint: Mapped[str] = mapped_column(String(255))
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
