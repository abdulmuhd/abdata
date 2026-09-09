"""Unified transaction history + receipt + pending verification.

The user-facing feed is built from the wallet ledger so every naira movement
(purchases, funding, refunds) appears exactly once, in order.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.errors import NotFoundError
from ..core.security import generate_reference
from ..dependencies.auth import get_current_user
from ..models import TxnStatus, User, Wallet, WalletTransaction
from ..schemas.common import PageMeta, to_kobo
from ..schemas.wallet import UnifiedTxnOut

router = APIRouter(prefix="/transactions", tags=["Transactions"])

SERVICE_LABELS = {
    "airtime": "Airtime top-up",
    "data": "Data purchase",
    "electricity": "Electricity payment",
    "cable": "Cable TV subscription",
    "exam_pins": "Exam PIN",
    "education": "School fees payment",
}


def _safe_service_type_str(vtxn) -> str | None:
    if vtxn is None:
        return None
    st = vtxn.service_type
    if hasattr(st, "value"):
        return st.value
    return str(st) if st else None


def _serialize(row: WalletTransaction) -> dict:
    vtxn = row.vtu_transaction
    txn_type = {"funding": "funding", "refund": "refund", "adjustment": "adjustment", "purchase": "purchase", "transfer": "transfer"}[row.category.value]

    if vtxn is not None and row.category.value == "purchase":
        svc_str = _safe_service_type_str(vtxn)
        label = SERVICE_LABELS.get(svc_str, svc_str or "service")
        d = vtxn.details or {}
        title = f"{d.get('network') or d.get('provider') or ''} {label}".strip()
        counterparty = vtxn.customer_ref
        service = svc_str
        status = vtxn.status.value
    elif row.category.value == "funding":
        title = "Wallet funding"
        counterparty = None
        service = None
        status = "successful"
        txn_type = "funding"
    elif row.category.value == "transfer":
        title = row.narration or "Wallet transfer"
        counterparty = None
        service = None
        status = "successful"
        txn_type = "transfer"
    else:
        # refund / adjustment — inherit the original purchase context when linked
        if vtxn is not None:
            svc_str = _safe_service_type_str(vtxn)
            label = SERVICE_LABELS.get(svc_str, svc_str or "service")
            d = vtxn.details or {}
            title = f"Refund — {(d.get('network') or d.get('provider') or '')} {label}".strip()
            counterparty = vtxn.customer_ref
            service = svc_str
        else:
            title = "Wallet refund"
            counterparty = None
            service = None
        status = "successful"
        txn_type = "refund"

    out = {
        "reference": vtxn.reference if vtxn is not None else row.reference.replace("-C", "").replace("-R", ""),
        "ledger_reference": row.reference,
        "txn_type": txn_type,
        "service_type": service,
        "title": title,
        "counterparty": counterparty,
        "customer_ref": vtxn.customer_ref if vtxn is not None else None,
        "direction": row.direction.value,
        "amount_kobo": row.amount_kobo,
        "balance_after_kobo": row.balance_after_kobo,
        "narration": row.narration,
        "status": status,
        "created_at": row.created_at.isoformat(),
    }
    if vtxn is not None:
        out["details"] = vtxn.details or {}
        out["failure_reason"] = vtxn.failure_reason
        out["provider_reference"] = vtxn.provider_reference
        out["fee_kobo"] = vtxn.fee_kobo
    else:
        out["details"] = {}
        out["failure_reason"] = None
        out["provider_reference"] = None
        out["fee_kobo"] = 0
    return out


@router.get("", summary="Transaction history (all services)")
def list_transactions(
    page: int = 1,
    per_page: int = 20,
    service: str | None = Query(None, description="airtime | data | electricity | cable | funding | refund"),
    status: str | None = Query(None),
    q: str | None = Query(None, description="search reference / phone / narration"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    page = max(page, 1)
    per_page = min(max(per_page, 1), 50)
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).one()

    from ..models import VTUTransaction

    query = (
        db.query(WalletTransaction)
        .outerjoin(VTUTransaction, WalletTransaction.vtu_transaction_id == VTUTransaction.id)
        .filter(WalletTransaction.wallet_id == wallet.id)
    )

    if service in ("airtime", "data", "electricity", "cable", "exam_pins", "education"):
        query = query.filter(VTUTransaction.service_type == service)
    elif service in ("funding", "refund", "adjustment"):
        query = query.filter(WalletTransaction.category == service)

    if status in ("pending", "successful", "failed"):
        # statuses describe the VTU order; restrict to purchase rows so refund
        # pairs of a failed order don't appear as "successful" noise
        query = query.filter(VTUTransaction.status == status, WalletTransaction.category == "purchase")

    if q:
        like = f"%{q}%"
        query = query.filter(
            (WalletTransaction.reference.ilike(like))
            | (WalletTransaction.narration.ilike(like))
            | (VTUTransaction.customer_ref.ilike(like))
            | (VTUTransaction.reference.ilike(like))
        )

    total = query.count()
    rows = query.order_by(WalletTransaction.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    data = {
        "items": [_serialize(r) for r in rows],
        "meta": PageMeta(page=page, per_page=per_page, total=total, total_pages=max((total + per_page - 1) // per_page, 1)).model_dump(mode="json"),
    }
    return {"success": True, "message": "OK", "data": data}


@router.get("/{reference}", summary="Transaction receipt")
def get_transaction(reference: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).one()
    row = (
        db.query(WalletTransaction)
        .filter(
            WalletTransaction.wallet_id == wallet.id,
            (WalletTransaction.reference == reference)
            | (WalletTransaction.reference == f"{reference}-D")
            | (WalletTransaction.reference.like(f"{reference}%")),
        )
        .order_by(WalletTransaction.id.asc())
        .first()
    )
    if not row:
        raise NotFoundError("Transaction not found.")
    return {"success": True, "message": "OK", "data": _serialize(row)}


@router.post("/{reference}/verify", summary="Re-check a pending transaction at the provider")
def verify_transaction(reference: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.purchase_service import _settle_failure  # reuse refund path

    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).one()
    row = (
        db.query(WalletTransaction)
        .filter(WalletTransaction.wallet_id == wallet.id, WalletTransaction.reference.like(f"{reference}%"))
        .first()
    )
    if not row or row.vtu_transaction is None:
        raise NotFoundError("Transaction not found.")
    txn = row.vtu_transaction
    if txn.status != TxnStatus.PENDING:
        return {"success": True, "message": "No changes.", "data": _serialize(row)}

    # Sandbox semantics: any pending order older than a few seconds resolved successfully.
    # Real adapters would call provider.query_status(reference).
    from ..core.security import utcnow

    age = (utcnow() - txn.created_at.replace(tzinfo=utcnow().tzinfo)).total_seconds()
    if age >= 3:
        txn.status = TxnStatus.SUCCESSFUL
        txn.provider_reference = generate_reference("PRV")
    db.commit()
    return {"success": True, "message": "Status updated." if age >= 3 else "Still processing.", "data": _serialize(db.refresh(row))}
