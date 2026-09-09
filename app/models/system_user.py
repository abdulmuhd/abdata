"""System user models — staff accounts for admin dashboard access with RBAC."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Table, Column, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class SystemUserRoleEnum(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"


class SystemUserStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


# Many-to-many: roles <-> permissions
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("system_roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("system_permissions.id", ondelete="CASCADE"), primary_key=True),
)


class SystemUser(Base):
    """Staff member authorized to access the admin dashboard."""

    __tablename__ = "system_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))

    role_id: Mapped[int] = mapped_column(ForeignKey("system_roles.id", ondelete="RESTRICT"), index=True)
    status: Mapped[SystemUserStatus] = mapped_column(
        String(20), default=SystemUserStatus.ACTIVE
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    role = relationship("SystemRole", back_populates="users")


class SystemRole(Base):
    """A named role with assigned permissions."""

    __tablename__ = "system_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # built-in roles can't be deleted

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    users = relationship("SystemUser", back_populates="role")
    permissions = relationship("SystemPermission", secondary=role_permissions, back_populates="roles")


class SystemPermission(Base):
    """A single permission string (e.g. 'users.view', 'providers.edit')."""

    __tablename__ = "system_permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    roles = relationship("SystemRole", secondary=role_permissions, back_populates="permissions")


class AdminActivityLog(Base):
    """Tracks important actions performed by system users."""

    __tablename__ = "admin_activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_name: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict | None] = mapped_column(String(500), nullable=True)
    previous_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
