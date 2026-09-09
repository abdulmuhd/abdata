"""Helper to send push notifications for transaction events."""

import os
import threading
from sqlalchemy.orm import Session

from ..models.push import PushSubscription
from ..models.user import User


def _send_push(db: Session, user_id: int, title: str, body: str, url: str = "/"):
    try:
        from pywebpush import webpush, WebPushException
        from pathlib import Path
        import json

        # Try env var first, then file
        vapid_key = os.environ.get("VAPID_PRIVATE_KEY")
        if not vapid_key:
            vapid_key_path = Path(__file__).parent.parent.parent / "vapid_private.pem"
            if vapid_key_path.exists():
                vapid_key = vapid_key_path.read_text()
        if not vapid_key:
            return
        subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()

        payload = json.dumps({"title": title, "body": body, "url": url})
        dead = []
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=vapid_key,
                    vapid_claims={"sub": "mailto:admin@zaply.ng"},
                )
            except WebPushException:
                dead.append(sub)
        for sub in dead:
            db.delete(sub)
        if dead:
            db.commit()
    except Exception:
        pass


def notify_transaction(user_id: int, title: str, body: str, url: str = "/"):
    """Send push notification in background thread."""
    from ..core.database import SessionLocal

    def _task():
        db = SessionLocal()
        try:
            _send_push(db, user_id, title, body, url)
        finally:
            db.close()

    threading.Thread(target=_task, daemon=True).start()
