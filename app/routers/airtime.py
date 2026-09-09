from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..dependencies.auth import get_current_user
from ..models import User
from ..schemas.wallet import AirtimePurchaseIn, TransactionOut
from ..services.airtime_service import purchase_airtime
from ..services.notify import notify_transaction

router = APIRouter(prefix="/airtime", tags=["Airtime"])


@router.post("/purchase", summary="Buy airtime for any Nigerian network")
def buy_airtime(payload: AirtimePurchaseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    txn = purchase_airtime(db, user, payload)
    amount = txn.amount_kobo // 100
    notify_transaction(
        user.id,
        "Airtime Purchase",
        f"₦{amount} {payload.network} airtime sent to {payload.phone}",
        f"/transactions",
    )
    return {
        "success": True,
        "message": f"Airtime delivered to {txn.customer_ref}.",
        "data": TransactionOut.model_validate(txn).model_dump(mode="json"),
    }
