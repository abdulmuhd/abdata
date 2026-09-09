from sqlalchemy.orm import Session

from ..models import Notification, User


def notify(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    *,
    type_: str = "system",
    reference: str | None = None,
) -> Notification:
    n = Notification(user_id=user_id, title=title[:120], body=body[:500], type=type_, reference=reference)
    db.add(n)
    db.flush()
    return n


def notify_txn_success(db: Session, user: User, service_label: str, amount_naira: str, reference: str, target: str):
    notify(
        db,
        user.id,
        f"{service_label} successful",
        f"Your {service_label.lower()} payment of {amount_naira} to {target} was successful.",
        type_="transaction",
        reference=reference,
    )


def notify_txn_failed(db: Session, user: User, service_label: str, amount_naira: str, reference: str, reason: str):
    notify(
        db,
        user.id,
        f"{service_label} failed",
        f"Your {service_label.lower()} payment of {amount_naira} failed. The amount has been refunded to your wallet.",
        type_="transaction",
        reference=reference,
    )


def notify_funding(db: Session, user: User, amount_naira: str, reference: str):
    notify(
        db,
        user.id,
        "Wallet funded successfully",
        f"Your wallet was credited with {amount_naira}. Ref: {reference}",
        type_="wallet",
        reference=reference,
    )
