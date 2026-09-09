"""Send web push notifications to subscribed users."""

import json
from pathlib import Path

from pywebpush import webpush, WebPushException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.push import PushSubscription
from ..models.user import User

VAPID_PRIVATE_KEY_PATH = Path(__file__).parent.parent.parent / "vapid_private.pem"
VAPID_CLAIMS = {"sub": "mailto:admin@zaply.ng"}

_vapid_private_key = None


def _get_vapid_key():
    global _vapid_private_key
    if _vapid_private_key is None:
        if VAPID_PRIVATE_KEY_PATH.exists():
            _vapid_private_key = VAPID_PRIVATE_KEY_PATH.read_text()
        else:
            return None
    return _vapid_private_key


def send_push_to_user(db: Session, user_id: int, title: str, body: str, url: str = "/"):
    subs = db.execute(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    ).scalars().all()

    vapid_key = _get_vapid_key()
    if not vapid_key:
        return

    payload = json.dumps({"title": title, "body": body, "url": url})

    dead_subs = []
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=vapid_key,
                vapid_claims=VAPID_CLAIMS,
            )
        except WebPushException:
            dead_subs.append(sub)

    for sub in dead_subs:
        db.delete(sub)
    if dead_subs:
        db.commit()


def send_push_to_all(db: Session, title: str, body: str, url: str = "/"):
    users = db.execute(select(User.id).where(User.is_active == True)).scalars().all()
    for uid in users:
        send_push_to_user(db, uid, title, body, url)
