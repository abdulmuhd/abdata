from fastapi import APIRouter

from . import (
    airtime,
    announcements,
    api_manager,
    auth,
    cable,
    data,
    education,
    electricity,
    exams,
    notifications,
    admin,
    services,
    system_users,
    transactions,
    transfer,
    users,
    wallet,
    webhooks,
)

api_router = APIRouter()
for r in (
    auth.router,
    users.router,
    wallet.router,
    services.router,
    airtime.router,
    data.router,
    electricity.router,
    cable.router,
    exams.router,
    education.router,
    transactions.router,
    notifications.router,
    announcements.router,
    admin.router,
    api_manager.router,
    system_users.router,
    transfer.router,
):
    api_router.include_router(r)


@api_router.get("/health", tags=["System"], summary="Service health")
def health():
    return {"success": True, "message": "OK", "data": {"status": "healthy", "service": "zaply-api"}}


# webhook router intentionally mounted without the auth-protected group
webhooks_router = webhooks.router
