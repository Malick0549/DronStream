from datetime import datetime, timezone
from backend.app.recordings.service import recording_service
from backend.app.screenshots.service import (
    screenshot_service,
)
from pydantic import BaseModel
from backend.app.models import PlatformSettings, SecurityLog
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from pathlib import Path
from fastapi.responses import FileResponse
from backend.app.auth.dependencies import get_current_admin
from backend.app.database import AsyncSessionLocal
from backend.app.models import (
    Admin,
    Stream,
    ViewerSession,
    Recording,
    RecordingPermission,
    Screenshot,
    ScreenshotPermission,
)
from backend.app.recordings.permissions import (
    grant_recording_permission,
    revoke_recording_permission,
)
from backend.app.screenshots.permissions import (
    grant_screenshot_permission,
    revoke_screenshot_permission,
)
from backend.app.streaming.manager import stream_manager


router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
)


class SettingsUpdate(BaseModel):
    default_viewer_can_record: bool | None = None
    default_viewer_can_screenshot: bool | None = None
    require_viewer_permission: bool | None = None
    auto_record_on_live: bool | None = None
    max_viewer_sessions: int | None = None
    session_timeout_minutes: int | None = None
    use_capture_card: bool | None = None
    capture_device_name: str | None = None
    stream_quality: str | None = None


def settings_to_dict(row: PlatformSettings) -> dict:
    return {
        "default_viewer_can_record": row.default_viewer_can_record,
        "default_viewer_can_screenshot": row.default_viewer_can_screenshot,
        "require_viewer_permission": row.require_viewer_permission,
        "auto_record_on_live": row.auto_record_on_live,
        "max_viewer_sessions": row.max_viewer_sessions,
        "session_timeout_minutes": row.session_timeout_minutes,
        "use_capture_card": row.use_capture_card,
        "capture_device_name": row.capture_device_name,
        "stream_quality": getattr(row, "stream_quality", "720p") or "720p",
    }


async def get_or_create_settings(session) -> PlatformSettings:
    result = await session.execute(
        select(PlatformSettings).order_by(PlatformSettings.id.asc()).limit(1)
    )
    row = result.scalar_one_or_none()
    if row:
        return row

    row = PlatformSettings()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


# ------------------------------------------------------------------
# ADMIN DASHBOARD
# ------------------------------------------------------------------

@router.get("/dashboard")
async def admin_dashboard(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Stream)
            .order_by(Stream.created_at.desc())
            .limit(1)
        )

        stream = result.scalar_one_or_none()

        if not stream:
            return {
                "success": True,
                "stream": None,
                "source": {
                    "running": False,
                    "type": "none",
                },
                "webrtc": {
                    "active_connections": 0,
                },
            }

        viewer_result = await session.execute(
            select(func.count(ViewerSession.id))
            .where(
                ViewerSession.stream_id == stream.id,
                ViewerSession.status == "watching",
            )
        )

        viewer_count = viewer_result.scalar_one()

        uptime_seconds = 0

        if stream.started_at and stream.status == "live":

            started = stream.started_at

            if started.tzinfo is None:
                started = started.replace(
                    tzinfo=timezone.utc
                )

            uptime_seconds = max(
                0,
                int(
                    (
                        datetime.now(timezone.utc)
                        - started
                    ).total_seconds()
                ),
            )

        settings_result = await session.execute(
            select(PlatformSettings)
            .order_by(PlatformSettings.id.asc())
            .limit(1)
        )
        platform_settings = settings_result.scalar_one_or_none()
        quality = (
            getattr(platform_settings, "stream_quality", None) or "720p"
        )
        quality_map = {
            "480p": "854 × 480",
            "720p": "1280 × 720",
            "1080p": "1920 × 1080",
        }
        resolution_label = quality_map.get(
            str(quality).lower(), "1280 × 720"
        )

        return {
            "success": True,

            "stream": {
                "id": stream.stream_id,
                "status": stream.status,
                "created_at": (
                    stream.created_at.isoformat()
                    if stream.created_at
                    else None
                ),
                "started_at": (
                    stream.started_at.isoformat()
                    if stream.started_at
                    else None
                ),
                "stopped_at": (
                    stream.stopped_at.isoformat()
                    if stream.stopped_at
                    else None
                ),
                "viewer_count": viewer_count,
                "uptime_seconds": uptime_seconds,
            },

            "source": {
                "running": stream_manager.is_running,
                "type": (
                    "ffmpeg"
                    if stream_manager.is_running
                    else "none"
                ),
                "resolution": resolution_label,
            },

            "webrtc": {
                "active_connections": len(
                    stream_manager.peer_connections
                ),
            },
        }


