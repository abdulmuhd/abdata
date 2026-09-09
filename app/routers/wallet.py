from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.errors import NotFoundError, ValidationError
from ..core.security import generate_reference
from ..dependencies.auth import get_current_user
from ..models import PaymentIntent, User, Wallet, WalletTransaction
from ..schemas.common import ApiResponse, PagedData, PageMeta, to_kobo
from ..schemas.wallet import FundInitOut, FundWalletIn, WalletOut, WalletTxnOut
from ..services import payment_service, wallet_service

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.get("", summary="Wallet balance")
def get_wallet(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).one()
    return {"success": True, "message": "OK", "data": WalletOut.model_validate(wallet).model_dump(mode="json")}


@router.get("/transactions", summary="Wallet ledger (credits & debits)")
def wallet_transactions(
    page: int = 1,
    per_page: int = 20,
    direction: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    page = max(page, 1)
    per_page = min(max(per_page, 1), 50)
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).one()

    q = db.query(WalletTransaction).filter(WalletTransaction.wallet_id == wallet.id)
    if direction in ("credit", "debit"):
        q = q.filter(WalletTransaction.direction == direction)
    if category:
        q = q.filter(WalletTransaction.category == category)

    total = q.count()
    rows = q.order_by(WalletTransaction.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    data = PagedData[WalletTxnOut](
        items=[WalletTxnOut.model_validate(r) for r in rows],
        meta=PageMeta(page=page, per_page=per_page, total=total, total_pages=max((total + per_page - 1) // per_page, 1)),
    ).model_dump(mode="json")
    return {"success": True, "message": "OK", "data": data}


@router.post("/fund", summary="Start a wallet funding checkout")
def fund_wallet(payload: FundWalletIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    amount_kobo = to_kobo(payload.amount_naira)
    intent = payment_service.create_funding_intent(db, user, amount_kobo)
    checkout = payment_service.build_checkout(intent)
    db.commit()

    data = FundInitOut(
        reference=intent.reference,
        amount_kobo=amount_kobo,
        payment_url=checkout["payment_url"],
        gateway=checkout["gateway"],
        public_key=checkout.get("public_key", ""),
    )
    return {
        "success": True,
        "message": f"Checkout created — pay ₦{amount_kobo / 100:,.2f}",
        "data": data.model_dump(mode="json"),
    }


@router.post("/fund/settle", summary="Sandbox settlement callback (mock gateway only)")
def settle_funding(reference: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Simulates the gateway redirect/webhook completing a payment. Disabled for real gateways."""
    if settings.PAYMENT_GATEWAY != "mock":
        raise ValidationError("Direct settlement is disabled when a real payment gateway is configured.")
    intent, settled = payment_service.settle_funding(db, reference)
    if not intent:
        raise NotFoundError("Payment reference not found.")
    if intent.user_id != user.id:
        raise NotFoundError("Payment reference not found.")
    db.commit()
    msg = "Payment successful — wallet credited." if settled else "Payment was already completed."
    return {"success": True, "message": msg, "data": {"reference": intent.reference, "status": intent.status}}


@router.get("/funding/{reference}", summary="Check funding status")
def funding_status(reference: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    intent = db.query(PaymentIntent).filter(PaymentIntent.reference == reference, PaymentIntent.user_id == user.id).first()
    if not intent:
        raise NotFoundError("Payment reference not found.")
    return {
        "success": True,
        "message": "OK",
        "data": {"reference": intent.reference, "amount_kobo": intent.amount_kobo, "status": intent.status},
    }
