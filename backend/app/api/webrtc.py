import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
    RTCRtpSender,
)

from backend.app.api.streams import stream_state
from backend.app.streaming.manager import stream_manager
from backend.app.auth.dependencies import get_current_broadcaster
from backend.app.database import AsyncSessionLocal
from backend.app.models.account import BroadcasterAccount, StreamOwnership
from backend.app.models.stream import Stream
from backend.app.models.viewer import StreamLink, ViewerEvent, ViewerSession
from backend.app.streaming.ice import create_ice_servers, public_ice_config
from sqlalchemy import select
from datetime import datetime, timezone

import os
import aioice.ice

# Default ON for local dev. Set DRONESTREAM_FORCE_LOOPBACK=0 for production.
FORCE_LOOPBACK = os.environ.get(
    "DRONESTREAM_FORCE_LOOPBACK",
    os.environ.get("FORCE_LOOPBACK", "1"),
).strip().lower() in ("1", "true", "yes", "on")

_original_get_host_addresses = aioice.ice.get_host_addresses

def _loopback_host_addresses(use_ipv4=True, use_ipv6=True):
    addrs = []
    if use_ipv4:
        addrs.append("127.0.0.1")
    return addrs

if FORCE_LOOPBACK:
    aioice.ice.get_host_addresses = _loopback_host_addresses
    print("DroneStream: ICE loopback mode ON (local dev)")
else:
    print("DroneStream: ICE loopback mode OFF (production / STUN)")

router = APIRouter(
    prefix="/api/webrtc",
    tags=["WebRTC"],
)


class WebRTCOffer(BaseModel):
    viewer_token: str
    sdp: str
    type: str
    viewer_session_id: str | None = None


class BroadcastOffer(BaseModel):
    stream_id: str
    sdp: str
    type: str


async def wait_for_ice_gathering_complete(
    peer_connection: RTCPeerConnection,
):
    if peer_connection.iceGatheringState == "complete":
        return

    import asyncio

    completed = asyncio.Event()

    @peer_connection.on("icegatheringstatechange")
    async def on_ice_gathering_state_change():
        if peer_connection.iceGatheringState == "complete":
            completed.set()

    await completed.wait()


def print_sdp_info(label: str, sdp: str):
    print()
    print("=" * 70)
    print(f"DroneStream: {label}")
    print("=" * 70)

    for line in sdp.splitlines():
        if (
            line.startswith("m=video")
            or line.startswith("a=rtpmap:")
            or line.startswith("a=sendrecv")
            or line.startswith("a=sendonly")
            or line.startswith("a=recvonly")
            or line.startswith("a=inactive")
        ):
            print(line)

    print("=" * 70)
    print()


def print_ice_info(label: str, sdp: str):
    print()
    print("=" * 70)
    print(f"DroneStream: {label} ICE")
    print("=" * 70)

    found = False

    for line in sdp.splitlines():
        if line.startswith("a=candidate:"):
            print(line)
            found = True

    if not found:
        print("NO ICE CANDIDATES FOUND")

    print("=" * 70)
    print()


def force_loopback_host_candidates(sdp: str) -> str:
    """Local-dev: map host ICE candidate IPs to 127.0.0.1."""
    lines = []
    for line in sdp.splitlines():
        if line.startswith("a=candidate:") and " typ host" in line:
            line = re.sub(
                r"(\d{1,3}(?:\.\d{1,3}){3})",
                "127.0.0.1",
                line,
                count=1,
            )
        lines.append(line)
    return "\r\n".join(lines) + "\r\n"


@router.get("/ice-config")
async def get_ice_config():
    return public_ice_config()


