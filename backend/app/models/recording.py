from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base

class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    stream_id: Mapped[int] = mapped_column(
        ForeignKey(
            "streams.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    file_path: Mapped[str] = mapped_column(
        nullable=False,
    )

    file_name: Mapped[str] = mapped_column(
        nullable=False,
    )

    file_size_bytes: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        default="recording",
        nullable=False,
    )

    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "admins.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    
    
    created_by_viewer_session_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "viewer_sessions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )


class RecordingPermission(Base):
    __tablename__ = "recording_permissions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    viewer_session_id: Mapped[int] = mapped_column(
        ForeignKey(
            "viewer_sessions.id",
            ondelete="CASCADE",
        ),
        unique=True,
        nullable=False,
        index=True,
    )

    allowed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    granted_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "admins.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )