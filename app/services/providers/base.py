"""VTU / bill-payment provider abstraction.

The platform talks to ONE interface; concrete adapters (mock today, VTPass /
Clubkonnect / etc. tomorrow) implement it. Provider secrets stay on the server
and are read from environment configuration inside these adapters only.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.errors import ProviderError
from ...models import ApiLog
from ...models.enums import MeterType


@dataclass
class ProviderResult:
    success: bool
    provider_reference: str | None = None
    message: str = ""
    resolved: bool = True  # False => still pending at the provider
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomerInfo:
    found: bool
    customer_name: str | None = None
    address: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class BaseVtuProvider(ABC):
    name: str = "abstract"

    # ── helpers ──────────────────────────────────────────────
    def _log(self, db: Session, endpoint: str, request: dict, response: dict, success: bool, started: float):
        db.add(
            ApiLog(
                provider=self.name,
                endpoint=endpoint,
                request_payload=request,
                response_payload=response,
                success=success,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )
        db.flush()

    @abstractmethod
    def buy_airtime(self, db: Session, *, network_code: str, phone: str, amount_kobo: int, reference: str) -> ProviderResult: ...

    @abstractmethod
    def buy_data(self, db: Session, *, network_code: str, phone: str, plan_code: str, amount_kobo: int, reference: str, provider_plan_id: int | None = None) -> ProviderResult: ...

    @abstractmethod
    def validate_meter(self, db: Session, *, disco_code: str, meter_number: str, meter_type: MeterType) -> CustomerInfo: ...

    @abstractmethod
    def pay_electricity(self, db: Session, *, disco_code: str, meter_number: str, meter_type: MeterType, amount_kobo: int, reference: str) -> ProviderResult: ...

    @abstractmethod
    def validate_smartcard(self, db: Session, *, cable_code: str, smartcard_number: str) -> CustomerInfo: ...

    @abstractmethod
    def pay_cable(self, db: Session, *, cable_code: str, smartcard_number: str, package_code: str, amount_kobo: int, reference: str) -> ProviderResult: ...

    # ── exam pins ────────────────────────────────────────────
    @abstractmethod
    def buy_exam_pin(self, db: Session, *, body_code: str, product_code: str, amount_kobo: int, reference: str) -> ProviderResult: ...

    # ── school fees ──────────────────────────────────────────
    @abstractmethod
    def validate_student(self, db: Session, *, institution_code: str, student_ref: str) -> CustomerInfo: ...

    @abstractmethod
    def pay_school_fees(self, db: Session, *, institution_code: str, student_ref: str, amount_kobo: int, reference: str) -> ProviderResult: ...


_registry: dict[str, type[BaseVtuProvider]] = {}


def register_provider(cls: type[BaseVtuProvider]):
    _registry[cls.name] = cls
    return cls


def list_providers() -> list[dict[str, Any]]:
    """Return available providers with metadata."""
    return [
        {"name": cls.name, "supports": getattr(cls, "supports", None) or ["all"]}
        for cls in _registry.values()
    ]


def _serves(cls: type[BaseVtuProvider], service: str | None) -> bool:
    """Adapters without an explicit `supports` set serve every service."""
    supported = getattr(cls, "supports", None)
    return supported is None or service in supported


def get_provider(service: str | None = None, db: Session | None = None) -> BaseVtuProvider:
    """Return the configured VTU adapter.

    Uses the generic provider for all real providers (reads config from API Manager).
    Only mock provider has its own adapter.
    """
    key = settings.VTU_PROVIDER.lower()

    # Check database override if db is available (takes priority over routing)
    if db is not None:
        try:
            from ...models import AppSetting
            row = db.get(AppSetting, "vtu_provider")
            if row and row.value:
                raw = row.value if isinstance(row.value, str) else str(row.value)
                key = raw.strip().strip('"').strip("'").lower()
        except Exception:
            pass

    # Use generic for all non-mock providers
    if key != "mock" and "generic" in _registry:
        from .generic_provider import GenericVtuProvider
        gen = GenericVtuProvider()
        gen._active_provider_code = key
        return gen

    cls = _registry.get(key)
    if not cls:
        # Fall back to routing table if configured provider not found
        if db is not None and service:
            try:
                from ...models import ApiProviderRouting, ApiProvider
                routing_rows = (
                    db.query(ApiProviderRouting)
                    .filter(ApiProviderRouting.service_type == service, ApiProviderRouting.is_active.is_(True))
                    .order_by(ApiProviderRouting.priority)
                    .all()
                )
                for r in routing_rows:
                    provider = db.get(ApiProvider, r.provider_id)
                    if provider and provider.is_active:
                        if provider.code.lower() != "mock":
                            from .generic_provider import GenericVtuProvider
                            gen = GenericVtuProvider()
                            gen._active_provider_code = provider.code
                            return gen
                        cls = _registry.get(provider.code.lower())
                        if cls:
                            return cls()
            except Exception:
                pass
        raise ProviderError(f"VTU provider '{key}' is not registered")

    return cls()
