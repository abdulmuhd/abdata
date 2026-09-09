import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.errors import AppError, AuthError, ConflictError, NotFoundError, RateLimitedError
from ..core.ratelimit import rate_limiter
from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_secret,
    utcnow,
    verify_password,
    verify_secret,
)
from ..dependencies.auth import get_current_user
from ..models import RefreshToken, User, Wallet
from ..schemas.auth import (
    AdminLoginIn,
    ForgotPasswordIn,
    ForgotPasswordOut,
    LoginIn,
    MessageOut,
    RefreshIn,
    RegisterIn,
    ResetPasswordIn,
    TokenPair,
    VerifyEmailIn,
)
from ..schemas.user import UserOut
from ..services import notification_service, wallet_service
from ..models.wallet import LedgerCategory

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _user_payload(user: User) -> dict:
    out = UserOut.model_validate(user).model_dump(mode="json")
    out["has_pin"] = bool(user.pin_hash)
    out["referral_code"] = user.referral_code or ""
    return out


def _issue_pair(db: Session, user: User) -> TokenPair:
    refresh = create_refresh_token(user.id)
    jti = decode_token(refresh)["jti"]
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    return TokenPair(access_token=create_access_token(user.id), refresh_token=refresh)


def _guard(request: Request):
    ip = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(f"auth:{ip}", settings.RATE_LIMIT_AUTH_REQUESTS, settings.RATE_LIMIT_AUTH_WINDOW):
        retry = rate_limiter.retry_after(f"auth:{ip}", settings.RATE_LIMIT_AUTH_WINDOW)
        raise RateLimitedError(f"Too many attempts. Try again in {retry}s.")


REFERRAL_BONUS_KOBO = 100_000  # ₦1,000


def _generate_referral_code() -> str:
    import random
    import string
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return code


@router.post("/register", summary="Create an account", responses={409: {"description": "Email/phone already used"}})
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)):
    """Creates the user + wallet and returns an initial token pair (auto sign-in)."""
    _guard(request)
    if db.query(User).filter(User.email == payload.email).first():
        raise ConflictError("An account with this email already exists.")
    if db.query(User).filter(User.phone == payload.phone).first():
        raise ConflictError("An account with this phone number already exists.")

    # Look up referrer if code provided
    referrer = None
    if payload.referral_code:
        referrer = db.query(User).filter(User.referral_code == payload.referral_code.strip().upper()).first()

    user = User(
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        referral_code=_generate_referral_code(),
        referred_by=referrer.id if referrer else None,
    )
    db.add(user)
    db.flush()
    db.add(Wallet(user_id=user.id))

    code = f"{secrets.randbelow(1_000_000):06d}"
    user.verification_code_hash = hash_secret(code)

    notification_service.notify(
        db, user.id, "Welcome to Zaply 🎉",
        "Your account is ready. Buy airtime & data, pay bills and fund your wallet — all in one place.",
        type_="system",
    )
    db.commit()

    # Credit referral bonus to both parties
    if referrer:
        try:
            referrer_wallet = wallet_service.get_wallet(db, referrer.id)
            wallet_service.credit_bonus(db, referrer_wallet, REFERRAL_BONUS_KOBO)
            notification_service.notify(
                db, referrer.id, "Referral bonus! 🎉",
                f"{user.full_name} joined using your code. You earned ₦{REFERRAL_BONUS_KOBO // 100:,}!",
                type_="system",
            )
        except Exception:
            pass  # don't block signup if bonus fails

        try:
            user_wallet = wallet_service.get_wallet(db, user.id)
            wallet_service.credit_bonus(db, user_wallet, REFERRAL_BONUS_KOBO)
        except Exception:
            pass

        db.commit()

    pair = _issue_pair(db, user)
    data = {**_user_payload(user), **pair.model_dump(), "email_verification": None}
    if not settings.is_prod:
        data["email_verification"] = {"required": True, "dev_code": code}
    return {"success": True, "message": "Account created successfully.", "data": data}


