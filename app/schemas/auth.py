from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import normalize_phone


# ── Auth requests ─────────────────────────────────────────────────────────


class RegisterIn(BaseModel):
    full_name: Annotated[str, Field(min_length=3, max_length=120)]
    email: str
    phone: str
    password: Annotated[str, Field(min_length=8, max_length=72)]
    referral_code: str | None = None

    @field_validator("email")
    @classmethod
    def email_ok(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v: str) -> str:
        return normalize_phone(v)


class LoginIn(BaseModel):
    phone: str
    password: str

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v: str) -> str:
        return normalize_phone(v)


class AdminLoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_ok(cls, v: str) -> str:
        return v.strip().lower()


class RefreshIn(BaseModel):
    refresh_token: str = ""


class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    reset_token: str
    new_password: Annotated[str, Field(min_length=8, max_length=72)]


class VerifyEmailIn(BaseModel):
    email: str
    code: Annotated[str, Field(min_length=6, max_length=6)]


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ── Generic responses ─────────────────────────────────────────────────────


class MessageOut(BaseModel):
    message: str


class ForgotPasswordOut(BaseModel):
    message: str
    dev_reset_token: str | None = None  # only populated outside production


# ── Catalog / provider responses ──────────────────────────────────────────


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    short_name: str
    service_type: str
    color: str | None = None


class CustomerInfoOut(BaseModel):
    found: bool
    customer_name: str | None = None
    address: str | None = None
    meter_type: str | None = None
    meta: dict = {}


class DataPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_code: str
    network_code: str
    name: str
    category: str
    volume_mb: int
    validity_days: int
    price_kobo: int


class CablePackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    package_code: str
    provider_code: str
    name: str
    price_kobo: int
    validity_days: int

    @classmethod
    def from_orm_model(cls, pkg):
        return cls(
            package_code=pkg.package_code,
            provider_code=pkg.provider_code,
            name=pkg.name,
            price_kobo=pkg.selling_price_kobo or pkg.price_kobo,
            validity_days=pkg.validity_days,
        )


class ComingSoonOut(BaseModel):
    code: str
    name: str
    icon: str = ""
    note: str = ""


class ServicesCatalog(BaseModel):
    airtime_networks: list[ProviderOut]
    electricity_providers: list[ProviderOut]
    cable_providers: list[ProviderOut]
    coming_soon: list[ComingSoonOut]