# ------------------------------------------------------------------
# STREAM HEALTH
# ------------------------------------------------------------------

@router.get("/stream-health")
async def stream_health(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Stream)
            .order_by(Stream.created_at.desc())
            .limit(1)
        )

        stream = result.scalar_one_or_none()

        if not stream:

            return {
                "success": True,
                "health": {
                    "status": "offline",
                    "stream_exists": False,
                    "source_running": False,
                    "webrtc_connections": 0,
                    "viewer_count": 0,
                },
            }

        viewer_result = await session.execute(
            select(func.count(ViewerSession.id))
            .where(
                ViewerSession.stream_id == stream.id,
                ViewerSession.status == "watching",
            )
        )

        viewer_count = viewer_result.scalar_one()

        source_running = stream_manager.is_running

        active_connections = len(
            stream_manager.peer_connections
        )

        if stream.status == "live" and source_running:

            health_status = "healthy"

        elif stream.status == "live" and not source_running:

            health_status = "degraded"

        else:

            health_status = "offline"
            
        from backend.app.models.settings import PlatformSettings

        settings_result = await session.execute(
            select(PlatformSettings)
            .order_by(PlatformSettings.id.asc())
            .limit(1)
        )
        platform_settings = settings_result.scalar_one_or_none()
        quality = (
            getattr(platform_settings, "stream_quality", None) or "720p"
        )
        quality_map = {
            "480p": "854 × 480",
            "720p": "1280 × 720",
            "1080p": "1920 × 1080",
        }
        resolution_label = quality_map.get(
            str(quality).lower(), "1280 × 720"
        )

        return {
            "success": True,

            "health": {
                "status": health_status,

                "stream_exists": True,

                "stream_status": stream.status,

                "source_running": source_running,

                "source_type": (
                    "ffmpeg"
                    if source_running
                    else "none"
                ),

                "webrtc_connections": active_connections,

                "viewer_count": viewer_count,

                "resolution": (
                    "1280x720"
                    if source_running
                    else None
                ),

                "fps": (
                    30
                    if source_running
                    else None
                ),
            },
        }


# ------------------------------------------------------------------
# STREAM STATISTICS
# ------------------------------------------------------------------

@router.get("/stream-stats")
async def stream_stats(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Stream)
            .order_by(Stream.created_at.desc())
            .limit(1)
        )

        stream = result.scalar_one_or_none()

        if not stream:

            return {
                "success": True,
                "stats": {
                    "stream_id": None,
                    "status": "offline",
                    "viewer_count": 0,
                    "webrtc_connections": 0,
                    "uptime_seconds": 0,
                },
            }

        viewer_result = await session.execute(
            select(func.count(ViewerSession.id))
            .where(
                ViewerSession.stream_id == stream.id,
                ViewerSession.status == "watching",
            )
        )

        viewer_count = viewer_result.scalar_one()

        uptime_seconds = 0

        if stream.started_at and stream.status == "live":

            started = stream.started_at

            if started.tzinfo is None:
                started = started.replace(
                    tzinfo=timezone.utc
                )

            uptime_seconds = max(
                0,
                int(
                    (
                        datetime.now(timezone.utc)
                        - started
                    ).total_seconds()
                ),
            )

        return {
            "success": True,

            "stats": {
                "stream_id": stream.stream_id,
                "status": stream.status,
                "viewer_count": viewer_count,
                "webrtc_connections": len(
                    stream_manager.peer_connections
                ),
                "uptime_seconds": uptime_seconds,
                "resolution": (
                    "1280x720"
                    if stream_manager.is_running
                    else None
                ),
                "fps": (
                    30
                    if stream_manager.is_running
                    else None
                ),
            },
        }
        
# ------------------------------------------------------------------
# RECORDING PERMISSIONS
# ------------------------------------------------------------------

