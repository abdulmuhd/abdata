"""Notification and push subscription endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..dependencies.auth import get_current_user
from ..models.notification import Notification
from ..models.push import PushSubscription
from ..models.user import User
from ..schemas.user import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])

VAPID_PUBLIC_KEY_PATH = Path(__file__).parent.parent.parent / "vapid_private.pem"


@router.get("", summary="List notifications")
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    per_page: int = Query(20, ge=1, le=100),
):
    q = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(per_page)
    )
    items = db.execute(q).scalars().all()
    return {"success": True, "data": {"items": [NotificationOut.model_validate(n).model_dump() for n in items]}}


@router.post("/read-all", summary="Mark all notifications as read")
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return {"success": True, "message": "All notifications marked as read"}


@router.post("/{notification_id}/read", summary="Mark a notification as read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    n = db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    ).scalar_one_or_none()
    if n:
        n.is_read = True
        db.commit()
    return {"success": True, "message": "Marked as read"}


def _get_public_key():
    try:
        from py_vapid import Vapid
        v = Vapid()
        if VAPID_PUBLIC_KEY_PATH.exists():
            v.private_key = VAPID_PUBLIC_KEY_PATH.read_bytes()
            return v.public_key.decode().strip()
    except Exception:
        pass
    return None


class PushSubscribeIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.post("/push/subscribe", summary="Save a push subscription")
def subscribe(
    body: PushSubscribeIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint == body.endpoint,
        )
    ).scalar_one_or_none()

    if existing:
        existing.p256dh = body.p256dh
        existing.auth = body.auth
    else:
        db.add(PushSubscription(
            user_id=user.id,
            endpoint=body.endpoint,
            p256dh=body.p256dh,
            auth=body.auth,
        ))
    db.commit()
    return {"success": True, "message": "Subscribed"}


@router.post("/push/unsubscribe", summary="Remove a push subscription")
def unsubscribe(
    body: PushSubscribeIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint == body.endpoint,
        )
    ).scalar_one_or_none()
    if sub:
        db.delete(sub)
        db.commit()
    return {"success": True, "message": "Unsubscribed"}


@router.get("/push/status", summary="Check if user has push enabled")
def push_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = db.execute(
        select(PushSubscription).where(PushSubscription.user_id == user.id)
    ).scalars().all()
    return {"success": True, "enabled": len(count) > 0}


@router.get("/push/vapid-key", summary="Get VAPID public key for push subscription")
def vapid_key():
    key = _get_public_key()
    if not key:
        return {"success": False, "message": "Push notifications not configured"}
    return {"success": True, "public_key": key}
