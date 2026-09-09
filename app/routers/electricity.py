from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..dependencies.auth import get_current_user
from ..models import User
from ..schemas.auth import CustomerInfoOut
from ..schemas.wallet import ElectricityPayIn, ElectricityValidateIn, TransactionOut
from ..services.electricity_service import pay_electricity, validate_meter

router = APIRouter(prefix="/electricity", tags=["Electricity"])


@router.post("/validate", summary="Verify a meter number before payment")
def validate(payload: ElectricityValidateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    info = validate_meter(db, payload)
    return {"success": True, "message": "Customer verified." if info.found else "Customer not found.", "data": CustomerInfoOut(found=info.found, customer_name=info.customer_name, address=info.address, meter_type=payload.meter_type, meta=info.meta or {}).model_dump(mode="json")}


@router.post("/pay", summary="Pay an electricity bill")
def pay(payload: ElectricityPayIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    txn = pay_electricity(db, user, payload)
    return {
        "success": True,
        "message": "Payment successful — token sent to the meter owner." if txn.status.value == "successful" else "Payment received.",
        "data": TransactionOut.model_validate(txn).model_dump(mode="json"),
    }
