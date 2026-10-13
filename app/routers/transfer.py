from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..dependencies.auth import get_current_user
from ..models import User
from ..schemas.common import normalize_phone
from ..schemas.wallet import TransferIn
from ..services import transfer_service

router = APIRouter(prefix="/transfer", tags=["Transfer"])


class RecipientOut(BaseModel):
    name: str
    phone: str


@router.get("/recipient/{phone}")
def find_recipient(phone: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    normalized = normalize_phone(phone)
    recipient = transfer_service.lookup_recipient(db, normalized)
    return {
        "success": True,
        "message": "OK",
        "data": {
            "name": recipient.full_name or "ElevenData User",
            "phone": recipient.phone,
        },
    }


@router.post("/send", summary="Transfer balance to another ElevenData user")
def send_money(payload: TransferIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    result = transfer_service.send_money(db, user, payload)
    return {
        "success": True,
        "message": f"₦{result['amount_kobo'] / 100:,.0f} sent to {result['recipient_name']}.",
        "data": result,
    }
