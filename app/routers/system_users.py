"""System Users admin routes — CRUD for staff accounts, roles, and permissions."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.errors import AppError, NotFoundError, ValidationError
from ..core.security import hash_password, verify_password
from ..dependencies.auth import get_current_admin
from ..models import User
from ..models.system_user import (
    SystemUser,
    SystemRole,
    SystemPermission,
    AdminActivityLog,
    SystemUserRoleEnum,
    SystemUserStatus,
    role_permissions,
)

router = APIRouter(prefix="/admin/system-users", tags=["System Users"])


# ── Schemas ──────────────────────────────────────────────────────────────

class SystemUserCreateIn(BaseModel):
    user_id: int  # promote an existing user
    role: str = "moderator"


class SystemUserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, min_length=5, max_length=255)
    phone: str | None = None
    role: str | None = None
    status: str | None = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=6)


class RoleCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    permissions: list[str] = []


class RoleUpdateIn(BaseModel):
    display_name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


# ── Helpers ──────────────────────────────────────────────────────────────

def _log_admin_action(db: Session, user_name: str, action: str, details: str | None = None,
                       previous_value: str | None = None, new_value: str | None = None):
    db.add(AdminActivityLog(
        system_user_id=None,
        user_name=user_name,
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


def _ensure_default_roles(db: Session):
    """Create default roles if they don't exist."""
    defaults = [
        {
            "name": "super_admin",
            "display_name": "Super Admin",
            "description": "Full access to all admin features",
            "permissions": [
                "users.view", "users.create", "users.edit", "users.delete",
                "transactions.view", "transactions.manage", "transactions.refund",
                "wallet.view", "wallet.manage",
                "providers.view", "providers.create", "providers.edit", "providers.delete", "providers.configure",
                "provider_routing.view", "provider_routing.manage",
                "pricing.view", "pricing.manage",
                "system_users.view", "system_users.create", "system_users.edit", "system_users.delete",
                "settings.view", "settings.manage",
                "logs.view",
            ],
        },
        {
            "name": "admin",
            "display_name": "Admin",
            "description": "Standard admin access",
            "permissions": [
                "users.view", "users.create", "users.edit",
                "transactions.view", "transactions.manage",
                "wallet.view", "wallet.manage",
                "providers.view",
                "pricing.view", "pricing.manage",
                "system_users.view",
                "settings.view",
                "logs.view",
            ],
        },
        {
            "name": "moderator",
            "display_name": "Moderator",
            "description": "Limited operational access",
            "permissions": [
                "users.view",
                "transactions.view",
                "wallet.view",
                "providers.view",
                "pricing.view",
                "broadcast.send",
            ],
        },
    ]

    for role_data in defaults:
        existing = db.query(SystemRole).filter(SystemRole.name == role_data["name"]).first()
        if not existing:
            role = SystemRole(
                name=role_data["name"],
                display_name=role_data["display_name"],
                description=role_data["description"],
                is_system=True,
            )
            db.add(role)
            db.flush()

            for perm_code in role_data["permissions"]:
                perm = db.query(SystemPermission).filter(SystemPermission.code == perm_code).first()
                if not perm:
                    perm = SystemPermission(code=perm_code, description=perm_code.replace(".", " ").title())
                    db.add(perm)
                    db.flush()
                role.permissions.append(perm)
        else:
            # Sync permissions for existing roles
            existing_perm_codes = {p.code for p in existing.permissions}
            for perm_code in role_data["permissions"]:
                if perm_code not in existing_perm_codes:
                    perm = db.query(SystemPermission).filter(SystemPermission.code == perm_code).first()
                    if not perm:
                        perm = SystemPermission(code=perm_code, description=perm_code.replace(".", " ").title())
                        db.add(perm)
                        db.flush()
                    existing.permissions.append(perm)

    db.flush()


# ── System Users CRUD ────────────────────────────────────────────────────

@router.get("/me/permissions", summary="Get current user's admin permissions")
def my_permissions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    _ensure_default_roles(db)
    from ..dependencies.auth import is_admin_email
    if is_admin_email(user.email):
        return {"success": True, "data": {"is_superadmin": True, "permissions": []}}

    su = db.query(SystemUser).filter(SystemUser.user_id == user.id, SystemUser.status == "active").first()
    if not su or not su.role:
        return {"success": True, "data": {"is_superadmin": False, "permissions": []}}

    perms = [p.code for p in su.role.permissions]
    return {"success": True, "data": {"is_superadmin": False, "permissions": perms}}