@router.get("/recording-permissions")
async def get_recording_permissions(
    admin: str = Depends(get_current_admin),
):
    """
    Return the current viewers and their recording permissions.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(
                ViewerSession,
                RecordingPermission,
            )
            .outerjoin(
                RecordingPermission,
                RecordingPermission.viewer_session_id
                == ViewerSession.id,
            )
            .where(
                ViewerSession.status == "watching"
            )
            .order_by(
                ViewerSession.connected_at.desc()
            )
        )

        rows = result.all()

        viewers = []

        for viewer_session, permission in rows:

            viewers.append(
                {
                    "viewer_session_id": viewer_session.id,
                    "session_id": viewer_session.session_id,
                    "stream_id": viewer_session.stream_id,
                    "connected_at": (
                        viewer_session.connected_at.isoformat()
                        if viewer_session.connected_at
                        else None
                    ),
                    "status": viewer_session.status,
                    "ip_address": viewer_session.ip_address,
                    "user_agent": viewer_session.user_agent,
                    "recording_allowed": (
                        permission.allowed
                        if permission
                        else False
                    ),
                    "granted_at": (
                        permission.granted_at.isoformat()
                        if permission
                        and permission.granted_at
                        else None
                    ),
                    "revoked_at": (
                        permission.revoked_at.isoformat()
                        if permission
                        and permission.revoked_at
                        else None
                    ),
                }
            )

        return {
            "success": True,
            "viewers": viewers,
            "count": len(viewers),
        }
@router.post("/recording-permissions/{viewer_session_id}/grant")
async def grant_viewer_recording_permission(
    viewer_session_id: int,
    admin: str = Depends(get_current_admin),
):
    """
    Grant recording permission to one viewer session.
    """

    async with AsyncSessionLocal() as session:

        admin_result = await session.execute(
            select(Admin).where(
                Admin.username == admin
            )
        )

        admin_record = admin_result.scalar_one_or_none()

        if admin_record is None:
            return {
                "success": False,
                "message": "Administrator account not found.",
            }

        viewer_result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.id == viewer_session_id
            )
        )

        viewer = viewer_result.scalar_one_or_none()

        if viewer is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        if viewer.status != "watching":
            return {
                "success": False,
                "message": "Viewer is no longer watching.",
            }

        permission = await grant_recording_permission(
            session,
            viewer_session_id,
            admin_record.id,
        )

        session.add(
            SecurityLog(
                event="permission_grant",
                actor=admin,
                detail=(
                    f"Recording permission granted to "
                    f"viewer session {viewer_session_id}"
                ),
            )
        )
        await session.commit()

        return {
            "success": True,
            "message": "Recording permission granted.",
            "permission": {
                "viewer_session_id": permission.viewer_session_id,
                "allowed": permission.allowed,
                "granted_at": (
                    permission.granted_at.isoformat()
                    if permission.granted_at
                    else None
                ),
                "granted_by_admin_id": (
                    permission.granted_by_admin_id
                ),
            },
        }
        
@router.post("/recording-permissions/{viewer_session_id}/revoke")
async def revoke_viewer_recording_permission(
    viewer_session_id: int,
    admin: str = Depends(get_current_admin),
):
    """
    Revoke recording permission from one viewer session.
    """

    async with AsyncSessionLocal() as session:

        viewer_result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.id == viewer_session_id
            )
        )

        viewer = viewer_result.scalar_one_or_none()

        if viewer is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        permission = await revoke_recording_permission(
            session,
            viewer_session_id,
        )
        
        session.add(
            SecurityLog(
                event="permission_revoke",
                actor=admin,
                detail=(
                    f"Recording permission revoked for "
                    f"viewer session {viewer_session_id}"
                ),
            )
        )
        await session.commit()

        if permission is None:
            return {
                "success": True,
                "message": "Viewer did not have recording permission.",
                "permission": {
                    "viewer_session_id": viewer_session_id,
                    "allowed": False,
                },
            }

        return {
            "success": True,
            "message": "Recording permission revoked.",
            "permission": {
                "viewer_session_id": permission.viewer_session_id,
                "allowed": permission.allowed,
                "revoked_at": (
                    permission.revoked_at.isoformat()
                    if permission.revoked_at
                    else None
                ),
            },
        }
        
# ------------------------------------------------------------------
# SCREENSHOT PERMISSIONS
# ------------------------------------------------------------------

@router.get("/screenshot-permissions")
async def get_screenshot_permissions(
    admin: str = Depends(get_current_admin),
):
    """
    Return the current viewers and their screenshot permissions.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(
                ViewerSession,
                ScreenshotPermission,
            )
            .outerjoin(
                ScreenshotPermission,
                ScreenshotPermission.viewer_session_id
                == ViewerSession.id,
            )
            .where(
                ViewerSession.status == "watching"
            )
            .order_by(
                ViewerSession.connected_at.desc()
            )
        )

        rows = result.all()

        viewers = []

        for viewer_session, permission in rows:

            viewers.append(
                {
                    "viewer_session_id": viewer_session.id,
                    "session_id": viewer_session.session_id,
                    "stream_id": viewer_session.stream_id,
                    "connected_at": (
                        viewer_session.connected_at.isoformat()
                        if viewer_session.connected_at
                        else None
                    ),
                    "status": viewer_session.status,
                    "ip_address": viewer_session.ip_address,
                    "user_agent": viewer_session.user_agent,
                    "screenshot_allowed": (
                        permission.allowed
                        if permission
                        else False
                    ),
                    "granted_at": (
                        permission.granted_at.isoformat()
                        if permission
                        and permission.granted_at
                        else None
                    ),
                    "revoked_at": (
                        permission.revoked_at.isoformat()
                        if permission
                        and permission.revoked_at
                        else None
                    ),
                }
            )

        return {
            "success": True,
            "viewers": viewers,
            "count": len(viewers),
        }


