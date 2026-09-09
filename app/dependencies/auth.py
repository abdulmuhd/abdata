from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.errors import AuthError
from ..core.security import decode_token
from ..models import User
from ..models.system_user import SystemUser, SystemUserStatus

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthError("Authentication required.")
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except Exception:
        raise AuthError("Session expired or invalid. Please sign in again.")  # noqa: B904
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise AuthError("Account not found or deactivated.")
    return user


Current_user = get_current_user


def is_admin_email(email: str | None) -> bool:
    allowed = {e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()}
    return (email or "").lower() in allowed


def _is_system_user(db: Session, user: User) -> bool:
    su = db.query(SystemUser).filter(
        SystemUser.user_id == user.id,
        SystemUser.status == SystemUserStatus.ACTIVE,
    ).first()
    return su is not None


def get_current_admin(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if is_admin_email(user.email) or _is_system_user(db, user):
        return user
    raise AuthError("Admin access required.", status_code=403)