@router.get("", summary="List all system users")
def list_system_users(
    q: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    _ensure_default_roles(db)

    query = db.query(SystemUser)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            SystemUser.full_name.ilike(like)
            | SystemUser.email.ilike(like)
            | SystemUser.username.ilike(like)
        )
    if status:
        query = query.filter(SystemUser.status == status)

    total = query.count()
    rows = query.order_by(SystemUser.id.asc()).offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for u in rows:
        role = db.get(SystemRole, u.role_id)
        items.append({
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone,
            "username": u.username,
            "role_id": u.role_id,
            "role_name": role.display_name if role else "Unknown",
            "status": u.status if isinstance(u.status, str) else u.status.value,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat(),
        })

    return {
        "success": True,
        "message": "OK",
        "data": {"items": items, "meta": _page_meta(page, per_page, total)},
    }


@router.get("/search-users", summary="Search users by email for system user promotion")
def search_users_for_promotion(
    q: str = Query("", min_length=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    if len(q.strip()) < 2:
        return {"success": True, "data": []}

    like = f"%{q.strip()}%"
    existing_su_user_ids = db.query(SystemUser.user_id).filter(SystemUser.user_id.isnot(None)).subquery()
    users = (
        db.query(User)
        .filter(
            (User.email.ilike(like) | User.full_name.ilike(like)),
            User.id.notin_(db.query(existing_su_user_ids)),
        )
        .limit(10)
        .all()
    )
    return {
        "success": True,
        "data": [
            {"id": u.id, "full_name": u.full_name, "email": u.email, "phone": u.phone}
            for u in users
        ],
    }


@router.get("/{user_id}", summary="Get system user details")
def get_system_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    u = db.get(SystemUser, user_id)
    if not u:
        raise NotFoundError("System user not found")

    role = db.get(SystemRole, u.role_id)
    return {
        "success": True,
        "message": "OK",
        "data": {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone,
            "username": u.username,
            "role_id": u.role_id,
            "role_name": role.display_name if role else "Unknown",
            "status": u.status if isinstance(u.status, str) else u.status.value,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat(),
        },
    }


@router.post("", summary="Promote an existing user to system user")
def create_system_user(
    payload: SystemUserCreateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    _ensure_default_roles(db)

    user = db.get(User, payload.user_id)
    if not user:
        raise NotFoundError("User not found")

    if db.query(SystemUser).filter(SystemUser.user_id == user.id).first():
        raise ValidationError("This user is already a system user.")

    role = db.query(SystemRole).filter(SystemRole.name == payload.role.lower()).first()
    if not role:
        raise ValidationError(f"Role '{payload.role}' not found.")

    # Generate a username from email
    username = user.email.split("@")[0].lower()
    base_username = username
    counter = 1
    while db.query(SystemUser).filter(SystemUser.username == username).first():
        username = f"{base_username}{counter}"
        counter += 1

    su = SystemUser(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        username=username,
        password_hash=user.password_hash,
        role_id=role.id,
        status="active",
    )
    db.add(su)
    db.flush()
    _log_admin_action(db, admin.full_name, "add_system_user", f"Promoted user to system user: {su.full_name} ({su.email}) as {role.display_name}")
    db.commit()
    return {"success": True, "message": f"'{su.full_name}' promoted to {role.display_name}.", "data": {"id": su.id}}


@router.put("/{user_id}", summary="Edit a system user")
def update_system_user(
    user_id: int,
    payload: SystemUserUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    su = db.get(SystemUser, user_id)
    if not su:
        raise NotFoundError("System user not found")

    changes = []
    if payload.full_name is not None:
        changes.append(f"name: {su.full_name} → {payload.full_name}")
        su.full_name = payload.full_name
    if payload.email is not None:
        existing = db.query(SystemUser).filter(SystemUser.email == payload.email.lower(), SystemUser.id != user_id).first()
        if existing:
            raise ValidationError("A system user with this email already exists.")
        su.email = payload.email.lower()
    if payload.phone is not None:
        su.phone = payload.phone
    if payload.role is not None:
        role = db.query(SystemRole).filter(SystemRole.name == payload.role.lower()).first()
        if not role:
            raise ValidationError(f"Role '{payload.role}' not found.")
        old_role = db.get(SystemRole, su.role_id)
        changes.append(f"role: {old_role.display_name if old_role else 'Unknown'} → {role.display_name}")
        su.role_id = role.id
    if payload.status is not None:
        old_status = su.status if isinstance(su.status, str) else su.status.value
        changes.append(f"status: {old_status} → {payload.status}")
        su.status = payload.status

    if changes:
        _log_admin_action(db, admin.full_name, "edit_system_user",
                          f"Updated system user: {su.full_name}",
                          details="; ".join(changes))
    db.commit()
    return {"success": True, "message": f"System user '{su.full_name}' updated.", "data": {"id": su.id}}


@router.post("/{user_id}/reset-password", summary="Reset a system user's password")
def reset_password(
    user_id: int,
    payload: ResetPasswordIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    su = db.get(SystemUser, user_id)
    if not su:
        raise NotFoundError("System user not found")

    su.password_hash = hash_password(payload.new_password)
    _log_admin_action(db, admin.full_name, "reset_password", f"Reset password for: {su.full_name}")
    db.commit()
    return {"success": True, "message": f"Password reset for '{su.full_name}'.", "data": None}


@router.delete("/{user_id}", summary="Delete a system user")
def delete_system_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    su = db.get(SystemUser, user_id)
    if not su:
        raise NotFoundError("System user not found")

    # Don't allow deleting the last super admin
    if su.role_id:
        role = db.get(SystemRole, su.role_id)
        if role and role.name == "super_admin":
            super_count = db.query(SystemUser).join(SystemRole).filter(SystemRole.name == "super_admin").count()
            if super_count <= 1:
                raise ValidationError("Cannot delete the last Super Admin.")

    name = su.full_name
    db.delete(su)
    _log_admin_action(db, admin.full_name, "delete_system_user", f"Deleted system user: {name}")
    db.commit()
    return {"success": True, "message": f"System user '{name}' deleted.", "data": None}


# ── Roles ────────────────────────────────────────────────────────────────

@router.get("/roles/list", summary="List all roles")
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    _ensure_default_roles(db)
    roles = db.query(SystemRole).order_by(SystemRole.id).all()
    return {
        "success": True,
        "message": "OK",
        "data": [
            {
                "id": r.id,
                "name": r.name,
                "display_name": r.display_name,
                "description": r.description,
                "is_system": r.is_system,
                "permission_count": len(r.permissions),
                "user_count": db.query(SystemUser).filter(SystemUser.role_id == r.id).count(),
            }
            for r in roles
        ],
    }


@router.get("/roles/{role_id}", summary="Get role details with permissions")
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    role = db.get(SystemRole, role_id)
    if not role:
        raise NotFoundError("Role not found")

    return {
        "success": True,
        "message": "OK",
        "data": {
            "id": role.id,
            "name": role.name,
            "display_name": role.display_name,
            "description": role.description,
            "is_system": role.is_system,
            "permissions": [p.code for p in role.permissions],
        },
    }


@router.post("/roles", summary="Create a custom role")
def create_role(
    payload: RoleCreateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if db.query(SystemRole).filter(SystemRole.name == payload.name.lower()).first():
        raise ValidationError("A role with this name already exists.")

    role = SystemRole(
        name=payload.name.lower(),
        display_name=payload.display_name,
        description=payload.description,
    )
    db.add(role)
    db.flush()

    for perm_code in payload.permissions:
        perm = db.query(SystemPermission).filter(SystemPermission.code == perm_code).first()
        if not perm:
            perm = SystemPermission(code=perm_code, description=perm_code.replace(".", " ").title())
            db.add(perm)
            db.flush()
        role.permissions.append(perm)

    _log_admin_action(db, admin.full_name, "create_role", f"Created role: {role.display_name}")
    db.commit()
    return {"success": True, "message": f"Role '{role.display_name}' created.", "data": {"id": role.id}}


@router.put("/roles/{role_id}", summary="Update a role")
def update_role(
    role_id: int,
    payload: RoleUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    role = db.get(SystemRole, role_id)
    if not role:
        raise NotFoundError("Role not found")
    if role.is_system:
        raise ValidationError("Cannot modify built-in system roles.")

    if payload.display_name is not None:
        role.display_name = payload.display_name
    if payload.description is not None:
        role.description = payload.description
    if payload.permissions is not None:
        role.permissions.clear()
        for perm_code in payload.permissions:
            perm = db.query(SystemPermission).filter(SystemPermission.code == perm_code).first()
            if not perm:
                perm = SystemPermission(code=perm_code, description=perm_code.replace(".", " ").title())
                db.add(perm)
                db.flush()
            role.permissions.append(perm)

    _log_admin_action(db, admin.full_name, "update_role", f"Updated role: {role.display_name}")
    db.commit()
    return {"success": True, "message": f"Role '{role.display_name}' updated.", "data": {"id": role.id}}


# ── Permissions ──────────────────────────────────────────────────────────

@router.get("/permissions/list", summary="List all permissions")
def list_permissions(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    perms = db.query(SystemPermission).order_by(SystemPermission.code).all()
    return {
        "success": True,
        "message": "OK",
        "data": [{"id": p.id, "code": p.code, "description": p.description} for p in perms],
    }


# ── Activity Log ─────────────────────────────────────────────────────────

@router.get("/activity/logs", summary="Admin activity logs")
def list_activity_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    action: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    query = db.query(AdminActivityLog)
    if action:
        query = query.filter(AdminActivityLog.action == action)

    total = query.count()
    rows = query.order_by(AdminActivityLog.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "success": True,
        "message": "OK",
        "data": {
            "items": [
                {
                    "id": log.id,
                    "user_name": log.user_name,
                    "action": log.action,
                    "details": log.details,
                    "previous_value": log.previous_value,
                    "new_value": log.new_value,
                    "created_at": log.created_at.isoformat(),
                }
                for log in rows
            ],
            "meta": _page_meta(page, per_page, total),
        },
    }
