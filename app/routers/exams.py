from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..dependencies.auth import get_current_user
from ..models import Provider, ServiceTypeEnum, User
from ..schemas.auth import ProviderOut
from ..schemas.wallet import ExamPurchaseIn, TransactionOut
from ..services import exam_service

router = APIRouter(prefix="/exam", tags=["Exam PINs"])


@router.get("/bodies", summary="Exam bodies offering e-PINs")
def bodies(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(Provider)
        .filter(Provider.service_type == ServiceTypeEnum.EXAM_PINS, Provider.is_active.is_(True))
        .order_by(Provider.sort_order)
        .all()
    )
    return {"success": True, "message": "OK", "data": [ProviderOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.get("/products", summary="Exam e-PIN products (optionally filtered by body code)")
def products(body: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = exam_service.list_products(db, body) if body else list_products_all(db)
    return {
        "success": True,
        "message": "OK",
        "data": [
            {
                "body_code": r.body_code,
                "product_code": r.product_code,
                "name": r.name,
                "price_kobo": r.price_kobo,
            }
            for r in rows
        ],
    }


def list_products_all(db: Session):
    from ..models import ExamProduct

    return db.query(ExamProduct).filter(ExamProduct.is_active.is_(True)).order_by(ExamProduct.price_kobo).all()


@router.post("/purchase", summary="Buy an exam e-PIN")
def purchase(payload: ExamPurchaseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    txn = exam_service.purchase_pin(db, user, payload)
    return {
        "success": True,
        "message": f"{txn.details.get('product_name', 'PIN')} delivered — view your PIN on the receipt.",
        "data": TransactionOut.model_validate(txn).model_dump(mode="json"),
    }
