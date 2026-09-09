from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..dependencies.auth import get_current_user
from ..models import User
from ..schemas.wallet import DataPurchaseIn, TransactionOut
from ..services.data_service import list_plans, purchase_data
from ..services.notify import notify_transaction

router = APIRouter(prefix="/data", tags=["Data"])


@router.get("/plans", summary="Data plans grouped by category (loaded dynamically)")
def plans(network: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = list_plans(db, network.lower() if network else None)
    grouped: dict[str, list] = {}
    for p in rows:
        selling = p.selling_price_kobo or p.price_kobo
        grouped.setdefault(p.category, []).append(
            {
                "plan_code": p.plan_code,
                "network_code": p.network_code,
                "name": p.name,
                "category": p.category,
                "volume_mb": p.volume_mb,
                "validity_days": p.validity_days,
                "price_kobo": selling,
                "original_price_kobo": p.price_kobo,
                "promo_price_kobo": p.promo_price_kobo,
            }
        )
    return {"success": True, "message": "OK", "data": grouped}


@router.post("/purchase", summary="Buy a data bundle")
def buy_data(payload: DataPurchaseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    txn = purchase_data(db, user, payload)
    plan_name = (txn.details or {}).get("plan_name", "Data")
    amount = txn.amount_kobo // 100
    notify_transaction(
        user.id,
        "Data Purchase",
        f"₦{amount} {plan_name} sent to {txn.customer_ref}",
        "/transactions",
    )
    return {
        "success": True,
        "message": f"{plan_name} delivered to {txn.customer_ref}.",
        "data": TransactionOut.model_validate(txn).model_dump(mode="json"),
    }
