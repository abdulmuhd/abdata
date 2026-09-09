from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import normalize_phone


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone: str
    is_verified: bool
    has_pin: bool = False
    last_login_at: Optional[datetime] = None
    created_at: datetime


class UpdateProfileIn(BaseModel):
    full_name: Annotated[str | None, Field(min_length=3, max_length=120)] = None
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v):
        return normalize_phone(v) if v else v


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: Annotated[str, Field(min_length=8, max_length=72)]


class PinUpdateIn(BaseModel):
    """current_pin is required only when a PIN already exists."""

    new_pin: Annotated[str, Field(pattern=r"^\d{4}$")]
    current_pin: Annotated[str | None, Field(pattern=r"^\d{4}$", default=None)]


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    body: str
    reference: str | None = None
    is_read: bool
    created_at: datetime


class VirtualAccountOut(BaseModel):
    bank_name: str
    account_name: str
    account_number: str


class DashboardOut(BaseModel):
    user: UserOut
    balance_kobo: int
    bonus_balance_kobo: int = 0
    unread_notifications: int
    virtual_account: Optional[VirtualAccountOut] = None
