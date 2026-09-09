from sqlalchemy.orm import Session

from ..core.errors import NotFoundError
from ..models import DataPlan, DisabledDataCategory, Provider, ServiceTypeEnum, User
from ..schemas.wallet import DataPurchaseIn
from .providers.base import get_provider
from .purchase_service import execute_purchase


def list_plans(db: Session, network_code: str | None = None):
    disabled = set(
        (r.network_code, r.category)
        for r in db.query(DisabledDataCategory).all()
    )
    q = db.query(DataPlan).filter(DataPlan.is_active.is_(True))
    if network_code:
        q = q.filter(DataPlan.network_code == network_code.lower())
    rows = q.order_by(DataPlan.category, DataPlan.price_kobo).all()
    return [p for p in rows if (p.network_code, p.category) not in disabled]


def purchase_data(db: Session, user: User, payload: DataPurchaseIn):
    network = (
        db.query(Provider)
        .filter(Provider.code == payload.network_code.lower(), Provider.service_type == ServiceTypeEnum.AIRTIME)
        .first()
    )
    if not network:
        raise NotFoundError("Selected network is not available")

    plan = (
        db.query(DataPlan)
        .filter(
            DataPlan.plan_code == payload.plan_code,
            DataPlan.network_code == network.code,
            DataPlan.is_active.is_(True),
        )
        .first()
    )
    if not plan:
        raise NotFoundError("Data plan not found for this network")

    # price ALWAYS comes from the DB plan row — never from the client
    # Use selling_price if set, otherwise fall back to price_kobo
    selling_price = plan.selling_price_kobo or plan.price_kobo
    provider = get_provider("data", db)
    return execute_purchase(
        db,
        user=user,
        service_type=ServiceTypeEnum.DATA,
        provider_code=network.code,
        customer_ref=payload.phone,
        amount_kobo=selling_price,
        buying_price_kobo=plan.buying_price_kobo or plan.price_kobo,
        details={
            "network": network.short_name,
            "plan_code": plan.plan_code,
            "plan_name": plan.name,
            "volume_mb": plan.volume_mb,
            "validity_days": plan.validity_days,
            "category": plan.category,
            "recipient": payload.phone,
        },
        narration=f"{network.short_name} {plan.name} for {payload.phone}",
        reference_prefix="DAT",
        idempotency_key=payload.idempotency_key,
        pin=payload.pin,
        run_provider=lambda db_, ref: provider.buy_data(
            db_, network_code=network.code, phone=payload.phone, plan_code=plan.plan_code, amount_kobo=plan.buying_price_kobo or plan.price_kobo, reference=ref,
            provider_plan_id=plan.provider_plan_id,
        ),
    )
