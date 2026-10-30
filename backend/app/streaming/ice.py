
from aiortc import RTCIceServer

from backend.app.config import settings


def create_ice_servers() -> list[RTCIceServer]:
    """
    Return the ICE servers used by DroneStream.
    Loopback mode disables external STUN and TURN servers.
    """

    import os

    force_loopback = os.environ.get(
        "DRONESTREAM_FORCE_LOOPBACK",
        os.environ.get("FORCE_LOOPBACK", "1"),
    ).strip().lower() in ("1", "true", "yes", "on")

    if force_loopback:
        return []

    servers = [
        RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
        RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
    ]

    if (
        settings.turn_urls
        and settings.turn_username
        and settings.turn_password
    ):
        servers.append(
            RTCIceServer(
                urls=settings.turn_urls,
                username=settings.turn_username,
                credential=settings.turn_password,
            )
        )

    return servers


def public_ice_config() -> dict:
    """
    Return ICE configuration for the authorized frontend.
    TURN credentials are required by WebRTC clients to connect.
    """

    servers = create_ice_servers()

    return {
        "iceServers": [
            {
                "urls": server.urls,
                **(
                    {"username": server.username}
                    if server.username
                    else {}
                ),
                **(
                    {"credential": server.credential}
                    if server.credential
                    else {}
                ),
            }
            for server in servers
        ]
    }