@router.post(
    "/screenshot-permissions/{viewer_session_id}/grant"
)
async def grant_viewer_screenshot_permission(
    viewer_session_id: int,
    admin: str = Depends(get_current_admin),
):
    """
    Grant screenshot permission to one viewer session.
    """

    async with AsyncSessionLocal() as session:

        admin_result = await session.execute(
            select(Admin).where(
                Admin.username == admin
            )
        )

        admin_record = (
            admin_result.scalar_one_or_none()
        )

        if admin_record is None:
            return {
                "success": False,
                "message": "Administrator account not found.",
            }

        viewer_result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.id == viewer_session_id
            )
        )

        viewer = (
            viewer_result.scalar_one_or_none()
        )

        if viewer is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        if viewer.status != "watching":
            return {
                "success": False,
                "message": "Viewer is no longer watching.",
            }

        permission = await grant_screenshot_permission(
            session,
            viewer_session_id,
            admin_record.id,
        )
        
        session.add(
            SecurityLog(
                event="permission_grant",
                actor=admin,
                detail=(
                    f"Screenshot permission granted to "
                    f"viewer session {viewer_session_id}"
                ),
            )
        )
        await session.commit()

        return {
            "success": True,
            "message": "Screenshot permission granted.",
            "permission": {
                "viewer_session_id": (
                    permission.viewer_session_id
                ),
                "allowed": permission.allowed,
                "granted_at": (
                    permission.granted_at.isoformat()
                    if permission.granted_at
                    else None
                ),
                "granted_by_admin_id": (
                    permission.granted_by_admin_id
                ),
            },
        }


@router.post(
    "/screenshot-permissions/{viewer_session_id}/revoke"
)
async def revoke_viewer_screenshot_permission(
    viewer_session_id: int,
    admin: str = Depends(get_current_admin),
):
    """
    Revoke screenshot permission from one viewer session.
    """

    async with AsyncSessionLocal() as session:

        viewer_result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.id == viewer_session_id
            )
        )

        viewer = (
            viewer_result.scalar_one_or_none()
        )

        if viewer is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        permission = await revoke_screenshot_permission(
            session,
            viewer_session_id,
        )
        
        session.add(
            SecurityLog(
                event="permission_revoke",
                actor=admin,
                detail=(
                    f"Screenshot permission revoked for "
                    f"viewer session {viewer_session_id}"
                ),
            )
        )
        await session.commit()

        if permission is None:
            return {
                "success": True,
                "message": (
                    "Viewer did not have "
                    "screenshot permission."
                ),
                "permission": {
                    "viewer_session_id": viewer_session_id,
                    "allowed": False,
                },
            }

        return {
            "success": True,
            "message": "Screenshot permission revoked.",
            "permission": {
                "viewer_session_id": (
                    permission.viewer_session_id
                ),
                "allowed": permission.allowed,
                "revoked_at": (
                    permission.revoked_at.isoformat()
                    if permission.revoked_at
                    else None
                ),
            },
        }



# ------------------------------------------------------------------
# START RECORDING
# ------------------------------------------------------------------

