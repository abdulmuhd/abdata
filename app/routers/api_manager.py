"""API Manager admin routes — CRUD for providers, credentials, endpoints,
service routing, balance checks, connection tests, and API logs."""

import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.errors import AppError, NotFoundError, ValidationError
from ..core.encryption import encrypt, decrypt
from ..core.config import settings
from ..dependencies.auth import get_current_admin
from ..models import (
    ApiProvider,
    ApiProviderCredential,
    ApiProviderEndpoint,
    ApiProviderService,
    ApiProviderRouting,
    ApiRequestLog,
    User,
)
from ..models.api_provider import HttpMethod, ServiceType
from ..models.system_user import AdminActivityLog

router = APIRouter(prefix="/admin/api-manager", tags=["API Manager"])

# Known VTU providers that can be pre-configured
KNOWN_VTU_PROVIDERS = [
    {
        "name": "bsokdata",
        "code": "bsokdata",
        "base_url": "https://bsokdata.com",
        "description": "BsokData VTU provider — airtime and data",
        "supports_balance_check": True,
        "default_services": ["airtime", "data"],
        "default_credentials": [
            {"credential_key": "bearer_token", "credential_value": "", "is_sensitive": True, "description": "API authentication token"},
        ],
        "default_endpoints": [
            {"operation": "buy_airtime", "path": "/api/topup/", "method": "POST"},
            {"operation": "buy_data", "path": "/api/data/", "method": "POST"},
            {"operation": "check_balance", "path": "/api/user/", "method": "GET"},
            {"operation": "fetch_cable_plans", "path": "/api/cable/", "method": "GET"},
        ],
    },
    {
        "name": "GongozConcept",
        "code": "gongozconcept",
        "base_url": "https://api.gongozconcept.com",
        "description": "GongozConcept VTU provider",
        "supports_balance_check": True,
        "default_services": ["airtime", "data", "cable", "electricity"],
        "default_credentials": [
            {"credential_key": "api_key", "credential_value": "", "is_sensitive": True, "description": "API key"},
            {"credential_key": "api_secret", "credential_value": "", "is_sensitive": True, "description": "API secret"},
        ],
        "default_endpoints": [
            {"operation": "buy_airtime", "path": "/api/airtime", "method": "POST"},
            {"operation": "buy_data", "path": "/api/data", "method": "POST"},
            {"operation": "get_data_plans", "path": "/api/data/plans", "method": "GET"},
            {"operation": "verify_cable_customer", "path": "/api/cable/verify", "method": "POST"},
            {"operation": "pay_cable", "path": "/api/cable", "method": "POST"},
            {"operation": "verify_electricity_customer", "path": "/api/electricity/verify", "method": "POST"},
            {"operation": "pay_electricity", "path": "/api/electricity", "method": "POST"},
            {"operation": "check_balance", "path": "/api/balance", "method": "GET"},
            {"operation": "check_transaction", "path": "/api/transaction/status", "method": "GET"},
        ],
    },
    {
        "name": "LegitDataWay",
        "code": "legitdataway",
        "base_url": "https://api.legitdataway.com",
        "description": "LegitDataWay VTU provider",
        "supports_balance_check": True,
        "default_services": ["airtime", "data"],
        "default_credentials": [
            {"credential_key": "api_token", "credential_value": "", "is_sensitive": True, "description": "API token"},
        ],
        "default_endpoints": [
            {"operation": "buy_airtime", "path": "/api/v1/airtime", "method": "POST"},
            {"operation": "buy_data", "path": "/api/v1/data", "method": "POST"},
            {"operation": "get_data_plans", "path": "/api/v1/data/plans", "method": "GET"},
            {"operation": "check_balance", "path": "/api/v1/balance", "method": "GET"},
        ],
    },
    {
        "name": "Topmate",
        "code": "topmate",
        "base_url": "https://api.topmate.io",
        "description": "Topmate VTU provider",
        "supports_balance_check": False,
        "default_services": ["data", "cable"],
        "default_credentials": [
            {"credential_key": "api_key", "credential_value": "", "is_sensitive": True, "description": "API key"},
        ],
        "default_endpoints": [
            {"operation": "buy_data", "path": "/api/data", "method": "POST"},
            {"operation": "verify_cable_customer", "path": "/api/cable/verify", "method": "POST"},
            {"operation": "pay_cable", "path": "/api/cable", "method": "POST"},
        ],
    },
    {
        "name": "N3Data",
        "code": "n3data",
        "base_url": "https://api.n3data.com",
        "description": "N3Data VTU provider",
        "supports_balance_check": True,
        "default_services": ["airtime", "data", "electricity"],
        "default_credentials": [
            {"credential_key": "api_key", "credential_value": "", "is_sensitive": True, "description": "API key"},
        ],
        "default_endpoints": [
            {"operation": "buy_airtime", "path": "/api/airtime", "method": "POST"},
            {"operation": "buy_data", "path": "/api/data", "method": "POST"},
            {"operation": "check_balance", "path": "/api/balance", "method": "GET"},
        ],
    },
    {
        "name": "VTU.ng",
        "code": "vtung",
        "base_url": "https://vtu.ng/api",
        "description": "VTU.ng provider",
        "supports_balance_check": True,
        "default_services": ["airtime", "data"],
        "default_credentials": [
            {"credential_key": "api_key", "credential_value": "", "is_sensitive": True, "description": "API key"},
            {"credential_key": "secret_key", "credential_value": "", "is_sensitive": True, "description": "Secret key"},
        ],
        "default_endpoints": [
            {"operation": "buy_airtime", "path": "/airtime", "method": "POST"},
            {"operation": "buy_data", "path": "/data", "method": "POST"},
            {"operation": "check_balance", "path": "/balance", "method": "GET"},
        ],
    },
    {
        "name": "VTpass",
        "code": "vtpass",
        "base_url": "https://vtpass.com/api",
        "description": "VTpass provider",
        "supports_balance_check": True,
        "default_services": ["airtime", "data", "cable", "electricity"],
        "default_credentials": [
            {"credential_key": "api_key", "credential_value": "", "is_sensitive": True, "description": "API key"},
            {"credential_key": "secret_key", "credential_value": "", "is_sensitive": True, "description": "Secret key"},
        ],
        "default_endpoints": [
            {"operation": "buy_airtime", "path": "/pay", "method": "POST"},
            {"operation": "buy_data", "path": "/pay", "method": "POST"},
            {"operation": "verify_customer", "path": "/merchant-verify", "method": "POST"},
            {"operation": "check_balance", "path": "/balance", "method": "GET"},
            {"operation": "check_transaction", "path": "/requery", "method": "GET"},
        ],
    },
    {
        "name": "mock",
        "code": "mock",
        "base_url": "http://localhost:8000",
        "description": "Built-in mock provider for testing",
        "supports_balance_check": False,
        "default_services": ["airtime", "data", "cable", "electricity", "exam_pins", "education"],
        "default_credentials": [],
        "default_endpoints": [],
    },
]


