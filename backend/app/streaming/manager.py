from aiortc import RTCPeerConnection
from aiortc.contrib.media import MediaRelay

from backend.app.streaming.input_source import FFmpegVideoSource



class StreamManager:
    """
    Controls the active DroneStream media source.

    One FFmpeg source is shared between all WebRTC viewers
    through MediaRelay.
    """

    def __init__(self):
        self.source: FFmpegVideoSource | None = None
        self.relay = MediaRelay()
        self.peer_connections: set[RTCPeerConnection] = set()
        self.recording_subscription = None
        
        
    @property
    def is_running(self) -> bool:
        return self.source is not None

    def start(
        self,
        input_source: str | None = None,
        width: int = 1280,
        height: int = 720,
    ):
        """
        Start the FFmpeg media source.
        input_source: file path OR capture device name.
        If None, falls back to test VIDEO_FILE.
        """

        if self.source is not None:
            print(
                "DroneStream: FFmpeg stream source "
                "is already running."
            )
            return self.source

        print("=" * 70)
        print("DroneStream: STARTING FFMPEG STREAM SOURCE")
        print("=" * 70)

        from backend.app.streaming.input_source import (
            VIDEO_FILE,
            FFmpegVideoSource,
        )

        source = input_source or VIDEO_FILE

        try:
            self.source = FFmpegVideoSource(
                input_source=source,
                width=width,
                height=height,
            )
        except Exception:
            self.source = None
            raise

        print(
            "DroneStream: FFmpeg stream source started. "
            f"Input: {source} ({width}x{height})"
        )
        print("=" * 70)

        return self.source

    def subscribe(self):
        """
        Give a viewer its own relay subscription
        to the shared FFmpeg source.
        """

        if self.source is None:
            raise RuntimeError(
                "The DroneStream FFmpeg source "
                "is not running."
            )

        return self.relay.subscribe(
            self.source.video
        )
        
    def subscribe_recording(self):
        """
        Give the recording system its own relay subscription
        to the shared FFmpeg source.
        """

        if self.source is None:
            raise RuntimeError(
                "The DroneStream FFmpeg source "
                "is not running."
            )

        self.recording_subscription = (
            self.relay.subscribe(
                self.source.video
            )
        )

        return self.recording_subscription

    def register_peer(
        self,
        peer_connection: RTCPeerConnection,
    ):
        """
        Register an active WebRTC viewer.
        """

        self.peer_connections.add(
            peer_connection
        )

        print(
            "DroneStream: WebRTC peer registered. "
            f"Active peers: "
            f"{len(self.peer_connections)}"
        )

    def unregister_peer(
        self,
        peer_connection: RTCPeerConnection,
    ):
        """
        Remove a WebRTC viewer.
        """

        self.peer_connections.discard(
            peer_connection
        )

        print(
            "DroneStream: WebRTC peer unregistered. "
            f"Active peers: "
            f"{len(self.peer_connections)}"
        )

    async def stop(self):
        """
        Stop the FFmpeg source and close
        all active WebRTC connections.
        """

        print("=" * 70)
        print("DroneStream: STOPPING FFMPEG STREAM SOURCE")
        print("=" * 70)

        peers = list(
            self.peer_connections
        )

        if peers:

            print(
                "DroneStream: Closing "
                f"{len(peers)} active "
                "WebRTC connection(s)."
            )

        for peer_connection in peers:

            try:

                await peer_connection.close()

            except Exception as error:

                print(
                    "DroneStream: Error closing "
                    "peer connection:",
                    repr(error),
                )

        self.peer_connections.clear()

        if self.source is not None:

            try:

                self.source.stop()

            except Exception as error:

                print(
                    "DroneStream: Error stopping "
                    "FFmpeg source:",
                    repr(error),
                )

        self.source = None

        print(
            "DroneStream: FFmpeg stream source stopped."
        )

        print("=" * 70)

    async def restart(self):

        await self.stop()

        return self.start()


stream_manager = StreamManager()