@router.post("/broadcast/offer")
async def create_broadcast_connection(
    offer: BroadcastOffer,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_start_streams:
        raise HTTPException(status_code=403, detail="You cannot broadcast.")
    if offer.type != "offer":
        raise HTTPException(status_code=400, detail="Expected a WebRTC offer.")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == offer.stream_id,
                StreamOwnership.account_id == account.id,
            )
        )
        stream = result.scalar_one_or_none()
        if stream is None:
            raise HTTPException(status_code=404, detail="Owned stream not found.")
        if stream.status != "starting":
            raise HTTPException(status_code=409, detail="Start the stream before broadcasting.")
        stream_key = str(stream.id)

    ice_servers = create_ice_servers()
    peer_connection = RTCPeerConnection(
        RTCConfiguration(iceServers=ice_servers)
    )
    attached = False

    @peer_connection.on("track")
    async def on_track(track):
        nonlocal attached
        if track.kind != "video":
            track.stop()
            return
        try:
            stream_manager.attach_publisher(
                stream_key,
                track,
                peer_connection,
            )
            attached = True
        except RuntimeError as error:
            print("DroneStream: Publisher attach failed:", repr(error))
            track.stop()
            return

        async with AsyncSessionLocal() as session:
            current = await session.get(Stream, stream.id)
            if current is not None and current.status == "starting":
                current.status = "live"
                current.started_at = datetime.now(timezone.utc)
                await session.commit()

    @peer_connection.on("connectionstatechange")
    async def on_connection_state_change():
        if peer_connection.connectionState in {"failed", "closed"}:
            await stream_manager.stop_stream(stream_key)
            async with AsyncSessionLocal() as session:
                current = await session.get(Stream, stream.id)
                if current is not None and current.status in {"starting", "live"}:
                    current.status = "offline"
                    stopped_at = datetime.now(timezone.utc)
                    current.stopped_at = stopped_at
                    viewers_result = await session.execute(
                        select(ViewerSession).where(
                            ViewerSession.stream_id == current.id,
                            ViewerSession.status == "watching",
                        )
                    )
                    for viewer in viewers_result.scalars().all():
                        viewer.status = "stream_ended"
                        viewer.disconnected_at = stopped_at
                        session.add(ViewerEvent(
                            session_id=viewer.id,
                            event_type="stream_ended",
                            created_at=stopped_at,
                        ))
                    await session.commit()

    try:
        await peer_connection.setRemoteDescription(
            RTCSessionDescription(sdp=offer.sdp, type=offer.type)
        )
        video_transceiver = next(
            (item for item in peer_connection.getTransceivers() if item.kind == "video"),
            None,
        )
        if video_transceiver is None:
            raise ValueError("The broadcaster offer has no video media section.")
        video_transceiver.direction = "recvonly"

        answer = await peer_connection.createAnswer()
        await peer_connection.setLocalDescription(answer)
        await wait_for_ice_gathering_complete(peer_connection)
        if peer_connection.localDescription is None:
            raise RuntimeError("WebRTC did not produce a local answer.")
    except Exception as error:
        await peer_connection.close()
        if attached:
            await stream_manager.stop_stream(stream_key)
        raise HTTPException(
            status_code=400,
            detail=f"Unable to establish broadcaster connection: {error}",
        ) from error

    answer_sdp = peer_connection.localDescription.sdp
    if FORCE_LOOPBACK:
        answer_sdp = force_loopback_host_candidates(answer_sdp)
    return {
        "success": True,
        "sdp": answer_sdp,
        "type": peer_connection.localDescription.type,
    }


