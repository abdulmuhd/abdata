"""Wallet money-movement engine.

Every naira that moves does so through `credit()` / `debit()`, which write an
immutable ledger row (`WalletTransaction`) inside the caller's DB transaction.
The UPDATE ... WHERE balance >= X guard makes overdrafts impossible even under
concurrent requests.
"""

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..core.errors import InsufficientFundsError
from ..core.security import generate_reference
from ..models import LedgerCategory, LedgerDirection, Wallet, WalletTransaction


def get_wallet(db: Session, user_id: int) -> Wallet:
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).one()
    return wallet


def _move(
    db: Session,
    wallet: Wallet,
    direction: LedgerDirection,
    amount_kobo: int,
    category: LedgerCategory,
    narration: str,
    reference: str | None = None,
    vtu_transaction_id: int | None = None,
    allow_negative: bool = False,
) -> WalletTransaction:
    if amount_kobo <= 0:
        raise ValueError("amount must be positive")

    stmt = update(Wallet)
    if direction is LedgerDirection.DEBIT:
        stmt = stmt.values(balance_kobo=Wallet.balance_kobo - amount_kobo)
        guard = Wallet.balance_kobo >= amount_kobo if not allow_negative else True
    else:
        stmt = stmt.values(balance_kobo=Wallet.balance_kobo + amount_kobo)
        guard = True

    result = db.execute(stmt.where(Wallet.id == wallet.id).where(guard))
    if result.rowcount != 1:
        raise InsufficientFundsError("Insufficient wallet balance for this transaction")

    db.expire(wallet, ["balance_kobo", "total_funded_kobo"])
    balance_after = wallet.balance_kobo
    row = WalletTransaction(
        wallet_id=wallet.id,
        direction=direction,
        category=category,
        amount_kobo=amount_kobo,
        balance_before_kobo=balance_after - amount_kobo if direction is LedgerDirection.CREDIT else balance_after + amount_kobo,
        balance_after_kobo=balance_after,
        reference=reference or generate_reference({"funding": "FND", "refund": "RFD", "adjustment": "ADJ"}.get(category.value, "TXN")),
        narration=narration,
        vtu_transaction_id=vtu_transaction_id,
    )
    db.add(row)
    db.flush()

    if direction is LedgerDirection.CREDIT and category is LedgerCategory.FUNDING:
        db.execute(update(Wallet).where(Wallet.id == wallet.id).values(total_funded_kobo=Wallet.total_funded_kobo + amount_kobo))

    return row


def debit(db: Session, wallet: Wallet, amount_kobo: int, *, category: LedgerCategory, narration: str, **kw) -> WalletTransaction:
    return _move(db, wallet, LedgerDirection.DEBIT, amount_kobo, category, narration, **kw)


def credit(db: Session, wallet: Wallet, amount_kobo: int, *, category: LedgerCategory, narration: str, **kw) -> WalletTransaction:
    return _move(db, wallet, LedgerDirection.CREDIT, amount_kobo, category, narration, **kw)


def credit_bonus(db: Session, wallet: Wallet, amount_kobo: int) -> None:
    """Credit the bonus balance directly (no ledger row, no balance_kobo change)."""
    wallet.bonus_kobo = (wallet.bonus_kobo or 0) + amount_kobo
    db.flush()


def fund_wallet(db: Session, wallet: Wallet, amount_kobo: int, reference: str, gateway_reference: str | None = None) -> WalletTransaction:
    """Credit a wallet from a successful gateway payment (idempotent by reference)."""
    existing = (
        db.query(WalletTransaction)
        .filter(WalletTransaction.reference == reference, WalletTransaction.category == LedgerCategory.FUNDING)
        .first()
    )
    if existing:
        return existing
    row = credit(
        db,
        wallet,
        amount_kobo,
        category=LedgerCategory.FUNDING,
        narration=f"Wallet funded via {gateway_reference or 'payment gateway'}",
        reference=reference,
    )
    return row