@router.post("/recording/start")
async def start_recording(
    admin: str = Depends(get_current_admin),
):
    """
    Start recording the currently live DroneStream.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Stream)
            .order_by(Stream.created_at.desc())
            .limit(1)
        )

        stream = result.scalar_one_or_none()

        if not stream:
            return {
                "success": False,
                "message": "No stream exists.",
            }

        if stream.status != "live":
            return {
                "success": False,
                "message": "The stream is not live.",
            }

        if recording_service.is_recording:
            return {
                "success": False,
                "message": "A recording is already in progress.",
            }

        if not stream_manager.is_running:
            return {
                "success": False,
                "message": "The stream source is not running.",
            }

        admin_result = await session.execute(
            select(Admin).where(
                Admin.username == admin
            )
        )

        admin_record = admin_result.scalar_one_or_none()

        if admin_record is None:
            return {
                "success": False,
                "message": "Administrator account not found.",
            }

        try:

            source_track = (
                stream_manager.subscribe_recording()
            )

            recording = recording_service.start(
                stream_id=stream.id,
                source_track=source_track,
                admin_id=admin_record.id,
            )

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Unable to start recording: {error}"
                ),
            }


        try:
            session.add(
                SecurityLog(
                    event="recording",
                    actor=admin,
                    detail=(
                        f"Admin started recording "
                        f"{recording['file_name']}"
                    ),
                )
            )
            await session.commit()
        except Exception:
            pass

        return {
            "success": True,
            "message": "Recording started.",
            "recording": {
                "stream_id": stream.stream_id,
                "file_name": recording["file_name"],
                "started_at": (
                    recording["started_at"].isoformat()
                ),
            },
        }
        
# ------------------------------------------------------------------
# STOP RECORDING
# ------------------------------------------------------------------

@router.post("/recording/stop")
async def stop_recording(
    admin: str = Depends(get_current_admin),
):
    """
    Stop the currently active DroneStream recording.
    """

    if not recording_service.is_recording:
        return {
            "success": False,
            "message": "No recording is currently active.",
        }

    try:

        recording = await recording_service.stop()

    except Exception as error:

        return {
            "success": False,
            "message": (
                f"Unable to stop recording: {error}"
            ),
        }

    async with AsyncSessionLocal() as session:

        recording_record = Recording(
            stream_id=recording["stream_id"],
            started_at=recording["started_at"],
            ended_at=recording["ended_at"],
            duration_seconds=recording["duration_seconds"],
            file_path=recording["file_path"],
            file_name=recording["file_name"],
            file_size_bytes=recording["file_size_bytes"],
            status="completed",
            created_by_admin_id=recording["admin_id"],
        )

        session.add(recording_record)

        session.add(
            SecurityLog(
                event="recording",
                actor=admin,
                detail=(
                    f"Admin stopped recording "
                    f"{recording['file_name']}"
                ),
            )
        )

        await session.commit()
        await session.refresh(recording_record)

        return {
            "success": True,
            "message": "Recording stopped.",
            "recording": {
                "id": recording_record.id,
                "stream_id": recording["stream_id"],
                "file_name": recording["file_name"],
                "file_path": recording["file_path"],
                "started_at": (
                    recording["started_at"].isoformat()
                ),
                "ended_at": (
                    recording["ended_at"].isoformat()
                ),
                "duration_seconds": (
                    recording["duration_seconds"]
                ),
                "file_size_bytes": (
                    recording["file_size_bytes"]
                ),
                "status": recording_record.status,
                "created_by_admin_id": (
                    recording_record.created_by_admin_id
                ),
            },
        }
        
        
# ------------------------------------------------------------------
# RECORDING HISTORY
# ------------------------------------------------------------------

@router.get("/recordings")
async def get_recording_history(
    admin: str = Depends(get_current_admin),
):
    """
    Return the recording history for the administrator.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Recording)
            .order_by(
                Recording.started_at.desc()
            )
        )

        recordings = result.scalars().all()

        return {
            "success": True,
            "count": len(recordings),
            "recordings": [
                {
                    "id": recording.id,
                    "stream_id": recording.stream_id,
                    "file_name": recording.file_name,
                    "file_path": recording.file_path,
                    "duration_seconds": (
                        recording.duration_seconds
                    ),
                    "file_size_bytes": (
                        recording.file_size_bytes
                    ),
                    "started_at": (
                        recording.started_at.isoformat()
                        if recording.started_at
                        else None
                    ),
                    "ended_at": (
                        recording.ended_at.isoformat()
                        if recording.ended_at
                        else None
                    ),
                    "status": recording.status,
                    "created_by_admin_id": (
                        recording.created_by_admin_id
                    ),
                    "created_by_viewer_session_id": (
                        recording.created_by_viewer_session_id
                    ),
                }
                for recording in recordings
            ],
        }
        
# ------------------------------------------------------------------
# RECORDING PLAYBACK
# ------------------------------------------------------------------

