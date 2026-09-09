from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..dependencies.auth import get_current_user
from ..models import CablePackage, DataPlan, Provider, ServiceTypeEnum, User
from ..schemas.auth import ProviderOut

router = APIRouter(prefix="/services", tags=["Services"])


@router.get("", summary="Full services catalog for the app")
def catalog(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def providers_of(service: ServiceTypeEnum):
        rows = (
            db.query(Provider)
            .filter(Provider.service_type == service, Provider.is_active.is_(True))
            .order_by(Provider.sort_order)
            .all()
        )
        return [ProviderOut.model_validate(r).model_dump(mode="json") for r in rows]

    data = {
        "airtime_networks": providers_of(ServiceTypeEnum.AIRTIME),
        "electricity_providers": providers_of(ServiceTypeEnum.ELECTRICITY),
        "cable_providers": providers_of(ServiceTypeEnum.CABLE),
        "exam_bodies": providers_of(ServiceTypeEnum.EXAM_PINS),
        "institutions": providers_of(ServiceTypeEnum.EDUCATION),
        "coming_soon": [],
    }
    return {"success": True, "message": "OK", "data": data}
