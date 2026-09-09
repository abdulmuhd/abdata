from sqlalchemy.orm import Session

from ..core.errors import NotFoundError
from ..models import Provider, ServiceTypeEnum, User
from ..schemas.wallet import EducationPayIn, EducationValidateIn
from .providers.base import CustomerInfo, get_provider
from .purchase_service import execute_purchase


def get_institution(db: Session, code: str) -> Provider:
    row = (
        db.query(Provider)
        .filter(Provider.code == (code or "").lower(), Provider.service_type == ServiceTypeEnum.EDUCATION)
        .first()
    )
    if not row:
        raise NotFoundError("Institution not found")
    return row


def validate_student(db: Session, payload: EducationValidateIn) -> CustomerInfo:
    institution = get_institution(db, payload.institution_code)
    return get_provider("education", db).validate_student(
        db, institution_code=institution.code, student_ref=payload.student_ref.strip()
    )


def pay_fees(db: Session, user: User, payload: EducationPayIn):
    institution = get_institution(db, payload.institution_code)
    student_ref = payload.student_ref.strip()

    info = get_provider("education", db).validate_student(db, institution_code=institution.code, student_ref=student_ref)
    if not info.found:
        raise NotFoundError("We could not verify this student record. Check the number and try again.")

    return execute_purchase(
        db,
        user=user,
        service_type=ServiceTypeEnum.EDUCATION,
        provider_code=institution.code,
        customer_ref=student_ref,
        amount_kobo=int(payload.amount_naira * 100),
        details={
            "provider": institution.name,
            "customer_name": info.customer_name,
            "recipient_phone": payload.phone,
        },
        narration=f"{institution.name} school fees — {student_ref}",
        reference_prefix="SCH",
        idempotency_key=payload.idempotency_key,
        pin=payload.pin,
        run_provider=lambda db_, ref: get_provider("education", db).pay_school_fees(
            db_, institution_code=institution.code, student_ref=student_ref,
            amount_kobo=int(payload.amount_naira * 100), reference=ref,
        ),
    )
