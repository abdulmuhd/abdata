from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from .enums import ServiceTypeEnum


class Provider(Base):
    """A biller / network operator exposed to users (DSTV, IKEDC, MTN...)."""

    __tablename__ = "providers"
    __table_args__ = (UniqueConstraint("service_type", "code", name="uq_service_provider_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service_type: Mapped[ServiceTypeEnum] = mapped_column(Enum(ServiceTypeEnum, native_enum=False), index=True)
    code: Mapped[str] = mapped_column(String(40), index=True)  # e.g. mtn, ikedc, dstv
    name: Mapped[str] = mapped_column(String(120))
    short_name: Mapped[str] = mapped_column(String(20))
    color: Mapped[str | None] = mapped_column(String(9), nullable=True)  # brand hex for UI chips
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class DataPlan(Base):
    __tablename__ = "data_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    network_code: Mapped[str] = mapped_column(String(40), index=True)  # provider code of the network
    plan_code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))          # "1GB Data Bundle"
    category: Mapped[str] = mapped_column(String(40), index=True)  # Daily / Weekly / Monthly / SME
    volume_mb: Mapped[int] = mapped_column(BigInteger)
    validity_days: Mapped[int] = mapped_column(BigInteger, default=30)
    price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    buying_price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    selling_price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    promo_price_kobo: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_plan_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CablePackage(Base):
    __tablename__ = "cable_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_code: Mapped[str] = mapped_column(String(40), index=True)
    package_code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    buying_price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    selling_price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    validity_days: Mapped[int] = mapped_column(BigInteger, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExamProduct(Base):
    """Fixed-price exam e-PIN product (WAEC result checker, JAMB UTME e-PIN...)."""

    __tablename__ = "exam_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    body_code: Mapped[str] = mapped_column(String(40), index=True)  # waec / jamb / neco
    product_code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. {"pin_label": "Result Checker PIN"}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DisabledDataCategory(Base):
    """Tracks which data plan categories are disabled per network."""

    __tablename__ = "disabled_data_categories"
    __table_args__ = (UniqueConstraint("network_code", "category", name="uq_network_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    network_code: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
