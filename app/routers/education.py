from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.errors import NotFoundError
from ..dependencies.auth import get_current_user
from ..models import User
from ..schemas.wallet import EducationPayIn, EducationValidateIn, TransactionOut
from ..services import education_service

router = APIRouter(prefix="/education", tags=["Education"])


@router.get("/institutions", summary="Supported institutions")
def institutions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models import Provider, ServiceTypeEnum
    from ..schemas.auth import ProviderOut

    rows = (
        db.query(Provider)
        .filter(Provider.service_type == ServiceTypeEnum.EDUCATION, Provider.is_active.is_(True))
        .order_by(Provider.sort_order)
        .all()
    )
    return {"success": True, "message": "OK", "data": [ProviderOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.post("/validate", summary="Verify a student record")
def validate(payload: EducationValidateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    info = education_service.validate_student(db, payload)
    if not info.found:
        raise NotFoundError("Student record not found. Check the number and try again.")
    return {
        "success": True,
        "message": "Student verified.",
        "data": {"found": True, "customer_name": info.customer_name},
    }


@router.post("/pay", summary="Pay school fees")
def pay(payload: EducationPayIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    txn = education_service.pay_fees(db, user, payload)
    return {
        "success": True,
        "message": "School fees payment successful — receipt number is on your receipt.",
        "data": TransactionOut.model_validate(txn).model_dump(mode="json"),
    }
