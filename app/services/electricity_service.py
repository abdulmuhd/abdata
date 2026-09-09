from sqlalchemy.orm import Session

from ..core.errors import AppError, NotFoundError
from ..models import Provider, ServiceTypeEnum, User
from ..models.enums import MeterType
from ..schemas.wallet import ElectricityPayIn, ElectricityValidateIn
from .providers.base import CustomerInfo, get_provider
from .purchase_service import execute_purchase
from ..schemas.common import to_kobo

MIN_ELECTRICITY_KOBO = 100_000     # ₦1,000
MAX_ELECTRICITY_KOBO = 10_000_000  # ₦100,000


def get_disco(db: Session, code: str) -> Provider:
    disco = (
        db.query(Provider)
        .filter(Provider.code == (code or "").lower(), Provider.service_type == ServiceTypeEnum.ELECTRICITY)
        .first()
    )
    if not disco:
        raise NotFoundError("Electricity provider not found")
    return disco


def _meter_type(value: str) -> MeterType:
    try:
        return MeterType(value)
    except ValueError:
        raise AppError("Meter type must be prepaid or postpaid")


def validate_meter(db: Session, payload: ElectricityValidateIn) -> CustomerInfo:
    disco = get_disco(db, payload.provider_code)
    mtype = _meter_type(payload.meter_type)
    return get_provider("electricity", db).validate_meter(db, disco_code=disco.code, meter_number=payload.meter_number.strip(), meter_type=mtype)


def pay_electricity(db: Session, user: User, payload: ElectricityPayIn):
    disco = get_disco(db, payload.provider_code)
    mtype = _meter_type(payload.meter_type)
    amount_kobo = to_kobo(payload.amount_naira)
    if amount_kobo < MIN_ELECTRICITY_KOBO:
        raise AppError("Minimum electricity payment is ₦1,000")
    if amount_kobo > MAX_ELECTRICITY_KOBO:
        raise AppError("Maximum electricity payment is ₦100,000")

    provider = get_provider("electricity", db)
    info = provider.validate_meter(db, disco_code=disco.code, meter_number=payload.meter_number.strip(), meter_type=mtype)
    if not info.found:
        raise NotFoundError("We could not verify this meter number. Check it and try again.")

    return execute_purchase(
        db,
        user=user,
        service_type=ServiceTypeEnum.ELECTRICITY,
        provider_code=disco.code,
        customer_ref=payload.meter_number.strip(),
        amount_kobo=amount_kobo,
        details={
            "provider": disco.name,
            "meter_type": mtype.value,
            "customer_name": info.customer_name,
            "address": info.address,
            "recipient_phone": payload.phone,
        },
        narration=f"{disco.name} {mtype.value.title()} token — {payload.meter_number.strip()}",
        reference_prefix="PWR",
        idempotency_key=payload.idempotency_key,
        pin=payload.pin,
        run_provider=lambda db_, ref: provider.pay_electricity(
            db_, disco_code=disco.code, meter_number=payload.meter_number.strip(), meter_type=mtype,
            amount_kobo=amount_kobo, reference=ref,
        ),
    )
