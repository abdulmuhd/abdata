"""Add API Manager and System Users tables

Revision ID: c1d2e3f4a5b6
Revises: b4e5f6a7c8d9
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b4e5f6a7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # API Providers
    op.create_table(
        "api_providers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
        sa.Column("supports_balance_check", sa.Boolean, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # API Provider Credentials
    op.create_table(
        "api_provider_credentials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider_id", sa.Integer, sa.ForeignKey("api_providers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("credential_key", sa.String(80), nullable=False),
        sa.Column("credential_value", sa.Text, nullable=False),
        sa.Column("is_sensitive", sa.Boolean, server_default=sa.text("1")),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "credential_key", name="uq_provider_credential_key"),
    )

    # API Provider Endpoints
    op.create_table(
        "api_provider_endpoints",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider_id", sa.Integer, sa.ForeignKey("api_providers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("method", sa.String(10), server_default="POST"),
        sa.Column("request_mapping", sa.JSON, nullable=True),
        sa.Column("response_mapping", sa.JSON, nullable=True),
        sa.Column("headers", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "operation", name="uq_provider_operation"),
    )

    # API Provider Services
    op.create_table(
        "api_provider_services",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider_id", sa.Integer, sa.ForeignKey("api_providers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("service_type", sa.String(50), nullable=False, index=True),
        sa.Column("is_enabled", sa.Boolean, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "service_type", name="uq_provider_service_type"),
    )

    # API Provider Routing
    op.create_table(
        "api_provider_routing",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("service_type", sa.String(50), nullable=False, index=True),
        sa.Column("provider_id", sa.Integer, sa.ForeignKey("api_providers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("priority", sa.Integer, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("service_type", "priority", name="uq_service_priority"),
    )

    # API Request Logs
    op.create_table(
        "api_request_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider_id", sa.Integer, sa.ForeignKey("api_providers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("service_type", sa.String(50), nullable=True, index=True),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("reference", sa.String(64), nullable=True, index=True),
        sa.Column("provider_reference", sa.String(120), nullable=True),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("http_method", sa.String(10), nullable=False),
        sa.Column("request_payload", sa.JSON, server_default=sa.text("'{}'")),
        sa.Column("response_payload", sa.JSON, server_default=sa.text("'{}'")),
        sa.Column("http_status_code", sa.Integer, nullable=True),
        sa.Column("success", sa.Boolean, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # System Roles
    op.create_table(
        "system_roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_system", sa.Boolean, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # System Permissions
    op.create_table(
        "system_permissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(80), unique=True, nullable=False, index=True),
        sa.Column("description", sa.String(200), nullable=True),
    )

    # Role-Permissions junction
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer, sa.ForeignKey("system_roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Integer, sa.ForeignKey("system_permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    # System Users
    op.create_table(
        "system_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("username", sa.String(80), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("system_roles.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Admin Activity Logs
    op.create_table(
        "admin_activity_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("system_user_id", sa.Integer, sa.ForeignKey("system_users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("user_name", sa.String(120), nullable=False),
        sa.Column("action", sa.String(80), nullable=False, index=True),
        sa.Column("details", sa.String(500), nullable=True),
        sa.Column("previous_value", sa.String(500), nullable=True),
        sa.Column("new_value", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("admin_activity_logs")
    op.drop_table("system_users")
    op.drop_table("role_permissions")
    op.drop_table("system_permissions")
    op.drop_table("system_roles")
    op.drop_table("api_request_logs")
    op.drop_table("api_provider_routing")
    op.drop_table("api_provider_services")
    op.drop_table("api_provider_endpoints")
    op.drop_table("api_provider_credentials")
    op.drop_table("api_providers")
