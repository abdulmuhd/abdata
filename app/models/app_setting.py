from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class AppSetting(Base):
    """Simple key/value store for runtime-editable platform settings (e.g. outbound webhook URL)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | str | None] = mapped_column(JSON, nullable=True)