@router.post("/offer")
async def create_webrtc_connection(
    offer: WebRTCOffer,
):
    print()
    print("=" * 70)
    print("DroneStream: NEW WEBRTC CONNECTION REQUEST")
    print("=" * 70)

    viewer_stream_key = None
    if offer.viewer_session_id:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ViewerSession, Stream, StreamLink)
                .join(Stream, Stream.id == ViewerSession.stream_id)
                .join(StreamLink, StreamLink.id == ViewerSession.stream_link_id)
                .where(
                    ViewerSession.session_id == offer.viewer_session_id,
                    ViewerSession.status == "watching",
                    StreamLink.token == offer.viewer_token,
                    StreamLink.revoked_at.is_(None),
                    Stream.status == "live",
                )
            )
            authorized = result.first()
            if authorized is not None:
                _, viewer_stream, stream_link = authorized
                if stream_link.expires_at is None or now < stream_link.expires_at:
                    viewer_stream_key = str(viewer_stream.id)

        if viewer_stream_key is None:
            raise HTTPException(
                status_code=403,
                detail="Viewer session is not authorized for a live stream.",
            )
    else:
        if not stream_state["id"]:
            raise HTTPException(status_code=404, detail="No stream exists.")
        if stream_state["status"] != "live":
            raise HTTPException(status_code=409, detail="The stream is not currently live.")
        if not stream_state["viewer_token"] or offer.viewer_token != stream_state["viewer_token"]:
            raise HTTPException(status_code=403, detail="Invalid or revoked viewer link.")

    if viewer_stream_key is not None:
        stream_session = stream_manager.stream_sessions.get(viewer_stream_key)
        if stream_session is None or stream_session.source_track.readyState != "live":
            raise HTTPException(status_code=503, detail="The streaming source is not running.")
    elif not stream_manager.is_running:
        raise HTTPException(status_code=503, detail="The streaming source is not running.")

    print("DroneStream: Viewer token accepted.")
    print("DroneStream: Stream is LIVE.")
    print("DroneStream: Shared media source is running.")

    # --------------------------------------------------------------
    # 5. Browser SDP
    # --------------------------------------------------------------

    print_sdp_info(
        "BROWSER OFFER",
        offer.sdp,
    )

    print_ice_info(
        "BROWSER OFFER",
        offer.sdp,
    )

    # --------------------------------------------------------------
    # 6. Create peer connection
    # --------------------------------------------------------------

    ice_servers = create_ice_servers()

    peer_connection = RTCPeerConnection(
        RTCConfiguration(iceServers=ice_servers)
    )
    if viewer_stream_key is None:
        stream_manager.register_peer(peer_connection)
    else:
        stream_manager.register_stream_peer(viewer_stream_key, peer_connection)

    def unregister_viewer_peer():
        if viewer_stream_key is None:
            stream_manager.unregister_peer(peer_connection)
        else:
            stream_manager.unregister_stream_peer(
                viewer_stream_key,
                peer_connection,
            )

    print("DroneStream: Peer connection created.")

    # --------------------------------------------------------------
    # 7. Get shared video track
    # --------------------------------------------------------------

    try:
        video_track = (
            stream_manager.subscribe_stream(viewer_stream_key)
            if viewer_stream_key is not None
            else stream_manager.subscribe()
        )
        print(
            "DroneStream: Shared video track subscribed "
            "for this viewer."
        )
    except Exception as error:
        if viewer_stream_key is None:
            stream_manager.unregister_peer(peer_connection)
        else:
            stream_manager.unregister_stream_peer(
                viewer_stream_key,
                peer_connection,
            )
        await peer_connection.close()
        print("DroneStream: FAILED to subscribe to shared source:", repr(error))
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access stream source: {error}",
        ) from error

    # --------------------------------------------------------------
    # 8. Find browser video transceiver
    # --------------------------------------------------------------

    video_transceiver = None

    for transceiver in peer_connection.getTransceivers():
        if transceiver.kind == "video":
            video_transceiver = transceiver
            break

    if video_transceiver is None:
        print(
            "DroneStream: Browser did not provide "
            "a video transceiver. Creating one."
        )

        video_transceiver = peer_connection.addTransceiver(
            "video",
            direction="sendrecv",
        )

    else:
        print(
            "DroneStream: Browser video transceiver found."
        )

        video_transceiver.direction = "sendonly"

    # --------------------------------------------------------------
    # 9. Prefer VP8
    # --------------------------------------------------------------

    try:
        capabilities = RTCRtpSender.getCapabilities("video")

        if capabilities and capabilities.codecs:

            vp8_codecs = [
                codec
                for codec in capabilities.codecs
                if codec.mimeType.lower() == "video/vp8"
            ]

            if vp8_codecs:
                video_transceiver.setCodecPreferences(
                    vp8_codecs
                )

                print(
                    "DroneStream: VP8 codec selected."
                )

    except Exception as error:
        print(
            "DroneStream: Codec preference warning:",
            repr(error),
        )

    # --------------------------------------------------------------
    # 10. Attach shared relay track
    # --------------------------------------------------------------

    try:
        video_transceiver.sender.replaceTrack(
            video_track
        )

        print(
            "DroneStream: Shared relay video track attached."
        )

    except Exception as error:
        unregister_viewer_peer()

        await peer_connection.close()

        print(
            "DroneStream: FAILED to attach video track:",
            repr(error),
        )

        raise HTTPException(
            status_code=500,
            detail=f"Unable to attach video track: {error}",
        )

    # --------------------------------------------------------------
    # 11. Connection state
    # --------------------------------------------------------------

    @peer_connection.on("connectionstatechange")
    async def on_connectionstatechange():

        state = peer_connection.connectionState

        print(
            "DroneStream: Connection state:",
            state,
        )

        if state == "connected":

            print("=" * 70)
            print(
                "DroneStream: WEBRTC CONNECTION CONNECTED"
            )
            print("=" * 70)

        elif state == "failed":

            print("=" * 70)
            print(
                "DroneStream: WEBRTC CONNECTION FAILED"
            )
            print("=" * 70)

            unregister_viewer_peer()

        elif state == "disconnected":

            print(
                "DroneStream: WebRTC connection disconnected."
            )

            unregister_viewer_peer()

        elif state == "closed":

            print(
                "DroneStream: WebRTC connection closed."
            )

            unregister_viewer_peer()

    # --------------------------------------------------------------
    # 12. ICE state
    # --------------------------------------------------------------

    @peer_connection.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():

        state = peer_connection.iceConnectionState

        print(
            "DroneStream: ICE state:",
            state,
        )

        if state == "checking":

            print(
                "DroneStream: ICE is checking candidates..."
            )

        elif state == "connected":

            print(
                "DroneStream: ICE CONNECTED."
            )

        elif state == "completed":

            print(
                "DroneStream: ICE COMPLETED."
            )

        elif state == "failed":

            print("=" * 70)
            print("DroneStream: ICE FAILED")
            print("=" * 70)

            print(
                "The browser and server could not establish "
                "a usable ICE connection."
            )

            print("=" * 70)

        elif state == "disconnected":

            print(
                "DroneStream: ICE disconnected."
            )

    # --------------------------------------------------------------
    # 13. Signaling state
    # --------------------------------------------------------------

    @peer_connection.on("signalingstatechange")
    async def on_signalingstatechange():

        print(
            "DroneStream: Signaling state:",
            peer_connection.signalingState,
        )

    # --------------------------------------------------------------
    # 14. Set browser offer
    # --------------------------------------------------------------

    try:

        remote_description = RTCSessionDescription(
            sdp=offer.sdp,
            type=offer.type,
        )

        await peer_connection.setRemoteDescription(
            remote_description
        )

        print(
            "DroneStream: Browser offer accepted."
        )

    except Exception as error:

        unregister_viewer_peer()

        await peer_connection.close()

        print(
            "DroneStream: FAILED to set remote description:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=f"Invalid WebRTC offer: {error}",
        )

    # --------------------------------------------------------------
    # 15. Create answer
    # --------------------------------------------------------------

    try:

        answer = await peer_connection.createAnswer()

        print(
            "DroneStream: WebRTC answer created."
        )

        await peer_connection.setLocalDescription(
            answer
        )

        print(
            "DroneStream: Local description set."
        )

    except Exception as error:

        unregister_viewer_peer()

        await peer_connection.close()

        print(
            "DroneStream: FAILED to create WebRTC answer:",
            repr(error),
        )

        raise HTTPException(
            status_code=500,
            detail=f"Unable to create WebRTC answer: {error}",
        )

    # --------------------------------------------------------------
    # 16. Wait for ICE gathering
    # --------------------------------------------------------------

    try:

        await wait_for_ice_gathering_complete(
            peer_connection
        )

        print(
            "DroneStream: ICE gathering complete."
        )

    except Exception as error:

        print(
            "DroneStream: ICE gathering warning:",
            repr(error),
        )

    # --------------------------------------------------------------
    # 17. Validate answer
    # --------------------------------------------------------------

    if not peer_connection.localDescription:

        unregister_viewer_peer()

        await peer_connection.close()

        print(
            "DroneStream: No local WebRTC description."
        )

        raise HTTPException(
            status_code=500,
            detail="WebRTC server failed to create an answer.",
        )

    answer_sdp = peer_connection.localDescription.sdp
    answer_type = peer_connection.localDescription.type

    # Local-dev: force host candidates to 127.0.0.1
    if FORCE_LOOPBACK:
        answer_sdp = force_loopback_host_candidates(answer_sdp)

    # --------------------------------------------------------------
    # 18. Print answer
    # --------------------------------------------------------------

    print_sdp_info(
        "SERVER ANSWER",
        answer_sdp,
    )

    print_ice_info(
        "SERVER ANSWER",
        answer_sdp,
    )

    # --------------------------------------------------------------
    # 19. Final information
    # --------------------------------------------------------------

    print(
        "DroneStream: Transceiver direction:",
        video_transceiver.direction,
    )

    print(
        "DroneStream: Sender track:",
        video_transceiver.sender.track,
    )

    print(
        "DroneStream: Active peer count:",
        len(stream_manager.peer_connections),
    )

    print("=" * 70)
    print(
        "DroneStream: WEBRTC ANSWER READY"
    )
    print("=" * 70)

    if FORCE_LOOPBACK:
        answer_sdp = force_loopback_host_candidates(answer_sdp)

    return {
        "success": True,
        "sdp": answer_sdp,
        "type": answer_type,
    }