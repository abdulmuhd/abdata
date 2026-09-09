from datetime import datetime
from pydantic import BaseModel


class PromoCodeCreate(BaseModel):
    code: str
    discount_percent: int = 0
    discount_kobo: int = 0
    max_uses: int = 0
    min_amount_kobo: int = 0
    is_active: bool = True
    expires_at: datetime | None = None


class PromoCodeUpdate(BaseModel):
    discount_percent: int | None = None
    discount_kobo: int | None = None
    max_uses: int | None = None
    min_amount_kobo: int | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None


class PromoCodeOut(BaseModel):
    id: int
    code: str
    discount_percent: int
    discount_kobo: int
    max_uses: int
    used_count: int
    min_amount_kobo: int
    is_active: bool
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
