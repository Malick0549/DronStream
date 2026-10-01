from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    default_viewer_can_record: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    default_viewer_can_screenshot: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    require_viewer_permission: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    auto_record_on_live: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    max_viewer_sessions: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False
    )
    session_timeout_minutes: Mapped[int] = mapped_column(
        Integer, default=120, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    
    use_capture_card: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    capture_device_name: Mapped[str] = mapped_column(
        String(200), default="USB Video", nullable=False
    )
    
    stream_quality: Mapped[str] = mapped_column(
        String(20), default="720p", nullable=False
    )