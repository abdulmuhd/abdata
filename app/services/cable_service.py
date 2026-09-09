from sqlalchemy.orm import Session

from ..core.errors import NotFoundError
from ..models import CablePackage, Provider, ServiceTypeEnum, User
from ..schemas.wallet import CablePayIn, CableValidateIn
from .providers.base import CustomerInfo, get_provider
from .purchase_service import execute_purchase


def get_cable_provider(db: Session, code: str) -> Provider:
    row = (
        db.query(Provider)
        .filter(Provider.code == (code or "").lower(), Provider.service_type == ServiceTypeEnum.CABLE)
        .first()
    )
    if not row:
        raise NotFoundError("Cable TV provider not found")
    return row


def list_packages(db: Session, provider_code: str):
    return (
        db.query(CablePackage)
        .filter(CablePackage.provider_code == provider_code.lower(), CablePackage.is_active.is_(True))
        .order_by(CablePackage.price_kobo)
        .all()
    )


def validate_smartcard(db: Session, payload: CableValidateIn) -> CustomerInfo:
    cable = get_cable_provider(db, payload.provider_code)
    return get_provider("cable", db).validate_smartcard(db, cable_code=cable.code, smartcard_number=payload.smartcard_number.strip())


def pay_cable(db: Session, user: User, payload: CablePayIn):
    cable = get_cable_provider(db, payload.provider_code)
    package = (
        db.query(CablePackage)
        .filter(
            CablePackage.package_code == payload.package_code,
            CablePackage.provider_code == cable.code,
            CablePackage.is_active.is_(True),
        )
        .first()
    )
    if not package:
        raise NotFoundError("Selected package is not available")

    provider = get_provider("cable", db)
    info = provider.validate_smartcard(db, cable_code=cable.code, smartcard_number=payload.smartcard_number.strip())
    if not info.found:
        raise NotFoundError("We could not verify this smartcard number. Check it and try again.")

    # Use selling_price if set, otherwise fall back to price_kobo
    selling_price = package.selling_price_kobo or package.price_kobo
    buying_price = package.buying_price_kobo or package.price_kobo

    return execute_purchase(
        db,
        user=user,
        service_type=ServiceTypeEnum.CABLE,
        provider_code=cable.code,
        customer_ref=payload.smartcard_number.strip(),
        amount_kobo=selling_price,
        buying_price_kobo=buying_price,
        details={
            "provider": cable.name,
            "package_code": package.package_code,
            "package_name": package.name,
            "validity_days": package.validity_days,
            "customer_name": info.customer_name,
            "recipient_phone": payload.phone,
        },
        narration=f"{cable.name} {package.name} — {payload.smartcard_number.strip()}",
        reference_prefix="TV",
        idempotency_key=payload.idempotency_key,
        pin=payload.pin,
        run_provider=lambda db_, ref: provider.pay_cable(
            db_, cable_code=cable.code, smartcard_number=payload.smartcard_number.strip(),
            package_code=package.package_code, amount_kobo=buying_price, reference=ref,
        ),
    )
