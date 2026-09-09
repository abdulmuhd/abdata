from sqlalchemy.orm import Session

from ..core.errors import NotFoundError
from ..models import ExamProduct, Provider, ServiceTypeEnum, User
from ..schemas.wallet import ExamPurchaseIn
from .purchase_service import execute_purchase
from .providers.base import get_provider


def get_body(db: Session, code: str) -> Provider:
    row = (
        db.query(Provider)
        .filter(Provider.code == (code or "").lower(), Provider.service_type == ServiceTypeEnum.EXAM_PINS)
        .first()
    )
    if not row:
        raise NotFoundError("Exam body not found")
    return row


def list_products(db: Session, body_code: str):
    return (
        db.query(ExamProduct)
        .filter(ExamProduct.body_code == body_code.lower(), ExamProduct.is_active.is_(True))
        .order_by(ExamProduct.price_kobo)
        .all()
    )


def purchase_pin(db: Session, user: User, payload: ExamPurchaseIn):
    body = get_body(db, payload.body_code)
    product = (
        db.query(ExamProduct)
        .filter(
            ExamProduct.product_code == payload.product_code,
            ExamProduct.body_code == body.code,
            ExamProduct.is_active.is_(True),
        )
        .first()
    )
    if not product:
        raise NotFoundError("Selected exam product is not available")

    return execute_purchase(
        db,
        user=user,
        service_type=ServiceTypeEnum.EXAM_PINS,
        provider_code=body.code,
        customer_ref=body.short_name,  # receipt shows the issuing body
        amount_kobo=product.price_kobo,  # price always from DB, never client
        details={
            "provider": body.name,
            "product_code": product.product_code,
            "product_name": product.name,
            "recipient_phone": payload.phone,
        },
        narration=f"{body.name} {product.name}",
        reference_prefix="EXM",
        idempotency_key=payload.idempotency_key,
        pin=payload.pin,
        run_provider=lambda db_, ref: get_provider("exam_pins", db).buy_exam_pin(
            db_, body_code=body.code, product_code=product.product_code,
            amount_kobo=product.price_kobo, reference=ref,
        ),
    )