@router.get("/recordings/{recording_id}/stream")
async def stream_recording(
    recording_id: int,
    admin: str = Depends(get_current_admin),
):
    """
    Stream a saved recording for in-browser playback.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Recording).where(
                Recording.id == recording_id
            )
        )

        recording = result.scalar_one_or_none()

    if recording is None:
        return {
            "success": False,
            "message": "Recording not found.",
        }

    file_path = Path(recording.file_path)

    if not file_path.exists():
        return {
            "success": False,
            "message": "Recording file is missing on disk.",
        }

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
    )


# ------------------------------------------------------------------
# RECORDING DOWNLOAD
# ------------------------------------------------------------------

@router.get("/recordings/{recording_id}/download")
async def download_recording(
    recording_id: int,
    admin: str = Depends(get_current_admin),
):
    """
    Download a saved recording as an MP4 file.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Recording).where(
                Recording.id == recording_id
            )
        )

        recording = result.scalar_one_or_none()

    if recording is None:
        return {
            "success": False,
            "message": "Recording not found.",
        }

    file_path = Path(recording.file_path)

    if not file_path.exists():
        return {
            "success": False,
            "message": "Recording file is missing on disk.",
        }

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=recording.file_name,
    )
    
# ------------------------------------------------------------------
# DELETE ONE RECORDING
# ------------------------------------------------------------------

@router.delete("/recordings/{recording_id}")
async def delete_recording(
    recording_id: int,
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Recording).where(Recording.id == recording_id)
        )
        recording = result.scalar_one_or_none()
        if recording is None:
            return {"success": False, "message": "Recording not found."}

        file_path = Path(recording.file_path) if recording.file_path else None
        name = recording.file_name

        await session.delete(recording)
        session.add(
            SecurityLog(
                event="recording_delete",
                actor=admin,
                detail=f"Deleted recording {name} (id={recording_id})",
            )
        )
        await session.commit()

        if file_path and file_path.is_file():
            try:
                file_path.unlink()
            except Exception as err:
                print("DroneStream: delete recording file:", err)

        return {"success": True, "message": "Recording deleted."}


# ------------------------------------------------------------------
# CLEAR ALL RECORDINGS
# ------------------------------------------------------------------

@router.delete("/recordings")
async def clear_all_recordings(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Recording))
        rows = result.scalars().all()
        count = 0
        for rec in rows:
            path = Path(rec.file_path) if rec.file_path else None
            await session.delete(rec)
            count += 1
            if path and path.is_file():
                try:
                    path.unlink()
                except Exception as err:
                    print("DroneStream: clear recording file:", err)

        session.add(
            SecurityLog(
                event="recordings_cleared",
                actor=admin,
                detail=f"Cleared {count} recording(s)",
            )
        )
        await session.commit()
        return {
            "success": True,
            "message": f"Deleted {count} recording(s).",
            "count": count,
        }


# ------------------------------------------------------------------
# DELETE ONE SCREENSHOT
# ------------------------------------------------------------------

@router.delete("/screenshots/{screenshot_id}")
async def delete_screenshot(
    screenshot_id: int,
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Screenshot).where(Screenshot.id == screenshot_id)
        )
        shot = result.scalar_one_or_none()
        if shot is None:
            return {"success": False, "message": "Screenshot not found."}

        file_path = Path(shot.file_path) if shot.file_path else None
        name = shot.file_name

        await session.delete(shot)
        session.add(
            SecurityLog(
                event="screenshot_delete",
                actor=admin,
                detail=f"Deleted screenshot {name} (id={screenshot_id})",
            )
        )
        await session.commit()

        if file_path and file_path.is_file():
            try:
                file_path.unlink()
            except Exception as err:
                print("DroneStream: delete screenshot file:", err)

        return {"success": True, "message": "Screenshot deleted."}


# ------------------------------------------------------------------
# CLEAR ALL SCREENSHOTS
# ------------------------------------------------------------------

@router.delete("/screenshots")
async def clear_all_screenshots(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Screenshot))
        rows = result.scalars().all()
        count = 0
        for shot in rows:
            path = Path(shot.file_path) if shot.file_path else None
            await session.delete(shot)
            count += 1
            if path and path.is_file():
                try:
                    path.unlink()
                except Exception as err:
                    print("DroneStream: clear screenshot file:", err)

        session.add(
            SecurityLog(
                event="screenshots_cleared",
                actor=admin,
                detail=f"Cleared {count} screenshot(s)",
            )
        )
        await session.commit()
        return {
            "success": True,
            "message": f"Deleted {count} screenshot(s).",
            "count": count,
        }
        
