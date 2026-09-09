from fastapi import APIRouter, Depends
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.errors import AppError, ConflictError
from ..core.security import hash_password, hash_pin, verify_password, verify_secret
from ..dependencies.auth import get_current_user, is_admin_email, _is_system_user
from ..models import Notification, User, Wallet
from ..schemas.user import (
    ChangePasswordIn,
    DashboardOut,
    PinUpdateIn,
    UpdateProfileIn,
    UserOut,
    VirtualAccountOut,
)
from ..schemas.common import normalize_phone_or_none

router = APIRouter(prefix="/users", tags=["Users"])


def _has_admin_access(db: Session, user: User) -> bool:
    return is_admin_email(user.email) or _is_system_user(db, user)


@router.get("/me", summary="Current user profile")
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = UserOut.model_validate(user).model_dump(mode="json")
    data["has_pin"] = bool(user.pin_hash)
    data["is_admin"] = _has_admin_access(db, user)
    return {"success": True, "message": "OK", "data": data}


@router.get("/me/dashboard", summary="Dashboard aggregate (user + balance + unread count)")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).one()
    unread = (
        db.query(sqlfunc.count(Notification.id))
        .filter(Notification.user_id == user.id, Notification.is_read.is_(False))
        .scalar()
    )
    # Deterministic per-user virtual account (10 digits) for funding by bank transfer.
    virtual_account = VirtualAccountOut(
        bank_name=settings.VA_BANK_NAME,
        account_name=user.full_name.upper(),
        account_number=f"70{user.id:08d}",
    )
    data = DashboardOut(
        user=UserOut.model_validate(user),
        balance_kobo=wallet.balance_kobo,
        bonus_balance_kobo=getattr(wallet, "bonus_kobo", 0),
        unread_notifications=int(unread or 0),
        virtual_account=virtual_account,
    ).model_dump(mode="json")
    data["user"]["has_pin"] = bool(user.pin_hash)
    data["user"]["is_admin"] = _has_admin_access(db, user)
    return {"success": True, "message": "OK", "data": data}


@router.patch("/me", summary="Update profile")
def update_me(payload: UpdateProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.full_name:
        user.full_name = payload.full_name.strip()
    if payload.phone:
        phone = normalize_phone_or_none(payload.phone) or payload.phone
        exists = db.query(User).filter(User.phone == phone, User.id != user.id).first()
        if exists:
            raise ConflictError("Another account already uses this phone number.")
        user.phone = phone
    db.commit()
    data = UserOut.model_validate(user).model_dump(mode="json")
    data["has_pin"] = bool(user.pin_hash)
    return {"success": True, "message": "Profile updated.", "data": data}


@router.put("/me/password", summary="Change password (requires current password)")
def change_password(payload: ChangePasswordIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(payload.current_password, user.password_hash):
        raise AppError("Your current password is incorrect.", code="bad_password")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"success": True, "message": "Password changed successfully.", "data": None}


@router.put("/me/pin", summary="Set or change transaction PIN")
def update_pin(payload: PinUpdateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.pin_hash:
        if not payload.current_pin or not verify_secret(payload.current_pin, user.pin_hash):
            raise AppError("Your current PIN is incorrect.", code="bad_pin")
    user.pin_hash = hash_pin(payload.new_pin)
    db.commit()
    msg = "Transaction PIN changed." if user.pin_hash else "Transaction PIN set."
    return {"success": True, "message": msg, "data": None}


@router.get("/me/referrals", summary="Get referral stats and code")
def get_referrals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    referral_count = db.query(sqlfunc.count(User.id)).filter(User.referred_by == user.id).scalar() or 0
    return {
        "success": True,
        "message": "OK",
        "data": {
            "referral_code": user.referral_code or "",
            "referral_count": referral_count,
            "bonus_kobo": 100_000,
        },
    }


@router.get("/me/active-promos", summary="Check if there are active promo codes available")
def has_active_promos(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    from datetime import datetime, timezone
    from ..models.promo import PromoCode

    now = datetime.now(timezone.utc)
    count = db.query(sqlfunc.count(PromoCode.id)).filter(
        PromoCode.is_active.is_(True),
    ).filter(
        (PromoCode.expires_at.is_(None)) | (PromoCode.expires_at > now)
    ).scalar() or 0
    return {"success": True, "message": "OK", "data": {"has_promos": count > 0}}
