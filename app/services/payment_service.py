"""Wallet funding via a payment gateway.

The gateway abstraction mirrors the Paystack/Flutterwave flow:
  initialize(reference, amount) -> checkout URL   (client is redirected)
  settle(reference)             -> wallet credited once, idempotently
  webhook(body, signature)      -> HMAC-verified settlement event

Secret keys live ONLY here, read from the environment. The client receives
nothing but a public key and a checkout URL.
"""

import hashlib
import hmac
import json

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import PaymentIntent, User
from . import notification_service, wallet_service


def _public_key() -> str:
    return settings.PAYMENT_PUBLIC_KEY


def create_funding_intent(db: Session, user: User, amount_kobo: int) -> PaymentIntent:
    from ..core.security import generate_reference

    intent = PaymentIntent(
        user_id=user.id,
        reference=generate_reference("FND"),
        amount_kobo=amount_kobo,
        status="pending",
    )
    db.add(intent)
    db.flush()
    return intent


def build_checkout(intent: PaymentIntent) -> dict:
    """Return the payload handed to the client to start a gateway checkout."""
    if settings.PAYMENT_GATEWAY == "mock":
        return {
            "reference": intent.reference,
            "amount_kobo": intent.amount_kobo,
            "payment_url": f"/checkout.html?reference={intent.reference}",
            "gateway": "mock",
            "public_key": _public_key(),
        }
    # Real gateways plug in here — e.g. paystack.transaction.initialize(...)
    raise NotImplementedError("Configure PAYMENT_GATEWAY with an implemented adapter")


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    expected = hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected or "", signature or "")


def parse_webhook_event(raw_body: bytes) -> dict:
    try:
        event = json.loads(raw_body)
        if event.get("event") != "charge.success" or not event.get("data", {}).get("reference"):
            raise ValueError()
        return event
    except Exception:
        raise ValueError("Malformed webhook payload")  # noqa: B904


def settle_funding(db: Session, reference: str, gateway_reference: str | None = None) -> tuple[PaymentIntent | None, bool]:
    """Credit the wallet for a successful gateway charge. Idempotent.

    Returns (intent, newly_settled).
    """
    intent = db.query(PaymentIntent).filter(PaymentIntent.reference == reference).first()
    if not intent:
        return None, False
    if intent.status == "successful":
        return intent, False  # already settled — never double-credit

    wallet = wallet_service.get_wallet(db, intent.user_id)
    ledger = wallet_service.fund_wallet(
        db,
        wallet,
        intent.amount_kobo,
        reference=f"{intent.reference}-C",
        gateway_reference=gateway_reference or settings.PAYMENT_GATEWAY,
    )

    intent.status = "successful"
    intent.gateway_reference = gateway_reference
    intent.settled_ledger_ref = ledger.reference
    from ..core.security import utcnow

    intent.paid_at = utcnow()

    user = db.get(User, intent.user_id)
    notification_service.notify_funding(db, user, f"₦{intent.amount_kobo / 100:,.2f}", intent.reference)
    return intent, True
