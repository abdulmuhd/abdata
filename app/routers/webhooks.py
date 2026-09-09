from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.errors import AppError
from ..services import payment_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/payment", summary="Payment gateway webhook (HMAC-verified)")
async def payment_webhook(
    request: Request,
    x_zaply_signature: str | None = Header(None, alias="X-Zaply-Signature"),
    db: Session = Depends(get_db),
):
    raw = await request.body()
    if not payment_service.verify_webhook_signature(raw, x_zaply_signature):
        raise AppError("Invalid webhook signature.", code="bad_signature", status_code=401)
    try:
        event = payment_service.parse_webhook_event(raw)
    except ValueError as exc:
        raise AppError(str(exc), code="bad_payload", status_code=400)

    data = event["data"]
    intent, settled = payment_service.settle_funding(db, data["reference"], gateway_reference=data.get("provider_reference"))
    db.commit()
    return {"received": True, "settled": settled, "reference": data["reference"] if intent else None}
