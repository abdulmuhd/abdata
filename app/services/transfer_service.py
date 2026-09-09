from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..core.errors import AppError, NotFoundError
from ..core.security import generate_reference
from ..models import User, WalletTransaction
from ..models.wallet import LedgerCategory, LedgerDirection
from ..schemas.wallet import TransferIn
from .purchase_service import check_transaction_pin
from . import notification_service, wallet_service


def lookup_recipient(db: Session, phone: str) -> User:
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise NotFoundError("No Zaply user found with that phone number.")
    return user


def send_money(db: Session, sender: User, payload: TransferIn) -> dict:
    amount_kobo = int(payload.amount_naira * 100)
    amount_naira_str = f"\u20a6{payload.amount_naira:,.0f}"

    # 1 — PIN check
    check_transaction_pin(db, sender, payload.pin)

    # 2 — find recipient
    recipient = lookup_recipient(db, payload.recipient_phone)
    if recipient.id == sender.id:
        raise AppError("You cannot transfer to yourself.", code="self_transfer")

    # 3 — debit sender (atomic via SQL WHERE balance >= ...)
    sender_wallet = wallet_service.get_wallet(db, sender.id)
    ref = generate_reference("XFR")
    wallet_service.debit(
        db,
        sender_wallet,
        amount_kobo,
        category=LedgerCategory.TRANSFER,
        narration=f"Transfer to {recipient.full_name or recipient.phone}",
        reference=f"{ref}-S",
    )

    # 4 — credit recipient
    recipient_wallet = wallet_service.get_wallet(db, recipient.id)
    wallet_service.credit(
        db,
        recipient_wallet,
        amount_kobo,
        category=LedgerCategory.TRANSFER,
        narration=f"Transfer from {sender.full_name or sender.phone}",
        reference=f"{ref}-R",
    )

    # 5 — notify sender
    notification_service.notify(
        db,
        sender.id,
        "Transfer successful",
        f"You sent {amount_naira_str} to {recipient.full_name or 'a Zaply user'} ({recipient.phone}).",
        type_="wallet",
        reference=f"{ref}-S",
    )

    # 6 — notify recipient
    notification_service.notify(
        db,
        recipient.id,
        "Money received",
        f"You received {amount_naira_str} from {sender.full_name or 'a Zaply user'} ({sender.phone}).",
        type_="wallet",
        reference=f"{ref}-R",
    )

    db.commit()

    return {
        "reference": ref,
        "recipient_name": recipient.full_name or "Zaply User",
        "recipient_phone": recipient.phone,
        "amount_kobo": amount_kobo,
        "status": "successful",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
