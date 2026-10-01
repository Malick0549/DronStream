import os
import asyncio
import time
from fractions import Fraction

import av

from aiortc import VideoStreamTrack


# ============================================================
# TEST VIDEO LOCATION
# ============================================================

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


# ============================================================
# TEST VIDEO TRACK
# ============================================================

class TestVideoTrack(VideoStreamTrack):
    """
    DroneStream development video source.

    Reads frames directly from test-drone.mp4 using PyAV
    and supplies them directly to aiortc as a WebRTC
    video track.
    """

    def __init__(self):
        super().__init__()

        if not os.path.exists(VIDEO_FILE):
            raise FileNotFoundError(
                f"Test video not found: {VIDEO_FILE}"
            )

        print("=" * 60)
        print("DroneStream: Initializing test video source")
        print("=" * 60)
        print(f"Video file: {VIDEO_FILE}")

        self.container = av.open(VIDEO_FILE)

        self.video_stream = self._find_video_stream()

        if self.video_stream is None:
            self.container.close()
            raise RuntimeError(
                "The test video does not contain a video stream."
            )

        self._fps = self._get_fps()
        self._frame_number = 0
        self._closed = False

        # WebRTC video uses a 90 kHz clock.
        self._time_base = Fraction(1, 90000)

        # Used to deliver frames at the source frame rate.
        self._start_time = time.monotonic()

        print("DroneStream: Video stream detected:")
        print(
            f"  Codec: {self.video_stream.codec_context.name}"
        )
        print(
            f"  Resolution: "
            f"{self.video_stream.codec_context.width}x"
            f"{self.video_stream.codec_context.height}"
        )
        print(
            f"  Source time base: "
            f"{self.video_stream.time_base}"
        )
        print(
            f"  Frame rate: {self._fps:.2f} FPS"
        )
        print("=" * 60)

        self.frame_generator = self._frame_generator()

    # ========================================================
    # FIND VIDEO STREAM
    # ========================================================

    def _find_video_stream(self):
        for stream in self.container.streams:
            if stream.type == "video":
                return stream

        return None

    # ========================================================
    # GET FPS
    # ========================================================

    def _get_fps(self):
        rate = self.video_stream.average_rate

        if rate:
            try:
                fps = float(rate)

                if fps > 0:
                    return fps
            except (TypeError, ValueError):
                pass

        # Safe fallback for the DroneStream test source.
        return 30.0

    # ========================================================
    # FRAME GENERATOR
    # ========================================================

    def _frame_generator(self):
        while not self._closed:

            try:
                for frame in self.container.decode(
                    self.video_stream
                ):
                    if self._closed:
                        return

                    yield frame

                # ------------------------------------------------
                # End of file reached.
                # Restart the test video automatically.
                # ------------------------------------------------

                print(
                    "DroneStream: Test video reached the end. "
                    "Restarting..."
                )

                try:
                    self.container.close()
                except Exception:
                    pass

                self.container = av.open(VIDEO_FILE)
                self.video_stream = self._find_video_stream()

                if self.video_stream is None:
                    raise RuntimeError(
                        "Unable to find video stream after looping."
                    )

            except Exception as error:
                if self._closed:
                    return

                print(
                    "DroneStream: Video decode error:",
                    error
                )
                raise

    # ========================================================
    # WEBRTC FRAME DELIVERY
    # ========================================================

    async def recv(self):
        if self._closed:
            raise RuntimeError(
                "Test video track is closed."
            )

        # Get the next decoded PyAV frame.
        frame = await asyncio.to_thread(
            next,
            self.frame_generator
        )

        # ----------------------------------------------------
        # aiortc can work directly with PyAV VideoFrame.
        #
        # Do NOT convert yuv420p through NumPy.
        # ----------------------------------------------------

        if frame.format.name != "yuv420p":
            frame = frame.reformat(
                format="yuv420p"
            )

        # ----------------------------------------------------
        # Give the frame a stable WebRTC timestamp.
        # Video clock = 90,000 Hz.
        # ----------------------------------------------------

        self._frame_number += 1

        frame.pts = int(
            self._frame_number * 90000 / self._fps
        )

        frame.time_base = self._time_base

        # ----------------------------------------------------
        # Pace the frames.
        #
        # This prevents the video file from being decoded and
        # transmitted as fast as the computer can process it.
        # ----------------------------------------------------

        target_time = (
            self._start_time
            + (
                self._frame_number
                / self._fps
            )
        )

        delay = (
            target_time
            - time.monotonic()
        )

        if delay > 0:
            await asyncio.sleep(delay)

        return frame

    # ========================================================
    # STOP
    # ========================================================

    def stop(self):
        if self._closed:
            return

        print(
            "DroneStream: Stopping test video source."
        )

        self._closed = True

        try:
            self.container.close()
        except Exception:
            pass

        super().stop()


# ============================================================
# SOURCE WRAPPER
# ============================================================

class TestVideoSource:
    """
    Wrapper around the DroneStream test video track.

    Keeps the existing interface used by the WebRTC API.
    """

    def __init__(self):
        self.track = TestVideoTrack()

        # Existing WebRTC API interface.
        self.video = self.track

    def stop(self):
        if self.track:
            try:
                self.track.stop()
            except Exception:
                pass

            self.track = None
            self.video = None