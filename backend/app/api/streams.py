from fastapi import APIRouter, Depends
from datetime import datetime, timezone
import secrets
from pydantic import BaseModel
from sqlalchemy import select, func

from backend.app.auth.dependencies import get_current_admin
from backend.app.database import AsyncSessionLocal
from backend.app.models import Stream, StreamLink, ViewerSession
from backend.app.streaming.manager import stream_manager


router = APIRouter(
    prefix="/api/streams",
    tags=["Streams"],
)


# ------------------------------------------------------------------
# WebRTC compatibility state
# ------------------------------------------------------------------
# PostgreSQL is now the permanent source of truth.
# This dictionary is retained because the existing WebRTC code
# imports stream_state from this module.
stream_state = {
    "id": None,
    "status": "offline",
    "created_at": None,
    "started_at": None,
    "viewer_count": 0,
    "viewer_token": None,
}


def update_stream_state(
    stream: Stream,
    viewer_token: str | None = None,
    viewer_count: int = 0,
):
    """
    Keep the existing in-memory state synchronized with PostgreSQL.

    This exists for compatibility with the current WebRTC implementation.
    """

    stream_state["id"] = stream.stream_id
    stream_state["status"] = stream.status
    stream_state["created_at"] = (
        stream.created_at.isoformat()
        if stream.created_at
        else None
    )
    stream_state["started_at"] = (
        stream.started_at.isoformat()
        if stream.started_at
        else None
    )
    stream_state["viewer_count"] = viewer_count

    if viewer_token is not None:
        stream_state["viewer_token"] = viewer_token


async def get_latest_stream(session):
    """
    Get the most recently created stream.
    """

    result = await session.execute(
        select(Stream)
        .order_by(Stream.created_at.desc())
        .limit(1)
    )

    return result.scalar_one_or_none()


async def get_active_viewer_count(session, stream_id: int):
    """
    Count currently watching viewers for a stream.
    """

    result = await session.execute(
        select(func.count(ViewerSession.id))
        .where(
            ViewerSession.stream_id == stream_id,
            ViewerSession.status == "watching",
        )
    )

    return result.scalar_one()


async def get_active_stream_link(session, stream_id: int):
    """
    Get the most recently created non-revoked viewer link.
    """

    result = await session.execute(
        select(StreamLink)
        .where(
            StreamLink.stream_id == stream_id,
            StreamLink.revoked_at.is_(None),
        )
        .order_by(StreamLink.created_at.desc())
        .limit(1)
    )

    return result.scalar_one_or_none()


# ------------------------------------------------------------------
# CREATE STREAM
# ------------------------------------------------------------------