@router.post("/login", summary="Sign in with phone number and password")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    _guard(request)
    user = db.query(User).filter(User.phone == payload.phone).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise AuthError("Incorrect phone number or password.")
    if not user.is_active:
        raise AuthError("This account has been deactivated. Contact support.")

    user.last_login_at = utcnow()
    db.commit()
    pair = _issue_pair(db, user)
    return {
        "success": True,
        "message": "Signed in successfully.",
        "data": {**_user_payload(user), **pair.model_dump()},
    }


@router.post("/admin-login", summary="Admin sign in with email and password")
def admin_login(payload: AdminLoginIn, request: Request, db: Session = Depends(get_db)):
    _guard(request)
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise AuthError("Incorrect email or password.")
    if not user.is_active:
        raise AuthError("This account has been deactivated. Contact support.")

    from ..dependencies.auth import is_admin_email, _is_system_user
    if not is_admin_email(user.email) and not _is_system_user(db, user):
        raise AuthError("Admin access required.", status_code=403)

    user.last_login_at = utcnow()
    db.commit()
    pair = _issue_pair(db, user)
    return {
        "success": True,
        "message": "Signed in successfully.",
        "data": {**_user_payload(user), **pair.model_dump()},
    }


@router.post("/refresh", summary="Exchange refresh token for a new pair")
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except Exception:
        raise AuthError("Refresh token invalid or expired. Sign in again.")  # noqa: B904

    row = db.query(RefreshToken).filter(RefreshToken.jti == claims["jti"]).first()
    if not row or row.revoked:
        raise AuthError("Session revoked. Sign in again.")
    user = db.get(User, int(claims["sub"]))
    if not user or not user.is_active:
        raise AuthError("Account unavailable.")

    row.revoked = True  # rotation
    pair = _issue_pair(db, user)
    return {"success": True, "message": "Token refreshed.", "data": pair.model_dump()}


@router.post("/logout", summary="Revoke the current session")
def logout(payload: RefreshIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.refresh_token:
        try:
            claims = decode_token(payload.refresh_token, expected_type="refresh")
            row = db.query(RefreshToken).filter(RefreshToken.jti == claims["jti"], RefreshToken.user_id == user.id).first()
            if row:
                row.revoked = True
                db.commit()
        except Exception:
            pass
    return {"success": True, "message": "Signed out.", "data": None}


@router.post("/forgot-password", response_model=ForgotPasswordOut, summary="Request a password reset")
def forgot_password(payload: ForgotPasswordIn, request: Request, db: Session = Depends(get_db)):
    """Always returns a generic message so accounts cannot be enumerated."""
    _guard(request)
    generic = "If the email exists, a reset link has been sent."
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user:
        return ForgotPasswordOut(message=generic)

    from ..core.security import create_reset_token

    token = create_reset_token(user.id)
    user.reset_token_hash = hash_secret(token)
    db.commit()

    out = ForgotPasswordOut(message=generic)
    if not settings.is_prod:
        out.dev_reset_token = token  # would be emailed in production
    return out


@router.post("/reset-password", response_model=MessageOut, summary="Complete a password reset")
def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    try:
        claims = decode_token(payload.reset_token, expected_type="password_reset")
    except Exception:
        raise AppError("Reset link is invalid or has expired.", code="invalid_reset")  # noqa: B904

    user = db.get(User, int(claims["sub"]))
    if not user or not user.reset_token_hash or not verify_secret(payload.reset_token, user.reset_token_hash):
        raise AppError("Reset link is invalid or has expired.", code="invalid_reset")

    user.password_hash = hash_password(payload.new_password)
    user.reset_token_hash = None
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"revoked": True})
    db.commit()
    return MessageOut(message="Password updated. Sign in with your new password.")


@router.post("/verify-email", response_model=MessageOut, summary="Verify email with 6-digit code")
def verify_email(payload: VerifyEmailIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user:
        raise NotFoundError("Account not found.")
    if user.is_verified:
        return MessageOut(message="Email already verified.")
    if not user.verification_code_hash or not verify_secret(payload.code, user.verification_code_hash):
        raise AppError("That verification code is incorrect.", code="bad_code")

    user.is_verified = True
    user.verification_code_hash = None
    db.commit()
    notification_service.notify(db, user.id, "Email verified ✅", "Your email address has been confirmed.", type_="security")
    db.commit()
    return MessageOut(message="Email verified successfully.")
