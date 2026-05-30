from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.connection import Base

class User(Base):
    """
    Core Identity Entity.
    Stores security credentials and account state inside PostgreSQL.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ORM Relationships for easy querying
    memberships: Mapped[list["GroupMember"]] = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")


class GroupChannel(Base):
    """
    Group Metadata Entity.
    Defines the structural room configuration (capped at 100 members max).
    """
    __tablename__ = "group_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ORM Relationships
    members: Mapped[list["GroupMember"]] = relationship("GroupMember", back_populates="channel", cascade="all, delete-orphan")


class GroupMember(Base):
    """
    Many-to-Many Bridge Table linking Users to Channels.
    Enforces strict access control lists before a user can connect to a WebSocket.
    """
    __tablename__ = "group_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("group_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Multi-Column unique constraint to prevent a user from joining the same group twice
    __table_args__ = (
        UniqueConstraint("user_id", "channel_id", name="uq_user_channel"),
    )

    # Back-populating targets
    user: Mapped["User"] = relationship("User", back_populates="memberships")
    channel: Mapped["GroupChannel"] = relationship("GroupChannel", back_populates="members")