@router.post("/create")
async def create_stream(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:

        stream = Stream(
            stream_id=secrets.token_urlsafe(16),
            status="ready",
            created_at=datetime.now(timezone.utc),
            started_at=None,
            stopped_at=None,
            viewer_count=0,
        )

        session.add(stream)

        await session.flush()

        # Create the initial secure viewer link.
        viewer_token = secrets.token_urlsafe(32)

        stream_link = StreamLink(
            stream_id=stream.id,
            token=viewer_token,
            created_at=datetime.now(timezone.utc),
            expires_at=None,
            revoked_at=None,
        )

        session.add(stream_link)

        await session.commit()
        await session.refresh(stream)

        update_stream_state(
            stream,
            viewer_token=viewer_token,
            viewer_count=0,
        )

        return {
            "success": True,
            "stream": {
                "id": stream.stream_id,
                "status": stream.status,
                "created_at": stream.created_at.isoformat(),
                "started_at": None,
                "viewer_count": 0,
            },
        }


# ------------------------------------------------------------------
# START STREAM
# ------------------------------------------------------------------

@router.post("/start")
async def start_stream(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:

        stream = await get_latest_stream(session)

        if not stream:
            return {
                "success": False,
                "message": "No stream has been created.",
            }

        from backend.app.models.settings import PlatformSettings
        from backend.app.streaming.input_source import VIDEO_FILE

        settings_result = await session.execute(
            select(PlatformSettings)
            .order_by(PlatformSettings.id.asc())
            .limit(1)
        )
        platform_settings = settings_result.scalar_one_or_none()

        if (
            platform_settings
            and getattr(platform_settings, "use_capture_card", False)
        ):
            input_source = (
                platform_settings.capture_device_name
                or "USB Video"
            )
        else:
            input_source = VIDEO_FILE

        try:
            quality = (
                getattr(platform_settings, "stream_quality", None)
                if platform_settings
                else None
            ) or "720p"
            quality_map = {
                "480p": (854, 480),
                "720p": (1280, 720),
                "1080p": (1920, 1080),
            }
            w, h = quality_map.get(str(quality).lower(), (1280, 720))
            stream_manager.start(
                input_source=input_source,
                width=w,
                height=h,
            )
        except Exception as error:
            return {
                "success": False,
                "message": f"Unable to start stream source: {error}",
            }

        stream.status = "live"
        stream.started_at = datetime.now(timezone.utc)
        stream.stopped_at = None

        viewer_count = await get_active_viewer_count(
            session,
            stream.id,
        )

        link = await get_active_stream_link(
            session,
            stream.id,
        )

        viewer_token = link.token if link else None

        from backend.app.models.security_log import SecurityLog
        from backend.app.models.settings import PlatformSettings
        from backend.app.recordings.service import recording_service

        session.add(
            SecurityLog(
                event="stream_start",
                actor=admin,
                detail=f"Stream {stream.stream_id} went live",
            )
        )

        settings_result = await session.execute(
            select(PlatformSettings)
            .order_by(PlatformSettings.id.asc())
            .limit(1)
        )
        platform_settings = settings_result.scalar_one_or_none()

        auto_record_started = False
        if (
            platform_settings
            and platform_settings.auto_record_on_live
            and not recording_service.is_recording
            and stream_manager.is_running
        ):
            try:
                source_track = stream_manager.subscribe_recording()
                recording_service.start(
                    stream_id=stream.id,
                    source_track=source_track,
                    admin_id=None,
                )
                auto_record_started = True
                session.add(
                    SecurityLog(
                        event="recording",
                        actor=admin,
                        detail="Auto-record started on live",
                    )
                )
            except Exception as auto_err:
                print("DroneStream: auto-record failed:", auto_err)

        await session.commit()
        await session.refresh(stream)

        update_stream_state(
            stream,
            viewer_token=viewer_token,
            viewer_count=viewer_count,
        )

        from backend.app.recordings.service import recording_service

        recording_payload = {"active": False}
        if recording_service.is_recording:
            active = getattr(recording_service, "active_recording", None) or {}
            started = active.get("started_at")
            recording_payload = {
                "active": True,
                "file_name": active.get("file_name"),
                "started_at": (
                    started.isoformat()
                    if started is not None and hasattr(started, "isoformat")
                    else None
                ),
            }

        return {
            "success": True,
            "stream": {
                "id": stream.stream_id,
                "status": stream.status,
                "created_at": stream.created_at.isoformat(),
                "started_at": (
                    stream.started_at.isoformat()
                    if stream.started_at
                    else None
                ),
                "viewer_count": viewer_count,
            },
            "recording": recording_payload,
        }
# ------------------------------------------------------------------
# STOP STREAM
# ------------------------------------------------------------------

@router.post("/stop")
async def stop_stream(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:

        stream = await get_latest_stream(session)

        if not stream:
            return {
                "success": False,
                "message": "No stream exists.",
            }

                # Stop any active recording before tearing down the source
        from backend.app.recordings.service import recording_service
        from backend.app.models import Recording
        from backend.app.models.security_log import SecurityLog

        if recording_service.is_recording:
            try:
                recording = await recording_service.stop()

                recording_record = Recording(
                    stream_id=recording["stream_id"],
                    started_at=recording["started_at"],
                    ended_at=recording["ended_at"],
                    duration_seconds=recording["duration_seconds"],
                    file_path=recording["file_path"],
                    file_name=recording["file_name"],
                    file_size_bytes=recording["file_size_bytes"],
                    status="completed",
                    created_by_admin_id=recording.get("admin_id"),
                    created_by_viewer_session_id=recording.get("viewer_session_id"),
                )
                session.add(recording_record)

                session.add(
                    SecurityLog(
                        event="recording",
                        actor=admin,
                        detail=(
                            f"Recording auto-stopped on stream stop "
                            f"({recording['file_name']})"
                        ),
                    )
                )
            except Exception as stop_err:
                print("DroneStream: failed to stop recording on stream stop:", stop_err)

        await stream_manager.stop()

        try:
            from backend.app.recordings.service import recording_service
            if recording_service.is_recording:
                await recording_service.stop()
        except Exception as stop_rec_err:
            print("DroneStream: stop recording on stream stop:", stop_rec_err)

        stream.status = "offline"
        stream.stopped_at = datetime.now(timezone.utc)

        try:
            from backend.app.api.viewer import _kicked_ips
            _kicked_ips.pop(stream.id, None)
        except Exception:
            pass

        from backend.app.models import ViewerEvent

        vs_result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.stream_id == stream.id,
                ViewerSession.status == "watching",
            )
        )
        for vs in vs_result.scalars().all():
            vs.status = "stream_ended"
            vs.disconnected_at = stream.stopped_at
            session.add(
                ViewerEvent(
                    session_id=vs.id,
                    event_type="stream_ended",
                    created_at=stream.stopped_at,
                )
            )

        viewer_count = await get_active_viewer_count(
            session,
            stream.id,
        )

        link = await get_active_stream_link(
            session,
            stream.id,
        )

        viewer_token = link.token if link else None

        from backend.app.models.security_log import SecurityLog

        session.add(
            SecurityLog(
                event="stream_stop",
                actor=admin,
                detail=f"Stream {stream.stream_id} stopped",
            )
        )

        await session.commit()
        await session.refresh(stream)

        update_stream_state(
            stream,
            viewer_token=viewer_token,
            viewer_count=viewer_count,
        )

        from backend.app.recordings.service import recording_service

        recording_payload = {"active": False}
        if recording_service.is_recording:
            active = getattr(recording_service, "active_recording", None) or {}
            started = active.get("started_at")
            recording_payload = {
                "active": True,
                "file_name": active.get("file_name"),
                "started_at": (
                    started.isoformat()
                    if started is not None and hasattr(started, "isoformat")
                    else None
                ),
            }

        return {
            "success": True,
            "stream": {
                "id": stream.stream_id,
                "status": stream.status,
                "created_at": stream.created_at.isoformat(),
                "started_at": (
                    stream.started_at.isoformat()
                    if stream.started_at
                    else None
                ),
                "viewer_count": viewer_count,
            },
            "recording": recording_payload,
        }


# ------------------------------------------------------------------
# STREAM STATUS
# ------------------------------------------------------------------

@router.get("/status")
async def stream_status(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:

        stream = await get_latest_stream(session)

        if not stream:
            stream_state["id"] = None
            stream_state["status"] = "offline"
            stream_state["created_at"] = None
            stream_state["started_at"] = None
            stream_state["viewer_count"] = 0
            stream_state["viewer_token"] = None

            return {
                "success": True,
                "stream": {
                    "id": None,
                    "status": "offline",
                    "created_at": None,
                    "started_at": None,
                    "viewer_count": 0,
                },
                "recording": {"active": False},
            }

        viewer_count = await get_active_viewer_count(
            session,
            stream.id,
        )

        link = await get_active_stream_link(
            session,
            stream.id,
        )

        viewer_token = link.token if link else None

        update_stream_state(
            stream,
            viewer_token=viewer_token,
            viewer_count=viewer_count,
        )

        from backend.app.recordings.service import recording_service

        recording_payload = {"active": False}
        if recording_service.is_recording:
            active = getattr(recording_service, "active_recording", None) or {}
            started = active.get("started_at")
            recording_payload = {
                "active": True,
                "file_name": active.get("file_name"),
                "started_at": (
                    started.isoformat()
                    if started is not None and hasattr(started, "isoformat")
                    else None
                ),
            }

        return {
            "success": True,
            "stream": {
                "id": stream.stream_id,
                "status": stream.status,
                "created_at": stream.created_at.isoformat(),
                "started_at": (
                    stream.started_at.isoformat()
                    if stream.started_at
                    else None
                ),
                "viewer_count": viewer_count,
            },
            "recording": recording_payload,
        }


# ------------------------------------------------------------------
# GENERATE VIEWER LINK
# ------------------------------------------------------------------

class ViewerLinkRequest(BaseModel):
    expires_in_minutes: int | None = None  # None = never expires
    expires_in_hours: int | None = None  # legacy alias
    password: str | None = None  # None / empty = no password


@router.post("/viewer-link")
async def generate_viewer_link(
    admin: str = Depends(get_current_admin),
    body: ViewerLinkRequest | None = None,
):
    async with AsyncSessionLocal() as session:

        stream = await get_latest_stream(session)

        if not stream:
            return {
                "success": False,
                "message": "Create a stream first.",
            }

        result = await session.execute(
            select(StreamLink)
            .where(
                StreamLink.stream_id == stream.id,
                StreamLink.revoked_at.is_(None),
            )
        )
        existing_links = result.scalars().all()
        now = datetime.now(timezone.utc)

        for link in existing_links:
            link.revoked_at = now
            

        viewer_token = secrets.token_urlsafe(32)

        expires_at = None
        minutes = None
        if body:
            if body.expires_in_minutes is not None and body.expires_in_minutes > 0:
                minutes = int(body.expires_in_minutes)
            elif body.expires_in_hours is not None and body.expires_in_hours > 0:
                minutes = int(body.expires_in_hours) * 60

        if minutes is not None and minutes > 0:
            from datetime import timedelta
            expires_at = now + timedelta(minutes=minutes)

        password_hash = None
        raw_password = (body.password if body else None) or None
        if raw_password and str(raw_password).strip():
            import hashlib
            password_hash = hashlib.sha256(
                str(raw_password).strip().encode("utf-8")
            ).hexdigest()

        new_link = StreamLink(
            stream_id=stream.id,
            token=viewer_token,
            created_at=now,
            expires_at=expires_at,
            revoked_at=None,
            password_hash=password_hash,
        )
        session.add(new_link)

        # When regenerating, end sessions on the links we just revoked
        from backend.app.models import ViewerEvent

        for link in existing_links:
            vs_result = await session.execute(
                select(ViewerSession).where(
                    ViewerSession.stream_link_id == link.id,
                    ViewerSession.status == "watching",
                )
            )
            for vs in vs_result.scalars().all():
                vs.status = "revoked"
                vs.disconnected_at = now
                session.add(
                    ViewerEvent(
                        session_id=vs.id,
                        event_type="link_revoked",
                        created_at=now,
                    )
                )

        from backend.app.models.security_log import SecurityLog
        session.add(
            SecurityLog(
                event="link_generate",
                actor=admin,
                detail=(
                    f"Viewer link generated"
                    + (f", expires in {minutes} min" if minutes else ", no expiry")
                    + (", password protected" if password_hash else ", no password")
                ),
            )
        )

        viewer_count = await get_active_viewer_count(session, stream.id)
        await session.commit()

        update_stream_state(
            stream,
            viewer_token=viewer_token,
            viewer_count=viewer_count,
        )

        return {
            "success": True,
            "stream_id": stream.stream_id,
            "viewer_token": viewer_token,
            "viewer_path": f"/watch/{viewer_token}",
            "expires_at": expires_at.isoformat() if expires_at else None,
            "password_protected": bool(password_hash),
        }
        
@router.get("/preview-token")
async def get_preview_token(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        stream = await get_latest_stream(session)

        if not stream:
            return {
                "success": False,
                "message": "Create a stream first.",
            }

        link = await get_active_stream_link(
            session,
            stream.id,
        )

        if not link:
            return {
                "success": False,
                "message": "No active viewer access token exists.",
            }

        if link.expires_at:
            now = datetime.now(timezone.utc)
            if now >= link.expires_at:
                return {
                    "success": False,
                    "message": "The active viewer access token has expired.",
                }

        return {
            "success": True,
            "stream_id": stream.stream_id,
            "viewer_token": link.token,
            "stream_status": stream.status,
        }        
        
@router.post("/viewer-link/revoke")
async def revoke_viewer_link(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        stream = await get_latest_stream(session)
        if not stream:
            return {
                "success": False,
                "message": "No stream exists.",
            }

        result = await session.execute(
            select(StreamLink)
            .where(
                StreamLink.stream_id == stream.id,
                StreamLink.revoked_at.is_(None),
            )
        )
        links = result.scalars().all()
        now = datetime.now(timezone.utc)
        for link in links:
            link.revoked_at = now

        from backend.app.models import ViewerEvent

        for link in links:
            vs_result = await session.execute(
                select(ViewerSession).where(
                    ViewerSession.stream_link_id == link.id,
                    ViewerSession.status == "watching",
                )
            )
            for vs in vs_result.scalars().all():
                vs.status = "revoked"
                vs.disconnected_at = now
                session.add(
                    ViewerEvent(
                        session_id=vs.id,
                        event_type="link_revoked",
                        created_at=now,
                    )
                )

        from backend.app.models.security_log import SecurityLog
        session.add(
            SecurityLog(
                event="link_revoke",
                actor=admin,
                detail=f"All viewer links revoked for stream {stream.stream_id}",
            )
        )

        await session.commit()

        stream_state["viewer_token"] = None

        return {
            "success": True,
            "message": "Viewer link revoked. Existing links no longer work.",
        }        