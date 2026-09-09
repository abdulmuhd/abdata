"""Transactional purchase orchestrator.

Flow (single auditable path for every service):
  1. verify transaction PIN (with lockout)
  2. idempotency check — same key returns the original order, never a duplicate
  3. create PENDING VTUTransaction + atomically debit the wallet, COMMIT
     (a crash after this point leaves an auditable pending order, money held)
  4. call the VTU provider adapter
  5. successful → attach provider reference; failed → refund wallet + ledger row
"""

import time
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.errors import AppError, AuthError, PinLockedError, ProviderError
from ..core.security import generate_reference, utcnow, verify_pin, hash_pin
from ..models import ServiceTypeEnum, TxnStatus, User, VTUTransaction
from . import notification_service, wallet_service
from .providers.base import get_provider


def ensure_pin_set(user: User) -> None:
    if not user.pin_hash:
        raise AppError("You need to set a transaction PIN before making payments.", code="pin_not_set", status_code=403)


def check_transaction_pin(db: Session, user: User, pin: str) -> None:
    ensure_pin_set(user)
    now = utcnow()
    locked = user.pin_locked_until.replace(tzinfo=now.tzinfo) if user.pin_locked_until and user.pin_locked_until.tzinfo is None else user.pin_locked_until
    if locked and locked > now:
        secs = int((locked - now).total_seconds())
        raise PinLockedError(f"Too many incorrect PIN attempts. Try again in {max(secs // 60, 1)} minute(s).")
    if pin == "1234":
        raise AppError("Your PIN is set to the default value. Please change your PIN to proceed with purchases.", code="default_pin", status_code=403)
    if not verify_pin(pin, user.pin_hash):
        user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
        if user.pin_failed_attempts >= settings.PIN_MAX_ATTEMPTS:
            user.pin_locked_until = utcnow() + timedelta(seconds=settings.PIN_LOCKOUT_SECONDS)
            user.pin_failed_attempts = 0
        db.commit()
        # 400 (not 401) so API clients don't confuse it with an auth-token failure
        raise AppError("Incorrect transaction PIN.", code="bad_pin")
    user.pin_failed_attempts = 0
    user.pin_locked_until = None