# ── Schemas ──────────────────────────────────────────────────────────────

class ProviderCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=50)
    base_url: str = Field(min_length=5, max_length=500)
    description: str | None = None
    supports_balance_check: bool = False


class ProviderUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    base_url: str | None = Field(default=None, min_length=5, max_length=500)
    description: str | None = None
    is_active: bool | None = None
    supports_balance_check: bool | None = None


class CredentialIn(BaseModel):
    credential_key: str = Field(min_length=1, max_length=80)
    credential_value: str = Field(min_length=1)
    is_sensitive: bool = True
    description: str | None = None


class EndpointIn(BaseModel):
    operation: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=500)
    method: str = "POST"
    request_mapping: dict | None = None
    response_mapping: dict | None = None
    headers: dict | None = None


class ServiceToggleIn(BaseModel):
    service_type: str
    is_enabled: bool = True


class RoutingIn(BaseModel):
    service_type: str
    provider_id: int
    priority: int = 1


class TestConnectionIn(BaseModel):
    provider_id: int


# ── Helpers ──────────────────────────────────────────────────────────────

def _mask_credential(value: str) -> str:
    """Mask sensitive credential values for display."""
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "•••" + value[-4:]


def _log_admin_action(db: Session, admin: User, action: str, details: str | None = None,
                       previous_value: str | None = None, new_value: str | None = None):
    db.add(AdminActivityLog(
        system_user_id=None,
        user_name=admin.full_name,
        action=action,
        details=details,
        previous_value=previous_value,
        new_value=new_value,
    ))


def _page_meta(page: int, per_page: int, total: int):
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": max((total + per_page - 1) // per_page, 1),
    }


# ── Known providers & seeding ───────────────────────────────────────────

