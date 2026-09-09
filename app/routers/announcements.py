from fastapi import APIRouter

from ..core.config import settings

router = APIRouter(prefix="/announcements", tags=["Announcements"])


@router.get("/active", summary="Current announcement shown after sign-in")
def active_announcement():
    """Public, config-driven announcement. Returns null when disabled."""
    if not settings.ANNOUNCEMENT_ENABLED or not settings.ANNOUNCEMENT_TITLE:
        return {"success": True, "message": "OK", "data": None}

    # Stable id derived from the content so a changed announcement re-shows.
    source = f"{settings.ANNOUNCEMENT_TITLE}|{settings.ANNOUNCEMENT_BODY}"
    numeric = sum((i + 1) * ord(c) for i, c in enumerate(source)) % 10**10

    return {
        "success": True,
        "message": "OK",
        "data": {
            "id": str(numeric),
            "title": settings.ANNOUNCEMENT_TITLE,
            "body": settings.ANNOUNCEMENT_BODY,
            "cta_label": settings.ANNOUNCEMENT_CTA_LABEL,
            "cta_path": settings.ANNOUNCEMENT_CTA_PATH,
        },
    }
