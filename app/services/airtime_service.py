from sqlalchemy.orm import Session

from ..core.errors import NotFoundError
from ..models import Provider, ServiceTypeEnum, User
from ..schemas.wallet import AirtimePurchaseIn
from ..schemas.common import to_kobo
from .providers.base import get_provider
from .purchase_service import execute_purchase

MIN_AIRTIME_KOBO = 5_000      # ₦50
MAX_AIRTIME_KOBO = 2_000_000  # ₦20,000


def get_network(db: Session, code: str) -> Provider:
    network = (
        db.query(Provider)
        .filter(Provider.code == (code or "").lower(), Provider.service_type == ServiceTypeEnum.AIRTIME)
        .first()
    )
    if not network:
        raise NotFoundError("Selected network is not available")
    return network


def purchase_airtime(db: Session, user: User, payload: AirtimePurchaseIn):
    network = get_network(db, payload.network_code)
    amount_kobo = to_kobo(payload.amount_naira)
    if amount_kobo < MIN_AIRTIME_KOBO:
        from ..core.errors import AppError

        raise AppError("Minimum airtime purchase is ₦50")
    if amount_kobo > MAX_AIRTIME_KOBO:
        from ..core.errors import AppError

        raise AppError("Maximum airtime per transaction is ₦20,000")

    provider = get_provider("airtime", db)
    return execute_purchase(
        db,
        user=user,
        service_type=ServiceTypeEnum.AIRTIME,
        provider_code=network.code,
        customer_ref=payload.phone,
        amount_kobo=amount_kobo,
        details={"network": network.short_name, "recipient": payload.phone},
        narration=f"{network.short_name} airtime for {payload.phone}",
        reference_prefix="AIR",
        idempotency_key=payload.idempotency_key,
        pin=payload.pin,
        run_provider=lambda db_, ref: provider.buy_airtime(
            db_, network_code=network.code, phone=payload.phone, amount_kobo=amount_kobo, reference=ref
        ),
    )