@router.get("/known-providers", summary="List known VTU provider templates")
def list_known_providers(
    _: User = Depends(get_current_admin),
):
    """Return pre-configured provider templates for quick setup."""
    return {
        "success": True,
        "message": "OK",
        "data": [
            {
                "name": p["name"],
                "code": p["code"],
                "base_url": p["base_url"],
                "description": p["description"],
                "supports_balance_check": p["supports_balance_check"],
                "services": p["default_services"],
            }
            for p in KNOWN_VTU_PROVIDERS
        ],
    }


@router.post("/seed/{provider_code}", summary="Quick-add a known provider by code")
def seed_provider(
    provider_code: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Pre-configure a known VTU provider with default endpoints and credential placeholders."""
    template = next((p for p in KNOWN_VTU_PROVIDERS if p["code"] == provider_code.lower()), None)
    if not template:
        raise ValidationError(f"Unknown provider code: {provider_code}")

    if db.query(ApiProvider).filter(ApiProvider.code == template["code"]).first():
        raise ValidationError(f"Provider '{template['name']}' already exists.")

    p = ApiProvider(
        name=template["name"],
        code=template["code"],
        base_url=template["base_url"],
        description=template["description"],
        supports_balance_check=template["supports_balance_check"],
    )
    db.add(p)
    db.flush()

    for cred in template["default_credentials"]:
        db.add(ApiProviderCredential(provider_id=p.id, **cred))

    for ep in template["default_endpoints"]:
        db.add(ApiProviderEndpoint(provider_id=p.id, **ep))

    for svc in template["default_services"]:
        try:
            svc_type = ServiceType(svc)
            db.add(ApiProviderService(provider_id=p.id, service_type=svc_type, is_enabled=True))
        except ValueError:
            pass

    _log_admin_action(db, admin, "seed_provider", f"Seeded provider: {p.name}")
    db.commit()
    return {"success": True, "message": f"Provider '{p.name}' pre-configured.", "data": {"id": p.id, "code": p.code}}


@router.post("/seed-defaults", summary="Seed bsokdata as the default provider")
def seed_defaults(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Create bsokdata as default provider if no providers exist yet."""
    if db.query(ApiProvider).count() > 0:
        return {"success": True, "message": "Providers already exist. Skipping seed.", "data": None}

    template = next(p for p in KNOWN_VTU_PROVIDERS if p["code"] == "bsokdata")
    p = ApiProvider(
        name=template["name"],
        code=template["code"],
        base_url=template["base_url"],
        description=template["description"],
        supports_balance_check=template["supports_balance_check"],
    )
    db.add(p)
    db.flush()

    for cred in template["default_credentials"]:
        db.add(ApiProviderCredential(provider_id=p.id, **cred))

    for ep in template["default_endpoints"]:
        db.add(ApiProviderEndpoint(provider_id=p.id, **ep))

    for svc in template["default_services"]:
        try:
            svc_type = ServiceType(svc)
            db.add(ApiProviderService(provider_id=p.id, service_type=svc_type, is_enabled=True))
        except ValueError:
            pass

    _log_admin_action(db, admin, "seed_defaults", "Seeded default provider: bsokdata")
    db.commit()
    return {"success": True, "message": "bsokdata provider pre-configured as default.", "data": {"id": p.id}}


# ── Provider CRUD ────────────────────────────────────────────────────────

@router.get("/providers", summary="List all API providers")
def list_providers(
    q: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    query = db.query(ApiProvider)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(ApiProvider.name.ilike(like) | ApiProvider.code.ilike(like))
    if is_active is not None:
        query = query.filter(ApiProvider.is_active == is_active)

    total = query.count()
    rows = query.order_by(ApiProvider.id.asc()).offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for p in rows:
        services = db.query(ApiProviderService).filter(ApiProviderService.provider_id == p.id).all()
        svc_list = [s.service_type.value for s in services if s.is_enabled]
        items.append({
            "id": p.id,
            "name": p.name,
            "code": p.code,
            "base_url": p.base_url,
            "description": p.description,
            "is_active": p.is_active,
            "supports_balance_check": p.supports_balance_check,
            "services": svc_list,
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
        })

    return {
        "success": True,
        "message": "OK",
        "data": {"items": items, "meta": _page_meta(page, per_page, total)},
    }


@router.get("/providers/{provider_id}", summary="Get provider details")
def get_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise NotFoundError("Provider not found")

    credentials = db.query(ApiProviderCredential).filter(ApiProviderCredential.provider_id == p.id).all()
    endpoints = db.query(ApiProviderEndpoint).filter(ApiProviderEndpoint.provider_id == p.id).all()
    services = db.query(ApiProviderService).filter(ApiProviderService.provider_id == p.id).all()
    routing = db.query(ApiProviderRouting).filter(ApiProviderRouting.provider_id == p.id).all()

    return {
        "success": True,
        "message": "OK",
        "data": {
            "id": p.id,
            "name": p.name,
            "code": p.code,
            "base_url": p.base_url,
            "description": p.description,
            "is_active": p.is_active,
            "supports_balance_check": p.supports_balance_check,
            "credentials": [
                {
                    "id": c.id,
                    "credential_key": c.credential_key,
                    "credential_value_masked": _mask_credential(c.credential_value) if c.is_sensitive else c.credential_value,
                    "is_sensitive": c.is_sensitive,
                    "description": c.description,
                }
                for c in credentials
            ],
            "endpoints": [
                {
                    "id": e.id,
                    "operation": e.operation,
                    "path": e.path,
                    "method": e.method.value if hasattr(e.method, "value") else e.method,
                    "request_mapping": e.request_mapping,
                    "response_mapping": e.response_mapping,
                    "headers": e.headers,
                }
                for e in endpoints
            ],
            "services": [
                {
                    "id": s.id,
                    "service_type": s.service_type.value,
                    "is_enabled": s.is_enabled,
                }
                for s in services
            ],
            "routing": [
                {
                    "id": r.id,
                    "service_type": r.service_type.value,
                    "provider_id": r.provider_id,
                    "priority": r.priority,
                    "is_active": r.is_active,
                }
                for r in routing
            ],
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
        },
    }


@router.post("/providers", summary="Add a new API provider")
def create_provider(
    payload: ProviderCreateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if db.query(ApiProvider).filter(ApiProvider.code == payload.code.lower()).first():
        raise ValidationError("A provider with this code already exists.")
    if db.query(ApiProvider).filter(ApiProvider.name == payload.name).first():
        raise ValidationError("A provider with this name already exists.")

    p = ApiProvider(
        name=payload.name,
        code=payload.code.lower(),
        base_url=payload.base_url.rstrip("/"),
        description=payload.description,
        supports_balance_check=payload.supports_balance_check,
    )
    db.add(p)
    db.flush()
    _log_admin_action(db, admin, "add_provider", f"Added provider: {p.name}")
    db.commit()
    return {"success": True, "message": f"Provider '{p.name}' created.", "data": {"id": p.id, "code": p.code}}


@router.put("/providers/{provider_id}", summary="Edit an API provider")
def update_provider(
    provider_id: int,
    payload: ProviderUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise NotFoundError("Provider not found")

    changes = []
    if payload.name is not None:
        existing = db.query(ApiProvider).filter(ApiProvider.name == payload.name, ApiProvider.id != provider_id).first()
        if existing:
            raise ValidationError("A provider with this name already exists.")
        changes.append(f"name: {p.name} → {payload.name}")
        p.name = payload.name
    if payload.base_url is not None:
        p.base_url = payload.base_url.rstrip("/")
    if payload.description is not None:
        p.description = payload.description
    if payload.is_active is not None:
        p.is_active = payload.is_active
        changes.append(f"active: {not payload.is_active} → {payload.is_active}")
    if payload.supports_balance_check is not None:
        p.supports_balance_check = payload.supports_balance_check

    if changes:
        _log_admin_action(db, admin, "edit_provider", f"Updated provider: {p.name}", previous_value=None, new_value="; ".join(changes))
    db.commit()
    return {"success": True, "message": f"Provider '{p.name}' updated.", "data": {"id": p.id}}


@router.delete("/providers/{provider_id}", summary="Delete an API provider")
def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise NotFoundError("Provider not found")

    # Check if provider is used in routing
    routing_count = db.query(ApiProviderRouting).filter(ApiProviderRouting.provider_id == provider_id).count()
    if routing_count > 0:
        raise ValidationError("Cannot delete provider that is used in service routing. Remove routing entries first.")

    name = p.name
    db.delete(p)
    _log_admin_action(db, admin, "delete_provider", f"Deleted provider: {name}")
    db.commit()
    return {"success": True, "message": f"Provider '{name}' deleted.", "data": None}


# ── Credentials ──────────────────────────────────────────────────────────

@router.post("/providers/{provider_id}/credentials", summary="Add a credential to a provider")
def add_credential(
    provider_id: int,
    payload: CredentialIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise NotFoundError("Provider not found")

    existing = db.query(ApiProviderCredential).filter(
        ApiProviderCredential.provider_id == provider_id,
        ApiProviderCredential.credential_key == payload.credential_key,
    ).first()
    if existing:
        existing.credential_value = encrypt(payload.credential_value, settings.SECRET_KEY) if payload.is_sensitive else payload.credential_value
        existing.is_sensitive = payload.is_sensitive
        existing.description = payload.description
        _log_admin_action(db, admin, "edit_credential", f"Updated credential '{payload.credential_key}' on {p.name}")
        db.commit()
        return {"success": True, "message": "Credential updated.", "data": {"id": existing.id}}

    cred = ApiProviderCredential(
        provider_id=provider_id,
        credential_key=payload.credential_key,
        credential_value=encrypt(payload.credential_value, settings.SECRET_KEY) if payload.is_sensitive else payload.credential_value,
        is_sensitive=payload.is_sensitive,
        description=payload.description,
    )
    db.add(cred)
    _log_admin_action(db, admin, "add_credential", f"Added credential '{payload.credential_key}' to {p.name}")
    db.commit()
    return {"success": True, "message": "Credential added.", "data": {"id": cred.id}}


@router.put("/credentials/{cred_id}", summary="Update a credential")
def update_credential(
    cred_id: int,
    payload: CredentialIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    cred = db.get(ApiProviderCredential, cred_id)
    if not cred:
        raise NotFoundError("Credential not found")

    cred.credential_key = payload.credential_key
    cred.credential_value = payload.credential_value
    cred.is_sensitive = payload.is_sensitive
    cred.description = payload.description
    _log_admin_action(db, admin, "edit_credential", f"Updated credential '{payload.credential_key}'")
    db.commit()
    return {"success": True, "message": "Credential updated.", "data": {"id": cred.id}}


@router.delete("/credentials/{cred_id}", summary="Delete a credential")
def delete_credential(
    cred_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    cred = db.get(ApiProviderCredential, cred_id)
    if not cred:
        raise NotFoundError("Credential not found")

    key = cred.credential_key
    db.delete(cred)
    _log_admin_action(db, admin, "delete_credential", f"Deleted credential '{key}'")
    db.commit()
    return {"success": True, "message": "Credential deleted.", "data": None}


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/providers/{provider_id}/endpoints", summary="Add an endpoint to a provider")
def add_endpoint(
    provider_id: int,
    payload: EndpointIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise NotFoundError("Provider not found")

    method_str = payload.method.upper()
    try:
        method = HttpMethod(method_str)
    except ValueError:
        raise ValidationError(f"Invalid HTTP method: {method_str}. Use GET, POST, PUT, or PATCH.")

    existing = db.query(ApiProviderEndpoint).filter(
        ApiProviderEndpoint.provider_id == provider_id,
        ApiProviderEndpoint.operation == payload.operation,
    ).first()
    if existing:
        raise ValidationError(f"An endpoint for operation '{payload.operation}' already exists.")

    ep = ApiProviderEndpoint(
        provider_id=provider_id,
        operation=payload.operation,
        path=payload.path,
        method=method,
        request_mapping=payload.request_mapping,
        response_mapping=payload.response_mapping,
        headers=payload.headers,
    )
    db.add(ep)
    _log_admin_action(db, admin, "add_endpoint", f"Added endpoint '{payload.operation}' to {p.name}")
    db.commit()
    return {"success": True, "message": "Endpoint added.", "data": {"id": ep.id}}


@router.put("/endpoints/{endpoint_id}", summary="Update an endpoint")
def update_endpoint(
    endpoint_id: int,
    payload: EndpointIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    ep = db.get(ApiProviderEndpoint, endpoint_id)
    if not ep:
        raise NotFoundError("Endpoint not found")

    method_str = payload.method.upper()
    try:
        method = HttpMethod(method_str)
    except ValueError:
        raise ValidationError(f"Invalid HTTP method: {method_str}.")

    ep.operation = payload.operation
    ep.path = payload.path
    ep.method = method
    ep.request_mapping = payload.request_mapping
    ep.response_mapping = payload.response_mapping
    ep.headers = payload.headers
    _log_admin_action(db, admin, "edit_endpoint", f"Updated endpoint '{payload.operation}'")
    db.commit()
    return {"success": True, "message": "Endpoint updated.", "data": {"id": ep.id}}


@router.delete("/endpoints/{endpoint_id}", summary="Delete an endpoint")
def delete_endpoint(
    endpoint_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    ep = db.get(ApiProviderEndpoint, endpoint_id)
    if not ep:
        raise NotFoundError("Endpoint not found")

    op = ep.operation
    db.delete(ep)
    _log_admin_action(db, admin, "delete_endpoint", f"Deleted endpoint '{op}'")
    db.commit()
    return {"success": True, "message": "Endpoint deleted.", "data": None}


# ── Services ─────────────────────────────────────────────────────────────

@router.get("/providers/{provider_id}/services", summary="Get provider services")
def get_provider_services(
    provider_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise NotFoundError("Provider not found")

    services = db.query(ApiProviderService).filter(ApiProviderService.provider_id == provider_id).all()
    return {
        "success": True,
        "message": "OK",
        "data": [
            {"id": s.id, "service_type": s.service_type.value, "is_enabled": s.is_enabled}
            for s in services
        ],
    }


@router.put("/providers/{provider_id}/services", summary="Set provider services")
def set_provider_services(
    provider_id: int,
    payloads: list[ServiceToggleIn],
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise NotFoundError("Provider not found")

    for item in payloads:
        try:
            svc_type = ServiceType(item.service_type)
        except ValueError:
            raise ValidationError(f"Invalid service type: {item.service_type}")

        existing = db.query(ApiProviderService).filter(
            ApiProviderService.provider_id == provider_id,
            ApiProviderService.service_type == svc_type,
        ).first()
        if existing:
            existing.is_enabled = item.is_enabled
        else:
            db.add(ApiProviderService(provider_id=provider_id, service_type=svc_type, is_enabled=item.is_enabled))

    _log_admin_action(db, admin, "update_services", f"Updated services for {p.name}")
    db.commit()
    return {"success": True, "message": "Services updated.", "data": None}


# ── Routing ──────────────────────────────────────────────────────────────

@router.get("/routing", summary="Get service provider routing configuration")
def get_routing(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    rows = db.query(ApiProviderRouting).order_by(
        ApiProviderRouting.service_type, ApiProviderRouting.priority
    ).all()

    result = {}
    for r in rows:
        svc = r.service_type.value
        if svc not in result:
            result[svc] = []
        provider = db.get(ApiProvider, r.provider_id)
        result[svc].append({
            "id": r.id,
            "service_type": svc,
            "provider_id": r.provider_id,
            "provider_name": provider.name if provider else "Unknown",
            "priority": r.priority,
            "is_active": r.is_active,
        })

    return {"success": True, "message": "OK", "data": result}


@router.post("/routing", summary="Set a routing entry")
def set_routing(
    payload: RoutingIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    try:
        svc_type = ServiceType(payload.service_type)
    except ValueError:
        raise ValidationError(f"Invalid service type: {payload.service_type}")

    provider = db.get(ApiProvider, payload.provider_id)
    if not provider:
        raise NotFoundError("Provider not found")

    existing = db.query(ApiProviderRouting).filter(
        ApiProviderRouting.service_type == svc_type,
        ApiProviderRouting.priority == payload.priority,
    ).first()

    old_provider_name = None
    if existing:
        old_p = db.get(ApiProvider, existing.provider_id)
        old_provider_name = old_p.name if old_p else "Unknown"
        existing.provider_id = payload.provider_id
    else:
        db.add(ApiProviderRouting(
            service_type=svc_type,
            provider_id=payload.provider_id,
            priority=payload.priority,
        ))

    _log_admin_action(
        db, admin, "change_routing",
        f"Changed {payload.service_type} routing (priority {payload.priority})",
        previous_value=old_provider_name,
        new_value=provider.name,
    )
    db.commit()
    return {"success": True, "message": f"Routing updated for {payload.service_type}.", "data": None}


@router.delete("/routing/{routing_id}", summary="Remove a routing entry")
def delete_routing(
    routing_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    r = db.get(ApiProviderRouting, routing_id)
    if not r:
        raise NotFoundError("Routing entry not found")

    _log_admin_action(db, admin, "delete_routing", f"Deleted routing entry for {r.service_type.value}")
    db.delete(r)
    db.commit()
    return {"success": True, "message": "Routing entry deleted.", "data": None}


# ── Provider Balance ─────────────────────────────────────────────────────

@router.get("/providers/{provider_id}/balance", summary="Check provider balance")
def check_balance(
    provider_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise NotFoundError("Provider not found")

    if not p.supports_balance_check:
        return {"success": True, "message": "Balance checking not supported for this provider.", "data": None}

    # Get credentials and balance endpoint
    credentials = {
        c.credential_key: c.credential_value
        for c in db.query(ApiProviderCredential).filter(ApiProviderCredential.provider_id == provider_id).all()
    }
    balance_ep = db.query(ApiProviderEndpoint).filter(
        ApiProviderEndpoint.provider_id == provider_id,
        ApiProviderEndpoint.operation == "check_balance",
    ).first()

    if not balance_ep:
        return {"success": True, "message": "No balance endpoint configured.", "data": None}

    try:
        url = f"{p.base_url}{balance_ep.path}"
        headers = {}
        if balance_ep.headers:
            for k, v in balance_ep.headers.items():
                headers[k] = v.format(**credentials) if isinstance(v, str) else v

        # Build auth header from credentials if not already set
        if not headers:
            auth_keys = [
                ("api_token", "Authorization"),
                ("api_key", "Api-Key"),
                ("authorization", "Authorization"),
                ("token", "Token"),
                ("bearer_token", "Authorization"),
            ]
            for key, header_name in auth_keys:
                if key in credentials:
                    val = credentials[key]
                    if header_name == "Authorization":
                        if key in ("api_token", "bearer_token", "token"):
                            val = val.strip()
                            if val.startswith("Token "):
                                pass
                            elif val.startswith("Bearer "):
                                val = "Token " + val[7:]
                            else:
                                val = f"Token {val}"
                        elif key == "authorization" and not val.startswith("Bearer"):
                            val = f"Bearer {val}"
                    headers[header_name] = val
                    break

        started = time.perf_counter()
        if balance_ep.method == HttpMethod.GET:
            resp = httpx.get(url, headers=headers, timeout=15.0)
        else:
            resp = httpx.post(url, headers=headers, timeout=15.0)
        duration = int((time.perf_counter() - started) * 1000)

        body = resp.json() if resp.status_code == 200 else {}

        # Apply response mapping
        mapped = body
        if balance_ep.response_mapping:
            mapped = {}
            for local_key, remote_path in balance_ep.response_mapping.items():
                if isinstance(remote_path, str) and remote_path.startswith("$."):
                    parts = remote_path[2:].split(".")
                    val = body
                    for part in parts:
                        val = val.get(part) if isinstance(val, dict) else None
                    mapped[local_key] = val
                else:
                    mapped[local_key] = remote_path

        # Try to extract balance from common paths if not mapped
        bal = mapped.get("balance")
        if bal is None:
            for path in ["Account_Balance", "wallet_balance", "balance_naira", "available_balance"]:
                if isinstance(body, dict):
                    inner = body.get("user", body) if isinstance(body.get("user"), dict) else body
                    val = inner.get(path)
                    if val is not None:
                        try:
                            bal = float(val)
                        except (TypeError, ValueError):
                            bal = val
                        break

        return {
            "success": True,
            "message": "Balance retrieved.",
            "data": {
                "balance": bal,
                "currency": mapped.get("currency", "NGN"),
                "raw": body,
            },
        }
    except Exception as exc:
        raise AppError(f"Failed to check balance: {exc}", code="balance_check_failed", status_code=502)


# ── Test Connection ──────────────────────────────────────────────────────

@router.post("/providers/test", summary="Test provider API connection")
def test_connection(
    payload: TestConnectionIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    p = db.get(ApiProvider, payload.provider_id)
    if not p:
        raise NotFoundError("Provider not found")

    credentials = {
        c.credential_key: c.credential_value
        for c in db.query(ApiProviderCredential).filter(ApiProviderCredential.provider_id == p.id).all()
    }

    # Try to find a suitable endpoint to test, preferring check_balance
    test_ep = (
        db.query(ApiProviderEndpoint)
        .filter(ApiProviderEndpoint.provider_id == p.id, ApiProviderEndpoint.operation == "check_balance")
        .first()
        or db.query(ApiProviderEndpoint).filter(ApiProviderEndpoint.provider_id == p.id).first()
    )

    started = time.perf_counter()
    try:
        headers = {}
        if test_ep:
            url = f"{p.base_url}{test_ep.path}"
            if test_ep.headers:
                for k, v in test_ep.headers.items():
                    try:
                        headers[k] = v.format(**credentials) if isinstance(v, str) else v
                    except KeyError:
                        headers[k] = v
        else:
            url = p.base_url

        # Build auth header from credentials if not already set
        if not headers:
            auth_keys = [
                ("api_token", "Authorization"),
                ("api_key", "Api-Key"),
                ("authorization", "Authorization"),
                ("token", "Token"),
                ("bearer_token", "Authorization"),
            ]
            for key, header_name in auth_keys:
                if key in credentials:
                    val = credentials[key]
                    if header_name == "Authorization":
                        if key in ("api_token", "bearer_token", "token"):
                            val = val.strip()
                            if val.startswith("Token "):
                                pass
                            elif val.startswith("Bearer "):
                                val = "Token " + val[7:]
                            else:
                                val = f"Token {val}"
                        elif key == "authorization" and not val.startswith("Bearer"):
                            val = f"Bearer {val}"
                    headers[header_name] = val
                    break

        method = test_ep.method if test_ep else HttpMethod.GET
        if method == HttpMethod.POST:
            resp = httpx.post(url, headers=headers, timeout=10.0)
        else:
            resp = httpx.get(url, headers=headers, timeout=10.0)
        duration = int((time.perf_counter() - started) * 1000)

        # Log the test
        db.add(ApiRequestLog(
            provider_id=p.id,
            provider_name=p.name,
            operation="test_connection",
            endpoint_url=url,
            http_method=method.value if hasattr(method, "value") else str(method),
            request_payload={"headers": {k: "***" for k in headers}},
            response_payload={"status_code": resp.status_code},
            http_status_code=resp.status_code,
            success=200 <= resp.status_code < 400,
            duration_ms=duration,
        ))
        db.flush()

        if 200 <= resp.status_code < 400:
            return {
                "success": True,
                "message": "Connection successful. Authentication successful.",
                "data": {"http_status": resp.status_code, "duration_ms": duration},
            }
        else:
            return {
                "success": False,
                "message": f"Connection failed. HTTP {resp.status_code}.",
                "data": {"http_status": resp.status_code, "duration_ms": duration},
            }
    except Exception as exc:
        duration = int((time.perf_counter() - started) * 1000)
        db.add(ApiRequestLog(
            provider_id=p.id,
            provider_name=p.name,
            operation="test_connection",
            endpoint_url=p.base_url,
            http_method="GET",
            request_payload={},
            response_payload={"error": str(exc)},
            success=False,
            error_message=str(exc),
            duration_ms=duration,
        ))
        db.flush()
        return {
            "success": False,
            "message": f"Connection failed: {exc.__class__.__name__}",
            "data": {"duration_ms": duration},
        }


# ── API Logs ─────────────────────────────────────────────────────────────

@router.get("/logs", summary="API request/response logs")
def list_logs(
    provider_id: int | None = None,
    service_type: str | None = None,
    success: bool | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    query = db.query(ApiRequestLog)
    if provider_id is not None:
        query = query.filter(ApiRequestLog.provider_id == provider_id)
    if service_type:
        query = query.filter(ApiRequestLog.service_type == service_type)
    if success is not None:
        query = query.filter(ApiRequestLog.success == success)

    total = query.count()
    rows = query.order_by(ApiRequestLog.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    # Scrub sensitive data from logs
    safe_logs = []
    for log in rows:
        safe_request = {k: v for k, v in log.request_payload.items() if k.lower() not in ("authorization", "password", "secret", "token", "api_key")}
        safe_logs.append({
            "id": log.id,
            "provider_name": log.provider_name,
            "service_type": log.service_type,
            "operation": log.operation,
            "reference": log.reference,
            "provider_reference": log.provider_reference,
            "endpoint_url": log.endpoint_url,
            "http_method": log.http_method,
            "http_status_code": log.http_status_code,
            "success": log.success,
            "error_message": log.error_message,
            "duration_ms": log.duration_ms,
            "created_at": log.created_at.isoformat(),
        })

    return {
        "success": True,
        "message": "OK",
        "data": {"items": safe_logs, "meta": _page_meta(page, per_page, total)},
    }