# ------------------------------------------------------------------
# CAPTURE SCREENSHOT
# ------------------------------------------------------------------

@router.post("/screenshot/capture")
async def capture_screenshot(
    admin: str = Depends(get_current_admin),
):
    """
    Capture one frame from the currently live
    DroneStream and save it as a PNG screenshot.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Stream)
            .order_by(Stream.created_at.desc())
            .limit(1)
        )

        stream = result.scalar_one_or_none()

        if not stream:
            return {
                "success": False,
                "message": "No stream exists.",
            }

        if stream.status != "live":
            return {
                "success": False,
                "message": "The stream is not live.",
            }

        if not stream_manager.is_running:
            return {
                "success": False,
                "message": "The stream source is not running.",
            }

        admin_result = await session.execute(
            select(Admin).where(
                Admin.username == admin
            )
        )

        admin_record = (
            admin_result.scalar_one_or_none()
        )

        if admin_record is None:
            return {
                "success": False,
                "message": (
                    "Administrator account not found."
                ),
            }

        screenshot_subscription = None

        try:

            screenshot_subscription = (
                stream_manager.relay.subscribe(
                    stream_manager.source.video
                )
            )

            screenshot = (
                await screenshot_service.capture(
                    source_track=(
                        screenshot_subscription
                    ),
                    stream_id=stream.id,
                    admin_id=admin_record.id,
                )
            )

            try:
                from backend.app.services.watermark import (
                    apply_screenshot_watermark,
                )
                apply_screenshot_watermark(
                    screenshot["file_path"]
                )
            except Exception as wm_err:
                print(
                    "DroneStream: admin screenshot watermark:",
                    wm_err,
                )
            
            screenshot_record = Screenshot(
                stream_id=stream.id,
                file_path=screenshot["file_path"],
                file_name=screenshot["file_name"],
                file_size_bytes=screenshot["file_size_bytes"],
                captured_at=screenshot["captured_at"],
                created_by_admin_id=admin_record.id,
            )

            session.add(screenshot_record)

            await session.commit()

            await session.refresh(
                screenshot_record
            )

            session.add(
                SecurityLog(
                    event="screenshot",
                    actor=admin,
                    detail=(
                        f"Admin captured screenshot "
                        f"{screenshot['file_name']}"
                    ),
                )
            )
            await session.commit()

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Unable to capture screenshot: "
                    f"{error}"
                ),
            }

        finally:

            if screenshot_subscription is not None:

                try:
                    screenshot_subscription.stop()
                except Exception:
                    pass

        return {
            "success": True,
            "message": "Screenshot captured.",
            "screenshot": {
                "stream_id": (
                    stream.stream_id
                ),
                "file_name": (
                    screenshot["file_name"]
                ),
                "file_path": (
                    screenshot["file_path"]
                ),
                "file_size_bytes": (
                    screenshot["file_size_bytes"]
                ),
                "captured_at": (
                    screenshot[
                        "captured_at"
                    ].isoformat()
                ),
                "width": screenshot["width"],
                "height": screenshot["height"],
                "created_by_admin_id": (
                    screenshot["admin_id"]
                ),
            },
        }  
        
# ------------------------------------------------------------------
# SCREENSHOT HISTORY
# ------------------------------------------------------------------

@router.get("/screenshots")
async def get_screenshot_history(
    admin: str = Depends(get_current_admin),
):
    """
    Return the screenshot history for the administrator.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Screenshot)
            .order_by(
                Screenshot.captured_at.desc()
            )
        )

        screenshots = result.scalars().all()

        return {
            "success": True,
            "count": len(screenshots),
            "screenshots": [
                {
                    "id": screenshot.id,
                    "stream_id": screenshot.stream_id,
                    "file_name": screenshot.file_name,
                    "file_path": screenshot.file_path,
                    "file_size_bytes": (
                        screenshot.file_size_bytes
                    ),
                    "captured_at": (
                        screenshot.captured_at.isoformat()
                        if screenshot.captured_at
                        else None
                    ),
                    "created_by_admin_id": (
                        screenshot.created_by_admin_id
                    ),
                    
                    "created_by_viewer_session_id": (
                        screenshot.created_by_viewer_session_id
                    ),
                }
                for screenshot in screenshots
            ],
        }
        
# ------------------------------------------------------------------
# SCREENSHOT VIEW
# ------------------------------------------------------------------

