from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..dependencies.auth import get_current_user
from ..models import User
from ..schemas.auth import CablePackageOut, CustomerInfoOut
from ..schemas.wallet import CablePayIn, CableValidateIn, TransactionOut
from ..services.cable_service import list_packages, pay_cable, validate_smartcard

router = APIRouter(prefix="/cable", tags=["Cable TV"])


@router.get("/packages", summary="Subscription packages for a provider")
def packages(provider: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = list_packages(db, provider)
    return {
        "success": True,
        "message": "OK",
        "data": [
            {
                "package_code": p.package_code,
                "provider_code": p.provider_code,
                "name": p.name,
                "price_kobo": p.selling_price_kobo or p.price_kobo,
                "validity_days": p.validity_days,
            }
            for p in rows
        ],
    }


@router.post("/validate", summary="Verify a smartcard / IUC number")
def validate(payload: CableValidateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    info = validate_smartcard(db, payload)
    return {
        "success": True,
        "message": "Customer verified." if info.found else "Customer not found.",
        "data": CustomerInfoOut(found=info.found, customer_name=info.customer_name, address=info.address, meta=info.meta or {}).model_dump(mode="json"),
    }


@router.post("/pay", summary="Pay a cable TV subscription")
def pay(payload: CablePayIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    txn = pay_cable(db, user, payload)
    return {
        "success": True,
        "message": f"Subscription active on {txn.customer_ref}." if txn.status.value == "successful" else "Payment received.",
        "data": TransactionOut.model_validate(txn).model_dump(mode="json"),
    }
