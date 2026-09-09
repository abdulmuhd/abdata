from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import normalize_phone, normalize_phone_or_none


class WalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    balance_kobo: int
    bonus_kobo: int = 0
    currency: str = "NGN"
    total_funded_kobo: int = 0


class FundWalletIn(BaseModel):
    amount_naira: Annotated[float, Field(gt=49, le=1_000_000)]


class FundInitOut(BaseModel):
    reference: str
    amount_kobo: int
    payment_url: str
    gateway: str
    public_key: str = ""


class WalletTxnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: str
    category: str
    amount_kobo: int
    balance_before_kobo: int
    balance_after_kobo: int
    reference: str
    narration: str
    created_at: datetime


# ── Transactions ──────────────────────────────────────────────────────────


class IdemKeyMixin(BaseModel):
    idempotency_key: Annotated[str | None, Field(max_length=64)] = None


class AirtimePurchaseIn(IdemKeyMixin):
    network_code: Annotated[str, Field(min_length=2, max_length=40)]
    phone: str
    amount_naira: Annotated[float, Field(gt=0)]
    pin: Annotated[str, Field(pattern=r"^\d{4}$")]

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v):
        return normalize_phone(v)


class DataPurchaseIn(IdemKeyMixin):
    network_code: str
    phone: str
    plan_code: str
    pin: Annotated[str, Field(pattern=r"^\d{4}$")]

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v):
        return normalize_phone(v)


class ElectricityValidateIn(BaseModel):
    provider_code: str
    meter_number: Annotated[str, Field(min_length=6, max_length=30)]
    meter_type: str  # prepaid | postpaid


class ElectricityPayIn(IdemKeyMixin):
    provider_code: str
    meter_number: Annotated[str, Field(min_length=6, max_length=30)]
    meter_type: str
    customer_name: str = ""
    amount_naira: Annotated[float, Field(gt=0)]
    phone: str | None = None
    pin: Annotated[str, Field(pattern=r"^\d{4}$")]


class CableValidateIn(BaseModel):
    provider_code: str
    smartcard_number: Annotated[str, Field(min_length=5, max_length=30)]


class CablePayIn(IdemKeyMixin):
    provider_code: str
    smartcard_number: Annotated[str, Field(min_length=5, max_length=30)]
    package_code: str
    customer_name: str = ""
    phone: str | None = None
    pin: Annotated[str, Field(pattern=r"^\d{4}$")]


# ── Exam PINs ─────────────────────────────────────────────────────────────


class ExamPurchaseIn(IdemKeyMixin):
    body_code: str
    product_code: str
    phone: str | None = None
    pin: Annotated[str, Field(pattern=r"^\d{4}$")]

    @field_validator("phone")
    @classmethod
    def phone_ok2(cls, v):
        return normalize_phone_or_none(v) if not v else normalize_phone(v)


# ── School fees ───────────────────────────────────────────────────────────


class EducationValidateIn(BaseModel):
    institution_code: str
    student_ref: Annotated[str, Field(min_length=5, max_length=40)]  # matric / application no.


class EducationPayIn(IdemKeyMixin):
    institution_code: str
    student_ref: Annotated[str, Field(min_length=5, max_length=40)]
    student_name: str = ""
    amount_naira: Annotated[float, Field(gt=99)]  # minimum ₦100
    phone: str | None = None
    pin: Annotated[str, Field(pattern=r"^\d{4}$")]


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_type: str
    provider_code: str
    customer_ref: str
    details: dict = {}
    amount_kobo: int
    fee_kobo: int = 0
    status: str
    failure_reason: str | None = None
    reference: str
    provider_reference: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class UnifiedTxnOut(BaseModel):
    """A row in the user-facing history — merges purchases + funding + refunds."""

    reference: str
    txn_type: str            # purchase | funding | refund | adjustment
    service_type: str | None  # airtime/data/electricity/cable (purchases)
    title: str
    counterparty: str | None = None
    direction: str           # credit | debit
    amount_kobo: int
    status: str
    created_at: datetime


# ── P2P Transfer ─────────────────────────────────────────────────────────


class TransferIn(IdemKeyMixin):
    recipient_phone: str
    amount_naira: Annotated[float, Field(gt=99, le=5_000)]
    pin: Annotated[str, Field(pattern=r"^\d{4}$")]

    @field_validator("recipient_phone")
    @classmethod
    def phone_ok(cls, v):
        return normalize_phone(v)