def execute_purchase(
    db: Session,
    *,
    user: User,
    service_type: ServiceTypeEnum,
    provider_code: str,
    customer_ref: str,
    amount_kobo: int,
    buying_price_kobo: int | None = None,
    details: dict,
    narration: str,
    reference_prefix: str,
    idempotency_key: str | None,
    pin: str,
    run_provider,  # Callable[[Session, str], ProviderResult]
) -> VTUTransaction:
    # 1 ── transaction PIN (with lockout after repeated failures)
    check_transaction_pin(db, user, pin)

    # 2 ── idempotency pre-check
    if idempotency_key:
        existing = (
            db.query(VTUTransaction)
            .filter(VTUTransaction.user_id == user.id, VTUTransaction.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return existing

    reference = generate_reference(reference_prefix)
    wallet = wallet_service.get_wallet(db, user.id)

    # ── pre-flight: check provider balance before debiting user wallet ──
    try:
        provider = get_provider(service_type.value, db)
        if hasattr(provider, "get_balance"):
            bal_info = provider.get_balance()
            provider_balance_naira = float(bal_info.get("balance_naira", 0))
            amount_naira = amount_kobo / 100
            if provider_balance_naira < amount_naira:
                raise AppError(
                    "Service temporarily unavailable. Please try again later.",
                    code="low_provider_balance",
                    status_code=503,
                )
    except AppError:
        raise
    except Exception:
        pass  # balance check is best-effort; don't block purchase if check fails

    # ── call provider FIRST (before any wallet debit) ──
    started = time.perf_counter()
    try:
        result = run_provider(db, reference)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        result = None
        reason = str(exc) if isinstance(exc, ProviderError) and str(exc) else f"Provider unavailable ({type(exc).__name__})"
        # create a failed transaction record (no wallet debit)
        txn = VTUTransaction(
            user_id=user.id,
            service_type=service_type,
            provider_code=provider_code,
            customer_ref=customer_ref,
            details=details,
            amount_kobo=amount_kobo,
            status=TxnStatus.FAILED,
            reference=reference,
            idempotency_key=idempotency_key,
            failure_reason=reason[:255],
        )
        db.add(txn)
        db.add(_audit(txn, type("_R", (), {"success": False, "message": reason, "provider_reference": None})(), elapsed_ms))
        db.commit()
        raise AppError("The service provider is currently unreachable. Please try again later.",
                       code="provider_unreachable", status_code=503)

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # ── provider responded — now create transaction + debit wallet ──
    txn = VTUTransaction(
        user_id=user.id,
        service_type=service_type,
        provider_code=provider_code,
        customer_ref=customer_ref,
        details=details,
        amount_kobo=amount_kobo,
        status=TxnStatus.PENDING,
        reference=reference,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        dup = (
            db.query(VTUTransaction)
            .filter(VTUTransaction.user_id == user.id, VTUTransaction.idempotency_key == idempotency_key)
            .one()
        )
        return dup

    wallet_service.debit(
        db,
        wallet,
        amount_kobo,
        category="purchase",
        narration=narration,
        reference=f"{reference}-D",
        vtu_transaction_id=txn.id,
    )
    db.commit()

    if result.success and result.resolved:
        txn.status = TxnStatus.SUCCESSFUL
        txn.provider_reference = result.provider_reference
        if buying_price_kobo is not None and buying_price_kobo > 0:
            txn.profit_kobo = max(amount_kobo - buying_price_kobo, 0)
        if result.raw:
            # e.g. generated exam PIN / school-fee receipt number for the user's receipt
            txn.details = {**(txn.details or {}), **result.raw}
        db.add(_audit(txn, result, elapsed_ms))
        db.commit()
        notification_service.notify_txn_success(
            db, user, SERVICE_LABELS[service_type], _fmt_naira(amount_kobo), reference, customer_ref
        )
        db.commit()
    elif result.success and not result.resolved:
        db.add(_audit(txn, result, elapsed_ms))
        db.commit()  # stays pending — verifiable via /transactions/{reference}/verify
    else:
        _settle_failure(db, txn, result.message or "Provider declined the transaction")
        db.add(_audit(txn, result, elapsed_ms))
        db.commit()

    db.refresh(txn)
    return txn


SERVICE_LABELS = {
    ServiceTypeEnum.AIRTIME: "Airtime top-up",
    ServiceTypeEnum.DATA: "Data purchase",
    ServiceTypeEnum.ELECTRICITY: "Electricity payment",
    ServiceTypeEnum.CABLE: "Cable TV subscription",
    ServiceTypeEnum.EXAM_PINS: "Exam PIN",
    ServiceTypeEnum.EDUCATION: "School fees payment",
}


def _fmt_naira(kobo: int) -> str:
    naira = kobo / 100
    return f"₦{naira:,.0f}" if naira == int(naira) else f"₦{naira:,.2f}"


def _settle_failure(db: Session, txn: VTUTransaction, reason: str):
    txn.status = TxnStatus.FAILED
    txn.failure_reason = reason[:255]
    wallet = wallet_service.get_wallet(db, txn.user_id)
    wallet_service.credit(
        db,
        wallet,
        txn.amount_kobo,
        category="refund",
        narration=f"Refund — {reason[:80]}",
        reference=f"{txn.reference}-R",
        vtu_transaction_id=txn.id,
    )
    user = db.get(User, txn.user_id)
    notification_service.notify_txn_failed(db, user, SERVICE_LABELS[txn.service_type], _fmt_naira(txn.amount_kobo), txn.reference, reason)


def _audit(txn: VTUTransaction, result, elapsed_ms: int):
    from ..models import ApiLog

    return ApiLog(
        provider="mock",
        endpoint=f"/purchase/{txn.service_type.value}",
        request_payload={"ref": txn.reference, "amount": txn.amount_kobo},
        response_payload={"success": result.success, "message": result.message, "provider_ref": result.provider_reference},
        success=result.success,
        duration_ms=elapsed_ms,
    )
