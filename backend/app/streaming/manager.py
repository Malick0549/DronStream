from aiortc import RTCPeerConnection, MediaStreamTrack
from aiortc.contrib.media import MediaRelay

from backend.app.streaming.input_source import FFmpegVideoSource



class StreamMediaSession:
    def __init__(
        self,
        source_track: MediaStreamTrack,
        publisher: RTCPeerConnection | None = None,
    ):
        self.source_track = source_track
        self.publisher = publisher
        self.relay = MediaRelay()
        self.peer_connections: set[RTCPeerConnection] = set()
        if publisher is not None:
            self.peer_connections.add(publisher)


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
        self.stream_sessions: dict[str, StreamMediaSession] = {}
        
        
    @property
    def is_running(self) -> bool:
        return self.source is not None or any(
            session.source_track.readyState == "live"
            for session in self.stream_sessions.values()
        )

    @property
    def active_peer_count(self) -> int:
        return len(self.peer_connections) + sum(
            len(session.peer_connections)
            for session in self.stream_sessions.values()
        )

    @property
    def source_type(self) -> str:
        if self.source is not None:
            return "ffmpeg"
        if any(
            session.publisher is not None
            and session.source_track.readyState == "live"
            for session in self.stream_sessions.values()
        ):
            return "browser"
        if self.is_running:
            return "ffmpeg"
        return "none"

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
            self.source.video,
            buffered=False,
        )
        
    def subscribe_recording(self, stream_key: str | None = None):
        """
        Give the recording system its own relay subscription
        to the shared FFmpeg source.
        """

        if stream_key is not None and stream_key in self.stream_sessions:
            stream_session = self.stream_sessions[stream_key]
            if stream_session.source_track.readyState != "live":
                raise RuntimeError("The stream media source is not running.")
            self.recording_subscription = stream_session.relay.subscribe(
                stream_session.source_track,
                buffered=True,
            )
            return self.recording_subscription

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

    def attach_publisher(
        self,
        stream_key: str,
        source_track: MediaStreamTrack,
        peer_connection: RTCPeerConnection,
    ):
        current = self.stream_sessions.get(stream_key)
        if current is not None and current.source_track.readyState == "live":
            raise RuntimeError("This stream already has a live publisher.")

        self.stream_sessions[stream_key] = StreamMediaSession(
            source_track=source_track,
            publisher=peer_connection,
        )

    def bind_existing_source(self, stream_key: str):
        if self.source is None or self.source.video is None:
            raise RuntimeError("The server capture source is not running.")
        self.stream_sessions[stream_key] = StreamMediaSession(
            source_track=self.source.video,
        )

    def subscribe_stream(self, stream_key: str) -> MediaStreamTrack:
        stream_session = self.stream_sessions.get(stream_key)
        if (
            stream_session is None
            or stream_session.source_track.readyState != "live"
        ):
            raise RuntimeError("The stream does not have a live publisher.")

        return stream_session.relay.subscribe(
            stream_session.source_track,
            buffered=False,
        )

    def has_stream_source(self, stream_key: str) -> bool:
        stream_session = self.stream_sessions.get(stream_key)
        if stream_session is not None:
            return stream_session.source_track.readyState == "live"
        return self.source is not None and self.source.video is not None

    def uses_browser_publisher(self, stream_key: str) -> bool:
        stream_session = self.stream_sessions.get(stream_key)
        return stream_session is not None and stream_session.publisher is not None

    def subscribe_stream_source(
        self,
        stream_key: str,
        buffered: bool = False,
    ) -> MediaStreamTrack:
        stream_session = self.stream_sessions.get(stream_key)
        if stream_session is not None:
            if stream_session.source_track.readyState != "live":
                raise RuntimeError("The stream media source is not running.")
            return stream_session.relay.subscribe(
                stream_session.source_track,
                buffered=buffered,
            )
        if self.source is None or self.source.video is None:
            raise RuntimeError("The stream media source is not running.")
        return self.relay.subscribe(self.source.video, buffered=buffered)

    def register_stream_peer(
        self,
        stream_key: str,
        peer_connection: RTCPeerConnection,
    ):
        stream_session = self.stream_sessions.get(stream_key)
        if stream_session is None:
            raise RuntimeError("The stream media session does not exist.")
        stream_session.peer_connections.add(peer_connection)

    def unregister_stream_peer(
        self,
        stream_key: str,
        peer_connection: RTCPeerConnection,
    ):
        stream_session = self.stream_sessions.get(stream_key)
        if stream_session is not None:
            stream_session.peer_connections.discard(peer_connection)

    async def stop_stream(self, stream_key: str):
        stream_session = self.stream_sessions.pop(stream_key, None)
        if stream_session is None:
            return

        for peer_connection in list(stream_session.peer_connections):
            try:
                await peer_connection.close()
            except Exception as error:
                print(
                    "DroneStream: Error closing stream peer:",
                    repr(error),
                )

        if stream_session.publisher is not None:
            try:
                stream_session.source_track.stop()
            except Exception as error:
                print(
                    "DroneStream: Error stopping stream track:",
                    repr(error),
                )

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