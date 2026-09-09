"""API Provider configuration models — stores external VTU/API provider credentials,
endpoints, supported services, and routing configuration."""

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class HttpMethod(str, enum.Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"


class ServiceType(str, enum.Enum):
    AIRTIME = "airtime"
    DATA = "data"
    CABLE = "cable"
    ELECTRICITY = "electricity"
    EPIN = "epin"
    BULK_SMS = "bulk_sms"
    EXAM_PINS = "exam_pins"
    EDUCATION = "education"


class ApiProvider(Base):
    """An external VTU/API provider (e.g. GongozConcept, LegitDataWay, VTU.ng)."""

    __tablename__ = "api_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_balance_check: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    credentials = relationship("ApiProviderCredential", back_populates="provider", cascade="all, delete-orphan")
    endpoints = relationship("ApiProviderEndpoint", back_populates="provider", cascade="all, delete-orphan")
    services = relationship("ApiProviderService", back_populates="provider", cascade="all, delete-orphan")


class ApiProviderCredential(Base):
    """Encrypted credentials for an API provider. Sensitive values are stored
    as hashed/encrypted strings and never exposed to the frontend in plain text."""

    __tablename__ = "api_provider_credentials"
    __table_args__ = (UniqueConstraint("provider_id", "credential_key", name="uq_provider_credential_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("api_providers.id", ondelete="CASCADE"), index=True)
    credential_key: Mapped[str] = mapped_column(String(80))
    credential_value: Mapped[str] = mapped_column(Text)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    provider = relationship("ApiProvider", back_populates="credentials")


class ApiProviderEndpoint(Base):
    """API endpoint configuration for a specific service operation."""

    __tablename__ = "api_provider_endpoints"
    __table_args__ = (UniqueConstraint("provider_id", "operation", name="uq_provider_operation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("api_providers.id", ondelete="CASCADE"), index=True)
    operation: Mapped[str] = mapped_column(String(80))  # e.g. buy_airtime, buy_data, check_balance
    path: Mapped[str] = mapped_column(String(500))
    method: Mapped[HttpMethod] = mapped_column(Enum(HttpMethod, native_enum=False), default=HttpMethod.POST)

    # Request/response mapping configuration
    request_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    provider = relationship("ApiProvider", back_populates="endpoints")


class ApiProviderService(Base):
    """Maps which services a provider supports."""

    __tablename__ = "api_provider_services"
    __table_args__ = (UniqueConstraint("provider_id", "service_type", name="uq_provider_service_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("api_providers.id", ondelete="CASCADE"), index=True)
    service_type: Mapped[ServiceType] = mapped_column(Enum(ServiceType, native_enum=False), index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    provider = relationship("ApiProvider", back_populates="services")


class ApiProviderRouting(Base):
    """Service-to-provider routing configuration. Determines which provider
    handles each service type, with optional primary/backup hierarchy."""

    __tablename__ = "api_provider_routing"
    __table_args__ = (UniqueConstraint("service_type", "priority", name="uq_service_priority"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service_type: Mapped[ServiceType] = mapped_column(Enum(ServiceType, native_enum=False), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("api_providers.id", ondelete="CASCADE"), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)  # 1=primary, 2=backup, 3=second backup
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    provider = relationship("ApiProvider")


class ApiRequestLog(Base):
    """Audit trail of API requests made to external providers."""

    __tablename__ = "api_request_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("api_providers.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_name: Mapped[str] = mapped_column(String(100))
    service_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(80))
    reference: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    endpoint_url: Mapped[str] = mapped_column(String(500))
    http_method: Mapped[str] = mapped_column(String(10))
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
