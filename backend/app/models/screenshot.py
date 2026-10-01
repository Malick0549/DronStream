from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class Screenshot(Base):
    __tablename__ = "screenshots"

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

    file_path: Mapped[str] = mapped_column(
        nullable=False,
    )

    file_name: Mapped[str] = mapped_column(
        nullable=False,
    )

    file_size_bytes: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
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
    