import asyncio
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import av
from aiortc import MediaStreamTrack


RECORDINGS_DIRECTORY = Path(
    "backend"
) / "recordings" / "saved"

RECORDINGS_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True,
)


class RecordingTrack(MediaStreamTrack):
    """
    Receives video frames from the DroneStream media pipeline
    and writes them into an MP4 recording using PyAV.
    """

    kind = "video"

    def __init__(
        self,
        source_track: MediaStreamTrack,
        output_path: str,
    ):
        super().__init__()

        self.source_track = source_track
        self.output_path = output_path

        self.container = None
        self.stream = None

        self.started_at = datetime.now(
            timezone.utc
        )

        self.frame_count = 0

        self._lock = threading.Lock()
        self._closed = False

        self._open_output()

    def _open_output(self):
        output_directory = os.path.dirname(
            self.output_path
        )

        if output_directory:
            os.makedirs(
                output_directory,
                exist_ok=True,
            )

        self.container = av.open(
            self.output_path,
            mode="w",
        )

        self.stream = self.container.add_stream(
            "libx264",
            rate=30,
        )

        self.stream.width = 1280
        self.stream.height = 720
        self.stream.pix_fmt = "yuv420p"

        self.stream.options = {
            "preset": "veryfast",
            "crf": "23",
        }

    async def recv(self):

        if self._closed:
            raise RuntimeError(
                "Recording track is closed."
            )

        frame = await self.source_track.recv()

        if self._closed:
            raise RuntimeError(
                "Recording track is closed."
            )

        with self._lock:

            if self.container is not None:
                for packet in self.stream.encode(
                    frame
                ):
                    self.container.mux(
                        packet
                    )

        self.frame_count += 1

        return frame

    def close(self):

        if self._closed:
            return

        self._closed = True

        with self._lock:

            if self.container is not None:

                try:

                    for packet in self.stream.encode(
                        None
                    ):
                        self.container.mux(
                            packet
                        )

                except Exception as error:

                    print(
                        "DroneStream: Error "
                        "flushing recording:",
                        repr(error),
                    )

                try:
                    self.container.close()

                except Exception as error:

                    print(
                        "DroneStream: Error closing "
                        "recording container:",
                        repr(error),
                    )

                self.container = None

        print(
            "DroneStream: Recording track closed."
        )


class RecordingService:
    """
    Controls the active DroneStream recording.
    """

    def __init__(self):
        self.active_recording = None
        self.recording_track = None
        self.source_subscription = None
        self.recording_task = None

    @property
    def is_recording(self) -> bool:
        return (
            self.active_recording is not None
        )

    async def _record_loop(self):
        """
        Continuously consume frames from the recording
        subscription so they are written to the MP4 file.
        """

        try:

            while self.recording_track is not None:

                await self.recording_track.recv()

        except asyncio.CancelledError:

            return

        except Exception as error:

            print(
                "DroneStream: Recording loop stopped:",
                repr(error),
            )

    def start(
        self,
        stream_id: int,
        source_track: MediaStreamTrack,
        admin_id: int | None = None,
        viewer_session_id: int | None = None,
    ):

        if self.is_recording:
            raise RuntimeError(
                "A recording is already in progress."
            )

        timestamp = datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%d_%H%M%S"
        )

        file_name = (
            f"stream_{stream_id}_"
            f"{timestamp}.mp4"
        )

        output_path = (
            RECORDINGS_DIRECTORY
            / file_name
        )

        recording_track = RecordingTrack(
            source_track=source_track,
            output_path=str(
                output_path
            ),
        )

        self.recording_track = (
            recording_track
        )

        self.recording_task = asyncio.create_task(
            self._record_loop()
        )

        self.active_recording = {
            "stream_id": stream_id,
            "file_name": file_name,
            "file_path": str(
                output_path
            ),
            "started_at": (
                recording_track.started_at
            ),
            "admin_id": admin_id,
            "viewer_session_id": viewer_session_id,
        }

        print("=" * 70)
        print(
            "DroneStream: RECORDING STARTED"
        )
        print(
            f"File: {output_path}"
        )
        print("=" * 70)

        return self.active_recording

    async def stop(self):
        if not self.is_recording:
            raise RuntimeError(
                "No recording is currently active."
            )

        if self.recording_task is not None:

            self.recording_task.cancel()

            try:
                await self.recording_task
            except asyncio.CancelledError:
                pass

            self.recording_task = None

        recording = (
            self.active_recording
        )

        recording_track = (
            self.recording_track
        )

        if recording_track is not None:

            recording_track.close()

        output_path = Path(
            recording["file_path"]
        )

        ended_at = datetime.now(
            timezone.utc
        )

        duration = (
            ended_at
            - recording["started_at"]
        ).total_seconds()

        file_size = (
            output_path.stat().st_size
            if output_path.exists()
            else 0
        )

        result = {
            **recording,
            "ended_at": ended_at,
            "duration_seconds": duration,
            "file_size_bytes": file_size,
        }

        self.active_recording = None
        self.recording_track = None
        self.source_subscription = None
        self.recording_task = None

        print("=" * 70)
        print(
            "DroneStream: RECORDING STOPPED"
        )
        print(
            f"File: {output_path}"
        )
        print(
            f"Duration: {duration:.2f} seconds"
        )
        print(
            f"Size: {file_size} bytes"
        )
        print("=" * 70)

        return result


recording_service = RecordingService()

_stream_recording_services: dict[int, RecordingService] = {}


def get_stream_recording_service(stream_id: int) -> RecordingService:
    service = _stream_recording_services.get(stream_id)
    if service is None:
        service = RecordingService()
        _stream_recording_services[stream_id] = service
    return service