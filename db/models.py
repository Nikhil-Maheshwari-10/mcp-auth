"""
SQLAlchemy ORM models for the workspace agent.

Tables:
  User          — one row per authenticated human (login identity, keyed by Google sub)
  Workspace     — optional isolated environment with its own OAuth tokens and ADK chat history
  WorkspaceUser — links User identities to Workspaces they own/can access
  OAuthToken    — OAuth tokens (scoped to user_id, or optionally to workspace_id if in a workspace)
  Session       — browser session (session_id → user_id + optional active_workspace_id)
  AuditLog      — tool execution log (scoped to user_id + optional workspace_id)
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """Login identity — one row per human user (keyed by stable Google sub)."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    google_sub: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    workspaces: Mapped[list["WorkspaceUser"]] = relationship(
        "WorkspaceUser", back_populates="user", cascade="all, delete-orphan"
    )
    tokens: Mapped[list["OAuthToken"]] = relationship(
        "OAuthToken", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


class Workspace(Base):
    """Optional isolated environment created explicitly by a user."""
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    tokens: Mapped[list["OAuthToken"]] = relationship(
        "OAuthToken", back_populates="workspace", cascade="all, delete-orphan"
    )
    members: Mapped[list["WorkspaceUser"]] = relationship(
        "WorkspaceUser", back_populates="workspace", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="workspace", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Workspace id={self.id} name={self.name}>"


class WorkspaceUser(Base):
    """Many-to-many: User login identities ↔ Workspaces (with role)."""
    __tablename__ = "workspace_users"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="owner")
    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="workspaces")

    def __repr__(self) -> str:
        return f"<WorkspaceUser workspace={self.workspace_id} user={self.user_id} role={self.role}>"


class OAuthToken(Base):
    """
    OAuth tokens.
    Always associated with a user_id.
    Optionally associated with a workspace_id if connected inside a custom workspace.
    """
    __tablename__ = "oauth_tokens"

    __table_args__ = (
        CheckConstraint("provider IN ('google', 'github')", name="ck_oauth_tokens_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_account_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("TRUE")
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_username: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    avatar_url: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="tokens")
    workspace: Mapped["Workspace | None"] = relationship("Workspace", back_populates="tokens")

    def __repr__(self) -> str:
        return f"<OAuthToken user={self.user_id} workspace={self.workspace_id} provider={self.provider}>"


class Session(Base):
    """Browser session: session_id cookie → user_id + optional active_workspace_id."""
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    active_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Session id={self.id} user={self.user_id} workspace={self.active_workspace_id}>"


class AuditLog(Base):
    """Tool execution log, scoped to user_id and optional workspace_id."""
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    called_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    workspace: Mapped["Workspace | None"] = relationship("Workspace", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog tool={self.tool_name} user={self.user_id} status={self.status}>"
