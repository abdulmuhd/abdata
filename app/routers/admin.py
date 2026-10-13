"""Admin console API — analytics overview, user management, transaction browser,
data-plan pricing, broadcast notifications and outbound webhook configuration."""

from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, cast as sa_cast, func as sqlfunc, select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.errors import AppError, NotFoundError, ValidationError
from ..core.security import generate_reference, hash_password, hash_pin
from ..dependencies.auth import get_current_admin, is_admin_email
from ..models import (
    AppSetting,
    CablePackage,
    DataPlan,
    DisabledDataCategory,
    LedgerCategory,
    Notification,
    PromoCode,
    User,
    VTUTransaction,
    Wallet,
)
from ..models.enums import ServiceTypeEnum, TxnStatus
from ..schemas.promo import PromoCodeCreate, PromoCodeOut, PromoCodeUpdate
from ..services import wallet_service
from ..services.providers import get_provider

router = APIRouter(prefix="/admin", tags=["Admin"])

WEBHOOK_URL_KEY = "outbound_webhook_url"


def require_permission(permission: str):
    """Dependency factory — raises 403 if user lacks the given permission."""
    def _check(user: User = Depends(get_current_admin), db: Session = Depends(get_db)):
        if is_admin_email(user.email):
            return user
        from ..models.system_user import SystemUser
        su = db.query(SystemUser).filter(SystemUser.user_id == user.id, SystemUser.status == "active").first()
        if not su or not su.role:
            raise HTTPException(403, "Access denied.")
        perm_codes = {p.code for p in su.role.permissions}
        if permission not in perm_codes:
            raise HTTPException(403, "Access denied.")
        return user
    return _check


# ── schemas ──────────────────────────────────────────────────────────────


class StatusIn(BaseModel):
    is_active: bool


class DataPlanCreateIn(BaseModel):
    network_code: str = Field(min_length=2, max_length=40)
    plan_code: str = Field(min_length=3, max_length=60)
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=1, max_length=40)
    volume_mb: int = Field(gt=0, le=1_000_000)
    validity_days: int = Field(gt=0, le=3650, default=30)
    buying_price_kobo: int | None = Field(default=None, ge=0, le=50_000_000)
    selling_price_kobo: int = Field(ge=0, le=50_000_000)
    promo_price_kobo: int | None = Field(default=None, ge=0, le=50_000_000)
    is_active: bool = True


class DataPlanEditIn(BaseModel):
    network_code: str | None = Field(default=None, min_length=2, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    volume_mb: int | None = Field(default=None, gt=0, le=1_000_000)
    validity_days: int | None = Field(default=None, gt=0, le=3650)
    buying_price_kobo: int | None = Field(default=None, ge=0, le=50_000_000)
    selling_price_kobo: int | None = Field(default=None, ge=0, le=50_000_000)
    promo_price_kobo: int | None = Field(default=None, ge=0, le=50_000_000)
    is_active: bool | None = None


class PlanUpdateIn(BaseModel):
    price_kobo: int | None = Field(default=None, ge=500, le=50_000_000)
    buying_price_kobo: int | None = Field(default=None, ge=0, le=50_000_000)
    selling_price_kobo: int | None = Field(default=None, ge=0, le=50_000_000)
    promo_price_kobo: int | None = Field(default=None, ge=0, le=50_000_000)
    is_active: bool | None = None


class BroadcastIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=3, max_length=500)
    email: str | None = None  # None = send to all active users


class WebhookIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)


class AdminFundIn(BaseModel):
    amount_naira: float = Field(gt=0, le=5_000_000)
    note: str | None = Field(default=None, max_length=140)


class UserEditIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = None


class AdminResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class AdminResetPinIn(BaseModel):
    new_pin: str = Field(pattern=r"^\d{4}$")


class AdminDebitIn(BaseModel):
    amount_naira: float = Field(gt=0, le=5_000_000)
    note: str | None = Field(default=None, max_length=140)


# ── profit / loss ────────────────────────────────────────────────────────


@router.get("/profit-loss", summary="Platform profit & loss summary")
def profit_loss(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    now = datetime.utcnow()
    since = now - timedelta(days=days)

    known_services = [s.value for s in ServiceTypeEnum]
    successful_txns = (
        db.query(VTUTransaction)
        .filter(
            VTUTransaction.status == TxnStatus.SUCCESSFUL,
            VTUTransaction.created_at >= since,
            sa_cast(VTUTransaction.service_type, String).in_(known_services),
        )
        .all()
    )

    total_revenue_kobo = 0
    total_profit_kobo = 0
    by_service = {}

    for txn in successful_txns:
        svc = _safe_service_type(txn)

        revenue = txn.amount_kobo
        total_revenue_kobo += revenue

        profit = txn.profit_kobo or 0
        total_profit_kobo += profit

        if svc not in by_service:
            by_service[svc] = {"revenue_kobo": 0, "profit_kobo": 0, "count": 0}
        by_service[svc]["revenue_kobo"] += revenue
        by_service[svc]["profit_kobo"] += profit
        by_service[svc]["count"] += 1

    service_breakdown = []
    for svc, data in by_service.items():
        service_breakdown.append({
            "service": svc,
            "count": data["count"],
            "revenue_kobo": data["revenue_kobo"],
            "profit_kobo": data["profit_kobo"],
        })
    service_breakdown.sort(key=lambda x: x["profit_kobo"], reverse=True)

    return {
        "success": True,
        "message": "OK",
        "data": {
            "days": days,
            "revenue_kobo": total_revenue_kobo,
            "cost_kobo": total_revenue_kobo - total_profit_kobo,
            "profit_kobo": total_profit_kobo,
            "transaction_count": len(successful_txns),
            "services": service_breakdown,
        },
    }


def _safe_service_type(txn: VTUTransaction) -> str:
    st = txn.service_type
    if isinstance(st, ServiceTypeEnum):
        return st.value
    return str(st) if st else "unknown"


# ── helpers ──────────────────────────────────────────────────────────────


def _get_setting(db: Session, key: str):
    row = db.get(AppSetting, key)
    return row.value if row else None


def _set_setting(db: Session, key: str, value):
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.flush()


def _page_meta(page: int, per_page: int, total: int):
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": max((total + per_page - 1) // per_page, 1),
    }


# ── overview / analytics ─────────────────────────────────────────────────