@router.get("/screenshots/{screenshot_id}/view")
async def view_screenshot(
    screenshot_id: int,
    admin: str = Depends(get_current_admin),
):
    """
    Return a saved screenshot for inline viewing.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Screenshot).where(
                Screenshot.id == screenshot_id
            )
        )

        screenshot = result.scalar_one_or_none()

    if screenshot is None:
        return {
            "success": False,
            "message": "Screenshot not found.",
        }

    file_path = Path(screenshot.file_path)

    if not file_path.exists():
        return {
            "success": False,
            "message": "Screenshot file is missing on disk.",
        }

    return FileResponse(
        path=file_path,
        media_type="image/png",
    )


# ------------------------------------------------------------------
# SCREENSHOT DOWNLOAD
# ------------------------------------------------------------------

@router.get("/screenshots/{screenshot_id}/download")
async def download_screenshot(
    screenshot_id: int,
    admin: str = Depends(get_current_admin),
):
    """
    Download a saved screenshot as a PNG file.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Screenshot).where(
                Screenshot.id == screenshot_id
            )
        )

        screenshot = result.scalar_one_or_none()

    if screenshot is None:
        return {
            "success": False,
            "message": "Screenshot not found.",
        }

    file_path = Path(screenshot.file_path)

    if not file_path.exists():
        return {
            "success": False,
            "message": "Screenshot file is missing on disk.",
        }

    return FileResponse(
        path=file_path,
        media_type="image/png",
        filename=screenshot.file_name,
    ) 
    
# ------------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------------

@router.get("/settings")
async def get_settings(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        row = await get_or_create_settings(session)
        return {
            "success": True,
            "settings": settings_to_dict(row),
        }


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate,
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        row = await get_or_create_settings(session)

        data = body.model_dump(exclude_unset=True)

        for key, value in data.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)

        row.updated_at = datetime.now(timezone.utc)

        session.add(
            SecurityLog(
                event="settings_updated",
                actor=admin,
                detail=f"Settings updated by {admin}",
            )
        )

        await session.commit()
        await session.refresh(row)

        return {
            "success": True,
            "message": "Settings saved.",
            "settings": settings_to_dict(row),
        }


# ------------------------------------------------------------------
# SECURITY LOGS
# ------------------------------------------------------------------

@router.get("/security-logs")
async def get_security_logs(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SecurityLog)
            .order_by(SecurityLog.created_at.desc())
            .limit(200)
        )
        logs = result.scalars().all()

        return {
            "success": True,
            "count": len(logs),
            "logs": [
                {
                    "id": log.id,
                    "event": log.event,
                    "actor": log.actor,
                    "ip_address": log.ip_address,
                    "detail": log.detail,
                    "created_at": (
                        log.created_at.isoformat()
                        if log.created_at
                        else None
                    ),
                }
                for log in logs
            ],
        } 
        
# ------------------------------------------------------------------
# CLEAR SECURITY LOGS
# ------------------------------------------------------------------

@router.delete("/security-logs")
async def clear_security_logs(
    admin: str = Depends(get_current_admin),
    event: str | None = None,
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SecurityLog))
        rows = list(result.scalars().all())

        if event and event.strip() and event.strip().lower() != "all":
            needle = event.strip().lower()
            rows = [
                row
                for row in rows
                if needle in (row.event or "").lower()
            ]

        count = 0
        for row in rows:
            await session.delete(row)
            count += 1

        detail = (
            f"Cleared {count} security log(s)"
            + (
                f" (filter: {event})"
                if event and event.strip().lower() != "all"
                else ""
            )
        )
        session.add(
            SecurityLog(
                event="security_logs_cleared",
                actor=admin,
                detail=detail,
            )
        )
        await session.commit()
        return {
            "success": True,
            "message": detail,
            "count": count,
        }


# ------------------------------------------------------------------
# CLEAR ENDED VIEWER SESSIONS (not currently watching)
# ------------------------------------------------------------------

@router.delete("/viewer-sessions/ended")
async def clear_ended_viewer_sessions(
    admin: str = Depends(get_current_admin),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.status != "watching"
            )
        )
        rows = result.scalars().all()
        count = 0
        for vs in rows:
            await session.delete(vs)
            count += 1

        session.add(
            SecurityLog(
                event="viewer_sessions_cleared",
                actor=admin,
                detail=f"Cleared {count} ended viewer session(s)",
            )
        )
        await session.commit()
        return {
            "success": True,
            "message": f"Cleared {count} ended session(s).",
            "count": count,
        }                