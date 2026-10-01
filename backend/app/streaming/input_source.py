import os
import subprocess
import threading
import time
from fractions import Fraction

import av

from aiortc import VideoStreamTrack

VIDEO_FILE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "streaming",
        "recordings",
        "test-drone.mp4",
    )
)


FFMPEG_PATH = (
    r"C:\Users\ABDUL MALIK\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg.Shared_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-9.0.1-full_build-shared\bin\ffmpeg.exe"
)

DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 30

BYTES_PER_FRAME = (
    DEFAULT_WIDTH
    * DEFAULT_HEIGHT
    * 3
    // 2
)


class FFmpegVideoTrack(VideoStreamTrack):
    """
    VideoStreamTrack powered by an FFmpeg process.

    FFmpeg outputs raw YUV420P frames through stdout.
    """

    def __init__(
        self,
        input_source: str,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
    ):
        super().__init__()

        self.input_source = input_source
        self.width = width
        self.height = height
        self.fps = fps

        self.bytes_per_frame = (
            self.width
            * self.height
            * 3
            // 2
        )

        self.time_base = Fraction(1, 90000)

        self.frame_number = 0
        self.started_at = time.monotonic()

        self.process = None
        self._closed = False

        self._lock = threading.Lock()

        self._start_ffmpeg()

    # --------------------------------------------------------------
    # Start FFmpeg
    # --------------------------------------------------------------

    def _start_ffmpeg(self):
        if not os.path.exists(FFMPEG_PATH):
            raise FileNotFoundError(
                f"FFmpeg executable not found: {FFMPEG_PATH}"
            )

        print("=" * 70)
        print("DroneStream: STARTING FFMPEG INPUT")
        print("=" * 70)
        print(f"Input: {self.input_source}")
        print(f"Resolution: {self.width}x{self.height}")
        print(f"Frame rate: {self.fps} FPS")
        print(f"FFmpeg: {FFMPEG_PATH}")

        is_file = os.path.isfile(self.input_source)

        if is_file:
            # Test video file (looped)
            command = [
                FFMPEG_PATH,
                "-hide_banner",
                "-loglevel", "warning",
                "-stream_loop", "-1",
                "-re",
                "-i", self.input_source,
                "-vf", f"scale={self.width}:{self.height}",
                "-pix_fmt", "yuv420p",
                "-f", "rawvideo",
                "pipe:1",
            ]
        else:
            # Capture card / webcam (Windows DirectShow)
            command = [
                FFMPEG_PATH,
                "-hide_banner",
                "-loglevel", "warning",
                "-f", "dshow",
                "-rtbufsize", "100M",
                "-i", f"video={self.input_source}",
                "-vf", f"scale={self.width}:{self.height}",
                "-pix_fmt", "yuv420p",
                "-f", "rawvideo",
                "pipe:1",
            ]

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )

        except Exception as error:
            print(
                "DroneStream: Failed to start FFmpeg:",
                repr(error),
            )
            raise

        if not self.process.stdout:
            self.process.kill()
            self.process = None

            raise RuntimeError(
                "FFmpeg did not provide a video output pipe."
            )

        print("DroneStream: FFmpeg input started.")
        print("=" * 70)

    # --------------------------------------------------------------
    # Read exactly one video frame
    # --------------------------------------------------------------

    def _read_exact_frame(self):
        if not self.process or not self.process.stdout:
            raise RuntimeError(
                "FFmpeg process is not running."
            )

        remaining = self.bytes_per_frame
        chunks = []

        while remaining > 0:

            chunk = self.process.stdout.read(
                remaining
            )

            if not chunk:
                raise RuntimeError(
                    "FFmpeg stopped producing video frames."
                )

            chunks.append(chunk)
            remaining -= len(chunk)

        return b"".join(chunks)

    # --------------------------------------------------------------
    # Receive frame
    # --------------------------------------------------------------

    async def recv(self):

        if self._closed:
            raise RuntimeError(
                "FFmpeg video track is closed."
            )

        frame_data = await __import__(
            "asyncio"
        ).to_thread(
            self._read_exact_frame
        )

        if self._closed:
            raise RuntimeError(
                "FFmpeg video track was closed."
            )

        frame = av.VideoFrame(
            width=self.width,
            height=self.height,
            format="yuv420p",
        )

        frame.planes[0].update(
            frame_data[
                : self.width * self.height
            ]
        )

        uv_size = (
            self.width
            * self.height
            // 4
        )

        y_size = (
            self.width
            * self.height
        )

        frame.planes[1].update(
            frame_data[
                y_size : y_size + uv_size
            ]
        )

        frame.planes[2].update(
            frame_data[
                y_size + uv_size :
            ]
        )

        self.frame_number += 1

        frame.pts = int(
            self.frame_number
            * 90000
            / self.fps
        )

        frame.time_base = self.time_base

        return frame

    # --------------------------------------------------------------
    # Stop
    # --------------------------------------------------------------

    def stop(self):

        if self._closed:
            return

        print(
            "DroneStream: Stopping FFmpeg video input."
        )

        self._closed = True

        with self._lock:

            if self.process:

                try:
                    if self.process.stdin:
                        self.process.stdin.close()
                except Exception:
                    pass

                try:
                    self.process.terminate()
                    self.process.wait(
                        timeout=2
                    )
                except Exception:

                    try:
                        self.process.kill()
                    except Exception:
                        pass

                self.process = None

        super().stop()


class FFmpegVideoSource:
    """
    Wrapper around FFmpegVideoTrack.
    """

    def __init__(
        self,
        input_source: str,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
    ):

        self.track = FFmpegVideoTrack(
            input_source=input_source,
            width=width,
            height=height,
            fps=fps,
        )

        self.video = self.track

    def stop(self):

        if self.track:

            try:
                self.track.stop()

            except Exception as error:

                print(
                    "DroneStream: Error stopping FFmpeg source:",
                    repr(error),
                )

            self.track = None
            self.video = None