@router.get("/overview", summary="Platform-wide stats, charts series and service mix")
def overview(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    now = datetime.utcnow()

    users_total = db.query(sqlfunc.count(User.id)).scalar() or 0
    users_active = db.query(sqlfunc.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
    users_new_7d = (
        db.query(sqlfunc.count(User.id)).filter(User.created_at >= now - timedelta(days=7)).scalar() or 0
    )

    balances = db.query(sqlfunc.coalesce(sqlfunc.sum(Wallet.balance_kobo), 0)).scalar() or 0
    funded = db.query(sqlfunc.coalesce(sqlfunc.sum(Wallet.total_funded_kobo), 0)).scalar() or 0

    my_wallet = db.query(Wallet).filter(Wallet.user_id == admin.id).first()
    my_balance = my_wallet.balance_kobo if my_wallet else 0

    # status breakdown (all txns)
    status_rows = (
        db.query(VTUTransaction.status, sqlfunc.count(VTUTransaction.id), sqlfunc.coalesce(sqlfunc.sum(VTUTransaction.amount_kobo), 0))
        .group_by(VTUTransaction.status)
        .all()
    )
    by_status = {s.value: {"count": c, "volume_kobo": v} for s, c, v in status_rows}

    # service mix (successful only)
    service_rows = (
        db.query(
            sa_cast(VTUTransaction.service_type, String),
            sqlfunc.count(VTUTransaction.id),
            sqlfunc.coalesce(sqlfunc.sum(VTUTransaction.amount_kobo), 0),
        )
        .filter(VTUTransaction.status == TxnStatus.SUCCESSFUL)
        .group_by(sa_cast(VTUTransaction.service_type, String))
        .all()
    )
    by_service = {s: {"count": c, "volume_kobo": v} for s, c, v in service_rows}

    # 14-day daily series of successful purchases
    start = (now - timedelta(days=13)).date()
    day_col = sqlfunc.date(VTUTransaction.created_at)
    series_rows = (
        db.query(day_col, sqlfunc.count(VTUTransaction.id), sqlfunc.coalesce(sqlfunc.sum(VTUTransaction.amount_kobo), 0))
        .filter(
            VTUTransaction.status == TxnStatus.SUCCESSFUL,
            VTUTransaction.created_at >= datetime(start.year, start.month, start.day),
        )
        .group_by(day_col)
        .all()
    )
    lookup = {str(d): {"count": c, "volume_kobo": v} for d, c, v in series_rows}
    series = []
    for i in range(14):
        day = (start + timedelta(days=i)).isoformat()
        hit = lookup.get(day, {})
        series.append({"day": day, "count": hit.get("count", 0), "volume_kobo": hit.get("volume_kobo", 0)})

    signups = (
        db.query(User).order_by(User.id.desc()).limit(5).all()
    )

    # Referral stats
    total_referrals = db.query(sqlfunc.count(User.id)).filter(User.referred_by.isnot(None)).scalar() or 0
    referred_users_7d = db.query(sqlfunc.count(User.id)).filter(
        User.referred_by.isnot(None),
        User.created_at >= datetime.now(timezone.utc) - timedelta(days=7),
    ).scalar() or 0

    # Profit stats (successful transactions only)
    today_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)

    profit_today = db.query(sqlfunc.coalesce(sqlfunc.sum(VTUTransaction.profit_kobo), 0)).filter(
        VTUTransaction.status == TxnStatus.SUCCESSFUL,
        VTUTransaction.created_at >= today_start,
    ).scalar() or 0

    profit_month = db.query(sqlfunc.coalesce(sqlfunc.sum(VTUTransaction.profit_kobo), 0)).filter(
        VTUTransaction.status == TxnStatus.SUCCESSFUL,
        VTUTransaction.created_at >= month_start,
    ).scalar() or 0

    profit_total = db.query(sqlfunc.coalesce(sqlfunc.sum(VTUTransaction.profit_kobo), 0)).filter(
        VTUTransaction.status == TxnStatus.SUCCESSFUL,
    ).scalar() or 0

    return {
        "success": True,
        "message": "OK",
        "data": {
            "users": {
                "total": users_total,
                "active": users_active,
                "blocked": users_total - users_active,
                "new_7d": users_new_7d,
            },
            "wallet": {"balance_sum_kobo": balances, "funded_sum_kobo": funded},
            "me": {
                "full_name": admin.full_name,
                "email": admin.email,
                "balance_kobo": my_balance,
            },
            "transactions": {"by_status": by_status, "by_service": by_service},
            "profit": {
                "today_kobo": profit_today,
                "month_kobo": profit_month,
                "total_kobo": profit_total,
            },
            "series_14d": series,
            "recent_signups": [
                {"id": u.id, "full_name": u.full_name, "email": u.email, "created_at": u.created_at.isoformat()}
                for u in signups
            ],
            "referrals": {
                "total": total_referrals,
                "new_7d": referred_users_7d,
            },
        },
    }


# ── user management ──────────────────────────────────────────────────────


@router.get("/users", summary="Browse users (search, paginate)")
def list_users(
    q: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(User.full_name.ilike(like) | User.email.ilike(like) | User.phone.ilike(like))

    total = query.count()
    rows = (
        query.order_by(User.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    ids = [u.id for u in rows]
    balances: dict[int, int] = {}
    txn_counts: dict[int, int] = {}
    if ids:
        for w in db.query(Wallet).filter(Wallet.user_id.in_(ids)):
            balances[w.user_id] = w.balance_kobo
        counts = (
            db.query(VTUTransaction.user_id, sqlfunc.count(VTUTransaction.id))
            .filter(VTUTransaction.user_id.in_(ids))
            .group_by(VTUTransaction.user_id)
            .all()
        )
        txn_counts = dict(counts)

    return {
        "success": True,
        "message": "OK",
        "data": {
            "items": [
                {
                    "id": u.id,
                    "full_name": u.full_name,
                    "email": u.email,
                    "phone": u.phone,
                    "is_active": u.is_active,
                    "balance_kobo": balances.get(u.id, 0),
                    "txn_count": txn_counts.get(u.id, 0),
                    "created_at": u.created_at.isoformat(),
                }
                for u in rows
            ],
            "meta": _page_meta(page, per_page, total),
        },
    }


@router.get("/users/export", summary="Export users as CSV, Excel or JSON")
def export_users(
    q: str | None = None,
    format: str = Query("csv", regex="^(csv|xlsx|json)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    import io
    import json as _json
    from fastapi.responses import StreamingResponse

    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(User.full_name.ilike(like) | User.email.ilike(like) | User.phone.ilike(like))

    rows = query.order_by(User.id.asc()).limit(5000).all()
    ids = [u.id for u in rows]
    balances: dict[int, int] = {}
    txn_counts: dict[int, int] = {}
    if ids:
        for w in db.query(Wallet).filter(Wallet.user_id.in_(ids)):
            balances[w.user_id] = w.balance_kobo
        counts = (
            db.query(VTUTransaction.user_id, sqlfunc.count(VTUTransaction.id))
            .filter(VTUTransaction.user_id.in_(ids))
            .group_by(VTUTransaction.user_id)
            .all()
        )
        txn_counts = dict(counts)

    headers = ["ID", "Name", "Email", "Phone", "Status", "Balance (₦)", "Transactions", "Joined"]
    data = []
    for u in rows:
        data.append({
            "ID": u.id,
            "Name": u.full_name,
            "Email": u.email,
            "Phone": u.phone or "",
            "Status": "Active" if u.is_active else "Blocked",
            "Balance (₦)": round(balances.get(u.id, 0) / 100, 2),
            "Transactions": txn_counts.get(u.id, 0),
            "Joined": u.created_at.strftime("%Y-%m-%d %H:%M"),
        })

    ts = datetime.now().strftime("%Y%m%d")
    if format == "json":
        buf = io.BytesIO(_json.dumps(data, ensure_ascii=False, indent=2).encode())
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=users-{ts}.json"},
        )

    if format == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for row in data:
            ws.append([row[h] for h in headers])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=users-{ts}.xlsx"},
        )

    # CSV (default)
    import csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in data:
        writer.writerow([row[h] for h in headers])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=users-{ts}.csv"},
    )


@router.patch("/users/{user_id}/status", summary="Block or unblock a user account")
def set_user_status(
    user_id: int,
    payload: StatusIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if user_id == admin.id and not payload.is_active:
        from ..core.errors import ValidationError

        raise ValidationError("You cannot block your own admin account.")
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    user.is_active = payload.is_active
    db.commit()
    return {
        "success": True,
        "message": f"{user.full_name} {'unblocked' if user.is_active else 'blocked'}.",
        "data": {"id": user.id, "is_active": user.is_active},
    }


@router.post("/users/{user_id}/fund", summary="Manually credit a user's wallet")
def fund_user_wallet(
    user_id: int,
    payload: AdminFundIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")

    amount_kobo = int(round(payload.amount_naira * 100))
    if amount_kobo < 5000:
        raise ValidationError("Minimum credit is ₦50.")

    wallet = wallet_service.get_wallet(db, user.id)
    reference = generate_reference("ADJ")
    note = (payload.note or "").strip()

    txn = wallet_service.credit(
        db,
        wallet,
        amount_kobo,
        category=LedgerCategory.ADJUSTMENT,
        narration=f"Manual credit by admin ({admin.email})" + (f" — {note}" if note else ""),
        reference=reference,
    )
    db.add(
        Notification(
            user_id=user.id,
            type="wallet",
            title="Wallet credited",
            body=(
                f"Your wallet was credited with ₦{amount_kobo / 100:,.2f}."
                + (f" Note: {note}" if note else "")
            ),
            reference=reference,
        )
    )
    db.commit()
    return {
        "success": True,
        "message": f"{user.full_name}'s wallet credited with ₦{amount_kobo / 100:,.2f}.",
        "data": {
            "reference": reference,
            "ledger_id": txn.id,
            "balance_kobo": wallet.balance_kobo,
        },
    }


@router.patch("/users/{user_id}", summary="Edit a user's profile (name, phone)")
def edit_user(
    user_id: int,
    payload: UserEditIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.phone is not None:
        user.phone = payload.phone.strip() or None
    db.commit()
    return {
        "success": True,
        "message": f"{user.full_name}'s profile updated.",
        "data": {"id": user.id, "full_name": user.full_name, "phone": user.phone},
    }


@router.post("/users/{user_id}/reset-password", summary="Admin: reset a user's password")
def admin_reset_password(
    user_id: int,
    payload: AdminResetPasswordIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"success": True, "message": f"Password reset for '{user.full_name}'.", "data": None}


@router.post("/users/{user_id}/reset-pin", summary="Admin: reset a user's transaction PIN")
def admin_reset_pin(
    user_id: int,
    payload: AdminResetPinIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    user.pin_hash = hash_pin(payload.new_pin)
    db.commit()
    return {"success": True, "message": f"PIN reset for '{user.full_name}'.", "data": None}


@router.post("/users/{user_id}/debit", summary="Admin: debit a user's wallet")
def debit_user_wallet(
    user_id: int,
    payload: AdminDebitIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")

    amount_kobo = int(round(payload.amount_naira * 100))
    if amount_kobo < 5000:
        raise ValidationError("Minimum debit is ₦50.")

    wallet = wallet_service.get_wallet(db, user.id)
    reference = generate_reference("ADJ")
    note = (payload.note or "").strip()

    txn = wallet_service.debit(
        db,
        wallet,
        amount_kobo,
        category=LedgerCategory.ADJUSTMENT,
        narration=f"Manual debit by admin ({admin.email})" + (f" — {note}" if note else ""),
        reference=reference,
    )
    db.add(
        Notification(
            user_id=user.id,
            type="wallet",
            title="Wallet debited",
            body=(
                f"Your wallet was debited with ₦{amount_kobo / 100:,.2f}."
                + (f" Note: {note}" if note else "")
            ),
            reference=reference,
        )
    )
    db.commit()
    return {
        "success": True,
        "message": f"₦{amount_kobo / 100:,.2f} debited from {user.full_name}'s wallet.",
        "data": {
            "reference": reference,
            "ledger_id": txn.id,
            "balance_kobo": wallet.balance_kobo,
        },
    }


# ── transactions ─────────────────────────────────────────────────────────


@router.get("/transactions", summary="Browse every platform transaction")
def list_transactions(
    status: str | None = None,
    service_type: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    query = db.query(VTUTransaction).join(User, VTUTransaction.user_id == User.id)
    if status:
        try:
            query = query.filter(VTUTransaction.status == TxnStatus(status.lower()))
        except ValueError:
            pass
    if service_type:
        query = query.filter(sa_cast(VTUTransaction.service_type, String) == service_type.lower())
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            VTUTransaction.reference.ilike(like)
            | VTUTransaction.customer_ref.ilike(like)
            | User.email.ilike(like)
        )

    total = query.count()
    rows = (
        query.order_by(VTUTransaction.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # attach user emails in one go
    uid_map = {}
    if rows:
        ids = {t.user_id for t in rows}
        for u in db.query(User).filter(User.id.in_(ids)):
            uid_map[u.id] = {"email": u.email, "full_name": u.full_name}

    return {
        "success": True,
        "message": "OK",
        "data": {
            "items": [
                {
                    "id": t.id,
                    "reference": t.reference,
                    "service_type": t.service_type.value if hasattr(t.service_type, "value") else t.service_type,
                    "provider_code": t.provider_code,
                    "customer_ref": t.customer_ref,
                    "amount_kobo": t.amount_kobo,
                    "fee_kobo": t.fee_kobo,
                    "status": t.status.value if hasattr(t.status, "value") else t.status,
                    "user": uid_map.get(t.user_id),
                    "created_at": t.created_at.isoformat(),
                }
                for t in rows
            ],
            "meta": _page_meta(page, per_page, total),
        },
    }


@router.get("/transactions/export", summary="Export transactions as CSV, Excel or JSON")
def export_transactions(
    status: str | None = None,
    service_type: str | None = None,
    q: str | None = None,
    format: str = Query("csv", regex="^(csv|xlsx|json)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    import io
    import json as _json
    from fastapi.responses import StreamingResponse

    query = db.query(VTUTransaction).join(User, VTUTransaction.user_id == User.id)
    if status:
        try:
            query = query.filter(VTUTransaction.status == TxnStatus(status.lower()))
        except ValueError:
            pass
    if service_type:
        query = query.filter(sa_cast(VTUTransaction.service_type, String) == service_type.lower())
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            VTUTransaction.reference.ilike(like)
            | VTUTransaction.customer_ref.ilike(like)
            | User.email.ilike(like)
        )

    rows = query.order_by(VTUTransaction.id.desc()).limit(5000).all()

    uid_map = {}
    if rows:
        ids = {t.user_id for t in rows}
        for u in db.query(User).filter(User.id.in_(ids)):
            uid_map[u.id] = {"email": u.email, "full_name": u.full_name}

    headers = ["Reference", "User", "Email", "Service", "Customer Ref", "Amount (₦)", "Fee (₦)", "Status", "Date"]
    data = []
    for t in rows:
        u = uid_map.get(t.user_id, {})
        data.append({
            "Reference": t.reference,
            "User": u.get("full_name", ""),
            "Email": u.get("email", ""),
            "Service": t.service_type.value if hasattr(t.service_type, "value") else t.service_type,
            "Customer Ref": t.customer_ref,
            "Amount (₦)": round(t.amount_kobo / 100, 2),
            "Fee (₦)": round(t.fee_kobo / 100, 2),
            "Status": t.status.value if hasattr(t.status, "value") else t.status,
            "Date": t.created_at.strftime("%Y-%m-%d %H:%M"),
        })

    ts = datetime.now().strftime("%Y%m%d")
    if format == "json":
        buf = io.BytesIO(_json.dumps(data, ensure_ascii=False, indent=2).encode())
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=transactions-{ts}.json"},
        )

    if format == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for row in data:
            ws.append([row[h] for h in headers])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=transactions-{ts}.xlsx"},
        )

    # CSV (default)
    import csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in data:
        writer.writerow([row[h] for h in headers])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=transactions-{ts}.csv"},
    )


# ── data plans ───────────────────────────────────────────────────────────


@router.get("/data-plans/categories", summary="Distinct plan categories for filter dropdown")
def list_plan_categories(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    cats = set()
    for r in db.query(DataPlan.category).distinct().all():
        if r[0]:
            cats.add(r[0])
    return {"success": True, "message": "OK", "data": sorted(cats)}


@router.get("/data-plans", summary="All data plans (incl. inactive) for pricing management")
def list_plans(
    network: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    query = db.query(DataPlan)
    if network:
        query = query.filter(DataPlan.network_code == network.lower())
    if category:
        query = query.filter(DataPlan.category == category)
    rows = query.order_by(DataPlan.network_code, DataPlan.category, DataPlan.price_kobo).all()
    return {
        "success": True,
        "message": "OK",
        "data": [
            {
                "plan_code": p.plan_code,
                "network_code": p.network_code,
                "name": p.name,
                "category": p.category,
                "volume_mb": p.volume_mb,
                "validity_days": p.validity_days,
                "price_kobo": p.price_kobo,
                "buying_price_kobo": p.buying_price_kobo,
                "selling_price_kobo": p.selling_price_kobo,
                "promo_price_kobo": p.promo_price_kobo,
                "is_active": p.is_active,
            }
            for p in rows
        ],
    }


@router.post("/data-plans", summary="Create a new data plan manually")
def create_plan(
    payload: DataPlanCreateIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    existing = db.query(DataPlan).filter(DataPlan.plan_code == payload.plan_code).first()
    if existing:
        raise HTTPException(409, f"A plan with code '{payload.plan_code}' already exists.")
    plan = DataPlan(
        network_code=payload.network_code.lower(),
        plan_code=payload.plan_code,
        name=payload.name,
        category=payload.category,
        volume_mb=payload.volume_mb,
        validity_days=payload.validity_days,
        price_kobo=payload.selling_price_kobo,
        buying_price_kobo=payload.buying_price_kobo,
        selling_price_kobo=payload.selling_price_kobo,
        promo_price_kobo=payload.promo_price_kobo,
        is_active=payload.is_active,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {
        "success": True,
        "message": f"Data plan '{plan.name}' created.",
        "data": {
            "plan_code": plan.plan_code,
            "network_code": plan.network_code,
            "name": plan.name,
            "category": plan.category,
            "volume_mb": plan.volume_mb,
            "validity_days": plan.validity_days,
            "price_kobo": plan.price_kobo,
            "buying_price_kobo": plan.buying_price_kobo,
            "selling_price_kobo": plan.selling_price_kobo,
            "promo_price_kobo": plan.promo_price_kobo,
            "is_active": plan.is_active,
        },
    }


@router.put("/data-plans/{plan_code}", summary="Edit a data plan")
def edit_plan(
    plan_code: str,
    payload: DataPlanEditIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    plan = db.query(DataPlan).filter(DataPlan.plan_code == plan_code).first()
    if not plan:
        raise NotFoundError("Data plan not found")
    if payload.network_code is not None:
        plan.network_code = payload.network_code.lower()
    if payload.name is not None:
        plan.name = payload.name
    if payload.category is not None:
        plan.category = payload.category
    if payload.volume_mb is not None:
        plan.volume_mb = payload.volume_mb
    if payload.validity_days is not None:
        plan.validity_days = payload.validity_days
    if payload.buying_price_kobo is not None:
        plan.buying_price_kobo = payload.buying_price_kobo
    if payload.selling_price_kobo is not None:
        plan.selling_price_kobo = payload.selling_price_kobo
        plan.price_kobo = payload.selling_price_kobo
    if payload.promo_price_kobo is not None:
        plan.promo_price_kobo = payload.promo_price_kobo
    if payload.is_active is not None:
        plan.is_active = payload.is_active
    db.commit()
    return {
        "success": True,
        "message": f"{plan.name} updated.",
        "data": {
            "plan_code": plan.plan_code,
            "network_code": plan.network_code,
            "name": plan.name,
            "category": plan.category,
            "volume_mb": plan.volume_mb,
            "validity_days": plan.validity_days,
            "buying_price_kobo": plan.buying_price_kobo,
            "selling_price_kobo": plan.selling_price_kobo,
            "promo_price_kobo": plan.promo_price_kobo,
            "is_active": plan.is_active,
        },
    }


@router.delete("/data-plans/{plan_code}", summary="Delete a data plan")
def delete_plan(
    plan_code: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    plan = db.query(DataPlan).filter(DataPlan.plan_code == plan_code).first()
    if not plan:
        raise NotFoundError("Data plan not found")
    db.delete(plan)
    db.commit()
    return {"success": True, "message": f"Data plan '{plan_code}' deleted."}


@router.patch("/data-plans/{plan_code}", summary="Update a plan's price or availability")
def update_plan(
    plan_code: str,
    payload: PlanUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    plan = db.query(DataPlan).filter(DataPlan.plan_code == plan_code).first()
    if not plan:
        raise NotFoundError("Data plan not found")
    if payload.price_kobo is not None:
        plan.price_kobo = payload.price_kobo
    if payload.buying_price_kobo is not None:
        plan.buying_price_kobo = payload.buying_price_kobo
    if payload.selling_price_kobo is not None:
        plan.selling_price_kobo = payload.selling_price_kobo
    if payload.promo_price_kobo is not None:
        plan.promo_price_kobo = payload.promo_price_kobo
    if payload.is_active is not None:
        plan.is_active = payload.is_active
    db.commit()
    return {
        "success": True,
        "message": f"{plan.name} updated.",
        "data": {
            "plan_code": plan.plan_code,
            "price_kobo": plan.price_kobo,
            "buying_price_kobo": plan.buying_price_kobo,
            "selling_price_kobo": plan.selling_price_kobo,
            "is_active": plan.is_active,
        },
    }


# ── disabled data plan categories ────────────────────────────────────────


@router.get("/data-plans/disabled-categories", summary="List all disabled network+category combos")
def list_disabled_categories(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    rows = db.query(DisabledDataCategory).all()
    return {
        "success": True,
        "message": "OK",
        "data": [{"network_code": r.network_code, "category": r.category} for r in rows],
    }


class ToggleCategoryIn(BaseModel):
    network_code: str = Field(min_length=1, max_length=40)
    category: str = Field(min_length=1, max_length=40)


@router.post("/data-plans/disabled-categories/toggle", summary="Toggle a category on/off for a network")
def toggle_disabled_category(
    payload: ToggleCategoryIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    existing = db.query(DisabledDataCategory).filter(
        DisabledDataCategory.network_code == payload.network_code.lower(),
        DisabledDataCategory.category == payload.category,
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"success": True, "message": f"{payload.category} enabled for {payload.network_code}."}
    db.add(DisabledDataCategory(
        network_code=payload.network_code.lower(),
        category=payload.category,
    ))
    db.commit()
    return {"success": True, "message": f"{payload.category} disabled for {payload.network_code}."}


# ── cable plans ──────────────────────────────────────────────────────────


@router.get("/cable-plans", summary="All cable TV packages (incl. inactive) for pricing management")
def list_cable_plans(
    provider: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    query = db.query(CablePackage)
    if provider:
        query = query.filter(CablePackage.provider_code == provider.lower())
    rows = query.order_by(CablePackage.provider_code, CablePackage.price_kobo).all()
    return {
        "success": True,
        "message": "OK",
        "data": [
            {
                "package_code": c.package_code,
                "provider_code": c.provider_code,
                "name": c.name,
                "price_kobo": c.price_kobo,
                "buying_price_kobo": c.buying_price_kobo,
                "selling_price_kobo": c.selling_price_kobo,
                "is_active": c.is_active,
            }
            for c in rows
        ],
    }


@router.patch("/cable-plans/{package_code}", summary="Update a cable package's price or availability")
def update_cable_plan(
    package_code: str,
    payload: PlanUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    pkg = db.query(CablePackage).filter(CablePackage.package_code == package_code).first()
    if not pkg:
        raise NotFoundError("Cable package not found")
    if payload.price_kobo is not None:
        pkg.price_kobo = payload.price_kobo
    if payload.buying_price_kobo is not None:
        pkg.buying_price_kobo = payload.buying_price_kobo
    if payload.selling_price_kobo is not None:
        pkg.selling_price_kobo = payload.selling_price_kobo
    if payload.is_active is not None:
        pkg.is_active = payload.is_active
    db.commit()
    return {
        "success": True,
        "message": f"{pkg.name} updated.",
        "data": {
            "package_code": pkg.package_code,
            "price_kobo": pkg.price_kobo,
            "buying_price_kobo": pkg.buying_price_kobo,
            "selling_price_kobo": pkg.selling_price_kobo,
            "is_active": pkg.is_active,
        },
    }


# ── promo codes ────────────────────────────────────────────────────────────


@router.post("/promos", summary="Create a promo code")
def create_promo(
    body: PromoCodeCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from ..models.promo import PromoCode

    code = body.code.upper().strip()
    if len(code) < 3:
        raise HTTPException(400, "Code must be at least 3 characters")
    existing = db.execute(select(PromoCode).where(PromoCode.code == code)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Promo code already exists")
    promo = PromoCode(
        code=code,
        discount_percent=body.discount_percent,
        discount_kobo=body.discount_kobo,
        max_uses=body.max_uses,
        min_amount_kobo=body.min_amount_kobo,
        is_active=body.is_active,
        expires_at=body.expires_at,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return {"success": True, "data": PromoCodeOut.model_validate(promo).model_dump()}


@router.get("/promos", summary="List promo codes")
def list_promos(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    from ..models.promo import PromoCode

    q = select(PromoCode).order_by(PromoCode.id.desc()).offset(offset).limit(limit)
    rows = db.execute(q).scalars().all()
    return {"success": True, "data": [PromoCodeOut.model_validate(r).model_dump() for r in rows]}


@router.patch("/promos/{promo_id}", summary="Update a promo code")
def update_promo(
    promo_id: int,
    body: PromoCodeUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from ..models.promo import PromoCode

    promo = db.get(PromoCode, promo_id)
    if not promo:
        raise HTTPException(404, "Promo not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(promo, k, v)
    db.commit()
    db.refresh(promo)
    return {"success": True, "data": PromoCodeOut.model_validate(promo).model_dump()}


@router.delete("/promos/{promo_id}", summary="Delete a promo code")
def delete_promo(
    promo_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from ..models.promo import PromoCode

    promo = db.get(PromoCode, promo_id)
    if not promo:
        raise HTTPException(404, "Promo not found")
    db.delete(promo)
    db.commit()
    return {"success": True, "message": "Deleted"}


@router.get("/promos/validate/{code}", summary="Validate a promo code")
def validate_promo_code(
    code: str,
    amount_kobo: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from ..services.promo_service import validate_promo

    result = validate_promo(db, code, amount_kobo)
    if not result:
        raise HTTPException(404, "Invalid or expired promo code")
    return {"success": True, "data": result}


# ── broadcast notifications ──────────────────────────────────────────────


@router.post("/notifications/broadcast", summary="Send a notification to users")
def broadcast(
    payload: BroadcastIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if payload.email:
        user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
        if not user:
            raise HTTPException(404, "User not found with that email")
        active_ids = [user.id]
    else:
        active_ids = [uid for (uid,) in db.query(User.id).filter(User.is_active.is_(True)).all()]

    for uid in active_ids:
        db.add(Notification(user_id=uid, title=payload.title[:120], body=payload.body[:500], type="system"))
    db.commit()

    return {
        "success": True,
        "message": f"Notification sent to {len(active_ids)} user(s).",
        "data": {"recipients": len(active_ids)},
    }


# ── provider (bsokdata) balance & catalogue sync ─────────────────────────


@router.get("/provider/balance", summary="Reseller wallet balance at the VTU provider")
def provider_balance(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    try:
        provider = get_provider("data", db)
        if hasattr(provider, "get_balance"):
            balance_data = provider.get_balance(db)
            return {"success": True, "message": "OK", "data": balance_data}
        raise AppError("Balance check not supported for this provider", code="provider_error", status_code=502)
    except Exception as exc:  # noqa: BLE001 — surface delivery problems to the admin
        raise AppError(str(exc) or "Provider unreachable", code="provider_error", status_code=502)


@router.post("/provider/sync-plans", summary="Pull the provider's cable bouquet list into the catalogue")
def sync_provider_plans(
    provider_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    try:
        provider = get_provider("data", db)
        if hasattr(provider, "fetch_cable_plans"):
            plans = provider.fetch_cable_plans(db)
        else:
            plans = []
    except Exception as exc:  # noqa: BLE001
        raise AppError(str(exc) or "Provider unreachable", code="provider_error", status_code=502)

    # Deactivate all existing cable plans so only the current provider's plans remain active
    db.query(CablePackage).update({"is_active": False})

    created = updated = 0
    for p in plans:
        if not p["name"] or p["amount_naira"] <= 0:
            continue
        package_code = f"{p['provider_code']}-{p['provider_plan_id']}"
        price_kobo = int(p["amount_naira"] * 100)
        row = db.query(CablePackage).filter(CablePackage.package_code == package_code).first()
        if row:
            row.name = p["name"]
            row.price_kobo = price_kobo
            row.buying_price_kobo = price_kobo
            if row.selling_price_kobo is None:
                row.selling_price_kobo = price_kobo
            row.provider_code = p["provider_code"]
            row.is_active = True
            updated += 1
        else:
            db.add(
                CablePackage(
                    provider_code=p["provider_code"],
                    package_code=package_code,
                    name=p["name"],
                    price_kobo=price_kobo,
                    buying_price_kobo=price_kobo,
                    selling_price_kobo=price_kobo,
                )
            )
            created += 1
    db.commit()
    return {
        "success": True,
        "message": f"Cable plans synced — {created} added, {updated} refreshed.",
        "data": {"fetched": len(plans), "created": created, "updated": updated},
    }


@router.post("/provider/sync-data-plans", summary="Pull the provider's data plan list into the catalogue")
def sync_data_plans(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    try:
        provider = get_provider("data", db)
        if hasattr(provider, "fetch_data_plans"):
            plans = provider.fetch_data_plans(db)
        else:
            raise AppError("Data plan sync not supported for this provider", code="provider_error", status_code=502)
    except Exception as exc:  # noqa: BLE001
        raise AppError(str(exc) or "Provider unreachable", code="provider_error", status_code=502)

    # Deactivate all existing plans so only the current provider's plans remain active
    db.query(DataPlan).update({"is_active": False})

    created = updated = 0
    for p in plans:
        if not p["name"] or p["amount_naira"] <= 0:
            continue
        price_kobo = int(p["amount_naira"] * 100)
        row = db.query(DataPlan).filter(DataPlan.plan_code == p["plan_code"]).first()
        if row:
            row.name = p["name"]
            row.category = p["category"]
            row.volume_mb = p["volume_mb"]
            row.validity_days = p["validity_days"]
            row.price_kobo = price_kobo
            row.buying_price_kobo = price_kobo
            if row.selling_price_kobo is None:
                row.selling_price_kobo = price_kobo
            row.provider_plan_id = p.get("provider_plan_id")
            row.is_active = True
            updated += 1
        else:
            db.add(
                DataPlan(
                    network_code=p["network_code"],
                    plan_code=p["plan_code"],
                    name=p["name"],
                    category=p["category"],
                    volume_mb=p["volume_mb"],
                    validity_days=p["validity_days"],
                    price_kobo=price_kobo,
                    buying_price_kobo=price_kobo,
                    selling_price_kobo=price_kobo,
                    provider_plan_id=p.get("provider_plan_id"),
                )
            )
            created += 1
    db.commit()
    return {
        "success": True,
        "message": f"Data plans synced — {created} added, {updated} refreshed.",
        "data": {"fetched": len(plans), "created": created, "updated": updated},
    }


# ── outbound webhook ─────────────────────────────────────────────────────


@router.get("/webhook", summary="Current outbound webhook URL")
def get_webhook(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    return {"success": True, "message": "OK", "data": {"url": _get_setting(db, WEBHOOK_URL_KEY)}}


@router.put("/webhook", summary="Set the outbound webhook URL (transaction events will be POSTed here)")
def set_webhook(payload: WebhookIn, db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    url = payload.url.strip()
    if not url.startswith(("http://", "https://")):
        from ..core.errors import ValidationError

        raise ValidationError("URL must start with http:// or https://")
    _set_setting(db, WEBHOOK_URL_KEY, url)
    db.commit()
    return {"success": True, "message": "Webhook URL saved.", "data": {"url": url}}


@router.post("/webhook/test", summary="Send a sample event to the saved webhook URL")
def test_webhook(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    url = _get_setting(db, WEBHOOK_URL_KEY)
    if not url:
        raise NotFoundError("No webhook URL configured yet.")
    payload = {
        "event": "transaction.successful",
        "test": True,
        "sent_at": datetime.utcnow().isoformat(),
        "data": {
            "reference": "TEST-EVT-0001",
            "service_type": "data",
            "amount_kobo": 50000,
            "status": "successful",
        },
    }
    try:
        resp = httpx.post(url, json=payload, timeout=5.0)
        return {
            "success": True,
            "message": f"Test event delivered (HTTP {resp.status_code}).",
            "data": {"http_status": resp.status_code},
        }
    except Exception as exc:  # noqa: BLE001 - surface any delivery failure to the admin
        return {"success": False, "message": f"Delivery failed: {exc}", "data": None}


# ── provider switching ────────────────────────────────────────────────────

VTU_PROVIDER_KEY = "vtu_provider"


class ProviderIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)


@router.get("/provider", summary="Get current active VTU provider and available options")
def get_provider_config(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    from ..services.providers import list_providers
    from ..core.config import settings

    # Check database override first, then fall back to env var
    row = db.get(AppSetting, VTU_PROVIDER_KEY)
    current = row.value if row and row.value else settings.VTU_PROVIDER

    return {
        "success": True,
        "message": "OK",
        "data": {
            "current": current,
            "providers": list_providers(),
        },
    }


@router.put("/provider", summary="Switch the active VTU provider")
def set_provider(
    payload: ProviderIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    from ..services.providers import list_providers
    from ..services.providers.base import get_provider as _get_provider

    available = [p["name"] for p in list_providers()]
    if payload.name.lower() not in available:
        raise ValidationError(f"Provider '{payload.name}' is not available. Choose from: {', '.join(available)}")

    row = db.get(AppSetting, VTU_PROVIDER_KEY)
    if row:
        row.value = payload.name.lower()
    else:
        db.add(AppSetting(key=VTU_PROVIDER_KEY, value=payload.name.lower()))
    db.commit()

    # Auto-sync data plans from the new provider
    sync_summary = {}
    try:
        provider = _get_provider("data", db)
        if hasattr(provider, "fetch_data_plans"):
            plans = provider.fetch_data_plans(db)
            db.query(DataPlan).update({"is_active": False})
            created = updated = 0
            for p in plans:
                if not p["name"] or p["amount_naira"] <= 0:
                    continue
                price_kobo = int(p["amount_naira"] * 100)
                existing = db.query(DataPlan).filter(DataPlan.plan_code == p["plan_code"]).first()
                if existing:
                    existing.name = p["name"]
                    existing.category = p["category"]
                    existing.volume_mb = p["volume_mb"]
                    existing.validity_days = p["validity_days"]
                    existing.price_kobo = price_kobo
                    existing.buying_price_kobo = price_kobo
                    if existing.selling_price_kobo is None:
                        existing.selling_price_kobo = price_kobo
                    existing.provider_plan_id = p.get("provider_plan_id")
                    existing.is_active = True
                    updated += 1
                else:
                    db.add(DataPlan(
                        network_code=p["network_code"], plan_code=p["plan_code"],
                        name=p["name"], category=p["category"], volume_mb=p["volume_mb"],
                        validity_days=p["validity_days"], price_kobo=price_kobo,
                        buying_price_kobo=price_kobo, selling_price_kobo=price_kobo,
                        provider_plan_id=p.get("provider_plan_id"),
                    ))
                    created += 1
            db.commit()
            sync_summary["data_plans"] = {"fetched": len(plans), "created": created, "updated": updated}
    except Exception:
        db.rollback()

    # Auto-sync cable plans from the new provider
    try:
        provider = _get_provider("data", db)
        if hasattr(provider, "fetch_cable_plans"):
            plans = provider.fetch_cable_plans(db)
            db.query(CablePackage).update({"is_active": False})
            created = updated = 0
            for p in plans:
                if not p["name"] or p["amount_naira"] <= 0:
                    continue
                package_code = f"{p['provider_code']}-{p['provider_plan_id']}"
                price_kobo = int(p["amount_naira"] * 100)
                existing = db.query(CablePackage).filter(CablePackage.package_code == package_code).first()
                if existing:
                    existing.name = p["name"]
                    existing.price_kobo = price_kobo
                    existing.buying_price_kobo = price_kobo
                    if existing.selling_price_kobo is None:
                        existing.selling_price_kobo = price_kobo
                    existing.provider_code = p["provider_code"]
                    existing.is_active = True
                    updated += 1
                else:
                    db.add(CablePackage(
                        provider_code=p["provider_code"], package_code=package_code,
                        name=p["name"], price_kobo=price_kobo,
                        buying_price_kobo=price_kobo, selling_price_kobo=price_kobo,
                    ))
                    created += 1
            db.commit()
            sync_summary["cable_plans"] = {"fetched": len(plans), "created": created, "updated": updated}
    except Exception:
        db.rollback()

    return {
        "success": True,
        "message": f"Provider switched to {payload.name}. Plans synced.",
        "data": {"current": payload.name.lower(), "sync": sync_summary},
    }


# ── site settings ────────────────────────────────────────────────────────

SITE_NAME_KEY = "site_name"
SITE_THEME_KEY = "site_theme"

DEFAULT_THEMES = {
    "light": {
        "label": "Light",
        "bg": "#f5f7fa",
        "card": "#ffffff",
        "ink": "#101828",
        "ink2": "#475467",
        "muted": "#98a2b3",
        "brand": "#0aa65a",
        "brand050": "#ecfdf3",
        "brand100": "#d1fae5",
        "brand400": "#23bd77",
        "brand600": "#0aa65a",
        "brand700": "#059649",
        "line": "#eaecf0",
        "lineStrong": "#d0d5dd",
        "danger": "#f04438",
        "navBg": "rgba(255,255,255,0.94)",
        "statusBar": "#f5f7fa",
    },
    "dark": {
        "label": "Dark",
        "bg": "#0f1117",
        "card": "#1a1d27",
        "ink": "#f2f4f7",
        "ink2": "#d0d5dd",
        "muted": "#667085",
        "brand": "#0aa65a",
        "brand050": "#052e16",
        "brand100": "#064e3b",
        "brand400": "#23bd77",
        "brand600": "#0aa65a",
        "brand700": "#2dd36f",
        "line": "#2a2d3a",
        "lineStrong": "#3b3f4c",
        "danger": "#f04438",
        "navBg": "rgba(26,29,39,0.94)",
        "statusBar": "#0f1117",
    },
    "blue": {
        "label": "Ocean Blue",
        "bg": "#f0f5ff",
        "card": "#ffffff",
        "ink": "#101828",
        "ink2": "#475467",
        "muted": "#98a2b3",
        "brand": "#2563eb",
        "brand050": "#eff6ff",
        "brand100": "#dbeafe",
        "brand400": "#60a5fa",
        "brand600": "#2563eb",
        "brand700": "#1d4ed8",
        "line": "#eaecf0",
        "lineStrong": "#d0d5dd",
        "danger": "#f04438",
        "navBg": "rgba(255,255,255,0.94)",
        "statusBar": "#f0f5ff",
    },
    "green": {
        "label": "Emerald",
        "bg": "#ecfdf5",
        "card": "#ffffff",
        "ink": "#101828",
        "ink2": "#475467",
        "muted": "#98a2b3",
        "brand": "#059669",
        "brand050": "#ecfdf5",
        "brand100": "#d1fae5",
        "brand400": "#34d399",
        "brand600": "#059669",
        "brand700": "#047857",
        "line": "#eaecf0",
        "lineStrong": "#d0d5dd",
        "danger": "#f04438",
        "navBg": "rgba(255,255,255,0.94)",
        "statusBar": "#ecfdf5",
    },
    "purple": {
        "label": "Royal Purple",
        "bg": "#f5f3ff",
        "card": "#ffffff",
        "ink": "#101828",
        "ink2": "#475467",
        "muted": "#98a2b3",
        "brand": "#7c3aed",
        "brand050": "#f5f3ff",
        "brand100": "#ede9fe",
        "brand400": "#a78bfa",
        "brand600": "#7c3aed",
        "brand700": "#6d28d9",
        "line": "#eaecf0",
        "lineStrong": "#d0d5dd",
        "danger": "#f04438",
        "navBg": "rgba(255,255,255,0.94)",
        "statusBar": "#f5f3ff",
    },
    "sunset": {
        "label": "Sunset Orange",
        "bg": "#fff7ed",
        "card": "#ffffff",
        "ink": "#101828",
        "ink2": "#475467",
        "muted": "#98a2b3",
        "brand": "#ea580c",
        "brand050": "#fff7ed",
        "brand100": "#ffedd5",
        "brand400": "#fb923c",
        "brand600": "#ea580c",
        "brand700": "#c2410c",
        "line": "#eaecf0",
        "lineStrong": "#d0d5dd",
        "danger": "#f04438",
        "navBg": "rgba(255,255,255,0.94)",
        "statusBar": "#fff7ed",
    },
    "rose": {
        "label": "Rose Pink",
        "bg": "#fff1f2",
        "card": "#ffffff",
        "ink": "#101828",
        "ink2": "#475467",
        "muted": "#98a2b3",
        "brand": "#e11d48",
        "brand050": "#fff1f2",
        "brand100": "#ffe4e6",
        "brand400": "#fb7185",
        "brand600": "#e11d48",
        "brand700": "#be123c",
        "line": "#eaecf0",
        "lineStrong": "#d0d5dd",
        "danger": "#f04438",
        "navBg": "rgba(255,255,255,0.94)",
        "statusBar": "#fff1f2",
    },
    "midnight": {
        "label": "Midnight",
        "bg": "#18181b",
        "card": "#27272a",
        "ink": "#fafafa",
        "ink2": "#a1a1aa",
        "muted": "#71717a",
        "brand": "#6366f1",
        "brand050": "#1e1b4b",
        "brand100": "#312e81",
        "brand400": "#818cf8",
        "brand600": "#6366f1",
        "brand700": "#4f46e5",
        "line": "#3f3f46",
        "lineStrong": "#52525b",
        "danger": "#ef4444",
        "navBg": "rgba(24,24,27,0.94)",
        "statusBar": "#18181b",
    },
    "teal": {
        "label": "Teal",
        "bg": "#f0fdfa",
        "card": "#ffffff",
        "ink": "#101828",
        "ink2": "#475467",
        "muted": "#98a2b3",
        "brand": "#0d9488",
        "brand050": "#f0fdfa",
        "brand100": "#ccfbf1",
        "brand400": "#2dd4bf",
        "brand600": "#0d9488",
        "brand700": "#0f766e",
        "line": "#eaecf0",
        "lineStrong": "#d0d5dd",
        "danger": "#f04438",
        "navBg": "rgba(255,255,255,0.94)",
        "statusBar": "#f0fdfa",
    },
    "crimson": {
        "label": "Crimson",
        "bg": "#fef2f2",
        "card": "#ffffff",
        "ink": "#101828",
        "ink2": "#475467",
        "muted": "#98a2b3",
        "brand": "#dc2626",
        "brand050": "#fef2f2",
        "brand100": "#fee2e2",
        "brand400": "#f87171",
        "brand600": "#dc2626",
        "brand700": "#b91c1c",
        "line": "#eaecf0",
        "lineStrong": "#d0d5dd",
        "danger": "#f04438",
        "navBg": "rgba(255,255,255,0.94)",
        "statusBar": "#fef2f2",
    },
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _add_shadow_vars(themes: dict) -> dict:
    """Add shadow color variables to each theme based on its brand color."""
    for key, theme in themes.items():
        r, g, b = _hex_to_rgb(theme["brand"])
        theme["brandShadowSm"] = f"rgba({r}, {g}, {b}, 0.14)"
        theme["brandShadowMd"] = f"rgba({r}, {g}, {b}, 0.28)"
        theme["brandShadowLg"] = f"rgba({r}, {g}, {b}, 0.35)"
        theme["brandShadowXl"] = f"rgba({r}, {g}, {b}, 0.22)"
    return themes


DEFAULT_THEMES = _add_shadow_vars(DEFAULT_THEMES)


SITE_SUPPORT_PHONE_KEY = "support_phone"
SITE_SUPPORT_EMAIL_KEY = "support_email"


class SiteSettingsIn(BaseModel):
    site_name: str | None = None
    theme: str | None = None
    support_phone: str | None = None
    support_email: str | None = None


@router.get("/site-settings")
def get_site_settings(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    name = _get_setting(db, SITE_NAME_KEY) or ElevenData
    theme_key = _get_setting(db, SITE_THEME_KEY) or "light"
    support_phone = _get_setting(db, SITE_SUPPORT_PHONE_KEY) or ""
    support_email = _get_setting(db, SITE_SUPPORT_EMAIL_KEY) or ""
    return {
        "success": True,
        "message": "OK",
        "data": {
            "site_name": name,
            "theme": theme_key,
            "support_phone": support_phone,
            "support_email": support_email,
            "themes": DEFAULT_THEMES,
        },
    }


@router.put("/site-settings")
def update_site_settings(payload: SiteSettingsIn, db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    if payload.site_name is not None:
        name = payload.site_name.strip()
        if not name:
            raise ValidationError("Site name cannot be empty")
        if len(name) > 60:
            raise ValidationError("Site name must be 60 characters or less")
        _set_setting(db, SITE_NAME_KEY, name)
    if payload.theme is not None:
        if payload.theme not in DEFAULT_THEMES:
            raise ValidationError(f"Unknown theme: {payload.theme}")
        _set_setting(db, SITE_THEME_KEY, payload.theme)
    if payload.support_phone is not None:
        _set_setting(db, SITE_SUPPORT_PHONE_KEY, payload.support_phone.strip())
    if payload.support_email is not None:
        _set_setting(db, SITE_SUPPORT_EMAIL_KEY, payload.support_email.strip())
    db.commit()
    return {"success": True, "message": "Site settings updated."}


@router.get("/site-settings/public")
def get_public_site_settings(db: Session = Depends(get_db)):
    name = _get_setting(db, SITE_NAME_KEY) or ElevenData
    theme_key = _get_setting(db, SITE_THEME_KEY) or "light"
    theme_vars = DEFAULT_THEMES.get(theme_key, DEFAULT_THEMES["light"])
    support_phone = _get_setting(db, SITE_SUPPORT_PHONE_KEY) or ""
    support_email = _get_setting(db, SITE_SUPPORT_EMAIL_KEY) or ""
    return {
        "success": True,
        "message": "OK",
        "data": {"site_name": name, "theme": theme_key, "theme_vars": theme_vars, "support_phone": support_phone, "support_email": support_email},
    }


@router.get("/manifest.json")
def get_manifest(db: Session = Depends(get_db)):
    from fastapi.responses import JSONResponse
    name = _get_setting(db, SITE_NAME_KEY) or ElevenData
    theme_key = _get_setting(db, SITE_THEME_KEY) or "light"
    theme_vars = DEFAULT_THEMES.get(theme_key, DEFAULT_THEMES["light"])
    return JSONResponse({
        "name": f"{name} — Airtime, Data & Bills",
        "short_name": name,
        "start_url": "/",
        "display": "standalone",
        "background_color": theme_vars["bg"],
        "theme_color": theme_vars["statusBar"],
        "description": "Buy airtime & data, pay electricity and cable bills from one secure wallet.",
        "icons": [
            {
                "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'%3E%3Crect width='192' height='192' rx='44' fill='%230AA65A'/%3E%3Cpath d='M106 32 56 108h32l-10 52 52-76H98l8-52z' fill='%23fff'/%3E%3C/svg%3E",
                "sizes": "192x192",
                "type": "image/svg+xml",
            }
        ],
    })
